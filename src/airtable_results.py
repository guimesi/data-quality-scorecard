"""Detailed run results to Airtable: DQS_RUNS payload -> one record per result.

Where :mod:`src.airtable_push` upserts one summary row per Data Product,
this module explodes a *persisted run record* (what
:func:`src.persistence.save_run` wrote to ``DQS_RUNS`` - the promoted
columns plus the ``payload`` snapshot) into the rows of the Airtable
results table (``SETTINGS.airtable_results_table``):

- ``OVERALL``   - one per run: overall score, thresholds, row buckets,
  Standard / Custom source scores and the run metadata (source, username,
  domain, config hash, result fingerprint);
- ``DQR``       - one per rule pass rate (Custom rules link to the DQR
  table; Standard rules carry their CDE + dimension instead);
- ``CDE``       - one per CDE score;
- ``DIMENSION`` - one per dimension score.

Records are **upserted on "Result ID"** (``<run id>|<type>|<key>``), so
re-sending a run is idempotent. Only the columns fed by the payload are
written; lookups, formulas and automations in the table ("Rule Name",
"Status", "Is Latest Run", ...) are Airtable's job.

**Linked records** ("Data Product", "DQR", "CDE") are resolved here by
reading the linked table (``AIRTABLE_*_TABLE``) and matching the app's
value against the record's text fields (or only ``AIRTABLE_*_MATCH_FIELD``
when set), then sent as record ids. A value with no (or an ambiguous) match is left blank and reported
in :class:`ResultsPushSummary.unresolved` - nothing is ever auto-created
in the governance tables.

Same contract as :mod:`src.airtable_push`: every failure is an
:class:`~src.airtable_push.AirtablePushError`.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, urlencode

from config.settings import SETTINGS
from src import airtable_push
from src.airtable_push import API_ROOT, AirtablePushError

# Airtable column names (rename / drop via AIRTABLE_RESULTS_FIELD_MAP).
F_RESULT_ID = "Result ID"
F_RUN_ID = "Run ID"
F_TIMESTAMP = "Timestamp"
F_DATA_PRODUCT = "Data Product"
F_RESULT_TYPE = "Result Type"
F_DQR = "DQR"
F_CDE = "CDE"
F_DIMENSION = "Dimension"
F_SCORE = "Score"
F_RULE_TYPE = "Rule Type"
F_THRESHOLD_GREEN = "Threshold Green"
F_THRESHOLD_YELLOW = "Threshold Yellow"
F_TOTAL_ROWS = "Total Rows"
F_GREEN_ROWS = "Green Rows"
F_YELLOW_ROWS = "Yellow Rows"
F_RED_ROWS = "Red Rows"
F_STANDARD_SCORE = "Standard Score"
F_CUSTOM_SCORE = "Custom Score"
F_SOURCE = "Source"
F_USERNAME = "Username"
F_DOMAIN_CODE = "Domain Code"
F_CONFIG_HASH = "Config Hash"
F_RESULT_FINGERPRINT = "Result Fingerprint"

_LINK_FIELDS = (F_DATA_PRODUCT, F_DQR, F_CDE)
_ALL_FIELDS = (
    F_RESULT_ID, F_RUN_ID, F_TIMESTAMP, F_DATA_PRODUCT, F_RESULT_TYPE, F_DQR,
    F_CDE, F_DIMENSION, F_SCORE, F_RULE_TYPE, F_THRESHOLD_GREEN,
    F_THRESHOLD_YELLOW, F_TOTAL_ROWS, F_GREEN_ROWS, F_YELLOW_ROWS, F_RED_ROWS,
    F_STANDARD_SCORE, F_CUSTOM_SCORE, F_SOURCE, F_USERNAME, F_DOMAIN_CODE,
    F_CONFIG_HASH, F_RESULT_FINGERPRINT,
)
# Field types Airtable computes itself - writing to them is rejected.
_COMPUTED_TYPES = frozenset({
    "formula", "rollup", "multipleLookupValues", "count", "autoNumber",
    "createdTime", "lastModifiedTime", "createdBy", "lastModifiedBy",
    "button", "externalSyncSource", "aiText",
})

# CDE columns whose record in the Airtable CDE table is named differently
# from the column (per DP code -> column -> "Field Name" candidates). Only
# needed while that table has no field holding the physical column name:
# links match on any text field, so adding one there makes this redundant.
_CDE_ALIASES: Dict[str, Dict[str, List[str]]] = {
    "SQS": {
        "STATUS": ["Inspection Status"],
        "ALLOTED_HOURS": ["Allotted Hours", "Alloted Hours"],
    },
    "ADR": {
        "COMPLETE_WBC": ["Complete Work breakdown Structure (WBC)"],
        "COST_BASE_MATERIAL_COST": ["Cost Basis"],
        "COST_BASE_MATERIAL_MFC": ["Material Factor Code"],
        "COST_TOTAL_HOURS": ["Total Hours"],
        "QTY_QUANTITY": ["Quantity"],
        "QTY_UOM": ["Quantity Unite of Measure (UOM)",
                    "Quantity Unit of Measure (UOM)"],
        "DESIGN_KEY_PARAMETER_NAMES": ["Design Parameter"],
    },
}

# Airtable accepts at most 10 records per write and 5 requests/second/base.
_BATCH_SIZE = 10
_PAUSE_S = 0.21


@dataclass
class ResultsPushSummary:
    """Outcome of one push: what was written and which links stayed blank."""
    record_ids: List[str] = field(default_factory=list)
    run_ids: List[str] = field(default_factory=list)
    # exactly what was (or, on a dry run, would be) upserted
    rows: List[Dict[str, Any]] = field(default_factory=list)
    # link column -> values that matched no (or several) linked records
    unresolved: Dict[str, List[str]] = field(default_factory=dict)


def is_configured() -> bool:
    return bool(airtable_push.is_configured() and SETTINGS.airtable_results_table)


# =============================================================================
# Run record -> result rows (pure)
# =============================================================================

def _num(value: Any, ndigits: int = 2) -> Optional[float]:
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_result_rows(run: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Explode one DQS_RUNS record into the Airtable result rows.

    Link columns hold the app-side value here (DP code, rule id, CDE
    column); :func:`push_runs` swaps them for record ids. ``None`` values
    are dropped so absent data never blanks an existing cell.
    """
    payload = run.get("payload") or {}
    run_id = str(payload.get("id") or "")
    if not run_id:
        raise AirtablePushError("Run record has no payload id - cannot build "
                                "Result IDs.")
    dp_code = str(payload.get("dp_code") or run.get("dp_code") or "")
    common = {
        F_RUN_ID: run_id,
        # The record's ``ts`` is UTC with an explicit offset; the payload
        # timestamp is naive process-local time, which Airtable would have
        # to guess a time zone for.
        F_TIMESTAMP: run.get("ts") or payload.get("timestamp"),
        F_DATA_PRODUCT: dp_code,
        F_THRESHOLD_GREEN: _num(payload.get("threshold_green")),
        F_THRESHOLD_YELLOW: _num(payload.get("threshold_yellow")),
    }

    def row(result_type: str, key: Optional[str], **extra: Any) -> Dict[str, Any]:
        result_id = "|".join(p for p in (run_id, result_type, key) if p)
        fields = {F_RESULT_ID: result_id, F_RESULT_TYPE: result_type,
                  **common, **extra}
        return {k: v for k, v in fields.items() if v is not None and v != ""}

    standard = _num(payload.get("standard_score"))
    rows = [row(
        "OVERALL", None,
        **{
            F_SCORE: _num(payload.get("overall_score")),
            F_TOTAL_ROWS: _int(payload.get("total_rows")),
            F_GREEN_ROWS: _int(payload.get("rows_green")),
            F_YELLOW_ROWS: _int(payload.get("rows_yellow")),
            F_RED_ROWS: _int(payload.get("rows_red")),
            # "Standard Score" is a single-line-text column in Airtable.
            F_STANDARD_SCORE: None if standard is None else str(standard),
            F_CUSTOM_SCORE: _num(payload.get("custom_score")),
            F_SOURCE: payload.get("source"),
            F_USERNAME: run.get("username"),
            F_DOMAIN_CODE: run.get("domain_code"),
            F_CONFIG_HASH: run.get("config_hash"),
            F_RESULT_FINGERPRINT: payload.get("result_fingerprint"),
        },
    )]
    for rule_id, rate in (payload.get("custom_rule_pass_rates") or {}).items():
        rows.append(row("DQR", str(rule_id).lower(), **{
            F_DQR: str(rule_id), F_SCORE: _num(rate), F_RULE_TYPE: "Custom",
        }))
    for rule_id, rate in (payload.get("rule_pass_rates") or {}).items():
        # Standard rule ids are "<CDE column>::<dimension>".
        cde, _, dimension = str(rule_id).partition("::")
        rows.append(row("DQR", str(rule_id).lower(), **{
            F_CDE: cde, F_DIMENSION: dimension, F_SCORE: _num(rate),
            F_RULE_TYPE: "Standard",
        }))
    for cde, score in (payload.get("cde_scores") or {}).items():
        rows.append(row("CDE", str(cde), **{
            F_CDE: str(cde), F_SCORE: _num(score),
        }))
    for dimension, score in (payload.get("dimension_scores") or {}).items():
        rows.append(row("DIMENSION", str(dimension), **{
            F_DIMENSION: str(dimension), F_SCORE: _num(score),
        }))
    return rows


# =============================================================================
# Linked-record resolution
# =============================================================================

def _norm(value: Any) -> str:
    """Case / punctuation-insensitive key: ``TOTAL_HOURS`` == ``Total Hours``."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _table_url(table: str) -> str:
    return f"{API_ROOT}/{SETTINGS.airtable_base_id}/{quote(table)}"


def _texts(value: Any) -> List[str]:
    """Text values of a cell (lookups / multi-selects come as lists)."""
    items = value if isinstance(value, list) else [value]
    return [str(v) for v in items if isinstance(v, (str, int, float))
            and not isinstance(v, bool) and str(v) != ""]


def _load_link_index(tables: str,
                     match_field: str) -> List[Tuple[str, frozenset, str]]:
    """Index of a linked table. ``tables`` may list alternative names
    separated by ``|`` (``Data Sets|Datasets``): the first one Airtable
    accepts is used."""
    names = [t.strip() for t in tables.split("|") if t.strip()]
    for position, name in enumerate(names, start=1):
        try:
            return _read_link_table(name, match_field)
        except AirtablePushError as exc:
            if position == len(names):
                raise AirtablePushError(
                    f"Could not read the linked table (tried: "
                    f"{', '.join(names)}): {exc}") from exc
    return []


def _read_link_table(table: str,
                     match_field: str) -> List[Tuple[str, frozenset, str]]:
    """Every record of a linked table as ``(record id, match keys, blob)``.

    ``match keys`` are the normalized values of ``match_field`` - or of
    every text field when ``match_field`` is empty; ``blob`` is all the
    record's text normalized, used to break ties."""
    index: List[Tuple[str, frozenset, str]] = []
    offset: Optional[str] = None
    while True:
        query = {"pageSize": 100}
        if offset:
            query["offset"] = offset
        data = airtable_push._request(
            "GET", f"{_table_url(table)}?{urlencode(query)}", None,
            step=f"reading linked table '{table}'")
        for rec in data.get("records") or []:
            fields = rec.get("fields") or {}
            cells = [fields.get(match_field)] if match_field else fields.values()
            keys = frozenset(_norm(t) for cell in cells for t in _texts(cell))
            if not keys:
                continue
            blob = _norm(" ".join(
                t for cell in fields.values() for t in _texts(cell)))
            index.append((rec["id"], keys, blob))
        offset = data.get("offset")
        if not offset:
            return index
        time.sleep(_PAUSE_S)


def _resolve(index: List[Tuple[str, frozenset, str]], candidates: Iterable[str],
             scope: Iterable[str]) -> Optional[str]:
    """Record id matching any of ``candidates``. Several matches (the same
    column name under two Data Products) are narrowed to the one mentioning
    a ``scope`` label; still ambiguous = unresolved."""
    keys = {_norm(c) for c in candidates if c}
    matches = [rec for rec in index if rec[1] & keys]
    if len(matches) > 1:
        labels = [_norm(s) for s in scope if s]
        matches = [rec for rec in matches if any(lb in rec[2] for lb in labels)]
    return matches[0][0] if len(matches) == 1 else None


def _dp_aliases() -> Dict[str, str]:
    pairs = (p.split("=", 1) for p in SETTINGS.airtable_dp_aliases.split(",")
             if "=" in p)
    return {code.strip(): name.strip() for code, name in pairs}


def _link_rows(rows: List[Dict[str, Any]], dp_code: str, dp_labels: List[str],
               indexes: Dict[str, Optional[list]],
               unresolved: Dict[str, List[str]]) -> None:
    """Swap the app-side link values of ``rows`` for record-id lists in
    place; links that are not configured or do not resolve are removed."""
    for fields in rows:
        for column in _LINK_FIELDS:
            value = fields.pop(column, None)
            index = indexes.get(column)
            if value is None or index is None:
                continue
            if column == F_DATA_PRODUCT:
                candidates = dp_labels
            elif column == F_CDE:
                candidates = [value, *_CDE_ALIASES.get(dp_code, {}).get(value, [])]
            else:
                candidates = [value]
            record_id = _resolve(index, candidates, dp_labels)
            if record_id:
                fields[column] = [record_id]
            elif value not in unresolved.setdefault(column, []):
                unresolved[column].append(value)


# =============================================================================
# Push
# =============================================================================

def _field_map() -> Dict[str, str]:
    raw = SETTINGS.airtable_results_field_map
    if not raw:
        return {}
    try:
        mapping = json.loads(raw)
    except ValueError as exc:
        raise AirtablePushError(
            f"AIRTABLE_RESULTS_FIELD_MAP is not valid JSON: {exc}") from exc
    if not isinstance(mapping, dict):
        raise AirtablePushError(
            "AIRTABLE_RESULTS_FIELD_MAP must be a JSON object.")
    return {str(k): str(v or "") for k, v in mapping.items()}


def _upsert(rows: List[Dict[str, Any]], merge_field: str) -> List[str]:
    url = _table_url(SETTINGS.airtable_results_table)
    ids: List[str] = []
    for start in range(0, len(rows), _BATCH_SIZE):
        if start:
            time.sleep(_PAUSE_S)
        batch = rows[start:start + _BATCH_SIZE]
        data = airtable_push._request("PATCH", url, {
            "performUpsert": {"fieldsToMergeOn": [merge_field]},
            # typecast auto-creates select options (Run ID, Result Type...).
            "typecast": True,
            "records": [{"fields": fields} for fields in batch],
        }, step="result upsert")
        try:
            ids.extend(r["id"] for r in data["records"])
        except (KeyError, TypeError) as exc:
            raise AirtablePushError(
                f"Unexpected Airtable upsert response: {data}") from exc
    return ids


def push_runs(runs: List[Dict[str, Any]],
              dry_run: bool = False) -> ResultsPushSummary:
    """Upsert the result rows of every run record in ``runs``.

    ``dry_run`` does everything but the write: the linked tables are read,
    links resolved and the final rows returned in ``summary.rows``.
    """
    if not is_configured():
        raise AirtablePushError(
            "Airtable results are not configured - set AIRTABLE_TOKEN, "
            "AIRTABLE_BASE_ID and AIRTABLE_RESULTS_TABLE (see .env.example)."
        )
    if not runs:
        raise AirtablePushError("No persisted run to send.")
    mapping = _field_map()
    merge_field = mapping.get(F_RESULT_ID, F_RESULT_ID)
    if not merge_field:
        raise AirtablePushError(
            f"'{F_RESULT_ID}' is the upsert key and cannot be dropped.")

    links = {
        F_DATA_PRODUCT: (SETTINGS.airtable_dp_table, SETTINGS.airtable_dp_match_field),
        F_DQR: (SETTINGS.airtable_dqr_table, SETTINGS.airtable_dqr_match_field),
        F_CDE: (SETTINGS.airtable_cde_table, SETTINGS.airtable_cde_match_field),
    }
    indexes = {
        column: _load_link_index(table, match) if table else None
        for column, (table, match) in links.items()
    }
    aliases = _dp_aliases()

    summary = ResultsPushSummary()
    rows: List[Dict[str, Any]] = []
    for run in runs:
        run_rows = build_result_rows(run)
        payload = run.get("payload") or {}
        dp_code = str(payload.get("dp_code") or run.get("dp_code") or "")
        dp_labels = [aliases.get(dp_code, ""), dp_code,
                     str(payload.get("dp_name") or "")]
        _link_rows(run_rows, dp_code, dp_labels, indexes, summary.unresolved)
        rows.extend(run_rows)
        summary.run_ids.append(str(payload.get("id")))
    summary.rows = [
        {mapping.get(k, k): v for k, v in fields.items() if mapping.get(k, k)}
        for fields in rows
    ]
    if not dry_run:
        summary.record_ids = _upsert(summary.rows, merge_field)
    return summary


def inspect_schema() -> Dict[str, Any]:
    """Check the columns this module writes against the base schema.

    Needs a token with the ``schema.bases:read`` scope (the push itself
    does not). Returns ``missing`` (columns not in the results table),
    ``computed`` (columns Airtable computes - a write would be rejected),
    ``types`` (column -> Airtable field type) and ``links`` (link column ->
    the table it points at, that table's primary field and field names:
    what ``AIRTABLE_*_TABLE`` / ``AIRTABLE_*_MATCH_FIELD`` should be).
    """
    if not is_configured():
        raise AirtablePushError("Airtable results are not configured.")
    data = airtable_push._request(
        "GET", f"{API_ROOT}/meta/bases/{SETTINGS.airtable_base_id}/tables",
        None, step="schema read")
    tables = data.get("tables") or []
    by_id = {t.get("id"): t for t in tables}
    wanted = SETTINGS.airtable_results_table
    target = next((t for t in tables if wanted in (t.get("name"), t.get("id"))),
                  None)
    if target is None:
        raise AirtablePushError(
            f"Table '{wanted}' not found in the base. Tables: "
            f"{', '.join(str(t.get('name')) for t in tables)}")
    fields = {}
    for f in target.get("fields") or []:
        fields[f.get("name")] = fields[f.get("id")] = f
    mapping = _field_map()
    report: Dict[str, Any] = {"table": target.get("name"), "missing": [],
                              "computed": [], "types": {}, "links": {}}
    for column in _ALL_FIELDS:
        name = mapping.get(column, column)
        if not name:
            continue
        spec = fields.get(name)
        if spec is None:
            report["missing"].append(name)
            continue
        report["types"][name] = spec.get("type")
        if spec.get("type") in _COMPUTED_TYPES:
            report["computed"].append(name)
        linked = by_id.get((spec.get("options") or {}).get("linkedTableId"))
        if linked is not None:
            names = {f.get("id"): f.get("name") for f in linked.get("fields") or []}
            report["links"][name] = {
                "table": linked.get("name"),
                "primary_field": names.get(linked.get("primaryFieldId")),
                "fields": list(names.values()),
            }
    return report


def latest_runs(dp_codes: Iterable[str]) -> List[Dict[str, Any]]:
    """The most recent persisted run record of each DP (DPs with no
    persisted run are skipped)."""
    from src.persistence import list_runs

    runs: List[Dict[str, Any]] = []
    for code in dp_codes:
        last = list_runs(dp_code=code, limit=1)
        if last:
            runs.append(last[-1])
    return runs


def push_latest_runs(dp_codes: Iterable[str]) -> ResultsPushSummary:
    """Send the latest persisted run of each DP in ``dp_codes``."""
    codes = list(dp_codes)
    runs = latest_runs(codes)
    if not runs:
        raise AirtablePushError(
            f"No persisted run found for {', '.join(codes) or 'any system'} "
            "- is DQS_PERSISTENCE off?")
    return push_runs(runs)
