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
    # EXPECTED_SHIP_DATE drives SQ4; PO_REQUIRED_SHIP_DATE drives SQ5;
    # INSPECTION_ID / PLANVIEW_ID are the primary identifiers Step 2 /
    # Step 3 build the data product around. PROJECT_CODE backs the
    # Quality domain's sidebar Project filter.
    for col in (
        "INSPECTION_ID", "PLANVIEW_ID", "PROJECT_CODE",
        "EXPECTED_SHIP_DATE", "PO_REQUIRED_SHIP_DATE",
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


def test_quality_sqs_inspection_includes_null_expected_ship_dates():
    """SQ4 fails on NULL ``EXPECTED_SHIP_DATE``; the mock must inject at
    least one NULL or the rule's demo-mode FAIL path is unreachable."""
    df = mock_data.fetch_mock_table("CT_SQS_AT_INSPECTION")
    assert df["EXPECTED_SHIP_DATE"].isna().any()


def test_quality_sqs_inspection_includes_sq5_fail_cases():
    """SQ5 fails when ``EXPECTED_SHIP_DATE > PO_REQUIRED_SHIP_DATE``; the
    mock must inject at least one such case (and at least one NULL on the
    PO side) so the demo-mode FAIL / NULL-PASS paths are reachable."""
    df = mock_data.fetch_mock_table("CT_SQS_AT_INSPECTION")
    assert df["PO_REQUIRED_SHIP_DATE"].isna().any()
    expected = pd.to_datetime(df["EXPECTED_SHIP_DATE"], errors="coerce")
    po_required = pd.to_datetime(df["PO_REQUIRED_SHIP_DATE"], errors="coerce")
    after_po = expected.notna() & po_required.notna() & (expected > po_required)
    assert after_po.any()


def test_quality_sqs_inspection_includes_sq6_pass_and_fail_cases():
    """SQ6 needs both PASS and FAIL demo coverage: at least one row with
    a value from the allowed controlled-vocabulary set, and at least one
    off-list / NULL row so the FAIL path is reachable in mock mode."""
    from src.custom_dqr_engine import SQS_SQ6_ALLOWED_VALUES

    df = mock_data.fetch_mock_table("CT_SQS_AT_INSPECTION")
    allowed = set(SQS_SQ6_ALLOWED_VALUES)
    in_allowed = df["INSPECTION_TYPE"].isin(allowed)
    assert in_allowed.any(), "no INSPECTION_TYPE rows in the allowed set"
    assert (~in_allowed).any(), "no INSPECTION_TYPE rows outside the allowed set"
    # NULL must be present specifically (the off-list bucket also FAILs
    # SQ6, but NULL is a distinct production failure mode worth seeding).
    assert df["INSPECTION_TYPE"].isna().any()


def test_quality_sqs_inspection_includes_sq7_pass_and_fail_cases():
    """SQ7 (WORK_CRITICALITY in allowed set) needs the same coverage as
    SQ6: PASS rows in the allowed vocabulary, off-list FAIL rows, and at
    least one NULL so both FAIL paths are reachable in mock mode."""
    from src.custom_dqr_engine import SQS_SQ7_ALLOWED_VALUES

    df = mock_data.fetch_mock_table("CT_SQS_AT_INSPECTION")
    assert "WORK_CRITICALITY" in df.columns
    allowed = set(SQS_SQ7_ALLOWED_VALUES)
    in_allowed = df["WORK_CRITICALITY"].isin(allowed)
    assert in_allowed.any(), "no WORK_CRITICALITY rows in the allowed set"
    assert (~in_allowed).any(), "no WORK_CRITICALITY rows outside the allowed set"
    assert df["WORK_CRITICALITY"].isna().any()


def test_quality_sqs_inspection_includes_sq8_null_and_blank_cases():
    """SQ8 (Completeness on STATUS) needs both NULL and whitespace-only
    rows in the mock so the demo-mode FAIL branches are reachable."""
    df = mock_data.fetch_mock_table("CT_SQS_AT_INSPECTION")
    assert df["STATUS"].isna().any(), "no NULL STATUS rows in mock"
    blank = df["STATUS"].dropna().astype(str).str.strip() == ""
    assert blank.any(), "no whitespace-only STATUS rows in mock"


def test_quality_sqs_inspection_includes_sq9_pass_and_fail_cases():
    """SQ9 (STATUS in allowed set) needs both PASS rows from the
    canonical 11-value vocabulary and off-list FAIL rows so the
    demo-mode covers both branches independently of SQ8's NULL gap."""
    from src.custom_dqr_engine import SQS_SQ9_ALLOWED_VALUES

    df = mock_data.fetch_mock_table("CT_SQS_AT_INSPECTION")
    allowed = set(SQS_SQ9_ALLOWED_VALUES)
    in_allowed = df["STATUS"].isin(allowed)
    assert in_allowed.any(), "no STATUS rows in the SQ9 allowed set"
    # Off-list is anything non-null that doesn't match the allowed set
    # (NULL is a separate SQ8 concern).
    offlist = df["STATUS"].notna() & ~in_allowed
    assert offlist.any(), "no off-list STATUS rows for SQ9 FAIL coverage"


def test_quality_sqs_inspection_includes_sq10_completed_future_fail():
    """SQ10 fails only on ``STATUS == 'Completed'`` paired with a future
    ``EXPECTED_SHIP_DATE``; the mock must seed at least one such row
    (and at least one Completed PASS row) so both branches are
    reachable in demo mode."""
    df = mock_data.fetch_mock_table("CT_SQS_AT_INSPECTION")
    completed = df["STATUS"] == "Completed"
    assert completed.any(), "no Completed STATUS rows in mock"
    ship = pd.to_datetime(df["EXPECTED_SHIP_DATE"], errors="coerce")
    now = pd.Timestamp.now()
    completed_future = completed & ship.notna() & (ship > now)
    completed_past = completed & ship.notna() & (ship <= now)
    assert completed_future.any(), "no Completed+future-ship-date FAIL row"
    assert completed_past.any(), "no Completed+past-ship-date PASS row"


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
