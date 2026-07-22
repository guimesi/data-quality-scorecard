"""Tests for the persistence layer (src/persistence.py, F0).

Covers identity resolution, the three backends (Local / Snowflake / Null),
backend selection, the fire-and-forget domain API, and the new
``SnowflakeClient.execute`` write path.
"""
from __future__ import annotations

import os

# Force mock mode before importing anything that reads settings.
os.environ.setdefault("DATA_SOURCE", "mock")

import json
from unittest.mock import MagicMock

import pandas as pd
import pytest

import src.persistence as pers
from config.settings import Settings


@pytest.fixture
def local_pers(tmp_path, monkeypatch):
    """persistence module pinned to a LocalStore under ``tmp_path``."""
    monkeypatch.setattr(pers, "SETTINGS", Settings(
        data_source="mock", persistence_backend="local",
        store_dir=str(tmp_path),
    ))
    pers.reset_store()
    pers.reset_identity_cache()
    yield pers
    pers.reset_store()
    pers.reset_identity_cache()


# ================================================================== identity

def test_current_username_falls_back_to_os_user(local_pers, monkeypatch):
    import src.snowflake_client as sfc
    monkeypatch.setattr(sfc, "_active_snowpark_session", lambda: None)
    monkeypatch.setattr(pers.getpass, "getuser", lambda: "local-dev")
    assert local_pers.current_username() == "local-dev"


def test_current_username_uses_snowpark_current_user(local_pers, monkeypatch):
    import src.snowflake_client as sfc
    session = MagicMock()
    session.sql.return_value.collect.return_value = [("SNOW_USER",)]
    monkeypatch.setattr(sfc, "_active_snowpark_session", lambda: session)
    assert local_pers.current_username() == "SNOW_USER"
    session.sql.assert_called_once_with("SELECT CURRENT_USER()")


def test_current_username_session_failure_falls_back(local_pers, monkeypatch):
    import src.snowflake_client as sfc
    session = MagicMock()
    session.sql.side_effect = RuntimeError("no warehouse")
    monkeypatch.setattr(sfc, "_active_snowpark_session", lambda: session)
    monkeypatch.setattr(pers.getpass, "getuser", lambda: "fallback-user")
    assert local_pers.current_username() == "fallback-user"


def test_current_username_unknown_when_everything_fails(local_pers, monkeypatch):
    import src.snowflake_client as sfc
    monkeypatch.setattr(sfc, "_active_snowpark_session", lambda: None)

    def _boom():
        raise OSError("no login")
    monkeypatch.setattr(pers.getpass, "getuser", _boom)
    assert local_pers.current_username() == "unknown"


def test_current_username_is_cached_until_reset(local_pers, monkeypatch):
    import src.snowflake_client as sfc
    monkeypatch.setattr(sfc, "_active_snowpark_session", lambda: None)
    calls = []

    def _user():
        calls.append(1)
        return "cached-user"
    monkeypatch.setattr(pers.getpass, "getuser", _user)
    assert local_pers.current_username() == "cached-user"
    assert local_pers.current_username() == "cached-user"
    assert len(calls) == 1
    local_pers.reset_identity_cache()
    assert local_pers.current_username() == "cached-user"
    assert len(calls) == 2


# ================================================================ LocalStore

def test_local_store_roundtrip(tmp_path):
    store = pers.LocalStore(tmp_path / "store")
    store.append("runs", {"a": 1})
    store.append("runs", {"a": 2})
    assert store.load("runs") == [{"a": 1}, {"a": 2}]


def test_local_store_missing_file_is_empty(tmp_path):
    assert pers.LocalStore(tmp_path).load("events") == []


def test_local_store_skips_corrupt_and_blank_lines(tmp_path):
    store = pers.LocalStore(tmp_path)
    store.append("runs", {"ok": True})
    with open(store._path("runs"), "a", encoding="utf-8") as f:
        f.write("{not json\n\n")
    store.append("runs", {"ok": 2})
    assert store.load("runs") == [{"ok": True}, {"ok": 2}]


# ========================================================= backend selection

def test_get_store_local_by_default(local_pers):
    assert isinstance(local_pers.get_store(), pers.LocalStore)


def test_get_store_is_cached_until_reset(local_pers):
    assert local_pers.get_store() is local_pers.get_store()


def test_get_store_off_yields_null_store(local_pers, monkeypatch):
    monkeypatch.setattr(pers, "SETTINGS", Settings(
        data_source="mock", persistence_backend="off",
    ))
    pers.reset_store()
    store = pers.get_store()
    assert isinstance(store, pers.NullStore)
    store.append("runs", {"x": 1})
    assert store.load("runs") == []


def test_get_store_snowflake_backend(local_pers, monkeypatch):
    monkeypatch.setattr(pers, "SETTINGS", Settings(
        data_source="snowflake", persistence_backend="snowflake",
    ))
    pers.reset_store()
    assert isinstance(pers.get_store(), pers.SnowflakeStore)


def test_get_store_unknown_backend_falls_back_to_local(local_pers, monkeypatch,
                                                       tmp_path, caplog):
    monkeypatch.setattr(pers, "SETTINGS", Settings(
        data_source="mock", persistence_backend="typo",
        store_dir=str(tmp_path),
    ))
    pers.reset_store()
    with caplog.at_level("WARNING", logger="src.persistence"):
        store = pers.get_store()
    assert isinstance(store, pers.LocalStore)
    assert "typo" in caplog.text


def test_get_store_default_dir_used_when_store_dir_empty(local_pers, monkeypatch,
                                                         tmp_path):
    monkeypatch.setattr(pers, "SETTINGS", Settings(
        data_source="mock", persistence_backend="local", store_dir="",
    ))
    # Point the default at a temp dir so the test never touches the repo.
    monkeypatch.setattr(pers, "_DEFAULT_STORE_DIR", tmp_path / "default_store")
    pers.reset_store()
    store = pers.get_store()
    assert isinstance(store, pers.LocalStore)
    assert store.root == tmp_path / "default_store"


# ================================================================ domain API

def test_save_run_stamps_ts_and_username(local_pers, monkeypatch):
    import src.snowflake_client as sfc
    monkeypatch.setattr(sfc, "_active_snowpark_session", lambda: None)
    monkeypatch.setattr(pers.getpass, "getuser", lambda: "alex")
    assert local_pers.save_run("EPT", "cost_estimate", {"overall": 91.5},
                               config_hash="abc123")
    (run,) = local_pers.list_runs()
    assert run["username"] == "alex"
    assert run["dp_code"] == "EPT"
    assert run["domain_code"] == "cost_estimate"
    assert run["config_hash"] == "abc123"
    assert run["payload"] == {"overall": 91.5}
    assert run["ts"]  # ISO stamp present


def test_list_runs_filters_by_dp_and_limits_to_most_recent(local_pers):
    for i in range(3):
        local_pers.save_run("EPT", "d", {"i": i})
    local_pers.save_run("ADR", "d", {"i": 99})
    assert len(local_pers.list_runs()) == 4
    ept = local_pers.list_runs(dp_code="EPT")
    assert [r["payload"]["i"] for r in ept] == [0, 1, 2]
    assert [r["payload"]["i"] for r in local_pers.list_runs(dp_code="EPT", limit=2)] == [1, 2]


def test_log_event_and_list_events(local_pers):
    assert local_pers.log_event("app_open", domain_code="quality")
    assert local_pers.log_event("export", {"format": "csv"}, domain_code="quality")
    assert len(local_pers.list_events()) == 2
    (export,) = local_pers.list_events(event_type="export")
    assert export["payload"] == {"format": "csv"}
    assert local_pers.list_events(limit=1)[0]["event_type"] == "export"


def test_save_project_version_increments_per_project(local_pers):
    assert local_pers.save_project_version("proj-a", {"cfg": 1}, "created")
    assert local_pers.save_project_version("proj-a", {"cfg": 2}, "tweaked weights")
    assert local_pers.save_project_version("proj-b", {"cfg": 1}, "created")
    versions_a = local_pers.list_project_versions("proj-a")
    assert [v["version"] for v in versions_a] == [1, 2]
    assert versions_a[1]["change_summary"] == "tweaked weights"
    assert local_pers.list_project_versions("proj-b")[0]["version"] == 1
    assert len(local_pers.list_project_versions()) == 3
    assert local_pers.list_project_versions("proj-a", limit=1)[0]["version"] == 2


def test_save_project_version_survives_bad_existing_version(local_pers):
    """A corrupt version value in the store must not block a new save."""
    local_pers.get_store().append("projects", {
        "project_name": "proj-x", "version": "not-a-number", "payload": {},
    })
    assert local_pers.save_project_version("proj-x", {"cfg": 1}, "recovered")
    assert local_pers.list_project_versions("proj-x")[-1]["version"] == 1


class _ExplodingStore:
    def append(self, kind, record):
        raise RuntimeError("disk full")

    def load(self, kind):
        raise RuntimeError("disk gone")


def test_domain_api_is_fire_and_forget(local_pers, monkeypatch):
    """Storage failures degrade to False / [] - they never raise."""
    monkeypatch.setattr(pers, "_STORE", _ExplodingStore())
    assert local_pers.save_run("EPT", "d", {}) is False
    assert local_pers.log_event("app_open") is False
    assert local_pers.save_project_version("p", {}) is False
    assert local_pers.list_runs() == []
    assert local_pers.list_events() == []
    assert local_pers.list_project_versions() == []


# ============================================================ SnowflakeStore

@pytest.fixture
def fake_sf_client(monkeypatch):
    import src.snowflake_client as sfc
    client = MagicMock()
    monkeypatch.setattr(sfc, "get_shared_client", lambda: client)
    monkeypatch.setattr(pers, "SETTINGS", Settings(
        data_source="snowflake", persistence_backend="snowflake",
        sf_database="APPDB", sf_state_schema="DQS_APP_STATE",
    ))
    pers.reset_store()
    yield client
    pers.reset_store()


def test_snowflake_store_append_binds_columns_and_payload(fake_sf_client):
    store = pers.SnowflakeStore()
    record = {
        "ts": "2026-07-21T12:00:00+00:00", "username": "u",
        "event_type": "export", "domain_code": "quality",
        "payload": {"format": "csv"},
    }
    store.append("events", record)
    sql, values = fake_sf_client.execute.call_args[0]
    assert "APPDB.DQS_APP_STATE.DQS_EVENTS" in sql
    assert "PARSE_JSON(%s)" in sql
    assert values[:4] == ["2026-07-21T12:00:00+00:00", "u", "export", "quality"]
    assert json.loads(values[4]) == record


def test_snowflake_store_load_parses_payloads(fake_sf_client):
    fake_sf_client.fetch_query.return_value = pd.DataFrame({
        "PAYLOAD": [
            json.dumps({"a": 1}),      # string payload (connector path)
            {"a": 2},                  # already-parsed dict (snowpark path)
            "{broken",                 # unparsable -> skipped with warning
        ],
    })
    out = pers.SnowflakeStore().load("runs")
    assert out == [{"a": 1}, {"a": 2}]
    sql = fake_sf_client.fetch_query.call_args[0][0]
    assert "APPDB.DQS_APP_STATE.DQS_RUNS" in sql
    assert "ORDER BY TS" in sql


def test_snowflake_backend_end_to_end_through_domain_api(fake_sf_client, monkeypatch):
    import src.snowflake_client as sfc
    monkeypatch.setattr(sfc, "_active_snowpark_session", lambda: None)
    monkeypatch.setattr(pers.getpass, "getuser", lambda: "u")
    pers.reset_identity_cache()
    assert pers.save_run("EPT", "d", {"score": 88.0}, config_hash="h1")
    assert fake_sf_client.execute.called
    sql, values = fake_sf_client.execute.call_args[0]
    assert "DQS_RUNS" in sql
    assert "EPT" in values


# ==================================================== SnowflakeClient.execute

def _client_with_fake_conn():
    from src.snowflake_client import SnowflakeClient
    client = SnowflakeClient()
    conn = MagicMock()
    client._conn = conn
    return client, conn


def test_client_execute_connector_with_params():
    client, conn = _client_with_fake_conn()
    client.execute("INSERT INTO T VALUES (%s, %s)", ["a", 1])
    cur = conn.cursor.return_value
    cur.execute.assert_called_once_with("INSERT INTO T VALUES (%s, %s)", ["a", 1])
    cur.close.assert_called_once()


def test_client_execute_connector_without_params():
    client, conn = _client_with_fake_conn()
    client.execute("DELETE FROM NOTHING")
    conn.cursor.return_value.execute.assert_called_once_with("DELETE FROM NOTHING")


def test_client_execute_snowpark_translates_placeholders():
    from src.snowflake_client import SnowflakeClient
    client = SnowflakeClient()
    session = MagicMock()
    client._session = session
    client.execute("INSERT INTO T VALUES (%s)", ["x"])
    session.sql.assert_called_once_with("INSERT INTO T VALUES (?)", params=["x"])
    session.sql.return_value.collect.assert_called_once()


def test_client_execute_snowpark_without_params():
    from src.snowflake_client import SnowflakeClient
    client = SnowflakeClient()
    session = MagicMock()
    client._session = session
    client.execute("CREATE TABLE X (A INT)")
    session.sql.assert_called_once_with("CREATE TABLE X (A INT)")
