"""Tests for src/snowflake_client.py with a fully mocked snowflake.connector."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.snowflake_client import SnowflakeClient


@pytest.fixture
def fake_snowflake(monkeypatch):
    """Install a fake `snowflake.connector` module that records calls."""
    fake_conn = MagicMock(name="connection")
    fake_cursor = MagicMock(name="cursor")
    fake_cursor.fetch_pandas_all.return_value = pd.DataFrame(
        {"col_a": [1, 2], "col_b": [3, 4]}  # lowercase, to exercise uppercase normalization
    )
    fake_conn.cursor.return_value = fake_cursor

    fake_connector = MagicMock(name="snowflake.connector")
    fake_connector.connect.return_value = fake_conn

    fake_module = types.ModuleType("snowflake")
    fake_connector_module = types.ModuleType("snowflake.connector")
    fake_connector_module.connect = fake_connector.connect
    fake_module.connector = fake_connector_module

    monkeypatch.setitem(sys.modules, "snowflake", fake_module)
    monkeypatch.setitem(sys.modules, "snowflake.connector", fake_connector_module)
    return {"connector": fake_connector, "conn": fake_conn, "cursor": fake_cursor}


def test_connect_returns_connection_and_caches(fake_snowflake):
    client = SnowflakeClient()
    conn1 = client.connect()
    conn2 = client.connect()
    assert conn1 is conn2
    # connector.connect called exactly once (cached)
    assert fake_snowflake["connector"].connect.call_count == 1


def test_connect_passes_warehouse_and_role(fake_snowflake, monkeypatch):
    # Force non-empty warehouse/role to hit those branches
    from config import settings as settings_mod

    new_settings = settings_mod.Settings(
        data_source="snowflake",
        sf_account="acct",
        sf_user="u",
        sf_authenticator="externalbrowser",
        sf_warehouse="WH",
        sf_database="DB",
        sf_schema="SC",
        sf_role="ROLE",
        threshold_green=80,
        threshold_yellow=60,
        max_rows_per_table=10,
    )
    monkeypatch.setattr("src.snowflake_client.SETTINGS", new_settings)

    client = SnowflakeClient()
    client.connect()
    call_kwargs = fake_snowflake["connector"].connect.call_args.kwargs
    assert call_kwargs["warehouse"] == "WH"
    assert call_kwargs["role"] == "ROLE"
    assert call_kwargs["database"] == "DB"
    assert call_kwargs["schema"] == "SC"


def test_connect_omits_warehouse_role_when_empty(fake_snowflake, monkeypatch):
    from config import settings as settings_mod

    new_settings = settings_mod.Settings(
        sf_warehouse="", sf_role="",
    )
    monkeypatch.setattr("src.snowflake_client.SETTINGS", new_settings)

    client = SnowflakeClient()
    client.connect()
    call_kwargs = fake_snowflake["connector"].connect.call_args.kwargs
    assert "warehouse" not in call_kwargs
    assert "role" not in call_kwargs


def test_close_closes_underlying_connection(fake_snowflake):
    client = SnowflakeClient()
    client.connect()
    client.close()
    fake_snowflake["conn"].close.assert_called_once()
    # Closing again is a no-op
    client.close()
    assert fake_snowflake["conn"].close.call_count == 1


def test_fetch_table_builds_query_with_limit(fake_snowflake, monkeypatch):
    from config import settings as settings_mod
    monkeypatch.setattr(
        "src.snowflake_client.SETTINGS",
        settings_mod.Settings(sf_database="DB", sf_schema="SC"),
    )
    client = SnowflakeClient()
    df = client.fetch_table("MY_TABLE", limit=50)
    assert list(df.columns) == ["COL_A", "COL_B"]  # uppercase normalization
    exec_args = fake_snowflake["cursor"].execute.call_args.args[0]
    assert "DB.SC.MY_TABLE" in exec_args
    assert "LIMIT 50" in exec_args
    fake_snowflake["cursor"].close.assert_called_once()


def test_fetch_table_without_limit_no_limit_clause(fake_snowflake, monkeypatch):
    from config import settings as settings_mod
    monkeypatch.setattr(
        "src.snowflake_client.SETTINGS",
        settings_mod.Settings(sf_database="DB", sf_schema="SC"),
    )
    client = SnowflakeClient()
    client.fetch_table("MY_TABLE")
    exec_args = fake_snowflake["cursor"].execute.call_args.args[0]
    assert "LIMIT" not in exec_args


def test_fetch_table_pushes_where_with_parameter_binding(fake_snowflake, monkeypatch):
    """The sidebar Project filter pushdown relies on ``fetch_table``
    accepting a ``WHERE`` fragment plus parameterized values, so user
    input never gets concatenated into the SQL text."""
    from config import settings as settings_mod
    monkeypatch.setattr(
        "src.snowflake_client.SETTINGS",
        settings_mod.Settings(sf_database="DB", sf_schema="SC"),
    )
    client = SnowflakeClient()
    client.fetch_table(
        "MY_TABLE",
        where="PLANVIEW_ID IN (%s, %s)",
        params=["1101168", "1106771"],
    )
    sql, bound = fake_snowflake["cursor"].execute.call_args.args
    assert "WHERE PLANVIEW_ID IN (%s, %s)" in sql
    assert bound == ["1101168", "1106771"]


def test_fetch_table_where_combined_with_limit(fake_snowflake, monkeypatch):
    """``WHERE`` and ``LIMIT`` compose: the LIMIT applies to the filtered
    rows so a tiny project filter is never silently truncated by Sample
    mode's row cap."""
    from config import settings as settings_mod
    monkeypatch.setattr(
        "src.snowflake_client.SETTINGS",
        settings_mod.Settings(sf_database="DB", sf_schema="SC"),
    )
    client = SnowflakeClient()
    client.fetch_table(
        "MY_TABLE",
        limit=50,
        where="PLANVIEW_ID IN (%s)",
        params=["1101168"],
    )
    sql, _ = fake_snowflake["cursor"].execute.call_args.args
    # Both clauses present in the right order: WHERE before LIMIT.
    assert sql.index("WHERE") < sql.index("LIMIT")


def test_context_manager_opens_and_closes(fake_snowflake):
    with SnowflakeClient() as c:
        assert c._conn is not None
    # After exit, conn is set to None in close()
    assert c._conn is None


def test_fetch_table_closes_cursor_even_on_error(fake_snowflake, monkeypatch):
    from config import settings as settings_mod
    monkeypatch.setattr(
        "src.snowflake_client.SETTINGS",
        settings_mod.Settings(sf_database="DB", sf_schema="SC"),
    )
    fake_snowflake["cursor"].execute.side_effect = RuntimeError("boom")
    client = SnowflakeClient()
    with pytest.raises(RuntimeError):
        client.fetch_table("MY_TABLE", limit=10)
    fake_snowflake["cursor"].close.assert_called_once()


# =============================================================================
# fetch_query - non-Arrow path, resilient to Arrow chunk-schema mismatch
# =============================================================================

def test_fetch_query_uses_fetchall_and_description(fake_snowflake):
    """fetch_query must read rows via cur.fetchall() (NOT fetch_pandas_all)
    and build the DataFrame from cur.description, so callers are immune
    to ``ArrowInvalid: Schema at index N was different`` from Snowflake's
    Arrow encoding."""
    fake_snowflake["cursor"].fetchall.return_value = [
        ("PV-00001",), ("PV-00002",), ("PV-00003",)
    ]
    fake_snowflake["cursor"].description = [("project_id",)]

    client = SnowflakeClient()
    df = client.fetch_query("SELECT DISTINCT PROJECT_ID FROM SOMEVIEW")

    assert list(df.columns) == ["PROJECT_ID"]  # uppercase normalization
    assert df["PROJECT_ID"].tolist() == ["PV-00001", "PV-00002", "PV-00003"]
    fake_snowflake["cursor"].fetch_pandas_all.assert_not_called()
    fake_snowflake["cursor"].close.assert_called_once()


def test_fetch_query_passes_sql_through_unchanged(fake_snowflake):
    fake_snowflake["cursor"].fetchall.return_value = []
    fake_snowflake["cursor"].description = [("a",)]
    client = SnowflakeClient()
    sql = "SELECT DISTINCT PROJECT_ID FROM INSIGHTS_DB.UC_GP_CSC.VWS_GP_STANDARD_SHARE"
    client.fetch_query(sql)
    exec_args = fake_snowflake["cursor"].execute.call_args.args[0]
    assert exec_args == sql


def test_fetch_query_closes_cursor_on_error(fake_snowflake):
    fake_snowflake["cursor"].execute.side_effect = RuntimeError("boom")
    client = SnowflakeClient()
    with pytest.raises(RuntimeError):
        client.fetch_query("SELECT 1")
    fake_snowflake["cursor"].close.assert_called_once()


# =============================================================================
# Shared client (one auth round-trip per Step 2)
# =============================================================================

@pytest.fixture(autouse=True)
def _reset_shared_client():
    """Drop the module-level cached client between tests so each test
    starts from a clean state."""
    import src.snowflake_client as sc
    sc._SHARED = None
    yield
    sc._SHARED = None


def test_get_shared_client_returns_same_instance(fake_snowflake):
    """First call creates a SnowflakeClient and opens the connection;
    subsequent calls reuse it - proving Step 2's data-product build and
    the reference prefetch share one connection."""
    from src.snowflake_client import get_shared_client

    a = get_shared_client()
    b = get_shared_client()
    assert a is b
    # Underlying snowflake.connector.connect called only once.
    assert fake_snowflake["connector"].connect.call_count == 1


def test_close_shared_client_drops_cached_instance(fake_snowflake):
    """Restart calls close_shared_client(); the next get_shared_client()
    must create a fresh instance and re-auth."""
    from src.snowflake_client import close_shared_client, get_shared_client

    first = get_shared_client()
    close_shared_client()
    fake_snowflake["conn"].close.assert_called_once()

    second = get_shared_client()
    assert second is not first
    assert fake_snowflake["connector"].connect.call_count == 2


def test_close_shared_client_when_unset_is_noop():
    """Safe to call from any teardown path even when nothing is cached."""
    from src.snowflake_client import close_shared_client
    close_shared_client()  # must not raise


# =============================================================================
# Reference loader integration - Snowflake branch
# =============================================================================

def test_load_vws_gp_standard_share_in_snowflake_mode_uses_distinct_project_id(
    fake_snowflake, monkeypatch
):
    """``_load_vws_gp_standard_share`` must:
    - Skip the mock branch when DATA_SOURCE=snowflake.
    - Project PROJECT_ID + COUNTRY + E05_DEPARTMENT + BUSINESS (the columns
      E7, E2, and E6's project-type segmentation need) with DISTINCT (so
      we don't pull the entire view, and we avoid Snowflake's Arrow
      chunk-schema mismatch).
    - Use the SHARED client (so it reuses the connection opened by
      data_product_builder).
    """
    from config import settings as settings_mod

    monkeypatch.setattr(
        "src.reference_data.SETTINGS",
        settings_mod.Settings(
            data_source="snowflake",
            sf_database="INSIGHTS_DB",
            sf_schema="UC_GP_CSC",
        ),
    )
    monkeypatch.setattr(
        "src.snowflake_client.SETTINGS",
        settings_mod.Settings(
            data_source="snowflake",
            sf_database="INSIGHTS_DB",
            sf_schema="UC_GP_CSC",
        ),
    )
    fake_snowflake["cursor"].fetchall.return_value = [
        ("PV-00001", "BR", "BROWNFIELD", "UPSTREAM"),
        ("PV-00002", "US", "GREENFIELD", "DOWNSTREAM"),
    ]
    fake_snowflake["cursor"].description = [
        ("project_id",),
        ("country",),
        ("e05_department",),
        ("business",),
    ]

    from src.reference_data import _load_vws_gp_standard_share
    df = _load_vws_gp_standard_share()

    exec_args = fake_snowflake["cursor"].execute.call_args.args[0]
    assert exec_args == (
        "SELECT DISTINCT PROJECT_ID, COUNTRY, E05_DEPARTMENT, BUSINESS "
        "FROM INSIGHTS_DB.UC_GP_CSC.VWS_GP_STANDARD_SHARE"
    )
    assert list(df.columns) == [
        "PROJECT_ID", "COUNTRY", "E05_DEPARTMENT", "BUSINESS"
    ]
    assert df["PROJECT_ID"].tolist() == ["PV-00001", "PV-00002"]
    assert df["COUNTRY"].tolist() == ["BR", "US"]
    assert df["E05_DEPARTMENT"].tolist() == ["BROWNFIELD", "GREENFIELD"]
    assert df["BUSINESS"].tolist() == ["UPSTREAM", "DOWNSTREAM"]


def test_data_product_builder_uses_shared_client_in_snowflake_mode(
    fake_snowflake, monkeypatch
):
    """The data-product builder must obtain its fetcher from the shared
    client so a follow-up reference-dataset prefetch reuses the same
    connection (one auth round-trip total per Step 2 entry)."""
    from config import settings as settings_mod

    new_settings = settings_mod.Settings(
        data_source="snowflake",
        sf_database="DB",
        sf_schema="SC",
    )
    monkeypatch.setattr("src.data_product_builder.SETTINGS", new_settings)
    monkeypatch.setattr("src.snowflake_client.SETTINGS", new_settings)

    from src.data_product_builder import _default_fetcher
    from src.snowflake_client import get_shared_client

    fetcher = _default_fetcher(row_limit=None)
    fetcher("MY_TABLE")
    fetcher("OTHER_TABLE")
    # Touch the shared client directly, it must be the same one the
    # fetcher used (no second snowflake.connector.connect call).
    get_shared_client()

    assert fake_snowflake["connector"].connect.call_count == 1


# =============================================================================
# Snowpark (Streamlit in Snowflake) backend path
# =============================================================================

class _FakeSnowparkResult:
    def __init__(self, df):
        self._df = df

    def to_pandas(self):
        return self._df


class _FakeSnowparkSession:
    """Minimal stand-in for a Snowpark Session: records the last sql()/params."""

    def __init__(self):
        self.calls = []
        self.closed = False
        self._df = pd.DataFrame({"col_a": [1, 2], "col_b": [3, 4]})

    def sql(self, query, params=None):
        self.calls.append((query, params))
        return _FakeSnowparkResult(self._df)

    def close(self):  # must never be called by the client
        self.closed = True


@pytest.fixture
def fake_session(monkeypatch):
    """Force the client to use a fake in-platform Snowpark session."""
    session = _FakeSnowparkSession()
    monkeypatch.setattr(
        "src.snowflake_client._active_snowpark_session", lambda: session
    )
    from config import settings as settings_mod
    monkeypatch.setattr(
        "src.snowflake_client.SETTINGS",
        settings_mod.Settings(sf_database="DB", sf_schema="SC"),
    )
    return session


def test_connect_prefers_active_snowpark_session(fake_session):
    """In SiS, connect() returns the active Snowpark session, not a connector."""
    client = SnowflakeClient()
    handle = client.connect()
    assert handle is fake_session
    assert client._session is fake_session
    assert client._conn is None


def test_snowpark_fetch_table_translates_qmark_and_binds(fake_session):
    """fetch_table on the Snowpark backend must translate %s -> ? and bind
    params via session.sql(params=...), never concatenating user input."""
    client = SnowflakeClient()
    df = client.fetch_table(
        "MY_TABLE",
        where="PLANVIEW_ID IN (%s, %s)",
        params=["1101168", "1106771"],
    )
    assert list(df.columns) == ["COL_A", "COL_B"]  # uppercased
    query, params = fake_session.calls[-1]
    assert "PLANVIEW_ID IN (?, ?)" in query   # qmark, not %s
    assert "%s" not in query
    assert params == ["1101168", "1106771"]


def test_snowpark_fetch_table_no_params_no_binding(fake_session):
    client = SnowflakeClient()
    client.fetch_table("MY_TABLE", limit=50)
    query, params = fake_session.calls[-1]
    assert "DB.SC.MY_TABLE" in query and "LIMIT 50" in query
    assert params is None


def test_snowpark_fetch_query_uses_session(fake_session):
    client = SnowflakeClient()
    df = client.fetch_query("SELECT DISTINCT PROJECT_ID FROM REF")
    assert list(df.columns) == ["COL_A", "COL_B"]
    query, params = fake_session.calls[-1]
    assert query == "SELECT DISTINCT PROJECT_ID FROM REF"
    assert params is None


def test_close_does_not_close_active_session(fake_session):
    """The SiS session is platform-owned: close() drops the reference but
    must NOT call session.close()."""
    client = SnowflakeClient()
    client.connect()
    client.close()
    assert client._session is None
    assert fake_session.closed is False


def test_active_snowpark_session_returns_none_without_snowpark(monkeypatch):
    """Outside SiS (no snowpark / no active session) the helper returns None
    so the connector fallback is used."""
    from src import snowflake_client as sc
    # snowpark is not installed in the test env -> import guard returns None.
    assert sc._active_snowpark_session() is None
