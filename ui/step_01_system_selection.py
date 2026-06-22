"""
Step 1: System selection.

The user chooses which systems (ADR, ACCE, EPT) to analyze. Each system
shows which tables compose it so the user understands what will be joined.

Layout notes:
- Cards have NO fixed height - they expand to fit the content (no scrollbar).
- Descriptions (system-level and per-table) are rendered inside HTML divs with
  a `min-height`, so that cards of different text length stay visually aligned.
  Shorter descriptions simply leave blank space at the bottom of their block
"""
from __future__ import annotations

import html

import streamlit as st

from config.domains import get_active_domain
from config.settings import SETTINGS
from utils.helpers import section_header
from utils.session_state import next_step, prev_step, restart_app
from utils.ui_components import render_choice_card, render_restart_button

# Min-Heights (in em units so they scale with font size).
# Tuned to comfortably fit the longest description in each category
_DESC_MIN_HEIGHT = 8.0  # system-level description
_TABLE_DESC_MIN_HEIGHT_EM = 3.2  # per-table description

# Fallback icon / accent for systems the active domain doesn't supply
# visuals for - cosmetic safety net so a freshly-registered domain
# always renders something rather than blowing up the card layout.
_DEFAULT_ICON = "🧩"
_DEFAULT_ACCENT = "#6366f1"


def _system_icon(code: str) -> str:
    return get_active_domain().system_icons.get(code, _DEFAULT_ICON)


def _system_accent(code: str) -> str:
    return get_active_domain().system_accents.get(code, _DEFAULT_ACCENT)


def _table_row(name: str, description: str, is_primary: bool) -> None:
    """One table entry inside expander: name (with optional Primary badge)
    + description in a fixed min-height block so sibling rows align."""
    badge = '<span class="primary-badge">PRIMARY</span>' if is_primary else ""
    st.markdown(
        f"""
        <div class="table-row">
            <div style="font-weight: 600; font-size: 0.9em; margin-bottom: 0.15em; color: #0f172a;">
                {html.escape(name)}{badge}
            </div>
            <div style="
                min-height: {_TABLE_DESC_MIN_HEIGHT_EM}em;
                color: rgba(49, 51, 63, 0.7);
                font-size: 0.82em;
                line-height: 1.45;
            ">{html.escape(description)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _connection_banner() -> None:
    """Show whether we're in mock or live (Snowflake) mode, with a
    consistent compact look."""
    if SETTINGS.is_mock:
        st.info(
            "🧪 Running in **mock** mode (synthetic data). "
            "Edit `.env` to connect to Snowflake."
        )
    else:
        # Domain-level override wins (e.g. Quality reads from
        # INGESTION_DB.GP_QUALITY regardless of .env); otherwise the
        # banner reflects the global Snowflake credentials.
        domain = get_active_domain()
        database = domain.snowflake_database or SETTINGS.sf_database
        schema = domain.snowflake_schema or SETTINGS.sf_schema
        st.success(
            f"🔌 Connected to **{database}.{schema}** on Snowflake."
        )


def _selection_summary(selected: list[str], total: int) -> None:
    """Render the selection summary (chips for picked systems, or an
    empty-state hint)."""
    if selected:
        chips_html = "".join(
            f'<span class="sel-chip" style="background: {_system_accent(c)};">'
            f'{_system_icon(c)}&nbsp;&nbsp;{html.escape(c)}</span>'
            for c in selected
        )
        st.markdown(
            f"""
            <div class="sel-summary">
                <div class="sel-summary-title">
                    ✓ {len(selected)} of {total} systems selected
                </div>
                <div>{chips_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="empty-notice">
                ⚠️ <b>No systems selected.</b> Pick at least one system above to continue.
            </div>
            """,
            unsafe_allow_html=True,
        )


def render() -> None:

    domain = get_active_domain()
    domain_systems = domain.systems

    # ── Page intro ───────────────────────────────────────────────────────
    st.markdown(
        f'<div class="step-pill">Step 1 · {html.escape(domain.name)} · System Selection</div>',
        unsafe_allow_html=True,
    )
    section_header(
        "Step 1 - System selection",
        f"Choose the systems you want to analyse within the "
        f"**{html.escape(domain.name)}** domain. For each selected system, "
        "the application will join the tables into a single Data Product.",
    )

    # ── Connection / mode banner ─────────────────────────────────────────
    _connection_banner()

    st.markdown("---")

    # ── System cards ─────────────────────────────────────────────────────
    st.markdown(
        "<div style='font-size: 0.88em; color: rgba(49,51,63,0.7); "
        "margin-bottom: 0.6em;'>"
        "🧭 Select one or more systems. Expand <b>Tables</b> to preview "
        "what gets joined into each Data Product."
        "</div>",
        unsafe_allow_html=True,
    )

    if not domain_systems:
        st.markdown(
            """
            <div class="empty-notice">
                ⚠️ <b>No systems registered for this domain yet.</b>
                Register at least one system in <code>config/domains.py</code>
                to enable this step.
            </div>
            """,
            unsafe_allow_html=True,
        )
        _nav([], total=0)
        return

    selected = []
    cols = st.columns(len(domain_systems), gap="medium")

    for (code, system), col in zip(domain_systems.items(), cols):
        with col:
            # Tables expander - this screen's after-control slot. Opens on
            # demand; height varies with table count by design (1 for EPT vs
            # 3 for ADR/ACCE). Default args bind the loop variables.
            def _tables_expander(sys=system, c=code) -> None:
                with st.expander(
                    f"📋 Tables in {c} ({len(sys.tables)})", expanded=False
                ):
                    for t in sys.tables:
                        _table_row(
                            name=t.name,
                            description=t.description,
                            is_primary=t.is_primary,
                        )

            # Shared renderer (utils.ui_components): multi-select checkbox
            # control, with the Tables expander rendered after it.
            if render_choice_card(
                accent=_system_accent(code),
                icon=_system_icon(code),
                title=system.name,
                code=code,
                description=system.description,
                desc_min_height_em=_DESC_MIN_HEIGHT,
                selected=(code in st.session_state.selected_systems),
                multi=True,
                select_label=f"Select {system.name}",
                select_key=f"chk_system_{code}",
                after_control=_tables_expander,
            ):
                selected.append(code)

    st.markdown("---")

    # ── Selection summary ────────────────────────────────────────────────
    _selection_summary(selected, total=len(domain_systems))

    _nav(selected, total=len(domain_systems))


def _nav(selected: list[str], total: int) -> None:
    """Render the Back / Restart / Next row used at the bottom of Step 1.

    Step 1 now sits *after* Step 0 (domain selection), so it ships a
    Back button that returns the user to the domain picker - useful for
    re-routing into Quality after starting Cost Estimate by mistake.
    """
    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)
    c_back, c_restart, c_mid, c_next = st.columns([1, 1, 4, 1])
    with c_back:
        if st.button("⬅ Back", use_container_width=True,
                     help="Return to Step 0 - change the active domain."):
            prev_step()
    with c_restart:
        render_restart_button(restart_app, key="restart_confirm_systems")
    with c_mid:
        if selected:
            st.markdown(
                "<div style='text-align: center; padding-top: 0.55em; "
                "color: rgba(49,51,63,0.6); font-size: 0.85em;'>"
                "Next step → configure data quality rules for the selected systems."
                "</div>",
                unsafe_allow_html=True,
            )
    with c_next:
        if st.button(
            "Next ➡",
            type="primary",
            disabled=(total == 0 or len(selected) == 0),
            use_container_width=True,
            key="step1_next",
        ):
            st.session_state.selected_systems = selected
            # Clear downstream state when selection changes
            st.session_state.data_products = {}
            st.session_state.configs = {}
            st.session_state.scorecards = {}
            next_step()
