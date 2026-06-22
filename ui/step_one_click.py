"""
One-click flow: domain + systems, then full automation.

The single working step of One-click mode. The user makes exactly two
choices - the domain and the systems to include - and presses **Generate**.
From there :func:`src.one_click.run_one_click` reproduces the whole Step-by-step
workflow with default settings (custom rules only, required CDEs, default
options, equal weights), computes the scorecards, validates the CSV export,
stores everything in ``session_state`` and lands the user on the dashboard.

No further interaction is required unless a blocking validation issue
arises (no domain, no system, no applicable custom rules, or a generation
failure), in which case the user stays here with a clear message.
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
from utils.helpers import section_header
from utils.session_state import (
    get_planview_filter,
    get_row_limit,
    goto,
    prev_step,
    restart_app,
    set_domain,
)
from utils.ui_components import render_choice_card, render_restart_button

logger = logging.getLogger(__name__)

_DEFAULT_ACCENT = "#6366f1"
_OC_DESC_MIN_HEIGHT = 4.2  # em - One-click cards are more compact than Steps 0/1


def _inject_css() -> None:
    """One-click-local override: the amber theme on top of the global sheet.

    Shared chrome (cards, buttons, .sel-summary, .empty-notice, .card-accent)
    now comes from :func:`ui._theme.inject_global_css`; only the amber
    ``.step-pill`` / ``.sel-chip`` re-theme and the One-click-specific
    ``.oc-*`` classes live here."""
    st.markdown(
        """
        <style>
            .step-pill { background: rgba(245, 158, 11, 0.14); color: #b45309; }
            .sel-chip { background: rgba(22, 163, 74, 0.12); color: #14532d; }
            .oc-rulecount {
                display: inline-block; padding: 0.12em 0.55em; border-radius: 6px;
                font-size: 0.76em; font-weight: 700;
            }
            .oc-rulecount.has { background: rgba(22, 163, 74, 0.12); color: #166534; }
            .oc-rulecount.none { background: rgba(234, 179, 8, 0.18); color: #854d0e; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Domain picker
# ---------------------------------------------------------------------------

def _render_domain_picker() -> str | None:
    """Render the domain cards and return the active domain code (or None).

    Picking a (different) domain calls ``set_domain``, which resets the
    downstream system selection so the system checkboxes start clean.
    """
    st.markdown("#### 1 · Domain")
    active = st.session_state.get("domain")
    cols = st.columns(len(DOMAINS), gap="medium")
    for (code, domain), col in zip(DOMAINS.items(), cols):
        is_active = code == active
        with col:
            # Shared renderer - same card chrome as the Step-by-step domain
            # picker. One-click cards are more compact (smaller description
            # min-height) and omit the systems-row.
            if render_choice_card(
                accent=domain.accent,
                icon=domain.icon,
                title=domain.name,
                code=domain.code.upper(),
                subtitle=domain.subtitle,
                description=domain.description,
                desc_min_height_em=_OC_DESC_MIN_HEIGHT,
                placeholder=getattr(domain, "placeholder", False),
                selected=is_active,
                multi=False,
                select_label=f"Select {domain.name}",
                select_key=f"oneclick_domain_{code}",
            ):
                set_domain(code)
                st.rerun()
    return active


# ---------------------------------------------------------------------------
# System picker
# ---------------------------------------------------------------------------

def _rule_counts_for(systems: List[str]) -> Dict[str, int]:
    """Return ``{system_code: number_of_custom_rules}`` for the active domain.

    Used to flag systems that have no applicable Custom DQRs (One-click is
    custom-only, so those systems can't be scored).
    """
    return {code: len(get_available_custom_dqr_rules(code)) for code in systems}


def _render_system_picker(domain_code: str) -> List[str]:
    """Render the system checkboxes for ``domain_code`` and return the
    selected system codes."""
    st.markdown("#### 2 · Systems")
    domain = get_domain(domain_code)
    systems = domain.systems
    if not systems:
        st.markdown(
            "<div class='empty-notice'>⚠️ This domain has no systems registered.</div>",
            unsafe_allow_html=True,
        )
        return []

    rule_counts = _rule_counts_for(list(systems.keys()))
    selected: List[str] = []
    cols = st.columns(len(systems), gap="medium")
    for (code, system), col in zip(systems.items(), cols):
        with col:
            count = rule_counts.get(code, 0)

            # Rule-count badge - this screen's before-control slot. Flags
            # systems with no applicable Custom DQRs (One-click is custom-only).
            def _rule_count_badge(cnt=count) -> None:
                badge_cls = "has" if cnt else "none"
                badge = f"{cnt} custom rule(s)" if cnt else "no custom rules"
                st.markdown(
                    f'<span class="oc-rulecount {badge_cls}">{badge}</span>',
                    unsafe_allow_html=True,
                )

            if render_choice_card(
                accent=domain.system_accents.get(code, _DEFAULT_ACCENT),
                icon=domain.system_icons.get(code, "🧩"),
                title=system.name,
                code=code,
                description=system.description,
                desc_min_height_em=_OC_DESC_MIN_HEIGHT,
                selected=(code in st.session_state.get("selected_systems", [])),
                multi=True,
                select_label=f"Select {system.name}",
                select_key=f"oneclick_sys_{code}",
                before_control=_rule_count_badge,
            ):
                selected.append(code)
    return selected


# ---------------------------------------------------------------------------
# Generate / run
# ---------------------------------------------------------------------------

def _run_one_click(domain_code: str, systems: List[str]) -> None:
    """Run the One-click pipeline and, on success, store the result in
    session state and navigate to the dashboard. On a blocking failure the
    user stays on this step with an error message."""
    with st.spinner(
        "⚙️ Building data products, applying default Custom DQRs, "
        "distributing weights and scoring..."
    ):
        try:
            result = run_one_click(
                domain_code,
                systems,
                row_limit=get_row_limit(),
                planview_filter=get_planview_filter() or None,
                filter_column=get_active_project_filter().column,
            )
        except OneClickError as exc:
            st.error(f"❌ {exc}")
            return

    if not result.products:
        reasons = "\n".join(
            f"- **{code}**: {reason}" for code, reason in result.skipped.items()
        )
        st.error(
            "❌ One-click could not score any of the selected systems:\n\n"
            + (reasons or "- No scorable system.")
            + "\n\nPick different systems, widen the project filter, or use "
            "Step-by-step mode for full control."
        )
        return

    # Validate the CSV export now (reuses the dashboard's builder) so a
    # generation failure surfaces here rather than only on the download
    # button. Failures are recorded but don't block the (already valid)
    # scorecards from being shown.
    csv_errors: Dict[str, str] = {}
    for code, product in result.products.items():
        try:
            _build_rowscores_csv(
                product.data_product, product.scorecard, product.config
            )
        except Exception as exc:  # defensive: never block on export issues
            logger.warning("One-click CSV build failed for %s", code, exc_info=True)
            csv_errors[code] = str(exc)

    st.session_state.selected_systems = result.scored_systems
    st.session_state.data_products = result.data_products
    st.session_state.configs = result.configs
    st.session_state.scorecards = result.scorecards
    st.session_state[ONE_CLICK_SUMMARY_KEY] = {
        "scored": result.scored_systems,
        "skipped": dict(result.skipped),
        "warnings": list(result.warnings),
        "csv_errors": csv_errors,
    }
    goto("dashboard")


def _render_generate_section(domain_code: str | None, systems: List[str]) -> None:
    """Render the selection summary + Generate button with pre-validation."""
    st.markdown("---")

    if not domain_code:
        st.markdown(
            "<div class='empty-notice'>⚠️ <b>Pick a domain</b> above to continue.</div>",
            unsafe_allow_html=True,
        )
        _generate_button(enabled=False)
        return
    if not systems:
        st.markdown(
            "<div class='empty-notice'>⚠️ <b>Select at least one system</b> "
            "above to continue.</div>",
            unsafe_allow_html=True,
        )
        _generate_button(enabled=False)
        return

    # Pre-validate that at least one selected system has custom rules
    # (One-click is custom-only). All-empty selection is a blocking issue.
    rule_counts = _rule_counts_for(systems)
    with_rules = [c for c in systems if rule_counts.get(c, 0) > 0]
    without_rules = [c for c in systems if rule_counts.get(c, 0) == 0]

    chips = "".join(f'<span class="sel-chip">📦 {html.escape(c)}</span>' for c in systems)
    st.markdown(
        f"""
        <div class="sel-summary">
            <div class="sel-summary-title">✓ Ready to generate · {len(systems)} system(s)</div>
            <div>{chips}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if without_rules:
        st.warning(
            "⚠ No Custom DQRs are configured for: "
            + ", ".join(f"`{c}`" for c in without_rules)
            + ". One-click scores with custom rules only, so "
            + ("these systems will be skipped." if with_rules
               else "there is nothing to score.")
        )

    if not with_rules:
        st.error(
            "❌ None of the selected systems have applicable Custom DQRs. "
            "Pick a system with custom rules, or switch to Step-by-step mode to "
            "apply Standard DQRs manually."
        )
        _generate_button(enabled=False)
        return

    st.markdown(
        "<div style='font-size:0.85em; color:rgba(49,51,63,0.7); margin:0.5em 0;'>"
        "⚡ One click selects the required CDEs, applies every Custom DQR with "
        "its default options, distributes weights equally, scores each Data "
        "Product and prepares the CSV exports - then opens the dashboard."
        "</div>",
        unsafe_allow_html=True,
    )
    if _generate_button(enabled=True):
        _run_one_click(domain_code, [c for c in systems])


def _generate_button(*, enabled: bool) -> bool:
    """Render the primary Generate button. Returns True when clicked."""
    c_l, c_mid, c_r = st.columns([1, 2, 2])
    with c_r:
        return st.button(
            "⚡ Generate scorecards",
            type="primary",
            disabled=not enabled,
            use_container_width=True,
            key="oneclick_generate",
        )


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def _nav() -> None:
    """Back (to mode picker) / Restart row. No Next - Generate is the
    forward action and it jumps straight to the dashboard."""
    st.markdown("<div style='margin-top: 0.6rem;'></div>", unsafe_allow_html=True)
    c_back, c_restart, _ = st.columns([1, 1, 4])
    with c_back:
        if st.button("⬅ Back", use_container_width=True,
                     help="Return to the mode picker."):
            prev_step()
    with c_restart:
        render_restart_button(restart_app, key="restart_confirm_oneclick")


def render() -> None:
    _inject_css()
    st.markdown(
        '<div class="step-pill">One-click · Domain &amp; Systems</div>',
        unsafe_allow_html=True,
    )
    section_header(
        "One-click scorecards",
        "Pick a **domain** and the **systems** to include, then press "
        "**Generate**. The app automatically selects the required CDEs, "
        "applies every Custom DQR at its default settings, distributes "
        "weights equally, scores each Data Product and prepares the CSV "
        "exports - no further steps needed.",
    )

    domain_code = _render_domain_picker()
    selected_systems: List[str] = []
    if domain_code:
        st.markdown("---")
        selected_systems = _render_system_picker(domain_code)

    _render_generate_section(domain_code, selected_systems)
    _nav()
