"""
Step 5: Weight assignment.

For each Data Product the user distributes weights at two levels:

1. **Source-level weights** (read-only summary from Step 4): Standard /
   Custom DQR percentages that combine to 100% in the final score.
2. **Rule-level weights**, scoped per source: Standard rule weights must sum
   to 100% within the Standard source; Custom rule weights must sum to 100%
   within the Custom source. The "Distribute equally" buttons split 100
   evenly.

Live indicators show the running totals; the "Generate Scorecard" button is
gated until every active source's rules sum to 100%.
"""
from __future__ import annotations

import html
from typing import List

import streamlit as st

from config.custom_dqr_catalog import get_available_custom_dqr_rules
from config.dqr_sources import SOURCE_CUSTOM, SOURCE_LABELS, SOURCE_STANDARD
from src.models import CustomDQRAssignment, DQRAssignment
from utils.helpers import distribute_equally, section_header
from utils.session_state import next_step, prev_step, restart_app
from utils.ui_components import render_nav_footer

EPS = 0.5  # tolerance for the 100% sum check

_SYSTEM_ICONS = {"ADR": "📊", "ACCE": "📈", "EPT": "🗂️"}
_SYSTEM_ACCENTS = {"ADR": "#3b82f6", "ACCE": "#8b5cf6", "EPT": "#0ea5e9"}
_DEFAULT_ACCENT = "#6366f1"


def _dp_card_header(system_code: str) -> None:
    """Render the DP card header with icon + accent bar. Preserves the
    ``{system_code}_DATA_PRODUCT`` naming used previously."""
    icon = _SYSTEM_ICONS.get(system_code, "📦")
    accent = _SYSTEM_ACCENTS.get(system_code, _DEFAULT_ACCENT)
    name = f"{system_code}_DATA_PRODUCT"
    st.markdown(
        f"""
        <div class="dp-card-accent" style="background: {accent};"></div>
        <div class="dp-card-title">
            <span class="dp-icon">{icon}</span>
            <span class="dp-name">{html.escape(name)}</span>
            <span class="dp-code">{html.escape(system_code)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_section_head(title: str, badge: str, badge_class: str,
                         button_label: str, button_key: str) -> bool:
    """Render a "Standard rules" / "Custom rules" section header with the
    Distribute-equally button aligned to the right. Returns True when the
    button was clicked on this render."""
    head_l, head_r = st.columns([3, 1])
    with head_l:
        st.markdown(
            f"""
            <div class="sec-head">
                <div>
                    <span class="sec-title">{html.escape(title)}</span>
                    <span class="sec-badge {badge_class}">{html.escape(badge)}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with head_r:
        return st.button(
            button_label,
            key=button_key,
            use_container_width=True,
        )


def _render_weight_progress(total: float) -> None:
    """Visual progress bar towards 100%, purely decorative; the underlying
    `st.success`/`st.warning`/`st.error` (rendered by the caller) remains
    the authoritative signal."""
    pct = max(0.0, min(100.0, total))
    delta = total - 100.0
    if abs(delta) <= EPS:
        klass = "ok"
    elif total > 100.0:
        klass = "over"
    else:
        klass = "warn"
    st.markdown(
        f"""
        <div class="pct-track">
            <div class="pct-fill {klass}" style="width: {pct:.1f}%;"></div>
        </div>
        <div class="pct-label">
            <span>0%</span>
            <span><b>{total:.2f}%</b> / 100%</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_weight_table_header() -> None:
    st.markdown(
        """
        <div class="w-col-head">
            <div class="col-a">CDE / Rule</div>
            <div class="col-b">Dimension / Name</div>
            <div class="col-c">Weight (%)</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_standard_weights(system_code: str, cfg) -> float:
    assignments: List[DQRAssignment] = cfg.assignments
    if not assignments:
        st.caption("No Standard DQRs defined for this Data Product.")
        return 0.0

    clicked = _render_section_head(
        title="Standard rules",
        badge=f"{len(assignments)} rule(s)",
        badge_class="std",
        button_label="⚖ Distribute equally",
        button_key=f"equal_std_{system_code}",
    )
    if clicked:
        eq = distribute_equally(len(assignments))
        for a, w in zip(assignments, eq):
            a.weight = w
            st.session_state[f"w_{system_code}_{a.rule_id}"] = w
        st.rerun()

    keys = [f"w_{system_code}_{a.rule_id}" for a in assignments]
    for a, key in zip(assignments, keys):
        if key not in st.session_state:
            st.session_state[key] = float(a.weight)

    _render_weight_table_header()

    total = 0.0
    for a, key in zip(assignments, keys):
        others_sum = sum(float(st.session_state[k]) for k in keys if k != key)
        max_allowed = round(max(0.0, min(100.0, 100.0 - others_sum)), 2)
        if float(st.session_state[key]) > max_allowed:
            st.session_state[key] = max_allowed

        col1, col2, col3 = st.columns([3, 3, 2])
        with col1:
            st.markdown(f"`{a.cde_column}`")
        with col2:
            st.markdown(f"**{a.dimension}**")
        with col3:
            st.number_input(
                f"Weight (%) for {a.cde_column} · {a.dimension}",
                min_value=0.0, max_value=max_allowed, step=1.0,
                key=key,
                label_visibility="collapsed",
            )
        val = float(st.session_state[key])
        a.weight = val
        total += val

    return total


def _render_custom_weights(system_code: str, cfg) -> float:
    assignments: List[CustomDQRAssignment] = cfg.custom_assignments
    if not assignments:
        st.caption("No Custom DQRs selected for this Data Product.")
        return 0.0

    catalog = {r.id: r for r in get_available_custom_dqr_rules(system_code)}

    # Custom rule weights start blank (0%) so the user explicitly assigns
    # them, same UX as the Standard rules section. Use the "Distribute
    # equally" button below for a one-click 100% split across the selected
    # rules.

    clicked = _render_section_head(
        title="Custom rules",
        badge=f"{len(assignments)} rule(s)",
        badge_class="cus",
        button_label="⚖ Distribute equally",
        button_key=f"equal_cus_{system_code}",
    )
    if clicked:
        eq = distribute_equally(len(assignments))
        for a, w in zip(assignments, eq):
            a.weight = w
            st.session_state[f"wc_{system_code}_{a.rule_id}"] = w
        st.rerun()

    keys = [f"wc_{system_code}_{a.rule_id}" for a in assignments]
    for a, key in zip(assignments, keys):
        if key not in st.session_state:
            st.session_state[key] = float(a.weight)

    _render_weight_table_header()

    total = 0.0
    for a, key in zip(assignments, keys):
        others_sum = sum(float(st.session_state[k]) for k in keys if k != key)
        max_allowed = round(max(0.0, min(100.0, 100.0 - others_sum)), 2)
        if float(st.session_state[key]) > max_allowed:
            st.session_state[key] = max_allowed

        rule_def = catalog.get(a.rule_id)
        rule_name = rule_def.name if rule_def is not None else a.rule_id

        col1, col2, col3 = st.columns([3, 3, 2])
        with col1:
            st.markdown(f"`{a.rule_id}`")
        with col2:
            st.markdown(f"**{rule_name}**")
        with col3:
            st.number_input(
                f"Weight (%) for {rule_name}",
                min_value=0.0, max_value=max_allowed, step=1.0,
                key=key,
                label_visibility="collapsed",
            )
        val = float(st.session_state[key])
        a.weight = val
        total += val

    return total


def _render_source_summary(cfg) -> None:
    """Source weights from Step 4 - rendered as a mini-card with an inline
    proportion bar when both sources are active, or a single label when
    only one is. Numbers are identical to the original text rendering."""
    sources = cfg.effective_dqr_sources()
    weights = cfg.effective_source_weights()

    # Title block (always visible)
    parts = [
        f"<b>{html.escape(SOURCE_LABELS[s])}</b>: {weights.get(s, 0.0):.0f}%"
        for s in sources
    ]
    summary_line = " · ".join(parts)

    bar_html = ""
    if SOURCE_STANDARD in sources and SOURCE_CUSTOM in sources:
        std_w = weights.get(SOURCE_STANDARD, 0.0)
        cus_w = weights.get(SOURCE_CUSTOM, 0.0)
        bar_html = (
            f'<div class="src-bar">'
            f'  <div class="seg-std" style="flex: {std_w};"></div>'
            f'  <div class="seg-cus" style="flex: {cus_w};"></div>'
            f'</div>'
            f'<div class="src-legend">'
            f'  <span><span class="lbl-std">{html.escape(SOURCE_LABELS[SOURCE_STANDARD])}</span>: {std_w:.0f}%</span>'
            f'  <span><span class="lbl-cus">{html.escape(SOURCE_LABELS[SOURCE_CUSTOM])}</span>: {cus_w:.0f}%</span>'
            f'</div>'
        )

    st.markdown(
        f"""
        <div class="src-summary">
            <div class="src-summary-title">📐 Source weights (set in Step 4)</div>
            <div>{summary_line}</div>
            {bar_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
    # Plain-text fallback preserved verbatim - keeps the same information
    # shape the original page emitted via st.markdown.
    st.markdown("**Source weights (set in Step 4):** " + " · ".join(
        f"**{SOURCE_LABELS[s]}**: {weights.get(s, 0.0):.0f}%" for s in sources
    ))


def _render_dp_block(system_code: str, cfg) -> bool:
    """Render Step 5 for one DP. Returns True when all active sources have
    rule-level weights summing to 100% (within tolerance)."""
    sources = cfg.effective_dqr_sources()
    _dp_card_header(system_code)
    _render_source_summary(cfg)
    st.markdown("---")

    valid = True

    if SOURCE_STANDARD in sources:
        std_total = _render_standard_weights(system_code, cfg)
        if cfg.assignments:
            _render_weight_progress(std_total)
            delta = std_total - 100.0
            if abs(delta) <= EPS:
                st.success(f"✅ Standard sum = **{std_total:.2f}%** (OK)")
            elif std_total > 100:  # pragma: no cover - cap prevents this in the UI
                st.error(f"⚠ Standard sum = **{std_total:.2f}%**: reduce by {delta:.2f}%")
                valid = False
            else:
                st.warning(
                    f"⚠ Standard sum = **{std_total:.2f}%**: "
                    f"{-delta:.2f}% still needed."
                )
                valid = False

    if SOURCE_CUSTOM in sources:
        if SOURCE_STANDARD in sources:
            st.markdown("---")
        cus_total = _render_custom_weights(system_code, cfg)
        if cfg.custom_assignments:
            _render_weight_progress(cus_total)
            delta = cus_total - 100.0
            if abs(delta) <= EPS:
                st.success(f"✅ Custom sum = **{cus_total:.2f}%** (OK)")
            elif cus_total > 100:  # pragma: no cover - cap prevents this in the UI
                st.error(f"⚠ Custom sum = **{cus_total:.2f}%**: reduce by {delta:.2f}%")
                valid = False
            else:
                st.warning(
                    f"⚠ Custom sum = **{cus_total:.2f}%**: "
                    f"{-delta:.2f}% still needed."
                )
                valid = False
        else:
            st.warning(
                "Custom DQR source is selected but no rules were chosen in "
                "Step 4.2. Custom score will be 0%."
            )

    return valid


def render() -> None:
    st.markdown('<div class="step-pill">Step 5 · DQR Weights</div>',
                unsafe_allow_html=True)
    section_header(
        "Step 5 - DQR Weights",
        "Assign a weight to each DQR within its source. Each source's "
        "rule-level weights must sum to **100%**. Source-level weights were "
        "set in Step 4.",
    )

    configs = st.session_state.configs
    all_valid = True

    st.markdown("---")

    for code, cfg in configs.items():
        if not cfg.assignments and not cfg.custom_assignments:
            continue
        with st.container(border=True):
            ok = _render_dp_block(code, cfg)
            if not ok:
                all_valid = False

    st.markdown("---")
    _nav(show_next=all_valid)


def _nav(show_next: bool = False) -> None:
    render_nav_footer(
        show_next=show_next,
        next_message="Final step → generate and review the Data Quality scorecard.",
        blocked_message=(
            "Each source's rule weights must sum to exactly 100% to continue."
        ),
        next_button_label="Generate Scorecard ➡",
        on_back=prev_step,
        on_next=next_step,
        on_restart=restart_app,
    )
