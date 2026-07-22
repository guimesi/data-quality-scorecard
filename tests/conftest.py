"""Shared pytest fixtures."""
import sys
from pathlib import Path

# Ensure project root is on sys.path so tests can import `config`, `src`, etc.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import pytest


@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", "PV-002", "PV-003", None, "PV-002"],  # nulls + dup
        "AMOUNT": [100.0, 200.0, -50.0, 9999999.0, 150.0],
        "CATEGORY": ["A", "B", "A", "X", None],
        "DATE_COL": pd.to_datetime([
            "2025-01-01", "2025-06-15", "2024-12-31", None, "2020-01-01",
        ]),
    })


@pytest.fixture(autouse=True)
def _force_mock_data_source(monkeypatch):
    """Pin SETTINGS.data_source to "mock" for every test, regardless of the
    developer's .env / shell DATA_SOURCE value. Without this, runs with
    ``DATA_SOURCE=snowflake`` exported re-route loaders (e.g. the E7 reference
    dataset, ``_default_fetcher``) through the real Snowflake client and
    cause spurious failures. Tests that need to exercise the snowflake
    branch (e.g. ``test_default_fetcher_snowflake_branch``) override SETTINGS
    on the specific module under test, which takes precedence inside the
    test's scope."""
    from config import settings as settings_mod

    mock_settings = settings_mod.Settings(data_source="mock")
    monkeypatch.setattr(settings_mod, "SETTINGS", mock_settings)
    for mod_path in (
        "src.data_product_builder",
        "src.persistence",
        "src.reference_data",
        "src.snowflake_client",
        "src.scorecard",
    ):
        mod = sys.modules.get(mod_path)
        if mod is not None and hasattr(mod, "SETTINGS"):
            monkeypatch.setattr(mod, "SETTINGS", mock_settings)


@pytest.fixture(autouse=True)
def _restore_reference_registry():
    """Snapshot ``src.reference_data._REGISTRY`` and restore it after each
    test. Some tests (notably the AppTest-driven prefetch / error tests)
    register temporary loaders to simulate Snowflake failures; without this
    fixture those loaders leak into subsequent tests and cause spurious
    failures (real bug we hit during development)."""
    from src import reference_data as ref_mod

    original = dict(ref_mod._REGISTRY)
    yield
    ref_mod._REGISTRY.clear()
    ref_mod._REGISTRY.update(original)
