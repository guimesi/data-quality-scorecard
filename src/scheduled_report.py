"""Headless, scheduled execution of the scorecard + Data Quality Report.

What Step 6 does interactively, done by a Databricks Job (or any shell)
with **no Streamlit** involved:

1. run the One-click pipeline for a domain (every system of the domain
   by default) - :func:`src.one_click.run_one_click`;
2. record each scored system in the run history (deduplicated) -
   :func:`src.run_history.record_run_if_new`, so History / drift keep
   working for the dashboard and for the next report;
3. build both report editions - :func:`ui.step_06.report.build_report`
   (the PDF needs a headless Chromium on the machine; without one the
   print-ready HTML is still produced and stored);
4. store the artefacts in the report store - :func:`src.report_store`
   (the same workspace folder the app serves at ``/reports/<run_id>``
   and ``/reports/latest/<DOMAIN>``);
5. push the scores to Airtable when ``AIRTABLE_*`` is configured -
   :func:`src.airtable_push.push_results`.

Configuration is the same environment the app uses (``DATA_SOURCE``,
``DATABRICKS_*``, ``DQS_PERSISTENCE``, ``DQS_REPORT_STORE`` /
``DQS_REPORT_WORKSPACE_DIR``, ``AIRTABLE_*``). Entry points:
``scripts/run_scheduled_report.py`` (CLI) and
``deploy/databricks/scheduled_report_job.py`` (notebook for the Job).

Nothing here raises for a *partial* failure: a system that could not be
scored, a store that refused the write or an Airtable rejection land in
:class:`JobOutcome` (``skipped`` / ``store_error`` / ``airtable_error``)
and the exit code tells the scheduler whether the run is usable.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class JobOutcome:
    """What a scheduled run produced (serialisable, printed as JSON)."""
    domain_code: str
    requested_systems: List[str]
    scored_systems: List[str] = field(default_factory=list)
    skipped: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    run_id: str = ""
    generated_at: str = ""
    generated_by: str = ""
    overall_scores: Dict[str, float] = field(default_factory=dict)
    statuses: Dict[str, str] = field(default_factory=dict)
    history_recorded: Dict[str, bool] = field(default_factory=dict)
    has_pdf: bool = False
    pdf_error: Optional[str] = None
    stored: bool = False
    store_target: str = ""
    store_error: Optional[str] = None
    report_path: str = ""
    latest_path: str = ""
    airtable_record_ids: Optional[List[str]] = None
    airtable_error: Optional[str] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        """Usable run: at least one system scored, no blocking error, and
        the store accepted the artefacts (or storage is off)."""
        store_off = (self.store_error or "").startswith("report store is off")
        return (not self.error and bool(self.scored_systems)
                and (self.stored or store_off))

    def to_json(self) -> str:
        data = asdict(self)
        data["ok"] = self.ok
        return json.dumps(data, indent=2, default=str)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def default_generated_by() -> str:
    """Identity recorded on the report: the Databricks user running the
    job when the SDK can resolve one, else the OS login."""
    from config.settings import SETTINGS
    from src.persistence import current_username

    if not SETTINGS.is_mock:
        try:
            from databricks.sdk import WorkspaceClient  # type: ignore

            name = WorkspaceClient().current_user.me().user_name
            if name:
                return str(name)
        except Exception:  # nosec B110 - fall back to the OS login
            logger.info("Could not resolve the Databricks user; using OS login")
    return current_username()


def run_scheduled_report(
    domain_code: str,
    systems: Optional[Iterable[str]] = None,
    *,
    planview_filter: Optional[Iterable[str]] = None,
    want_pdf: bool = True,
    push_airtable: Optional[bool] = None,
    generated_by: Optional[str] = None,
    record_history: bool = True,
) -> JobOutcome:
    """Score ``systems`` of ``domain_code`` (every system of the domain
    when ``None``), record history, build + store the report and push
    the scores to Airtable (``push_airtable=None`` = when configured).
    """
    from config.domains import get_domain
    from src import airtable_push, report_store
    from src.one_click import OneClickError, run_one_click
    from src.persistence import log_event
    from src.run_history import record_run_if_new
    from ui.step_06.report import ReportContext, build_report

    domain = get_domain(domain_code)
    requested = [s.strip() for s in (systems or domain.system_codes) if str(s).strip()]
    project_filter = [str(p) for p in (planview_filter or []) if str(p).strip()]
    outcome = JobOutcome(domain_code=domain_code, requested_systems=requested,
                         generated_at=_utc_now_iso(),
                         generated_by=generated_by or default_generated_by())
    logger.info("[scheduled report] %s systems=%s filter=%s", domain_code,
                requested, project_filter or "none")

    # 1) score ------------------------------------------------------------
    try:
        result = run_one_click(domain_code, requested,
                               planview_filter=project_filter or None)
    except OneClickError as exc:
        outcome.error = f"One-click run failed: {exc}"
        logger.error(outcome.error)
        return outcome
    outcome.scored_systems = result.scored_systems
    outcome.skipped = dict(result.skipped)
    outcome.warnings = list(result.warnings)
    if not result.products:
        outcome.error = "No system could be scored"
        logger.error("[scheduled report] %s: %s", outcome.error, outcome.skipped)
        return outcome

    # 2) history ------------------------------------------------------------
    if record_history:
        for code, product in result.products.items():
            try:
                outcome.history_recorded[code] = bool(record_run_if_new(
                    code, product.data_product, product.scorecard,
                    product.config, domain_code))
            except Exception as exc:  # history must never block the report
                outcome.history_recorded[code] = False
                outcome.warnings.append(f"history not recorded for {code}: {exc}")
                logger.warning("[scheduled report] history failed for %s",
                               code, exc_info=True)

    # 3) report -------------------------------------------------------------
    first = next(iter(result.scorecards.values()))
    ctx = ReportContext(
        domain_code=domain_code,
        domain_name=domain.name,
        dp_codes=result.scored_systems,
        generated_at=outcome.generated_at,
        generated_by=outcome.generated_by,
        mode="one_click",
        data_scope="full",
        project_filter=project_filter,
        threshold_green=float(first.threshold_green),
        threshold_yellow=float(first.threshold_yellow),
    )
    artifacts = build_report(ctx, result.scorecards, result.data_products,
                             result.configs, want_pdf=want_pdf)
    outcome.run_id = artifacts.run_id
    outcome.overall_scores = dict(artifacts.metadata.get("overall_scores") or {})
    outcome.statuses = dict(artifacts.metadata.get("statuses") or {})
    outcome.has_pdf = artifacts.pdf is not None
    outcome.pdf_error = artifacts.metadata.get("pdf_error")

    # 4) store --------------------------------------------------------------
    outcome.store_target = report_store.describe_store()
    outcome.stored = report_store.save_artifacts(artifacts)
    outcome.store_error = None if outcome.stored else report_store.last_error()
    if outcome.stored:
        outcome.report_path = report_store.report_url(artifacts.run_id)
        outcome.latest_path = report_store.latest_url(domain_code)
    else:
        logger.warning("[scheduled report] not stored (%s): %s",
                       outcome.store_target, outcome.store_error)

    # 5) airtable -----------------------------------------------------------
    if push_airtable is None:
        push_airtable = airtable_push.is_configured()
    if push_airtable:
        try:
            outcome.airtable_record_ids = airtable_push.push_results(
                domain_code, result.scorecards)
        except airtable_push.AirtablePushError as exc:
            outcome.airtable_error = str(exc)
            logger.warning("[scheduled report] Airtable push failed: %s", exc)

    try:
        log_event("scheduled_run", {
            "run_id": outcome.run_id, "systems": outcome.scored_systems,
            "skipped": outcome.skipped, "stored": outcome.stored,
            "has_pdf": outcome.has_pdf,
            "airtable": outcome.airtable_record_ids is not None,
        }, domain_code)
    except Exception:  # nosec B110 - telemetry is best effort
        logger.info("[scheduled report] telemetry event not recorded", exc_info=True)

    logger.info("[scheduled report] done run_id=%s stored=%s pdf=%s airtable=%s",
                outcome.run_id, outcome.stored, outcome.has_pdf,
                outcome.airtable_record_ids)
    return outcome
