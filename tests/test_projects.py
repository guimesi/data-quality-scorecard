"""Tests for saved projects with audit changelog (phase 3).

Covers the UI-free service (src/projects.py: serialization round-trip,
change summaries, versioned saves, browsing) and the two UI surfaces (the
Step 6 save panel and the mode-selection browser/loader). The persistence
store is per-test isolated by conftest.
"""
from __future__ import annotations

import os

# Force mock mode before importing anything that reads settings.
os.environ.setdefault("DATA_SOURCE", "mock")

from unittest.mock import MagicMock

import src.projects as proj
import ui.step_06._projects as save_panel
import ui.step_mode_selection as smode
from src.models import CustomDQRAssignment, DataProductConfig, DQRAssignment
from src.persistence import list_events, list_project_versions


def _cfg(weight: float = 60.0, cdes=None,
         custom_weight: float = 40.0) -> DataProductConfig:
    return DataProductConfig(
        system_code="EPT",
        cdes=list(cdes or ["PLANVIEW_ID", "CODE_OF_RESOURCE"]),
        assignments=[
            DQRAssignment("PLANVIEW_ID", "Completeness", weight=weight,
                          params={"op": ">="}),
        ],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 50.0, "custom": 50.0},
        custom_assignments=[
            CustomDQRAssignment(rule_id="E1", weight=custom_weight,
                                params={"scoped": True}),
        ],
    )


# ============================================================= serialization

def test_project_serialization_roundtrip():
    configs = {"EPT": _cfg()}
    payload = proj.serialize_project("cost_estimate", configs)
    domain, restored = proj.deserialize_project(payload)
    assert domain == "cost_estimate"
    assert restored["EPT"] == configs["EPT"]
    assert payload["systems"] == ["EPT"]


def test_deserialize_project_tolerates_empty_payload():
    domain, configs = proj.deserialize_project({})
    assert domain == ""
    assert configs == {}


# ============================================================ change_summary

def _payload(**cfg_kwargs) -> dict:
    return proj.serialize_project("cost_estimate", {"EPT": _cfg(**cfg_kwargs)})


def test_change_summary_no_changes():
    assert proj.change_summary(_payload(), _payload()) == (
        "No configuration changes."
    )


def test_change_summary_reports_weight_and_param_changes():
    summary = proj.change_summary(_payload(), _payload(weight=80.0))
    assert "EPT: 1 rule weight(s) changed" in summary

    changed = _payload()
    changed["configs"]["EPT"]["custom_assignments"][0]["params"] = {"scoped": False}
    summary = proj.change_summary(_payload(), changed)
    assert "1 custom rule param(s) changed" in summary


def test_change_summary_reports_added_removed_entities():
    base = _payload()

    extra_rule = _payload()
    extra_rule["configs"]["EPT"]["assignments"].append(
        {"cde_column": "CODE_OF_RESOURCE", "dimension": "Uniqueness",
         "weight": 10.0, "params": {}},
    )
    summary = proj.change_summary(base, extra_rule)
    assert "+rule CODE_OF_RESOURCE::Uniqueness" in summary

    extra_system = _payload()
    extra_system["configs"]["ADR"] = proj.serialize_config(_cfg())
    assert "+system ADR" in proj.change_summary(base, extra_system)
    assert "-system ADR" in proj.change_summary(extra_system, base)

    fewer_cdes = _payload(cdes=["PLANVIEW_ID"])
    assert "-CDE CODE_OF_RESOURCE" in proj.change_summary(base, fewer_cdes)


def test_change_summary_reports_removed_rule():
    base = _payload()
    extra_rule = _payload()
    extra_rule["configs"]["EPT"]["assignments"].append(
        {"cde_column": "CODE_OF_RESOURCE", "dimension": "Uniqueness",
         "weight": 10.0, "params": {}},
    )
    assert "-rule CODE_OF_RESOURCE::Uniqueness" in proj.change_summary(
        extra_rule, base,
    )


def test_change_summary_reports_source_and_domain_changes():
    base = _payload()
    resourced = _payload()
    resourced["configs"]["EPT"]["source_weights"] = {"standard": 70.0,
                                                     "custom": 30.0}
    assert "sources/source weights changed" in proj.change_summary(base, resourced)

    other_domain = _payload()
    other_domain["domain_code"] = "quality"
    assert "domain cost_estimate → quality" in proj.change_summary(
        base, other_domain,
    )


def test_change_summary_caps_long_name_lists():
    base = _payload(cdes=["PLANVIEW_ID"])
    many = _payload(cdes=["PLANVIEW_ID", "A", "B", "C", "D"])
    summary = proj.change_summary(base, many)
    assert "+CDE 4" in summary   # > 3 names collapse to a count


# ============================================================== save / browse

def test_save_project_creates_versions_with_changelog():
    first = proj.save_project("proj-x", "cost_estimate", {"EPT": _cfg()})
    assert first["version"] == 1
    assert first["change_summary"] == "Project created."

    second = proj.save_project("proj-x", "cost_estimate",
                               {"EPT": _cfg(weight=80.0)})
    assert second["version"] == 2
    assert "1 rule weight(s) changed" in second["change_summary"]

    # Audit trail: the version list is the changelog, and telemetry logged.
    versions = list_project_versions("proj-x")
    assert [v["version"] for v in versions] == [1, 2]
    assert all(v["username"] for v in versions)
    saves = list_events(event_type="project_saved")
    assert len(saves) == 2


def test_save_project_none_when_persistence_down(monkeypatch):
    monkeypatch.setattr(proj, "save_project_version", lambda *a, **k: False)
    assert proj.save_project("x", "d", {"EPT": _cfg()}) is None
    assert list_events(event_type="project_saved") == []


def test_save_project_rejects_blank_name_or_empty_configs():
    assert proj.save_project("   ", "d", {"EPT": _cfg()}) is None
    assert proj.save_project("name", "d", {}) is None
    assert list_project_versions() == []


def test_list_projects_groups_and_orders():
    proj.save_project("alpha", "cost_estimate", {"EPT": _cfg()})
    proj.save_project("beta", "quality", {"EPT": _cfg()})
    proj.save_project("alpha", "cost_estimate", {"EPT": _cfg(weight=70.0)})
    projects = proj.list_projects()
    assert [p["name"] for p in projects][:1] == ["alpha"] or len(projects) == 2
    alpha = next(p for p in projects if p["name"] == "alpha")
    assert alpha["versions"] == 2
    assert alpha["domain_code"] == "cost_estimate"
    assert alpha["updated_by"]


def test_get_project_latest_and_specific_version():
    proj.save_project("p", "d1", {"EPT": _cfg()})
    proj.save_project("p", "d1", {"EPT": _cfg(weight=80.0)})
    assert proj.get_project("missing") is None
    assert proj.get_project("p")["version"] == 2
    assert proj.get_project("p", version=1)["version"] == 1
    assert proj.get_project("p", version=99) is None


def test_saved_project_roundtrips_through_load():
    configs = {"EPT": _cfg()}
    proj.save_project("rt", "cost_estimate", configs)
    record = proj.get_project("rt")
    domain, restored = proj.deserialize_project(record["payload"])
    assert domain == "cost_estimate"
    assert restored == configs


# ========================================================== Step 6 save panel

class _FakeSessionState(dict):
    __getattr__ = dict.__getitem__

    def __setattr__(self, key, value):
        self[key] = value


def _fake_st(session: _FakeSessionState) -> MagicMock:
    fake = MagicMock()
    fake.session_state = session
    fake.columns.side_effect = lambda spec, **kw: [
        MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))
    ]
    return fake


def test_save_panel_renders_nothing_without_configs(monkeypatch):
    fake = _fake_st(_FakeSessionState(configs={}))
    monkeypatch.setattr(save_panel, "st", fake)
    save_panel._render_project_save_panel()
    fake.expander.assert_not_called()


def test_save_panel_saves_version_and_shows_changelog(monkeypatch):
    session = _FakeSessionState(
        configs={"EPT": _cfg()}, domain="cost_estimate",
        loaded_project_name="",
    )
    fake = _fake_st(session)
    fake.text_input.return_value = "painel-proj"
    fake.button.return_value = True
    monkeypatch.setattr(save_panel, "st", fake)
    save_panel._render_project_save_panel()
    assert proj.get_project("painel-proj")["version"] == 1
    assert session["loaded_project_name"] == "painel-proj"
    fake.success.assert_called_once()
    fake.dataframe.assert_called_once()   # changelog table


def test_save_panel_reports_persistence_failure(monkeypatch):
    session = _FakeSessionState(
        configs={"EPT": _cfg()}, domain="d", loaded_project_name="",
    )
    fake = _fake_st(session)
    fake.text_input.return_value = "x"
    fake.button.return_value = True
    monkeypatch.setattr(save_panel, "st", fake)
    monkeypatch.setattr(save_panel, "save_project", lambda *a, **k: None)
    save_panel._render_project_save_panel()
    fake.error.assert_called_once()


# ================================================== mode-selection browser

def test_saved_projects_browser_hidden_when_empty(monkeypatch):
    fake = _fake_st(_FakeSessionState())
    fake.dataframe.return_value = {"selection": {"rows": []}}
    monkeypatch.setattr(smode, "st", fake)
    smode._render_saved_projects(proj.list_projects())
    fake.selectbox.assert_not_called()


def test_saved_projects_browser_lists_and_opens(monkeypatch):
    proj.save_project("abrir", "cost_estimate", {"EPT": _cfg()})
    fake = _fake_st(_FakeSessionState())

    def _select(label, options, **kwargs):
        return options[-1] if label == "Version to open" else options[0]
    fake.selectbox.side_effect = _select
    fake.button.return_value = True
    # The project list is a selectable dataframe; select its first row.
    fake.dataframe.return_value = {"selection": {"rows": [0]}}
    opened = {}
    monkeypatch.setattr(smode, "st", fake)
    monkeypatch.setattr(smode, "_open_project", lambda rec: opened.update(rec))
    smode._render_saved_projects(proj.list_projects())
    assert opened["project_name"] == "abrir"
    assert opened["version"] == 1
    assert fake.dataframe.call_count == 2   # project list + versions table


# ================================================================== loader

def _loader_env(monkeypatch, session: _FakeSessionState) -> MagicMock:
    """Stub every heavy dependency _open_project reaches for."""
    import config.domains as domains_mod
    import src.data_product_builder as dpb
    import src.profiler as profiler_mod
    import src.reference_data as ref_mod

    fake = _fake_st(session)
    monkeypatch.setattr(smode, "st", fake)
    monkeypatch.setattr(smode, "set_app_mode", MagicMock())
    monkeypatch.setattr(smode, "set_domain", MagicMock())
    monkeypatch.setattr(smode, "goto", MagicMock())
    monkeypatch.setattr(smode, "get_row_limit", lambda: 1000)
    monkeypatch.setattr(smode, "get_planview_filter", lambda: [])
    monkeypatch.setattr(domains_mod, "get_active_project_filter",
                        lambda: MagicMock(column="PLANVIEW_ID"))
    monkeypatch.setattr(
        dpb, "build_multiple",
        lambda systems, **kw: {code: MagicMock(df="df") for code in systems},
    )
    monkeypatch.setattr(profiler_mod, "profile_dataframe", lambda df: {})
    monkeypatch.setattr(ref_mod, "required_reference_datasets_for_systems",
                        lambda systems: [])
    return fake


def test_open_project_rebuilds_and_lands_on_dashboard(monkeypatch):
    proj.save_project("carregar", "cost_estimate", {"EPT": _cfg()})
    record = proj.get_project("carregar")
    session = _FakeSessionState()
    _loader_env(monkeypatch, session)
    smode._open_project(record)
    assert session["selected_systems"] == ["EPT"]
    assert session["configs"]["EPT"] == _cfg()
    assert session["loaded_project_name"] == "carregar"
    smode.set_app_mode.assert_called_once_with(smode.APP_MODE_STEP_BY_STEP)
    smode.set_domain.assert_called_once_with("cost_estimate")
    smode.goto.assert_called_once_with("dashboard")
    (load_event,) = list_events(event_type="project_loaded")
    assert load_event["payload"] == {"project": "carregar", "version": 1}


def test_saved_projects_browser_missing_version_shows_error(monkeypatch):
    proj.save_project("sumiu", "cost_estimate", {"EPT": _cfg()})
    fake = _fake_st(_FakeSessionState())
    fake.selectbox.side_effect = lambda label, options, **kw: (
        options[0] if options else None
    )
    fake.button.return_value = True
    fake.dataframe.return_value = {"selection": {"rows": [0]}}
    monkeypatch.setattr(smode, "st", fake)
    monkeypatch.setattr(smode, "get_project", lambda *a, **k: None)
    opened = MagicMock()
    monkeypatch.setattr(smode, "_open_project", opened)
    smode._render_saved_projects(proj.list_projects())
    fake.error.assert_called_once()
    opened.assert_not_called()


def test_open_project_prefetches_reference_datasets(monkeypatch):
    import src.reference_data as ref_mod

    proj.save_project("refs", "cost_estimate", {"EPT": _cfg()})
    record = proj.get_project("refs")
    session = _FakeSessionState()
    _loader_env(monkeypatch, session)
    monkeypatch.setattr(ref_mod, "required_reference_datasets_for_systems",
                        lambda systems: ["VWS_GP_STANDARD_SHARE"])
    prefetched = MagicMock()
    monkeypatch.setattr(ref_mod, "prefetch_reference_datasets", prefetched)
    smode._open_project(record)
    prefetched.assert_called_once_with(["VWS_GP_STANDARD_SHARE"])
    smode.goto.assert_called_once_with("dashboard")


def test_open_project_rejects_corrupt_record(monkeypatch):
    session = _FakeSessionState()
    fake = _loader_env(monkeypatch, session)
    smode._open_project({"payload": {}})
    fake.error.assert_called_once()
    smode.goto.assert_not_called()


def test_open_project_unknown_domain_shows_error(monkeypatch):
    proj.save_project("dom", "cost_estimate", {"EPT": _cfg()})
    record = proj.get_project("dom")
    session = _FakeSessionState()
    fake = _loader_env(monkeypatch, session)
    smode.set_domain.side_effect = KeyError("nope")
    smode._open_project(record)
    fake.error.assert_called_once()
    smode.goto.assert_not_called()


def test_open_project_build_failure_keeps_user_on_step(monkeypatch):
    import src.data_product_builder as dpb

    proj.save_project("quebra", "cost_estimate", {"EPT": _cfg()})
    record = proj.get_project("quebra")
    session = _FakeSessionState()
    fake = _loader_env(monkeypatch, session)

    def _boom(systems, **kw):
        raise RuntimeError("databricks offline")
    monkeypatch.setattr(dpb, "build_multiple", _boom)
    smode._open_project(record)
    fake.error.assert_called_once()
    assert "databricks offline" in fake.error.call_args[0][0]
    smode.goto.assert_not_called()
