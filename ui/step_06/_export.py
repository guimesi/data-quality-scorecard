"""CSV / JSON download builders for Step 6.

Both downloads run the *safe* engine variants so incompatible /
not-evaluated rules (already surfaced on the dashboard tabs) don't crash
the export - they're just omitted from the per-rule score columns.
"""
from __future__ import annotations

import io
import json
from datetime import datetime

import pandas as pd

from utils.helpers import score_bucket

# Spreadsheet applications (Excel, Google Sheets, LibreOffice) treat any cell
# whose text begins with one of these characters as a formula. A value pulled
# from the warehouse that starts with one of them would execute when the
# downloaded CSV is opened - the classic "CSV injection" vector. We prefix
# such cells with a single quote so they render as literal text instead.
# This is OWASP's full trigger set: the four formula leaders (= + - @) plus the
# tab (\t) and carriage-return (\r) control characters, which some apps strip
# before parsing so a leading "\t=cmd()" would still execute.
_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _sanitize_csv_cell(value: object) -> object:
    """Neutralize spreadsheet formula injection for a single cell value.

    Only string values that start with a formula trigger are touched; numbers,
    dates and NaN pass through unchanged so the CSV still round-trips to the
    original types. ``value[:1]`` keeps empty strings safe (``""[:1] == ""``).

    The check is on the *raw* first character - no ``strip()``/normalization
    runs first (here or in the caller), so a leading ``\\t`` / ``\\r`` is not
    lost before the comparison.
    """
    if isinstance(value, str) and value[:1] in _CSV_FORMULA_PREFIXES:
        return "'" + value
    return value


def _per_rule_score_columns(dp, config) -> pd.DataFrame:
    """Build per-row, per-rule score columns for both the worst-rows table
    and the CSV export.

    Each rule contributes one column showing the row's score for that rule
    (100 if the row passed, 0 if it failed). The column header embeds the
    rule weight so the user can spot which failures hurt the row score the
    most when scanning a single row. Standard and Custom rules are prefixed
    so they're easy to tell apart; rules that couldn't be evaluated are
    omitted (they're flagged separately on the Dashboard tabs).
    """
    from config.custom_dqr_catalog import get_available_custom_dqr_rules
    from src.custom_dqr_engine import evaluate_custom_rules
    from src.dqr_engine import evaluate_all_safe

    out = pd.DataFrame(index=dp.df.index)

    if config.assignments:
        std_flags, _ = evaluate_all_safe(dp.df, config.assignments, dp.profiles)
        for a in config.assignments:
            if a.rule_id not in std_flags.columns:
                continue
            header = f"STD · {a.cde_column} · {a.dimension} (w={a.weight:.1f}%)"
            out[header] = std_flags[a.rule_id].astype(int) * 100

    if config.custom_assignments:
        cust_flags, _ = evaluate_custom_rules(
            dp.df, config.custom_assignments, dp.system_code
        )
        catalog = {r.id: r for r in get_available_custom_dqr_rules(dp.system_code)}
        for a in config.custom_assignments:
            if a.rule_id not in cust_flags.columns:
                continue
            rule = catalog.get(a.rule_id)
            label = rule.name if rule is not None else a.rule_id
            header = f"CUSTOM · {a.rule_id} · {label} (w={a.weight:.1f}%)"
            out[header] = cust_flags[a.rule_id].astype(int) * 100

    return out


def _reference_join_key(series: pd.Series, dataset: str, source_col: str) -> pd.Series:
    """Derive the join key on the *source* (data-product) side for a
    reference-dataset lookup.

    Mirrors the key construction the custom rules themselves use so the
    appended reference columns line up with the same master rows the rule
    evaluated against:

    - ACCE ``COA`` rolls up to the 3-char ``ICARUS_COA`` group
      (``check_acce_ac1``: ``coa.str.strip().str[:3]``).
    - ADR ``COMPLETE_WBC`` keys on its leading dot-separated segment
      (``check_adr_a1``: ``wbc.str.strip().str.split(".").str[0]``).
    - Everything else (e.g. ``PLANVIEW_ID`` → ``PROJECT_ID``) joins on the
      stripped string value.

    Keyed on ``(dataset, source_col)`` which is unambiguous: a given data
    product is one system, so each reference dataset is reached through a
    single source column.
    """
    base = series.astype(object).astype(str).str.strip()
    if dataset == "ACCE_COA_MASTER" and source_col == "COA":
        return base.str[:3]
    if dataset == "ACCE_COA_MASTER" and source_col == "COMPLETE_WBC":
        return base.str.split(".", n=1).str[0]
    return base


def _reference_columns_for_export(dp, config) -> pd.DataFrame:
    """Build reference-dataset columns to append to the row-level exports.

    For every custom rule assigned to this data product that declares a
    ``reference`` (referential-integrity metadata), left-join the named
    reference dataset onto the data product on the rule's
    ``source_column`` == ``reference_column`` and surface every reference
    column, suffixed with the origin dataset so its provenance is
    unambiguous. A dataset reached by several rules is joined once.

    Returns an empty frame (same index as ``dp.df``) when no rule
    references a dataset or the dataset is unavailable - the exports then
    look exactly as they did before.
    """
    from config.custom_dqr_catalog import get_available_custom_dqr_rules
    from src.reference_data import get_reference_dataset

    out = pd.DataFrame(index=dp.df.index)
    if not config.custom_assignments:
        return out

    catalog = {r.id: r for r in get_available_custom_dqr_rules(dp.system_code)}
    seen_datasets: set[str] = set()
    for a in config.custom_assignments:
        rule = catalog.get(a.rule_id)
        if rule is None or not rule.reference:
            continue
        ref = rule.reference
        dataset = ref.get("reference_dataset")
        source_col = ref.get("source_column")
        ref_col = ref.get("reference_column")
        if not dataset or not source_col or not ref_col:
            continue
        if dataset in seen_datasets or source_col not in dp.df.columns:
            continue
        reference_df = get_reference_dataset(dataset)
        if reference_df is None or ref_col not in reference_df.columns:
            continue
        seen_datasets.add(dataset)

        keys = _reference_join_key(dp.df[source_col], dataset, source_col)
        # Collapse the reference to one row per (normalized) key, first wins,
        # so the lookup index matches the string keys built above.
        lookup_src = reference_df.copy()
        lookup_src["__key__"] = (
            lookup_src[ref_col].astype(object).astype(str).str.strip()
        )
        lookup_src = lookup_src.drop_duplicates(subset="__key__").set_index("__key__")
        for col in reference_df.columns:
            out[f"{col} [{dataset}]"] = keys.map(lookup_src[col]).values
    return out


def _build_rowscores_csv(dp, result, config) -> bytes:
    """Return a CSV (as bytes) with every row of the data product plus its
    score, status, and a per-row score for every Standard and Custom rule
    (column headers carry the rule weight).

    Uses the *safe* evaluators so that incompatible / not-evaluated rules
    (already surfaced on the Dashboard) do not crash the export, they are
    simply omitted from the per-rule score columns.
    """
    rule_scores = _per_rule_score_columns(dp, config)
    ref_cols = _reference_columns_for_export(dp, config)
    out = dp.df.copy()
    out.insert(0, "_row_score", result.row_scores.round(2))
    out.insert(1, "_status", result.row_scores.apply(
        lambda s: score_bucket(
            s, result.threshold_green, result.threshold_yellow
        ).upper()
    ))
    for col in ref_cols.columns:
        out[col] = ref_cols[col]
    for col in rule_scores.columns:
        out[col] = rule_scores[col]
    # Neutralize CSV formula injection on text cells before writing. The
    # numeric columns (_row_score and the per-rule score columns) are left
    # untouched; only object/string columns can carry a formula trigger.
    for col in out.select_dtypes(include=["object"]).columns:
        out[col] = out[col].map(_sanitize_csv_cell)
    buf = io.StringIO()
    # Emit CRLF row terminators - the CSV dialect Excel expects. Cell content
    # is left untouched: a value that legitimately contains newlines is still
    # quoted by the default QUOTE_MINIMAL (so it stays one logical record), but
    # the file is now consistently CRLF instead of mixing LF row endings with
    # any CRLF embedded inside a quoted field - the mix that made Excel split a
    # JSON-bearing row across several visual lines.
    out.to_csv(buf, index=False, lineterminator="\r\n")
    return buf.getvalue().encode("utf-8")


def _build_config_json(dp, result, config) -> bytes:
    """Return a JSON (as bytes) with the full scorecard config and summary."""
    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "system_code": dp.system_code,
        "data_product_name": dp.name,
        "row_count": dp.row_count,
        "column_count": dp.column_count,
        "source_tables": dp.source_tables,
        "cdes": config.cdes,
        "thresholds": {
            "green": result.threshold_green,
            "yellow": result.threshold_yellow,
        },
        "assignments": [
            {
                "cde_column": a.cde_column,
                "dimension": a.dimension,
                "weight_pct": round(a.weight, 4),
                "params": a.params,
                "pass_rate_pct": round(result.rule_pass_rates.get(a.rule_id, 0.0), 2),
            }
            for a in config.assignments
        ],
        "summary": {
            "overall_score": round(result.overall_score, 2),
            "rows_green": result.rows_green,
            "rows_yellow": result.rows_yellow,
            "rows_red": result.rows_red,
            "cde_scores": {k: round(v, 2) for k, v in result.cde_scores.items()},
            "dimension_scores": {k: round(v, 2) for k, v in result.dimension_scores.items()},
            "not_computed_standard_rules": dict(result.not_computed_standard_rules),
        },
    }
    return json.dumps(payload, indent=2, default=str).encode("utf-8")
