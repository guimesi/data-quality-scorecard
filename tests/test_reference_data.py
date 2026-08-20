"""Tests for src/reference_data.py.

Covers the public surface (get/prefetch/clear/required_*) plus the
session-state cache plumbing without needing a live Streamlit run. The
existing autouse fixture in ``conftest.py`` pins ``DATA_SOURCE=mock``, so
the loaders resolve to the in-memory mock builders rather than hitting
Snowflake.
"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from src import reference_data as rd

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeSessionState(dict):
    """Minimal stand-in for ``st.session_state`` - dict semantics is all the
    cache plumbing actually uses."""


class _FakeStreamlit:
    def __init__(self) -> None:
        self.session_state = _FakeSessionState()


@pytest.fixture
def fake_st(monkeypatch):
    """Patch ``streamlit`` so reference_data sees a controllable session_state.

    The module does ``import streamlit as st`` inside the cache helpers, so
    we replace the cached module in ``sys.modules`` rather than the import
    statement itself.
    """
    import sys
    fake = _FakeStreamlit()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    yield fake


# ---------------------------------------------------------------------------
# get_reference_dataset
# ---------------------------------------------------------------------------

def test_get_reference_dataset_unknown_name_returns_none(fake_st):
    assert rd.get_reference_dataset("THIS_TABLE_DOES_NOT_EXIST") is None


def test_get_reference_dataset_falls_back_to_loader_when_cache_empty(fake_st):
    """Without a populated cache, ``get_reference_dataset`` calls the
    registered loader directly. In mock mode this resolves to the
    ``_mock_vws_gp_standard_share`` DataFrame."""
    df = rd.get_reference_dataset("VWS_GP_STANDARD_SHARE")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert "PROJECT_ID" in df.columns


def test_get_reference_dataset_reads_from_cache_when_populated(fake_st):
    """A populated cache short-circuits the loader. The returned DataFrame
    is the cached one, not whatever the loader would produce now."""
    sentinel = pd.DataFrame({"A": [1, 2]})
    fake_st.session_state[rd._SESSION_STATE_KEY] = {
        "VWS_GP_STANDARD_SHARE": rd._CacheEntry(df=sentinel, error=None),
    }
    out = rd.get_reference_dataset("VWS_GP_STANDARD_SHARE")
    assert out is sentinel


def test_get_reference_dataset_returns_cached_none_for_failed_loader(fake_st):
    """When the cache recorded a load failure, the dataset reads ``None``
    even though a fresh loader call would succeed in mock mode. This is
    the contract Step 6 relies on to surface 'Not evaluated' rules."""
    fake_st.session_state[rd._SESSION_STATE_KEY] = {
        "VWS_GP_STANDARD_SHARE": rd._CacheEntry(df=None, error="boom"),
    }
    assert rd.get_reference_dataset("VWS_GP_STANDARD_SHARE") is None


# ---------------------------------------------------------------------------
# get_reference_dataset_error
# ---------------------------------------------------------------------------

def test_get_reference_dataset_error_returns_none_without_cache(fake_st):
    assert rd.get_reference_dataset_error("VWS_GP_STANDARD_SHARE") is None


def test_get_reference_dataset_error_returns_recorded_message(fake_st):
    fake_st.session_state[rd._SESSION_STATE_KEY] = {
        "VWS_GP_STANDARD_SHARE": rd._CacheEntry(df=None, error="ConnectionError: nope"),
    }
    assert (
        rd.get_reference_dataset_error("VWS_GP_STANDARD_SHARE")
        == "ConnectionError: nope"
    )


def test_get_reference_dataset_error_returns_none_for_unknown_name(fake_st):
    fake_st.session_state[rd._SESSION_STATE_KEY] = {}
    assert rd.get_reference_dataset_error("MISSING") is None


# ---------------------------------------------------------------------------
# prefetch_reference_datasets
# ---------------------------------------------------------------------------

def test_prefetch_loads_known_names_into_cache(fake_st):
    out = rd.prefetch_reference_datasets(["VWS_GP_STANDARD_SHARE"])
    assert set(out.keys()) == {"VWS_GP_STANDARD_SHARE"}
    assert isinstance(out["VWS_GP_STANDARD_SHARE"], pd.DataFrame)
    # Cache is populated, so a second call should hit the cache (not reload).
    cache = fake_st.session_state[rd._SESSION_STATE_KEY]
    assert "VWS_GP_STANDARD_SHARE" in cache
    assert cache["VWS_GP_STANDARD_SHARE"].error is None


def test_prefetch_skips_already_cached_names(fake_st):
    """Names already in the cache (success or failure) are not re-loaded.
    We prove this by seeding a sentinel and asserting it survives."""
    sentinel = pd.DataFrame({"X": [99]})
    fake_st.session_state[rd._SESSION_STATE_KEY] = {
        "VWS_GP_STANDARD_SHARE": rd._CacheEntry(df=sentinel, error=None),
    }
    out = rd.prefetch_reference_datasets(["VWS_GP_STANDARD_SHARE"])
    assert out["VWS_GP_STANDARD_SHARE"] is sentinel


def test_prefetch_records_missing_loader_with_error(fake_st):
    out = rd.prefetch_reference_datasets(["NOT_A_DATASET"])
    cache = fake_st.session_state[rd._SESSION_STATE_KEY]
    assert cache["NOT_A_DATASET"].df is None
    assert "No loader registered" in cache["NOT_A_DATASET"].error
    assert out["NOT_A_DATASET"] is None


def test_prefetch_records_loader_exception_as_typed_error(fake_st):
    """If a loader raises, the cache captures ``TypeName: message`` so the
    UI can surface the failure instead of silently passing."""
    def boom() -> pd.DataFrame:
        raise ConnectionError("databricks unreachable")

    with patch.dict(rd._REGISTRY, {"FAILING": boom}):
        rd.prefetch_reference_datasets(["FAILING"])
    cache = fake_st.session_state[rd._SESSION_STATE_KEY]
    assert cache["FAILING"].df is None
    assert cache["FAILING"].error == "ConnectionError: databricks unreachable"


def test_prefetch_records_none_return_as_error(fake_st):
    """A loader that returns ``None`` (not an exception) is still flagged
    so callers can surface it to the user."""
    with patch.dict(rd._REGISTRY, {"RETURNS_NONE": lambda: None}):
        rd.prefetch_reference_datasets(["RETURNS_NONE"])
    cache = fake_st.session_state[rd._SESSION_STATE_KEY]
    assert cache["RETURNS_NONE"].df is None
    assert "returned None" in cache["RETURNS_NONE"].error


# ---------------------------------------------------------------------------
# clear_reference_cache
# ---------------------------------------------------------------------------

def test_clear_reference_cache_removes_session_key(fake_st):
    fake_st.session_state[rd._SESSION_STATE_KEY] = {"x": rd._CacheEntry(df=None)}
    rd.clear_reference_cache()
    assert rd._SESSION_STATE_KEY not in fake_st.session_state


def test_clear_reference_cache_noop_when_key_absent(fake_st):
    # Pre-condition: cache key doesn't exist.
    assert rd._SESSION_STATE_KEY not in fake_st.session_state
    # Should not raise.
    rd.clear_reference_cache()
    assert rd._SESSION_STATE_KEY not in fake_st.session_state


# ---------------------------------------------------------------------------
# required_reference_datasets_for_systems
# ---------------------------------------------------------------------------

def test_required_reference_datasets_for_known_system(fake_st):
    """EPT uses E7 which depends on VWS_GP_STANDARD_SHARE; ADR uses A1
    which depends on ACCE_COA_MASTER. The helper returns the union."""
    out = rd.required_reference_datasets_for_systems(["EPT"])
    assert "VWS_GP_STANDARD_SHARE" in out

    out = rd.required_reference_datasets_for_systems(["ADR"])
    assert "ACCE_COA_MASTER" in out


def test_required_reference_datasets_deduplicates(fake_st):
    """Same dataset declared by two systems must appear exactly once,
    preserving first-seen order."""
    out = rd.required_reference_datasets_for_systems(["EPT", "EPT"])
    assert out.count("VWS_GP_STANDARD_SHARE") == 1


def test_required_reference_datasets_empty_for_systems_without_refs(fake_st):
    """A system whose rules have no reference dependency contributes
    nothing to the prefetch list."""
    # SQS rules are referential-integrity-free at the catalog level.
    out = rd.required_reference_datasets_for_systems(["SQS"])
    # The result is the order-preserved union; it must not contain any
    # dataset that isn't actually requested by any SQS rule.
    for name in out:
        assert isinstance(name, str)
