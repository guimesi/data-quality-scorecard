"""Persistence layer: run history, telemetry events, saved projects (F0).

Foundation for the dashboard run history / trend / "what changed" panel,
the adoption + audit telemetry, and saved projects with a version
changelog. This module owns the *plumbing* only - the features that write
and read through it land in their own phases.

One interface, three interchangeable backends selected by
``SETTINGS.persistence_backend`` (``DQS_PERSISTENCE`` env var):

- ``local`` (default) - JSON-lines files under ``.dqs_store/`` at the
  project root (git-ignored). Used until the DQS_* tables exist in
  production; also what local development and tests exercise.
- ``databricks`` - append-only ``DQS_RUNS`` / ``DQS_EVENTS`` /
  ``DQS_PROJECTS`` tables in ``SETTINGS.dbx_catalog``.
  ``SETTINGS.dbx_state_schema`` (DDL + grants in
  ``deploy/databricks/02_persistence_tables.sql``). Writes go through
  :meth:`src.databricks_client.DatabricksClient.execute`.
- ``off`` - a no-op store: nothing is persisted, reads return empty.

Besides the three record kinds, each recorded run's *failed rows* go to
one ``DQS_FAILS_<DOMAIN>_<DP>`` table per (domain, data product) - see
:func:`save_failed_rows` and ``deploy/databricks/04_failed_rows_tables.sql``
(locally: one ``dqs_fails_<domain>_<dp>.jsonl`` file each).

The backend is deliberately decoupled from ``DATA_SOURCE``: a local run
can read real Databricks data while still persisting app state to local
files.

**Fire-and-forget contract**: every public function catches all storage
exceptions, logs them, and returns a benign value (``False`` / ``[]``).
Persistence being down must never break the dashboard.

Records are plain dicts. Every write stamps ``ts`` (UTC ISO-8601) and
``username`` (see :func:`current_username`); reads return records
oldest-first.
"""
from __future__ import annotations

import getpass
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import SETTINGS

logger = logging.getLogger(__name__)

# Project root (parent of src/); default home of the local store.
_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_STORE_DIR = _ROOT / ".dqs_store"

# Record kinds and, for the Databricks backend, their tables and the record
# keys promoted to real (queryable) columns; everything else about a record
# travels in the PAYLOAD column (JSON as STRING).
_KINDS = ("runs", "events", "projects")
_DBX_TABLES = {"runs": "DQS_RUNS", "events": "DQS_EVENTS", "projects": "DQS_PROJECTS"}
_DBX_COLUMNS = {
    "runs": ["ts", "username", "domain_code", "dp_code", "config_hash"],
    "events": ["ts", "username", "event_type", "domain_code"],
    "projects": ["ts", "username", "project_name", "version", "change_summary"],
}

# Failed-row tables: run-level columns (bound once per INSERT) + the
# row-level struct that travels as one JSON array per chunk.
_FAILS_HEADER_COLUMNS = ["run_id", "ts", "username", "domain_code", "dp_code",
                         "config_hash", "total_failed_rows"]
_FAILS_ROW_SCHEMA = ("array<struct<planview_id:string,row_key:string,"
                     "row_score:double,failed_rules:string,row_data:string>>")
_FAILS_CHUNK_ROWS = 2000


def fails_table_name(domain_code: str, dp_code: str) -> str:
    """``DQS_FAILS_<DOMAIN>_<DP>`` - one failed-rows table per (domain,
    data product). Codes are reduced to ``[A-Z0-9_]`` so the name is always
    a safe identifier."""
    slug = re.sub(r"[^A-Z0-9]+", "_", f"{domain_code}_{dp_code}".upper())
    return f"DQS_FAILS_{slug.strip('_')}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# =============================================================================
# Identity
# =============================================================================

_CACHED_USERNAME: Optional[str] = None


def _forwarded_username() -> str:
    """End-user identity forwarded by Databricks Apps, or ``""``.

    Databricks Apps authenticates every viewer and forwards their identity
    to the app process as HTTP headers (``X-Forwarded-Preferred-Username``
    / ``X-Forwarded-Email`` / ``X-Forwarded-User``). Streamlit >= 1.37
    exposes request headers via ``st.context.headers``. Outside a request
    context (unit tests, bare scripts) this simply returns ``""``.
    """
    try:
        import streamlit as st
        headers = st.context.headers
        for key in (
            "X-Forwarded-Preferred-Username",
            "X-Forwarded-Email",
            "X-Forwarded-User",
        ):
            value = headers.get(key)
            if value:
                return str(value)
    except Exception:  # nosec B110 - best-effort identity outside a request
        pass
    return ""


def current_username() -> str:
    """Best-effort identity of the person driving this app process.

    Inside Databricks Apps the platform forwards the authenticated
    viewer's identity via HTTP headers (see :func:`_forwarded_username`).
    Locally there is no forwarded identity, so the OS login is used.
    Falls back to ``"unknown"`` rather than raising; cached for the
    process lifetime (:func:`reset_identity_cache` clears it, for tests).
    """
    global _CACHED_USERNAME
    if _CACHED_USERNAME is not None:
        return _CACHED_USERNAME

    name = _forwarded_username()
    if not name:
        try:
            name = getpass.getuser()
        except Exception:
            logger.warning("OS username lookup failed", exc_info=True)
    _CACHED_USERNAME = name or "unknown"
    return _CACHED_USERNAME


def reset_identity_cache() -> None:
    """Forget the cached username (tests / user switch)."""
    global _CACHED_USERNAME
    _CACHED_USERNAME = None


# =============================================================================
# Backends
# =============================================================================

class LocalStore:
    """JSON-lines files, one per record kind, under ``root``.

    Append-only; corrupt lines (e.g. a half-written record from a killed
    process) are skipped with a warning instead of poisoning every read.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, kind: str) -> Path:
        return self.root / f"{kind}.jsonl"

    def append(self, kind: str, record: Dict[str, Any]) -> None:
        with open(self._path(kind), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def load(self, kind: str) -> List[Dict[str, Any]]:
        path = self._path(kind)
        if not path.exists():
            return []
        out: List[Dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(
                        "Skipping corrupt record %s:%d", path.name, lineno,
                    )
        return out

    def append_failed_rows(self, table: str, header: Dict[str, Any],
                           rows: List[Dict[str, Any]]) -> None:
        with open(self._path(table.lower()), "a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps({**header, **row}, default=str) + "\n")


class DatabricksStore:
    """Append-only DQS_* tables (``deploy/databricks/02_persistence_tables.sql``).

    Indexed record keys become real columns; the full record also travels
    in the PAYLOAD column (JSON serialized to STRING), so ``load`` can
    reconstruct the exact dict that was appended (single source of truth,
    no column drift).
    """

    def _qualified(self, kind: str) -> str:
        return self._qualified_table(_DBX_TABLES[kind])

    def _qualified_table(self, table: str) -> str:
        schema = SETTINGS.dbx_state_schema or SETTINGS.dbx_schema
        return f"{SETTINGS.dbx_catalog}.{schema}.{table}"

    def _client(self):
        from src.databricks_client import get_shared_client
        return get_shared_client()

    def append(self, kind: str, record: Dict[str, Any]) -> None:
        cols = _DBX_COLUMNS[kind]
        col_sql = ", ".join(c.upper() for c in cols)
        placeholders = ", ".join(["%s"] * (len(cols) + 1))
        # Table/columns are internal config, never user input; every value
        # is bound server-side.
        sql = (
            f"INSERT INTO {self._qualified(kind)} ({col_sql}, PAYLOAD) "  # nosec B608
            f"VALUES ({placeholders})"
        )
        values = [record.get(c) for c in cols]
        values.append(json.dumps(record, default=str))
        self._client().execute(sql, values)

    def load(self, kind: str) -> List[Dict[str, Any]]:
        df = self._client().fetch_query(
            f"SELECT PAYLOAD FROM {self._qualified(kind)} ORDER BY TS"  # nosec B608
        )
        out: List[Dict[str, Any]] = []
        for raw in df["PAYLOAD"].tolist():
            try:
                out.append(raw if isinstance(raw, dict) else json.loads(raw))
            except (TypeError, json.JSONDecodeError):
                logger.warning("Skipping unparsable %s payload", kind)
        return out

    def append_failed_rows(self, table: str, header: Dict[str, Any],
                           rows: List[Dict[str, Any]]) -> None:
        """One INSERT per chunk of rows: the run-level values are bound
        once and the rows travel as a single JSON-array parameter that
        the warehouse explodes (``from_json``) - no per-row statement."""
        cols = _FAILS_HEADER_COLUMNS
        col_sql = ", ".join(c.upper() for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))
        # Table name comes from fails_table_name ([A-Z0-9_] only); every
        # value is bound server-side.
        sql = (
            f"INSERT INTO {self._qualified_table(table)} "  # nosec B608
            f"({col_sql}, PLANVIEW_ID, ROW_KEY, ROW_SCORE, FAILED_RULES, ROW_DATA) "
            f"SELECT {placeholders}, r.planview_id, r.row_key, r.row_score, "
            f"r.failed_rules, r.row_data "
            f"FROM (SELECT explode(from_json(%s, '{_FAILS_ROW_SCHEMA}')) AS r)"
        )
        head = [header.get(c) for c in cols]
        client = self._client()
        for start in range(0, len(rows), _FAILS_CHUNK_ROWS):
            chunk = [
                {
                    "planview_id": r.get("planview_id"),
                    "row_key": r.get("row_key"),
                    "row_score": r.get("row_score"),
                    "failed_rules": json.dumps(r.get("failed_rules"), default=str),
                    "row_data": json.dumps(r.get("row_data"), default=str),
                }
                for r in rows[start:start + _FAILS_CHUNK_ROWS]
            ]
            client.execute(sql, head + [json.dumps(chunk, default=str)])


class NullStore:
    """``DQS_PERSISTENCE=off``: persist nothing, read nothing."""

    def append(self, kind: str, record: Dict[str, Any]) -> None:
        pass

    def load(self, kind: str) -> List[Dict[str, Any]]:
        return []

    def append_failed_rows(self, table: str, header: Dict[str, Any],
                           rows: List[Dict[str, Any]]) -> None:
        pass


_STORE: Optional[object] = None


def get_store():
    """Process-wide store singleton for ``SETTINGS.persistence_backend``.

    Unknown backend values fall back to ``local`` (with a warning) so a
    typo in ``DQS_PERSISTENCE`` degrades to the safe default instead of
    disabling persistence silently.
    """
    global _STORE
    if _STORE is not None:
        return _STORE
    backend = SETTINGS.persistence_backend
    if backend == "off":
        _STORE = NullStore()
    elif backend == "databricks":
        _STORE = DatabricksStore()
    else:
        if backend != "local":
            logger.warning(
                "Unknown DQS_PERSISTENCE=%r; falling back to 'local'", backend,
            )
        _STORE = LocalStore(Path(SETTINGS.store_dir) if SETTINGS.store_dir
                            else _DEFAULT_STORE_DIR)
    return _STORE


def reset_store() -> None:
    """Drop the cached store so the next call re-reads SETTINGS (tests)."""
    global _STORE
    _STORE = None


# =============================================================================
# Domain API (fire-and-forget)
# =============================================================================

def _stamp(record: Dict[str, Any]) -> Dict[str, Any]:
    return {"ts": _utc_now_iso(), "username": current_username(), **record}


def _append(kind: str, record: Dict[str, Any]) -> bool:
    try:
        get_store().append(kind, _stamp(record))
        return True
    except Exception:
        logger.warning("Persistence write failed (kind=%s)", kind, exc_info=True)
        return False


def _load(kind: str) -> List[Dict[str, Any]]:
    try:
        return get_store().load(kind)
    except Exception:
        logger.warning("Persistence read failed (kind=%s)", kind, exc_info=True)
        return []


def save_run(dp_code: str, domain_code: str, payload: Dict[str, Any],
             config_hash: str = "") -> bool:
    """Persist one scorecard run snapshot for ``dp_code``.

    ``payload`` is the feature-owned snapshot (phase 1 will pass the
    ML-Lab-compatible scorecard snapshot); ``config_hash`` lets readers
    tell "the data changed" apart from "the configuration changed".
    """
    return _append("runs", {
        "domain_code": domain_code, "dp_code": dp_code,
        "config_hash": config_hash, "payload": payload,
    })


def save_failed_rows(domain_code: str, dp_code: str, run_id: str,
                     rows: List[Dict[str, Any]], total_failed_rows: int,
                     config_hash: str = "") -> bool:
    """Persist the failed rows of run ``run_id`` in the (domain, DP)'s
    ``DQS_FAILS_*`` table.

    Each row is ``{planview_id, row_key, row_score, failed_rules, row_data}``
    (see :func:`src.failed_rows.collect_failed_rows`). ``total_failed_rows``
    is the run's full failing-row count, stored on every row so readers can
    tell when ``rows`` was capped. ``run_id`` is the DQS_RUNS payload id.
    """
    if not rows:
        return True
    try:
        header = _stamp({
            "run_id": run_id, "domain_code": domain_code, "dp_code": dp_code,
            "config_hash": config_hash,
            "total_failed_rows": int(total_failed_rows),
        })
        get_store().append_failed_rows(
            fails_table_name(domain_code, dp_code), header, rows)
        return True
    except Exception:
        logger.warning("Failed-rows write failed (%s/%s)", domain_code, dp_code,
                       exc_info=True)
        return False


def list_runs(dp_code: Optional[str] = None,
              limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Run snapshots oldest-first, optionally for one DP / capped to the
    most recent ``limit``."""
    runs = _load("runs")
    if dp_code is not None:
        runs = [r for r in runs if r.get("dp_code") == dp_code]
    return runs[-limit:] if limit else runs


def log_event(event_type: str, payload: Optional[Dict[str, Any]] = None,
              domain_code: str = "") -> bool:
    """Record one telemetry / audit event (adoption metrics, phase 2)."""
    return _append("events", {
        "event_type": event_type, "domain_code": domain_code,
        "payload": payload or {},
    })


def list_events(event_type: Optional[str] = None,
                limit: Optional[int] = None) -> List[Dict[str, Any]]:
    events = _load("events")
    if event_type is not None:
        events = [e for e in events if e.get("event_type") == event_type]
    return events[-limit:] if limit else events


def save_project_version(project_name: str, payload: Dict[str, Any],
                         change_summary: str = "") -> bool:
    """Persist a new immutable version of a saved project (phase 3).

    Versions are append-only - each save is a new row numbered
    ``max(existing) + 1`` - so the version list *is* the audit changelog
    (who, when, what changed via ``change_summary``).
    """
    try:
        existing = [
            int(v.get("version", 0))
            for v in _load("projects")
            if v.get("project_name") == project_name
        ]
        version = (max(existing) + 1) if existing else 1
    except Exception:
        logger.warning("Version lookup failed for %r", project_name, exc_info=True)
        version = 1
    return _append("projects", {
        "project_name": project_name, "version": version,
        "change_summary": change_summary, "payload": payload,
    })


def list_project_versions(project_name: Optional[str] = None,
                          limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Saved-project versions oldest-first (the audit changelog)."""
    versions = _load("projects")
    if project_name is not None:
        versions = [v for v in versions if v.get("project_name") == project_name]
    return versions[-limit:] if limit else versions
