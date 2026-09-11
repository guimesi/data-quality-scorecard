"""Data Quality Report - two artefacts from ONE view model.

``build_report`` turns real ``ScorecardResult`` / config / data-product
objects (plus the run metadata in :class:`ReportContext`) into a
:class:`ReportArtifacts`:

- the **interactive HTML** - ONE standalone ``.html`` (no CDN, no fonts,
  no Plotly, no external JS/CSS) that works from ``file:///`` and is
  hosted by the app at ``/reports/<run_id>``;
- the **PDF edition** - a paginated A4 HTML (``pdf_html``, print-ready
  in any Chromium browser) converted with headless Chromium into
  ``pdf`` bytes when a converter is available (see
  :mod:`ui.step_06.report.convert`).

Pipeline::

    ScorecardResult + Config + history
            │
            ▼
    collect.build_model()  ──►  ReportModel
            ├── render_interactive(model) ─► html
            └── pdf.render_pdf_html(model) ─► pdf_html ─► convert.html_to_pdf() ─► pdf

``build_executive_report_html`` is the backwards-compatible alias
returning just the interactive HTML bytes (the previous builder's
contract). The builder never touches Streamlit -
``ui/step_06/_exec_report.py`` is the thin wrapper that assembles a
``ReportContext`` from session state.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from ui.step_06.report import collect, sections
from ui.step_06.report.convert import PdfConversionUnavailable, html_to_pdf
from ui.step_06.report.html import document
from ui.step_06.report.interactivity import REPORT_JS, safe_json_for_script
from ui.step_06.report.models import (
    ReportArtifact,
    ReportArtifacts,
    ReportCaps,
    ReportContext,
    ReportModel,
)
from ui.step_06.report.pdf import count_pages, render_pdf_html
from ui.step_06.report.styles import REPORT_CSS

logger = logging.getLogger(__name__)

__all__ = [
    "ReportArtifact",
    "ReportArtifacts",
    "ReportCaps",
    "ReportContext",
    "ReportModel",
    "build_executive_report_html",
    "build_model",
    "build_report",
    "filenames_for",
    "render_interactive",
    "render_pdf_html",
]

build_model = collect.build_model


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def _stamp(ctx: ReportContext) -> str:
    try:
        return datetime.fromisoformat(
            ctx.generated_at.replace("Z", "+00:00")
        ).strftime("%Y%m%d_%H%M%S")
    except ValueError:
        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def filenames_for(ctx: ReportContext) -> Dict[str, str]:
    """``dq_scorecard_report_<DOMAIN>_<YYYYMMDD_HHMMSS>.<ext>`` per artefact."""
    base = f"dq_scorecard_report_{(ctx.domain_code or 'report').upper()}_{_stamp(ctx)}"
    return {
        "interactive": f"{base}.html",
        "pdf": f"{base}.pdf",
        "pdf_html": f"{base}_print.html",
    }


def _ensure_run_id(ctx: ReportContext) -> ReportContext:
    """Every artefact set needs an identifier (it keys the report store
    and the ``/reports/<run_id>`` link); mint one when the caller did not."""
    if ctx.run_id:
        return ctx
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return replace(ctx, run_id=f"run_{stamp}_{uuid.uuid4().hex[:4]}")


def render_interactive(model: ReportModel) -> str:
    """The interactive edition (self-contained HTML) of ``model``."""
    ctx = model.ctx
    views = model.dps
    body = (
        sections.render_nav(views)
        + '\n<main class="wrap">\n'
        + sections.render_header(ctx) + "\n"
        + sections.render_summary(views, ctx) + "\n"
        + "\n".join(sections.render_dp(v, ctx) for v in views)
        + "\n" + sections.render_footer(ctx)
        + "\n</main>"
    )
    date = (ctx.generated_at or "")[:10]
    title = sections.report_title(ctx) + (f" · {date}" if date else "")
    return document(
        title=title,
        css=REPORT_CSS,
        body=body,
        data_json=safe_json_for_script(model.data),
        js=REPORT_JS,
    )


def build_report(ctx: ReportContext, scorecards: Dict[str, object],
                 dps: Dict[str, object], configs: Dict[str, object], *,
                 want_pdf: bool = True,
                 converter: Optional[Callable[[str], bytes]] = None,
                 ) -> ReportArtifacts:
    """Build both editions of the Data Quality Report for one run.

    ``scorecards`` / ``dps`` / ``configs`` are keyed by system code; a
    code missing from ``dps`` or ``configs`` is skipped. History and
    drift come from the persisted run store via :mod:`src.run_history`.

    ``want_pdf=False`` skips the Chromium conversion (the print-ready
    HTML is still produced); ``converter`` overrides the converter
    detection. A failed conversion never fails the build: ``pdf`` is
    ``None`` and ``metadata["pdf_error"]`` carries the reason.
    """
    ctx = _ensure_run_id(ctx)
    model = build_model(ctx, scorecards, dps, configs)
    html_text = render_interactive(model)
    pdf_html = render_pdf_html(model)

    pdf_bytes: Optional[bytes] = None
    pdf_error: Optional[str] = None
    if want_pdf:
        try:
            pdf_bytes = html_to_pdf(pdf_html, converter=converter)
        except PdfConversionUnavailable as exc:
            pdf_error = str(exc)
            logger.info("PDF edition not rendered: %s", exc)
        except Exception as exc:  # converter crashed: degrade, don't fail
            pdf_error = f"{type(exc).__name__}: {exc}"
            logger.warning("PDF conversion failed", exc_info=True)
    else:
        pdf_error = "PDF conversion not requested"

    views = model.dps
    caps = ctx.caps
    metadata = {
        # Every ReportContext field travels with the artefacts for the
        # publisher, including the ones the report does not render
        # (mode, data scope, thresholds, saved project).
        "run_id": ctx.run_id,
        "domain_code": ctx.domain_code,
        "domain_name": ctx.domain_name,
        "dp_codes": [v["code"] for v in views],
        "dp_names": {v["code"]: v["name"] for v in views},
        "generated_at": ctx.generated_at,
        "generated_by": ctx.generated_by,
        "mode": ctx.mode,
        "data_scope": ctx.data_scope,
        "sample_rows_cap": ctx.sample_rows_cap,
        "project_filter": list(ctx.project_filter),
        "threshold_green": ctx.threshold_green,
        "threshold_yellow": ctx.threshold_yellow,
        "saved_project": ctx.saved_project,
        "overall_scores": {
            v["code"]: round(float(v["result"].overall_score), 2) for v in views
        },
        "statuses": {v["code"]: v["bucket"] for v in views},
        "row_counts": {v["code"]: int(v["result"].total_rows) for v in views},
        "config_hashes": {v["code"]: v["config_hash"] for v in views},
        "caps": {
            "worst_rows": caps.worst_rows, "drill_rows": caps.drill_rows,
            "row_store": caps.row_store, "pdf_rows": caps.pdf_rows,
            "pdf_sample_rows": caps.pdf_sample_rows,
            "pdf_run_log": caps.pdf_run_log,
        },
        "pdf_pages": count_pages(pdf_html),
        "has_pdf": pdf_bytes is not None,
        "pdf_error": pdf_error,
    }
    return ReportArtifacts(
        run_id=ctx.run_id or "",
        domain_code=ctx.domain_code,
        generated_at=ctx.generated_at,
        html=html_text.encode("utf-8"),
        pdf=pdf_bytes,
        pdf_html=pdf_html.encode("utf-8"),
        metadata=metadata,
        filenames=filenames_for(ctx),
    )


def build_executive_report_html(
    domain_code: str, scorecards: Dict[str, object], dps: Dict[str, object],
    configs: Dict[str, object], ctx: Optional[ReportContext] = None,
) -> bytes:
    """Compatibility alias: the interactive report as UTF-8 bytes.

    Builds a minimal :class:`ReportContext` when none is given (metadata
    fields the caller didn't provide render as an em dash - the builder
    never invents values) and skips the PDF conversion.
    """
    if ctx is None:
        first = next(iter(scorecards.values()), None)
        ctx = ReportContext(
            domain_code=domain_code,
            dp_codes=list(scorecards.keys()),
            generated_at=_utc_now_iso(),
            threshold_green=(float(first.threshold_green)
                             if first is not None else 80.0),
            threshold_yellow=(float(first.threshold_yellow)
                              if first is not None else 60.0),
        )
    return build_report(ctx, scorecards, dps, configs, want_pdf=False).html
