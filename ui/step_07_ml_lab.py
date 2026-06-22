"""
Step 7: ML Lab (BETA) - orchestration.

Experimental, read-only Machine-Learning / statistical-analytics sandbox.
Does NOT alter the rules-based scorecard in any way; it only OBSERVES the
artefacts the main flow already produced and surfaces complementary
insights across 9 tabs.

The 9 tabs are partitioned into :mod:`ui.step_07` (one module per tab) so
each file stays small. This module owns:

- the header / banner / Data-Product picker
- the ``render()`` entry point that wires the tabs into ``st.tabs(...)``
- the bottom navigation (Back / Restart / Back to Dashboard)

It re-exports the per-tab ``_render_tab_*`` callables from the
:mod:`ui.step_07` package so existing tests that import them directly
from ``ui.step_07_ml_lab`` keep working unchanged.

Algorithms live in :mod:`src.ml_lab`; this file is the Streamlit layer.
"""
from __future__ import annotations

import html
from typing import Dict, List

import streamlit as st

from src.ml_lab import build_rule_flag_matrix, sklearn_status
from src.models import ScorecardResult
from ui.step_07._cde_clusters import _render_tab_cde_clusters
from ui.step_07._cross_dp import _render_tab_cross_dp
from ui.step_07._recommendations import _render_tab_recommendations
from ui.step_07._risk_model import _render_tab_risk_model
from ui.step_07._row_anomalies import _render_tab_row_anomalies
from ui.step_07._row_explain import _render_tab_row_explain
from ui.step_07._rule_impact import _render_tab_rule_impact
from ui.step_07._run_history import _render_tab_run_history
from ui.step_07._shared import (
    _SYSTEM_ICONS,
    _ensure_scorecards,
    _inject_css,
    _render_banner,
    _render_empty,
    _render_explainer,
)
from ui.step_07._weight_sensitivity import _render_tab_weight_sensitivity
from utils.helpers import section_header
from utils.session_state import goto, prev_step, restart_app
from utils.ui_components import render_restart_button


def _render_header() -> None:
    sk = sklearn_status()
    sk_badge = (
        f"<span class='lab-tag' style='margin-left:0.5em;'>"
        f"🔬 sklearn {sk['version']}</span>"
        if sk["available"] else
        "<span class='lab-tag' style='margin-left:0.5em;background:rgba(0,0,0,0.06);color:#64748b;'>"
        "sklearn not installed</span>"
    )
    st.markdown(
        f'<div class="lab-pill">🧪 Experimental · ML Lab '
        f'<span class="lab-beta-tag">BETA</span>{sk_badge}</div>',
        unsafe_allow_html=True,
    )
    section_header(
        "ML Lab - Data Quality Intelligence (beta)",
        "Unsupervised analytics, run-history drift, supervised risk and "
        "SHAP-like row explainability - all read-only on top of your "
        "rules-based scorecard.",
    )
    _render_banner()


def _render_dp_picker(scorecards: Dict[str, ScorecardResult]) -> str:
    options: List[str] = list(scorecards.keys())
    pretty = [
        f"{_SYSTEM_ICONS.get(c, '📦')}  {c}"
        for c in options
    ]
    idx_default = 0
    col_pick, col_sk = st.columns([3, 2])
    with col_pick:
        chosen = st.radio(
            "Select a Data Product to analyse",
            options=list(range(len(options))),
            format_func=lambda i: pretty[i],
            index=idx_default,
            horizontal=True,
            key="ml_lab_dp_pick",
        )
    with col_sk:
        sk = sklearn_status()
        if sk["available"]:
            st.toggle(
                "🔬 Use scikit-learn when available",
                value=st.session_state.get("ml_lab_use_sklearn", False),
                key="ml_lab_use_sklearn",
                help="Switches Row Anomalies → IsolationForest, "
                     "CDE Clustering → KMeans + PCA, Risk Model → "
                     "sklearn LogisticRegression. Numpy fallbacks are "
                     "used when this is off OR when sklearn is missing.",
            )
        else:
            st.caption(
                "🔬 scikit-learn not installed - algorithms use the "
                "numpy fallbacks. Install it (`pip install scikit-learn`) "
                "to unlock the sklearn toggle."
            )
    return options[int(chosen)]


def render() -> None:
    _inject_css()
    _render_header()

    scorecards = _ensure_scorecards()
    if not scorecards:
        _render_empty(
            "The ML Lab needs at least one Data Product with rules configured "
            "and a scorecard computed. Go back to Step 6 (Dashboard) - it "
            "will compute scorecards on render - then come back here."
        )
        _nav()
        return

    code = _render_dp_picker(scorecards)
    dp = st.session_state.data_products[code]
    config = st.session_state.configs[code]
    result = scorecards[code]

    # Build the per-row rule-flag matrix ONCE and reuse it across the tabs that
    # need it (Row Anomalies, Risk Model, Row Explainability). Without this each
    # of those tabs rebuilt it, running the rule engine 3x per rerun. The
    # reference cache is warm here (scorecards were just computed by
    # _ensure_scorecards), so this single build equals what each tab would
    # otherwise compute independently.
    with st.spinner("⚙️ Evaluating rules for the ML Lab..."):
        flags, rule_meta = build_rule_flag_matrix(dp, config)

    # Per-DP overview (mirrors the dashboard's quick-glance metrics without
    # duplicating its visualizations).
    with st.container(border=True):
        st.markdown(
            f'<div class="lab-card-title">'
            f'<span class="lab-icon">{_SYSTEM_ICONS.get(code, "📦")}</span>'
            f'<span class="lab-title">{html.escape(dp.name)} '
            f'<span class="lab-tag">{code}</span></span>'
            f'<span class="lab-tag" style="margin-left:auto;">'
            f'{len(config.cdes or [])} CDEs · '
            f'{len(config.assignments)} std · '
            f'{len(config.custom_assignments)} custom</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Overall score", f"{result.overall_score:.1f}")
        m2.metric("Total rows", f"{result.total_rows:,}")
        m3.metric("🔴 Red %",
                  f"{result.rows_red / max(result.total_rows, 1) * 100:.1f}%")
        if result.standard_score is not None:
            m4.metric("Standard sub-score", f"{result.standard_score:.1f}")
        elif result.custom_score is not None:
            m4.metric("Custom sub-score", f"{result.custom_score:.1f}")
        else:
            m4.metric("Sub-score", "-")

    (
        tab_anom, tab_impact, tab_clust, tab_wsens, tab_xdp,
        tab_hist, tab_risk, tab_reco, tab_explain,
    ) = st.tabs([
        "🔎 Row Anomalies",
        "🎯 Rule Impact",
        "🌿 CDE Clustering",
        "⚖️ Weight Sensitivity",
        "🔭 Cross-DP Comparison",
        "📜 Run History",
        "🧠 Risk Model",
        "💡 DQR Recommendations",
        "🧩 Row Explainability",
    ])

    with tab_anom:
        _render_tab_row_anomalies(code, dp, config, result, flags, rule_meta)
    with tab_impact:
        _render_tab_rule_impact(code, dp, config, result)
    with tab_clust:
        _render_tab_cde_clusters(code, dp, config, result)
    with tab_wsens:
        _render_tab_weight_sensitivity(code, dp, config, result)
    with tab_xdp:
        _render_tab_cross_dp(scorecards)
    with tab_hist:
        _render_tab_run_history(scorecards)
    with tab_risk:
        _render_tab_risk_model(code, dp, config, result, flags, rule_meta)
    with tab_reco:
        _render_tab_recommendations(code, dp, config, result)
    with tab_explain:
        _render_tab_row_explain(code, dp, config, result, flags, rule_meta)

    st.markdown("---")
    _nav()


def _nav() -> None:
    c1, c2, c3, c_mid = st.columns([1, 1, 2, 4])
    with c1:
        if st.button("⬅ Back", use_container_width=True, key="ml_lab_back"):
            prev_step()
    with c2:
        render_restart_button(restart_app, key="restart_confirm_mllab")
    with c3:
        if st.button("📊 Back to Dashboard", use_container_width=True,
                     key="ml_lab_to_dashboard",
                     help="Return to the rules-based scorecard dashboard."):
            goto("dashboard")
    with c_mid:
        st.markdown(
            "<div style='text-align: center; padding-top: 0.55em; "
            "color: rgba(76, 29, 149, 0.7); font-size: 0.85em;'>"
            "🧪 Experimental results - use as a complement to the "
            "rules-based scorecard, not as a replacement."
            "</div>",
            unsafe_allow_html=True,
        )
