"""Tests for src/databricks_client.py with fully mocked databricks packages."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.databricks_client import (
    DatabricksClient,
    _translate_placeholders,
)


@pytest.fixture
def fake_databricks(monkeypatch):
    """Install fake `databricks.sql` / `databricks.sdk.core` modules that
    record calls, so no real network/auth is involved."""
    fake_conn = MagicMock(name="connection")
    fake_cursor = MagicMock(name="cursor")
    arrow_table = MagicMock(name="arrow_table")
    arrow_table.to_pandas.return_value = pd.DataFrame(
        {"col_a": [1, 2], "col_b": [3, 4]}  # lowercase, to exercise uppercase normalization
    )
    fake_cursor.fetchall_arrow.return_value = arrow_table
    fake_conn.cursor.return_value = fake_cursor

    fake_sql_module = types.ModuleType("databricks.sql")
    fake_sql_module.connect = MagicMock(name="connect", return_value=fake_conn)

    class _FakeConfig:
        """Stand-in for databricks.sdk.core.Config (headless identity)."""

        def __init__(self):
            self.host = "https://example.cloud.databricks.com"
            self.authenticate = MagicMock(name="authenticate")

    fake_core_module = types.ModuleType("databricks.sdk.core")
    fake_core_module.Config = _FakeConfig

    fake_pkg = types.ModuleType("databricks")
    fake_pkg.sql = fake_sql_module
    fake_sdk_pkg = types.ModuleType("databricks.sdk")
    fake_sdk_pkg.core = fake_core_module

    monkeypatch.setitem(sys.modules, "databricks", fake_pkg)
    monkeypatch.setitem(sys.modules, "databricks.sql", fake_sql_module)
    monkeypatch.setitem(sys.modules, "databricks.sdk", fake_sdk_pkg)
    monkeypatch.setitem(sys.modules, "databricks.sdk.core", fake_core_module)

    from config import settings as settings_mod
    monkeypatch.setattr(
        "src.databricks_client.SETTINGS",
        settings_mod.Settings(
            dbx_catalog="CAT", dbx_schema="SC", dbx_warehouse_id="wh123",
        ),
    )
    return {
        "connect": fake_sql_module.connect,
        "conn": fake_conn,
        "cursor": fake_cursor,
    }


# =============================================================================
# Placeholder translation (%s -> :pN + dict) - the binding contract
# =============================================================================

def test_translate_placeholders_positional_to_named():
    sql, named = _translate_placeholders(
        "SELECT * FROM T WHERE A IN (%s, %s) AND B = %s", ["x", "y", "z"]
    )
    assert sql == "SELECT * FROM T WHERE A IN (:p0, :p1) AND B = :p2"
    assert named == {"p0": "x", "p1": "y", "p2": "z"}


def test_translate_placeholders_none_params_passthrough():
    sql, named = _translate_placeholders("SELECT 1", None)
    assert sql == "SELECT 1"
    assert named is None


def test_translate_placeholders_mismatch_raises():
    with pytest.raises(ValueError):
        _translate_placeholders("A = %s AND B = %s", ["only-one"])


# =============================================================================
# Connection lifecycle
# =============================================================================

def test_connect_returns_connection_and_caches(fake_databricks):
    client = DatabricksClient()
    conn1 = client.connect()
    conn2 = client.connect()
    assert conn1 is conn2
    # databricks.sql.connect called exactly once (cached)
    assert fake_databricks["connect"].call_count == 1


def test_connect_builds_http_path_from_warehouse_id(fake_databricks):
    client = DatabricksClient()
    client.connect()
    kwargs = fake_databricks["connect"].call_args.kwargs
    assert kwargs["http_path"] == "/sql/1.0/warehouses/wh123"
    # Host is passed bare (no scheme), from the SDK Config.
    assert kwargs["server_hostname"] == "example.cloud.databricks.com"
    # Headless credentials provider from the SDK Config - never a browser.
    assert callable(kwargs["credentials_provider"])


def test_connect_prefers_explicit_http_path(fake_databricks, monkeypatch):
    from config import settings as settings_mod
    monkeypatch.setattr(
        "src.databricks_client.SETTINGS",
        settings_mod.Settings(
            dbx_http_path="/sql/1.0/warehouses/explicit",
            dbx_warehouse_id="ignored",
        ),
    )
    client = DatabricksClient()
    client.connect()
    kwargs = fake_databricks["connect"].call_args.kwargs
    assert kwargs["http_path"] == "/sql/1.0/warehouses/explicit"


def test_connect_without_warehouse_raises_clear_error(fake_databricks, monkeypatch):
    from config import settings as settings_mod
    monkeypatch.setattr(
        "src.databricks_client.SETTINGS",
        settings_mod.Settings(dbx_http_path="", dbx_warehouse_id=""),
    )
    client = DatabricksClient()
    with pytest.raises(RuntimeError, match="DATABRICKS_WAREHOUSE_ID"):
        client.connect()


def test_close_closes_underlying_connection(fake_databricks):
    client = DatabricksClient()
    client.connect()
    client.close()
    fake_databricks["conn"].close.assert_called_once()
    # Closing again is a no-op
    client.close()
    assert fake_databricks["conn"].close.call_count == 1


def test_context_manager_opens_and_closes(fake_databricks):
    with DatabricksClient() as c:
        assert c._conn is not None
    # After exit, conn is set to None in close()
    assert c._conn is None


# =============================================================================
# fetch_table - Arrow path
# =============================================================================

def test_fetch_table_builds_query_with_limit(fake_databricks):
    client = DatabricksClient()
    df = client.fetch_table("MY_TABLE", limit=50)
    assert list(df.columns) == ["COL_A", "COL_B"]  # uppercase normalization
    exec_args = fake_databricks["cursor"].execute.call_args.args[0]
    assert "CAT.SC.MY_TABLE" in exec_args
    assert "LIMIT 50" in exec_args
    fake_databricks["cursor"].close.assert_called_once()


def test_fetch_table_without_limit_no_limit_clause(fake_databricks):
    client = DatabricksClient()
    client.fetch_table("MY_TABLE")
    exec_args = fake_databricks["cursor"].execute.call_args.args[0]
    assert "LIMIT" not in exec_args


def test_fetch_table_pushes_where_with_parameter_binding(fake_databricks):
    """The sidebar Project filter pushdown relies on ``fetch_table``
    accepting a ``WHERE`` fragment plus parameterized values, so user
    input never gets concatenated into the SQL text."""
    client = DatabricksClient()
    client.fetch_table(
        "MY_TABLE",
        where="PLANVIEW_ID IN (%s, %s)",
        params=["1101168", "1106771"],
    )
    sql, bound = fake_databricks["cursor"].execute.call_args.args
    assert "WHERE PLANVIEW_ID IN (:p0, :p1)" in sql
    assert "%s" not in sql
    assert bound == {"p0": "1101168", "p1": "1106771"}


def test_fetch_table_where_combined_with_limit(fake_databricks):
    """``WHERE`` and ``LIMIT`` compose: the LIMIT applies to the filtered
    rows so a tiny project filter is never silently truncated by Sample
    mode's row cap."""
    client = DatabricksClient()
    client.fetch_table(
        "MY_TABLE",
        limit=50,
        where="PLANVIEW_ID IN (%s)",
        params=["1101168"],
    )
    sql, _ = fake_databricks["cursor"].execute.call_args.args
    # Both clauses present in the right order: WHERE before LIMIT.
    assert sql.index("WHERE") < sql.index("LIMIT")


def test_fetch_table_closes_cursor_even_on_error(fake_databricks):
    fake_databricks["cursor"].execute.side_effect = RuntimeError("boom")
    client = DatabricksClient()
    with pytest.raises(RuntimeError):
        client.fetch_table("MY_TABLE", limit=10)
    fake_databricks["cursor"].close.assert_called_once()


# =============================================================================
# fetch_query - Python-rows path
# =============================================================================

def test_fetch_query_uses_fetchall_and_description(fake_databricks):
    """fetch_query must read rows via cur.fetchall() (NOT the Arrow path)
    and build the DataFrame from cur.description."""
    fake_databricks["cursor"].fetchall.return_value = [
        ("PV-00001",), ("PV-00002",), ("PV-00003",)
    ]
    fake_databricks["cursor"].description = [("project_id",)]

    client = DatabricksClient()
    df = client.fetch_query("SELECT DISTINCT PROJECT_ID FROM SOMEVIEW")

    assert list(df.columns) == ["PROJECT_ID"]  # uppercase normalization
    assert df["PROJECT_ID"].tolist() == ["PV-00001", "PV-00002", "PV-00003"]
    fake_databricks["cursor"].fetchall_arrow.assert_not_called()
    fake_databricks["cursor"].close.assert_called_once()


def test_fetch_query_passes_sql_through_unchanged(fake_databricks):
    fake_databricks["cursor"].fetchall.return_value = []
    fake_databricks["cursor"].description = [("a",)]
    client = DatabricksClient()
    sql = "SELECT DISTINCT PROJECT_ID FROM CAT.SC.VWS_GP_STANDARD_SHARE"
    client.fetch_query(sql)
    exec_args = fake_databricks["cursor"].execute.call_args.args[0]
    assert exec_args == sql


def test_fetch_query_closes_cursor_on_error(fake_databricks):
    fake_databricks["cursor"].execute.side_effect = RuntimeError("boom")
    client = DatabricksClient()
    with pytest.raises(RuntimeError):
        client.fetch_query("SELECT 1")
    fake_databricks["cursor"].close.assert_called_once()


# =============================================================================
# execute - persistence write path
# =============================================================================

def test_execute_binds_params_server_side(fake_databricks):
    client = DatabricksClient()
    client.execute(
        "INSERT INTO CAT.SC.DQS_EVENTS (TS, PAYLOAD) VALUES (%s, %s)",
        ["2026-01-01T00:00:00+00:00", "{}"],
    )
    sql, bound = fake_databricks["cursor"].execute.call_args.args
    assert "VALUES (:p0, :p1)" in sql
    assert bound == {"p0": "2026-01-01T00:00:00+00:00", "p1": "{}"}
    fake_databricks["cursor"].close.assert_called_once()


def test_execute_without_params(fake_databricks):
    client = DatabricksClient()
    client.execute("DELETE FROM CAT.SC.DQS_EVENTS WHERE FALSE")
    assert fake_databricks["cursor"].execute.call_args.args == (
        "DELETE FROM CAT.SC.DQS_EVENTS WHERE FALSE",
    )


# =============================================================================
# Shared client (one connection per Step 2)
# =============================================================================

@pytest.fixture(autouse=True)
def _reset_shared_client():
    """Drop the module-level cached client between tests so each test
    starts from a clean state."""
    import src.databricks_client as dc
    dc._SHARED = None
    yield
    dc._SHARED = None


def test_get_shared_client_returns_same_instance(fake_databricks):
    """First call creates a DatabricksClient and opens the connection;
    subsequent calls reuse it - proving Step 2's data-product build and
    the reference prefetch share one connection."""
    from src.databricks_client import get_shared_client

    a = get_shared_client()
    b = get_shared_client()
    assert a is b
    # Underlying databricks.sql.connect called only once.
    assert fake_databricks["connect"].call_count == 1


def test_close_shared_client_drops_cached_instance(fake_databricks):
    """Restart calls close_shared_client(); the next get_shared_client()
    must create a fresh instance and reconnect."""
    from src.databricks_client import close_shared_client, get_shared_client

    first = get_shared_client()
    close_shared_client()
    fake_databricks["conn"].close.assert_called_once()

    second = get_shared_client()
    assert second is not first
    assert fake_databricks["connect"].call_count == 2


def test_close_shared_client_when_unset_is_noop():
    """Safe to call from any teardown path even when nothing is cached."""
    from src.databricks_client import close_shared_client
    close_shared_client()  # must not raise


# =============================================================================
# Reference loader integration - Databricks branch
# =============================================================================

def test_load_vws_gp_standard_share_in_databricks_mode_uses_distinct_project_id(
    fake_databricks, monkeypatch
):
    """``_load_vws_gp_standard_share`` must:
    - Skip the mock branch when DATA_SOURCE=databricks.
    - Project PROJECT_ID + COUNTRY + E05_DEPARTMENT + BUSINESS (the columns
      E7, E2, and E6's project-type segmentation need) with DISTINCT.
    - Read from the configured Unity Catalog namespace.
    - Use the SHARED client (so it reuses the connection opened by
      data_product_builder).
    """
    from config import settings as settings_mod

    new_settings = settings_mod.Settings(
        data_source="databricks",
        dbx_catalog="CAT",
        dbx_schema="SC",
        dbx_warehouse_id="wh123",
    )
    monkeypatch.setattr("src.reference_data.SETTINGS", new_settings)
    monkeypatch.setattr("src.databricks_client.SETTINGS", new_settings)
    fake_databricks["cursor"].fetchall.return_value = [
        ("PV-00001", "BR", "BROWNFIELD", "UPSTREAM"),
        ("PV-00002", "US", "GREENFIELD", "DOWNSTREAM"),
    ]
    fake_databricks["cursor"].description = [
        ("project_id",),
        ("country",),
        ("e05_department",),
        ("business",),
    ]

    from src.reference_data import _load_vws_gp_standard_share
    df = _load_vws_gp_standard_share()

    exec_args = fake_databricks["cursor"].execute.call_args.args[0]
    assert exec_args == (
        "SELECT DISTINCT PROJECT_ID, COUNTRY, E05_DEPARTMENT, BUSINESS "
        "FROM CAT.SC.VWS_GP_STANDARD_SHARE"
    )
    assert list(df.columns) == [
        "PROJECT_ID", "COUNTRY", "E05_DEPARTMENT", "BUSINESS"
    ]
    assert df["PROJECT_ID"].tolist() == ["PV-00001", "PV-00002"]


def test_load_acce_coa_master_reads_from_configured_namespace(
    fake_databricks, monkeypatch
):
    """``ACCE_COA_MASTER`` lost its hardcoded Snowflake-era location: the
    migration consolidated it into the single configured namespace."""
    from config import settings as settings_mod

    new_settings = settings_mod.Settings(
        data_source="databricks",
        dbx_catalog="CAT",
        dbx_schema="SC",
        dbx_warehouse_id="wh123",
    )
    monkeypatch.setattr("src.reference_data.SETTINGS", new_settings)
    monkeypatch.setattr("src.databricks_client.SETTINGS", new_settings)
    fake_databricks["cursor"].fetchall.return_value = [("101", "ISO1", "SAB1")]
    fake_databricks["cursor"].description = [
        ("icarus_coa",), ("iso_cor",), ("sab",),
    ]

    from src.reference_data import _load_acce_coa_master
    df = _load_acce_coa_master()

    exec_args = fake_databricks["cursor"].execute.call_args.args[0]
    assert exec_args == "SELECT ICARUS_COA, ISO_COR, SAB FROM CAT.SC.ACCE_COA_MASTER"
    assert list(df.columns) == ["ICARUS_COA", "ISO_COR", "SAB"]


def test_data_product_builder_uses_shared_client_in_databricks_mode(
    fake_databricks, monkeypatch
):
    """The data-product builder must obtain its fetcher from the shared
    client so a follow-up reference-dataset prefetch reuses the same
    connection (one connection total per Step 2 entry)."""
    from config import settings as settings_mod

    new_settings = settings_mod.Settings(
        data_source="databricks",
        dbx_catalog="CAT",
        dbx_schema="SC",
        dbx_warehouse_id="wh123",
    )
    monkeypatch.setattr("src.data_product_builder.SETTINGS", new_settings)
    monkeypatch.setattr("src.databricks_client.SETTINGS", new_settings)

    from src.data_product_builder import _default_fetcher
    from src.databricks_client import get_shared_client

    fetcher = _default_fetcher(row_limit=None)
    fetcher("MY_TABLE")
    fetcher("OTHER_TABLE")
    # Touch the shared client directly, it must be the same one the
    # fetcher used (no second databricks.sql.connect call).
    get_shared_client()

    assert fake_databricks["connect"].call_count == 1
