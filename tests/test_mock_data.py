"""Shape / contract tests for src/mock_data.py.

The mock generator is deterministic (``np.random.default_rng(seed=42)``)
and is the data source every test runs against via the autouse
``_force_mock_data_source`` fixture. These tests pin the public surface
(``fetch_mock_table``, ``list_mock_tables``) and verify the per-table
builders produce non-empty DataFrames with the columns downstream
consumers (data_product_builder, profilers, DQR rules) rely on.
"""
from __future__ import annotations

import pandas as pd
import pytest

from src import mock_data

# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------

def test_list_mock_tables_returns_every_registered_name():
    """Every name in the internal ``_MOCK_REGISTRY`` must surface through
    ``list_mock_tables`` so the data product builder can rely on it."""
    listed = mock_data.list_mock_tables()
    assert set(listed.keys()) == set(mock_data._MOCK_REGISTRY.keys())
    assert all(v == "mock" for v in listed.values())


def test_fetch_mock_table_unknown_name_raises_keyerror():
    with pytest.raises(KeyError, match="No mock generator for table"):
        mock_data.fetch_mock_table("THIS_TABLE_DOES_NOT_EXIST")


def test_fetch_mock_table_returns_dataframe_for_every_registered_name():
    """Smoke test: every registered table builds without raising and
    returns a non-empty DataFrame. Catches drift between the registry
    and the actual builder functions."""
    for name in mock_data.list_mock_tables():
        df = mock_data.fetch_mock_table(name)
        assert isinstance(df, pd.DataFrame), name
        assert not df.empty, name


# ---------------------------------------------------------------------------
# Per-system primary tables - key columns and shape
# ---------------------------------------------------------------------------

def test_adr_dim_estimateitemrecord_has_expected_key_columns():
    df = mock_data.fetch_mock_table("ADR_DIM_ESTIMATEITEMRECORD")
    # These columns are what Step 1 chips and the ADR custom rules consume.
    for col in ("PLANVIEW_ID", "ROW_ID", "COMPLETE_WBC", "ITEM_TYPE"):
        assert col in df.columns, col


def test_acce_estimateitemrecord_has_expected_key_columns():
    df = mock_data.fetch_mock_table("ACCE_ESTIMATEITEMRECORD")
    # ACCE's primary table carries COA (the Code of Account), not
    # COMPLETE_WBC; the AC4/AC7/AC8 discipline classifier keys off
    # DESCRIPTION (the former ACCT account-code classifier was retired);
    # JOB_NO is AC2's estimate-job/period proxy.
    for col in ("PLANVIEW_ID", "ROW_ID", "COA", "DESCRIPTION", "JOB_NO"):
        assert col in df.columns, col


def test_ept_onshore_cetdata_has_expected_key_columns():
    df = mock_data.fetch_mock_table("ONSHORE_CETDATA")
    # EPT primary table - drives every E1-E7 custom rule.
    for col in ("PLANVIEW_ID", "WBC_LEVEL_1", "WBC_LEVEL_5",
                "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN",
                "TOTAL_HOURS", "TOTAL_COST_USD"):
        assert col in df.columns, col


def test_quality_sqs_inspection_has_expected_key_columns():
    df = mock_data.fetch_mock_table("CT_SQS_AT_INSPECTION")
    assert not df.empty
    # STATUS + TOTAL_CONSUMED_HOURS drive dq-inspection-12; ALLOTED_HOURS
    # drives dq-inspection-13. INSPECTION_ID / PLANVIEW_ID are the
    # primary identifiers Step 2 / Step 3 build the data product around.
    # PROJECT_CODE backs the Quality domain's sidebar Project filter.
    for col in (
        "INSPECTION_ID", "PLANVIEW_ID", "PROJECT_CODE",
        "STATUS", "TOTAL_CONSUMED_HOURS", "ALLOTED_HOURS",
    ):
        assert col in df.columns, col


def test_quality_sqs_inspection_project_code_format_and_alignment():
    """PROJECT_CODE backs the Quality sidebar filter, must follow the
    deterministic ``QPC-NNN`` shape and stay 1:1 with PLANVIEW_ID so the
    filter has meaningful, project-grain semantics in mock mode."""
    df = mock_data.fetch_mock_table("CT_SQS_AT_INSPECTION")
    non_null = df.dropna(subset=["PROJECT_CODE", "PLANVIEW_ID"])
    assert not non_null.empty
    assert non_null["PROJECT_CODE"].str.match(r"^QPC-\d{3}$").all()
    # PLANVIEW_ID → PROJECT_CODE is a deterministic mapping; no
    # PLANVIEW_ID should resolve to two different PROJECT_CODEs.
    mapping = non_null.groupby("PLANVIEW_ID")["PROJECT_CODE"].nunique()
    assert (mapping == 1).all()


def test_quality_sqs_inspection_includes_dq_inspection_12_pass_and_fail():
    """dq-inspection-12 fails only on ``STATUS == 'Completed'`` paired with
    a NULL ``TOTAL_CONSUMED_HOURS``; the mock must seed at least one such
    row (and at least one Completed PASS row) so both branches are
    reachable in demo mode."""
    df = mock_data.fetch_mock_table("CT_SQS_AT_INSPECTION")
    completed = df["STATUS"] == "Completed"
    assert completed.any(), "no Completed STATUS rows in mock"
    hours_null = df["TOTAL_CONSUMED_HOURS"].isna()
    assert (completed & hours_null).any(), "no Completed+NULL-hours FAIL row"
    assert (completed & ~hours_null).any(), "no Completed+hours PASS row"
    # Out-of-scope rows with NULL hours must exist too (open inspections
    # legitimately have no consumed hours yet) so the ELSE 'PASS' branch
    # is exercised.
    assert (~completed & hours_null).any()


def test_quality_sqs_inspection_includes_dq_inspection_13_null_cases():
    """dq-inspection-13 fails on NULL ``ALLOTED_HOURS``; the mock must
    inject at least one NULL (and keep the majority populated) so both
    branches are reachable in demo mode."""
    df = mock_data.fetch_mock_table("CT_SQS_AT_INSPECTION")
    assert df["ALLOTED_HOURS"].isna().any(), "no NULL ALLOTED_HOURS rows"
    assert df["ALLOTED_HOURS"].notna().sum() > df["ALLOTED_HOURS"].isna().sum()


def test_quality_sqs_inspection_status_has_null_blank_and_offlist_values():
    """STATUS keeps its deliberate gaps (NULL, whitespace-only, off-list)
    so the Standard Completeness / Validity rules stay meaningful on the
    Quality data product."""
    df = mock_data.fetch_mock_table("CT_SQS_AT_INSPECTION")
    assert df["STATUS"].isna().any(), "no NULL STATUS rows in mock"
    blank = df["STATUS"].dropna().astype(str).str.strip() == ""
    assert blank.any(), "no whitespace-only STATUS rows in mock"
    assert (df["STATUS"] == "Cancelled").any(), "no off-list STATUS rows"


# ---------------------------------------------------------------------------
# Reference datasets
# ---------------------------------------------------------------------------

def test_acce_coa_master_has_iso_lookup_columns():
    """A1 / AC1 join on (ICARUS_COA → ISO_COR, SAB); both must be present."""
    df = mock_data._mock_acce_coa_master()
    for col in ("ICARUS_COA", "ISO_COR", "SAB"):
        assert col in df.columns, col
    assert not df.empty
    # The mock intentionally repeats some ICARUS_COA codes so the A1/AC1
    # validator gets to exercise its "multiple ISO mappings per COA"
    # branch; the joiner handles duplicates downstream.


def test_vws_gp_standard_share_has_project_lookup_columns():
    """E7 joins PLANVIEW_ID → PROJECT_ID; E2 reads COUNTRY; E6 / A7 segment
    by E05_DEPARTMENT + BUSINESS."""
    df = mock_data._mock_vws_gp_standard_share()
    for col in ("PROJECT_ID", "COUNTRY", "E05_DEPARTMENT", "BUSINESS"):
        assert col in df.columns, col
    assert not df.empty


# ---------------------------------------------------------------------------
# Deliberate quality issues - the mock is *expected* to contain dirty rows
# so the DQR engine has something to flag downstream.
# ---------------------------------------------------------------------------

def test_adr_primary_contains_some_null_planview_ids():
    """A primary table without any null PLANVIEW_IDs would let A2 pass on
    every row and defeat the demo's purpose."""
    df = mock_data.fetch_mock_table("ADR_DIM_ESTIMATEITEMRECORD")
    assert df["PLANVIEW_ID"].isna().any() or (
        df["PLANVIEW_ID"].astype(str).str.strip() == ""
    ).any()


def test_ept_primary_has_at_least_one_planview_id_set():
    """E7 needs at least one row that *does* resolve so the rule produces
    a non-trivial pass-rate distribution."""
    df = mock_data.fetch_mock_table("ONSHORE_CETDATA")
    assert df["PLANVIEW_ID"].notna().any()


# ---------------------------------------------------------------------------
# Sizing constants - guard against silent drops to ~0 rows
# ---------------------------------------------------------------------------

def test_project_pool_size_matches_constant():
    assert len(mock_data._PLANVIEW_ID_POOL) == mock_data.N_PROJECTS


def test_row_id_pool_size_matches_constant():
    assert len(mock_data._ITEM_ROW_IDS) == mock_data.N_ITEMS


def test_adr_primary_has_row_count_close_to_n_items():
    """The ADR primary table should be ~N_ITEMS wide (one row per item).
    A deliberate-dup row inflates it slightly so we allow a small delta."""
    df = mock_data.fetch_mock_table("ADR_DIM_ESTIMATEITEMRECORD")
    assert mock_data.N_ITEMS <= len(df) <= mock_data.N_ITEMS + 20
