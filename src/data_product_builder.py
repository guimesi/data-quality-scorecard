# pyright: reportArgumentType=false, reportReturnType=false
"""
Data Product Builder.

Takes a system code (ADR, ACCE, EPT), fetches all its tables from either
mock data or Databricks, and joins them into a single denormalized DataFrame
(the "Data Product") using the primary table + left joins on the join_key
declared in each TableDef.

Join keys used (see config/systems.py - TableDef.join_key per child):
 - ADR  -> ROW_ID for all children (primary = ADR_DIM_ESTIMATEITEMRECORD)
 - ACCE -> ROW_ID for cost / qty children, DESIGN_ID for the design
           dimension (primary = ACCE_ESTIMATEITEMRECORD)
 - EPT  -> no joins (single-table system)

PLANVIEW_ID is NOT used for building data products. It is preserved as a
regular column in the output (present on primary tables) and may be used
later for cross-system analysis.
"""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd

from config.settings import SETTINGS
from config.systems import SHARED_KEY, SystemDef, TableDef, get_system
from src.models import DataProduct


def _default_fetcher(
    row_limit: Optional[int] = None,
    system: Optional[SystemDef] = None,
    planview_ids: Optional[Iterable[str]] = None,
    filter_column: str = SHARED_KEY,
) -> Callable[[str], pd.DataFrame]:
    """Return a function that fetches a table by name.

    ``row_limit`` is a per-table row cap (``None`` = no cap).

    When ``planview_ids`` is non-empty and ``system`` is supplied, the
    Databricks branch **pushes the filter down to SQL**: the primary
    table is fetched with ``WHERE filter_column IN (...)`` and each
    child table is fetched with ``WHERE join_key IN (SELECT join_key
    FROM primary WHERE ...)``. This avoids a real-world bug where
    Sample mode's ``LIMIT N`` was applied **before** the in-memory
    filter, so a user filtering on a project that wasn't in the first
    ``N`` rows saw an empty data product. The mock branch leaves the
    in-memory filter to do its job since mock datasets are small.
    """
    if SETTINGS.is_mock:
        from src.mock_data import fetch_mock_table
        if row_limit is None:
            return fetch_mock_table
        return lambda name: fetch_mock_table(name).head(row_limit)

    # Databricks branch - shared client so reference-dataset prefetch
    # reuses the same connection (single connection per Step 2).
    from src.databricks_client import _resolve_location, get_shared_client
    client = get_shared_client()

    canon_values: List[str] = []
    if planview_ids:
        canon_values = [
            v for v in (_canonicalize_id(p) for p in planview_ids) if v is not None
        ]

    # No filter (or no system metadata to drive the per-table pushdown):
    # keep the historical behaviour - ``SELECT * FROM table LIMIT N``.
    if not canon_values or system is None:
        return lambda name: client.fetch_table(name, limit=row_limit)

    primary_name = system.primary_table.name
    placeholders = ", ".join(["%s"] * len(canon_values))
    database, schema = _resolve_location()
    primary_qualified = f"{database}.{schema}.{primary_name}"
    join_keys: Dict[str, str] = {t.name: t.join_key for t in system.tables if not t.is_primary}

    def _fetch(name: str) -> pd.DataFrame:
        if name == primary_name:
            # Push the filter onto the primary directly. LIMIT applies
            # to the *filtered* set, so a tiny filter never gets capped
            # away by Sample mode.
            return client.fetch_table(
                name,
                limit=row_limit,
                where=f"{filter_column} IN ({placeholders})",
                params=canon_values,
            )
        join_key = join_keys.get(name)
        if join_key is None:
            # Defensive fallback - an unexpected table name (would mean
            # the fetcher was called for something outside the system's
            # declared tables). Behave like the unfiltered path so we
            # don't break the build.
            return client.fetch_table(name, limit=row_limit)
        # Child table - narrow it via a subquery on the primary's
        # filtered ``join_key`` set so the LEFT JOIN downstream always
        # finds its match and Sample mode's LIMIT can't drop the
        # relevant rows.
        return client.fetch_table(
            name,
            where=(
                f"{join_key} IN ("  # nosec B608 - join_key/filter_column/primary_qualified are internal config; user values are bound via params, never interpolated
                f"SELECT {join_key} FROM {primary_qualified} "
                f"WHERE {filter_column} IN ({placeholders})"
                f")"
            ),
            params=canon_values,
        )

    return _fetch


def _prefix_columns(df: pd.DataFrame, table: TableDef, exclude: List[str]) -> pd.DataFrame:
    """Prefix all columns of df with a short table-specific prefix, except
    columns listed in `exclude`.

    Prefix source: TableDef.column_prefix if provided, otherwise derived
    from the last underscore-separated component of the table name.
    """
    if table.column_prefix:
        prefix = table.column_prefix
    else:
        # Fallback: last component (e.g. ADR_ESTIMATEWBS -> ESTIMATEWBS)
        prefix = table.name.rsplit("_", 1)[-1]

    renames = {}
    for col in df.columns:
        if col in exclude:
            continue
        if not col.upper().startswith(prefix.upper()):
            renames[col] = f"{prefix}_{col}"
    return df.rename(columns=renames)


def _canonicalize_id(value: object) -> Optional[str]:
    """Normalize a single id value for filter comparison.

    Real-world ``PLANVIEW_ID``s in the warehouse are stored as numbers (e.g.
    ``1101168``). When pandas pulls them back with any NULL in the column,
    the dtype is promoted to ``float64`` and a naive ``astype("string")``
    yields ``"1101168.0"`` - which never matches the user's typed
    ``"1101168"``. We canonicalize both sides: strip whitespace, and for
    values that parse as a whole number, return the integer form. Non-
    numeric IDs (``PV-00001``, ``QPC-001``) fall through unchanged.
    """
    if value is None:
        return None
    try:
        if pd.isna(value):  # NaN / NaT / pd.NA
            return None
    except (TypeError, ValueError):
        # Value is not NA-testable (e.g. an unhashable/array-like): fall
        # through to canonicalize it as a string below. Not an error.
        pass
    text = str(value).strip()
    if not text:
        return None
    try:
        as_float = float(text)
    except (TypeError, ValueError):
        return text
    if as_float.is_integer():
        return str(int(as_float))
    return text


def _apply_planview_filter(
    df: pd.DataFrame,
    planview_ids: Optional[Iterable[str]],
    column: str = SHARED_KEY,
) -> pd.DataFrame:
    """Restrict ``df`` to rows whose ``column`` value is in ``planview_ids``.

    The column defaults to :data:`SHARED_KEY` (``PLANVIEW_ID``) for the
    historical Cost Estimate flow; the Quality domain passes
    ``column="PROJECT_CODE"`` (see ``config.domains.ProjectFilterDef``).

    Both the user input and the column values are run through
    :func:`_canonicalize_id` so a typed ``"1101168"`` matches a stored
    ``1101168`` / ``1101168.0`` / ``" 1101168 "`` interchangeably.

    No-op when the filter is empty/None or when the column is absent;
    the latter shouldn't happen for a domain-configured column, but we
    guard defensively so a malformed schema doesn't crash the build.
    """
    if not planview_ids:
        return df
    if column not in df.columns:
        return df
    wanted = {c for c in (_canonicalize_id(p) for p in planview_ids) if c is not None}
    if not wanted:
        return df.iloc[0:0].copy()
    canonical = df[column].map(_canonicalize_id)
    return df[canonical.isin(wanted)].copy()


def build_data_product(
    system_code: str,
    fetcher: Optional[Callable[[str], pd.DataFrame]] = None,
    row_limit: Optional[int] = None,
    planview_ids: Optional[Iterable[str]] = None,
    filter_column: str = SHARED_KEY,
) -> DataProduct:
    """Build the data product for one system.

    Strategy:
    - Fetch the primary table.
    - Optionally filter the primary table by PLANVIEW_ID - child joins on
      ROW_ID then naturally only carry rows for those projects.
    - For each non-primary table, left-join on table.join_key (ROW_ID for
      ADR/ACCE). EPT has no non-primary tables.
    - Prefix columns of non-primary tables to avoid name collisions.
    - Return a DataProduct wrapping the resulting DataFrame.
    """
    system: SystemDef = get_system(system_code)
    fetch = fetcher or _default_fetcher(
        row_limit=row_limit,
        system=system,
        planview_ids=planview_ids,
        filter_column=filter_column,
    )

    primary = system.primary_table
    result: pd.DataFrame = fetch(primary.name).copy()
    # Normalize column names to uppercase for consistency
    result.columns = [c.upper() for c in result.columns]
    result = _apply_planview_filter(result, planview_ids, column=filter_column)

    joined_tables = [primary.name]

    for table in system.tables:
        if table.is_primary:
            continue
        df = fetch(table.name).copy()
        df.columns = [c.upper() for c in df.columns]
        if table.join_key not in df.columns:
            raise ValueError(
                f"Table {table.name} is missing join_key {table.join_key}."
            )
        df = _prefix_columns(df, table, exclude=[table.join_key])

        # Optional per-row derivation, applied *before* group-by aggregation
        # so transforms that depend on row-level state (e.g. COALESCE of two
        # source columns) see the unaggregated input.
        if table.derive_columns is not None:
            df = table.derive_columns(df)

        # For one-to-many relationships (e.g., WBS), we aggregate by join_key
        # so the primary row is not duplicated. Aggregation rules:
        # - numeric -> sum (totals)
        # - others -> first non-null
        if df[table.join_key].duplicated().any():
            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            other_cols = [c for c in df.columns if c not in numeric_cols and c != table.join_key]
            agg: Dict[str, str] = {}
            for c in numeric_cols:
                agg[c] = "sum"
            for c in other_cols:
                agg[c] = "first"
            df = df.groupby(table.join_key, as_index=False).agg(agg)

        result = result.merge(df, how="left", on=table.join_key)
        joined_tables.append(table.name)

    return DataProduct(
        system_code=system_code,
        name=f"{system_code}_DATA_PRODUCT",
        df=result,
        source_tables=joined_tables,
    )


def build_multiple(
    system_codes: List[str],
    row_limit: Optional[int] = None,
    planview_ids: Optional[Iterable[str]] = None,
    filter_column: str = SHARED_KEY,
) -> Dict[str, DataProduct]:
    """Build data products for multiple systems.

    Each system gets its own fetcher because the SQL pushdown for the
    sidebar Project filter needs the active system's primary-table name
    and per-child ``join_key`` (see :func:`_default_fetcher`). The
    underlying Databricks connection is still shared - ``get_shared_client``
    is process-wide - so this keeps the single-auth-round-trip behavior.
    """
    return {
        code: build_data_product(
            code,
            row_limit=row_limit,
            planview_ids=planview_ids,
            filter_column=filter_column,
        )
        for code in system_codes
    }
