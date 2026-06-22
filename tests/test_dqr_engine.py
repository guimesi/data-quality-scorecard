"""Tests for the DQR engine."""
import pandas as pd

from src.dqr_engine import evaluate_all, evaluate_rule, suggest_assignments_for_cde
from src.models import DQRAssignment
from src.profiler import profile_column


def test_completeness_detects_nulls(sample_df):
    a = DQRAssignment(cde_column="PLANVIEW_ID", dimension="Completeness")
    result = evaluate_rule(sample_df, a)
    # One null in row index 3
    assert result.tolist() == [True, True, True, False, True]


def test_uniqueness_detects_duplicates(sample_df):
    a = DQRAssignment(cde_column="PLANVIEW_ID", dimension="Uniqueness")
    result = evaluate_rule(sample_df, a)
    # PV-002 appears twice (rows 1 and 4) -> both fail.
    # Single NaN is "unique" by value-count semantics (nullness is Completeness' concern).
    assert result.tolist() == [True, False, True, True, False]


def test_accuracy_range(sample_df):
    a = DQRAssignment(
        cde_column="AMOUNT",
        dimension="Accuracy",
        params={"min_value": 0, "max_value": 1000},
    )
    result = evaluate_rule(sample_df, a)
    # Row 2 is -50 (fails), row 3 is 9999999 (fails); others pass
    assert result.tolist() == [True, True, False, False, True]


def test_conformity_allowed_values(sample_df):
    a = DQRAssignment(
        cde_column="CATEGORY",
        dimension="Conformity",
        params={"allowed_values": ["A", "B"]},
    )
    result = evaluate_rule(sample_df, a)
    # "X" and None fail
    assert result.tolist() == [True, True, True, False, False]


def test_precision_max_decimals():
    df = pd.DataFrame({"PRICE": [1.00, 1.234, 5.6789, 10.0, None]})
    a = DQRAssignment(
        cde_column="PRICE",
        dimension="Precision",
        params={"max_decimals": 2},
    )
    result = evaluate_rule(df, a)
    # 1.0 ok, 1.234 fails, 5.6789 fails, 10.0 ok, None fails
    assert result.tolist() == [True, False, False, True, False]


def test_evaluate_all_returns_dataframe(sample_df):
    assignments = [
        DQRAssignment(cde_column="PLANVIEW_ID", dimension="Completeness"),
        DQRAssignment(cde_column="PLANVIEW_ID", dimension="Uniqueness"),
    ]
    result = evaluate_all(sample_df, assignments)
    assert list(result.columns) == [
        "PLANVIEW_ID::Completeness",
        "PLANVIEW_ID::Uniqueness",
    ]
    assert len(result) == len(sample_df)


def test_suggest_assignments_for_id_column(sample_df):
    profile = profile_column(sample_df, "PLANVIEW_ID")
    suggestions = suggest_assignments_for_cde(profile)
    dims = {a.dimension for a in suggestions}
    # Always suggested
    assert "Completeness" in dims
    assert "Uniqueness" in dims
