"""
Step 4: DQR source selection.

For each Data Product the user picks one or both DQR sources:

- **Standard DQR Rules**: the existing catalog of 10 dimensions (sub-step 4.1).
- **Custom DQR Rules**: data-product-specific rules (sub-step 4.2).

When both are selected the user also splits a 100% weight between them via
a slider (the second source is auto-derived as ``100 − first``). When only
one source is selected its weight is locked at 100%.

Selections are persisted in ``DataProductConfig.dqr_sources`` and
``DataProductConfig.source_weights``; downstream steps respect them via
the visibility predicates in :mod:`utils.session_state`.
"""
from __future__ import annotations

import html
from typing import Dict

import streamlit as st

from config.dqr_sources import SOURCE_CUSTOM, SOURCE_LABELS, SOURCE_STANDARD
from utils.helpers import section_header
from utils.session_state import next_step, prev_step, restart_app
from utils.ui_components import render_nav_footer

_SYSTEM_ICONS = {"ADR": "📊", "ACCE": "📈", "EPT": "🗂️"}
_SYSTEM_ACCENTS = {"ADR": "#3b82f6", "ACCE": "#8b5cf6", "EPT": "#0ea5e9"}
_DEFAULT_ACCENT = "#6366f1"


def _dp_card_header(code: str) -> None:
    icon = _SYSTEM_ICONS.get(code, "📦")
    accent = _SYSTEM_ACCENTS.get(code, _DEFAULT_ACCENT)
    st.markdown(
        f"""
        <div class="dp-card-accent" style="background: {accent};"></div>
        <div class="dp-card-title">
            <span class="dp-icon">{icon}</span>
            <span class="dp-name">{html.escape(code)}</span>
            <span class="dp-code">{html.escape(code)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_dp_block(system_code: str, cfg) -> bool:
    """Render the source selection block for one DP. Returns True when the
    DP's selection is valid (≥ 1 source picked AND source weights sum to 100).
    """
    _dp_card_header(system_code)
    current_sources = list(cfg.dqr_sources or [])

    cb_col1, cb_col2 = st.columns(2)
    with cb_col1:
        use_standard = st.checkbox(
            SOURCE_LABELS[SOURCE_STANDARD],
            value=SOURCE_STANDARD in current_sources,
            key=f"src_{system_code}_standard",
            help="Apply the catalog of 10 standard data-quality dimensions to "
                 "the CDEs you selected in Step 3.",
        )
    with cb_col2:
        use_custom = st.checkbox(
            SOURCE_LABELS[SOURCE_CUSTOM],
            value=SOURCE_CUSTOM in current_sources,
            key=f"src_{system_code}_custom",
            help="Apply data-product-specific rules curated for this system.",
        )

    selected = []
    if use_standard:
        selected.append(SOURCE_STANDARD)
    if use_custom:
        selected.append(SOURCE_CUSTOM)
    cfg.dqr_sources = selected

    if not selected:
        st.warning("⚠ Select at least one DQR source to continue.")
        cfg.source_weights = {}
        return False

    weights: Dict[str, float] = {}
    if len(selected) == 1:
        only = selected[0]
        weights = {only: 100.0}
        st.info(f"**{SOURCE_LABELS[only]}** = 100% (only source selected).")
    else:
        st.markdown(
            "<div class='ui-tip'>"
            "⚖️ Both sources selected - split the final score weight between them."
            "</div>",
            unsafe_allow_html=True,
        )
        existing = cfg.source_weights or {}
        try:
            default_std = float(existing.get(SOURCE_STANDARD, 70.0))
        except (TypeError, ValueError):
            # Stored value got corrupted (legacy string, None payload, etc.)
            # Fall back to the slider's neutral 70/30 default so the step
            # always renders even if the persisted config is bad.
            default_std = 70.0
        default_std = min(99.0, max(1.0, default_std))
        std_weight = st.slider(
            f"Weight for {SOURCE_LABELS[SOURCE_STANDARD]} (%)",
            min_value=1, max_value=99,
            value=int(round(default_std)),
            step=1,
            key=f"src_weight_{system_code}_standard",
        )
        cus_weight = 100 - std_weight
        weights = {
            SOURCE_STANDARD: float(std_weight),
            SOURCE_CUSTOM: float(cus_weight),
        }
        # Visual proportion bar + labelled legend (purely cosmetic, mirrors
        # the same numbers as the caption below).
        st.markdown(
            f"""
            <div class="weight-bar">
                <div class="seg-std" style="flex: {std_weight};"></div>
                <div class="seg-cus" style="flex: {cus_weight};"></div>
            </div>
            <div class="weight-legend">
                <span><span class="lbl-std">{html.escape(SOURCE_LABELS[SOURCE_STANDARD])}</span>: {std_weight}%</span>
                <span><span class="lbl-cus">{html.escape(SOURCE_LABELS[SOURCE_CUSTOM])}</span>: {cus_weight}%</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(
            f"**{SOURCE_LABELS[SOURCE_STANDARD]}**: {std_weight}% · "
            f"**{SOURCE_LABELS[SOURCE_CUSTOM]}**: {cus_weight}% · Total: 100%"
        )
    cfg.source_weights = weights
    return True


def render() -> None:
    st.markdown('<div class="step-pill">Step 4 · DQR Sources</div>',
                unsafe_allow_html=True)
    section_header(
        "Step 4 - DQR Sources",
        "Choose which families of Data Quality Rules to apply to each Data "
        "Product. You can pick one or both. When both are selected, set how "
        "the final score should be split between them.",
    )

    configs = st.session_state.configs
    if not configs:
        st.error("🚫 No Data Products configured. Go back to the previous step.")
        _nav(show_next=False)
        return

    st.markdown("---")

    all_valid = True
    for code, cfg in configs.items():
        with st.container(border=True):
            valid = _render_dp_block(code, cfg)
            if not valid:
                all_valid = False

    st.markdown("---")
    _nav(show_next=all_valid)


def _nav(show_next: bool = False) -> None:
    render_nav_footer(
        show_next=show_next,
        next_message=(
            "Next step → configure Data Quality Rules from the selected sources."
        ),
        on_back=prev_step,
        on_next=next_step,
        on_restart=restart_app,
    )
