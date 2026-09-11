"""Tests for the SharePoint publisher (``src/sharepoint_push.py``) and
its Step 6 button.

All HTTP is faked at the ``requests.request`` seam - no network, no
credentials. The fake Graph records every call so the tests assert the
exact sequence: token -> drive lookup -> folder creation -> uploads.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATA_SOURCE", "mock")

from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import unquote

import pytest

import src.sharepoint_push as sp
from ui.step_06.report.models import ReportArtifacts

# ==================================================================== fakes


def _settings(**overrides):
    base = dict(
        sharepoint_tenant_id="tenant-1", sharepoint_client_id="client-1",
        sharepoint_client_secret="s3cret",
        sharepoint_site="contoso.sharepoint.com:/sites/DQ",
        sharepoint_drive_id="", sharepoint_folder="DQ Reports",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _Resp:
    def __init__(self, payload=None, status_code=200, text="", headers=None):
        self._payload = payload
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = text if text else (json.dumps(payload) if payload is not None else "")
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _artifacts(pdf=b"%PDF-1.7 fake"):
    return ReportArtifacts(
        run_id="run_20260911_120000_ab12", domain_code="cost_estimate",
        generated_at="2026-09-11T12:00:00Z",
        html=b"<!DOCTYPE html><html>interactive</html>", pdf=pdf,
        pdf_html=b"<!DOCTYPE html><html>print</html>",
        metadata={"dp_codes": ["EPT"], "overall_scores": {"EPT": 81.5},
                  "generated_by": "tester"},
        filenames={"interactive": "dq_scorecard_report_COST_ESTIMATE_20260911_120000.html",
                   "pdf": "dq_scorecard_report_COST_ESTIMATE_20260911_120000.pdf",
                   "pdf_html": "dq_scorecard_report_COST_ESTIMATE_20260911_120000_print.html"},
    )


class _FakeGraph:
    """Minimal Graph: token, site drive, folder children, uploads."""

    def __init__(self, folder_exists=False):
        self.calls = []
        self.folder_exists = folder_exists

    def __call__(self, method, url, json=None, data=None, headers=None, timeout=None):
        self.calls.append(SimpleNamespace(method=method, url=url, json=json,
                                          data=data, headers=headers or {}))
        if url.startswith(sp.LOGIN_ROOT):
            return _Resp({"access_token": "tok-123", "expires_in": 3600})
        if url.endswith("/sites/contoso.sharepoint.com:/sites/DQ/drive"):
            return _Resp({"id": "drive-9"})
        if url.endswith("/children"):
            if self.folder_exists:
                return _Resp({"error": {"code": "nameAlreadyExists",
                                        "message": "exists"}}, status_code=409)
            return _Resp({"id": "folder", "name": json["name"]}, status_code=201)
        if url.endswith("/createUploadSession"):
            return _Resp({"uploadUrl": "https://upload.example/session-1"})
        if url.startswith("https://upload.example/"):
            rng = headers["Content-Range"]              # bytes a-b/total
            end, total = rng.split(" ")[1].split("/")[0].split("-")[1], rng.split("/")[1]
            if int(end) + 1 == int(total):
                return _Resp({"name": "big.pdf", "webUrl": "https://sp/big.pdf",
                              "size": int(total)}, status_code=201)
            return _Resp({"nextExpectedRanges": [f"{int(end) + 1}-"]}, status_code=202)
        if "/content" in url:
            name = unquote(url.split("root:/")[1].split(":/content")[0]).rsplit("/", 1)[-1]
            return _Resp({"name": name, "webUrl": f"https://sp/{name}",
                          "size": len(data)}, status_code=201)
        return _Resp({"error": {"code": "unexpected", "message": url}}, 400)


@pytest.fixture
def graph(monkeypatch):
    monkeypatch.setattr(sp, "SETTINGS", _settings())
    fake = _FakeGraph()
    monkeypatch.setattr(sp.requests, "request", fake)
    monkeypatch.setattr(sp.time, "sleep", lambda s: None)
    return fake


# ==================================================================== plan


def test_publish_plan_lists_pdf_html_metadata_and_latest_copies(monkeypatch):
    monkeypatch.setattr(sp, "SETTINGS", _settings())
    art = _artifacts()
    plan = sp.publish_plan(art, hosted_url="https://app/reports/run_20260911_120000_ab12")
    paths = [p for p, _ in plan]
    assert paths == [
        "DQ Reports/COST_ESTIMATE/dq_scorecard_report_COST_ESTIMATE_20260911_120000.pdf",
        "DQ Reports/COST_ESTIMATE/dq_scorecard_report_COST_ESTIMATE_20260911_120000.html",
        "DQ Reports/COST_ESTIMATE/dq_scorecard_report_COST_ESTIMATE_20260911_120000.json",
        "DQ Reports/COST_ESTIMATE/dq_scorecard_report_COST_ESTIMATE_latest.pdf",
        "DQ Reports/COST_ESTIMATE/dq_scorecard_report_COST_ESTIMATE_latest.html",
    ]
    meta = json.loads(dict(plan)[paths[2]].decode("utf-8"))
    assert meta["run_id"] == "run_20260911_120000_ab12"
    assert meta["hosted_url"] == "https://app/reports/run_20260911_120000_ab12"
    assert meta["overall_scores"] == {"EPT": 81.5}
    assert meta["has_pdf"] is True
    assert dict(plan)[paths[3]] == art.pdf and dict(plan)[paths[4]] == art.html


def test_publish_plan_without_pdf_skips_pdf_files(monkeypatch):
    monkeypatch.setattr(sp, "SETTINGS", _settings(sharepoint_folder="/Reports/"))
    paths = [p for p, _ in sp.publish_plan(_artifacts(pdf=None))]
    assert paths == [
        "Reports/COST_ESTIMATE/dq_scorecard_report_COST_ESTIMATE_20260911_120000.html",
        "Reports/COST_ESTIMATE/dq_scorecard_report_COST_ESTIMATE_20260911_120000.json",
        "Reports/COST_ESTIMATE/dq_scorecard_report_COST_ESTIMATE_latest.html",
    ]


# ==================================================================== publish


def test_publish_report_sequence_token_drive_folders_uploads(graph):
    result = sp.publish_report(_artifacts(), hosted_url="https://app/reports/x")

    calls = graph.calls
    # 1) client-credentials token
    assert calls[0].method == "POST"
    assert calls[0].url == f"{sp.LOGIN_ROOT}/tenant-1/oauth2/v2.0/token"
    assert calls[0].data["grant_type"] == "client_credentials"
    assert calls[0].data["client_id"] == "client-1"
    assert calls[0].data["client_secret"] == "s3cret"
    assert calls[0].data["scope"] == sp.GRAPH_SCOPE
    # 2) default drive of the site (path form)
    assert calls[1].method == "GET"
    assert calls[1].url == f"{sp.GRAPH_ROOT}/sites/contoso.sharepoint.com:/sites/DQ/drive"
    assert calls[1].headers["Authorization"] == "Bearer tok-123"
    # 3) folder + sub-folder, created with conflictBehavior=fail
    assert calls[2].url == f"{sp.GRAPH_ROOT}/drives/drive-9/root/children"
    assert calls[2].json == {"name": "DQ Reports", "folder": {},
                             "@microsoft.graph.conflictBehavior": "fail"}
    assert calls[3].url == f"{sp.GRAPH_ROOT}/drives/drive-9/root:/DQ%20Reports:/children"
    assert calls[3].json["name"] == "COST_ESTIMATE"
    # 4) five simple uploads, replace semantics, octet-stream bodies
    uploads = calls[4:]
    assert len(uploads) == 5
    assert all(c.method == "PUT" and c.url.endswith(
        ":/content?@microsoft.graph.conflictBehavior=replace") for c in uploads)
    assert all(c.headers["Content-Type"] == "application/octet-stream" for c in uploads)
    assert uploads[0].url.startswith(
        f"{sp.GRAPH_ROOT}/drives/drive-9/root:/DQ%20Reports/COST_ESTIMATE/"
        "dq_scorecard_report_COST_ESTIMATE_20260911_120000.pdf:")
    assert uploads[0].data == b"%PDF-1.7 fake"
    assert uploads[-1].url.endswith(
        "dq_scorecard_report_COST_ESTIMATE_latest.html:/content"
        "?@microsoft.graph.conflictBehavior=replace")

    assert result.folder_path == "DQ Reports/COST_ESTIMATE"
    assert [f.name for f in result.files] == [
        "dq_scorecard_report_COST_ESTIMATE_20260911_120000.pdf",
        "dq_scorecard_report_COST_ESTIMATE_20260911_120000.html",
        "dq_scorecard_report_COST_ESTIMATE_20260911_120000.json",
        "dq_scorecard_report_COST_ESTIMATE_latest.pdf",
        "dq_scorecard_report_COST_ESTIMATE_latest.html",
    ]
    assert result.pdf_url == "https://sp/dq_scorecard_report_COST_ESTIMATE_20260911_120000.pdf"
    assert result.latest_pdf_url == "https://sp/dq_scorecard_report_COST_ESTIMATE_latest.pdf"


def test_existing_folders_are_fine(graph):
    graph.folder_exists = True
    result = sp.publish_report(_artifacts(pdf=None))
    assert len(result.files) == 3
    assert [c.url for c in graph.calls if c.url.endswith("/children")]  # tried


def test_explicit_drive_id_skips_site_lookup(monkeypatch, graph):
    monkeypatch.setattr(sp, "SETTINGS", _settings(sharepoint_drive_id="drive-X"))
    sp.publish_report(_artifacts(pdf=None))
    assert not any("/sites/" in c.url for c in graph.calls)
    assert graph.calls[1].url == f"{sp.GRAPH_ROOT}/drives/drive-X/root/children"


def test_large_file_uses_upload_session_in_chunks(monkeypatch, graph):
    monkeypatch.setattr(sp, "SIMPLE_UPLOAD_LIMIT", 100)
    monkeypatch.setattr(sp, "CHUNK_SIZE", 64)
    big = b"x" * 150
    item = sp.upload_file("tok", "drive-9", "DQ Reports/COST_ESTIMATE/big.pdf", big)
    session = [c for c in graph.calls if c.url.endswith("/createUploadSession")]
    assert len(session) == 1
    assert session[0].json == {"item": {"@microsoft.graph.conflictBehavior": "replace",
                                        "name": "big.pdf"}}
    chunks = [c for c in graph.calls if c.url.startswith("https://upload.example/")]
    assert [c.headers["Content-Range"] for c in chunks] == [
        "bytes 0-63/150", "bytes 64-127/150", "bytes 128-149/150"]
    assert [len(c.data) for c in chunks] == [64, 64, 22]
    assert "Authorization" not in chunks[0].headers   # pre-authenticated URL
    assert item.web_url == "https://sp/big.pdf" and item.size == 150


def test_throttling_is_retried_with_retry_after(monkeypatch):
    monkeypatch.setattr(sp, "SETTINGS", _settings())
    waits = []
    monkeypatch.setattr(sp.time, "sleep", waits.append)
    responses = [_Resp({"error": {"code": "tooManyRequests", "message": "slow"}},
                       status_code=429, headers={"Retry-After": "3"}),
                 _Resp({"access_token": "tok"})]
    monkeypatch.setattr(sp.requests, "request", lambda *a, **k: responses.pop(0))
    assert sp.acquire_token() == "tok"
    assert waits == [3.0]


def test_graph_error_becomes_push_error_with_code_and_step(monkeypatch):
    monkeypatch.setattr(sp, "SETTINGS", _settings())
    monkeypatch.setattr(sp.requests, "request", lambda *a, **k: _Resp(
        {"error": {"code": "accessDenied", "message": "Sites.Selected missing"}},
        status_code=403))
    with pytest.raises(sp.SharePointPushError,
                       match="403 during token request.*accessDenied: Sites.Selected"):
        sp.acquire_token()


def test_transport_error_becomes_push_error(monkeypatch):
    monkeypatch.setattr(sp, "SETTINGS", _settings())

    def boom(*a, **k):
        raise sp.requests.ConnectionError("egress blocked")

    monkeypatch.setattr(sp.requests, "request", boom)
    with pytest.raises(sp.SharePointPushError, match="Could not reach"):
        sp.publish_report(_artifacts())


def test_not_configured_raises_and_is_hidden(monkeypatch):
    monkeypatch.setattr(sp, "SETTINGS", _settings(sharepoint_client_secret=""))
    assert not sp.is_configured()
    with pytest.raises(sp.SharePointPushError, match="not configured"):
        sp.publish_report(_artifacts())


def test_non_json_token_response_is_reported(monkeypatch):
    monkeypatch.setattr(sp, "SETTINGS", _settings())
    monkeypatch.setattr(sp.requests, "request",
                        lambda *a, **k: _Resp(None, text="<html>proxy block</html>"))
    with pytest.raises(sp.SharePointPushError, match="Non-JSON.*proxy block"):
        sp.acquire_token()


# ==================================================================== UI


def _fake_st(clicked=True, cache=None):
    fake = MagicMock()
    fake.session_state = {"_dq_report_cache": cache} if cache is not None else {}
    fake.button.return_value = clicked
    fake.spinner.return_value.__enter__.return_value = None
    return fake


def test_button_hidden_when_not_configured(monkeypatch):
    import ui.step_06._exec_report as er

    monkeypatch.setattr(sp, "SETTINGS", _settings(sharepoint_site=""))
    fake_st = _fake_st()
    monkeypatch.setattr(er, "st", fake_st)
    er._render_sharepoint_push("d", _artifacts(), None)
    fake_st.button.assert_not_called()


def test_button_publish_success_logs_event_and_keeps_links(monkeypatch):
    import ui.step_06._exec_report as er

    monkeypatch.setattr(sp, "SETTINGS", _settings())
    calls = []

    def fake_publish(artifacts, hosted_url=None):
        calls.append(hosted_url)
        return sp.PublishResult("DQ Reports/COST_ESTIMATE", [
            sp.PublishedFile("a.pdf", "https://sp/a.pdf", 3),
            sp.PublishedFile("a.html", "https://sp/a.html", 5),
        ])

    monkeypatch.setattr(sp, "publish_report", fake_publish)
    events = []
    monkeypatch.setattr(er, "log_event", lambda *a, **k: events.append((a, k)))
    fake_st = _fake_st(cache={"key": "k", "artifacts": None, "stored": True})
    monkeypatch.setattr(er, "st", fake_st)

    er._render_sharepoint_push("cost_estimate", _artifacts(), "https://app/reports/x")

    assert calls == ["https://app/reports/x"]
    assert fake_st.button.call_args.kwargs["width"] == "stretch"
    fake_st.error.assert_not_called()
    message = fake_st.success.call_args.args[0]
    assert "[a.pdf](https://sp/a.pdf)" in message and "DQ Reports/COST_ESTIMATE" in message
    assert events[0][0][1]["format"] == "sharepoint_publish"
    assert events[0][0][1]["files"] == ["a.pdf", "a.html"]
    assert events[0][0][2] == "cost_estimate"
    # Links survive reruns: stored in the run cache, shown without a click.
    cached = fake_st.session_state["_dq_report_cache"]["sharepoint"]
    assert cached["files"] == [("a.pdf", "https://sp/a.pdf"), ("a.html", "https://sp/a.html")]
    fake_st2 = _fake_st(clicked=False, cache=fake_st.session_state["_dq_report_cache"])
    monkeypatch.setattr(er, "st", fake_st2)
    er._render_sharepoint_push("cost_estimate", _artifacts(), None)
    fake_st2.success.assert_called_once()


def test_button_publish_failure_shows_error(monkeypatch):
    import ui.step_06._exec_report as er

    monkeypatch.setattr(sp, "SETTINGS", _settings())

    def boom(*a, **k):
        raise sp.SharePointPushError("Microsoft Graph returned 403")

    monkeypatch.setattr(sp, "publish_report", boom)
    fake_st = _fake_st()
    monkeypatch.setattr(er, "st", fake_st)
    er._render_sharepoint_push("d", _artifacts(), None)
    fake_st.error.assert_called_once()
    fake_st.success.assert_not_called()
