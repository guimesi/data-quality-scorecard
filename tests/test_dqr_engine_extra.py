"""Extra tests for src/dqr_engine.py to cover the remaining branches:
validity (datetime/numeric/regex/length), consistency (all operators),
timeliness, currency, integrity, conformity (empty), precision (non-numeric
and exception path), evaluate_rule dispatch error, and suggest_assignments_for_cde.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.dqr_engine import (
    evaluate_rule,
    suggest_assignments_for_cde,
)
from src.models import ColumnProfile, DQRAssignment

# ---------------------------------------------------------------------------
# Validity
# ---------------------------------------------------------------------------

def test_validity_on_datetime_column():
    df = pd.DataFrame({"D": pd.to_datetime(["2024-01-01", None, "2024-06-01"])})
    a = DQRAssignment(cde_column="D", dimension="Validity")
    result = evaluate_rule(df, a)
    assert result.tolist() == [True, False, True]


def test_validity_on_numeric_column():
    df = pd.DataFrame({"N": [1.0, float("inf"), np.nan, 5.0]})
    a = DQRAssignment(cde_column="N", dimension="Validity")
    result = evaluate_rule(df, a)
    # NaN and inf both fail; fill+isfinite => True only for 1.0 and 5.0
    assert result.tolist() == [True, False, False, True]


def test_validity_regex_and_length():
    df = pd.DataFrame({"S": ["abc", "AB12", "x", None, "abcdef"]})
    a = DQRAssignment(
        cde_column="S",
        dimension="Validity",
        params={"regex": r"[a-z]+", "min_length": 2, "max_length": 4},
    )
    result = evaluate_rule(df, a)
    # "abc": regex OK, len 3 OK -> True
    # "AB12": regex fail (uppercase/digits) -> False
    # "x": regex OK but len 1 < 2 -> False
    # None: None -> False
    # "abcdef": regex OK but len 6 > 4 -> False
    assert result.tolist() == [True, False, False, False, False]


def test_validity_string_without_regex_just_checks_notna():
    df = pd.DataFrame({"S": ["a", "", None]})
    a = DQRAssignment(cde_column="S", dimension="Validity")
    result = evaluate_rule(df, a)
    # Nulls fail; empty string still notna -> True
    assert result.tolist() == [True, True, False]


# ---------------------------------------------------------------------------
# Consistency, each operator + unconfigured branch
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "op,expected",
    [
        ("<=", [True, True, False]),
        ("<", [True, False, False]),
        (">=", [False, True, True]),
        (">", [False, False, True]),
        ("==", [False, True, False]),
        ("!=", [True, False, True]),
    ],
)
def test_consistency_operators(op, expected):
    df = pd.DataFrame({"A": [1, 2, 3], "B": [2, 2, 2]})
    a = DQRAssignment(
        cde_column="A",
        dimension="Consistency",
        params={"compare_column": "B", "operator": op},
    )
    assert evaluate_rule(df, a).tolist() == expected


def test_consistency_unknown_operator_returns_all_true():
    df = pd.DataFrame({"A": [1, 2], "B": [2, 2]})
    a = DQRAssignment(
        cde_column="A",
        dimension="Consistency",
        params={"compare_column": "B", "operator": "~="},
    )
    assert evaluate_rule(df, a).tolist() == [True, True]


def test_consistency_missing_compare_column_is_noop():
    df = pd.DataFrame({"A": [1, 2, 3]})
    a = DQRAssignment(
        cde_column="A",
        dimension="Consistency",
        params={"compare_column": "MISSING"},
    )
    assert evaluate_rule(df, a).tolist() == [True, True, True]


def test_consistency_no_compare_column_configured():
    df = pd.DataFrame({"A": [1, 2, 3]})
    a = DQRAssignment(cde_column="A", dimension="Consistency", params={})
    assert evaluate_rule(df, a).tolist() == [True, True, True]


def test_consistency_null_in_either_side_passes():
    df = pd.DataFrame({"A": [1, None, 5], "B": [2, 2, None]})
    a = DQRAssignment(
        cde_column="A",
        dimension="Consistency",
        params={"compare_column": "B", "operator": "<="},
    )
    # Both-present: row 0 -> 1<=2 True; row 1 -> A is null, passes; row 2 -> B null, passes
    assert evaluate_rule(df, a).tolist() == [True, True, True]


# ---------------------------------------------------------------------------
# Timeliness + Currency (both naive and tz-aware)
# ---------------------------------------------------------------------------

def test_timeliness_naive_dates():
    today = datetime.now()
    df = pd.DataFrame({"D": [today - timedelta(days=5), today - timedelta(days=60), None]})
    a = DQRAssignment(cde_column="D", dimension="Timeliness", params={"max_lag_days": 30})
    assert evaluate_rule(df, a).tolist() == [True, False, False]


def test_timeliness_tz_aware_dates_handled():
    """Regression: mixing tz-aware dates with tz-naive datetime.now() used to crash."""
    today = pd.Timestamp.utcnow()
    df = pd.DataFrame({
        "D": pd.to_datetime([
            today - pd.Timedelta(days=2),
            today - pd.Timedelta(days=100),
        ], utc=True),
    })
    a = DQRAssignment(cde_column="D", dimension="Timeliness", params={"max_lag_days": 30})
    assert evaluate_rule(df, a).tolist() == [True, False]


def test_currency_default_params():
    today = datetime.now()
    df = pd.DataFrame({"D": [today - timedelta(days=100), today - timedelta(days=5000)]})
    a = DQRAssignment(cde_column="D", dimension="Currency", params={"max_age_days": 365})
    assert evaluate_rule(df, a).tolist() == [True, False]


# ---------------------------------------------------------------------------
# Conformity + Integrity
# ---------------------------------------------------------------------------

def test_conformity_with_empty_allowed_returns_all_true():
    df = pd.DataFrame({"X": ["A", "B"]})
    a = DQRAssignment(cde_column="X", dimension="Conformity", params={"allowed_values": []})
    assert evaluate_rule(df, a).tolist() == [True, True]


def test_integrity_with_references():
    df = pd.DataFrame({"X": ["ref1", "ref2", "missing"]})
    a = DQRAssignment(
        cde_column="X",
        dimension="Integrity",
        params={"reference_values": ["ref1", "ref2"]},
    )
    assert evaluate_rule(df, a).tolist() == [True, True, False]


def test_integrity_without_references_falls_back_to_notna():
    df = pd.DataFrame({"X": ["a", None, "b"]})
    a = DQRAssignment(cde_column="X", dimension="Integrity", params={})
    assert evaluate_rule(df, a).tolist() == [True, False, True]


# ---------------------------------------------------------------------------
# Precision
# ---------------------------------------------------------------------------

def test_precision_non_numeric_returns_all_true():
    df = pd.DataFrame({"S": ["a", "b"]})
    a = DQRAssignment(cde_column="S", dimension="Precision", params={"max_decimals": 2})
    assert evaluate_rule(df, a).tolist() == [True, True]


def test_precision_nan_fails():
    """NaN is treated as a precision failure."""
    df = pd.DataFrame({"N": pd.Series([float("nan"), 1.0, 1.23])})
    a = DQRAssignment(cde_column="N", dimension="Precision", params={"max_decimals": 2})
    assert evaluate_rule(df, a).tolist() == [False, True, True]


# ---------------------------------------------------------------------------
# Dispatch error
# ---------------------------------------------------------------------------

def test_evaluate_rule_unknown_dimension_raises():
    df = pd.DataFrame({"X": [1, 2]})
    a = DQRAssignment(cde_column="X", dimension="NotARealDimension")
    with pytest.raises(KeyError, match="Dimension not implemented"):
        evaluate_rule(df, a)


# ---------------------------------------------------------------------------
# suggest_assignments_for_cde
# ---------------------------------------------------------------------------

def test_suggest_assignments_pre_fills_accuracy_from_profile():
    """Accuracy min_value/max_value are pre-filled from the column profile."""
    profile = ColumnProfile(
        name="AMOUNT",
        dtype="float64",
        column_type_group="float",
        total_rows=10,
        null_count=0,
        null_pct=0.0,
        distinct_count=8,
        duplicate_count=2,
        sample_values=[1.0, 2.0],
        min_value=0.0,
        max_value=1000.0,
    )
    assignments = suggest_assignments_for_cde(profile)
    acc = next(a for a in assignments if a.dimension == "Accuracy")
    assert acc.params["min_value"] == 0.0
    assert acc.params["max_value"] == 1000.0


def test_suggest_assignments_accuracy_handles_bad_min_max():
    profile = ColumnProfile(
        name="AMOUNT",
        dtype="float64",
        column_type_group="float",
        total_rows=10,
        null_count=0,
        null_pct=0.0,
        distinct_count=8,
        duplicate_count=2,
        sample_values=[],
        min_value="not-a-number",  # triggers the except branch
        max_value=1000.0,
    )
    # Should NOT raise; just leave params untouched
    assignments = suggest_assignments_for_cde(profile)
    acc = next(a for a in assignments if a.dimension == "Accuracy")
    assert acc.params.get("min_value") is None or isinstance(acc.params.get("min_value"), float) is False


def test_suggest_assignments_conformity_branch_low_cardinality():
    profile = ColumnProfile(
        name="CATEGORY",
        dtype="object",
        column_type_group="categorical",
        total_rows=100,
        null_count=0,
        null_pct=0.0,
        distinct_count=5,   # <= 30 triggers the Conformity branch pass-through
        duplicate_count=95,
        sample_values=["A", "B"],
    )
    assignments = suggest_assignments_for_cde(profile)
    dims = {a.dimension for a in assignments}
    assert "Conformity" in dims
