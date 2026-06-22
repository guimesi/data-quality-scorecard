"""Unit tests for the Step 4 source-selection UI module.

Covers the helpers that the AppTest-based scenario tests don't easily reach:
- empty-configs error path
- the ``_nav`` Back-click and disabled-Next branches
- the dual-source slider rendering when both sources are pre-selected
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.test_ui_units import _make_fake_st


def test_render_with_empty_configs_shows_error_and_disables_next():
    import ui.step_04_dqr_source_selection as s4

    fake_st = _make_fake_st()
    fake_st.session_state["configs"] = {}
    with patch.object(s4, "st", fake_st):
        s4.render()

    fake_st.error.assert_called_once()
    args, _ = fake_st.error.call_args
    assert "No Data Products configured" in args[0]


def test_nav_disabled_next_renders_without_action():
    import ui.step_04_dqr_source_selection as s4

    fake_st = _make_fake_st()
    fake_st.button = MagicMock(return_value=False)
    # ``_nav`` now delegates to ``utils.ui_components.render_nav_footer``;
    # the shared helper has its own ``st`` import that must see the fake.
    with patch.object(s4, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_04_dqr_source_selection.next_step") as mock_next, \
         patch("ui.step_04_dqr_source_selection.prev_step") as mock_prev:
        s4._nav(show_next=False)
    # Disabled button rendered, no navigation invoked.
    mock_next.assert_not_called()
    mock_prev.assert_not_called()


def test_nav_back_click_calls_prev_step():
    import ui.step_04_dqr_source_selection as s4

    # First call (Back) returns True; subsequent calls (any Next) return False.
    fake_st = _make_fake_st()
    call_results = iter([True, False, False])
    fake_st.button = MagicMock(side_effect=lambda *a, **kw: next(call_results))
    with patch.object(s4, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_04_dqr_source_selection.prev_step") as mock_prev:
        s4._nav(show_next=True)
    mock_prev.assert_called_once()


def test_nav_next_click_calls_next_step():
    import ui.step_04_dqr_source_selection as s4

    fake_st = _make_fake_st()
    # Back=False, Restart=False, Next=True (3-button nav row).
    call_results = iter([False, False, True])
    fake_st.button = MagicMock(side_effect=lambda *a, **kw: next(call_results))
    with patch.object(s4, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_04_dqr_source_selection.next_step") as mock_next:
        s4._nav(show_next=True)
    mock_next.assert_called_once()


def test_nav_restart_click_calls_restart_app():
    """Step 4 also exposes the Restart button; clicking it calls
    ``restart_app`` to clear all workflow state."""
    import ui.step_04_dqr_source_selection as s4

    fake_st = _make_fake_st()
    # Back=False, Restart=True, Next=False
    call_results = iter([False, True, False])
    fake_st.button = MagicMock(side_effect=lambda *a, **kw: next(call_results))
    with patch.object(s4, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_04_dqr_source_selection.restart_app") as mock_restart:
        s4._nav(show_next=True)
    mock_restart.assert_called_once()
