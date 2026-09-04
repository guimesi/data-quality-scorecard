"""The main per-DP dashboard card (gauge + tabs) and the cross-DP
overview tiles rendered at the top of Step 6.
"""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.persistence import log_event
from ui.step_06._breakdown import (
    _render_custom_rules_table,
    _render_dp_card_header,
    _render_source_breakdown,
)
from ui.step_06._charts import _gauge, _threshold_bar
from ui.step_06._drilldown import (
    _render_cde_drilldown,
    _render_dimension_drilldown,
    _render_rule_drilldown,
)
from ui.step_06._export import (
    _build_config_json,
    _build_rowscores_csv,
    _per_rule_score_columns,
    _reference_columns_for_export,
)
from ui.step_06._history import _render_drop_alert, _render_history_tab
from ui.step_06._rule_rows import standard_rule_rows
from ui.step_06._shared import (
    _DEFAULT_ACCENT,
    _SYSTEM_ACCENTS,
    _SYSTEM_ICONS,
    _status_class,
)
from utils.helpers import score_color, score_label


def _render_dashboard_for_dp(code: str, dp, result) -> None:
    with st.container(border=True):
        hdr_left, hdr_right = st.columns([3, 2])
        with hdr_left:
            _render_dp_card_header(code, dp, result)
            _render_source_breakdown(result)
        with hdr_right:
            st.markdown(
                '<div class="export-title">⬇ Export</div>',
                unsafe_allow_html=True,
            )
            # Original page emitted a `**⬇ Export**` markdown - preserved
            # for any downstream parser / test that relies on the text.
            st.markdown("**⬇ Export**")
            cfg = st.session_state.configs[code]
            domain_code = str(st.session_state.get("domain", "") or "")
            d1, d2 = st.columns(2)
            with d1:
                if st.download_button(
                    "CSV (row scores)",
                    data=_build_rowscores_csv(dp, result, cfg),
                    file_name=f"{code}_row_scores.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key=f"dl_csv_{code}",
                ):
                    log_event("export", {"format": "csv", "dp": code},
                              domain_code)
            with d2:
                if st.download_button(
                    "JSON (config+summary)",
                    data=_build_config_json(dp, result, cfg),
                    file_name=f"{code}_scorecard.json",
                    mime="application/json",
                    use_container_width=True,
                    key=f"dl_json_{code}",
                ):
                    log_event("export", {"format": "json", "dp": code},
                              domain_code)

        _render_drop_alert(code)

        c1, c2 = st.columns([1, 2])
        with c1:
            st.plotly_chart(
                _gauge(result.overall_score, "Data Product Score",
                       result.threshold_green, result.threshold_yellow),
                use_container_width=True,
            )
        with c2:
            cc1, cc2, cc3, cc4 = st.columns(4)
            cc1.metric("Total rows", f"{result.total_rows:,}")
            cc2.metric("🟢 Green", f"{result.rows_green:,}",
                       delta=f"{result.rows_green/max(result.total_rows,1)*100:.1f}%",
                       delta_color="off")
            cc3.metric("🟡 Yellow", f"{result.rows_yellow:,}",
                       delta=f"{result.rows_yellow/max(result.total_rows,1)*100:.1f}%",
                       delta_color="off")
            cc4.metric("🔴 Red", f"{result.rows_red:,}",
                       delta=f"{result.rows_red/max(result.total_rows,1)*100:.1f}%",
                       delta_color="off")
            st.plotly_chart(_threshold_bar(result), use_container_width=True)

        # Breakdowns
        tab_cde, tab_dim, tab_rules, tab_custom, tab_worst, tab_hist = st.tabs([
            "By CDE", "By Dimension", "Rules (pass rate)", "Custom Rules",
            "Worst rows", "History",
        ])

        with tab_cde:
            if result.cde_scores:
                df_cde = pd.DataFrame([
                    {"CDE": k, "Score": round(v, 2)} for k, v in result.cde_scores.items()
                ]).sort_values("Score", ascending=True)
                fig = go.Figure(go.Bar(
                    x=df_cde["Score"], y=df_cde["CDE"], orientation="h",
                    marker_color=[
                        score_color(s, result.threshold_green, result.threshold_yellow)
                        for s in df_cde["Score"]
                    ],
                    text=[f"{s:.1f}" for s in df_cde["Score"]],
                    textposition="outside",
                ))
                fig.update_layout(
                    height=max(200, 40 * len(df_cde) + 80),
                    xaxis=dict(range=[0, 105], title="Score"),
                    margin=dict(t=20, b=20, l=20, r=20),
                )
                st.caption(
                    "Each bar is the simple (unweighted) mean of the pass "
                    "rates of every rule tied to that CDE - Standard and "
                    "Custom blended. Step 5 weights do not affect this view; "
                    "for weight-aware score impact see ML Lab → 🎯 Rule Impact."
                )
                cde_event = st.plotly_chart(
                    fig, use_container_width=True,
                    on_select="rerun", key=f"cde_chart_{code}",
                )
                _render_cde_drilldown(
                    code, dp, result, st.session_state.configs[code], cde_event,
                )

        with tab_dim:
            if result.dimension_scores:
                df_dim = pd.DataFrame([
                    {"Dimension": k, "Score": round(v, 2)}
                    for k, v in result.dimension_scores.items()
                ]).sort_values("Score", ascending=True)
                fig = go.Figure(go.Bar(
                    x=df_dim["Score"], y=df_dim["Dimension"], orientation="h",
                    marker_color=[
                        score_color(s, result.threshold_green, result.threshold_yellow)
                        for s in df_dim["Score"]
                    ],
                    text=[f"{s:.1f}" for s in df_dim["Score"]],
                    textposition="outside",
                ))
                fig.update_layout(
                    height=max(200, 40 * len(df_dim) + 80),
                    xaxis=dict(range=[0, 105], title="Score"),
                    margin=dict(t=20, b=20, l=20, r=20),
                )
                st.caption(
                    "Each bar is the simple (unweighted) mean of the pass "
                    "rates of every rule of that dimension (Custom rules "
                    "count via their type). Step 5 weights do not affect this "
                    "view; for weight-aware score impact see ML Lab → "
                    "🎯 Rule Impact."
                )
                dim_event = st.plotly_chart(
                    fig, use_container_width=True,
                    on_select="rerun", key=f"dim_chart_{code}",
                )
                _render_dimension_drilldown(
                    code, dp, result, st.session_state.configs[code], dim_event,
                )

        with tab_rules:
            cfg = st.session_state.configs[code]
            rows = [
                {
                    "CDE": r["cde"],
                    "Dimension": r["dimension"],
                    "Weight (%)": round(r["weight"], 2),
                    "Status": r["status"],
                    "Pass rate (%)": (
                        float("nan") if r["pass_rate"] is None
                        else round(r["pass_rate"], 2)
                    ),
                }
                for r in standard_rule_rows(cfg, result)
            ]
            if rows:
                df_rules = pd.DataFrame(rows).sort_values(
                    "Pass rate (%)", na_position="first",
                )
                rules_event = st.dataframe(
                    df_rules,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Pass rate (%)": st.column_config.ProgressColumn(
                            "Pass rate (%)", min_value=0, max_value=100, format="%.1f%%",
                        ),
                        "Weight (%)": st.column_config.NumberColumn(format="%.2f%%"),
                    },
                    on_select="rerun",
                    selection_mode="single-row",
                    key=f"rules_table_{code}",
                )
                _render_rule_drilldown(
                    code, dp, result, cfg, df_rules, rules_event,
                )
                if result.not_computed_standard_rules:
                    for rule_id, reason in result.not_computed_standard_rules.items():
                        st.warning(
                            f"⚠ **{rule_id}** could not be computed - "
                            f"{reason}"
                        )
            else:
                st.caption("No Standard DQRs defined for this Data Product.")

        with tab_custom:
            _render_custom_rules_table(code, result)

        with tab_hist:
            _render_history_tab(code)

        with tab_worst:
            scores = result.row_scores
            if len(scores) > 0:
                n = min(50, len(scores))
                worst_idx = scores.sort_values().head(n).index
                show = dp.df.loc[worst_idx].copy()
                cfg = st.session_state.configs[code]
                ref_cols = _reference_columns_for_export(dp, cfg).loc[worst_idx]
                for col in ref_cols.columns:
                    show[col] = ref_cols[col]
                rule_scores = _per_rule_score_columns(dp, cfg).loc[worst_idx]
                for col in rule_scores.columns:
                    show[col] = rule_scores[col]
                show.insert(0, "row_score", scores.loc[worst_idx].round(2))
                st.markdown(
                    f"<div class='worst-banner'>"
                    f"🔍 <b>Inspecting the {n} lowest-scoring rows.</b> "
                    f"Each rule column shows <b>100</b> (pass) or <b>0</b> (fail); "
                    f"rule weights are embedded in the column header."
                    f"</div>",
                    unsafe_allow_html=True,
                )
                # Original caption preserved for parity.
                st.caption(
                    f"Showing the {n} rows with the lowest score. Each rule "
                    "column shows 100 (pass) or 0 (fail); weights are in the "
                    "column header."
                )
                st.dataframe(show, use_container_width=True, height=350)

def _render_overview_cards(scorecards) -> None:
    """Render the per-DP score cards across the top of the dashboard.
    Visually richer than the original `st.metric` row, but conveys the same
    numbers (overall_score + score_label)."""
    cols = st.columns(len(scorecards))
    for (code, result), col in zip(scorecards.items(), cols):
        with col:
            label = score_label(result.overall_score,
                                result.threshold_green, result.threshold_yellow)
            cls = _status_class(result.overall_score,
                                result.threshold_green, result.threshold_yellow)
            accent = _SYSTEM_ACCENTS.get(code, _DEFAULT_ACCENT)
            icon = _SYSTEM_ICONS.get(code, "📦")
            color = score_color(result.overall_score,
                                result.threshold_green, result.threshold_yellow)
            st.markdown(
                f"""
                <div class="score-card">
                    <div class="accent-bar" style="background: {accent};"></div>
                    <div class="sys-row">
                        <span class="sys-icon">{icon}</span>
                        <span class="sys-code">{html.escape(code)}</span>
                    </div>
                    <div class="score-val" style="color: {color};">
                        {result.overall_score:.1f}
                        <span class="score-suffix">/ 100</span>
                    </div>
                    <div class="status-label dp-status-pill {cls}"
                         style="display:inline-block;">
                        {html.escape(label)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
