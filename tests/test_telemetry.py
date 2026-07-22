"""Tests for adoption/audit telemetry (phase 2).

Covers the UI-free metrics (src/telemetry.py), the session-side logging
helpers (utils/telemetry.py) and the 📊 Adoption admin page
(ui/step_adoption.py). The persistence store is per-test isolated by
conftest.
"""
from __future__ import annotations

import os

# Force mock mode before importing anything that reads settings.
os.environ.setdefault("DATA_SOURCE", "mock")

from unittest.mock import MagicMock

import src.telemetry as tel
import ui.step_adoption as adoption_page
import utils.telemetry as utel
from src.persistence import (
    get_store,
    list_events,
    log_event,
    save_project_version,
    save_run,
)


def _seed_run(dp_code: str, ts: str, score: float = 90.0,
              domain: str = "cost_estimate") -> None:
    """Append a run record with a controlled timestamp (bypasses the
    domain API's automatic UTC stamp so week grouping is deterministic)."""
    get_store().append("runs", {
        "ts": ts, "username": "seed-user", "domain_code": domain,
        "dp_code": dp_code, "config_hash": "h",
        "payload": {"overall_score": score},
    })


# ============================================================== src.telemetry

def test_adoption_overview_counts_everything():
    log_event("app_open")
    log_event("export", {"format": "csv", "dp": "EPT"}, "cost_estimate")
    log_event("project_loaded", {"project": "p"}, "cost_estimate")
    save_run("EPT", "cost_estimate", {"overall_score": 90.0})
    save_project_version("p", {"domain_code": "cost_estimate"}, "created")
    overview = tel.adoption_overview()
    assert overview["app_opens"] == 1
    assert overview["exports"] == 1
    assert overview["projects_loaded"] == 1
    assert overview["projects_saved"] == 0   # counts the event, not versions
    assert overview["scorecard_runs"] == 1
    assert overview["unique_users"] == 1
    assert overview["last_activity"]


def test_adoption_overview_empty_store():
    overview = tel.adoption_overview()
    assert overview["unique_users"] == 0
    assert overview["scorecard_runs"] == 0
    assert overview["last_activity"] == ""


def test_runs_per_week_groups_iso_weeks():
    _seed_run("EPT", "2026-07-13T10:00:00+00:00")   # ISO week 2026-W29
    _seed_run("EPT", "2026-07-14T10:00:00+00:00")   # same week
    _seed_run("ADR", "2026-07-20T10:00:00+00:00")   # next week (W30)
    trend = tel.runs_per_week()
    assert trend["week"].tolist() == ["2026-W29", "2026-W30"]
    assert trend["runs"].tolist() == [2, 1]


def test_runs_per_week_empty_and_unparsable():
    assert tel.runs_per_week().empty
    _seed_run("EPT", "not-a-date")
    assert tel.runs_per_week().empty


def test_runs_by_system_groups_and_orders():
    _seed_run("EPT", "2026-07-13T10:00:00+00:00")
    _seed_run("EPT", "2026-07-14T10:00:00+00:00")
    _seed_run("ADR", "2026-07-15T10:00:00+00:00")
    by_system = tel.runs_by_system()
    assert by_system.iloc[0]["system"] == "EPT"
    assert int(by_system.iloc[0]["runs"]) == 2
    assert by_system.iloc[0]["last_run"] == "2026-07-14T10:00:00+00:00"
    assert tel.runs_by_system().columns.tolist() == [
        "domain", "system", "runs", "last_run",
    ]


def test_user_activity_pivots_per_user():
    log_event("app_open")                       # current OS user
    _seed_run("EPT", "2026-07-13T10:00:00+00:00")   # seed-user
    save_project_version("p", {}, "created")    # current OS user
    activity = tel.user_activity()
    seed_row = activity[activity["user"] == "seed-user"].iloc[0]
    assert int(seed_row["runs"]) == 1
    assert int(seed_row["events"]) == 0
    real_user = activity[activity["user"] != "seed-user"].iloc[0]
    assert int(real_user["events"]) == 1
    assert int(real_user["project_saves"]) == 1
    assert tel.user_activity().notna().all().all()


def test_user_activity_empty():
    assert tel.user_activity().empty


def test_recent_activity_merges_and_limits():
    log_event("app_open")
    log_event("export", {"format": "csv"}, "cost_estimate")
    _seed_run("EPT", "2099-01-01T00:00:00+00:00", score=88.4)
    save_project_version("proj", {"domain_code": "cost_estimate"}, "created")
    trail = tel.recent_activity()
    assert trail.iloc[0]["action"] == "scorecard_run"    # 2099 sorts first
    assert "score=88.4" in trail.iloc[0]["detail"]
    actions = set(trail["action"])
    assert {"app_open", "export", "scorecard_run", "project_version"} <= actions
    project_row = trail[trail["action"] == "project_version"].iloc[0]
    assert "proj v1 - created" in project_row["detail"]
    export_row = trail[trail["action"] == "export"].iloc[0]
    assert '"format": "csv"' in export_row["detail"]
    app_open_row = trail[trail["action"] == "app_open"].iloc[0]
    assert app_open_row["detail"] == ""
    assert len(tel.recent_activity(limit=2)) == 2


def test_recent_activity_empty():
    trail = tel.recent_activity()
    assert trail.empty
    assert trail.columns.tolist() == ["ts", "user", "action", "domain", "detail"]


# ============================================================ utils.telemetry

class _FakeSessionState(dict):
    __getattr__ = dict.__getitem__

    def __setattr__(self, key, value):
        self[key] = value


def test_log_app_open_once_per_session(monkeypatch):
    fake = MagicMock()
    fake.session_state = _FakeSessionState()
    monkeypatch.setattr(utel, "st", fake)
    utel.log_app_open_once()
    utel.log_app_open_once()
    assert len(list_events(event_type="app_open")) == 1


def test_log_step_view_only_on_transition(monkeypatch):
    fake = MagicMock()
    fake.session_state = _FakeSessionState(
        app_mode="step_by_step", domain="cost_estimate",
    )
    monkeypatch.setattr(utel, "st", fake)
    utel.log_step_view("dashboard")
    utel.log_step_view("dashboard")    # rerun of the same step: no-op
    utel.log_step_view("ml_lab")
    views = list_events(event_type="step_view")
    assert [v["payload"]["step"] for v in views] == ["dashboard", "ml_lab"]
    assert views[0]["payload"]["mode"] == "step_by_step"
    assert views[0]["domain_code"] == "cost_estimate"


# =========================================================== ui.step_adoption

def _fake_page_st() -> MagicMock:
    fake = MagicMock()
    fake.session_state = _FakeSessionState()
    fake.columns.side_effect = lambda spec, **kw: [
        MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))
    ]
    fake.button.return_value = False
    return fake


def test_adoption_page_renders_empty_state(monkeypatch):
    fake = _fake_page_st()
    monkeypatch.setattr(adoption_page, "st", fake)
    monkeypatch.setattr(adoption_page, "section_header", MagicMock())
    adoption_page.render()
    fake.plotly_chart.assert_not_called()
    fake.dataframe.assert_not_called()
    assert fake.caption.call_count >= 4   # trend + three empty tables


def test_adoption_page_renders_metrics_charts_and_tables(monkeypatch):
    log_event("app_open")
    _seed_run("EPT", "2026-07-13T10:00:00+00:00")
    save_project_version("p", {"domain_code": "cost_estimate"}, "created")
    fake = _fake_page_st()
    monkeypatch.setattr(adoption_page, "st", fake)
    monkeypatch.setattr(adoption_page, "section_header", MagicMock())
    adoption_page.render()
    fake.plotly_chart.assert_called_once()
    assert fake.dataframe.call_count == 3   # by-system, per-user, audit trail


def test_adoption_page_back_button_goes_to_start(monkeypatch):
    fake = _fake_page_st()
    fake.button.return_value = True
    goto = MagicMock()
    monkeypatch.setattr(adoption_page, "st", fake)
    monkeypatch.setattr(adoption_page, "section_header", MagicMock())
    monkeypatch.setattr(adoption_page, "goto", goto)
    adoption_page.render()
    goto.assert_called_once_with("mode_selection")
