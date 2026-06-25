"""End-to-end tests for the Step 7 ML Lab UI.

The ML Lab is the most complex step in the app. Rather than re-implement each
of its nine analytics tabs in mocked-streamlit unit tests, we drive the whole
step through ``streamlit.testing.v1.AppTest`` with a pre-built EPT scorecard
in session state. Streamlit's tab widgets render every tab's content on every
run, so a single AppTest pass exercises most of the file.

A few branches that AppTest can't easily trigger - the file-upload + drift
flow, the worst/median jump buttons, the empty-state branches - are covered
with smaller targeted patches.
"""
from __future__ import annotations


class _AttrDict(dict):
    """dict that also supports attribute access (mirrors Streamlit's session state)."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(item) from e

    def __setattr__(self, key, value):
        self[key] = value

import os
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

# Force mock mode before importing settings-aware modules.
os.environ.setdefault("DATA_SOURCE", "mock")

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


@contextmanager
def _patch_step07_st(fake_st):
    """Apply a fake ``st`` to every sub-module of ``ui.step_07``.

    Required since B5 partitioned the monolithic ``ui/step_07_ml_lab.py``
    into one module per tab (``ui.step_07._row_anomalies`` and friends),
    each holding its own ``import streamlit as st``. A single patch on
    ``ui.step_07_ml_lab.st`` no longer affects the tab renderers.
    """
    targets = [
        "ui.step_07_ml_lab",
        "ui.step_07._shared",
        "ui.step_07._row_anomalies",
        "ui.step_07._rule_impact",
        "ui.step_07._cde_clusters",
        "ui.step_07._weight_sensitivity",
        "ui.step_07._cross_dp",
        "ui.step_07._run_history",
        "ui.step_07._risk_model",
        "ui.step_07._recommendations",
        "ui.step_07._row_explain",
    ]
    patches = [patch(f"{t}.st", fake_st) for t in targets]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()


# ===========================================================================
# Fixtures
# ===========================================================================

def _build_scored_state(system: str = "EPT"):
    """Build a minimal session_state for the ML Lab: data product, config,
    and a real scorecard."""
    from config.settings import SETTINGS
    from src.data_product_builder import build_data_product
    from src.models import DataProductConfig, DQRAssignment
    from src.profiler import profile_dataframe
    from src.scorecard import compute_scorecard

    dp = build_data_product(system)
    dp.profiles = profile_dataframe(dp.df)

    if system == "EPT":
        # Use 5 CDEs so the CDE Clustering tab's slider has range > 1.
        # The first ones come from the build's primary columns; we keep ones
        # that are guaranteed to exist in EPT's mock data.
        cdes = ["PLANVIEW_ID", "WBC_LEVEL_1", "COR", "SAB", "TOTAL_COST_USD"]
        # Drop any CDE that isn't actually in the data product (defensive).
        cdes = [c for c in cdes if c in dp.df.columns][:5]
        assignments = [
            DQRAssignment("PLANVIEW_ID", "Completeness", weight=30),
            DQRAssignment("PLANVIEW_ID", "Uniqueness", weight=30),
            DQRAssignment(cdes[1], "Completeness", weight=20),
            DQRAssignment(cdes[2], "Completeness", weight=20),
        ]
    else:
        # ACCE / ADR alternative path - simple completeness only.
        cdes = [c for c in dp.df.columns[:2]]
        assignments = [
            DQRAssignment(cdes[0], "Completeness", weight=100),
        ]
    cfg = DataProductConfig(
        system_code=system,
        cdes=cdes,
        assignments=assignments,
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    result = compute_scorecard(
        dp, cfg,
        threshold_green=SETTINGS.threshold_green,
        threshold_yellow=SETTINGS.threshold_yellow,
    )
    return {
        # The mode + domain gates are bypassed for these AppTest scenarios
        # by pre-populating ``app_mode`` / ``domain``: the ML Lab tests
        # target the Step 7 behaviour, not the entry pickers. ``app_mode``
        # is Step-by-step so the main Back button (prev_step) walks back to the
        # dashboard rather than the mode picker.
        "app_mode": "step_by_step",
        "domain": "cost_estimate",
        "current_step": "ml_lab",
        "selected_systems": [system],
        "data_products": {system: dp},
        "configs": {system: cfg},
        "scorecards": {system: result},
    }


def _new_lab_app(**extra_state) -> AppTest:
    """Create an AppTest already inside the ML Lab with a real scorecard."""
    state = _build_scored_state()
    state.update(extra_state)
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    return at


# ===========================================================================
# Empty / fallback paths
# ===========================================================================

def test_ml_lab_renders_empty_state_when_no_scorecards_can_be_built():
    """current_step=ml_lab + no DPs/configs → empty callout + nav."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["domain"] = "cost_estimate"
    at.session_state["current_step"] = "ml_lab"
    at.session_state["data_products"] = {}
    at.session_state["configs"] = {}
    at.session_state["scorecards"] = {}
    at.run()
    markdowns = [m.value for m in at.markdown]
    assert any("ML Lab needs at least" in m for m in markdowns)


def test_ml_lab_recomputes_scorecards_when_missing_but_dp_present():
    """Covers the ``recomputed[]`` branch of ``_ensure_scorecards``."""
    state = _build_scored_state()
    # Drop the cached scorecards so _ensure_scorecards has to rebuild them.
    state["scorecards"] = {}
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    # After render, scorecards must have been re-populated.
    assert "EPT" in at.session_state["scorecards"]


# ===========================================================================
# Full render path - covers every tab's happy branch
# ===========================================================================

def test_ml_lab_full_render_covers_every_tab():
    at = _new_lab_app()
    # No render-time exceptions.
    assert at.exception == []
    # Section header + banner are present.
    markdowns = [m.value for m in at.markdown]
    assert any("ML Lab" in m for m in markdowns)
    # The data-product picker radio is present.
    radios = [r.label for r in at.radio]
    assert any("Data Product" in r for r in radios)


def test_ml_lab_full_render_with_sklearn_toggle_engaged():
    """Flip the sklearn toggle and re-run to cover the sklearn-enabled
    branches in every algorithmic tab. If sklearn isn't installed, this
    test silently exercises the numpy fallbacks (which is still useful
    coverage of the toggle wiring)."""
    state = _build_scored_state()
    state["ml_lab_use_sklearn"] = True
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    assert at.exception == []
    # Beyond "didn't crash": confirm the lab actually rendered its structure
    # under the engaged toggle - the section header and the Data Product picker
    # (the same markers the default-toggle render test asserts). Works whether
    # or not scikit-learn is installed.
    assert any("ML Lab" in m.value for m in at.markdown)
    assert any("Data Product" in r.label for r in at.radio)


# ===========================================================================
# Run-history flow - snapshot + clear + download
# ===========================================================================

def test_ml_lab_run_history_snapshot_button_captures_runs():
    """Clicking 📸 must persist snapshot dicts into ml_lab_runs."""
    at = _new_lab_app()
    snap_btn = [b for b in at.button if "Snapshot" in b.label]
    assert snap_btn, "📸 Snapshot button is expected in the run-history tab"
    snap_btn[0].click().run()
    runs = at.session_state["ml_lab_runs"]
    assert len(runs) >= 1
    assert runs[0]["dp_code"] == "EPT"


def test_ml_lab_run_history_clear_button_resets_runs():
    """🗑 Clear must wipe ml_lab_runs and the dedupe set."""
    state = _build_scored_state()
    state["ml_lab_runs"] = [{"id": "abc", "dp_code": "EPT", "label": "old"}]
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    clear_btn = [b for b in at.button if "🗑" in b.label or "Clear" in b.label]
    assert clear_btn, "🗑 Clear button is expected when runs exist"
    clear_btn[0].click().run()
    assert at.session_state["ml_lab_runs"] == []


def test_ml_lab_drift_renders_with_two_snapshots():
    """When two snapshots exist, the drift analyzer renders its metrics
    and sub-tabs (covers the drift branch + the disjoint-DP warning)."""
    state = _build_scored_state()
    # Snapshot the current run twice (same DP) to exercise the drift path.
    from src.ml_lab import snapshot_scorecard
    dp = state["data_products"]["EPT"]
    res = state["scorecards"]["EPT"]
    state["ml_lab_runs"] = [
        snapshot_scorecard("EPT", dp, res, label="A"),
        snapshot_scorecard("EPT", dp, res, label="B"),
    ]
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    assert at.exception == []
    # Drift metric labels are rendered as st.metric widgets.
    metric_labels = [m.label for m in at.metric]
    assert any("Score Δ" in lbl for lbl in metric_labels)


def test_ml_lab_drift_disjoint_dp_warning():
    """Comparing snapshots of different DPs surfaces a warning."""
    state = _build_scored_state()
    from src.ml_lab import snapshot_scorecard
    dp = state["data_products"]["EPT"]
    res = state["scorecards"]["EPT"]
    snap_a = snapshot_scorecard("EPT", dp, res, label="A")
    snap_b = snapshot_scorecard("EPT", dp, res, label="B")
    snap_b["dp_code"] = "ACCE"  # force disjoint codes
    state["ml_lab_runs"] = [snap_a, snap_b]
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    at.run()
    warnings = [w.value for w in at.warning]
    assert any("different DPs" in w for w in warnings)


# ===========================================================================
# Nav buttons
# ===========================================================================

def test_ml_lab_back_button_returns_to_dashboard_step():
    at = _new_lab_app()
    back = [b for b in at.button if b.label.strip().startswith("⬅") or
            "Back" in b.label]
    # Multiple Back buttons may exist (per tab + main nav); click the main one.
    main_back = [b for b in back if "Dashboard" not in b.label]
    assert main_back, "⬅ Back nav button is expected"
    main_back[0].click().run()
    assert at.session_state["current_step"] == "dashboard"


def test_ml_lab_back_to_dashboard_button_navigates_to_step6():
    at = _new_lab_app()
    btn = [b for b in at.button if "Back to Dashboard" in b.label]
    assert btn, "📊 Back to Dashboard button expected"
    btn[0].click().run()
    assert at.session_state["current_step"] == "dashboard"


# ===========================================================================
# Run History upload (temporarily under maintenance) + worst/median row
# buttons (mock-driven unit-style coverage)
# ===========================================================================

def test_ml_lab_run_history_upload_is_under_maintenance():
    """Snapshot upload is temporarily disabled: the 📂 control renders but is
    surfaced as 'under maintenance' rather than an active file uploader. The
    loader functions remain unit-tested in test_ml_lab / test_coverage_gaps."""
    at = _new_lab_app()
    upload_buttons = [b for b in at.button if "Upload" in b.label]
    assert upload_buttons, "📂 Upload (under maintenance) button expected"
    assert any("maintenance" in b.label.lower() for b in upload_buttons)
    # The feature being disabled, no upload-dedupe state is created.
    assert "ml_lab_uploaded_fingerprints" not in at.session_state


def _col():
    col = MagicMock()
    col.__enter__ = lambda self: self
    col.__exit__ = lambda self, *a: False
    return col


def test_row_explain_worst_button_writes_pending_position():
    """🔴 Worst row click stages the new position via pending key."""
    import ui.step_07_ml_lab as s7

    state = _build_scored_state()
    dp = state["data_products"]["EPT"]
    cfg = state["configs"]["EPT"]
    result = state["scorecards"]["EPT"]

    class _RerunSignal(Exception):
        pass

    # First call returns True for "Worst row", everything else False.
    call_count = {"i": 0}

    def _btn(label, *a, **kw):
        if "Worst" in label and call_count["i"] == 0:
            call_count["i"] += 1
            return True
        return False

    fake_session = {}
    fake_st = MagicMock()
    fake_st.session_state = fake_session
    fake_st.columns = MagicMock(
        side_effect=lambda spec: [_col() for _ in range(
            spec if isinstance(spec, int) else len(spec))]
    )
    fake_st.button = MagicMock(side_effect=_btn)
    fake_st.number_input = MagicMock(return_value=0)
    fake_st.rerun = MagicMock(side_effect=_RerunSignal)
    fake_st.markdown = MagicMock()
    fake_st.caption = MagicMock()
    fake_st.metric = MagicMock()
    fake_st.dataframe = MagicMock()
    fake_st.plotly_chart = MagicMock()

    with _patch_step07_st(fake_st):
        with pytest.raises(_RerunSignal):
            s7._render_tab_row_explain("EPT", dp, cfg, result)

    # The pending-position key must be set for the next rerun.
    assert any(k.startswith("ml_lab_row_pos_pending_") for k in fake_session)


def test_row_explain_median_button_writes_pending_position():
    """🟡 Median row click stages the median position."""
    import ui.step_07_ml_lab as s7

    state = _build_scored_state()
    dp = state["data_products"]["EPT"]
    cfg = state["configs"]["EPT"]
    result = state["scorecards"]["EPT"]

    class _RerunSignal(Exception):
        pass

    def _btn(label, *a, **kw):
        return "Median" in label

    fake_session = {}
    fake_st = MagicMock()
    fake_st.session_state = fake_session
    fake_st.columns = MagicMock(
        side_effect=lambda spec: [_col() for _ in range(
            spec if isinstance(spec, int) else len(spec))]
    )
    fake_st.button = MagicMock(side_effect=_btn)
    fake_st.number_input = MagicMock(return_value=0)
    fake_st.rerun = MagicMock(side_effect=_RerunSignal)
    fake_st.markdown = MagicMock()
    fake_st.caption = MagicMock()
    fake_st.metric = MagicMock()
    fake_st.dataframe = MagicMock()
    fake_st.plotly_chart = MagicMock()

    with _patch_step07_st(fake_st):
        with pytest.raises(_RerunSignal):
            s7._render_tab_row_explain("EPT", dp, cfg, result)

    assert any(k.startswith("ml_lab_row_pos_pending_") for k in fake_session)


def test_row_explain_pending_position_consumed_into_pos_key():
    """When a previous click left a pending value, it gets transferred to the
    actual position key before the widget is built."""
    import ui.step_07_ml_lab as s7

    state = _build_scored_state()
    dp = state["data_products"]["EPT"]
    cfg = state["configs"]["EPT"]
    result = state["scorecards"]["EPT"]

    fake_session = {
        "ml_lab_row_pos_pending_EPT": 0,
    }
    fake_st = MagicMock()
    fake_st.session_state = fake_session
    fake_st.columns = MagicMock(
        side_effect=lambda spec: [_col() for _ in range(
            spec if isinstance(spec, int) else len(spec))]
    )
    fake_st.button = MagicMock(return_value=False)
    fake_st.number_input = MagicMock(return_value=0)
    fake_st.markdown = MagicMock()
    fake_st.caption = MagicMock()
    fake_st.metric = MagicMock()
    fake_st.dataframe = MagicMock()
    fake_st.plotly_chart = MagicMock()

    with _patch_step07_st(fake_st):
        s7._render_tab_row_explain("EPT", dp, cfg, result)

    assert "ml_lab_row_pos_pending_EPT" not in fake_session
    assert fake_session["ml_lab_row_pos_EPT"] == 0


# ===========================================================================
# Empty-state branches (each tab's "nothing to do" early return)
# ===========================================================================

def test_row_anomalies_empty_when_no_rules_evaluated():
    """Configure a CDE that doesn't exist in the DP so no rule evaluates."""
    import ui.step_07_ml_lab as s7
    from src.data_product_builder import build_data_product
    from src.models import DataProductConfig, DQRAssignment
    from src.profiler import profile_dataframe
    from src.scorecard import compute_scorecard

    dp = build_data_product("EPT")
    dp.profiles = profile_dataframe(dp.df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["NOPE"],
        assignments=[DQRAssignment("NOPE", "Completeness", weight=100)],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)

    fake_st = MagicMock()
    fake_st.session_state = {}
    fake_st.columns = MagicMock(
        side_effect=lambda spec: [_col() for _ in range(
            spec if isinstance(spec, int) else len(spec))]
    )
    fake_st.slider = MagicMock(side_effect=[50, 0.7])
    fake_st.markdown = MagicMock()
    captured: list[str] = []

    def _md(text, **kw):
        captured.append(text)

    fake_st.markdown.side_effect = _md
    fake_st.caption = MagicMock()
    fake_st.dataframe = MagicMock()
    fake_st.plotly_chart = MagicMock()
    fake_st.metric = MagicMock()

    with _patch_step07_st(fake_st):
        s7._render_tab_row_anomalies("EPT", dp, cfg, result)

    # The empty-state message contains "No rules were successfully evaluated".
    assert any("No rules were successfully evaluated" in t for t in captured)


def test_cde_clusters_empty_when_only_one_cde():
    import ui.step_07_ml_lab as s7
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

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.session_state = {}
    fake_st.columns = MagicMock(
        side_effect=lambda spec: [_col() for _ in range(
            spec if isinstance(spec, int) else len(spec))]
    )
    fake_st.slider = MagicMock(return_value=2)
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))
    fake_st.caption = MagicMock()

    with _patch_step07_st(fake_st):
        s7._render_tab_cde_clusters("EPT", dp, cfg, result)

    assert any("At least two CDEs" in t for t in captured)


def test_rule_impact_empty_when_no_assignments():
    """Empty DataFrame branch in rule impact."""
    import ui.step_07_ml_lab as s7
    from src.data_product_builder import build_data_product
    from src.models import DataProductConfig
    from src.profiler import profile_dataframe
    from src.scorecard import compute_scorecard

    dp = build_data_product("EPT")
    dp.profiles = profile_dataframe(dp.df)
    cfg = DataProductConfig(
        system_code="EPT", cdes=[], assignments=[],
        dqr_sources=["standard"], source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.session_state = {}
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))
    fake_st.caption = MagicMock()

    with _patch_step07_st(fake_st):
        s7._render_tab_rule_impact("EPT", dp, cfg, result)

    assert any("nothing to rank" in t for t in captured)


def test_weight_sensitivity_empty_when_no_standard_assignments():
    """Empty branch when there are no Standard rules to perturb."""
    import ui.step_07_ml_lab as s7
    from src.data_product_builder import build_data_product
    from src.models import CustomDQRAssignment, DataProductConfig
    from src.profiler import profile_dataframe
    from src.scorecard import compute_scorecard

    dp = build_data_product("EPT")
    dp.profiles = profile_dataframe(dp.df)
    cfg = DataProductConfig(
        system_code="EPT", cdes=["PLANVIEW_ID"], assignments=[],
        dqr_sources=["custom"], source_weights={"custom": 100.0},
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100.0)],
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.session_state = {}
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))
    fake_st.caption = MagicMock()
    fake_st.columns = MagicMock(
        side_effect=lambda spec: [_col() for _ in range(
            spec if isinstance(spec, int) else len(spec))]
    )

    with _patch_step07_st(fake_st):
        s7._render_tab_weight_sensitivity("EPT", dp, cfg, result)

    assert any("no Standard DQRs" in t for t in captured)


def test_cross_dp_empty_when_no_scorecards():
    """compare_data_products on empty input → empty callout."""
    import ui.step_07_ml_lab as s7

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))
    fake_st.caption = MagicMock()

    with _patch_step07_st(fake_st):
        s7._render_tab_cross_dp({})

    assert any("No scorecards" in t for t in captured)


def test_row_explain_empty_when_no_row_scores():
    """row_scores is empty → early return."""
    import ui.step_07_ml_lab as s7
    from src.data_product_builder import build_data_product
    from src.models import DataProductConfig
    from src.profiler import profile_dataframe
    from src.scorecard import compute_scorecard

    dp = build_data_product("EPT")
    dp.profiles = profile_dataframe(dp.df)
    cfg = DataProductConfig(
        system_code="EPT", cdes=[], assignments=[],
        dqr_sources=["standard"], source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)
    # Force the empty branch by clobbering row_scores.
    object.__setattr__(result, "row_scores", pd.Series([], dtype=float))

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.session_state = {}
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))

    with _patch_step07_st(fake_st):
        s7._render_tab_row_explain("EPT", dp, cfg, result)

    assert any("no scored rows" in t for t in captured)


def test_recommendations_empty_branch():
    """When every CDE is already covered, the recommendations tab is empty."""
    import ui.step_07_ml_lab as s7
    state = _build_scored_state()
    dp = state["data_products"]["EPT"]
    cfg = state["configs"]["EPT"]
    result = state["scorecards"]["EPT"]

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.session_state = _AttrDict(state)
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))
    fake_st.caption = MagicMock()
    fake_st.dataframe = MagicMock()
    fake_st.columns = MagicMock(
        side_effect=lambda spec: [_col() for _ in range(
            spec if isinstance(spec, int) else len(spec))]
    )
    fake_st.metric = MagicMock()

    with _patch_step07_st(fake_st), \
         patch("ui.step_07._recommendations.recommend_dqrs_for_cde",
               return_value=pd.DataFrame()):
        s7._render_tab_recommendations("EPT", dp, cfg, result)

    # _render_empty html-escapes the message body, so look for unique substring.
    assert any("No actionable recommendations" in t for t in captured)


def test_risk_model_empty_when_no_rules_evaluated():
    """train_risk_classifier returns n_rules=0 → empty branch."""
    import ui.step_07_ml_lab as s7
    state = _build_scored_state()
    dp = state["data_products"]["EPT"]
    cfg = state["configs"]["EPT"]
    result = state["scorecards"]["EPT"]

    captured: list[str] = []
    fake_st = MagicMock()
    fake_st.session_state = {}
    fake_st.markdown = MagicMock(side_effect=lambda t, **kw: captured.append(t))
    fake_st.caption = MagicMock()

    fake_report = {"n_rules": 0, "accuracy": 0.0, "base_rate": 0.0,
                   "confusion": {"tp": 0, "fp": 0, "fn": 0, "tn": 0},
                   "sklearn_used": False, "coef_table": pd.DataFrame(),
                   "predictions": pd.Series([], dtype=float)}

    with _patch_step07_st(fake_st), \
         patch("ui.step_07._risk_model.train_risk_classifier",
               return_value=fake_report):
        s7._render_tab_risk_model("EPT", dp, cfg, result)

    # _render_empty html-escapes the message, so the apostrophe becomes &#x27;.
    assert any("No rules were evaluated" in t for t in captured)
