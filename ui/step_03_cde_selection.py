"""
Step 3: CDE selection (redesigned).

Per Data Product: a summary row (collapsed when valid) → when expanded: selected
chips (with the Custom DQR ids that need each column), filter + "Select required
by Custom DQRs", and the profile grid. Only the first DP without CDEs starts
expanded. Data contracts (data_editor caching keyed on ``id(dp)``, widget keys)
are unchanged from the original module.
"""
from __future__ import annotations

import html
from typing import Dict, List

import pandas as pd
import streamlit as st

from config.custom_dqr_catalog import get_available_custom_dqr_rules
from utils.session_state import next_step, prev_step, restart_app
from utils.ui_components import (
    callout,
    code_chip,
    dp_summary_row,
    page_header,
    render_nav_footer,
    step_eyebrow,
)

_PICK_COLUMN = "CDE"
_REQ_COLUMN = "Required by"
_READ_ONLY_COLUMNS: List[str] = ["Column", _REQ_COLUMN, "Type", "Null %", "Distinct", "Sample"]
_EXPANDED_KEY = "expanded_cde"


def _build_required_columns_map(system_code: str) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for rule in get_available_custom_dqr_rules(system_code):
        seen: set = set()
        cols = list(rule.required_columns.values())
        for opt in rule.options:
            cols += list(opt.required_columns_when_enabled.values())
        for col in cols:
            if col in seen:
                continue
            seen.add(col)
            out.setdefault(col, []).append(rule.id)
    return out


def _distinct_sample_for(dp, col: str, n: int = 3) -> List:
    if col not in dp.df.columns:
        return []
    vals = dp.df[col].dropna().drop_duplicates().head(n).tolist()
    return [v.item() if hasattr(v, "item") else v for v in vals]


def _build_profile_grid(dp, current_cdes: List[str], required: Dict[str, List[str]]) -> pd.DataFrame:
    rows = []
    for col in dp.df.columns:
        p = dp.profiles.get(col)
        rows.append({
            _PICK_COLUMN: col in current_cdes,
            "Column": col,
            _REQ_COLUMN: ", ".join(required.get(col, [])),
            "Type": p.column_type_group if p else "-",
            "Null %": p.null_pct if p else 0.0,
            "Distinct": p.distinct_count if p else 0,
            "Sample": ", ".join(str(v) for v in _distinct_sample_for(dp, col)) if p else "",
        })
    return pd.DataFrame(rows)


def _missing_required(cfg, required: Dict[str, List[str]]) -> List[str]:
    return [c for c in required if c not in set(cfg.cdes)]


def _render_dp_block(system_code: str, dp) -> None:
    cfg = st.session_state.configs[system_code]
    required = _build_required_columns_map(system_code)
    token = id(dp)
    base_key = f"cde_grid_base_{system_code}_{token}"
    editor_key = f"cde_grid_{system_code}_{token}"
    if base_key not in st.session_state:
        st.session_state[base_key] = _build_profile_grid(dp, list(cfg.cdes), required)

    # toolbar: chips + filter + shortcut
    chip_slot = st.empty()
    c_filter, c_btn = st.columns([2, 1.6])
    with c_filter:
        query = st.text_input("Filter columns", key=f"cde_filter_{system_code}", placeholder="Filter columns…",
                              label_visibility="collapsed")
    with c_btn:
        if required and st.button(f"Select required by Custom DQRs · {len(required)}",
                                  key=f"cde_select_all_required_{system_code}_{token}",
                                  use_container_width=True,
                                  help="Mark every column a Custom DQR needs as a CDE. Existing picks are kept."):
            new = [c for c in dp.df.columns if c in set(cfg.cdes) or c in required]
            cfg.cdes = new
            st.session_state[base_key] = _build_profile_grid(dp, new, required)
            st.session_state.pop(editor_key, None)

    base = st.session_state[base_key]
    view = base[base["Column"].str.contains(query, case=False, na=False)] if query else base
    edited = st.data_editor(
        view,
        column_config={
            _PICK_COLUMN: st.column_config.CheckboxColumn(_PICK_COLUMN, help="Tick to mark as a Critical Data Element.", default=False, width="small"),
            _REQ_COLUMN: st.column_config.TextColumn(_REQ_COLUMN, help="Custom DQRs that need this column.", width="small"),
            "Null %": st.column_config.ProgressColumn("Null %", min_value=0, max_value=100, format="%.1f%%"),
            "Distinct": st.column_config.NumberColumn(format="%d"),
            "Sample": st.column_config.TextColumn("Sample (3 distinct values)", width="medium"),
        },
        disabled=_READ_ONLY_COLUMNS, hide_index=True, use_container_width=True, height=380, key=editor_key,
    )
    # merge edits back (filtered view edits only touch visible rows)
    picked = set(base.loc[base[_PICK_COLUMN].astype(bool), "Column"])
    picked -= set(view["Column"])
    picked |= set(edited.loc[edited[_PICK_COLUMN].astype(bool), "Column"])
    cfg.cdes = [c for c in dp.df.columns if c in picked]

    with chip_slot.container():
        if cfg.cdes:
            chips = "".join(
                f'<span class="dq-code brand" style="margin:0 6px 6px 0">{html.escape(c)}'
                + (f' <span style="opacity:.7;font-size:10px">{html.escape(" ".join(required[c]))}</span>' if c in required else "")
                + "</span>"
                for c in cfg.cdes
            )
            st.markdown(f'<div style="margin:4px 0 8px"><span style="font-size:12px;color:var(--dq-tx3);margin-right:6px">Selected</span>{chips}</div>',
                        unsafe_allow_html=True)
        else:
            callout("No CDE selected yet — tick rows in the grid.", "info")
    st.caption(f"{len(dp.df.columns)} columns · Required-by lists the Custom DQRs (later step) that need the column.")


def render() -> None:
    page_header(step_eyebrow(), "Mark Critical Data Elements",
                "Profile metadata is inline; columns required by Custom DQRs are flagged.")
    dps = st.session_state.data_products
    if not dps:
        callout("Data Products are not built yet. Go back one step.", "info")
        _nav()
        return

    expanded = st.session_state.get(_EXPANDED_KEY)
    if expanded not in dps:
        expanded = next((c for c in dps if not st.session_state.configs[c].cdes), next(iter(dps)))
        st.session_state[_EXPANDED_KEY] = expanded

    for code, dp in dps.items():
        cfg = st.session_state.configs[code]
        required = _build_required_columns_map(code)
        missing = _missing_required(cfg, required)
        n = len(cfg.cdes)
        if not n:
            kind, text = "none", "No CDEs yet"
        elif missing:
            kind, text = "warn", f"{n} CDEs · {len(missing)} required missing"
        else:
            kind, text = "good", f"{n} CDEs"
        with st.container(border=True):
            is_open = dp_summary_row(
                code=code, name=dp.name, status_kind=kind, status_text=text,
                meta=f"{dp.column_count} columns", expanded=(code == expanded), key=f"cde_toggle_{code}",
            )
            if is_open != (code == expanded):
                st.session_state[_EXPANDED_KEY] = code if is_open else None
                st.rerun()
            if code == expanded:
                _render_dp_block(code, dp)

    any_cdes = any(cfg.cdes for cfg in st.session_state.configs.values())
    _nav(show_next=any_cdes)


def _nav(show_next: bool = False) -> None:
    total = sum(len(c.cdes) for c in st.session_state.get("configs", {}).values())
    render_nav_footer(
        show_next=show_next,
        next_message=f"{total} CDEs across {len(st.session_state.get('configs', {}))} Data Products",
        blocked_message="Pick at least one CDE in any Data Product to continue.",
        on_back=prev_step, on_next=next_step, on_restart=restart_app,
    )
