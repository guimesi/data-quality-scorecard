"""Sidebar = navigation rail.

Order (top → bottom): brand row · workspace block (domain + mode + systems,
only once a domain exists) · step list · settings (Dataset, Project filter -
each inside a popover so they don't compete with the wizard) · footer
(Usage & audit link + catalog.schema).

Test contracts preserved (tests/test_session_state.py, test_step_mode_selection_ui.py):
- ``render_progress_sidebar`` emits ONE ``st.sidebar.markdown`` block that
  contains the word ``Progress``, ``Step X of N`` and ``class="sb-step current"``
  on the current row (labels come from ``STEP_LABELS``).
- ``render_sample_mode_toggle`` uses ``st.sidebar.toggle`` and emits a
  markdown containing ``Sample`` or ``Full dataset``; flipping it wipes
  data_products/configs/scorecards and reruns.
- ``render_planview_filter`` uses ``st.sidebar.text_area`` and is a no-op
  before a domain is picked.
The FakeSidebar used by unit tests only implements ``markdown``, ``toggle``
and ``text_area`` - hence the ``_popover()`` guard below.
"""
from __future__ import annotations

import html as _html
from contextlib import contextmanager
from typing import List

import streamlit as st

from config.domains import get_active_domain, get_domain
from utils.session.navigation import _visible_steps
from utils.session.state import APP_MODE_ONE_CLICK, STEP_LABELS

_APP_VERSION = "v2.3"


def inject_sidebar_css() -> None:
    """Compatibility shim - the rail CSS (``.dq-*`` classes) is part of the
    single global sheet in :func:`ui._theme.inject_global_css`."""
    return None


@contextmanager
def _popover(label: str):
    """Yields the container that must own the widgets: the popover body when
    ``st.sidebar.popover`` exists (real Streamlit), else ``st.sidebar`` itself
    (unit-test FakeSidebar). Callers MUST call ``box.toggle(...)`` /
    ``box.text_area(...)`` on the yielded object - ``st.sidebar.toggle`` inside
    the ``with`` would render outside the popover."""
    popover = getattr(st.sidebar, "popover", None)
    if popover is None:
        yield st.sidebar
        return
    with popover(label, use_container_width=True) as box:
        yield box if box is not None else st


# ---------------------------------------------------------------------------
# Brand + workspace
# ---------------------------------------------------------------------------

def render_sidebar_brand() -> None:
    st.sidebar.markdown(
        f"""
        <div class="dq-brand">
            <div class="mark">DQ</div>
            <div class="name">DQ Scorecard</div>
            <div class="ver">{_APP_VERSION}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    code = st.session_state.get("domain")
    if not code or st.session_state.get("current_step") == "adoption":
        return
    try:
        domain = get_active_domain()
    except Exception:
        return
    mode = st.session_state.get("app_mode")
    mode_label = "One-click" if mode == APP_MODE_ONE_CLICK else "Step-by-step"
    systems: List[str] = list(st.session_state.get("selected_systems") or [])
    systems_txt = " · ".join(systems) if systems else _html.escape(domain.subtitle)
    st.sidebar.markdown(
        f"""
        <div class="dq-ctx">
            <div class="dq-rail-title" style="padding:0 0 2px;">Workspace</div>
            <div style="display:flex;align-items:center;gap:8px;">
                <span style="font-weight:600;font-size:13px;">{_html.escape(domain.name)}</span>
                <span class="dq-badge brand" style="margin-left:auto;">{mode_label}</span>
            </div>
            <div style="font-family:var(--dq-mono);font-size:11px;color:var(--dq-tx3);">{systems_txt}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Stepper
# ---------------------------------------------------------------------------

def _rail_title() -> str:
    mode = st.session_state.get("app_mode")
    step = st.session_state.get("current_step")
    if step == "adoption":
        return "Admin"
    if mode == APP_MODE_ONE_CLICK:
        return "One-click"
    if mode:
        return "Steps"
    return "Start"


def render_progress_sidebar() -> None:
    visible = _visible_steps()
    current = st.session_state.current_step
    try:
        current_idx = visible.index(current)
    except ValueError:
        current_idx = -1

    selected = st.session_state.get("selected_systems") or []
    rows = []
    for i, step in enumerate(visible):
        label = _html.escape(STEP_LABELS[step])
        if step == current:
            klass, marker = "current", str(i + 1)
        elif 0 <= current_idx and i < current_idx:
            klass, marker = "done", "&#10003;"
        else:
            klass, marker = "todo", str(i + 1)
        meta = ""
        if klass == "done" and step in ("system_selection", "one_click") and selected:
            meta = f'<span class="meta">{_html.escape(", ".join(selected))}</span>'
        rows.append(
            f'<div class="dq-step sb-step {klass}">'
            f'<span class="mk">{marker}</span><span>{label}</span>{meta}</div>'
        )

    pos_text = (
        f"Step {current_idx + 1} of {len(visible)}" if current_idx >= 0
        else f"{len(visible)} step(s)"
    )
    st.sidebar.markdown(
        f"""
        <div class="dq-rail-title">{_rail_title()}
            <span style="float:right;font-weight:400;">Progress · {pos_text}</span>
        </div>
        {''.join(rows)}
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Settings (Dataset / Project filter)
# ---------------------------------------------------------------------------

def _settings_visible() -> bool:
    step = st.session_state.get("current_step")
    return bool(st.session_state.get("app_mode")) and step not in ("mode_selection", "adoption")


def _invalidate_workflow_data() -> None:
    from src.reference_data import clear_reference_cache

    st.session_state.data_products = {}
    st.session_state.configs = {}
    st.session_state.scorecards = {}
    clear_reference_cache()


def render_sample_mode_toggle() -> None:
    """Dataset size: Sample (row-capped) vs Full. Lives in a popover; the
    trigger shows the current state as a badge."""
    from config.settings import SETTINGS

    previous = st.session_state.get("sample_mode", True)
    if _settings_visible() or not hasattr(st.sidebar, "popover"):
        if _settings_visible():
            st.sidebar.markdown('<div class="dq-rail-title">Settings</div>', unsafe_allow_html=True)
        badge = (
            f"Sample · {SETTINGS.max_rows_per_table // 1000}k rows" if previous else "Full dataset"
        )
        with _popover(f"Dataset · {badge}") as box:
            sample_mode = box.toggle(
                f"Sample mode (max {SETTINGS.max_rows_per_table:,} rows/table)",
                value=previous,
                key="sample_mode_toggle",
                help="On: cap each table to the sample size for fast iteration. "
                     "Off: fetch the full dataset. Changing this rebuilds the Data Products.",
            )
    else:
        sample_mode = previous

    if sample_mode != previous:
        st.session_state.sample_mode = sample_mode
        _invalidate_workflow_data()
        st.rerun()
    st.session_state.sample_mode = sample_mode

    # State line (test contract: "Sample" / "Full dataset" in a markdown).
    if _settings_visible() or not hasattr(st.sidebar, "popover"):
        if sample_mode:
            st.sidebar.markdown(
                f'<div class="dq-setting">Dataset<span class="dq-badge" style="background:var(--dq-wn-soft);color:var(--dq-wn);">'
                f'Sample ≤ {SETTINGS.max_rows_per_table:,} rows</span></div>',
                unsafe_allow_html=True,
            )
        else:
            st.sidebar.markdown(
                '<div class="dq-setting">Dataset<span class="dq-badge brand">Full dataset</span></div>',
                unsafe_allow_html=True,
            )


def get_row_limit() -> int | None:
    from config.settings import SETTINGS

    if st.session_state.get("sample_mode", True):
        return SETTINGS.max_rows_per_table
    return None


_PLANVIEW_FILTER_INPUT_KEY = "planview_filter_input"


def _parse_planview_filter_text(text: str) -> List[str]:
    if not text:
        return []
    raw = text.replace(",", " ").replace(";", " ").split()
    seen, out = set(), []
    for token in raw:
        token = token.strip()
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def get_planview_filter() -> List[str]:
    return list(st.session_state.get("planview_filter", []) or [])


def render_planview_filter() -> None:
    code = st.session_state.get("domain")
    if not code or not _settings_visible():
        return
    try:
        project_filter = get_domain(code).project_filter
    except KeyError:
        return

    previous = st.session_state.get("planview_filter", []) or []
    badge = (
        f"{len(previous)} {project_filter.pill_singular if len(previous) == 1 else project_filter.pill_plural}"
        if previous else f"All {project_filter.pill_plural}"
    )
    with _popover(f"Project filter · {badge}") as box:
        text = box.text_area(
            project_filter.label,
            value="\n".join(previous),
            key=_PLANVIEW_FILTER_INPUT_KEY,
            height=80,
            placeholder=project_filter.placeholder,
            help=project_filter.help + " Changing this rebuilds the Data Products.",
        )
    parsed = _parse_planview_filter_text(text)
    if parsed != previous:
        st.session_state.planview_filter = parsed
        _invalidate_workflow_data()
        st.rerun()

    if parsed:
        st.sidebar.markdown(
            f'<div class="dq-setting">Project filter<span class="dq-badge brand">{len(parsed)} '
            f'{_html.escape(project_filter.pill_singular if len(parsed) == 1 else project_filter.pill_plural)}</span></div>',
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            f'<div class="dq-setting">Project filter<span class="dq-badge">All {_html.escape(project_filter.pill_plural)}</span></div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

def render_sidebar_footer() -> None:
    """Usage & audit entry point + data location. No product blurb."""
    from config.settings import SETTINGS

    button = getattr(st.sidebar, "button", None)
    if button is not None and st.session_state.get("current_step") != "adoption":
        st.sidebar.markdown('<div class="dq-rail-footer"></div>', unsafe_allow_html=True)
        if button("Usage & audit", key="rail_open_adoption", type="tertiary",
                  help="Adoption metrics and the audit trail (admin)."):
            from utils.session.navigation import goto
            goto("adoption")
    st.sidebar.markdown(
        f'<div class="dq-rail-loc">{_html.escape(SETTINGS.dbx_catalog)}.{_html.escape(SETTINGS.dbx_schema)}</div>',
        unsafe_allow_html=True,
    )
