"""Tests for the Airtable write-back (phase 5).

All HTTP is faked at the ``requests.request`` seam - no network. The
frozen ``SETTINGS`` dataclass is swapped for a stub on the module under
test, mirroring how the other suites isolate configuration.
"""
from __future__ import annotations

import base64
import os

# Force mock mode before importing anything that reads settings.
os.environ.setdefault("DATA_SOURCE", "mock")

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import src.airtable_push as ap


# ==================================================================== fakes

def _settings(**overrides):
    base = dict(
        airtable_token="pat-test", airtable_base_id="appBASE",
        airtable_table="DQ Results", airtable_key_field="Name",
        airtable_system_field="System",
        airtable_attachment_field="Executive Report",
        airtable_keep_old_reports=False,
        threshold_green=80.0, threshold_yellow=60.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class _Resp:
    def __init__(self, payload=None, status_code=200, text="ok"):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.ok = status_code < 400
        self.text = text

    def json(self):
        return self._payload


def _result(score, green=80.0, yellow=60.0):
    return SimpleNamespace(overall_score=score, threshold_green=green,
                           threshold_yellow=yellow)


def _scorecards():
    return {"EPT": _result(61.0), "ADR": _result(90.0)}


# ==================================================================== fields

def test_record_fields_carry_system_and_result_thresholds(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    fields = ap.build_record_fields("cost_estimate", "EPT",
                                    _result(61.0, green=90.0, yellow=70.0))
    assert fields["Name"] == "cost_estimate"
    assert fields["System"] == "EPT"
    assert fields["Overall Score"] == pytest.approx(61.0)
    # Status honours the thresholds the scorecard ran with (61 < 70 = red).
    assert fields["Status"] == ap.score_label(61.0, 90.0, 70.0)
    assert fields["Run By"]
    assert "T" in str(fields["Last Run"])  # ISO timestamp


# ==================================================================== push

def test_push_not_configured_raises(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings(airtable_token=""))
    with pytest.raises(ap.AirtablePushError, match="not configured"):
        ap.push_executive_report("d", _scorecards(), b"<html>")


def test_push_empty_scorecards_raises(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    with pytest.raises(ap.AirtablePushError, match="No scorecard"):
        ap.push_executive_report("d", {}, b"<html>")


def test_push_upserts_per_system_then_uploads_to_each(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json, headers))
        if url.startswith(ap.API_ROOT):
            return _Resp({"records": [{"id": "recEPT"}, {"id": "recADR"}]})
        return _Resp({})

    monkeypatch.setattr(ap.requests, "request", fake_request)
    record_ids = ap.push_executive_report(
        "cost_estimate", _scorecards(), b"<html>report</html>")

    assert record_ids == ["recEPT", "recADR"]
    assert len(calls) == 3  # 1 batched upsert + 1 upload per system

    method, url, payload, headers = calls[0]
    assert method == "PATCH"
    assert url == f"{ap.API_ROOT}/appBASE/DQ%20Results"
    assert payload["performUpsert"] == {
        "fieldsToMergeOn": ["Name", "System"]}
    assert payload["typecast"] is True
    assert [r["fields"]["System"] for r in payload["records"]] == \
        ["EPT", "ADR"]
    assert all(r["fields"]["Name"] == "cost_estimate"
               for r in payload["records"])
    assert headers["Authorization"] == "Bearer pat-test"

    for (method, url, payload, _), rec, code in zip(
            calls[1:], ["recEPT", "recADR"], ["EPT", "ADR"]):
        assert method == "POST"
        assert url == (f"{ap.CONTENT_ROOT}/appBASE/{rec}/"
                       "Executive%20Report/uploadAttachment")
        # text/plain on purpose: the org's Airtable policy 403s text/html.
        assert payload["contentType"] == "text/plain"
        assert payload["filename"].startswith(
            f"dq_scorecard_cost_estimate_{code}_")
        assert base64.b64decode(payload["file"]) == b"<html>report</html>"


def test_stacked_old_reports_are_pruned_to_newest(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json))
        if method == "PATCH" and url.endswith("DQ%20Results"):
            return _Resp({"records": [{"id": "recEPT"}]})
        if "uploadAttachment" in url:
            # Upload response: the field now stacks old + new.
            return _Resp({"id": "recEPT", "fields": {"Executive Report": [
                {"id": "attOLD", "filename": "dq_scorecard_d_EPT_old.html"},
                {"id": "attNEW", "filename": json["filename"]},
            ]}})
        return _Resp({})

    monkeypatch.setattr(ap.requests, "request", fake_request)
    ap.push_executive_report("d", {"EPT": _result(61.0)}, b"<html>")

    method, url, payload = calls[-1]
    assert method == "PATCH"
    assert url.endswith("/DQ%20Results/recEPT")
    assert payload == {"fields": {"Executive Report": [{"id": "attNEW"}]}}


def test_keep_old_reports_flag_skips_pruning(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS",
                        _settings(airtable_keep_old_reports=True))
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url))
        if method == "PATCH":
            return _Resp({"records": [{"id": "recEPT"}]})
        return _Resp({"id": "recEPT", "fields": {"Executive Report": [
            {"id": "attOLD", "filename": "old.html"},
            {"id": "attNEW", "filename": json["filename"]},
        ]}})

    monkeypatch.setattr(ap.requests, "request", fake_request)
    ap.push_executive_report("d", {"EPT": _result(61.0)}, b"<html>")
    assert len(calls) == 2  # upsert + upload, no cleanup PATCH


def test_prune_failure_never_fails_the_push(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())

    def fake_request(method, url, json=None, headers=None, timeout=None):
        if method == "PATCH" and url.endswith("DQ%20Results"):
            return _Resp({"records": [{"id": "recEPT"}]})
        if "uploadAttachment" in url:
            return _Resp({"id": "recEPT", "fields": {"Executive Report": [
                {"id": "attOLD", "filename": "old.html"},
                {"id": "attNEW", "filename": json["filename"]},
            ]}})
        return _Resp({}, status_code=500, text="boom")  # cleanup PATCH

    monkeypatch.setattr(ap.requests, "request", fake_request)
    assert ap.push_executive_report(
        "d", {"EPT": _result(61.0)}, b"<html>") == ["recEPT"]


def test_prune_handles_field_configured_by_id(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS",
                        _settings(airtable_attachment_field="fldABC123"))
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json))
        return _Resp({})

    monkeypatch.setattr(ap.requests, "request", fake_request)
    # Response keys by NAME even when the field is configured by id.
    ap._prune_old_reports("recEPT", {"fields": {"Executive Report": [
        {"id": "attOLD", "filename": "old.html"},
        {"id": "attNEW", "filename": "new.html"},
    ]}}, "new.html")
    assert calls and calls[-1][2] == {
        "fields": {"fldABC123": [{"id": "attNEW"}]}}


def test_upsert_response_mismatch_raises(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    monkeypatch.setattr(
        ap.requests, "request",
        lambda *a, **k: _Resp({"records": [{"id": "recOnlyOne"}]}))
    with pytest.raises(ap.AirtablePushError, match="Unexpected"):
        ap.push_executive_report("d", _scorecards(), b"<html>")


def test_oversize_report_rejected_before_any_upload(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    monkeypatch.setattr(
        ap.requests, "request",
        MagicMock(side_effect=AssertionError("no HTTP expected")))
    with pytest.raises(ap.AirtablePushError, match="5 MB"):
        ap._upload_report("recXYZ", "r.html",
                          b"x" * (ap.MAX_ATTACHMENT_BYTES + 1))


def test_upload_retries_403_then_succeeds(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    monkeypatch.setattr(ap.time, "sleep", lambda s: None)
    responses = iter([_Resp({}, status_code=403, text="MODEL_NOT_FOUND"),
                      _Resp({}, status_code=403, text="MODEL_NOT_FOUND"),
                      _Resp({})])
    calls = []
    monkeypatch.setattr(
        ap.requests, "request",
        lambda *a, **k: calls.append(a) or next(responses))
    ap._upload_report("recXYZ", "r.html", b"<html>")  # must not raise
    assert len(calls) == 3


def test_upload_403_gives_up_after_max_attempts(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    monkeypatch.setattr(ap.time, "sleep", lambda s: None)
    calls = []
    monkeypatch.setattr(
        ap.requests, "request",
        lambda *a, **k: calls.append(a) or _Resp({}, status_code=403,
                                                 text="MODEL_NOT_FOUND"))
    with pytest.raises(ap.AirtablePushError, match="403"):
        ap._upload_report("recXYZ", "r.html", b"<html>")
    assert len(calls) == ap._UPLOAD_ATTEMPTS


def test_upload_non_403_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    calls = []
    monkeypatch.setattr(
        ap.requests, "request",
        lambda *a, **k: calls.append(a) or _Resp({}, status_code=413,
                                                 text="TOO_LARGE"))
    with pytest.raises(ap.AirtablePushError, match="413"):
        ap._upload_report("recXYZ", "r.html", b"<html>")
    assert len(calls) == 1


def test_http_error_becomes_push_error(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    monkeypatch.setattr(
        ap.requests, "request",
        lambda *a, **k: _Resp({}, status_code=422, text="INVALID_FIELD"))
    with pytest.raises(ap.AirtablePushError, match="422.*INVALID_FIELD"):
        ap.push_executive_report("d", _scorecards(), b"<html>")


def test_transport_error_becomes_push_error(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())

    def boom(*a, **k):
        raise ap.requests.ConnectionError("egress blocked")

    monkeypatch.setattr(ap.requests, "request", boom)
    with pytest.raises(ap.AirtablePushError, match="Could not reach"):
        ap.push_executive_report("d", _scorecards(), b"<html>")


# ==================================================================== UI

def test_button_hidden_when_not_configured(monkeypatch):
    import ui.step_06._exec_report as er

    monkeypatch.setattr(ap, "SETTINGS", _settings(airtable_token=""))
    fake_st = MagicMock()
    monkeypatch.setattr(er, "st", fake_st)
    er._render_airtable_push("d", _scorecards(), b"<html>")
    fake_st.button.assert_not_called()


def test_button_push_success_logs_event(monkeypatch):
    import ui.step_06._exec_report as er

    monkeypatch.setattr(ap, "SETTINGS", _settings())
    monkeypatch.setattr(ap, "push_executive_report",
                        lambda *a, **k: ["recEPT", "recADR"])
    events = []
    monkeypatch.setattr(er, "log_event",
                        lambda *a, **k: events.append((a, k)))
    fake_st = MagicMock()
    fake_st.button.return_value = True
    monkeypatch.setattr(er, "st", fake_st)
    er._render_airtable_push("d", _scorecards(), b"<html>")
    fake_st.success.assert_called_once()
    fake_st.error.assert_not_called()
    assert events and events[0][0][1]["format"] == "airtable_push"
    assert events[0][0][1]["record_ids"] == ["recEPT", "recADR"]


def test_button_push_failure_shows_error(monkeypatch):
    import ui.step_06._exec_report as er

    monkeypatch.setattr(ap, "SETTINGS", _settings())

    def boom(*a, **k):
        raise ap.AirtablePushError("Airtable returned 401")

    monkeypatch.setattr(ap, "push_executive_report", boom)
    fake_st = MagicMock()
    fake_st.button.return_value = True
    monkeypatch.setattr(er, "st", fake_st)
    er._render_airtable_push("d", _scorecards(), b"<html>")
    fake_st.error.assert_called_once()
    fake_st.success.assert_not_called()
