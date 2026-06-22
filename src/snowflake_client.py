# pyright: reportArgumentType=false
"""
Snowflake client wrapper.

Supports externalbrowser auth (default). Returns pandas DataFrames.

Two paths to fetch data:

- :meth:`SnowflakeClient.fetch_table` - fast Arrow path
  (``cursor.fetch_pandas_all``). Used by the data-product builder for system
  tables.
- :meth:`SnowflakeClient.fetch_query` - Python-rows path (``cursor.fetchall``).
  Used by the reference-data loader because Snowflake's Arrow encoding can
  produce inconsistent per-chunk schemas on tables whose nullable columns
  get inferred as different types per result chunk
  (``ArrowInvalid: Schema at index N was different ...``). Slightly slower
  but resilient.

A shared client (:func:`get_shared_client` / :func:`close_shared_client`)
lets multiple call sites within a single Streamlit run reuse one open
connection, so Step 2's data-product build and the reference-data
prefetch don't trigger two consecutive auth round-trips.
"""
from __future__ import annotations

import logging
from typing import Optional, Sequence

import pandas as pd

from config.settings import SETTINGS

logger = logging.getLogger(__name__)


def _resolve_location() -> tuple:
    """Resolve the ``(database, schema)`` to qualify table reads.

    Reads the active domain's ``snowflake_database`` /
    ``snowflake_schema`` first - so Quality reads from
    ``INGESTION_DB.GP_QUALITY`` even when ``.env`` points at a different
    default - and falls back to this module's ``SETTINGS`` reference
    when the domain leaves them empty. Reading ``SETTINGS`` from this
    module (rather than via the helper in ``config.domains``) keeps
    test monkeypatches on ``src.snowflake_client.SETTINGS`` effective.
    """
    domain_db = ""
    domain_schema = ""
    try:
        from config.domains import get_active_domain
        domain = get_active_domain()
        domain_db = domain.snowflake_database or ""
        domain_schema = domain.snowflake_schema or ""
    except Exception:
        # Domain resolution can fail outside a Streamlit run or if config
        # is mid-refactor; we log so the SETTINGS fallback isn't silent.
        logger.warning(
            "Failed to resolve active domain; falling back to SETTINGS",
            exc_info=True,
        )
    database = domain_db or SETTINGS.sf_database
    schema = domain_schema or SETTINGS.sf_schema
    return database, schema


class SnowflakeClient:
    """Thin wrapper over snowflake.connector. Instantiated lazily."""

    def __init__(self) -> None:
        self._conn = None

    def connect(self):
        if self._conn is not None:
            return self._conn

        # Imported lazily so that mock mode does not require the package
        import snowflake.connector  # type: ignore

        params = {
            "account": SETTINGS.sf_account,
            "user": SETTINGS.sf_user,
            "authenticator": SETTINGS.sf_authenticator,
            "database": SETTINGS.sf_database,
            "schema": SETTINGS.sf_schema,
        }
        if SETTINGS.sf_warehouse:
            params["warehouse"] = SETTINGS.sf_warehouse
        if SETTINGS.sf_role:
            params["role"] = SETTINGS.sf_role

        self._conn = snowflake.connector.connect(**params)
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
        """Fetch a table as DataFrame. Respects DATABASE.SCHEMA from the
        active domain (with ``SETTINGS`` as fallback).

        Uses the Arrow path (``fetch_pandas_all``) - fastest for the wide
        result sets we need for system tables. If you hit an
        ``ArrowInvalid: Schema at index N was different`` error on a
        specific table, project the columns you actually need via
        :meth:`fetch_query` instead.

        Args:
            table_name: bare table name (qualified with the resolved
                ``database.schema`` internally).
            limit: optional row cap (``None`` = no LIMIT clause).
            where: optional SQL WHERE fragment (without the ``WHERE``
                keyword) that the caller has built. Use ``%s``
                placeholders for any user-supplied literal and pass the
                values through ``params`` - the Snowflake connector
                binds them server-side, so no quoting / escaping is
                performed in this module.
            params: positional parameter values that match ``%s`` slots
                in ``where``. Ignored when ``where`` is falsy.
        """
        conn = self.connect()
        database, schema = _resolve_location()
        qualified = f"{database}.{schema}.{table_name}"
        query = f"SELECT * FROM {qualified}"
        if where:
            query += f" WHERE {where}"
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        cur = conn.cursor()
        try:
            if where and params:
                cur.execute(query, list(params))
            else:
                cur.execute(query)
            df = cur.fetch_pandas_all()
        finally:
            cur.close()
        # Normalize column names to uppercase (Snowflake default)
        df.columns = [c.upper() for c in df.columns]
        return df

    def fetch_query(self, sql: str) -> pd.DataFrame:
        """Run an arbitrary SELECT and return the result as a DataFrame.

        Uses ``cur.fetchall()`` (Python rows → pandas) instead of the Arrow
        path, so callers are immune to Snowflake's Arrow chunk-schema
        mismatch - a real-world bug where ``fetch_pandas_all()`` raises
        ``ArrowInvalid: Schema at index N was different ...`` because
        nullable columns get inferred as different Arrow types across
        result chunks.

        Use this for small reference datasets (e.g. ``SELECT DISTINCT
        PROJECT_ID FROM ...``); use :meth:`fetch_table` for the wide
        system-table reads where the Arrow path is faster and safe.
        """
        conn = self.connect()
        cur = conn.cursor()
        try:
            cur.execute(sql)
            rows = cur.fetchall()
            cols = [d[0].upper() for d in cur.description]
        finally:
            cur.close()
        return pd.DataFrame(rows, columns=cols)

    def __enter__(self) -> "SnowflakeClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


# =============================================================================
# Process-wide shared client (so Step 2's system-table fetch and the
# reference-dataset prefetch share a single auth round-trip)
# =============================================================================

_SHARED: Optional[SnowflakeClient] = None


def get_shared_client() -> SnowflakeClient:
    """Return a process-wide cached :class:`SnowflakeClient`.

    The first call opens the connection (triggering external-browser auth
    when needed); subsequent calls reuse it, so the data-product build
    and the reference dataset prefetch in Step 2 share **one** open
    connection instead of opening two consecutive ones.

    Lifetime is the Streamlit script process.
    :func:`utils.session.state._clear_workflow_state_for_domain_switch`
    drops it - it runs on Restart and on any domain / mode switch.
    """
    global _SHARED
    if _SHARED is None:
        _SHARED = SnowflakeClient()
    _SHARED.connect()  # idempotent: returns the existing _conn if any
    return _SHARED


def close_shared_client() -> None:
    """Close and drop the cached shared client. Safe to call when nothing
    is cached (no-op). Called from
    ``utils.session.state._clear_workflow_state_for_domain_switch`` - i.e. on
    Restart and on any domain / mode switch - so the next selection starts
    with a fresh auth round."""
    global _SHARED
    if _SHARED is not None:
        try:
            _SHARED.close()
        finally:
            _SHARED = None
