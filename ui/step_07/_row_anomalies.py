"""Step 7 ML Lab tab: Row Anomalies.

Extracted from the monolithic ``ui/step_07_ml_lab.py`` so each tab lives
in its own file and stays small enough to navigate. The orchestrating
``render()`` (still in :mod:`ui.step_07_ml_lab`) wires this tab into the
``st.tabs(...)`` row at the top.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src.ml_lab import (
    compute_row_anomalies,
)
from ui.step_07._shared import (
    _render_empty,
    _render_explainer,
)
from utils.colors import STATUS_RED


def _render_tab_row_anomalies(code: str, dp, config, result, flags=None, rule_meta=None) -> None:
    _render_explainer(
        "<b>What this does.</b> Ranks rows by an <b>anomaly score</b> that "
        "blends two signals:<br>"
        "&nbsp;&nbsp;• <b>Robust z-score</b> on the row's quality score "
        "(MAD-based, resilient to outliers).<br>"
        "&nbsp;&nbsp;• <b>Rare-failure score</b> = <code>Σ -log(fail_rate)</code> "
        "over the rules the row failed - a row that fails a rule 99 % of "
        "rows pass is far more suspicious than one that fails a rule "
        "everyone fails."
    )

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        top_n = st.slider(
            "Rows to inspect", 10, 200, 50, 10,
            help="How many of the most anomalous rows to surface.",
            key=f"ml_top_n_{code}",
        )
    with c2:
        rarity_weight = st.slider(
            "Rarity weight (α)", 0.0, 1.0, 0.7, 0.05,
            help="α = 0 → rank by row_score only. α = 1 → rank by rare-failure "
                 "pattern only. Default 0.7 emphasises rare combinations.",
            key=f"ml_rarity_w_{code}",
        )
    with c3:
        st.markdown(
            "<div style='padding-top:1.6em;color:rgba(49,51,63,0.55);"
            "font-size:0.85em;'>Re-runs instantly on slider change.</div>",
            unsafe_allow_html=True,
        )

    use_sklearn = bool(st.session_state.get("ml_lab_use_sklearn", False))
    with st.spinner("🔎 Detecting row anomalies..."):
        report = compute_row_anomalies(
            dp, config, result, top_n=int(top_n), rarity_weight=float(rarity_weight),
            use_sklearn=use_sklearn, flags=flags, rule_meta=rule_meta,
        )
    if report.get("sklearn_used"):
        st.caption(
            "🔬 **sklearn engaged.** IsolationForest score blended into the "
            "composite anomaly score at 30% weight (`iso_forest_score` "
            "column visible in the table)."
        )

    if report["n_rules_evaluated"] == 0:
        _render_empty(
            "No rules were successfully evaluated for this Data Product, "
            "so there are no failure patterns to mine. Configure at least "
            "one Standard or Custom DQR upstream and try again."
        )
        return

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Rules used", f"{report['n_rules_evaluated']}")
    m2.metric("Total rows", f"{report['n_rows_total']:,}")
    m3.metric("Anomalies shown", f"{len(report['table']):,}")
    median_anom = float(report["table"]["anomaly_score"].median()) if len(report["table"]) else 0.0
    m4.metric("Median anomaly", f"{median_anom:.2f}")

    st.markdown("##### 🔎 Top anomalous rows")
    st.caption(
        "Sorted by anomaly score (higher = stranger). The "
        "<b>top_rare_failures</b> column lists the rules this row failed "
        "ranked by rarity - that's WHY the row stands out.",
        unsafe_allow_html=True,
    )
    st.dataframe(
        report["table"],
        use_container_width=True,
        height=420,
        column_config={
            "row_score": st.column_config.ProgressColumn(
                "row_score", min_value=0, max_value=100, format="%.1f",
            ),
            "anomaly_score": st.column_config.ProgressColumn(
                "anomaly_score", min_value=0.0, max_value=1.0, format="%.3f",
            ),
            "robust_z": st.column_config.NumberColumn(format="%.2f"),
            "rarity_score": st.column_config.NumberColumn(format="%.2f"),
        },
    )

    cleft, cright = st.columns([3, 2])
    with cleft:
        st.markdown("##### 📈 Row-score distribution with anomalies highlighted")
        scores = result.row_scores
        if len(scores) > 0:
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=scores, nbinsx=40,
                marker_color="rgba(99, 102, 241, 0.45)",
                name="All rows",
            ))
            anom_scores = report["table"]["row_score"]
            fig.add_trace(go.Scatter(
                x=anom_scores,
                y=np.zeros(len(anom_scores)) + 1,
                mode="markers",
                marker=dict(
                    color=STATUS_RED, size=8, symbol="diamond",
                    line=dict(color="white", width=1),
                ),
                name="Flagged anomalies",
                hovertemplate="row_score=%{x:.1f}<extra></extra>",
            ))
            fig.update_layout(
                height=320, bargap=0.05, showlegend=True,
                xaxis_title="row_score", yaxis_title="count",
                margin=dict(t=20, b=30, l=20, r=20),
            )
            st.plotly_chart(fig, use_container_width=True)
    with cright:
        st.markdown("##### 🧮 Per-rule fail rate (rarity context)")
        st.caption(
            "Rules at the TOP are the rarest failures - when they fail, "
            "the row is unusual."
        )
        fr = report["rule_fail_rate_pct"].to_frame("fail_rate_pct").reset_index(
            names="rule_id",
        )
        # Add a human label column from rule_meta
        meta = report["rule_meta"]
        fr["label"] = fr["rule_id"].map(
            lambda rid: f"{meta.get(rid, {}).get('source', '')[:3].upper()} · "
                        f"{meta.get(rid, {}).get('label', rid)}"
        )
        fr = fr[["label", "fail_rate_pct"]]
        st.dataframe(
            fr,
            use_container_width=True,
            hide_index=True,
            height=320,
            column_config={
                "fail_rate_pct": st.column_config.ProgressColumn(
                    "fail rate (%)", min_value=0, max_value=100, format="%.1f%%",
                ),
            },
        )


# =============================================================================
# Tab - Rule Impact
# =============================================================================

