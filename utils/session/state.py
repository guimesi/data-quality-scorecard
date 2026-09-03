"""Workflow state: step inventory, init, domain set/get/clear.

Holds the canonical step list and labels, the ``init_state`` factory that
seeds Streamlit ``session_state`` defaults, and the domain switching
helpers that wipe downstream selections when the active domain changes.

Navigation logic (next / prev / restart / visibility) lives in
:mod:`utils.session.navigation`; sidebar rendering lives in
:mod:`utils.session.sidebar`. The legacy :mod:`utils.session_state` module
re-exports everything so callers don't need to be updated.
"""
from __future__ import annotations

import logging
from typing import Dict, List

import streamlit as st

logger = logging.getLogger(__name__)


# Application modes picked at the new initial step (``mode_selection``).
# ``one_click`` automates the whole flow after domain + system selection;
# ``step_by_step`` enters the historical manual flow unchanged.
APP_MODE_ONE_CLICK: str = "one_click"
APP_MODE_STEP_BY_STEP: str = "step_by_step"
APP_MODES = (APP_MODE_ONE_CLICK, APP_MODE_STEP_BY_STEP)


# Ordered list of steps. ``mode_selection`` is the new entry point: the
# user first picks One-click vs Step-by-step. The One-click flow uses the single
# ``one_click`` step (domain + systems, then full automation) and lands on
# the dashboard; the Step-by-step flow walks the historical steps unchanged
# (``domain_selection`` gates everything after it). Which steps are
# *visible* depends on the active mode, see :func:`_visible_steps`.
# Sub-steps 4.1 / 4.2 remain conditionally visible based on each Data
# Product's selected DQR sources.
STEPS: List[str] = [
    "mode_selection",
    "one_click",
    "domain_selection",
    "system_selection",
    "data_product_review",
    "cde_selection",
    "dqr_source_selection",
    "dqr_assignment",
    "dqr_custom_rules",
    "weight_assignment",
    "dashboard",
    "ml_lab",
    # Standalone admin page (adoption / audit metrics). Reached from the
    # entry screen; only visible in the stepper while inside it.
    "adoption",
]

STEP_LABELS: Dict[str, str] = {
    "mode_selection": "Mode",
    "one_click": "Domain & systems",
    "domain_selection": "Domain",
    "system_selection": "Systems",
    "data_product_review": "Data Products",
    "cde_selection": "CDEs",
    "dqr_source_selection": "DQR sources",
    "dqr_assignment": "Standard DQRs",
    "dqr_custom_rules": "Custom DQRs",
    "weight_assignment": "Weights",
    "dashboard": "Scorecard",
    "ml_lab": "ML Lab",
    "adoption": "Usage & audit",
}


def init_state() -> None:
    defaults = {
        # Entry step - the user first picks an application mode
        # (One-click vs Step-by-step). ``None`` means "not picked yet"; the
        # ``mode_selection`` UI sets it and the app routes here until it's
        # one of ``APP_MODES``.
        "app_mode": None,
        # Domain (Cost Estimate, Quality, ...). ``None`` means "user hasn't
        # picked yet"; both the Step-by-step Step 0 UI and the One-click step set
        # it, and downstream Step-by-step steps refuse to render until it's a
        # valid registered code.
        "domain": None,
        "current_step": "mode_selection",
        "selected_systems": [],          # list[str] e.g. ["ADR", "ACCE"]
        "data_products": {},             # dict[str, DataProduct]
        "configs": {},                   # dict[str, DataProductConfig]
        "scorecards": {},                # dict[str, ScorecardResult]
        "sample_mode": True,             # True = cap rows (sample); False = full dataset
        "planview_filter": [],           # list[str] of PLANVIEW_IDs; empty = no filter
        # ML Lab - session-local list of snapshot dicts (see src.ml_lab).
        # Lives across reruns but is wiped by ``restart_app``.
        "ml_lab_runs": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _clear_workflow_state_for_domain_switch() -> None:
    """Drop any domain-scoped state so the new domain renders cleanly.

    Called by Step 0 when the user picks (or changes) a domain, and by
    ``restart_app`` when the user resets the whole flow. Keeps purely
    UI-side preferences (``sample_mode``, ``planview_filter``) intact -
    those are general dataset-size controls, not domain artefacts.
    """
    # Imported lazily to avoid pulling pandas + Databricks deps when this
    # module is imported by lightweight tests that mock streamlit.
    try:
        from src.databricks_client import close_shared_client
        from src.reference_data import clear_reference_cache

        clear_reference_cache()
        close_shared_client()
    except Exception:
        # Best-effort cleanup. In unit tests that mock these modules
        # away the cleanup is irrelevant and we don't want a stray
        # import error to mask the actual test failure. Log at DEBUG
        # so prod runs with verbose logging still get a breadcrumb.
        logger.debug("Skipped reference/client cleanup", exc_info=True)

    st.session_state.selected_systems = []
    st.session_state.data_products = {}
    st.session_state.configs = {}
    st.session_state.scorecards = {}
    st.session_state.ml_lab_runs = []
    # One-click leaves a one-time summary banner for the dashboard; drop it
    # so a restarted / re-pointed session doesn't show a stale notice.
    st.session_state.pop("one_click_summary", None)


def set_domain(code: str) -> None:
    """Set the active domain and reset any state from the previous one.

    Idempotent: picking the same domain again is a no-op so the user
    doesn't lose their in-flight workflow by clicking the same card
    twice. Switching domains wipes the downstream selections so the
    next render of Step 1 starts from a clean slate (otherwise a
    ``selected_systems = ["ADR"]`` left over from Cost Estimate would
    leak into the Quality flow as an invalid system code).
    """
    from config.domains import get_domain  # validates the code

    get_domain(code)  # raises KeyError for unknown codes
    previous = st.session_state.get("domain")
    st.session_state.domain = code
    if previous != code:
        _clear_workflow_state_for_domain_switch()


def set_app_mode(mode: str) -> None:
    """Set the active application mode picked at ``mode_selection``.

    Idempotent: re-picking the same mode is a no-op so a user re-entering
    the mode picker (e.g. via Back) doesn't lose their in-flight workflow.
    Switching modes wipes the downstream workflow artefacts (systems, data
    products, configs, scorecards, ML Lab runs) so a half-built Step-by-step flow
    never leaks into a One-click run or vice-versa. The active domain and
    pure UI preferences (sample mode, project filter) are intentionally
    kept - they're reusable across both modes.
    """
    if mode not in APP_MODES:
        raise ValueError(
            f"Unknown app mode: {mode}. Expected one of {APP_MODES}."
        )
    previous = st.session_state.get("app_mode")
    st.session_state.app_mode = mode
    if previous != mode:
        _clear_workflow_state_for_domain_switch()


def require_active_domain() -> str:
    """Return the active domain code, raising if Step 0 was bypassed.

    Step renderers downstream of Step 0 call this so a malformed entry
    URL (or a session that lost ``domain``) sends the user back to
    Step 0 instead of rendering Cost-Estimate-shaped widgets against an
    unknown domain.
    """
    code = st.session_state.get("domain")
    if not code:
        raise RuntimeError(
            "No active domain. Return to Step 0 to pick one."
        )
    return code
