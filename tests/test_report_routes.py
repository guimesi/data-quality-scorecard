"""Tests for the ``/reports`` routes (``src/report_routes.py``) and the
``server.py`` ASGI entry point.

The routes are exercised through a minimal in-process ASGI client (no
HTTP client dependency) against a Starlette app carrying only the report
routes, backed by the local report store in a temp dir."""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("DATA_SOURCE", "mock")

import pytest
from starlette.applications import Starlette

from config.settings import Settings
from src import report_store as rs
from src.report_routes import report_routes
from ui.step_06.report.models import ReportArtifacts

RUN = "run_20260910_120000_ab12"


def _artifacts(run_id: str = RUN, pdf=b"%PDF-1.7 fake",
               generated_at: str = "2026-09-10T12:00:00Z"):
    return ReportArtifacts(
        run_id=run_id, domain_code="cost_estimate",
        generated_at=generated_at,
        html=b"<!DOCTYPE html><html><body>interactive <b>x</b></body></html>",
        pdf=pdf, pdf_html=b"<!DOCTYPE html><html>print</html>",
        metadata={"dp_codes": ["EPT"], "overall_scores": {"EPT": 81.5},
                  "statuses": {"EPT": "green"}, "generated_by": "<tester>",
                  "domain_name": "Cost <Estimate>"},
        filenames={"interactive": "dq_scorecard_report_X.html",
                   "pdf": "dq_scorecard_report_X.pdf",
                   "pdf_html": "dq_scorecard_report_X_print.html"},
    )


def _get(app, path: str, query: str = ""):
    """Minimal ASGI GET: returns ``(status, headers, body)``."""
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": path,
        "raw_path": path.encode(), "query_string": query.encode(),
        "headers": [], "client": ("127.0.0.1", 1), "server": ("test", 80),
        "root_path": "",
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    headers = {k.decode().lower(): v.decode() for k, v in start["headers"]}
    body = b"".join(m.get("body", b"") for m in messages
                    if m["type"] == "http.response.body")
    return start["status"], headers, body


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "SETTINGS", Settings(
        data_source="mock", report_store="local", store_dir=str(tmp_path)))
    rs.reset_report_store()
    yield Starlette(routes=report_routes())
    rs.reset_report_store()


def test_interactive_report_is_served_as_html(app):
    art = _artifacts()
    assert rs.save_artifacts(art)
    status, headers, body = _get(app, f"/reports/{RUN}")
    assert status == 200
    assert body == art.html
    assert headers["content-type"].startswith("text/html")
    assert headers["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in headers["content-security-policy"]
    assert "script-src 'unsafe-inline'" in headers["content-security-policy"]
    assert headers["content-disposition"] == \
        'inline; filename="dq_scorecard_report_X.html"'
    assert headers["cache-control"].startswith("private")


def test_pdf_and_print_editions_and_metadata(app):
    art = _artifacts()
    rs.save_artifacts(art)
    status, headers, body = _get(app, f"/reports/{RUN}/pdf")
    assert status == 200 and body == art.pdf
    assert headers["content-type"] == "application/pdf"
    assert "content-security-policy" not in headers
    assert headers["content-disposition"] == \
        'inline; filename="dq_scorecard_report_X.pdf"'

    status, headers, body = _get(app, f"/reports/{RUN}/pdf_html")
    assert status == 200 and body == art.pdf_html
    assert "content-security-policy" in headers

    status, headers, body = _get(app, f"/reports/{RUN}/metadata")
    assert status == 200
    assert headers["content-type"] == "application/json"
    assert b'"run_id": "run_20260910_120000_ab12"' in body


def test_missing_pdf_is_404_not_500(app):
    rs.save_artifacts(_artifacts(pdf=None))
    status, _, body = _get(app, f"/reports/{RUN}/pdf")
    assert status == 404
    assert b"not found" in body.lower()


@pytest.mark.parametrize("path", [
    "/reports/run_does_not_exist",
    "/reports/..%2F..%2Fetc%2Fpasswd",
    "/reports/a%20b",
    f"/reports/{RUN}/exe",
])
def test_unknown_or_hostile_paths_are_404(app, path):
    rs.save_artifacts(_artifacts())
    status, headers, _ = _get(app, path)
    assert status == 404
    assert headers["x-content-type-options"] == "nosniff"


def test_index_lists_runs_escaped_and_json(app):
    rs.save_artifacts(_artifacts())
    status, headers, body = _get(app, "/reports")
    assert status == 200
    text = body.decode("utf-8")
    assert headers["content-type"].startswith("text/html")
    assert f'href="/reports/{RUN}"' in text
    assert f'href="/reports/{RUN}/pdf"' in text
    assert "&lt;tester&gt;" in text and "<tester>" not in text
    assert "Cost &lt;Estimate&gt;" in text
    assert "EPT 81.5 (green)" in text
    assert "default-src 'none'" in headers["content-security-policy"]

    status, headers, body = _get(app, "/reports", "format=json")
    assert status == 200
    assert headers["content-type"] == "application/json"
    assert b'"run_id":"run_20260910_120000_ab12"' in body.replace(b" ", b"")


def test_index_when_store_is_empty_or_off(app, monkeypatch):
    status, _, body = _get(app, "/reports")
    assert status == 200 and b"No stored reports yet" in body
    monkeypatch.setattr(rs, "SETTINGS", Settings(data_source="mock",
                                                 report_store="off"))
    rs.reset_report_store()
    status, _, body = _get(app, f"/reports/{RUN}")
    assert status == 404 and b"disabled" in body


def test_latest_redirects_to_newest_run_of_the_domain(app):
    rs.save_artifacts(_artifacts(run_id="run_old", generated_at="2026-09-01T10:00:00Z"))
    rs.save_artifacts(_artifacts(run_id="run_new", generated_at="2026-09-02T10:00:00Z"))
    status, headers, _ = _get(app, "/reports/latest/COST_ESTIMATE")
    assert status == 302
    assert headers["location"] == "/reports/run_new"
    assert headers["cache-control"] == "no-store"      # follows new runs
    assert headers["x-content-type-options"] == "nosniff"
    status, headers, _ = _get(app, "/reports/latest/cost_estimate/pdf")
    assert status == 302 and headers["location"] == "/reports/run_new/pdf"


@pytest.mark.parametrize("path, status", [
    ("/reports/latest/QUALITY", 404),              # no run of that domain
    ("/reports/latest/COST_ESTIMATE/exe", 404),    # unknown kind
    ("/reports/latest/a%20b", 404),                # hostile domain
])
def test_latest_unknown_cases_are_404(app, path, status):
    rs.save_artifacts(_artifacts())
    got, headers, body = _get(app, path)
    assert got == status
    assert headers["cache-control"] == "no-store" or b"Not found" in body


def test_index_mentions_the_fixed_latest_link(app):
    _, _, body = _get(app, "/reports")
    assert b"/reports/latest/&lt;DOMAIN&gt;" in body


def test_server_entry_point_mounts_the_routes():
    """``server.py`` exposes an ``st.App`` (what ``streamlit run server.py``
    discovers) with the /reports routes attached."""
    import importlib

    import streamlit as st

    server = importlib.import_module("server")
    assert isinstance(server.app, st.App)
    paths = [r.path for r in server.app._user_routes]
    assert paths == ["/reports", "/reports/latest/{domain}",
                     "/reports/latest/{domain}/{kind}", "/reports/{run_id}",
                     "/reports/{run_id}/{kind}"]   # latest before {run_id}
