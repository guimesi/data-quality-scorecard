"""Report store: keeps every run's Data Quality Report artefacts so the
app can serve the interactive edition at ``GET /reports/<run_id>``.

SharePoint sanitises ``.html`` files, so the interactive report is
hosted by the app and SharePoint receives a link. The artefacts of a run
(:class:`~ui.step_06.report.models.ReportArtifacts`) are stored under
one ``run_id`` as four objects:

- ``<run_id>.html``      interactive edition (served as ``text/html``)
- ``<run_id>.pdf``       PDF edition (when it could be rendered)
- ``<run_id>.print.html`` print-ready HTML (the PDF edition's source)
- ``<run_id>.json``      metadata (publisher columns, filenames)

Three interchangeable backends selected by ``SETTINGS.report_store``
(``DQS_REPORT_STORE``):

- ``local``  - files under ``<store_dir>/reports/`` (default; what local
  development and tests use).
- ``volume`` - a Unity Catalog Volume (``SETTINGS.report_volume_path``,
  e.g. ``/Volumes/<catalog>/<schema>/dq_reports``) through the Databricks
  Files API, with the same headless identity as the SQL client. This is
  the production backend: the app container's disk does not survive
  restarts, a Volume does.
- ``off``    - nothing is stored; every read returns ``None``.

**Fire-and-forget contract** for writes: :func:`save_artifacts` catches
storage exceptions, logs them and returns ``False`` - a broken store
must never break the dashboard. Reads propagate nothing either: an
unknown run is simply ``None``.

``run_id`` values are validated (:func:`is_valid_run_id`) before they
touch any path, so a request cannot escape the store directory.
"""
from __future__ import annotations

import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import SETTINGS

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_STORE_DIR = _ROOT / ".dqs_store"

# Object kinds and their file suffixes / MIME types.
KINDS: Dict[str, Dict[str, str]] = {
    "html": {"suffix": ".html", "mime": "text/html; charset=utf-8"},
    "pdf": {"suffix": ".pdf", "mime": "application/pdf"},
    "pdf_html": {"suffix": ".print.html", "mime": "text/html; charset=utf-8"},
    "metadata": {"suffix": ".json", "mime": "application/json"},
}

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")


def is_valid_run_id(run_id: object) -> bool:
    """Run identifiers are short ``[A-Za-z0-9_-]`` tokens - never a path."""
    return isinstance(run_id, str) and bool(_RUN_ID_RE.match(run_id))


def _object_name(run_id: str, kind: str) -> str:
    if not is_valid_run_id(run_id):
        raise ValueError(f"invalid run_id {run_id!r}")
    return f"{run_id}{KINDS[kind]['suffix']}"


# =============================================================================
# Backends
# =============================================================================

class LocalReportStore:
    """Files under ``root`` (one directory, flat)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def put(self, run_id: str, kind: str, data: bytes) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / _object_name(run_id, kind)).write_bytes(data)

    def get(self, run_id: str, kind: str) -> Optional[bytes]:
        path = self.root / _object_name(run_id, kind)
        return path.read_bytes() if path.is_file() else None

    def list_run_ids(self) -> List[str]:
        if not self.root.is_dir():
            return []
        suffix = KINDS["metadata"]["suffix"]
        return sorted(
            p.name[:-len(suffix)] for p in self.root.glob(f"*{suffix}")
            if is_valid_run_id(p.name[:-len(suffix)])
        )


class VolumeReportStore:
    """A Unity Catalog Volume directory via the Databricks Files API.

    Identity is resolved by ``databricks.sdk`` exactly like the SQL
    client (app service principal in Databricks Apps, PAT locally).
    """

    def __init__(self, directory: str, client: Any = None) -> None:
        if not directory or not directory.startswith("/Volumes/"):
            raise ValueError(
                "DQS_REPORT_VOLUME must be a Unity Catalog Volume path "
                "(/Volumes/<catalog>/<schema>/<volume>[/<dir>])"
            )
        self.directory = directory.rstrip("/")
        self._client = client

    def _files(self):
        if self._client is None:
            from databricks.sdk import WorkspaceClient  # type: ignore

            self._client = WorkspaceClient()
        return self._client.files

    def _path(self, run_id: str, kind: str) -> str:
        return f"{self.directory}/{_object_name(run_id, kind)}"

    def put(self, run_id: str, kind: str, data: bytes) -> None:
        files = self._files()
        files.create_directory(self.directory)
        files.upload(self._path(run_id, kind), io.BytesIO(data), overwrite=True)

    def get(self, run_id: str, kind: str) -> Optional[bytes]:
        from databricks.sdk.errors import NotFound  # type: ignore

        try:
            response = self._files().download(self._path(run_id, kind))
        except NotFound:
            return None
        contents = response.contents
        return contents.read() if hasattr(contents, "read") else bytes(contents)

    def list_run_ids(self) -> List[str]:
        from databricks.sdk.errors import NotFound  # type: ignore

        suffix = KINDS["metadata"]["suffix"]
        try:
            entries = list(self._files().list_directory_contents(self.directory))
        except NotFound:
            return []
        out = []
        for entry in entries:
            name = str(getattr(entry, "name", "") or "")
            if name.endswith(suffix) and is_valid_run_id(name[:-len(suffix)]):
                out.append(name[:-len(suffix)])
        return sorted(out)


class NullReportStore:
    """``DQS_REPORT_STORE=off``: store nothing, serve nothing."""

    def put(self, run_id: str, kind: str, data: bytes) -> None:
        pass

    def get(self, run_id: str, kind: str) -> Optional[bytes]:
        return None

    def list_run_ids(self) -> List[str]:
        return []


_STORE: Optional[object] = None


def get_report_store():
    """Process-wide store singleton for ``SETTINGS.report_store``.

    Unknown backend values fall back to ``local`` with a warning; a
    ``volume`` backend without a Volume path degrades to ``off``.
    """
    global _STORE
    if _STORE is not None:
        return _STORE
    backend = (SETTINGS.report_store or "local").lower()
    if backend == "off":
        _STORE = NullReportStore()
    elif backend == "volume":
        try:
            _STORE = VolumeReportStore(SETTINGS.report_volume_path)
        except ValueError:
            logger.warning("DQS_REPORT_STORE=volume without a valid "
                           "DQS_REPORT_VOLUME; reports are not stored")
            _STORE = NullReportStore()
    else:
        if backend != "local":
            logger.warning("Unknown DQS_REPORT_STORE=%r; falling back to "
                           "'local'", backend)
        root = (Path(SETTINGS.store_dir) if SETTINGS.store_dir
                else _DEFAULT_STORE_DIR) / "reports"
        _STORE = LocalReportStore(root)
    return _STORE


def reset_report_store() -> None:
    """Drop the cached store so the next call re-reads SETTINGS (tests)."""
    global _STORE
    _STORE = None


def is_enabled() -> bool:
    return not isinstance(get_report_store(), NullReportStore)


# =============================================================================
# Domain API
# =============================================================================

def save_artifacts(artifacts) -> bool:
    """Store every artefact of a run under its ``run_id``.

    Returns ``True`` when all objects were written. Storage failures are
    logged and return ``False`` (fire-and-forget) - the download buttons
    keep working from the in-memory artefacts.
    """
    run_id = artifacts.run_id
    if not is_valid_run_id(run_id):
        logger.warning("Refusing to store report with invalid run_id %r", run_id)
        return False
    store = get_report_store()
    if isinstance(store, NullReportStore):
        return False
    objects = [("html", artifacts.html), ("pdf_html", artifacts.pdf_html)]
    if artifacts.pdf:
        objects.append(("pdf", artifacts.pdf))
    objects.append(("metadata", json.dumps({
        "run_id": run_id,
        "domain_code": artifacts.domain_code,
        "generated_at": artifacts.generated_at,
        "filenames": dict(artifacts.filenames),
        "has_pdf": bool(artifacts.pdf),
        **{k: v for k, v in artifacts.metadata.items()
           if k not in ("run_id", "domain_code", "generated_at")},
    }, default=str).encode("utf-8")))
    try:
        for kind, data in objects:
            store.put(run_id, kind, data)
        return True
    except Exception:
        logger.warning("Report store write failed (run_id=%s)", run_id,
                       exc_info=True)
        return False


def load_report(run_id: str, kind: str = "html") -> Optional[bytes]:
    """The stored object of ``run_id`` (``None`` when unknown / disabled /
    invalid id / storage error)."""
    if kind not in KINDS or not is_valid_run_id(run_id):
        return None
    try:
        return get_report_store().get(run_id, kind)
    except Exception:
        logger.warning("Report store read failed (run_id=%s, kind=%s)",
                       run_id, kind, exc_info=True)
        return None


def load_metadata(run_id: str) -> Optional[Dict[str, Any]]:
    raw = load_report(run_id, "metadata")
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Unparsable report metadata (run_id=%s)", run_id)
        return None
    return data if isinstance(data, dict) else None


def list_reports() -> List[Dict[str, Any]]:
    """Metadata of every stored run, newest first."""
    try:
        ids = get_report_store().list_run_ids()
    except Exception:
        logger.warning("Report store listing failed", exc_info=True)
        return []
    out = []
    for run_id in ids:
        meta = load_metadata(run_id)
        # Only metadata written by ``save_artifacts`` (stray files in the
        # directory are ignored).
        if meta is not None and meta.get("run_id") == run_id:
            out.append(meta)
    out.sort(key=lambda m: str(m.get("generated_at", "")), reverse=True)
    return out


def report_url(run_id: str, kind: str = "html") -> str:
    """Path of the served artefact (relative to the app origin)."""
    base = f"/reports/{run_id}"
    return base if kind == "html" else f"{base}/{kind}"
