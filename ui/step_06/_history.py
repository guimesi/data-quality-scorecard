"""Step 6 run-history UI: auto-recording, drop alert, History tab.

Thin Streamlit layer over :mod:`src.run_history`. Recording happens once
per render pass (session-cached fingerprints keep reruns free); the drop
alert sits on the DP card so a regression is visible without opening any
tab; the History tab shows the persisted trend, the run log (who / when /
config), and a "what changed" diff against the previous run reusing the
ML Lab's :func:`src.ml_lab.compute_drift`.
"""
from __future__ import annotations

import html
from typing import Dict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.settings import SETTINGS
from src.run_history import (
    config_fingerprint,
    load_history,
    record_run_if_new,
    result_fingerprint,
    score_drop,
)

# session_state key: dp_code -> (config_fingerprint, result_fingerprint) of
# the last run this session already recorded, so dashboard reruns (tab
# clicks, drill-downs) don't re-read the store on every pass.
_RECORD_CACHE_KEY = "_run_history_recorded"


def _record_runs(scorecards: Dict[str, object]) -> None:
    """Persist one snapshot per freshly computed scorecard (deduplicated)."""
    domain_code = str(st.session_state.get("domain", "") or "")
    cache = st.session_state.setdefault(_RECORD_CACHE_KEY, {})
    for code, result in scorecards.items():
        dp = st.session_state.data_products.get(code)
        cfg = st.session_state.configs.get(code)
        if dp is None or cfg is None:
            continue
        key = (config_fingerprint(cfg), result_fingerprint(result))
        if cache.get(code) == key:
            continue
        record_run_if_new(code, dp, result, cfg, domain_code)
        cache[code] = key


def _render_drop_alert(code: str) -> None:
    """Banner on the DP card when the score fell vs the previous run."""
    drop = score_drop(load_history(code))
    if drop is None or drop["delta"] > -SETTINGS.drop_alert_pp:
        return
    context = (
        " ⚠ The configuration also changed between these runs - review the "
        "History tab before blaming the data."
        if drop["config_changed"] else ""
    )
    st.error(
        f"📉 **Score dropped {abs(drop['delta']):.1f} pp** vs the previous "
        f"run: {drop['prev_score']:.1f} → {drop['curr_score']:.1f} "
        f"(previous run {drop['prev_ts']} by {drop['prev_username']})."
        f"{context} Details in the **History** tab."
    )


def _render_history_tab(code: str) -> None:
    history = load_history(code)
    if not history:
        st.caption(
            "No persisted runs yet - history builds up automatically every "
            "time this scorecard is computed (deduplicated: reruns of an "
            "unchanged dashboard record nothing) and survives Restart."
        )
        return

    payloads = [r.get("payload") or {} for r in history]
    scores = [float(p.get("overall_score", 0.0)) for p in payloads]
    ts = [r.get("ts", "") for r in history]
    users = [r.get("username", "") for r in history]
    hashes = [r.get("config_hash", "") for r in history]
    changed = [i > 0 and hashes[i] != hashes[i - 1] for i in range(len(history))]

    # ---- Trend ----
    fig = go.Figure(go.Scatter(
        x=ts, y=scores, mode="lines+markers",
        line=dict(color="#3b82f6", width=2),
        marker=dict(
            size=10, color="#3b82f6",
            symbol=["diamond" if c else "circle" for c in changed],
        ),
        customdata=[
            [users[i], hashes[i][:8], "yes" if changed[i] else "no"]
            for i in range(len(history))
        ],
        hovertemplate=(
            "%{x}<br>score=%{y:.1f}<br>user=%{customdata[0]}"
            "<br>config=%{customdata[1]} (changed: %{customdata[2]})"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        height=260,
        yaxis=dict(range=[0, 105], title="Overall score"),
        margin=dict(t=20, b=20, l=20, r=20),
    )
    st.plotly_chart(fig, use_container_width=True, key=f"hist_chart_{code}")
    st.caption(
        "◆ marker = the configuration changed vs the previous run. Alert "
        f"threshold: drop ≥ {SETTINGS.drop_alert_pp:.0f} pp shows a banner "
        "on this card."
    )

    # ---- Run log ----
    rows = []
    for i, r in enumerate(history):
        rows.append({
            "Run (UTC)": ts[i],
            "User": users[i],
            "Score": round(scores[i], 2),
            "Δ vs prev": round(scores[i] - scores[i - 1], 2) if i > 0 else None,
            "Config": hashes[i][:8],
            "Config changed": "yes" if changed[i] else "",
        })
    st.dataframe(
        pd.DataFrame(rows).iloc[::-1],  # newest first
        use_container_width=True, hide_index=True, height=220,
        column_config={
            "Score": st.column_config.NumberColumn(format="%.2f"),
            "Δ vs prev": st.column_config.NumberColumn(format="%+.2f"),
        },
    )

    # ---- What changed vs previous run ----
    if len(history) < 2:
        return
    # Imported lazily: ml_lab pulls optional heavy deps (sklearn detection).
    from src.ml_lab import compute_drift

    st.markdown("##### 🔍 What changed vs the previous run")
    drift = compute_drift(payloads[-2], payloads[-1], rule_delta_threshold=5.0)
    m1, m2, m3 = st.columns(3)
    m1.metric("Score Δ", f"{drift['overall_score_delta']:+.2f}")
    m2.metric("PSI", "-" if drift["psi"] is None else f"{drift['psi']:.3f}")
    flagged_total = 0
    for table_key in ("rule_table", "cde_table", "dimension_table"):
        table = drift[table_key]
        if not table.empty:
            flagged_total += int(table["flagged"].sum())
    m3.metric("Flagged changes (|Δ| ≥ 5 pp)", flagged_total)

    if flagged_total:
        for label, table_key in (
            ("Rules", "rule_table"), ("CDEs", "cde_table"),
            ("Dimensions", "dimension_table"),
        ):
            table = drift[table_key]
            flagged = table[table["flagged"]] if not table.empty else table
            if flagged.empty:
                continue
            st.markdown(f"**{html.escape(label)} that moved ≥ 5 pp**")
            st.dataframe(
                flagged.drop(columns=["flagged"]),
                use_container_width=True, hide_index=True,
                column_config={
                    "score_a": st.column_config.NumberColumn(
                        "previous", format="%.2f"),
                    "score_b": st.column_config.NumberColumn(
                        "current", format="%.2f"),
                    "delta": st.column_config.NumberColumn(format="%+.2f"),
                },
            )
    else:
        st.caption("Nothing moved ≥ 5 pp between the last two runs.")
    st.caption(
        "Comparing the two most recent runs. For arbitrary baselines, PSI/KS "
        "detail and per-rule drift, open ML Lab → 📜 Run History."
    )
