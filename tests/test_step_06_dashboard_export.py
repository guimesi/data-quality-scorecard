"""Tests for the Step 6 dashboard export / worst-row helpers.

Covers ``_per_rule_score_columns`` (shared by the Worst rows tab and the
CSV download) and ``_build_rowscores_csv`` (the actual CSV bytes).
"""
from __future__ import annotations

import csv
import io
import os

# Force mock mode before importing anything that reads settings.
os.environ.setdefault("DATA_SOURCE", "mock")

import pandas as pd

from src.models import (
    CustomDQRAssignment,
    DataProduct,
    DataProductConfig,
    DQRAssignment,
)
from src.profiler import profile_dataframe
from src.scorecard import compute_scorecard
from ui.step_06_dashboard import (
    _build_rowscores_csv,
    _per_rule_score_columns,
    _reference_columns_for_export,
)


def _ept_dp(df: pd.DataFrame) -> DataProduct:
    return DataProduct(
        system_code="EPT", name="EPT", df=df,
        source_tables=["T"], profiles=profile_dataframe(df),
    )


def _ept_df_with_one_failure() -> pd.DataFrame:
    return pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", "PV-002", "PV-003", "PV-004"],
        "CODE_OF_RESOURCE": ["LOC-A", None, "LOC-C", "LOC-D"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV", "PROD", "DEC"],
    })


def test_per_rule_score_columns_includes_standard_with_weight_in_header():
    df = _ept_df_with_one_failure()
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=42.5)],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    cols = _per_rule_score_columns(dp, cfg)
    # Exactly one column for the single standard rule, with weight in header.
    assert len(cols.columns) == 1
    header = cols.columns[0]
    assert header.startswith("STD · PLANVIEW_ID · Completeness")
    assert "w=42.5%" in header
    # Every value is 100 (no nulls in PLANVIEW_ID).
    assert cols[header].tolist() == [100, 100, 100, 100]


def test_per_rule_score_columns_includes_custom_with_rule_name_and_weight():
    df = _ept_df_with_one_failure()
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=33.3)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    cols = _per_rule_score_columns(dp, cfg)
    assert len(cols.columns) == 1
    header = cols.columns[0]
    assert header.startswith("CUSTOM · E1 · ")
    assert "w=33.3%" in header
    # Row 1 has null COR → fails E1; the other three pass.
    assert cols[header].tolist() == [100, 0, 100, 100]


def test_per_rule_score_columns_combines_standard_and_custom():
    df = _ept_df_with_one_failure()
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID", "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=50)],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=50)],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 50.0, "custom": 50.0},
    )
    cols = _per_rule_score_columns(dp, cfg)
    headers = list(cols.columns)
    assert any(h.startswith("STD · ") for h in headers)
    assert any(h.startswith("CUSTOM · ") for h in headers)
    assert len(headers) == 2


def test_per_rule_score_columns_omits_not_evaluated_custom_rule(monkeypatch):
    """If a custom rule's reference data is missing, the rule must not be
    surfaced in the per-rule columns (it would have no meaningful score)."""
    import src.reference_data as ref_mod
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)

    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "PV-00002"]})
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E7", weight=100)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    cols = _per_rule_score_columns(dp, cfg)
    assert cols.shape[1] == 0


def test_build_rowscores_csv_has_row_score_status_and_rule_columns():
    df = _ept_df_with_one_failure()
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID", "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100)],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 60.0, "custom": 40.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    csv_bytes = _build_rowscores_csv(dp, result, cfg)
    out = pd.read_csv(io.BytesIO(csv_bytes))
    # Score + status + at least one Standard and one Custom rule column.
    assert "_row_score" in out.columns
    assert "_status" in out.columns
    assert any(c.startswith("STD · ") for c in out.columns)
    assert any(c.startswith("CUSTOM · ") for c in out.columns)
    assert set(out["_status"].unique()).issubset({"GREEN", "YELLOW", "RED"})
    # Row scores match what the scorecard computed.
    assert out["_row_score"].tolist() == result.row_scores.round(2).tolist()


def test_reference_columns_for_export_joins_planview_reference():
    """E2/E7 reference VWS_GP_STANDARD_SHARE on PLANVIEW_ID → PROJECT_ID.
    The helper left-joins it onto the data product and suffixes every
    reference column with the origin dataset name."""
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-99999"]})
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[],
        custom_assignments=[
            CustomDQRAssignment(rule_id="E2", weight=50),
            CustomDQRAssignment(rule_id="E7", weight=50),
        ],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    cols = _reference_columns_for_export(dp, cfg)
    # Same index as the data product, every column suffixed with the dataset.
    assert list(cols.index) == list(df.index)
    assert cols.shape[1] > 0
    assert all(c.endswith(" [VWS_GP_STANDARD_SHARE]") for c in cols.columns)
    # The shared dataset (E2 + E7 both reference it) is joined exactly once.
    project_cols = [c for c in cols.columns if c.startswith("PROJECT_ID ")]
    assert len(project_cols) == 1
    # Known mock keys resolve; an unmatched key leaves the row null.
    matched = cols[project_cols[0]]
    assert matched.iloc[0] == "PV-00001"
    assert pd.isna(matched.iloc[2])


def test_reference_columns_for_export_empty_without_reference_rules():
    """A config with only Standard rules (no referential-integrity custom
    rules) adds no reference columns - the export is unchanged."""
    df = _ept_df_with_one_failure()
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    cols = _reference_columns_for_export(dp, cfg)
    assert cols.shape[1] == 0
    assert list(cols.index) == list(df.index)


def test_reference_columns_skipped_when_dataset_unavailable(monkeypatch):
    """If the reference dataset can't be loaded, no columns are added rather
    than a frame full of nulls."""
    import src.reference_data as ref_mod
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)

    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "PV-00002"]})
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E7", weight=100)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    cols = _reference_columns_for_export(dp, cfg)
    assert cols.shape[1] == 0


def test_build_rowscores_csv_includes_reference_columns():
    """The row-scores CSV carries the reference-dataset columns alongside the
    data-product columns and the per-rule score columns."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002"],
        "CODE_OF_RESOURCE": ["LOC-A", "LOC-B"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV"],
    })
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID", "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E2", weight=100)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    csv_bytes = _build_rowscores_csv(dp, result, cfg)
    out = pd.read_csv(io.BytesIO(csv_bytes))
    assert any(c.endswith("[VWS_GP_STANDARD_SHARE]") for c in out.columns)
    # The original data-product column is still present (and distinct from the
    # suffixed reference column of the same base name).
    assert "PLANVIEW_ID" in out.columns


def _ept_dp_with_note(notes: list[str]) -> tuple[DataProduct, DataProductConfig]:
    """Build an EPT DP whose rows carry an arbitrary text NOTE column plus a
    single Standard Completeness rule, for exercising the CSV writer."""
    df = pd.DataFrame({
        "PLANVIEW_ID": [f"PV-{i:03d}" for i in range(len(notes))],
        "NOTE": notes,
    })
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    return dp, cfg


def test_build_rowscores_csv_neutralizes_spreadsheet_formula_injection():
    """Cells beginning with =, +, -, @, tab, or carriage-return (OWASP's full
    trigger set) are prefixed with a single quote so they cannot execute as
    formulas when the CSV is opened in Excel/Sheets. The leading control char
    must be checked on the raw value, so "\\t=2+2" is caught too."""
    notes = ["=1+1", "+SUM(A1)", "-2+3", "@cmd|'/C calc'!A0", "\t=2+2"]
    dp, cfg = _ept_dp_with_note(notes)
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    csv_bytes = _build_rowscores_csv(dp, result, cfg)
    # dtype=str so pandas doesn't coerce; the leading single quote is part of
    # the stored literal (CSV escaping uses double quotes, not single).
    out = pd.read_csv(io.BytesIO(csv_bytes), dtype=str)
    assert out["NOTE"].tolist() == [
        "'=1+1", "'+SUM(A1)", "'-2+3", "'@cmd|'/C calc'!A0", "'\t=2+2",
    ]


def test_build_rowscores_csv_roundtrips_commas_quotes_and_newlines():
    """Benign text that merely contains commas / quotes / newlines is NOT
    altered (it doesn't start with a formula trigger) and round-trips intact
    through standard CSV quoting."""
    notes = ["a,b,c", 'say "hi"', "line1\nline2"]
    dp, cfg = _ept_dp_with_note(notes)
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    csv_bytes = _build_rowscores_csv(dp, result, cfg)
    out = pd.read_csv(io.BytesIO(csv_bytes), dtype=str)
    assert out["NOTE"].tolist() == notes


def test_build_rowscores_csv_emits_crlf_and_keeps_multiline_json_as_one_record():
    """Option A: the file is written with CRLF (\\r\\n) row terminators - the
    dialect Excel expects - while cell content is left untouched. A value with
    REAL embedded \\r\\n (a JSON payload with quotes and a comma) stays a single
    logical record (RFC4180-quoted), even though it spans several physical
    lines. This asserts the PHYSICAL structure of the bytes, not just a
    pd.read_csv round-trip (which would hide the line-terminator change)."""
    json_val = (
        '{"checks": ["leak", "weld"],\r\n'
        '  "note": "see \\"spec A\\", rev 2",\r\n'
        '  "ok": true}'
    )
    assert json_val.count("\r\n") == 2  # the value carries two real CRLFs
    dp, cfg = _ept_dp_with_note([json_val, "plain value"])
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    csv_bytes = _build_rowscores_csv(dp, result, cfg)

    # (b) PHYSICAL STRUCTURE: the file is consistently CRLF - every line break
    # is part of a \r\n, with no bare LF or CR left over (the LF-row-ending /
    # CRLF-in-field mix was what made Excel split the row).
    assert csv_bytes.count(b"\n") == csv_bytes.count(b"\r\n")  # no lone LF
    assert csv_bytes.count(b"\r") == csv_bytes.count(b"\r\n")  # no lone CR
    # The \r\n tally is fully explained: 3 record terminators (header + 2 data
    # rows) plus the 2 \r\n embedded inside the JSON value. Confirms the row
    # terminator is now CRLF, and that the embedded ones weren't duplicated.
    n_records = 1 + 2  # header + 2 data rows
    assert csv_bytes.count(b"\r\n") == n_records + json_val.count("\r\n")
    # The JSON row really does span multiple PHYSICAL lines (we did not flatten
    # it): splitting raw bytes on CRLF yields more pieces than records.
    physical_lines = [p for p in csv_bytes.split(b"\r\n") if p != b""]
    assert len(physical_lines) == 5  # header + 3 (JSON spans 3) + 1 (plain row)

    # (a) LOGICAL RECORDS: a compliant parser sees exactly the expected records
    # (header + 2 data), each at full width - embedded newlines do NOT spawn
    # extra records. newline="" lets the csv module honor RFC4180 quoting.
    rows = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8"), newline="")))
    assert len(rows) == n_records
    assert {len(r) for r in rows} == {len(rows[0])}  # every record same width
    # Data fidelity: only the row terminator changed, never the cell content -
    # the JSON cell comes back byte-identical.
    note_idx = rows[0].index("NOTE")
    assert rows[1][note_idx] == json_val
