"""Step 7 ML Lab tab: Recommendations.

Extracted from the monolithic ``ui/step_07_ml_lab.py`` so each tab lives
in its own file and stays small enough to navigate. The orchestrating
``render()`` (still in :mod:`ui.step_07_ml_lab`) wires this tab into the
``st.tabs(...)`` row at the top.
"""
from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from src.ml_lab import (
    recommend_dqrs_for_cde,
)
from ui.step_07._shared import (
    _render_empty,
    _render_explainer,
)


def _render_tab_recommendations(code: str, dp, config, result) -> None:
    _render_explainer(
        "<b>What this does.</b> Suggests DQRs to <b>add</b> to each CDE, "
        "using two signals:<br>"
        "&nbsp;&nbsp;• <b>Neighbor recommendations</b> - find CDEs across "
        "all DPs in this session with similar profile signatures (cosine "
        "on null %, distinct ratio, duplicate ratio, dtype) and borrow the "
        "DQRs assigned to them.<br>"
        "&nbsp;&nbsp;• <b>Heuristics</b> - profile-driven rules of thumb "
        "(e.g. high null % → Completeness; low cardinality → Conformity).<br>"
        "Only ACTIONABLE additions are shown (already-assigned DQRs are "
        "filtered out)."
    )

    # Build the cross-DP scope so neighbor recommendations can leverage
    # other systems too.
    other_scope: Dict[str, Any] = {}
    for c2 in (st.session_state.get("data_products", {}) or {}):
        cfg2 = st.session_state.configs.get(c2)
        dp2 = st.session_state.data_products.get(c2)
        if cfg2 is None or dp2 is None:
            continue
        other_scope[c2] = (dp2, cfg2)

    df = recommend_dqrs_for_cde(dp, config, other_scope=other_scope, top_neighbors=3)
    if df.empty:
        _render_empty(
            "No actionable recommendations - every heuristic and neighbor "
            "signal is already covered by your current DQR setup. 🎉"
        )
        return

    st.dataframe(
        df,
        use_container_width=True, hide_index=True, height=360,
        column_config={
            "similarity": st.column_config.NumberColumn(
                format="%.3f", help="Cosine similarity on profile vectors.",
            ),
        },
    )
    by_cde = df.groupby("cde").size().to_dict()
    m1, m2, m3 = st.columns(3)
    m1.metric("Recommendations", f"{len(df):,}")
    m2.metric("CDEs covered", f"{len(by_cde):,}")
    m3.metric(
        "From neighbors",
        f"{int((df['source'] == 'neighbor').sum())}",
    )
    st.caption(
        "Recommendations are advisory - review them upstream in Step 4.1 "
        "before applying. The lab does NOT modify your live config."
    )


# =============================================================================
# Tab - Row Explainability (SHAP-like waterfall)
# =============================================================================

