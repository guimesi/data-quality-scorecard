"""Step 7 ML Lab tab: Cross Dp.

Extracted from the monolithic ``ui/step_07_ml_lab.py`` so each tab lives
in its own file and stays small enough to navigate. The orchestrating
``render()`` (still in :mod:`ui.step_07_ml_lab`) wires this tab into the
``st.tabs(...)`` row at the top.
"""
from __future__ import annotations

from typing import Dict

import plotly.graph_objects as go
import streamlit as st

from src.ml_lab import (
    compare_data_products,
)
from src.models import ScorecardResult
from ui.step_07._shared import (
    _render_empty,
    _render_explainer,
)
from utils.colors import STATUS_GREEN, STATUS_RED


def _render_tab_cross_dp(scorecards: Dict[str, ScorecardResult]) -> None:
    _render_explainer(
        "<b>What this does.</b> Compares every Data Product's overall "
        "score using a <b>robust z-score</b> (MAD-based). With only a few "
        "Data Products this is informational - a DP flagged as "
        "<i>Anomalous</i> isn't necessarily bad, it just stands apart "
        "from its peers and deserves a second look."
    )

    df = compare_data_products(scorecards)
    if df.empty:
        _render_empty("No scorecards are available to compare.")
        return

    palette = {"Anomalous": STATUS_RED, "In-line": STATUS_GREEN, "Single DP": "#6366f1"}
    # Non-color channel (a11y): hatch each bar by status so the categories are
    # distinguishable without relying on colour alone.
    hatch = {"Anomalous": "x", "In-line": "", "Single DP": "/"}
    fig = go.Figure(go.Bar(
        x=df["data_product"], y=df["overall_score"],
        marker=dict(
            color=[palette.get(s, "#6366f1") for s in df["status"]],
            pattern=dict(shape=[hatch.get(s, "") for s in df["status"]]),
        ),
        text=[f"{v:.1f}" for v in df["overall_score"]],
        textposition="outside",
        hovertemplate=(
            "<b>%{x}</b><br>overall=%{y:.1f}<br>"
            "robust_z=%{customdata[0]:.2f}<br>"
            "status=%{customdata[1]}<extra></extra>"
        ),
        customdata=df[["robust_z", "status"]].to_numpy(),
    ))
    fig.update_layout(
        height=320,
        yaxis=dict(range=[0, 105], title="overall_score"),
        margin=dict(t=20, b=20, l=20, r=20),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Status uses **colour and hatch** (so it reads without relying on colour "
        "alone): ✕-hatched = **Anomalous**, diagonal = **Single DP**, plain = "
        "**In-line**. The full status per Data Product is in the table below."
    )

    st.markdown("##### 🔭 Comparison table")
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "overall_score": st.column_config.ProgressColumn(
                "overall_score", min_value=0, max_value=100, format="%.1f",
            ),
            "rows_green_pct": st.column_config.NumberColumn(format="%.1f%%"),
            "rows_yellow_pct": st.column_config.NumberColumn(format="%.1f%%"),
            "rows_red_pct": st.column_config.NumberColumn(format="%.1f%%"),
            "robust_z": st.column_config.NumberColumn(format="%+.2f"),
        },
    )
    anomalies = df[df["status"] == "Anomalous"]["data_product"].tolist()
    if anomalies:
        st.warning(
            "🚨 Flagged as anomalous (|robust_z| > 1.5): **"
            + ", ".join(anomalies) + "**. "
            "These DPs sit far from the median quality - worth a closer look."
        )
    else:
        st.success("✅ No DP stands out at the |robust_z| > 1.5 threshold.")


# =============================================================================
# Main renderer
# =============================================================================

# =============================================================================
# Tab - Run History (snapshot + upload + drift)
# =============================================================================

