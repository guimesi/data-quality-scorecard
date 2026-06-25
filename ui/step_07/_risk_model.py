"""Step 7 ML Lab tab: Risk Model.

Extracted from the monolithic ``ui/step_07_ml_lab.py`` so each tab lives
in its own file and stays small enough to navigate. The orchestrating
``render()`` (still in :mod:`ui.step_07_ml_lab`) wires this tab into the
``st.tabs(...)`` row at the top.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from config.settings import SETTINGS
from src.ml_lab import (
    train_risk_classifier,
)
from ui.step_07._shared import (
    _render_empty,
    _render_explainer,
)
from utils.colors import STATUS_GREEN, STATUS_RED


def _render_tab_risk_model(code: str, dp, config, result, flags=None, rule_meta=None) -> None:
    _render_explainer(
        "<b>What this does.</b> Trains a small logistic regression where:<br>"
        "&nbsp;&nbsp;• <b>Features</b> = per-row pass/fail flags (1 = rule "
        "failed).<br>"
        "&nbsp;&nbsp;• <b>Target</b> = the row is <b>RED</b> "
        f"(<code>row_score &lt; {SETTINGS.threshold_yellow}</code>).<br>"
        "The coefficients tell you which RULE FAILURES are most "
        "<b>discriminative</b> of RED rows - which can differ from the "
        "configured weights. A small-weight rule with a big coefficient is "
        "an <b>underweighted high-signal rule</b> worth re-discussing."
    )

    use_sklearn = bool(st.session_state.get("ml_lab_use_sklearn", False))
    with st.spinner("🧠 Training the risk model..."):
        report = train_risk_classifier(
            dp, config, result, use_sklearn=use_sklearn,
            flags=flags, rule_meta=rule_meta,
        )

    if report["n_rules"] == 0:
        _render_empty("No rules were evaluated, so the risk model can't be trained.")
        return

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Accuracy", f"{report['accuracy']*100:.1f}%")
    m2.metric("Base rate (RED)", f"{report['base_rate']*100:.1f}%")
    cm = report["confusion"]
    m3.metric("True positives", f"{cm['tp']:,}")
    m4.metric("False positives", f"{cm['fp']:,}")
    m5.metric(
        "Backend",
        "sklearn LR" if report["sklearn_used"] else "numpy LR",
    )

    st.markdown("##### 🧠 Rule coefficients (descriminative power)")
    st.caption(
        "Coefficient > 0 → failing this rule INCREASES the row's risk of "
        "being RED. ``odds_ratio`` = e^coefficient - how many times the "
        "odds of RED multiply when the rule fails."
    )
    st.caption(
        "⚠️ The **sklearn** and **numpy** backends are not calibrated to match "
        "(different solver and regularization), so coefficient magnitudes - and "
        "sometimes the exact ranking - can differ between them. Read the "
        "ranking *within* one backend; don't compare values across the toggle."
    )
    coef = report["coef_table"]
    st.dataframe(
        coef,
        use_container_width=True, hide_index=True, height=360,
        column_config={
            "coefficient": st.column_config.NumberColumn(format="%+.3f"),
            # %.3g (not %.2f): odds_ratio = e^coefficient and the coefficient
            # is clipped to +/-50, so it can span ~1e-22 to ~1e21. %.2f turned
            # those into a 22-digit decimal or a misleading "0.00"; %.3g keeps
            # 3 sig-figs and switches to scientific notation at the extremes.
            "odds_ratio": st.column_config.NumberColumn(format="%.3g"),
            "weight_pct": st.column_config.NumberColumn(format="%.2f%%"),
        },
    )

    if not coef.empty:
        # Visual: bar chart of the top 15 by |coefficient|
        top = coef.head(15).copy()
        fig = go.Figure(go.Bar(
            x=top["coefficient"][::-1],
            y=(top["label"] + " - " + top["source"])[::-1],
            orientation="h",
            marker_color=[STATUS_RED if c > 0 else STATUS_GREEN for c in top["coefficient"][::-1]],
            text=[f"{c:+.2f}" for c in top["coefficient"][::-1]],
            textposition="outside",
            hovertemplate="%{y}<br>coef=%{x:+.3f}<extra></extra>",
        ))
        fig.update_layout(
            height=max(280, 26 * len(top) + 80),
            xaxis_title="logistic-regression coefficient",
            margin=dict(t=20, b=30, l=20, r=40),
            shapes=[dict(
                type="line", x0=0, x1=0, y0=-0.5, y1=len(top) - 0.5,
                line=dict(color="rgba(0,0,0,0.4)", width=1, dash="dot"),
            )],
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "🔴 Red bars → failing the rule makes the row more likely RED. "
            "🟢 Green bars → failing the rule (counter-intuitively) is "
            "associated with non-RED rows (often because the rule fails "
            "uniformly across the whole DP)."
        )

    # Risk distribution histogram
    preds = report["predictions"]
    if len(preds) > 0:
        st.markdown("##### 📈 Predicted risk probability across rows")
        fig = go.Figure(go.Histogram(
            x=preds, nbinsx=30, marker_color="rgba(124, 58, 237, 0.55)",
        ))
        fig.add_vline(
            x=0.5, line_color="rgba(0,0,0,0.5)", line_dash="dot",
            annotation_text="decision threshold 0.5",
            annotation_position="top right",
        )
        fig.update_layout(
            height=260, bargap=0.05,
            xaxis_title="P(row is RED)", yaxis_title="count",
            margin=dict(t=20, b=30, l=20, r=20),
        )
        st.plotly_chart(fig, use_container_width=True)


# =============================================================================
# Tab - DQR Recommendations
# =============================================================================

