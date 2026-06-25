"""Tests that close the remaining small coverage gaps across the codebase.

Covers a long list of one-off branches identified from
``pytest --cov-report=term-missing``:

* utils/session_state.py: planview filter parse + render + ML-Lab visibility
* ui/step_02 filter banner / empty callout branches
* ui/step_03 duplicate-column and missing-column branches
* ui/step_04_dqr_assignment validation feedback branches
* ui/step_05 over-100% style branch
* ui/step_06 yellow status / not-computed warnings / ML-Lab nav branch
* src/dqr_validation: every per-dimension validator's edge branches
* src/data_product_builder: PLANVIEW_ID filter when SHARED_KEY is absent
* src/dqr_engine: empty-assignments early return
* src/reference_data: snowflake branch for the ACCE COA loader
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.models import ColumnProfile, DataProduct, DQRAssignment


@contextmanager
def _patch_session_st(fake_st):
    """Apply a fake ``st`` to every sub-module of ``utils.session``.

    Required since M7 partitioned ``utils/session_state.py`` into
    :mod:`utils.session.state` / :mod:`utils.session.navigation` /
    :mod:`utils.session.sidebar`; each holds its own ``import streamlit
    as st`` so a single patch on the legacy module no longer affects the
    rendering helpers.
    """
    with patch("utils.session.state.st", fake_st), \
         patch("utils.session.navigation.st", fake_st), \
         patch("utils.session.sidebar.st", fake_st):
        yield


# ===========================================================================
# utils/session_state.py
# ===========================================================================

def test_parse_planview_filter_handles_commas_semicolons_and_dedupes():
    from utils.session_state import _parse_planview_filter_text
    out = _parse_planview_filter_text("PV-1, PV-2; PV-1\nPV-3   PV-2")
    assert out == ["PV-1", "PV-2", "PV-3"]


def test_parse_planview_filter_handles_blank_input():
    from utils.session_state import _parse_planview_filter_text
    assert _parse_planview_filter_text("") == []
    assert _parse_planview_filter_text("   ") == []


def test_get_planview_filter_returns_copy():
    from utils import session_state as ss_mod

    fake_st = MagicMock()
    fake_st.session_state = {"planview_filter": ["PV-A"]}
    with _patch_session_st(fake_st):
        out = ss_mod.get_planview_filter()
    assert out == ["PV-A"]
    out.append("X")  # mutating result must not affect session state
    assert fake_st.session_state["planview_filter"] == ["PV-A"]


def test_ml_lab_visibility_true_when_already_on_step():
    """Covers the ``current_step == "ml_lab"`` short-circuit branch."""
    from utils import session_state as ss_mod

    fake_st = MagicMock()
    fake_st.session_state = {"current_step": "ml_lab", "scorecards": {}}
    with _patch_session_st(fake_st):
        assert ss_mod._ml_lab_visible() is True


def test_render_planview_filter_no_change_emits_neutral_pill():
    from utils import session_state as ss_mod

    fake_st = MagicMock()
    # ``domain`` must be set; ``render_planview_filter`` no-ops on
    # Step 0 before a domain has been picked (the filter widget is
    # domain-aware - see config.domains.ProjectFilterDef).
    fake_st.session_state = {"domain": "cost_estimate", "planview_filter": []}
    captured: list[str] = []
    fake_st.sidebar.markdown = MagicMock(
        side_effect=lambda t, **kw: captured.append(t)
    )
    fake_st.sidebar.text_area = MagicMock(return_value="")

    with _patch_session_st(fake_st):
        ss_mod.render_planview_filter()

    assert any("All projects" in m for m in captured)


class _AttrDict(dict):
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(item) from e

    def __setattr__(self, key, value):
        self[key] = value


def test_render_planview_filter_change_invalidates_caches_and_reruns():
    from utils import session_state as ss_mod

    fake_st = MagicMock()
    fake_st.session_state = _AttrDict({
        "domain": "cost_estimate",
        "planview_filter": [],
        "data_products": {"A": object()},
        "configs": {"A": object()},
        "scorecards": {"A": object()},
    })
    fake_st.sidebar.markdown = MagicMock()
    fake_st.sidebar.text_area = MagicMock(return_value="PV-1, PV-2")

    class _RerunSignal(Exception):
        pass

    fake_st.rerun = MagicMock(side_effect=_RerunSignal)
    with _patch_session_st(fake_st), \
         patch("src.reference_data.clear_reference_cache") as mock_clear:
        with pytest.raises(_RerunSignal):
            ss_mod.render_planview_filter()

    assert fake_st.session_state["planview_filter"] == ["PV-1", "PV-2"]
    assert fake_st.session_state["data_products"] == {}
    assert fake_st.session_state["configs"] == {}
    assert fake_st.session_state["scorecards"] == {}
    mock_clear.assert_called_once()


def test_render_planview_filter_active_emits_ok_pill_with_count():
    from utils import session_state as ss_mod

    fake_st = MagicMock()
    fake_st.session_state = {"domain": "cost_estimate", "planview_filter": ["PV-A"]}
    captured: list[str] = []
    fake_st.sidebar.markdown = MagicMock(
        side_effect=lambda t, **kw: captured.append(t)
    )
    fake_st.sidebar.text_area = MagicMock(return_value="PV-A")

    with _patch_session_st(fake_st):
        ss_mod.render_planview_filter()

    assert any("Filtering on 1 project" in m for m in captured)


def test_render_planview_filter_skipped_when_no_domain():
    """Step 0 has not picked a domain yet: the filter widget is gated
    on ``session_state.domain`` so the sidebar stays clean (no filter
    can be rendered without knowing the active domain's filter column).
    """
    from utils import session_state as ss_mod

    fake_st = MagicMock()
    fake_st.session_state = {"domain": None, "planview_filter": []}
    fake_st.sidebar.markdown = MagicMock()
    fake_st.sidebar.text_area = MagicMock()

    with _patch_session_st(fake_st):
        ss_mod.render_planview_filter()

    fake_st.sidebar.markdown.assert_not_called()
    fake_st.sidebar.text_area.assert_not_called()


def test_render_planview_filter_uses_domain_filter_column_for_quality():
    """Quality domain filters on ``PROJECT_CODE``: the sidebar widget's
    label must reflect that, not the Cost-Estimate-shaped ``PLANVIEW_ID(s)``.
    """
    from utils import session_state as ss_mod

    fake_st = MagicMock()
    fake_st.session_state = {"domain": "quality", "planview_filter": []}
    fake_st.sidebar.markdown = MagicMock()
    fake_st.sidebar.text_area = MagicMock(return_value="")

    with _patch_session_st(fake_st):
        ss_mod.render_planview_filter()

    (label, *_), _ = fake_st.sidebar.text_area.call_args
    assert "PROJECT_CODE" in label


def test_render_planview_filter_active_singular_vs_plural():
    """Exercises the plural-suffix branch (covers the ``len(parsed) != 1`` arm)."""
    from utils import session_state as ss_mod

    fake_st = MagicMock()
    fake_st.session_state = {
        "domain": "cost_estimate",
        "planview_filter": ["PV-A", "PV-B"],
    }
    captured: list[str] = []
    fake_st.sidebar.markdown = MagicMock(
        side_effect=lambda t, **kw: captured.append(t)
    )
    fake_st.sidebar.text_area = MagicMock(return_value="PV-A\nPV-B")

    with _patch_session_st(fake_st):
        ss_mod.render_planview_filter()

    assert any("Filtering on 2 projects" in m for m in captured)


# ===========================================================================
# src/data_product_builder.py - PLANVIEW_ID filter
# ===========================================================================

def test_apply_planview_filter_returns_df_when_column_absent():
    """Covers the ``SHARED_KEY not in df.columns`` defensive branch."""
    from src.data_product_builder import _apply_planview_filter

    df = pd.DataFrame({"OTHER": [1, 2, 3]})
    out = _apply_planview_filter(df, ["PV-1"])
    assert out is df


def test_apply_planview_filter_returns_df_when_filter_empty():
    from src.data_product_builder import _apply_planview_filter

    df = pd.DataFrame({"PLANVIEW_ID": ["A", "B"]})
    assert _apply_planview_filter(df, []) is df
    assert _apply_planview_filter(df, None) is df


def test_apply_planview_filter_keeps_matching_rows():
    """Exercises lines 84-85: build the wanted set and return the filtered df."""
    from src.data_product_builder import _apply_planview_filter

    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2", "PV-3"],
        "VAL": [10, 20, 30],
    })
    out = _apply_planview_filter(df, ["PV-2", "PV-3"])
    assert list(out["PLANVIEW_ID"]) == ["PV-2", "PV-3"]
    assert list(out["VAL"]) == [20, 30]


# ===========================================================================
# src/dqr_engine.py - empty assignments early return
# ===========================================================================

def test_evaluate_all_safe_empty_assignments_returns_empty_results():
    from src.dqr_engine import evaluate_all_safe

    df = pd.DataFrame({"A": [1, 2, 3]})
    out, not_computed = evaluate_all_safe(df, [], profiles={})
    assert out.empty
    assert list(out.index) == [0, 1, 2]
    assert not_computed == {}


# ===========================================================================
# src/reference_data.py - snowflake branch
# ===========================================================================

def test_load_acce_coa_master_snowflake_branch(monkeypatch):
    """Covers lines 99-102 - the snowflake fetch path for ACCE COA master."""
    from config import settings as settings_mod
    from src import reference_data as ref_mod

    monkeypatch.setattr(
        ref_mod, "SETTINGS", settings_mod.Settings(data_source="snowflake")
    )
    fake_client = MagicMock()
    fake_client.fetch_query.return_value = pd.DataFrame({
        "ICARUS_COA": ["A"], "ISO_COR": ["B"], "SAB": ["C"],
    })
    with patch("src.snowflake_client.get_shared_client", return_value=fake_client):
        out = ref_mod._load_acce_coa_master()

    fake_client.fetch_query.assert_called_once()
    sql = fake_client.fetch_query.call_args[0][0]
    assert "ACCE_COA_MASTER" in sql
    assert list(out.columns) == ["ICARUS_COA", "ISO_COR", "SAB"]


# ===========================================================================
# src/dqr_validation.py - per-dimension edge branches
# ===========================================================================

def _profile(name="X", group="text", dtype="object", *,
             total_rows=10, null_count=0, null_pct=0.0,
             distinct_count=10, duplicate_count=0,
             sample_values=("a",)) -> ColumnProfile:
    return ColumnProfile(
        name=name, dtype=dtype, column_type_group=group,
        total_rows=total_rows, null_count=null_count, null_pct=null_pct,
        distinct_count=distinct_count, duplicate_count=duplicate_count,
        sample_values=list(sample_values),
    )


def test_validity_warns_when_length_bounds_used_on_numeric():
    from src.dqr_validation import validate_assignment

    a = DQRAssignment("X", "Validity", weight=10,
                      params={"min_length": 1, "max_length": 5})
    report = validate_assignment(a, _profile(group="integer", dtype="int64"))
    msgs = [i.message for i in report.warnings]
    assert any("numeric columns" in m for m in msgs)


def test_validity_warns_when_regex_used_on_temporal():
    from src.dqr_validation import validate_assignment

    a = DQRAssignment("X", "Validity", weight=10,
                      params={"regex": r"\d{4}"})
    report = validate_assignment(
        a, _profile(group="datetime", dtype="datetime64[ns]")
    )
    msgs = [i.message for i in report.warnings]
    assert any("date/datetime columns" in m for m in msgs)


def test_validity_errors_when_lengths_non_integer():
    from src.dqr_validation import validate_assignment

    a = DQRAssignment("X", "Validity", weight=10,
                      params={"min_length": "abc", "max_length": "xyz"})
    report = validate_assignment(a, _profile())
    msgs = [i.message for i in report.errors]
    assert any("Min length and max length must be integers" in m for m in msgs)


def test_accuracy_errors_when_bounds_non_numeric():
    from src.dqr_validation import validate_assignment

    a = DQRAssignment("X", "Accuracy", weight=10,
                      params={"min_value": "lo", "max_value": "hi"})
    report = validate_assignment(
        a, _profile(group="integer", dtype="int64")
    )
    msgs = [i.message for i in report.errors]
    assert any("Accuracy bounds must be numeric" in m for m in msgs)


def test_value_list_warns_when_some_entries_not_numeric_for_numeric_cde():
    """Triggers _validate_value_list non-numeric branch + the ``…`` overflow
    suffix when more than 3 entries are bad."""
    from src.dqr_validation import validate_assignment

    a = DQRAssignment("X", "Conformity", weight=10,
                      params={"allowed_values": ["1", "two", "three", "four", "five"]})
    report = validate_assignment(
        a, _profile(group="integer", dtype="int64")
    )
    msgs = [i.message for i in report.warnings]
    assert any("not numeric" in m and "…" in m for m in msgs)


def test_value_list_no_warning_when_empty():
    from src.dqr_validation import validate_assignment

    a = DQRAssignment("X", "Conformity", weight=10, params={"allowed_values": []})
    report = validate_assignment(
        a, _profile(group="integer", dtype="int64")
    )
    # Compatible numeric CDE, empty list → no warning of any kind from the validator.
    assert all("not numeric" not in i.message for i in report.warnings)


def test_precision_errors_when_max_decimals_not_integer():
    from src.dqr_validation import validate_assignment

    a = DQRAssignment("X", "Precision", weight=10,
                      params={"max_decimals": "two"})
    report = validate_assignment(
        a, _profile(group="float", dtype="float64")
    )
    msgs = [i.message for i in report.errors]
    assert any("Max decimals must be an integer" in m for m in msgs)


def test_precision_errors_when_max_decimals_negative():
    from src.dqr_validation import validate_assignment

    a = DQRAssignment("X", "Precision", weight=10,
                      params={"max_decimals": -1})
    report = validate_assignment(
        a, _profile(group="float", dtype="float64")
    )
    msgs = [i.message for i in report.errors]
    assert any("Max decimals must be ≥ 0" in m for m in msgs)


def test_precision_returns_no_issues_when_max_decimals_none_or_ok():
    from src.dqr_validation import validate_assignment

    a = DQRAssignment("X", "Precision", weight=10,
                      params={"max_decimals": 3})
    report = validate_assignment(
        a, _profile(group="float", dtype="float64")
    )
    # Compatible, valid -> empty
    assert not any("decimals" in i.message.lower() for i in report.errors)


def test_positive_int_validator_handles_non_integer_and_negative():
    from src.dqr_validation import validate_assignment

    a = DQRAssignment("X", "Timeliness", weight=10,
                      params={"max_lag_days": "soon"})
    report = validate_assignment(
        a, _profile(group="datetime", dtype="datetime64[ns]")
    )
    assert any("integer" in i.message for i in report.errors)

    a2 = DQRAssignment("X", "Timeliness", weight=10,
                       params={"max_lag_days": 0})
    report2 = validate_assignment(
        a2, _profile(group="datetime", dtype="datetime64[ns]")
    )
    assert any("positive integer" in i.message for i in report2.errors)


def test_categories_compatible_handles_none_and_boolean():
    """Exercises the early-out / boolean and textual/temporal arms together."""
    from src.dqr_validation import _categories_compatible

    assert _categories_compatible(None, "integer") is False
    assert _categories_compatible("integer", None) is False
    assert _categories_compatible("boolean", "boolean") is True
    assert _categories_compatible("datetime", "date") is True
    # Two text-group columns are compatible (covers TEXTUAL_GROUPS arm).
    assert _categories_compatible("string", "string") is True
    assert _categories_compatible("integer", "text") is False


def test_value_list_compatible_numeric_entries_emit_no_warning():
    """Exercises ``return []`` after a numeric-CDE conformity check passes."""
    from src.dqr_validation import validate_assignment

    a = DQRAssignment(
        "X", "Conformity", weight=10,
        params={"allowed_values": ["1", "2", "3"]},
    )
    report = validate_assignment(a, _profile(group="integer", dtype="int64"))
    # All entries parse as numeric → no "not numeric" warning.
    assert all("not numeric" not in i.message for i in report.warnings)


def test_precision_returns_empty_when_max_decimals_missing():
    """Exercises the ``if md is None: return []`` branch."""
    from src.dqr_validation import _validate_precision

    profile = _profile(group="float", dtype="float64")
    assert _validate_precision(profile, {"max_decimals": None}) == []
    # And with the key entirely absent.
    assert _validate_precision(profile, {}) == []


def test_category_label_recognises_all_groups():
    from src.dqr_validation import _category_label

    assert _category_label("integer") == "numeric"
    assert _category_label("float") == "numeric"
    assert _category_label("datetime") == "date/datetime"
    assert _category_label("string") == "text"
    assert _category_label("boolean") == "boolean"
    assert _category_label("garbage") == "garbage"
    assert _category_label(None) == "unknown"


def test_looks_numeric_handles_none_and_invalid():
    from src.dqr_validation import _looks_numeric

    assert _looks_numeric(None) is False
    assert _looks_numeric("not-a-number") is False
    assert _looks_numeric("123.45") is True


def test_consistency_warning_on_ordering_for_boolean():
    """Ordering operators on a boolean CDE → warning branch."""
    from src.dqr_validation import validate_assignment

    profiles = {
        "X": _profile(name="X", group="boolean", dtype="bool"),
        "Y": _profile(name="Y", group="boolean", dtype="bool"),
    }
    a = DQRAssignment(
        "X", "Consistency", weight=10,
        params={"compare_column": "Y", "operator": "<="},
    )
    report = validate_assignment(a, profiles["X"], profiles)
    assert any("Ordering operators on boolean" in i.message
               for i in report.warnings)


# ===========================================================================
# ui/step_03_cde_selection - duplicate-column / missing-column branches
# ===========================================================================

def test_distinct_sample_for_missing_column_returns_empty():
    """Covers ``if col not in dp.df.columns: return []`` defensive branch."""
    from ui import step_03_cde_selection as s3

    df = pd.DataFrame({"A": [1, 2]})
    dp = DataProduct(
        system_code="X", name="X_DP", df=df, source_tables=["t"], profiles={},
    )
    assert s3._distinct_sample_for(dp, "MISSING_COL") == []


def test_build_required_columns_map_dedupes_within_rule_and_options():
    """A rule whose required + option columns share entries must not list the
    same rule_id twice for the same column (covers both ``seen`` branches)."""
    from ui import step_03_cde_selection as s3

    class _Opt:
        required_columns_when_enabled = {"a": "PLANVIEW_ID", "b": "PLANVIEW_ID"}

    class _Rule:
        id = "R1"
        required_columns = {"k1": "PLANVIEW_ID", "k2": "PLANVIEW_ID"}
        options = [_Opt()]

    with patch(
        "ui.step_03_cde_selection.get_available_custom_dqr_rules",
        return_value=[_Rule()],
    ):
        out = s3._build_required_columns_map("SYS")

    assert out == {"PLANVIEW_ID": ["R1"]}


# ===========================================================================
# ui/step_05_weight_assignment - over-100% style branch
# ===========================================================================

def test_render_weight_progress_over_100_uses_over_class():
    from ui import step_05_weight_assignment as s5

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))
    with patch.object(s5, "st", fake_st):
        s5._render_weight_progress(150.0)
    assert any("pct-fill over" in m for m in captured)


def test_render_weight_progress_under_100_uses_warn_class():
    from ui import step_05_weight_assignment as s5

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))
    with patch.object(s5, "st", fake_st):
        s5._render_weight_progress(40.0)
    assert any("pct-fill warn" in m for m in captured)


def test_render_weight_progress_at_100_uses_ok_class():
    from ui import step_05_weight_assignment as s5

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))
    with patch.object(s5, "st", fake_st):
        s5._render_weight_progress(100.0)
    assert any("pct-fill ok" in m for m in captured)


# ===========================================================================
# ui/step_06_dashboard - yellow status branch + ML Lab nav button
# ===========================================================================

def test_status_class_yellow_branch():
    from ui.step_06_dashboard import _status_class

    assert _status_class(85.0, green=80, yellow=60) == "s-green"
    assert _status_class(70.0, green=80, yellow=60) == "s-yellow"
    assert _status_class(40.0, green=80, yellow=60) == "s-red"


# ===========================================================================
# ui/step_04_dqr_assignment - validation feedback branches
# ===========================================================================

def test_render_validation_feedback_no_issues_emits_success():
    from src.dqr_validation import DQRValidationReport
    from ui import step_04_dqr_assignment as s4

    fake_st = MagicMock()
    with patch.object(s4, "st", fake_st):
        s4._render_validation_feedback(DQRValidationReport(issues=()))
    fake_st.success.assert_called_once()


def test_render_validation_feedback_errors_and_warnings_branch():
    from src.dqr_validation import DQRValidationIssue, DQRValidationReport
    from ui import step_04_dqr_assignment as s4

    report = DQRValidationReport(issues=(
        DQRValidationIssue("error", "bad config", "fix it"),
        DQRValidationIssue("warning", "be careful", "consider this"),
        DQRValidationIssue("error", "another bad"),
    ))
    fake_st = MagicMock()
    with patch.object(s4, "st", fake_st):
        s4._render_validation_feedback(report)
    # Two errors + one warning expected.
    assert fake_st.error.call_count == 2
    assert fake_st.warning.call_count == 1


def test_expander_status_tag_three_branches():
    from src.dqr_validation import DQRValidationIssue, DQRValidationReport
    from ui.step_04_dqr_assignment import _expander_status_tag

    err = DQRValidationReport(
        issues=(DQRValidationIssue("error", "x"),))
    warn = DQRValidationReport(
        issues=(DQRValidationIssue("warning", "x"),))
    ok = DQRValidationReport(issues=())

    assert "❌" in _expander_status_tag(err)
    assert "⚠" in _expander_status_tag(warn)
    assert "✅" in _expander_status_tag(ok)


# ===========================================================================
# ui/step_02_data_product_review - filter banner / empty callout branches
# ===========================================================================

def test_filter_banner_renders_chips_for_active_filter():
    from ui import step_02_data_product_review as s2

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))
    with patch.object(s2, "st", fake_st):
        s2._filter_banner(["PV-1", "PV-2"])
    body = captured[0]
    assert "Project filter active" in body
    assert "PV-1" in body
    assert "PV-2" in body
    assert "2 PLANVIEW_ID(s)" in body


def test_empty_callout_lists_each_system_with_chip():
    from ui import step_02_data_product_review as s2

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))
    with patch.object(s2, "st", fake_st):
        s2._empty_callout(["ADR", "EPT"])
    body = captured[0]
    assert "matched 0 rows" in body
    assert "ADR" in body
    assert "EPT" in body


# ===========================================================================
# Step 4.1 - DP status pills + error / warning branches
# ===========================================================================

def test_dp_status_errors_branch_returns_true_and_emits_error():
    from src.dqr_validation import DQRValidationIssue, DQRValidationReport
    from ui import step_04_dqr_assignment as s4

    err = DQRValidationReport(
        issues=(DQRValidationIssue("error", "incompatible"),))
    fake_st = MagicMock()
    with patch.object(s4, "st", fake_st):
        blocking = s4._render_dp_status([err], "EPT_DP", "EPT")
    assert blocking is True
    fake_st.error.assert_called_once()


def test_dp_status_warnings_branch_emits_warning_but_not_blocking():
    from src.dqr_validation import DQRValidationIssue, DQRValidationReport
    from ui import step_04_dqr_assignment as s4

    warn = DQRValidationReport(
        issues=(DQRValidationIssue("warning", "watch out"),))
    fake_st = MagicMock()
    with patch.object(s4, "st", fake_st):
        blocking = s4._render_dp_status([warn], "EPT_DP", "EPT")
    assert blocking is False
    fake_st.warning.assert_called_once()


def test_dp_status_ok_emits_neither_error_nor_warning():
    from src.dqr_validation import DQRValidationReport
    from ui import step_04_dqr_assignment as s4

    ok = DQRValidationReport(issues=())
    fake_st = MagicMock()
    with patch.object(s4, "st", fake_st):
        blocking = s4._render_dp_status([ok], "EPT_DP", "EPT")
    assert blocking is False
    fake_st.error.assert_not_called()
    fake_st.warning.assert_not_called()


# ===========================================================================
# Step 6 - per-rule columns skip rules absent from the eval matrix
# ===========================================================================

def test_per_rule_score_columns_skips_rules_not_in_evaluation_matrix():
    """Covers the ``if a.rule_id not in std_flags.columns: continue`` branch."""

    from src.data_product_builder import build_data_product
    from src.models import DataProductConfig, DQRAssignment
    from src.profiler import profile_dataframe
    from ui import step_06_dashboard as s6

    dp = build_data_product("EPT")
    dp.profiles = profile_dataframe(dp.df)
    # Mix one valid rule with one that targets a missing column so
    # ``evaluate_all_safe`` cannot evaluate it and skips the column.
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[
            DQRAssignment("PLANVIEW_ID", "Completeness", weight=50),
            DQRAssignment("NOT_REAL", "Completeness", weight=50),
        ],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    out = s6._per_rule_score_columns(dp, cfg)
    # Only one rule column should land in the output (the unevaluated rule is
    # silently skipped by the ``continue`` branch we wanted to cover).
    assert sum(1 for c in out.columns if c.startswith("STD · ")) == 1


# ===========================================================================
# Step 7 - additional small branches
# ===========================================================================

def test_render_empty_html_escapes_message():
    """Exercises ``_render_empty`` which is on a one-line call site."""
    # B5 moved ``_render_empty`` to ``ui.step_07._shared``; patch ``st``
    # there since that's where the helper looks it up.
    from ui.step_07 import _shared

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))
    with patch.object(_shared, "st", fake_st):
        _shared._render_empty("<script>alert('x')</script>")
    assert "&lt;script&gt;" in captured[0]
    assert "lab-empty" in captured[0]


def test_build_rule_flag_matrix_includes_custom_assignments():
    """Covers the ``if config.custom_assignments:`` branch in
    ``build_rule_flag_matrix`` (lines 200-217)."""
    from src import ml_lab
    from src.data_product_builder import build_data_product
    from src.models import CustomDQRAssignment, DataProductConfig
    from src.profiler import profile_dataframe

    dp = build_data_product("EPT")
    dp.profiles = profile_dataframe(dp.df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100.0)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    flags, meta = ml_lab.build_rule_flag_matrix(dp, cfg)
    # E1 must appear with source=Custom and the metadata pulled from the catalog.
    assert "E1" in flags.columns
    assert meta["E1"]["source"] == "Custom"
    assert meta["E1"]["weight"] == 100.0


def test_step_02_filter_banner_and_empty_callout_in_render(monkeypatch):
    """Drive step 2 with a planview filter that matches zero rows so both
    the filter banner (line 305) and the empty callout (line 331) render."""
    import os
    os.environ.setdefault("DATA_SOURCE", "mock")
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    app_path = str(Path(__file__).resolve().parent.parent / "app.py")
    at = AppTest.from_file(app_path, default_timeout=30)
    at.session_state["domain"] = "cost_estimate"
    at.session_state["current_step"] = "data_product_review"
    at.session_state["selected_systems"] = ["EPT"]
    # Empty list of products forces the build branch.
    at.session_state["data_products"] = {}
    # A filter that won't match anything in the mock data → empty callout.
    at.session_state["planview_filter"] = ["IMPOSSIBLE-ID-XYZ"]
    at.run()
    markdowns = [m.value for m in at.markdown]
    # Filter banner is rendered.
    assert any("Project filter active" in m for m in markdowns)
    # Empty callout is rendered because the filter matched zero rows.
    assert any("matched 0 rows" in m for m in markdowns)


def test_step_06_emits_warning_for_not_computed_standard_rules():
    """Drive step 6 with an unevaluatable Standard rule so the
    ``not_computed_standard_rules`` warning loop fires (lines 591-592)."""
    import os
    os.environ.setdefault("DATA_SOURCE", "mock")
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from src.data_product_builder import build_data_product
    from src.models import DataProductConfig, DQRAssignment
    from src.profiler import profile_dataframe
    from src.scorecard import compute_scorecard

    dp = build_data_product("EPT")
    dp.profiles = profile_dataframe(dp.df)
    # Use a column that exists but pair it with a dimension that is
    # incompatible so the validator emits an error and the engine marks
    # the rule as Not computed.
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[
            DQRAssignment("PLANVIEW_ID", "Completeness", weight=50),
            # PLANVIEW_ID is text → Precision is incompatible.
            DQRAssignment("PLANVIEW_ID", "Precision", weight=50,
                          params={"max_decimals": 2}),
        ],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.not_computed_standard_rules, (
        "Test setup precondition: at least one rule must be Not computed"
    )

    app_path = str(Path(__file__).resolve().parent.parent / "app.py")
    at = AppTest.from_file(app_path, default_timeout=60)
    at.session_state["domain"] = "cost_estimate"
    at.session_state["current_step"] = "dashboard"
    at.session_state["selected_systems"] = ["EPT"]
    at.session_state["data_products"] = {"EPT": dp}
    at.session_state["configs"] = {"EPT": cfg}
    at.session_state["scorecards"] = {"EPT": result}
    at.run()
    warning_values = [w.value for w in at.warning]
    assert any("could not be computed" in w for w in warning_values)


def test_step_06_ml_lab_button_navigates_to_ml_lab():
    """Click the 🧪 ML Lab button on the dashboard → current_step flips."""
    import os
    os.environ.setdefault("DATA_SOURCE", "mock")
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from src.data_product_builder import build_data_product
    from src.models import DataProductConfig, DQRAssignment
    from src.profiler import profile_dataframe
    from src.scorecard import compute_scorecard

    dp = build_data_product("EPT")
    dp.profiles = profile_dataframe(dp.df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)

    app_path = str(Path(__file__).resolve().parent.parent / "app.py")
    at = AppTest.from_file(app_path, default_timeout=60)
    at.session_state["domain"] = "cost_estimate"
    at.session_state["current_step"] = "dashboard"
    at.session_state["selected_systems"] = ["EPT"]
    at.session_state["data_products"] = {"EPT": dp}
    at.session_state["configs"] = {"EPT": cfg}
    at.session_state["scorecards"] = {"EPT": result}
    at.run()
    btn = [b for b in at.button if "ML Lab" in b.label]
    assert btn, "🧪 ML Lab nav button must be present on the dashboard"
    btn[0].click().run()
    assert at.session_state["current_step"] == "ml_lab"


def test_load_snapshot_from_csv_extracts_std_and_custom_rule_ids():
    """Covers lines 864-870 - both STD · and CUSTOM · header parsing."""
    from src.ml_lab import load_snapshot_from_csv

    csv = (
        "_row_score,_status,STD · A · Completeness (w=30%),"
        "CUSTOM · E1 · Some Rule (w=70%)\n"
        "90,GREEN,100,100\n"
        "40,RED,0,0\n"
    ).encode("utf-8")
    snap = load_snapshot_from_csv(csv, dp_code="EPT")
    assert "A::Completeness" in snap["rule_pass_rates"]
    assert "E1" in snap["custom_rule_pass_rates"]
    assert snap["dp_code"] == "EPT"


def test_load_snapshot_from_csv_raises_on_missing_row_score_column():
    """Covers the explicit ValueError when the column is missing (line 849)."""
    from src.ml_lab import load_snapshot_from_csv

    csv = b"OTHER\n1\n"
    with pytest.raises(ValueError, match="_row_score"):
        load_snapshot_from_csv(csv, dp_code="EPT")


def test_explain_row_score_with_custom_assignments_and_known_rule():
    """Covers the custom-rule branches of explain_row_score
    (1463-1477, 1497-1515) where a Custom DQR feeds the per-CDE deficit map."""
    from src.data_product_builder import build_data_product
    from src.ml_lab import explain_row_score
    from src.models import CustomDQRAssignment, DataProductConfig
    from src.profiler import profile_dataframe
    from src.scorecard import compute_scorecard

    dp = build_data_product("EPT")
    dp.profiles = profile_dataframe(dp.df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID", "WBC_LEVEL_1"],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100.0)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    # Pick a row that exists; explain it. The function exercises the custom-
    # assignments cde mapping branch, since E1 declares required columns in
    # the catalog.
    expl = explain_row_score(dp, cfg, result, row_index=dp.df.index[0])
    assert "row_score" in expl
    assert "per_rule" in expl
    # The per-rule frame includes the Custom row.
    assert "E1" in list(expl["per_rule"]["rule_id"])


def test_explain_row_score_with_unattributed_custom_rule():
    """Covers the `(unattributed)` branch (1517-1519). We hand-craft a
    failing custom assignment whose catalog entry returns no required columns
    so the deficit falls back to the ``(unattributed)`` bucket."""
    from unittest.mock import patch

    import pandas as _pd

    from src import ml_lab
    from src.data_product_builder import build_data_product
    from src.models import (
        CustomDQRAssignment,
        DataProductConfig,
        ScorecardResult,
    )
    from src.profiler import profile_dataframe

    dp = build_data_product("EPT")
    dp.profiles = profile_dataframe(dp.df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="MYRULE", weight=100.0)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )

    # Hand-build a ScorecardResult so the function consumes our fail flags.
    n = min(5, dp.row_count)
    row_idx = dp.df.index[:n]
    row_scores = _pd.Series([0.0] * n, index=row_idx, dtype=float)
    result = ScorecardResult(
        system_code="EPT",
        overall_score=0.0,
        threshold_green=80, threshold_yellow=60,
        total_rows=n, rows_green=0, rows_yellow=0, rows_red=n,
        cde_scores={"PLANVIEW_ID": 0.0},
        dimension_scores={"Custom": 0.0},
        rule_pass_rates={},
        custom_rule_pass_rates={"MYRULE": 0.0},
        row_scores=row_scores,
        standard_score=None,
        custom_score=0.0,
        source_weights={"custom": 100.0},
    )

    # Patch the inner build_rule_flag_matrix to return a failing MYRULE flag
    # so the per-row contribution branch fires.
    flags = _pd.DataFrame({"MYRULE": [False] * n}, index=row_idx)
    rule_meta = {"MYRULE": {"source": "Custom", "label": "MYRULE", "weight": 100.0}}
    with patch.object(ml_lab, "build_rule_flag_matrix",
                      return_value=(flags, rule_meta)), \
         patch("config.custom_dqr_catalog.get_available_custom_dqr_rules",
               return_value=[]):
        expl = ml_lab.explain_row_score(
            dp, cfg, result, row_index=row_idx[0],
        )
    cdes = list(expl["per_cde"]["cde"]) if not expl["per_cde"].empty else []
    assert "(unattributed)" in cdes


def test_step_07_ensure_scorecards_skips_dp_without_assignments():
    """Covers line 223 - the ``continue`` branch when a config has no
    Standard or Custom assignments."""
    import os
    os.environ.setdefault("DATA_SOURCE", "mock")
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from src.data_product_builder import build_data_product
    from src.models import DataProductConfig
    from src.profiler import profile_dataframe

    # Two DPs: one with assignments, one without.
    dp_ept = build_data_product("EPT")
    dp_ept.profiles = profile_dataframe(dp_ept.df)
    cfg_ept = DataProductConfig(
        system_code="EPT", cdes=[], assignments=[], custom_assignments=[],
        dqr_sources=[], source_weights={},
    )

    app_path = str(Path(__file__).resolve().parent.parent / "app.py")
    at = AppTest.from_file(app_path, default_timeout=30)
    at.session_state["domain"] = "cost_estimate"
    at.session_state["current_step"] = "ml_lab"
    at.session_state["data_products"] = {"EPT": dp_ept}
    at.session_state["configs"] = {"EPT": cfg_ept}
    at.session_state["scorecards"] = {}
    at.run()
    # No scorecards were recomputed → ML Lab renders the empty state.
    markdowns = [m.value for m in at.markdown]
    assert any("ML Lab needs at least" in m for m in markdowns)


def test_step_04_1_render_emits_resolve_error_when_assignments_incompatible():
    """Drive step 4.1 with an incompatible CDE/dim pair so render's
    ``has_errors`` branch (line 582) and ``invalid_dps.append`` branch
    (line 563) both fire."""
    import os
    os.environ.setdefault("DATA_SOURCE", "mock")
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from src.data_product_builder import build_data_product
    from src.models import DataProductConfig, DQRAssignment
    from src.profiler import profile_dataframe

    dp = build_data_product("EPT")
    dp.profiles = profile_dataframe(dp.df)
    # PLANVIEW_ID is a text column → Precision is incompatible.
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[
            DQRAssignment("PLANVIEW_ID", "Precision", weight=100,
                          params={"max_decimals": 2}),
        ],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )

    app_path = str(Path(__file__).resolve().parent.parent / "app.py")
    at = AppTest.from_file(app_path, default_timeout=60)
    at.session_state["domain"] = "cost_estimate"
    at.session_state["current_step"] = "dqr_assignment"
    at.session_state["selected_systems"] = ["EPT"]
    at.session_state["data_products"] = {"EPT": dp}
    at.session_state["configs"] = {"EPT": cfg}
    at.run()
    errors = [e.value for e in at.error]
    assert any("Resolve the incompatible" in e for e in errors)


def test_ml_lab_dp_picker_radio_sklearn_not_installed_emits_caption(monkeypatch):
    """When sklearn is missing, the picker emits an informational caption."""
    from ui import step_07_ml_lab as s7

    fake_st = MagicMock()
    fake_st.session_state = {}

    class _Col:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    fake_st.columns = MagicMock(return_value=[_Col(), _Col()])
    fake_st.radio = MagicMock(return_value=0)
    fake_st.toggle = MagicMock()
    fake_st.caption = MagicMock()

    with patch.object(s7, "st", fake_st), \
         patch.object(s7, "sklearn_status",
                      return_value={"available": False, "version": None}):
        out = s7._render_dp_picker({"EPT": object()})
    assert out == "EPT"
    fake_st.caption.assert_called_once()
    fake_st.toggle.assert_not_called()
