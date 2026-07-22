"""Step navigation: next / prev / restart, visibility predicates, scroll-to-top.

Sub-steps 4.1 (Standard DQR assignment) and 4.2 (Custom DQR rules) are
conditionally visible based on each Data Product's selected DQR sources,
and the ML Lab is only visible once a scorecard has been generated.
:func:`_visible_steps` collapses the canonical :data:`STEPS` list to the
ones actually relevant to the current configuration; ``next_step`` /
``prev_step`` walk that collapsed list.
"""
from __future__ import annotations

from typing import Callable, Dict, List

import streamlit as st
import streamlit.components.v1 as components

from config.dqr_sources import SOURCE_CUSTOM, SOURCE_STANDARD
from utils.session.state import APP_MODE_ONE_CLICK, APP_MODE_STEP_BY_STEP, STEPS

_SCROLL_TO_TOP_KEY = "_scroll_to_top"


def _any_dp_uses_source(source: str) -> bool:
    configs = st.session_state.get("configs", {}) or {}
    return any(source in (cfg.dqr_sources or []) for cfg in configs.values())


def _mode_is_step_by_step() -> bool:
    return st.session_state.get("app_mode") == APP_MODE_STEP_BY_STEP


def _mode_is_one_click() -> bool:
    return st.session_state.get("app_mode") == APP_MODE_ONE_CLICK


def _ml_lab_visible() -> bool:
    """The experimental ML Lab is opt-in: only surfaces in the sidebar
    stepper once the user has reached Step 6 at least once (which populates
    ``scorecards``) OR is currently inside the lab. This keeps the
    "Step X of N" counter honest during the first five steps and avoids
    distracting first-time users with a beta tab they can't use yet."""
    if st.session_state.get("current_step") == "ml_lab":
        return True
    return bool(st.session_state.get("scorecards"))


# Steps absent from this dict are always visible (only ``mode_selection``,
# the entry step, qualifies). Everything else is gated on the active mode:
# the Step-by-step steps only show in Step-by-step mode, the ``one_click`` step only in
# One-click mode, and the dashboard / ML Lab show in either mode once
# reachable.
STEP_VISIBILITY_PREDICATES: Dict[str, Callable[[], bool]] = {
    "one_click": _mode_is_one_click,
    "domain_selection": _mode_is_step_by_step,
    "system_selection": _mode_is_step_by_step,
    "data_product_review": _mode_is_step_by_step,
    "cde_selection": _mode_is_step_by_step,
    "dqr_source_selection": _mode_is_step_by_step,
    "dqr_assignment": lambda: _mode_is_step_by_step() and _any_dp_uses_source(SOURCE_STANDARD),
    "dqr_custom_rules": lambda: _mode_is_step_by_step() and _any_dp_uses_source(SOURCE_CUSTOM),
    "weight_assignment": _mode_is_step_by_step,
    # Both modes land on the dashboard; it surfaces once a mode is chosen.
    "dashboard": lambda: bool(st.session_state.get("app_mode")),
    "ml_lab": _ml_lab_visible,
    # Standalone admin page: visible in the stepper only while inside it,
    # so the "Step X of N" counter stays honest for the scoring flow.
    "adoption": lambda: st.session_state.get("current_step") == "adoption",
}


def _visible_steps() -> List[str]:
    return [s for s in STEPS if STEP_VISIBILITY_PREDICATES.get(s, lambda: True)()]


def goto(step: str) -> None:
    if step not in STEPS:
        raise ValueError(f"Unknown step: {step}")
    st.session_state.current_step = step
    # Request the next render to scroll the parent window back to the top so
    # the user lands at the new step's header instead of mid-scroll.
    st.session_state[_SCROLL_TO_TOP_KEY] = True
    st.rerun()


def consume_scroll_to_top() -> None:
    """If a step transition requested a scroll-to-top, emit a tiny invisible
    HTML/JS component that scrolls the parent window to the top, then clear
    the flag. Safe to call on every render."""
    if not st.session_state.get(_SCROLL_TO_TOP_KEY):
        return
    st.session_state[_SCROLL_TO_TOP_KEY] = False
    components.html(
        """
        <script>
            // The component runs in an iframe sharing origin with the host
            // page, so we can scroll the parent window directly.
            window.parent.scrollTo({top: 0, left: 0, behavior: 'instant'});
        </script>
        """,
        height=0,
        width=0,
    )


def restart_app() -> None:
    """Clear all workflow state and return to the entry step (mode picker).

    Used by the Restart button that lives in every step's nav bar. Keeps
    the sidebar's Sample-mode preference intact (it's a UI preference,
    not part of the workflow data the user is restarting). Also clears
    the active domain *and* the chosen mode so the user re-picks both -
    useful when restarting from late in the flow to switch domain or to
    swap between One-click and Step-by-step.
    """
    from utils.session.state import _clear_workflow_state_for_domain_switch

    _clear_workflow_state_for_domain_switch()
    st.session_state.planview_filter = []
    st.session_state.domain = None
    st.session_state.app_mode = None
    goto("mode_selection")


def next_step() -> None:
    """Advance to the next *visible* step. Sub-steps 4.1/4.2 are skipped when
    no Data Product has opted into their respective source."""
    visible = _visible_steps()
    current = st.session_state.current_step
    if current not in visible:
        # Currently on a hidden step (shouldn't happen via the UI, but be
        # defensive): jump to the next visible step in raw order. If the
        # stored step is unknown entirely (corrupted session), restart at
        # the first visible step.
        if current not in STEPS:
            goto(visible[0])
            return
        idx = STEPS.index(current)
        for s in STEPS[idx + 1:]:
            if s in visible:
                goto(s)
                return
        return  # pragma: no cover - dashboard is the last visible step
    idx = visible.index(current)
    if idx < len(visible) - 1:
        goto(visible[idx + 1])


def prev_step() -> None:
    visible = _visible_steps()
    current = st.session_state.current_step
    if current not in visible:
        if current not in STEPS:
            goto(visible[0])
            return
        idx = STEPS.index(current)
        for s in reversed(STEPS[:idx]):
            if s in visible:
                goto(s)
                return
        return  # pragma: no cover - mode_selection is the first visible step
    idx = visible.index(current)
    if idx > 0:
        goto(visible[idx - 1])
