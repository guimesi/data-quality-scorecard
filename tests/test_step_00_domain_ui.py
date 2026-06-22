"""End-to-end tests for Step 0 (Domain selection) UI.

Step 0 is the entry point. New users land here with no active domain;
returning users may have one from a previous session. The tests use
``streamlit.testing.v1.AppTest`` to exercise the real button clicks
and assert on session-state side effects.
"""
from __future__ import annotations

import os
from pathlib import Path

# Force mock mode before importing settings-aware modules.
os.environ.setdefault("DATA_SOURCE", "mock")

from streamlit.testing.v1 import AppTest  # noqa: E402

from config.domains import DOMAIN_COST_ESTIMATE, DOMAIN_QUALITY  # noqa: E402

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


def _fresh_app() -> AppTest:
    """An app session sitting on the Step-by-step domain picker (Step 0).

    The domain picker now lives *behind* the new ``mode_selection`` entry
    step, reached by choosing Step-by-step mode. These tests target the domain
    picker itself, so we land directly on it (``app_mode='step_by_step'``,
    ``current_step='domain_selection'``) with no domain picked yet -
    exactly the state a user reaches after picking Step-by-step at the entry step.
    """
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["app_mode"] = "step_by_step"
    at.session_state["current_step"] = "domain_selection"
    at.run()
    return at


def test_mode_selection_is_the_default_entry_point():
    """A brand-new session lands on the mode picker, with neither a mode
    nor a domain chosen yet."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert at.session_state["current_step"] == "mode_selection"
    assert at.session_state["app_mode"] is None
    assert at.session_state["domain"] is None


def test_step0_renders_card_for_each_domain():
    at = _fresh_app()
    markdowns = [m.value for m in at.markdown]
    blob = "\n".join(markdowns)
    assert "Cost Estimate" in blob
    assert "Quality" in blob
    # Step 0 pill is rendered.
    assert any("Step 0" in m for m in markdowns)


def test_step0_next_disabled_until_pick():
    at = _fresh_app()
    next_btns = [b for b in at.button if "Next" in b.label]
    assert next_btns and all(b.disabled for b in next_btns)
    # Empty-state notice is surfaced.
    markdowns = [m.value for m in at.markdown]
    assert any("Pick a domain above" in m for m in markdowns)


def test_step0_pick_cost_estimate_sets_active_domain():
    at = _fresh_app()
    # Click the Cost Estimate card's select button.
    pick = [
        b for b in at.button
        if "Cost Estimate" in b.label and "Selected" not in b.label
    ]
    assert pick, "Select button for Cost Estimate should be present"
    pick[0].click().run()
    assert at.session_state["domain"] == DOMAIN_COST_ESTIMATE
    # After picking, the Next button becomes enabled.
    next_btns = [b for b in at.button if "Next" in b.label]
    assert any(not b.disabled for b in next_btns)


def test_step0_pick_quality_sets_active_domain():
    at = _fresh_app()
    pick = [
        b for b in at.button
        if "Quality" in b.label and "Selected" not in b.label
    ]
    assert pick, "Select button for Quality should be present"
    pick[0].click().run()
    assert at.session_state["domain"] == DOMAIN_QUALITY


def test_step0_next_advances_to_system_selection():
    at = _fresh_app()
    pick = [
        b for b in at.button
        if "Cost Estimate" in b.label and "Selected" not in b.label
    ]
    pick[0].click().run()
    next_btn = [b for b in at.button if "Next" in b.label and not b.disabled]
    assert next_btn
    next_btn[-1].click().run()
    assert at.session_state["current_step"] == "system_selection"


def test_step0_back_returns_to_mode_picker():
    """Step 0 now sits after the mode picker, so its Back button returns
    there (to switch One-click / Step-by-step)."""
    at = _fresh_app()
    back = [b for b in at.button if "Back" in b.label]
    assert back, "Step 0 should ship a Back button now that it follows the mode picker"
    back[0].click().run()
    assert at.session_state["current_step"] == "mode_selection"


def test_step0_restart_returns_to_mode_picker_and_clears_state():
    at = _fresh_app()
    pick = [
        b for b in at.button
        if "Cost Estimate" in b.label and "Selected" not in b.label
    ]
    pick[0].click().run()
    # Restart is now a two-click confirmation: the popover trigger opens it,
    # the "Yes, restart" button inside performs the reset.
    restart = [b for b in at.button if "Yes, restart" in b.label]
    assert restart, "Step 0 should ship a Restart confirmation button"
    restart[0].click().run()
    assert at.session_state["current_step"] == "mode_selection"
    assert at.session_state["app_mode"] is None
    assert at.session_state["domain"] is None


def test_step0_switching_domain_resets_downstream_state():
    """Pre-populate a partial Cost Estimate workflow, then re-enter
    Step 0 and switch to Quality. The Cost Estimate selections must
    be cleared so they don't leak into the new domain."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["domain"] = DOMAIN_COST_ESTIMATE
    at.session_state["current_step"] = "domain_selection"
    at.session_state["selected_systems"] = ["ADR"]
    at.session_state["data_products"] = {"ADR": object()}
    at.run()
    # Pick Quality from the Step 0 cards.
    pick = [
        b for b in at.button
        if "Quality" in b.label and "Selected" not in b.label
    ]
    assert pick
    pick[0].click().run()
    assert at.session_state["domain"] == DOMAIN_QUALITY
    assert at.session_state["selected_systems"] == []
    assert at.session_state["data_products"] == {}


def test_downstream_step_without_domain_is_rerouted_to_step0():
    """Defensive: if a session lands on Step 3 without a domain, the
    app.py guard reroutes it to Step 0 instead of crashing on a
    Cost-Estimate-shaped renderer."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    # Step-by-step mode picked but no "domain" → the domain gate fires and reroutes
    # to the domain picker (not the mode picker, since the mode is set).
    at.session_state["app_mode"] = "step_by_step"
    at.session_state["current_step"] = "cde_selection"
    at.run()
    assert at.session_state["current_step"] == "domain_selection"


def test_step1_uses_quality_systems_when_quality_active():
    """The historical Step 1 must show the active domain's systems.
    Switching to Quality should yield the single SQS card instead of
    ADR / ACCE / EPT - no other code change needed in Step 1."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["domain"] = DOMAIN_QUALITY
    at.session_state["current_step"] = "system_selection"
    at.run()
    # Quality-domain system checkbox is present.
    checkbox_keys = [c.key for c in at.checkbox]
    assert "chk_system_SQS" in checkbox_keys
    # Cost Estimate ones must NOT show up.
    assert "chk_system_ADR" not in checkbox_keys


def test_quality_full_flow_through_step2_builds_data_product():
    """Smoke-test the Quality domain end-to-end up to Step 2 (data
    product review). Confirms the new domain wires through the
    builder pipeline with no special-case branches required."""
    at = AppTest.from_file(APP_PATH, default_timeout=60)
    at.session_state["app_mode"] = "step_by_step"
    at.session_state["domain"] = DOMAIN_QUALITY
    at.session_state["current_step"] = "system_selection"
    at.run()
    # Pick SQS and advance to Step 2.
    at.checkbox(key="chk_system_SQS").check().run()
    next_btn = [b for b in at.button if "Next" in b.label and not b.disabled]
    next_btn[-1].click().run()
    assert at.session_state["current_step"] == "data_product_review"
    # Builder produced a non-empty SQS data product.
    assert "SQS" in at.session_state["data_products"]
    sqs_dp = at.session_state["data_products"]["SQS"]
    assert sqs_dp.row_count > 0
