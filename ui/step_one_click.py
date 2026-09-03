"""
One-click: domain + systems on the left, a sticky "Run plan" with the single
primary action on the right. Generation reports its real phases through
``st.status`` (requires the optional ``progress`` callback on
``src.one_click.run_one_click`` - see IMPLEMENTATION.md §6; pure addition).
"""
from __future__ import annotations

import html
import logging
from typing import Dict, List

import streamlit as st

from config.custom_dqr_catalog import get_available_custom_dqr_rules
from config.domains import DOMAINS, get_active_project_filter, get_domain
from src.one_click import ONE_CLICK_SUMMARY_KEY, OneClickError, run_one_click
from ui.step_06._export import _build_rowscores_csv
from utils.session_state import (
    get_planview_filter,
    get_row_limit,
    goto,
    prev_step,
    restart_app,
    set_domain,
)
from utils.ui_components import (
    badge,
    callout,
    code_chip,
    page_header,
    render_choice_card,
    render_nav_footer,
    section_title,
)

logger = logging.getLogger(__name__)


def _rule_counts_for(systems: List[str]) -> Dict[str, int]:
    return {code: len(get_available_custom_dqr_rules(code)) for code in systems}


def _render_domain_picker() -> str | None:
    section_title(1, "Domain")
    active = st.session_state.get("domain")
    cols = st.columns(len(DOMAINS), gap="medium")
    for (code, domain), col in zip(DOMAINS.items(), cols):
        with col:
            if render_choice_card(
                accent=domain.accent, icon=domain.icon,
                title=domain.name, code=" · ".join(domain.system_codes) or domain.code.upper(),
                description=domain.description,
                placeholder=getattr(domain, "placeholder", False),
                selected=(code == active), multi=False,
                select_label=f"Select {domain.name}",
                select_key=f"oneclick_domain_{code}",
            ):
                set_domain(code)
                st.rerun()
    return active


def _render_system_picker(domain_code: str) -> List[str]:
    section_title(2, "Systems", "One-click scores with Custom DQRs only")
    domain = get_domain(domain_code)
    systems = domain.systems
    if not systems:
        callout("This domain has no systems registered.", "warn")
        return []
    rule_counts = _rule_counts_for(list(systems))
    selected: List[str] = []
    cols = st.columns(len(systems), gap="medium")
    for (code, system), col in zip(systems.items(), cols):
        count = rule_counts.get(code, 0)
        with col:
            def _rule_badge(cnt=count) -> None:
                st.markdown(
                    badge(f"{cnt} custom rules" if cnt else "No custom rules", "good" if cnt else "warn"),
                    unsafe_allow_html=True,
                )
            if render_choice_card(
                accent="", icon="", title=system.name, code=code,
                description=system.description,
                selected=(code in st.session_state.get("selected_systems", [])),
                multi=True, select_label=f"Include {code}",
                select_key=f"oneclick_sys_{code}", before_control=_rule_badge,
                disabled=(count == 0),
                disabled_reason="Skipped in One-click: no Custom DQRs. Use Step-by-step to apply Standard DQRs.",
            ):
                selected.append(code)
    return selected


def _run_one_click(domain_code: str, systems: List[str]) -> None:
    with st.status("Generating scorecards…", expanded=True) as status:
        def progress(phase: str, detail: str = "") -> None:
            status.update(label=f"Generating · {phase}")
            status.write(f"{phase}" + (f" · {detail}" if detail else ""))

        try:
            try:
                result = run_one_click(
                    domain_code, systems,
                    row_limit=get_row_limit(),
                    planview_filter=get_planview_filter() or None,
                    filter_column=get_active_project_filter().column,
                    progress=progress,
                )
            except TypeError:  # run_one_click without the progress kwarg yet
                result = run_one_click(
                    domain_code, systems,
                    row_limit=get_row_limit(),
                    planview_filter=get_planview_filter() or None,
                    filter_column=get_active_project_filter().column,
                )
        except OneClickError as exc:
            status.update(label="Generation failed", state="error")
            st.error(str(exc))
            return

        if not result.products:
            status.update(label="Nothing could be scored", state="error")
            reasons = "\n".join(f"- **{c}**: {r}" for c, r in result.skipped.items())
            st.error("None of the selected systems could be scored.\n\n" + (reasons or "- No scorable system.")
                     + "\n\nPick different systems, widen the project filter, or use Step-by-step.")
            return

        progress("Preparing exports", "CSV · JSON")
        csv_errors: Dict[str, str] = {}
        for code, product in result.products.items():
            try:
                _build_rowscores_csv(product.data_product, product.scorecard, product.config)
            except Exception as exc:  # never block the (valid) scorecards on export issues
                logger.warning("One-click CSV build failed for %s", code, exc_info=True)
                csv_errors[code] = str(exc)
        status.update(label="Scorecards ready", state="complete", expanded=False)

    st.session_state.selected_systems = result.scored_systems
    st.session_state.data_products = result.data_products
    st.session_state.configs = result.configs
    st.session_state.scorecards = result.scorecards
    st.session_state[ONE_CLICK_SUMMARY_KEY] = {
        "scored": result.scored_systems, "skipped": dict(result.skipped),
        "warnings": list(result.warnings), "csv_errors": csv_errors,
    }
    goto("dashboard")


def _render_run_plan(domain_code: str | None, systems: List[str]) -> None:
    from config.settings import SETTINGS

    with st.container(border=True):
        st.markdown('<div style="font-weight:600;font-size:14px;margin-bottom:8px">Run plan</div>',
                    unsafe_allow_html=True)
        if not domain_code:
            callout("Pick a domain to continue.", "info")
            st.button("Generate scorecards", type="primary", disabled=True, use_container_width=True,
                      key="oneclick_generate")
            return
        domain = get_domain(domain_code)
        rule_counts = _rule_counts_for(systems)
        with_rules = [c for c in systems if rule_counts.get(c, 0) > 0]
        without_rules = [c for c in systems if rule_counts.get(c, 0) == 0]
        n_rules = sum(rule_counts.get(c, 0) for c in with_rules)
        row_limit = get_row_limit()
        dataset = f"Sample ≤ {row_limit:,} rows/table" if row_limit else "Full dataset"
        pv = get_planview_filter()
        filt = f"{len(pv)} project filter(s)" if pv else "All projects"
        chosen = " · ".join(code_chip(c) for c in systems) if systems else "<i>no system yet</i>"
        st.markdown(
            f'<div class="dq-choice-grid" style="margin-bottom:12px">'
            f'<span class="k">You chose</span><span>{html.escape(domain.name)} · {chosen}</span>'
            f'<span class="k">Automated</span><span>CDEs required by rules · {n_rules} Custom DQRs at defaults · Equal weights · CSV + JSON exports</span>'
            f'<span class="k">Dataset</span><span>{dataset} · {filt}</span></div>',
            unsafe_allow_html=True,
        )
        if without_rules:
            callout(f"<b>{', '.join(without_rules)} will be skipped</b> — no Custom DQRs configured.", "warn")
        if not systems:
            callout("Select at least one system.", "info")
        elif not with_rules:
            callout("None of the selected systems has Custom DQRs. Pick another system or use Step-by-step.", "err")
        enabled = bool(with_rules)
        label = f"Generate scorecards for {len(with_rules)} system{'s' if len(with_rules) != 1 else ''}" if enabled else "Generate scorecards"
        if st.button(label, type="primary", disabled=not enabled, use_container_width=True,
                     key="oneclick_generate"):
            _run_one_click(domain_code, list(systems))


def render() -> None:
    page_header("One-click", "Pick a domain and systems",
                "Everything else runs with curated defaults and lands on the Scorecard.")
    left, right = st.columns([2.2, 1], gap="large")
    with left:
        domain_code = _render_domain_picker()
        selected: List[str] = []
        if domain_code:
            selected = _render_system_picker(domain_code)
    with right:
        _render_run_plan(domain_code, selected)
    _nav()


def _nav() -> None:
    render_nav_footer(
        show_next=False, next_message="", blocked_message=None,
        on_back=prev_step, on_next=lambda: None, on_restart=restart_app,
        next_button_label="Generate from the Run plan →",
        restart_key="restart_confirm_oneclick",
    )
