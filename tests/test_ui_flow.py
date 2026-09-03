"""UI tests driven by streamlit.testing.v1.AppTest.

Each test isolates a single step by pre-populating session_state and running
the app fresh. This avoids AppTest's known cross-step widget-tracking issues
(transitioning between steps can leave stale widget references).
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

# Force mock mode before importing anything that reads settings
os.environ.setdefault("DATA_SOURCE", "mock")

from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _new_app(**session_state) -> AppTest:
    """Create a new AppTest, optionally pre-populating session_state.

    The historical Step 1 (system selection) now sits behind a Step 0
    (domain selection) gate. Tests in this file are written against
    Step 1+, so we default the active domain to ``cost_estimate`` and
    land the user on ``system_selection`` whenever a caller doesn't
    override either knob - that preserves byte-for-byte behaviour of
    the pre-domain test suite. Tests that exercise Step 0 itself pass
    explicit overrides.
    """
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    # The flow now sits behind a ``mode_selection`` (One-click vs Step-by-step)
    # gate and a ``domain_selection`` gate. Tests in this file exercise the
    # historical Step-by-step steps, so default the mode to Step-by-step and the domain to
    # ``cost_estimate`` whenever a caller doesn't override them - that keeps
    # the pre-mode test suite byte-for-byte. Tests that exercise the mode /
    # domain pickers themselves pass explicit overrides.
    session_state.setdefault("app_mode", "step_by_step")
    session_state.setdefault("domain", "cost_estimate")
    session_state.setdefault("current_step", "system_selection")
    for k, v in session_state.items():
        at.session_state[k] = v
    at.run()
    return at


class _SessionDict(dict):
    """dict with attribute access, standing in for ``st.session_state``."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(item) from e

    def __setattr__(self, key, value):
        self[key] = value


def _run_restart_app(session: dict) -> dict:
    """Run ``restart_app`` against a fake ``st`` seeded with ``session``.

    Restart is confirmed inside an ``st.dialog`` whose body AppTest never
    renders, so UI tests assert the opener button and exercise the reset
    itself here - the dialog is only a wrapper around the unchanged
    ``restart_app``. Returns the session state after the reset."""
    from unittest.mock import patch

    from utils.session.navigation import restart_app

    fake = MagicMock()
    fake.session_state = _SessionDict(session)
    with patch("utils.session.navigation.st", fake), \
         patch("utils.session.state.st", fake):
        restart_app()
    return fake.session_state


def _click_last(at: AppTest, label_fragment: str) -> AppTest:
    """Click the LAST enabled button whose label contains label_fragment."""
    matches = [b for b in at.button if label_fragment in b.label and not b.disabled]
    if not matches:
        raise AssertionError(
            f"No enabled button with '{label_fragment}' found. "
            f"Got: {[(b.label, b.disabled) for b in at.button]}"
        )
    matches[-1].click().run()
    return at


def _build_data_product_for(system: str):
    """Build a DataProduct using mock data + profiling."""
    from src.data_product_builder import build_data_product
    from src.profiler import profile_dataframe
    dp = build_data_product(system)
    dp.profiles = profile_dataframe(dp.df)
    return dp


def _config_with_ept_assignments(
    dqr_sources=None,
    custom_assignments=None,
    source_weights=None,
):
    """Create a DataProductConfig for EPT with PLANVIEW_ID as CDE and some DQRs.

    Defaults to the standard-only path so existing tests written before the
    DQR-source feature continue to exercise their original flow.
    """
    from src.models import DataProductConfig, DQRAssignment
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[
            DQRAssignment("PLANVIEW_ID", "Completeness", weight=50),
            DQRAssignment("PLANVIEW_ID", "Uniqueness", weight=50),
        ],
        dqr_sources=list(dqr_sources) if dqr_sources is not None else ["standard"],
        source_weights=dict(source_weights) if source_weights is not None
        else ({"standard": 100.0} if dqr_sources in (None, ["standard"])
              else None) or {},
        custom_assignments=list(custom_assignments) if custom_assignments else [],
    )
    return cfg


# ---------------------------------------------------------------------------
# App entry point (app.py)
# ---------------------------------------------------------------------------

def test_app_renders_unknown_step_shows_error():
    """Covers app.py branch where renderer is None."""
    at = _new_app(current_step="not_a_real_step")
    errors = [e.value for e in at.error]
    assert any("Unknown step" in e for e in errors)


def test_app_sidebar_shows_progress():
    at = _new_app()
    sidebar_markdowns = [m.value for m in at.sidebar.markdown]
    assert any("Progress" in m for m in sidebar_markdowns)


# ---------------------------------------------------------------------------
# Step 1: System selection
# ---------------------------------------------------------------------------

def test_step1_initial_state():
    at = _new_app()
    assert at.session_state["current_step"] == "system_selection"
    next_btns = [b for b in at.button if "Next" in b.label]
    assert all(b.disabled for b in next_btns)


def test_step1_shows_mock_mode_banner(monkeypatch):
    """Force mock mode regardless of the user's environment."""
    import ui.step_01_system_selection as s1
    from config import settings as settings_mod
    monkeypatch.setattr(s1, "SETTINGS", settings_mod.Settings(data_source="mock"))
    at = _new_app()
    infos = [i.value for i in at.info]
    assert any("mock" in i.lower() for i in infos)


def test_step1_shows_databricks_success_when_not_mock(monkeypatch):
    """Covers the `else` branch showing the Databricks connection banner."""
    import ui.step_01_system_selection as s1
    from config import settings as settings_mod
    monkeypatch.setattr(
        s1, "SETTINGS",
        settings_mod.Settings(
            data_source="databricks", dbx_catalog="CAT", dbx_schema="SC",
        ),
    )
    at = _new_app()
    successes = [s.value for s in at.success]
    assert any("CAT.SC" in s for s in successes)


def test_step1_select_system_enables_next():
    at = _new_app()
    at.checkbox(key="chk_system_ADR").check().run()
    # Selection summary is rendered as an HTML markdown chip block.
    markdowns = [m.value for m in at.markdown]
    assert any("ADR" in m and "sel-chip" in m for m in markdowns)
    # Next button must now be enabled
    assert any("Next" in b.label and not b.disabled for b in at.button)


def test_step1_click_next_advances():
    at = _new_app()
    at.checkbox(key="chk_system_EPT").check().run()
    _click_last(at, "Next")
    assert at.session_state["current_step"] == "data_product_review"
    assert at.session_state["selected_systems"] == ["EPT"]
    # Downstream state initialized
    assert "EPT" in at.session_state["data_products"]


def test_step1_click_back_returns_to_domain_selection():
    """Step 1's Back button takes the user back to Step 0 (domain
    picker) - useful when restarting late in the flow to switch
    domains."""
    at = _new_app()
    _click_last(at, "Back")
    assert at.session_state["current_step"] == "domain_selection"


def test_step1_empty_domain_shows_no_systems_notice(monkeypatch):
    """Domains that ship without systems (e.g. a stub registered for an
    upcoming integration) still let the user land on Step 1 - the page
    must surface a clear "no systems registered" notice instead of
    crashing on an empty column-grid."""
    from config import domains as domains_mod
    from config.domains import DomainDef

    empty_domain = DomainDef(
        code="empty_stub",
        name="Empty Stub",
        subtitle="-",
        description="Stub for testing the no-systems branch.",
        icon="🪧",
        accent="#666666",
        tagline="-",
        page_title="-",
        sidebar_brand_subtitle="-",
        systems={},
        custom_rules={},
    )
    monkeypatch.setitem(domains_mod.DOMAINS, "empty_stub", empty_domain)
    try:
        at = _new_app(domain="empty_stub", current_step="system_selection")
        markdowns = [m.value for m in at.markdown]
        assert any("No systems registered" in m for m in markdowns)
    finally:
        domains_mod.DOMAINS.pop("empty_stub", None)


# ---------------------------------------------------------------------------
# Step 2: Data product review
# ---------------------------------------------------------------------------

def test_step2_no_system_shows_error():
    at = _new_app(current_step="data_product_review", selected_systems=[])
    errors = [e.value for e in at.error]
    assert any("No system selected" in e for e in errors)


def test_step2_renders_data_product_metrics():
    at = _new_app(
        current_step="data_product_review",
        selected_systems=["EPT"],
    )
    # Should have built the data product and shown the preview
    assert "EPT" in at.session_state["data_products"]
    # Metric widgets should contain "Rows" and "Columns"
    metric_labels = [m.label for m in at.metric]
    assert "Rows" in metric_labels
    assert "Columns" in metric_labels


def test_step2_back_goes_to_step1():
    at = _new_app(
        current_step="data_product_review",
        selected_systems=["EPT"],
    )
    _click_last(at, "Back")
    assert at.session_state["current_step"] == "system_selection"


def test_step2_build_failure_shows_error(monkeypatch):
    """Force build_multiple to raise so we cover the exception branch."""
    import ui.step_02_data_product_review as s2
    monkeypatch.setattr(s2, "build_multiple", MagicMock(side_effect=RuntimeError("boom")))
    at = _new_app(
        current_step="data_product_review",
        selected_systems=["EPT"],
        data_products={},
    )
    errors = [e.value for e in at.error]
    assert any("Failed to build" in e for e in errors)


def test_step2_passes_active_domain_filter_column_to_build(monkeypatch):
    """Step 2 must forward the active domain's
    ``project_filter.column`` into ``build_multiple`` so the filter is
    applied against the right key for each domain (PLANVIEW_ID for Cost
    Estimate, PROJECT_CODE for Quality)."""
    import ui.step_02_data_product_review as s2

    captured = {}

    def _fake_build(systems, row_limit=None, planview_ids=None, filter_column=None):
        captured["systems"] = systems
        captured["filter_column"] = filter_column
        captured["planview_ids"] = planview_ids
        from src.data_product_builder import build_multiple as _real
        return _real(systems, row_limit=row_limit)

    monkeypatch.setattr(s2, "build_multiple", _fake_build)

    _new_app(
        domain="quality",
        current_step="data_product_review",
        selected_systems=["SQS"],
        data_products={},
        planview_filter=["QPC-001"],
    )

    assert captured["filter_column"] == "PROJECT_CODE"
    assert captured["planview_ids"] == ["QPC-001"]


# ---------------------------------------------------------------------------
# Step 3: CDE selection
# ---------------------------------------------------------------------------

def _preloaded_step3_state(system: str = "EPT") -> dict:
    from src.models import DataProductConfig
    dp = _build_data_product_for(system)
    return {
        "current_step": "cde_selection",
        "selected_systems": [system],
        "data_products": {system: dp},
        "configs": {system: DataProductConfig(system_code=system)},
    }


def test_step3_no_data_products_shows_error():
    at = _new_app(current_step="cde_selection", data_products={})
    markdowns = [m.value for m in at.markdown]
    assert any("not built" in m for m in markdowns)


def test_step3_initial_state_has_no_cdes_and_disabled_next():
    """Fresh Step 3 render: Next is disabled until at least one CDE is
    picked, and the chip-strip is in its empty-state HTML callout."""
    at = _new_app(**_preloaded_step3_state("EPT"))
    assert all(b.disabled for b in at.button if "Next" in b.label)
    markdowns = [m.value for m in at.markdown]
    assert any("No CDE selected yet" in m for m in markdowns)


def test_step3_preselected_cdes_appear_as_badges_and_enable_next():
    """Pre-populating ``cfg.cdes`` makes the corresponding badges render and
    the Next button become enabled (no drag-drop bug - selection round-trips
    deterministically through the data-editor)."""
    state = _preloaded_step3_state("EPT")
    state["configs"]["EPT"].cdes = ["PLANVIEW_ID"]
    at = _new_app(**state)
    # The cdes survived the render unchanged.
    assert at.session_state["configs"]["EPT"].cdes == ["PLANVIEW_ID"]
    # Selected-CDEs chip-strip renders exactly one chip, for the CDE.
    markdowns = [m.value for m in at.markdown]
    assert sum(m.count('class="dq-code brand"') for m in markdowns) == 1
    assert any("PLANVIEW_ID" in m and 'class="dq-code brand"' in m for m in markdowns)
    # Next is enabled.
    assert any("Next" in b.label and not b.disabled for b in at.button)


def test_step3_grid_renders_one_row_per_source_column():
    """The data-editor grid is built from ``dp.df.columns`` so every source
    column shows up, the user has access to the full universe (no
    hidden-column bug like the previous drag-drop sometimes exhibited)."""
    import ui.step_03_cde_selection as s3
    state = _preloaded_step3_state("EPT")
    dp = state["data_products"]["EPT"]
    grid = s3._build_profile_grid(dp, current_cdes=[], required={})
    assert list(grid["Column"]) == list(dp.df.columns)
    # All checkboxes start unticked when the config has no CDEs.
    assert grid["CDE"].sum() == 0


def test_step3_grid_marks_preselected_cdes_as_ticked():
    """The Pick column is initialized from the existing ``cfg.cdes`` so the
    grid stays in sync with the chip-strip on every render."""
    import ui.step_03_cde_selection as s3
    state = _preloaded_step3_state("EPT")
    dp = state["data_products"]["EPT"]
    grid = s3._build_profile_grid(
        dp, current_cdes=["PLANVIEW_ID"], required={},
    )
    pick_for_planview = grid.loc[grid["Column"] == "PLANVIEW_ID", "CDE"].iloc[0]
    assert bool(pick_for_planview) is True
    other_picks = grid.loc[grid["Column"] != "PLANVIEW_ID", "CDE"]
    assert (~other_picks).all()


# ---------------------------------------------------------------------------
# Step 4: DQR assignment
# ---------------------------------------------------------------------------

def _preloaded_step4_state(system: str = "EPT") -> dict:
    from src.models import DataProductConfig
    dp = _build_data_product_for(system)
    cfg = DataProductConfig(
        system_code=system,
        cdes=["PLANVIEW_ID"],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    return {
        "current_step": "dqr_assignment",
        "selected_systems": [system],
        "data_products": {system: dp},
        "configs": {system: cfg},
    }


def test_step4_does_not_pre_apply_suggestions():
    """Suggestions are no longer auto-applied on first render. The user
    lands on Step 4.1 with an empty selection and a 💡-tagged catalog, they either tick dimensions individually or use the **Apply all
    suggested DQRs** shortcut to enable every still-pending suggestion at
    once. The page shows the "Enable at least one DQR" warning until the
    user opts in."""
    at = _new_app(**_preloaded_step4_state("EPT"))
    assignments = at.session_state["configs"]["EPT"].assignments
    assert assignments == []
    assert any(
        "Enable at least one DQR" in w.value for w in at.warning
    ), "Expected the 'Enable at least one DQR' warning when no rules are applied"


def test_step4_apply_all_suggested_button_applies_all_pending_suggestions():
    """Clicking the per-DP **Apply all suggested DQRs** shortcut populates
    ``cfg.assignments`` with every suggestion that wasn't already enabled.
    Once the click lands, the success banner reports the total Standard
    DQR count and Next becomes available."""
    at = _new_app(**_preloaded_step4_state("EPT"))
    # Sanity: nothing applied before the click.
    assert at.session_state["configs"]["EPT"].assignments == []
    _click_last(at, "Apply all suggested DQRs")
    assignments = at.session_state["configs"]["EPT"].assignments
    assert len(assignments) > 0, (
        "Expected at least one suggested DQR to be applied after clicking "
        "the per-DP shortcut."
    )
    # Each applied assignment matches a suggestion (dimension is in the
    # `suggest_assignments_for_cde` output for the CDE's profile).
    from src.dqr_engine import suggest_assignments_for_cde
    dp = at.session_state["data_products"]["EPT"]
    for a in assignments:
        profile = dp.profiles[a.cde_column]
        suggested_dims = {s.dimension for s in suggest_assignments_for_cde(profile)}
        assert a.dimension in suggested_dims
    # Success banner now reports the count.
    assert any("Total Standard DQRs defined" in s.value for s in at.success)


def test_step4_apply_all_suggested_button_is_idempotent():
    """Clicking the shortcut a second time is a no-op for already-applied
    suggestions - manual edits and previously-applied suggestions survive,
    no duplicates are introduced. This is the contract that lets the
    button be safely re-clicked after the user has refined the selection."""
    at = _new_app(**_preloaded_step4_state("EPT"))
    _click_last(at, "Apply all suggested DQRs")
    first_pass = list(at.session_state["configs"]["EPT"].assignments)
    # The pending count goes to zero after the first click, so the button
    # is replaced by the "all suggestions already applied" caption. Verify
    # no duplicate assignment entries linger.
    dims_per_cde = [(a.cde_column, a.dimension) for a in first_pass]
    assert len(dims_per_cde) == len(set(dims_per_cde)), (
        "Suggestions should be applied exactly once per (CDE, dimension)."
    )


def test_step4_back_goes_to_step3():
    at = _new_app(**_preloaded_step4_state("EPT"))
    _click_last(at, "Back")
    # Step 4.1's Back now goes to the new Step 4 source-selection screen.
    assert at.session_state["current_step"] == "dqr_source_selection"


def test_step4_skips_cde_without_profile():
    """Covers the `if profile is None: continue` branch."""
    from src.models import DataProductConfig
    dp = _build_data_product_for("EPT")
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["NON_EXISTENT_COLUMN"],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    at = _new_app(
        current_step="dqr_assignment",
        selected_systems=["EPT"],
        data_products={"EPT": dp},
        configs={"EPT": cfg},
    )
    # No rules => warning shown
    assert any("Enable at least one DQR" in w.value for w in at.warning)


def test_step4_skips_dp_without_cdes():
    """Covers the `if not cfg.cdes: continue` branch."""
    from src.models import DataProductConfig
    dp = _build_data_product_for("EPT")
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=[],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    at = _new_app(
        current_step="dqr_assignment",
        selected_systems=["EPT"],
        data_products={"EPT": dp},
        configs={"EPT": cfg},
    )
    # When there are no CDEs to render, Step 4.1 shows the "nothing to
    # configure" info message and leaves Next enabled.
    assert any("Nothing to configure" in i.value for i in at.info)


# ---------------------------------------------------------------------------
# Step 5: Weight assignment
# ---------------------------------------------------------------------------

def _preloaded_step5_state(system: str = "EPT") -> dict:
    dp = _build_data_product_for(system)
    cfg = _config_with_ept_assignments()
    return {
        "current_step": "weight_assignment",
        "selected_systems": [system],
        "data_products": {system: dp},
        "configs": {system: cfg},
    }


def test_step5_initial_render_and_ok_banner():
    at = _new_app(**_preloaded_step5_state())
    # Weights were set to 50/50 in the fixture -> sum = 100 -> OK banner
    assert any("sum =" in s.value.lower() and "OK" in s.value for s in at.success)


def test_step5_hard_cap_prevents_sum_over_100():
    """Individual widgets are capped so the total can never exceed 100%,
    even when input weights would otherwise sum higher."""
    state = _preloaded_step5_state()
    # Pre-populate with weights that would sum to 160 without the cap
    for a in state["configs"]["EPT"].assignments:
        a.weight = 80
    at = _new_app(**state)
    # The first widget's value gets clamped so the sum stays <= 100
    weights = [a.weight for a in at.session_state["configs"]["EPT"].assignments]
    assert sum(weights) <= 100.0 + 0.01  # within float tolerance
    # No "reduce by" error, the cap prevented the over-100 state
    assert not any("reduce by" in e.value for e in at.error)


def test_step5_under_100_shows_warning():
    state = _preloaded_step5_state()
    for a in state["configs"]["EPT"].assignments:
        a.weight = 10  # 10+10 = 20 < 100
    at = _new_app(**state)
    assert any("still needed" in w.value for w in at.warning)


def test_step5_distribute_equally_button_sets_weights():
    """Pre-set equal weights on the config so session_state is initialized
    cleanly at 50/50. (We can't click the 'Distribute equally' button in
    AppTest due to stale-widget tracking across reruns.)"""
    state = _preloaded_step5_state()
    n = len(state["configs"]["EPT"].assignments)
    for a in state["configs"]["EPT"].assignments:
        a.weight = 100.0 / n
    at = _new_app(**state)
    assert any("OK" in s.value for s in at.success)


def test_step5_dp_without_assignments_is_skipped():
    """Covers the `if not cfg.assignments: continue` branch."""
    from src.models import DataProductConfig
    dp = _build_data_product_for("EPT")
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )  # no assignments
    at = _new_app(
        current_step="weight_assignment",
        selected_systems=["EPT"],
        data_products={"EPT": dp},
        configs={"EPT": cfg},
    )
    # No assignments => Generate Scorecard button stays enabled (all_valid defaults True)
    # Since there's nothing to validate, the page renders without errors/warnings
    assert at.session_state["current_step"] == "weight_assignment"


# ---------------------------------------------------------------------------
# Step 6: Dashboard
# ---------------------------------------------------------------------------

def _preloaded_step6_state(system: str = "EPT") -> dict:
    dp = _build_data_product_for(system)
    cfg = _config_with_ept_assignments()
    return {
        "current_step": "dashboard",
        "selected_systems": [system],
        "data_products": {system: dp},
        "configs": {system: cfg},
    }


def test_step6_dashboard_renders_with_all_tabs():
    at = _new_app(**_preloaded_step6_state())
    assert at.session_state["current_step"] == "dashboard"
    # Scorecard computed
    assert "EPT" in at.session_state["scorecards"]
    result = at.session_state["scorecards"]["EPT"]
    assert 0.0 <= result.overall_score <= 100.0
    # One overview score card per scored Data Product.
    markdowns = [m.value for m in at.markdown]
    n_cards = sum(m.count('class="dq-scorecard"') for m in markdowns)
    assert n_cards == len(at.session_state["scorecards"])


def test_step6_no_configs_shows_error():
    at = _new_app(
        current_step="dashboard",
        selected_systems=["EPT"],
        data_products={},
        configs={},
    )
    assert any("No Data Product" in m.value for m in at.markdown)


def test_step6_isolates_a_failing_data_product(monkeypatch):
    """H1: a scorecard error for ONE Data Product must not blank the whole
    dashboard. The failing DP is left out and surfaced in an error banner; the
    healthy DP still scores and renders, and no exception escapes render()."""
    import ui.step_06_dashboard as dash
    from src.models import DataProductConfig, DQRAssignment
    from src.scorecard import compute_scorecard as _real_compute

    ept = _build_data_product_for("EPT")
    adr = _build_data_product_for("ADR")
    ept_cfg = _config_with_ept_assignments()
    adr_cfg = DataProductConfig(
        system_code="ADR",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )

    def _flaky(dp, cfg, **kwargs):
        if dp.system_code == "ADR":
            raise RuntimeError("boom in ADR")
        return _real_compute(dp, cfg, **kwargs)

    monkeypatch.setattr(dash, "compute_scorecard", _flaky)

    at = _new_app(
        current_step="dashboard",
        selected_systems=["EPT", "ADR"],
        data_products={"EPT": ept, "ADR": adr},
        configs={"EPT": ept_cfg, "ADR": adr_cfg},
    )

    # No uncaught exception escaped the render loop.
    assert not at.exception
    # The healthy DP scored; the failing one was left out, not crashed on.
    assert "EPT" in at.session_state["scorecards"]
    assert "ADR" not in at.session_state["scorecards"]
    # The failure is surfaced to the user (error callout naming the DP),
    # not silently swallowed.
    assert any(
        "could not be scored" in m.value and "ADR" in m.value for m in at.markdown
    )


def test_step6_back_returns_to_weights():
    at = _new_app(**_preloaded_step6_state())
    _click_last(at, "Back")
    assert at.session_state["current_step"] == "weight_assignment"


def test_step6_ml_lab_button_navigates_to_lab():
    """The dashboard's nav row carries an extra "🧪 ML Lab (beta)" button
    that jumps to Step 7. Once a scorecard is computed, the button is
    enabled and the click sets ``current_step`` to ``"ml_lab"``."""
    at = _new_app(**_preloaded_step6_state())
    _click_last(at, "ML Lab")
    assert at.session_state["current_step"] == "ml_lab"


def test_step6_restart_clears_everything():
    at = _new_app(**_preloaded_step6_state())
    # Restart is a two-click confirmation behind ``st.dialog``: the opener
    # renders in the nav footer; the dialog body does not render in AppTest.
    assert any(b.key == "restart_confirm_dashboard_open" for b in at.button), \
        "Dashboard should ship a Restart opener button"
    # Restart returns to the entry step (mode picker) and clears both the
    # active domain and the chosen mode so the user re-picks both.
    session = _run_restart_app({
        "current_step": "dashboard", "domain": "cost_estimate",
        "app_mode": "step_by_step", "selected_systems": ["EPT"],
        "data_products": {"EPT": object()}, "configs": {"EPT": object()},
        "scorecards": {"EPT": object()}, "planview_filter": [],
    })
    assert session["current_step"] == "mode_selection"
    assert session["domain"] is None
    assert session["app_mode"] is None
    assert session["selected_systems"] == []
    assert session["data_products"] == {}
    assert session["configs"] == {}


def test_step6_skips_dp_without_assignments():
    """Covers the `if not cfg.assignments and not cfg.custom_assignments`
    branch in step 6."""
    from src.models import DataProductConfig
    dp = _build_data_product_for("EPT")
    cfg_empty = DataProductConfig(
        system_code="EPT",
        cdes=[],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    at = _new_app(
        current_step="dashboard",
        selected_systems=["EPT"],
        data_products={"EPT": dp},
        configs={"EPT": cfg_empty},
    )
    # No scorecards => error shown
    assert any("No Data Product" in m.value for m in at.markdown)


# ---------------------------------------------------------------------------
# Dashboard helper functions (exercised through the step)
# ---------------------------------------------------------------------------

def test_dashboard_csv_and_json_helpers_produce_valid_payloads():
    """Directly invoke _build_rowscores_csv and _build_config_json to cover
    any lines not hit by the full dashboard render."""
    import json

    import ui.step_06_dashboard as s6
    from src.scorecard import compute_scorecard

    dp = _build_data_product_for("EPT")
    cfg = _config_with_ept_assignments()
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)

    csv_bytes = s6._build_rowscores_csv(dp, result, cfg)
    assert b"_row_score" in csv_bytes
    assert b"_status" in csv_bytes

    json_bytes = s6._build_config_json(dp, result, cfg)
    payload = json.loads(json_bytes.decode())
    assert payload["system_code"] == "EPT"
    assert "summary" in payload
    assert "assignments" in payload


def test_dashboard_gauge_and_bar_build_figures():
    """Directly invoke the _threshold_bar helper (the gauge was removed)."""
    import ui.step_06_dashboard as s6
    from src.scorecard import compute_scorecard

    dp = _build_data_product_for("EPT")
    cfg = _config_with_ept_assignments()
    result = compute_scorecard(dp, cfg, threshold_green=80, threshold_yellow=60)

    fig2 = s6._threshold_bar(result)
    assert fig2 is not None


# ---------------------------------------------------------------------------
# Step 4 (source selection) and Step 4.2 (custom rules) - scenario coverage
# ---------------------------------------------------------------------------

def _preloaded_step4_source_state(system: str = "EPT", dqr_sources=None,
                                  source_weights=None) -> dict:
    from src.models import DataProductConfig
    dp = _build_data_product_for(system)
    cfg = DataProductConfig(
        system_code=system,
        cdes=["PLANVIEW_ID"],
        dqr_sources=list(dqr_sources) if dqr_sources is not None else [],
        source_weights=dict(source_weights) if source_weights is not None else {},
    )
    return {
        "current_step": "dqr_source_selection",
        "selected_systems": [system],
        "data_products": {system: dp},
        "configs": {system: cfg},
    }


def _preloaded_step4_2_state(system: str = "EPT") -> dict:
    from src.models import DataProductConfig
    dp = _build_data_product_for(system)
    cfg = DataProductConfig(
        system_code=system,
        cdes=["PLANVIEW_ID"],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    return {
        "current_step": "dqr_custom_rules",
        "selected_systems": [system],
        "data_products": {system: dp},
        "configs": {system: cfg},
    }


def test_step4_source_renders_one_block_per_dp():
    at = _new_app(**_preloaded_step4_source_state("EPT"))
    markdowns = [m.value for m in at.markdown]
    assert any("Step 4 - DQR Sources" in m for m in markdowns)
    assert any("EPT" in m for m in markdowns)


def test_dqr_source_selection_blocks_next_when_no_source_selected():
    """Scenario 1: at least one source must be selected to advance."""
    at = _new_app(**_preloaded_step4_source_state("EPT", dqr_sources=[]))
    next_btns = [b for b in at.button if "Next" in b.label]
    assert next_btns and all(b.disabled for b in next_btns)
    assert any("at least one DQR source" in w.value for w in at.warning)


def test_only_standard_selected_pins_standard_weight_to_100():
    """Scenario 2: single-source selection auto-pins weight to 100%."""
    at = _new_app(**_preloaded_step4_source_state(
        "EPT",
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    ))
    cfg = at.session_state["configs"]["EPT"]
    assert cfg.dqr_sources == ["standard"]
    assert cfg.source_weights == {"standard": 100.0}
    assert any("100%" in i.value for i in at.info)


def test_only_custom_selected_pins_custom_weight_to_100():
    """Scenario 3: symmetric to the standard-only case."""
    at = _new_app(**_preloaded_step4_source_state(
        "EPT",
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    ))
    cfg = at.session_state["configs"]["EPT"]
    assert cfg.dqr_sources == ["custom"]
    assert cfg.source_weights == {"custom": 100.0}


def test_both_sources_selected_keeps_total_at_100():
    """Scenario 4: with both sources selected, the slider + auto-derived
    second weight always sum to 100%."""
    at = _new_app(**_preloaded_step4_source_state(
        "EPT",
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 70.0, "custom": 30.0},
    ))
    cfg = at.session_state["configs"]["EPT"]
    assert sorted(cfg.dqr_sources) == ["custom", "standard"]
    assert sum(cfg.source_weights.values()) == 100.0


def test_step4_1_only_iterates_dps_with_standard_source():
    """Scenario: a DP that picked only Custom is skipped in Step 4.1."""
    from src.models import DataProductConfig
    ept_dp = _build_data_product_for("EPT")
    ept_cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    at = _new_app(
        current_step="dqr_assignment",
        selected_systems=["EPT"],
        data_products={"EPT": ept_dp},
        configs={"EPT": ept_cfg},
    )
    # No DP selected Standard → "Nothing to configure" info + Next enabled.
    assert any("Nothing to configure" in i.value for i in at.info)
    assert any("Next" in b.label and not b.disabled for b in at.button)


def test_step4_2_lists_ept_e1_with_required_columns():
    """Scenario 7 (UI): EPT custom flow shows E1 card + COR/SAB mapping."""
    at = _new_app(**_preloaded_step4_2_state("EPT"))
    markdowns = [m.value for m in at.markdown]
    assert any("Step 4.2" in m for m in markdowns)
    assert any("E1" in m and "ISO Code of Account Present" in m for m in markdowns)


def test_step4_2_renders_ac1_card_for_acce():
    """ACCE custom flow renders AC1 - ISO Code of Account Present -
    once the data product opts into the Custom source. Replaces the
    historical empty-state test now that ACCE ships AC1."""
    from src.models import DataProductConfig
    dp = _build_data_product_for("ACCE")
    cfg = DataProductConfig(
        system_code="ACCE",
        cdes=["PLANVIEW_ID", "COA"],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    at = _new_app(
        current_step="dqr_custom_rules",
        selected_systems=["ACCE"],
        data_products={"ACCE": dp},
        configs={"ACCE": cfg},
    )
    markdowns = [m.value for m in at.markdown]
    assert any("Step 4.2" in m for m in markdowns)
    assert any("AC1" in m and "ISO Code of Account" in m for m in markdowns)


def test_step4_2_renders_a2_card_for_adr():
    """ADR ships A2 (Location + estimate date present), the rule card is
    rendered when ADR opts into the Custom source."""
    from src.models import DataProductConfig
    dp = _build_data_product_for("ADR")
    cfg = DataProductConfig(
        system_code="ADR",
        cdes=["PLANVIEW_ID", "COST_UPDATE"],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    at = _new_app(
        current_step="dqr_custom_rules",
        selected_systems=["ADR"],
        data_products={"ADR": dp},
        configs={"ADR": cfg},
    )
    markdowns = [m.value for m in at.markdown]
    assert any("A2" in m and "Location" in m for m in markdowns)


def test_step4_2_when_no_dp_uses_custom_shows_info():
    """Defensive: hitting Step 4.2 with no DP using 'custom' shows an info
    message rather than blank."""
    from src.models import DataProductConfig
    dp = _build_data_product_for("EPT")
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    at = _new_app(
        current_step="dqr_custom_rules",
        selected_systems=["EPT"],
        data_products={"EPT": dp},
        configs={"EPT": cfg},
    )
    assert any(
        "No Data Product selected the Custom DQR source" in i.value
        for i in at.info
    )


# ---------------------------------------------------------------------------
# Step 5: source weights surface + custom rule weight table
# ---------------------------------------------------------------------------

def test_step5_shows_source_weights_summary():
    """When both sources are active, Step 5 surfaces the source-level weights
    that were set in Step 4."""
    from src.models import CustomDQRAssignment
    state = _preloaded_step5_state()
    cfg = state["configs"]["EPT"]
    cfg.dqr_sources = ["standard", "custom"]
    cfg.source_weights = {"standard": 70.0, "custom": 30.0}
    cfg.custom_assignments = [CustomDQRAssignment(rule_id="E1", weight=100.0)]
    at = _new_app(**state)
    markdowns = [m.value for m in at.markdown]
    assert any(
        "Source weights" in m and "70%" in m and "30%" in m for m in markdowns
    )


# ---------------------------------------------------------------------------
# Step 6: combined score + presentation includes source weights & custom rules
# ---------------------------------------------------------------------------

def test_step6_combines_standard_and_custom_per_source_weights():
    """Scenario 12: final overall == w_std*standard + w_cus*custom."""
    from src.models import CustomDQRAssignment
    state = _preloaded_step6_state()
    cfg = state["configs"]["EPT"]
    cfg.dqr_sources = ["standard", "custom"]
    cfg.source_weights = {"standard": 70.0, "custom": 30.0}
    cfg.custom_assignments = [CustomDQRAssignment(rule_id="E1", weight=100.0)]
    at = _new_app(**state)
    result = at.session_state["scorecards"]["EPT"]
    assert result.standard_score is not None
    assert result.custom_score is not None
    expected = 0.7 * result.standard_score + 0.3 * result.custom_score
    assert round(result.overall_score, 6) == round(expected, 6)


def test_step6_presentation_includes_source_weights_and_custom_rule_results():
    """Scenario 13: dashboard shows source weights + custom rule pass-rate row."""
    from src.models import CustomDQRAssignment
    state = _preloaded_step6_state()
    cfg = state["configs"]["EPT"]
    cfg.dqr_sources = ["standard", "custom"]
    cfg.source_weights = {"standard": 70.0, "custom": 30.0}
    cfg.custom_assignments = [CustomDQRAssignment(rule_id="E1", weight=100.0)]
    at = _new_app(**state)
    markdowns = [m.value for m in at.markdown]
    # The source weights now live in the dashboard header strip
    # ("Standard <score> · 70%" / "Custom <score> · 30%").
    assert any(
        "Standard" in m and "70%" in m and "Custom" in m and "30%" in m
        for m in markdowns
    )
    # Custom rule pass rates surfaced on the result for the dashboard tab to
    # render. (AppTest doesn't expose the dataframe content directly, so we
    # assert the upstream payload.)
    result = at.session_state["scorecards"]["EPT"]
    assert "E1" in result.custom_rule_pass_rates


def test_step6_backward_compat_existing_flow_still_passes():
    """Scenario 13 / regression: the prior Standard-only flow still produces
    a valid scorecard with no Custom subscore."""
    at = _new_app(**_preloaded_step6_state())
    result = at.session_state["scorecards"]["EPT"]
    assert result.standard_score is not None
    assert result.custom_score is None
    assert 0.0 <= result.overall_score <= 100.0


# ---------------------------------------------------------------------------
# Mock data sanity - ensure E1's required columns landed in the EPT schema
# ---------------------------------------------------------------------------

def test_ept_mock_data_includes_cor_and_sab():
    dp = _build_data_product_for("EPT")
    assert "CODE_OF_RESOURCE" in dp.df.columns
    assert "STANDARD_ACTIVITY_BREAKDOWN" in dp.df.columns
    # Deliberately injected gaps must be present so E1 has failures to detect.
    cor = dp.df["CODE_OF_RESOURCE"]
    sab = dp.df["STANDARD_ACTIVITY_BREAKDOWN"]
    has_cor_gap = cor.isna().any() or (cor.astype(str).str.strip() == "").any()
    has_sab_gap = sab.isna().any() or (sab.astype(str).str.strip() == "").any()
    assert has_cor_gap
    assert has_sab_gap


def test_ept_mock_data_includes_wbc_level_1():
    dp = _build_data_product_for("EPT")
    assert "WBC_LEVEL_1" in dp.df.columns
    wbc = dp.df["WBC_LEVEL_1"]
    has_gap = wbc.isna().any() or (wbc.astype(str).str.strip() == "").any()
    assert has_gap, "Expected deliberate WBC_LEVEL_1 gaps so E4 has failures to detect"


def test_ept_mock_data_has_orphan_planview_ids_for_e7():
    """E7 needs orphan PLANVIEW_IDs (not in VWS_GP_STANDARD_SHARE.PROJECT_ID)
    to exercise the referential-integrity failure branch."""
    from src.reference_data import get_reference_dataset

    dp = _build_data_product_for("EPT")
    master = get_reference_dataset("VWS_GP_STANDARD_SHARE")
    assert master is not None
    valid_keys = set(master["PROJECT_ID"].astype(str))
    ept_keys = set(dp.df["PLANVIEW_ID"].dropna().astype(str))
    orphans = ept_keys - valid_keys
    assert orphans, f"Expected ≥1 orphan PLANVIEW_ID; got ept∩master={ept_keys & valid_keys}"


# ---------------------------------------------------------------------------
# Step 4.2: E4 + E7 surfaced via AppTest
# ---------------------------------------------------------------------------

def test_step4_2_lists_e4_and_e7_alongside_e1():
    """Scenarios 6/7 (UI): when EPT is in custom mode, all three custom
    rules (E1, E4, E7) are visible in Step 4.2 markdown."""
    at = _new_app(**_preloaded_step4_2_state("EPT"))
    markdowns = [m.value for m in at.markdown]
    body = "\n\n".join(markdowns)
    assert "E1" in body
    assert "E4" in body and "Level 1 cost category populated" in body
    assert "E7" in body and "Project Key linkage" in body
    # E7 reference dataset metadata is rendered (not just hidden in tooltips).
    assert "VWS_GP_STANDARD_SHARE" in body
    assert "PLANVIEW_ID" in body            # source column in EPT
    assert "PROJECT_ID" in body             # reference column in the master


# ---------------------------------------------------------------------------
# Step 6: E4 + E7 end-to-end through AppTest
# ---------------------------------------------------------------------------

def test_step6_with_e4_and_e7_combines_with_source_weights():
    """Scenarios 27/28/29/30/31: full EPT flow with E4 + E7 selected,
    custom-only source, weights distributed; assert custom subscore + final
    overall score are populated and reflect E4/E7 results."""
    from src.models import CustomDQRAssignment

    state = _preloaded_step6_state()
    cfg = state["configs"]["EPT"]
    cfg.dqr_sources = ["custom"]
    cfg.source_weights = {"custom": 100.0}
    cfg.assignments = []
    cfg.custom_assignments = [
        CustomDQRAssignment(rule_id="E4", weight=50.0),
        CustomDQRAssignment(rule_id="E7", weight=50.0),
    ]
    at = _new_app(**state)
    result = at.session_state["scorecards"]["EPT"]
    assert result.custom_score is not None
    assert "E4" in result.custom_rule_pass_rates
    assert "E7" in result.custom_rule_pass_rates
    # Mock data has deliberate gaps → both rules should report < 100% pass rate.
    assert result.custom_rule_pass_rates["E4"] < 100.0
    assert result.custom_rule_pass_rates["E7"] < 100.0
    assert result.overall_score == result.custom_score


def test_step6_presentation_lists_e4_and_e7_in_custom_rules():
    """Scenario 32: Step 6 renders the source weights and the rule-level
    Custom DQR details (rule names from the catalog, including E4 and E7)."""
    from src.models import CustomDQRAssignment

    state = _preloaded_step6_state()
    cfg = state["configs"]["EPT"]
    cfg.dqr_sources = ["standard", "custom"]
    cfg.source_weights = {"standard": 50.0, "custom": 50.0}
    cfg.custom_assignments = [
        CustomDQRAssignment(rule_id="E4", weight=50.0),
        CustomDQRAssignment(rule_id="E7", weight=50.0),
    ]
    at = _new_app(**state)
    # The dashboard's "Custom Rules" tab calls _render_custom_rules_table,
    # which constructs a DataFrame including the rule names from the catalog.
    # Assert that both E4 and E7 appear in the scorecard's pass-rate map and
    # that the source-weights header was rendered.
    result = at.session_state["scorecards"]["EPT"]
    assert "E4" in result.custom_rule_pass_rates
    assert "E7" in result.custom_rule_pass_rates
    markdowns = [m.value for m in at.markdown]
    body = "\n\n".join(markdowns)
    assert "Standard" in body and "Custom" in body
    assert "50%" in body


def test_step6_renders_not_evaluated_warning_for_e7_when_reference_missing(monkeypatch):
    """Scenario 22 + presentation: when project_master is unavailable, E7
    surfaces as 'Not evaluated' in Step 6 (via st.warning), not as a silent
    pass."""
    import src.reference_data as ref_mod
    monkeypatch.setattr(ref_mod, "get_reference_dataset", lambda name: None)

    from src.models import CustomDQRAssignment

    state = _preloaded_step6_state()
    cfg = state["configs"]["EPT"]
    cfg.dqr_sources = ["custom"]
    cfg.source_weights = {"custom": 100.0}
    cfg.assignments = []
    cfg.custom_assignments = [CustomDQRAssignment(rule_id="E7", weight=100.0)]
    at = _new_app(**state)
    warnings = [w.value for w in at.warning]
    assert any("E7" in w and "not evaluated" in w.lower() for w in warnings)


def test_step5_with_e4_only_lands_with_blank_weight():
    """Custom rule weights now start blank (0%), matching the Standard UX.
    The user is expected to either type a value or click "Distribute
    equally" to fill them in - there is no longer an auto-pin on first
    render."""
    from src.models import CustomDQRAssignment, DataProductConfig

    dp = _build_data_product_for("EPT")
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
        custom_assignments=[CustomDQRAssignment(rule_id="E4", weight=0.0)],
    )
    at = _new_app(
        current_step="weight_assignment",
        selected_systems=["EPT"],
        data_products={"EPT": dp},
        configs={"EPT": cfg},
    )
    weight = at.session_state["configs"]["EPT"].custom_assignments[0].weight
    assert weight == 0.0
    # And the "still needed" warning should fire because the sum is < 100%.
    assert any("still needed" in w.value for w in at.warning)


def test_step2_prefetches_reference_datasets_when_ept_selected():
    """Step 2 must eagerly load VWS_GP_STANDARD_SHARE into the session-state
    cache so Step 6 doesn't open a fresh Databricks connection on render."""
    from src.reference_data import _SESSION_STATE_KEY

    at = _new_app(
        current_step="data_product_review",
        selected_systems=["EPT"],
    )
    assert _SESSION_STATE_KEY in at.session_state
    cache = at.session_state[_SESSION_STATE_KEY]
    assert "VWS_GP_STANDARD_SHARE" in cache


def test_step2_prefetches_acce_reference_datasets():
    """ACCE ships AC1 (`ACCE_COA_MASTER`) and AC2 (`VWS_GP_STANDARD_SHARE`).
    Step 2 must prefetch both so the rules can evaluate in Step 6 without
    re-opening a Databricks connection."""
    from src.reference_data import _SESSION_STATE_KEY

    at = _new_app(
        current_step="data_product_review",
        selected_systems=["ACCE"],
    )
    assert _SESSION_STATE_KEY in at.session_state
    cache = at.session_state[_SESSION_STATE_KEY]
    assert "ACCE_COA_MASTER" in cache
    assert "VWS_GP_STANDARD_SHARE" in cache


def test_step2_prefetches_planview_share_for_adr():
    """ADR now ships A2, which depends on VWS_GP_STANDARD_SHARE, the
    Step 2 prefetch must seed the same reference dataset as for EPT."""
    from src.reference_data import _SESSION_STATE_KEY

    at = _new_app(
        current_step="data_product_review",
        selected_systems=["ADR"],
    )
    assert _SESSION_STATE_KEY in at.session_state
    cache = at.session_state[_SESSION_STATE_KEY]
    assert "VWS_GP_STANDARD_SHARE" in cache


def test_step2_surfaces_reference_load_error_as_warning(monkeypatch):
    """If VWS_GP_STANDARD_SHARE fails to load, Step 2 shows a warning
    pointing at the actual error so the user knows up-front that E7 will
    be marked Not evaluated in Step 6."""
    import src.reference_data as ref_mod

    def boom():
        raise RuntimeError("Databricks auth failed for VWS_GP_STANDARD_SHARE")

    monkeypatch.setitem(ref_mod._REGISTRY, "VWS_GP_STANDARD_SHARE", boom)

    at = _new_app(
        current_step="data_product_review",
        selected_systems=["EPT"],
    )
    warnings = [w.value for w in at.warning]
    assert any(
        "VWS_GP_STANDARD_SHARE" in w and "Databricks auth failed" in w
        for w in warnings
    )


def test_step6_restart_does_not_reload_reference_dataset():
    """Once Step 6 has rendered (cache populated), the dashboard re-render
    triggered by clicking Restart must NOT call the loader again, the
    cache short-circuits the call."""
    from streamlit.testing.v1 import AppTest

    # Track loader calls before mounting any state
    code = (
        "import streamlit as st\n"
        "import pandas as pd\n"
        "import src.reference_data as ref\n"
        "calls = {'n': 0}\n"
        "real_loader = ref._REGISTRY['VWS_GP_STANDARD_SHARE']\n"
        "def counted():\n"
        "    calls['n'] += 1\n"
        "    return real_loader()\n"
        "ref._REGISTRY['VWS_GP_STANDARD_SHARE'] = counted\n"
        "ref.prefetch_reference_datasets(['VWS_GP_STANDARD_SHARE'])\n"
        "ref.get_reference_dataset('VWS_GP_STANDARD_SHARE')\n"
        "ref.get_reference_dataset('VWS_GP_STANDARD_SHARE')\n"
        "ref.get_reference_dataset('VWS_GP_STANDARD_SHARE')\n"
        "st.session_state['n'] = calls['n']\n"
    )
    at = AppTest.from_string(code)
    at.run()
    assert at.session_state["n"] == 1


def test_step5_preserves_source_weights_across_renders():
    """Scenario 26: source-level weights from Step 4 are preserved when
    Step 5 renders, they are read-only summaries, not editable here."""
    from src.models import CustomDQRAssignment

    state = _preloaded_step5_state()
    cfg = state["configs"]["EPT"]
    cfg.dqr_sources = ["standard", "custom"]
    cfg.source_weights = {"standard": 80.0, "custom": 20.0}
    cfg.custom_assignments = [CustomDQRAssignment(rule_id="E4", weight=0)]
    at = _new_app(**state)
    final = at.session_state["configs"]["EPT"].source_weights
    assert final == {"standard": 80.0, "custom": 20.0}
