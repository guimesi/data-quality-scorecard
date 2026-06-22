"""Fills the remaining coverage gaps across config/, src/models, src/scorecard,
src/profiler, src/mock_data, src/data_product_builder, and config/systems."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from config.dqr_catalog import (
    DIMENSIONS,
    get_dimension,
    list_dimensions,
    suggest_dimensions_for,
)
from config.systems import SystemDef, TableDef, get_system, list_system_codes

# ---------------------------------------------------------------------------
# config/dqr_catalog.py
# ---------------------------------------------------------------------------

def test_list_dimensions_returns_all():
    dims = list_dimensions()
    assert len(dims) == len(DIMENSIONS)
    assert "Completeness" in dims


def test_get_dimension_known():
    d = get_dimension("Completeness")
    assert d.name == "Completeness"


def test_get_dimension_unknown_raises():
    with pytest.raises(KeyError, match="Unknown dimension"):
        get_dimension("Foo")


def test_suggest_dimensions_adds_uniqueness_for_id_like():
    suggested = suggest_dimensions_for("string", "CUSTOMER_ID")
    assert "Uniqueness" in suggested
    assert "Completeness" in suggested


def test_suggest_dimensions_always_adds_completeness_if_missing():
    # Pass a column type that won't auto-add Completeness via applies_to
    # Completeness applies to virtually all types, so we'd need to force the
    # missing-path. Use an unknown type group.
    suggested = suggest_dimensions_for("unknown-group", "SOMECOL")
    assert suggested[0] == "Completeness"


def test_suggest_dimensions_id_only_triggers_id_branch():
    """Covers the `elif is_id_like and COLUMN_TYPE_ID in dim.applies_to` branch."""
    # Column name ends in _id -> is_id_like = True, column_type is not id
    suggested = suggest_dimensions_for("unknown-group", "something_id")
    # Should pick up dimensions whose applies_to includes 'id' (Integrity, Uniqueness, Validity)
    assert "Integrity" in suggested
    assert "Uniqueness" in suggested


# ---------------------------------------------------------------------------
# config/systems.py
# ---------------------------------------------------------------------------

def test_primary_table_raises_when_none_defined():
    sys_def = SystemDef(
        code="X", name="X", description="",
        tables=[TableDef(name="T", description="", join_key="K", is_primary=False)],
    )
    with pytest.raises(ValueError, match="no primary table"):
        sys_def.primary_table


def test_table_names_property():
    s = get_system("ADR")
    assert "ADR_DIM_ESTIMATEITEMRECORD" in s.table_names


def test_get_system_unknown_raises():
    with pytest.raises(KeyError, match="Unknown system"):
        get_system("DOES_NOT_EXIST")


def test_list_system_codes_returns_adr_acce_ept():
    codes = list_system_codes()
    assert set(codes) == {"ADR", "ACCE", "EPT"}


# ---------------------------------------------------------------------------
# src/models.py
# ---------------------------------------------------------------------------

def test_data_product_column_count():
    from src.models import DataProduct
    dp = DataProduct(
        system_code="X", name="X",
        df=pd.DataFrame({"A": [1], "B": [2], "C": [3]}),
        source_tables=["t"],
    )
    assert dp.column_count == 3


def test_data_product_config_get_assignments_for_cde():
    from src.models import DataProductConfig, DQRAssignment
    cfg = DataProductConfig(
        system_code="X",
        assignments=[
            DQRAssignment("A", "Completeness"),
            DQRAssignment("A", "Uniqueness"),
            DQRAssignment("B", "Completeness"),
        ],
    )
    a = cfg.get_assignments_for("A")
    assert len(a) == 2
    assert {x.dimension for x in a} == {"Completeness", "Uniqueness"}


def test_data_product_config_weights_sum():
    from src.models import DataProductConfig, DQRAssignment
    cfg = DataProductConfig(
        system_code="X",
        assignments=[
            DQRAssignment("A", "Completeness", weight=30),
            DQRAssignment("B", "Completeness", weight=70),
        ],
    )
    assert cfg.weights_sum() == 100


# ---------------------------------------------------------------------------
# src/scorecard.py: zero-weight normalization + CDE without assignments
# ---------------------------------------------------------------------------

def test_scorecard_all_zero_weights_falls_back_to_equal():
    from src.models import DataProduct, DataProductConfig, DQRAssignment
    from src.scorecard import compute_scorecard
    df = pd.DataFrame({"A": [1, 1], "B": [None, 2]})
    dp = DataProduct(system_code="X", name="X", df=df, source_tables=["t"])
    cfg = DataProductConfig(
        system_code="X",
        cdes=["A", "B"],
        assignments=[
            DQRAssignment("A", "Completeness", weight=0),
            DQRAssignment("B", "Completeness", weight=0),
        ],
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    # With equal fallback weights (0.5/0.5): row0 A passes(0.5) B fails(0) -> 50
    # row1 both pass -> 100
    assert result.row_scores.tolist() == [50.0, 100.0]


def test_scorecard_cde_without_related_rules_is_zero():
    from src.models import DataProduct, DataProductConfig, DQRAssignment
    from src.scorecard import compute_scorecard
    df = pd.DataFrame({"A": [1, 2]})
    dp = DataProduct(system_code="X", name="X", df=df, source_tables=["t"])
    cfg = DataProductConfig(
        system_code="X",
        cdes=["A", "ORPHAN"],  # ORPHAN has no rules
        assignments=[DQRAssignment("A", "Completeness", weight=100)],
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.cde_scores["ORPHAN"] == 0.0


# ---------------------------------------------------------------------------
# src/mock_data.py
# ---------------------------------------------------------------------------

def test_fetch_mock_table_unknown_raises():
    from src.mock_data import fetch_mock_table
    with pytest.raises(KeyError, match="No mock generator"):
        fetch_mock_table("NOT_A_TABLE")


def test_list_mock_tables_returns_all_registered():
    from src.mock_data import list_mock_tables
    tables = list_mock_tables()
    assert "ADR_DIM_ESTIMATEITEMRECORD" in tables
    assert "ONSHORE_CETDATA" in tables
    assert all(v == "mock" for v in tables.values())


# ---------------------------------------------------------------------------
# src/data_product_builder.py: column_prefix fallback + missing join_key
# ---------------------------------------------------------------------------

def test_build_data_product_missing_join_key_raises():
    """If the child table is missing its join_key, a ValueError is raised."""
    from src.data_product_builder import build_data_product

    # Fake fetcher: primary has ROW_ID, child is missing ROW_ID
    def fake_fetch(name: str) -> pd.DataFrame:
        if name == "ADR_DIM_ESTIMATEITEMRECORD":
            return pd.DataFrame({"ROW_ID": ["R1", "R2"], "PLANVIEW_ID": ["P1", "P1"]})
        # any child table: return a df without ROW_ID
        return pd.DataFrame({"OTHER": [1, 2]})

    with pytest.raises(ValueError, match="missing join_key"):
        build_data_product("ADR", fetcher=fake_fetch)


def test_build_data_product_column_prefix_fallback(monkeypatch):
    """Cover the fallback prefix derivation (line 56) when TableDef has no column_prefix."""
    from config import systems as systems_mod
    from src.data_product_builder import build_data_product

    # Create a custom system with a child table that has NO explicit column_prefix.
    custom_primary = TableDef(
        name="FOO_PRIMARY", description="", join_key="ROW_ID", is_primary=True,
    )
    custom_child = TableDef(
        name="FOO_SOMECHILD", description="", join_key="ROW_ID",
        column_prefix=None,  # force fallback to derived prefix
    )
    custom_system = SystemDef(
        code="FOOSYS", name="FOOSYS", description="",
        tables=[custom_primary, custom_child],
    )
    monkeypatch.setitem(systems_mod.SYSTEMS, "FOOSYS", custom_system)

    def fake_fetch(name: str) -> pd.DataFrame:
        if name == "FOO_PRIMARY":
            return pd.DataFrame({"ROW_ID": ["R1", "R2"]})
        return pd.DataFrame({"ROW_ID": ["R1", "R2"], "VAL": [10, 20]})

    dp = build_data_product("FOOSYS", fetcher=fake_fetch)
    # Column 'VAL' should have been prefixed with 'SOMECHILD' (last _ segment)
    assert any("SOMECHILD" in c for c in dp.df.columns)


def test_default_fetcher_snowflake_branch(monkeypatch):
    """Cover lines 38-42: is_mock=False path building a Snowflake fetcher."""
    from config import settings as settings_mod
    from src import data_product_builder as dpb

    # Force is_mock to be False
    monkeypatch.setattr(
        dpb, "SETTINGS",
        settings_mod.Settings(data_source="snowflake"),
    )

    mock_client_instance = MagicMock()
    mock_client_instance.fetch_table.return_value = pd.DataFrame({"X": [1]})
    with patch("src.snowflake_client.SnowflakeClient", return_value=mock_client_instance):
        fetcher = dpb._default_fetcher(row_limit=100)
        df = fetcher("SOME_TABLE")
        assert list(df.columns) == ["X"]
        mock_client_instance.fetch_table.assert_called_once_with(
            "SOME_TABLE", limit=100
        )


def test_default_fetcher_mock_branch_no_limit():
    """Cover the is_mock branch without row_limit."""
    from src.data_product_builder import _default_fetcher
    fetcher = _default_fetcher(row_limit=None)
    df = fetcher("ADR_DIM_ESTIMATEITEMRECORD")
    assert "ROW_ID" in df.columns


def test_default_fetcher_mock_branch_with_limit():
    from src.data_product_builder import _default_fetcher
    fetcher = _default_fetcher(row_limit=5)
    df = fetcher("ADR_DIM_ESTIMATEITEMRECORD")
    assert len(df) == 5


def test_default_fetcher_snowflake_pushdown_primary_uses_where(monkeypatch):
    """When the sidebar Project filter is active, the Snowflake fetcher
    must push ``WHERE filter_column IN (...)`` onto the primary table -
    Sample mode's LIMIT would otherwise drop the very rows the user
    asked for (the production bug for PLANVIEW_ID=1101168)."""
    from config import settings as settings_mod
    from config.systems import get_system
    from src import data_product_builder as dpb

    monkeypatch.setattr(
        dpb, "SETTINGS",
        settings_mod.Settings(data_source="snowflake"),
    )

    mock_client = MagicMock()
    mock_client.fetch_table.return_value = pd.DataFrame({"PLANVIEW_ID": ["1101168"]})
    with patch("src.snowflake_client.get_shared_client", return_value=mock_client), \
         patch("src.snowflake_client._resolve_location", return_value=("DB", "SC")):
        fetcher = dpb._default_fetcher(
            row_limit=50000,
            system=get_system("EPT"),
            planview_ids=["1101168"],
            filter_column="PLANVIEW_ID",
        )
        fetcher("ONSHORE_CETDATA")  # EPT's primary table

    kwargs = mock_client.fetch_table.call_args.kwargs
    assert kwargs["where"] == "PLANVIEW_ID IN (%s)"
    assert kwargs["params"] == ["1101168"]
    # LIMIT is still applied, but now against the filtered set.
    assert kwargs["limit"] == 50000


def test_default_fetcher_snowflake_pushdown_child_uses_subquery(monkeypatch):
    """Child tables must filter via a sub-SELECT on the primary's
    ``join_key`` so the downstream LEFT JOIN finds every matching row.
    Without this, Sample mode's LIMIT could silently drop child rows
    that join to the filtered primary set."""
    from config import settings as settings_mod
    from config.systems import get_system
    from src import data_product_builder as dpb

    monkeypatch.setattr(
        dpb, "SETTINGS",
        settings_mod.Settings(data_source="snowflake"),
    )

    mock_client = MagicMock()
    mock_client.fetch_table.return_value = pd.DataFrame({"ROW_ID": ["r1"]})
    with patch("src.snowflake_client.get_shared_client", return_value=mock_client), \
         patch("src.snowflake_client._resolve_location", return_value=("DB", "SC")):
        fetcher = dpb._default_fetcher(
            row_limit=50000,
            system=get_system("ADR"),
            planview_ids=["1101168", "1106771"],
            filter_column="PLANVIEW_ID",
        )
        fetcher("ADR_FACT_ESTIMATECOSTRESULTS")  # ADR child, joins on ROW_ID

    kwargs = mock_client.fetch_table.call_args.kwargs
    where = kwargs["where"]
    # The child WHERE pulls join_keys from the primary's filtered set.
    assert "ROW_ID IN (" in where
    assert "SELECT ROW_ID FROM DB.SC.ADR_DIM_ESTIMATEITEMRECORD" in where
    assert "WHERE PLANVIEW_ID IN (%s, %s)" in where
    assert kwargs["params"] == ["1101168", "1106771"]
    # Child fetches drop the LIMIT - the subquery already bounds the
    # result to the filtered project set.
    assert "limit" not in kwargs or kwargs.get("limit") is None


def test_default_fetcher_snowflake_no_filter_keeps_historical_behaviour(monkeypatch):
    """No active filter → no WHERE, plain ``LIMIT N`` like before so
    Step 2 still runs Sample mode against unfiltered Cost Estimate
    tables exactly as it did pre-fix."""
    from config import settings as settings_mod
    from config.systems import get_system
    from src import data_product_builder as dpb

    monkeypatch.setattr(
        dpb, "SETTINGS",
        settings_mod.Settings(data_source="snowflake"),
    )

    mock_client = MagicMock()
    mock_client.fetch_table.return_value = pd.DataFrame({"X": [1]})
    with patch("src.snowflake_client.get_shared_client", return_value=mock_client):
        fetcher = dpb._default_fetcher(
            row_limit=50000,
            system=get_system("EPT"),
            planview_ids=None,
            filter_column="PLANVIEW_ID",
        )
        fetcher("ONSHORE_CETDATA")

    # Falls back to the simple ``fetch_table(name, limit=row_limit)``
    # signature - no pushdown, no surprises.
    mock_client.fetch_table.assert_called_once_with("ONSHORE_CETDATA", limit=50000)


# ---------------------------------------------------------------------------
# src/profiler.py
# ---------------------------------------------------------------------------

def test_profiler_bool_dtype():
    from config.dqr_catalog import COLUMN_TYPE_BOOLEAN
    from src.profiler import classify_column
    s = pd.Series([True, False, True, None], dtype="boolean")
    assert classify_column(s, "FLAG") == COLUMN_TYPE_BOOLEAN


def test_profiler_integer_dtype():
    from config.dqr_catalog import COLUMN_TYPE_INTEGER
    from src.profiler import classify_column
    s = pd.Series([1, 2, 3])
    assert classify_column(s, "COUNT") == COLUMN_TYPE_INTEGER


def test_profiler_categorical_dtype():
    from config.dqr_catalog import COLUMN_TYPE_CATEGORICAL
    from src.profiler import classify_column
    s = pd.Series(["A", "B", "A"], dtype="category")
    assert classify_column(s, "CAT") == COLUMN_TYPE_CATEGORICAL


def test_profiler_detects_datetime_strings():
    """Covers lines 61-62: string column whose values parse as dates."""
    from config.dqr_catalog import COLUMN_TYPE_DATETIME
    from src.profiler import classify_column
    s = pd.Series(["2024-01-01", "2024-06-15", "2024-12-31"])
    assert classify_column(s, "DATESTR") == COLUMN_TYPE_DATETIME


def test_profiler_numeric_complex_dtype():
    """Covers line 47: numeric but not bool/datetime/int/float."""
    from config.dqr_catalog import COLUMN_TYPE_NUMERIC
    from src.profiler import classify_column
    s = pd.Series([1 + 2j, 3 + 4j, 5 + 6j])
    assert classify_column(s, "COMPLEX") == COLUMN_TYPE_NUMERIC


def test_profiler_generic_string_fallback():
    from config.dqr_catalog import COLUMN_TYPE_STRING
    from src.profiler import classify_column
    # High-cardinality strings, not datetimes
    s = pd.Series([f"free_text_{i}" for i in range(50)])
    assert classify_column(s, "NOTES") == COLUMN_TYPE_STRING


def test_profile_column_with_object_min_max_skips_safely():
    """Covers lines 74-75, 81-82: _safe_min/_safe_max exception branches."""
    from src.profiler import profile_column
    # Mixed-type column that raises on min()/max()
    df = pd.DataFrame({"MIXED": [1, "two", 3]})
    p = profile_column(df, "MIXED")
    # It's classified as string, so min/max aren't even computed -> None
    assert p.min_value is None
    assert p.max_value is None


def test_safe_min_max_exception_branches():
    """Force exceptions inside the helpers by patching dropna to raise."""
    from src import profiler as prof
    s = pd.Series([1, 2, 3])
    # Temporarily monkeypatch to make dropna raise
    with patch.object(pd.Series, "dropna", side_effect=RuntimeError("boom")):
        assert prof._safe_min(s) is None
        assert prof._safe_max(s) is None


def test_profiles_to_table_renders_rows(sample_df):
    """Covers lines 131-144."""
    from src.profiler import profile_dataframe, profiles_to_table
    profiles = profile_dataframe(sample_df)
    table = profiles_to_table(profiles)
    assert len(table) == len(sample_df.columns)
    expected_cols = {
        "Column", "Dtype", "Type Group", "Rows", "Nulls",
        "Null %", "Distinct", "Duplicates", "Sample",
    }
    assert expected_cols.issubset(set(table.columns))


# ---------------------------------------------------------------------------
# DataProductConfig source-weight defaults
# ---------------------------------------------------------------------------

def test_effective_source_weights_split_evenly_for_two_sources_without_weights():
    """Configs that declare both sources but never set source_weights get a
    50/50 split via the default helper."""
    from src.models import DataProductConfig
    cfg = DataProductConfig(
        system_code="X",
        dqr_sources=["standard", "custom"],
        source_weights={},
    )
    weights = cfg.effective_source_weights()
    assert sorted(weights.keys()) == ["custom", "standard"]
    assert weights["standard"] == weights["custom"] == 50.0


# ---------------------------------------------------------------------------
# scorecard internals - early-return branches
# ---------------------------------------------------------------------------

def test_normalize_custom_weights_zero_falls_back_to_equal():
    """When all custom weights are zero, _normalize_custom_weights spreads
    equally instead of dividing by zero."""
    import numpy as np

    from src.models import CustomDQRAssignment
    from src.scorecard import _normalize_custom_weights
    out = _normalize_custom_weights([
        CustomDQRAssignment(rule_id="A", weight=0),
        CustomDQRAssignment(rule_id="B", weight=0),
    ])
    np.testing.assert_allclose(out, [0.5, 0.5])


def test_compute_standard_row_scores_empty_assignments_returns_zero_series():
    """Reached when Custom rules exist but Standard assignments are empty -
    ``_compute_standard_row_scores`` must short-circuit cleanly."""
    from src.models import (
        CustomDQRAssignment,
        DataProduct,
        DataProductConfig,
        DQRAssignment,
    )
    from src.scorecard import _compute_standard_row_scores, compute_scorecard

    df = pd.DataFrame({"X": [1, 2, 3]})
    dp = DataProduct(system_code="X", name="X", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="X",
        cdes=[],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100)],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 50.0, "custom": 50.0},
    )
    series, rates, not_computed = _compute_standard_row_scores(dp, cfg)
    assert series.tolist() == [0.0, 0.0, 0.0]
    assert rates == {}
    assert not_computed == {}
    # Round-trip via compute_scorecard to also exercise the integrated path.
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.standard_score == 0.0


def test_compute_custom_row_scores_empty_assignments_returns_zero_series():
    """Reached when Standard rules exist but Custom assignments are empty
    while Custom is still in dqr_sources."""
    from src.models import (
        DataProduct,
        DataProductConfig,
        DQRAssignment,
    )
    from src.scorecard import _compute_custom_row_scores, compute_scorecard

    df = pd.DataFrame({"X": [1, 2, 3]})
    dp = DataProduct(system_code="X", name="X", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="X",
        cdes=["X"],
        assignments=[DQRAssignment("X", "Completeness", weight=100)],
        custom_assignments=[],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 50.0, "custom": 50.0},
    )
    series, rates, not_eval = _compute_custom_row_scores(dp, cfg)
    assert series.tolist() == [0.0, 0.0, 0.0]
    assert rates == {}
    assert not_eval == {}
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.custom_score == 0.0


def test_compute_custom_row_scores_skips_unknown_rule_id():
    """When every selected rule_id is unknown to the catalog, the dispatcher
    returns an empty DataFrame and the wrapper falls back to a zero-score
    series."""
    from src.models import (
        CustomDQRAssignment,
        DataProduct,
        DataProductConfig,
    )
    from src.scorecard import _compute_custom_row_scores

    df = pd.DataFrame({"X": [1, 2, 3]})
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=[],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="UNKNOWN", weight=100)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    series, rates, not_eval = _compute_custom_row_scores(dp, cfg)
    assert series.tolist() == [0.0, 0.0, 0.0]
    assert rates == {}
    assert not_eval == {}


def test_compute_scorecard_zero_total_weight_falls_back_to_zero():
    """Defensive fallback: if the user manually sets all source weights to 0,
    the combined row score collapses to 0 instead of dividing by zero."""
    from src.models import (
        DataProduct,
        DataProductConfig,
        DQRAssignment,
    )
    from src.scorecard import compute_scorecard

    df = pd.DataFrame({"X": [1, 2, 3]})
    dp = DataProduct(system_code="X", name="X", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="X",
        cdes=["X"],
        assignments=[DQRAssignment("X", "Completeness", weight=100)],
        dqr_sources=["standard"],
        source_weights={"standard": 0.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.overall_score == 0.0
    assert result.row_scores.tolist() == [0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------
# session_state - defensive branches when current_step is hidden
# ---------------------------------------------------------------------------

def test_next_step_from_hidden_step_jumps_to_next_visible():
    """If somehow the user lands on dqr_assignment without any DP picking
    Standard, next_step() must skip past it cleanly."""
    import streamlit as st

    from src.models import DataProductConfig
    from utils.session_state import next_step

    # Reset the global session state used by streamlit (testing context).
    st.session_state.clear()
    st.session_state["app_mode"] = "step_by_step"  # Step-by-step steps must be visible
    st.session_state["current_step"] = "dqr_assignment"
    st.session_state["configs"] = {
        "EPT": DataProductConfig(
            system_code="EPT",
            dqr_sources=["custom"],
            source_weights={"custom": 100.0},
        ),
    }
    # ``goto`` calls st.rerun() which raises RerunException in test context;
    # catch any exception to verify the function still updates the step.
    try:
        next_step()
    except Exception:
        pass
    assert st.session_state["current_step"] in {
        "dqr_custom_rules",
        "weight_assignment",
        "dashboard",
    }


def test_prev_step_from_hidden_step_jumps_to_prev_visible():
    import streamlit as st

    from src.models import DataProductConfig
    from utils.session_state import prev_step

    st.session_state.clear()
    st.session_state["app_mode"] = "step_by_step"  # Step-by-step steps must be visible
    st.session_state["current_step"] = "dqr_custom_rules"
    st.session_state["configs"] = {
        "EPT": DataProductConfig(
            system_code="EPT",
            dqr_sources=["standard"],
            source_weights={"standard": 100.0},
        ),
    }
    try:
        prev_step()
    except Exception:
        pass
    assert st.session_state["current_step"] in {
        "dqr_assignment",
        "dqr_source_selection",
        "cde_selection",
    }


def test_next_step_at_last_visible_is_a_noop():
    import streamlit as st

    from utils.session_state import next_step

    st.session_state.clear()
    st.session_state["current_step"] = "dashboard"
    st.session_state["configs"] = {}
    try:
        next_step()
    except Exception:
        pass
    assert st.session_state["current_step"] == "dashboard"


def test_prev_step_at_first_visible_is_a_noop():
    import streamlit as st

    from utils.session_state import prev_step

    # ``mode_selection`` is the new first visible step (the entry point).
    # The noop guard is what we're really exercising here, the specific
    # step name is incidental.
    st.session_state.clear()
    st.session_state["current_step"] = "mode_selection"
    st.session_state["configs"] = {}
    try:
        prev_step()
    except Exception:
        pass
    assert st.session_state["current_step"] == "mode_selection"
