"""Step 7 ML Lab tab: Cde Clusters.

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
from utils.helpers import section_header
from utils.session_state import goto, prev_step, restart_app


def _render_tab_cde_clusters(code: str, dp, config, result) -> None:
    _render_explainer(
        "<b>What this does.</b> Groups your selected CDEs into clusters by "
        "their <b>profile signature</b> (null %, distinct ratio, duplicate "
        "ratio, type) plus their <b>average pass-rate</b>. Features are "
        "robust-standardized (median / MAD) and clustered via a small "
        "<b>k-means</b>; the 2-D scatter is a PCA projection (numpy SVD). "
        "CDEs that land near each other behave similarly - useful to spot "
        "groups of columns you can audit together."
    )

    available = [c for c in (config.cdes or []) if c in dp.profiles]
    if len(available) < 2:
        _render_empty(
            "At least two CDEs are needed for a meaningful clustering. "
            "This Data Product currently has "
            f"{len(available)} CDE(s) - add more upstream in Step 3 and "
            "rerun."
        )
        return

    max_k = max(2, min(6, len(available)))
    if max_k <= 2:
        k = 2
        st.caption("Only two CDEs available - using k=2.")
    else:
        k = st.slider(
            "Clusters (k)", 2, max_k, min(3, max_k),
            help="Number of CDE groups to discover.",
            key=f"ml_cde_k_{code}",
        )

    use_sklearn = bool(st.session_state.get("ml_lab_use_sklearn", False))
    with st.spinner("🌿 Clustering CDE profiles..."):
        out = compute_cde_profile_clusters(
            dp, config, result, n_clusters=int(k), use_sklearn=use_sklearn,
        )
    if out.get("sklearn_used"):
        st.caption(
            "🔬 **sklearn engaged.** Clustering by `sklearn.cluster.KMeans` "
            "and projection by `sklearn.decomposition.PCA`."
        )
    df = out["table"]
    if df.empty:
        _render_empty("Unable to build CDE feature vectors for this Data Product.")
        return

    ev = out.get("explained_variance", (0.0, 0.0))
    st.caption(
        f"PC1 explains {ev[0]*100:.1f}% of the variance; "
        f"PC2 explains {ev[1]*100:.1f}%."
    )

    palette = ["#6366f1", "#22c55e", "#f59e0b", "#ec4899", "#06b6d4", "#a855f7"]
    fig = go.Figure()
    for cl in sorted(df["cluster"].unique()):
        sub = df[df["cluster"] == cl]
        fig.add_trace(go.Scatter(
            x=sub["pc1"], y=sub["pc2"],
            mode="markers+text",
            marker=dict(
                size=14, color=palette[int(cl) % len(palette)],
                line=dict(color="white", width=1.5),
            ),
            text=sub["cde"],
            textposition="top center",
            textfont=dict(size=10),
            name=f"Cluster {int(cl)}",
            customdata=sub[["type", "null_pct", "cde_score"]].to_numpy(),
            hovertemplate=(
                "<b>%{text}</b><br>type=%{customdata[0]}<br>"
                "null %=%{customdata[1]:.1f}<br>"
                "cde_score=%{customdata[2]:.1f}<extra></extra>"
            ),
        ))
    fig.update_layout(
        height=420,
        xaxis_title="PC1 (profile + score signature)",
        yaxis_title="PC2",
        margin=dict(t=20, b=30, l=20, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("##### 🌿 Cluster summary")
    summary = (
        df.groupby("cluster")[["null_pct", "distinct_ratio_pct",
                              "duplicate_ratio_pct", "cde_score"]]
          .mean()
          .round(2)
          .reset_index()
    )
    counts = df.groupby("cluster")["cde"].apply(lambda s: ", ".join(s)).reset_index(
        name="cdes_in_cluster",
    )
    summary = summary.merge(counts, on="cluster", how="left")
    st.dataframe(summary, use_container_width=True, hide_index=True)
    st.caption(
        "Clusters with higher null/duplicate ratios and lower cde_score "
        "are the ones to audit first - they are the columns behaving "
        "similarly bad."
    )


# =============================================================================
# Tab - Weight Sensitivity
# =============================================================================

