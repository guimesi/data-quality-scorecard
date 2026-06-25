"""Step 7 ML Lab tab: Row Explain.

Extracted from the monolithic ``ui/step_07_ml_lab.py`` so each tab lives
in its own file and stays small enough to navigate. The orchestrating
``render()`` (still in :mod:`ui.step_07_ml_lab`) wires this tab into the
``st.tabs(...)`` row at the top.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.ml_lab import (
    explain_row_score,
)
from ui.step_07._shared import (
    _render_empty,
    _render_explainer,
)
from utils.colors import STATUS_GREEN, STATUS_RED, STATUS_YELLOW


def _render_tab_row_explain(code: str, dp, config, result, flags=None, rule_meta=None) -> None:
    _render_explainer(
        "<b>What this does.</b> Picks a single row and decomposes its "
        "<code>100 − row_score</code> deficit into <b>per-CDE</b> "
        "contributions. The waterfall starts at the perfect score (100) "
        "and each CDE pulls it down by exactly how much its failing rules "
        "(× their normalized weight × the source weight) cost the row. "
        "This is the SHAP-equivalent for our linear scoring model - "
        "the decomposition is <b>exact</b>, not approximate."
    )

    if len(result.row_scores) == 0:
        _render_empty("This Data Product has no scored rows.")
        return

    # Default to the worst-scoring row (most interesting to explain).
    worst_idx = result.row_scores.sort_values().index[0]
    options = list(result.row_scores.index)
    median_idx = result.row_scores.sort_values().index[len(options) // 2]

    # Streamlit forbids modifying ``session_state[k]`` AFTER the widget with
    # key=k has been instantiated. We work around it with a "pending" key
    # that the buttons write to; the value is then transferred into the
    # widget's key BEFORE the widget instantiates on the next rerun.
    pos_key = f"ml_lab_row_pos_{code}"
    pending_key = f"ml_lab_row_pos_pending_{code}"
    if pending_key in st.session_state:
        st.session_state[pos_key] = int(st.session_state.pop(pending_key))

    default_pos = options.index(worst_idx) if worst_idx in options else 0

    # Build a small "browse" widget with index input + worst / median shortcuts.
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        chosen_pos = st.number_input(
            "Row position (0-based)",
            min_value=0, max_value=len(options) - 1, value=int(default_pos),
            step=1, key=pos_key,
            help="Pick which row to explain. Defaults to the worst-scoring row.",
        )
        row_index = options[int(chosen_pos)]
    with c2:
        if st.button("🔴 Worst row", use_container_width=True,
                     key=f"ml_lab_row_worst_{code}"):
            st.session_state[pending_key] = options.index(worst_idx)
            st.rerun()
    with c3:
        if st.button("🟡 Median row", use_container_width=True,
                     key=f"ml_lab_row_med_{code}"):
            st.session_state[pending_key] = options.index(median_idx)
            st.rerun()

    with st.spinner("🧩 Explaining the row score..."):
        expl = explain_row_score(
            dp, config, result, row_index, flags=flags, rule_meta=rule_meta,
        )
    status = expl["status"]
    status_color = {"GREEN": STATUS_GREEN, "YELLOW": STATUS_YELLOW, "RED": STATUS_RED}.get(status, "#64748b")

    m1, m2, m3 = st.columns(3)
    m1.metric("Row score", f"{expl['row_score']:.1f}")
    m2.markdown(
        f"<div style='padding:0.3em 0.7em;border-radius:8px;"
        f"background:{status_color}22;color:{status_color};font-weight:700;"
        f"text-align:center;margin-top:0.5em'>{status}</div>",
        unsafe_allow_html=True,
    )
    if not expl["per_cde"].empty:
        top_cde = expl["per_cde"].iloc[0]
        m3.metric(
            "Worst-offender CDE",
            f"{top_cde['cde']}",
            delta=f"−{top_cde['deficit']:.1f} pts ({top_cde['share_pct']:.0f}%)",
            delta_color="off",
        )

    # Waterfall
    if expl["waterfall_x"]:
        fig = go.Figure(go.Waterfall(
            x=expl["waterfall_x"],
            y=expl["waterfall_y"],
            measure=expl["waterfall_measure"],
            connector=dict(line=dict(color="rgba(0,0,0,0.25)", dash="dot")),
            increasing=dict(marker=dict(color=STATUS_GREEN)),
            decreasing=dict(marker=dict(color=STATUS_RED)),
            totals=dict(marker=dict(color="#6366f1")),
            text=[f"{v:+.1f}" if m == "relative" else f"{v:.1f}"
                  for v, m in zip(expl["waterfall_y"], expl["waterfall_measure"])],
            textposition="outside",
        ))
        fig.update_layout(
            height=380,
            yaxis_title="row_score points",
            margin=dict(t=20, b=40, l=20, r=20),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Each red step shows how many points the corresponding CDE's "
            "failing rules cost this row. The bars sum to exactly "
            "<code>100 − row_score</code> when only one source is active.",
            unsafe_allow_html=True,
        )

    cleft, cright = st.columns(2)
    with cleft:
        st.markdown("##### 🌿 Per-CDE deficit")
        if not expl["per_cde"].empty:
            st.dataframe(
                expl["per_cde"],
                use_container_width=True, hide_index=True, height=260,
                column_config={
                    "deficit": st.column_config.NumberColumn(format="%.2f"),
                    "share_pct": st.column_config.ProgressColumn(
                        "share %", min_value=0, max_value=100, format="%.1f%%",
                    ),
                },
            )
        else:
            st.caption("This row passed every rule - perfect score.")
    with cright:
        st.markdown("##### 🔍 Per-rule contribution")
        if not expl["per_rule"].empty:
            st.dataframe(
                expl["per_rule"],
                use_container_width=True, hide_index=True, height=260,
                column_config={
                    "contribution_to_deficit": st.column_config.NumberColumn(
                        "deficit pts", format="%.2f",
                    ),
                    "weight_pct": st.column_config.NumberColumn(format="%.2f%%"),
                },
            )


# =============================================================================
# Header
# =============================================================================

