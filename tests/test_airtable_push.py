"""Tests for the Airtable write-back (phase 5).

All HTTP is faked at the ``requests.request`` seam - no network. The
frozen ``SETTINGS`` dataclass is swapped for a stub on the module under
test, mirroring how the other suites isolate configuration.
"""
from __future__ import annotations

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
        ap.push_results("d", _scorecards())


def test_push_empty_scorecards_raises(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    with pytest.raises(ap.AirtablePushError, match="No scorecard"):
        ap.push_results("d", {})


def test_push_upserts_per_system_scores_only(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    calls = []

    def fake_request(method, url, json=None, headers=None, timeout=None):
        calls.append((method, url, json, headers))
        return _Resp({"records": [{"id": "recEPT"}, {"id": "recADR"}]})

    monkeypatch.setattr(ap.requests, "request", fake_request)
    record_ids = ap.push_results("cost_estimate", _scorecards())

    assert record_ids == ["recEPT", "recADR"]
    assert len(calls) == 1  # one batched upsert, nothing else (no upload)

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
    assert [r["fields"]["Overall Score"] for r in payload["records"]] == \
        [61.0, 90.0]
    assert [r["fields"]["Status"] for r in payload["records"]] == \
        ["🟡 Yellow", "🟢 Green"]
    assert headers["Authorization"] == "Bearer pat-test"
    # The module has no attachment path at all any more.
    assert not hasattr(ap, "_upload_report")
    assert not hasattr(ap, "CONTENT_ROOT")


def test_upsert_response_mismatch_raises(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    monkeypatch.setattr(
        ap.requests, "request",
        lambda *a, **k: _Resp({"records": [{"id": "recOnlyOne"}]}))
    with pytest.raises(ap.AirtablePushError, match="Unexpected"):
        ap.push_results("d", _scorecards())


def test_http_error_becomes_push_error(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())
    monkeypatch.setattr(
        ap.requests, "request",
        lambda *a, **k: _Resp({}, status_code=422, text="INVALID_FIELD"))
    with pytest.raises(ap.AirtablePushError, match="422.*INVALID_FIELD"):
        ap.push_results("d", _scorecards())


def test_transport_error_becomes_push_error(monkeypatch):
    monkeypatch.setattr(ap, "SETTINGS", _settings())

    def boom(*a, **k):
        raise ap.requests.ConnectionError("egress blocked")

    monkeypatch.setattr(ap.requests, "request", boom)
    with pytest.raises(ap.AirtablePushError, match="Could not reach"):
        ap.push_results("d", _scorecards())


# ==================================================================== UI

def test_button_hidden_when_not_configured(monkeypatch):
    import ui.step_06._exec_report as er

    monkeypatch.setattr(ap, "SETTINGS", _settings(airtable_token=""))
    fake_st = MagicMock()
    monkeypatch.setattr(er, "st", fake_st)
    er._render_airtable_push("d", _scorecards())
    fake_st.button.assert_not_called()


def test_button_push_success_logs_event(monkeypatch):
    import ui.step_06._exec_report as er

    monkeypatch.setattr(ap, "SETTINGS", _settings())
    monkeypatch.setattr(ap, "push_results",
                        lambda *a, **k: ["recEPT", "recADR"])
    events = []
    monkeypatch.setattr(er, "log_event",
                        lambda *a, **k: events.append((a, k)))
    fake_st = MagicMock()
    fake_st.button.return_value = True
    monkeypatch.setattr(er, "st", fake_st)
    er._render_airtable_push("d", _scorecards())
    fake_st.success.assert_called_once()
    fake_st.error.assert_not_called()
    assert events and events[0][0][1]["format"] == "airtable_push"
    assert events[0][0][1]["record_ids"] == ["recEPT", "recADR"]


def test_button_push_failure_shows_error(monkeypatch):
    import ui.step_06._exec_report as er

    monkeypatch.setattr(ap, "SETTINGS", _settings())

    def boom(*a, **k):
        raise ap.AirtablePushError("Airtable returned 401")

    monkeypatch.setattr(ap, "push_results", boom)
    fake_st = MagicMock()
    fake_st.button.return_value = True
    monkeypatch.setattr(er, "st", fake_st)
    er._render_airtable_push("d", _scorecards())
    fake_st.error.assert_called_once()
    fake_st.success.assert_not_called()
