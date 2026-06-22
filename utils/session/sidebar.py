"""Sidebar rendering: CSS, brand, progress stepper, sample-mode toggle,
project filter, footer.

Pure rendering; never mutates workflow state except through the
``sample_mode`` / ``planview_filter`` widgets which use Streamlit's
``session_state`` for persistence. Cache invalidation on those widget
changes is co-located with the widget itself.
"""
from __future__ import annotations

from typing import List

import streamlit as st

from config.domains import get_active_domain, get_domain
from utils.colors import STATUS_GREEN
from utils.session.navigation import _visible_steps
from utils.session.state import STEP_LABELS


def inject_sidebar_css() -> None:
    """Inject CSS scoped to the sidebar. Safe to call on every render, the
    block is idempotent and Streamlit dedupes <style> tags within a render."""
    st.sidebar.markdown(
        """
        <style>
            /* Sidebar background tint */
            section[data-testid="stSidebar"] > div {
                background: linear-gradient(180deg,
                    rgba(248, 250, 252, 1) 0%,
                    rgba(243, 244, 246, 1) 100%);
            }

            /* Sidebar brand block */
            .sb-brand {
                padding: 0.8em 0.9em;
                border-radius: 12px;
                background: linear-gradient(135deg,
                    rgba(99, 102, 241, 0.95) 0%,
                    rgba(79, 70, 229, 0.95) 100%);
                color: #fff;
                margin-bottom: 0.6em;
                box-shadow: 0 2px 8px rgba(79, 70, 229, 0.18);
            }
            .sb-brand-row {
                display: flex; align-items: center; gap: 0.55em;
            }
            .sb-brand-icon { font-size: 1.6em; line-height: 1; }
            .sb-brand-title {
                font-weight: 800; font-size: 1.05em; letter-spacing: 0.01em;
            }
            .sb-brand-subtitle {
                font-size: 0.72em; opacity: 0.85; letter-spacing: 0.04em;
                text-transform: uppercase; font-weight: 600;
            }
            .sb-brand-tagline {
                font-size: 0.78em; opacity: 0.9; margin-top: 0.4em;
                line-height: 1.3;
            }

            /* Section card wrapping sample-mode / filter blocks */
            .sb-section {
                padding: 0.65em 0.8em;
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.7);
                border: 1px solid rgba(0, 0, 0, 0.05);
                margin-bottom: 0.6em;
            }
            .sb-section-title {
                font-size: 0.72em; font-weight: 700; letter-spacing: 0.06em;
                color: #475569; text-transform: uppercase; margin-bottom: 0.45em;
            }
            .sb-section-title .sec-icon { margin-right: 0.35em; }

            /* Progress stepper */
            .sb-stepper {
                padding: 0.65em 0.8em;
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.75);
                border: 1px solid rgba(0, 0, 0, 0.05);
                margin-bottom: 0.6em;
            }
            .sb-step-count {
                font-size: 0.72em; font-weight: 700; letter-spacing: 0.05em;
                color: #4f46e5; text-transform: uppercase; margin-bottom: 0.55em;
            }
            .sb-step {
                display: flex; align-items: center; gap: 0.55em;
                padding: 0.25em 0; font-size: 0.88em;
                position: relative;
            }
            .sb-step .marker {
                display: inline-flex;
                align-items: center; justify-content: center;
                width: 1.35em; height: 1.35em; border-radius: 999px;
                font-size: 0.7em; font-weight: 700; flex-shrink: 0;
            }
            .sb-step.done    .marker { background: __GREEN__; color: #fff; }
            .sb-step.current .marker { background: #4f46e5; color: #fff;
                box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.22); }
            .sb-step.todo    .marker { background: rgba(15,23,42,0.08); color: #64748b; }
            .sb-step.done    .lbl    { color: #64748b; text-decoration: line-through; opacity: 0.85; }
            .sb-step.current .lbl    { color: #0f172a; font-weight: 700; }
            .sb-step.todo    .lbl    { color: #475569; }

            /* Status pills inside sample-mode / filter sections */
            .sb-pill {
                display: inline-block;
                padding: 0.18em 0.55em;
                border-radius: 999px;
                font-size: 0.74em; font-weight: 600;
                margin-top: 0.3em;
            }
            .sb-pill.ok   { background: rgba(22,163,74,0.12); color: #166534; }
            .sb-pill.warn { background: rgba(234,179,8,0.18); color: #854d0e; }
            .sb-pill.info { background: rgba(59,130,246,0.12); color: #1e40af; }
            .sb-pill.neutral { background: rgba(15,23,42,0.08); color: #475569; }

            /* Footer */
            .sb-footer {
                font-size: 0.74em; color: rgba(49,51,63,0.65);
                line-height: 1.4; padding: 0.4em 0.2em 0 0.2em;
            }
            .sb-version {
                display: inline-block; padding: 0.1em 0.45em;
                border-radius: 5px; background: rgba(15,23,42,0.06);
                color: #475569; font-weight: 700; font-size: 0.75em;
                letter-spacing: 0.04em; margin-left: 0.3em;
            }
        </style>
        """.replace("__GREEN__", STATUS_GREEN),
        unsafe_allow_html=True,
    )


def render_sidebar_brand() -> None:
    """Sidebar header - branded card with logo, title, subtitle and tagline.

    Subtitle and tagline come from the active :class:`DomainDef` so the
    sidebar shadows the domain the user is working in. When no domain
    is picked yet (Step 0) the card stays generic.
    """
    import html as _html

    code = st.session_state.get("domain")
    if code:
        try:
            domain = get_active_domain()
            icon = _html.escape(domain.icon)
            subtitle = _html.escape(domain.sidebar_brand_subtitle)
            tagline = _html.escape(domain.tagline)
        except Exception:
            # Defensive: a corrupted session_state shouldn't take the
            # sidebar down. Fall back to the neutral header below.
            icon, subtitle, tagline = "📊", "Multi-domain", (
                "Build CDE-driven Data Quality scorecards across domains."
            )
    else:
        icon = "📊"
        subtitle = "Pick a domain to start"
        tagline = "Build CDE-driven Data Quality scorecards across domains."

    st.sidebar.markdown(
        f"""
        <div class="sb-brand">
            <div class="sb-brand-row">
                <span class="sb-brand-icon">{icon}</span>
                <div>
                    <div class="sb-brand-title">DQ Scorecard</div>
                    <div class="sb-brand-subtitle">{subtitle}</div>
                </div>
            </div>
            <div class="sb-brand-tagline">
                {tagline}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_progress_sidebar() -> None:
    """Render a simple step tracker in the sidebar, hiding sub-steps the user
    doesn't need to visit based on their source selection."""
    visible = _visible_steps()
    current = st.session_state.current_step
    # Index used for "Step X of N" - clamp to range so a hidden current step
    # (defensive) still renders something sensible.
    try:
        current_idx = visible.index(current)
    except ValueError:
        current_idx = -1

    rows_html = []
    for i, step in enumerate(visible):
        label = STEP_LABELS[step]
        if step == current:
            klass = "current"
            marker = "●"
        elif current_idx >= 0 and i < current_idx:
            klass = "done"
            marker = "✓"
        else:
            klass = "todo"
            marker = f"{i + 1}"
        rows_html.append(
            f'<div class="sb-step {klass}">'
            f'  <span class="marker">{marker}</span>'
            f'  <span class="lbl">{label}</span>'
            f'</div>'
        )

    pos_text = (
        f"Step {current_idx + 1} of {len(visible)}"
        if current_idx >= 0 else f"{len(visible)} step(s)"
    )
    st.sidebar.markdown(
        f"""
        <div class="sb-stepper">
            <div class="sb-step-count">🧭 Progress · {pos_text}</div>
            {''.join(rows_html)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sample_mode_toggle() -> None:
    """Toggle between sample mode (row-capped) and full dataset.

    Switching invalidates any cached data products / configs / scorecards so
    the next step re-fetches with the new limit.
    """
    from config.settings import SETTINGS

    st.sidebar.markdown(
        '<div class="sb-section-title">'
        '<span class="sec-icon">⚙️</span>Dataset size'
        '</div>',
        unsafe_allow_html=True,
    )
    previous = st.session_state.get("sample_mode", True)
    sample_mode = st.sidebar.toggle(
        f"Sample mode (max {SETTINGS.max_rows_per_table:,} rows/table)",
        value=previous,
        key="sample_mode_toggle",
        help="On: cap each table to the sample size for fast iteration. "
             "Off: fetch the full dataset.",
    )
    if sample_mode != previous:
        # Imported lazily to keep utils/ → src/ dependency direction unambiguous.
        from src.reference_data import clear_reference_cache

        st.session_state.sample_mode = sample_mode
        st.session_state.data_products = {}
        st.session_state.configs = {}
        st.session_state.scorecards = {}
        clear_reference_cache()
        st.rerun()
    st.session_state.sample_mode = sample_mode
    if sample_mode:
        st.sidebar.markdown(
            f'<span class="sb-pill warn">📉 Sample ≤ {SETTINGS.max_rows_per_table:,} rows/table</span>',
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            '<span class="sb-pill info">📊 Full dataset (all rows)</span>',
            unsafe_allow_html=True,
        )


def get_row_limit() -> int | None:
    """Return row limit to apply when fetching tables. None = no limit."""
    from config.settings import SETTINGS

    if st.session_state.get("sample_mode", True):
        return SETTINGS.max_rows_per_table
    return None


_PLANVIEW_FILTER_INPUT_KEY = "planview_filter_input"


def _parse_planview_filter_text(text: str) -> List[str]:
    """Split free-form user input into a deduplicated list of PLANVIEW_IDs.

    Accepts commas, semicolons, whitespace and newlines as separators so the
    user can paste lists in whatever shape they have them. Order is preserved
    (first occurrence wins) so the UI feedback is predictable.
    """
    if not text:
        return []
    raw = text.replace(",", " ").replace(";", " ").split()
    seen = set()
    out: List[str] = []
    for token in raw:
        token = token.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def get_planview_filter() -> List[str]:
    """Return the active PLANVIEW_ID filter (empty list = no filter)."""
    return list(st.session_state.get("planview_filter", []) or [])


def render_planview_filter() -> None:
    """Sidebar widget for filtering the whole app to one or more projects.

    Domain-aware: each :class:`config.domains.DomainDef` declares its own
    ``project_filter`` (Cost Estimate filters on ``PLANVIEW_ID``; Quality
    filters on ``PROJECT_CODE``). The widget is hidden entirely until a
    domain has been selected at Step 0, because the right filter column
    is only known once the domain is known.

    The filter is applied at build_data_product time, so changing it must
    invalidate the cached data products / configs / scorecards just like the
    sample-mode toggle does.
    """
    code = st.session_state.get("domain")
    if not code:
        # Step 0 hasn't completed yet - no domain, no domain-specific
        # filter to render. Sidebar shows the brand + progress only.
        return

    # Resolve the domain off the *patched* ``st.session_state`` rather
    # than via :func:`get_active_domain`, which goes through the real
    # streamlit module - tests patch this module's ``st`` reference,
    # not ``config.domains.st``.
    try:
        project_filter = get_domain(code).project_filter
    except KeyError:
        # Unknown domain code in session state (corrupted session). Skip
        # the widget rather than crash the sidebar; restart_app sends
        # the user back to Step 0 which will repopulate ``domain``.
        return
    st.sidebar.markdown(
        '<div class="sb-section-title">'
        '<span class="sec-icon">🎯</span>Project filter'
        '</div>',
        unsafe_allow_html=True,
    )
    previous = st.session_state.get("planview_filter", []) or []
    default_text = "\n".join(previous)
    text = st.sidebar.text_area(
        project_filter.label,
        value=default_text,
        key=_PLANVIEW_FILTER_INPUT_KEY,
        height=80,
        placeholder=project_filter.placeholder,
        help=project_filter.help,
    )
    parsed = _parse_planview_filter_text(text)
    if parsed != previous:
        from src.reference_data import clear_reference_cache

        st.session_state.planview_filter = parsed
        st.session_state.data_products = {}
        st.session_state.configs = {}
        st.session_state.scorecards = {}
        clear_reference_cache()
        st.rerun()
    if parsed:
        pill_word = (
            project_filter.pill_singular if len(parsed) == 1
            else project_filter.pill_plural
        )
        st.sidebar.markdown(
            f'<span class="sb-pill ok">🎯 Filtering on {len(parsed)} '
            f'{pill_word}</span>',
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            f'<span class="sb-pill neutral">🌐 All {project_filter.pill_plural} '
            '(no filter)</span>',
            unsafe_allow_html=True,
        )


def render_sidebar_footer() -> None:
    """Sidebar footer - app description + a small version badge. Pure
    decoration; no state interaction."""
    st.sidebar.markdown(
        """
        <div class="sb-footer">
            Application for identifying CDEs, defining Data Quality Rules
            and generating scorecards per Data Product.
            <div style="margin-top: 0.5em;">
                Build <span class="sb-version">v2.3</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
