"""
Step 2: Data Product review.

For each selected system:
- builds the data product (joins tables)
- shows summary (row count, column count, source tables)
- shows a head() preview
"""
from __future__ import annotations

import html

import streamlit as st

from config.domains import get_active_project_filter
from src.data_product_builder import build_multiple
from src.models import DataProductConfig
from src.profiler import profile_dataframe
from src.reference_data import (
    get_reference_dataset_error,
    prefetch_reference_datasets,
    required_reference_datasets_for_systems,
)
from utils.helpers import section_header
from utils.session_state import (
    get_planview_filter,
    get_row_limit,
    next_step,
    prev_step,
    restart_app,
)
from utils.ui_components import render_nav_footer

# Visual identity per system - keeps cards visually consistent with Step 1.
_SYSTEM_ICONS = {
    "ADR": "📊",
    "ACCE": "📈",
    "EPT": "🗂️",
}
_SYSTEM_ACCENTS = {
    "ADR": "#3b82f6",
    "ACCE": "#8b5cf6",
    "EPT": "#0ea5e9",
}
_DEFAULT_ACCENT = "#6366f1"


def _inject_css() -> None:
    """Step-02-local override: keep the smaller metric *value* size.

    All other Step-02 chrome now lives in the consolidated global stylesheet
    (:func:`ui._theme.inject_global_css`). Only ``stMetricValue`` stays scoped
    here - globalising 1.6em would shrink the Dashboard / ML-Lab metric
    numbers, which use Streamlit's default size."""
    st.markdown(
        """
        <style>
            div[data-testid="stMetricValue"] {
                font-size: 1.6em !important;
                font-weight: 700 !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _filter_banner(planview_filter: list[str]) -> None:
    """Render a stylised callout describing the active project filter.

    Wording is sourced from the active domain's ``project_filter`` so
    Quality reads "PROJECT_CODE(s)" while Cost Estimate keeps the
    historical "PLANVIEW_ID(s)" copy.
    """
    project_filter = get_active_project_filter()
    chips = "".join(
        f'<span class="filter-chip">{html.escape(str(p))}</span>'
        for p in planview_filter
    )
    st.markdown(
        f"""
        <div class="filter-banner">
            <div class="filter-title">
                🎯 Project filter active - {len(planview_filter)} {html.escape(project_filter.label)}
            </div>
            <div>{chips}</div>
            <div class="filter-hint">
                Clear it from the sidebar to use all {html.escape(project_filter.pill_plural)}.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _empty_callout(empty_codes: list[str]) -> None:
    """Highlight systems where the project filter matched zero rows."""
    project_filter = get_active_project_filter()
    chips = "".join(
        f'<span class="empty-chip">{_SYSTEM_ICONS.get(c, "🧩")}&nbsp;{html.escape(c)}</span>'
        for c in empty_codes
    )
    st.markdown(
        f"""
        <div class="empty-callout">
            ⚠️ <b>The {html.escape(project_filter.column)} filter matched 0 rows for:</b><br>
            <div style="margin-top: 0.45em;">{chips}</div>
            <div style="margin-top: 0.5em; font-size: 0.88em;">
                Either widen the filter from the sidebar or remove the
                affected system in <b>Step 1</b>.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _dp_card_header(code: str, name: str, source_tables: list[str]) -> None:
    """Render the per-card icon, title, code pill, and source tables row."""
    icon = _SYSTEM_ICONS.get(code, "📦")
    accent = _SYSTEM_ACCENTS.get(code, _DEFAULT_ACCENT)
    sources_html = " ".join(
        f"<code>{html.escape(t)}</code>" for t in source_tables
    )
    st.markdown(
        f"""
        <div class="dp-card-accent" style="background: {accent};"></div>
        <div class="dp-card-title">
            <span class="dp-icon">{icon}</span>
            <span class="dp-name">{html.escape(name)}</span>
            <span class="dp-code">{html.escape(code)}</span>
        </div>
        <div class="dp-source"><b>Source tables:</b> {sources_html}</div>
        """,
        unsafe_allow_html=True,
    )


def render() -> None:
    _inject_css()

    # ── Intro ────────────────────────────────────────────────────────────
    st.markdown('<div class="step-pill">Step 2 · Data Product Review</div>',
                unsafe_allow_html=True)
    section_header(
        "Step 2 - Data Product review",
        "ADR and ACCE: their 4 tables were joined via ROW_ID into a single Data Product. "
        "EPT: single table ONSHORE_CETDATA used as-is. "
        "Check dimensions and columns before proceeding.",
    )

    systems = st.session_state.selected_systems
    if not systems:
        st.error("🚫 No system selected. Go back to step 1.")
        _nav()
        return

    # ── Filter banner ────────────────────────────────────────────────────
    planview_filter = get_planview_filter()
    if planview_filter:
        _filter_banner(planview_filter)

    # Build if not already built (cached on session_state)
    if not st.session_state.data_products or set(st.session_state.data_products) != set(systems):
        row_limit = get_row_limit()
        filter_column = get_active_project_filter().column
        label = f"(sample ≤ {row_limit:,} rows/table)" if row_limit else "(full dataset)"
        with st.spinner(f"⚙️ Building Data Products from source tables {label}..."):
            try:
                dps = build_multiple(
                    systems,
                    row_limit=row_limit,
                    planview_ids=planview_filter or None,
                    filter_column=filter_column,
                )
                for code, dp in dps.items():
                    dp.profiles = profile_dataframe(dp.df)
                st.session_state.data_products = dps
                # Initialize empty configs
                st.session_state.configs = {
                    code: DataProductConfig(system_code=code) for code in systems
                }
            except Exception as e:
                st.error(f"❌ Failed to build data products: {e}")
                _nav()
                return
        # If the filter matched zero rows in any system, surface it now -
        # the downstream steps need at least one row to profile / score.
        empty = [code for code, dp in st.session_state.data_products.items() if dp.row_count == 0]
        if empty:
            _empty_callout(empty)

        # Eager-load reference datasets for the selected systems' custom
        # rules. Caching them here means Step 6 (and any dashboard
        # re-render, e.g. on Restart) hits the cache instead of opening a
        # fresh Snowflake connection.
        ref_names = required_reference_datasets_for_systems(systems)
        if ref_names:
            with st.spinner(
                f"📚 Loading reference dataset(s): {', '.join(ref_names)}..."
            ):
                prefetch_reference_datasets(ref_names)

    # ── Reference-dataset errors (grouped, less noisy) ───────────────────
    # Surface any reference-dataset load errors so the user knows up-front
    # which Custom rules will be marked "Not evaluated" in Step 6.
    ref_errors: list[tuple[str, str]] = []
    for ref_name in required_reference_datasets_for_systems(systems):
        err = get_reference_dataset_error(ref_name)
        if err:
            ref_errors.append((ref_name, err))
    if ref_errors:
        with st.expander(
            f"⚠️ {len(ref_errors)} reference dataset(s) could not be loaded - "
            "click for details",
            expanded=False,
        ):
            for ref_name, err in ref_errors:
                st.warning(
                    f"Reference dataset `{ref_name}` could not be loaded: {err}. "
                    "Custom rules depending on it will be marked **Not evaluated** "
                    "in Step 6."
                )

    st.markdown("---")
    st.markdown(
        "<div style='font-size: 0.88em; color: rgba(49,51,63,0.7); "
        "margin-bottom: 0.6em;'>"
        "📦 Review each Data Product below. Expand <b>Preview</b> to inspect "
        "the first rows before configuring rules in the next step."
        "</div>",
        unsafe_allow_html=True,
    )

    # ── Data Product cards ───────────────────────────────────────────────
    for code in systems:
        dp = st.session_state.data_products[code]
        with st.container(border=True):
            # Header (icon, name, code pill, sources)
            _dp_card_header(code, dp.name, list(dp.source_tables))

            # Metrics row, three side-by-side cards with consistent labels.
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric("Rows", f"{dp.row_count:,}")
            with m2:
                st.metric("Columns", dp.column_count)
            with m3:
                st.metric("Tables", len(dp.source_tables))

            # Preview expander
            with st.expander("👁 Preview (first 10 rows)", expanded=False):
                st.caption(
                    "Read-only sample of the joined Data Product. "
                    "Full data is used for profiling and scoring downstream."
                )
                st.dataframe(dp.df.head(10), use_container_width=True, height=300)

    st.markdown("---")
    _nav(show_next=True)


def _nav(show_next: bool = False) -> None:
    render_nav_footer(
        show_next=show_next,
        next_message="Next step → configure data quality rules for each Data Product.",
        on_back=prev_step,
        on_next=next_step,
        on_restart=restart_app,
    )
