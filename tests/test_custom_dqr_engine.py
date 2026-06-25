"""Tests for the custom DQR engine and the EPT E1 rule.

Covers user-spec scenarios 6 (EPT has E1), 9 (E1 passes when complete),
10 (E1 fails on missing CODE_OF_RESOURCE), 11 (E1 fails on missing
STANDARD_ACTIVITY_BREAKDOWN), plus the missing-required-columns branch in
the dispatcher.
"""
from __future__ import annotations

import pandas as pd
import pytest

from config.custom_dqr_catalog import get_available_custom_dqr_rules
from src.custom_dqr_engine import (
    EPT_E1_REQUIRED_COLUMNS,
    check_ept_e1,
    evaluate_custom_rules,
)
from src.models import CustomDQRAssignment


@pytest.fixture
def complete_ept_df() -> pd.DataFrame:
    return pd.DataFrame({
        "CODE_OF_RESOURCE": ["LOC-A", "LOC-B", "LOC-C"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXPLORATION", "DEVELOPMENT", "PRODUCTION"],
    })


def test_ept_has_custom_rule_e1_available():
    """Scenario 6: EPT catalog exposes E1 with the documented metadata."""
    rules = get_available_custom_dqr_rules("EPT")
    by_id = {r.id: r for r in rules}
    assert "E1" in by_id
    rule = by_id["E1"]
    assert rule.type == "Completeness"
    assert rule.blocking is True
    assert rule.required_columns == {
        "COR": "CODE_OF_RESOURCE",
        "SAB": "STANDARD_ACTIVITY_BREAKDOWN",
    }


def test_ept_e1_passes_when_both_columns_complete(complete_ept_df):
    """Scenario 9: every row passes when both required columns are filled."""
    result = check_ept_e1(complete_ept_df)
    assert result.tolist() == [True, True, True]


def test_ept_e1_fails_when_code_of_resource_missing():
    """Scenario 10: rows with null/blank CODE_OF_RESOURCE fail."""
    df = pd.DataFrame({
        "CODE_OF_RESOURCE": ["LOC-A", None, "", "  "],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXPLORATION"] * 4,
    })
    result = check_ept_e1(df)
    assert result.tolist() == [True, False, False, False]


def test_ept_e1_fails_when_standard_activity_breakdown_missing():
    """Scenario 11: rows with null/blank STANDARD_ACTIVITY_BREAKDOWN fail."""
    df = pd.DataFrame({
        "CODE_OF_RESOURCE": ["LOC-A"] * 4,
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXPLORATION", None, "", "   "],
    })
    result = check_ept_e1(df)
    assert result.tolist() == [True, False, False, False]


def test_ept_e1_fails_for_all_rows_when_required_column_missing():
    """If a required column is absent from the DataFrame, the rule must fail
    for every row instead of raising, so the scorecard pipeline keeps running."""
    df = pd.DataFrame({"CODE_OF_RESOURCE": ["LOC-A", "LOC-B"]})
    result = check_ept_e1(df)
    assert result.tolist() == [False, False]


def test_evaluate_custom_rules_empty_assignments_returns_empty_df(complete_ept_df):
    out, not_evaluated = evaluate_custom_rules(complete_ept_df, [], "EPT")
    assert out.shape == (0, 0) or out.shape[1] == 0
    assert not_evaluated == {}


def test_evaluate_custom_rules_dispatches_to_e1(complete_ept_df):
    assignments = [CustomDQRAssignment(rule_id="E1", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(complete_ept_df, assignments, "EPT")
    assert list(out.columns) == ["E1"]
    assert out["E1"].tolist() == [True, True, True]
    assert not_evaluated == {}


def test_evaluate_custom_rules_skips_unknown_rule_id(complete_ept_df):
    assignments = [CustomDQRAssignment(rule_id="NOT_A_RULE", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(complete_ept_df, assignments, "EPT")
    assert "NOT_A_RULE" not in out.columns
    assert not_evaluated == {}


def test_ept_e1_required_columns_constant_matches_catalog():
    """Constant exported from the engine matches the catalog metadata."""
    rule = next(
        r for r in get_available_custom_dqr_rules("EPT") if r.id == "E1"
    )
    assert rule.required_columns == EPT_E1_REQUIRED_COLUMNS


# =============================================================================
# E4: Level 1 cost category populated (Completeness on WBC_LEVEL_1)
# =============================================================================

def test_ept_has_custom_rule_e4_available():
    """EPT catalog exposes E4 with the documented metadata."""
    rules = get_available_custom_dqr_rules("EPT")
    by_id = {r.id: r for r in rules}
    assert "E4" in by_id
    rule = by_id["E4"]
    assert rule.type == "Completeness"
    assert rule.required_columns == {"Level 1": "WBC_LEVEL_1"}


def test_ept_e4_uses_wbc_level_1_as_required_column():
    rule = next(
        r for r in get_available_custom_dqr_rules("EPT") if r.id == "E4"
    )
    assert "WBC_LEVEL_1" in rule.required_columns.values()


def test_ept_e4_passes_when_wbc_level_1_populated():
    from src.custom_dqr_engine import check_ept_e4
    df = pd.DataFrame({"WBC_LEVEL_1": ["L1_CAPEX", "L1_OPEX", "L1_LABOR"]})
    assert check_ept_e4(df).tolist() == [True, True, True]


def test_ept_e4_fails_when_wbc_level_1_null():
    from src.custom_dqr_engine import check_ept_e4
    df = pd.DataFrame({"WBC_LEVEL_1": ["L1_CAPEX", None, "L1_LABOR"]})
    assert check_ept_e4(df).tolist() == [True, False, True]


def test_ept_e4_fails_when_wbc_level_1_blank():
    from src.custom_dqr_engine import check_ept_e4
    df = pd.DataFrame({"WBC_LEVEL_1": ["L1_CAPEX", "", "L1_LABOR"]})
    assert check_ept_e4(df).tolist() == [True, False, True]


def test_ept_e4_fails_when_wbc_level_1_whitespace_only():
    from src.custom_dqr_engine import check_ept_e4
    df = pd.DataFrame({"WBC_LEVEL_1": ["L1_CAPEX", "   ", "\t\n"]})
    assert check_ept_e4(df).tolist() == [True, False, False]


def test_ept_e4_fails_for_all_rows_when_wbc_level_1_column_missing():
    """Schema-level missing column → rule fails for every row (does not raise
    or silently pass)."""
    from src.custom_dqr_engine import check_ept_e4
    df = pd.DataFrame({"OTHER_COL": ["x", "y"]})
    assert check_ept_e4(df).tolist() == [False, False]


# =============================================================================
# E3: Statistical Excessive WBC-to-ISO Mapping (group-level percentile,
# row-level verdict)
# =============================================================================

def _e3_required_cols():
    return [
        "WBC_LEVEL_5",
        "CODE_OF_RESOURCE",
        "STANDARD_ACTIVITY_BREAKDOWN",
        "TOTAL_HOURS",
        "TOTAL_COST_USD",
    ]


def _make_e3_df(rows):
    """Build an EPT-shaped DataFrame from a list of dicts. Any column not
    provided defaults to a sensible placeholder so individual tests stay
    short."""
    cols = _e3_required_cols()
    completed = [
        {
            **{c: None for c in cols},
            **r,
        }
        for r in rows
    ]
    return pd.DataFrame(completed, columns=cols)


def test_ept_has_custom_rule_e3_available():
    """EPT catalog exposes E3 as a non-blocking statistical-outlier rule."""
    rules = get_available_custom_dqr_rules("EPT")
    by_id = {r.id: r for r in rules}
    assert "E3" in by_id
    rule = by_id["E3"]
    assert rule.type == "Statistical Outlier"
    assert rule.blocking is False
    assert rule.reference is None
    assert rule.required_columns == {
        "WBC Level 5": "WBC_LEVEL_5",
        "COR": "CODE_OF_RESOURCE",
        "SAB": "STANDARD_ACTIVITY_BREAKDOWN",
        "Total Hours": "TOTAL_HOURS",
        "Total Cost (USD)": "TOTAL_COST_USD",
    }


def test_ept_e3_passes_when_no_outlier_iso_mapping():
    """All ISO mappings have the same WBC-to-ISO ratio → P90 == ratio,
    nothing exceeds the threshold, every row passes."""
    from src.custom_dqr_engine import check_ept_e3
    rows = []
    for cor, sab in [("A", "S1"), ("B", "S1"), ("C", "S1")]:
        for wbc in ("W1", "W2"):
            rows.append({
                "WBC_LEVEL_5": wbc,
                "CODE_OF_RESOURCE": cor,
                "STANDARD_ACTIVITY_BREAKDOWN": sab,
                "TOTAL_HOURS": 10.0,
                "TOTAL_COST_USD": 5_000.0,
            })
    df = _make_e3_df(rows)
    assert check_ept_e3(df).all()


def test_ept_e3_fails_for_outlier_iso_mapping_when_material():
    """An ISO mapping that aggregates many more WBCs than its peers AND is
    material (cost above the 100k threshold) fails, and every row inside
    that group inherits the FAIL."""
    from src.custom_dqr_engine import check_ept_e3
    rows = []
    # Peers: 5 ISO mappings, each with 1 distinct WBC, low cost → not material.
    for k in range(5):
        rows.append({
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"COR-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 1_000.0,
        })
    # Outlier mapping with 8 distinct WBCs and material cost.
    for k in range(8):
        rows.append({
            "WBC_LEVEL_5": f"WX-{k}",
            "CODE_OF_RESOURCE": "OUT",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 50_000.0,  # 8 * 50k = 400k → material
        })
    df = _make_e3_df(rows)
    result = check_ept_e3(df)
    # Peer rows (first 5) pass; every outlier row fails.
    assert result.iloc[:5].all()
    assert (~result.iloc[5:]).all()


def test_ept_e3_passes_outlier_when_not_material():
    """The same over-aggregating mapping does NOT fail when the materiality
    filter is not satisfied (zero hours AND cost below 100k USD)."""
    from src.custom_dqr_engine import check_ept_e3
    rows = []
    for k in range(5):
        rows.append({
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"COR-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 1_000.0,
        })
    for k in range(8):
        rows.append({
            "WBC_LEVEL_5": f"WX-{k}",
            "CODE_OF_RESOURCE": "OUT",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,        # no hours
            "TOTAL_COST_USD": 1_000.0,  # 8 * 1k = 8k → below 100k threshold
        })
    df = _make_e3_df(rows)
    assert check_ept_e3(df).all()


def test_ept_e3_materiality_triggered_by_hours_only():
    """Hours > 0 alone is sufficient to make a mapping material, even when
    cost stays below the USD threshold."""
    from src.custom_dqr_engine import check_ept_e3
    rows = []
    for k in range(5):
        rows.append({
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"COR-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 1_000.0,
        })
    for k in range(8):
        rows.append({
            "WBC_LEVEL_5": f"WX-{k}",
            "CODE_OF_RESOURCE": "OUT",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.1,        # any positive hours → material
            "TOTAL_COST_USD": 0.0,
        })
    df = _make_e3_df(rows)
    result = check_ept_e3(df)
    assert (~result.iloc[5:]).all()


def test_ept_e3_materiality_threshold_is_inclusive_on_cost():
    """The cost branch of the materiality filter is ``>=`` 100k USD per
    spec, so an aggregated cost equal to the threshold counts as material."""
    from src.custom_dqr_engine import check_ept_e3
    rows = []
    for k in range(5):
        rows.append({
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"COR-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 1_000.0,
        })
    for k in range(8):
        rows.append({
            "WBC_LEVEL_5": f"WX-{k}",
            "CODE_OF_RESOURCE": "OUT",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            # 8 * 12_500 = 100_000 exactly
            "TOTAL_COST_USD": 12_500.0,
        })
    df = _make_e3_df(rows)
    result = check_ept_e3(df)
    assert (~result.iloc[5:]).all()


def test_ept_e3_rows_with_missing_iso_key_pass():
    """Rows lacking COR or SAB cannot be assessed against the threshold;
    they pass E3 (E1 already covers the missing-COR/SAB failure)."""
    from src.custom_dqr_engine import check_ept_e3
    rows = [
        {"WBC_LEVEL_5": "W1", "CODE_OF_RESOURCE": None,
         "STANDARD_ACTIVITY_BREAKDOWN": "S1",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 500_000.0},
        {"WBC_LEVEL_5": "W2", "CODE_OF_RESOURCE": "A",
         "STANDARD_ACTIVITY_BREAKDOWN": None,
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 500_000.0},
        {"WBC_LEVEL_5": "W3", "CODE_OF_RESOURCE": "  ",
         "STANDARD_ACTIVITY_BREAKDOWN": "S1",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 500_000.0},
        # Reference well-mapped row so the percentile has at least one
        # eligible group.
        {"WBC_LEVEL_5": "W4", "CODE_OF_RESOURCE": "B",
         "STANDARD_ACTIVITY_BREAKDOWN": "S1",
         "TOTAL_HOURS": 1.0, "TOTAL_COST_USD": 1_000.0},
    ]
    df = _make_e3_df(rows)
    assert check_ept_e3(df).tolist() == [True, True, True, True]


def test_ept_e3_blank_or_null_wbc_does_not_inflate_distinct_count():
    """``COUNT(DISTINCT WBC_LEVEL_5)`` ignores null/blank values, mirroring
    SQL semantics, so an outlier mapping that's only outlier because of
    blank WBCs does not fail."""
    from src.custom_dqr_engine import check_ept_e3
    rows = []
    for k in range(5):
        rows.append({
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"COR-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 500_000.0,
        })
    # Same single distinct WBC, but several rows with blank/null WBCs that
    # would have looked like cardinality if naively counted.
    for blank in (None, "", "  ", "\t"):
        rows.append({
            "WBC_LEVEL_5": blank,
            "CODE_OF_RESOURCE": "OUT",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 500_000.0,
        })
    rows.append({
        "WBC_LEVEL_5": "W1",
        "CODE_OF_RESOURCE": "OUT",
        "STANDARD_ACTIVITY_BREAKDOWN": "S1",
        "TOTAL_HOURS": 0.0,
        "TOTAL_COST_USD": 500_000.0,
    })
    df = _make_e3_df(rows)
    assert check_ept_e3(df).all()


def test_ept_e3_fails_for_all_rows_when_required_column_missing():
    """Schema-level missing column → rule fails for every row (does not
    silently pass)."""
    from src.custom_dqr_engine import check_ept_e3
    df = pd.DataFrame({
        "WBC_LEVEL_5": ["W1", "W2"],
        "CODE_OF_RESOURCE": ["A", "B"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["S1", "S1"],
        "TOTAL_HOURS": [1.0, 2.0],
        # TOTAL_COST_USD intentionally absent
    })
    assert check_ept_e3(df).tolist() == [False, False]


def test_ept_e3_empty_dataframe_returns_empty_pass_series():
    from src.custom_dqr_engine import check_ept_e3
    df = pd.DataFrame({c: [] for c in _e3_required_cols()})
    out = check_ept_e3(df)
    assert out.tolist() == []


def test_ept_e3_dispatches_through_evaluate_custom_rules():
    """End-to-end: evaluate_custom_rules routes an E3 assignment through
    check_ept_e3 and returns the per-row Boolean column."""
    from src.custom_dqr_engine import evaluate_custom_rules
    rows = []
    for k in range(5):
        rows.append({
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"COR-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 1.0,
            "TOTAL_COST_USD": 1_000.0,
        })
    df = _make_e3_df(rows)
    out, not_evaluated = evaluate_custom_rules(
        df, [CustomDQRAssignment(rule_id="E3", weight=100.0)], "EPT"
    )
    assert "E3" in out.columns
    assert out["E3"].tolist() == [True] * 5
    assert not_evaluated == {}


# -----------------------------------------------------------------------------
# E3: project-scoped percentile (params={"project_scoped": True})
# -----------------------------------------------------------------------------

def _e3_required_cols_with_planview():
    return _e3_required_cols() + ["PLANVIEW_ID"]


def _make_e3_df_with_planview(rows):
    cols = _e3_required_cols_with_planview()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def test_ept_e3_project_scope_isolates_per_project_p90():
    """With project scope on, each PLANVIEW_ID gets its own P90. A project
    whose mappings all share the same ratio passes; an outlier in another
    project still fails because that project's local P90 is exceeded."""
    from src.custom_dqr_engine import EPT_E3_PROJECT_SCOPED_PARAM, check_ept_e3

    rows = []
    # Project P-OK: 5 mappings each with 1 distinct WBC, all material.
    for k in range(5):
        rows.append({
            "PLANVIEW_ID": "P-OK",
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"OK-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    # Project P-OUT: 5 peer mappings (1 distinct WBC each) plus 1 outlier
    # mapping with 8 distinct WBCs. Local P90 ≈ 4.5; outlier (8) exceeds it.
    for k in range(5):
        rows.append({
            "PLANVIEW_ID": "P-OUT",
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"PEER-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    for k in range(8):
        rows.append({
            "PLANVIEW_ID": "P-OUT",
            "WBC_LEVEL_5": f"WX-{k}",
            "CODE_OF_RESOURCE": "OUT",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    df = _make_e3_df_with_planview(rows)
    result = check_ept_e3(df, params={EPT_E3_PROJECT_SCOPED_PARAM: True})
    # First 5 (P-OK) pass; 5 P-OUT peers pass; final 8 P-OUT outlier rows fail.
    assert result.iloc[:10].all()
    assert (~result.iloc[10:]).all()


def test_ept_e3_project_scope_does_not_flag_when_outlier_is_global_only():
    """Same mapping that fails in global scope can pass in project scope
    when, viewed from inside its own project, the ratio is the local norm.

    Construction: 20 low projects (each one mapping, ratio 1) plus one
    high project (one mapping with 5 distinct WBCs). Global sorted
    ratios = [1]*20 + [5] → P90 = 1 (the lone 5 sits past the 90th
    percentile and is flagged). Inside P-HI the local distribution is just
    [5], so its local P90 == 5 → no fail."""
    from src.custom_dqr_engine import EPT_E3_PROJECT_SCOPED_PARAM, check_ept_e3

    rows = []
    for k in range(20):
        rows.append({
            "PLANVIEW_ID": f"P-LOW-{k}",
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": "C",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    for w in range(5):
        rows.append({
            "PLANVIEW_ID": "P-HI",
            "WBC_LEVEL_5": f"W-HI-{w}",
            "CODE_OF_RESOURCE": "HI",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    df = _make_e3_df_with_planview(rows)

    # Sanity: in global scope the P-HI mapping FAILS (ratio 5 > global P90 1).
    global_result = check_ept_e3(df, params={EPT_E3_PROJECT_SCOPED_PARAM: False})
    assert global_result.iloc[:20].all()
    assert (~global_result.iloc[20:]).all()

    # In project scope, P-HI's local distribution is just [5]; its own P90
    # is 5; so 5 > 5 is False → P-HI rows now PASS.
    proj_result = check_ept_e3(df, params={EPT_E3_PROJECT_SCOPED_PARAM: True})
    assert proj_result.all()


def test_ept_e3_project_scope_passes_rows_with_null_planview_id():
    """When project scope is on, rows lacking PLANVIEW_ID can't be assigned
    to a project; they pass E3 (E7 already covers the missing-project gap)."""
    from src.custom_dqr_engine import EPT_E3_PROJECT_SCOPED_PARAM, check_ept_e3
    rows = [
        {"PLANVIEW_ID": None, "WBC_LEVEL_5": "W1",
         "CODE_OF_RESOURCE": "OUT", "STANDARD_ACTIVITY_BREAKDOWN": "S1",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 500_000.0},
        {"PLANVIEW_ID": "  ", "WBC_LEVEL_5": "W2",
         "CODE_OF_RESOURCE": "OUT", "STANDARD_ACTIVITY_BREAKDOWN": "S1",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 500_000.0},
        # Reference well-mapped row inside an actual project so the percentile
        # has at least one eligible group.
        {"PLANVIEW_ID": "P-OK", "WBC_LEVEL_5": "W3",
         "CODE_OF_RESOURCE": "B", "STANDARD_ACTIVITY_BREAKDOWN": "S1",
         "TOTAL_HOURS": 1.0, "TOTAL_COST_USD": 1_000.0},
    ]
    df = _make_e3_df_with_planview(rows)
    out = check_ept_e3(df, params={EPT_E3_PROJECT_SCOPED_PARAM: True})
    assert out.tolist() == [True, True, True]


def test_ept_e3_project_scope_fails_all_rows_when_planview_id_missing():
    """Schema-level: project scope is on but the dataset lacks PLANVIEW_ID
    altogether → rule fails for every row (rather than silently passing)."""
    from src.custom_dqr_engine import EPT_E3_PROJECT_SCOPED_PARAM, check_ept_e3
    df = _make_e3_df([
        {"WBC_LEVEL_5": "W1", "CODE_OF_RESOURCE": "C",
         "STANDARD_ACTIVITY_BREAKDOWN": "S1",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 0.0}
    ])
    out = check_ept_e3(df, params={EPT_E3_PROJECT_SCOPED_PARAM: True})
    assert out.tolist() == [False]


def test_ept_e3_default_params_match_global_scope():
    """Calling check_ept_e3 with params=None or {} must match the global-
    scope behaviour (project_scoped defaults to False)."""
    from src.custom_dqr_engine import check_ept_e3
    rows = []
    for k in range(5):
        rows.append({
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"COR-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 1.0,
            "TOTAL_COST_USD": 1_000.0,
        })
    df = _make_e3_df(rows)
    assert check_ept_e3(df).equals(check_ept_e3(df, params={}))
    assert check_ept_e3(df).equals(
        check_ept_e3(df, params={"project_scoped": False})
    )


def test_evaluate_custom_rules_plumbs_assignment_params_to_check():
    """Dispatcher must pass ``CustomDQRAssignment.params`` through to a
    check function that accepts ``params``. Proven by switching E3 between
    global and project scope using the same DataFrame and getting different
    verdicts only via the assignment."""
    from src.custom_dqr_engine import (
        EPT_E3_PROJECT_SCOPED_PARAM,
        evaluate_custom_rules,
    )

    rows = []
    for k in range(5):
        rows.append({
            "PLANVIEW_ID": "P-A",
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"PEER-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    for k in range(8):
        rows.append({
            "PLANVIEW_ID": "P-A",
            "WBC_LEVEL_5": f"WX-{k}",
            "CODE_OF_RESOURCE": "OUT",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    # Add a second project so global vs project P90 can diverge.
    for k in range(5):
        rows.append({
            "PLANVIEW_ID": "P-B",
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"OTHER-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    df = _make_e3_df_with_planview(rows)

    # Global scope (default) - outlier rows fail.
    global_out, _ = evaluate_custom_rules(
        df,
        [CustomDQRAssignment(rule_id="E3", weight=100.0, params={})],
        "EPT",
    )
    assert (~global_out["E3"].iloc[5:13]).all()

    # Project scope toggled via the assignment params.
    proj_out, _ = evaluate_custom_rules(
        df,
        [
            CustomDQRAssignment(
                rule_id="E3",
                weight=100.0,
                params={EPT_E3_PROJECT_SCOPED_PARAM: True},
            )
        ],
        "EPT",
    )
    # P-A's local P90 ≈ 4.5; outlier 8 still > 4.5 → still FAIL inside P-A.
    assert (~proj_out["E3"].iloc[5:13]).all()
    # But P-B's local distribution is all 1s, so its rows still PASS.
    assert proj_out["E3"].iloc[13:].all()


# -----------------------------------------------------------------------------
# E3: uniform 1:1 mapping detection (params={"detect_uniform_mapping": True})
# -----------------------------------------------------------------------------

def test_ept_e3_uniform_detection_off_by_default_passes_uniform_mappings():
    """Without the toggle, a dataset where every ISO bucket holds exactly
    one distinct WBC still PASSES, the regular P90 path treats uniform
    distributions as the baseline (P90 == ratio == 1)."""
    from src.custom_dqr_engine import check_ept_e3
    rows = []
    for k in range(10):
        rows.append({
            "WBC_LEVEL_5": f"W-{k}",
            "CODE_OF_RESOURCE": f"COR-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 1.0,
            "TOTAL_COST_USD": 1_000.0,
        })
    df = _make_e3_df(rows)
    assert check_ept_e3(df).all()


def test_ept_e3_uniform_detection_flags_material_1_to_1_mappings():
    """Toggle on → every material bucket with ratio == 1 FAILS, even
    when no bucket exceeds the P90."""
    from src.custom_dqr_engine import (
        EPT_E3_DETECT_UNIFORM_MAPPING_PARAM,
        check_ept_e3,
    )
    rows = []
    for k in range(10):
        rows.append({
            "WBC_LEVEL_5": f"W-{k}",
            "CODE_OF_RESOURCE": f"COR-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 1.0,                  # material via hours
            "TOTAL_COST_USD": 1_000.0,
        })
    df = _make_e3_df(rows)
    result = check_ept_e3(
        df, params={EPT_E3_DETECT_UNIFORM_MAPPING_PARAM: True}
    )
    # Every material 1:1 row is flagged.
    assert (~result).all()


def test_ept_e3_uniform_detection_respects_materiality():
    """Even with the toggle on, immaterial 1:1 buckets must still PASS -
    materiality gates both the percentile and uniform branches."""
    from src.custom_dqr_engine import (
        EPT_E3_DETECT_UNIFORM_MAPPING_PARAM,
        check_ept_e3,
    )
    rows = []
    for k in range(10):
        rows.append({
            "WBC_LEVEL_5": f"W-{k}",
            "CODE_OF_RESOURCE": f"COR-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,                  # not material
            "TOTAL_COST_USD": 1_000.0,           # below 100k threshold
        })
    df = _make_e3_df(rows)
    assert check_ept_e3(
        df, params={EPT_E3_DETECT_UNIFORM_MAPPING_PARAM: True}
    ).all()


def test_ept_e3_uniform_detection_layers_on_top_of_percentile_fail():
    """Toggle on combines with the percentile fail via OR: an over-
    aggregating bucket still fails through the P90 branch, and the 1:1
    peer buckets fail through the uniform branch - both signals coexist."""
    from src.custom_dqr_engine import (
        EPT_E3_DETECT_UNIFORM_MAPPING_PARAM,
        check_ept_e3,
    )
    rows = []
    # 5 peer mappings, each 1:1, material.
    for k in range(5):
        rows.append({
            "WBC_LEVEL_5": f"W-{k}",
            "CODE_OF_RESOURCE": f"PEER-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 1.0,
            "TOTAL_COST_USD": 1_000.0,
        })
    # Outlier mapping: 8 distinct WBCs, material - fails the percentile branch.
    for k in range(8):
        rows.append({
            "WBC_LEVEL_5": f"WX-{k}",
            "CODE_OF_RESOURCE": "OUT",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 50_000.0,          # 8 * 50k = 400k → material
        })
    df = _make_e3_df(rows)
    result = check_ept_e3(
        df, params={EPT_E3_DETECT_UNIFORM_MAPPING_PARAM: True}
    )
    # Every row fails: peers via uniform branch, outliers via percentile branch.
    assert (~result).all()


def test_check_supports_params_distinguishes_signatures():
    """Helper used by the dispatcher to decide whether to pass params."""
    from src.custom_dqr_engine import (
        _check_supports_params,
        check_ept_e1,
        check_ept_e3,
    )
    assert _check_supports_params(check_ept_e3) is True
    assert _check_supports_params(check_ept_e1) is False


# =============================================================================
# E2: Location + Estimate Date Present (Completeness via Planview join)
# =============================================================================

def test_ept_has_custom_rule_e2_available():
    """EPT catalog exposes E2 with the documented Planview reference metadata."""
    rules = get_available_custom_dqr_rules("EPT")
    by_id = {r.id: r for r in rules}
    assert "E2" in by_id
    rule = by_id["E2"]
    assert rule.type == "Completeness"
    assert rule.required_columns == {
        "Estimate Basis Date": "CENTROID_DATE",
        "Project Key": "PLANVIEW_ID",
    }
    assert rule.reference is not None
    assert rule.reference["reference_dataset"] == "VWS_GP_STANDARD_SHARE"
    assert rule.reference["source_column"] == "PLANVIEW_ID"
    assert rule.reference["reference_column"] == "PROJECT_ID"
    assert rule.reference["lookup_column"] == "COUNTRY"


@pytest.fixture
def _e2_reference_with_countries(monkeypatch):
    """Pin the Planview reference to a known PROJECT_ID → COUNTRY mapping so
    E2 row-level assertions don't depend on the mock's RNG."""
    import src.reference_data as ref_mod
    ref_df = pd.DataFrame({
        "PROJECT_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "COUNTRY": ["BR", "US", "UK"],
    })
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    return ref_df


def test_ept_e2_passes_when_centroid_date_and_country_present(
    _e2_reference_with_countries,
):
    """E2 passes when CENTROID_DATE is filled AND PLANVIEW_ID joins to a
    project whose COUNTRY is populated."""
    from src.custom_dqr_engine import check_ept_e2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002"],
        "CENTROID_DATE": pd.to_datetime(["2024-01-01", "2024-06-15"]),
    })
    assert check_ept_e2(df).tolist() == [True, True]


def test_ept_e2_fails_when_centroid_date_null(_e2_reference_with_countries):
    from src.custom_dqr_engine import check_ept_e2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "CENTROID_DATE": [pd.Timestamp("2024-01-01"), None, pd.Timestamp("2024-03-01")],
    })
    assert check_ept_e2(df).tolist() == [True, False, True]


def test_ept_e2_fails_when_centroid_date_blank_string(_e2_reference_with_countries):
    """Treats blank/whitespace strings the same way as null - E2 piggy-backs
    on _is_filled, mirroring the shelf Completeness semantics."""
    from src.custom_dqr_engine import check_ept_e2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "CENTROID_DATE": ["2024-01-01", "", "  "],
    })
    assert check_ept_e2(df).tolist() == [True, False, False]


def test_ept_e2_fails_when_planview_id_does_not_match_reference(monkeypatch):
    """An unmatched PLANVIEW_ID is treated as missing COUNTRY (per spec)."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_ept_e2
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({
            "PROJECT_ID": ["PV-00001", "PV-00002"],
            "COUNTRY": ["BR", "US"],
        }),
    )
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-ORPHAN", "PV-00002"],
        "CENTROID_DATE": pd.to_datetime(["2024-01-01"] * 3),
    })
    assert check_ept_e2(df).tolist() == [True, False, True]


def test_ept_e2_fails_when_country_null_after_join(monkeypatch):
    """A matched PLANVIEW_ID whose project has a null COUNTRY fails E2."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_ept_e2
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({
            "PROJECT_ID": ["PV-00001", "PV-00002", "PV-00003"],
            "COUNTRY": ["BR", None, "  "],
        }),
    )
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "CENTROID_DATE": pd.to_datetime(["2024-01-01"] * 3),
    })
    assert check_ept_e2(df).tolist() == [True, False, False]


def test_ept_e2_fails_when_planview_id_is_null(_e2_reference_with_countries):
    """A null PLANVIEW_ID can't be looked up - COUNTRY is treated as missing."""
    from src.custom_dqr_engine import check_ept_e2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", None, "PV-00002"],
        "CENTROID_DATE": pd.to_datetime(["2024-01-01"] * 3),
    })
    assert check_ept_e2(df).tolist() == [True, False, True]


def test_ept_e2_fails_for_all_rows_when_centroid_date_column_missing():
    from src.custom_dqr_engine import check_ept_e2
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "PV-00002"]})
    assert check_ept_e2(df).tolist() == [False, False]


def test_ept_e2_fails_for_all_rows_when_planview_id_column_missing():
    from src.custom_dqr_engine import check_ept_e2
    df = pd.DataFrame({"CENTROID_DATE": pd.to_datetime(["2024-01-01", "2024-02-01"])})
    assert check_ept_e2(df).tolist() == [False, False]


def test_ept_e2_raises_not_evaluated_when_reference_unavailable(monkeypatch):
    """If the Planview reference loader returns None, E2 must raise
    CustomRuleNotEvaluated rather than silently passing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import CustomRuleNotEvaluated, check_ept_e2
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001"],
        "CENTROID_DATE": pd.to_datetime(["2024-01-01"]),
    })
    try:
        check_ept_e2(df)
        raised = False
    except CustomRuleNotEvaluated:
        raised = True
    assert raised


def test_ept_e2_fails_for_all_rows_when_reference_missing_country_column(monkeypatch):
    """If the reference dataset lacks COUNTRY, the join cannot validate
    location, every row fails (rule does not silently pass)."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_ept_e2
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({"PROJECT_ID": ["PV-00001"]}),
    )
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001"],
        "CENTROID_DATE": pd.to_datetime(["2024-01-01"]),
    })
    assert check_ept_e2(df).tolist() == [False]


def test_evaluate_custom_rules_dispatches_to_e2(_e2_reference_with_countries):
    """End-to-end: dispatcher routes an E2 assignment through check_ept_e2
    against a known reference dataset."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002"],
        "CENTROID_DATE": pd.to_datetime(["2024-01-01", "2024-02-01"]),
    })
    assignments = [CustomDQRAssignment(rule_id="E2", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "EPT")
    assert "E2" in out.columns
    assert out["E2"].tolist() == [True, True]
    assert not_evaluated == {}


def test_required_reference_datasets_unchanged_when_e2_added():
    """E2 reuses the same VWS_GP_STANDARD_SHARE reference as E7, so the
    Step 2 prefetch list stays a single entry, no extra round-trip."""
    from src.reference_data import required_reference_datasets_for_systems
    assert required_reference_datasets_for_systems(["EPT"]) == [
        "VWS_GP_STANDARD_SHARE"
    ]


# =============================================================================
# A1: ISO Code of Account Present (COR + SAB) for ADR
# =============================================================================

@pytest.fixture
def _a1_coa_master_with_known_groups(monkeypatch):
    """Pin the COA master to a known ICARUS_COA → ISO_COR / SAB mapping
    so A1 row-level assertions don't depend on the mock's RNG. Includes
    one row each for: valid mapping, invalid ISO_COR, invalid SAB, and
    duplicate-COA-with-best-pick semantics."""
    import src.reference_data as ref_mod
    ref_df = pd.DataFrame({
        "ICARUS_COA": ["313", "314", "315", "316", "317", "317"],
        "ISO_COR": [
            "C2.12.1",      # 313 - valid
            "C2.13",        # 314 - valid
            "ERROR: #N/A",  # 315 - invalid ISO_COR
            "C3.1",         # 316 - valid (paired with invalid SAB)
            "ERROR: stale", # 317 - duplicate row 1 (invalid)
            "C3.2",         # 317 - duplicate row 2 (valid; should win)
        ],
        "SAB": [
            "S3.2.2",       # 313 - valid
            "S3.4",         # 314 - valid
            "S2.1",         # 315 - valid (paired with invalid ISO_COR)
            "ERROR: #N/A",  # 316 - invalid SAB
            "S2.5",         # 317 - duplicate row 1
            "ERROR: stale", # 317 - duplicate row 2
        ],
    })
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    return ref_df


def test_adr_has_custom_rule_a1_available():
    """ADR catalog exposes A1 as a *blocking* Completeness rule with a
    reference dataset linkage to ACCE_COA_MASTER."""
    rules = get_available_custom_dqr_rules("ADR")
    by_id = {r.id: r for r in rules}
    assert "A1" in by_id
    rule = by_id["A1"]
    assert rule.type == "Completeness"
    assert rule.blocking is True
    assert rule.required_columns == {
        "Project Key": "PLANVIEW_ID",
        "Complete WBC": "COMPLETE_WBC",
    }
    assert rule.reference is not None
    assert rule.reference["reference_dataset"] == "ACCE_COA_MASTER"
    assert rule.reference["source_column"] == "COMPLETE_WBC"
    assert rule.reference["reference_column"] == "ICARUS_COA"


def test_adr_a1_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ADR_A1_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ADR") if r.id == "A1"
    )
    assert rule.required_columns == ADR_A1_REQUIRED_COLUMNS


# ----- check_adr_a1 - happy + each FAIL path ---------------------------------

def test_adr_a1_passes_when_wbc_resolves_to_valid_iso_cor_and_sab(
    _a1_coa_master_with_known_groups,
):
    from src.custom_dqr_engine import check_adr_a1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2"],
        "COMPLETE_WBC": ["313.1.10.10", "314.0.5.18"],
    })
    assert check_adr_a1(df).tolist() == [True, True]


def test_adr_a1_fails_when_complete_wbc_null_or_blank(
    _a1_coa_master_with_known_groups,
):
    from src.custom_dqr_engine import check_adr_a1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2", "PV-3"],
        "COMPLETE_WBC": [None, "", "   "],
    })
    assert check_adr_a1(df).tolist() == [False, False, False]


def test_adr_a1_fails_when_iso_cor_is_invalid_marker(
    _a1_coa_master_with_known_groups,
):
    """COA group 315 has ``ISO_COR = 'ERROR: #N/A'`` in the master -
    should fail A1 even though SAB is valid."""
    from src.custom_dqr_engine import check_adr_a1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COMPLETE_WBC": ["315.1.10.10"],
    })
    assert check_adr_a1(df).tolist() == [False]


def test_adr_a1_fails_when_sab_is_invalid_marker(
    _a1_coa_master_with_known_groups,
):
    """COA group 316 has ``SAB = 'ERROR: #N/A'`` - should fail A1 even
    though ISO_COR is valid."""
    from src.custom_dqr_engine import check_adr_a1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COMPLETE_WBC": ["316.0.5.18"],
    })
    assert check_adr_a1(df).tolist() == [False]


def test_adr_a1_fails_when_coa_group_is_orphan(
    _a1_coa_master_with_known_groups,
):
    """A WBC whose COA group does not appear in the master at all
    resolves to NaN for both ISO_COR and SAB → FAIL."""
    from src.custom_dqr_engine import check_adr_a1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COMPLETE_WBC": ["999.0.0.0"],
    })
    assert check_adr_a1(df).tolist() == [False]


def test_adr_a1_picks_best_available_mapping_for_duplicate_coa_group(
    _a1_coa_master_with_known_groups,
):
    """COA group 317 has two rows in the master, one fully invalid,
    one with valid ISO_COR + valid SAB. Per spec §9 the rule prefers
    the valid pair, so a 317 WBC must PASS."""
    from src.custom_dqr_engine import check_adr_a1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COMPLETE_WBC": ["317.2.2.2"],
    })
    assert check_adr_a1(df).tolist() == [True]


@pytest.mark.parametrize("invalid_marker", ["ERROR", "ERROR: #N/A", "#N/A", "n/a", "  "])
def test_adr_a1_value_validator_rejects_known_invalid_markers(invalid_marker):
    """Direct test of the validity helper, every documented invalid
    spelling must read as not-valid."""
    from src.custom_dqr_engine import _a1_value_valid
    s = pd.Series([invalid_marker, "C2.12.1"])
    assert _a1_value_valid(s).tolist() == [False, True]


def test_adr_a1_value_validator_treats_null_as_invalid():
    from src.custom_dqr_engine import _a1_value_valid
    assert _a1_value_valid(pd.Series([None, ""])).tolist() == [False, False]


# ----- check_adr_a1 - schema-level / structural failures ---------------------

def test_adr_a1_fails_for_all_rows_when_complete_wbc_column_missing(
    _a1_coa_master_with_known_groups,
):
    from src.custom_dqr_engine import check_adr_a1
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-1", "PV-2"]})
    assert check_adr_a1(df).tolist() == [False, False]


def test_adr_a1_fails_for_all_rows_when_planview_id_column_missing(
    _a1_coa_master_with_known_groups,
):
    from src.custom_dqr_engine import check_adr_a1
    df = pd.DataFrame({"COMPLETE_WBC": ["313.1.10.10", "314.0.5.18"]})
    assert check_adr_a1(df).tolist() == [False, False]


def test_adr_a1_raises_not_evaluated_when_reference_unavailable(monkeypatch):
    """If the COA master loader returns None, A1 must raise
    CustomRuleNotEvaluated rather than silently passing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import CustomRuleNotEvaluated, check_adr_a1
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COMPLETE_WBC": ["313.1.10.10"],
    })
    raised = False
    try:
        check_adr_a1(df)
    except CustomRuleNotEvaluated:
        raised = True
    assert raised


def test_adr_a1_fails_for_all_rows_when_reference_missing_required_columns(
    monkeypatch,
):
    """If the reference dataset lacks ICARUS_COA / ISO_COR / SAB the
    join cannot validate, every row fails."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_adr_a1
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({"ICARUS_COA": ["313"]}),  # no ISO_COR/SAB
    )
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COMPLETE_WBC": ["313.1.10.10"],
    })
    assert check_adr_a1(df).tolist() == [False]


def test_evaluate_custom_rules_dispatches_to_a1(
    _a1_coa_master_with_known_groups,
):
    """End-to-end: dispatcher routes an A1 assignment through check_adr_a1."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2", "PV-3"],
        "COMPLETE_WBC": ["313.1.10.10", "315.0.5.18", None],
    })
    assignments = [CustomDQRAssignment(rule_id="A1", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ADR")
    assert "A1" in out.columns
    # 313 → valid PASS; 315 → invalid ISO_COR; null WBC → FAIL.
    assert out["A1"].tolist() == [True, False, False]
    assert not_evaluated == {}


def test_required_reference_datasets_for_adr_now_includes_coa_master():
    """A1 introduces a second reference dataset for ADR
    (``ACCE_COA_MASTER`` alongside ``VWS_GP_STANDARD_SHARE``). Step 2
    must prefetch both."""
    from src.reference_data import required_reference_datasets_for_systems
    refs = required_reference_datasets_for_systems(["ADR"])
    assert set(refs) == {"VWS_GP_STANDARD_SHARE", "ACCE_COA_MASTER"}


def test_acce_coa_master_loader_resolves_in_mock_mode():
    """The mock-mode loader returns a populated DataFrame with the
    three columns A1 needs. Sanity check so future regressions don't
    silently break A1 in demo mode."""
    from src.reference_data import _load_acce_coa_master
    df = _load_acce_coa_master()
    assert df is not None
    assert {"ICARUS_COA", "ISO_COR", "SAB"}.issubset(df.columns)
    assert len(df) > 0


# =============================================================================
# AC1: ISO Code of Account Present (COR + SAB) for ACCE
# =============================================================================

# Reuses the ``_a1_coa_master_with_known_groups`` fixture above: same COA
# master schema, same best-available-mapping semantics. AC1 differs from
# A1 only in the source column (``COA``, used directly), so the same
# pinned reference fixture covers both rules.


def test_acce_has_custom_rule_ac1_available():
    """ACCE catalog exposes AC1 as a *blocking* Completeness rule with a
    reference dataset linkage to ACCE_COA_MASTER on the direct ``COA``
    column (no WBC split, unlike ADR's A1)."""
    rules = get_available_custom_dqr_rules("ACCE")
    by_id = {r.id: r for r in rules}
    assert "AC1" in by_id
    rule = by_id["AC1"]
    assert rule.type == "Completeness"
    assert rule.blocking is True
    assert rule.required_columns == {
        "Project Key": "PLANVIEW_ID",
        "Code of Account": "COA",
    }
    assert rule.reference is not None
    assert rule.reference["reference_dataset"] == "ACCE_COA_MASTER"
    assert rule.reference["source_column"] == "COA"
    assert rule.reference["reference_column"] == "ICARUS_COA"


def test_acce_ac1_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ACCE_AC1_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ACCE") if r.id == "AC1"
    )
    assert rule.required_columns == ACCE_AC1_REQUIRED_COLUMNS


# ----- check_acce_ac1 - happy + each FAIL path -------------------------------

def test_acce_ac1_passes_when_coa_resolves_to_valid_iso_cor_and_sab(
    _a1_coa_master_with_known_groups,
):
    from src.custom_dqr_engine import check_acce_ac1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2"],
        "COA": ["313", "314"],
    })
    assert check_acce_ac1(df).tolist() == [True, True]


def test_acce_ac1_fails_when_coa_null_or_blank(
    _a1_coa_master_with_known_groups,
):
    from src.custom_dqr_engine import check_acce_ac1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2", "PV-3"],
        "COA": [None, "", "   "],
    })
    assert check_acce_ac1(df).tolist() == [False, False, False]


def test_acce_ac1_fails_when_iso_cor_is_invalid_marker(
    _a1_coa_master_with_known_groups,
):
    """COA 315 has ``ISO_COR = 'ERROR: #N/A'`` in the master - should
    fail AC1 even though SAB is valid."""
    from src.custom_dqr_engine import check_acce_ac1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COA": ["315"],
    })
    assert check_acce_ac1(df).tolist() == [False]


def test_acce_ac1_fails_when_sab_is_invalid_marker(
    _a1_coa_master_with_known_groups,
):
    """COA 316 has ``SAB = 'ERROR: #N/A'`` - should fail AC1 even
    though ISO_COR is valid."""
    from src.custom_dqr_engine import check_acce_ac1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COA": ["316"],
    })
    assert check_acce_ac1(df).tolist() == [False]


def test_acce_ac1_fails_when_coa_is_orphan(
    _a1_coa_master_with_known_groups,
):
    """A COA whose value does not appear in the master at all resolves
    to NaN for both ISO_COR and SAB → FAIL."""
    from src.custom_dqr_engine import check_acce_ac1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COA": ["999"],
    })
    assert check_acce_ac1(df).tolist() == [False]


def test_acce_ac1_picks_best_available_mapping_for_duplicate_coa(
    _a1_coa_master_with_known_groups,
):
    """COA 317 has two rows in the master, one fully invalid, one with
    valid ISO_COR + valid SAB. The rule prefers the valid pair, so a
    317 row must PASS, same FIRST_VALUE-by-invalid-flag semantics as A1."""
    from src.custom_dqr_engine import check_acce_ac1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COA": ["317"],
    })
    assert check_acce_ac1(df).tolist() == [True]


def test_acce_ac1_accepts_numeric_coa_column_dtype(
    _a1_coa_master_with_known_groups,
):
    """ACCE's ``COA`` may arrive as an int64 column when Snowflake casts
    the numeric code. Stringify-then-strip on both sides of the lookup
    must keep the join working - otherwise mock vs prod dtypes would
    silently produce all-NaN lookups."""
    from src.custom_dqr_engine import check_acce_ac1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2"],
        "COA": [313, 314],  # numeric, not string
    })
    assert check_acce_ac1(df).tolist() == [True, True]


def test_acce_ac1_truncates_four_char_coa_to_three_char_prefix(
    _a1_coa_master_with_known_groups,
):
    """Production ACCE COA codes are 4-character (e.g. ``3131``) but
    the master ``ICARUS_COA`` is the 3-character group prefix
    (``313``). The rule must take the first three characters of the
    COA before joining - analogous to ADR's
    ``SPLIT_PART(COMPLETE_WBC, '.', 1)`` derivation.

    The fixture pins ``ICARUS_COA = "313"`` and ``"314"`` with valid
    mappings, so every 4-character COA whose 3-character prefix is
    ``313`` or ``314`` must PASS - character-for-character equality
    with the master key is NOT required.
    """
    from src.custom_dqr_engine import check_acce_ac1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2", "PV-3", "PV-4"],
        "COA": ["3131", "3130", "3140", "3149"],
    })
    assert check_acce_ac1(df).tolist() == [True, True, True, True]


def test_acce_ac1_truncated_prefix_picks_up_invalid_marker(
    _a1_coa_master_with_known_groups,
):
    """A 4-char COA whose 3-char prefix is ``315`` resolves through
    the master row pinned with ``ISO_COR = 'ERROR: #N/A'`` - should
    still FAIL even though the source value differs from the master
    key character-for-character. Locks in that the truncation does
    not bypass the invalid-marker validity check."""
    from src.custom_dqr_engine import check_acce_ac1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COA": ["3155"],
    })
    assert check_acce_ac1(df).tolist() == [False]


def test_acce_ac1_truncated_prefix_orphan_still_fails(
    _a1_coa_master_with_known_groups,
):
    """A 4-char COA whose 3-char prefix has no master row at all
    (e.g. ``999``) resolves to NaN for ISO_COR/SAB → FAIL. Same as
    the legacy orphan-COA path, just with a 4-char source value."""
    from src.custom_dqr_engine import check_acce_ac1
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COA": ["9999"],
    })
    assert check_acce_ac1(df).tolist() == [False]


# ----- check_acce_ac1 - schema-level / structural failures -------------------

def test_acce_ac1_fails_for_all_rows_when_coa_column_missing(
    _a1_coa_master_with_known_groups,
):
    from src.custom_dqr_engine import check_acce_ac1
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-1", "PV-2"]})
    assert check_acce_ac1(df).tolist() == [False, False]


def test_acce_ac1_fails_for_all_rows_when_planview_id_column_missing(
    _a1_coa_master_with_known_groups,
):
    from src.custom_dqr_engine import check_acce_ac1
    df = pd.DataFrame({"COA": ["313", "314"]})
    assert check_acce_ac1(df).tolist() == [False, False]


def test_acce_ac1_raises_not_evaluated_when_reference_unavailable(monkeypatch):
    """If the COA master loader returns None, AC1 must raise
    CustomRuleNotEvaluated rather than silently passing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import CustomRuleNotEvaluated, check_acce_ac1
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COA": ["313"],
    })
    raised = False
    try:
        check_acce_ac1(df)
    except CustomRuleNotEvaluated:
        raised = True
    assert raised


def test_acce_ac1_fails_for_all_rows_when_reference_missing_required_columns(
    monkeypatch,
):
    """If the reference dataset lacks ICARUS_COA / ISO_COR / SAB the
    join cannot validate, every row fails."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_acce_ac1
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({"ICARUS_COA": ["313"]}),  # no ISO_COR/SAB
    )
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COA": ["313"],
    })
    assert check_acce_ac1(df).tolist() == [False]


def test_evaluate_custom_rules_dispatches_to_ac1(
    _a1_coa_master_with_known_groups,
):
    """End-to-end: dispatcher routes an AC1 assignment through check_acce_ac1."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2", "PV-3"],
        "COA": ["313", "315", None],
    })
    assignments = [CustomDQRAssignment(rule_id="AC1", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ACCE")
    assert "AC1" in out.columns
    # 313 → valid PASS; 315 → invalid ISO_COR; null COA → FAIL.
    assert out["AC1"].tolist() == [True, False, False]
    assert not_evaluated == {}


def test_required_reference_datasets_for_acce_includes_coa_master():
    """AC1 introduces ``ACCE_COA_MASTER`` as a reference dataset for
    ACCE. Step 2 must prefetch it so the rule can evaluate."""
    from src.reference_data import required_reference_datasets_for_systems
    refs = required_reference_datasets_for_systems(["ACCE"])
    assert "ACCE_COA_MASTER" in refs


# =============================================================================
# AC2: Location + Estimate Date Present (ACCE; mirrors ADR A2 with JOB_NO)
# =============================================================================

# Reuses the ``_a2_reference_with_countries`` fixture defined below in
# the ADR A2 block. AC2 differs from A2 only in the date source column
# (``JOB_NO`` vs ``COST_UPDATE``), so the same pinned reference
# dataset covers both rules.


def test_acce_has_custom_rule_ac2_available():
    """ACCE catalog exposes AC2 - non-blocking Completeness & Validity rule
    that joins ``PLANVIEW_ID`` to ``VWS_GP_STANDARD_SHARE.PROJECT_ID`` and
    requires ``JOB_NO`` filled and well-formed (ACCE's estimate-basis-date
    proxy)."""
    rules = get_available_custom_dqr_rules("ACCE")
    by_id = {r.id: r for r in rules}
    assert "AC2" in by_id
    rule = by_id["AC2"]
    assert rule.type == "Completeness & Validity"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Estimate Job Number": "JOB_NO",
        "Project Key": "PLANVIEW_ID",
    }
    assert rule.reference is not None
    assert rule.reference["reference_dataset"] == "VWS_GP_STANDARD_SHARE"
    assert rule.reference["source_column"] == "PLANVIEW_ID"
    assert rule.reference["reference_column"] == "PROJECT_ID"
    assert rule.reference["lookup_column"] == "COUNTRY"


def test_acce_ac2_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ACCE_AC2_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ACCE") if r.id == "AC2"
    )
    assert rule.required_columns == ACCE_AC2_REQUIRED_COLUMNS


@pytest.fixture
def _ac2_reference_with_countries(monkeypatch):
    """Pin the Planview reference to a known PROJECT_ID → COUNTRY mapping
    so AC2 row-level assertions don't depend on the mock's RNG."""
    import src.reference_data as ref_mod
    ref_df = pd.DataFrame({
        "PROJECT_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "COUNTRY": ["BR", "US", "UK"],
    })
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    return ref_df


def test_acce_ac2_passes_when_job_no_and_country_present(
    _ac2_reference_with_countries,
):
    """AC2 passes when JOB_NO is filled AND PLANVIEW_ID joins to a
    project whose COUNTRY is populated."""
    from src.custom_dqr_engine import check_acce_ac2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002"],
        "JOB_NO": ["2Q23 RP1", "2Q24"],
    })
    assert check_acce_ac2(df).tolist() == [True, True]


def test_acce_ac2_fails_when_job_no_null(_ac2_reference_with_countries):
    from src.custom_dqr_engine import check_acce_ac2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "JOB_NO": ["2Q23 RP1", None, "2Q25"],
    })
    assert check_acce_ac2(df).tolist() == [True, False, True]


def test_acce_ac2_fails_when_job_no_blank_string(_ac2_reference_with_countries):
    """Blank/whitespace strings count as missing - AC2 piggy-backs on
    ``_is_filled``, same as A2. (The empty-string value seen in the live
    JOB_NO column lands here.)"""
    from src.custom_dqr_engine import check_acce_ac2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "JOB_NO": ["4Q23", "", "  "],
    })
    assert check_acce_ac2(df).tolist() == [True, False, False]


def test_acce_ac2_fails_when_job_no_filled_but_invalid_format(
    _ac2_reference_with_countries,
):
    """Validity: a populated JOB_NO that does not start with the fiscal
    quarter-year token fails AC2 even though it satisfies Completeness."""
    from src.custom_dqr_engine import check_acce_ac2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003", "PV-00001"],
        # valid quarter-year / no quarter token / bad quarter / truncated
        "JOB_NO": ["2Q23 RP1", "2023", "5Q23", "2Q"],
    })
    assert check_acce_ac2(df).tolist() == [True, False, False, False]


def test_acce_ac2_validity_accepts_new_quarters_and_revision_suffixes(
    _ac2_reference_with_countries,
):
    """The check is structural, not an enum: a quarter/year never seen
    before still passes, as does any whitespace-separated revision suffix,
    and the 'Q' is matched case-insensitively."""
    from src.custom_dqr_engine import check_acce_ac2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003"],
        # future period / lowercase q / multi-token revision suffix
        "JOB_NO": ["1Q30", "3q27", "4Q26 RP2 DRAFT"],
    })
    assert check_acce_ac2(df).tolist() == [True, True, True]


def test_acce_ac2_fails_when_planview_id_does_not_match_reference(monkeypatch):
    """An unmatched PLANVIEW_ID is treated as missing COUNTRY (per spec)."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_acce_ac2
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({
            "PROJECT_ID": ["PV-00001", "PV-00002"],
            "COUNTRY": ["BR", "US"],
        }),
    )
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-ORPHAN", "PV-00002"],
        "JOB_NO": ["2Q23 RP1", "2Q24", "2Q25"],
    })
    assert check_acce_ac2(df).tolist() == [True, False, True]


def test_acce_ac2_fails_when_country_null_after_join(monkeypatch):
    """A matched PLANVIEW_ID whose project has a null COUNTRY fails AC2."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_acce_ac2
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({
            "PROJECT_ID": ["PV-00001", "PV-00002", "PV-00003"],
            "COUNTRY": ["BR", None, "  "],
        }),
    )
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "JOB_NO": ["2Q23 RP1", "2Q24", "2Q25"],
    })
    assert check_acce_ac2(df).tolist() == [True, False, False]


def test_acce_ac2_fails_when_planview_id_is_null(_ac2_reference_with_countries):
    """A null PLANVIEW_ID can't be looked up - COUNTRY is treated as missing."""
    from src.custom_dqr_engine import check_acce_ac2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", None, "PV-00002"],
        "JOB_NO": ["2Q23 RP1", "2Q24", "2Q25"],
    })
    assert check_acce_ac2(df).tolist() == [True, False, True]


def test_acce_ac2_fails_for_all_rows_when_job_no_column_missing():
    from src.custom_dqr_engine import check_acce_ac2
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "PV-00002"]})
    assert check_acce_ac2(df).tolist() == [False, False]


def test_acce_ac2_fails_for_all_rows_when_planview_id_column_missing():
    from src.custom_dqr_engine import check_acce_ac2
    df = pd.DataFrame({"JOB_NO": ["2Q23 RP1", "2Q24"]})
    assert check_acce_ac2(df).tolist() == [False, False]


def test_acce_ac2_raises_not_evaluated_when_reference_unavailable(monkeypatch):
    """If the Planview reference loader returns None, AC2 must raise
    CustomRuleNotEvaluated rather than silently passing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import CustomRuleNotEvaluated, check_acce_ac2
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001"],
        "JOB_NO": ["2Q23 RP1"],
    })
    try:
        check_acce_ac2(df)
        raised = False
    except CustomRuleNotEvaluated:
        raised = True
    assert raised


def test_acce_ac2_fails_for_all_rows_when_reference_missing_country_column(
    monkeypatch,
):
    """If the reference dataset lacks COUNTRY, the join cannot validate
    location, every row fails (rule does not silently pass)."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_acce_ac2
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({"PROJECT_ID": ["PV-00001"]}),
    )
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001"],
        "JOB_NO": ["2Q23 RP1"],
    })
    assert check_acce_ac2(df).tolist() == [False]


def test_evaluate_custom_rules_dispatches_to_ac2(_ac2_reference_with_countries):
    """End-to-end: dispatcher routes an AC2 assignment through
    check_acce_ac2 against a known reference dataset for ACCE."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002"],
        "JOB_NO": ["2Q23 RP1", "2Q24"],
    })
    assignments = [CustomDQRAssignment(rule_id="AC2", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ACCE")
    assert "AC2" in out.columns
    assert out["AC2"].tolist() == [True, True]
    assert not_evaluated == {}


def test_required_reference_datasets_for_acce_now_includes_planview_share():
    """AC2 introduces ``VWS_GP_STANDARD_SHARE`` alongside
    ``ACCE_COA_MASTER`` for ACCE. Step 2 must prefetch both."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ACCE"])) == {
        "ACCE_COA_MASTER",
        "VWS_GP_STANDARD_SHARE",
    }


# =============================================================================
# AC3: Statistical COA-to-ISO mapping ratio (ACCE; mirrors ADR A3 with COA)
# =============================================================================

def _ac3_required_cols():
    return [
        "PLANVIEW_ID",
        "COA",
        "COST_MH",
        "COST_TOTAL_COST",
    ]


def _make_ac3_df(rows):
    """Build an ACCE-shaped denormalized DataFrame from a list of dicts.
    Missing keys default to None so the rule sees them as null."""
    cols = _ac3_required_cols()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


@pytest.fixture
def _ac3_coa_master_with_population(monkeypatch):
    """Pin the COA master to a known mapping so AC3 row-level assertions
    don't depend on the mock's RNG. Provides 10 distinct ``ICARUS_COA``
    codes mapping to 10 distinct ``(ISO_COR, SAB)`` buckets - just
    enough to cross ``ACCE_AC3_MIN_MAPPING_POPULATION`` (10).

    Tests synthesise an over-aggregating bucket by feeding many
    distinct 4-character source ``COA`` values that all share the
    same 3-character prefix (e.g. ``3130``, ``3131``, …, ``3154`` →
    all truncate to ``313`` → all resolve to ``(C2.12.1, S3.2.2)``).
    The per-bucket ``COUNT(DISTINCT COA)`` metric counts the full
    4-character COA, so 25 such source rows contribute ratio = 25
    on top of any baseline rows already in the bucket.
    """
    import src.reference_data as ref_mod
    rows = [
        # 10 baseline ICARUS_COA → 10 distinct (ISO_COR, SAB) buckets.
        # Each bucket therefore receives ≥ 1 distinct full-COA value in
        # the baseline population → ratio ≥ 1.
        ("311", "C1.6",     "S3.2.2"),
        ("312", "C1.7",     "S3.2.3"),
        ("313", "C2.12.1",  "S3.2.2"),    # over-aggregating bucket below
        ("314", "C2.13",    "S3.4"),
        ("317", "C3.2",     "S2.5"),
        ("318", "C3.3",     "S2.6"),
        ("321", "C4.2",     "S4.1"),
        ("323", "C5.1",     "S5.1"),
        ("324", "C5.2",     "S5.2"),
        ("325", "C5.3",     "S5.3"),
    ]
    ref_df = pd.DataFrame(rows, columns=["ICARUS_COA", "ISO_COR", "SAB"])
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    return ref_df


def _ac3_baseline_population(hours: float = 100.0, cost: float = 50.0):
    """Build AC3 rows for each of the 10 baseline (ISO_COR, SAB) buckets
    in the ``_ac3_coa_master_with_population`` fixture. Each row uses
    a unique 4-character ``COA`` whose 3-character prefix matches one
    of the baseline ``ICARUS_COA`` codes, so the per-bucket
    ``COUNT(DISTINCT COA)`` is 1 in the baseline distribution."""
    baseline_coas = [
        "3110", "3120", "3130", "3140", "3170",
        "3180", "3210", "3230", "3240", "3250",
    ]
    return [
        {
            "PLANVIEW_ID": f"PV-{coa}",
            "COA": coa,
            "COST_MH": hours,
            "COST_TOTAL_COST": cost,
        }
        for coa in baseline_coas
    ]


# ----- Catalog metadata ------------------------------------------------------

def test_acce_has_custom_rule_ac3_available():
    """ACCE catalog exposes AC3 as a non-blocking Statistical Outlier
    rule joined to the COA master through the direct ``COA`` column."""
    rules = get_available_custom_dqr_rules("ACCE")
    by_id = {r.id: r for r in rules}
    assert "AC3" in by_id
    rule = by_id["AC3"]
    assert rule.type == "Statistical Outlier"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Project Key": "PLANVIEW_ID",
        "Code of Account": "COA",
        "Construction Hours": "COST_MH",
        "Total Cost": "COST_TOTAL_COST",
    }
    assert rule.reference is not None
    assert rule.reference["reference_dataset"] == "ACCE_COA_MASTER"
    assert rule.reference["source_column"] == "COA"
    assert rule.reference["reference_column"] == "ICARUS_COA"


def test_acce_ac3_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ACCE_AC3_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ACCE") if r.id == "AC3"
    )
    assert rule.required_columns == ACCE_AC3_REQUIRED_COLUMNS


def test_acce_ac3_constants_are_documented_defaults():
    from src.custom_dqr_engine import (
        ACCE_AC3_MATERIALITY_USD,
        ACCE_AC3_MIN_MAPPING_POPULATION,
        ACCE_AC3_PERCENTILE,
        ACCE_AC3_UNIFORM_THRESHOLD,
    )
    assert ACCE_AC3_PERCENTILE == 0.90
    assert ACCE_AC3_MATERIALITY_USD == 100_000.0
    assert ACCE_AC3_MIN_MAPPING_POPULATION == 10
    assert ACCE_AC3_UNIFORM_THRESHOLD == 0.80


def test_acce_ac3_does_not_expose_project_scope_option():
    """Per the AC3 spec, the rule ships only the percentile selector
    and the uniform-detection toggle, no project-scope option (unlike
    ADR A3). This guards against accidentally adding it in the future,
    which would change the rule's user contract."""
    rule = next(
        r for r in get_available_custom_dqr_rules("ACCE") if r.id == "AC3"
    )
    option_keys = {opt.key for opt in (rule.options or ())}
    assert "project_scoped" not in option_keys


# ----- check_acce_ac3 - happy & FAIL paths -----------------------------------

def test_acce_ac3_passes_when_every_bucket_below_p90(
    _ac3_coa_master_with_population,
):
    """All 10 baseline buckets have ratio = 1 (one distinct COA each).
    P90 = 1, no bucket strictly exceeds the threshold → every row PASS."""
    from src.custom_dqr_engine import check_acce_ac3
    df = _make_ac3_df(_ac3_baseline_population())
    assert check_acce_ac3(df).all()


def test_acce_ac3_flags_over_aggregating_bucket(
    _ac3_coa_master_with_population,
):
    """Bucket ``(C2.12.1, S3.2.2)`` carries 1 baseline COA (``3130``)
    plus 9 extras (``3131``…``3139``), every value sharing the
    ``313`` prefix → COUNT(DISTINCT COA) = 10, well above the P90 of
    [1]*9+[10] = 1.9. Every row whose COA truncates to ``313`` must
    FAIL; every other baseline row must PASS.

    Note: only ten distinct 4-character codes share any given 3-char
    prefix (``313X`` where ``X`` is one of 0–9), so 9 is the largest
    pure-prefix-313 overload achievable; that ratio is more than
    enough to clear the P90."""
    from src.custom_dqr_engine import check_acce_ac3
    rows = _ac3_baseline_population()
    # Over-aggregating bucket: 9 extra distinct 4-char COAs all
    # sharing the 3-char prefix "313", all resolve via the same
    # ICARUS_COA = "313" master row → same (ISO_COR, SAB) bucket.
    overload_coas = [str(3131 + i) for i in range(9)]
    for coa in overload_coas:
        rows.append({
            "PLANVIEW_ID": "PV-OUTLIER",
            "COA": coa,
            "COST_MH": 1_000.0,
            "COST_TOTAL_COST": 500_000.0,
        })
    df = _make_ac3_df(rows)
    result = check_acce_ac3(df)
    # All rows whose COA maps to (C2.12.1, S3.2.2), the ``3130``
    # baseline row plus the 9 ``3131``–``3139`` overload rows -
    # must FAIL.
    overload_mask = df["COA"].astype(str).str[:3] == "313"
    assert (~result[overload_mask]).all()
    assert result[~overload_mask].all()


def test_acce_ac3_does_not_fail_immaterial_bucket(
    _ac3_coa_master_with_population,
):
    """An over-aggregating bucket whose hours = 0 AND cost <
    ACCE_AC3_MATERIALITY_USD must PASS, the materiality filter
    suppresses planning / structural-only mappings.

    Note: the bucket aggregates the ``3130`` baseline row *plus* the
    9 overload rows; materiality is summed across the whole bucket,
    so every row contributing to the bucket must be immaterial for
    the bucket to fall under the materiality bar.
    """
    from src.custom_dqr_engine import check_acce_ac3
    # Build a baseline where the 313-prefixed row is also immaterial.
    # Every other baseline bucket is material, they still pass
    # because ratio = 1 is at or below the P90 = 1 threshold.
    rows = [
        {
            "PLANVIEW_ID": f"PV-{coa}",
            "COA": coa,
            "COST_MH": 0.0 if coa.startswith("313") else 100.0,
            "COST_TOTAL_COST": 50.0,
        }
        for coa in [
            "3110", "3120", "3130", "3140", "3170",
            "3180", "3210", "3230", "3240", "3250",
        ]
    ]
    overload_coas = [str(3131 + i) for i in range(9)]
    for coa in overload_coas:
        rows.append({
            "PLANVIEW_ID": "PV-IMMATERIAL",
            "COA": coa,
            "COST_MH": 0.0,
            "COST_TOTAL_COST": 100.0,           # well below 100k threshold
        })
    df = _make_ac3_df(rows)
    assert check_acce_ac3(df).all()


def test_acce_ac3_uses_cost_materiality_when_hours_are_zero(
    _ac3_coa_master_with_population,
):
    """Hours zero but cost ≥ ACCE_AC3_MATERIALITY_USD still trips
    materiality, the cost branch suffices on its own."""
    from src.custom_dqr_engine import check_acce_ac3
    rows = _ac3_baseline_population()
    overload_coas = [str(3131 + i) for i in range(9)]
    for coa in overload_coas:
        rows.append({
            "PLANVIEW_ID": "PV-COST-MATERIAL",
            "COA": coa,
            "COST_MH": 0.0,
            "COST_TOTAL_COST": 200_000.0,
        })
    df = _make_ac3_df(rows)
    result = check_acce_ac3(df)
    # All rows whose COA shares the 313 prefix (baseline 3130 + 9
    # overloads) end up in the same bucket → cost-only materiality
    # trips → bucket FAILS.
    cost_mask = df["COA"].astype(str).str[:3] == "313"
    assert (~result[cost_mask]).all()


def test_acce_ac3_passes_when_population_below_min_threshold(monkeypatch):
    """If fewer than ``ACCE_AC3_MIN_MAPPING_POPULATION`` distinct ISO
    mappings exist, the P90 cannot be derived, every row passes."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_acce_ac3
    # Only 3 distinct master mappings - far below the min population
    # threshold (10).
    ref_df = pd.DataFrame({
        "ICARUS_COA": ["311", "312", "313"],
        "ISO_COR": ["C1.6", "C1.7", "C2.12.1"],
        "SAB": ["S3.2.2", "S3.2.3", "S3.2.2"],
    })
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    rows = [
        # An over-aggregating bucket that *would* fail if the
        # population were sufficient - with only 2 eligible (ISO,
        # SAB) buckets (313 and 311 share the same bucket as 312
        # does not - actually 311/312/313 produce 2 distinct buckets:
        # (C1.7,S3.2.3) and (C1.6/C2.12.1 share S3.2.2 → 2 buckets
        # since C1.6 ≠ C2.12.1), so 3 buckets total, still well below
        # the floor) the rule short-circuits to PASS.
        {"PLANVIEW_ID": "PV-1", "COA": "3130",
         "COST_MH": 1_000.0, "COST_TOTAL_COST": 500_000.0},
        {"PLANVIEW_ID": "PV-1", "COA": "3131",
         "COST_MH": 1_000.0, "COST_TOTAL_COST": 500_000.0},
        {"PLANVIEW_ID": "PV-1", "COA": "3110",
         "COST_MH": 100.0, "COST_TOTAL_COST": 50.0},
        {"PLANVIEW_ID": "PV-2", "COA": "3120",
         "COST_MH": 100.0, "COST_TOTAL_COST": 50.0},
    ]
    df = _make_ac3_df(rows)
    assert check_acce_ac3(df).all()


def test_acce_ac3_passes_when_coa_does_not_resolve(
    _ac3_coa_master_with_population,
):
    """Rows whose COA's 3-char prefix isn't in the master (orphan)
    resolve to NaN for both ISO_COR and SAB → those rows are
    NOT_APPLICABLE for AC3 (AC1's territory) and PASS regardless of
    the bucket distribution."""
    from src.custom_dqr_engine import check_acce_ac3
    rows = _ac3_baseline_population()
    # Orphan COA at the front; prefix ``999`` never appears in master.
    rows.insert(0, {
        "PLANVIEW_ID": "PV-ORPHAN",
        "COA": "9999",
        "COST_MH": 100.0,
        "COST_TOTAL_COST": 50.0,
    })
    df = _make_ac3_df(rows)
    assert check_acce_ac3(df).iloc[0]


def test_acce_ac3_passes_rows_whose_iso_or_sab_is_invalid(monkeypatch):
    """COAs that resolve to ``ERROR`` / ``N/A`` ISO_COR or SAB are
    NOT_APPLICABLE for AC3 - AC1 already covers that gap."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_acce_ac3
    # Build a population of 10 valid buckets + one ICARUS_COA that
    # resolves to an invalid ISO_COR. The invalid-mapping row must
    # PASS even though in principle its bucket would be eligible.
    rows = [
        ("311", "C1.6", "S3.2.2"),
        ("312", "C1.7", "S3.2.3"),
        ("313", "C2.12.1", "S3.2.2"),
        ("314", "C2.13", "S3.4"),
        ("317", "C3.2", "S2.5"),
        ("318", "C3.3", "S2.6"),
        ("321", "C4.2", "S4.1"),
        ("323", "C5.1", "S5.1"),
        ("324", "C5.2", "S5.2"),
        ("325", "C5.3", "S5.3"),
        ("888", "ERROR: #N/A", "S0.0"),  # invalid ISO_COR → NOT_APPLICABLE
    ]
    ref_df = pd.DataFrame(rows, columns=["ICARUS_COA", "ISO_COR", "SAB"])
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    df = _make_ac3_df([
        # 4-char source COA whose 3-char prefix is ``888`` → resolves
        # via the invalid-marker master row.
        {"PLANVIEW_ID": "PV-INVALID", "COA": "8881",
         "COST_MH": 1_000.0, "COST_TOTAL_COST": 500_000.0},
        *_ac3_baseline_population(),
    ])
    assert check_acce_ac3(df).all()


def test_acce_ac3_accepts_numeric_coa_column_dtype(
    _ac3_coa_master_with_population,
):
    """COA may arrive from Snowflake as a numeric column. Stringify-
    then-strip-then-truncate on both sides of the lookup must keep
    the join working - otherwise mock vs prod dtypes would silently
    produce all-NaN lookups and the rule would short-circuit to PASS."""
    from src.custom_dqr_engine import check_acce_ac3
    # 4-digit numeric COAs whose stringified first 3 characters match
    # the baseline ICARUS_COA codes in the fixture.
    rows = []
    for coa in (3110, 3120, 3130, 3140, 3170,
                3180, 3210, 3230, 3240, 3250):
        rows.append({
            "PLANVIEW_ID": f"PV-{coa}",
            "COA": coa,
            "COST_MH": 100.0,
            "COST_TOTAL_COST": 50.0,
        })
    df = _make_ac3_df(rows)
    df["COA"] = df["COA"].astype("Int64")
    assert check_acce_ac3(df).all()


# ----- schema-level / structural failures -----------------------------------

def test_acce_ac3_fails_for_all_rows_when_required_column_missing(
    _ac3_coa_master_with_population,
):
    """Drop one required column at a time, every row must FAIL
    (structurally incomplete, same convention as the rest of the
    catalog)."""
    from src.custom_dqr_engine import check_acce_ac3
    rows = _ac3_baseline_population()
    for missing in _ac3_required_cols():
        df = _make_ac3_df(rows).drop(columns=[missing])
        assert (~check_acce_ac3(df)).all(), (
            f"Expected all-FAIL when {missing} is missing"
        )


def test_acce_ac3_empty_dataframe_returns_empty_pass_series():
    from src.custom_dqr_engine import check_acce_ac3
    df = pd.DataFrame({c: [] for c in _ac3_required_cols()})
    result = check_acce_ac3(df)
    assert result.empty
    assert result.dtype == bool


def test_acce_ac3_raises_not_evaluated_when_reference_unavailable(monkeypatch):
    """If the COA master loader returns None, AC3 must raise
    CustomRuleNotEvaluated rather than silently passing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import CustomRuleNotEvaluated, check_acce_ac3
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    df = _make_ac3_df(_ac3_baseline_population())
    try:
        check_acce_ac3(df)
        raised = False
    except CustomRuleNotEvaluated:
        raised = True
    assert raised


def test_acce_ac3_fails_for_all_rows_when_reference_missing_required_columns(
    monkeypatch,
):
    """If the reference dataset lacks ICARUS_COA / ISO_COR / SAB the
    join cannot resolve mappings, every row fails."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_acce_ac3
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({"ICARUS_COA": ["313"]}),  # no ISO_COR/SAB
    )
    df = _make_ac3_df(_ac3_baseline_population())
    assert (~check_acce_ac3(df)).all()


def test_evaluate_custom_rules_dispatches_to_ac3(
    _ac3_coa_master_with_population,
):
    """End-to-end: dispatcher routes an AC3 assignment through
    check_acce_ac3 with default params (percentile P90, uniform off)."""
    rows = _ac3_baseline_population()
    overload_coas = [str(3131 + i) for i in range(9)]
    for coa in overload_coas:
        rows.append({
            "PLANVIEW_ID": "PV-OUTLIER",
            "COA": coa,
            "COST_MH": 1_000.0,
            "COST_TOTAL_COST": 500_000.0,
        })
    df = _make_ac3_df(rows)
    assignments = [CustomDQRAssignment(rule_id="AC3", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ACCE")
    assert "AC3" in out.columns
    overload_mask = df["COA"].astype(str).str[:3] == "313"
    assert (~out["AC3"][overload_mask]).all()
    assert out["AC3"][~overload_mask].all()
    assert not_evaluated == {}


# ----- AC3 - percentile threshold (params={"threshold_percentile": …}) -------

def test_acce_ac3_threshold_percentile_param_changes_pass_fail_boundary(
    monkeypatch,
):
    """A stricter percentile (P75) flags 2-ratio buckets that the
    default P90 lets pass.

    Engineered distribution: 8 baseline buckets with ratio = 1 plus 3
    buckets with ratio = 2 (population = 11 ≥ min-population floor).
    Sorted ratios = ``[1]*8 + [2]*3``. With numpy's linear-interpolation
    quantile:

    - P90 sits at position 9.0 → threshold = 2; ``2 > 2`` is False → the
      2-ratio buckets PASS.
    - P75 sits at position 7.5 → threshold = 1.5; ``2 > 1.5`` → the
      2-ratio buckets FAIL.

    Locks in that the user-customizable percentile actually rewires the
    PASS / FAIL boundary, not just the surface presentation.

    With the 3-char-prefix lookup, the 2-ratio buckets carry **two
    distinct 4-character source COAs sharing the same 3-character
    prefix** (so they truncate to the same ICARUS_COA and end up in
    the same bucket, but ``COUNT(DISTINCT COA)`` over the full
    4-character value is 2).
    """
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ACCE_AC3_THRESHOLD_PARAM,
        check_acce_ac3,
    )
    # 11-bucket master, every entry is a 3-char ICARUS_COA. The
    # 2-ratio buckets are realised by the source data (two distinct
    # 4-char COAs sharing the same 3-char prefix), not by extra
    # master rows.
    ref_rows = [
        ("311", "C1.6", "S3.2.2"),
        ("312", "C1.7", "S3.2.3"),
        ("314", "C2.13", "S3.4"),
        ("317", "C3.2", "S2.5"),
        ("318", "C3.3", "S2.6"),
        ("321", "C4.2", "S4.1"),
        ("323", "C5.1", "S5.1"),
        ("324", "C5.2", "S5.2"),
        ("325", "C5.3", "S5.3"),
        ("326", "C6.1", "S6.1"),
        ("327", "C7.1", "S7.1"),
    ]
    ref_df = pd.DataFrame(ref_rows, columns=["ICARUS_COA", "ISO_COR", "SAB"])
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)

    # 8 singleton buckets (one 4-char COA each, prefix matches one
    # ICARUS_COA above), and 3 paired buckets (two distinct 4-char
    # COAs each, both sharing a prefix → same (ISO_COR, SAB) bucket).
    singletons = [
        "3110", "3120", "3140", "3170", "3180", "3210", "3230", "3240",
    ]
    paired = ["3250", "3251", "3260", "3261", "3270", "3271"]
    rows = []
    for coa in singletons + paired:
        rows.append({
            "PLANVIEW_ID": f"PV-{coa}",
            "COA": coa,
            "COST_MH": 100.0,
            "COST_TOTAL_COST": 50.0,
        })
    df = _make_ac3_df(rows)

    paired_mask = df["COA"].isin(set(paired))

    # P90 default → 2-ratio buckets sit at threshold; no strict
    # exceedance → every row PASSES.
    result_default = check_acce_ac3(df)
    assert result_default.all()

    # P75 → threshold drops below 2 → every row in the 2-ratio buckets
    # FAILS; the 1:1 buckets still PASS.
    result_p75 = check_acce_ac3(
        df, params={ACCE_AC3_THRESHOLD_PARAM: 0.75}
    )
    assert (~result_p75[paired_mask]).all()
    assert result_p75[~paired_mask].all()


def test_acce_ac3_stale_threshold_param_falls_back_to_default(
    _ac3_coa_master_with_population,
):
    """A non-numeric / out-of-range threshold value must fall back to
    ACCE_AC3_PERCENTILE (P90) via _coerce_threshold, same contract as
    E3 / A3."""
    from src.custom_dqr_engine import (
        ACCE_AC3_THRESHOLD_PARAM,
        check_acce_ac3,
    )
    df = _make_ac3_df(_ac3_baseline_population())
    # Garbage threshold value → falls back to P90 → baseline all PASS.
    assert check_acce_ac3(
        df, params={ACCE_AC3_THRESHOLD_PARAM: "not-a-number"}
    ).all()


# ----- AC3 - uniform 1:1 detection with the 80% portfolio gate ---------------

def test_acce_ac3_uniform_detection_off_by_default_passes_uniform_buckets(
    _ac3_coa_master_with_population,
):
    """Without the toggle, the baseline population (every bucket 1:1)
    PASSES, the percentile branch sees P90 == 1 and no bucket exceeds it."""
    from src.custom_dqr_engine import check_acce_ac3
    df = _make_ac3_df(_ac3_baseline_population())
    assert check_acce_ac3(df).all()


def test_acce_ac3_uniform_detection_trips_when_majority_buckets_are_1_to_1(
    _ac3_coa_master_with_population,
):
    """Toggle on AND ≥ ACCE_AC3_UNIFORM_THRESHOLD (default 80%) of
    eligible mappings have ratio == 1 → every material 1:1 bucket
    inherits the FAIL. Baseline = 10 buckets all 1:1 → 100% uniform
    share → trips."""
    from src.custom_dqr_engine import (
        ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM,
        check_acce_ac3,
    )
    df = _make_ac3_df(_ac3_baseline_population(hours=100.0, cost=50.0))
    result = check_acce_ac3(
        df, params={ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM: True}
    )
    assert (~result).all()


@pytest.fixture
def _ac3_coa_master_ten_buckets(monkeypatch):
    """A 10-bucket master pinning ten distinct 3-character
    ``ICARUS_COA`` codes to ten distinct ``(ISO_COR, SAB)`` buckets.
    Tests realise the per-bucket ``COUNT(DISTINCT COA)`` ratio through
    the source data (4-character COAs sharing 3-character prefixes),
    not through extra master rows.

    Shared by the two uniform-gate tests below: one drives
    uniform-share = 8 / 10 = 80 % (exactly the gate), the other
    drives 6 / 10 = 60 % (below the gate)."""
    import src.reference_data as ref_mod
    rows = [
        ("311", "C1.6", "S3.2.2"),
        ("312", "C1.7", "S3.2.3"),
        ("314", "C2.13", "S3.4"),
        ("317", "C3.2", "S2.5"),
        ("318", "C3.3", "S2.6"),
        ("321", "C4.2", "S4.1"),
        ("323", "C5.1", "S5.1"),
        ("324", "C5.2", "S5.2"),
        ("325", "C5.3", "S5.3"),
        ("326", "C6.1", "S6.1"),
    ]
    ref_df = pd.DataFrame(rows, columns=["ICARUS_COA", "ISO_COR", "SAB"])
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    return ref_df


def test_acce_ac3_uniform_gate_trips_at_exact_threshold(
    _ac3_coa_master_ten_buckets,
):
    """Uniform-share = 8 / 10 = 80 %, exactly the gate. With the
    toggle on, every material 1:1 bucket fails.

    Source data: 8 buckets carry exactly one 4-character COA
    (ratio = 1) and 2 buckets carry two distinct 4-character COAs
    sharing the same 3-character prefix (ratio = 2).
    """
    from src.custom_dqr_engine import (
        ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM,
        check_acce_ac3,
    )
    one_to_one_coas = [
        "3110", "3120", "3140", "3170", "3180", "3210", "3230", "3240",
    ]
    two_to_one_coas = ["3250", "3251", "3260", "3261"]
    rows = []
    for coa in one_to_one_coas + two_to_one_coas:
        rows.append({
            "PLANVIEW_ID": f"PV-{coa}",
            "COA": coa,
            "COST_MH": 100.0,
            "COST_TOTAL_COST": 50.0,
        })
    df = _make_ac3_df(rows)
    result = check_acce_ac3(
        df, params={ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM: True}
    )
    one_to_one_mask = df["COA"].isin(set(one_to_one_coas))
    two_to_one_mask = df["COA"].isin(set(two_to_one_coas))
    # Material 1:1 buckets all FAIL when the gate trips.
    assert (~result[one_to_one_mask]).all()
    # 2:1 buckets aren't 1:1 → uniform branch doesn't touch them; with
    # ratio = 2 and baseline [1]*8+[2]*2, P90 = 2 → no percentile fail
    # either → those rows PASS.
    assert result[two_to_one_mask].all()


def test_acce_ac3_uniform_gate_below_threshold_does_not_trip(
    _ac3_coa_master_ten_buckets,
):
    """Uniform-share = 6 / 10 = 60 %, below the 80 % gate → toggle on
    does **not** flag the 1:1 buckets. P90 of [1]*6 + [2]*4 = 2 → no
    percentile fail either → every row PASSES.

    Source data: 6 buckets carry exactly one 4-character COA
    (ratio = 1) and 4 buckets carry two distinct 4-character COAs
    sharing the same 3-character prefix (ratio = 2).
    """
    from src.custom_dqr_engine import (
        ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM,
        check_acce_ac3,
    )
    one_to_one_coas = [
        "3110", "3120", "3140", "3170", "3180", "3210",
    ]
    two_to_one_coas = [
        "3230", "3231",
        "3240", "3241",
        "3250", "3251",
        "3260", "3261",
    ]
    rows = []
    for coa in one_to_one_coas + two_to_one_coas:
        rows.append({
            "PLANVIEW_ID": f"PV-{coa}",
            "COA": coa,
            "COST_MH": 100.0,
            "COST_TOTAL_COST": 50.0,
        })
    df = _make_ac3_df(rows)
    result = check_acce_ac3(
        df, params={ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM: True}
    )
    assert result.all()


def test_acce_ac3_uniform_detection_respects_materiality(
    _ac3_coa_master_with_population,
):
    """Toggle on AND ≥80% of buckets are 1:1, but the 1:1 buckets are
    immaterial (hours = 0 AND cost < materiality) → those buckets
    PASS. Materiality gates both the percentile and uniform branches,
    same as A3."""
    from src.custom_dqr_engine import (
        ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM,
        check_acce_ac3,
    )
    df = _make_ac3_df(
        _ac3_baseline_population(hours=0.0, cost=50.0)
    )
    assert check_acce_ac3(
        df, params={ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM: True}
    ).all()


# =============================================================================
# AC4: Core quantities populated (ACCE; DESCRIPTION allow-lists + split qty)
# =============================================================================

def _ac4_required_cols():
    return [
        "PLANVIEW_ID",
        "DESCRIPTION",
        "QTY_KEY_QTY",
        "QTY_OTHER_QTY",
        "QTY_KEY_UNITS",
        "QTY_OTHER_UNITS",
    ]


def _make_ac4_df(rows):
    """Build an ACCE-shaped denormalized DataFrame from a list of dicts.
    Missing keys default to None so the rule sees them as null."""
    cols = _ac4_required_cols()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def _ac4_row(planview, description, qty=None, uom=None, *, slot="key"):
    """Convenience row builder: populate one qty slot (KEY by default).
    ``qty`` / ``uom`` land in ``QTY_KEY_*`` (slot='key') or
    ``QTY_OTHER_*`` (slot='other'); the opposite slot stays null."""
    row = {"PLANVIEW_ID": planview, "DESCRIPTION": description}
    if slot == "other":
        row["QTY_OTHER_QTY"] = qty
        row["QTY_OTHER_UNITS"] = uom
    else:
        row["QTY_KEY_QTY"] = qty
        row["QTY_KEY_UNITS"] = uom
    return row


# ----- Catalog metadata ------------------------------------------------------

def test_acce_has_custom_rule_ac4_available():
    """ACCE catalog exposes AC4 as a non-blocking Completeness & Validity
    rule with no reference dataset (same as A4)."""
    rules = get_available_custom_dqr_rules("ACCE")
    by_id = {r.id: r for r in rules}
    assert "AC4" in by_id
    rule = by_id["AC4"]
    assert rule.type == "Completeness & Validity"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Project Key": "PLANVIEW_ID",
        "Item Description": "DESCRIPTION",
        "Key Quantity": "QTY_KEY_QTY",
        "Other Quantity": "QTY_OTHER_QTY",
        "Key Units": "QTY_KEY_UNITS",
        "Other Units": "QTY_OTHER_UNITS",
    }
    assert rule.reference is None


def test_acce_ac4_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ACCE_AC4_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ACCE") if r.id == "AC4"
    )
    assert rule.required_columns == ACCE_AC4_REQUIRED_COLUMNS


# ----- Scope classifier ------------------------------------------------------

def test_ac4_scope_classifier_picks_up_each_of_seven_categories():
    """One representative DESCRIPTION per scope category, every
    category must be returned. Scope keys off the DESCRIPTION
    allow-lists alone (MODULE_COUNT is a substring match)."""
    from src.custom_dqr_engine import _classify_ac4_scope_acce
    cases = [
        ("PIPING",              "PIPING_LF"),
        ("CS PIPE ERECTION",    "PIPING_LF"),
        ("CONCRETE",            "CONCRETE_CY"),
        ("FOUNDATION ACCESSORIES", "CONCRETE_CY"),
        ("STEEL STRUCTURES",    "STEEL_TONS"),
        ("CABLE TRAYS",         "CABLE_LENGTH"),
        ("ELECTRICAL",          "CABLE_LENGTH"),
        ("FLOW INSTRUMENTS",    "TRANSMITTER_COUNT"),
        ("CENTRIFUGAL PUMPS",   "EQUIPMENT_COUNT"),
        ("PROCESS MODULE",      "MODULE_COUNT"),
        ("MODULAR SKID",        "MODULE_COUNT"),
    ]
    for desc, expected in cases:
        scopes = _classify_ac4_scope_acce(desc)
        assert expected in scopes, f"({desc!r}) → {scopes}"


def test_ac4_scope_classifier_unrecognised_inputs_return_empty_set():
    from src.custom_dqr_engine import _classify_ac4_scope_acce
    assert _classify_ac4_scope_acce(None) == set()
    assert _classify_ac4_scope_acce("") == set()
    assert _classify_ac4_scope_acce("GENERIC WIDGET") == set()


def test_ac4_scope_classifier_matches_description_case_insensitively():
    """DESCRIPTION matching is case-insensitive and trims whitespace -
    a lower-cased / padded canonical label still resolves."""
    from src.custom_dqr_engine import _classify_ac4_scope_acce
    assert "PIPING_LF" in _classify_ac4_scope_acce("  piping  ")
    assert "STEEL_TONS" in _classify_ac4_scope_acce("Steel Structures")


def test_ac4_scope_classifier_module_keyword_case_insensitive():
    """``MODULE`` / ``MODULAR`` is a case-insensitive substring match,
    so any DESCRIPTION carrying the token implies module scope."""
    from src.custom_dqr_engine import _classify_ac4_scope_acce
    for desc in ("module skid", "Process Module", "PRE-MODULAR YARD"):
        assert "MODULE_COUNT" in _classify_ac4_scope_acce(desc)


# ----- Quantity classifier ---------------------------------------------------

def test_ac4_quantity_classifier_returns_correct_category_per_pattern():
    from src.custom_dqr_engine import _classify_ac4_quantity_acce
    # (description, key_units, expected) - positive KEY_QTY, OTHER null.
    cases = [
        # PIPING_LF
        ("PIPING",            "FT",    "PIPING_LF"),
        ("CS PIPE ERECTION",  "FEET",  "PIPING_LF"),
        ("PIPING",            "M",     "PIPING_LF"),
        # CONCRETE_CY
        ("CONCRETE",          "YD3",   "CONCRETE_CY"),
        ("CONCRETE",          "CY",    "CONCRETE_CY"),
        ("FOUNDATION ACCESSORIES", "M3", "CONCRETE_CY"),
        # STEEL_TONS
        ("STEEL",             "T",     "STEEL_TONS"),
        ("STEEL STRUCTURES",  "TONS",  "STEEL_TONS"),
        ("STEEL",             "TONNE", "STEEL_TONS"),
        # CABLE_LENGTH
        ("ELECTRICAL",        "FT",    "CABLE_LENGTH"),
        ("CABLE TRAYS",       "M",     "CABLE_LENGTH"),
        # TRANSMITTER_COUNT
        ("INSTRUMENTATION",   "EACH",  "TRANSMITTER_COUNT"),
        ("FLOW INSTRUMENTS",  "ITEMS", "TRANSMITTER_COUNT"),
        # EQUIPMENT_COUNT
        ("CENTRIFUGAL PUMPS", "EACH",  "EQUIPMENT_COUNT"),
        ("S&T EXCHANGER",     "EA",    "EQUIPMENT_COUNT"),
        ("HORZ. VESSELS",     "ITEM",  "EQUIPMENT_COUNT"),
        # MODULE_COUNT - DESCRIPTION substring (MODULE / MODULAR) + count UOM.
        ("PROCESS MODULE",    "EACH",  "MODULE_COUNT"),
    ]
    for desc, uom, expected in cases:
        got = _classify_ac4_quantity_acce(desc, uom, None, 10.0, None)
        assert got == expected, (
            f"({desc!r}, {uom!r}) → {got}, expected {expected}"
        )


def test_ac4_quantity_classifier_reads_other_slot():
    """Population can come from the OTHER_* slot when KEY_* is null -
    a positive ``OTHER_QTY`` with an ``OTHER_UNITS`` in the type's set
    classifies the same as the KEY slot."""
    from src.custom_dqr_engine import _classify_ac4_quantity_acce
    assert _classify_ac4_quantity_acce(
        "PIPING", None, "FT", None, 25.0
    ) == "PIPING_LF"


def test_ac4_quantity_classifier_rejects_off_pattern_uom_for_each_category():
    """Each category requires a specific UOM family - a piping row in
    tons doesn't classify as steel (or as anything else)."""
    from src.custom_dqr_engine import _classify_ac4_quantity_acce
    assert _classify_ac4_quantity_acce("PIPING", "T", None, 10.0, None) is None
    assert _classify_ac4_quantity_acce("STEEL", "FT", None, 10.0, None) is None
    assert _classify_ac4_quantity_acce("CONCRETE", "FT", None, 10.0, None) is None
    assert _classify_ac4_quantity_acce("ELECTRICAL", "T", None, 10.0, None) is None
    assert _classify_ac4_quantity_acce(
        "CENTRIFUGAL PUMPS", "T", None, 10.0, None
    ) is None
    assert _classify_ac4_quantity_acce(
        "INSTRUMENTATION", "T", None, 10.0, None
    ) is None


def test_ac4_quantity_classifier_requires_positive_quantity():
    """Population requires ``KEY_QTY > 0`` OR ``OTHER_QTY > 0`` strictly -
    zero / negative / null in both slots classifies as None."""
    from src.custom_dqr_engine import _classify_ac4_quantity_acce
    assert _classify_ac4_quantity_acce("PIPING", "FT", None, 0.0, None) is None
    assert _classify_ac4_quantity_acce("PIPING", "FT", None, -5.0, None) is None
    assert _classify_ac4_quantity_acce("PIPING", "FT", None, None, None) is None


def test_ac4_quantity_classifier_returns_none_on_blank_or_unrecognised_inputs():
    from src.custom_dqr_engine import _classify_ac4_quantity_acce
    # Positive qty but the DESCRIPTION is in no allow-list → None.
    assert _classify_ac4_quantity_acce(
        "GENERAL WORKS", "EACH", None, 10.0, None
    ) is None
    # Positive qty + valid description but blank / null units → None.
    assert _classify_ac4_quantity_acce("PIPING", None, None, 10.0, None) is None
    assert _classify_ac4_quantity_acce("PIPING", "  ", "  ", 10.0, None) is None
    # Null description → None.
    assert _classify_ac4_quantity_acce(None, "FT", None, 10.0, None) is None


# ----- check_acce_ac4 - happy & failure paths --------------------------------

def test_acce_ac4_passes_project_with_all_expected_quantities_populated():
    """Project P1 has piping + concrete scope and a populated row for
    each - passes."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        _ac4_row("P1", "PIPING", 1000.0, "FT"),
        _ac4_row("P1", "CONCRETE", 50.0, "YD3"),
    ])
    assert check_acce_ac4(df).tolist() == [True, True]


def test_acce_ac4_fails_project_when_expected_scope_lacks_populated_quantity():
    """Project P1 has piping scope but the only piping row has UOM=T
    (steel UOM), no populated PIPING_LF → project FAILs."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        _ac4_row("P1", "PIPING", 1000.0, "T"),       # wrong UOM
        _ac4_row("P1", "CONCRETE", 50.0, "YD3"),
    ])
    assert check_acce_ac4(df).tolist() == [False, False]


def test_acce_ac4_fails_project_when_quantity_zero_or_null_for_expected_scope():
    """Population requires KEY_QTY / OTHER_QTY > 0 strictly - null /
    zero / negative don't satisfy 'populated' for that scope."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([_ac4_row("P1", "STEEL", 0.0, "T")])
    assert check_acce_ac4(df).tolist() == [False]
    df = _make_ac4_df([_ac4_row("P1", "STEEL", -5.0, "T")])
    assert check_acce_ac4(df).tolist() == [False]


def test_acce_ac4_passes_project_with_no_recognised_scope():
    """Off-pattern DESCRIPTION values imply no core quantity type → no
    EXPECTS_X = 1 → project trivially passes."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([_ac4_row("P1", "GENERAL WORKS", 100.0, "EA")])
    assert check_acce_ac4(df).tolist() == [True]


def test_acce_ac4_handles_multiple_projects_independently():
    """A failing project must not contaminate a passing one, each
    project's scope and population is judged in isolation."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        # P1: concrete scope populated → PASS.
        _ac4_row("P1", "CONCRETE", 30.0, "YD3"),
        # P2: concrete populated AND piping scope with wrong UOM → FAIL.
        _ac4_row("P2", "CONCRETE", 30.0, "YD3"),
        _ac4_row("P2", "PIPING", 100.0, "EA"),       # wrong UOM
    ])
    assert check_acce_ac4(df).tolist() == [True, False, False]


def test_acce_ac4_population_can_come_from_other_slot():
    """A core type is populated when the OTHER_* slot carries the
    positive qty + matching unit and the KEY_* slot is null."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        _ac4_row("P1", "PIPING", 1000.0, "FT", slot="other"),
    ])
    assert check_acce_ac4(df).tolist() == [True]


def test_acce_ac4_fails_project_with_negative_total_quantity():
    """Validity: a project whose combined KEY+OTHER quantity total sums
    to a negative value fails, independent of the expected-type check."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        _ac4_row("P1", "GENERAL WORKS", -200.0, "EA"),
        _ac4_row("P1", "GENERAL WORKS", 50.0, "EA"),
    ])
    # Project total = -150 < 0 → both rows FAIL.
    assert check_acce_ac4(df).tolist() == [False, False]


def test_acce_ac4_passes_project_with_negative_rows_but_nonnegative_total():
    """Individual rows may carry negative quantities (corrections /
    reversals) - the project passes as long as the combined total is not
    negative."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        _ac4_row("P1", "GENERAL WORKS", -50.0, "EA"),
        _ac4_row("P1", "GENERAL WORKS", 120.0, "EA"),
    ])
    # Project total = +70 ≥ 0 → both rows PASS despite a negative row.
    assert check_acce_ac4(df).tolist() == [True, True]


def test_acce_ac4_passes_project_with_zero_total_quantity():
    """A combined total of exactly zero is not negative → passes."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        _ac4_row("P1", "GENERAL WORKS", -50.0, "EA"),
        _ac4_row("P1", "GENERAL WORKS", 50.0, "EA"),
    ])
    assert check_acce_ac4(df).tolist() == [True, True]


def test_acce_ac4_negative_total_combines_key_and_other_slots():
    """The negative-total check sums BOTH quantity slots: a positive KEY
    total offset by a larger negative OTHER total fails the project."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        _ac4_row("P1", "GENERAL WORKS", 40.0, "EA", slot="key"),
        _ac4_row("P1", "GENERAL WORKS", -100.0, "EA", slot="other"),
    ])
    # KEY=+40, OTHER=-100 → combined -60 < 0 → FAIL.
    assert check_acce_ac4(df).tolist() == [False, False]


def test_acce_ac4_fails_populated_project_with_negative_total():
    """The negative-total check is OR-ed with the completeness check: a
    project whose expected scope IS populated still fails if a large
    correction drives its combined total negative."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        _ac4_row("P1", "CONCRETE", 30.0, "YD3"),    # concrete populated
        _ac4_row("P1", "CONCRETE", -100.0, "YD3"),  # correction
    ])
    # Concrete scope populated (the +30 row) → completeness passes, but
    # project total = -70 < 0 → project FAILs.
    assert check_acce_ac4(df).tolist() == [False, False]


def test_acce_ac4_negative_total_in_one_project_does_not_affect_another():
    """Negative-total failure is scoped per project."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        _ac4_row("P1", "GENERAL WORKS", 500.0, "EA"),
        _ac4_row("P2", "GENERAL WORKS", -10.0, "EA"),
    ])
    # P1 total +500 → PASS; P2 total -10 → FAIL.
    assert check_acce_ac4(df).tolist() == [True, False]


def test_acce_ac4_passes_rows_with_blank_planview_id():
    """Rows whose PLANVIEW_ID is null/blank can't be assigned to a
    project, they pass regardless of how their peer projects do."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        _ac4_row(None, "PIPING", 100.0, "T"),        # wrong UOM
        _ac4_row("P-BAD", "CONCRETE", 10.0, "T"),    # wrong UOM
    ])
    result = check_acce_ac4(df).tolist()
    assert result[0] is True
    assert result[1] is False


def test_acce_ac4_passes_when_every_expected_scope_populated_for_all_seven():
    """A project with all seven scopes expected and all seven populated
    must pass - exercises every category branch end-to-end."""
    from src.custom_dqr_engine import check_acce_ac4
    rows = [
        _ac4_row("P1", "PIPING", 1000.0, "FT"),            # PIPING_LF
        _ac4_row("P1", "CONCRETE", 50.0, "YD3"),           # CONCRETE_CY
        _ac4_row("P1", "STEEL", 100.0, "T"),               # STEEL_TONS
        _ac4_row("P1", "ELECTRICAL", 200.0, "M"),          # CABLE_LENGTH
        _ac4_row("P1", "INSTRUMENTATION", 12.0, "EACH"),   # TRANSMITTER_COUNT
        _ac4_row("P1", "CENTRIFUGAL PUMPS", 5.0, "EACH"),  # EQUIPMENT_COUNT
        _ac4_row("P1", "PROCESS MODULE", 3.0, "EACH"),     # MODULE_COUNT
    ]
    df = _make_ac4_df(rows)
    assert check_acce_ac4(df).all()


def test_acce_ac4_fails_when_one_of_seven_expected_scopes_unpopulated():
    """Piping + concrete scope implied, but the concrete row has the
    wrong UOM - HAS_CONCRETE_CY = False → project FAILS."""
    from src.custom_dqr_engine import check_acce_ac4
    rows = [
        _ac4_row("P1", "PIPING", 1000.0, "FT"),
        # Concrete scope is implied but the row uses tons.
        _ac4_row("P1", "CONCRETE", 50.0, "T"),
    ]
    df = _make_ac4_df(rows)
    assert check_acce_ac4(df).tolist() == [False, False]


# ----- check_acce_ac4 - schema-level / structural failures -------------------

def test_acce_ac4_fails_for_all_rows_when_required_column_missing():
    """Schema-level structural incompleteness fails every row."""
    from src.custom_dqr_engine import check_acce_ac4
    base = pd.DataFrame({
        "PLANVIEW_ID": ["P1", "P1"],
        "DESCRIPTION": ["CONCRETE"] * 2,
        "QTY_KEY_QTY": [10.0, 20.0],
        "QTY_OTHER_QTY": [None, None],
        "QTY_KEY_UNITS": ["YD3", "YD3"],
        "QTY_OTHER_UNITS": [None, None],
    })
    for missing in _ac4_required_cols():
        df = base.drop(columns=missing)
        assert check_acce_ac4(df).tolist() == [False, False], (
            f"missing {missing} should fail every row"
        )


def test_acce_ac4_empty_dataframe_returns_empty_pass_series():
    from src.custom_dqr_engine import check_acce_ac4
    df = pd.DataFrame({c: [] for c in _ac4_required_cols()})
    result = check_acce_ac4(df)
    assert result.tolist() == []
    assert result.dtype == bool


def test_acce_ac4_passes_when_no_planview_id_filled_for_any_row():
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        _ac4_row(None, "CONCRETE", 10.0, "T"),
        _ac4_row("  ", "STEEL", 5.0, "FT"),
    ])
    assert check_acce_ac4(df).tolist() == [True, True]


def test_acce_ac4_handles_object_dtyped_numeric_quantities():
    """Mixed string / numeric inputs must coerce - non-numeric become
    NaN and are treated as not-populated."""
    from src.custom_dqr_engine import check_acce_ac4
    df = _make_ac4_df([
        _ac4_row("P1", "CONCRETE", "abc", "YD3"),
        _ac4_row("P1", "CONCRETE", "50", "YD3"),
    ])
    # Concrete scope, one populated row → P1 passes.
    assert check_acce_ac4(df).tolist() == [True, True]


def test_evaluate_custom_rules_dispatches_to_ac4():
    """End-to-end: dispatcher routes an AC4 assignment through
    check_acce_ac4 against the ACCE data product."""
    df = _make_ac4_df([
        _ac4_row("P1", "CONCRETE", 30.0, "YD3"),
        _ac4_row("P-BAD", "PIPING", 100.0, "T"),     # piping scope, wrong UOM
    ])
    assignments = [CustomDQRAssignment(rule_id="AC4", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ACCE")
    assert "AC4" in out.columns
    assert out["AC4"].tolist() == [True, False]
    assert not_evaluated == {}


def test_acce_ac4_does_not_add_reference_dataset_to_prefetch():
    """AC4 has no ``reference`` dataset, so the ACCE system's prefetch
    list is the same one AC1 + AC2 already require."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ACCE"])) == {
        "ACCE_COA_MASTER",
        "VWS_GP_STANDARD_SHARE",
    }


# =============================================================================
# AC5: Design details present when quantity exists (ACCE; mirrors ADR A5)
# =============================================================================

def _ac5_required_cols():
    return ["QTY_KEY_QTY", "QTY_OTHER_QTY", "DESIGN_PROPERTY", "DESIGN_VALUE"]


def _make_ac5_df(rows):
    """Build an ACCE-shaped denormalized DataFrame from a list of dicts.
    Missing keys default to None so the rule sees them as null."""
    cols = _ac5_required_cols()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def _ac5_row(qty=None, value=None, prop="DESIGN PRESSURE", *, slot="key"):
    """One AC5 row: a single populated qty slot (KEY by default) plus a
    design parameter name (``prop``, defaults to a populated name) and
    value. A populated detail needs BOTH ``prop`` and ``value`` set."""
    row = {"DESIGN_PROPERTY": prop, "DESIGN_VALUE": value}
    if slot == "other":
        row["QTY_OTHER_QTY"] = qty
    else:
        row["QTY_KEY_QTY"] = qty
    return row


def test_acce_has_custom_rule_ac5_available():
    """ACCE catalog exposes AC5 as a non-blocking Consistency rule
    with the documented physical column mapping (split qty + named
    design parameter)."""
    rules = get_available_custom_dqr_rules("ACCE")
    by_id = {r.id: r for r in rules}
    assert "AC5" in by_id
    rule = by_id["AC5"]
    assert rule.type == "Consistency"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Key Quantity": "QTY_KEY_QTY",
        "Other Quantity": "QTY_OTHER_QTY",
        "Design Parameter Name": "DESIGN_PROPERTY",
        "Design Parameter Value": "DESIGN_VALUE",
    }
    # AC5 does not consult an external reference dataset.
    assert rule.reference is None


def test_acce_ac5_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ACCE_AC5_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ACCE") if r.id == "AC5"
    )
    assert rule.required_columns == ACCE_AC5_REQUIRED_COLUMNS


def test_acce_ac5_passes_when_quantity_and_design_detail_both_present():
    """Happy path: positive quantity + both DESIGN_PROPERTY and
    DESIGN_VALUE populated. The quantity may sit in either slot."""
    from src.custom_dqr_engine import check_acce_ac5
    df = _make_ac5_df([
        _ac5_row(10.0, "SCH 40"),
        _ac5_row(0.5, "Carbon Steel"),
        _ac5_row(3.0, "6 in", slot="other"),   # qty in OTHER slot
    ])
    assert check_acce_ac5(df).tolist() == [True, True, True]


def test_acce_ac5_fails_when_quantity_present_but_value_missing():
    """A positive quantity with a named parameter but no value FAILs.
    Null / empty / whitespace-only ``DESIGN_VALUE`` all count as
    missing (same ``_is_filled`` semantics AC1 / AC2 use)."""
    from src.custom_dqr_engine import check_acce_ac5
    df = _make_ac5_df([
        _ac5_row(10.0, None),
        _ac5_row(5.0, ""),
        _ac5_row(2.0, "   "),
    ])
    assert check_acce_ac5(df).tolist() == [False, False, False]


def test_acce_ac5_fails_when_value_present_but_property_missing():
    """The new PROPERTY requirement: a value with no named parameter
    (the "120 m of what?" case) is not a usable design detail, so a
    positive-quantity row with a blank ``DESIGN_PROPERTY`` FAILs."""
    from src.custom_dqr_engine import check_acce_ac5
    df = _make_ac5_df([
        _ac5_row(10.0, "120", prop=None),
        _ac5_row(5.0, "120", prop=""),
        _ac5_row(2.0, "120", prop="   "),
    ])
    assert check_acce_ac5(df).tolist() == [False, False, False]


def test_acce_ac5_passes_when_quantity_zero_regardless_of_design_detail():
    """Zero quantity in both slots is treated as 'no quantity'; rule is
    not applicable and the row passes - even when the design detail is
    also missing."""
    from src.custom_dqr_engine import check_acce_ac5
    df = _make_ac5_df([
        _ac5_row(0.0, None, prop=None),
        _ac5_row(0.0, ""),
        _ac5_row(0.0, "ABC"),
    ])
    assert check_acce_ac5(df).tolist() == [True, True, True]


def test_acce_ac5_passes_when_quantity_null_regardless_of_design_detail():
    """A null aggregated quantity in both slots is treated as 'no
    quantity', the rule is not applicable and the row passes."""
    from src.custom_dqr_engine import check_acce_ac5
    df = _make_ac5_df([
        _ac5_row(None, None, prop=None),
        _ac5_row(None, "SS-316"),
    ])
    assert check_acce_ac5(df).tolist() == [True, True]


def test_acce_ac5_negative_quantity_counts_as_no_quantity():
    """Population uses ``KEY_QTY > 0 OR OTHER_QTY > 0`` strictly, so a
    negative aggregated quantity counts as 'no quantity' → the rule is
    not applicable and the row PASSES even with no design detail."""
    from src.custom_dqr_engine import check_acce_ac5
    df = _make_ac5_df([
        _ac5_row(-3.0, None, prop=None),
        _ac5_row(-3.0, "Carbon Steel"),
    ])
    assert check_acce_ac5(df).tolist() == [True, True]


def test_acce_ac5_decision_matrix_covers_all_four_states():
    """End-to-end coverage of the four-state decision matrix in a
    single batch."""
    from src.custom_dqr_engine import check_acce_ac5
    df = _make_ac5_df([
        # HAS_QUANTITY=0, HAS_DESIGN_DETAIL=0 → PASS
        _ac5_row(0.0, None, prop=None),
        # HAS_QUANTITY=0, HAS_DESIGN_DETAIL=1 → PASS
        _ac5_row(0.0, "ASME"),
        # HAS_QUANTITY=1, HAS_DESIGN_DETAIL=0 → FAIL
        _ac5_row(12.0, "", prop=None),
        # HAS_QUANTITY=1, HAS_DESIGN_DETAIL=1 → PASS
        _ac5_row(12.0, "API-650"),
    ])
    assert check_acce_ac5(df).tolist() == [True, True, False, True]


def test_acce_ac5_handles_object_dtyped_numeric_quantities():
    """A heterogeneous source (e.g. mixed numeric strings and floats)
    must not crash the rule - ``pd.to_numeric`` coerces unrecognised
    values to NaN which the rule treats as 'no quantity'."""
    from src.custom_dqr_engine import check_acce_ac5
    df = pd.DataFrame({
        "QTY_KEY_QTY": ["10", "0", None, "abc"],
        "QTY_OTHER_QTY": [None, None, None, None],
        "DESIGN_PROPERTY": [None, None, None, None],
        "DESIGN_VALUE": [None, None, None, None],
    })
    # Row 0: "10" → 10 > 0, no detail → FAIL.
    # Rows 1, 2, 3: 0 / NaN / NaN → "no quantity" → PASS.
    assert check_acce_ac5(df).tolist() == [False, True, True, True]


def test_acce_ac5_fails_for_all_rows_when_required_column_missing():
    """Schema-level structural incompleteness fails every row, for any
    of the four required columns."""
    from src.custom_dqr_engine import ACCE_AC5_REQUIRED_COLUMNS, check_acce_ac5
    base = pd.DataFrame({
        "QTY_KEY_QTY": [10.0, 10.0],
        "QTY_OTHER_QTY": [None, None],
        "DESIGN_PROPERTY": ["DIAMETER", "DIAMETER"],
        "DESIGN_VALUE": ["SCH 40", "ASME"],
    })
    for missing in ACCE_AC5_REQUIRED_COLUMNS.values():
        df = base.drop(columns=missing)
        assert check_acce_ac5(df).tolist() == [False, False], (
            f"missing {missing} should fail every row"
        )


def test_acce_ac5_empty_dataframe_returns_empty_pass_series():
    """An empty DataFrame produces an empty Boolean Series, the rule
    short-circuits before any column logic runs."""
    from src.custom_dqr_engine import check_acce_ac5
    df = pd.DataFrame({c: [] for c in _ac5_required_cols()})
    result = check_acce_ac5(df)
    assert result.tolist() == []
    assert result.dtype == bool


def test_evaluate_custom_rules_dispatches_to_ac5():
    """End-to-end: dispatcher routes an AC5 assignment through
    check_acce_ac5 for the ACCE data product."""
    df = _make_ac5_df([
        _ac5_row(10.0, "ASME"),
        _ac5_row(7.0, None),                 # positive qty, no value → FAIL
        _ac5_row(0.0, None, prop=None),
    ])
    assignments = [CustomDQRAssignment(rule_id="AC5", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ACCE")
    assert "AC5" in out.columns
    assert out["AC5"].tolist() == [True, False, True]
    assert not_evaluated == {}


def test_acce_ac5_does_not_add_reference_dataset_to_prefetch():
    """AC5 has no ``reference`` dataset, so the ACCE prefetch list
    is unchanged."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ACCE"])) == {
        "ACCE_COA_MASTER",
        "VWS_GP_STANDARD_SHARE",
    }


# =============================================================================
# AC6: Construction hours present when quantity exists (ACCE; mirrors A6)
# =============================================================================

def _ac6_required_cols():
    return ["QTY_KEY_QTY", "QTY_OTHER_QTY", "COST_MH"]


def _make_ac6_df(rows):
    """Build an ACCE-shaped denormalized DataFrame from a list of dicts.
    Missing keys default to None so the rule sees them as null.

    Note the hours column is ``COST_MH`` (sourced from ``MH`` on
    ``ACCE_ESTIMATECOSTRESULTS``); ACCE has no Design-Build hours
    counterpart of ``COST_DB_TOTAL_HOURS``."""
    cols = _ac6_required_cols()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def _ac6_row(qty=None, mh=None, *, slot="key"):
    """One AC6 row: a single populated qty slot (KEY by default) and a
    construction-hours value (``COST_MH``)."""
    row = {"COST_MH": mh}
    if slot == "other":
        row["QTY_OTHER_QTY"] = qty
    else:
        row["QTY_KEY_QTY"] = qty
    return row


def test_acce_has_custom_rule_ac6_available():
    """ACCE catalog exposes AC6 as a non-blocking Consistency rule
    with the documented physical column mapping (split qty +
    ``COST_MH``)."""
    rules = get_available_custom_dqr_rules("ACCE")
    by_id = {r.id: r for r in rules}
    assert "AC6" in by_id
    rule = by_id["AC6"]
    assert rule.type == "Consistency"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Key Quantity": "QTY_KEY_QTY",
        "Other Quantity": "QTY_OTHER_QTY",
        "Construction Hours": "COST_MH",
    }
    # AC6 does not consult an external reference dataset.
    assert rule.reference is None


def test_acce_ac6_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ACCE_AC6_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ACCE") if r.id == "AC6"
    )
    assert rule.required_columns == ACCE_AC6_REQUIRED_COLUMNS


def test_acce_ac6_passes_when_quantity_and_hours_both_present():
    """Happy path: positive quantity + positive ``COST_MH``. The
    quantity may sit in either slot."""
    from src.custom_dqr_engine import check_acce_ac6
    df = _make_ac6_df([
        _ac6_row(10.0, 50.0),
        _ac6_row(0.5, 0.001),
        _ac6_row(3.0, 10.0, slot="other"),   # qty in OTHER slot
    ])
    assert check_acce_ac6(df).tolist() == [True, True, True]


def test_acce_ac6_fails_when_quantity_present_but_no_construction_hours():
    """The only FAIL path: positive quantity, zero / null hours.
    Operates on the single ``COST_MH`` column - ACCE has no
    Design-Build hours fallback."""
    from src.custom_dqr_engine import check_acce_ac6
    df = _make_ac6_df([
        _ac6_row(10.0, None),
        _ac6_row(5.0, 0.0),
        _ac6_row(2.0, 0),
    ])
    assert check_acce_ac6(df).tolist() == [False, False, False]


def test_acce_ac6_negative_hours_do_not_count_as_present():
    """Per spec: ``HAS_CONSTRUCTION_HOURS = COST_MH > 0`` strictly.
    Negative aggregates do not count as hours present, so a row
    with positive quantity and negative hours FAILS."""
    from src.custom_dqr_engine import check_acce_ac6
    df = _make_ac6_df([
        _ac6_row(10.0, -50.0),
        _ac6_row(10.0, -0.001),
    ])
    assert check_acce_ac6(df).tolist() == [False, False]


def test_acce_ac6_passes_when_quantity_zero_regardless_of_hours():
    """Zero quantity in both slots is treated as 'no quantity'; rule
    is not applicable and the row passes - even when hours are also
    missing (one-directional implication)."""
    from src.custom_dqr_engine import check_acce_ac6
    df = _make_ac6_df([
        _ac6_row(0.0, None),
        _ac6_row(0.0, 0.0),
        _ac6_row(0.0, 100.0),
    ])
    assert check_acce_ac6(df).tolist() == [True, True, True]


def test_acce_ac6_passes_when_quantity_null_regardless_of_hours():
    """A null aggregated quantity in both slots is treated as 'no
    quantity', the rule is not applicable and the row passes."""
    from src.custom_dqr_engine import check_acce_ac6
    df = _make_ac6_df([
        _ac6_row(None, None),
        _ac6_row(None, 50.0),
    ])
    assert check_acce_ac6(df).tolist() == [True, True]


def test_acce_ac6_negative_quantity_counts_as_no_quantity():
    """Population uses ``KEY_QTY > 0 OR OTHER_QTY > 0`` strictly, so a
    negative aggregated quantity counts as 'no quantity' → the row
    PASSES even with no hours present."""
    from src.custom_dqr_engine import check_acce_ac6
    df = _make_ac6_df([
        _ac6_row(-3.0, None),
        _ac6_row(-3.0, 50.0),
    ])
    assert check_acce_ac6(df).tolist() == [True, True]


def test_acce_ac6_decision_matrix_covers_all_four_states():
    """End-to-end coverage of the four-state decision matrix in a
    single batch."""
    from src.custom_dqr_engine import check_acce_ac6
    df = _make_ac6_df([
        # HAS_QUANTITY=0, HAS_HOURS=0 → PASS
        _ac6_row(0.0, None),
        # HAS_QUANTITY=0, HAS_HOURS=1 → PASS (one-directional)
        _ac6_row(0.0, 100.0),
        # HAS_QUANTITY=1, HAS_HOURS=0 → FAIL
        _ac6_row(12.0, 0.0),
        # HAS_QUANTITY=1, HAS_HOURS=1 → PASS
        _ac6_row(12.0, 50.0),
    ])
    assert check_acce_ac6(df).tolist() == [True, True, False, True]


def test_acce_ac6_handles_object_dtyped_numeric_inputs():
    """Heterogeneous source (mixed numeric strings and floats) must
    not crash - ``pd.to_numeric`` coerces unrecognised values to NaN
    which the rule treats as zero / 'no quantity'."""
    from src.custom_dqr_engine import check_acce_ac6
    df = pd.DataFrame({
        "QTY_KEY_QTY": ["10", "0", None, "abc"],
        "QTY_OTHER_QTY": [None, None, None, None],
        "COST_MH": [None, None, "50", "100"],
    })
    # Row 0: 10 / NaN(0) → quantity, no hours → FAIL.
    # Row 1: 0 / NaN(0) → no quantity → PASS.
    # Row 2: NaN(0) / 50 → no quantity → PASS.
    # Row 3: NaN(0) / 100 → no quantity → PASS.
    assert check_acce_ac6(df).tolist() == [False, True, True, True]


def test_acce_ac6_fails_for_all_rows_when_required_column_missing():
    """Schema-level structural incompleteness fails every row, for any
    required column."""
    from src.custom_dqr_engine import ACCE_AC6_REQUIRED_COLUMNS, check_acce_ac6
    base = pd.DataFrame({
        "QTY_KEY_QTY": [10.0, 10.0],
        "QTY_OTHER_QTY": [None, None],
        "COST_MH": [50.0, 0.0],
    })
    for missing in ACCE_AC6_REQUIRED_COLUMNS.values():
        df = base.drop(columns=missing)
        assert check_acce_ac6(df).tolist() == [False, False], (
            f"missing {missing} should fail every row"
        )


def test_acce_ac6_empty_dataframe_returns_empty_pass_series():
    """An empty DataFrame produces an empty Boolean Series, the
    rule short-circuits before any column logic runs."""
    from src.custom_dqr_engine import check_acce_ac6
    df = pd.DataFrame({c: [] for c in _ac6_required_cols()})
    result = check_acce_ac6(df)
    assert result.tolist() == []
    assert result.dtype == bool


def test_evaluate_custom_rules_dispatches_to_ac6():
    """End-to-end: dispatcher routes an AC6 assignment through
    check_acce_ac6 for the ACCE data product."""
    df = _make_ac6_df([
        _ac6_row(10.0, 50.0),
        _ac6_row(7.0, None),                 # positive qty, no hours → FAIL
        _ac6_row(0.0, None),
    ])
    assignments = [CustomDQRAssignment(rule_id="AC6", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ACCE")
    assert "AC6" in out.columns
    assert out["AC6"].tolist() == [True, False, True]
    assert not_evaluated == {}


def test_acce_ac6_does_not_add_reference_dataset_to_prefetch():
    """AC6 has no ``reference`` dataset, so the ACCE prefetch list
    is unchanged."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ACCE"])) == {
        "ACCE_COA_MASTER",
        "VWS_GP_STANDARD_SHARE",
    }


# =============================================================================
# AC7: Within-discipline quantity / hour ratio outlier (ACCE; mirrors A7)
# =============================================================================

def _ac7_required_cols():
    return [
        "DESCRIPTION",
        "QTY_KEY_QTY",
        "QTY_OTHER_QTY",
        "QTY_KEY_UNITS",
        "QTY_OTHER_UNITS",
        "COST_MH",
    ]


def _make_ac7_df(rows):
    """Build an ACCE-shaped denormalized DataFrame from a list of dicts.
    Missing keys default to None so the rule sees them as null.

    Note the segment-by columns are the raw ``DESCRIPTION`` value +
    the effective UOM (``COALESCE(KEY_UNITS, OTHER_UNITS)``), and the
    hours column is ``COST_MH`` (sourced from ``MH``)."""
    cols = _ac7_required_cols()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def _ac7_row(description, qty, mh, uom, *, slot="key"):
    """One AC7 row: a ``DESCRIPTION`` segment label, a quantity in one
    slot (KEY by default) with its UOM, and construction hours
    (``COST_MH``)."""
    row = {"DESCRIPTION": description, "COST_MH": mh}
    if slot == "other":
        row["QTY_OTHER_QTY"] = qty
        row["QTY_OTHER_UNITS"] = uom
    else:
        row["QTY_KEY_QTY"] = qty
        row["QTY_KEY_UNITS"] = uom
    return row


def _ac7_segment_with_outlier(
    description: str = "CONCRETE",
    qty_uom: str = "CY",
    n_baseline: int = 12,
    baseline_ratio: float = 5.0,
    outlier_ratio: float = 50.0,
):
    """Build a single ``(DESCRIPTION, QTY_UOM)`` segment with
    ``n_baseline`` rows clustered tightly around ``baseline_ratio`` plus
    one row at ``outlier_ratio``."""
    rows = []
    for i in range(n_baseline):
        # Mild jitter keeps IQR strictly > 0 (so the segment doesn't
        # short-circuit to PASS via the ``IQR == 0`` branch) without
        # widening the spread enough to absorb the outlier.
        ratio = baseline_ratio + (0.05 if i % 2 else -0.05)
        rows.append(_ac7_row(description, 100.0, ratio * 100.0, qty_uom))
    rows.append(_ac7_row(description, 100.0, outlier_ratio * 100.0, qty_uom))
    return _make_ac7_df(rows)


def test_acce_has_custom_rule_ac7_available():
    """ACCE catalog exposes AC7 as a non-blocking Statistical Outlier
    rule with the documented physical column mapping (raw
    ``DESCRIPTION`` + effective UOM segment, split qty, ``COST_MH``,
    IQR-multiplier selectbox, and a project-type segmentation toggle)."""
    rules = get_available_custom_dqr_rules("ACCE")
    by_id = {r.id: r for r in rules}
    assert "AC7" in by_id
    rule = by_id["AC7"]
    assert rule.type == "Statistical Outlier"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Item Description": "DESCRIPTION",
        "Key Quantity": "QTY_KEY_QTY",
        "Other Quantity": "QTY_OTHER_QTY",
        "Key Units": "QTY_KEY_UNITS",
        "Other Units": "QTY_OTHER_UNITS",
        "Construction Hours": "COST_MH",
    }
    assert rule.reference is None
    # AC7 surfaces the IQR-multiplier selectbox and the
    # segment_by_project_type toggle (mirrors A7).
    select_keys = {opt.key for opt in (rule.select_options or ())}
    assert "threshold_iqr_multiplier" in select_keys
    option_keys = {opt.key for opt in (rule.options or ())}
    assert "segment_by_project_type" in option_keys


def test_acce_ac7_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ACCE_AC7_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ACCE") if r.id == "AC7"
    )
    assert rule.required_columns == ACCE_AC7_REQUIRED_COLUMNS


def test_acce_ac7_constants_are_documented_defaults():
    """The IQR multipliers and population threshold match what the
    rule documentation promises (1.5× / 3.0× / 10)."""
    from src.custom_dqr_engine import (
        ACCE_AC7_EXTREME_IQR_MULTIPLIER,
        ACCE_AC7_MILD_IQR_MULTIPLIER,
        ACCE_AC7_MIN_POPULATION,
    )
    assert ACCE_AC7_MILD_IQR_MULTIPLIER == 1.5
    assert ACCE_AC7_EXTREME_IQR_MULTIPLIER == 3.0
    assert ACCE_AC7_MIN_POPULATION == 10


# ----- check_acce_ac7 - happy & failure paths --------------------------------

def test_acce_ac7_flags_outlier_in_well_populated_segment():
    """Headline scenario: 12 baseline rows clustered around ratio=5
    plus one row at ratio=50. The outlier must FAIL; every baseline
    row must PASS."""
    from src.custom_dqr_engine import check_acce_ac7
    df = _ac7_segment_with_outlier(
        n_baseline=12, baseline_ratio=5.0, outlier_ratio=50.0
    )
    result = check_acce_ac7(df).tolist()
    assert result[:-1] == [True] * 12
    assert result[-1] is False


def test_acce_ac7_flags_low_side_outlier_below_mild_lower_bound():
    """Outliers below ``Q1 - 1.5*IQR`` must also FAIL - AC7 is
    two-sided, same as A7."""
    from src.custom_dqr_engine import check_acce_ac7
    df = _ac7_segment_with_outlier(
        n_baseline=12, baseline_ratio=5.0, outlier_ratio=0.05
    )
    result = check_acce_ac7(df).tolist()
    assert result[:-1] == [True] * 12
    assert result[-1] is False


def test_acce_ac7_passes_when_segment_population_below_min_threshold():
    """A segment with fewer than ``ACCE_AC7_MIN_POPULATION`` eligible
    rows is too small to derive thresholds, every row passes."""
    from src.custom_dqr_engine import (
        ACCE_AC7_MIN_POPULATION,
        check_acce_ac7,
    )
    df = _ac7_segment_with_outlier(
        n_baseline=ACCE_AC7_MIN_POPULATION - 2,
        baseline_ratio=5.0,
        outlier_ratio=50.0,
    )
    # Total rows < 10 → no segment can FAIL.
    assert check_acce_ac7(df).all()


def test_acce_ac7_passes_every_row_when_segment_iqr_is_zero():
    """If every eligible row in a segment has the same ratio, IQR = 0
    and the rule short-circuits to PASS for the segment."""
    from src.custom_dqr_engine import check_acce_ac7
    rows = [
        _ac7_row("CONCRETE", 100.0, 500.0, "CY")
        for _ in range(12)
    ]
    # One row with a different ratio would otherwise be a FAIL, but
    # since every other ratio is exactly 5.0, IQR = 0 → PASS.
    rows.append(_ac7_row("CONCRETE", 100.0, 50_000.0, "CY"))
    df = _make_ac7_df(rows)
    # The added row introduces variation - Q1=5, Q3=5 still (12 of 13
    # at ratio 5), but IQR = 0 means the segment cannot fail. Even
    # though the 13th ratio is far from the median, AC7 returns PASS.
    result = check_acce_ac7(df)
    assert result.iloc[:-1].all()
    # Documented IQR=0 short-circuit: the spike row also passes.
    assert bool(result.iloc[-1])


def test_acce_ac7_ignores_ineligible_rows_when_computing_bounds():
    """Rows that can't produce a ratio must be excluded from the
    segment's IQR computation - non-zero quantity AND non-zero hours
    is the gate. Ineligible rows themselves are always PASS."""
    from src.custom_dqr_engine import check_acce_ac7
    df = _ac7_segment_with_outlier(n_baseline=12, outlier_ratio=5.0)
    head = _make_ac7_df([
        _ac7_row("CONCRETE", 0.0, 5_000.0, "CY"),
        _ac7_row("CONCRETE", 100.0, 0.0, "CY"),
        _ac7_row("CONCRETE", None, 5_000.0, "CY"),
        _ac7_row("CONCRETE", -50.0, 5_000.0, "CY"),
        _ac7_row("CONCRETE", 100.0, -1.0, "CY"),
    ])
    df = pd.concat([head, df], ignore_index=True)
    result = check_acce_ac7(df)
    # The first 5 rows are not eligible → all PASS regardless of segment.
    assert result.iloc[:5].tolist() == [True, True, True, True, True]


def test_acce_ac7_passes_when_description_or_uom_blank():
    """Rows that can't be assigned to a ``(DESCRIPTION, QTY_UOM)``
    segment pass - there's no peer group to compare against."""
    from src.custom_dqr_engine import check_acce_ac7
    df = _make_ac7_df([
        _ac7_row(None, 100.0, 5_000.0, "CY"),
        _ac7_row("CONCRETE", 100.0, 5_000.0, None),
        _ac7_row("   ", 100.0, 5_000.0, "CY"),
        _ac7_row("CONCRETE", 100.0, 5_000.0, "  "),
    ])
    assert check_acce_ac7(df).tolist() == [True, True, True, True]


def test_acce_ac7_segments_independently_by_description_and_uom():
    """An outlier in segment X must not contaminate segment Y. Two
    well-populated segments - CONCRETE/CY tight around 5, STEEL/T
    tight around 80, and one row in each that is an outlier *for
    its own segment*. Both outliers FAIL; baseline rows PASS."""
    from src.custom_dqr_engine import check_acce_ac7
    civ_baseline = [
        _ac7_row("CONCRETE", 100.0, 500.0 + (5.0 if i % 2 else -5.0), "CY")
        for i in range(12)
    ]
    steel_baseline = [
        _ac7_row("STEEL", 10.0, 800.0 + (10.0 if i % 2 else -10.0), "T")
        for i in range(12)
    ]
    civ_outlier = _ac7_row("CONCRETE", 100.0, 8_000.0, "CY")
    steel_outlier = _ac7_row("STEEL", 10.0, 50.0, "T")
    rows = civ_baseline + [civ_outlier] + steel_baseline + [steel_outlier]
    df = _make_ac7_df(rows)
    result = check_acce_ac7(df).tolist()
    assert result[:12] == [True] * 12
    assert result[12] is False
    assert result[13:25] == [True] * 12
    assert result[25] is False


def test_acce_ac7_does_not_cross_segments_when_uoms_differ():
    """Same DESCRIPTION but different effective UOM = different
    segments. A single row in a tiny UOM segment (population = 1)
    passes even with an absurd ratio."""
    from src.custom_dqr_engine import check_acce_ac7
    civ_cy = [
        _ac7_row("CONCRETE", 100.0, 500.0 + (5.0 if i % 2 else -5.0), "CY")
        for i in range(12)
    ]
    civ_ft = _ac7_row("CONCRETE", 100.0, 100_000.0, "FT")
    df = _make_ac7_df(civ_cy + [civ_ft])
    assert check_acce_ac7(df).all()


# ----- AC7 - IQR multiplier param --------------------------------------------

def test_acce_ac7_iqr_multiplier_param_widens_pass_band():
    """A row that fails at 1.5×IQR may pass at 3.0×IQR, the param
    controls the per-segment PASS band width."""
    from src.custom_dqr_engine import (
        ACCE_AC7_THRESHOLD_PARAM,
        check_acce_ac7,
    )
    # Outlier at 10× the baseline - sits inside 3.0×IQR for a tight
    # baseline (jitter ±0.05 over a baseline of 5.0, so IQR ≈ 0.1
    # → 3.0×IQR widens the upper bound to ~5.3, then linear extrapolation
    # depends on Q3). The exact bound depends on the distribution; we
    # use a ratio that's *clearly* an outlier at 1.5× and *clearly*
    # within range at 3.0×. To engineer this reliably, choose a
    # moderately spread baseline and a ratio that sits between the
    # mild and extreme bands.
    rows = [
        _ac7_row("CONCRETE", 100.0, (5.0 + i * 0.1) * 100.0, "CY")
        for i in range(12)
    ]
    # Q1 ≈ 5.25, Q3 ≈ 5.85, IQR ≈ 0.6.
    # mild_upper = 5.85 + 1.5*0.6 = 6.75.
    # extreme_upper = 5.85 + 3.0*0.6 = 7.65.
    # Outlier ratio = 7.0 → fails at 1.5×, passes at 3.0×.
    rows.append(_ac7_row("CONCRETE", 100.0, 700.0, "CY"))
    df = _make_ac7_df(rows)
    # Default (1.5×) → outlier fails.
    result_default = check_acce_ac7(df).tolist()
    assert result_default[-1] is False
    # 3.0× → outlier sits inside the wider band → passes.
    result_extreme = check_acce_ac7(
        df, params={ACCE_AC7_THRESHOLD_PARAM: 3.0}
    ).tolist()
    assert result_extreme[-1] is True


def test_acce_ac7_stale_threshold_param_falls_back_to_default():
    """A non-numeric / out-of-range threshold value must fall back to
    ``ACCE_AC7_MILD_IQR_MULTIPLIER`` (1.5×) via ``_coerce_threshold``."""
    from src.custom_dqr_engine import (
        ACCE_AC7_THRESHOLD_PARAM,
        check_acce_ac7,
    )
    df = _ac7_segment_with_outlier(
        n_baseline=12, baseline_ratio=5.0, outlier_ratio=50.0
    )
    # Stale param → fallback to 1.5× → outlier still fails.
    result = check_acce_ac7(
        df, params={ACCE_AC7_THRESHOLD_PARAM: "garbage"}
    ).tolist()
    assert result[-1] is False


# ----- AC7 - schema-level / structural failures -----------------------------

def test_acce_ac7_fails_for_all_rows_when_required_column_missing():
    """Schema-level structural incompleteness fails every row."""
    from src.custom_dqr_engine import check_acce_ac7
    base = pd.DataFrame({
        "DESCRIPTION": ["CONCRETE"] * 3,
        "QTY_KEY_QTY": [100.0, 100.0, 100.0],
        "QTY_OTHER_QTY": [None, None, None],
        "QTY_KEY_UNITS": ["CY"] * 3,
        "QTY_OTHER_UNITS": [None, None, None],
        "COST_MH": [500.0, 500.0, 500.0],
    })
    for missing in _ac7_required_cols():
        df = base.drop(columns=missing)
        assert check_acce_ac7(df).tolist() == [False, False, False], (
            f"missing {missing} should fail every row"
        )


def test_acce_ac7_empty_dataframe_returns_empty_pass_series():
    from src.custom_dqr_engine import check_acce_ac7
    df = pd.DataFrame({c: [] for c in _ac7_required_cols()})
    result = check_acce_ac7(df)
    assert result.tolist() == []
    assert result.dtype == bool


def test_acce_ac7_passes_when_no_eligible_rows_at_all():
    """Every row ineligible → no segment statistics to compute → every
    row passes (rule short-circuits before the groupby)."""
    from src.custom_dqr_engine import check_acce_ac7
    df = _make_ac7_df([
        _ac7_row("CONCRETE", 0.0, 0.0, "CY"),
        _ac7_row(None, 100.0, 500.0, None),
    ])
    assert check_acce_ac7(df).tolist() == [True, True]


def test_acce_ac7_handles_object_dtyped_numeric_inputs():
    """Mixed string / numeric inputs must not crash. Non-numeric
    values coerce to NaN and are treated as ineligible."""
    from src.custom_dqr_engine import check_acce_ac7
    rows = [
        _ac7_row("CONCRETE", "100", "abc", "CY"),
        _ac7_row("CONCRETE", "abc", "500", "CY"),
    ]
    df = _make_ac7_df(rows)
    # Both rows have a non-numeric value somewhere → not eligible → PASS.
    assert check_acce_ac7(df).tolist() == [True, True]


def test_evaluate_custom_rules_dispatches_to_ac7():
    """End-to-end: dispatcher routes an AC7 assignment through
    check_acce_ac7 for the ACCE data product."""
    df = _ac7_segment_with_outlier(
        n_baseline=12, baseline_ratio=5.0, outlier_ratio=50.0
    )
    assignments = [CustomDQRAssignment(rule_id="AC7", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ACCE")
    assert "AC7" in out.columns
    assert out["AC7"].iloc[:-1].all()
    assert out["AC7"].iloc[-1] is False or bool(out["AC7"].iloc[-1]) is False
    assert not_evaluated == {}


def test_acce_ac7_does_not_add_reference_dataset_to_prefetch():
    """AC7 declares no static reference (the Planview lookup only
    fires when the segment-by-project-type toggle is on), so the
    ACCE prefetch list is unchanged. AC2 already brings in
    ``VWS_GP_STANDARD_SHARE`` for ACCE, so the segmented branch has
    a cached reference when it runs."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ACCE"])) == {
        "ACCE_COA_MASTER",
        "VWS_GP_STANDARD_SHARE",
    }


# ----- AC7 - project-type segmentation (toggle: segment_by_project_type) -----

def _ac7_required_cols_with_planview():
    return _ac7_required_cols() + ["PLANVIEW_ID"]


def _make_ac7_segmented_df(rows):
    """Build an ACCE-shaped DataFrame that also carries ``PLANVIEW_ID``
    so the AC7 segment-by-project-type lookup can resolve each row to
    a segment."""
    cols = _ac7_required_cols_with_planview()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def _ac7_segment_reference(rows):
    """Build a Planview reference DataFrame with the segmentation
    columns AC7 reads when the segment-by-project-type toggle is on."""
    return pd.DataFrame(
        rows, columns=["PROJECT_ID", "E05_DEPARTMENT", "BUSINESS"]
    )


def _ac7_baseline_rows(
    planview_prefix: str,
    description: str = "CONCRETE",
    qty_uom: str = "CY",
    n: int = 12,
    ratio: float = 5.0,
):
    """Build ``n`` rows clustered tightly around ``ratio`` for one
    discipline. Mild jitter keeps IQR > 0 so the segment isn't
    short-circuited via the ``IQR == 0`` PASS branch."""
    rows = []
    for i in range(n):
        jitter = 0.05 if i % 2 else -0.05
        rows.append({
            "PLANVIEW_ID": f"{planview_prefix}-{i}",
            "DESCRIPTION": description,
            "QTY_KEY_QTY": 100.0,
            "QTY_KEY_UNITS": qty_uom,
            "COST_MH": (ratio + jitter) * 100.0,
        })
    return rows


def test_acce_ac7_segment_param_constants_match_catalog():
    """The segmentation toggle exposed on the AC7 catalog rule card
    carries the same key the engine reads from ``params``, and the
    rule declares ``PLANVIEW_ID`` as a required-when-enabled column."""
    from src.custom_dqr_engine import ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM
    rule = next(
        r for r in get_available_custom_dqr_rules("ACCE") if r.id == "AC7"
    )
    by_key = {opt.key: opt for opt in (rule.options or ())}
    assert ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM in by_key
    opt = by_key[ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM]
    # PLANVIEW_ID is needed only when the toggle is on - Step 4.2's
    # CDE-coverage check picks this up via effective_required_columns.
    assert "PLANVIEW_ID" in opt.required_columns_when_enabled.values()


def test_acce_ac7_segmented_isolates_outliers_per_segment(monkeypatch):
    """With segmentation on, an outlier within its own segment is
    flagged even though it would look in-band against the
    discipline-only population. Two segments with distinct ratios are
    kept separate, so a row that is 'normal' for FPSO does not get
    judged against a refinery baseline."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_acce_ac7,
    )
    seg_a = _ac7_baseline_rows(planview_prefix="P-A", n=12, ratio=5.0)
    seg_b = _ac7_baseline_rows(planview_prefix="P-B", n=12, ratio=50.0)
    # Outlier within segment A: ratio 50 looks normal globally (matches
    # segment B's centre) but is a huge outlier in segment A.
    seg_a.append({
        "PLANVIEW_ID": "P-A-OUT",
        "DESCRIPTION": "CONCRETE",
        "QTY_KEY_QTY": 100.0,
        "QTY_KEY_UNITS": "CY",
        "COST_MH": 5_000.0,
    })
    ref_rows = (
        [(f"P-A-{k}", "BROWNFIELD", "UPSTREAM") for k in range(12)]
        + [("P-A-OUT", "BROWNFIELD", "UPSTREAM")]
        + [(f"P-B-{k}", "GREENFIELD", "DOWNSTREAM") for k in range(12)]
    )
    ref_df = _ac7_segment_reference(ref_rows)
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    df = _make_ac7_segmented_df(seg_a + seg_b)
    result = check_acce_ac7(
        df, params={ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # Segment A baseline rows pass; the within-segment outlier fails.
    assert result.iloc[:12].all()
    assert not bool(result.iloc[12])
    # Segment B rows all pass (their own segment is uniform).
    assert result.iloc[13:].all()


def test_acce_ac7_segmented_passes_when_segment_population_below_minimum(
    monkeypatch,
):
    """A (DESCRIPTION, QTY_UOM, E05_DEPARTMENT, BUSINESS) segment whose
    eligible-row count is below ``ACCE_AC7_MIN_POPULATION`` is
    NOT_APPLICABLE → PASS, even when one of its rows has a ratio
    that would obviously fail against the discipline-wide IQR."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ACCE_AC7_MIN_POPULATION,
        ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_acce_ac7,
    )
    seg_a = _ac7_baseline_rows(planview_prefix="P-A", n=12, ratio=5.0)
    seg_b = _ac7_baseline_rows(
        planview_prefix="P-B", n=ACCE_AC7_MIN_POPULATION - 2, ratio=5.0
    )
    seg_b.append({
        "PLANVIEW_ID": "P-B-OUT",
        "DESCRIPTION": "CONCRETE",
        "QTY_KEY_QTY": 100.0,
        "QTY_KEY_UNITS": "CY",
        "COST_MH": 50_000.0,        # ratio 500 - would fail globally
    })
    ref_rows = (
        [(f"P-A-{k}", "BROWNFIELD", "UPSTREAM") for k in range(12)]
        + [
            (f"P-B-{k}", "GREENFIELD", "LNG")
            for k in range(ACCE_AC7_MIN_POPULATION - 2)
        ]
        + [("P-B-OUT", "GREENFIELD", "LNG")]
    )
    ref_df = _ac7_segment_reference(ref_rows)
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    df = _make_ac7_segmented_df(seg_a + seg_b)
    result = check_acce_ac7(
        df, params={ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # Segment A is uniform (passes); segment B is under the floor (passes).
    assert result.all()


def test_acce_ac7_segmented_passes_rows_without_resolved_segment(monkeypatch):
    """Rows whose PLANVIEW_ID does not match the reference, or whose
    matched segment has a null/blank ``E05_DEPARTMENT`` / ``BUSINESS``,
    are NOT_APPLICABLE → PASS so segmentation never double-penalises
    the referential-integrity gap AC2 / blocking AC1 already cover."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_acce_ac7,
    )
    seg_a = _ac7_baseline_rows(planview_prefix="P-A", n=12, ratio=5.0)
    # ORPHAN belongs nowhere - stripped from the reference.
    seg_a.append({
        "PLANVIEW_ID": "P-A-ORPHAN",
        "DESCRIPTION": "CONCRETE",
        "QTY_KEY_QTY": 100.0,
        "QTY_KEY_UNITS": "CY",
        "COST_MH": 50_000.0,
    })
    # NULL-SEG has a matched row but a null segment column.
    seg_a.append({
        "PLANVIEW_ID": "P-A-NULL",
        "DESCRIPTION": "CONCRETE",
        "QTY_KEY_QTY": 100.0,
        "QTY_KEY_UNITS": "CY",
        "COST_MH": 50_000.0,
    })
    # Row with a null PLANVIEW_ID - also NOT_APPLICABLE → PASS.
    seg_a.append({
        "PLANVIEW_ID": None,
        "DESCRIPTION": "CONCRETE",
        "QTY_KEY_QTY": 100.0,
        "QTY_KEY_UNITS": "CY",
        "COST_MH": 50_000.0,
    })
    ref_rows = (
        [(f"P-A-{k}", "BROWNFIELD", "UPSTREAM") for k in range(12)]
        + [("P-A-NULL", None, "UPSTREAM")]
    )
    ref_df = _ac7_segment_reference(ref_rows)
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    df = _make_ac7_segmented_df(seg_a)
    result = check_acce_ac7(
        df, params={ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # All baseline rows pass (uniform segment) AND every unresolved row
    # passes too, they are NOT_APPLICABLE in segmented mode.
    assert result.all()


def test_acce_ac7_segmented_raises_not_evaluated_when_reference_unavailable(
    monkeypatch,
):
    """With segmentation on, an absent ``VWS_GP_STANDARD_SHARE``
    reference must raise :class:`CustomRuleNotEvaluated` - never
    silently fall back to the discipline-only IQR baseline."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM,
        CustomRuleNotEvaluated,
        check_acce_ac7,
    )
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset_error", lambda name: "network down"
    )
    df = _make_ac7_segmented_df(
        _ac7_baseline_rows(planview_prefix="P-A", n=12, ratio=5.0)
    )
    with pytest.raises(CustomRuleNotEvaluated):
        check_acce_ac7(
            df, params={ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
        )


def test_acce_ac7_unsegmented_does_not_touch_reference(monkeypatch):
    """Default (segmentation off) must not consult the reference
    dataset at all, the legacy (DESCRIPTION, QTY_UOM)-only path keeps
    its standalone behaviour and never blows up when the reference is
    missing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_acce_ac7

    def _boom(_name):
        raise AssertionError(
            "Unsegmented AC7 must not call get_reference_dataset"
        )

    monkeypatch.setattr(ref_mod, "get_reference_dataset", _boom)
    df = _make_ac7_segmented_df(
        _ac7_baseline_rows(planview_prefix="P-A", n=12, ratio=5.0)
    )
    # No outlier, so the rule passes regardless of segmentation.
    assert check_acce_ac7(df).all()


def test_acce_ac7_segmented_fails_when_planview_id_column_missing(monkeypatch):
    """With segmentation on, PLANVIEW_ID becomes a structurally
    required column, the rule fails every row when it is missing,
    mirroring the schema-incomplete convention."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_acce_ac7,
    )
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: _ac7_segment_reference([])
    )
    df = _make_ac7_df([
        _ac7_row("CONCRETE", 100.0, 500.0, "CY"),
    ])
    # ``df`` lacks PLANVIEW_ID → segmented mode treats every row as
    # structurally incomplete → FAIL.
    result = check_acce_ac7(
        df, params={ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    assert result.tolist() == [False]


# =============================================================================
# AC8: Cross-discipline quantity ratios (ACCE; DESCRIPTION + COMPONENT_SOURCE)
# =============================================================================

def _ac8_required_cols():
    return [
        "COMPONENT_SOURCE",
        "DESCRIPTION",
        "QTY_KEY_QTY",
        "QTY_OTHER_QTY",
        "QTY_KEY_UNITS",
        "QTY_OTHER_UNITS",
    ]


def _make_ac8_df(rows):
    """Build an ACCE-shaped denormalized DataFrame from a list of dicts.
    Missing keys default to None so the rule sees them as null.

    Note the project key is ``COMPONENT_SOURCE`` and the discipline is
    classified off ``DESCRIPTION`` + the split unit columns."""
    cols = _ac8_required_cols()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def _ac8_row(component, description, qty=None, uom=None, *, slot="key"):
    """One AC8 row: a ``COMPONENT_SOURCE`` project key, a ``DESCRIPTION``,
    and a single populated qty slot (KEY by default)."""
    row = {"COMPONENT_SOURCE": component, "DESCRIPTION": description}
    if slot == "other":
        row["QTY_OTHER_QTY"] = qty
        row["QTY_OTHER_UNITS"] = uom
    else:
        row["QTY_KEY_QTY"] = qty
        row["QTY_KEY_UNITS"] = uom
    return row


def _ac8_steel_concrete_population(
    n_normal: int = 12,
    normal_steel: float = 100.0,
    normal_concrete: float = 50.0,
    outlier_project: str = "PROJECT-OUTLIER",
    outlier_steel: float = 100.0,
    outlier_concrete: float = 5.0,
):
    """Build an AC8-shaped DataFrame containing two rows per project
    (one steel, one concrete) with ``n_normal`` projects clustered
    tightly around the same ratio plus one project whose ratio is far
    outside the mild IQR bound. Returns the DataFrame ready for
    ``check_acce_ac8``."""
    rows = []
    for i in range(n_normal):
        proj = f"PROJECT-{i:03d}"
        # Tight jitter keeps IQR > 0 without absorbing the outlier.
        jitter = 0.5 if i % 2 else -0.5
        rows.append(_ac8_row(proj, "STEEL", normal_steel + jitter, "T"))
        rows.append(_ac8_row(proj, "CONCRETE", normal_concrete - jitter, "YD3"))
    rows.append(_ac8_row(outlier_project, "STEEL", outlier_steel, "T"))
    rows.append(_ac8_row(outlier_project, "CONCRETE", outlier_concrete, "YD3"))
    return _make_ac8_df(rows), outlier_project


# ----- Catalog metadata ------------------------------------------------------

def test_acce_has_custom_rule_ac8_available():
    """ACCE catalog exposes AC8 as a non-blocking Statistical Outlier
    rule with the documented physical column mapping (DESCRIPTION +
    COMPONENT_SOURCE + split qty/unit slots, IQR-multiplier selectbox,
    and a project-type segmentation toggle)."""
    rules = get_available_custom_dqr_rules("ACCE")
    by_id = {r.id: r for r in rules}
    assert "AC8" in by_id
    rule = by_id["AC8"]
    assert rule.type == "Statistical Outlier"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Project Scope": "COMPONENT_SOURCE",
        "Item Description": "DESCRIPTION",
        "Key Quantity": "QTY_KEY_QTY",
        "Other Quantity": "QTY_OTHER_QTY",
        "Key Units": "QTY_KEY_UNITS",
        "Other Units": "QTY_OTHER_UNITS",
    }
    assert rule.reference is None
    # AC8 surfaces the IQR-multiplier selectbox and the
    # segment_by_project_type toggle (mirrors A8).
    select_keys = {opt.key for opt in (rule.select_options or ())}
    assert "threshold_iqr_multiplier" in select_keys
    option_keys = {opt.key for opt in (rule.options or ())}
    assert "segment_by_project_type" in option_keys


def test_acce_ac8_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ACCE_AC8_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ACCE") if r.id == "AC8"
    )
    assert rule.required_columns == ACCE_AC8_REQUIRED_COLUMNS


def test_acce_ac8_constants_are_documented_defaults():
    from src.custom_dqr_engine import (
        ACCE_AC8_EXTREME_IQR_MULTIPLIER,
        ACCE_AC8_MILD_IQR_MULTIPLIER,
        ACCE_AC8_MIN_POPULATION,
    )
    assert ACCE_AC8_MILD_IQR_MULTIPLIER == 1.5
    assert ACCE_AC8_EXTREME_IQR_MULTIPLIER == 3.0
    assert ACCE_AC8_MIN_POPULATION == 10


# ----- Discipline classifier -------------------------------------------------

def test_ac8_classifier_returns_correct_category_per_description_uom():
    """The classifier matches a DESCRIPTION value list paired with a
    unit in the category's UOM family. Units come from either slot;
    here KEY_UNITS carries the value, OTHER_UNITS is null."""
    from src.custom_dqr_engine import _classify_ac8_category_acce
    cases = [
        ("STEEL",                "T",     "STEEL_WEIGHT"),
        ("STEEL STRUCTURES",     "TONS",  "STEEL_WEIGHT"),
        ("CONCRETE",             "YD3",   "CONCRETE_VOLUME"),
        ("CONCRETE",             "CY",    "CONCRETE_VOLUME"),
        ("FOUNDATION ACCESSORIES", "M³",  "CONCRETE_VOLUME"),
        ("PIPING",               "FT",    "PIPE_LENGTH"),
        ("CS PIPE ERECTION",     "FEET",  "PIPE_LENGTH"),
        ("PIPING",               "M",     "PIPE_LENGTH"),
        ("ELECTRICAL",           "FT",    "CABLE_LENGTH"),
        ("CABLE TRAYS",          "M",     "CABLE_LENGTH"),
        ("INSTRUMENTATION",      "EACH",  "TRANSMITTER_COUNT"),
        ("FLOW INSTRUMENTS",     "ITEMS", "TRANSMITTER_COUNT"),
        ("CENTRIFUGAL PUMPS",    "EA",    "EQUIPMENT_COUNT"),
        ("S&T EXCHANGER",        "ITEM",  "EQUIPMENT_COUNT"),
    ]
    for desc, uom, expected in cases:
        got = _classify_ac8_category_acce(desc, uom, None)
        assert got == expected, f"({desc!r}, {uom!r}) → {got}, expected {expected}"


def test_ac8_classifier_reads_other_units_slot():
    """The eligible-unit gate accepts a match in either slot - a row
    whose KEY_UNITS is null but OTHER_UNITS is in the family still
    classifies."""
    from src.custom_dqr_engine import _classify_ac8_category_acce
    assert _classify_ac8_category_acce("STEEL", None, "TONS") == "STEEL_WEIGHT"


def test_ac8_classifier_equipment_accepts_comma_variant():
    """AC8's equipment list spells the turbo-expander compressor with a
    comma (``TURBO-EXPAND, COMPRESSOR``) per its SQL spec."""
    from src.custom_dqr_engine import _classify_ac8_category_acce
    assert _classify_ac8_category_acce(
        "TURBO-EXPAND, COMPRESSOR", "EACH", None
    ) == "EQUIPMENT_COUNT"


def test_ac8_classifier_rejects_off_family_uom_for_each_discipline():
    """Each DESCRIPTION requires a unit from its canonical family. A
    piping row with a count UOM is not eligible for any ratio."""
    from src.custom_dqr_engine import _classify_ac8_category_acce
    # DESCRIPTION matches but UOM family is wrong → None.
    assert _classify_ac8_category_acce("PIPING", "T", None) is None     # piping ≠ tons
    assert _classify_ac8_category_acce("PIPING", "EA", None) is None    # piping ≠ count
    assert _classify_ac8_category_acce("STEEL", "FT", None) is None     # steel ≠ length
    assert _classify_ac8_category_acce("CONCRETE", "EA", None) is None  # civil ≠ count
    assert _classify_ac8_category_acce(
        "CENTRIFUGAL PUMPS", "T", None
    ) is None                                                           # equipment ≠ weight
    assert _classify_ac8_category_acce(
        "INSTRUMENTATION", "FT", None
    ) is None                                                           # instrument ≠ length
    assert _classify_ac8_category_acce("ELECTRICAL", "EA", None) is None  # cable ≠ count


def test_ac8_classifier_returns_none_for_unknown_description():
    """The classifier is a closed allow-list - a DESCRIPTION outside
    every discipline list contributes to no ratio, whatever its UOM."""
    from src.custom_dqr_engine import _classify_ac8_category_acce
    assert _classify_ac8_category_acce("GENERAL WORKS", "EA", None) is None
    assert _classify_ac8_category_acce("SITE PREPARATION", "FT", None) is None
    assert _classify_ac8_category_acce("UNKNOWN", "T", None) is None


def test_ac8_classifier_returns_none_on_blank_or_null_inputs():
    from src.custom_dqr_engine import _classify_ac8_category_acce
    assert _classify_ac8_category_acce(None, "FT", None) is None
    assert _classify_ac8_category_acce("PIPING", None, None) is None
    assert _classify_ac8_category_acce("", "FT", None) is None
    assert _classify_ac8_category_acce("PIPING", "  ", "  ") is None


def test_ac8_volume_uom_set_differs_from_ac4():
    """AC8's volume set admits the bare ``YD`` spelling where AC4's
    admits ``YDS``; both reject the other's variant. Length now matches
    AC4's wider set (``METERS`` / ``LF`` accepted). Locks in the
    per-rule UOM split so a refactor doesn't quietly merge them."""
    from src.custom_dqr_engine import _classify_ac8_category_acce
    # AC8 volume: bare YD accepted, YDS (AC4's spelling) rejected.
    assert _classify_ac8_category_acce("CONCRETE", "YD", None) == "CONCRETE_VOLUME"
    assert _classify_ac8_category_acce("CONCRETE", "YDS", None) is None
    # AC8 length matches AC4's wider set: METERS / LF accepted.
    assert _classify_ac8_category_acce("PIPING", "METERS", None) == "PIPE_LENGTH"
    assert _classify_ac8_category_acce("ELECTRICAL", "LF", None) == "CABLE_LENGTH"


# ----- check_acce_ac8 - happy & NOT_APPLICABLE paths -------------------------

def test_acce_ac8_flags_outlier_project_in_well_populated_population():
    """Headline scenario: 12 projects clustered around steel/concrete
    ratio = 2.0 plus one outlier at ratio = 20.0. Every row of the
    outlier project must FAIL; every row of the normal projects must
    PASS."""
    from src.custom_dqr_engine import check_acce_ac8
    df, outlier_project = _ac8_steel_concrete_population(
        n_normal=12,
        normal_steel=100.0,
        normal_concrete=50.0,
        outlier_steel=100.0,
        outlier_concrete=5.0,
    )
    result = check_acce_ac8(df)
    is_outlier = df["COMPONENT_SOURCE"] == outlier_project
    assert (~result[is_outlier]).all()
    assert result[~is_outlier].all()


def test_acce_ac8_passes_every_row_when_population_below_min():
    """Fewer than ACCE_AC8_MIN_POPULATION projects → no ratio can flag, every row passes."""
    from src.custom_dqr_engine import ACCE_AC8_MIN_POPULATION, check_acce_ac8
    df, _ = _ac8_steel_concrete_population(
        n_normal=ACCE_AC8_MIN_POPULATION - 2,   # 8 normal + 1 outlier = 9
        outlier_concrete=5.0,
    )
    assert check_acce_ac8(df).all()


def test_acce_ac8_passes_when_population_iqr_is_zero():
    """If every project's ratio is the same, IQR = 0 and the rule
    short-circuits to PASS for that ratio."""
    from src.custom_dqr_engine import check_acce_ac8
    rows = []
    for i in range(15):
        proj = f"PROJECT-{i:03d}"
        rows.append(_ac8_row(proj, "STEEL", 100.0, "T"))
        rows.append(_ac8_row(proj, "CONCRETE", 50.0, "YD3"))
    df = _make_ac8_df(rows)
    assert check_acce_ac8(df).all()


def test_acce_ac8_passes_rows_with_blank_component_source():
    """A row whose COMPONENT_SOURCE is null/blank can't be assigned to a
    project, it always passes regardless of how its peer projects
    are doing."""
    from src.custom_dqr_engine import check_acce_ac8
    df, _ = _ac8_steel_concrete_population(outlier_concrete=5.0)
    extra = _make_ac8_df([
        _ac8_row(None, "STEEL", 50.0, "T"),
        _ac8_row("   ", "STEEL", 50.0, "T"),
    ])
    df = pd.concat([extra, df], ignore_index=True)
    result = check_acce_ac8(df)
    assert result.iloc[:2].tolist() == [True, True]


def test_acce_ac8_passes_when_quantity_non_positive():
    """Rows with zero / null / negative quantity in both slots are not
    eligible for aggregation. Their project's pass/fail is decided only
    by the eligible rows."""
    from src.custom_dqr_engine import check_acce_ac8
    df, outlier_project = _ac8_steel_concrete_population(outlier_concrete=5.0)
    extra = _make_ac8_df([
        _ac8_row("PROJECT-000", "CONCRETE", 0.0, "YD3"),
        _ac8_row("PROJECT-001", "CONCRETE", None, "YD3"),
        _ac8_row("PROJECT-002", "CONCRETE", -5.0, "YD3"),
    ])
    df = pd.concat([df, extra], ignore_index=True)
    result = check_acce_ac8(df)
    is_outlier = df["COMPONENT_SOURCE"] == outlier_project
    assert (~result[is_outlier]).all()
    assert result[~is_outlier].all()


def test_acce_ac8_unrecognised_classification_does_not_contribute():
    """A row whose DESCRIPTION / units are outside the allow-list falls
    through the classifier and contributes to no ratio, its project
    is judged only by the rows that *did* classify."""
    from src.custom_dqr_engine import check_acce_ac8
    df, outlier_project = _ac8_steel_concrete_population(outlier_concrete=5.0)
    extra = _make_ac8_df([
        _ac8_row(outlier_project, "GENERAL WORKS", 1_000_000.0, "Widgets"),
    ])
    df = pd.concat([df, extra], ignore_index=True)
    result = check_acce_ac8(df)
    assert (~result[df["COMPONENT_SOURCE"] == outlier_project]).all()


def test_acce_ac8_population_is_per_ratio_not_global():
    """Each ratio defines its own population. A pipe/equipment
    population that's too small must not block flagging on a
    well-populated steel/concrete population."""
    from src.custom_dqr_engine import check_acce_ac8
    base, outlier_project = _ac8_steel_concrete_population(
        n_normal=12, outlier_concrete=5.0,
    )
    # Two extra rows on a single project - pipe/equipment population
    # of 1 is far below the min-population floor; the rule must
    # ignore that ratio.
    extra = _make_ac8_df([
        _ac8_row("PROJECT-000", "PIPING", 1000.0, "FT"),
        _ac8_row("PROJECT-000", "CENTRIFUGAL PUMPS", 5.0, "EA"),
    ])
    df = pd.concat([base, extra], ignore_index=True)
    result = check_acce_ac8(df)
    # Steel/concrete outlier still flagged.
    assert (~result[df["COMPONENT_SOURCE"] == outlier_project]).all()


# ----- AC8 - IQR multiplier param --------------------------------------------

def test_acce_ac8_iqr_multiplier_param_widens_pass_band():
    """A project that fails at 1.5×IQR may pass at 3.0×IQR, the
    threshold param controls the per-ratio PASS band width."""
    from src.custom_dqr_engine import (
        ACCE_AC8_THRESHOLD_PARAM,
        check_acce_ac8,
    )
    df, outlier_project = _ac8_steel_concrete_population(
        n_normal=12, outlier_concrete=5.0,
    )
    result_default = check_acce_ac8(df)
    assert (~result_default[df["COMPONENT_SOURCE"] == outlier_project]).all()
    # Wide threshold - engineered so the outlier sits inside the
    # band. Baseline jitter is ±0.5 on a 50-yd³ concrete denominator
    # → steel/concrete ratios vary in [99.5/50.5, 100.5/49.5] ≈
    # [1.97, 2.03], IQR ≈ 0.03; outlier ratio = 20.0. To widen the
    # band to include 20.0 we'd need a *very* large multiplier, far
    # beyond the documented 3.0×. So at 3.0× the outlier still fails
    # - pick a generous multiplier to assert the wider-band branch.
    result_wide = check_acce_ac8(
        df, params={ACCE_AC8_THRESHOLD_PARAM: 1000.0}
    )
    # 1000× makes the band [Q1 - 1000*IQR, Q3 + 1000*IQR] which
    # comfortably contains 20.0 → outlier passes.
    assert result_wide.all()


def test_acce_ac8_stale_threshold_param_falls_back_to_default():
    """A non-numeric / out-of-range threshold value must fall back to
    ``ACCE_AC8_MILD_IQR_MULTIPLIER`` (1.5×) via ``_coerce_threshold``."""
    from src.custom_dqr_engine import (
        ACCE_AC8_THRESHOLD_PARAM,
        check_acce_ac8,
    )
    df, outlier_project = _ac8_steel_concrete_population(outlier_concrete=5.0)
    # Stale param → fallback to 1.5× → outlier still fails.
    result = check_acce_ac8(
        df, params={ACCE_AC8_THRESHOLD_PARAM: "garbage"}
    )
    assert (~result[df["COMPONENT_SOURCE"] == outlier_project]).all()


# ----- check_acce_ac8 - schema-level / structural failures -------------------

def test_acce_ac8_fails_for_all_rows_when_required_column_missing():
    from src.custom_dqr_engine import check_acce_ac8
    base = pd.DataFrame({
        "COMPONENT_SOURCE": ["P1"] * 3,
        "DESCRIPTION": ["STEEL"] * 3,
        "QTY_KEY_QTY": [100.0, 100.0, 100.0],
        "QTY_OTHER_QTY": [None, None, None],
        "QTY_KEY_UNITS": ["T"] * 3,
        "QTY_OTHER_UNITS": [None, None, None],
    })
    for missing in _ac8_required_cols():
        df = base.drop(columns=missing)
        assert check_acce_ac8(df).tolist() == [False, False, False], (
            f"missing {missing} should fail every row"
        )


def test_acce_ac8_empty_dataframe_returns_empty_pass_series():
    from src.custom_dqr_engine import check_acce_ac8
    df = pd.DataFrame({c: [] for c in _ac8_required_cols()})
    result = check_acce_ac8(df)
    assert result.tolist() == []
    assert result.dtype == bool


def test_acce_ac8_passes_when_no_eligible_rows_exist():
    """All rows ineligible (zero qty / blank inputs) → no aggregation,
    no ratio computed, every row passes."""
    from src.custom_dqr_engine import check_acce_ac8
    df = _make_ac8_df([
        _ac8_row("P1", "STEEL", 0.0, "T"),
        _ac8_row("P2", None, 100.0, "T"),
    ])
    assert check_acce_ac8(df).tolist() == [True, True]


def test_acce_ac8_handles_object_dtyped_numeric_inputs():
    """Mixed string / numeric inputs must coerce cleanly - non-numeric
    quantities become NaN and are treated as ineligible."""
    from src.custom_dqr_engine import check_acce_ac8
    df = _make_ac8_df([
        _ac8_row("P1", "STEEL", "100", "T"),
        _ac8_row("P1", "STEEL", "abc", "T"),
    ])
    # Population too small → all PASS.
    assert check_acce_ac8(df).all()


def test_evaluate_custom_rules_dispatches_to_ac8():
    """End-to-end: dispatcher routes an AC8 assignment through
    check_acce_ac8 for the ACCE data product."""
    df, outlier_project = _ac8_steel_concrete_population(outlier_concrete=5.0)
    assignments = [CustomDQRAssignment(rule_id="AC8", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ACCE")
    assert "AC8" in out.columns
    is_outlier = df["COMPONENT_SOURCE"] == outlier_project
    assert (~out["AC8"][is_outlier]).all()
    assert out["AC8"][~is_outlier].all()
    assert not_evaluated == {}


def test_acce_ac8_does_not_add_reference_dataset_to_prefetch():
    """AC8 declares no static reference (the Planview lookup only
    fires when the segment-by-project-type toggle is on), so the
    ACCE prefetch list is unchanged. AC2 already brings in
    ``VWS_GP_STANDARD_SHARE`` for ACCE, so the segmented branch has
    a cached reference when it runs."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ACCE"])) == {
        "ACCE_COA_MASTER",
        "VWS_GP_STANDARD_SHARE",
    }


# ----- AC8 - project-type segmentation (toggle: segment_by_project_type) -----

def _ac8_required_cols_with_planview():
    return _ac8_required_cols() + ["PLANVIEW_ID"]


def _make_ac8_segmented_df(rows):
    """Build an ACCE-shaped DataFrame that also carries ``PLANVIEW_ID``
    so the AC8 segment-by-project-type lookup can resolve each project
    to a segment."""
    cols = _ac8_required_cols_with_planview()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def _ac8_segment_reference(rows):
    """Build a Planview reference DataFrame with the segmentation
    columns AC8 reads when the segment-by-project-type toggle is on."""
    return pd.DataFrame(
        rows, columns=["PROJECT_ID", "E05_DEPARTMENT", "BUSINESS"]
    )


def _ac8_segmented_steel_concrete_rows(
    project: str,
    planview_id: str,
    steel: float,
    concrete: float,
):
    """Return two rows (one steel, one concrete) for the same project
    so AC8 can compute the steel/concrete ratio."""
    return [
        {"COMPONENT_SOURCE": project, "PLANVIEW_ID": planview_id,
         "DESCRIPTION": "STEEL", "QTY_KEY_QTY": steel, "QTY_KEY_UNITS": "T"},
        {"COMPONENT_SOURCE": project, "PLANVIEW_ID": planview_id,
         "DESCRIPTION": "CONCRETE", "QTY_KEY_QTY": concrete,
         "QTY_KEY_UNITS": "YD3"},
    ]


def test_acce_ac8_segment_param_constants_match_catalog():
    """The segmentation toggle exposed on the AC8 catalog rule card
    carries the same key the engine reads from ``params``, and the
    rule declares ``PLANVIEW_ID`` as a required-when-enabled column."""
    from src.custom_dqr_engine import ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM
    rule = next(
        r for r in get_available_custom_dqr_rules("ACCE") if r.id == "AC8"
    )
    by_key = {opt.key: opt for opt in (rule.options or ())}
    assert ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM in by_key
    opt = by_key[ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM]
    assert "PLANVIEW_ID" in opt.required_columns_when_enabled.values()


def test_acce_ac8_segmented_isolates_outliers_per_segment(monkeypatch):
    """With segmentation on, the per-ratio IQR is recomputed within
    each (E05_DEPARTMENT, BUSINESS) segment. A project that is an
    outlier *within its own segment* fails even when its ratio would
    sit inside the dataset-wide band."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_acce_ac8,
    )

    rows = []
    # Segment A (BROWNFIELD/UPSTREAM): 12 projects with steel/concrete
    # ratio ≈ 2.0 plus an in-segment outlier with ratio ≈ 20.0.
    for i in range(12):
        proj = f"P-A-{i:03d}"
        jitter = 0.5 if i % 2 else -0.5
        rows.extend(_ac8_segmented_steel_concrete_rows(
            project=proj, planview_id=proj,
            steel=100.0 + jitter, concrete=50.0 - jitter,
        ))
    rows.extend(_ac8_segmented_steel_concrete_rows(
        project="P-A-OUT", planview_id="P-A-OUT",
        steel=100.0, concrete=5.0,                 # ratio = 20 - outlier
    ))
    # Segment B (GREENFIELD/DOWNSTREAM): 12 projects with their own
    # tight ratio centre. The within-segment IQR keeps them isolated.
    for i in range(12):
        proj = f"P-B-{i:03d}"
        jitter = 0.5 if i % 2 else -0.5
        rows.extend(_ac8_segmented_steel_concrete_rows(
            project=proj, planview_id=proj,
            steel=200.0 + jitter, concrete=50.0 - jitter,
        ))

    ref_rows = (
        [(f"P-A-{i:03d}", "BROWNFIELD", "UPSTREAM") for i in range(12)]
        + [("P-A-OUT", "BROWNFIELD", "UPSTREAM")]
        + [(f"P-B-{i:03d}", "GREENFIELD", "DOWNSTREAM") for i in range(12)]
    )
    ref_df = _ac8_segment_reference(ref_rows)
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)

    df = _make_ac8_segmented_df(rows)
    result = check_acce_ac8(
        df, params={ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # Every row of P-A-OUT must FAIL; every other row must PASS.
    is_outlier = df["COMPONENT_SOURCE"] == "P-A-OUT"
    assert (~result[is_outlier]).all()
    assert result[~is_outlier].all()


def test_acce_ac8_segmented_passes_when_segment_population_below_minimum(
    monkeypatch,
):
    """A per-segment population below ``ACCE_AC8_MIN_POPULATION`` is
    NOT_APPLICABLE → every project in that segment passes, even when
    one of them would obviously fail against the global IQR."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ACCE_AC8_MIN_POPULATION,
        ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_acce_ac8,
    )

    rows = []
    # Well-populated segment A - uniform ratio.
    for i in range(12):
        proj = f"P-A-{i:03d}"
        jitter = 0.5 if i % 2 else -0.5
        rows.extend(_ac8_segmented_steel_concrete_rows(
            project=proj, planview_id=proj,
            steel=100.0 + jitter, concrete=50.0 - jitter,
        ))
    # Tiny segment B (under the floor) including an obvious global
    # outlier - must still PASS in segmented mode.
    for i in range(ACCE_AC8_MIN_POPULATION - 2):
        proj = f"P-B-{i:03d}"
        rows.extend(_ac8_segmented_steel_concrete_rows(
            project=proj, planview_id=proj,
            steel=100.0, concrete=50.0,
        ))
    rows.extend(_ac8_segmented_steel_concrete_rows(
        project="P-B-OUT", planview_id="P-B-OUT",
        steel=100.0, concrete=5.0,
    ))

    ref_rows = (
        [(f"P-A-{i:03d}", "BROWNFIELD", "UPSTREAM") for i in range(12)]
        + [
            (f"P-B-{i:03d}", "GREENFIELD", "LNG")
            for i in range(ACCE_AC8_MIN_POPULATION - 2)
        ]
        + [("P-B-OUT", "GREENFIELD", "LNG")]
    )
    ref_df = _ac8_segment_reference(ref_rows)
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)

    df = _make_ac8_segmented_df(rows)
    result = check_acce_ac8(
        df, params={ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    assert result.all()


def test_acce_ac8_segmented_passes_projects_without_resolved_segment(
    monkeypatch,
):
    """Projects whose PLANVIEW_ID does not match the reference, or
    whose matched segment has a null/blank ``E05_DEPARTMENT`` /
    ``BUSINESS``, are NOT_APPLICABLE → PASS even when their ratio
    would clearly fail against the dataset-wide IQR."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_acce_ac8,
    )

    rows = []
    for i in range(12):
        proj = f"P-A-{i:03d}"
        jitter = 0.5 if i % 2 else -0.5
        rows.extend(_ac8_segmented_steel_concrete_rows(
            project=proj, planview_id=proj,
            steel=100.0 + jitter, concrete=50.0 - jitter,
        ))
    # Outlier whose PLANVIEW_ID has no match in the reference.
    rows.extend(_ac8_segmented_steel_concrete_rows(
        project="P-ORPHAN", planview_id="P-ORPHAN",
        steel=100.0, concrete=5.0,
    ))
    # Outlier whose segment row carries a null E05_DEPARTMENT.
    rows.extend(_ac8_segmented_steel_concrete_rows(
        project="P-NULL", planview_id="P-NULL",
        steel=100.0, concrete=5.0,
    ))

    ref_rows = (
        [(f"P-A-{i:03d}", "BROWNFIELD", "UPSTREAM") for i in range(12)]
        + [("P-NULL", None, "UPSTREAM")]
    )
    ref_df = _ac8_segment_reference(ref_rows)
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)

    df = _make_ac8_segmented_df(rows)
    result = check_acce_ac8(
        df, params={ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # Every row passes, the unresolved outliers are NOT_APPLICABLE.
    assert result.all()


def test_acce_ac8_segmented_raises_not_evaluated_when_reference_unavailable(
    monkeypatch,
):
    """With segmentation on, an absent ``VWS_GP_STANDARD_SHARE``
    reference must raise :class:`CustomRuleNotEvaluated` - never
    silently fall back to the global IQR baseline."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM,
        CustomRuleNotEvaluated,
        check_acce_ac8,
    )
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset_error", lambda name: "network down"
    )
    # Build a minimal populated DataFrame so the segmented branch
    # reaches the reference lookup before the eligibility short-circuit.
    rows = []
    for i in range(12):
        proj = f"P-A-{i:03d}"
        rows.extend(_ac8_segmented_steel_concrete_rows(
            project=proj, planview_id=proj,
            steel=100.0, concrete=50.0,
        ))
    df = _make_ac8_segmented_df(rows)
    with pytest.raises(CustomRuleNotEvaluated):
        check_acce_ac8(
            df, params={ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
        )


def test_acce_ac8_unsegmented_does_not_touch_reference(monkeypatch):
    """Default (segmentation off) must not consult the reference
    dataset at all, the legacy global-IQR path keeps its standalone
    behaviour and never blows up when the reference is missing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_acce_ac8

    def _boom(_name):
        raise AssertionError(
            "Unsegmented AC8 must not call get_reference_dataset"
        )

    monkeypatch.setattr(ref_mod, "get_reference_dataset", _boom)
    rows = []
    for i in range(12):
        proj = f"P-A-{i:03d}"
        rows.extend(_ac8_segmented_steel_concrete_rows(
            project=proj, planview_id=proj,
            steel=100.0, concrete=50.0,
        ))
    df = _make_ac8_segmented_df(rows)
    # Uniform ratios → no outliers → all PASS regardless of toggle.
    assert check_acce_ac8(df).all()


def test_acce_ac8_segmented_fails_when_planview_id_column_missing(monkeypatch):
    """With segmentation on, PLANVIEW_ID becomes a structurally
    required column, the rule fails every row when it is missing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_acce_ac8,
    )
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: _ac8_segment_reference([])
    )
    df = _make_ac8_df([
        _ac8_row("P1", "STEEL", 100.0, "T"),
    ])
    # ``df`` lacks PLANVIEW_ID → segmented mode treats every row as
    # structurally incomplete → FAIL.
    result = check_acce_ac8(
        df, params={ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    assert result.tolist() == [False]


# =============================================================================
# A2: Location + Estimate Date Present (ADR; mirrors EPT E2 with COST_UPDATE)
# =============================================================================

def test_adr_has_custom_rule_a2_available():
    """ADR catalog exposes A2 with the documented Planview reference metadata.
    Mirrors EPT E2 but swaps CENTROID_DATE for COST_UPDATE."""
    rules = get_available_custom_dqr_rules("ADR")
    by_id = {r.id: r for r in rules}
    assert "A2" in by_id
    rule = by_id["A2"]
    assert rule.type == "Completeness & Validity"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Estimate Basis Date": "COST_UPDATE",
        "Project Key": "PLANVIEW_ID",
    }
    assert rule.reference is not None
    assert rule.reference["reference_dataset"] == "VWS_GP_STANDARD_SHARE"
    assert rule.reference["source_column"] == "PLANVIEW_ID"
    assert rule.reference["reference_column"] == "PROJECT_ID"
    assert rule.reference["lookup_column"] == "COUNTRY"


@pytest.fixture
def _a2_reference_with_countries(monkeypatch):
    """Pin the Planview reference to a known PROJECT_ID → COUNTRY mapping so
    A2 row-level assertions don't depend on the mock's RNG."""
    import src.reference_data as ref_mod
    ref_df = pd.DataFrame({
        "PROJECT_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "COUNTRY": ["BR", "US", "UK"],
    })
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    return ref_df


def test_adr_a2_passes_when_cost_update_and_country_present(
    _a2_reference_with_countries,
):
    """A2 passes when COST_UPDATE is filled AND PLANVIEW_ID joins to a
    project whose COUNTRY is populated."""
    from src.custom_dqr_engine import check_adr_a2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002"],
        "COST_UPDATE": ["2Q2019", "4Q2015"],
    })
    assert check_adr_a2(df).tolist() == [True, True]


def test_adr_a2_fails_when_cost_update_null(_a2_reference_with_countries):
    from src.custom_dqr_engine import check_adr_a2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "COST_UPDATE": ["2Q2019", None, "3Q2022"],
    })
    assert check_adr_a2(df).tolist() == [True, False, True]


def test_adr_a2_fails_when_cost_update_blank_string(_a2_reference_with_countries):
    """Blank/whitespace strings count as missing - A2 piggy-backs on
    `_is_filled`, mirroring the shelf Completeness semantics."""
    from src.custom_dqr_engine import check_adr_a2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "COST_UPDATE": ["2Q2019", "", "  "],
    })
    assert check_adr_a2(df).tolist() == [True, False, False]


def test_adr_a2_fails_when_cost_update_filled_but_invalid_format(
    _a2_reference_with_countries,
):
    """Validity: a populated COST_UPDATE that does not match the fiscal
    quarter-year shape [1-4]Q<YYYY> fails A2 even though it satisfies
    Completeness."""
    from src.custom_dqr_engine import check_adr_a2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003", "PV-00001"],
        # valid quarter-year / non-period text / bad quarter / wrong shape
        "COST_UPDATE": ["2Q2019", "N/A", "5Q2019", "2019"],
    })
    assert check_adr_a2(df).tolist() == [True, False, False, False]


def test_adr_a2_validity_accepts_lowercase_q(_a2_reference_with_countries):
    """The quarter separator is matched case-insensitively, so '2q2019'
    is accepted alongside '2Q2019'."""
    from src.custom_dqr_engine import check_adr_a2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002"],
        "COST_UPDATE": ["2q2019", "4Q2015"],
    })
    assert check_adr_a2(df).tolist() == [True, True]


def test_adr_a2_fails_when_planview_id_does_not_match_reference(monkeypatch):
    """An unmatched PLANVIEW_ID is treated as missing COUNTRY (per spec)."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_adr_a2
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({
            "PROJECT_ID": ["PV-00001", "PV-00002"],
            "COUNTRY": ["BR", "US"],
        }),
    )
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-ORPHAN", "PV-00002"],
        "COST_UPDATE": ["2Q2019"] * 3,
    })
    assert check_adr_a2(df).tolist() == [True, False, True]


def test_adr_a2_fails_when_country_null_after_join(monkeypatch):
    """A matched PLANVIEW_ID whose project has a null COUNTRY fails A2."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_adr_a2
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({
            "PROJECT_ID": ["PV-00001", "PV-00002", "PV-00003"],
            "COUNTRY": ["BR", None, "  "],
        }),
    )
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003"],
        "COST_UPDATE": ["2Q2019"] * 3,
    })
    assert check_adr_a2(df).tolist() == [True, False, False]


def test_adr_a2_fails_when_planview_id_is_null(_a2_reference_with_countries):
    """A null PLANVIEW_ID can't be looked up - COUNTRY is treated as missing."""
    from src.custom_dqr_engine import check_adr_a2
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", None, "PV-00002"],
        "COST_UPDATE": ["2Q2019"] * 3,
    })
    assert check_adr_a2(df).tolist() == [True, False, True]


def test_adr_a2_fails_for_all_rows_when_cost_update_column_missing():
    from src.custom_dqr_engine import check_adr_a2
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "PV-00002"]})
    assert check_adr_a2(df).tolist() == [False, False]


def test_adr_a2_fails_for_all_rows_when_planview_id_column_missing():
    from src.custom_dqr_engine import check_adr_a2
    df = pd.DataFrame({"COST_UPDATE": ["2Q2019", "4Q2015"]})
    assert check_adr_a2(df).tolist() == [False, False]


def test_adr_a2_raises_not_evaluated_when_reference_unavailable(monkeypatch):
    """If the Planview reference loader returns None, A2 must raise
    CustomRuleNotEvaluated rather than silently passing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import CustomRuleNotEvaluated, check_adr_a2
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001"],
        "COST_UPDATE": ["2Q2019"],
    })
    try:
        check_adr_a2(df)
        raised = False
    except CustomRuleNotEvaluated:
        raised = True
    assert raised


def test_adr_a2_fails_for_all_rows_when_reference_missing_country_column(monkeypatch):
    """If the reference dataset lacks COUNTRY, the join cannot validate
    location, every row fails (rule does not silently pass)."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_adr_a2
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({"PROJECT_ID": ["PV-00001"]}),
    )
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001"],
        "COST_UPDATE": ["2Q2019"],
    })
    assert check_adr_a2(df).tolist() == [False]


def test_evaluate_custom_rules_dispatches_to_a2(_a2_reference_with_countries):
    """End-to-end: dispatcher routes an A2 assignment through check_adr_a2
    against a known reference dataset for the ADR data product."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", "PV-00002"],
        "COST_UPDATE": ["2Q2019", "4Q2015"],
    })
    assignments = [CustomDQRAssignment(rule_id="A2", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ADR")
    assert "A2" in out.columns
    assert out["A2"].tolist() == [True, True]
    assert not_evaluated == {}


def test_required_reference_datasets_for_adr_includes_planview_share():
    """A2 makes ADR depend on VWS_GP_STANDARD_SHARE, the same reference
    used by EPT E2 / E7, and A1 adds ACCE_COA_MASTER. Step 2 must
    prefetch both for ADR."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ADR"])) == {
        "VWS_GP_STANDARD_SHARE",
        "ACCE_COA_MASTER",
    }


# =============================================================================
# A3: Statistical WBC-to-ISO mapping ratio (ADR; mirrors EPT E3)
# =============================================================================

def _a3_required_cols():
    return [
        "PLANVIEW_ID",
        "COMPLETE_WBC",
        "COST_TOTAL_HOURS",
        "COST_TOTAL_COST",
    ]


def _make_a3_df(rows):
    """Build an ADR-shaped denormalized DataFrame from a list of dicts.
    Missing keys default to None so the rule sees them as null."""
    cols = _a3_required_cols()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


@pytest.fixture
def _a3_coa_master_with_population(monkeypatch):
    """Pin the COA master to a known mapping so A3 row-level assertions
    don't depend on the mock's RNG. Provides 11 distinct ICARUS_COAs
    mapping to 10 distinct (ISO_COR, SAB) buckets - just enough to
    cross ``ADR_A3_MIN_MAPPING_POPULATION`` (10) and let the P90 be
    computed."""
    import src.reference_data as ref_mod
    rows = [
        ("311", "C1.6",     "S3.2.2"),
        ("312", "C1.7",     "S3.2.3"),
        ("313", "C2.12.1",  "S3.2.2"),    # over-aggregating bucket below
        ("314", "C2.13",    "S3.4"),
        ("317", "C3.2",     "S2.5"),
        ("318", "C3.3",     "S2.6"),
        ("321", "C4.2",     "S4.1"),
        ("323", "C5.1",     "S5.1"),
        ("324", "C5.2",     "S5.2"),
        ("325", "C5.3",     "S5.3"),
        ("326", "C6.1",     "S6.1"),
    ]
    ref_df = pd.DataFrame(rows, columns=["ICARUS_COA", "ISO_COR", "SAB"])
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    return ref_df


def _a3_baseline_population(
    n_buckets: int = 10,
    rows_per_bucket: int = 1,
    hours: float = 100.0,
    cost: float = 50.0,
):
    """Build A3 rows for each of the 10 baseline (ISO_COR, SAB) buckets
    used by the ``_a3_coa_master_with_population`` fixture. Each row
    has a unique COMPLETE_WBC, so the per-bucket
    ``COUNT(DISTINCT COMPLETE_WBC)`` ratio defaults to ``rows_per_bucket``.
    Excludes the 313 bucket (the test layers an outlier on top of it)."""
    baseline_coas = [
        "311", "312", "314", "317", "318",
        "321", "323", "324", "325", "326",
    ][:n_buckets]
    rows = []
    for coa in baseline_coas:
        for sub in range(rows_per_bucket):
            rows.append({
                "PLANVIEW_ID": f"PV-{coa}",
                "COMPLETE_WBC": f"{coa}.{sub}.10.10",
                "COST_TOTAL_HOURS": hours,
                "COST_TOTAL_COST": cost,
            })
    return rows


# ----- Catalog metadata ------------------------------------------------------

def test_adr_has_custom_rule_a3_available():
    """ADR catalog exposes A3 as a non-blocking Statistical Outlier
    rule with the COA-master reference linkage."""
    rules = get_available_custom_dqr_rules("ADR")
    by_id = {r.id: r for r in rules}
    assert "A3" in by_id
    rule = by_id["A3"]
    assert rule.type == "Statistical Outlier"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Project Key": "PLANVIEW_ID",
        "Complete WBC": "COMPLETE_WBC",
        "Total Hours": "COST_TOTAL_HOURS",
        "Total Cost": "COST_TOTAL_COST",
    }
    assert rule.reference is not None
    assert rule.reference["reference_dataset"] == "ACCE_COA_MASTER"
    assert rule.reference["source_column"] == "COMPLETE_WBC"
    assert rule.reference["reference_column"] == "ICARUS_COA"


def test_adr_a3_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ADR_A3_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ADR") if r.id == "A3"
    )
    assert rule.required_columns == ADR_A3_REQUIRED_COLUMNS


def test_adr_a3_constants_are_documented_defaults():
    from src.custom_dqr_engine import (
        ADR_A3_MATERIALITY_USD,
        ADR_A3_MIN_MAPPING_POPULATION,
        ADR_A3_PERCENTILE,
    )
    assert ADR_A3_PERCENTILE == 0.90
    assert ADR_A3_MATERIALITY_USD == 100_000.0
    assert ADR_A3_MIN_MAPPING_POPULATION == 10


# ----- check_adr_a3 - happy & FAIL paths -------------------------------------

def test_adr_a3_passes_when_every_bucket_below_p90(_a3_coa_master_with_population):
    """All 10 baseline buckets have ratio = 1 (one distinct WBC each).
    P90 = 1, no bucket strictly exceeds the threshold → every row PASS."""
    from src.custom_dqr_engine import check_adr_a3
    df = _make_a3_df(_a3_baseline_population(rows_per_bucket=1))
    assert check_adr_a3(df).all()


def test_adr_a3_flags_over_aggregating_bucket(_a3_coa_master_with_population):
    """The 313 bucket (C2.12.1, S3.2.2) carries 30 distinct WBCs while
    every other bucket has just 1 → 313's ratio is far above the P90.
    Every row whose ROW resolves to (C2.12.1, S3.2.2) must FAIL; every
    baseline row must PASS."""
    from src.custom_dqr_engine import check_adr_a3
    rows = _a3_baseline_population(rows_per_bucket=1)
    # Outlier bucket: 30 distinct WBCs, all resolving via 313.
    for sub in range(30):
        rows.append({
            "PLANVIEW_ID": "PV-OUTLIER",
            "COMPLETE_WBC": f"313.{sub}.10.10",
            "COST_TOTAL_HOURS": 1_000.0,
            "COST_TOTAL_COST": 500_000.0,
        })
    df = _make_a3_df(rows)
    result = check_adr_a3(df)
    is_outlier = df["COMPLETE_WBC"].fillna("").str.startswith("313.")
    assert (~result[is_outlier]).all()
    assert result[~is_outlier].all()


def test_adr_a3_does_not_fail_immaterial_bucket(_a3_coa_master_with_population):
    """An over-aggregating bucket whose hours = 0 AND cost <
    ADR_A3_MATERIALITY_USD must PASS, the materiality filter
    suppresses planning / structural-only mappings."""
    from src.custom_dqr_engine import check_adr_a3
    rows = _a3_baseline_population(rows_per_bucket=1)
    # 30 distinct WBCs through 313, but with zero hours and trivial cost.
    for sub in range(30):
        rows.append({
            "PLANVIEW_ID": "PV-IMMATERIAL",
            "COMPLETE_WBC": f"313.{sub}.10.10",
            "COST_TOTAL_HOURS": 0.0,
            "COST_TOTAL_COST": 100.0,           # well below 100k threshold
        })
    df = _make_a3_df(rows)
    assert check_adr_a3(df).all()


def test_adr_a3_passes_when_population_below_min_threshold(monkeypatch):
    """If fewer than ``ADR_A3_MIN_MAPPING_POPULATION`` distinct ISO
    mappings exist, the P90 cannot be derived, every row passes."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_adr_a3
    # Only 3 valid mappings - far below the min population threshold.
    ref_df = pd.DataFrame({
        "ICARUS_COA": ["311", "312", "313"],
        "ISO_COR": ["C1.6", "C1.7", "C2.12.1"],
        "SAB": ["S3.2.2", "S3.2.3", "S3.2.2"],
    })
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    rows = []
    # Simulate an over-aggregating 313 bucket that *would* fail if there
    # were enough peer mappings, but with population = 2 (since 313 and
    # 311/312 share ISO buckets), the rule short-circuits to PASS.
    for sub in range(20):
        rows.append({
            "PLANVIEW_ID": "PV-1",
            "COMPLETE_WBC": f"313.{sub}.10.10",
            "COST_TOTAL_HOURS": 1_000.0,
            "COST_TOTAL_COST": 500_000.0,
        })
    rows.append({
        "PLANVIEW_ID": "PV-2",
        "COMPLETE_WBC": "311.0.10.10",
        "COST_TOTAL_HOURS": 100.0,
        "COST_TOTAL_COST": 50.0,
    })
    rows.append({
        "PLANVIEW_ID": "PV-3",
        "COMPLETE_WBC": "312.0.10.10",
        "COST_TOTAL_HOURS": 100.0,
        "COST_TOTAL_COST": 50.0,
    })
    df = _make_a3_df(rows)
    assert check_adr_a3(df).all()


def test_adr_a3_passes_when_wbc_does_not_resolve(_a3_coa_master_with_population):
    """Rows whose WBC is missing or whose COA group has no master entry
    are NOT_APPLICABLE - A3 must PASS them (A1 covers the gap)."""
    from src.custom_dqr_engine import check_adr_a3
    rows = _a3_baseline_population(rows_per_bucket=1)
    # NOT_APPLICABLE rows mixed in alongside an ordinary baseline.
    rows.extend([
        {"PLANVIEW_ID": "PV-X", "COMPLETE_WBC": None,
         "COST_TOTAL_HOURS": 100.0, "COST_TOTAL_COST": 0.0},
        {"PLANVIEW_ID": "PV-X", "COMPLETE_WBC": "",
         "COST_TOTAL_HOURS": 100.0, "COST_TOTAL_COST": 0.0},
        {"PLANVIEW_ID": "PV-X", "COMPLETE_WBC": "999.0.0.0",   # orphan COA
         "COST_TOTAL_HOURS": 100.0, "COST_TOTAL_COST": 0.0},
    ])
    df = _make_a3_df(rows)
    result = check_adr_a3(df)
    # Last 3 rows → NOT_APPLICABLE → PASS regardless.
    assert result.iloc[-3:].tolist() == [True, True, True]


def test_adr_a3_passes_rows_whose_iso_or_sab_is_invalid(monkeypatch):
    """If the COA master row carries ERROR / null in ISO_COR or SAB,
    the row's mapping is invalid → A3 NOT_APPLICABLE → PASS."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_adr_a3
    ref_df = pd.DataFrame({
        "ICARUS_COA": ["315", "316"],
        "ISO_COR":    ["ERROR: #N/A", "C3.1"],
        "SAB":        ["S2.1",        "ERROR: #N/A"],
    })
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: ref_df)
    df = _make_a3_df([
        {"PLANVIEW_ID": "PV-1", "COMPLETE_WBC": "315.0.0.0",
         "COST_TOTAL_HOURS": 1_000.0, "COST_TOTAL_COST": 500_000.0},
        {"PLANVIEW_ID": "PV-2", "COMPLETE_WBC": "316.0.0.0",
         "COST_TOTAL_HOURS": 1_000.0, "COST_TOTAL_COST": 500_000.0},
    ])
    assert check_adr_a3(df).tolist() == [True, True]


def test_adr_a3_uses_cost_materiality_when_hours_are_zero(
    _a3_coa_master_with_population,
):
    """If a bucket's hours sum is zero but its cost sum >= materiality
    threshold, it's still material → the bucket can FAIL when its
    ratio exceeds the P90."""
    from src.custom_dqr_engine import check_adr_a3
    rows = _a3_baseline_population(rows_per_bucket=1)
    for sub in range(30):
        rows.append({
            "PLANVIEW_ID": "PV-COST-MATERIAL",
            "COMPLETE_WBC": f"313.{sub}.10.10",
            "COST_TOTAL_HOURS": 0.0,
            "COST_TOTAL_COST": 50_000.0,    # SUM = 30 × 50k = 1.5M ≥ 100k
        })
    df = _make_a3_df(rows)
    result = check_adr_a3(df)
    is_outlier = df["COMPLETE_WBC"].fillna("").str.startswith("313.")
    assert (~result[is_outlier]).all()
    assert result[~is_outlier].all()


# ----- check_adr_a3 - schema-level / structural failures ---------------------

def test_adr_a3_fails_for_all_rows_when_required_column_missing(
    _a3_coa_master_with_population,
):
    """Schema-level structural incompleteness fails every row."""
    from src.custom_dqr_engine import check_adr_a3
    base = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1"],
        "COMPLETE_WBC": ["311.0.0.0"],
        "COST_TOTAL_HOURS": [100.0],
        "COST_TOTAL_COST": [50.0],
    })
    for missing in _a3_required_cols():
        df = base.drop(columns=missing)
        assert check_adr_a3(df).tolist() == [False], (
            f"missing {missing} should fail every row"
        )


def test_adr_a3_empty_dataframe_returns_empty_pass_series():
    from src.custom_dqr_engine import check_adr_a3
    df = pd.DataFrame({c: [] for c in _a3_required_cols()})
    result = check_adr_a3(df)
    assert result.tolist() == []
    assert result.dtype == bool


def test_adr_a3_raises_not_evaluated_when_reference_unavailable(monkeypatch):
    """If the COA master loader returns None, A3 must raise
    CustomRuleNotEvaluated (same convention A1 / E2 / E7 follow)."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import CustomRuleNotEvaluated, check_adr_a3
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    df = _make_a3_df([
        {"PLANVIEW_ID": "PV-1", "COMPLETE_WBC": "311.0.0.0",
         "COST_TOTAL_HOURS": 100.0, "COST_TOTAL_COST": 50.0},
    ])
    raised = False
    try:
        check_adr_a3(df)
    except CustomRuleNotEvaluated:
        raised = True
    assert raised


def test_adr_a3_fails_for_all_rows_when_reference_missing_required_columns(
    monkeypatch,
):
    """If the reference dataset lacks ICARUS_COA / ISO_COR / SAB, the
    join cannot resolve, every row fails."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_adr_a3
    monkeypatch.setattr(
        ref_mod,
        "get_reference_dataset",
        lambda name: pd.DataFrame({"ICARUS_COA": ["311"]}),  # no ISO_COR / SAB
    )
    df = _make_a3_df([
        {"PLANVIEW_ID": "PV-1", "COMPLETE_WBC": "311.0.0.0",
         "COST_TOTAL_HOURS": 100.0, "COST_TOTAL_COST": 50.0},
    ])
    assert check_adr_a3(df).tolist() == [False]


def test_evaluate_custom_rules_dispatches_to_a3(_a3_coa_master_with_population):
    """End-to-end: dispatcher routes an A3 assignment through check_adr_a3."""
    rows = _a3_baseline_population(rows_per_bucket=1)
    # Outlier bucket: 30 distinct WBCs through 313.
    for sub in range(30):
        rows.append({
            "PLANVIEW_ID": "PV-OUTLIER",
            "COMPLETE_WBC": f"313.{sub}.10.10",
            "COST_TOTAL_HOURS": 1_000.0,
            "COST_TOTAL_COST": 500_000.0,
        })
    df = _make_a3_df(rows)
    assignments = [CustomDQRAssignment(rule_id="A3", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ADR")
    assert "A3" in out.columns
    is_outlier = df["COMPLETE_WBC"].fillna("").str.startswith("313.")
    assert (~out["A3"][is_outlier]).all()
    assert out["A3"][~is_outlier].all()
    assert not_evaluated == {}


def test_adr_a3_reuses_acce_coa_master_reference():
    """A3 declares ACCE_COA_MASTER as its reference dataset, so the
    ADR prefetch list is unchanged from what A1 already requires."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ADR"])) == {
        "VWS_GP_STANDARD_SHARE",
        "ACCE_COA_MASTER",
    }


# -----------------------------------------------------------------------------
# A3: project-scoped percentile (params={"project_scoped": True})
# -----------------------------------------------------------------------------

def test_adr_a3_project_scope_isolates_per_project_p90(
    _a3_coa_master_with_population,
):
    """With project scope on, each PLANVIEW_ID gets its own P90.

    P-A has 5 peer buckets (each 1:1) and one outlier bucket
    (8 distinct WBCs through 313 → (C2.12.1, S3.2.2)). P-A local sorted
    ratios = [1,1,1,1,1,8] → P90 = 4.5; the outlier (8) exceeds it → FAIL.
    P-B has 5 baseline buckets all 1:1 → local P90 = 1; nothing fails.
    Total bucket count (11) clears ``ADR_A3_MIN_MAPPING_POPULATION``."""
    from src.custom_dqr_engine import (
        ADR_A3_PROJECT_SCOPED_PARAM,
        check_adr_a3,
    )
    rows = []
    # P-A peers: 5 distinct ICARUS_COAs, each 1:1, all material via hours.
    for coa in ("311", "312", "314", "317", "318"):
        rows.append({
            "PLANVIEW_ID": "P-A",
            "COMPLETE_WBC": f"{coa}.0.10.10",
            "COST_TOTAL_HOURS": 100.0,
            "COST_TOTAL_COST": 0.0,
        })
    # P-A outlier: 8 distinct COMPLETE_WBC values mapping through 313.
    for sub in range(8):
        rows.append({
            "PLANVIEW_ID": "P-A",
            "COMPLETE_WBC": f"313.{sub}.10.10",
            "COST_TOTAL_HOURS": 100.0,
            "COST_TOTAL_COST": 0.0,
        })
    # P-B baseline: 5 distinct 1:1 buckets.
    for coa in ("321", "323", "324", "325", "326"):
        rows.append({
            "PLANVIEW_ID": "P-B",
            "COMPLETE_WBC": f"{coa}.0.10.10",
            "COST_TOTAL_HOURS": 100.0,
            "COST_TOTAL_COST": 0.0,
        })
    df = _make_a3_df(rows)
    result = check_adr_a3(df, params={ADR_A3_PROJECT_SCOPED_PARAM: True})
    # First 5 P-A peers PASS; 8 P-A outliers FAIL; 5 P-B rows PASS.
    assert result.iloc[:5].all()
    assert (~result.iloc[5:13]).all()
    assert result.iloc[13:].all()


def test_adr_a3_project_scope_does_not_flag_when_outlier_is_global_only(
    _a3_coa_master_with_population,
):
    """A mapping that fails in global scope can PASS in project scope when,
    viewed from inside its own project, the ratio is the local norm.

    10 P-LOW projects, each with one 1:1 bucket, plus one P-HI project
    whose single bucket holds 5 distinct WBCs through 313. Global sorted
    ratios = [1]*10 + [5] → global P90 = 1 → P-HI fails. Inside P-HI
    the local distribution is just [5]; local P90 = 5 → 5 > 5 is False
    → P-HI passes."""
    from src.custom_dqr_engine import (
        ADR_A3_PROJECT_SCOPED_PARAM,
        check_adr_a3,
    )
    rows = []
    for coa in (
        "311", "312", "314", "317", "318",
        "321", "323", "324", "325", "326",
    ):
        rows.append({
            "PLANVIEW_ID": f"P-LOW-{coa}",
            "COMPLETE_WBC": f"{coa}.0.10.10",
            "COST_TOTAL_HOURS": 100.0,
            "COST_TOTAL_COST": 0.0,
        })
    for sub in range(5):
        rows.append({
            "PLANVIEW_ID": "P-HI",
            "COMPLETE_WBC": f"313.{sub}.10.10",
            "COST_TOTAL_HOURS": 100.0,
            "COST_TOTAL_COST": 0.0,
        })
    df = _make_a3_df(rows)

    # Sanity: in global scope the P-HI mapping FAILS.
    global_result = check_adr_a3(
        df, params={ADR_A3_PROJECT_SCOPED_PARAM: False}
    )
    assert global_result.iloc[:10].all()
    assert (~global_result.iloc[10:]).all()

    # In project scope, P-HI's local distribution is [5]; its local P90 is
    # 5; so 5 > 5 is False → P-HI rows now PASS.
    proj_result = check_adr_a3(
        df, params={ADR_A3_PROJECT_SCOPED_PARAM: True}
    )
    assert proj_result.all()


def test_adr_a3_project_scope_passes_rows_with_null_planview_id(
    _a3_coa_master_with_population,
):
    """Rows lacking PLANVIEW_ID can't be assigned to a project; in project
    scope they PASS (A2 already covers the missing-project linkage)."""
    from src.custom_dqr_engine import (
        ADR_A3_PROJECT_SCOPED_PARAM,
        check_adr_a3,
    )
    rows = [
        # Null / blank PLANVIEW_ID rows - should PASS regardless of WBC.
        {"PLANVIEW_ID": None, "COMPLETE_WBC": "313.0.10.10",
         "COST_TOTAL_HOURS": 100.0, "COST_TOTAL_COST": 0.0},
        {"PLANVIEW_ID": "  ", "COMPLETE_WBC": "313.1.10.10",
         "COST_TOTAL_HOURS": 100.0, "COST_TOTAL_COST": 0.0},
    ]
    # Baseline 1:1 buckets across enough projects to cross the min pop floor.
    rows.extend(_a3_baseline_population(rows_per_bucket=1, hours=100.0, cost=0.0))
    df = _make_a3_df(rows)
    out = check_adr_a3(df, params={ADR_A3_PROJECT_SCOPED_PARAM: True})
    assert out.iloc[:2].tolist() == [True, True]
    assert out.iloc[2:].all()


def test_adr_a3_project_scope_fails_all_rows_when_planview_id_missing():
    """Schema-level: project scope is on but the dataset lacks PLANVIEW_ID
    altogether → rule fails for every row (rather than silently passing)."""
    from src.custom_dqr_engine import (
        ADR_A3_PROJECT_SCOPED_PARAM,
        check_adr_a3,
    )
    df = pd.DataFrame([
        {"COMPLETE_WBC": "313.0.10.10",
         "COST_TOTAL_HOURS": 100.0, "COST_TOTAL_COST": 0.0},
    ], columns=["COMPLETE_WBC", "COST_TOTAL_HOURS", "COST_TOTAL_COST"])
    out = check_adr_a3(df, params={ADR_A3_PROJECT_SCOPED_PARAM: True})
    assert out.tolist() == [False]


def test_adr_a3_default_params_match_global_scope(
    _a3_coa_master_with_population,
):
    """Calling check_adr_a3 with params=None / {} / project_scoped=False
    must produce identical results - global scope is the default."""
    from src.custom_dqr_engine import (
        ADR_A3_PROJECT_SCOPED_PARAM,
        check_adr_a3,
    )
    df = _make_a3_df(_a3_baseline_population(rows_per_bucket=1, hours=100.0))
    assert check_adr_a3(df).equals(check_adr_a3(df, params={}))
    assert check_adr_a3(df).equals(
        check_adr_a3(df, params={ADR_A3_PROJECT_SCOPED_PARAM: False})
    )


# -----------------------------------------------------------------------------
# A3: uniform 1:1 mapping detection (params={"detect_uniform_mapping": True})
# -----------------------------------------------------------------------------

def test_adr_a3_uniform_detection_off_by_default_passes_uniform_buckets(
    _a3_coa_master_with_population,
):
    """Without the toggle, the baseline population (every bucket 1:1)
    PASSES, the percentile branch sees P90 == 1 and no bucket exceeds it."""
    from src.custom_dqr_engine import check_adr_a3
    df = _make_a3_df(_a3_baseline_population(rows_per_bucket=1, hours=1.0, cost=50.0))
    assert check_adr_a3(df).all()


def test_adr_a3_uniform_detection_flags_material_1_to_1_buckets(
    _a3_coa_master_with_population,
):
    """Toggle on → every material bucket with ratio == 1 FAILS, even when
    no bucket exceeds the P90."""
    from src.custom_dqr_engine import (
        ADR_A3_DETECT_UNIFORM_MAPPING_PARAM,
        check_adr_a3,
    )
    # Baseline population is uniformly 1:1 and material via hours.
    df = _make_a3_df(
        _a3_baseline_population(rows_per_bucket=1, hours=100.0, cost=50.0)
    )
    result = check_adr_a3(
        df, params={ADR_A3_DETECT_UNIFORM_MAPPING_PARAM: True}
    )
    assert (~result).all()


def test_adr_a3_uniform_detection_respects_materiality(
    _a3_coa_master_with_population,
):
    """Toggle on still doesn't fail immaterial 1:1 buckets - materiality
    gates both the percentile and uniform branches."""
    from src.custom_dqr_engine import (
        ADR_A3_DETECT_UNIFORM_MAPPING_PARAM,
        check_adr_a3,
    )
    df = _make_a3_df(
        _a3_baseline_population(rows_per_bucket=1, hours=0.0, cost=50.0)
    )
    assert check_adr_a3(
        df, params={ADR_A3_DETECT_UNIFORM_MAPPING_PARAM: True}
    ).all()


# =============================================================================
# A4: Core quantities populated (ADR; project-level completeness rule)
# =============================================================================

def _a4_required_cols():
    return [
        "PLANVIEW_ID",
        "ITEM_TYPE",
        "ITEM_DESCRIPTION",
        "QTY_QUANTITY",
        "QTY_UOM",
    ]


def _make_a4_df(rows):
    """Build an ADR-shaped denormalized DataFrame from a list of dicts.
    Missing keys default to None so the rule sees them as null."""
    cols = _a4_required_cols()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


# ----- Catalog metadata ------------------------------------------------------

def test_adr_has_custom_rule_a4_available():
    """ADR catalog exposes A4 as a non-blocking Completeness & Validity rule."""
    rules = get_available_custom_dqr_rules("ADR")
    by_id = {r.id: r for r in rules}
    assert "A4" in by_id
    rule = by_id["A4"]
    assert rule.type == "Completeness & Validity"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Project Key": "PLANVIEW_ID",
        "Item Type": "ITEM_TYPE",
        "Item Description": "ITEM_DESCRIPTION",
        "Quantity": "QTY_QUANTITY",
        "Quantity UOM": "QTY_UOM",
    }
    assert rule.reference is None


def test_adr_a4_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ADR_A4_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ADR") if r.id == "A4"
    )
    assert rule.required_columns == ADR_A4_REQUIRED_COLUMNS


# ----- Scope classifier ------------------------------------------------------

def test_a4_scope_classifier_picks_up_each_of_seven_categories():
    """One representative item per scope category, every category
    must be returned, none of the others."""
    from src.custom_dqr_engine import _classify_a4_scope
    cases = [
        ("EstimateAbovegroundInstrumentPiping", "", "PIPING_LF"),
        ("EstimatePipingUnderground", "", "PIPING_LF"),
        ("EstimatePipingPneumatic", "", "PIPING_LF"),
        ("EstimateFoundation", "", "CONCRETE_CY"),
        ("EstimateMiscellaneousConcrete", "", "CONCRETE_CY"),
        ("EstimateSteelStructure", "", "STEEL_TONS"),
        ("EstimatePiperack", "", "STEEL_TONS"),
        ("EstimateElectricalPowerGroup", "", "CABLE_LENGTH"),
        ("EstimateFieldInstrumentGroup", "", "TRANSMITTER_COUNT"),
        ("EstimatePump", "", "EQUIPMENT_COUNT"),
        ("EstimateGasTurbine", "", "EQUIPMENT_COUNT"),
        ("EstimateModular", "", "MODULE_COUNT"),
        ("EstimateGeneric", "Modular skid 4x4", "MODULE_COUNT"),
    ]
    for it, desc, expected in cases:
        scopes = _classify_a4_scope(it, desc)
        assert expected in scopes, f"({it!r}, {desc!r}) → {scopes}"


def test_a4_scope_classifier_unrecognised_inputs_return_empty_set():
    from src.custom_dqr_engine import _classify_a4_scope
    assert _classify_a4_scope(None, None) == set()
    assert _classify_a4_scope("", "") == set()
    assert _classify_a4_scope("EstimateRandom", "RandomDescription") == set()


def test_a4_scope_classifier_piperack_does_not_imply_piping_scope():
    """A4 distinguishes piping (length) from steel (weight) - Piperack
    is steel scope only, not piping."""
    from src.custom_dqr_engine import _classify_a4_scope
    scopes = _classify_a4_scope("EstimatePiperack", "")
    assert "STEEL_TONS" in scopes
    assert "PIPING_LF" not in scopes


def test_a4_scope_classifier_cable_length_does_not_match_field_instrument():
    """Spec §8.4 - A4 keeps CABLE_LENGTH conservative: only ITEM_TYPE
    containing 'Electrical' implies cable scope. FieldInstrument is
    transmitter-count scope, not cable scope."""
    from src.custom_dqr_engine import _classify_a4_scope
    assert "CABLE_LENGTH" not in _classify_a4_scope(
        "EstimateFieldInstrumentGroup", ""
    )


# ----- Quantity classifier ---------------------------------------------------

def test_a4_quantity_classifier_returns_correct_category_per_pattern():
    from src.custom_dqr_engine import _classify_a4_quantity
    cases = [
        # PIPING_LF
        ("EstimateAbovegroundInstrumentPiping", "ft", "", "PIPING_LF"),
        ("EstimatePipingUnderground", "m", "", "PIPING_LF"),
        # CONCRETE_CY (with CY → yd³ alias)
        ("EstimateFoundation", "yd³", "", "CONCRETE_CY"),
        ("EstimateFoundation", "CY", "", "CONCRETE_CY"),
        ("EstimateMiscellaneousConcrete", "m³", "", "CONCRETE_CY"),
        # STEEL_TONS
        ("EstimateSteelStructure", "t", "", "STEEL_TONS"),
        ("EstimatePiperack", "t,sht", "", "STEEL_TONS"),
        # CABLE_LENGTH
        ("EstimateElectricalPowerGroup", "ft", "", "CABLE_LENGTH"),
        # TRANSMITTER_COUNT
        ("EstimateFieldInstrumentGroup", "Pressure Gauges", "",
         "TRANSMITTER_COUNT"),
        ("EstimateFieldInstrumentGroup", "Transmitters", "",
         "TRANSMITTER_COUNT"),
        # EQUIPMENT_COUNT - exact pair from the allow-list
        ("EstimatePump", "Parallel Pumps", "", "EQUIPMENT_COUNT"),
        ("EstimateTankage", "Order Quantity", "", "EQUIPMENT_COUNT"),
        ("EstimateAirCooledExchanger", "Air-Fins", "", "EQUIPMENT_COUNT"),
        ("EstimateShellAndTubeExchanger", "Shells", "", "EQUIPMENT_COUNT"),
        ("EstimateVerticalPressureVessel", "Vertical Drum Sections", "",
         "EQUIPMENT_COUNT"),
        # MODULE_COUNT
        ("EstimateModularUnit", "Each", "", "MODULE_COUNT"),
        ("EstimateGeneric", "Modules", "Modular skid", "MODULE_COUNT"),
    ]
    for it, uom, desc, expected in cases:
        got = _classify_a4_quantity(it, uom, desc)
        assert got == expected, (
            f"({it!r}, {uom!r}, {desc!r}) → {got}, expected {expected}"
        )


def test_a4_quantity_classifier_rejects_off_pattern_uom_for_each_category():
    """Each category requires a specific UOM - a foundation row with
    UOM=t doesn't classify as concrete (or as anything else)."""
    from src.custom_dqr_engine import _classify_a4_quantity
    # Scope-matching ITEM_TYPEs with the *wrong* UOM → None.
    assert _classify_a4_quantity("EstimateFoundation", "t", "") is None
    assert _classify_a4_quantity("EstimateSteelStructure", "ft", "") is None
    assert _classify_a4_quantity(
        "EstimateAbovegroundInstrumentPiping", "yd³", ""
    ) is None
    assert _classify_a4_quantity("EstimateElectricalPowerGroup", "t", "") is None


def test_a4_quantity_classifier_equipment_requires_exact_allowlist_pair():
    """EQUIPMENT_COUNT is gated to the exact (ITEM_TYPE, UOM) pairs in
    the spec - even a major-equipment item with a generic count UOM
    like 'EA' doesn't classify."""
    from src.custom_dqr_engine import _classify_a4_quantity
    # Pump + EA is generic, not on the allow-list → None.
    assert _classify_a4_quantity("EstimatePump", "EA", "") is None
    # The ITEM_TYPE matches but the UOM doesn't appear paired with it.
    assert _classify_a4_quantity("EstimatePump", "Drivers", "") is None


def test_a4_quantity_classifier_returns_none_on_blank_inputs():
    from src.custom_dqr_engine import _classify_a4_quantity
    assert _classify_a4_quantity(None, "ft", "") is None
    assert _classify_a4_quantity("EstimateFoundation", None, "") is None
    assert _classify_a4_quantity("", "ft", "") is None
    assert _classify_a4_quantity("EstimateFoundation", "  ", "") is None


# ----- check_adr_a4 - happy & failure paths ----------------------------------

def test_adr_a4_passes_project_with_all_expected_quantities_populated():
    """Project P1 has piping + concrete scope and a populated row for
    each - passes."""
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateAbovegroundInstrumentPiping",
         "ITEM_DESCRIPTION": "pipeline 6in",
         "QTY_QUANTITY": 1000.0, "QTY_UOM": "ft"},
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateFoundation",
         "ITEM_DESCRIPTION": "slab",
         "QTY_QUANTITY": 50.0, "QTY_UOM": "yd³"},
    ])
    assert check_adr_a4(df).tolist() == [True, True]


def test_adr_a4_fails_project_when_expected_scope_lacks_populated_quantity():
    """Project P1 has piping scope but the only piping row has UOM=t
    (steel UOM), no populated PIPING_LF → project FAILs, both rows
    inherit FAIL."""
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateAbovegroundInstrumentPiping",
         "ITEM_DESCRIPTION": "pipeline",
         "QTY_QUANTITY": 1000.0, "QTY_UOM": "t"},   # wrong UOM
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateFoundation",
         "ITEM_DESCRIPTION": "slab",
         "QTY_QUANTITY": 50.0, "QTY_UOM": "yd³"},
    ])
    assert check_adr_a4(df).tolist() == [False, False]


def test_adr_a4_fails_project_when_quantity_zero_or_null_for_expected_scope():
    """Population requires QUANTITY > 0 strictly - null / zero / negative
    don't satisfy 'populated' for that scope."""
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        # Steel scope but qty is 0 → not populated → project FAILs.
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateSteelStructure",
         "ITEM_DESCRIPTION": "frame",
         "QTY_QUANTITY": 0.0, "QTY_UOM": "t"},
    ])
    assert check_adr_a4(df).tolist() == [False]
    # Same with negative quantity.
    df = _make_a4_df([
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateSteelStructure",
         "ITEM_DESCRIPTION": "frame",
         "QTY_QUANTITY": -5.0, "QTY_UOM": "t"},
    ])
    assert check_adr_a4(df).tolist() == [False]


def test_adr_a4_passes_project_with_no_recognised_scope():
    """Off-pattern ITEM_TYPEs imply no core quantity type → no
    EXPECTS_X = 1 → project trivially passes."""
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateRandomThing",
         "ITEM_DESCRIPTION": "-",
         "QTY_QUANTITY": 100.0, "QTY_UOM": "EA"},
    ])
    assert check_adr_a4(df).tolist() == [True]


def test_adr_a4_handles_multiple_projects_independently():
    """A failing project must not contaminate a passing one, each
    project's scope and population is judged in isolation."""
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        # P1: foundation scope, foundation populated → PASS.
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateFoundation", "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 30.0, "QTY_UOM": "yd³"},
        # P2: foundation scope, foundation populated, but ALSO a piping
        # scope item with no populated piping length → P2 FAILs.
        {"PLANVIEW_ID": "P2",
         "ITEM_TYPE": "EstimateFoundation", "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 30.0, "QTY_UOM": "yd³"},
        {"PLANVIEW_ID": "P2",
         "ITEM_TYPE": "EstimateAbovegroundInstrumentPiping",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 100.0, "QTY_UOM": "EA"},   # wrong UOM
    ])
    assert check_adr_a4(df).tolist() == [True, False, False]


def test_adr_a4_fails_project_with_negative_total_quantity():
    """Validity: a project whose total QTY_QUANTITY sums to a negative
    value fails, even when no core scope is recognised (the negative-sum
    check is independent of the expected-type completeness check)."""
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        {"PLANVIEW_ID": "P1", "ITEM_TYPE": "EstimateRandomThing",
         "ITEM_DESCRIPTION": "-", "QTY_QUANTITY": -200.0, "QTY_UOM": "EA"},
        {"PLANVIEW_ID": "P1", "ITEM_TYPE": "EstimateRandomThing",
         "ITEM_DESCRIPTION": "-", "QTY_QUANTITY": 50.0, "QTY_UOM": "EA"},
    ])
    # Project total = -150 < 0 → both rows FAIL.
    assert check_adr_a4(df).tolist() == [False, False]


def test_adr_a4_passes_project_with_negative_rows_but_nonnegative_total():
    """Individual rows may carry negative quantities (corrections /
    reversals) - the project passes as long as the *total* is not
    negative."""
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        {"PLANVIEW_ID": "P1", "ITEM_TYPE": "EstimateRandomThing",
         "ITEM_DESCRIPTION": "-", "QTY_QUANTITY": -50.0, "QTY_UOM": "EA"},
        {"PLANVIEW_ID": "P1", "ITEM_TYPE": "EstimateRandomThing",
         "ITEM_DESCRIPTION": "-", "QTY_QUANTITY": 120.0, "QTY_UOM": "EA"},
    ])
    # Project total = +70 ≥ 0 → both rows PASS despite a negative row.
    assert check_adr_a4(df).tolist() == [True, True]


def test_adr_a4_passes_project_with_zero_total_quantity():
    """A project total of exactly zero is not negative → passes (only a
    strictly negative total fails)."""
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        {"PLANVIEW_ID": "P1", "ITEM_TYPE": "EstimateRandomThing",
         "ITEM_DESCRIPTION": "-", "QTY_QUANTITY": -50.0, "QTY_UOM": "EA"},
        {"PLANVIEW_ID": "P1", "ITEM_TYPE": "EstimateRandomThing",
         "ITEM_DESCRIPTION": "-", "QTY_QUANTITY": 50.0, "QTY_UOM": "EA"},
    ])
    assert check_adr_a4(df).tolist() == [True, True]


def test_adr_a4_fails_populated_project_with_negative_total():
    """The negative-total check is OR-ed with the completeness check: a
    project whose expected scope IS populated still fails if a large
    correction drives its total QTY_QUANTITY negative."""
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateFoundation", "ITEM_DESCRIPTION": "slab",
         "QTY_QUANTITY": 30.0, "QTY_UOM": "yd³"},   # concrete populated
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateFoundation", "ITEM_DESCRIPTION": "reversal",
         "QTY_QUANTITY": -100.0, "QTY_UOM": "yd³"},  # correction
    ])
    # Concrete scope is populated (the +30 row), so completeness passes,
    # but project total = -70 < 0 → project FAILs.
    assert check_adr_a4(df).tolist() == [False, False]


def test_adr_a4_negative_total_in_one_project_does_not_affect_another():
    """Negative-total failure is scoped per project."""
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        {"PLANVIEW_ID": "P1", "ITEM_TYPE": "EstimateRandomThing",
         "ITEM_DESCRIPTION": "-", "QTY_QUANTITY": 500.0, "QTY_UOM": "EA"},
        {"PLANVIEW_ID": "P2", "ITEM_TYPE": "EstimateRandomThing",
         "ITEM_DESCRIPTION": "-", "QTY_QUANTITY": -10.0, "QTY_UOM": "EA"},
    ])
    # P1 total +500 → PASS; P2 total -10 → FAIL.
    assert check_adr_a4(df).tolist() == [True, False]


def test_adr_a4_passes_rows_with_blank_planview_id():
    """A row whose PLANVIEW_ID is null/blank can't be assigned to a
    project, it always passes regardless of how its peer projects do."""
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        {"PLANVIEW_ID": None,
         "ITEM_TYPE": "EstimateAbovegroundInstrumentPiping",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 100.0, "QTY_UOM": "t"},   # wrong UOM
        # A failing project alongside, just to make sure the orphan
        # really is independent.
        {"PLANVIEW_ID": "P-BAD",
         "ITEM_TYPE": "EstimateFoundation",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 10.0, "QTY_UOM": "t"},
    ])
    result = check_adr_a4(df).tolist()
    assert result[0] is True
    assert result[1] is False


def test_adr_a4_pass_when_every_expected_scope_populated_for_all_seven():
    """A project with all seven scopes expected and all seven populated
    must pass - exercises every classifier branch end-to-end."""
    from src.custom_dqr_engine import check_adr_a4
    rows = [
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateAbovegroundInstrumentPiping",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 1000.0, "QTY_UOM": "ft"},          # PIPING_LF
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateFoundation",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 50.0, "QTY_UOM": "yd³"},           # CONCRETE_CY
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateSteelStructure",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 100.0, "QTY_UOM": "t"},            # STEEL_TONS
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateElectricalPowerGroup",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 200.0, "QTY_UOM": "m"},            # CABLE_LENGTH
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateFieldInstrumentGroup",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 12.0, "QTY_UOM": "Pressure Gauges"},  # TRANSMITTER_COUNT
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimatePump",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 5.0, "QTY_UOM": "Parallel Pumps"}, # EQUIPMENT_COUNT
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateModularSkid",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 3.0, "QTY_UOM": "Each"},           # MODULE_COUNT
    ]
    df = _make_a4_df(rows)
    assert check_adr_a4(df).all()


def test_adr_a4_fails_when_one_of_seven_expected_scopes_unpopulated():
    """Drop the populated foundation row from the all-seven setup, the
    project still has CONCRETE scope (because of the unrelated
    foundation that's missing its populated row) … wait, no: scope
    detection is *per-row*. We need a different approach: keep all
    seven scopes implied by separate item types, but make one of them
    populated on the wrong UOM."""
    from src.custom_dqr_engine import check_adr_a4
    rows = [
        # PIPING_LF - populated correctly.
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateAbovegroundInstrumentPiping",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 1000.0, "QTY_UOM": "ft"},
        # CONCRETE scope is implied, but the only foundation row has
        # the wrong UOM (t instead of yd³). HAS_CONCRETE_CY = False.
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateFoundation",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 50.0, "QTY_UOM": "t"},
    ]
    df = _make_a4_df(rows)
    assert check_adr_a4(df).tolist() == [False, False]


# ----- check_adr_a4 - schema-level / structural failures ---------------------

def test_adr_a4_fails_for_all_rows_when_required_column_missing():
    """Schema-level structural incompleteness fails every row."""
    from src.custom_dqr_engine import check_adr_a4
    base = pd.DataFrame({
        "PLANVIEW_ID": ["P1", "P1"],
        "ITEM_TYPE": ["EstimateFoundation"] * 2,
        "ITEM_DESCRIPTION": [""] * 2,
        "QTY_QUANTITY": [10.0, 20.0],
        "QTY_UOM": ["yd³", "yd³"],
    })
    for missing in _a4_required_cols():
        df = base.drop(columns=missing)
        assert check_adr_a4(df).tolist() == [False, False], (
            f"missing {missing} should fail every row"
        )


def test_adr_a4_empty_dataframe_returns_empty_pass_series():
    from src.custom_dqr_engine import check_adr_a4
    df = pd.DataFrame({c: [] for c in _a4_required_cols()})
    result = check_adr_a4(df)
    assert result.tolist() == []
    assert result.dtype == bool


def test_adr_a4_passes_when_no_planview_id_filled_for_any_row():
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        {"PLANVIEW_ID": None,
         "ITEM_TYPE": "EstimateFoundation", "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 10.0, "QTY_UOM": "t"},
        {"PLANVIEW_ID": "  ",
         "ITEM_TYPE": "EstimateSteelStructure", "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 5.0, "QTY_UOM": "ft"},
    ])
    assert check_adr_a4(df).tolist() == [True, True]


def test_adr_a4_handles_object_dtyped_numeric_quantities():
    """Mixed string / numeric inputs must coerce - non-numeric become
    NaN and are treated as not-populated."""
    from src.custom_dqr_engine import check_adr_a4
    df = _make_a4_df([
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateFoundation", "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": "abc", "QTY_UOM": "yd³"},
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateFoundation", "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": "50", "QTY_UOM": "yd³"},
    ])
    # Foundation scope, one populated row → P1 passes.
    assert check_adr_a4(df).tolist() == [True, True]


def test_evaluate_custom_rules_dispatches_to_a4():
    """End-to-end: dispatcher routes an A4 assignment through check_adr_a4."""
    df = _make_a4_df([
        {"PLANVIEW_ID": "P1",
         "ITEM_TYPE": "EstimateFoundation", "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 30.0, "QTY_UOM": "yd³"},
        {"PLANVIEW_ID": "P-BAD",
         "ITEM_TYPE": "EstimateAbovegroundInstrumentPiping",
         "ITEM_DESCRIPTION": "",
         "QTY_QUANTITY": 100.0, "QTY_UOM": "t"},   # piping scope, wrong UOM
    ])
    assignments = [CustomDQRAssignment(rule_id="A4", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ADR")
    assert "A4" in out.columns
    assert out["A4"].tolist() == [True, False]
    assert not_evaluated == {}


def test_adr_a4_does_not_add_reference_dataset_to_prefetch():
    """A4 has no ``reference`` dataset, so the ADR system's prefetch
    list is the same one A1 + A2 already require."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ADR"])) == {
        "VWS_GP_STANDARD_SHARE",
        "ACCE_COA_MASTER",
    }


# =============================================================================
# A5: Design details present when quantity exists (ADR; consistency rule)
# =============================================================================

def _make_a5_df(rows):
    """Build an ADR-shaped denormalized DataFrame from a list of dicts.
    Missing keys default to None so the rule sees them as null."""
    cols = ["QTY_QUANTITY", "DESIGN_PARAMETER_VALUE"]
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def test_adr_has_custom_rule_a5_available():
    """ADR catalog exposes A5 as a non-blocking Consistency rule with the
    documented physical column mapping."""
    rules = get_available_custom_dqr_rules("ADR")
    by_id = {r.id: r for r in rules}
    assert "A5" in by_id
    rule = by_id["A5"]
    assert rule.type == "Consistency"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Quantity": "QTY_QUANTITY",
        "Design Parameter Value": "DESIGN_PARAMETER_VALUE",
    }
    # A5 does not consult an external reference dataset.
    assert rule.reference is None


def test_adr_a5_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ADR_A5_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ADR") if r.id == "A5"
    )
    assert rule.required_columns == ADR_A5_REQUIRED_COLUMNS


def test_adr_a5_passes_when_quantity_and_design_detail_both_present():
    """Happy path: non-zero quantity + populated DESIGN_PARAMETER_VALUE."""
    from src.custom_dqr_engine import check_adr_a5
    df = _make_a5_df([
        {"QTY_QUANTITY": 10.0, "DESIGN_PARAMETER_VALUE": "SCH 40"},
        {"QTY_QUANTITY": 0.5, "DESIGN_PARAMETER_VALUE": "Carbon Steel"},
        {"QTY_QUANTITY": -1.0, "DESIGN_PARAMETER_VALUE": "6 in"},
    ])
    assert check_adr_a5(df).tolist() == [True, True, True]


def test_adr_a5_fails_when_quantity_present_but_design_detail_missing():
    """The only FAIL path: non-zero quantity, no design detail."""
    from src.custom_dqr_engine import check_adr_a5
    df = _make_a5_df([
        {"QTY_QUANTITY": 10.0, "DESIGN_PARAMETER_VALUE": None},
        {"QTY_QUANTITY": 5.0, "DESIGN_PARAMETER_VALUE": ""},
        {"QTY_QUANTITY": 2.0, "DESIGN_PARAMETER_VALUE": "   "},
    ])
    assert check_adr_a5(df).tolist() == [False, False, False]


def test_adr_a5_passes_when_quantity_zero_regardless_of_design_detail():
    """``QUANTITY = 0`` is treated as 'no quantity'; rule is not applicable
    and the row passes - even when DESIGN_PARAMETER_VALUE is also missing."""
    from src.custom_dqr_engine import check_adr_a5
    df = _make_a5_df([
        {"QTY_QUANTITY": 0.0, "DESIGN_PARAMETER_VALUE": None},
        {"QTY_QUANTITY": 0, "DESIGN_PARAMETER_VALUE": ""},
        {"QTY_QUANTITY": 0.0, "DESIGN_PARAMETER_VALUE": "ABC"},
    ])
    assert check_adr_a5(df).tolist() == [True, True, True]


def test_adr_a5_passes_when_quantity_null_regardless_of_design_detail():
    """``QUANTITY IS NULL`` is treated as 'no quantity' (per rule §12),
    so the rule is not applicable and the row passes."""
    from src.custom_dqr_engine import check_adr_a5
    df = _make_a5_df([
        {"QTY_QUANTITY": None, "DESIGN_PARAMETER_VALUE": None},
        {"QTY_QUANTITY": None, "DESIGN_PARAMETER_VALUE": "SS-316"},
    ])
    assert check_adr_a5(df).tolist() == [True, True]


def test_adr_a5_negative_quantity_counts_as_quantity_present():
    """Per spec §13: 'A negative quantity should count as quantity existing
    because it is non-zero.' So a negative-quantity row with no design
    detail must FAIL."""
    from src.custom_dqr_engine import check_adr_a5
    df = _make_a5_df([
        {"QTY_QUANTITY": -3.0, "DESIGN_PARAMETER_VALUE": None},
        {"QTY_QUANTITY": -3.0, "DESIGN_PARAMETER_VALUE": "Carbon Steel"},
    ])
    assert check_adr_a5(df).tolist() == [False, True]


def test_adr_a5_decision_matrix_covers_all_four_states():
    """End-to-end coverage of the §11 decision matrix in a single batch."""
    from src.custom_dqr_engine import check_adr_a5
    df = _make_a5_df([
        # HAS_QUANTITY=0, HAS_DESIGN_DETAIL=0 → PASS
        {"QTY_QUANTITY": 0.0, "DESIGN_PARAMETER_VALUE": None},
        # HAS_QUANTITY=0, HAS_DESIGN_DETAIL=1 → PASS
        {"QTY_QUANTITY": 0.0, "DESIGN_PARAMETER_VALUE": "ASME"},
        # HAS_QUANTITY=1, HAS_DESIGN_DETAIL=0 → FAIL
        {"QTY_QUANTITY": 12.0, "DESIGN_PARAMETER_VALUE": ""},
        # HAS_QUANTITY=1, HAS_DESIGN_DETAIL=1 → PASS
        {"QTY_QUANTITY": 12.0, "DESIGN_PARAMETER_VALUE": "API-650"},
    ])
    assert check_adr_a5(df).tolist() == [True, True, False, True]


def test_adr_a5_handles_object_dtyped_numeric_quantities():
    """A heterogeneous source (e.g. mixed numeric strings and floats) must
    not crash the rule - pd.to_numeric coerces unrecognised values to NaN
    which the rule treats as 'no quantity'."""
    from src.custom_dqr_engine import check_adr_a5
    df = pd.DataFrame({
        "QTY_QUANTITY": ["10", "0", None, "abc"],
        "DESIGN_PARAMETER_VALUE": [None, None, None, None],
    })
    # Row 0: "10" -> 10 -> non-zero, no detail -> FAIL.
    # Rows 1,2,3: 0 / NaN / NaN -> "no quantity" -> PASS.
    assert check_adr_a5(df).tolist() == [False, True, True, True]


def test_adr_a5_fails_for_all_rows_when_quantity_column_missing():
    """Schema-level structural incompleteness fails every row, same
    convention as the other custom rules (E1, E4, A2, ...)."""
    from src.custom_dqr_engine import check_adr_a5
    df = pd.DataFrame({"DESIGN_PARAMETER_VALUE": ["SCH 40", "ASME"]})
    assert check_adr_a5(df).tolist() == [False, False]


def test_adr_a5_fails_for_all_rows_when_design_parameter_value_column_missing():
    from src.custom_dqr_engine import check_adr_a5
    df = pd.DataFrame({"QTY_QUANTITY": [10.0, 0.0]})
    assert check_adr_a5(df).tolist() == [False, False]


def test_adr_a5_empty_dataframe_returns_empty_pass_series():
    """An empty DataFrame produces an empty Boolean Series (PASS-by-default
    for the empty index), the rule short-circuits before any column logic
    runs."""
    from src.custom_dqr_engine import check_adr_a5
    df = pd.DataFrame(
        {"QTY_QUANTITY": [], "DESIGN_PARAMETER_VALUE": []}
    )
    result = check_adr_a5(df)
    assert result.tolist() == []
    assert result.dtype == bool


def test_evaluate_custom_rules_dispatches_to_a5():
    """End-to-end: dispatcher routes an A5 assignment through check_adr_a5
    for the ADR data product."""
    df = _make_a5_df([
        {"QTY_QUANTITY": 10.0, "DESIGN_PARAMETER_VALUE": "ASME"},
        {"QTY_QUANTITY": 7.0, "DESIGN_PARAMETER_VALUE": None},
        {"QTY_QUANTITY": 0.0, "DESIGN_PARAMETER_VALUE": None},
    ])
    assignments = [CustomDQRAssignment(rule_id="A5", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ADR")
    assert "A5" in out.columns
    assert out["A5"].tolist() == [True, False, True]
    assert not_evaluated == {}


def test_adr_a5_does_not_add_reference_dataset_to_prefetch():
    """A5 has no ``reference`` dataset, so adding it must not change the set
    of references Step 2 needs to prefetch for the ADR system."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ADR"])) == {
        "VWS_GP_STANDARD_SHARE",
        "ACCE_COA_MASTER",
    }


# =============================================================================
# A6: Construction hours present when quantity exists (ADR; consistency rule)
# =============================================================================

def _make_a6_df(rows):
    """Build an ADR-shaped denormalized DataFrame from a list of dicts.
    Missing keys default to None so the rule sees them as null."""
    cols = ["QTY_QUANTITY", "COST_TOTAL_HOURS", "COST_DB_TOTAL_HOURS"]
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def test_adr_has_custom_rule_a6_available():
    """ADR catalog exposes A6 as a non-blocking Consistency rule with the
    documented physical column mapping."""
    rules = get_available_custom_dqr_rules("ADR")
    by_id = {r.id: r for r in rules}
    assert "A6" in by_id
    rule = by_id["A6"]
    assert rule.type == "Consistency"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Quantity": "QTY_QUANTITY",
        "Construction Hours": "COST_TOTAL_HOURS",
        "Construction Hours (DB)": "COST_DB_TOTAL_HOURS",
    }
    # A6 does not consult an external reference dataset.
    assert rule.reference is None


def test_adr_a6_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ADR_A6_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ADR") if r.id == "A6"
    )
    assert rule.required_columns == ADR_A6_REQUIRED_COLUMNS


def test_adr_a6_passes_when_quantity_and_total_hours_both_present():
    """Happy path A: non-zero quantity + positive TOTAL_HOURS (DB null)."""
    from src.custom_dqr_engine import check_adr_a6
    df = _make_a6_df([
        {"QTY_QUANTITY": 10.0, "COST_TOTAL_HOURS": 5.0,
         "COST_DB_TOTAL_HOURS": None},
        {"QTY_QUANTITY": 0.5, "COST_TOTAL_HOURS": 0.1,
         "COST_DB_TOTAL_HOURS": 0.0},
    ])
    assert check_adr_a6(df).tolist() == [True, True]


def test_adr_a6_passes_when_only_db_total_hours_is_positive():
    """Either column is sufficient - DB_TOTAL_HOURS > 0 alone makes the
    item PASS, even with TOTAL_HOURS at null/zero."""
    from src.custom_dqr_engine import check_adr_a6
    df = _make_a6_df([
        {"QTY_QUANTITY": 10.0, "COST_TOTAL_HOURS": None,
         "COST_DB_TOTAL_HOURS": 10.0},
        {"QTY_QUANTITY": 1.0, "COST_TOTAL_HOURS": 0.0,
         "COST_DB_TOTAL_HOURS": 5.0},
    ])
    assert check_adr_a6(df).tolist() == [True, True]


def test_adr_a6_fails_when_quantity_present_but_no_construction_hours():
    """The only FAIL path: non-zero quantity, both hours columns at zero
    or null."""
    from src.custom_dqr_engine import check_adr_a6
    df = _make_a6_df([
        {"QTY_QUANTITY": 10.0, "COST_TOTAL_HOURS": 0.0,
         "COST_DB_TOTAL_HOURS": 0.0},
        {"QTY_QUANTITY": 5.0, "COST_TOTAL_HOURS": None,
         "COST_DB_TOTAL_HOURS": None},
        {"QTY_QUANTITY": 2.0, "COST_TOTAL_HOURS": 0.0,
         "COST_DB_TOTAL_HOURS": None},
    ])
    assert check_adr_a6(df).tolist() == [False, False, False]


def test_adr_a6_negative_hours_do_not_count_as_present():
    """Per spec §12: negative hours do not count as construction hours.
    A row with non-zero quantity and only negative hours must FAIL."""
    from src.custom_dqr_engine import check_adr_a6
    df = _make_a6_df([
        # Both hours columns non-positive → FAIL.
        {"QTY_QUANTITY": 10.0, "COST_TOTAL_HOURS": -5.0,
         "COST_DB_TOTAL_HOURS": -5.0},
        {"QTY_QUANTITY": 10.0, "COST_TOTAL_HOURS": -5.0,
         "COST_DB_TOTAL_HOURS": 0.0},
        # One column negative, the other positive → PASS (either suffices).
        {"QTY_QUANTITY": 10.0, "COST_TOTAL_HOURS": -5.0,
         "COST_DB_TOTAL_HOURS": 3.0},
    ])
    assert check_adr_a6(df).tolist() == [False, False, True]


def test_adr_a6_passes_when_quantity_zero_regardless_of_hours():
    """``QUANTITY = 0`` is treated as 'no quantity'; rule is not
    applicable and the row passes - even with hours absent."""
    from src.custom_dqr_engine import check_adr_a6
    df = _make_a6_df([
        {"QTY_QUANTITY": 0.0, "COST_TOTAL_HOURS": 0.0,
         "COST_DB_TOTAL_HOURS": 0.0},
        {"QTY_QUANTITY": 0, "COST_TOTAL_HOURS": None,
         "COST_DB_TOTAL_HOURS": None},
        {"QTY_QUANTITY": 0.0, "COST_TOTAL_HOURS": 100.0,
         "COST_DB_TOTAL_HOURS": 50.0},
    ])
    assert check_adr_a6(df).tolist() == [True, True, True]


def test_adr_a6_passes_when_quantity_null_regardless_of_hours():
    """``QUANTITY IS NULL`` is treated as 'no quantity', so the rule is
    not applicable and the row passes."""
    from src.custom_dqr_engine import check_adr_a6
    df = _make_a6_df([
        {"QTY_QUANTITY": None, "COST_TOTAL_HOURS": None,
         "COST_DB_TOTAL_HOURS": None},
        {"QTY_QUANTITY": None, "COST_TOTAL_HOURS": 0.0,
         "COST_DB_TOTAL_HOURS": 0.0},
        # Spec §15 example 5: hours present, no quantity → PASS.
        {"QTY_QUANTITY": None, "COST_TOTAL_HOURS": 100.0,
         "COST_DB_TOTAL_HOURS": None},
    ])
    assert check_adr_a6(df).tolist() == [True, True, True]


def test_adr_a6_negative_quantity_counts_as_quantity_present():
    """A negative aggregated quantity counts as 'quantity exists' (same
    as A5 / spec §13). A negative-quantity row with no hours must FAIL."""
    from src.custom_dqr_engine import check_adr_a6
    df = _make_a6_df([
        {"QTY_QUANTITY": -3.0, "COST_TOTAL_HOURS": 0.0,
         "COST_DB_TOTAL_HOURS": 0.0},
        {"QTY_QUANTITY": -3.0, "COST_TOTAL_HOURS": 5.0,
         "COST_DB_TOTAL_HOURS": 0.0},
    ])
    assert check_adr_a6(df).tolist() == [False, True]


def test_adr_a6_decision_matrix_covers_all_four_states():
    """End-to-end coverage of the §11 decision matrix."""
    from src.custom_dqr_engine import check_adr_a6
    df = _make_a6_df([
        # HAS_QUANTITY=0, HAS_HOURS=0 → PASS
        {"QTY_QUANTITY": 0.0, "COST_TOTAL_HOURS": 0.0,
         "COST_DB_TOTAL_HOURS": 0.0},
        # HAS_QUANTITY=0, HAS_HOURS=1 → PASS
        {"QTY_QUANTITY": 0.0, "COST_TOTAL_HOURS": 8.0,
         "COST_DB_TOTAL_HOURS": 0.0},
        # HAS_QUANTITY=1, HAS_HOURS=0 → FAIL
        {"QTY_QUANTITY": 12.0, "COST_TOTAL_HOURS": 0.0,
         "COST_DB_TOTAL_HOURS": 0.0},
        # HAS_QUANTITY=1, HAS_HOURS=1 → PASS
        {"QTY_QUANTITY": 12.0, "COST_TOTAL_HOURS": 4.0,
         "COST_DB_TOTAL_HOURS": 0.0},
    ])
    assert check_adr_a6(df).tolist() == [True, True, False, True]


def test_adr_a6_handles_object_dtyped_numeric_inputs():
    """Mixed string / numeric inputs must not crash - non-numeric values
    coerce to NaN (treated as zero)."""
    from src.custom_dqr_engine import check_adr_a6
    df = pd.DataFrame({
        "QTY_QUANTITY": ["10", "0", "abc"],
        "COST_TOTAL_HOURS": [None, "5", "8"],
        "COST_DB_TOTAL_HOURS": ["0", None, None],
    })
    # Row 0: qty=10, hours=0/0 → FAIL.
    # Row 1: qty=0 → PASS regardless.
    # Row 2: qty="abc"→NaN→0 → PASS regardless.
    assert check_adr_a6(df).tolist() == [False, True, True]


def test_adr_a6_fails_for_all_rows_when_quantity_column_missing():
    """Schema-level structural incompleteness fails every row."""
    from src.custom_dqr_engine import check_adr_a6
    df = pd.DataFrame({
        "COST_TOTAL_HOURS": [10.0, 0.0],
        "COST_DB_TOTAL_HOURS": [0.0, 0.0],
    })
    assert check_adr_a6(df).tolist() == [False, False]


def test_adr_a6_fails_for_all_rows_when_total_hours_column_missing():
    from src.custom_dqr_engine import check_adr_a6
    df = pd.DataFrame({
        "QTY_QUANTITY": [10.0, 0.0],
        "COST_DB_TOTAL_HOURS": [5.0, 0.0],
    })
    assert check_adr_a6(df).tolist() == [False, False]


def test_adr_a6_fails_for_all_rows_when_db_total_hours_column_missing():
    from src.custom_dqr_engine import check_adr_a6
    df = pd.DataFrame({
        "QTY_QUANTITY": [10.0, 0.0],
        "COST_TOTAL_HOURS": [5.0, 0.0],
    })
    assert check_adr_a6(df).tolist() == [False, False]


def test_adr_a6_empty_dataframe_returns_empty_pass_series():
    from src.custom_dqr_engine import check_adr_a6
    df = pd.DataFrame({
        "QTY_QUANTITY": [],
        "COST_TOTAL_HOURS": [],
        "COST_DB_TOTAL_HOURS": [],
    })
    result = check_adr_a6(df)
    assert result.tolist() == []
    assert result.dtype == bool


def test_evaluate_custom_rules_dispatches_to_a6():
    """End-to-end: dispatcher routes an A6 assignment through check_adr_a6
    for the ADR data product."""
    df = _make_a6_df([
        {"QTY_QUANTITY": 10.0, "COST_TOTAL_HOURS": 5.0,
         "COST_DB_TOTAL_HOURS": 0.0},
        {"QTY_QUANTITY": 7.0, "COST_TOTAL_HOURS": 0.0,
         "COST_DB_TOTAL_HOURS": 0.0},
        {"QTY_QUANTITY": 0.0, "COST_TOTAL_HOURS": 0.0,
         "COST_DB_TOTAL_HOURS": 0.0},
    ])
    assignments = [CustomDQRAssignment(rule_id="A6", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ADR")
    assert "A6" in out.columns
    assert out["A6"].tolist() == [True, False, True]
    assert not_evaluated == {}


def test_adr_a6_does_not_add_reference_dataset_to_prefetch():
    """A6 has no ``reference`` dataset, so adding it must not change the
    set of references Step 2 needs to prefetch for the ADR system."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ADR"])) == {
        "VWS_GP_STANDARD_SHARE",
        "ACCE_COA_MASTER",
    }


# =============================================================================
# A7: Within-discipline quantity / hour ratio outlier (ADR; statistical rule)
# =============================================================================

def _a7_required_cols():
    return ["ITEM_TYPE", "QTY_QUANTITY", "QTY_UOM", "COST_TOTAL_HOURS"]


def _make_a7_df(rows):
    """Build an ADR-shaped denormalized DataFrame from a list of dicts.
    Missing keys default to None so the rule sees them as null."""
    cols = _a7_required_cols()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def _a7_segment_with_outlier(
    item_type: str = "EstimateFoundation",
    qty_uom: str = "CY",
    n_baseline: int = 12,
    baseline_ratio: float = 5.0,
    outlier_ratio: float = 50.0,
):
    """Build a single (ITEM_TYPE, QTY_UOM) segment with ``n_baseline``
    rows clustered tightly around ``baseline_ratio`` plus one row at
    ``outlier_ratio``. With Q1 ≈ Q3 ≈ baseline (tight cluster) the IQR
    is small, so the outlier sits well outside ``Q3 + 1.5*IQR`` and
    A7 should flag it as FAIL while every baseline row passes."""
    rows = []
    for i in range(n_baseline):
        # Mild jitter keeps IQR strictly > 0 (so the segment doesn't
        # short-circuit to PASS via the ``IQR == 0`` branch) without
        # widening the spread enough to absorb the outlier.
        ratio = baseline_ratio + (0.05 if i % 2 else -0.05)
        rows.append({
            "ITEM_TYPE": item_type,
            "QTY_UOM": qty_uom,
            "QTY_QUANTITY": 100.0,
            "COST_TOTAL_HOURS": ratio * 100.0,
        })
    rows.append({
        "ITEM_TYPE": item_type,
        "QTY_UOM": qty_uom,
        "QTY_QUANTITY": 100.0,
        "COST_TOTAL_HOURS": outlier_ratio * 100.0,
    })
    return _make_a7_df(rows)


def test_adr_has_custom_rule_a7_available():
    """ADR catalog exposes A7 as a non-blocking Statistical Outlier rule."""
    rules = get_available_custom_dqr_rules("ADR")
    by_id = {r.id: r for r in rules}
    assert "A7" in by_id
    rule = by_id["A7"]
    assert rule.type == "Statistical Outlier"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Item Type": "ITEM_TYPE",
        "Quantity": "QTY_QUANTITY",
        "Quantity UOM": "QTY_UOM",
        "Construction Hours": "COST_TOTAL_HOURS",
    }
    assert rule.reference is None


def test_adr_a7_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ADR_A7_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ADR") if r.id == "A7"
    )
    assert rule.required_columns == ADR_A7_REQUIRED_COLUMNS


def test_adr_a7_constants_are_documented_defaults():
    """The IQR multipliers and population threshold match what the
    rule documentation promises (1.5x / 3.0x / 10)."""
    from src.custom_dqr_engine import (
        ADR_A7_EXTREME_IQR_MULTIPLIER,
        ADR_A7_MILD_IQR_MULTIPLIER,
        ADR_A7_MIN_POPULATION,
    )
    assert ADR_A7_MILD_IQR_MULTIPLIER == 1.5
    assert ADR_A7_EXTREME_IQR_MULTIPLIER == 3.0
    assert ADR_A7_MIN_POPULATION == 10


def test_adr_a7_flags_outlier_in_well_populated_segment():
    """The headline scenario: 12 baseline rows clustered around ratio=5
    plus one row at ratio=50. The outlier must be FAIL; every baseline
    row must PASS."""
    from src.custom_dqr_engine import check_adr_a7
    df = _a7_segment_with_outlier(
        n_baseline=12, baseline_ratio=5.0, outlier_ratio=50.0
    )
    result = check_adr_a7(df).tolist()
    assert result[:-1] == [True] * 12   # baseline rows pass
    assert result[-1] is False          # outlier row fails


def test_adr_a7_flags_low_side_outlier_below_mild_lower_bound():
    """Outliers below ``Q1 - 1.5*IQR`` must also FAIL - A7 is two-sided."""
    from src.custom_dqr_engine import check_adr_a7
    df = _a7_segment_with_outlier(
        n_baseline=12, baseline_ratio=5.0, outlier_ratio=0.05
    )
    result = check_adr_a7(df).tolist()
    assert result[:-1] == [True] * 12
    assert result[-1] is False


def test_adr_a7_passes_when_segment_population_below_min_threshold():
    """A segment with fewer than ``ADR_A7_MIN_POPULATION`` eligible rows
    is too small to derive thresholds, every row passes."""
    from src.custom_dqr_engine import ADR_A7_MIN_POPULATION, check_adr_a7
    df = _a7_segment_with_outlier(
        n_baseline=ADR_A7_MIN_POPULATION - 2,   # 8 baseline + 1 outlier = 9
        baseline_ratio=5.0,
        outlier_ratio=50.0,
    )
    # Total rows < 10 → no segment can FAIL.
    assert check_adr_a7(df).all()


def test_adr_a7_passes_every_row_when_segment_iqr_is_zero():
    """If every eligible row in a segment has the same ratio, IQR = 0
    and the rule short-circuits to PASS (no meaningful outlier detection
    possible) - even for a row that, statistically speaking, sits on a
    spike."""
    from src.custom_dqr_engine import check_adr_a7
    rows = [
        {
            "ITEM_TYPE": "EstimateFoundation",
            "QTY_UOM": "CY",
            "QTY_QUANTITY": 100.0,
            "COST_TOTAL_HOURS": 500.0,         # ratio = 5.0 for every row
        }
        for _ in range(12)
    ]
    df = _make_a7_df(rows)
    assert check_adr_a7(df).all()


def test_adr_a7_passes_when_quantity_or_hours_are_non_positive():
    """Rows that can't produce a ratio (qty <= 0 or hours <= 0) must
    PASS regardless of segment statistics, the rule is not applicable."""
    from src.custom_dqr_engine import check_adr_a7
    # Build a populated segment so rows would otherwise be judged...
    df = _a7_segment_with_outlier(n_baseline=12, outlier_ratio=5.0)
    # ...then prepend rows that aren't eligible.
    head = _make_a7_df([
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "CY",
         "QTY_QUANTITY": 0.0,   "COST_TOTAL_HOURS": 5_000.0},
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "CY",
         "QTY_QUANTITY": 100.0, "COST_TOTAL_HOURS": 0.0},
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "CY",
         "QTY_QUANTITY": None,  "COST_TOTAL_HOURS": 5_000.0},
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "CY",
         "QTY_QUANTITY": -50.0, "COST_TOTAL_HOURS": 5_000.0},
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "CY",
         "QTY_QUANTITY": 100.0, "COST_TOTAL_HOURS": -1.0},
    ])
    df = pd.concat([head, df], ignore_index=True)
    result = check_adr_a7(df)
    # The first 5 rows are not eligible → all PASS regardless of segment.
    assert result.iloc[:5].tolist() == [True, True, True, True, True]


def test_adr_a7_passes_when_item_type_or_uom_blank():
    """Rows that can't be assigned to a (ITEM_TYPE, QTY_UOM) segment
    pass - there's no peer group to compare against."""
    from src.custom_dqr_engine import check_adr_a7
    df = _make_a7_df([
        {"ITEM_TYPE": None,                  "QTY_UOM": "CY",
         "QTY_QUANTITY": 100.0, "COST_TOTAL_HOURS": 5_000.0},
        {"ITEM_TYPE": "EstimateFoundation",  "QTY_UOM": None,
         "QTY_QUANTITY": 100.0, "COST_TOTAL_HOURS": 5_000.0},
        {"ITEM_TYPE": "   ",                 "QTY_UOM": "CY",
         "QTY_QUANTITY": 100.0, "COST_TOTAL_HOURS": 5_000.0},
        {"ITEM_TYPE": "EstimateFoundation",  "QTY_UOM": "  ",
         "QTY_QUANTITY": 100.0, "COST_TOTAL_HOURS": 5_000.0},
    ])
    assert check_adr_a7(df).tolist() == [True, True, True, True]


def test_adr_a7_segments_independently_by_item_type_and_uom():
    """An outlier in segment X must not contaminate segment Y. We build
    two well-populated segments - Foundation/CY tight around 5,
    StructuralSteel/T tight around 80, and one row in each that
    is an outlier *for its own segment* but well within the other's
    expected band. Both outliers must FAIL; baseline rows must PASS."""
    from src.custom_dqr_engine import check_adr_a7

    foundation_baseline = [
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "CY",
         "QTY_QUANTITY": 100.0,
         "COST_TOTAL_HOURS": 500.0 + (5.0 if i % 2 else -5.0)}
        for i in range(12)
    ]
    steel_baseline = [
        {"ITEM_TYPE": "EstimateStructuralSteel", "QTY_UOM": "T",
         "QTY_QUANTITY": 10.0,
         "COST_TOTAL_HOURS": 800.0 + (10.0 if i % 2 else -10.0)}
        for i in range(12)
    ]
    # Foundation outlier: ratio 80 - typical for steel, alien for foundation.
    foundation_outlier = {
        "ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "CY",
        "QTY_QUANTITY": 100.0, "COST_TOTAL_HOURS": 8_000.0,
    }
    # Steel outlier: ratio 5 - typical for foundation, alien for steel.
    steel_outlier = {
        "ITEM_TYPE": "EstimateStructuralSteel", "QTY_UOM": "T",
        "QTY_QUANTITY": 10.0, "COST_TOTAL_HOURS": 50.0,
    }

    rows = (
        foundation_baseline
        + [foundation_outlier]
        + steel_baseline
        + [steel_outlier]
    )
    df = _make_a7_df(rows)
    result = check_adr_a7(df).tolist()
    assert result[:12] == [True] * 12        # foundation baseline
    assert result[12] is False               # foundation outlier
    assert result[13:25] == [True] * 12      # steel baseline
    assert result[25] is False               # steel outlier


def test_adr_a7_does_not_cross_segments_when_uoms_differ():
    """Same ITEM_TYPE but different QTY_UOM = different segments. A row
    that is an outlier compared to ITEM_TYPE-X in feet must not be
    flagged when its UOM peer group (ITEM_TYPE-X in metres) is
    structurally tiny."""
    from src.custom_dqr_engine import check_adr_a7

    # 12 baseline rows in CY (tight around 5.0).
    foundation_cy = [
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "CY",
         "QTY_QUANTITY": 100.0,
         "COST_TOTAL_HOURS": 500.0 + (5.0 if i % 2 else -5.0)}
        for i in range(12)
    ]
    # A single row in a different UOM, its segment population is 1
    # (well below MIN_POPULATION), so even an absurd ratio passes.
    foundation_ft = {
        "ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "FT",
        "QTY_QUANTITY": 100.0, "COST_TOTAL_HOURS": 100_000.0,
    }
    df = _make_a7_df(foundation_cy + [foundation_ft])
    result = check_adr_a7(df).tolist()
    assert result == [True] * 13


def test_adr_a7_fails_for_all_rows_when_required_column_missing():
    """Schema-level structural incompleteness fails every row."""
    from src.custom_dqr_engine import check_adr_a7
    base = pd.DataFrame({
        "ITEM_TYPE": ["EstimateFoundation"] * 3,
        "QTY_QUANTITY": [100.0, 100.0, 100.0],
        "QTY_UOM": ["CY"] * 3,
        "COST_TOTAL_HOURS": [500.0, 500.0, 500.0],
    })
    for missing in _a7_required_cols():
        df = base.drop(columns=missing)
        assert check_adr_a7(df).tolist() == [False, False, False], (
            f"missing {missing} should fail every row"
        )


def test_adr_a7_empty_dataframe_returns_empty_pass_series():
    from src.custom_dqr_engine import check_adr_a7
    df = pd.DataFrame({c: [] for c in _a7_required_cols()})
    result = check_adr_a7(df)
    assert result.tolist() == []
    assert result.dtype == bool


def test_adr_a7_passes_when_no_eligible_rows_at_all():
    """Every row ineligible → no segment statistics to compute → every
    row passes (rule short-circuits before the groupby)."""
    from src.custom_dqr_engine import check_adr_a7
    df = _make_a7_df([
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "CY",
         "QTY_QUANTITY": 0.0, "COST_TOTAL_HOURS": 0.0},
        {"ITEM_TYPE": None, "QTY_UOM": None,
         "QTY_QUANTITY": 100.0, "COST_TOTAL_HOURS": 500.0},
    ])
    assert check_adr_a7(df).tolist() == [True, True]


def test_adr_a7_handles_object_dtyped_numeric_inputs():
    """Mixed string / numeric inputs must not crash. Non-numeric values
    coerce to NaN and are treated as ineligible."""
    from src.custom_dqr_engine import check_adr_a7
    rows = [
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "CY",
         "QTY_QUANTITY": "100", "COST_TOTAL_HOURS": "abc"},
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "CY",
         "QTY_QUANTITY": "abc", "COST_TOTAL_HOURS": "500"},
    ]
    df = _make_a7_df(rows)
    # Both rows have a non-numeric value somewhere → not eligible → PASS.
    assert check_adr_a7(df).tolist() == [True, True]


def test_evaluate_custom_rules_dispatches_to_a7():
    """End-to-end: dispatcher routes an A7 assignment through check_adr_a7
    for the ADR data product."""
    df = _a7_segment_with_outlier(
        n_baseline=12, baseline_ratio=5.0, outlier_ratio=50.0
    )
    assignments = [CustomDQRAssignment(rule_id="A7", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ADR")
    assert "A7" in out.columns
    assert out["A7"].tolist() == [True] * 12 + [False]
    assert not_evaluated == {}


def test_adr_a7_does_not_add_reference_dataset_to_prefetch():
    """A7 has no ``reference`` dataset, so adding it must not change the
    set of references Step 2 needs to prefetch for the ADR system."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ADR"])) == {
        "VWS_GP_STANDARD_SHARE",
        "ACCE_COA_MASTER",
    }


# -----------------------------------------------------------------------------
# A7: project-type segmentation (toggle: segment_by_project_type)
# -----------------------------------------------------------------------------


def _a7_required_cols_with_planview():
    return _a7_required_cols() + ["PLANVIEW_ID"]


def _make_a7_segmented_df(rows):
    """Build an ADR-shaped DataFrame that also carries ``PLANVIEW_ID`` so the
    A7 segment-by-project-type lookup can resolve each row to a segment.
    Missing keys default to None so the rule sees them as null."""
    cols = _a7_required_cols_with_planview()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def _a7_segment_reference(rows):
    """Build a Planview reference DataFrame with the segmentation columns
    A7 reads when the segment-by-project-type toggle is on.

    ``rows`` is a list of ``(PROJECT_ID, E05_DEPARTMENT, BUSINESS)`` tuples.
    """
    return pd.DataFrame(
        rows, columns=["PROJECT_ID", "E05_DEPARTMENT", "BUSINESS"]
    )


def _a7_baseline_rows(
    planview_prefix: str,
    item_type: str = "EstimateFoundation",
    qty_uom: str = "CY",
    n: int = 12,
    ratio: float = 5.0,
):
    """Build ``n`` rows clustered tightly around ``ratio`` for one
    discipline. Mild jitter keeps IQR > 0 so the segment isn't short-
    circuited via the ``IQR == 0`` PASS branch."""
    rows = []
    for i in range(n):
        jitter = 0.05 if i % 2 else -0.05
        rows.append({
            "PLANVIEW_ID": f"{planview_prefix}-{i}",
            "ITEM_TYPE": item_type,
            "QTY_UOM": qty_uom,
            "QTY_QUANTITY": 100.0,
            "COST_TOTAL_HOURS": (ratio + jitter) * 100.0,
        })
    return rows


def test_adr_a7_segment_param_constants_match_catalog():
    """The segmentation toggle exposed on the A7 catalog rule card carries
    the same key the engine reads from ``params``, and the rule declares
    PLANVIEW_ID as a required-when-enabled column."""
    from src.custom_dqr_engine import ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM
    rule = next(
        r for r in get_available_custom_dqr_rules("ADR") if r.id == "A7"
    )
    by_key = {opt.key: opt for opt in rule.options}
    assert ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM in by_key
    opt = by_key[ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM]
    # PLANVIEW_ID is needed only when the toggle is on (it is not in the
    # static A7 required_columns) - Step 4.2's CDE-coverage check picks
    # this up via ``effective_required_columns``.
    assert "PLANVIEW_ID" in opt.required_columns_when_enabled.values()


def test_adr_a7_segmented_isolates_outliers_per_segment(monkeypatch):
    """With segmentation on, an outlier within its own (BROWN/UPSTREAM)
    segment is flagged even though it would look in-band against the
    discipline-only population. Two segments with distinct ratios are
    kept separate, so a row that is "normal" for FPSO does not get
    judged against a refinery baseline."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_adr_a7,
    )

    # Same discipline (Foundation/CY) across the two project types, but
    # the typical hours-per-quantity ratio differs by segment.
    seg_a = _a7_baseline_rows(planview_prefix="P-A", n=12, ratio=5.0)
    seg_b = _a7_baseline_rows(planview_prefix="P-B", n=12, ratio=50.0)
    # Outlier *within segment A*: ratio 50 looks normal globally
    # (matches segment B's centre) but is a huge outlier in segment A.
    seg_a.append({
        "PLANVIEW_ID": "P-A-OUT",
        "ITEM_TYPE": "EstimateFoundation",
        "QTY_UOM": "CY",
        "QTY_QUANTITY": 100.0,
        "COST_TOTAL_HOURS": 5_000.0,
    })

    ref_rows = (
        [(f"P-A-{k}", "BROWNFIELD", "UPSTREAM") for k in range(12)]
        + [("P-A-OUT", "BROWNFIELD", "UPSTREAM")]
        + [(f"P-B-{k}", "GREENFIELD", "DOWNSTREAM") for k in range(12)]
    )
    ref_df = _a7_segment_reference(ref_rows)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: ref_df
    )

    df = _make_a7_segmented_df(seg_a + seg_b)
    result = check_adr_a7(
        df, params={ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # Segment A baseline rows pass; the within-segment outlier fails.
    assert result.iloc[:12].all()
    assert not bool(result.iloc[12])
    # Segment B rows all pass (their own segment is uniform).
    assert result.iloc[13:].all()


def test_adr_a7_segmented_passes_when_segment_population_below_minimum(monkeypatch):
    """A `(ITEM_TYPE, QTY_UOM, E05_DEPARTMENT, BUSINESS)` segment whose
    eligible-row count is below ``ADR_A7_MIN_POPULATION`` is NOT_APPLICABLE
    → PASS, even when one of its rows has a ratio that would obviously
    fail against the discipline-wide IQR."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ADR_A7_MIN_POPULATION,
        ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_adr_a7,
    )

    # Well-populated decoy segment A + tiny segment B (under the floor)
    seg_a = _a7_baseline_rows(planview_prefix="P-A", n=12, ratio=5.0)
    seg_b = _a7_baseline_rows(
        planview_prefix="P-B", n=ADR_A7_MIN_POPULATION - 2, ratio=5.0
    )
    seg_b.append({
        "PLANVIEW_ID": "P-B-OUT",
        "ITEM_TYPE": "EstimateFoundation",
        "QTY_UOM": "CY",
        "QTY_QUANTITY": 100.0,
        "COST_TOTAL_HOURS": 50_000.0,        # ratio 500 - would fail globally
    })

    ref_rows = (
        [(f"P-A-{k}", "BROWNFIELD", "UPSTREAM") for k in range(12)]
        + [
            (f"P-B-{k}", "GREENFIELD", "LNG")
            for k in range(ADR_A7_MIN_POPULATION - 2)
        ]
        + [("P-B-OUT", "GREENFIELD", "LNG")]
    )
    ref_df = _a7_segment_reference(ref_rows)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: ref_df
    )

    df = _make_a7_segmented_df(seg_a + seg_b)
    result = check_adr_a7(
        df, params={ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # Segment A is uniform (passes); segment B is under the floor (passes).
    assert result.all()


def test_adr_a7_segmented_passes_rows_without_resolved_segment(monkeypatch):
    """Rows whose PLANVIEW_ID does not match the reference, or whose matched
    segment has a null/blank ``E05_DEPARTMENT`` / ``BUSINESS``, are
    NOT_APPLICABLE → PASS so segmentation never double-penalises the
    referential-integrity gap A2 / blocking A1 already cover."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_adr_a7,
    )

    seg_a = _a7_baseline_rows(planview_prefix="P-A", n=12, ratio=5.0)
    # ORPHAN belongs nowhere - stripped from the reference. Without the
    # segmentation toggle the row would fail (ratio 500 vs cluster of 5);
    # with the toggle on, it is NOT_APPLICABLE → PASS.
    seg_a.append({
        "PLANVIEW_ID": "P-A-ORPHAN",
        "ITEM_TYPE": "EstimateFoundation",
        "QTY_UOM": "CY",
        "QTY_QUANTITY": 100.0,
        "COST_TOTAL_HOURS": 50_000.0,
    })
    # NULL has a matched row but a null segment column.
    seg_a.append({
        "PLANVIEW_ID": "P-A-NULL",
        "ITEM_TYPE": "EstimateFoundation",
        "QTY_UOM": "CY",
        "QTY_QUANTITY": 100.0,
        "COST_TOTAL_HOURS": 50_000.0,
    })
    # Row with a null PLANVIEW_ID - also NOT_APPLICABLE → PASS.
    seg_a.append({
        "PLANVIEW_ID": None,
        "ITEM_TYPE": "EstimateFoundation",
        "QTY_UOM": "CY",
        "QTY_QUANTITY": 100.0,
        "COST_TOTAL_HOURS": 50_000.0,
    })

    ref_rows = (
        [(f"P-A-{k}", "BROWNFIELD", "UPSTREAM") for k in range(12)]
        + [("P-A-NULL", None, "UPSTREAM")]
    )
    ref_df = _a7_segment_reference(ref_rows)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: ref_df
    )

    df = _make_a7_segmented_df(seg_a)
    result = check_adr_a7(
        df, params={ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # All baseline rows pass (uniform segment) AND every unresolved row
    # passes too, they are NOT_APPLICABLE in segmented mode.
    assert result.all()


def test_adr_a7_segmented_raises_not_evaluated_when_reference_unavailable(
    monkeypatch,
):
    """With segmentation on, an absent ``VWS_GP_STANDARD_SHARE`` reference
    must raise :class:`CustomRuleNotEvaluated` - never silently fall back
    to the discipline-only IQR baseline."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM,
        CustomRuleNotEvaluated,
        check_adr_a7,
    )

    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset_error", lambda name: "network down"
    )

    df = _make_a7_segmented_df(
        _a7_baseline_rows(planview_prefix="P-A", n=12, ratio=5.0)
    )
    with pytest.raises(CustomRuleNotEvaluated):
        check_adr_a7(
            df, params={ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
        )


def test_adr_a7_unsegmented_does_not_touch_reference(monkeypatch):
    """Default (segmentation off) must not consult the reference dataset
    at all, the legacy (ITEM_TYPE, QTY_UOM)-only path keeps its standalone
    behaviour and never blows up when the reference is missing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_adr_a7

    def _boom(_name):
        raise AssertionError(
            "Unsegmented A7 must not call get_reference_dataset"
        )

    monkeypatch.setattr(ref_mod, "get_reference_dataset", _boom)
    df = _make_a7_segmented_df(
        _a7_baseline_rows(planview_prefix="P-A", n=12, ratio=5.0)
    )
    # No outlier, so the rule passes regardless of segmentation, the
    # point of this test is that it does not call get_reference_dataset.
    assert check_adr_a7(df).all()


def test_adr_a7_segmented_fails_when_planview_id_column_missing(monkeypatch):
    """With segmentation on, PLANVIEW_ID becomes a structurally required
    column, the rule fails every row when it is missing, mirroring the
    schema-incomplete convention used by the static required-columns
    check."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_adr_a7,
    )

    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: _a7_segment_reference([])
    )

    rows = _a7_baseline_rows(planview_prefix="P-A", n=12, ratio=5.0)
    df = _make_a7_segmented_df(rows).drop(columns="PLANVIEW_ID")
    result = check_adr_a7(
        df, params={ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    assert (~result).all()


# =============================================================================
# A8: Cross-discipline quantity ratios (ADR; project-level statistical rule)
# =============================================================================

def _a8_required_cols():
    return ["ITEM_TYPE", "ROOT_ITEM_NAME", "QTY_QUANTITY", "QTY_UOM"]


def _make_a8_df(rows):
    """Build an ADR-shaped denormalized DataFrame from a list of dicts.
    Missing keys default to None so the rule sees them as null."""
    cols = _a8_required_cols()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def _a8_steel_concrete_population(
    n_normal: int = 12,
    normal_steel: float = 100.0,
    normal_concrete: float = 50.0,
    outlier_project: str = "PROJECT-OUTLIER",
    outlier_steel: float = 100.0,
    outlier_concrete: float = 5.0,
):
    """Build an A8-shaped DataFrame containing two rows per project
    (one steel, one concrete), with ``n_normal`` projects clustered
    tightly around the same ratio plus one project whose ratio is far
    outside the mild IQR bound. Returns the DataFrame ready for
    ``check_adr_a8``."""
    rows = []
    for i in range(n_normal):
        proj = f"PROJECT-{i:03d}"
        # Tight jitter keeps IQR > 0 without absorbing the outlier.
        jitter = 0.5 if i % 2 else -0.5
        rows.append({
            "ITEM_TYPE": "EstimateSteelStructure", "QTY_UOM": "t",
            "ROOT_ITEM_NAME": proj,
            "QTY_QUANTITY": normal_steel + jitter,
        })
        rows.append({
            "ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "yd³",
            "ROOT_ITEM_NAME": proj,
            "QTY_QUANTITY": normal_concrete - jitter,
        })
    rows.append({
        "ITEM_TYPE": "EstimateSteelStructure", "QTY_UOM": "t",
        "ROOT_ITEM_NAME": outlier_project,
        "QTY_QUANTITY": outlier_steel,
    })
    rows.append({
        "ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "yd³",
        "ROOT_ITEM_NAME": outlier_project,
        "QTY_QUANTITY": outlier_concrete,
    })
    return _make_a8_df(rows), outlier_project


# ----- Catalog metadata ------------------------------------------------------

def test_adr_has_custom_rule_a8_available():
    """ADR catalog exposes A8 as a non-blocking Statistical Outlier rule."""
    rules = get_available_custom_dqr_rules("ADR")
    by_id = {r.id: r for r in rules}
    assert "A8" in by_id
    rule = by_id["A8"]
    assert rule.type == "Statistical Outlier"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Item Type": "ITEM_TYPE",
        "Root Item Name": "ROOT_ITEM_NAME",
        "Quantity": "QTY_QUANTITY",
        "Quantity UOM": "QTY_UOM",
    }
    assert rule.reference is None


def test_adr_a8_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import ADR_A8_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("ADR") if r.id == "A8"
    )
    assert rule.required_columns == ADR_A8_REQUIRED_COLUMNS


def test_adr_a8_constants_are_documented_defaults():
    from src.custom_dqr_engine import (
        ADR_A8_EXTREME_IQR_MULTIPLIER,
        ADR_A8_MILD_IQR_MULTIPLIER,
        ADR_A8_MIN_POPULATION,
    )
    assert ADR_A8_MILD_IQR_MULTIPLIER == 1.5
    assert ADR_A8_EXTREME_IQR_MULTIPLIER == 3.0
    assert ADR_A8_MIN_POPULATION == 10


# ----- Discipline classifier -------------------------------------------------

def test_a8_classifier_steel_weight_takes_precedence_over_pipe_length():
    """``EstimatePiperack`` contains "Pipe", but with a weight UOM the
    classifier must resolve to STEEL_WEIGHT (the weight-UOM filter is
    checked before the length-UOM filter)."""
    from src.custom_dqr_engine import _classify_a8_category
    assert _classify_a8_category("EstimatePiperack", "t") == "STEEL_WEIGHT"
    assert _classify_a8_category("EstimateSteelStructure", "t,sht") == "STEEL_WEIGHT"


def test_a8_classifier_pipe_length_for_piping_with_length_uom():
    from src.custom_dqr_engine import _classify_a8_category
    assert _classify_a8_category(
        "EstimateAbovegroundInstrumentPiping", "ft"
    ) == "PIPE_LENGTH"
    assert _classify_a8_category(
        "EstimatePipingUnderground", "m"
    ) == "PIPE_LENGTH"


def test_a8_classifier_concrete_volume_aliases_for_cy_yds3():
    """``CY``, ``yds³``, and ``yd³`` should all resolve to the same
    CONCRETE_VOLUME category, the spec lists them as equivalent
    spellings."""
    from src.custom_dqr_engine import _classify_a8_category
    for uom in ("yd³", "yds³", "CY", "cy"):
        assert _classify_a8_category("EstimateFoundation", uom) == "CONCRETE_VOLUME"


def test_a8_classifier_cable_length_and_transmitter_count():
    from src.custom_dqr_engine import _classify_a8_category
    assert _classify_a8_category(
        "EstimateElectricalPowerGroup", "ft"
    ) == "CABLE_LENGTH"
    assert _classify_a8_category(
        "EstimateFieldInstrumentGroup", "m"
    ) == "CABLE_LENGTH"
    # FieldInstrument + a count UOM falls into TRANSMITTER_COUNT (not
    # CABLE_LENGTH) when the UOM is one of the documented instrument
    # count labels.
    assert _classify_a8_category(
        "EstimateFieldInstrumentGroup", "Pressure Gauges"
    ) == "TRANSMITTER_COUNT"


def test_a8_classifier_equipment_count_only_for_known_types_with_count_uom():
    """EQUIPMENT_COUNT is gated to a closed list of major equipment
    ITEM_TYPEs, AND requires a UOM that is *not* a length / area /
    volume / weight / known subcomponent label."""
    from src.custom_dqr_engine import _classify_a8_category
    assert _classify_a8_category("EstimatePump", "EA") == "EQUIPMENT_COUNT"
    assert _classify_a8_category(
        "EstimateGasTurbine", "Units"
    ) == "EQUIPMENT_COUNT"
    # Excluded UOM (length): not equipment count.
    assert _classify_a8_category("EstimatePump", "ft") is None
    # Excluded UOM (subcomponent): not equipment count.
    assert _classify_a8_category("EstimatePump", "Nozzles") is None
    # Item type not on the list - even with a sensible UOM.
    assert _classify_a8_category("EstimateMystery", "EA") is None


def test_a8_classifier_returns_none_on_blank_or_unrecognised_inputs():
    from src.custom_dqr_engine import _classify_a8_category
    assert _classify_a8_category(None, "ft") is None
    assert _classify_a8_category("EstimatePiping", None) is None
    assert _classify_a8_category("", "ft") is None
    assert _classify_a8_category("EstimatePiping", "  ") is None
    assert _classify_a8_category("RandomText", "RandomUOM") is None


# ----- check_adr_a8 - happy & NOT_APPLICABLE paths ---------------------------

def test_adr_a8_flags_outlier_project_in_well_populated_population():
    """The headline scenario: 12 projects clustered around steel/concrete
    ratio = 2.0 plus one outlier project at ratio = 20.0. Every row of
    the outlier project must FAIL; every row of the normal projects
    must PASS."""
    from src.custom_dqr_engine import check_adr_a8
    df, outlier_project = _a8_steel_concrete_population(
        n_normal=12,
        normal_steel=100.0,
        normal_concrete=50.0,
        outlier_steel=100.0,
        outlier_concrete=5.0,   # ratio = 20 - far above Q3 + 1.5*IQR
    )
    result = check_adr_a8(df)
    is_outlier = df["ROOT_ITEM_NAME"] == outlier_project
    assert (~result[is_outlier]).all()
    assert result[~is_outlier].all()


def test_adr_a8_passes_every_row_when_population_below_min():
    """Fewer than ADR_A8_MIN_POPULATION projects → no ratio can flag, every row passes."""
    from src.custom_dqr_engine import ADR_A8_MIN_POPULATION, check_adr_a8
    df, _ = _a8_steel_concrete_population(
        n_normal=ADR_A8_MIN_POPULATION - 2,   # 8 normal + 1 outlier = 9
        outlier_concrete=5.0,
    )
    assert check_adr_a8(df).all()


def test_adr_a8_passes_when_population_iqr_is_zero():
    """If every project's ratio is the same, IQR = 0 and the rule
    short-circuits to PASS for that ratio, every row passes."""
    from src.custom_dqr_engine import check_adr_a8
    rows = []
    for i in range(15):
        proj = f"PROJECT-{i:03d}"
        rows.append({
            "ITEM_TYPE": "EstimateSteelStructure", "QTY_UOM": "t",
            "ROOT_ITEM_NAME": proj, "QTY_QUANTITY": 100.0,
        })
        rows.append({
            "ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "yd³",
            "ROOT_ITEM_NAME": proj, "QTY_QUANTITY": 50.0,
        })
    # All ratios = 2.0 exactly → IQR = 0 → no project can be flagged.
    df = _make_a8_df(rows)
    assert check_adr_a8(df).all()


def test_adr_a8_passes_rows_with_blank_root_item_name():
    """A row whose ROOT_ITEM_NAME is null/blank can't be assigned to a
    project group, so it always PASSes regardless of how its peer
    projects are doing."""
    from src.custom_dqr_engine import check_adr_a8
    df, outlier_project = _a8_steel_concrete_population(outlier_concrete=5.0)
    extra = _make_a8_df([
        {"ITEM_TYPE": "EstimateSteelStructure", "QTY_UOM": "t",
         "ROOT_ITEM_NAME": None,    "QTY_QUANTITY": 50.0},
        {"ITEM_TYPE": "EstimateSteelStructure", "QTY_UOM": "t",
         "ROOT_ITEM_NAME": "   ",   "QTY_QUANTITY": 50.0},
    ])
    df = pd.concat([extra, df], ignore_index=True)
    result = check_adr_a8(df)
    assert result.iloc[:2].tolist() == [True, True]


def test_adr_a8_passes_when_quantity_non_positive():
    """Rows with zero / null / negative quantity are not eligible for
    aggregation, they don't contribute to any ratio. Their project's
    pass/fail is decided only by the eligible rows."""
    from src.custom_dqr_engine import check_adr_a8
    df, outlier_project = _a8_steel_concrete_population(outlier_concrete=5.0)
    # Add a few non-positive-qty rows in random projects, they must be
    # ignored by the aggregation, not crash the rule.
    extra = _make_a8_df([
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "yd³",
         "ROOT_ITEM_NAME": "PROJECT-000", "QTY_QUANTITY": 0.0},
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "yd³",
         "ROOT_ITEM_NAME": "PROJECT-001", "QTY_QUANTITY": None},
        {"ITEM_TYPE": "EstimateFoundation", "QTY_UOM": "yd³",
         "ROOT_ITEM_NAME": "PROJECT-002", "QTY_QUANTITY": -5.0},
    ])
    df = pd.concat([df, extra], ignore_index=True)
    result = check_adr_a8(df)
    is_outlier = df["ROOT_ITEM_NAME"] == outlier_project
    # Outlier project still flagged; the new "PROJECT-000/001/002" rows
    # belong to passing projects, so they pass.
    assert (~result[is_outlier]).all()
    assert result[~is_outlier].all()


def test_adr_a8_unrecognised_classification_does_not_contribute_to_any_ratio():
    """A row whose ITEM_TYPE / QTY_UOM isn't a known discipline falls
    through the classifier and contributes to no ratio, its project
    is judged only by the rows that *did* classify."""
    from src.custom_dqr_engine import check_adr_a8
    df, outlier_project = _a8_steel_concrete_population(outlier_concrete=5.0)
    extra = _make_a8_df([
        {"ITEM_TYPE": "EstimateMystery", "QTY_UOM": "Widgets",
         "ROOT_ITEM_NAME": outlier_project, "QTY_QUANTITY": 1_000_000.0},
    ])
    df = pd.concat([df, extra], ignore_index=True)
    # Classifier returns None for the new row → no influence on ratios.
    # The outlier project is still flagged (its 100 t / 5 yd³ ratio).
    result = check_adr_a8(df)
    assert (~result[df["ROOT_ITEM_NAME"] == outlier_project]).all()


def test_adr_a8_population_is_per_ratio_not_global():
    """Each ratio defines its own population. A pipe/equipment
    population that's too small must not block flagging on a
    well-populated steel/concrete population."""
    from src.custom_dqr_engine import check_adr_a8
    # 12 projects with steel/concrete (well-populated, with one outlier)
    base, outlier_project = _a8_steel_concrete_population(
        n_normal=12, outlier_concrete=5.0,
    )
    # Two extra projects with pipe/equipment ratios - well below the min
    # population threshold. The rule must ignore that ratio entirely.
    extra = _make_a8_df([
        {"ITEM_TYPE": "EstimatePipingUnderground", "QTY_UOM": "ft",
         "ROOT_ITEM_NAME": "PROJECT-000", "QTY_QUANTITY": 1000.0},
        {"ITEM_TYPE": "EstimatePump", "QTY_UOM": "EA",
         "ROOT_ITEM_NAME": "PROJECT-000", "QTY_QUANTITY": 5.0},
    ])
    df = pd.concat([base, extra], ignore_index=True)
    result = check_adr_a8(df)
    # Steel/concrete outlier still flagged.
    assert (~result[df["ROOT_ITEM_NAME"] == outlier_project]).all()


# ----- check_adr_a8 - schema-level / structural failures ---------------------

def test_adr_a8_fails_for_all_rows_when_required_column_missing():
    from src.custom_dqr_engine import check_adr_a8
    base = pd.DataFrame({
        "ITEM_TYPE": ["EstimateSteelStructure"] * 3,
        "ROOT_ITEM_NAME": ["P1"] * 3,
        "QTY_QUANTITY": [100.0, 100.0, 100.0],
        "QTY_UOM": ["t"] * 3,
    })
    for missing in _a8_required_cols():
        df = base.drop(columns=missing)
        assert check_adr_a8(df).tolist() == [False, False, False], (
            f"missing {missing} should fail every row"
        )


def test_adr_a8_empty_dataframe_returns_empty_pass_series():
    from src.custom_dqr_engine import check_adr_a8
    df = pd.DataFrame({c: [] for c in _a8_required_cols()})
    result = check_adr_a8(df)
    assert result.tolist() == []
    assert result.dtype == bool


def test_adr_a8_passes_when_no_eligible_rows_exist():
    """All rows ineligible (zero qty / blank inputs) → no aggregation,
    no ratio computed, every row passes."""
    from src.custom_dqr_engine import check_adr_a8
    df = _make_a8_df([
        {"ITEM_TYPE": "EstimateSteelStructure", "QTY_UOM": "t",
         "ROOT_ITEM_NAME": "P1", "QTY_QUANTITY": 0.0},
        {"ITEM_TYPE": None, "QTY_UOM": "t",
         "ROOT_ITEM_NAME": "P2", "QTY_QUANTITY": 100.0},
    ])
    assert check_adr_a8(df).tolist() == [True, True]


def test_adr_a8_handles_object_dtyped_numeric_inputs():
    """Mixed string / numeric inputs must coerce cleanly - non-numeric
    quantities become NaN and are treated as ineligible."""
    from src.custom_dqr_engine import check_adr_a8
    df = _make_a8_df([
        {"ITEM_TYPE": "EstimateSteelStructure", "QTY_UOM": "t",
         "ROOT_ITEM_NAME": "P1", "QTY_QUANTITY": "100"},
        {"ITEM_TYPE": "EstimateSteelStructure", "QTY_UOM": "t",
         "ROOT_ITEM_NAME": "P1", "QTY_QUANTITY": "abc"},
    ])
    # Population is too small (1 project, 1 ratio impossible) → all PASS.
    assert check_adr_a8(df).all()


def test_evaluate_custom_rules_dispatches_to_a8():
    """End-to-end: dispatcher routes an A8 assignment through check_adr_a8."""
    df, outlier_project = _a8_steel_concrete_population(outlier_concrete=5.0)
    assignments = [CustomDQRAssignment(rule_id="A8", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "ADR")
    assert "A8" in out.columns
    is_outlier = df["ROOT_ITEM_NAME"] == outlier_project
    assert (~out["A8"][is_outlier]).all()
    assert out["A8"][~is_outlier].all()
    assert not_evaluated == {}


def test_adr_a8_does_not_add_reference_dataset_to_prefetch():
    """A8 has no ``reference`` dataset, so the ADR system's prefetch
    list is the same one A1 + A2 already require."""
    from src.reference_data import required_reference_datasets_for_systems
    assert set(required_reference_datasets_for_systems(["ADR"])) == {
        "VWS_GP_STANDARD_SHARE",
        "ACCE_COA_MASTER",
    }


# -----------------------------------------------------------------------------
# A8: project-type segmentation (toggle: segment_by_project_type)
# -----------------------------------------------------------------------------


def _a8_required_cols_with_planview():
    return _a8_required_cols() + ["PLANVIEW_ID"]


def _make_a8_segmented_df(rows):
    """Build an A8-shaped DataFrame that also carries ``PLANVIEW_ID`` so
    the segment-by-project-type lookup can resolve each project to a
    segment. Missing keys default to None so the rule sees them as null."""
    cols = _a8_required_cols_with_planview()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def _a8_segment_reference(rows):
    """Build a Planview reference DataFrame with the segmentation columns
    A8 reads when the segment-by-project-type toggle is on.

    ``rows`` is a list of ``(PROJECT_ID, E05_DEPARTMENT, BUSINESS)`` tuples.
    """
    return pd.DataFrame(
        rows, columns=["PROJECT_ID", "E05_DEPARTMENT", "BUSINESS"]
    )


def _a8_steel_concrete_segment_rows(
    n_projects: int,
    project_prefix: str,
    planview_prefix: str,
    normal_steel: float = 100.0,
    normal_concrete: float = 50.0,
):
    """Build ``n_projects`` projects each contributing one steel + one
    concrete row at the documented tight cluster (ratio ≈ 2.0). Each
    project carries a stable PLANVIEW_ID drawn from ``planview_prefix``
    so the segmentation lookup can resolve every project to a segment."""
    rows = []
    for i in range(n_projects):
        proj = f"{project_prefix}-{i:03d}"
        pv = f"{planview_prefix}-{i:03d}"
        jitter = 0.5 if i % 2 else -0.5
        rows.append({
            "PLANVIEW_ID": pv,
            "ROOT_ITEM_NAME": proj,
            "ITEM_TYPE": "EstimateSteelStructure",
            "QTY_UOM": "t",
            "QTY_QUANTITY": normal_steel + jitter,
        })
        rows.append({
            "PLANVIEW_ID": pv,
            "ROOT_ITEM_NAME": proj,
            "ITEM_TYPE": "EstimateFoundation",
            "QTY_UOM": "yd³",
            "QTY_QUANTITY": normal_concrete - jitter,
        })
    return rows


def test_adr_a8_segment_param_constants_match_catalog():
    """The segmentation toggle exposed on the A8 catalog rule card carries
    the same key the engine reads from ``params``, and the rule declares
    PLANVIEW_ID as a required-when-enabled column."""
    from src.custom_dqr_engine import ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM
    rule = next(
        r for r in get_available_custom_dqr_rules("ADR") if r.id == "A8"
    )
    by_key = {opt.key: opt for opt in rule.options}
    assert ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM in by_key
    opt = by_key[ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM]
    # PLANVIEW_ID is needed only when the toggle is on (it is not in the
    # static A8 required_columns) - Step 4.2's CDE-coverage check picks
    # this up via ``effective_required_columns``.
    assert "PLANVIEW_ID" in opt.required_columns_when_enabled.values()


def test_adr_a8_segmented_isolates_outliers_per_segment(monkeypatch):
    """With segmentation on, an outlier within its own (BROWN/UPSTREAM)
    segment is flagged even though it would look in-band against the
    global population. Two segments with distinct steel/concrete ratios
    are kept separate, so a row that is "normal" for FPSO does not get
    judged against a refinery baseline."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_adr_a8,
    )

    # Segment A: steel/concrete ratio ≈ 2.0 across 12 projects.
    seg_a = _a8_steel_concrete_segment_rows(
        n_projects=12,
        project_prefix="PROJ-A",
        planview_prefix="P-A",
        normal_steel=100.0,
        normal_concrete=50.0,
    )
    # Segment B: ratio ≈ 20.0, the "FPSO" archetype where steel
    # dominates over concrete. Twelve projects keep IQR > 0.
    seg_b = _a8_steel_concrete_segment_rows(
        n_projects=12,
        project_prefix="PROJ-B",
        planview_prefix="P-B",
        normal_steel=200.0,
        normal_concrete=10.0,
    )
    # Outlier within segment A: ratio 20 - looks "normal" globally
    # (matches segment B) but is a huge outlier in segment A's IQR.
    seg_a.append({
        "PLANVIEW_ID": "P-A-OUT",
        "ROOT_ITEM_NAME": "PROJ-A-OUT",
        "ITEM_TYPE": "EstimateSteelStructure",
        "QTY_UOM": "t",
        "QTY_QUANTITY": 100.0,
    })
    seg_a.append({
        "PLANVIEW_ID": "P-A-OUT",
        "ROOT_ITEM_NAME": "PROJ-A-OUT",
        "ITEM_TYPE": "EstimateFoundation",
        "QTY_UOM": "yd³",
        "QTY_QUANTITY": 5.0,
    })

    ref_rows = (
        [(f"P-A-{k:03d}", "BROWNFIELD", "UPSTREAM") for k in range(12)]
        + [("P-A-OUT", "BROWNFIELD", "UPSTREAM")]
        + [(f"P-B-{k:03d}", "GREENFIELD", "DOWNSTREAM") for k in range(12)]
    )
    ref_df = _a8_segment_reference(ref_rows)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: ref_df
    )

    df = _make_a8_segmented_df(seg_a + seg_b)
    result = check_adr_a8(
        df, params={ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # Every row of the A-OUT project fails; every other row passes.
    is_outlier = df["ROOT_ITEM_NAME"] == "PROJ-A-OUT"
    assert (~result[is_outlier]).all()
    assert result[~is_outlier].all()


def test_adr_a8_segmented_passes_when_segment_population_below_minimum(monkeypatch):
    """A segment whose project count is below ``ADR_A8_MIN_POPULATION``
    is NOT_APPLICABLE → PASS, even when one of its projects has a ratio
    that would obviously fail against the global IQR."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ADR_A8_MIN_POPULATION,
        ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_adr_a8,
    )

    # Well-populated decoy segment A + tiny segment B (under the floor).
    seg_a = _a8_steel_concrete_segment_rows(
        n_projects=12, project_prefix="PROJ-A", planview_prefix="P-A",
    )
    seg_b = _a8_steel_concrete_segment_rows(
        n_projects=ADR_A8_MIN_POPULATION - 2,
        project_prefix="PROJ-B", planview_prefix="P-B",
    )
    seg_b.append({
        "PLANVIEW_ID": "P-B-OUT",
        "ROOT_ITEM_NAME": "PROJ-B-OUT",
        "ITEM_TYPE": "EstimateSteelStructure",
        "QTY_UOM": "t",
        "QTY_QUANTITY": 100.0,
    })
    seg_b.append({
        "PLANVIEW_ID": "P-B-OUT",
        "ROOT_ITEM_NAME": "PROJ-B-OUT",
        "ITEM_TYPE": "EstimateFoundation",
        "QTY_UOM": "yd³",
        "QTY_QUANTITY": 1.0,                  # ratio = 100 - would fail globally
    })

    ref_rows = (
        [(f"P-A-{k:03d}", "BROWNFIELD", "UPSTREAM") for k in range(12)]
        + [
            (f"P-B-{k:03d}", "GREENFIELD", "LNG")
            for k in range(ADR_A8_MIN_POPULATION - 2)
        ]
        + [("P-B-OUT", "GREENFIELD", "LNG")]
    )
    ref_df = _a8_segment_reference(ref_rows)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: ref_df
    )

    df = _make_a8_segmented_df(seg_a + seg_b)
    result = check_adr_a8(
        df, params={ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # Segment A is uniform (passes); segment B is under the floor (passes).
    assert result.all()


def test_adr_a8_segmented_passes_projects_without_resolved_segment(monkeypatch):
    """Projects whose PLANVIEW_ID does not match the reference, or whose
    matched segment has a null/blank ``E05_DEPARTMENT`` / ``BUSINESS``,
    are NOT_APPLICABLE → PASS so segmentation never double-penalises the
    referential / completeness gap A1 / A2 already cover."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_adr_a8,
    )

    seg_a = _a8_steel_concrete_segment_rows(
        n_projects=12, project_prefix="PROJ-A", planview_prefix="P-A",
    )
    # Orphan project: PLANVIEW_ID is not in the reference. Its ratio (20)
    # would clearly fail against segment A globally, but in segmented mode
    # the project is NOT_APPLICABLE → PASS.
    seg_a.append({
        "PLANVIEW_ID": "P-A-ORPHAN",
        "ROOT_ITEM_NAME": "PROJ-A-ORPHAN",
        "ITEM_TYPE": "EstimateSteelStructure",
        "QTY_UOM": "t",
        "QTY_QUANTITY": 100.0,
    })
    seg_a.append({
        "PLANVIEW_ID": "P-A-ORPHAN",
        "ROOT_ITEM_NAME": "PROJ-A-ORPHAN",
        "ITEM_TYPE": "EstimateFoundation",
        "QTY_UOM": "yd³",
        "QTY_QUANTITY": 5.0,
    })
    # Null-segment project: matched in the reference but E05_DEPARTMENT is null.
    seg_a.append({
        "PLANVIEW_ID": "P-A-NULL",
        "ROOT_ITEM_NAME": "PROJ-A-NULL",
        "ITEM_TYPE": "EstimateSteelStructure",
        "QTY_UOM": "t",
        "QTY_QUANTITY": 100.0,
    })
    seg_a.append({
        "PLANVIEW_ID": "P-A-NULL",
        "ROOT_ITEM_NAME": "PROJ-A-NULL",
        "ITEM_TYPE": "EstimateFoundation",
        "QTY_UOM": "yd³",
        "QTY_QUANTITY": 5.0,
    })
    # Project with no PLANVIEW_ID at all on any row.
    seg_a.append({
        "PLANVIEW_ID": None,
        "ROOT_ITEM_NAME": "PROJ-A-NOPV",
        "ITEM_TYPE": "EstimateSteelStructure",
        "QTY_UOM": "t",
        "QTY_QUANTITY": 100.0,
    })
    seg_a.append({
        "PLANVIEW_ID": None,
        "ROOT_ITEM_NAME": "PROJ-A-NOPV",
        "ITEM_TYPE": "EstimateFoundation",
        "QTY_UOM": "yd³",
        "QTY_QUANTITY": 5.0,
    })

    ref_rows = (
        [(f"P-A-{k:03d}", "BROWNFIELD", "UPSTREAM") for k in range(12)]
        + [("P-A-NULL", None, "UPSTREAM")]
    )
    ref_df = _a8_segment_reference(ref_rows)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: ref_df
    )

    df = _make_a8_segmented_df(seg_a)
    result = check_adr_a8(
        df, params={ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # All baseline rows pass (uniform segment); every unresolved row passes
    # too, they are NOT_APPLICABLE in segmented mode.
    assert result.all()


def test_adr_a8_segmented_raises_not_evaluated_when_reference_unavailable(
    monkeypatch,
):
    """With segmentation on, an absent ``VWS_GP_STANDARD_SHARE`` reference
    must raise :class:`CustomRuleNotEvaluated` - never silently fall back
    to the global IQR baseline."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM,
        CustomRuleNotEvaluated,
        check_adr_a8,
    )

    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset_error", lambda name: "network down"
    )

    df = _make_a8_segmented_df(
        _a8_steel_concrete_segment_rows(
            n_projects=12, project_prefix="PROJ-A", planview_prefix="P-A",
        )
    )
    with pytest.raises(CustomRuleNotEvaluated):
        check_adr_a8(
            df, params={ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
        )


def test_adr_a8_unsegmented_does_not_touch_reference(monkeypatch):
    """Default (segmentation off) must not consult the reference dataset
    at all, the legacy global-IQR path keeps its standalone behaviour
    and never blows up when the reference is missing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_adr_a8

    def _boom(_name):
        raise AssertionError(
            "Unsegmented A8 must not call get_reference_dataset"
        )

    monkeypatch.setattr(ref_mod, "get_reference_dataset", _boom)
    df = _make_a8_segmented_df(
        _a8_steel_concrete_segment_rows(
            n_projects=12, project_prefix="PROJ-A", planview_prefix="P-A",
        )
    )
    # No outlier → rule passes regardless of segmentation; the point of
    # this test is that the reference is not consulted.
    assert check_adr_a8(df).all()


def test_adr_a8_segmented_fails_when_planview_id_column_missing(monkeypatch):
    """With segmentation on, PLANVIEW_ID becomes a structurally required
    column, the rule fails every row when it is missing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_adr_a8,
    )

    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: _a8_segment_reference([])
    )

    rows = _a8_steel_concrete_segment_rows(
        n_projects=12, project_prefix="PROJ-A", planview_prefix="P-A",
    )
    df = _make_a8_segmented_df(rows).drop(columns="PLANVIEW_ID")
    result = check_adr_a8(
        df, params={ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    assert (~result).all()


# =============================================================================
# E5: FEED / Engineering hours estimate present when cost exists
# =============================================================================

def _e5_required_cols():
    return [
        "WBC_LEVEL_1",
        "TOTAL_HOURS",
        "TOTAL_COST_USD",
        "TOTAL_COST_ESTIMATE_CURRENCY",
    ]


def _make_e5_df(rows):
    """Build an EPT-shaped DataFrame from a list of dicts; missing cols
    default to None so the rule sees them as null."""
    cols = _e5_required_cols()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def test_ept_has_custom_rule_e5_available():
    """EPT catalog exposes E5 as a non-blocking Consistency rule."""
    rules = get_available_custom_dqr_rules("EPT")
    by_id = {r.id: r for r in rules}
    assert "E5" in by_id
    rule = by_id["E5"]
    assert rule.type == "Consistency"
    assert rule.blocking is False
    assert rule.required_columns == {
        "Level 1": "WBC_LEVEL_1",
        "Total Hours": "TOTAL_HOURS",
        "Total Cost (USD)": "TOTAL_COST_USD",
        "Total Cost (Local Currency)": "TOTAL_COST_ESTIMATE_CURRENCY",
    }


def test_ept_e5_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import EPT_E5_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("EPT") if r.id == "E5"
    )
    assert rule.required_columns == EPT_E5_REQUIRED_COLUMNS


@pytest.mark.parametrize(
    "wbc_level_1",
    [
        "FEED",
        "FEED BY CONTRACTOR",
        "FEED BY CONTRACTOR(S)",
        "FEED by Contractor",
        "250.0-FEED BY CONTRACTOR(S)",
        "250.0-FEED BY CONTRACTOR",
        "DETAILED ENGINEERING",
        "Detailed Engineering",
        "230.0-DETAILED ENGINEERING",
        "ENGINEERING COSTS",
    ],
)
def test_ept_e5_passes_when_cost_and_hours_both_present(wbc_level_1):
    """A FEED / Engineering row with both cost and hours populated passes,
    regardless of which sample WBC label triggered the in-scope match."""
    from src.custom_dqr_engine import check_ept_e5
    df = _make_e5_df([{
        "WBC_LEVEL_1": wbc_level_1,
        "TOTAL_HOURS": 1500.0,
        "TOTAL_COST_USD": 200_000.0,
        "TOTAL_COST_ESTIMATE_CURRENCY": 0.0,
    }])
    assert check_ept_e5(df).tolist() == [True]


def test_ept_e5_passes_when_both_cost_and_hours_absent():
    """Both sides absent (NULL/zero) is consistent - passes."""
    from src.custom_dqr_engine import check_ept_e5
    df = _make_e5_df([
        {"WBC_LEVEL_1": "FEED",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 0.0,
         "TOTAL_COST_ESTIMATE_CURRENCY": 0.0},
        {"WBC_LEVEL_1": "DETAILED ENGINEERING",
         "TOTAL_HOURS": None, "TOTAL_COST_USD": None,
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
    ])
    assert check_ept_e5(df).tolist() == [True, True]


def test_ept_e5_fails_when_cost_present_but_hours_missing():
    """Cost > 0 with TOTAL_HOURS NULL/0 is the headline failure mode."""
    from src.custom_dqr_engine import check_ept_e5
    df = _make_e5_df([
        {"WBC_LEVEL_1": "FEED",
         "TOTAL_HOURS": None, "TOTAL_COST_USD": 50_000.0,
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
        {"WBC_LEVEL_1": "DETAILED ENGINEERING",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 25_000.0,
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
    ])
    assert check_ept_e5(df).tolist() == [False, False]


def test_ept_e5_fails_when_hours_present_but_cost_missing():
    """Symmetric failure: TOTAL_HOURS > 0 with no cost on either field."""
    from src.custom_dqr_engine import check_ept_e5
    df = _make_e5_df([{
        "WBC_LEVEL_1": "ENGINEERING COSTS",
        "TOTAL_HOURS": 800.0,
        "TOTAL_COST_USD": None,
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    }])
    assert check_ept_e5(df).tolist() == [False]


def test_ept_e5_uses_currency_fallback_when_usd_null():
    """COALESCE: when TOTAL_COST_USD is NULL, TOTAL_COST_ESTIMATE_CURRENCY
    is treated as the cost amount."""
    from src.custom_dqr_engine import check_ept_e5
    df = _make_e5_df([
        # Currency fallback satisfies the cost side; hours present → PASS.
        {"WBC_LEVEL_1": "FEED BY CONTRACTOR",
         "TOTAL_HOURS": 600.0, "TOTAL_COST_USD": None,
         "TOTAL_COST_ESTIMATE_CURRENCY": 75_000.0},
        # Currency fallback gives cost > 0 but hours = 0 → FAIL.
        {"WBC_LEVEL_1": "FEED",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": None,
         "TOTAL_COST_ESTIMATE_CURRENCY": 40_000.0},
    ])
    assert check_ept_e5(df).tolist() == [True, False]


def test_ept_e5_zero_in_total_cost_usd_does_not_fall_back_to_currency():
    """SQL COALESCE semantics: a *populated* zero in TOTAL_COST_USD wins
    over the local-currency fallback. Both sides resolve to 0 → PASS."""
    from src.custom_dqr_engine import check_ept_e5
    df = _make_e5_df([{
        "WBC_LEVEL_1": "FEED",
        "TOTAL_HOURS": 0.0,
        "TOTAL_COST_USD": 0.0,
        "TOTAL_COST_ESTIMATE_CURRENCY": 100_000.0,
    }])
    assert check_ept_e5(df).tolist() == [True]


def test_ept_e5_non_feed_rows_pass_regardless_of_balance():
    """Non-FEED / non-Engineering rows are Not Applicable and always pass -
    even when cost/hours are inconsistent (E5 is scoped to FEED only)."""
    from src.custom_dqr_engine import check_ept_e5
    df = _make_e5_df([
        # Cost without hours - would FAIL if it were FEED, but isn't.
        {"WBC_LEVEL_1": "L1_CAPEX",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 500_000.0,
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
        # Hours without cost, same.
        {"WBC_LEVEL_1": "100.0-PROCUREMENT",
         "TOTAL_HOURS": 1200.0, "TOTAL_COST_USD": None,
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
        # Empty / null WBC_LEVEL_1 - out of scope, so PASS (E4 covers it).
        {"WBC_LEVEL_1": None,
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 50_000.0,
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
        {"WBC_LEVEL_1": "   ",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 50_000.0,
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
    ])
    assert check_ept_e5(df).tolist() == [True, True, True, True]


def test_ept_e5_word_boundary_excludes_false_positives():
    """The pattern uses word boundaries so substrings like ``FEEDBACK`` or
    ``ENGINEERED`` aren't pulled into FEED / Engineering scope."""
    from src.custom_dqr_engine import check_ept_e5
    df = _make_e5_df([
        {"WBC_LEVEL_1": "FEEDBACK COSTS",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 50_000.0,
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
        {"WBC_LEVEL_1": "ENGINEERED EQUIPMENT",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 50_000.0,
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
    ])
    assert check_ept_e5(df).tolist() == [True, True]


def test_ept_e5_treats_string_numerics_correctly():
    """Numeric columns may arrive as strings (CSV / Snowflake VARCHAR);
    ``pd.to_numeric`` coerces them, so the rule still distinguishes
    populated cost from missing hours."""
    from src.custom_dqr_engine import check_ept_e5
    df = _make_e5_df([
        {"WBC_LEVEL_1": "FEED",
         "TOTAL_HOURS": "0", "TOTAL_COST_USD": "75000",
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
    ])
    assert check_ept_e5(df).tolist() == [False]


def test_ept_e5_fails_for_all_rows_when_required_column_missing():
    """Schema-level missing column → rule fails for every row, mirroring
    the convention used by E1/E3/E4."""
    from src.custom_dqr_engine import check_ept_e5
    # Drop TOTAL_COST_ESTIMATE_CURRENCY entirely.
    df = pd.DataFrame({
        "WBC_LEVEL_1": ["FEED", "DETAILED ENGINEERING"],
        "TOTAL_HOURS": [100.0, 0.0],
        "TOTAL_COST_USD": [10_000.0, 0.0],
    })
    assert check_ept_e5(df).tolist() == [False, False]


def test_ept_e5_empty_dataframe_returns_empty_pass_series():
    from src.custom_dqr_engine import check_ept_e5
    df = pd.DataFrame({c: [] for c in _e5_required_cols()})
    out = check_ept_e5(df)
    assert out.empty and out.dtype == bool


def test_ept_e5_dispatches_through_evaluate_custom_rules():
    """End-to-end: an E5 assignment is routed through evaluate_custom_rules
    and produces one Boolean column per row."""
    df = _make_e5_df([
        {"WBC_LEVEL_1": "FEED",
         "TOTAL_HOURS": 1000.0, "TOTAL_COST_USD": 200_000.0,
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
        {"WBC_LEVEL_1": "DETAILED ENGINEERING",
         "TOTAL_HOURS": None, "TOTAL_COST_USD": 50_000.0,
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
        {"WBC_LEVEL_1": "L1_CAPEX",
         "TOTAL_HOURS": 0.0, "TOTAL_COST_USD": 500_000.0,
         "TOTAL_COST_ESTIMATE_CURRENCY": None},
    ])
    out, not_evaluated = evaluate_custom_rules(
        df, [CustomDQRAssignment(rule_id="E5", weight=100.0)], "EPT"
    )
    assert "E5" in out.columns
    assert out["E5"].tolist() == [True, False, True]
    assert not_evaluated == {}


# =============================================================================
# E6: Cost-to-hours ratio outlier check (project-level ratio, row-level
# verdict, IQR thresholds)
# =============================================================================

def _e6_required_cols():
    return [
        "PLANVIEW_ID",
        "TOTAL_HOURS",
        "TOTAL_COST_USD",
        "TOTAL_COST_ESTIMATE_CURRENCY",
    ]


def _make_e6_df(rows):
    """Build an EPT-shaped DataFrame from a list of dicts; missing cols
    default to None so the rule sees them as null."""
    cols = _e6_required_cols()
    completed = [{**{c: None for c in cols}, **r} for r in rows]
    return pd.DataFrame(completed, columns=cols)


def _e6_normal_population(planview_prefix="P-NORMAL", n=6, ratio=50.0):
    """Build a normal-distribution baseline: ``n`` projects each producing
    the same cost/hours ratio. Used as the IQR baseline so a single outlier
    introduced on top stands out clearly."""
    rows = []
    for k in range(n):
        rows.append({
            "PLANVIEW_ID": f"{planview_prefix}-{k}",
            "TOTAL_HOURS": 100.0,
            "TOTAL_COST_USD": 100.0 * ratio,  # ratio of `ratio` per project
            "TOTAL_COST_ESTIMATE_CURRENCY": None,
        })
    return rows


def test_ept_has_custom_rule_e6_available():
    """EPT catalog exposes E6 as a non-blocking statistical-outlier rule."""
    rules = get_available_custom_dqr_rules("EPT")
    by_id = {r.id: r for r in rules}
    assert "E6" in by_id
    rule = by_id["E6"]
    assert rule.type == "Statistical Outlier"
    assert rule.blocking is False
    assert rule.reference is None
    assert rule.required_columns == {
        "Project Key": "PLANVIEW_ID",
        "Total Hours": "TOTAL_HOURS",
        "Total Cost (USD)": "TOTAL_COST_USD",
        "Total Cost (Local Currency)": "TOTAL_COST_ESTIMATE_CURRENCY",
    }


def test_ept_e6_required_columns_constant_matches_catalog():
    from src.custom_dqr_engine import EPT_E6_REQUIRED_COLUMNS
    rule = next(
        r for r in get_available_custom_dqr_rules("EPT") if r.id == "E6"
    )
    assert rule.required_columns == EPT_E6_REQUIRED_COLUMNS


def test_ept_e6_passes_when_all_projects_share_the_same_ratio():
    """A degenerate population where every project has the same ratio has
    Q1 == Q3 (IQR == 0), so the bounds collapse to that single value and
    nothing is outside them, every row passes."""
    from src.custom_dqr_engine import check_ept_e6
    df = _make_e6_df(_e6_normal_population(n=6))
    assert check_ept_e6(df).all()


def test_ept_e6_fails_high_outlier_project():
    """A project whose ratio is far above the IQR upper bound fails, and
    every row in that project inherits the FAIL."""
    from src.custom_dqr_engine import check_ept_e6
    rows = _e6_normal_population(n=6, ratio=50.0)
    # P-OUT: same hours but ~10× the cost → ratio 500 is well outside the
    # mild upper bound of the otherwise-uniform population.
    rows.append({
        "PLANVIEW_ID": "P-OUT",
        "TOTAL_HOURS": 100.0,
        "TOTAL_COST_USD": 50_000.0,
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    rows.append({
        "PLANVIEW_ID": "P-OUT",
        "TOTAL_HOURS": 100.0,
        "TOTAL_COST_USD": 50_000.0,
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    df = _make_e6_df(rows)
    result = check_ept_e6(df)
    # Normal-population rows pass; both P-OUT rows fail.
    assert result.iloc[:6].all()
    assert (~result.iloc[6:]).all()


def test_ept_e6_fails_low_outlier_project():
    """A project whose ratio is far below the IQR lower bound also fails."""
    from src.custom_dqr_engine import check_ept_e6
    rows = _e6_normal_population(n=6, ratio=50.0)
    rows.append({
        "PLANVIEW_ID": "P-LOW",
        "TOTAL_HOURS": 1_000.0,
        "TOTAL_COST_USD": 100.0,        # ratio 0.1 - far below 50
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    df = _make_e6_df(rows)
    result = check_ept_e6(df)
    assert result.iloc[:6].all()
    assert not bool(result.iloc[6])


def test_ept_e6_aggregates_multiple_rows_per_project():
    """The rule aggregates by PLANVIEW_ID before computing the ratio: a
    project that looks like an outlier on a single row but normal once
    aggregated does not fail."""
    from src.custom_dqr_engine import check_ept_e6
    rows = _e6_normal_population(n=6, ratio=50.0)
    # P-MULTI: aggregated ratio = (100 + 4900) / (1 + 99) = 50 → in-band.
    rows.append({
        "PLANVIEW_ID": "P-MULTI",
        "TOTAL_HOURS": 1.0,
        "TOTAL_COST_USD": 100.0,        # ratio 100 in isolation
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    rows.append({
        "PLANVIEW_ID": "P-MULTI",
        "TOTAL_HOURS": 99.0,
        "TOTAL_COST_USD": 4_900.0,      # ratio ~49.5 in isolation
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    df = _make_e6_df(rows)
    assert check_ept_e6(df).all()


def test_ept_e6_uses_currency_fallback_when_usd_null():
    """COALESCE: when TOTAL_COST_USD is null, the local-currency cost is
    used in the aggregation. A project whose only populated cost field is
    `TOTAL_COST_ESTIMATE_CURRENCY` still contributes a real ratio."""
    from src.custom_dqr_engine import check_ept_e6
    rows = _e6_normal_population(n=6, ratio=50.0)
    # P-LOCAL aggregates to ratio 50 via the local-currency fallback.
    rows.append({
        "PLANVIEW_ID": "P-LOCAL",
        "TOTAL_HOURS": 100.0,
        "TOTAL_COST_USD": None,
        "TOTAL_COST_ESTIMATE_CURRENCY": 5_000.0,
    })
    df = _make_e6_df(rows)
    assert check_ept_e6(df).all()


def test_ept_e6_zero_in_total_cost_usd_does_not_fall_back_to_currency():
    """SQL COALESCE: a populated zero in TOTAL_COST_USD wins over the
    local-currency fallback, so a 0 cost stays 0 even if the local-currency
    column is populated."""
    from src.custom_dqr_engine import check_ept_e6
    rows = _e6_normal_population(n=6, ratio=50.0)
    rows.append({
        "PLANVIEW_ID": "P-ZERO-USD",
        "TOTAL_HOURS": 100.0,
        "TOTAL_COST_USD": 0.0,                 # populated zero wins
        "TOTAL_COST_ESTIMATE_CURRENCY": 5_000.0,
    })
    df = _make_e6_df(rows)
    # Aggregated ratio for P-ZERO-USD is 0 → far below the cluster of 50,
    # so it should be flagged as a low outlier.
    result = check_ept_e6(df)
    assert result.iloc[:6].all()
    assert not bool(result.iloc[6])


def test_ept_e6_passes_projects_with_zero_hours():
    """Projects with `project_total_hours <= 0` are NOT_APPLICABLE → PASS,
    even when they look superficially anomalous (cost without hours)."""
    from src.custom_dqr_engine import check_ept_e6
    rows = _e6_normal_population(n=6, ratio=50.0)
    rows.append({
        "PLANVIEW_ID": "P-NOHOURS",
        "TOTAL_HOURS": 0.0,
        "TOTAL_COST_USD": 500_000.0,
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    rows.append({
        "PLANVIEW_ID": "P-NULLHOURS",
        "TOTAL_HOURS": None,
        "TOTAL_COST_USD": 500_000.0,
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    df = _make_e6_df(rows)
    assert check_ept_e6(df).all()


def test_ept_e6_passes_rows_with_null_planview_id():
    """Rows lacking PLANVIEW_ID can't be assigned to a project, they pass
    E6 (E7 already covers the missing-project linkage)."""
    from src.custom_dqr_engine import check_ept_e6
    rows = _e6_normal_population(n=6, ratio=50.0)
    rows.append({
        "PLANVIEW_ID": None,
        "TOTAL_HOURS": 1.0,
        "TOTAL_COST_USD": 5_000_000.0,         # extreme ratio in isolation
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    rows.append({
        "PLANVIEW_ID": "  ",
        "TOTAL_HOURS": 1.0,
        "TOTAL_COST_USD": 5_000_000.0,
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    df = _make_e6_df(rows)
    assert check_ept_e6(df).all()


def test_ept_e6_passes_when_population_below_minimum():
    """When the eligible-project count is below EPT_E6_MIN_POPULATION the
    rule emits NOT_APPLICABLE → PASS for every row, even if one project
    has a wildly different ratio from the rest."""
    from src.custom_dqr_engine import EPT_E6_MIN_POPULATION, check_ept_e6
    # Total eligible projects = (min - 2) baseline + 1 outlier = min - 1
    # (one short of the threshold), so the rule must skip the IQR check.
    rows = _e6_normal_population(n=EPT_E6_MIN_POPULATION - 2, ratio=50.0)
    rows.append({
        "PLANVIEW_ID": "P-OUT",
        "TOTAL_HOURS": 100.0,
        "TOTAL_COST_USD": 50_000.0,            # ratio 500 - would fail
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    df = _make_e6_df(rows)
    assert check_ept_e6(df).all()


def test_ept_e6_fails_for_all_rows_when_required_column_missing():
    """Schema-level missing column → rule fails for every row, mirroring
    the convention used by E1/E3/E4/E5."""
    from src.custom_dqr_engine import check_ept_e6
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2"],
        "TOTAL_HOURS": [100.0, 200.0],
        "TOTAL_COST_USD": [5_000.0, 10_000.0],
        # TOTAL_COST_ESTIMATE_CURRENCY intentionally absent
    })
    assert check_ept_e6(df).tolist() == [False, False]


def test_ept_e6_empty_dataframe_returns_empty_pass_series():
    from src.custom_dqr_engine import check_ept_e6
    df = pd.DataFrame({c: [] for c in _e6_required_cols()})
    out = check_ept_e6(df)
    assert out.empty and out.dtype == bool


def test_ept_e6_treats_string_numerics_correctly():
    """Numeric columns may arrive as strings (CSV / Snowflake VARCHAR);
    ``pd.to_numeric`` coerces them so the aggregation still works."""
    from src.custom_dqr_engine import check_ept_e6
    rows = _e6_normal_population(n=6, ratio=50.0)
    # Convert P-NORMAL-0 to string-typed values, the rule must still
    # produce the same verdicts (all pass).
    rows[0] = {
        "PLANVIEW_ID": "P-NORMAL-0",
        "TOTAL_HOURS": "100",
        "TOTAL_COST_USD": "5000",
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    }
    df = _make_e6_df(rows)
    assert check_ept_e6(df).all()


def test_ept_e6_dispatches_through_evaluate_custom_rules():
    """End-to-end: evaluate_custom_rules routes an E6 assignment through
    check_ept_e6 and returns the per-row Boolean column."""
    rows = _e6_normal_population(n=6, ratio=50.0)
    rows.append({
        "PLANVIEW_ID": "P-OUT",
        "TOTAL_HOURS": 100.0,
        "TOTAL_COST_USD": 100_000.0,
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    df = _make_e6_df(rows)
    out, not_evaluated = evaluate_custom_rules(
        df, [CustomDQRAssignment(rule_id="E6", weight=100.0)], "EPT"
    )
    assert "E6" in out.columns
    # Normal-population rows pass; outlier row fails.
    assert out["E6"].iloc[:6].tolist() == [True] * 6
    assert not bool(out["E6"].iloc[6])
    assert not_evaluated == {}


# -----------------------------------------------------------------------------
# E6: project-type segmentation (toggle: segment_by_project_type)
# -----------------------------------------------------------------------------


def _e6_segment_reference(rows):
    """Build a Planview reference DataFrame with the segmentation columns
    used by E6 when the segment-by-project-type toggle is on.

    ``rows`` is a list of ``(PROJECT_ID, E05_DEPARTMENT, BUSINESS)`` tuples.
    """
    return pd.DataFrame(
        rows, columns=["PROJECT_ID", "E05_DEPARTMENT", "BUSINESS"]
    )


def test_ept_e6_segment_param_constants_match_catalog():
    """The segmentation toggle exposed on the catalog rule card carries the
    same key the engine reads from ``params``."""
    from src.custom_dqr_engine import EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM
    rule = next(
        r for r in get_available_custom_dqr_rules("EPT") if r.id == "E6"
    )
    keys = {opt.key for opt in rule.options}
    assert EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM in keys


def test_ept_e6_segmented_isolates_outliers_per_segment(monkeypatch):
    """With segmentation on, an outlier within its own (BROWN/UPSTREAM)
    segment is flagged even though it would look in-band against the
    global population. Two segments with distinct ratios are kept
    separate, so a project that is "normal" for refineries does not get
    judged against an FPSO baseline."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_ept_e6,
    )

    seg_a = _e6_normal_population(planview_prefix="P-A", n=6, ratio=50.0)
    seg_b = _e6_normal_population(planview_prefix="P-B", n=6, ratio=500.0)
    # Outlier *within segment A*: ratio 500 looks normal globally
    # (matches segment B's centre) but is a huge outlier in segment A.
    seg_a.append({
        "PLANVIEW_ID": "P-A-OUT",
        "TOTAL_HOURS": 100.0,
        "TOTAL_COST_USD": 50_000.0,
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })

    ref_rows = (
        [(f"P-A-{k}", "BROWNFIELD", "UPSTREAM") for k in range(6)]
        + [("P-A-OUT", "BROWNFIELD", "UPSTREAM")]
        + [(f"P-B-{k}", "GREENFIELD", "DOWNSTREAM") for k in range(6)]
    )
    ref_df = _e6_segment_reference(ref_rows)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: ref_df
    )

    df = _make_e6_df(seg_a + seg_b)
    result = check_ept_e6(
        df, params={EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # Segment A baseline rows pass; the within-segment outlier fails.
    assert result.iloc[:6].all()
    assert not bool(result.iloc[6])
    # Segment B rows all pass (their own segment is uniform).
    assert result.iloc[7:].all()


def test_ept_e6_segmented_passes_when_segment_population_below_minimum(monkeypatch):
    """A segment whose eligible-project count is below
    ``EPT_E6_MIN_POPULATION`` is NOT_APPLICABLE → PASS, even when one of
    its projects has a ratio that would obviously fail against the
    global IQR."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        EPT_E6_MIN_POPULATION,
        EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_ept_e6,
    )

    # Big well-populated segment A as a decoy + tiny segment B
    seg_a = _e6_normal_population(planview_prefix="P-A", n=8, ratio=50.0)
    seg_b = _e6_normal_population(
        planview_prefix="P-B", n=EPT_E6_MIN_POPULATION - 2, ratio=50.0
    )
    seg_b.append({
        "PLANVIEW_ID": "P-B-OUT",
        "TOTAL_HOURS": 100.0,
        "TOTAL_COST_USD": 5_000_000.0,           # would fail globally
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })

    ref_rows = (
        [(f"P-A-{k}", "BROWNFIELD", "UPSTREAM") for k in range(8)]
        + [
            (f"P-B-{k}", "GREENFIELD", "LNG")
            for k in range(EPT_E6_MIN_POPULATION - 2)
        ]
        + [("P-B-OUT", "GREENFIELD", "LNG")]
    )
    ref_df = _e6_segment_reference(ref_rows)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: ref_df
    )

    df = _make_e6_df(seg_a + seg_b)
    result = check_ept_e6(
        df, params={EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # Every row passes: segment A is uniform, segment B is under the floor.
    assert result.all()


def test_ept_e6_segmented_passes_projects_without_resolved_segment(monkeypatch):
    """Projects whose PLANVIEW_ID does not match the reference, or whose
    matched segment has a null/blank ``E05_DEPARTMENT`` / ``BUSINESS``,
    are NOT_APPLICABLE → PASS so segmentation never double-penalises the
    referential-integrity gap E7 / E2 already cover."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM,
        check_ept_e6,
    )

    seg_a = _e6_normal_population(planview_prefix="P-A", n=6, ratio=50.0)
    # P-A-OUT belongs to the same segment and would normally fail; here
    # we strip it from the reference to simulate an orphan PLANVIEW_ID.
    seg_a.append({
        "PLANVIEW_ID": "P-A-ORPHAN",
        "TOTAL_HOURS": 100.0,
        "TOTAL_COST_USD": 5_000_000.0,
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    # P-A-NULL has a matched row but the segment columns are null.
    seg_a.append({
        "PLANVIEW_ID": "P-A-NULL",
        "TOTAL_HOURS": 100.0,
        "TOTAL_COST_USD": 5_000_000.0,
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })

    ref_rows = (
        [(f"P-A-{k}", "BROWNFIELD", "UPSTREAM") for k in range(6)]
        + [("P-A-NULL", None, "UPSTREAM")]
    )
    ref_df = _e6_segment_reference(ref_rows)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset", lambda name: ref_df
    )

    df = _make_e6_df(seg_a)
    result = check_ept_e6(
        df, params={EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
    )
    # All baseline rows pass (uniform segment A). The orphan / null-segment
    # rows pass too, they are NOT_APPLICABLE in segmented mode.
    assert result.all()


def test_ept_e6_segmented_raises_not_evaluated_when_reference_unavailable(
    monkeypatch,
):
    """With segmentation on, an absent ``VWS_GP_STANDARD_SHARE`` reference
    must raise :class:`CustomRuleNotEvaluated` - never silently fall back
    to the global IQR baseline."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import (
        EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM,
        CustomRuleNotEvaluated,
        check_ept_e6,
    )

    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset_error", lambda name: "network down"
    )

    df = _make_e6_df(_e6_normal_population(n=6, ratio=50.0))
    with pytest.raises(CustomRuleNotEvaluated):
        check_ept_e6(
            df, params={EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM: True}
        )


def test_ept_e6_unsegmented_does_not_touch_reference(monkeypatch):
    """Default (segmentation off) must not consult the reference dataset
    at all, the legacy global-IQR path keeps its standalone behaviour
    and never blows up when the reference is missing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import check_ept_e6

    def _boom(_name):
        raise AssertionError(
            "Unsegmented E6 must not call get_reference_dataset"
        )

    monkeypatch.setattr(ref_mod, "get_reference_dataset", _boom)
    df = _make_e6_df(_e6_normal_population(n=6, ratio=50.0))
    assert check_ept_e6(df).all()


# =============================================================================
# E7: Project Key linkage (Referential Integrity on PLANVIEW_ID)
# =============================================================================

def test_ept_has_custom_rule_e7_available():
    """EPT catalog exposes E7 with referential-integrity metadata pointing
    at the VWS_GP_STANDARD_SHARE.PROJECT_ID reference column."""
    rules = get_available_custom_dqr_rules("EPT")
    by_id = {r.id: r for r in rules}
    assert "E7" in by_id
    rule = by_id["E7"]
    assert rule.type == "Referential Integrity"
    assert rule.blocking is True
    assert rule.required_columns == {"Project Key": "PLANVIEW_ID"}
    assert rule.reference is not None
    assert rule.reference["reference_dataset"] == "VWS_GP_STANDARD_SHARE"
    assert rule.reference["source_column"] == "PLANVIEW_ID"
    assert rule.reference["reference_column"] == "PROJECT_ID"


def test_ept_e7_passes_when_planview_id_in_master():
    """E7 passes when PLANVIEW_ID is non-blank AND present in the project
    master reference dataset."""
    from src.custom_dqr_engine import check_ept_e7
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "PV-00002", "PV-00003"]})
    assert check_ept_e7(df).tolist() == [True, True, True]


def test_ept_e7_fails_when_planview_id_null():
    from src.custom_dqr_engine import check_ept_e7
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", None, "PV-00003"]})
    assert check_ept_e7(df).tolist() == [True, False, True]


def test_ept_e7_fails_when_planview_id_blank():
    from src.custom_dqr_engine import check_ept_e7
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "", "PV-00003"]})
    assert check_ept_e7(df).tolist() == [True, False, True]


def test_ept_e7_fails_when_planview_id_whitespace_only():
    from src.custom_dqr_engine import check_ept_e7
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "   ", "\t"]})
    assert check_ept_e7(df).tolist() == [True, False, False]


def test_ept_e7_fails_when_planview_id_not_in_master():
    """Orphan PLANVIEW_IDs (not present in project_master) fail E7."""
    from src.custom_dqr_engine import check_ept_e7
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "PV-ORPHAN-999", "PV-00003"]})
    assert check_ept_e7(df).tolist() == [True, False, True]


def test_ept_e7_fails_for_all_rows_when_planview_id_column_missing():
    from src.custom_dqr_engine import check_ept_e7
    df = pd.DataFrame({"OTHER_COL": ["x", "y"]})
    assert check_ept_e7(df).tolist() == [False, False]


def test_ept_e7_raises_not_evaluated_when_reference_unavailable(monkeypatch):
    """If the project_master loader returns None, E7 must raise
    CustomRuleNotEvaluated rather than silently passing."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import CustomRuleNotEvaluated, check_ept_e7

    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    # Re-import path used inside check_ept_e7 (lazy import) - patching the
    # source module is sufficient because the function imports at call time.
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "PV-00002"]})
    try:
        check_ept_e7(df)
        raised = False
    except CustomRuleNotEvaluated:
        raised = True
    assert raised


def test_evaluate_custom_rules_records_not_evaluated_when_reference_missing(monkeypatch):
    """Dispatcher catches CustomRuleNotEvaluated, omits the rule from the
    Boolean results, and records the reason, so the rule never silently
    passes when its dependency is unavailable."""
    import src.reference_data as ref_mod
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)

    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "PV-00002"]})
    assignments = [CustomDQRAssignment(rule_id="E7", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "EPT")
    assert "E7" not in out.columns
    assert "E7" in not_evaluated
    assert "vws_gp_standard_share" in not_evaluated["E7"].lower()


# =============================================================================
# Reusable validator API (validate_completeness_rule, validate_referential_integrity_rule)
# =============================================================================

def test_validate_completeness_rule_all_required_columns_filled():
    from src.custom_dqr_engine import validate_completeness_rule
    df = pd.DataFrame({"A": ["x", "y"], "B": ["1", "2"]})
    assert validate_completeness_rule(df, ["A", "B"]).tolist() == [True, True]


def test_validate_completeness_rule_missing_column_fails_all_rows():
    from src.custom_dqr_engine import validate_completeness_rule
    df = pd.DataFrame({"A": ["x", "y"]})
    assert validate_completeness_rule(df, ["A", "B"]).tolist() == [False, False]


def test_validate_referential_integrity_rule_passes_when_in_set():
    from src.custom_dqr_engine import validate_referential_integrity_rule
    src = pd.DataFrame({"PK": ["A", "B", "C"]})
    ref = pd.DataFrame({"PK": ["A", "B", "C", "D"]})
    out = validate_referential_integrity_rule(src, "PK", ref, "PK")
    assert out.tolist() == [True, True, True]


def test_validate_referential_integrity_rule_fails_when_not_in_set():
    from src.custom_dqr_engine import validate_referential_integrity_rule
    src = pd.DataFrame({"PK": ["A", "Z"]})
    ref = pd.DataFrame({"PK": ["A", "B"]})
    assert validate_referential_integrity_rule(src, "PK", ref, "PK").tolist() == [
        True, False,
    ]


def test_validate_referential_integrity_rule_missing_source_column():
    from src.custom_dqr_engine import validate_referential_integrity_rule
    src = pd.DataFrame({"OTHER": ["A", "B"]})
    ref = pd.DataFrame({"PK": ["A", "B"]})
    assert validate_referential_integrity_rule(src, "PK", ref, "PK").tolist() == [
        False, False,
    ]


def test_validate_referential_integrity_rule_missing_reference_column():
    from src.custom_dqr_engine import validate_referential_integrity_rule
    src = pd.DataFrame({"PK": ["A", "B"]})
    ref = pd.DataFrame({"OTHER": ["A", "B"]})
    assert validate_referential_integrity_rule(src, "PK", ref, "PK").tolist() == [
        False, False,
    ]


def test_get_reference_dataset_returns_none_for_unknown_name():
    """Unknown logical names yield None, the caller (custom rule) must then
    raise CustomRuleNotEvaluated rather than silently passing."""
    from src.reference_data import get_reference_dataset
    assert get_reference_dataset("does_not_exist") is None


# =============================================================================
# Eager prefetch + session-state cache (Step 2 → Step 6 caching contract)
# =============================================================================

def test_required_reference_datasets_collects_unique_names():
    """Step 2 uses this to know what to prefetch for the selected systems."""
    from src.reference_data import required_reference_datasets_for_systems
    # EPT has E2/E7 with VWS_GP_STANDARD_SHARE; ADR has A1 (ACCE_COA_MASTER)
    # plus A2 (VWS_GP_STANDARD_SHARE); ACCE has AC1 (ACCE_COA_MASTER) plus
    # AC2 (VWS_GP_STANDARD_SHARE).
    assert required_reference_datasets_for_systems(["EPT"]) == ["VWS_GP_STANDARD_SHARE"]
    assert set(required_reference_datasets_for_systems(["ADR"])) == {
        "VWS_GP_STANDARD_SHARE",
        "ACCE_COA_MASTER",
    }
    assert set(required_reference_datasets_for_systems(["ACCE"])) == {
        "ACCE_COA_MASTER",
        "VWS_GP_STANDARD_SHARE",
    }
    # No duplicates across systems that share a reference.
    assert set(required_reference_datasets_for_systems(["EPT", "ADR"])) == {
        "VWS_GP_STANDARD_SHARE",
        "ACCE_COA_MASTER",
    }
    assert set(required_reference_datasets_for_systems(["ADR", "ACCE"])) == {
        "VWS_GP_STANDARD_SHARE",
        "ACCE_COA_MASTER",
    }
    assert required_reference_datasets_for_systems(["EPT", "EPT"]) == [
        "VWS_GP_STANDARD_SHARE"
    ]


def test_prefetch_outside_streamlit_returns_loaded_datasets_without_caching():
    """In pure pytest (no Streamlit run), prefetch falls back to direct
    loader calls and returns a {name: df} mapping."""
    from src.reference_data import prefetch_reference_datasets
    result = prefetch_reference_datasets(["VWS_GP_STANDARD_SHARE"])
    assert "VWS_GP_STANDARD_SHARE" in result
    assert result["VWS_GP_STANDARD_SHARE"] is not None
    assert "PROJECT_ID" in result["VWS_GP_STANDARD_SHARE"].columns


def test_prefetch_records_error_for_unknown_dataset():
    """Unknown logical names round-trip an error string via the cache so
    Step 2 can surface the failure."""
    from streamlit.testing.v1 import AppTest

    code = (
        "import streamlit as st\n"
        "from src.reference_data import (\n"
        "    prefetch_reference_datasets,\n"
        "    get_reference_dataset_error,\n"
        "    get_reference_dataset,\n"
        ")\n"
        "prefetch_reference_datasets(['NOPE'])\n"
        "st.session_state['err'] = get_reference_dataset_error('NOPE')\n"
        "st.session_state['df_is_none'] = get_reference_dataset('NOPE') is None\n"
    )
    at = AppTest.from_string(code)
    at.run()
    assert at.session_state["df_is_none"] is True
    err = at.session_state["err"]
    assert err and "no loader" in err.lower()


def test_prefetch_records_error_when_loader_raises():
    """Loader exceptions are captured in the cache so the rule's
    CustomRuleNotEvaluated message can include the underlying reason."""
    from streamlit.testing.v1 import AppTest

    code = (
        "import streamlit as st\n"
        "import src.reference_data as ref\n"
        "def boom():\n"
        "    raise RuntimeError('snowflake auth blew up')\n"
        "ref._REGISTRY['BROKEN'] = boom\n"
        "ref.prefetch_reference_datasets(['BROKEN'])\n"
        "st.session_state['err'] = ref.get_reference_dataset_error('BROKEN')\n"
        "st.session_state['df_is_none'] = ref.get_reference_dataset('BROKEN') is None\n"
    )
    at = AppTest.from_string(code)
    at.run()
    assert at.session_state["df_is_none"] is True
    err = at.session_state["err"]
    assert err and "snowflake auth blew up" in err
    assert "RuntimeError" in err


def test_e7_exception_includes_cached_loader_error():
    """When prefetch recorded a loader error, check_ept_e7's
    CustomRuleNotEvaluated message must include that error so Step 6 shows
    the actual cause (not the generic 'unavailable' text)."""
    from streamlit.testing.v1 import AppTest

    code = (
        "import streamlit as st, pandas as pd\n"
        "import src.reference_data as ref\n"
        "from src.custom_dqr_engine import check_ept_e7, CustomRuleNotEvaluated\n"
        "def boom():\n"
        "    raise RuntimeError('SF connection refused')\n"
        "ref._REGISTRY['VWS_GP_STANDARD_SHARE'] = boom\n"
        "ref.prefetch_reference_datasets(['VWS_GP_STANDARD_SHARE'])\n"
        "df = pd.DataFrame({'PLANVIEW_ID': ['PV-1']})\n"
        "try:\n"
        "    check_ept_e7(df)\n"
        "    st.session_state['raised'] = False\n"
        "except CustomRuleNotEvaluated as e:\n"
        "    st.session_state['raised'] = True\n"
        "    st.session_state['msg'] = str(e)\n"
    )
    at = AppTest.from_string(code)
    at.run()
    assert at.session_state["raised"] is True
    msg = at.session_state["msg"]
    assert "VWS_GP_STANDARD_SHARE" in msg
    assert "SF connection refused" in msg
    assert "RuntimeError" in msg


def test_get_reference_dataset_uses_session_cache():
    """Once prefetched, subsequent calls hit the cache instead of the
    loader, this is what prevents Step 6 / Restart from re-opening the
    Snowflake connection."""
    from streamlit.testing.v1 import AppTest

    code = (
        "import streamlit as st, pandas as pd\n"
        "import src.reference_data as ref\n"
        "calls = {'n': 0}\n"
        "def loader():\n"
        "    calls['n'] += 1\n"
        "    return pd.DataFrame({'PROJECT_ID': ['A']})\n"
        "ref._REGISTRY['CACHED'] = loader\n"
        "ref.prefetch_reference_datasets(['CACHED'])\n"
        "ref.get_reference_dataset('CACHED')\n"
        "ref.get_reference_dataset('CACHED')\n"
        "ref.get_reference_dataset('CACHED')\n"
        "st.session_state['n'] = calls['n']\n"
    )
    at = AppTest.from_string(code)
    at.run()
    # Loader called exactly once during prefetch; subsequent reads served from cache.
    assert at.session_state["n"] == 1


def test_clear_reference_cache_drops_session_entries():
    """Restart must drop cached references so the next selection re-fetches."""
    from streamlit.testing.v1 import AppTest

    code = (
        "import streamlit as st\n"
        "import src.reference_data as ref\n"
        "ref.prefetch_reference_datasets(['VWS_GP_STANDARD_SHARE'])\n"
        "st.session_state['cached_before'] = ref._SESSION_STATE_KEY in st.session_state\n"
        "ref.clear_reference_cache()\n"
        "st.session_state['cached_after'] = ref._SESSION_STATE_KEY in st.session_state\n"
    )
    at = AppTest.from_string(code)
    at.run()
    assert at.session_state["cached_before"] is True
    assert at.session_state["cached_after"] is False


def test_clear_reference_cache_outside_streamlit_is_noop():
    """``clear_reference_cache`` must be safe to call from pure pytest
    (no streamlit run)."""
    from src.reference_data import clear_reference_cache
    clear_reference_cache()  # must not raise


def test_prefetch_does_not_re_run_loader_for_already_cached_names():
    """Prefetch is idempotent - passing the same name twice must not invoke
    the loader twice (covers the 'already cached, skip' branch)."""
    from streamlit.testing.v1 import AppTest

    code = (
        "import streamlit as st\n"
        "import src.reference_data as ref\n"
        "calls = {'n': 0}\n"
        "def loader():\n"
        "    calls['n'] += 1\n"
        "    return __import__('pandas').DataFrame({'PROJECT_ID': ['A']})\n"
        "ref._REGISTRY['IDEMP'] = loader\n"
        "ref.prefetch_reference_datasets(['IDEMP'])\n"
        "ref.prefetch_reference_datasets(['IDEMP'])\n"
        "ref.prefetch_reference_datasets(['IDEMP', 'IDEMP'])\n"
        "st.session_state['n'] = calls['n']\n"
    )
    at = AppTest.from_string(code)
    at.run()
    assert at.session_state["n"] == 1


# =============================================================================
# Defensive paths when Streamlit's session_state is not accessible
#
# These three tests simulate "running outside a Streamlit script" by swapping
# ``streamlit.session_state`` for an object that raises on every access. The
# reference_data helpers must degrade gracefully so that pure pytest unit
# tests (and any future CLI / scripted use) keep working.
# =============================================================================

class _RaisingSessionState:
    """Stand-in for streamlit.session_state that raises on every operation,
    simulating a context with no active Streamlit runtime."""
    def __contains__(self, key):
        raise RuntimeError("no streamlit runtime")
    def __setitem__(self, key, value):
        raise RuntimeError("no streamlit runtime")
    def __getitem__(self, key):
        raise RuntimeError("no streamlit runtime")
    def __delitem__(self, key):
        raise RuntimeError("no streamlit runtime")
    def get(self, *a, **kw):
        raise RuntimeError("no streamlit runtime")


def test_session_cache_get_only_handles_no_runtime(monkeypatch):
    """``_session_cache_get_only`` returns None when session_state access
    raises, so callers transparently fall back to the loader."""
    import streamlit as st
    monkeypatch.setattr(st, "session_state", _RaisingSessionState())

    from src.reference_data import _session_cache_get_only
    assert _session_cache_get_only() is None


def test_prefetch_outside_runtime_falls_back_to_direct_loader(monkeypatch):
    """When session_state isn't usable, prefetch returns the loaded
    DataFrames directly (no caching) instead of crashing."""
    import streamlit as st
    monkeypatch.setattr(st, "session_state", _RaisingSessionState())

    from src.reference_data import prefetch_reference_datasets
    out = prefetch_reference_datasets(["VWS_GP_STANDARD_SHARE"])
    assert "VWS_GP_STANDARD_SHARE" in out
    assert out["VWS_GP_STANDARD_SHARE"] is not None


def test_clear_reference_cache_no_runtime_is_silent(monkeypatch):
    """``clear_reference_cache`` swallows the AttributeError raised when
    session_state isn't available, so it can be safely called from any
    teardown path."""
    import streamlit as st
    monkeypatch.setattr(st, "session_state", _RaisingSessionState())

    from src.reference_data import clear_reference_cache
    clear_reference_cache()  # must not raise


# =============================================================================
# Custom outlier-rule threshold customization (E3 / E6 / A3 / A7 / A8)
#
# Each statistical-outlier rule reads its threshold from
# ``params[<RULE>_THRESHOLD_PARAM]`` and falls back to the catalog default
# when the param is absent or malformed. Tests below confirm the wiring
# end-to-end - flipping the threshold up makes the rule more lenient (a
# previously-flagged outlier passes); flipping it down makes it stricter.
# =============================================================================


def test_ept_e3_threshold_param_makes_rule_more_lenient():
    """Raising the percentile threshold lifts the cutoff so a mid-tier
    outlier that fails at the default (P90) passes at a stricter
    percentile (P99). Construction: 10 normal mappings (ratio 1), one MID
    mapping (ratio 2), one EXTREME mapping (ratio 5). Pandas sorted
    quantile of [1]*10 + [2, 5]: P90 ≈ 1.9 → MID fails, EXTREME fails;
    P99 ≈ 4.67 → MID passes, EXTREME still fails."""
    from src.custom_dqr_engine import EPT_E3_THRESHOLD_PARAM, check_ept_e3

    rows = []
    for k in range(10):
        rows.append({
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"NORMAL-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    # MID mapping: 2 distinct WBCs → ratio 2
    for w in range(2):
        rows.append({
            "WBC_LEVEL_5": f"W-MID-{w}",
            "CODE_OF_RESOURCE": "MID",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    # EXTREME mapping: 5 distinct WBCs → ratio 5
    for w in range(5):
        rows.append({
            "WBC_LEVEL_5": f"W-EX-{w}",
            "CODE_OF_RESOURCE": "EXTREME",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    df = _make_e3_df(rows)

    # Default (P90 ≈ 1.9): MID and EXTREME both fail.
    default_result = check_ept_e3(df)
    assert default_result.iloc[:10].all()              # NORMAL passes
    assert (~default_result.iloc[10:12]).all()         # MID fails
    assert (~default_result.iloc[12:]).all()           # EXTREME fails

    # P99 (≈ 4.67): MID is now under the cutoff → passes; EXTREME still fails.
    lenient_result = check_ept_e3(df, params={EPT_E3_THRESHOLD_PARAM: 0.99})
    assert lenient_result.iloc[:10].all()              # NORMAL still passes
    assert lenient_result.iloc[10:12].all()            # MID now passes
    assert (~lenient_result.iloc[12:]).all()           # EXTREME still fails


def test_ept_e3_threshold_param_falls_back_to_default_when_invalid():
    """Malformed threshold (None, string, negative, zero) silently falls
    back to the catalog default (P90) so a stale assignment never
    accidentally disables the rule."""
    from src.custom_dqr_engine import EPT_E3_THRESHOLD_PARAM, check_ept_e3

    rows = []
    for k in range(9):
        rows.append({
            "WBC_LEVEL_5": "W1",
            "CODE_OF_RESOURCE": f"NORMAL-{k}",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    for w in range(5):
        rows.append({
            "WBC_LEVEL_5": f"W-OUT-{w}",
            "CODE_OF_RESOURCE": "OUT",
            "STANDARD_ACTIVITY_BREAKDOWN": "S1",
            "TOTAL_HOURS": 0.0,
            "TOTAL_COST_USD": 200_000.0,
        })
    df = _make_e3_df(rows)

    expected = check_ept_e3(df).tolist()
    for bad in (None, "not-a-number", -1.0, 0.0):
        out = check_ept_e3(df, params={EPT_E3_THRESHOLD_PARAM: bad})
        assert out.tolist() == expected, bad


def _e6_varied_population_with_outlier():
    """A 6-project baseline with non-zero IQR (ratios 40..65) plus a
    single outlier project at ratio 100. Sorted population ratios are
    [40, 45, 50, 55, 60, 65, 100] - Q1=46.25, Q3=58.75, IQR=12.5. At 1.5×
    the upper bound is ~77.5 (outlier 100 fails); at 20× the upper bound
    is ~308.75 (outlier 100 swallowed by the wider band)."""
    rows = []
    for k, ratio in enumerate((40.0, 45.0, 50.0, 55.0, 60.0, 65.0)):
        rows.append({
            "PLANVIEW_ID": f"P-NORMAL-{k}",
            "TOTAL_HOURS": 100.0,
            "TOTAL_COST_USD": 100.0 * ratio,
            "TOTAL_COST_ESTIMATE_CURRENCY": None,
        })
    rows.append({
        "PLANVIEW_ID": "P-OUT",
        "TOTAL_HOURS": 100.0,
        "TOTAL_COST_USD": 10_000.0,  # ratio = 100
        "TOTAL_COST_ESTIMATE_CURRENCY": None,
    })
    return rows


def test_ept_e6_threshold_param_widens_pass_band():
    """Raising the IQR multiplier widens the PASS band so a previously-
    flagged outlier project passes."""
    from src.custom_dqr_engine import EPT_E6_THRESHOLD_PARAM, check_ept_e6

    df = _make_e6_df(_e6_varied_population_with_outlier())

    default_result = check_ept_e6(df)
    assert default_result.iloc[:6].all()       # 6 normal projects pass
    assert not default_result.iloc[6]          # outlier fails at 1.5× IQR

    lenient = check_ept_e6(df, params={EPT_E6_THRESHOLD_PARAM: 20.0})
    assert lenient.all()                       # 20× swallows the outlier


def test_ept_e6_threshold_param_default_matches_no_params():
    """No params, empty params, and explicit-default params must all
    produce the same verdicts (the rule's documented baseline)."""
    from src.custom_dqr_engine import (
        EPT_E6_MILD_IQR_MULTIPLIER,
        EPT_E6_THRESHOLD_PARAM,
        check_ept_e6,
    )
    df = _make_e6_df(_e6_varied_population_with_outlier())

    base = check_ept_e6(df)
    assert base.equals(check_ept_e6(df, params={}))
    assert base.equals(
        check_ept_e6(df, params={EPT_E6_THRESHOLD_PARAM: EPT_E6_MILD_IQR_MULTIPLIER})
    )


def test_dispatcher_passes_threshold_param_through_to_check():
    """Dispatcher must plumb ``CustomDQRAssignment.params`` through to a
    check function on a custom threshold. End-to-end: same DataFrame,
    different threshold → different verdict."""
    from src.custom_dqr_engine import (
        EPT_E6_THRESHOLD_PARAM,
        evaluate_custom_rules,
    )

    df = _make_e6_df(_e6_varied_population_with_outlier())

    strict = [CustomDQRAssignment(rule_id="E6", weight=100.0, params={})]
    out_strict, _ = evaluate_custom_rules(df, strict, "EPT")
    assert not out_strict["E6"].all()  # outlier flagged

    lenient = [
        CustomDQRAssignment(
            rule_id="E6", weight=100.0,
            params={EPT_E6_THRESHOLD_PARAM: 20.0},
        )
    ]
    out_lenient, _ = evaluate_custom_rules(df, lenient, "EPT")
    assert out_lenient["E6"].all()  # outlier swallowed by the wider band


def test_check_supports_params_now_true_for_every_outlier_rule():
    """Every statistical-outlier check must declare a ``params`` parameter
    so the dispatcher routes the threshold (and any other per-rule option)
    through. Guards against a future regression where someone removes the
    arg from one rule and silently ignores user customization."""
    from src.custom_dqr_engine import (
        _check_supports_params,
        check_adr_a3,
        check_adr_a7,
        check_adr_a8,
        check_ept_e3,
        check_ept_e6,
    )
    for fn in (check_ept_e3, check_ept_e6, check_adr_a3, check_adr_a7, check_adr_a8):
        assert _check_supports_params(fn) is True, fn.__name__


# =============================================================================
# SQ4: Valid Date (Quality domain - SQS - EXPECTED_SHIP_DATE)
# =============================================================================

def test_sqs_sq4_required_columns_constant():
    """Constant exported from the engine matches the catalog metadata."""
    from src.custom_dqr_engine import SQS_SQ4_REQUIRED_COLUMNS

    assert SQS_SQ4_REQUIRED_COLUMNS == {
        "Expected Ship Date": "EXPECTED_SHIP_DATE",
    }


def test_sqs_sq4_passes_when_all_dates_valid():
    """Row passes when ``EXPECTED_SHIP_DATE`` is a valid calendar date."""
    from src.custom_dqr_engine import check_sqs_sq4

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": pd.to_datetime([
            "2024-06-15", "2025-01-01", "2024-12-31"
        ]),
    })
    assert check_sqs_sq4(df).tolist() == [True, True, True]


def test_sqs_sq4_fails_when_null():
    """NULL ``EXPECTED_SHIP_DATE`` (the dominant production failure mode)
    must FAIL."""
    from src.custom_dqr_engine import check_sqs_sq4

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": [pd.Timestamp("2024-06-15"), None, pd.NaT],
    })
    assert check_sqs_sq4(df).tolist() == [True, False, False]


def test_sqs_sq4_fails_on_unparseable_string():
    """Strings that don't parse as a calendar date land as NaT after
    ``pd.to_datetime(errors="coerce")`` and FAIL - mirrors the SQL spec's
    ``TRY_TO_DATE(TO_VARCHAR(..., 'YYYY-MM-DD'), 'YYYY-MM-DD')`` round-trip
    for values that arrive via VARIANT / string paths."""
    from src.custom_dqr_engine import check_sqs_sq4

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": ["2024-06-15", "not-a-date", "2024-13-40"],
    })
    assert check_sqs_sq4(df).tolist() == [True, False, False]


def test_sqs_sq4_passes_when_strings_parse():
    """ISO-format date strings parse cleanly and PASS."""
    from src.custom_dqr_engine import check_sqs_sq4

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": ["2024-06-15", "2025-01-01"],
    })
    assert check_sqs_sq4(df).tolist() == [True, True]


def test_sqs_sq4_fails_for_all_rows_when_column_missing():
    """Schema-level missing column → rule FAILS for every row (does not
    raise) - same convention as the other custom rules."""
    from src.custom_dqr_engine import check_sqs_sq4

    df = pd.DataFrame({"OTHER_COL": ["x", "y"]})
    assert check_sqs_sq4(df).tolist() == [False, False]


def test_sqs_sq4_handles_empty_dataframe():
    from src.custom_dqr_engine import check_sqs_sq4

    df = pd.DataFrame({"EXPECTED_SHIP_DATE": pd.to_datetime([])})
    out = check_sqs_sq4(df)
    assert isinstance(out, pd.Series)
    assert len(out) == 0


def test_sqs_sq4_dispatches_through_quality_domain(monkeypatch):
    """End-to-end: switching to Quality and dispatching against SQS surfaces
    SQ4 with the correct row verdicts."""
    from config.domains import DOMAIN_QUALITY
    from src.custom_dqr_engine import evaluate_custom_rules
    from src.models import CustomDQRAssignment

    monkeypatch.setattr(
        "config.domains.get_active_domain_code",
        lambda: DOMAIN_QUALITY,
    )

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": [pd.Timestamp("2024-06-15"), None],
    })
    assignments = [CustomDQRAssignment(rule_id="SQ4", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "SQS")
    assert list(out.columns) == ["SQ4"]
    assert out["SQ4"].tolist() == [True, False]
    assert not_evaluated == {}


# =============================================================================
# SQ5: Not after PO Required Ship Date (Business Rule)
# =============================================================================

def test_sqs_sq5_required_columns_constant():
    """Constant exported from the engine matches the catalog metadata."""
    from src.custom_dqr_engine import SQS_SQ5_REQUIRED_COLUMNS

    assert SQS_SQ5_REQUIRED_COLUMNS == {
        "Expected Ship Date": "EXPECTED_SHIP_DATE",
        "PO Required Ship Date": "PO_REQUIRED_SHIP_DATE",
    }


def test_sqs_sq5_passes_when_expected_before_po_required():
    from src.custom_dqr_engine import check_sqs_sq5

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": pd.to_datetime(["2024-06-10"]),
        "PO_REQUIRED_SHIP_DATE": pd.to_datetime(["2024-06-15"]),
    })
    assert check_sqs_sq5(df).tolist() == [True]


def test_sqs_sq5_passes_when_dates_are_equal():
    """The comparison is strict `>` per spec - equal dates are compliant."""
    from src.custom_dqr_engine import check_sqs_sq5

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": pd.to_datetime(["2024-06-15"]),
        "PO_REQUIRED_SHIP_DATE": pd.to_datetime(["2024-06-15"]),
    })
    assert check_sqs_sq5(df).tolist() == [True]


def test_sqs_sq5_fails_when_expected_after_po_required():
    from src.custom_dqr_engine import check_sqs_sq5

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": pd.to_datetime(["2024-06-20"]),
        "PO_REQUIRED_SHIP_DATE": pd.to_datetime(["2024-06-15"]),
    })
    assert check_sqs_sq5(df).tolist() == [False]


def test_sqs_sq5_passes_when_either_side_is_null():
    """NULL on either side → PASS (the rule cannot be evaluated without
    both values; SQ4 covers the completeness gap separately)."""
    from src.custom_dqr_engine import check_sqs_sq5

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": [None, pd.Timestamp("2024-06-10"), None],
        "PO_REQUIRED_SHIP_DATE": [pd.Timestamp("2024-06-15"), None, None],
    })
    assert check_sqs_sq5(df).tolist() == [True, True, True]


@pytest.mark.filterwarnings(
    "ignore:Could not infer format.*:UserWarning"
)
def test_sqs_sq5_passes_when_unparseable_string():
    """Unparseable strings land as NaT after `pd.to_datetime(errors=
    'coerce')` and PASS - SQ4 owns the validity check. The pandas
    format-inference warning is suppressed because the rule intentionally
    runs with ``errors='coerce'`` and treats parse failures as NULL."""
    from src.custom_dqr_engine import check_sqs_sq5

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": ["not-a-date", "2024-06-20"],
        "PO_REQUIRED_SHIP_DATE": ["2024-06-15", "not-a-date"],
    })
    assert check_sqs_sq5(df).tolist() == [True, True]


def test_sqs_sq5_mixed_rows():
    from src.custom_dqr_engine import check_sqs_sq5

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": pd.to_datetime([
            "2024-06-10", "2024-06-15", "2024-06-20", "2024-06-25",
        ]),
        "PO_REQUIRED_SHIP_DATE": pd.to_datetime([
            "2024-06-15", "2024-06-15", "2024-06-15", "2024-06-20",
        ]),
    })
    # before / equal / after / after
    assert check_sqs_sq5(df).tolist() == [True, True, False, False]


def test_sqs_sq5_fails_for_all_rows_when_either_column_missing():
    """Schema-level missing column → rule FAILS for every row (same
    convention as the other custom rules - it's the structural-gap
    signal, distinct from the per-row NULL-handling PASS)."""
    from src.custom_dqr_engine import check_sqs_sq5

    df_missing_po = pd.DataFrame({
        "EXPECTED_SHIP_DATE": pd.to_datetime(["2024-06-10"]),
    })
    assert check_sqs_sq5(df_missing_po).tolist() == [False]

    df_missing_expected = pd.DataFrame({
        "PO_REQUIRED_SHIP_DATE": pd.to_datetime(["2024-06-15"]),
    })
    assert check_sqs_sq5(df_missing_expected).tolist() == [False]


def test_sqs_sq5_handles_empty_dataframe():
    from src.custom_dqr_engine import check_sqs_sq5

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": pd.to_datetime([]),
        "PO_REQUIRED_SHIP_DATE": pd.to_datetime([]),
    })
    out = check_sqs_sq5(df)
    assert isinstance(out, pd.Series)
    assert len(out) == 0


def test_sqs_sq5_dispatches_through_quality_domain(monkeypatch):
    """End-to-end: switching to Quality and dispatching against SQS
    surfaces SQ5 with the correct row verdicts."""
    from config.domains import DOMAIN_QUALITY
    from src.custom_dqr_engine import evaluate_custom_rules
    from src.models import CustomDQRAssignment

    monkeypatch.setattr(
        "config.domains.get_active_domain_code",
        lambda: DOMAIN_QUALITY,
    )

    df = pd.DataFrame({
        "EXPECTED_SHIP_DATE": pd.to_datetime(["2024-06-10", "2024-06-20"]),
        "PO_REQUIRED_SHIP_DATE": pd.to_datetime(["2024-06-15", "2024-06-15"]),
    })
    assignments = [CustomDQRAssignment(rule_id="SQ5", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "SQS")
    assert list(out.columns) == ["SQ5"]
    assert out["SQ5"].tolist() == [True, False]
    assert not_evaluated == {}


# =============================================================================
# SQ6: INSPECTION_TYPE value in allowed set (Validity)
# =============================================================================

def test_sqs_sq6_allowed_values_constant():
    """Allowed-value tuple matches the SQL spec verbatim (case-sensitive)."""
    from src.custom_dqr_engine import SQS_SQ6_ALLOWED_VALUES

    assert SQS_SQ6_ALLOWED_VALUES == (
        "Source Inspection",
        "Supplier Assessment",
        "Expediting",
        "Supplemental Inspection",
    )


def test_sqs_sq6_required_columns_constant():
    from src.custom_dqr_engine import SQS_SQ6_REQUIRED_COLUMNS

    assert SQS_SQ6_REQUIRED_COLUMNS == {
        "Inspection Type": "INSPECTION_TYPE",
    }


def test_sqs_sq6_passes_for_every_allowed_value():
    from src.custom_dqr_engine import SQS_SQ6_ALLOWED_VALUES, check_sqs_sq6

    df = pd.DataFrame({"INSPECTION_TYPE": list(SQS_SQ6_ALLOWED_VALUES)})
    assert check_sqs_sq6(df).tolist() == [True] * len(SQS_SQ6_ALLOWED_VALUES)


def test_sqs_sq6_fails_on_null():
    from src.custom_dqr_engine import check_sqs_sq6

    df = pd.DataFrame({"INSPECTION_TYPE": ["Source Inspection", None, "Expediting"]})
    assert check_sqs_sq6(df).tolist() == [True, False, True]


def test_sqs_sq6_fails_on_case_mismatch():
    """The match is case-sensitive per the Snowflake ``IN`` operator -
    ``source inspection`` is FAIL even though it represents the same
    logical category. This is the documented behaviour, not an accident."""
    from src.custom_dqr_engine import check_sqs_sq6

    df = pd.DataFrame({
        "INSPECTION_TYPE": [
            "Source Inspection",
            "source inspection",
            "SOURCE INSPECTION",
        ]
    })
    assert check_sqs_sq6(df).tolist() == [True, False, False]


def test_sqs_sq6_fails_on_unexpected_value():
    from src.custom_dqr_engine import check_sqs_sq6

    df = pd.DataFrame({
        "INSPECTION_TYPE": ["Source Inspection", "Audit", "Expedite", ""]
    })
    # Audit, "Expedite" (typo, not "Expediting"), and empty string all FAIL.
    assert check_sqs_sq6(df).tolist() == [True, False, False, False]


def test_sqs_sq6_fails_for_all_rows_when_column_missing():
    from src.custom_dqr_engine import check_sqs_sq6

    df = pd.DataFrame({"OTHER_COL": ["x", "y"]})
    assert check_sqs_sq6(df).tolist() == [False, False]


def test_sqs_sq6_handles_empty_dataframe():
    from src.custom_dqr_engine import check_sqs_sq6

    df = pd.DataFrame({"INSPECTION_TYPE": pd.Series([], dtype=object)})
    out = check_sqs_sq6(df)
    assert isinstance(out, pd.Series)
    assert len(out) == 0


def test_sqs_sq6_dispatches_through_quality_domain(monkeypatch):
    """End-to-end via the dispatcher: switching to Quality and asking for
    SQ6 surfaces the rule with the correct row verdicts."""
    from config.domains import DOMAIN_QUALITY
    from src.custom_dqr_engine import evaluate_custom_rules
    from src.models import CustomDQRAssignment

    monkeypatch.setattr(
        "config.domains.get_active_domain_code",
        lambda: DOMAIN_QUALITY,
    )

    df = pd.DataFrame({
        "INSPECTION_TYPE": [
            "Supplier Assessment",
            None,
            "Audit",
            "Supplemental Inspection",
        ],
    })
    assignments = [CustomDQRAssignment(rule_id="SQ6", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "SQS")
    assert list(out.columns) == ["SQ6"]
    assert out["SQ6"].tolist() == [True, False, False, True]
    assert not_evaluated == {}


# =============================================================================
# SQ7: WORK_CRITICALITY value in allowed set (Validity)
# =============================================================================

def test_sqs_sq7_allowed_values_constant():
    """Allowed-value tuple matches the SQL spec verbatim (case-sensitive)."""
    from src.custom_dqr_engine import SQS_SQ7_ALLOWED_VALUES

    assert SQS_SQ7_ALLOWED_VALUES == (
        "I - High Critical",
        "II - Medium Critical",
        "III - Low Critical",
        "IV - Non Critical",
    )


def test_sqs_sq7_required_columns_constant():
    from src.custom_dqr_engine import SQS_SQ7_REQUIRED_COLUMNS

    assert SQS_SQ7_REQUIRED_COLUMNS == {
        "Work Criticality": "WORK_CRITICALITY",
    }


def test_sqs_sq7_passes_for_every_allowed_value():
    from src.custom_dqr_engine import SQS_SQ7_ALLOWED_VALUES, check_sqs_sq7

    df = pd.DataFrame({"WORK_CRITICALITY": list(SQS_SQ7_ALLOWED_VALUES)})
    assert check_sqs_sq7(df).tolist() == [True] * len(SQS_SQ7_ALLOWED_VALUES)


def test_sqs_sq7_fails_on_null():
    from src.custom_dqr_engine import check_sqs_sq7

    df = pd.DataFrame({
        "WORK_CRITICALITY": ["I - High Critical", None, "IV - Non Critical"]
    })
    assert check_sqs_sq7(df).tolist() == [True, False, True]


def test_sqs_sq7_fails_on_case_mismatch():
    """The match is case-sensitive per the Snowflake ``IN`` operator -
    ``"i - high critical"`` and ``"I - HIGH CRITICAL"`` both FAIL."""
    from src.custom_dqr_engine import check_sqs_sq7

    df = pd.DataFrame({
        "WORK_CRITICALITY": [
            "I - High Critical",
            "i - high critical",
            "I - HIGH CRITICAL",
        ]
    })
    assert check_sqs_sq7(df).tolist() == [True, False, False]


def test_sqs_sq7_fails_on_empty_string_and_unexpected_value():
    from src.custom_dqr_engine import check_sqs_sq7

    df = pd.DataFrame({
        "WORK_CRITICALITY": [
            "II - Medium Critical",
            "",
            "V - Unknown",
            "High",
        ]
    })
    assert check_sqs_sq7(df).tolist() == [True, False, False, False]


def test_sqs_sq7_fails_for_all_rows_when_column_missing():
    from src.custom_dqr_engine import check_sqs_sq7

    df = pd.DataFrame({"OTHER_COL": ["x", "y"]})
    assert check_sqs_sq7(df).tolist() == [False, False]


def test_sqs_sq7_handles_empty_dataframe():
    from src.custom_dqr_engine import check_sqs_sq7

    df = pd.DataFrame({"WORK_CRITICALITY": pd.Series([], dtype=object)})
    out = check_sqs_sq7(df)
    assert isinstance(out, pd.Series)
    assert len(out) == 0


def test_sqs_sq7_dispatches_through_quality_domain(monkeypatch):
    """End-to-end via the dispatcher: switching to Quality and asking for
    SQ7 surfaces the rule with the correct row verdicts."""
    from config.domains import DOMAIN_QUALITY
    from src.custom_dqr_engine import evaluate_custom_rules
    from src.models import CustomDQRAssignment

    monkeypatch.setattr(
        "config.domains.get_active_domain_code",
        lambda: DOMAIN_QUALITY,
    )

    df = pd.DataFrame({
        "WORK_CRITICALITY": [
            "I - High Critical",
            None,
            "V - Unknown",
            "IV - Non Critical",
        ],
    })
    assignments = [CustomDQRAssignment(rule_id="SQ7", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "SQS")
    assert list(out.columns) == ["SQ7"]
    assert out["SQ7"].tolist() == [True, False, False, True]
    assert not_evaluated == {}


# =============================================================================
# SQ8: STATUS required (Completeness)
# =============================================================================

def test_sqs_sq8_required_columns_constant():
    from src.custom_dqr_engine import SQS_SQ8_REQUIRED_COLUMNS

    assert SQS_SQ8_REQUIRED_COLUMNS == {"Status": "STATUS"}


def test_sqs_sq8_passes_when_status_populated():
    from src.custom_dqr_engine import check_sqs_sq8

    df = pd.DataFrame({
        "STATUS": ["OPEN", "Completed", "In Progress", "REJECTED"],
    })
    assert check_sqs_sq8(df).tolist() == [True, True, True, True]


def test_sqs_sq8_fails_on_null():
    from src.custom_dqr_engine import check_sqs_sq8

    df = pd.DataFrame({"STATUS": ["OPEN", None, "CLOSED"]})
    assert check_sqs_sq8(df).tolist() == [True, False, True]


def test_sqs_sq8_fails_on_empty_string():
    from src.custom_dqr_engine import check_sqs_sq8

    df = pd.DataFrame({"STATUS": ["OPEN", "", "CLOSED"]})
    assert check_sqs_sq8(df).tolist() == [True, False, True]


def test_sqs_sq8_fails_on_whitespace_only():
    """The spec uses ``TRIM(STATUS) = ''`` so any whitespace-only value
    (spaces, tabs, newlines) FAILs."""
    from src.custom_dqr_engine import check_sqs_sq8

    df = pd.DataFrame({"STATUS": ["OPEN", "   ", "\t\n", "  \t  "]})
    assert check_sqs_sq8(df).tolist() == [True, False, False, False]


def test_sqs_sq8_fails_for_all_rows_when_column_missing():
    from src.custom_dqr_engine import check_sqs_sq8

    df = pd.DataFrame({"OTHER_COL": ["x", "y"]})
    assert check_sqs_sq8(df).tolist() == [False, False]


def test_sqs_sq8_handles_empty_dataframe():
    from src.custom_dqr_engine import check_sqs_sq8

    df = pd.DataFrame({"STATUS": pd.Series([], dtype=object)})
    out = check_sqs_sq8(df)
    assert isinstance(out, pd.Series)
    assert len(out) == 0


def test_sqs_sq8_dispatches_through_quality_domain(monkeypatch):
    """End-to-end via the dispatcher: switching to Quality and asking for
    SQ8 surfaces the rule with the correct row verdicts."""
    from config.domains import DOMAIN_QUALITY
    from src.custom_dqr_engine import evaluate_custom_rules
    from src.models import CustomDQRAssignment

    monkeypatch.setattr(
        "config.domains.get_active_domain_code",
        lambda: DOMAIN_QUALITY,
    )

    df = pd.DataFrame({
        "STATUS": ["OPEN", None, "   ", "Completed"],
    })
    assignments = [CustomDQRAssignment(rule_id="SQ8", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "SQS")
    assert list(out.columns) == ["SQ8"]
    assert out["SQ8"].tolist() == [True, False, False, True]
    assert not_evaluated == {}


# =============================================================================
# SQ9: STATUS value in allowed set (Validity)
# =============================================================================

def test_sqs_sq9_allowed_values_constant():
    """Allowed-value tuple matches the SQL spec verbatim (11 canonical
    workflow statuses, in the documented order)."""
    from src.custom_dqr_engine import SQS_SQ9_ALLOWED_VALUES

    assert SQS_SQ9_ALLOWED_VALUES == (
        "Approved",
        "Inspection In Progress",
        "Completed",
        "Inspection Approved",
        "Pending SER Review",
        "Additional Funding Requested",
        "Deprecated",
        "Pending Review",
        "Completed (Short Closed)",
        "Inspection Rejected",
        "OAP Pending",
    )


def test_sqs_sq9_required_columns_constant():
    from src.custom_dqr_engine import SQS_SQ9_REQUIRED_COLUMNS

    assert SQS_SQ9_REQUIRED_COLUMNS == {"Status": "STATUS"}


def test_sqs_sq9_passes_for_every_allowed_value():
    from src.custom_dqr_engine import SQS_SQ9_ALLOWED_VALUES, check_sqs_sq9

    df = pd.DataFrame({"STATUS": list(SQS_SQ9_ALLOWED_VALUES)})
    assert check_sqs_sq9(df).tolist() == [True] * len(SQS_SQ9_ALLOWED_VALUES)


def test_sqs_sq9_fails_on_null():
    from src.custom_dqr_engine import check_sqs_sq9

    df = pd.DataFrame({"STATUS": ["Approved", None, "Completed"]})
    assert check_sqs_sq9(df).tolist() == [True, False, True]


def test_sqs_sq9_fails_on_case_mismatch():
    """Match is case-sensitive per the Snowflake ``IN`` operator -
    ``"approved"`` and ``"APPROVED"`` both FAIL."""
    from src.custom_dqr_engine import check_sqs_sq9

    df = pd.DataFrame({
        "STATUS": ["Approved", "approved", "APPROVED"]
    })
    assert check_sqs_sq9(df).tolist() == [True, False, False]


def test_sqs_sq9_fails_on_leading_or_trailing_whitespace():
    """Spec calls out `` Approved `` as FAIL - ``isin`` performs an
    exact equality match, so surrounding whitespace breaks it."""
    from src.custom_dqr_engine import check_sqs_sq9

    df = pd.DataFrame({
        "STATUS": ["Approved", " Approved", "Approved ", " Approved "]
    })
    assert check_sqs_sq9(df).tolist() == [True, False, False, False]


def test_sqs_sq9_fails_on_unexpected_value():
    from src.custom_dqr_engine import check_sqs_sq9

    df = pd.DataFrame({
        "STATUS": ["Completed", "Cancelled", "In Progress", ""]
    })
    # "Cancelled" is off-list; "In Progress" is off-list (canonical form
    # is "Inspection In Progress"); empty string is off-list.
    assert check_sqs_sq9(df).tolist() == [True, False, False, False]


def test_sqs_sq9_fails_for_all_rows_when_column_missing():
    from src.custom_dqr_engine import check_sqs_sq9

    df = pd.DataFrame({"OTHER_COL": ["x", "y"]})
    assert check_sqs_sq9(df).tolist() == [False, False]


def test_sqs_sq9_handles_empty_dataframe():
    from src.custom_dqr_engine import check_sqs_sq9

    df = pd.DataFrame({"STATUS": pd.Series([], dtype=object)})
    out = check_sqs_sq9(df)
    assert isinstance(out, pd.Series)
    assert len(out) == 0


def test_sqs_sq9_dispatches_through_quality_domain(monkeypatch):
    """End-to-end via the dispatcher: switching to Quality and asking
    for SQ9 surfaces the rule with the correct row verdicts."""
    from config.domains import DOMAIN_QUALITY
    from src.custom_dqr_engine import evaluate_custom_rules
    from src.models import CustomDQRAssignment

    monkeypatch.setattr(
        "config.domains.get_active_domain_code",
        lambda: DOMAIN_QUALITY,
    )

    df = pd.DataFrame({
        "STATUS": [
            "Inspection In Progress",
            None,
            "Cancelled",
            "Completed",
        ],
    })
    assignments = [CustomDQRAssignment(rule_id="SQ9", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "SQS")
    assert list(out.columns) == ["SQ9"]
    assert out["SQ9"].tolist() == [True, False, False, True]
    assert not_evaluated == {}


def test_sqs_sq8_and_sq9_layer_correctly():
    """SQ8 (Completeness) and SQ9 (Validity in allowed set) target the
    same column. A populated-but-off-list value should PASS SQ8 and
    FAIL SQ9; a NULL should FAIL both."""
    from src.custom_dqr_engine import check_sqs_sq8, check_sqs_sq9

    df = pd.DataFrame({
        "STATUS": ["Approved", "Cancelled", None, "   "],
    })
    # SQ8: PASS, PASS (populated), FAIL (null), FAIL (whitespace)
    assert check_sqs_sq8(df).tolist() == [True, True, False, False]
    # SQ9: PASS, FAIL (off-list), FAIL (null), FAIL ("   " not in set)
    assert check_sqs_sq9(df).tolist() == [True, False, False, False]


# =============================================================================
# SQ10: Status / Expected Ship Date sequencing (Business Rule)
# =============================================================================

def test_sqs_sq10_required_columns_constant():
    from src.custom_dqr_engine import SQS_SQ10_REQUIRED_COLUMNS

    assert SQS_SQ10_REQUIRED_COLUMNS == {
        "Status": "STATUS",
        "Expected Ship Date": "EXPECTED_SHIP_DATE",
    }


def test_sqs_sq10_completed_status_constant():
    from src.custom_dqr_engine import SQS_SQ10_COMPLETED_STATUS

    assert SQS_SQ10_COMPLETED_STATUS == "Completed"


def test_sqs_sq10_passes_when_status_is_not_completed():
    """Every status other than ``"Completed"`` is out of scope - even a
    far-future ship date PASSes when STATUS isn't ``"Completed"``."""
    from src.custom_dqr_engine import check_sqs_sq10

    future = pd.Timestamp.now() + pd.Timedelta(days=365)
    df = pd.DataFrame({
        "STATUS": ["Approved", "In Progress", "Pending", "Inspection Approved"],
        "EXPECTED_SHIP_DATE": [future, future, future, future],
    })
    assert check_sqs_sq10(df).tolist() == [True, True, True, True]


def test_sqs_sq10_passes_when_completed_with_past_date():
    from src.custom_dqr_engine import check_sqs_sq10

    past = pd.Timestamp.now() - pd.Timedelta(days=30)
    df = pd.DataFrame({
        "STATUS": ["Completed"],
        "EXPECTED_SHIP_DATE": [past],
    })
    assert check_sqs_sq10(df).tolist() == [True]


def test_sqs_sq10_fails_when_completed_with_future_date():
    from src.custom_dqr_engine import check_sqs_sq10

    future = pd.Timestamp.now() + pd.Timedelta(days=30)
    df = pd.DataFrame({
        "STATUS": ["Completed"],
        "EXPECTED_SHIP_DATE": [future],
    })
    assert check_sqs_sq10(df).tolist() == [False]


def test_sqs_sq10_passes_when_completed_with_null_date():
    """Spec: completed record with NULL ship date PASSes (the rule
    targets future dates only; date completeness is SQ4's concern)."""
    from src.custom_dqr_engine import check_sqs_sq10

    df = pd.DataFrame({
        "STATUS": ["Completed"],
        "EXPECTED_SHIP_DATE": [None],
    })
    assert check_sqs_sq10(df).tolist() == [True]


def test_sqs_sq10_passes_when_unparseable_date():
    """Unparseable string ship date collapses to NaT after
    ``pd.to_datetime(errors='coerce')`` and PASSes - same NULL handling
    as the rest of the spec."""
    from src.custom_dqr_engine import check_sqs_sq10

    df = pd.DataFrame({
        "STATUS": ["Completed"],
        "EXPECTED_SHIP_DATE": ["not-a-date"],
    })
    assert check_sqs_sq10(df).tolist() == [True]


def test_sqs_sq10_mixed_rows():
    from src.custom_dqr_engine import check_sqs_sq10

    now = pd.Timestamp.now()
    past = now - pd.Timedelta(days=30)
    future = now + pd.Timedelta(days=30)
    df = pd.DataFrame({
        "STATUS": [
            "Completed",        # past → PASS
            "Completed",        # future → FAIL
            "Completed",        # NULL → PASS
            "Approved",         # future, but not completed → PASS
            "Approved",         # past → PASS
        ],
        "EXPECTED_SHIP_DATE": [past, future, None, future, past],
    })
    assert check_sqs_sq10(df).tolist() == [True, False, True, True, True]


def test_sqs_sq10_completed_status_match_is_case_sensitive():
    """Per spec ``STATUS = 'Completed'`` is the trigger predicate, an
    exact match. ``"completed"`` (lowercase) is out of scope and PASSes
    even when paired with a future ship date - SQ9 owns the
    case-sensitivity gripe on STATUS itself."""
    from src.custom_dqr_engine import check_sqs_sq10

    future = pd.Timestamp.now() + pd.Timedelta(days=30)
    df = pd.DataFrame({
        "STATUS": ["Completed", "completed", "COMPLETED"],
        "EXPECTED_SHIP_DATE": [future, future, future],
    })
    assert check_sqs_sq10(df).tolist() == [False, True, True]


def test_sqs_sq10_fails_for_all_rows_when_status_column_missing():
    from src.custom_dqr_engine import check_sqs_sq10

    df = pd.DataFrame({"EXPECTED_SHIP_DATE": [pd.Timestamp.now()]})
    assert check_sqs_sq10(df).tolist() == [False]


def test_sqs_sq10_fails_for_all_rows_when_ship_date_column_missing():
    from src.custom_dqr_engine import check_sqs_sq10

    df = pd.DataFrame({"STATUS": ["Completed"]})
    assert check_sqs_sq10(df).tolist() == [False]


def test_sqs_sq10_handles_empty_dataframe():
    from src.custom_dqr_engine import check_sqs_sq10

    df = pd.DataFrame({
        "STATUS": pd.Series([], dtype=object),
        "EXPECTED_SHIP_DATE": pd.to_datetime([]),
    })
    out = check_sqs_sq10(df)
    assert isinstance(out, pd.Series)
    assert len(out) == 0


def test_sqs_sq10_dispatches_through_quality_domain(monkeypatch):
    """End-to-end via the dispatcher: switching to Quality and asking
    for SQ10 surfaces the rule with the correct row verdicts."""
    from config.domains import DOMAIN_QUALITY
    from src.custom_dqr_engine import evaluate_custom_rules
    from src.models import CustomDQRAssignment

    monkeypatch.setattr(
        "config.domains.get_active_domain_code",
        lambda: DOMAIN_QUALITY,
    )

    now = pd.Timestamp.now()
    df = pd.DataFrame({
        "STATUS": ["Completed", "Completed", "Approved"],
        "EXPECTED_SHIP_DATE": [
            now - pd.Timedelta(days=30),    # past → PASS
            now + pd.Timedelta(days=30),    # future → FAIL
            now + pd.Timedelta(days=30),    # future, non-completed → PASS
        ],
    })
    assignments = [CustomDQRAssignment(rule_id="SQ10", weight=100.0)]
    out, not_evaluated = evaluate_custom_rules(df, assignments, "SQS")
    assert list(out.columns) == ["SQ10"]
    assert out["SQ10"].tolist() == [True, False, True]
    assert not_evaluated == {}


def test_evaluate_custom_rules_downgrades_unexpected_exception(monkeypatch):
    """A custom check raising a NON-CustomRuleNotEvaluated error must be
    recorded in ``not_evaluated`` and omitted from the results - never
    propagated. Otherwise a single rule bug would crash the whole Step 6
    dashboard (the H1 finding). Mirrors evaluate_all_safe for Standard rules.
    """
    import config.custom_dqr_catalog as cat

    class _BoomRule:
        id = "BOOM"

        def check(self, df):  # no ``params`` kwarg -> called as check(df)
            raise ValueError("kaboom")

    monkeypatch.setattr(cat, "get_available_custom_dqr_rules", lambda dp: [_BoomRule()])

    df = pd.DataFrame({"X": [1, 2, 3]})
    out, not_evaluated = evaluate_custom_rules(
        df, [CustomDQRAssignment(rule_id="BOOM", weight=100.0)], "EPT"
    )
    assert "BOOM" not in out.columns
    assert "BOOM" in not_evaluated
    assert "kaboom" in not_evaluated["BOOM"]


def test_evaluate_custom_rules_records_segmented_rule_not_evaluated(monkeypatch):
    """The dispatcher must RECORD a CustomRuleNotEvaluated raised by a rule
    (with params plumbed through), not silently pass it. E6 with segmentation
    on and the VWS_GP_STANDARD_SHARE reference unavailable raises; assert
    evaluate_custom_rules surfaces it in not_evaluated and omits it from the
    results. Covers a segmented rule routed through the dispatcher - the audit
    noted only the E7 referential-integrity case proved the recording path."""
    import src.reference_data as ref_mod
    from src.custom_dqr_engine import EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM

    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)
    monkeypatch.setattr(
        ref_mod, "get_reference_dataset_error", lambda name: "network down"
    )
    df = _make_e6_df(_e6_normal_population(n=6, ratio=50.0))
    out, not_evaluated = evaluate_custom_rules(
        df,
        [CustomDQRAssignment(
            rule_id="E6", weight=100,
            params={EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM: True},
        )],
        "EPT",
    )
    assert "E6" not in out.columns
    assert "E6" in not_evaluated
    assert not_evaluated["E6"]  # a human-readable reason was recorded
