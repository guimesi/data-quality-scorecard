"""Scope-aware custom rules (``CustomRuleDef.applicable``, 2026-10-30).

A rule may declare the rows it applies to. Not-applicable rows PASS (row
scores, colours and the overall score are untouched) but are left out of
the rule's pass-rate denominator, so DQ-ACCE-5 reads "failing / equipment
lines with a quantity" instead of "failing / all 835,280 lines".
"""
from __future__ import annotations

import pandas as pd
import pytest

from config.custom_dqr_catalog import get_available_custom_dqr_rules
from src.custom_dqr_engine import (
    acce_ac5_applicable,
    acce_ac6_applicable,
    evaluate_custom_rules,
    evaluate_custom_rules_scoped,
)
from src.models import CustomDQRAssignment, DataProduct, DataProductConfig
from src.scorecard import compute_scorecard

# ----------------------------------------------------------------- fixtures

_AC5_COLS = ["DESCRIPTION", "QTY_KEY_QTY", "QTY_OTHER_QTY", "COA", "DESIGN_KEY_PARAMETER_NAMES"]
_AC6_COLS = ["QTY_KEY_QTY", "QTY_OTHER_QTY", "COST_MH", "COST_LABOR_COST"]


def _ac5_frame():
    """6 rows: 3 equipment lines with a quantity (2 with a design, 1 without),
    1 equipment line without quantity, 2 bulk lines with a quantity and no
    design."""
    return pd.DataFrame({
        "DESCRIPTION": ["CENTRIFUGAL PUMPS", "S&T EXCHANGER", "MIXERS",
                        "CENTRIFUGAL PUMPS", "CS REMOTE SHOP MATERIAL", "PIPE INSULATION"],
        "QTY_KEY_QTY": [2.0, 1.0, 3.0, 0.0, 120.0, 120.0],
        "QTY_OTHER_QTY": [None] * 6,
        "COA": ["3240", "3110", "3300", "3240", "3110", "8110"],
        "DESIGN_KEY_PARAMETER_NAMES": ["Pump type|Item type", "Item type", None, None, None, None],
    })


def _ac6_frame():
    """5 rows: 2 labor-costed lines with a quantity (1 with hours, 1 without),
    2 material lines (quantity, no labor, no hours), 1 line without quantity."""
    return pd.DataFrame({
        "QTY_KEY_QTY": [120.0, 120.0, 120.0, 6.0, 0.0],
        "QTY_OTHER_QTY": [None] * 5,
        "COST_MH": [85.0, 0.0, 0.0, 0.0, 0.0],
        "COST_LABOR_COST": [850.0, 850.0, 0.0, None, 850.0],
    })


# ------------------------------------------------------------- catalog field

def test_only_acce_5_and_6_declare_a_scope():
    scoped = {
        r.id for code in ("ADR", "ACCE", "EPT", "SQS")
        for r in get_available_custom_dqr_rules(code, include_inactive=True)
        if r.applicable is not None
    }
    assert scoped == {"DQ-ACCE-5", "DQ-ACCE-6"}


# -------------------------------------------------------- scope callables

def test_acce_ac5_applicable_marks_equipment_lines_with_a_quantity():
    scope = acce_ac5_applicable(_ac5_frame())
    assert scope.tolist() == [True, True, True, False, False, False]


def test_acce_ac6_applicable_marks_labor_costed_lines_with_a_quantity():
    scope = acce_ac6_applicable(_ac6_frame())
    assert scope.tolist() == [True, True, False, False, False]


@pytest.mark.parametrize("fn, cols", [
    (acce_ac5_applicable, _AC5_COLS),
    (acce_ac6_applicable, _AC6_COLS),
])
def test_scope_is_every_row_when_a_required_column_is_missing(fn, cols):
    """A structural failure (missing column → every row FAILS) must stay
    visible as 0%, so the whole frame counts as in scope."""
    df = pd.DataFrame({c: [1.0, 2.0] for c in cols if c != cols[0]})
    assert fn(df).tolist() == [True, True]
    assert fn(pd.DataFrame({c: [] for c in cols})).tolist() == []


# ---------------------------------------------------------------- dispatcher

def test_scoped_evaluation_forces_not_applicable_rows_to_pass():
    ev = evaluate_custom_rules_scoped(
        _ac5_frame(), [CustomDQRAssignment(rule_id="DQ-ACCE-5", weight=100.0)], "ACCE",
    )
    assert ev.results["DQ-ACCE-5"].tolist() == [True, True, False, True, True, True]
    assert ev.applicable["DQ-ACCE-5"].tolist() == [True, True, True, False, False, False]
    assert ev.applicable_counts() == {"DQ-ACCE-5": 3}
    assert ev.not_evaluated == {}


def test_scoped_evaluation_is_all_true_for_rules_without_a_scope():
    df = pd.DataFrame({"COA": ["3240", None], "COST_MH": [1.0, 1.0]})
    ev = evaluate_custom_rules_scoped(
        df, [CustomDQRAssignment(rule_id="DQ-ACCE-1", weight=100.0)], "ACCE",
    )
    assert ev.applicable["DQ-ACCE-1"].tolist() == [True, True]
    assert ev.applicable_counts() == {"DQ-ACCE-1": 2}


def test_two_tuple_wrapper_returns_the_same_pass_flags():
    assignments = [CustomDQRAssignment(rule_id="DQ-ACCE-6", weight=100.0)]
    ev = evaluate_custom_rules_scoped(_ac6_frame(), assignments, "ACCE")
    results, not_evaluated = evaluate_custom_rules(_ac6_frame(), assignments, "ACCE")
    pd.testing.assert_frame_equal(results, ev.results)
    assert not_evaluated == ev.not_evaluated == {}
    # labor-costed line without hours is the only failure
    assert results["DQ-ACCE-6"].tolist() == [True, False, True, True, True]


# ----------------------------------------------------------------- scorecard

def _custom_only(df, rule_id, system="ACCE"):
    dp = DataProduct(system_code=system, name=system, df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code=system, cdes=[], assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id=rule_id, weight=100.0)],
        dqr_sources=["custom"], source_weights={"custom": 100.0},
    )
    return compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)


def test_pass_rate_is_computed_over_the_rows_in_scope():
    result = _custom_only(_ac5_frame(), "DQ-ACCE-5")
    # 1 failing equipment line out of 3 in scope → 66.67%, not 5/6 = 83.33%
    assert result.custom_rule_pass_rates["DQ-ACCE-5"] == pytest.approx(200 / 3)
    assert result.custom_rule_applicable_rows == {"DQ-ACCE-5": 3}
    assert result.custom_rule_row_pass_rates["DQ-ACCE-5"] == pytest.approx(500 / 6)


def test_row_scores_and_overall_are_unaffected_by_the_scope():
    """Not-applicable rows pass for the row score, so the overall score and
    the buckets are exactly what the unscoped engine produced."""
    result = _custom_only(_ac5_frame(), "DQ-ACCE-5")
    assert result.row_scores.tolist() == [100.0, 100.0, 0.0, 100.0, 100.0, 100.0]
    assert result.overall_score == pytest.approx(500 / 6)
    assert result.custom_score == pytest.approx(500 / 6)
    assert (result.rows_green, result.rows_yellow, result.rows_red) == (5, 0, 1)


def test_rule_with_nothing_in_scope_rates_100():
    df = _ac5_frame().iloc[3:]            # no equipment line with a quantity
    result = _custom_only(df, "DQ-ACCE-5")
    assert result.custom_rule_pass_rates["DQ-ACCE-5"] == 100.0
    assert result.custom_rule_applicable_rows == {"DQ-ACCE-5": 0}


def test_unscoped_rules_keep_the_all_rows_denominator():
    df = pd.DataFrame({"COA": ["3240", "", "3110", None], "COST_MH": [1.0] * 4})
    result = _custom_only(df, "DQ-ACCE-1")
    assert result.custom_rule_applicable_rows == {"DQ-ACCE-1": 4}
    assert result.custom_rule_pass_rates["DQ-ACCE-1"] == result.custom_rule_row_pass_rates["DQ-ACCE-1"]


def test_acce_6_production_shape_reads_the_in_scope_rate():
    result = _custom_only(_ac6_frame(), "DQ-ACCE-6")
    assert result.custom_rule_applicable_rows == {"DQ-ACCE-6": 2}
    assert result.custom_rule_pass_rates["DQ-ACCE-6"] == 50.0      # 1 of 2 labor-costed lines
    assert result.custom_rule_row_pass_rates["DQ-ACCE-6"] == 80.0  # 4 of 5 rows


# ------------------------------------------------------------ dashboard rows

def test_custom_rule_rows_carry_the_rows_in_scope():
    from ui.step_06._rule_rows import custom_rule_rows
    df = _ac5_frame()
    dp = DataProduct(system_code="ACCE", name="ACCE", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="ACCE", cdes=[], assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="DQ-ACCE-5", weight=100.0)],
        dqr_sources=["custom"], source_weights={"custom": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    rows = custom_rule_rows("ACCE", cfg, result)
    assert rows[0]["rows_in_scope"] == 3
    # A result that predates the scope-aware engine falls back to every row.
    result.custom_rule_applicable_rows = {}
    assert custom_rule_rows("ACCE", cfg, result)[0]["rows_in_scope"] == 6
