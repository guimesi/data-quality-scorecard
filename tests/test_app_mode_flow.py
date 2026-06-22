"""Cross-cutting tests for the mode split: entry on-ramp, flow separation,
and the regression guarantee that the Step-by-step flow is reachable and unchanged.

Two layers:
- ``AppTest`` smoke tests for the entry -> Step-by-step / One-click on-ramps.
- Unit tests for the mode-aware visibility predicates and ``set_app_mode``
  state-clearing, driven through the bare streamlit session state.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("DATA_SOURCE", "mock")

import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from utils.session.navigation import _visible_steps  # noqa: E402
from utils.session.state import set_app_mode  # noqa: E402

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


# ---------------------------------------------------------------------------
# Entry on-ramps (AppTest)
# ---------------------------------------------------------------------------

def test_entry_then_step_by_step_reaches_domain_then_systems():
    """Regression: the Step-by-step flow is fully reachable through the new entry
    step and behaves as before (domain picker -> system selection)."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert at.session_state["current_step"] == "mode_selection"

    at.button(key="mode_pick_step_by_step").click().run()
    assert at.session_state["current_step"] == "domain_selection"

    # Pick Cost Estimate and advance - the historical Step 1 still works.
    pick = [b for b in at.button if "Cost Estimate" in b.label and "Selected" not in b.label]
    pick[0].click().run()
    nxt = [b for b in at.button if "Next" in b.label and not b.disabled]
    nxt[-1].click().run()
    assert at.session_state["current_step"] == "system_selection"


def test_entry_then_one_click_reaches_one_click_step():
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    at.button(key="mode_pick_one_click").click().run()
    assert at.session_state["app_mode"] == "one_click"
    assert at.session_state["current_step"] == "one_click"
    # The One-click domain picker is present.
    assert any(b.key == "oneclick_domain_cost_estimate" for b in at.button)


# ---------------------------------------------------------------------------
# Flow separation (visibility predicates)
# ---------------------------------------------------------------------------

def test_visible_steps_step_by_step_hides_one_click():
    st.session_state.clear()
    st.session_state["app_mode"] = "step_by_step"
    st.session_state["current_step"] = "domain_selection"
    visible = _visible_steps()
    assert "one_click" not in visible
    for step in ("domain_selection", "system_selection", "weight_assignment", "dashboard"):
        assert step in visible
    assert visible[0] == "mode_selection"


def test_visible_steps_one_click_hides_step_by_step_steps():
    st.session_state.clear()
    st.session_state["app_mode"] = "one_click"
    st.session_state["current_step"] = "one_click"
    visible = _visible_steps()
    assert visible == ["mode_selection", "one_click", "dashboard"]
    for step in ("domain_selection", "system_selection", "cde_selection", "weight_assignment"):
        assert step not in visible


def test_visible_steps_before_mode_pick_is_just_entry():
    st.session_state.clear()
    st.session_state["app_mode"] = None
    st.session_state["current_step"] = "mode_selection"
    assert _visible_steps() == ["mode_selection"]


# ---------------------------------------------------------------------------
# set_app_mode state handling
# ---------------------------------------------------------------------------

def test_switching_mode_clears_workflow_state():
    st.session_state.clear()
    st.session_state["app_mode"] = "one_click"
    st.session_state["selected_systems"] = ["EPT"]
    st.session_state["data_products"] = {"EPT": object()}
    st.session_state["configs"] = {"EPT": object()}
    st.session_state["scorecards"] = {"EPT": object()}
    set_app_mode("step_by_step")
    assert st.session_state["app_mode"] == "step_by_step"
    assert st.session_state["selected_systems"] == []
    assert st.session_state["data_products"] == {}
    assert st.session_state["configs"] == {}
    assert st.session_state["scorecards"] == {}


def test_repicking_same_mode_keeps_state():
    st.session_state.clear()
    st.session_state["app_mode"] = "step_by_step"
    st.session_state["selected_systems"] = ["EPT"]
    set_app_mode("step_by_step")  # idempotent - must not wipe in-flight work
    assert st.session_state["selected_systems"] == ["EPT"]


def test_set_app_mode_rejects_unknown_mode():
    import pytest
    st.session_state.clear()
    with pytest.raises(ValueError, match="Unknown app mode"):
        set_app_mode("turbo")
