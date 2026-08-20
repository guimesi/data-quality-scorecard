# pyright: reportArgumentType=false
"""
Databricks SQL client wrapper.

Connects to a Databricks SQL Warehouse via ``databricks-sql-connector``
and returns pandas DataFrames. Authentication is fully headless:

- **Databricks Apps (production)** - the platform injects the app's
  service-principal OAuth credentials (``DATABRICKS_CLIENT_ID`` /
  ``DATABRICKS_CLIENT_SECRET``) plus ``DATABRICKS_HOST`` into the
  container; ``databricks.sdk.core.Config`` picks them up automatically.
- **Local development** - set ``DATABRICKS_HOST`` and a personal access
  token (``DATABRICKS_TOKEN``) in ``.env`` (or use a configured
  ``~/.databrickscfg`` profile). Same ``Config`` resolution, no browser
  round-trip involved.

There is deliberately **no interactive (browser) auth path**: the app
must be able to run in a headless container.

Two paths to fetch data (same contract the app has always used):

- :meth:`DatabricksClient.fetch_table` - Arrow path
  (``cursor.fetchall_arrow().to_pandas()``), fastest for the wide system
  tables.
- :meth:`DatabricksClient.fetch_query` - Python-rows path
  (``cursor.fetchall``), used for the small reference datasets.

A shared client (:func:`get_shared_client` / :func:`close_shared_client`)
lets multiple call sites within a single Streamlit run reuse one open
connection, so Step 2's data-product build and the reference-data
prefetch don't open two consecutive connections.

**Parameter binding**: callers build WHERE fragments with ``%s``
placeholders and pass values via ``params`` (the historical contract).
The connector's native parameters use *named* markers, so ``%s`` slots
are translated positionally to ``:p0 .. :pN`` and the values travel in a
dict - user input is always bound server-side, never concatenated into
the SQL text.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional, Sequence, Tuple

import pandas as pd

from config.settings import SETTINGS

logger = logging.getLogger(__name__)


def _resolve_location() -> tuple:
    """Resolve the ``(catalog, schema)`` used to qualify table reads.

    All application tables live in a single Unity Catalog namespace
    (``SETTINGS.dbx_catalog`` . ``SETTINGS.dbx_schema``, default
    ``entai_sandbox_catalog.data_quality_scorecards``), mirroring the
    original Snowflake table names one-to-one.
    """
    return SETTINGS.dbx_catalog, SETTINGS.dbx_schema


def _resolve_http_path() -> str:
    """Resolve the SQL Warehouse HTTP path for this connection.

    ``DATABRICKS_SQL_HTTP_PATH`` (full path) wins; otherwise the path is
    built from ``DATABRICKS_WAREHOUSE_ID`` - which is what a Databricks
    App receives when a ``sql-warehouse`` resource is attached to it.
    """
    if SETTINGS.dbx_http_path:
        return SETTINGS.dbx_http_path
    if SETTINGS.dbx_warehouse_id:
        return f"/sql/1.0/warehouses/{SETTINGS.dbx_warehouse_id}"
    raise RuntimeError(
        "No SQL Warehouse configured: set DATABRICKS_SQL_HTTP_PATH or "
        "DATABRICKS_WAREHOUSE_ID (in Databricks Apps, attach a "
        "sql-warehouse resource to the app)."
    )


def _translate_placeholders(
    sql: str, params: Optional[Sequence[object]]
) -> Tuple[str, Optional[Dict[str, object]]]:
    """Translate positional ``%s`` slots to the connector's named markers.

    ``"X IN (%s, %s)"`` with ``[a, b]`` becomes ``"X IN (:p0, :p1)"``
    with ``{"p0": a, "p1": b}``. Slot order is preserved, so the
    positional contract callers rely on still holds, and every value is
    bound server-side by the connector's native parameters.
    """
    if params is None:
        return sql, None
    parts = sql.split("%s")
    if len(parts) - 1 != len(params):
        raise ValueError(
            f"Placeholder mismatch: {len(parts) - 1} %s slots, "
            f"{len(params)} params"
        )
    out = parts[0]
    named: Dict[str, object] = {}
    for i, (value, tail) in enumerate(zip(params, parts[1:])):
        named[f"p{i}"] = value
        out += f":p{i}" + tail
    return out, named


class DatabricksClient:
    """Thin data-access wrapper over a Databricks SQL Warehouse connection.

    Queries run via ``databricks.sql`` cursors; callers build WHERE
    fragments with ``%s`` placeholders and pass values via ``params``
    (translated to named markers internally - see
    :func:`_translate_placeholders`). User input is **bound server-side**,
    never concatenated into SQL.
    """

    def __init__(self) -> None:
        self._conn = None  # databricks.sql Connection

    def connect(self):
        """Return the open connection, creating it on first use.

        Identity comes from ``databricks.sdk.core.Config`` - the app's
        service principal inside Databricks Apps, or ``DATABRICKS_HOST``
        + ``DATABRICKS_TOKEN`` (PAT) locally. Both are headless.
        """
        if self._conn is not None:
            return self._conn

        # Imported lazily so mock mode / unit tests don't require the
        # databricks packages.
        from databricks import sql as dbsql  # type: ignore
        from databricks.sdk.core import Config  # type: ignore

        cfg = Config()
        host = (cfg.host or "").removeprefix("https://").removeprefix("http://")
        if not host:
            raise RuntimeError(
                "No Databricks host configured: set DATABRICKS_HOST (and "
                "DATABRICKS_TOKEN for local development)."
            )
        self._conn = dbsql.connect(
            server_hostname=host,
            http_path=_resolve_http_path(),
            credentials_provider=lambda: cfg.authenticate,
        )
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None

    def fetch_table(
        self,
        table_name: str,
        limit: Optional[int] = None,
        where: Optional[str] = None,
        params: Optional[Sequence[object]] = None,
    ) -> pd.DataFrame:
        """Fetch a table as DataFrame, qualified with the configured
        ``catalog.schema`` (see :func:`_resolve_location`).

        Uses the Arrow path (``fetchall_arrow``) - fastest for the wide
        result sets we need for system tables.

        Args:
            table_name: bare table name (qualified with the resolved
                ``catalog.schema`` internally).
            limit: optional row cap (``None`` = no LIMIT clause).
            where: optional SQL WHERE fragment (without the ``WHERE``
                keyword) that the caller has built. Use ``%s``
                placeholders for any user-supplied literal and pass the
                values through ``params`` - they are bound server-side,
                so no quoting / escaping is performed in this module.
            params: positional parameter values that match ``%s`` slots
                in ``where``. Ignored when ``where`` is falsy.
        """
        self.connect()
        catalog, schema = _resolve_location()
        qualified = f"{catalog}.{schema}.{table_name}"
        query = f"SELECT * FROM {qualified}"  # nosec B608 - catalog/schema/table are internal config (not user input); user-supplied filter values are bound server-side via params, never interpolated
        if where:
            query += f" WHERE {where}"
        if limit is not None:
            query += f" LIMIT {int(limit)}"

        bind = list(params) if (where and params) else None
        sql, named = _translate_placeholders(query, bind)
        cur = self._conn.cursor()
        try:
            if named is not None:
                cur.execute(sql, named)
            else:
                cur.execute(sql)
            df = cur.fetchall_arrow().to_pandas()
        finally:
            cur.close()
        # Normalize column names to uppercase (the app's historical
        # Snowflake-era convention; every downstream consumer expects it).
        df.columns = [c.upper() for c in df.columns]
        return df

    def fetch_query(self, sql: str) -> pd.DataFrame:
        """Run an arbitrary SELECT and return the result as a DataFrame.

        Uses ``cur.fetchall()`` (Python rows -> pandas) instead of the
        Arrow path. Use this for small reference datasets (e.g. ``SELECT
        DISTINCT PROJECT_ID FROM ...``); use :meth:`fetch_table` for the
        wide system-table reads where the Arrow path is faster.
        """
        self.connect()
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            cols = [d[0].upper() for d in cur.description]
        finally:
            cur.close()
        return pd.DataFrame(rows, columns=cols)

    def execute(self, sql: str, params: Optional[Sequence[object]] = None) -> None:
        """Execute a non-SELECT statement (INSERT into the DQS_* app-state
        tables). ``%s`` slots in ``sql`` are translated to named markers
        and values are always bound server-side; callers never interpolate
        user input into ``sql``.

        This is the persistence layer's write path (:mod:`src.persistence`).
        Data reads stay on :meth:`fetch_table` / :meth:`fetch_query`.
        """
        self.connect()
        bind = list(params) if params else None
        stmt, named = _translate_placeholders(sql, bind)
        cur = self._conn.cursor()
        try:
            if named is not None:
                cur.execute(stmt, named)
            else:
                cur.execute(stmt)
        finally:
            cur.close()

    def __enter__(self) -> "DatabricksClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


# =============================================================================
# Process-wide shared client (so Step 2's system-table fetch and the
# reference-dataset prefetch share a single connection)
# =============================================================================

_SHARED: Optional[DatabricksClient] = None


def get_shared_client() -> DatabricksClient:
    """Return a process-wide cached :class:`DatabricksClient`.

    The first call opens the connection; subsequent calls reuse it, so
    the data-product build and the reference dataset prefetch in Step 2
    share **one** open connection instead of opening two consecutive ones.

    Lifetime is the Streamlit script process.
    :func:`utils.session.state._clear_workflow_state_for_domain_switch`
    drops it - it runs on Restart and on any domain / mode switch.
    """
    global _SHARED
    if _SHARED is None:
        _SHARED = DatabricksClient()
    _SHARED.connect()  # idempotent: returns the existing _conn if any
    return _SHARED


def close_shared_client() -> None:
    """Close and drop the cached shared client. Safe to call when nothing
    is cached (no-op). Called from
    ``utils.session.state._clear_workflow_state_for_domain_switch`` - i.e. on
    Restart and on any domain / mode switch - so the next selection starts
    with a fresh connection."""
    global _SHARED
    if _SHARED is not None:
        try:
            _SHARED.close()
        finally:
            _SHARED = None
