"""Data Quality Report (HTML) - the self-contained report builder.

``build_report`` turns real ``ScorecardResult`` / config / data-product
objects (plus the run metadata in :class:`ReportContext`) into ONE
standalone ``.html`` - no CDN, no fonts, no Plotly, no external JS/CSS -
that works from ``file:///`` with no internet and no Streamlit. It is a
published data product; a future ``publish_report()`` (SharePoint or
other) consumes the returned :class:`ReportArtifact` unchanged.

``build_executive_report_html`` is the backwards-compatible alias
returning just the HTML bytes (the previous builder's contract).

The builder never touches Streamlit - ``ui/step_06/_exec_report.py`` is
the thin wrapper that assembles a ``ReportContext`` from session state.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional

from ui.step_06.report import collect, sections
from ui.step_06.report.html import document
from ui.step_06.report.interactivity import REPORT_JS, safe_json_for_script
from ui.step_06.report.models import ReportArtifact, ReportCaps, ReportContext
from ui.step_06.report.styles import REPORT_CSS

__all__ = [
    "ReportArtifact",
    "ReportCaps",
    "ReportContext",
    "build_executive_report_html",
    "build_report",
]


def _filename(ctx: ReportContext) -> str:
    domain = (ctx.domain_code or "report").upper()
    try:
        stamp = datetime.fromisoformat(
            ctx.generated_at.replace("Z", "+00:00")
        ).strftime("%Y%m%d_%H%M%S")
    except ValueError:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"dq_scorecard_report_{domain}_{stamp}.html"


def build_report(ctx: ReportContext, scorecards: Dict[str, object],
                 dps: Dict[str, object],
                 configs: Dict[str, object]) -> ReportArtifact:
    """Build the full Data Quality Report for one scorecard run.

    ``scorecards`` / ``dps`` / ``configs`` are keyed by system code; a
    code missing from ``dps`` or ``configs`` is skipped (same behaviour
    as the previous builder). History and drift come from the persisted
    run store via :mod:`src.run_history`.
    """
    views = [
        collect.build_dp_view(code, dps[code], result, configs[code], ctx)
        for code, result in scorecards.items()
        if code in dps and code in configs
    ]

    data_json = safe_json_for_script({
        "green": ctx.threshold_green,
        "yellow": ctx.threshold_yellow,
        "caps": {
            "worst_rows": ctx.caps.worst_rows,
            "drill_rows": ctx.caps.drill_rows,
            "row_store": ctx.caps.row_store,
        },
        "dps": {v["code"]: v["store_json"] for v in views},
    })

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
    title_parts = ["Data Quality Scorecard Report"]
    if ctx.domain_name or ctx.domain_code:
        title_parts.append(ctx.domain_name or ctx.domain_code)
    if date:
        title_parts.append(date)
    html_text = document(
        title=" · ".join(title_parts),
        css=REPORT_CSS,
        body=body,
        data_json=data_json,
        js=REPORT_JS,
    )
    return ReportArtifact(
        html=html_text.encode("utf-8"),
        filename=_filename(ctx),
        metadata={
            "domain_code": ctx.domain_code,
            "domain_name": ctx.domain_name,
            "dp_codes": [v["code"] for v in views],
            "generated_at": ctx.generated_at,
            "generated_by": ctx.generated_by,
            "run_id": ctx.run_id,
            "overall_scores": {
                v["code"]: round(float(v["result"].overall_score), 2)
                for v in views
            },
        },
    )


def build_executive_report_html(
    domain_code: str, scorecards: Dict[str, object], dps: Dict[str, object],
    configs: Dict[str, object], ctx: Optional[ReportContext] = None,
) -> bytes:
    """Compatibility alias: the report as UTF-8 bytes.

    Builds a minimal :class:`ReportContext` when none is given (metadata
    fields the caller didn't provide render as an em dash - the builder
    never invents values).
    """
    if ctx is None:
        first = next(iter(scorecards.values()), None)
        ctx = ReportContext(
            domain_code=domain_code,
            dp_codes=list(scorecards.keys()),
            generated_at=datetime.now(timezone.utc).isoformat(
                timespec="seconds").replace("+00:00", "Z"),
            threshold_green=(float(first.threshold_green)
                             if first is not None else 80.0),
            threshold_yellow=(float(first.threshold_yellow)
                              if first is not None else 60.0),
        )
    return build_report(ctx, scorecards, dps, configs).html
