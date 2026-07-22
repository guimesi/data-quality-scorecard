"""Tests for the Step 6 drill-down helpers.

Covers the pure selection-event extractors, the failing-row mask, and the
render functions (with the module's ``st`` faked) that surface the rows
failing a clicked CDE / dimension / rule.
"""
from __future__ import annotations

import os

# Force mock mode before importing anything that reads settings.
os.environ.setdefault("DATA_SOURCE", "mock")

from unittest.mock import MagicMock

import pandas as pd

import ui.step_06._drilldown as dd
from src.models import (
    CustomDQRAssignment,
    DataProduct,
    DataProductConfig,
    DQRAssignment,
)
from src.profiler import profile_dataframe
from src.scorecard import compute_scorecard


def _ept_dp(df: pd.DataFrame) -> DataProduct:
    return DataProduct(
        system_code="EPT", name="EPT", df=df,
        source_tables=["T"], profiles=profile_dataframe(df),
    )


def _dp_cfg_result():
    """EPT data product with one Completeness rule; row 3 fails it."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", "PV-002", "PV-003", None],
        "CODE_OF_RESOURCE": ["LOC-A", "LOC-B", "LOC-C", "LOC-D"],
    })
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100.0)],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    return dp, cfg, result


# ---------------------------------------------------------------- extractors

def test_selected_bar_labels_empty_and_none_events():
    assert dd._selected_bar_labels(None) == []
    assert dd._selected_bar_labels({}) == []
    assert dd._selected_bar_labels({"selection": {}}) == []
    assert dd._selected_bar_labels({"selection": {"points": []}}) == []


def test_selected_bar_labels_extracts_and_dedupes_y():
    event = {"selection": {"points": [
        {"x": 50.0, "y": "PLANVIEW_ID"},
        {"x": 50.0, "y": "PLANVIEW_ID"},   # duplicate click point
        {"x": 80.0, "y": "AMOUNT"},
        {"x": 10.0},                        # no y → ignored
    ]}}
    assert dd._selected_bar_labels(event) == ["PLANVIEW_ID", "AMOUNT"]


def test_selected_table_rows_empty_and_populated():
    assert dd._selected_table_rows(None) == []
    assert dd._selected_table_rows({}) == []
    assert dd._selected_table_rows({"selection": {"rows": []}}) == []
    assert dd._selected_table_rows({"selection": {"rows": [2, 0]}}) == [2, 0]


# ---------------------------------------------------------------- mask/flags

def test_failing_mask_none_when_no_rule_computed():
    flags = pd.DataFrame({"A::Completeness": [True, False]})
    assert dd._failing_mask(flags, ["B::Uniqueness"]) is None


def test_failing_mask_any_rule_failure_flags_row():
    flags = pd.DataFrame({
        "A::Completeness": [True, False, True],
        "A::Uniqueness": [True, True, False],
    })
    mask = dd._failing_mask(flags, ["A::Completeness", "A::Uniqueness"])
    assert mask.tolist() == [False, True, True]


def test_standard_flags_marks_null_row_as_failing():
    dp, cfg, _ = _dp_cfg_result()
    flags = dd._standard_flags(dp, cfg)
    assert "PLANVIEW_ID::Completeness" in flags.columns
    assert flags["PLANVIEW_ID::Completeness"].tolist() == [True, True, True, False]


def test_standard_flags_empty_when_no_assignments():
    dp, _, _ = _dp_cfg_result()
    empty_cfg = DataProductConfig(system_code="EPT")
    assert dd._standard_flags(dp, empty_cfg).empty


# ------------------------------------------------------------------- renders

def test_render_failing_rows_success_when_mask_empty(monkeypatch):
    dp, cfg, result = _dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    mask = pd.Series([False] * 4, index=dp.df.index)
    dd._render_failing_rows(dp, result, cfg, mask, context="CDE X", key="k")
    fake_st.success.assert_called_once()
    fake_st.dataframe.assert_not_called()


def test_render_failing_rows_shows_failing_rows_worst_first(monkeypatch):
    dp, cfg, result = _dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    mask = pd.Series([False, False, False, True], index=dp.df.index)
    dd._render_failing_rows(dp, result, cfg, mask, context="CDE PLANVIEW_ID", key="k")
    fake_st.dataframe.assert_called_once()
    shown = fake_st.dataframe.call_args[0][0]
    assert list(shown.index) == [3]
    assert shown.columns[0] == "row_score"
    banner = fake_st.markdown.call_args[0][0]
    assert "1 row(s) fail" in banner


def test_render_cde_drilldown_click_surfaces_failing_rows(monkeypatch):
    dp, cfg, result = _dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    event = {"selection": {"points": [{"y": "PLANVIEW_ID"}]}}
    dd._render_cde_drilldown("EPT", dp, result, cfg, event)
    shown = fake_st.dataframe.call_args[0][0]
    assert list(shown.index) == [3]


def test_render_cde_drilldown_no_selection_shows_hint(monkeypatch):
    dp, cfg, result = _dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    dd._render_cde_drilldown("EPT", dp, result, cfg, {"selection": {"points": []}})
    fake_st.caption.assert_called_once()
    fake_st.dataframe.assert_not_called()


def test_render_dimension_drilldown_no_selection_shows_hint(monkeypatch):
    dp, cfg, result = _dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    dd._render_dimension_drilldown("EPT", dp, result, cfg,
                                   {"selection": {"points": []}})
    fake_st.caption.assert_called_once()
    fake_st.dataframe.assert_not_called()


def test_render_dimension_drilldown_click_surfaces_failing_rows(monkeypatch):
    dp, cfg, result = _dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    event = {"selection": {"points": [{"y": "Completeness"}]}}
    dd._render_dimension_drilldown("EPT", dp, result, cfg, event)
    shown = fake_st.dataframe.call_args[0][0]
    assert list(shown.index) == [3]


def test_render_rule_drilldown_selected_row_maps_to_rule(monkeypatch):
    dp, cfg, result = _dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    df_rules = pd.DataFrame([
        {"CDE": "PLANVIEW_ID", "Dimension": "Completeness",
         "Weight (%)": 100.0, "Status": "Evaluated", "Pass rate (%)": 75.0},
    ])
    event = {"selection": {"rows": [0]}}
    dd._render_rule_drilldown("EPT", dp, result, cfg, df_rules, event)
    shown = fake_st.dataframe.call_args[0][0]
    assert list(shown.index) == [3]


def test_render_rule_drilldown_not_computed_shows_info(monkeypatch):
    dp, cfg, result = _dp_cfg_result()
    result.not_computed_standard_rules["PLANVIEW_ID::Completeness"] = "boom"
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    df_rules = pd.DataFrame([
        {"CDE": "PLANVIEW_ID", "Dimension": "Completeness",
         "Weight (%)": 100.0, "Status": "Not computed",
         "Pass rate (%)": float("nan")},
    ])
    dd._render_rule_drilldown("EPT", dp, result, cfg, df_rules,
                              {"selection": {"rows": [0]}})
    fake_st.info.assert_called_once()
    fake_st.dataframe.assert_not_called()


# ------------------------------------------------- custom-only (One-click)

def _custom_only_dp_cfg_result():
    """EPT scored with only the Custom source (One-click shape): E1 fails
    on row 1 (null CODE_OF_RESOURCE); ``cfg.assignments`` is empty."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", "PV-002", "PV-003", "PV-004"],
        "CODE_OF_RESOURCE": ["LOC-A", None, "LOC-C", "LOC-D"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV", "PROD", "DEC"],
    })
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100.0)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    return dp, cfg, result


def test_custom_rule_meta_maps_columns_and_type():
    _, cfg, _ = _custom_only_dp_cfg_result()
    meta = dd._custom_rule_meta(cfg, "EPT")
    cols, rule_type = meta["E1"]
    assert "CODE_OF_RESOURCE" in cols
    assert rule_type == "Completeness"


def test_cde_drilldown_works_for_custom_only_config(monkeypatch):
    """Regression: a By-CDE bar built from Custom rules (e.g. a One-click
    run, where ``cfg.assignments`` is empty) must drill down to the rows the
    Custom rule fails - not report "No computed rule"."""
    dp, cfg, result = _custom_only_dp_cfg_result()
    # The bar the user clicks exists on the chart (scored via E1).
    assert "CODE_OF_RESOURCE" in result.cde_scores
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    event = {"selection": {"points": [{"y": "CODE_OF_RESOURCE"}]}}
    dd._render_cde_drilldown("EPT", dp, result, cfg, event)
    fake_st.info.assert_not_called()
    shown = fake_st.dataframe.call_args[0][0]
    assert list(shown.index) == [1]


def test_dimension_drilldown_works_for_custom_only_config(monkeypatch):
    """Regression: By-Dimension bars come from Custom rule *types* when only
    the Custom source is selected - drill-down must follow the same mapping."""
    dp, cfg, result = _custom_only_dp_cfg_result()
    assert "Completeness" in result.dimension_scores
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    event = {"selection": {"points": [{"y": "Completeness"}]}}
    dd._render_dimension_drilldown("EPT", dp, result, cfg, event)
    fake_st.info.assert_not_called()
    shown = fake_st.dataframe.call_args[0][0]
    assert list(shown.index) == [1]


def test_cde_drilldown_combines_standard_and_custom_rules(monkeypatch):
    """A CDE covered by both sources flags rows failing either rule."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", None, "PV-003", "PV-004"],
        "CODE_OF_RESOURCE": ["LOC-A", "LOC-B", None, "LOC-D"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV", "PROD", "DEC"],
    })
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID", "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        assignments=[
            DQRAssignment("CODE_OF_RESOURCE", "Completeness", weight=100.0),
        ],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100.0)],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 50.0, "custom": 50.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    event = {"selection": {"points": [{"y": "CODE_OF_RESOURCE"}]}}
    dd._render_cde_drilldown("EPT", dp, result, cfg, event)
    shown = fake_st.dataframe.call_args[0][0]
    # Row 2 fails both the Standard rule and E1 on CODE_OF_RESOURCE.
    assert list(shown.index) == [2]


def test_custom_rule_meta_skips_unknown_rule_id():
    _, _, _ = _custom_only_dp_cfg_result()
    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[CustomDQRAssignment(rule_id="NOPE", weight=100.0)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    assert dd._custom_rule_meta(cfg, "EPT") == {}


def test_cde_drilldown_unknown_label_shows_info(monkeypatch):
    dp, cfg, result = _custom_only_dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    event = {"selection": {"points": [{"y": "NOT_A_CDE"}]}}
    dd._render_cde_drilldown("EPT", dp, result, cfg, event)
    fake_st.info.assert_called_once()
    fake_st.dataframe.assert_not_called()


def test_dimension_drilldown_unknown_label_shows_info(monkeypatch):
    dp, cfg, result = _custom_only_dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    event = {"selection": {"points": [{"y": "NOT_A_DIMENSION"}]}}
    dd._render_dimension_drilldown("EPT", dp, result, cfg, event)
    fake_st.info.assert_called_once()
    fake_st.dataframe.assert_not_called()


def test_rule_drilldown_rule_without_flags_shows_info(monkeypatch):
    """A rule row whose rule produced no flags (not in ``not_computed``
    either - e.g. a stale table row) falls back to an info message."""
    dp, cfg, result = _dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    df_rules = pd.DataFrame([
        {"CDE": "GHOST", "Dimension": "Uniqueness",
         "Weight (%)": 10.0, "Status": "Evaluated", "Pass rate (%)": 50.0},
    ])
    dd._render_rule_drilldown("EPT", dp, result, cfg, df_rules,
                              {"selection": {"rows": [0]}})
    fake_st.info.assert_called_once()
    fake_st.dataframe.assert_not_called()


def test_rule_drilldown_no_selection_shows_hint(monkeypatch):
    dp, cfg, result = _dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    dd._render_rule_drilldown("EPT", dp, result, cfg, pd.DataFrame(),
                              {"selection": {"rows": []}})
    fake_st.caption.assert_called_once()
    fake_st.dataframe.assert_not_called()


# --------------------------------------------- custom rule table drill-down

def _custom_table_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"Rule ID": "E1", "Name": "ISO Code of Account Present (COR + SAB)",
         "Type": "Completeness", "Blocking": "Yes", "Status": "Evaluated",
         "Weight (%)": 100.0, "Pass rate (%)": 75.0},
    ])


def test_custom_rule_drilldown_selected_row_surfaces_failing_rows(monkeypatch):
    dp, cfg, result = _custom_only_dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    dd._render_custom_rule_drilldown("EPT", dp, result, cfg, _custom_table_df(),
                                     {"selection": {"rows": [0]}})
    shown = fake_st.dataframe.call_args[0][0]
    assert list(shown.index) == [1]


def test_custom_rule_drilldown_no_selection_shows_hint(monkeypatch):
    dp, cfg, result = _custom_only_dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    dd._render_custom_rule_drilldown("EPT", dp, result, cfg, _custom_table_df(),
                                     {"selection": {"rows": []}})
    fake_st.caption.assert_called_once()
    fake_st.dataframe.assert_not_called()


def test_custom_rule_drilldown_not_evaluated_shows_info(monkeypatch):
    dp, cfg, result = _custom_only_dp_cfg_result()
    result.not_evaluated_custom_rules["E1"] = "reference dataset unavailable"
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    dd._render_custom_rule_drilldown("EPT", dp, result, cfg, _custom_table_df(),
                                     {"selection": {"rows": [0]}})
    fake_st.info.assert_called_once()
    fake_st.dataframe.assert_not_called()


def test_custom_rule_drilldown_rule_without_flags_shows_info(monkeypatch):
    dp, cfg, result = _custom_only_dp_cfg_result()
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    ghost = _custom_table_df().assign(**{"Rule ID": "ZZ", "Name": "Ghost"})
    dd._render_custom_rule_drilldown("EPT", dp, result, cfg, ghost,
                                     {"selection": {"rows": [0]}})
    fake_st.info.assert_called_once()
    fake_st.dataframe.assert_not_called()


def test_render_failing_rows_appends_reference_columns(monkeypatch):
    """A DP whose custom rules declare a reference dataset gets the
    reference columns appended to the drill-down table (parity with the
    Worst-rows tab and the CSV export)."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-99999"],
        "CODE_OF_RESOURCE": ["LOC-A", None],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV"],
    })
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID", "CODE_OF_RESOURCE"],
        custom_assignments=[
            CustomDQRAssignment(rule_id="E1", weight=50.0),
            CustomDQRAssignment(rule_id="E7", weight=50.0),
        ],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    mask = pd.Series([False, True], index=df.index)
    dd._render_failing_rows(dp, result, cfg, mask, context="CDE X", key="k")
    shown = fake_st.dataframe.call_args[0][0]
    assert any("[" in str(c) and "]" in str(c) for c in shown.columns), (
        f"expected reference-dataset columns, got {list(shown.columns)}"
    )


def test_render_failing_rows_caps_at_max(monkeypatch):
    n = dd._MAX_DRILLDOWN_ROWS + 50
    df = pd.DataFrame({
        "PLANVIEW_ID": [None] * n,
        "CODE_OF_RESOURCE": ["LOC-A"] * n,
    })
    dp = _ept_dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100.0)],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    fake_st = MagicMock()
    monkeypatch.setattr(dd, "st", fake_st)
    mask = pd.Series([True] * n, index=df.index)
    dd._render_failing_rows(dp, result, cfg, mask, context="CDE PLANVIEW_ID", key="k")
    shown = fake_st.dataframe.call_args[0][0]
    assert len(shown) == dd._MAX_DRILLDOWN_ROWS
    # The truncation notice mentions the full failing count.
    caption = fake_st.caption.call_args[0][0]
    assert f"{n:,}" in caption
