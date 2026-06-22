"""Step 7 ML Lab tab: Run History.

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
    recommend_dqrs_for_cde,
    simulate_weight_perturbation,
    sklearn_status,
    snapshot_scorecard,
    train_risk_classifier,
)
from src.models import ScorecardResult
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


def _render_tab_run_history(scorecards: Dict[str, ScorecardResult]) -> None:
    _render_explainer(
        "<b>What this does.</b> Captures <b>snapshots</b> of your scorecards "
        "over time so you can compare runs.<br>"
        "&nbsp;&nbsp;• <b>📸 Snapshot</b> stores all current scorecards in "
        "session state (lives until you Restart).<br>"
        "&nbsp;&nbsp;• <b>📂 Upload JSON / CSV</b> <i>(temporarily under "
        "maintenance)</i> - snapshot import is being reworked so runs are "
        "saved automatically; manual upload won't be needed.<br>"
        "&nbsp;&nbsp;• <b>Drift</b> compares two snapshots: <code>PSI</code> "
        "and <code>KS</code> on the row-score distribution, plus per-rule, "
        "per-CDE and per-dimension deltas (flagged when |Δ| ≥ 5 pp)."
    )

    runs: List[Dict[str, Any]] = list(st.session_state.get("ml_lab_runs", []) or [])

    bar_l, bar_m, bar_r, bar_x = st.columns([1.4, 1.4, 1.4, 1])
    with bar_l:
        if st.button("📸 Snapshot current runs", use_container_width=True,
                     key="ml_lab_snap_btn", help="Capture every current scorecard."):
            new = []
            for code, res in scorecards.items():
                dp = st.session_state.data_products[code]
                new.append(snapshot_scorecard(code, dp, res))
            st.session_state.ml_lab_runs = runs + new
            st.success(f"Captured {len(new)} snapshot(s).")
            st.rerun()
    with bar_m:
        # 📂 Snapshot upload (JSON / CSV) is temporarily disabled while the
        # feature is reworked to persist snapshots automatically, so the user
        # won't need to upload anything. The loader functions
        # (load_snapshot_from_json / load_snapshot_from_csv) are retained in
        # src/ml_lab.py for that upcoming work.
        st.button(
            "📂 Upload (under maintenance)",
            use_container_width=True,
            key="ml_lab_uploader_disabled",
            disabled=True,
            help="Snapshot upload is temporarily under maintenance. Snapshots "
                 "will soon be captured automatically - no manual upload needed.",
        )
    with bar_r:
        if runs:
            buf = json.dumps(runs, indent=2, default=str).encode("utf-8")
            st.download_button(
                "💾 Export history (JSON)",
                data=buf, file_name="ml_lab_history.json",
                mime="application/json",
                use_container_width=True,
                key="ml_lab_history_dl",
            )
    with bar_x:
        if runs and st.button("🗑 Clear", use_container_width=True,
                              key="ml_lab_clear_hist",
                              help="Drop every snapshot in session state."):
            st.session_state.ml_lab_runs = []
            st.rerun()

    if not runs:
        _render_empty(
            "No snapshots yet. Use 📸 to capture the current run, then come "
            "back to compute drift. (Snapshot upload is temporarily under "
            "maintenance.)"
        )
        return

    # ---- Snapshot table ----
    snap_df = pd.DataFrame([
        {
            "id": s.get("id"),
            "label": s.get("label"),
            "timestamp": s.get("timestamp"),
            "source": s.get("source"),
            "dp_code": s.get("dp_code"),
            "overall_score": round(float(s.get("overall_score", 0.0)), 2),
            "rows": s.get("total_rows", 0),
            "rules_std": len(s.get("rule_pass_rates", {})),
            "rules_custom": len(s.get("custom_rule_pass_rates", {})),
            "has_hist": s.get("row_score_hist") is not None,
        }
        for s in runs
    ])
    st.markdown("##### 📜 Snapshots in session")
    st.dataframe(snap_df, use_container_width=True, hide_index=True, height=240)

    # ---- Trend chart ----
    # ``filter(None, ...)`` drops falsy values (None / empty string) so the
    # resulting set is ``set[str]`` for sorted() rather than ``set[str | None]``.
    dp_codes = sorted(set(filter(None, (s.get("dp_code") for s in runs))))
    if dp_codes:
        st.markdown("##### 📈 Score trend by Data Product")
        cols = st.columns(min(len(dp_codes), 3))
        for i, c in enumerate(dp_codes):
            sub = [s for s in runs if s.get("dp_code") == c]
            sub.sort(key=lambda s: s.get("timestamp", ""))
            with cols[i % len(cols)]:
                fig = go.Figure(go.Scatter(
                    x=[s.get("timestamp") for s in sub],
                    y=[float(s.get("overall_score", 0.0)) for s in sub],
                    mode="lines+markers",
                    line=dict(color="#6d28d9", width=2),
                    marker=dict(size=9, color="#a855f7"),
                    text=[s.get("label") for s in sub],
                    hovertemplate="<b>%{text}</b><br>%{x}<br>score=%{y:.1f}<extra></extra>",
                ))
                fig.update_layout(
                    height=220,
                    title=dict(text=f"{c}", font=dict(size=14)),
                    yaxis=dict(range=[0, 100], title="overall_score"),
                    margin=dict(t=30, b=20, l=20, r=20),
                )
                st.plotly_chart(fig, use_container_width=True)

    # ---- Drift analyzer ----
    st.markdown("##### 🌊 Drift between two snapshots")
    if len(runs) < 2:
        st.caption("Need at least two snapshots to compute drift.")
        return
    opts = list(range(len(runs)))
    label_for = lambda i: f"{runs[i].get('dp_code', '?')} · {runs[i].get('label', '')}"
    c_a, c_b, c_t = st.columns([2, 2, 1])
    with c_a:
        i_a = st.selectbox(
            "Baseline (A)", opts, format_func=label_for, index=0,
            key="ml_lab_drift_a",
        )
    with c_b:
        # Default to the most recent one
        default_b = len(opts) - 1 if len(opts) > 1 else 0
        i_b = st.selectbox(
            "Compare against (B)", opts, format_func=label_for, index=default_b,
            key="ml_lab_drift_b",
        )
    with c_t:
        threshold = st.number_input(
            "Δ threshold (pp)", min_value=0.0, max_value=50.0, value=5.0, step=0.5,
            key="ml_lab_drift_th",
            help="Per-rule / per-CDE / per-dim deltas larger than this are flagged.",
        )

    if i_a == i_b:
        st.info("Select two different snapshots to compare.")
        return

    snap_a = runs[i_a]
    snap_b = runs[i_b]
    if snap_a.get("dp_code") != snap_b.get("dp_code"):
        st.warning(
            f"⚠ You're comparing snapshots of different DPs "
            f"(**{snap_a.get('dp_code')}** vs **{snap_b.get('dp_code')}**). "
            "Drift below may be partially nonsensical."
        )

    with st.spinner("📜 Computing drift between runs..."):
        drift = compute_drift(snap_a, snap_b, rule_delta_threshold=float(threshold))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Score Δ (B − A)", f"{drift['overall_score_delta']:+.2f}")
    if drift["psi"] is not None:
        psi_label = (
            "negligible" if drift["psi"] < 0.1
            else "moderate" if drift["psi"] < 0.25
            else "significant"
        )
        m2.metric("PSI", f"{drift['psi']:.3f}", delta=psi_label, delta_color="off")
    else:
        m2.metric("PSI", "-", delta="histograms missing", delta_color="off")
    if drift["ks"] is not None:
        m3.metric("KS distance", f"{drift['ks']:.3f}")
    else:
        m3.metric("KS distance", "-")
    flagged_rules = int(drift["rule_table"]["flagged"].sum()) if not drift["rule_table"].empty else 0
    m4.metric("Flagged rules", flagged_rules)

    if drift["psi"] is not None:
        st.caption(
            "PSI conventions: < 0.10 negligible · 0.10–0.25 moderate · "
            "> 0.25 significant - investigate."
        )

    tab_r, tab_c, tab_d = st.tabs([
        "🧮 Rules drift", "🌿 CDE drift", "🎯 Dimension drift",
    ])
    for tab, df_ in zip(
        (tab_r, tab_c, tab_d),
        (drift["rule_table"], drift["cde_table"], drift["dimension_table"]),
    ):
        with tab:
            if df_.empty:
                st.caption("No data in this scope.")
                continue
            st.dataframe(
                df_,
                use_container_width=True, hide_index=True, height=320,
                column_config={
                    "score_a": st.column_config.NumberColumn(format="%.2f"),
                    "score_b": st.column_config.NumberColumn(format="%.2f"),
                    "delta": st.column_config.NumberColumn(format="%+.2f"),
                },
            )


# =============================================================================
# Tab - Risk Model (logistic regression on RED rows)
# =============================================================================

