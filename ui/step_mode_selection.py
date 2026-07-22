"""
Initial step: Mode selection.

The new entry point of the app. Before anything else, the user chooses how
they want to build their scorecards:

- **One-click**: pick a domain + systems, then the app automates the rest
  (CDEs, custom rules, default options, equal weights, scorecards, CSVs).
- **Step-by-step**: the historical manual flow - full control over every step.

This step only sets ``session_state.app_mode`` and routes onward; it owns
no workflow data of its own. Visual identity mirrors Step 0 (domain
selection) so the two early screens read as one coherent on-ramp.
A third on-ramp - **Open a saved project** - appears below the two mode
cards once at least one project exists: pick a project (and optionally an
older version from its audit changelog), and the app rebuilds the data
products fresh, applies the saved configuration and lands on the
dashboard in Step-by-step mode, so every step remains editable.
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from src.projects import get_project, list_projects
from utils.helpers import section_header
from utils.session_state import (
    APP_MODE_ONE_CLICK,
    APP_MODE_STEP_BY_STEP,
    get_planview_filter,
    get_row_limit,
    goto,
    set_app_mode,
    set_domain,
)

# Card content for the two modes. Order is the display order (One-click
# first - it's the recommended fast path for most users).
_MODE_CARDS = (
    {
        "mode": APP_MODE_ONE_CLICK,
        "icon": "⚡",
        "title": "One-click mode",
        "accent": "#f59e0b",
        "tagline": "Fastest path to a scorecard",
        "next_step": "one_click",
        "description": (
            "Pick a domain and the systems to include - the app does the "
            "rest automatically."
        ),
        "bullets": [
            "Selects only the CDEs the custom rules need",
            "Applies every Custom DQR with its default options",
            "Distributes rule weights equally",
            "Generates the scorecards and CSV exports",
        ],
    },
    {
        "mode": APP_MODE_STEP_BY_STEP,
        "icon": "🛠️",
        "title": "Step-by-step mode",
        "accent": "#4f46e5",
        "tagline": "Full manual control",
        "next_step": "domain_selection",
        "description": (
            "The original step-by-step workflow. Customise every choice "
            "exactly as before."
        ),
        "bullets": [
            "Choose Standard and/or Custom DQR sources",
            "Hand-pick CDEs and tune every rule option",
            "Set source and rule weights yourself",
            "Review, then export from the dashboard",
        ],
    },
)


def _mode_card(card: dict, is_active: bool) -> None:
    """Render one mode card and wire its Select button."""
    active_pill = (
        '<span class="mode-active-pill">SELECTED</span>' if is_active else ""
    )
    bullets = "".join(
        f"<li>{html.escape(b)}</li>" for b in card["bullets"]
    )
    st.markdown(
        f"""
        <div class="card-accent" style="background: {card['accent']};"></div>
        <div class="mode-title-row">
            <span class="mode-icon">{html.escape(card['icon'])}</span>
            <span class="mode-title">{html.escape(card['title'])}{active_pill}</span>
        </div>
        <div class="mode-tagline">{html.escape(card['tagline'])}</div>
        <div class="mode-desc">{html.escape(card['description'])}</div>
        <ul class="mode-bullets">{bullets}</ul>
        """,
        unsafe_allow_html=True,
    )
    label = "✓ Selected" if is_active else f"Start {card['title'].split(' mode')[0]}"
    if st.button(
        label,
        key=f"mode_pick_{card['mode']}",
        type="primary" if is_active else "secondary",
        use_container_width=True,
    ):
        set_app_mode(card["mode"])
        goto(card["next_step"])


def _open_project(record: dict) -> None:
    """Load a saved project version: rebuild the data products fresh and
    apply the stored configuration, then land on the dashboard.

    Enters Step-by-step mode so every step stays editable - the user can
    walk back, tweak, and save again as a new version.
    """
    # Imported lazily: data building pulls pandas/Snowflake machinery this
    # lightweight entry step doesn't otherwise need.
    from config.domains import get_active_project_filter
    from src.data_product_builder import build_multiple
    from src.persistence import log_event
    from src.profiler import profile_dataframe
    from src.projects import deserialize_project
    from src.reference_data import (
        prefetch_reference_datasets,
        required_reference_datasets_for_systems,
    )

    domain_code, configs = deserialize_project(record.get("payload") or {})
    if not domain_code or not configs:
        st.error("❌ This project version is empty or corrupt.")
        return
    set_app_mode(APP_MODE_STEP_BY_STEP)
    try:
        set_domain(domain_code)
    except KeyError:
        st.error(f"❌ Unknown domain in saved project: {domain_code}")
        return
    systems = sorted(configs)
    with st.spinner(
        f"📂 Rebuilding {', '.join(systems)} and applying the saved "
        "configuration..."
    ):
        try:
            dps = build_multiple(
                systems,
                row_limit=get_row_limit(),
                planview_ids=get_planview_filter() or None,
                filter_column=get_active_project_filter().column,
            )
            for dp in dps.values():
                dp.profiles = profile_dataframe(dp.df)
            ref_names = required_reference_datasets_for_systems(systems)
            if ref_names:
                prefetch_reference_datasets(ref_names)
        except Exception as exc:
            st.error(
                f"❌ Could not rebuild the project's data products: {exc}"
            )
            return
    st.session_state.selected_systems = systems
    st.session_state.data_products = dps
    st.session_state.configs = configs
    st.session_state.loaded_project_name = record.get("project_name", "")
    log_event(
        "project_loaded",
        {"project": record.get("project_name", ""),
         "version": record.get("version")},
        domain_code,
    )
    goto("dashboard")


def _render_saved_projects() -> None:
    """Browser for saved projects: pick one (and optionally an older
    version from the changelog) and open it. Renders nothing when no
    project has been saved yet."""
    projects = list_projects()
    if not projects:
        return
    st.markdown("---")
    st.markdown("### 📂 Open a saved project")
    st.caption(
        "Projects capture the whole configuration (domain, systems, CDEs, "
        "rules, weights) with a versioned audit changelog. Data is rebuilt "
        "fresh on open; every step stays editable."
    )
    names = [p["name"] for p in projects]
    by_name = {p["name"]: p for p in projects}
    c_proj, c_ver, c_open = st.columns([3, 2, 1])
    with c_proj:
        name = st.selectbox(
            "Project", names, key="project_open_name",
            format_func=lambda n: (
                f"{n} · {by_name[n].get('domain_code', '?')} · "
                f"v{by_name[n].get('versions', 0)} · last saved by "
                f"{by_name[n].get('updated_by', '?')}"
            ),
        )
    from src.persistence import list_project_versions
    versions = list_project_versions(name)
    with c_ver:
        options = [int(v.get("version", 0)) for v in versions]
        version = st.selectbox(
            "Version", options,
            index=len(options) - 1 if options else 0,
            key="project_open_version",
            format_func=lambda v: f"v{v}" + (
                " (latest)" if options and v == options[-1] else ""
            ),
        )
    with c_open:
        st.markdown("<div style='height:1.7em'></div>", unsafe_allow_html=True)
        open_clicked = st.button(
            "📂 Open", key="project_open_btn", type="primary",
            use_container_width=True,
        )
    with st.expander(f"📜 Changelog - {name}", expanded=False):
        st.dataframe(
            pd.DataFrame([
                {
                    "Version": int(v.get("version", 0)),
                    "When (UTC)": v.get("ts", ""),
                    "Who": v.get("username", ""),
                    "What changed": v.get("change_summary", ""),
                }
                for v in versions
            ]).iloc[::-1],
            use_container_width=True, hide_index=True,
        )
    if open_clicked:
        record = get_project(name, version)
        if record is None:
            st.error("❌ Could not load that project version.")
            return
        _open_project(record)


def render() -> None:

    st.markdown(
        '<div class="step-pill">Start · Choose how to build</div>',
        unsafe_allow_html=True,
    )
    section_header(
        "How do you want to build your scorecards?",
        "Pick **One-click** to go from domain + systems straight to finished "
        "scorecards, or **Step-by-step** for the full step-by-step workflow with "
        "manual control over every CDE, rule, option and weight. You can "
        "restart and switch modes at any time.",
    )

    active_mode = st.session_state.get("app_mode")
    cols = st.columns(len(_MODE_CARDS), gap="large")
    for card, col in zip(_MODE_CARDS, cols):
        with col:
            with st.container(border=True):
                _mode_card(card, is_active=(card["mode"] == active_mode))

    _render_saved_projects()
