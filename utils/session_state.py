"""Session state and navigation - public entry point.

The implementation has been partitioned by concern into
:mod:`utils.session`. This module re-exports the public names so external
callers (UI step modules, tests that ``patch("utils.session_state.X", ...)``)
keep importing from ``utils.session_state`` exactly as before.

- :mod:`utils.session.state`: STEPS, STEP_LABELS, init_state, set_domain,
  require_active_domain, _clear_workflow_state_for_domain_switch.
- :mod:`utils.session.navigation`: _visible_steps, goto,
  consume_scroll_to_top, restart_app, next_step, prev_step, plus the
  ``STEP_VISIBILITY_PREDICATES`` map and its ``_any_dp_uses_source`` /
  ``_ml_lab_visible`` helpers.
- :mod:`utils.session.sidebar`: inject_sidebar_css, render_sidebar_brand,
  render_progress_sidebar, render_sample_mode_toggle, get_row_limit,
  get_planview_filter, render_planview_filter, render_sidebar_footer.
"""
from __future__ import annotations

from utils.session.navigation import (
    _SCROLL_TO_TOP_KEY,
    STEP_VISIBILITY_PREDICATES,
    _any_dp_uses_source,
    _ml_lab_visible,
    _mode_is_one_click,
    _mode_is_step_by_step,
    _visible_steps,
    consume_scroll_to_top,
    goto,
    next_step,
    prev_step,
    restart_app,
)
from utils.session.sidebar import (
    _parse_planview_filter_text,
    get_planview_filter,
    get_row_limit,
    inject_sidebar_css,
    render_planview_filter,
    render_progress_sidebar,
    render_sample_mode_toggle,
    render_sidebar_brand,
    render_sidebar_footer,
)
from utils.session.state import (
    APP_MODE_ONE_CLICK,
    APP_MODE_STEP_BY_STEP,
    APP_MODES,
    STEP_LABELS,
    STEPS,
    _clear_workflow_state_for_domain_switch,
    init_state,
    logger,
    require_active_domain,
    set_app_mode,
    set_domain,
)

__all__ = [
    # state.py
    "STEPS",
    "STEP_LABELS",
    "APP_MODE_ONE_CLICK",
    "APP_MODE_STEP_BY_STEP",
    "APP_MODES",
    "init_state",
    "set_domain",
    "set_app_mode",
    "require_active_domain",
    "_clear_workflow_state_for_domain_switch",
    "logger",
    # navigation.py
    "STEP_VISIBILITY_PREDICATES",
    "_visible_steps",
    "goto",
    "consume_scroll_to_top",
    "restart_app",
    "next_step",
    "prev_step",
    "_SCROLL_TO_TOP_KEY",
    "_any_dp_uses_source",
    "_ml_lab_visible",
    "_mode_is_step_by_step",
    "_mode_is_one_click",
    # sidebar.py
    "inject_sidebar_css",
    "render_sidebar_brand",
    "render_progress_sidebar",
    "render_sample_mode_toggle",
    "get_row_limit",
    "get_planview_filter",
    "render_planview_filter",
    "render_sidebar_footer",
    "_parse_planview_filter_text",
]
