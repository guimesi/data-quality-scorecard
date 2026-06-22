"""Tests for scorecard computation."""
import pandas as pd
import pytest

from src.models import (
    CustomDQRAssignment,
    DataProduct,
    DataProductConfig,
    DQRAssignment,
)
from src.profiler import profile_dataframe
from src.scorecard import compute_scorecard


def test_scorecard_all_pass():
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", "PV-002", "PV-003"],
        "AMOUNT": [10, 20, 30],
    })
    dp = DataProduct(system_code="TEST", name="TEST", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["PLANVIEW_ID", "AMOUNT"],
        assignments=[
            DQRAssignment("PLANVIEW_ID", "Completeness", weight=50),
            DQRAssignment("AMOUNT", "Completeness", weight=50),
        ],
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.overall_score == 100.0
    assert result.rows_green == 3
    assert result.rows_yellow == 0
    assert result.rows_red == 0


def test_scorecard_partial_fail():
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", None, "PV-003"],
    })
    dp = DataProduct(system_code="TEST", name="TEST", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["PLANVIEW_ID"],
        assignments=[
            DQRAssignment("PLANVIEW_ID", "Completeness", weight=100),
        ],
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    # 2 of 3 rows pass completeness, row scores 100/0/100
    assert result.row_scores.tolist() == [100.0, 0.0, 100.0]
    assert round(result.overall_score, 2) == round(200 / 3, 2)
    assert result.rows_green == 2
    assert result.rows_red == 1


def test_scorecard_weights_are_normalized():
    df = pd.DataFrame({
        "A": [1, 1, 1, 1],
        "B": [None, 2, 2, 2],
    })
    dp = DataProduct(system_code="TEST", name="TEST", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["A", "B"],
        assignments=[
            DQRAssignment("A", "Completeness", weight=80),
            DQRAssignment("B", "Completeness", weight=20),
        ],
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    # Row 0: A passes (weight 0.8), B fails (weight 0.2) -> 80
    # Rows 1-3: both pass -> 100
    assert result.row_scores.tolist() == [80.0, 100.0, 100.0, 100.0]


def test_empty_assignments_returns_zero():
    df = pd.DataFrame({"X": [1, 2, 3]})
    dp = DataProduct(system_code="TEST", name="TEST", df=df, source_tables=["T"])
    cfg = DataProductConfig(system_code="TEST", cdes=[], assignments=[])
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.overall_score == 0.0
    assert result.rows_red == 3


def test_scorecard_duplicate_standard_rule_id_raises_clear_error():
    """A duplicate Standard rule_id (same cde+dimension assigned twice) fails
    with a readable ValueError, not the cryptic numpy broadcast error the
    misaligned weight array would otherwise raise (L8)."""
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-001", "PV-002", "PV-003"]})
    dp = DataProduct(system_code="TEST", name="TEST", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["PLANVIEW_ID"],
        assignments=[
            DQRAssignment("PLANVIEW_ID", "Completeness", weight=50),
            DQRAssignment("PLANVIEW_ID", "Completeness", weight=50),
        ],
    )
    with pytest.raises(ValueError, match="Duplicate Standard rule_id"):
        compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)


def test_scorecard_duplicate_custom_rule_id_raises_clear_error():
    """Same guard for the Custom source: a repeated custom rule_id fails fast
    with a clear message instead of a shape mismatch (L8)."""
    df = pd.DataFrame({"PLANVIEW_ID": ["PV-001", "PV-002"]})
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
        custom_assignments=[
            CustomDQRAssignment(rule_id="E1", weight=50),
            CustomDQRAssignment(rule_id="E1", weight=50),
        ],
    )
    with pytest.raises(ValueError, match="Duplicate Custom rule_id"):
        compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)


# =============================================================================
# Source-weighted combination (Standard + Custom)
# =============================================================================


def _ept_df_complete():
    return pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", "PV-002", "PV-003", "PV-004"],
        "CODE_OF_RESOURCE": ["LOC-A", "LOC-B", "LOC-C", "LOC-D"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV", "PROD", "DEC"],
    })


def _ept_df_one_e1_failure():
    return pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", "PV-002", None, "PV-004"],
        "CODE_OF_RESOURCE": ["LOC-A", None, "LOC-C", "LOC-D"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV", "PROD", "DEC"],
    })


def test_scorecard_backward_compat_no_dqr_sources():
    """Configs created before the source-selection feature must produce
    byte-identical scores to the prior single-source flow."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", None, "PV-003"],
    })
    dp = DataProduct(system_code="TEST", name="TEST", df=df, source_tables=["T"])
    # No dqr_sources / source_weights set, same shape as old fixtures.
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.row_scores.tolist() == [100.0, 0.0, 100.0]
    assert result.standard_score is not None
    assert result.custom_score is None
    assert result.source_weights == {"standard": 100.0}


def test_scorecard_standard_only_explicit_source():
    df = _ept_df_complete()
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.standard_score == 100.0
    assert result.custom_score is None
    assert result.overall_score == 100.0


def test_scorecard_custom_only_explicit_source():
    from src.models import CustomDQRAssignment

    df = _ept_df_one_e1_failure()
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.standard_score is None
    # 3 of 4 rows pass E1 (one row has null COR)
    assert result.custom_score == 75.0
    assert result.overall_score == 75.0
    assert result.custom_rule_pass_rates["E1"] == 75.0


def test_scorecard_custom_only_empty_assignments_yields_zero():
    """User picked Custom in Step 4 but selected zero rules in 4.2 → score 0
    (not vacuously 100)."""
    df = _ept_df_complete()
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=[],
        assignments=[],
        custom_assignments=[],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    # Empty config branch returns a stock zero-score scorecard.
    assert result.overall_score == 0.0
    assert result.custom_score is None  # empty branch short-circuits before computing


def test_scorecard_combined_70_30_matches_linear_combination():
    """Scenario 12: combined overall == w_std * standard + w_cus * custom."""
    from src.models import CustomDQRAssignment

    df = _ept_df_one_e1_failure()
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100)],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 70.0, "custom": 30.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.standard_score is not None
    assert result.custom_score is not None
    expected = 0.7 * result.standard_score + 0.3 * result.custom_score
    assert round(result.overall_score, 6) == round(expected, 6)


def test_scorecard_includes_e4_when_selected():
    """Scenario 27 / 29: E4 selected → its pass rate appears in the result
    and a failure on WBC_LEVEL_1 lowers the Custom score."""
    from src.models import CustomDQRAssignment

    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", "PV-002", "PV-003", "PV-004"],
        "WBC_LEVEL_1": ["L1_CAPEX", None, "L1_LABOR", "  "],
    })
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=[],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E4", weight=100)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    # 2 of 4 rows pass E4 → 50%
    assert result.custom_rule_pass_rates["E4"] == 50.0
    assert result.custom_score == 50.0


def test_scorecard_includes_e7_when_selected():
    """Scenario 28 / 30: E7 selected → its pass rate is reflected and
    PLANVIEW_ID linkage failures lower the Custom score."""
    from src.models import CustomDQRAssignment

    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", None, "PV-ORPHAN-X"],
    })
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=[],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E7", weight=100)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    # Only the first row (PV-00001) passes - null and orphan both fail.
    assert round(result.custom_rule_pass_rates["E7"], 2) == round(100 / 3, 2)


def test_scorecard_e7_not_evaluated_when_reference_unavailable(monkeypatch):
    """Scenario 22: when project_master is unavailable, E7 is recorded as
    not_evaluated and contributes 0 to the score (instead of silently
    passing)."""
    import src.reference_data as ref_mod
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)

    from src.models import CustomDQRAssignment

    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "PV-00002"]})
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=[],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E7", weight=100)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert "E7" in result.not_evaluated_custom_rules
    assert "E7" not in result.custom_rule_pass_rates
    assert result.custom_score == 0.0


def test_scorecard_combines_standard_and_custom_with_e4_and_e7():
    """Scenario 31: final combined score correctly applies Standard vs Custom
    source-level weights when E4 + E7 are both selected."""
    from src.models import CustomDQRAssignment

    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-00001", None, "PV-00003"],
        "WBC_LEVEL_1": ["L1_CAPEX", "L1_OPEX", None],
    })
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
        custom_assignments=[
            CustomDQRAssignment(rule_id="E4", weight=50),
            CustomDQRAssignment(rule_id="E7", weight=50),
        ],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 60.0, "custom": 40.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    expected = 0.6 * result.standard_score + 0.4 * result.custom_score
    assert round(result.overall_score, 6) == round(expected, 6)
    assert "E4" in result.custom_rule_pass_rates
    assert "E7" in result.custom_rule_pass_rates


def test_scorecard_combined_linearity_independent_of_split():
    """For the same data, swapping the 70/30 split changes overall_score by
    the linear combination - verifying the math is independent of the split."""
    from src.models import CustomDQRAssignment

    df = _ept_df_one_e1_failure()
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])

    def _run(w_std, w_cus):
        cfg = DataProductConfig(
            system_code="EPT",
            cdes=["PLANVIEW_ID"],
            assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
            custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100)],
            dqr_sources=["standard", "custom"],
            source_weights={"standard": float(w_std), "custom": float(w_cus)},
        )
        return compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)

    r1 = _run(70, 30)
    r2 = _run(30, 70)
    assert r1.standard_score == r2.standard_score
    assert r1.custom_score == r2.custom_score
    expected_1 = 0.7 * r1.standard_score + 0.3 * r1.custom_score
    expected_2 = 0.3 * r2.standard_score + 0.7 * r2.custom_score
    assert round(r1.overall_score, 6) == round(expected_1, 6)
    assert round(r2.overall_score, 6) == round(expected_2, 6)


# =============================================================================
# Step-6 graceful fallback when a Standard DQR cannot be computed
# =============================================================================

def _dp_with_profiles(df: pd.DataFrame, system_code: str = "TEST") -> DataProduct:
    """Build a DataProduct with real profiles, the safe evaluator and the
    validation layer both consult ``dp.profiles`` to decide which rules can
    run, so tests must populate them just like Step 2 does."""
    return DataProduct(
        system_code=system_code, name=system_code, df=df,
        source_tables=["T"], profiles=profile_dataframe(df),
    )


def test_step6_does_not_crash_on_datetime_vs_numeric_consistency():
    """The exact regression: a date CDE compared against a numeric column
    used to bubble up a TypeError from pandas in Step 6. The scorecard now
    skips the rule (recording a Not-computed reason) and keeps producing a
    usable result."""
    df = pd.DataFrame({
        "EVENT_DATE": pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01"]),
        "AMOUNT": [10.0, 20.0, 30.0],
    })
    dp = _dp_with_profiles(df)
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["EVENT_DATE", "AMOUNT"],
        assignments=[
            DQRAssignment("AMOUNT", "Completeness", weight=50),
            DQRAssignment(
                "EVENT_DATE", "Consistency",
                params={"compare_column": "AMOUNT", "operator": ">="},
                weight=50,
            ),
        ],
    )
    # Scoring must not raise.
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)

    # The bad rule is surfaced as Not computed with a user-friendly reason.
    assert "EVENT_DATE::Consistency" in result.not_computed_standard_rules
    reason = result.not_computed_standard_rules["EVENT_DATE::Consistency"]
    assert "date/datetime" in reason or "datetime" in reason

    # The good rule still produced a pass rate and the scorecard rendered.
    assert "AMOUNT::Completeness" in result.rule_pass_rates
    assert result.standard_score is not None


def test_step6_continues_processing_other_dqrs_when_one_is_invalid():
    """Multiple Standard DQRs where only one is invalid → the others still
    contribute to the score and ``rule_pass_rates``."""
    df = pd.DataFrame({
        "EVENT_DATE": pd.to_datetime(["2025-01-01", None, "2025-03-01"]),
        "AMOUNT": [10.0, 20.0, 30.0],
    })
    dp = _dp_with_profiles(df)
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["EVENT_DATE", "AMOUNT"],
        assignments=[
            DQRAssignment("AMOUNT", "Completeness", weight=33),
            DQRAssignment("EVENT_DATE", "Completeness", weight=33),
            DQRAssignment(
                "EVENT_DATE", "Consistency",
                params={"compare_column": "AMOUNT", "operator": "<="},
                weight=34,
            ),
        ],
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert "EVENT_DATE::Consistency" in result.not_computed_standard_rules
    assert "AMOUNT::Completeness" in result.rule_pass_rates
    assert "EVENT_DATE::Completeness" in result.rule_pass_rates
    # AMOUNT::Completeness should be 100%; EVENT_DATE has one null → ~66.7%.
    assert result.rule_pass_rates["AMOUNT::Completeness"] == 100.0
    assert round(result.rule_pass_rates["EVENT_DATE::Completeness"], 1) == 66.7


def test_partial_invalid_config_drops_rule_and_renormalizes_survivors_in_score():
    """M1 semantics, pinned at the SCORE level: a Standard rule that can't be
    computed is DROPPED from the score, not scored as 0 - the surviving rules'
    weights renormalize to sum to 1, so the score reflects only what was
    measurable.

    Same fixture as test_step6_continues_processing_other_dqrs_when_one_is_invalid
    (weights 33/33/34; EVENT_DATE::Consistency is invalid). Surviving rules:
    AMOUNT::Completeness [1,1,1] and EVENT_DATE::Completeness [1,0,1], each
    renormalized to 33/(33+33)=0.5 → row scores [100, 50, 100] → standard_score
    83.33. The "contribute 0" reading (invalid rule keeps its 34% weight and
    scores 0) would instead give 55 - this test guards against that drift."""
    df = pd.DataFrame({
        "EVENT_DATE": pd.to_datetime(["2025-01-01", None, "2025-03-01"]),
        "AMOUNT": [10.0, 20.0, 30.0],
    })
    dp = _dp_with_profiles(df)
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["EVENT_DATE", "AMOUNT"],
        assignments=[
            DQRAssignment("AMOUNT", "Completeness", weight=33),
            DQRAssignment("EVENT_DATE", "Completeness", weight=33),
            DQRAssignment(
                "EVENT_DATE", "Consistency",
                params={"compare_column": "AMOUNT", "operator": "<="},
                weight=34,
            ),
        ],
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)

    # The invalid rule is recorded as not-computed, then excluded from the score.
    assert "EVENT_DATE::Consistency" in result.not_computed_standard_rules
    # Per-row evidence of the 0.5/0.5 renormalized split (not 0.33/0.33/0.34).
    assert result.row_scores.round(2).tolist() == [100.0, 50.0, 100.0]
    # Drop-and-renormalize → 83.33, NOT the contribute-0 value of 55.
    assert result.standard_score is not None  # standard source is active
    assert round(result.standard_score, 2) == 83.33
    assert round(result.overall_score, 2) == 83.33  # standard-only config


def test_gyr_bucketing_is_inclusive_at_thresholds():
    """Bucketing edges: score >= green is green, score >= yellow (and < green)
    is yellow, score < yellow is red. Three Completeness rules weighted 60/20/20
    over four rows produce scores [100, 80, 60, 40], landing exactly on the 80
    (green edge) and 60 (yellow edge) thresholds - the existing tests only ever
    bucket far-from-edge scores."""
    df = pd.DataFrame({
        "A": ["x", "x", "x", None],
        "B": ["x", "x", None, "x"],
        "C": ["x", None, None, "x"],
    })
    dp = DataProduct("TEST", "TEST", df, ["T"], profiles=profile_dataframe(df))
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["A", "B", "C"],
        assignments=[
            DQRAssignment("A", "Completeness", weight=60),
            DQRAssignment("B", "Completeness", weight=20),
            DQRAssignment("C", "Completeness", weight=20),
        ],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.row_scores.round(2).tolist() == [100.0, 80.0, 60.0, 40.0]
    # 100 and exactly-80 are green; exactly-60 is yellow; 40 is red.
    assert (result.rows_green, result.rows_yellow, result.rows_red) == (2, 1, 1)


def test_source_weights_renormalize_when_not_summing_to_100():
    """Source weights that don't sum to 100 are renormalized over the active
    sources, not used raw. Standard scores 100, Custom scores 50; source_weights
    {standard: 30, custom: 30} renormalize to 50/50 -> overall 75 (NOT 45, which
    raw 0.3/0.3 weights would give)."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["P1", "P2"],
        "CODE_OF_RESOURCE": ["a", None],            # row 2 fails E1
        "STANDARD_ACTIVITY_BREAKDOWN": ["x", "y"],
    })
    dp = DataProduct("EPT", "EPT", df, ["T"], profiles=profile_dataframe(df))
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID", "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100)],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 30.0, "custom": 30.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.standard_score == 100.0
    assert result.custom_score == 50.0
    assert round(result.overall_score, 4) == 75.0
    assert result.row_scores.round(2).tolist() == [100.0, 50.0]


def test_source_weights_zero_total_falls_back_to_zero():
    """Defensive fallback: if both active sources carry weight 0 (a config that
    'should not happen'), weight_total <= 0 and the combined row score is 0
    rather than NaN / a crash - every row lands red."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["P1", "P2"],
        "CODE_OF_RESOURCE": ["a", "b"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["x", "y"],
    })
    dp = DataProduct("EPT", "EPT", df, ["T"], profiles=profile_dataframe(df))
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID", "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100)],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 0.0, "custom": 0.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.overall_score == 0.0
    assert result.rows_red == result.total_rows == 2


def test_step6_all_assignments_invalid_yields_zero_without_crashing():
    """Every Standard DQR is invalid → ``standard_score`` is 0, every rule
    is in ``not_computed_standard_rules``, and the dashboard still renders."""
    df = pd.DataFrame({"NAME": ["alice", "bob", None]})
    dp = _dp_with_profiles(df)
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["NAME"],
        assignments=[
            DQRAssignment("NAME", "Accuracy"),       # numeric-only
            DQRAssignment("NAME", "Timeliness"),     # date-only
            DQRAssignment("NAME", "Precision"),      # numeric-only
        ],
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert len(result.not_computed_standard_rules) == 3
    assert result.rule_pass_rates == {}
    # Standard score falls back to 0 instead of raising.
    assert result.standard_score == 0.0
    assert result.overall_score == 0.0


def test_step6_safe_evaluator_recovers_from_unexpected_runtime_error(monkeypatch):
    """If a rule body raises an unexpected exception that the static
    validator did not anticipate, the dashboard still renders, the rule
    is recorded as Not computed with the exception message."""
    import src.dqr_engine as eng_mod

    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", "PV-002", "PV-003"],
        "AMOUNT": [10.0, 20.0, 30.0],
    })
    dp = _dp_with_profiles(df)

    original_evaluate_rule = eng_mod.evaluate_rule

    def _flaky_evaluate(df, assignment):
        if assignment.dimension == "Uniqueness":
            raise RuntimeError("synthetic pandas blowup")
        return original_evaluate_rule(df, assignment)

    monkeypatch.setattr(eng_mod, "evaluate_rule", _flaky_evaluate)

    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["PLANVIEW_ID", "AMOUNT"],
        assignments=[
            DQRAssignment("PLANVIEW_ID", "Uniqueness", weight=50),
            DQRAssignment("AMOUNT", "Completeness", weight=50),
        ],
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert "PLANVIEW_ID::Uniqueness" in result.not_computed_standard_rules
    assert (
        "synthetic pandas blowup"
        in result.not_computed_standard_rules["PLANVIEW_ID::Uniqueness"]
    )
    assert "AMOUNT::Completeness" in result.rule_pass_rates


# =============================================================================
# Per-CDE / per-dimension scores blend Standard + Custom rules
# =============================================================================


def test_cde_scores_custom_only_populates_required_columns():
    """When only the Custom source is selected, the dashboard's "By CDE"
    tab must surface a meaningful score for every CDE covered by a custom
    rule (instead of zeros). Each required column of the custom rule is
    treated as a CDE the rule contributes to - E1 reads COR and SAB, so
    both CDEs should equal E1's pass rate."""
    from src.models import CustomDQRAssignment

    df = _ept_df_one_e1_failure()
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    # E1 pass rate is 75% (3 of 4 rows fully populated).
    assert result.custom_rule_pass_rates["E1"] == 75.0
    assert result.cde_scores["CODE_OF_RESOURCE"] == 75.0
    assert result.cde_scores["STANDARD_ACTIVITY_BREAKDOWN"] == 75.0


def test_dimension_scores_custom_only_uses_rule_type():
    """``dimension_scores`` rolls up Custom rules by their ``rule.type``.
    E1 is type ``Completeness`` - when only Custom is selected the
    Completeness dimension still lights up on the By-Dimension tab."""
    from src.models import CustomDQRAssignment

    df = _ept_df_one_e1_failure()
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        assignments=[],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert "Completeness" in result.dimension_scores
    assert result.dimension_scores["Completeness"] == 75.0


def test_cde_scores_blend_standard_and_custom_on_shared_cde():
    """Both sources active and tied to the same CDE → the per-CDE score
    averages the Standard rule's pass rate with the Custom rule's pass
    rate. Failure on the Standard side and on the Custom side both pull
    the CDE score down, in proportion."""
    from src.models import CustomDQRAssignment

    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", "PV-002", "PV-003", "PV-004"],
        "CODE_OF_RESOURCE": ["LOC-A", "LOC-B", "LOC-C", "LOC-D"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV", "PROD", None],
    })
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        assignments=[
            DQRAssignment("CODE_OF_RESOURCE", "Completeness", weight=100),
        ],
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100)],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 50.0, "custom": 50.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    # COR: Standard rule = 100% (no nulls) + Custom E1 = 75% → mean 87.5
    assert round(result.cde_scores["CODE_OF_RESOURCE"], 2) == 87.5
    # SAB: only Custom E1 contributes → 75
    assert round(result.cde_scores["STANDARD_ACTIVITY_BREAKDOWN"], 2) == 75.0


def test_cde_scores_skip_not_evaluated_custom_rule(monkeypatch):
    """A Custom rule recorded in ``not_evaluated_custom_rules`` must not
    contribute to the per-CDE mean - otherwise a missing reference dataset
    would silently inject a 0 into every CDE the rule depends on."""
    import src.reference_data as ref_mod
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)

    from src.models import CustomDQRAssignment

    df = pd.DataFrame({"PLANVIEW_ID": ["PV-00001", "PV-00002", None]})
    dp = DataProduct(system_code="EPT", name="EPT", df=df, source_tables=["T"])
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
        custom_assignments=[CustomDQRAssignment(rule_id="E7", weight=100)],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 50.0, "custom": 50.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert "E7" in result.not_evaluated_custom_rules
    # Standard Completeness on PLANVIEW_ID = 2/3 ≈ 66.67. E7 (not evaluated)
    # is excluded from the mean so the per-CDE score equals the Standard
    # rule's pass rate, not a 0-inflated value.
    assert round(result.cde_scores["PLANVIEW_ID"], 2) == round(200 / 3, 2)


def test_step6_valid_datetime_consistency_does_compute():
    """Twin of the regression test: a datetime CDE compared against another
    datetime column should compute normally and contribute to the score."""
    df = pd.DataFrame({
        "START_DATE": pd.to_datetime(["2025-01-01", "2025-02-01", "2025-03-01"]),
        "END_DATE": pd.to_datetime(["2025-01-31", "2025-01-15", "2025-04-01"]),
    })
    dp = _dp_with_profiles(df)
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["START_DATE"],
        assignments=[
            DQRAssignment(
                "START_DATE", "Consistency",
                params={"compare_column": "END_DATE", "operator": "<="},
                weight=100,
            ),
        ],
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    assert result.not_computed_standard_rules == {}
    assert "START_DATE::Consistency" in result.rule_pass_rates
    # 2 of 3 rows have START_DATE <= END_DATE → ~66.7%.
    assert round(result.rule_pass_rates["START_DATE::Consistency"], 1) == 66.7
