"""Streamlit wrapper for the Data Quality Report (HTML).

The report itself is built by the pure package
:mod:`ui.step_06.report` (``build_report`` never touches Streamlit).
This module only:

- assembles a :class:`~ui.step_06.report.models.ReportContext` from
  ``st.session_state`` (domain, mode, data scope, project filter,
  thresholds, saved project, a fresh run identifier);
- renders the download button (telemetry event unchanged:
  ``export`` / ``{"format": "executive_html"}``);
- renders the Send-to-Airtable button (attachment contract unchanged -
  the Airtable push receives the report bytes as before).

``_build_executive_report_html`` keeps the previous builder's
name/signature for existing imports and tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, Optional

import streamlit as st

from config.settings import SETTINGS
from src.persistence import current_username, log_event
from ui.step_06.report import ReportContext, build_report
from ui.step_06.report import (
    build_executive_report_html as _pure_build_executive_report_html,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _domain_name(domain_code: str) -> str:
    """Human label for the domain; degrades to '' for unknown codes."""
    if not domain_code:
        return ""
    try:
        from config.domains import get_domain

        return get_domain(domain_code).name
    except KeyError:
        return ""


def _build_report_context(domain_code: str,
                          scorecards: Dict[str, object]) -> ReportContext:
    """Assemble the run metadata for the report header from session state.

    Values that are not in the session render as an em dash in the
    report - nothing is invented.
    """
    first = next(iter(scorecards.values()), None)
    mode = st.session_state.get("app_mode") or None
    sample_mode = st.session_state.get("sample_mode")
    saved_project = str(
        st.session_state.get("loaded_project_name", "") or "").strip() or None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return ReportContext(
        domain_code=domain_code,
        domain_name=_domain_name(domain_code),
        dp_codes=list(scorecards.keys()),
        generated_at=_utc_now_iso(),
        generated_by=current_username(),
        mode=mode,
        data_scope=(None if sample_mode is None
                    else ("sample" if sample_mode else "full")),
        sample_rows_cap=SETTINGS.max_rows_per_table,
        project_filter=[
            str(p) for p in (st.session_state.get("planview_filter") or [])
        ],
        threshold_green=(float(first.threshold_green) if first is not None
                         else SETTINGS.threshold_green),
        threshold_yellow=(float(first.threshold_yellow) if first is not None
                          else SETTINGS.threshold_yellow),
        saved_project=saved_project,
        run_id=f"run_{stamp}_{uuid.uuid4().hex[:4]}",
        drop_alert_pp=SETTINGS.drop_alert_pp,
    )


def _build_executive_report_html(
    domain_code: str, scorecards: Dict[str, object], dps: Dict[str, object],
    configs: Dict[str, object], ctx: Optional[ReportContext] = None,
) -> bytes:
    """Compatibility entry point: the full report as UTF-8 bytes.

    Without an explicit ``ctx`` a minimal context is built (generated-at
    timestamp, user, domain, thresholds); the Streamlit session is NOT
    consulted, so this stays callable from tests and scripts.
    """
    if ctx is None:
        first = next(iter(scorecards.values()), None)
        ctx = ReportContext(
            domain_code=domain_code,
            domain_name=_domain_name(domain_code),
            dp_codes=list(scorecards.keys()),
            generated_at=_utc_now_iso(),
            generated_by=current_username(),
            threshold_green=(float(first.threshold_green)
                             if first is not None
                             else SETTINGS.threshold_green),
            threshold_yellow=(float(first.threshold_yellow)
                              if first is not None
                              else SETTINGS.threshold_yellow),
            drop_alert_pp=SETTINGS.drop_alert_pp,
        )
    return _pure_build_executive_report_html(
        domain_code, scorecards, dps, configs, ctx=ctx,
    )


def _render_executive_report_download(scorecards: Dict[str, object]) -> None:
    """Step 6 download button; logs an ``export`` telemetry event on click."""
    dps = st.session_state.get("data_products") or {}
    configs = st.session_state.get("configs") or {}
    domain_code = str(st.session_state.get("domain", "") or "")
    if not scorecards:
        return
    ctx = _build_report_context(domain_code, scorecards)
    artifact = build_report(ctx, scorecards, dps, configs)
    if st.download_button(
        "📑 Data Quality Report (HTML)",
        data=artifact.html,
        file_name=artifact.filename,
        mime="text/html",
        key="dl_exec_report",
        help="Self-contained, interactive snapshot of this run - scores, "
             "rules with reasons, failing rows, history, drift and the "
             "exact configuration. Works offline from file://; open it and "
             "press Ctrl+P to save as a shareable PDF.",
    ):
        log_event("export", {"format": "executive_html"}, domain_code)
    _render_airtable_push(domain_code, scorecards, artifact.html)


def _render_airtable_push(domain_code: str, scorecards: Dict[str, object],
                          html_bytes: bytes) -> None:
    """Send-to-Airtable button (phase 5). Hidden unless AIRTABLE_* is
    configured; failures surface as an inline error, never a crash."""
    from src.airtable_push import (
        AirtablePushError,
        is_configured,
        push_executive_report,
    )

    if not is_configured():
        return
    if st.button(
        "📤 Send to Airtable",
        key="btn_airtable_push",
        help="Upserts this domain's record in the Airtable results table "
             "(score, status, per-DP breakdown) and attaches the executive "
             "HTML report, giving data owners the full picture in Airtable.",
    ):
        try:
            record_ids = push_executive_report(domain_code, scorecards,
                                               html_bytes)
        except AirtablePushError as exc:
            st.error(f"Airtable push failed: {exc}")
        else:
            log_event("export", {"format": "airtable_push",
                                 "record_ids": record_ids}, domain_code)
            st.success(
                f"Results sent to Airtable - {len(record_ids)} system "
                "record(s) updated, executive report attached to each."
            )
