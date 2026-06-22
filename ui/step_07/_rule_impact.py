"""Step 7 ML Lab tab: Rule Impact.

Extracted from the monolithic ``ui/step_07_ml_lab.py`` so each tab lives
in its own file and stays small enough to navigate. The orchestrating
``render()`` (still in :mod:`ui.step_07_ml_lab`) wires this tab into the
``st.tabs(...)`` row at the top.
"""
from __future__ import annotations

import html
import json
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.settings import SETTINGS
from src.ml_lab import (
    compare_data_products,
    compute_cde_profile_clusters,
    compute_drift,
    compute_row_anomalies,
    compute_rule_impact,
    explain_row_score,
    load_snapshot_from_csv,
    load_snapshot_from_json,
    recommend_dqrs_for_cde,
    simulate_weight_perturbation,
    sklearn_status,
    snapshot_scorecard,
    train_risk_classifier,
)
from src.scorecard import compute_scorecard
from ui.step_07._shared import (
    _SYSTEM_ICONS,
    _ensure_scorecards,
    _render_banner,
    _render_empty,
    _render_explainer,
)
from utils.colors import STATUS_GREEN, STATUS_RED
from utils.helpers import section_header
from utils.session_state import goto, prev_step, restart_app


def _render_tab_rule_impact(code: str, dp, config, result) -> None:
    _render_explainer(
        "<b>What this does.</b> For every rule, recomputes the source "
        "sub-score <b>as if that rule were removed</b> (remaining weights "
        "are renormalized). Because each source's sub-score is linear in "
        "the rule pass-rates, the leave-one-out value is <b>exact</b>.<br>"
        "&nbsp;&nbsp;• <code>delta_vs_baseline</code> < 0 → the rule is "
        "<b>lifting</b> the score. Losing it would hurt.<br>"
        "&nbsp;&nbsp;• <code>delta_vs_baseline</code> > 0 → the rule is "
        "<b>dragging</b> the score down (low pass-rate × high weight). "
        "Investigate or rebalance.<br>"
        "&nbsp;&nbsp;• <code>potential_uplift_pct</code> = how many points "
        "the source sub-score would gain if this rule were 100 % passing."
    )

    impact = compute_rule_impact(config, result)
    if impact.empty:
        _render_empty(
            "No DQRs are assigned to this Data Product, so there is nothing "
            "to rank for impact."
        )
        return

    st.dataframe(
        impact[[
            "source", "rule_id", "label", "weight_pct", "pass_rate_pct",
            "baseline_source_score", "loo_source_score",
            "delta_vs_baseline", "criticality", "potential_uplift_pct",
        ]],
        use_container_width=True,
        hide_index=True,
        height=380,
        column_config={
            "weight_pct": st.column_config.NumberColumn(format="%.2f%%"),
            "pass_rate_pct": st.column_config.ProgressColumn(
                "pass_rate_pct", min_value=0, max_value=100, format="%.1f%%",
            ),
            "baseline_source_score": st.column_config.NumberColumn(format="%.2f"),
            "loo_source_score": st.column_config.NumberColumn(format="%.2f"),
            "delta_vs_baseline": st.column_config.NumberColumn(format="%+.2f"),
            "criticality": st.column_config.NumberColumn(format="%.2f"),
            "potential_uplift_pct": st.column_config.NumberColumn(format="%+.2f"),
        },
    )

    st.markdown("##### 🎯 Top criticality (|Δ| if removed)")
    top = impact.sort_values("criticality", ascending=True).tail(15)
    if len(top) > 0:
        fig = go.Figure(go.Bar(
            x=top["delta_vs_baseline"],
            y=top["label"] + " - " + top["source"],
            orientation="h",
            marker_color=[
                STATUS_GREEN if d < 0 else STATUS_RED for d in top["delta_vs_baseline"]
            ],
            text=[f"{d:+.2f}" for d in top["delta_vs_baseline"]],
            textposition="outside",
            hovertemplate="%{y}<br>Δ if removed: %{x:+.2f}<extra></extra>",
        ))
        fig.update_layout(
            height=max(280, 26 * len(top) + 80),
            xaxis_title="Δ source sub-score if this rule were removed",
            margin=dict(t=20, b=30, l=20, r=40),
            shapes=[dict(
                type="line", x0=0, x1=0, y0=-0.5, y1=len(top) - 0.5,
                line=dict(color="rgba(0,0,0,0.4)", width=1, dash="dot"),
            )],
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Green bars (Δ < 0) = the rule's removal would HURT the source - "
            "it's load-bearing. Red bars (Δ > 0) = the rule is dragging the "
            "source score down."
        )


# =============================================================================
# Tab - CDE Clustering
# =============================================================================

