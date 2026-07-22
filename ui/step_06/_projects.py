"""Step 6 save-as-project panel with the version changelog (phase 3).

Thin Streamlit layer over :mod:`src.projects`. Saving is append-only:
every save creates a new immutable version stamped with who/when and a
human-readable summary of what changed - that version list is the audit
changelog, shown here and on the mode-selection project browser.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.persistence import list_project_versions
from src.projects import save_project


def _render_project_save_panel() -> None:
    """Expander with the project name + Save button + changelog table."""
    configs = st.session_state.get("configs") or {}
    if not configs:
        return
    domain_code = str(st.session_state.get("domain", "") or "")
    with st.expander("💾 Save as project (versioned, with audit changelog)",
                     expanded=False):
        st.caption(
            "Saves the whole configuration - systems, CDEs, rules, params "
            "and weights (not the data). Each save is a new version with "
            "who/when and what changed; reopen it from the start screen."
        )
        c_name, c_btn = st.columns([3, 1])
        with c_name:
            name = st.text_input(
                "Project name",
                value=str(st.session_state.get("loaded_project_name", "") or ""),
                key="project_save_name",
                placeholder="e.g. cost-estimate-quarterly",
            )
        with c_btn:
            st.markdown("<div style='height:1.7em'></div>",
                        unsafe_allow_html=True)
            save_clicked = st.button(
                "💾 Save version", key="project_save_btn",
                use_container_width=True, disabled=not name.strip(),
            )
        if save_clicked:
            record = save_project(name, domain_code, configs)
            if record is None:
                st.error(
                    "❌ Could not save the project (blank name or "
                    "persistence unavailable)."
                )
            else:
                st.session_state.loaded_project_name = name.strip()
                st.success(
                    f"✅ Saved **{name.strip()}** as "
                    f"**v{record.get('version')}** - "
                    f"{record.get('change_summary', '')}"
                )
        versions = list_project_versions(name.strip()) if name.strip() else []
        if versions:
            st.markdown("**📜 Changelog**")
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
                use_container_width=True, hide_index=True, height=180,
            )
