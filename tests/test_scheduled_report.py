"""Tests for the headless scheduled run (``src/scheduled_report.py`` and
``scripts/run_scheduled_report.py``).

End-to-end in mock mode with a throw-away persistence store and a local
report store: the run scores real mock systems, records history, builds
the report, stores it and (with a fake) pushes scores to Airtable."""
from __future__ import annotations

import json
import os

os.environ.setdefault("DATA_SOURCE", "mock")

import pytest

from config.settings import Settings
from src import airtable_push, persistence, report_store
from src.scheduled_report import JobOutcome, run_scheduled_report


@pytest.fixture
def stores(monkeypatch, tmp_path):
    """Local persistence + local report store in ``tmp_path``."""
    settings = Settings(data_source="mock", persistence_backend="local",
                        store_dir=str(tmp_path), report_store="local")
    monkeypatch.setattr(persistence, "SETTINGS", settings)
    monkeypatch.setattr(report_store, "SETTINGS", settings)
    monkeypatch.setattr(airtable_push, "SETTINGS", settings)
    persistence.reset_identity_cache()
    report_store.reset_report_store()
    yield tmp_path
    report_store.reset_report_store()


def test_end_to_end_mock_run_scores_stores_and_records_history(stores):
    outcome = run_scheduled_report("cost_estimate", ["ACCE", "ADR"],
                                   want_pdf=False, generated_by="job-bot")
    assert outcome.ok, outcome.to_json()
    assert outcome.scored_systems == ["ACCE", "ADR"]
    assert outcome.skipped == {}
    assert outcome.generated_by == "job-bot"
    assert outcome.run_id.startswith("COST_ESTIMATE__ACCE-ADR__")
    assert set(outcome.overall_scores) == {"ACCE", "ADR"}
    assert all(0 <= s <= 100 for s in outcome.overall_scores.values())
    assert set(outcome.statuses.values()) <= {"green", "yellow", "red"}
    assert outcome.history_recorded == {"ACCE": True, "ADR": True}
    assert outcome.has_pdf is False and "not requested" in outcome.pdf_error
    assert outcome.stored is True and outcome.store_error is None
    assert outcome.store_target.startswith("local folder")
    assert outcome.report_path == f"/reports/{outcome.run_id}"
    assert outcome.latest_path == "/reports/latest/COST_ESTIMATE"
    assert outcome.airtable_record_ids is None      # not configured
    assert outcome.airtable_error is None

    # Stored under the domain folder, served by the store API.
    root = stores / "reports" / "COST_ESTIMATE"
    assert (root / f"{outcome.run_id}.html").is_file()
    assert (root / f"{outcome.run_id}.print.html").is_file()
    assert not (root / f"{outcome.run_id}.pdf").exists()
    assert report_store.latest_run_id("cost_estimate") == outcome.run_id
    meta = report_store.load_metadata(outcome.run_id)
    assert meta["generated_by"] == "job-bot" and meta["mode"] == "one_click"

    # History recorded once (a second identical run is deduplicated).
    from src.run_history import load_history
    assert len(load_history("ACCE")) == 1
    again = run_scheduled_report("cost_estimate", ["ACCE"], want_pdf=False,
                                 generated_by="job-bot")
    assert again.history_recorded == {"ACCE": False}
    assert len(load_history("ACCE")) == 1

    # Telemetry event for the adoption page.
    events = persistence.list_events(event_type="scheduled_run")
    assert events and events[-1]["payload"]["systems"] == ["ACCE"]

    # JSON summary is complete and carries the verdict.
    data = json.loads(outcome.to_json())
    assert data["ok"] is True and data["run_id"] == outcome.run_id


def test_every_system_of_the_domain_by_default(stores):
    from config.domains import get_domain

    outcome = run_scheduled_report("cost_estimate", None, want_pdf=False,
                                   generated_by="x", record_history=False)
    assert outcome.requested_systems == get_domain("cost_estimate").system_codes
    assert outcome.history_recorded == {}
    assert outcome.ok


def test_airtable_push_when_configured_and_failures_are_reported(stores, monkeypatch):
    calls = []
    monkeypatch.setattr(airtable_push, "is_configured", lambda: True)
    monkeypatch.setattr(airtable_push, "push_results",
                        lambda domain, scorecards: calls.append(
                            (domain, sorted(scorecards))) or ["recA", "recB"])
    outcome = run_scheduled_report("cost_estimate", ["ACCE", "ADR"], want_pdf=False,
                                   generated_by="x", record_history=False)
    assert calls == [("cost_estimate", ["ACCE", "ADR"])]
    assert outcome.airtable_record_ids == ["recA", "recB"]

    def boom(domain, scorecards):
        raise airtable_push.AirtablePushError("Airtable returned 401")

    monkeypatch.setattr(airtable_push, "push_results", boom)
    outcome = run_scheduled_report("cost_estimate", ["ACCE"], want_pdf=False,
                                   generated_by="x", record_history=False)
    assert outcome.airtable_error == "Airtable returned 401"
    assert outcome.ok                                   # report still usable

    # Explicit opt-out wins over configuration.
    calls.clear()
    monkeypatch.setattr(airtable_push, "push_results",
                        lambda *a, **k: calls.append(a) or [])
    run_scheduled_report("cost_estimate", ["ACCE"], want_pdf=False,
                         push_airtable=False, generated_by="x", record_history=False)
    assert calls == []


def test_unscorable_run_is_not_ok(stores, monkeypatch):
    from src import one_click

    def no_rules(domain, systems, **kw):
        return one_click.OneClickResult(domain_code=domain, requested_systems=list(systems),
                                        skipped={s: "no custom rules" for s in systems})

    monkeypatch.setattr(one_click, "run_one_click", no_rules)
    outcome = run_scheduled_report("cost_estimate", ["ACCE"], want_pdf=False,
                                   generated_by="x")
    assert not outcome.ok
    assert outcome.error == "No system could be scored"
    assert outcome.skipped == {"ACCE": "no custom rules"}
    assert outcome.run_id == ""


def test_blocking_one_click_error_is_captured(stores, monkeypatch):
    from src import one_click

    def boom(*a, **k):
        raise one_click.OneClickError("unknown system ZZZ")

    monkeypatch.setattr(one_click, "run_one_click", boom)
    outcome = run_scheduled_report("cost_estimate", ["ZZZ"], generated_by="x")
    assert not outcome.ok and "unknown system ZZZ" in outcome.error


def test_store_failure_is_reported_and_marks_run_unusable(stores, monkeypatch):
    def explode(run_id, kind, data):
        raise PermissionError("PERMISSION_DENIED")

    monkeypatch.setattr(report_store.get_report_store(), "put", explode)
    outcome = run_scheduled_report("cost_estimate", ["ACCE"], want_pdf=False,
                                   generated_by="x", record_history=False)
    assert outcome.stored is False
    assert outcome.store_error.startswith("PermissionError")
    assert outcome.report_path == "" and not outcome.ok


def test_store_off_is_still_a_usable_run(stores, monkeypatch):
    monkeypatch.setattr(report_store, "SETTINGS", Settings(
        data_source="mock", report_store="off"))
    report_store.reset_report_store()
    outcome = run_scheduled_report("cost_estimate", ["ACCE"], want_pdf=False,
                                   generated_by="x", record_history=False)
    assert outcome.stored is False and outcome.store_error.startswith("report store is off")
    assert outcome.ok


def test_outcome_json_is_serialisable():
    outcome = JobOutcome(domain_code="d", requested_systems=["A"])
    data = json.loads(outcome.to_json())
    assert data["ok"] is False and data["domain_code"] == "d"


def test_cli_prints_summary_and_exit_code(stores, capsys):
    from scripts.run_scheduled_report import main

    code = main(["--domain", "cost_estimate", "--systems", "ACCE", "--no-pdf",
                 "--no-airtable", "--generated-by", "cli", "--quiet"])
    out = capsys.readouterr().out
    summary = json.loads(out[out.index("{"):])
    assert code == 0 and summary["ok"] is True
    assert summary["scored_systems"] == ["ACCE"]
    assert summary["generated_by"] == "cli"
    assert summary["latest_path"] == "/reports/latest/COST_ESTIMATE"

    code = main(["--domain", "cost_estimate", "--systems", "NOPE", "--no-pdf",
                 "--quiet", "--generated-by", "cli"])
    assert code == 1
