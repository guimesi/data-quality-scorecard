"""Step 7 ML Lab tab: Weight Sensitivity.

Extracted from the monolithic ``ui/step_07_ml_lab.py`` so each tab lives
in its own file and stays small enough to navigate. The orchestrating
``render()`` (still in :mod:`ui.step_07_ml_lab`) wires this tab into the
``st.tabs(...)`` row at the top.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.ml_lab import (
    simulate_weight_perturbation,
)
from ui.step_07._shared import (
    _render_empty,
    _render_explainer,
)
from utils.colors import STATUS_RED


def _render_tab_weight_sensitivity(code: str, dp, config, result) -> None:
    _render_explainer(
        "<b>What this does.</b> Asks <b>“how fragile is my Standard "
        "sub-score to the exact weights I chose?”</b> by drawing random "
        "weight vectors from a Dirichlet anchored at your current "
        "weights, then computing the resulting sub-score for each draw. "
        "If the histogram is tight around the baseline, your score is "
        "robust. If it's wide, small weight changes meaningfully move "
        "the score - your current weights matter a lot."
    )

    if not config.assignments or not result.rule_pass_rates:
        _render_empty(
            "Weight sensitivity is computed on the Standard-source rules. "
            "This Data Product has no Standard DQRs configured."
        )
        return

    c1, c2 = st.columns(2)
    with c1:
        n_sim = st.slider(
            "Simulations", 50, 1000, 300, 50,
            help="Number of Monte-Carlo draws.",
            key=f"ml_wsens_n_{code}",
        )
    with c2:
        jitter = st.slider(
            "Jitter (perturbation strength)", 0.05, 0.6, 0.25, 0.05,
            help="Higher = weights drift further from your current setup.",
            key=f"ml_wsens_jitter_{code}",
        )

    with st.spinner("⚖️ Running the weight-sensitivity simulation..."):
        sim = simulate_weight_perturbation(
            config, result,
            n_simulations=int(n_sim), jitter=float(jitter),
        )
    scores = sim["scores"]
    baseline = sim["baseline"]
    summary = sim["summary"]

    if len(scores) == 0 or baseline is None:
        _render_empty("Not enough data to simulate weight perturbations.")
        return

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Baseline", f"{baseline:.1f}")
    m2.metric("Mean", f"{summary['mean']:.1f}")
    m3.metric("Std", f"{summary['std']:.2f}")
    m4.metric("P05", f"{summary['p05']:.1f}")
    m5.metric("P95", f"{summary['p95']:.1f}")

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=scores, nbinsx=40,
        marker_color="rgba(99, 102, 241, 0.55)",
        name="Simulated scores",
    ))
    fig.add_vline(
        x=baseline, line_color=STATUS_RED, line_width=2,
        annotation_text=f"baseline {baseline:.1f}",
        annotation_position="top",
    )
    fig.add_vline(
        x=summary["p05"], line_color="rgba(0,0,0,0.5)", line_dash="dot",
        annotation_text="P05", annotation_position="bottom right",
    )
    fig.add_vline(
        x=summary["p95"], line_color="rgba(0,0,0,0.5)", line_dash="dot",
        annotation_text="P95", annotation_position="bottom left",
    )
    fig.update_layout(
        height=320, bargap=0.05, showlegend=False,
        xaxis_title="Standard sub-score",
        yaxis_title="count",
        margin=dict(t=30, b=30, l=20, r=20),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "If P95 − P05 is small (a few points), your score is robust. "
        "If it spans a 10-15+ point range, the current weighting is "
        "fragile and worth re-discussing with the data owner. "
        "The draw uses a fixed random seed, so the histogram is reproducible "
        "run-to-run - it won't reshuffle on every interaction."
    )


# =============================================================================
# Tab - Cross-DP comparison
# =============================================================================

