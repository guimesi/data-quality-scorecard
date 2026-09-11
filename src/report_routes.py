"""HTTP routes that serve stored Data Quality Reports from the app.

Mounted next to Streamlit by ``server.py`` (``st.App(routes=...)``):

- ``GET /reports``                 index of stored runs (HTML; ``?format=json``
                                   for the raw metadata list)
- ``GET /reports/{run_id}``        the interactive edition (``text/html``)
- ``GET /reports/{run_id}/pdf``    the PDF edition (``application/pdf``)
- ``GET /reports/{run_id}/pdf_html``  the print-ready HTML
- ``GET /reports/{run_id}/metadata``  the run metadata (JSON)
- ``GET /reports/latest/{domain}[/{kind}]``  redirects (302, uncached) to
  the newest stored run of that domain - the fixed link for an Airtable
  button or a SharePoint page.

Authentication is the app's own: in Databricks Apps every request is
authenticated by the platform before it reaches this process, so a link
pasted in SharePoint only works for users entitled to the app.

Security: ``run_id`` is validated before it touches storage (no path
traversal); every response carries ``X-Content-Type-Options: nosniff``;
the HTML editions get a Content-Security-Policy that allows only their
own inline script/style and blocks every network fetch, so a hostile
value rendered inside a report can never reach out. Nothing here
imports Streamlit at module level.
"""
from __future__ import annotations

import html as _html
import re
from typing import Any, Dict, List, Optional

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from starlette.routing import Route

from src import report_store

_CSP_REPORT = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
)
_CSP_INDEX = ("default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
              "form-action 'none'")
_CACHE = "private, max-age=3600"

_KIND_EXT = {"html": ".html", "pdf": ".pdf", "pdf_html": "_print.html",
             "metadata": ".json"}
_DOMAIN_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _esc(value: object) -> str:
    return _html.escape(str(value), quote=True)


def _secure(response: Response, csp: Optional[str] = None) -> Response:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = _CACHE
    response.headers["Referrer-Policy"] = "no-referrer"
    if csp:
        response.headers["Content-Security-Policy"] = csp
    return response


def _filename(meta: Optional[Dict[str, Any]], run_id: str, kind: str) -> str:
    names = (meta or {}).get("filenames") or {}
    key = "interactive" if kind == "html" else kind
    name = names.get(key) if isinstance(names, dict) else None
    if isinstance(name, str) and name and "/" not in name and "\\" not in name:
        return name
    return f"{run_id}{_KIND_EXT.get(kind, '')}"


async def get_report(request: Request) -> Response:
    """One stored artefact of a run (``kind`` defaults to the interactive
    edition)."""
    run_id = request.path_params.get("run_id", "")
    kind = request.path_params.get("kind", "html")
    if not report_store.is_valid_run_id(run_id) or kind not in report_store.KINDS:
        return _secure(PlainTextResponse("Not found", status_code=404))
    data = await run_in_threadpool(report_store.load_report, run_id, kind)
    if data is None:
        return _secure(PlainTextResponse(
            "Report not found - it may not have been stored, or the report "
            "store is disabled.", status_code=404))
    meta = await run_in_threadpool(report_store.load_metadata, run_id)
    filename = _filename(meta, run_id, kind)
    response = Response(
        content=data, media_type=report_store.KINDS[kind]["mime"],
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
    csp = _CSP_REPORT if kind in ("html", "pdf_html") else None
    return _secure(response, csp)


async def get_latest(request: Request) -> Response:
    """Redirect to the newest stored run of ``domain`` (optionally one
    ``kind`` of it). Never cached, so the fixed link follows new runs."""
    domain = request.path_params.get("domain", "")
    kind = request.path_params.get("kind", "html")
    if not _DOMAIN_RE.match(domain) or kind not in report_store.KINDS:
        return _secure(PlainTextResponse("Not found", status_code=404))
    run_id = await run_in_threadpool(report_store.latest_run_id, domain)
    if run_id is None:
        response = _secure(PlainTextResponse(
            f"No stored report for domain {domain!r} yet.", status_code=404))
    else:
        response = _secure(RedirectResponse(
            report_store.report_url(run_id, kind), status_code=302))
    response.headers["Cache-Control"] = "no-store"
    return response


def _index_html(reports: List[Dict[str, Any]]) -> str:
    rows = []
    for m in reports:
        run_id = str(m.get("run_id", ""))
        if not report_store.is_valid_run_id(run_id):
            continue
        scores = m.get("overall_scores") or {}
        statuses = m.get("statuses") or {}
        dps = " · ".join(
            f"{_esc(code)} {_esc(scores.get(code, '—'))} "
            f"({_esc(statuses.get(code, '—'))})"
            for code in (m.get("dp_codes") or [])
        )
        pdf = (f' · <a href="/reports/{_esc(run_id)}/pdf">PDF</a>'
               if m.get("has_pdf") else "")
        rows.append(
            f"<tr><td>{_esc(m.get('generated_at', ''))}</td>"
            f"<td>{_esc(m.get('domain_name') or m.get('domain_code', ''))}</td>"
            f"<td>{dps}</td><td>{_esc(m.get('generated_by', ''))}</td>"
            f'<td><a href="/reports/{_esc(run_id)}">Interactive</a>{pdf}</td>'
            f"<td><code>{_esc(run_id)}</code></td></tr>"
        )
    body = "".join(rows) or ('<tr><td colspan="6">No stored reports yet.</td>'
                             "</tr>")
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>Data Quality Reports</title><style>"
        'body{font:14px/1.5 "Segoe UI",-apple-system,Helvetica,Arial,sans-serif;'
        "color:#1f2937;margin:32px;max-width:1100px}table{border-collapse:collapse;"
        "width:100%}th,td{padding:6px 10px;border-bottom:1px solid #e5e7eb;"
        "text-align:left;vertical-align:top}th{font-size:11.5px;text-transform:"
        "uppercase;color:#64748b}code{font-size:.9em;background:#f1f5f9;"
        "padding:.1em .4em;border-radius:4px}a{color:#3b4d8f}</style></head>"
        "<body><h1>Data Quality Reports</h1><p>Every stored run, newest first. "
        "Links open the report served by this app. The newest run of a domain "
        "is always at <code>/reports/latest/&lt;DOMAIN&gt;</code> "
        "(<code>/pdf</code> for the PDF edition).</p>"
        "<table><thead><tr><th>Generated (UTC)</th><th>Domain</th>"
        "<th>Data Products</th><th>By</th><th>Editions</th><th>Run</th></tr>"
        f"</thead><tbody>{body}</tbody></table></body></html>"
    )


async def list_reports(request: Request) -> Response:
    reports = await run_in_threadpool(report_store.list_reports)
    if request.query_params.get("format") == "json":
        return _secure(JSONResponse(reports))
    return _secure(HTMLResponse(_index_html(reports)), _CSP_INDEX)


def report_routes() -> List[Route]:
    """The Starlette routes to mount alongside Streamlit."""
    return [
        Route("/reports", list_reports, methods=["GET"]),
        # ``latest`` routes first: "latest" would otherwise match {run_id}.
        Route("/reports/latest/{domain}", get_latest, methods=["GET"]),
        Route("/reports/latest/{domain}/{kind}", get_latest, methods=["GET"]),
        Route("/reports/{run_id}", get_report, methods=["GET"]),
        Route("/reports/{run_id}/{kind}", get_report, methods=["GET"]),
    ]
