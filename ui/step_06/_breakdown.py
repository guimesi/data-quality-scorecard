"""Per-DP header, source-breakdown card, and Custom Rules table.

These are the cards / tables that sit at the top of each Data Product
dashboard before the gauge + tab row.
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from config.dqr_sources import SOURCE_LABELS
from ui.step_06._drilldown import _render_custom_rule_drilldown
from ui.step_06._rule_rows import custom_rule_rows
from ui.step_06._shared import (
    _DEFAULT_ACCENT,
    _SYSTEM_ACCENTS,
    _SYSTEM_ICONS,
    _status_class,
)
from utils.helpers import score_label


def _render_source_breakdown(result) -> None:
    """Show the per-source subscores + the source weights used."""
    sources = list(result.source_weights.keys()) if result.source_weights else []
    if not sources:
        return
    weights = result.source_weights
    inline_parts = " · ".join(
        f"<b>{html.escape(SOURCE_LABELS[s])}</b>: {weights.get(s, 0.0):.0f}%"
        for s in sources
    )
    st.markdown(
        f"""
        <div class="src-mini">
            <div class="src-mini-title">📐 Source weights</div>
            <div>{inline_parts}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    sub_cols = []
    if result.standard_score is not None:
        sub_cols.append(("Standard score", result.standard_score))
    if result.custom_score is not None:
        sub_cols.append(("Custom score", result.custom_score))
    if not sub_cols:
        return
    cols = st.columns(len(sub_cols))
    for col, (label, value) in zip(cols, sub_cols):
        col.metric(label, f"{value:.1f}")


def _render_custom_rules_table(code: str, result) -> None:
    cfg = st.session_state.configs[code]
    rows = [
        {
            "Rule ID": r["rule_id"],
            "Name": r["name"],
            "Type": r["type"],
            "Blocking": "Yes" if r["blocking"] else "No",
            "Status": r["status"],
            "Weight (%)": round(r["weight"], 2),
            "Pass rate (%)": (
                float("nan") if r["pass_rate"] is None
                else round(r["pass_rate"], 2)
            ),
        }
        for r in custom_rule_rows(code, cfg, result)
    ]
    if not rows:
        st.caption("No custom rules selected for this Data Product.")
        return
    df = pd.DataFrame(rows).sort_values("Pass rate (%)")
    custom_event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Pass rate (%)": st.column_config.ProgressColumn(
                "Pass rate (%)", min_value=0, max_value=100, format="%.1f%%",
            ),
            "Weight (%)": st.column_config.NumberColumn(format="%.2f%%"),
        },
        on_select="rerun",
        selection_mode="single-row",
        key=f"custom_rules_table_{code}",
    )
    dp = st.session_state.data_products.get(code)
    if dp is not None:
        _render_custom_rule_drilldown(code, dp, result, cfg, df, custom_event)
    if result.not_evaluated_custom_rules:
        for rule_id, reason in result.not_evaluated_custom_rules.items():
            st.warning(f"⚠ **{rule_id}** not evaluated - {reason}")


def _render_dp_card_header(code: str, dp, result) -> None:
    """Polished header for each DP dashboard card: icon, name, code pill,
    status pill on the right. Visually replaces the original ``## 📦 dp.name``
    + plain `**Status:** ...` line."""
    icon = _SYSTEM_ICONS.get(code, "📦")
    accent = _SYSTEM_ACCENTS.get(code, _DEFAULT_ACCENT)
    label = score_label(result.overall_score,
                        result.threshold_green, result.threshold_yellow)
    cls = _status_class(result.overall_score,
                        result.threshold_green, result.threshold_yellow)
    st.markdown(
        f"""
        <div class="dp-card-accent" style="background: {accent};"></div>
        <div class="dp-card-title-row">
            <span class="dp-icon">{icon}</span>
            <span class="dp-name">{html.escape(dp.name)}</span>
            <span class="dp-code">{html.escape(code)}</span>
            <span class="dp-status-pill {cls}">{html.escape(label)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    # Keep the markdown line that the original page rendered so that
    # anything downstream relying on the literal "**Status:**" text still
    # finds it.
    st.markdown(f"**Status:** {label}")
