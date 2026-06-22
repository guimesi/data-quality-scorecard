"""
Streamlit entry point for the Data Quality Scorecard application.

Run with:  streamlit run app.py
"""
from __future__ import annotations

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

st.set_page_config(
    page_title="DQ Scorecard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Steps that render *before* a domain is known. Everything else assumes
# ``session_state.domain`` is populated (the domain gate below enforces it).
# ``mode_selection`` picks the mode, ``one_click`` picks the domain itself,
# and ``domain_selection`` is the Step-by-step domain picker.
_DOMAINLESS_STEPS = {"mode_selection", "one_click", "domain_selection"}


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
}


def main() -> None:
    init_state()

    # Mode gate: ``mode_selection`` is the entry point. A brand-new session
    # (no mode and no domain) is routed there so the user picks One-click or
    # Step-by-step before anything else renders.
    if not st.session_state.get("app_mode") and not st.session_state.get("domain"):
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
    renderer()


if __name__ == "__main__":
    main()
