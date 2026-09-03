"""Step 6: Scorecard - orchestration (redesigned).

Narrative: header actions → run summary → overview (score cards + Needs
attention) → detail for the SELECTED Data Product only → footer.
Re-exports the helper symbols tests reach for (unchanged list, minus ``_gauge``).
"""
from __future__ import annotations

import logging

import streamlit as st

from config.settings import SETTINGS
from src.one_click import ONE_CLICK_SUMMARY_KEY
from src.persistence import log_event
from src.scorecard import compute_scorecard
from ui.step_06._breakdown import (
    _render_custom_rules_table,
    _render_dp_card_header,
    _render_source_breakdown,
)
from ui.step_06._charts import _threshold_bar
from ui.step_06._dp_dashboard import _render_dashboard_for_dp, _render_overview_cards
from ui.step_06._drilldown import (
    _render_cde_drilldown,
    _render_custom_rule_drilldown,
    _render_dimension_drilldown,
    _render_failing_rows,
    _render_rule_drilldown,
)
from ui.step_06._exec_report import (
    _build_executive_report_html,
    _render_executive_report_download,
)
from ui.step_06._export import (
    _build_config_json,
    _build_rowscores_csv,
    _per_rule_score_columns,
    _reference_columns_for_export,
)
from ui.step_06._history import _record_runs, _render_drop_alert, _render_history_tab
from ui.step_06._overview import render_overview
from ui.step_06._projects import _render_project_save_panel
from ui.step_06._shared import _DEFAULT_ACCENT, _SYSTEM_ACCENTS, _SYSTEM_ICONS, _status_class
from utils.session_state import APP_MODE_ONE_CLICK, goto, prev_step, restart_app
from utils.ui_components import badge, callout, code_chip, page_header, render_nav_footer, step_eyebrow

logger = logging.getLogger(__name__)


def _render_header_actions(scorecards: dict) -> None:
    """Save project · Export ▾ · ML Lab - one row, right-aligned under the title."""
    _, c_save, c_export, c_lab = st.columns([5, 1.1, 1, 1.1])
    with c_save:
        if hasattr(st, "dialog"):
            @st.dialog("Save as project")
            def _save_dialog() -> None:
                _render_project_save_panel()  # existing panel: name + Save version + changelog
            if st.button("Save project", key="dash_save_project", use_container_width=True):
                _save_dialog()
        else:
            _render_project_save_panel()
    with c_export:
        with st.popover("Export", use_container_width=True):
            _render_executive_report_download(scorecards)
            domain_code = str(st.session_state.get("domain", "") or "")
            for code, result in scorecards.items():
                dp = st.session_state.data_products[code]
                cfg = st.session_state.configs[code]
                st.markdown(f"**{code}**")
                d1, d2 = st.columns(2)
                if d1.download_button("CSV · row scores", data=_build_rowscores_csv(dp, result, cfg),
                                      file_name=f"{code}_row_scores.csv", mime="text/csv",
                                      use_container_width=True, key=f"dl_csv_{code}"):
                    log_event("export", {"format": "csv", "dp": code}, domain_code)
                if d2.download_button("JSON · config", data=_build_config_json(dp, result, cfg),
                                      file_name=f"{code}_scorecard.json", mime="application/json",
                                      use_container_width=True, key=f"dl_json_{code}"):
                    log_event("export", {"format": "json", "dp": code}, domain_code)
    with c_lab:
        if st.button("ML Lab · beta", key="dashboard_open_ml_lab", use_container_width=True,
                     help="Experimental, read-only analyses on top of this scorecard."):
            goto("ml_lab")


def _render_one_click_summary() -> None:
    summary = st.session_state.get(ONE_CLICK_SUMMARY_KEY)
    if not summary:
        return
    scored = summary.get("scored", [])
    skipped = summary.get("skipped", {}) or {}
    warnings = summary.get("warnings", []) or []
    csv_errors = summary.get("csv_errors", {}) or {}
    skipped_txt = (
        f' · <span style="color:var(--dq-wn);font-weight:500">{", ".join(skipped)} skipped</span>'
        if skipped else ""
    )
    c_msg, c_more = st.columns([6, 1], vertical_alignment="center")
    with c_msg:
        callout(
            f'{badge("One-click", "brand")} {len(scored)} system{"s" if len(scored) != 1 else ""} scored '
            f'with all Custom DQRs at defaults, equal weights{skipped_txt}', "info",
        )
    with c_more:
        if skipped or warnings or csv_errors:
            with st.popover("Run details", use_container_width=True):
                for c, r in skipped.items():
                    st.markdown(f"**{c}** skipped — {r}")
                for w in warnings:
                    st.markdown(f"- {w}")
                for c, e in csv_errors.items():
                    st.error(f"CSV export could not be prepared for **{c}**: {e}")


def render() -> None:
    dps = st.session_state.data_products
    configs = st.session_state.configs

    scorecards, failed = {}, {}
    with st.spinner("Computing scorecards…"):
        for code, dp in dps.items():
            cfg = configs[code]
            if not cfg.assignments and not cfg.custom_assignments:
                continue
            try:
                scorecards[code] = compute_scorecard(
                    dp, cfg, threshold_green=SETTINGS.threshold_green,
                    threshold_yellow=SETTINGS.threshold_yellow,
                )
            except Exception as exc:
                logger.warning("Scorecard computation failed for %s", code, exc_info=True)
                failed[code] = str(exc)
    st.session_state.scorecards = scorecards
    _record_runs(scorecards)

    row_limit = st.session_state.get("sample_mode", True)
    from utils.session_state import get_planview_filter, get_row_limit
    rl = get_row_limit()
    sub = (f"Sample ≤ {rl:,} rows/table" if rl else "Full dataset") + \
          (f" · {len(get_planview_filter())} project filter(s)" if get_planview_filter() else " · All projects")
    page_header(step_eyebrow(), "Scorecard", sub)

    if not scorecards:
        if failed:
            callout("Some Data Products could not be scored: " + "; ".join(f"<b>{c}</b> — {e}" for c, e in failed.items()), "err")
        else:
            callout("No Data Product has rules yet. Go back and configure DQRs.", "info")
        _nav()
        return

    _render_header_actions(scorecards)
    _render_one_click_summary()
    if failed:
        callout("Left out (could not be scored): " + "; ".join(f"<b>{c}</b> — {e}" for c, e in failed.items()), "err")

    skipped = (st.session_state.get(ONE_CLICK_SUMMARY_KEY) or {}).get("skipped", {}) or {}
    sel = render_overview(scorecards, skipped=skipped)

    _render_dashboard_for_dp(sel, dps[sel], scorecards[sel])
    _nav()


def _nav() -> None:
    render_nav_footer(
        show_next=False, next_message="",
        blocked_message=None,
        on_back=prev_step, on_next=lambda: None, on_restart=restart_app,
        restart_key="restart_confirm_dashboard",
    )
    st.markdown(
        '<div class="dq-nav-msg" style="text-align:left;margin-top:-6px">End of workflow — export from the header or save this configuration as a project.</div>',
        unsafe_allow_html=True,
    )


__all__ = [
    "render", "_build_config_json", "_build_rowscores_csv", "_per_rule_score_columns",
    "_reference_columns_for_export", "_status_class", "_render_source_breakdown",
    "_render_custom_rules_table", "_render_dp_card_header", "_render_dashboard_for_dp",
    "_render_overview_cards", "_render_cde_drilldown", "_render_dimension_drilldown",
    "_render_rule_drilldown", "_render_custom_rule_drilldown", "_render_failing_rows",
    "_record_runs", "_render_drop_alert", "_render_history_tab", "_render_project_save_panel",
    "_build_executive_report_html", "_render_executive_report_download", "_threshold_bar",
    "_SYSTEM_ICONS", "_SYSTEM_ACCENTS", "_DEFAULT_ACCENT",
]
