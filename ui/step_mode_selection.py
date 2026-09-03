"""
Entry step: choose how to build (One-click / Step-by-step) or open a saved project.

Test contracts kept (tests/test_step_mode_selection_ui.py): markdown contains
"One-click mode" and "Step-by-step mode"; buttons ``mode_pick_one_click`` /
``mode_pick_step_by_step``; the active mode's button label contains "Selected".
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from src.projects import get_project, list_projects
from utils.session_state import (
    APP_MODE_ONE_CLICK,
    APP_MODE_STEP_BY_STEP,
    get_planview_filter,
    get_row_limit,
    goto,
    set_app_mode,
    set_domain,
)
from utils.ui_components import badge, callout, code_chip, page_header

_MODE_CARDS = (
    {
        "mode": APP_MODE_ONE_CLICK,
        "title": "One-click mode",
        "recommended": True,
        "time": "~2 min",
        "desc": "Pick a domain and systems. Everything else runs with curated defaults.",
        "you": "Domain · Systems",
        "auto": "Required CDEs · All Custom DQRs (defaults) · Equal weights · Exports",
        "best": "Best for recurring monitoring runs.",
        "cta": "Start One-click →",
        "next_step": "one_click",
    },
    {
        "mode": APP_MODE_STEP_BY_STEP,
        "title": "Step-by-step mode",
        "recommended": False,
        "time": "7 steps · 10–20 min",
        "desc": "Configure every CDE, rule, option and weight yourself.",
        "you": "Domain · Systems · CDEs · DQR sources · Rules & options · Weights",
        "auto": "Scoring and exports only",
        "best": "Best for new rule sets, audits and Standard DQRs.",
        "cta": "Start Step-by-step →",
        "next_step": "domain_selection",
    },
)


def _mode_card(card: dict, is_active: bool) -> None:
    key = f"choice_mode_{card['mode']}"
    if is_active or card["recommended"]:
        st.markdown(
            f"<style>.st-key-{key} div[data-testid='stVerticalBlockBorderWrapper']"
            "{border-color:var(--dq-br)!important;box-shadow:0 0 0 3px var(--dq-br-soft);}</style>",
            unsafe_allow_html=True,
        )
    with st.container(border=True, key=key):
        rec = badge("Recommended", "brand") if card["recommended"] else ""
        st.markdown(
            f'<div class="dq-choice-title">{html.escape(card["title"])}{rec}'
            f'<span style="margin-left:auto;font-size:12px;color:var(--dq-tx3);font-weight:400">{card["time"]}</span></div>'
            f'<div class="dq-choice-desc">{html.escape(card["desc"])}</div>'
            f'<div class="dq-choice-grid"><span class="k">You choose</span><span>{card["you"]}</span>'
            f'<span class="k">Automated</span><span>{card["auto"]}</span></div>'
            f'<div style="font-size:12.5px;color:var(--dq-tx3);margin-bottom:10px">{card["best"]}</div>',
            unsafe_allow_html=True,
        )
        label = "Selected · continue →" if is_active else card["cta"]
        if st.button(
            label,
            key=f"mode_pick_{card['mode']}",
            type="primary" if (is_active or card["recommended"]) else "secondary",
            use_container_width=True,
        ):
            set_app_mode(card["mode"])
            goto(card["next_step"])


def _open_project(record: dict) -> None:
    """Rebuild data fresh and apply the saved configuration, then land on the
    Scorecard in Step-by-step mode so every step stays editable."""
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
        st.error("This project version is empty or corrupt.")
        return
    set_app_mode(APP_MODE_STEP_BY_STEP)
    try:
        set_domain(domain_code)
    except KeyError:
        st.error(f"Unknown domain in saved project: {domain_code}")
        return
    systems = sorted(configs)
    with st.status(f"Opening {record.get('project_name', 'project')}…", expanded=True) as status:
        try:
            status.write(f"Building Data Products · {', '.join(systems)}")
            dps = build_multiple(
                systems,
                row_limit=get_row_limit(),
                planview_ids=get_planview_filter() or None,
                filter_column=get_active_project_filter().column,
            )
            status.write("Profiling columns")
            for dp in dps.values():
                dp.profiles = profile_dataframe(dp.df)
            ref_names = required_reference_datasets_for_systems(systems)
            if ref_names:
                status.write(f"Loading reference datasets · {', '.join(ref_names)}")
                prefetch_reference_datasets(ref_names)
            status.update(label="Project opened", state="complete", expanded=False)
        except Exception as exc:
            status.update(label="Could not rebuild the project's Data Products", state="error")
            st.error(str(exc))
            return
    st.session_state.selected_systems = systems
    st.session_state.data_products = dps
    st.session_state.configs = configs
    st.session_state.loaded_project_name = record.get("project_name", "")
    log_event("project_loaded",
              {"project": record.get("project_name", ""), "version": record.get("version")},
              domain_code)
    goto("dashboard")


def _render_saved_projects(projects: list) -> None:
    from src.persistence import list_project_versions

    df = pd.DataFrame([
        {
            "Project": p["name"],
            "Domain": p.get("domain_code", "?"),
            "Version": f"v{p.get('versions', 0)}",
            "Last saved": p.get("updated_at", ""),
            "By": p.get("updated_by", "?"),
        }
        for p in projects
    ])
    event = st.dataframe(
        df, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key="project_table",
        column_config={"Version": st.column_config.TextColumn(width="small")},
    )
    rows = (event.get("selection", {}) or {}).get("rows", []) if event else []
    if not rows:
        st.caption("Select a project to see its versions and open it.")
        return
    name = df.iloc[rows[0]]["Project"]
    versions = list_project_versions(name)
    latest = int(versions[-1].get("version", 0)) if versions else 0

    c_v, c_open = st.columns([3, 1], vertical_alignment="bottom")
    with c_v:
        options = [int(v.get("version", 0)) for v in versions] or [latest]
        version = st.selectbox(
            "Version to open", options, index=len(options) - 1, key="project_open_version",
            format_func=lambda v: f"v{v}" + (" · latest" if v == latest else ""),
        )
    with c_open:
        open_clicked = st.button("Open", key="project_open_btn", type="primary", use_container_width=True)

    with st.expander(f"Versions · {name}", expanded=False):
        st.dataframe(
            pd.DataFrame([
                {"Version": f"v{int(v.get('version', 0))}", "When (UTC)": v.get("ts", ""),
                 "Who": v.get("username", ""), "What changed": v.get("change_summary", "")}
                for v in versions
            ]).iloc[::-1],
            use_container_width=True, hide_index=True,
        )
    st.caption("Opening rebuilds the data fresh and lands on the Scorecard in Step-by-step mode; every step stays editable.")

    if open_clicked:
        record = get_project(name, version)
        if record is None:
            st.error("Could not load that project version.")
            return
        _open_project(record)


def render() -> None:
    page_header("Start", "Build a Data Quality scorecard",
                "Choose how to build, or reopen a saved configuration.")

    projects = list_projects()
    tab_labels = ["New scorecard"] + ([f"Saved projects · {len(projects)}"] if projects else [])
    if hasattr(st, "segmented_control") and len(tab_labels) > 1:
        picked = st.segmented_control("Start", tab_labels, default=tab_labels[0],
                                      key="home_tab", label_visibility="collapsed")
    else:
        picked = tab_labels[0]

    if picked == tab_labels[0]:
        active_mode = st.session_state.get("app_mode")
        cols = st.columns(len(_MODE_CARDS), gap="medium")
        for card, col in zip(_MODE_CARDS, cols):
            with col:
                _mode_card(card, is_active=(card["mode"] == active_mode))
        st.caption("You can restart or switch modes at any point. Data is always rebuilt fresh from Databricks.")
    else:
        _render_saved_projects(projects)
