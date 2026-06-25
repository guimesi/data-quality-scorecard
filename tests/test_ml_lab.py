"""
Tests for the experimental ML Lab module (``src.ml_lab``).

Mirrors the style of ``test_scorecard.py``: small synthetic DataFrames,
hand-built ``DataProduct`` / ``DataProductConfig`` / ``ScorecardResult``
objects, then assertions on the public outputs of each function.

The tests purposefully cover both code paths (numpy fallback and sklearn
swap-in) when sklearn is importable, and stay defensive when it isn't.
"""
from __future__ import annotations

import importlib

import pandas as pd
import pytest

from src import ml_lab
from src.models import DataProduct, DataProductConfig, DQRAssignment
from src.profiler import profile_dataframe
from src.scorecard import compute_scorecard

# =============================================================================
# Fixtures
# =============================================================================

def _make_dp_with_score():
    """Build a 12-row synthetic DataProduct + a scored config.

    The columns are intentionally heterogeneous so profiling exercises
    several column-type groups and the scorecard generates a mix of
    PASS / FAIL flags."""
    df = pd.DataFrame({
        "PLANVIEW_ID": [f"PV-{i:03d}" for i in range(12)],
        "AMOUNT":      [10, 20, 30, 40, 50, 60, 70, 80, 90, None, 110, 120],
        "LOCATION":    ["A", "B", "C", "A", "B", None, "C", "A", "B", "C", "A", "B"],
        "STATUS":      ["OK", "OK", "OK", "FAIL", "OK", "OK", "FAIL", "OK",
                         "OK", "OK", "OK", "OK"],
    })
    dp = DataProduct(
        system_code="TEST", name="TEST_DP", df=df, source_tables=["T"],
    )
    dp.profiles = profile_dataframe(df)
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["PLANVIEW_ID", "AMOUNT", "LOCATION", "STATUS"],
        assignments=[
            DQRAssignment("PLANVIEW_ID", "Completeness", weight=25),
            DQRAssignment("PLANVIEW_ID", "Uniqueness", weight=25),
            DQRAssignment("AMOUNT", "Completeness", weight=20),
            DQRAssignment("LOCATION", "Completeness", weight=15),
            DQRAssignment("STATUS", "Completeness", weight=15),
        ],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    return dp, cfg, result


# =============================================================================
# build_rule_flag_matrix
# =============================================================================

def test_build_rule_flag_matrix_shape_and_alignment():
    dp, cfg, _ = _make_dp_with_score()
    flags, meta = ml_lab.build_rule_flag_matrix(dp, cfg)
    assert flags.index.equals(dp.df.index)
    # Each assignment should map to one column when evaluation succeeded.
    assert flags.shape[1] == len(cfg.assignments)
    for a in cfg.assignments:
        assert a.rule_id in flags.columns
        assert a.rule_id in meta
        assert meta[a.rule_id]["source"] == "Standard"
        assert meta[a.rule_id]["weight"] == pytest.approx(a.weight)


def test_build_rule_flag_matrix_empty_config():
    df = pd.DataFrame({"X": [1, 2, 3]})
    dp = DataProduct(system_code="TEST", name="T", df=df, source_tables=["T"])
    cfg = DataProductConfig(system_code="TEST", cdes=[], assignments=[])
    flags, meta = ml_lab.build_rule_flag_matrix(dp, cfg)
    assert flags.empty
    assert meta == {}


# =============================================================================
# compute_row_anomalies
# =============================================================================

def test_row_anomalies_basic_structure():
    dp, cfg, result = _make_dp_with_score()
    report = ml_lab.compute_row_anomalies(dp, cfg, result, top_n=5, rarity_weight=0.7)
    assert report["n_rules_evaluated"] == len(cfg.assignments)
    assert report["n_rows_total"] == dp.row_count
    assert 0.0 <= report["rarity_weight"] <= 1.0
    table = report["table"]
    assert {"row_score", "robust_z", "rarity_score", "anomaly_score",
            "n_rules_failed", "top_rare_failures"} <= set(table.columns)
    assert len(table) <= 5
    # anomaly_score should be sorted descending.
    assert table["anomaly_score"].is_monotonic_decreasing


def test_row_anomalies_alpha_extremes_change_ordering():
    """rarity_weight must actually reorder the ranking, not be ignored.

    Build a DP where the worst-scoring rows fail a *common*, high-weight rule
    while a *different* row fails a unique low-weight rule. Then:
      - alpha=1 (rare-failure only) ranks the unique-failure row first;
      - alpha=0 (score only) never ranks it first (it has the best score among
        the failing rows).
    Asserting the *full* index order differs would be fragile - most rows tie
    on anomaly_score and pandas' sort tie-break is platform-dependent (this
    test passed locally but coincided on CI). So we pin the deterministic
    signal: which row tops the ranking at each extreme."""
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-0", "PV-1", "PV-2", "PV-3"],
        # BIG: high-weight rule fails on rows 0/2/3 (common) -> worst scores.
        "BIG":  [None, "x", None, None],
        # RARE: low-weight rule fails on row 1 only (unique) -> rarest failure.
        "RARE": ["a", None, "c", "d"],
    })
    dp = DataProduct(system_code="TEST", name="TEST_DP", df=df, source_tables=["T"])
    dp.profiles = profile_dataframe(df)
    cfg = DataProductConfig(
        system_code="TEST",
        cdes=["PLANVIEW_ID", "BIG", "RARE"],
        assignments=[
            DQRAssignment("BIG", "Completeness", weight=80),
            DQRAssignment("RARE", "Completeness", weight=20),
        ],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)

    a0 = ml_lab.compute_row_anomalies(dp, cfg, result, top_n=4, rarity_weight=0.0)
    a1 = ml_lab.compute_row_anomalies(dp, cfg, result, top_n=4, rarity_weight=1.0)
    assert not a0["table"].empty and not a1["table"].empty
    # Deterministic regardless of tie-break: row 1 is the strict rarity max and
    # the strict score-anomaly min.
    assert a1["table"].index[0] == 1          # rare-failure row tops at alpha=1
    assert a0["table"].index[0] != 1          # ...but never at alpha=0
    # And rarity_weight genuinely changes the blended scores.
    assert (
        a0["table"]["anomaly_score"].tolist()
        != a1["table"]["anomaly_score"].tolist()
    )


def test_row_anomalies_with_sklearn_optional():
    sklearn = importlib.util.find_spec("sklearn")
    if sklearn is None:  # pragma: no cover - sklearn missing
        pytest.skip("scikit-learn not installed")
    dp, cfg, result = _make_dp_with_score()
    report = ml_lab.compute_row_anomalies(dp, cfg, result, use_sklearn=True)
    # When sklearn is engaged we expect the iso_forest_score column.
    if report["sklearn_used"]:
        assert "iso_forest_score" in report["table"].columns


# =============================================================================
# compute_rule_impact
# =============================================================================

def test_rule_impact_baseline_matches_standard_score():
    dp, cfg, result = _make_dp_with_score()
    imp = ml_lab.compute_rule_impact(cfg, result)
    assert not imp.empty
    # Baseline reported per row must equal the result's standard_score
    # (every row has the same baseline column → assert any value).
    std_baseline = imp[imp["source"] == "Standard"]["baseline_source_score"].iloc[0]
    assert std_baseline == pytest.approx(round(result.standard_score, 2), abs=0.05)


def test_rule_impact_leave_one_out_renormalizes_correctly():
    """Removing a rule then renormalizing the rest must equal
    ``Σ (w_j / Σ_{k≠i} w_k) * pass_rate_j`` analytically."""
    dp, cfg, result = _make_dp_with_score()
    imp = ml_lab.compute_rule_impact(cfg, result)
    pr_map = {a.rule_id: result.rule_pass_rates[a.rule_id]
              for a in cfg.assignments if a.rule_id in result.rule_pass_rates}
    w_map = {a.rule_id: a.weight for a in cfg.assignments
             if a.rule_id in result.rule_pass_rates}
    for _, row in imp[imp["source"] == "Standard"].iterrows():
        others = {rid: pr for rid, pr in pr_map.items() if rid != row["rule_id"]}
        others_w = {rid: w_map[rid] for rid in others}
        tot = sum(others_w.values()) or 1.0
        expected = sum(others_w[r] / tot * (others[r] / 100.0) for r in others) * 100
        assert row["loo_source_score"] == pytest.approx(round(expected, 2), abs=0.05)


# =============================================================================
# compute_cde_profile_clusters
# =============================================================================

def test_cde_clusters_table_shape():
    dp, cfg, result = _make_dp_with_score()
    out = ml_lab.compute_cde_profile_clusters(dp, cfg, result, n_clusters=2)
    df = out["table"]
    assert len(df) == len(cfg.cdes)
    assert {"cluster", "pc1", "pc2"} <= set(df.columns)
    assert 1 <= out["n_clusters"] <= 2


def test_cde_clusters_with_sklearn_optional():
    if importlib.util.find_spec("sklearn") is None:  # pragma: no cover
        pytest.skip("scikit-learn not installed")
    dp, cfg, result = _make_dp_with_score()
    out = ml_lab.compute_cde_profile_clusters(
        dp, cfg, result, n_clusters=2, use_sklearn=True,
    )
    # When sklearn is engaged the explained variance ratios sum to <= 1.
    if out["sklearn_used"]:
        ev = out["explained_variance"]
        assert ev[0] + ev[1] <= 1.0 + 1e-6


# =============================================================================
# simulate_weight_perturbation
# =============================================================================

def test_weight_sensitivity_summary_around_baseline():
    dp, cfg, result = _make_dp_with_score()
    sim = ml_lab.simulate_weight_perturbation(
        cfg, result, n_simulations=200, jitter=0.2, seed=0,
    )
    assert sim["n_simulations"] == 200
    assert len(sim["scores"]) == 200
    s = sim["summary"]
    # Mean should sit roughly around the baseline; not strictly equal due
    # to non-symmetric Dirichlet samples.
    assert abs(s["mean"] - sim["baseline"]) < 25
    assert s["p05"] <= s["p95"]


def test_weight_sensitivity_no_assignments():
    df = pd.DataFrame({"X": [1, 2, 3]})
    dp = DataProduct(system_code="TEST", name="T", df=df, source_tables=["T"])
    dp.profiles = profile_dataframe(df)
    cfg = DataProductConfig(system_code="TEST", cdes=[], assignments=[])
    result = compute_scorecard(dp, cfg)
    sim = ml_lab.simulate_weight_perturbation(cfg, result)
    assert sim["baseline"] is None
    assert len(sim["scores"]) == 0


# =============================================================================
# compare_data_products
# =============================================================================

def test_compare_data_products_single():
    dp, cfg, result = _make_dp_with_score()
    df = ml_lab.compare_data_products({"TEST": result})
    assert len(df) == 1
    assert df["status"].iloc[0] == "Single DP"


def test_compare_data_products_multi_flags_outlier():
    """Stack three near-identical scorecards plus one outlier - expect the
    outlier to be flagged as Anomalous via robust-z."""
    dp, cfg, result = _make_dp_with_score()
    # Synthesise dummy ScorecardResult variants with hand-tuned scores.
    from src.models import ScorecardResult
    s = result
    variants = {
        "A": ScorecardResult(
            system_code="A", overall_score=90, row_scores=s.row_scores,
            rule_pass_rates={}, cde_scores={}, dimension_scores={},
            total_rows=100, rows_green=95, rows_yellow=5, rows_red=0,
            threshold_green=80, threshold_yellow=60,
        ),
        "B": ScorecardResult(
            system_code="B", overall_score=88, row_scores=s.row_scores,
            rule_pass_rates={}, cde_scores={}, dimension_scores={},
            total_rows=100, rows_green=94, rows_yellow=5, rows_red=1,
            threshold_green=80, threshold_yellow=60,
        ),
        "C": ScorecardResult(
            system_code="C", overall_score=91, row_scores=s.row_scores,
            rule_pass_rates={}, cde_scores={}, dimension_scores={},
            total_rows=100, rows_green=96, rows_yellow=4, rows_red=0,
            threshold_green=80, threshold_yellow=60,
        ),
        "OUT": ScorecardResult(
            system_code="OUT", overall_score=30, row_scores=s.row_scores,
            rule_pass_rates={}, cde_scores={}, dimension_scores={},
            total_rows=100, rows_green=5, rows_yellow=10, rows_red=85,
            threshold_green=80, threshold_yellow=60,
        ),
    }
    df = ml_lab.compare_data_products(variants)
    out_row = df[df["data_product"] == "OUT"].iloc[0]
    assert out_row["status"] == "Anomalous"


# =============================================================================
# Run history - snapshot, JSON / CSV round-trip
# =============================================================================

def test_snapshot_round_trip_via_json():
    dp, cfg, result = _make_dp_with_score()
    snap = ml_lab.snapshot_scorecard("TEST", dp, result, label="baseline")
    # Crucial fields are present.
    for key in (
        "id", "label", "timestamp", "source", "dp_code", "overall_score",
        "rule_pass_rates", "cde_scores", "dimension_scores", "row_score_hist",
    ):
        assert key in snap
    assert snap["source"] == "session"
    # Histogram has fixed 20 bins from 0..100.
    assert len(snap["row_score_hist"]["bin_edges"]) == 21
    assert len(snap["row_score_hist"]["counts"]) == 20


def test_load_snapshot_from_json_uses_export_schema():
    """Build a JSON payload matching Step 6's export and load it back."""
    import json
    payload = {
        "exported_at": "2026-05-16T01:00:00",
        "system_code": "EPT",
        "data_product_name": "EPT",
        "row_count": 100,
        "thresholds": {"green": 80, "yellow": 60},
        "assignments": [
            {"cde_column": "AMOUNT", "dimension": "Completeness",
             "weight_pct": 100.0, "pass_rate_pct": 92.5},
        ],
        "summary": {
            "overall_score": 92.5,
            "rows_green": 90, "rows_yellow": 8, "rows_red": 2,
            "cde_scores": {"AMOUNT": 92.5},
            "dimension_scores": {"Completeness": 92.5},
        },
    }
    snap = ml_lab.load_snapshot_from_json(json.dumps(payload).encode("utf-8"))
    assert snap["dp_code"] == "EPT"
    assert snap["overall_score"] == pytest.approx(92.5)
    assert snap["rule_pass_rates"]["AMOUNT::Completeness"] == pytest.approx(92.5)
    assert snap["row_score_hist"] is None  # JSON exports omit row scores


def test_load_snapshot_from_csv_reconstructs_histogram():
    """Build a CSV in the same shape Step 6 emits and verify the histogram
    is reconstructed plus rule_pass_rates are recovered from columns."""
    csv = (
        "_row_score,_status,STD · AMOUNT · Completeness (w=100.0%)\n"
        "100,GREEN,100\n50,RED,0\n80,GREEN,100\n100,GREEN,100\n70,YELLOW,100\n"
    )
    snap = ml_lab.load_snapshot_from_csv(csv.encode("utf-8"), dp_code="EPT")
    assert snap["dp_code"] == "EPT"
    assert snap["total_rows"] == 5
    assert snap["row_score_hist"] is not None
    assert snap["rule_pass_rates"]["AMOUNT::Completeness"] == pytest.approx(80.0)
    # 3 rows >= 80 → green; 1 row in [60, 80) → yellow; 1 row < 60 → red.
    assert snap["rows_green"] == 3
    assert snap["rows_yellow"] == 1
    assert snap["rows_red"] == 1


def test_load_snapshot_from_csv_rejects_missing_score_column():
    with pytest.raises(ValueError):
        ml_lab.load_snapshot_from_csv(b"col_a,col_b\n1,2\n", dp_code="EPT")


def test_compute_drift_psi_and_per_rule_table():
    dp, cfg, result = _make_dp_with_score()
    snap_a = ml_lab.snapshot_scorecard("TEST", dp, result, label="A")
    # Snap B with the same histogram should produce PSI ≈ 0 (within float noise).
    snap_b = ml_lab.snapshot_scorecard("TEST", dp, result, label="B")
    drift = ml_lab.compute_drift(snap_a, snap_b, rule_delta_threshold=5)
    assert drift["psi"] is not None and drift["psi"] < 1e-6
    assert drift["overall_score_delta"] == 0.0
    # All deltas == 0 → none flagged
    assert (drift["rule_table"]["delta"].fillna(0).abs() < 1e-6).all()


def test_compute_drift_flags_changes():
    """Hand-craft two snapshots so a specific rule moves by 10 pp and
    verify the flag column reflects the threshold."""
    snap_a = {
        "id": "a", "dp_code": "X", "overall_score": 90,
        "rule_pass_rates": {"R1": 95.0, "R2": 80.0},
        "custom_rule_pass_rates": {},
        "cde_scores": {}, "dimension_scores": {},
        "row_score_hist": None,
    }
    snap_b = {
        "id": "b", "dp_code": "X", "overall_score": 80,
        "rule_pass_rates": {"R1": 85.0, "R2": 78.0},  # R1 drops 10 pp
        "custom_rule_pass_rates": {},
        "cde_scores": {}, "dimension_scores": {},
        "row_score_hist": None,
    }
    drift = ml_lab.compute_drift(snap_a, snap_b, rule_delta_threshold=5)
    rule_tbl = drift["rule_table"]
    r1 = rule_tbl[rule_tbl["rule_id"] == "R1"].iloc[0]
    r2 = rule_tbl[rule_tbl["rule_id"] == "R2"].iloc[0]
    assert r1["delta"] == pytest.approx(-10.0, abs=0.01)
    assert bool(r1["flagged"]) is True
    assert bool(r2["flagged"]) is False  # |Δ| = 2 < 5
    assert drift["overall_score_delta"] == pytest.approx(-10.0)


def test_compute_drift_handles_disjoint_keys_without_abs_none_crash():
    """Regression test for the 'TypeError: bad operand type for abs():
    NoneType' bug. When two snapshots have disjoint rule_id / CDE /
    dimension keysets (e.g. the user compares ADR vs EPT snapshots), the
    delta column ends up with missing values for keys present in only
    one map. Earlier revisions used ``None`` for those entries, which
    promoted the column to object dtype and broke
    ``df.sort_values(... key=lambda s: s.abs())`` with a TypeError.

    We assert that the function returns cleanly AND that the missing
    deltas serialise as NaN (float dtype), not None / object.
    """
    snap_a = {
        "id": "a", "dp_code": "ADR", "overall_score": 90,
        "rule_pass_rates": {"R_ADR_1": 95.0, "R_ADR_2": 80.0},
        "custom_rule_pass_rates": {},
        "cde_scores": {"CDE_ADR_X": 90.0},
        "dimension_scores": {"Completeness": 90.0},
        "row_score_hist": None,
    }
    snap_b = {
        "id": "b", "dp_code": "EPT", "overall_score": 70,
        # Disjoint rule_ids - every key appears in exactly one map.
        "rule_pass_rates": {"R_EPT_1": 85.0, "R_EPT_2": 60.0},
        "custom_rule_pass_rates": {},
        "cde_scores": {"CDE_EPT_Y": 70.0},
        "dimension_scores": {"Uniqueness": 70.0},
        "row_score_hist": None,
    }
    drift = ml_lab.compute_drift(snap_a, snap_b, rule_delta_threshold=5)
    rule_tbl = drift["rule_table"]
    cde_tbl = drift["cde_table"]
    dim_tbl = drift["dimension_table"]
    # Each disjoint key appears once; delta is NaN-able but the column
    # must be numeric (float64), not object.
    for tbl in (rule_tbl, cde_tbl, dim_tbl):
        assert not tbl.empty
        assert tbl["delta"].dtype.kind == "f"
        # The flagged column is genuinely boolean (not object) - a structural
        # check the all-False assertions below don't make.
        assert tbl["flagged"].dtype == bool
    # No row should have flagged=True when one side is missing.
    assert (rule_tbl["flagged"]).sum() == 0
    assert (cde_tbl["flagged"]).sum() == 0
    assert (dim_tbl["flagged"]).sum() == 0


# =============================================================================
# train_risk_classifier
# =============================================================================

def test_risk_classifier_numpy_path_returns_coefs():
    dp, cfg, result = _make_dp_with_score()
    out = ml_lab.train_risk_classifier(dp, cfg, result, use_sklearn=False)
    assert out["n_rules"] == len(cfg.assignments)
    # Logistic regression must produce one coefficient per feature.
    assert len(out["coef_table"]) == out["n_rules"]
    # Accuracy on training data must beat the constant predictor.
    assert out["accuracy"] >= max(out["base_rate"], 1 - out["base_rate"]) - 0.05
    # Confusion matrix counts sum to row count.
    cm = out["confusion"]
    assert cm["tn"] + cm["fp"] + cm["fn"] + cm["tp"] == dp.row_count
    # Predictions exist for every row.
    assert len(out["predictions"]) == dp.row_count


def test_risk_classifier_sklearn_path_when_available():
    if importlib.util.find_spec("sklearn") is None:  # pragma: no cover
        pytest.skip("scikit-learn not installed")
    dp, cfg, result = _make_dp_with_score()
    out = ml_lab.train_risk_classifier(dp, cfg, result, use_sklearn=True)
    # When sklearn is installed AND there is class variance, the sklearn
    # path should be selected (we ensure variance via the fixture).
    if len(set((result.row_scores < result.threshold_yellow).astype(int))) > 1:
        assert out["sklearn_used"] is True


# =============================================================================
# recommend_dqrs_for_cde
# =============================================================================

def test_recommendations_heuristic_high_nulls_triggers_completeness():
    """A CDE with > 10% nulls and no Completeness rule should get a
    Completeness recommendation."""
    df = pd.DataFrame({
        "NULL_COL": [None, None, 1, 2, 3, 4, 5, 6, 7, 8],  # 20% null
        "OK_COL":   [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    })
    dp = DataProduct(system_code="T", name="T", df=df, source_tables=["t"])
    dp.profiles = profile_dataframe(df)
    cfg = DataProductConfig(
        system_code="T",
        cdes=["NULL_COL"],          # only one CDE
        assignments=[],             # no rules assigned yet
        dqr_sources=["standard"], source_weights={"standard": 100.0},
    )
    out = ml_lab.recommend_dqrs_for_cde(dp, cfg, other_scope={})
    assert not out.empty
    nc = out[out["cde"] == "NULL_COL"]
    assert "Completeness" in nc["recommendation"].tolist()


def test_recommendations_skip_already_assigned():
    """Completeness is already assigned → it should NOT appear in the
    heuristic suggestions."""
    df = pd.DataFrame({
        "NULL_COL": [None, None, 1, 2, 3, 4, 5, 6, 7, 8],
    })
    dp = DataProduct(system_code="T", name="T", df=df, source_tables=["t"])
    dp.profiles = profile_dataframe(df)
    cfg = DataProductConfig(
        system_code="T",
        cdes=["NULL_COL"],
        assignments=[DQRAssignment("NULL_COL", "Completeness", weight=100)],
        dqr_sources=["standard"], source_weights={"standard": 100.0},
    )
    out = ml_lab.recommend_dqrs_for_cde(dp, cfg, other_scope={})
    if not out.empty:
        assert "Completeness" not in out["recommendation"].tolist()


# =============================================================================
# explain_row_score
# =============================================================================

def test_explain_row_score_decomposition_sums_correctly():
    """For a single-source DP the per-CDE deficits must sum to
    ``100 − row_score`` (within float noise)."""
    dp, cfg, result = _make_dp_with_score()
    # Pick a non-perfect row.
    losses = (100 - result.row_scores).sort_values(ascending=False)
    bad_idx = losses.index[0]
    expl = ml_lab.explain_row_score(dp, cfg, result, bad_idx)
    assert expl["status"] in {"GREEN", "YELLOW", "RED"}
    if not expl["per_cde"].empty:
        total_deficit = float(expl["per_cde"]["deficit"].sum())
        assert total_deficit == pytest.approx(100 - expl["row_score"], abs=0.1)
    # Waterfall starts at 100 and ends at row_score.
    assert expl["waterfall_y"][0] == 100.0
    assert expl["waterfall_y"][-1] == pytest.approx(expl["row_score"])
    assert expl["waterfall_measure"][0] == "absolute"
    assert expl["waterfall_measure"][-1] == "total"


def test_explain_row_score_unknown_index_returns_empty():
    dp, cfg, result = _make_dp_with_score()
    expl = ml_lab.explain_row_score(dp, cfg, result, 99999)
    assert expl["row_score"] == 0.0
    assert expl["per_cde"].empty
    assert expl["per_rule"].empty


# =============================================================================
# sklearn_status - both branches
# =============================================================================

def test_sklearn_status_shape():
    s = ml_lab.sklearn_status()
    assert set(s.keys()) == {"available", "version"}
    assert isinstance(s["available"], bool)
