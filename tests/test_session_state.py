"""Tests for utils/session_state.py.

Uses a FakeSessionState (a dict that also supports attribute access) plus
monkeypatching of the Streamlit module so these tests don't require
a running Streamlit session.
"""
from __future__ import annotations

import pytest

from utils import session_state as ss_mod


class FakeSessionState(dict):
    """Dict that also supports attribute-style access (like Streamlit's)."""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(item) from e

    def __setattr__(self, key, value):
        self[key] = value


class FakeSidebar:
    def __init__(self) -> None:
        self.markdowns: list[str] = []
        self.captions: list[str] = []
        self.text_areas: list[tuple] = []
        self._toggle_return = True
        self._text_area_return = ""

    def markdown(self, text: str, **kwargs) -> None:
        self.markdowns.append(text)

    def caption(self, text: str) -> None:
        self.captions.append(text)

    def toggle(self, label: str, value: bool = False, key: str | None = None, help: str | None = None) -> bool:
        return self._toggle_return

    def text_area(self, label: str, value: str = "", key: str | None = None,
                  height: int | None = None, placeholder: str | None = None,
                  help: str | None = None) -> str:
        self.text_areas.append((label, value))
        return self._text_area_return or value


class FakeStreamlit:
    def __init__(self) -> None:
        self.session_state = FakeSessionState()
        self.sidebar = FakeSidebar()
        self.rerun_called = False

    def rerun(self) -> None:
        self.rerun_called = True
        raise _RerunSignal()


class _RerunSignal(Exception):
    """Mimic st.rerun halting execution."""


@pytest.fixture
def fake_st(monkeypatch):
    # session_state was partitioned into utils.session.{state, navigation,
    # sidebar} (M7). Patch ``st`` on each sub-module since each one imports
    # its own copy of the streamlit module at top-level.
    from utils.session import navigation as nav_mod
    from utils.session import sidebar as sidebar_mod
    from utils.session import state as state_mod

    fake = FakeStreamlit()
    monkeypatch.setattr(state_mod, "st", fake)
    monkeypatch.setattr(nav_mod, "st", fake)
    monkeypatch.setattr(sidebar_mod, "st", fake)
    return fake


def test_init_state_populates_defaults(fake_st):
    ss_mod.init_state()
    # ``mode_selection`` is the new entry point; ``app_mode`` and ``domain``
    # both stay ``None`` until the user picks them in the entry steps.
    assert fake_st.session_state.current_step == "mode_selection"
    assert fake_st.session_state.app_mode is None
    assert fake_st.session_state.domain is None
    assert fake_st.session_state.selected_systems == []
    assert fake_st.session_state.data_products == {}
    assert fake_st.session_state.configs == {}
    assert fake_st.session_state.scorecards == {}
    assert fake_st.session_state.sample_mode is True


def test_init_state_does_not_overwrite_existing(fake_st):
    fake_st.session_state["current_step"] = "cde_selection"
    ss_mod.init_state()
    assert fake_st.session_state.current_step == "cde_selection"


def test_goto_valid_step(fake_st):
    ss_mod.init_state()
    with pytest.raises(_RerunSignal):
        ss_mod.goto("dashboard")
    assert fake_st.session_state.current_step == "dashboard"
    assert fake_st.rerun_called


def test_goto_invalid_step(fake_st):
    ss_mod.init_state()
    with pytest.raises(ValueError, match="Unknown step"):
        ss_mod.goto("not_a_step")


def test_next_step_advances(fake_st):
    ss_mod.init_state()
    # In Step-by-step mode the step after the domain picker is system_selection.
    fake_st.session_state.app_mode = "step_by_step"
    fake_st.session_state.current_step = "domain_selection"
    with pytest.raises(_RerunSignal):
        ss_mod.next_step()
    assert fake_st.session_state.current_step == "system_selection"


def test_next_step_at_last_is_noop(fake_st):
    ss_mod.init_state()
    fake_st.session_state.current_step = "dashboard"
    # Should NOT call rerun / advance further
    ss_mod.next_step()
    assert fake_st.session_state.current_step == "dashboard"
    assert not fake_st.rerun_called


def test_prev_step_goes_back(fake_st):
    ss_mod.init_state()
    fake_st.session_state.app_mode = "step_by_step"
    fake_st.session_state.current_step = "cde_selection"
    with pytest.raises(_RerunSignal):
        ss_mod.prev_step()
    assert fake_st.session_state.current_step == "data_product_review"


def test_prev_step_at_first_is_noop(fake_st):
    ss_mod.init_state()
    # current_step is "mode_selection" by default (the entry step now)
    ss_mod.prev_step()
    assert fake_st.session_state.current_step == "mode_selection"
    assert not fake_st.rerun_called


def test_next_step_recovers_from_unknown_current_step(fake_st):
    """A corrupted session_state where current_step is not in STEPS at all
    (e.g. an old persisted value from a removed step) must not crash;
    next_step should reset to the first visible step instead of raising."""
    ss_mod.init_state()
    fake_st.session_state.current_step = "ghost_step_that_was_removed"
    with pytest.raises(_RerunSignal):
        ss_mod.next_step()
    assert fake_st.session_state.current_step == "mode_selection"


def test_prev_step_recovers_from_unknown_current_step(fake_st):
    """Mirror of next_step recovery: prev_step on an unknown step also
    resets to the first visible step rather than raising ValueError."""
    ss_mod.init_state()
    fake_st.session_state.current_step = "ghost_step_that_was_removed"
    with pytest.raises(_RerunSignal):
        ss_mod.prev_step()
    assert fake_st.session_state.current_step == "mode_selection"


def test_render_progress_sidebar_marks_current_bold(fake_st):
    ss_mod.init_state()
    fake_st.session_state.app_mode = "step_by_step"
    fake_st.session_state.current_step = "cde_selection"
    ss_mod.render_progress_sidebar()
    # The new sidebar emits a single HTML block with all steps inline.
    blob = "\n".join(fake_st.sidebar.markdowns)
    assert "Progress" in blob
    # The current step is rendered with the "current" CSS class and the CDEs label.
    assert 'sb-step current' in blob
    # The "CDEs" label is the current step's label.
    current_segment = blob.split('sb-step current', 1)[1]
    # Other steps follow, so only check the label appears before the next step block.
    next_step_start = current_segment.find('class="sb-step ')
    current_block = (
        current_segment[:next_step_start] if next_step_start != -1 else current_segment
    )
    assert "CDEs" in current_block


def test_get_row_limit_in_sample_mode(fake_st):
    ss_mod.init_state()
    fake_st.session_state.sample_mode = True
    assert ss_mod.get_row_limit() is not None


def test_get_row_limit_in_full_mode(fake_st):
    ss_mod.init_state()
    fake_st.session_state.sample_mode = False
    assert ss_mod.get_row_limit() is None


def test_render_sample_mode_toggle_no_change(fake_st):
    ss_mod.init_state()
    fake_st.session_state.sample_mode = True
    fake_st.sidebar._toggle_return = True  # unchanged
    ss_mod.render_sample_mode_toggle()
    assert fake_st.session_state.sample_mode is True
    # Sample-mode status pill is rendered as HTML markdown in the sidebar.
    assert any("Sample" in m for m in fake_st.sidebar.markdowns)


def test_render_sample_mode_toggle_switching_to_full_invalidates_caches(fake_st):
    ss_mod.init_state()
    fake_st.session_state.sample_mode = True
    fake_st.session_state.data_products = {"ADR": object()}
    fake_st.session_state.configs = {"ADR": object()}
    fake_st.session_state.scorecards = {"ADR": object()}
    fake_st.sidebar._toggle_return = False  # user flipped it

    with pytest.raises(_RerunSignal):
        ss_mod.render_sample_mode_toggle()

    assert fake_st.session_state.sample_mode is False
    assert fake_st.session_state.data_products == {}
    assert fake_st.session_state.configs == {}
    assert fake_st.session_state.scorecards == {}


def test_render_sample_mode_toggle_full_mode_caption(fake_st):
    ss_mod.init_state()
    fake_st.session_state.sample_mode = False
    fake_st.sidebar._toggle_return = False  # unchanged, stays False
    ss_mod.render_sample_mode_toggle()
    # Full-dataset pill is rendered as HTML markdown in the sidebar.
    assert any("Full dataset" in m for m in fake_st.sidebar.markdowns)
