"""Per-DP detail card (redesigned): header strip → tabs. No gauge, no duplicated
metrics; the drill-down (select a rule → failing rows) is the primary
interaction and renders in a side panel.

``_render_overview_cards`` is kept as a thin wrapper for backwards
compatibility (tests / __all__) and delegates to ``_overview.render_overview``.
"""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.dqr_sources import SOURCE_CUSTOM, SOURCE_LABELS, SOURCE_STANDARD
from ui.step_06._breakdown import _render_custom_rules_table
from ui.step_06._drilldown import (
    _render_cde_drilldown,
    _render_dimension_drilldown,
    _render_rule_drilldown,
)
from ui.step_06._export import _per_rule_score_columns, _reference_columns_for_export
from ui.step_06._history import _render_drop_alert, _render_history_tab
from ui.step_06._overview import render_overview
from utils.colors import STATUS_GREEN, STATUS_RED, STATUS_YELLOW
from utils.helpers import score_bucket, score_color
from utils.ui_components import code_chip, dist_bar, status_badge, status_glyph_text

_GLYPH_BY_BUCKET = {"green": "good", "yellow": "warn", "red": "poor"}


def _render_overview_cards(scorecards) -> None:  # compat shim
    render_overview(scorecards)


def _bar_chart(items: dict, result, key: str):
    """Horizontal bars, worst first, with glyph+value labels so status is not
    colour-only. Click → drill-down (unchanged event contract)."""
    df = pd.DataFrame([{"name": k, "score": round(v, 2)} for k, v in items.items()]).sort_values("score")
    labels = [
        f"{status_glyph_text(_GLYPH_BY_BUCKET[score_bucket(s, result.threshold_green, result.threshold_yellow)])} {s:.1f}"
        for s in df["score"]
    ]
    fig = go.Figure(go.Bar(
        x=df["score"], y=df["name"], orientation="h",
        marker_color=[score_color(s, result.threshold_green, result.threshold_yellow) for s in df["score"]],
        text=labels, textposition="outside", cliponaxis=False,
    ))
    fig.update_layout(
        template="plotly_white", height=max(160, 30 * len(df) + 60),
        xaxis=dict(range=[0, 112], title=None, showgrid=True, gridcolor="#E2E5EA"),
        yaxis=dict(title=None, tickfont=dict(family="ui-monospace, Menlo, monospace", size=12)),
        margin=dict(t=8, b=8, l=8, r=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(size=12, color="#4A5262"),
    )
    fig.add_vline(x=result.threshold_green, line_dash="dot", line_color="#C9CED7")
    fig.add_vline(x=result.threshold_yellow, line_dash="dot", line_color="#C9CED7")
    return st.plotly_chart(fig, use_container_width=True, on_select="rerun", key=key)


def _header_strip(code: str, dp, result) -> None:
    weights = result.source_weights or {}
    parts = []
    if result.standard_score is not None:
        parts.append(f'<span><span style="color:var(--dq-tx3)">Standard</span> <b style="font-family:var(--dq-mono)">{result.standard_score:.1f}</b>'
                     f' <span style="color:var(--dq-tx3)">· {weights.get(SOURCE_STANDARD, 0):.0f}%</span></span>')
    if result.custom_score is not None:
        parts.append(f'<span><span style="color:var(--dq-tx3)">Custom</span> <b style="font-family:var(--dq-mono)">{result.custom_score:.1f}</b>'
                     f' <span style="color:var(--dq-tx3)">· {weights.get(SOURCE_CUSTOM, 0):.0f}%</span></span>')
    parts.append(
        f'<span style="color:var(--dq-tx3)">Rows <b style="font-family:var(--dq-mono);color:var(--dq-tx)">{result.total_rows:,}</b> · '
        f'<span style="color:var(--dq-ok)">{result.rows_green:,}</span> / '
        f'<span style="color:var(--dq-wn)">{result.rows_yellow:,}</span> / '
        f'<span style="color:var(--dq-er)">{result.rows_red:,}</span></span>'
    )
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;font-size:12.5px;margin-bottom:6px">'
        f'{code_chip(code)}<span style="font-weight:600;font-size:15px">{html.escape(dp.name)}</span>'
        f'{status_badge(result.overall_score, result.threshold_green, result.threshold_yellow, f"{result.overall_score:.1f}")}'
        f'<span style="font-size:12px;color:var(--dq-tx3)">Thresholds · Good ≥ {result.threshold_green:.0f} · Warning ≥ {result.threshold_yellow:.0f}</span>'
        f'<div style="margin-left:auto;display:flex;gap:18px">{"".join(parts)}</div></div>'
        f'{dist_bar(result.rows_green, result.rows_yellow, result.rows_red)}',
        unsafe_allow_html=True,
    )


def _render_dashboard_for_dp(code: str, dp, result) -> None:
    cfg = st.session_state.configs[code]
    with st.container(border=True):
        _header_strip(code, dp, result)
        _render_drop_alert(code)

        tab_rules, tab_custom, tab_cde, tab_dim, tab_worst, tab_hist = st.tabs([
            "Rules", "Custom rules", "CDEs", "Dimensions", "Failing rows", "History",
        ])

        with tab_rules:
            rows = []
            for a in cfg.assignments:
                reason = result.not_computed_standard_rules.get(a.rule_id)
                rows.append({
                    "CDE": a.cde_column, "Dimension": a.dimension, "Weight (%)": round(a.weight, 2),
                    "Status": "Not computed" if reason is not None else "Evaluated",
                    "Pass rate (%)": float("nan") if reason is not None else round(result.rule_pass_rates.get(a.rule_id, 0.0), 2),
                })
            if rows:
                df_rules = pd.DataFrame(rows).sort_values("Pass rate (%)", na_position="first")
                c_tbl, c_drill = st.columns([1, 1], gap="medium")
                with c_tbl:
                    st.caption("Sorted worst first · select a rule to see its failing rows")
                    rules_event = st.dataframe(
                        df_rules, use_container_width=True, hide_index=True,
                        column_config={
                            "Pass rate (%)": st.column_config.ProgressColumn("Pass rate", min_value=0, max_value=100, format="%.1f%%"),
                            "Weight (%)": st.column_config.NumberColumn("Weight", format="%.0f%%"),
                        },
                        on_select="rerun", selection_mode="single-row", key=f"rules_table_{code}",
                    )
                    for rule_id, reason in result.not_computed_standard_rules.items():
                        st.caption(f"▲ {rule_id} not computed — {reason}")
                with c_drill:
                    _render_rule_drilldown(code, dp, result, cfg, df_rules, rules_event)
            else:
                st.caption("No Standard DQRs on this Data Product.")

        with tab_custom:
            _render_custom_rules_table(code, result)

        with tab_cde:
            if result.cde_scores:
                ev = _bar_chart(result.cde_scores, result, key=f"cde_chart_{code}")
                st.caption("Unweighted mean of the pass rates of every rule tied to the CDE (Standard + Custom). Click a bar to inspect failing rows.")
                _render_cde_drilldown(code, dp, result, cfg, ev)
            else:
                st.caption("No CDE-level results.")

        with tab_dim:
            if result.dimension_scores:
                ev = _bar_chart(result.dimension_scores, result, key=f"dim_chart_{code}")
                st.caption("Unweighted mean per dimension (Custom rules count via their type). Click a bar to inspect failing rows.")
                _render_dimension_drilldown(code, dp, result, cfg, ev)
            else:
                st.caption("No dimension-level results.")

        with tab_worst:
            scores = result.row_scores
            if len(scores) > 0:
                n = min(50, len(scores))
                worst_idx = scores.sort_values().head(n).index
                show = dp.df.loc[worst_idx].copy()
                ref_cols = _reference_columns_for_export(dp, cfg).loc[worst_idx]
                for col in ref_cols.columns:
                    show[col] = ref_cols[col]
                rule_scores = _per_rule_score_columns(dp, cfg).loc[worst_idx]
                for col in rule_scores.columns:
                    show[col] = rule_scores[col]
                show.insert(0, "row_score", scores.loc[worst_idx].round(2))
                st.caption(f"The {n} lowest-scoring rows · rule columns show 100 (pass) or 0 (fail); weights in the header.")
                st.dataframe(show, use_container_width=True, height=350)

        with tab_hist:
            _render_history_tab(code)
