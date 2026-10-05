"""Tests for the per-rule score history (``src/rule_scores.py`` and the
``save_rule_scores`` side of ``src/persistence.py``)."""
from __future__ import annotations

import os

os.environ.setdefault("DATA_SOURCE", "mock")

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

import src.persistence as pers
import src.rule_scores as rs
import src.run_history as rh
from config.settings import Settings
from src.models import (
    CustomDQRAssignment,
    DataProduct,
    DataProductConfig,
    DQRAssignment,
)
from src.scorecard import compute_scorecard


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    settings = Settings(data_source="mock", persistence_backend="local",
                        store_dir=str(tmp_path))
    monkeypatch.setattr(pers, "SETTINGS", settings)
    pers.reset_store()
    yield tmp_path
    pers.reset_store()


def _result(standard=None, custom=None):
    return SimpleNamespace(rule_pass_rates=standard or {},
                           custom_rule_pass_rates=custom or {})


def test_rows_for_standard_and_custom_rules():
    rows = rs.rule_score_rows("ADR", _result(
        standard={"PLANVIEW_ID::Completeness": 91.23456},
        custom={"DQ-ADR-1": 83.3, "not-in-catalog": 10.0},
    ))
    assert rows[0] == {
        "rule_id": "PLANVIEW_ID::Completeness", "rule_type": "Standard",
        "rule_name": "Completeness", "cde": "PLANVIEW_ID",
        "dimension": "Completeness", "score": 91.2346,
    }
    custom = {r["rule_id"]: r for r in rows[1:]}
    assert custom["DQ-ADR-1"]["rule_type"] == "Custom"
    assert custom["DQ-ADR-1"]["rule_name"]            # from the catalog
    assert custom["DQ-ADR-1"]["dimension"]            # the rule's type
    assert custom["DQ-ADR-1"]["cde"] is None
    assert custom["not-in-catalog"]["rule_name"] == ""


def test_recording_a_run_appends_its_rule_scores(local_store):
    df = pd.DataFrame({"PLANVIEW_ID": ["a", None], "AMOUNT": [1.0, 2.0]})
    dp = DataProduct("EPT", "EPT", df, ["T"])
    cfg = DataProductConfig(
        system_code="EPT", cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100)],
    )
    assert rh.record_run_if_new("EPT", dp, compute_scorecard(dp, cfg), cfg, "d")
    run_id = pers.list_runs("EPT")[-1]["payload"]["id"]
    stored = [json.loads(ln) for ln in
              (local_store / "dqs_rule_scores.jsonl").read_text().splitlines()]
    assert len(stored) == 1
    assert stored[0]["run_id"] == run_id and stored[0]["dp_code"] == "EPT"
    assert stored[0]["rule_id"] == "PLANVIEW_ID::Completeness"
    assert stored[0]["score"] == 50.0
    # Identical rerun: no new run, no new history rows.
    assert rh.record_run_if_new("EPT", dp, compute_scorecard(dp, cfg), cfg, "d") is False
    assert len((local_store / "dqs_rule_scores.jsonl").read_text().splitlines()) == 1


def test_custom_rule_rows_reach_the_store(local_store):
    from src.custom_dqr._dispatcher import evaluate_custom_rules  # noqa: F401

    df = pd.DataFrame({"PLANVIEW_ID": ["a"], "COMPLETE_WBC": ["1.2"]})
    dp = DataProduct("ADR", "ADR", df, ["T"])
    cfg = DataProductConfig(
        system_code="ADR", cdes=["COMPLETE_WBC"], dqr_sources=["custom"],
        custom_assignments=[CustomDQRAssignment("DQ-ADR-1", weight=100)],
    )
    result = compute_scorecard(dp, cfg)
    if not result.custom_rule_pass_rates:
        pytest.skip("DQ-ADR-1 could not be evaluated on this fixture")
    assert rs.record_rule_scores("snap_x", "ADR", "d", result, "h") is True
    stored = [json.loads(ln) for ln in
              (local_store / "dqs_rule_scores.jsonl").read_text().splitlines()]
    assert stored[0]["rule_id"] == "DQ-ADR-1" and stored[0]["rule_type"] == "Custom"


def test_rule_scores_are_fire_and_forget(local_store, monkeypatch):
    store = MagicMock()
    store.write_rows.side_effect = RuntimeError("down")
    monkeypatch.setattr(pers, "get_store", lambda: store)
    assert rs.record_rule_scores("s", "EPT", "d", _result(
        standard={"A::Completeness": 1.0})) is False
    assert pers.save_rule_scores("d", "EPT", "s", []) is True   # nothing to write
    monkeypatch.setattr(rs, "rule_score_rows", MagicMock(side_effect=ValueError))
    assert rs.record_rule_scores("s", "EPT", "d", _result()) is False
