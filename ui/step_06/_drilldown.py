"""Click-to-inspect drill-down for the Step 6 dashboard tabs.

Clicking a bar on the "By CDE" / "By Dimension" charts, or selecting a row
on the "Rules (pass rate)" / "Custom Rules" tables, surfaces the actual
data rows that fail the clicked element - so the user can jump straight
from "this CDE / dimension / rule looks bad" to the problematic records
without scanning the full export.

The failing-row table reuses the same enrichment as the "Worst rows" tab
(row_score first, reference-dataset columns, one 100/0 column per rule) so
the two views read the same way.
"""
from __future__ import annotations

import html
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from config.custom_dqr_catalog import (
    effective_required_columns,
    get_available_custom_dqr_rules,
)
from src.custom_dqr_engine import evaluate_custom_rules
from src.dqr_engine import evaluate_all_safe
from ui.step_06._export import (
    _per_rule_score_columns,
    _reference_columns_for_export,
)

# Hard cap on the rows rendered per drill-down so a very unhealthy dataset
# doesn't ship thousands of rows to the browser; worst rows come first.
_MAX_DRILLDOWN_ROWS = 200


def _standard_flags(dp, cfg) -> pd.DataFrame:
    """Per-row Boolean pass flags (True = pass), one column per Standard
    rule_id. Rules that could not be computed are simply absent."""
    if not cfg.assignments:
        return pd.DataFrame(index=dp.df.index)
    flags, _ = evaluate_all_safe(dp.df, cfg.assignments, dp.profiles)
    return flags


def _custom_flags(dp, cfg) -> pd.DataFrame:
    """Per-row Boolean pass flags, one column per *evaluated* Custom rule."""
    if not cfg.custom_assignments:
        return pd.DataFrame(index=dp.df.index)
    flags, _ = evaluate_custom_rules(dp.df, cfg.custom_assignments, dp.system_code)
    return flags


def _all_flags(dp, cfg) -> pd.DataFrame:
    """Standard + Custom pass flags side by side (columns never collide:
    Standard rule_ids are ``CDE::Dimension``, Custom ids are catalog codes)."""
    std = _standard_flags(dp, cfg)
    cust = _custom_flags(dp, cfg)
    if cust.empty:
        return std
    if std.empty:
        return cust
    return pd.concat([std, cust], axis=1)


def _custom_rule_meta(cfg, system_code: str) -> Dict[str, Tuple[List[str], str]]:
    """``rule_id -> (source columns, rule type)`` for the DP's Custom rules.

    Mirrors how ``compute_scorecard`` rolls Custom rules up into the By-CDE
    (via each rule's effective required columns) and By-Dimension (via the
    rule's ``type``) charts - so a bar built from Custom rules drills down
    to the same rules that produced its score.
    """
    if not cfg.custom_assignments:
        return {}
    catalog = {r.id: r for r in get_available_custom_dqr_rules(system_code)}
    meta: Dict[str, Tuple[List[str], str]] = {}
    for a in cfg.custom_assignments:
        rule = catalog.get(a.rule_id)
        if rule is None:
            continue
        req = effective_required_columns(rule, getattr(a, "params", None) or {})
        meta[a.rule_id] = (list(req.values()), rule.type)
    return meta


def _selected_bar_labels(event) -> List[str]:
    """Extract the clicked bars' y-axis labels from a plotly selection event.

    Defensive on purpose: the event is ``None`` / empty on the first render,
    and AppTest returns an empty selection state.
    """
    try:
        points = event["selection"]["points"]
    except Exception:
        return []
    labels: List[str] = []
    for p in points or []:
        y = p.get("y") if isinstance(p, dict) else None
        if y is not None and str(y) not in labels:
            labels.append(str(y))
    return labels


def _selected_table_rows(event) -> List[int]:
    """Positional indices of the rows selected on a ``st.dataframe``."""
    try:
        rows = event["selection"]["rows"]
    except Exception:
        return []
    return list(rows or [])


def _failing_mask(flags: pd.DataFrame, rule_ids: List[str]) -> Optional[pd.Series]:
    """True for rows failing at least one of ``rule_ids``.

    Returns ``None`` when none of the requested rules produced flags (all
    of them were "Not computed" / "Not evaluated") - the caller then shows
    an explanatory message instead of a misleading empty table.
    """
    present = [r for r in rule_ids if r in flags.columns]
    if not present:
        return None
    return ~flags[present].all(axis=1)


def _render_failing_rows(dp, result, cfg, mask: pd.Series,
                         context: str, key: str) -> None:
    """Render the drill-down table: every row failing ``mask``'s rules,
    worst score first, enriched exactly like the Worst-rows tab."""
    n_fail = int(mask.sum())
    if n_fail == 0:
        st.success(f"✅ No failing rows for **{context}** - every row passes.")
        return

    scores = result.row_scores
    fail_idx = scores[mask].sort_values().index
    shown_idx = fail_idx[:_MAX_DRILLDOWN_ROWS]

    show = dp.df.loc[shown_idx].copy()
    ref_cols = _reference_columns_for_export(dp, cfg).loc[shown_idx]
    for col in ref_cols.columns:
        show[col] = ref_cols[col]
    rule_scores = _per_rule_score_columns(dp, cfg).loc[shown_idx]
    for col in rule_scores.columns:
        show[col] = rule_scores[col]
    show.insert(0, "row_score", scores.loc[shown_idx].round(2))

    st.markdown(
        f"<div class='worst-banner'>"
        f"🎯 <b>{n_fail:,} row(s) fail {html.escape(context)}.</b> "
        f"Each rule column shows <b>100</b> (pass) or <b>0</b> (fail); "
        f"worst rows first."
        f"</div>",
        unsafe_allow_html=True,
    )
    if n_fail > len(shown_idx):
        st.caption(
            f"Showing the {len(shown_idx)} lowest-scoring of the "
            f"{n_fail:,} failing rows. Use the CSV export for the full list."
        )
    st.dataframe(show, use_container_width=True, height=300, key=key)


def _render_cde_drilldown(code: str, dp, result, cfg, event) -> None:
    """Failing rows for every CDE bar the user clicked on the By-CDE chart."""
    selected = _selected_bar_labels(event)
    if not selected:
        st.caption(
            "💡 Click a bar to inspect the rows failing that CDE's rules. "
            "Double-click the chart background to clear the selection."
        )
        return
    flags = _all_flags(dp, cfg)
    custom_meta = _custom_rule_meta(cfg, dp.system_code)
    for cde in selected:
        rule_ids = [a.rule_id for a in cfg.assignments if a.cde_column == cde]
        rule_ids += [rid for rid, (cols, _) in custom_meta.items() if cde in cols]
        mask = _failing_mask(flags, rule_ids)
        if mask is None:
            st.info(
                f"ℹ️ No computed rule for CDE **{cde}** - see the "
                "Rules / Custom Rules tabs for the reason."
            )
            continue
        _render_failing_rows(
            dp, result, cfg, mask,
            context=f"CDE {cde}", key=f"drill_cde_{code}_{cde}",
        )


def _render_dimension_drilldown(code: str, dp, result, cfg, event) -> None:
    """Failing rows for every dimension bar the user clicked."""
    selected = _selected_bar_labels(event)
    if not selected:
        st.caption(
            "💡 Click a bar to inspect the rows failing that dimension's "
            "rules. Double-click the chart background to clear the selection."
        )
        return
    flags = _all_flags(dp, cfg)
    custom_meta = _custom_rule_meta(cfg, dp.system_code)
    for dim in selected:
        rule_ids = [a.rule_id for a in cfg.assignments if a.dimension == dim]
        rule_ids += [
            rid for rid, (_, rtype) in custom_meta.items() if rtype == dim
        ]
        mask = _failing_mask(flags, rule_ids)
        if mask is None:
            st.info(
                f"ℹ️ No computed rule for dimension **{dim}** - see the "
                "Rules / Custom Rules tabs for the reason."
            )
            continue
        _render_failing_rows(
            dp, result, cfg, mask,
            context=f"dimension {dim}", key=f"drill_dim_{code}_{dim}",
        )


def _render_rule_drilldown(code: str, dp, result, cfg,
                           df_rules: pd.DataFrame, event) -> None:
    """Failing rows for the Standard rule selected on the Rules table."""
    rows_sel = _selected_table_rows(event)
    if not rows_sel:
        st.caption("💡 Select a rule row to inspect the rows that fail it.")
        return
    row = df_rules.iloc[rows_sel[0]]
    rule_id = f"{row['CDE']}::{row['Dimension']}"
    if rule_id in result.not_computed_standard_rules:
        st.info(
            f"ℹ️ **{rule_id}** was not computed - "
            f"{result.not_computed_standard_rules[rule_id]}"
        )
        return
    mask = _failing_mask(_standard_flags(dp, cfg), [rule_id])
    if mask is None:
        st.info(f"ℹ️ **{rule_id}** produced no per-row results.")
        return
    _render_failing_rows(
        dp, result, cfg, mask,
        context=f"rule {rule_id}", key=f"drill_rule_{code}",
    )


def _render_custom_rule_drilldown(code: str, dp, result, cfg,
                                  df_custom: pd.DataFrame, event) -> None:
    """Failing rows for the Custom rule selected on the Custom Rules table."""
    rows_sel = _selected_table_rows(event)
    if not rows_sel:
        st.caption("💡 Select a rule row to inspect the rows that fail it.")
        return
    row = df_custom.iloc[rows_sel[0]]
    rule_id = str(row["Rule ID"])
    if rule_id in result.not_evaluated_custom_rules:
        st.info(
            f"ℹ️ **{rule_id}** was not evaluated - "
            f"{result.not_evaluated_custom_rules[rule_id]}"
        )
        return
    mask = _failing_mask(_custom_flags(dp, cfg), [rule_id])
    if mask is None:
        st.info(f"ℹ️ **{rule_id}** produced no per-row results.")
        return
    _render_failing_rows(
        dp, result, cfg, mask,
        context=f"custom rule {rule_id} ({row['Name']})",
        key=f"drill_custom_{code}",
    )
