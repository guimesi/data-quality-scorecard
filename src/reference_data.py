"""
Reference data registry for referential-integrity DQR rules.

Custom rules (e.g. EPT E7) need to look up a *master* / reference dataset
to validate that a foreign key resolves. This module is the single point of
truth for those lookups so individual rule check functions stay decoupled
from where the data lives (mock generator vs. Snowflake).

Registered datasets are exposed by **table name** (e.g.
``"VWS_GP_STANDARD_SHARE"``) and returned as a pandas DataFrame, or
``None`` when the dependency is unavailable. Custom rules that depend on a
missing reference must raise
:class:`src.custom_dqr_engine.CustomRuleNotEvaluated` instead of silently
passing, the dispatcher records the reason and Step 6 surfaces a
"Not evaluated" warning.

Eager loading: :func:`prefetch_reference_datasets` pre-loads each named
dataset into the Streamlit session-state cache. Step 2 calls it after
building the data products so the Snowflake round-trip happens once,
alongside the system table fetches, instead of lazily during Step 6 or on
every dashboard re-render. :func:`get_reference_dataset` always reads from
that cache first, falling back to the loader only when the cache is empty
(e.g. during pure unit tests that don't go through Step 2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd

from config.settings import SETTINGS
from src.mock_data import _mock_acce_coa_master, _mock_vws_gp_standard_share

logger = logging.getLogger(__name__)


_SESSION_STATE_KEY = "_reference_datasets"


@dataclass
class _CacheEntry:
    df: Optional[pd.DataFrame]
    error: Optional[str] = None


# =============================================================================
# Loaders (pure, no session_state)
# =============================================================================

def _resolve_reference_location() -> tuple:
    """Resolve ``(database, schema)`` for the reference dataset that lives
    alongside the active domain's primary tables.

    Mirrors ``src.snowflake_client._resolve_location`` so this loader and
    the table fetcher agree on where to read from. Domains with explicit
    ``snowflake_database`` / ``snowflake_schema`` (e.g. Quality with
    ``INGESTION_DB.GP_QUALITY``) win over this module's ``SETTINGS`` -
    Cost Estimate leaves them empty and falls back to ``SETTINGS`` so
    legacy callers / tests keep their behaviour.
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
            "Failed to resolve active domain for reference data; "
            "falling back to SETTINGS",
            exc_info=True,
        )
    return (
        domain_db or SETTINGS.sf_database,
        domain_schema or SETTINGS.sf_schema,
    )


def _load_vws_gp_standard_share() -> Optional[pd.DataFrame]:
    """Resolve the ``VWS_GP_STANDARD_SHARE`` reference dataset for the active
    data source. Lives in the same warehouse / database / schema as the
    EPT primary table when running against Snowflake.

    Snowflake mode projects ``PROJECT_ID`` (used by E7 for referential
    integrity), ``COUNTRY`` (used by E2 to validate project location
    after the EPT → Planview join), ``E05_DEPARTMENT`` (brownfield /
    greenfield classification consumed by E6's segmented-IQR mode) and
    ``BUSINESS`` (business-line classification, same consumer), and uses
    ``DISTINCT`` to keep the result small. The query goes through
    ``SnowflakeClient.fetch_query`` (rows → pandas, no pyarrow) so we
    sidestep the ``ArrowInvalid: Schema at index N was different`` error
    that ``fetch_pandas_all`` raises on this view when nullable columns
    are inferred as different types across result chunks.

    May raise the underlying connector error, callers
    (:func:`prefetch_reference_datasets`) capture and surface it as a
    cached error string.
    """
    if SETTINGS.data_source == "mock":
        return _mock_vws_gp_standard_share()
    # Snowflake mode - exception propagates to the caller.
    from src.snowflake_client import get_shared_client
    database, schema = _resolve_reference_location()
    qualified = f"{database}.{schema}.VWS_GP_STANDARD_SHARE"
    sql = (
        "SELECT DISTINCT PROJECT_ID, COUNTRY, E05_DEPARTMENT, BUSINESS "  # nosec B608 - static column list; only the internal db/schema is interpolated, no user input
        f"FROM {qualified}"
    )
    return get_shared_client().fetch_query(sql)


def _load_acce_coa_master() -> Optional[pd.DataFrame]:
    """Resolve the ``ACCE_COA_MASTER`` reference dataset for the active
    data source. Used by A1 to map the leading 3-digit COA group derived
    from ``COMPLETE_WBC`` to ``ISO_COR`` and ``SAB``.

    Lives in ``INGESTION_DB.GP_ADF_CSE`` in production (a different
    database than ``VWS_GP_STANDARD_SHARE``), the qualified name is
    fully spelled out so the loader doesn't depend on Snowflake search
    paths. Snowflake mode projects only the three columns A1 needs.

    May raise the underlying connector error, callers
    (:func:`prefetch_reference_datasets`) capture and surface it as a
    cached error string.
    """
    if SETTINGS.data_source == "mock":
        return _mock_acce_coa_master()
    from src.snowflake_client import get_shared_client
    qualified = "INGESTION_DB.GP_ADF_CSE.ACCE_COA_MASTER"
    sql = f"SELECT ICARUS_COA, ISO_COR, SAB FROM {qualified}"  # nosec B608 - static column list + hardcoded internal table name, no user input
    return get_shared_client().fetch_query(sql)


# Logical name -> loader callable. The logical name is the actual table
# name in Snowflake so the same identifier flows from the catalog metadata
# to the rule card and to the SQL fetcher.
_REGISTRY: Dict[str, Callable[[], Optional[pd.DataFrame]]] = {
    "VWS_GP_STANDARD_SHARE": _load_vws_gp_standard_share,
    "ACCE_COA_MASTER": _load_acce_coa_master,
}


# =============================================================================
# Session-state cache plumbing
# =============================================================================

def _session_cache_get_only() -> Optional[Dict[str, _CacheEntry]]:
    """Return the existing session-state cache dict, or ``None`` outside a
    Streamlit run / when the cache hasn't been initialised yet."""
    try:
        import streamlit as st
        return st.session_state.get(_SESSION_STATE_KEY)
    except Exception:
        return None


def _session_cache_get_or_create() -> Optional[Dict[str, _CacheEntry]]:
    """Return the session-state cache dict, creating it if needed. Returns
    ``None`` outside a Streamlit run (e.g. pure pytest unit tests) so the
    caller knows there's nothing to cache to."""
    try:
        import streamlit as st
        if _SESSION_STATE_KEY not in st.session_state:
            st.session_state[_SESSION_STATE_KEY] = {}
        return st.session_state[_SESSION_STATE_KEY]
    except Exception:
        return None


# =============================================================================
# Public API
# =============================================================================

def get_reference_dataset(name: str) -> Optional[pd.DataFrame]:
    """Return the reference DataFrame registered under ``name``.

    Reads from the session-state cache first (populated by
    :func:`prefetch_reference_datasets` in Step 2). Falls back to the
    loader when the cache is empty - convenient for unit tests that don't
    go through Step 2. Returns ``None`` when no loader is configured or
    the loader resolves to ``None``.
    """
    cache = _session_cache_get_only()
    if cache is not None and name in cache:
        return cache[name].df
    loader = _REGISTRY.get(name)
    if loader is None:
        return None
    return loader()


def get_reference_dataset_error(name: str) -> Optional[str]:
    """Return the error message recorded when the loader for ``name`` last
    failed, or ``None`` when there is no recorded error."""
    cache = _session_cache_get_only()
    if cache is None:
        return None
    entry = cache.get(name)
    return entry.error if entry is not None else None


def prefetch_reference_datasets(
    names: Iterable[str],
) -> Dict[str, Optional[pd.DataFrame]]:
    """Eager-load each requested reference dataset into the session-state
    cache. Already-cached names (success or failure) are not re-loaded.

    Returns a dict of ``{name: df_or_none}`` so the caller can introspect
    what was loaded. Outside a Streamlit run, falls back to direct loader
    calls without caching.
    """
    cache = _session_cache_get_or_create()
    if cache is None:
        # Outside Streamlit - just call loaders directly, no caching.
        return {n: get_reference_dataset(n) for n in names}
    for name in names:
        if name in cache:
            continue
        loader = _REGISTRY.get(name)
        if loader is None:
            cache[name] = _CacheEntry(
                df=None,
                error=f"No loader registered for reference dataset '{name}'",
            )
            continue
        try:
            df = loader()
            cache[name] = _CacheEntry(
                df=df,
                error=None if df is not None else f"Loader for '{name}' returned None",
            )
        except Exception as e:  # broad: Snowflake / network errors of any kind
            cache[name] = _CacheEntry(df=None, error=f"{type(e).__name__}: {e}")
    return {n: cache[n].df for n in names if n in cache}


def clear_reference_cache() -> None:
    """Drop every cached reference dataset. Called from the Restart button
    in Step 6 and from sample-mode toggle so subsequent navigation gets a
    fresh fetch."""
    try:
        import streamlit as st
        if _SESSION_STATE_KEY in st.session_state:
            del st.session_state[_SESSION_STATE_KEY]
    except Exception:  # nosec B110 - best-effort cache invalidation; outside a Streamlit run (no import / no key) there is simply nothing to clear, which is non-fatal
        pass


def required_reference_datasets_for_systems(systems: Iterable[str]) -> List[str]:
    """Return the unique set of reference dataset names needed by the
    custom rules of the given systems, in the order they appear in the
    catalog. Used by Step 2 to know what to prefetch."""
    # Imported lazily to keep src/ free of UI-side import cycles.
    from config.custom_dqr_catalog import get_available_custom_dqr_rules

    seen: List[str] = []
    for system in systems:
        for rule in get_available_custom_dqr_rules(system):
            if rule.reference is None:
                continue
            ref_name = rule.reference.get("reference_dataset")
            if ref_name and ref_name not in seen:
                seen.append(ref_name)
    return seen
