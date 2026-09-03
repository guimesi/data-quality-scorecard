"""Dashboard overview: one score card per Data Product + "Needs attention".

Pure presentation over ``ScorecardResult``; no new math. "Needs attention"
ranks the existing ``rule_pass_rates`` / ``custom_rule_pass_rates`` ascending.
"""
from __future__ import annotations

import html
from typing import Dict, List, Tuple

import streamlit as st

from config.custom_dqr_catalog import get_available_custom_dqr_rules
from utils.ui_components import code_chip, dist_bar, progress_bar, status_class, status_word

_SELECTED_KEY = "dash_selected_dp"


def selected_dp(scorecards: Dict[str, object]) -> str:
    """Selected DP code; defaults to the WORST-scoring one so the page opens on
    the problem, not on the first system alphabetically."""
    codes = list(scorecards)
    cur = st.session_state.get(_SELECTED_KEY)
    if cur in scorecards:
        return cur
    worst = min(codes, key=lambda c: scorecards[c].overall_score)
    st.session_state[_SELECTED_KEY] = worst
    return worst


def _delta_vs_previous(code: str) -> str | None:
    try:
        from src.run_history import load_history
        hist = load_history(code)
        if len(hist) < 2:
            return None
        prev = float((hist[-2].get("payload") or {}).get("overall_score", 0.0))
        curr = float((hist[-1].get("payload") or {}).get("overall_score", 0.0))
        d = curr - prev
        return f"{d:+.1f} pp"
    except Exception:
        return None


def _worst_rules(scorecards: Dict[str, object], limit: int = 4) -> List[Tuple[str, str, float]]:
    rows: List[Tuple[str, str, float]] = []
    for code, r in scorecards.items():
        for rule_id, pct in (r.rule_pass_rates or {}).items():
            rows.append((code, rule_id.replace("::", " · "), float(pct)))
        if r.custom_rule_pass_rates:
            names = {x.id: x.name for x in get_available_custom_dqr_rules(code)}
            for rule_id, pct in r.custom_rule_pass_rates.items():
                rows.append((code, f"{rule_id} · {names.get(rule_id, rule_id)}", float(pct)))
    rows.sort(key=lambda t: t[2])
    return rows[:limit]


def render_overview(scorecards: Dict[str, object], skipped: Dict[str, str] | None = None) -> str:
    """Score cards (clickable → selects the DP) + Needs attention. Returns the
    selected DP code."""
    sel = selected_dp(scorecards)
    codes = list(scorecards) + list((skipped or {}).keys())
    cols = st.columns([1] * len(codes) + [1.3], gap="small")

    for code, col in zip(codes, cols[:-1]):
        with col:
            key = f"score_{code}"
            if code == sel:
                st.markdown(
                    f"<style>.st-key-{key} div[data-testid='stVerticalBlockBorderWrapper']"
                    "{border-color:var(--dq-br)!important;box-shadow:0 0 0 3px var(--dq-br-soft);}</style>",
                    unsafe_allow_html=True,
                )
            with st.container(border=True, key=key):
                r = scorecards.get(code)
                dp = (st.session_state.get("data_products") or {}).get(code)
                name = html.escape(getattr(dp, "name", code))
                if r is None:
                    st.markdown(
                        f'<div class="dq-scorecard"><div class="head"><b>{code}</b>{name}</div>'
                        f'<div class="line"><span class="dq-score none">—</span>'
                        f'<span class="dq-status none">Not scored</span></div>'
                        f'<div class="foot"><span>{html.escape((skipped or {}).get(code, "skipped"))}</span></div></div>',
                        unsafe_allow_html=True,
                    )
                    continue
                kind = status_class(r.overall_score, r.threshold_green, r.threshold_yellow)
                delta = _delta_vs_previous(code)
                delta_html = ""
                if delta:
                    color = "var(--dq-er)" if delta.startswith("-") else "var(--dq-ok)"
                    delta_html = f'<span style="color:{color}">{delta}</span>'
                st.markdown(
                    f'<div class="dq-scorecard"><div class="head"><b>{code}</b>{name}</div>'
                    f'<div class="line"><span class="dq-score {kind}">{r.overall_score:.1f}</span>'
                    f'<span class="dq-status {kind}">{status_word(r.overall_score, r.threshold_green, r.threshold_yellow)}</span></div>'
                    f'{dist_bar(r.rows_green, r.rows_yellow, r.rows_red)}'
                    f'<div class="foot"><span>{r.total_rows:,} rows</span>{delta_html}</div></div>',
                    unsafe_allow_html=True,
                )
                if st.button("Inspect", key=f"pick_{code}", type="tertiary", use_container_width=True,
                             disabled=(code == sel)):
                    st.session_state[_SELECTED_KEY] = code
                    st.rerun()

    with cols[-1]:
        with st.container(border=True):
            st.markdown(
                '<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px">'
                '<span style="font-weight:600;font-size:13px">Needs attention</span>'
                '<span style="font-size:11.5px;color:var(--dq-tx3)">lowest pass rates</span></div>',
                unsafe_allow_html=True,
            )
            worst = _worst_rules(scorecards)
            if not worst:
                st.caption("No rule results yet.")
            for code, label, pct in worst:
                kind = "good" if pct >= 80 else ("warn" if pct >= 60 else "poor")
                st.markdown(
                    f'<div class="dq-attn"><span class="dp">{code}</span>'
                    f'<div><div class="name">{html.escape(label)}</div>{progress_bar(pct, kind)}</div>'
                    f'<span class="pct" style="color:var(--dq-{ {"good":"ok","warn":"wn","poor":"er"}[kind] })">{pct:.1f}%</span></div>',
                    unsafe_allow_html=True,
                )
    return sel
