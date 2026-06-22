"""
Step 0: Domain selection.

The user picks the *domain* of data they want to assess (Cost Estimate,
Quality, ...). The chosen domain swaps the systems / tables, the CDE
suggestions, the standard and custom DQR catalogs, and the metadata
shown throughout the rest of the workflow.

This is the only step that runs before the historical Step 1; every
later step assumes ``st.session_state.domain`` is populated and returns
the user here when it isn't.

Visual identity intentionally mirrors Step 1 (system selection) so the
two screens read as parts of the same workflow rather than a bolted-on
prelude: same bordered card, same accent strip, same chip-style step
pill, same Next-button right-alignment.
"""
from __future__ import annotations

import html

import streamlit as st

from config.domains import DOMAINS
from utils.helpers import section_header
from utils.session_state import next_step, prev_step, restart_app, set_domain
from utils.ui_components import render_choice_card, render_restart_button

_DESC_MIN_HEIGHT = 8.0  # em - keeps each card's Select button aligned


def _systems_row(domain) -> None:
    codes_html = " ".join(
        f"<code>{html.escape(c)}</code>" for c in domain.system_codes
    )
    st.markdown(
        f"""
        <div class="domain-systems">
            <b>Systems:</b> {codes_html or '<i>none yet</i>'}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render() -> None:

    st.markdown(
        '<div class="step-pill">Step 0 · Domain Selection</div>',
        unsafe_allow_html=True,
    )
    section_header(
        "Step 0 - Pick a data domain",
        "Choose which domain of data this DQ workflow will assess. The "
        "selection swaps the tables, CDEs, standard and custom DQR "
        "catalogs, and the per-step copy throughout the rest of the app.",
    )

    cols = st.columns(len(DOMAINS), gap="medium")
    for (code, domain), col in zip(DOMAINS.items(), cols):
        is_active = (code == st.session_state.get("domain"))
        with col:
            # Shared renderer (utils.ui_components). The active domain shows
            # the header state badge + a primary Select button; clicking the
            # button (even on the active one) is harmless thanks to
            # ``set_domain``'s idempotence. The "Systems:" row is this screen's
            # before-control slot.
            if render_choice_card(
                accent=domain.accent,
                icon=domain.icon,
                title=domain.name,
                code=domain.code.upper(),
                subtitle=domain.subtitle,
                description=domain.description,
                desc_min_height_em=_DESC_MIN_HEIGHT,
                placeholder=domain.placeholder,
                selected=is_active,
                multi=False,
                select_label=f"Select {domain.name}",
                select_key=f"domain_pick_{code}",
                before_control=lambda d=domain: _systems_row(d),
            ):
                set_domain(code)
                st.rerun()

    st.markdown("---")

    # Confirmation summary
    picked_code = st.session_state.get("domain")
    if picked_code:
        picked = DOMAINS[picked_code]
        placeholder_note = (
            " · <i>Placeholder schema - real tables and rules pending.</i>"
            if picked.placeholder
            else ""
        )
        st.markdown(
            f"""
            <div class="sel-summary">
                <div class="sel-summary-title">
                    ✓ Active domain
                </div>
                <div>
                    {html.escape(picked.icon)} <b>{html.escape(picked.name)}</b>
                    &nbsp;·&nbsp;
                    <span style="color: rgba(49,51,63,0.7); font-size: 0.9em;">
                        {html.escape(picked.subtitle)}{placeholder_note}
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="empty-notice">
                ⚠️ <b>Pick a domain above</b> to enable the rest of the workflow.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Navigation. Step 0 now sits *after* the mode picker (mode_selection),
    # so it ships Back (return to the mode picker to switch One-click / AS-IS)
    # and Restart, matching the One-click step's nav row.
    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
    c_back, c_restart, c_mid, c_next = st.columns([1, 1, 4, 1])
    with c_back:
        if st.button("⬅ Back", use_container_width=True,
                     help="Return to the mode picker (One-click / Step-by-step)."):
            prev_step()
    with c_restart:
        render_restart_button(restart_app, key="restart_confirm_domain")
    with c_mid:
        if picked_code:
            st.markdown(
                "<div style='text-align: center; padding-top: 0.55em; "
                "color: rgba(49,51,63,0.6); font-size: 0.85em;'>"
                "Next step → select systems within the chosen domain."
                "</div>",
                unsafe_allow_html=True,
            )
    with c_next:
        if st.button(
            "Next ➡",
            type="primary",
            disabled=picked_code is None,
            use_container_width=True,
        ):
            next_step()
