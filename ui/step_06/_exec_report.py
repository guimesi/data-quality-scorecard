"""Streamlit wrapper for the Data Quality Report (HTML + PDF).

The report itself is built by the pure package
:mod:`ui.step_06.report` (``build_report`` never touches Streamlit).
This module only:

- assembles a :class:`~ui.step_06.report.models.ReportContext` from
  ``st.session_state`` (domain, mode, data scope, project filter,
  thresholds, saved project, a run identifier);
- builds the artefacts ONCE per run (cached in session state keyed by
  the config + result fingerprints, so dashboard reruns don't rebuild
  or re-render the PDF) and stores them in the report store so the app
  can serve the interactive edition at ``/reports/<run_id>``;
- renders the download buttons (telemetry event unchanged for the
  interactive edition: ``export`` / ``{"format": "executive_html"}``)
  and the hosted link;
- renders the Send-to-Airtable button (attachment contract unchanged -
  the Airtable push receives the interactive HTML bytes as before).

``_build_executive_report_html`` keeps the previous builder's
name/signature for existing imports and tests.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import streamlit as st

from config.settings import SETTINGS
from src import report_store
from src.persistence import current_username, log_event
from src.run_history import config_fingerprint, result_fingerprint
from ui.step_06.report import ReportArtifacts, ReportContext, build_report
from ui.step_06.report import (
    build_executive_report_html as _pure_build_executive_report_html,
)

# session_state key: {"key": <run fingerprint>, "artifacts": ReportArtifacts,
# "stored": bool} for the run currently shown on the dashboard.
_CACHE_KEY = "_dq_report_cache"


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
    """Assemble the run metadata for the report from session state.

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
    """Compatibility entry point: the interactive report as UTF-8 bytes.

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


def _run_key(domain_code: str, scorecards: Dict[str, object],
             configs: Dict[str, object]) -> Tuple:
    """Fingerprint of the run on screen: same configs + same results =
    same artefacts (a rerun must not mint a new run_id or re-render)."""
    return (
        domain_code,
        tuple(str(p) for p in (st.session_state.get("planview_filter") or [])),
        tuple(
            (code, config_fingerprint(configs[code]) if code in configs else "",
             result_fingerprint(result))
            for code, result in scorecards.items()
        ),
    )


def _get_artifacts(domain_code: str, scorecards: Dict[str, object],
                   dps: Dict[str, object], configs: Dict[str, object]
                   ) -> Tuple[ReportArtifacts, bool]:
    """The run's artefacts, built and stored once per run.

    Returns ``(artifacts, stored)`` - ``stored`` tells whether the report
    store accepted the run (i.e. ``/reports/<run_id>`` is live).
    """
    key = _run_key(domain_code, scorecards, configs)
    cache = st.session_state.get(_CACHE_KEY)
    if cache and cache.get("key") == key and cache.get("artifacts") is not None:
        return cache["artifacts"], bool(cache.get("stored"))
    with st.spinner("📑 Preparing the Data Quality Report (HTML + PDF)..."):
        ctx = _build_report_context(domain_code, scorecards)
        artifacts = build_report(ctx, scorecards, dps, configs)
        stored = report_store.save_artifacts(artifacts)
    st.session_state[_CACHE_KEY] = {
        "key": key, "artifacts": artifacts, "stored": stored,
    }
    return artifacts, stored


def _hosted_url(run_id: str) -> str:
    """Absolute ``/reports/<run_id>`` link when the request URL is known,
    else the app-relative path."""
    path = report_store.report_url(run_id)
    try:
        url = str(st.context.url or "")
    except Exception:  # nosec B110 - no request context (tests, scripts)
        url = ""
    if "://" in url:
        origin = url.split("://", 1)[0] + "://" + url.split("://", 1)[1].split("/", 1)[0]
        return origin + path
    return path


def _render_executive_report_download(scorecards: Dict[str, object]) -> None:
    """Step 6 download buttons + hosted link; logs ``export`` telemetry
    events on click."""
    dps = st.session_state.get("data_products") or {}
    configs = st.session_state.get("configs") or {}
    domain_code = str(st.session_state.get("domain", "") or "")
    if not scorecards:
        return
    artifacts, stored = _get_artifacts(domain_code, scorecards, dps, configs)

    if st.download_button(
        "📑 Data Quality Report (HTML)",
        data=artifacts.html,
        file_name=artifacts.filenames["interactive"],
        mime="text/html",
        key="dl_exec_report",
        help="Self-contained, interactive snapshot of this run - scores, "
             "DQRs with reasons, failing rows, history, drift and the exact "
             "configuration. Works offline from file://.",
    ):
        log_event("export", {"format": "executive_html"}, domain_code)

    if artifacts.pdf is not None:
        if st.download_button(
            "📄 Data Quality Report (PDF)",
            data=artifacts.pdf,
            file_name=artifacts.filenames["pdf"],
            mime="application/pdf",
            key="dl_exec_report_pdf",
            help="Complete paginated edition (cover, executive summary, one "
                 "chapter per Data Product, configuration) - the file to "
                 "publish in SharePoint.",
        ):
            log_event("export", {"format": "executive_pdf"}, domain_code)
    else:
        if st.download_button(
            "🖨️ PDF edition (print-ready HTML)",
            data=artifacts.pdf_html,
            file_name=artifacts.filenames["pdf_html"],
            mime="text/html",
            key="dl_exec_report_print",
            help="The paginated PDF edition as HTML: open it in Chrome or "
                 "Edge and press Ctrl+P → Save as PDF (A4, backgrounds on).",
        ):
            log_event("export", {"format": "executive_pdf_html"}, domain_code)
        st.caption(
            "PDF conversion is not available on this server "
            f"({artifacts.metadata.get('pdf_error') or 'no converter'}); the "
            "print-ready HTML produces the same document."
        )

    if stored:
        url = _hosted_url(artifacts.run_id)
        st.caption(
            f"Hosted copy: [{url}]({url}) - the link to paste in SharePoint "
            "(opens for users entitled to this app). "
            f"Run `{artifacts.run_id}`."
        )
    _render_airtable_push(domain_code, scorecards, artifacts.html)


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
             "(score, status, per-DP breakdown) and attaches the interactive "
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
