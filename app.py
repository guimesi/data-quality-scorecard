"""
Streamlit entry point for the Data Quality Scorecard application.

Run with:  streamlit run app.py
"""
from __future__ import annotations

# On corporate machines behind a TLS-inspecting proxy, Python's bundled
# certifi CAs reject outbound HTTPS (e.g. the Airtable push). truststore
# switches SSL verification to the OS trust store, where corporate IT
# already provisions the proxy's root CA. Harmless in Databricks Apps
# (no intercepting proxy); in any env without the package this no-ops
# and certificate handling stays exactly as before.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover - truststore not installed
    pass

import streamlit as st

from ui import (
    step_00_domain_selection,
    step_01_system_selection,
    step_02_data_product_review,
    step_03_cde_selection,
    step_04_2_custom_dqr,
    step_04_dqr_assignment,
    step_04_dqr_source_selection,
    step_05_weight_assignment,
    step_06_dashboard,
    step_07_ml_lab,
    step_adoption,
    step_mode_selection,
    step_one_click,
)
from ui._theme import inject_global_css
from utils.session_state import (
    consume_scroll_to_top,
    init_state,
    inject_sidebar_css,
    render_planview_filter,
    render_progress_sidebar,
    render_sample_mode_toggle,
    render_sidebar_brand,
    render_sidebar_footer,
)
from utils.telemetry import log_app_open_once, log_step_view

st.set_page_config(
    page_title="DQ Scorecard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Steps that render *before* a domain is known. Everything else assumes
# ``session_state.domain`` is populated (the domain gate below enforces it).
# ``mode_selection`` picks the mode, ``one_click`` picks the domain itself,
# ``domain_selection`` is the Step-by-step domain picker, and ``adoption``
# is the standalone admin page (usage metrics span every domain).
_DOMAINLESS_STEPS = {"mode_selection", "one_click", "domain_selection", "adoption"}


STEP_RENDERERS = {
    "mode_selection": step_mode_selection.render,
    "one_click": step_one_click.render,
    "domain_selection": step_00_domain_selection.render,
    "system_selection": step_01_system_selection.render,
    "data_product_review": step_02_data_product_review.render,
    "cde_selection": step_03_cde_selection.render,
    "dqr_source_selection": step_04_dqr_source_selection.render,
    "dqr_assignment": step_04_dqr_assignment.render,
    "dqr_custom_rules": step_04_2_custom_dqr.render,
    "weight_assignment": step_05_weight_assignment.render,
    "dashboard": step_06_dashboard.render,
    "ml_lab": step_07_ml_lab.render,
    "adoption": step_adoption.render,
}


def main() -> None:
    init_state()

    # Mode gate: ``mode_selection`` is the entry point. A brand-new session
    # (no mode and no domain) is routed there so the user picks One-click or
    # Step-by-step before anything else renders. The ``adoption`` admin page
    # is exempt - it is reached from the entry screen before any mode is
    # picked and needs neither mode nor domain.
    if (
        not st.session_state.get("app_mode")
        and not st.session_state.get("domain")
        and st.session_state.get("current_step") != "adoption"
    ):
        st.session_state.current_step = "mode_selection"
    # Domain gate: every step outside ``_DOMAINLESS_STEPS`` assumes
    # ``session_state.domain`` is populated. A session that lost the domain
    # (older bookmarked URL, manual session_state edit) is rerouted to the
    # Step-by-step domain picker so it never renders domain-shaped widgets against
    # an unknown domain.
    elif (
        st.session_state.current_step not in _DOMAINLESS_STEPS
        and not st.session_state.get("domain")
    ):
        st.session_state.current_step = "domain_selection"

    # If the previous render requested a scroll-to-top (Next/Back/Restart),
    # emit the JS now - before any visible widgets, so the user lands at
    # the top of the new step.
    consume_scroll_to_top()

    # Inject CSS once per render, then build each sidebar section. Each
    # render_* helper wraps its widgets in a scoped card via the injected
    # styles; the original section break / order is preserved.
    inject_sidebar_css()
    render_sidebar_brand()
    render_progress_sidebar()
    render_sample_mode_toggle()
    render_planview_filter()
    render_sidebar_footer()

    # Main-area chrome: one consolidated stylesheet for every step (the
    # Step-by-step wizard + Dashboard). The ML Lab and One-click steps layer a
    # slim themed override on top inside their own render().
    inject_global_css()

    st.title("Data Quality Scorecard")

    current = st.session_state.current_step
    renderer = STEP_RENDERERS.get(current)
    if renderer is None:
        st.error(f"Unknown step: {current}")
        return

    # Adoption/audit telemetry (fire-and-forget; session-state guards make
    # these no-ops on reruns): one app_open per session, one step_view per
    # step transition.
    log_app_open_once()
    log_step_view(current)

    renderer()


if __name__ == "__main__":
    main()
