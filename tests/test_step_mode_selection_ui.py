"""End-to-end tests for the new initial step: mode selection.

``mode_selection`` is the entry point of the app. The user chooses
One-click (automated) or Step-by-step (manual), which sets ``app_mode`` and routes
onward. Driven through ``AppTest`` so the real button clicks and their
session-state side effects are exercised.
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("DATA_SOURCE", "mock")

from streamlit.testing.v1 import AppTest  # noqa: E402

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


def _entry_app() -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    return at


def test_entry_renders_both_mode_cards():
    at = _entry_app()
    assert at.session_state["current_step"] == "mode_selection"
    blob = "\n".join(m.value for m in at.markdown)
    assert "One-click mode" in blob
    assert "Step-by-step mode" in blob
    # Both pick buttons are present.
    keys = [b.key for b in at.button]
    assert "mode_pick_one_click" in keys
    assert "mode_pick_step_by_step" in keys


def test_pick_one_click_sets_mode_and_routes_to_one_click_step():
    at = _entry_app()
    at.button(key="mode_pick_one_click").click().run()
    assert at.session_state["app_mode"] == "one_click"
    assert at.session_state["current_step"] == "one_click"


def test_pick_step_by_step_sets_mode_and_routes_to_domain_selection():
    at = _entry_app()
    at.button(key="mode_pick_step_by_step").click().run()
    assert at.session_state["app_mode"] == "step_by_step"
    assert at.session_state["current_step"] == "domain_selection"


def test_active_mode_marked_selected():
    """Re-rendering the picker with a mode already chosen marks its card as
    selected (button label flips to the selected state)."""
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["app_mode"] = "one_click"
    at.session_state["current_step"] = "mode_selection"
    at.run()
    one_click_btn = at.button(key="mode_pick_one_click")
    assert "Selected" in one_click_btn.label


def test_sidebar_progress_shows_only_mode_step_before_pick():
    """Before a mode is picked the stepper collapses to just the entry step
    so the 'Step X of N' counter stays honest."""
    at = _entry_app()
    sidebar_blob = "\n".join(m.value for m in at.sidebar.markdown)
    assert "Progress" in sidebar_blob
    assert "1 of 1" in sidebar_blob or "Step 1 of 1" in sidebar_blob
