"""Tests for the data product builder using mock data."""
import os

# Force mock mode before importing anything that reads settings
os.environ["DATA_SOURCE"] = "mock"

from src.data_product_builder import build_data_product, build_multiple


def test_build_adr_data_product():
    dp = build_data_product("ADR")
    assert dp.system_code == "ADR"
    assert "ROW_ID" in dp.df.columns
    assert "PLANVIEW_ID" in dp.df.columns
    assert dp.row_count > 0
    # 4 source tables in ADR: primary ESTIMATEITEMRECORD + 2 result facts
    # (cost / qty) + ESTIMATEDESIGNDETAILS (design specs, joined on ROW_ID).
    assert len(dp.source_tables) == 4


def test_build_acce_data_product():
    dp = build_data_product("ACCE")
    assert dp.system_code == "ACCE"
    assert "ROW_ID" in dp.df.columns
    assert "PLANVIEW_ID" in dp.df.columns
    # 4 source tables in ACCE: primary ESTIMATEITEMRECORD + cost / qty
    # results (joined on ROW_ID) + ESTIMATEDESIGNDETAILS (joined on
    # DESIGN_ID, many items can share one design).
    assert len(dp.source_tables) == 4
    # DESIGN_ID is the FK on the primary used to join the design dim,
    # so it survives the merge as a regular column on the data product.
    assert "DESIGN_ID" in dp.df.columns
    # A sample of the design columns should be attached via the left
    # join. Items with a null DESIGN_ID get NaNs here, that's expected.
    assert "DESIGN_VALUE" in dp.df.columns
    assert "DESIGN_MATERIAL_SPEC" in dp.df.columns


def test_build_ept_data_product():
    dp = build_data_product("EPT")
    assert dp.system_code == "EPT"
    assert "PLANVIEW_ID" in dp.df.columns
    # EPT has only 1 table
    assert len(dp.source_tables) == 1


def test_build_multiple_returns_all():
    dps = build_multiple(["ADR", "ACCE", "EPT"])
    assert set(dps.keys()) == {"ADR", "ACCE", "EPT"}
    # All should have PLANVIEW_ID (cross-system linking key)
    for dp in dps.values():
        assert "PLANVIEW_ID" in dp.df.columns
    # ADR and ACCE primaries should also have ROW_ID
    assert "ROW_ID" in dps["ADR"].df.columns
    assert "ROW_ID" in dps["ACCE"].df.columns


def test_apply_planview_filter_matches_numeric_column_against_string_input():
    """Real warehouse ``PLANVIEW_ID``s are numeric (``1101168``). When the
    column has any NULL, pandas promotes the dtype to ``float64`` and the
    pre-fix code compared the user's ``"1101168"`` against the column's
    ``"1101168.0"``, producing zero rows. The canonicalizer must collapse
    both forms so the filter actually keeps the matching rows.
    """
    import pandas as pd

    from src.data_product_builder import _apply_planview_filter

    df = pd.DataFrame({
        "PLANVIEW_ID": [1101168, 1106771, 9999999, None],
        "VAL": [10, 20, 30, 40],
    })
    # The NULL forces dtype promotion to float64 in pandas, which is
    # exactly the production scenario.
    assert df["PLANVIEW_ID"].dtype.kind == "f"

    out = _apply_planview_filter(df, ["1101168"])
    assert list(out["VAL"]) == [10]

    # Multi-id, and the user can also type the trailing-.0 form.
    out = _apply_planview_filter(df, ["1101168", "1106771.0"])
    assert sorted(out["VAL"]) == [10, 20]


def test_apply_planview_filter_strips_whitespace_and_handles_object_dtype():
    """Object-dtype column with mixed int / float entries (another
    warehouse-pandas shape) and whitespace-padded user input must still
    resolve to the right rows."""
    import pandas as pd

    from src.data_product_builder import _apply_planview_filter

    df = pd.DataFrame({
        "PLANVIEW_ID": [1101168, 1106771.0, "1107000", None],
        "VAL": [10, 20, 30, 40],
    })
    out = _apply_planview_filter(df, [" 1101168 ", "1106771", "1107000"])
    assert sorted(out["VAL"]) == [10, 20, 30]


def test_apply_planview_filter_preserves_existing_string_id_behaviour():
    """The mock data ships ``PLANVIEW_ID`` as ``PV-NNNNN`` strings; the
    canonicalizer must leave non-numeric IDs alone."""
    import pandas as pd

    from src.data_product_builder import _apply_planview_filter

    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "VAL": [10, 20, 30],
    })
    out = _apply_planview_filter(df, ["PV-00002"])
    assert list(out["VAL"]) == [20]


def test_apply_planview_filter_respects_custom_column():
    """The filter helper accepts an explicit ``column`` argument so a
    domain configured to filter on something other than ``PLANVIEW_ID``
    (Quality → ``PROJECT_CODE``) restricts on the right key."""
    import pandas as pd

    from src.data_product_builder import _apply_planview_filter

    df = pd.DataFrame({
        "PROJECT_CODE": ["QPC-001", "QPC-002", "QPC-003"],
        "PLANVIEW_ID": ["PV-1", "PV-2", "PV-3"],
        "VAL": [10, 20, 30],
    })
    out = _apply_planview_filter(df, ["QPC-002"], column="PROJECT_CODE")
    assert list(out["PROJECT_CODE"]) == ["QPC-002"]
    assert list(out["VAL"]) == [20]


def _activate_quality_domain(monkeypatch):
    """Resolve ``get_system('SQS')`` by flipping ``session_state.domain``
    to Quality on a fake ``streamlit`` module - mirrors the helper used
    in ``tests/test_domains.py``."""
    class _FakeST:
        def __init__(self):
            self.session_state = {"domain": "quality"}

    fake = _FakeST()
    import sys
    monkeypatch.setitem(sys.modules, "streamlit", fake)


def test_build_data_product_filter_column_quality_uses_project_code(monkeypatch):
    """End-to-end: building the SQS data product with
    ``filter_column='PROJECT_CODE'`` must keep only inspections whose
    ``PROJECT_CODE`` matches the requested set."""
    _activate_quality_domain(monkeypatch)
    dp = build_data_product("SQS")
    # The mock seeds ``QPC-001`` (PROJECT_CODE for the first PLANVIEW_ID)
    # by construction; restrict to that one project.
    filtered = build_data_product(
        "SQS",
        planview_ids=["QPC-001"],
        filter_column="PROJECT_CODE",
    )
    assert filtered.row_count > 0
    assert filtered.row_count < dp.row_count
    assert set(filtered.df["PROJECT_CODE"].dropna().unique()) == {"QPC-001"}


def test_build_multiple_propagates_filter_column(monkeypatch):
    """``build_multiple`` must pass ``filter_column`` through so all
    systems in the active domain agree on which column to filter on."""
    _activate_quality_domain(monkeypatch)
    dps = build_multiple(
        ["SQS"], planview_ids=["QPC-001"], filter_column="PROJECT_CODE"
    )
    assert "SQS" in dps
    assert set(dps["SQS"].df["PROJECT_CODE"].dropna().unique()) == {"QPC-001"}


def test_canonicalize_id_normalizes_without_sanitizing():
    """_canonicalize_id normalizes ids for matching (strip whitespace, collapse
    whole-number floats to int form) but is explicitly NOT a sanitizer: any
    non-numeric text - including a SQL-injection-shaped value - passes through
    verbatim. Injection safety comes from parameter binding downstream, not
    from mangling the value here."""
    import pandas as pd

    from src.data_product_builder import _canonicalize_id

    assert _canonicalize_id(None) is None
    assert _canonicalize_id(pd.NA) is None
    assert _canonicalize_id(float("nan")) is None
    assert _canonicalize_id("") is None
    assert _canonicalize_id("   ") is None
    assert _canonicalize_id("1101168") == "1101168"
    assert _canonicalize_id(1101168.0) == "1101168"      # whole float -> int form
    assert _canonicalize_id(" 1101168 ") == "1101168"    # stripped
    assert _canonicalize_id("1101168.5") == "1101168.5"  # non-integer float -> text
    assert _canonicalize_id("PV-00001") == "PV-00001"    # non-numeric passthrough
    assert _canonicalize_id("QPC-001") == "QPC-001"
    evil = "1101168'); DROP TABLE X; --"
    assert _canonicalize_id(evil) == evil                # returned unchanged


def test_default_fetcher_binds_adversarial_id_as_param_not_sql(monkeypatch):
    """Injection safety end-to-end through the pushdown: a malicious project id
    never reaches the SQL text. The WHERE fragment carries only a %s
    placeholder and the payload is bound as a parameter, so it cannot alter the
    SQL structure (the connector binds it server-side)."""
    from unittest.mock import MagicMock, patch

    import pandas as pd

    from config import settings as settings_mod
    from config.systems import get_system
    from src import data_product_builder as dpb

    monkeypatch.setattr(
        dpb, "SETTINGS", settings_mod.Settings(data_source="databricks")
    )
    evil = "1101168'); DROP TABLE ADR_DIM_ESTIMATEITEMRECORD; --"
    mock_client = MagicMock()
    mock_client.fetch_table.return_value = pd.DataFrame({"ROW_ID": ["r1"]})
    with patch("src.databricks_client.get_shared_client", return_value=mock_client), \
         patch("src.databricks_client._resolve_location", return_value=("DB", "SC")):
        fetcher = dpb._default_fetcher(
            row_limit=50000,
            system=get_system("ADR"),
            planview_ids=[evil],
            filter_column="PLANVIEW_ID",
        )
        fetcher("ADR_DIM_ESTIMATEITEMRECORD")  # the primary table

    kwargs = mock_client.fetch_table.call_args.kwargs
    assert kwargs["where"] == "PLANVIEW_ID IN (%s)"   # only a placeholder
    assert "DROP TABLE" not in kwargs["where"]
    assert kwargs["params"] == [evil]                 # payload bound, verbatim
