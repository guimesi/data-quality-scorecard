"""
Streamlit entry point for the Data Quality Scorecard application.

Run with:  streamlit run app.py
"""
from __future__ import annotations

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
    page_icon=":material/fact_check:",
    layout="wide",
    initial_sidebar_state="expanded",
)

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

    if (
        not st.session_state.get("app_mode")
        and not st.session_state.get("domain")
        and st.session_state.get("current_step") != "adoption"
    ):
        st.session_state.current_step = "mode_selection"
    elif (
        st.session_state.current_step not in _DOMAINLESS_STEPS
        and not st.session_state.get("domain")
    ):
        st.session_state.current_step = "domain_selection"

    consume_scroll_to_top()

    # One stylesheet for the whole app (main area + sidebar rail). Injected
    # before the sidebar so the rail paints styled on the first frame.
    inject_global_css()
    inject_sidebar_css()  # kept for API compatibility; the rail CSS lives in ui/_theme.py

    # Sidebar = navigation rail: brand → workspace + stepper → settings → footer.
    render_sidebar_brand()
    render_progress_sidebar()
    render_sample_mode_toggle()
    render_planview_filter()
    render_sidebar_footer()

    # NOTE: no st.title() here - each step owns its page header via
    # utils.ui_components.page_header (eyebrow + title + one-line subtitle).

    current = st.session_state.current_step
    renderer = STEP_RENDERERS.get(current)
    if renderer is None:
        st.error(f"Unknown step: {current}")
        return

    log_app_open_once()
    log_step_view(current)

    renderer()


if __name__ == "__main__":
    main()
