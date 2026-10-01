"""Tests for the failed-rows store (``src/failed_rows.py`` + the
``DQS_FAILS_*`` side of ``src/persistence.py``)."""
from __future__ import annotations

import os

os.environ.setdefault("DATA_SOURCE", "mock")

import json
from unittest.mock import MagicMock

import pandas as pd
import pytest

import src.failed_rows as fr
import src.persistence as pers
import src.run_history as rh
from config.settings import Settings
from src.models import DataProduct, DataProductConfig, DQRAssignment
from src.scorecard import compute_scorecard


def _dp() -> DataProduct:
    df = pd.DataFrame({
        "ROW_ID": ["r1", "r2", "r3", "r4"],
        "PLANVIEW_ID": ["PV-1", None, "PV-3", "PV-4"],
        "AMOUNT": [10.0, 20.0, None, None],
        "NOT_A_CDE": ["x", "y", "z", "w"],
    })
    return DataProduct("EPT", "EPT_DATA_PRODUCT", df, ["T"])


def _cfg() -> DataProductConfig:
    return DataProductConfig(
        system_code="EPT", cdes=["PLANVIEW_ID", "AMOUNT"],
        assignments=[
            DQRAssignment("PLANVIEW_ID", "Completeness", weight=50),
            DQRAssignment("AMOUNT", "Completeness", weight=50),
        ],
    )


@pytest.fixture
def local_store(tmp_path, monkeypatch):
    settings = Settings(data_source="mock", persistence_backend="local",
                        store_dir=str(tmp_path), fails_max_rows=100)
    monkeypatch.setattr(pers, "SETTINGS", settings)
    monkeypatch.setattr(fr, "SETTINGS", settings)
    pers.reset_store()
    yield tmp_path
    pers.reset_store()


def _read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


# ================================================================== collect

def test_collect_returns_failing_rows_worst_first():
    dp, cfg = _dp(), _cfg()
    rows, total = fr.collect_failed_rows(dp, compute_scorecard(dp, cfg), cfg, 100)
    assert total == 3                                 # r1 passes everything
    assert {r["row_key"] for r in rows} == {"r2", "r3", "r4"}
    assert [r["row_score"] for r in rows] == [50.0, 50.0, 50.0]
    by_key = {r["row_key"]: r for r in rows}
    assert by_key["r2"]["failed_rules"] == ["PLANVIEW_ID::Completeness"]
    assert by_key["r3"]["failed_rules"] == ["AMOUNT::Completeness"]
    assert by_key["r2"]["planview_id"] is None
    assert by_key["r3"]["planview_id"] == "PV-3"
    # Only CDE columns travel; NaN becomes null.
    assert by_key["r3"]["row_data"] == {"PLANVIEW_ID": "PV-3", "AMOUNT": None}


def test_collect_caps_rows_but_reports_the_full_count():
    dp, cfg = _dp(), _cfg()
    rows, total = fr.collect_failed_rows(dp, compute_scorecard(dp, cfg), cfg, 2)
    assert len(rows) == 2 and total == 3


def test_collect_without_row_id_uses_the_row_position():
    dp, cfg = _dp(), _cfg()
    dp.df = dp.df.drop(columns=["ROW_ID"])
    rows, _ = fr.collect_failed_rows(dp, compute_scorecard(dp, cfg), cfg, 100)
    assert sorted(r["row_key"] for r in rows) == ["1", "2", "3"]


def test_collect_with_no_failures_or_no_rules_is_empty():
    dp, cfg = _dp(), _cfg()
    dp.df = dp.df.iloc[[0]]
    assert fr.collect_failed_rows(dp, compute_scorecard(dp, cfg), cfg, 100) == ([], 0)
    empty = DataProductConfig(system_code="EPT")
    assert fr.collect_failed_rows(_dp(), compute_scorecard(_dp(), empty),
                                  empty, 100) == ([], 0)


# ================================================================== record

def test_table_name_is_per_domain_and_data_product():
    assert pers.fails_table_name("cost_estimate", "ADR") == "DQS_FAILS_COST_ESTIMATE_ADR"
    assert pers.fails_table_name("quality", "SQS") == "DQS_FAILS_QUALITY_SQS"
    # Never anything but [A-Z0-9_] in the identifier.
    assert pers.fails_table_name("a;b", "x y") == "DQS_FAILS_A_B_X_Y"


def test_recording_a_run_stores_its_failed_rows(local_store):
    dp, cfg = _dp(), _cfg()
    result = compute_scorecard(dp, cfg)
    assert rh.record_run_if_new("EPT", dp, result, cfg, "cost_estimate") is True
    run = pers.list_runs("EPT")[-1]
    stored = _read(local_store / "dqs_fails_cost_estimate_ept.jsonl")
    assert len(stored) == 3
    assert {r["run_id"] for r in stored} == {run["payload"]["id"]}
    assert all(r["total_failed_rows"] == 3 and r["dp_code"] == "EPT"
               and r["domain_code"] == "cost_estimate"
               and r["config_hash"] == run["config_hash"] for r in stored)
    # A deduplicated rerun records neither a run nor more failed rows.
    assert rh.record_run_if_new("EPT", dp, result, cfg, "cost_estimate") is False
    assert len(_read(local_store / "dqs_fails_cost_estimate_ept.jsonl")) == 3


def test_feature_off_or_no_domain_stores_nothing(local_store, monkeypatch):
    dp, cfg = _dp(), _cfg()
    result = compute_scorecard(dp, cfg)
    assert fr.record_failed_rows("snap", "EPT", "", dp, result, cfg) is False
    monkeypatch.setattr(fr, "SETTINGS", Settings(data_source="mock"))  # default: off
    assert fr.record_failed_rows("snap", "EPT", "cost_estimate", dp, result, cfg) is False
    assert not list(local_store.glob("dqs_fails_*"))


def test_failed_rows_error_never_blocks_the_run_record(local_store, monkeypatch):
    dp, cfg = _dp(), _cfg()

    def boom(*a, **k):
        raise RuntimeError("rule engine exploded")

    monkeypatch.setattr(fr, "collect_failed_rows", boom)
    assert rh.record_run_if_new("EPT", dp, compute_scorecard(dp, cfg), cfg,
                                "cost_estimate") is True
    assert len(pers.list_runs("EPT")) == 1


# =============================================================== databricks

def test_databricks_store_inserts_chunks_as_one_json_parameter(monkeypatch):
    monkeypatch.setattr(pers, "SETTINGS", Settings(
        data_source="databricks", persistence_backend="databricks",
        dbx_catalog="APPCAT", dbx_schema="APPSCHEMA", dbx_state_schema="",
    ))
    monkeypatch.setattr(pers, "_FAILS_CHUNK_ROWS", 2)
    client = MagicMock()
    store = pers.DatabricksStore()
    monkeypatch.setattr(store, "_client", lambda: client)
    header = {"run_id": "snap_1", "ts": "t", "username": "u",
              "domain_code": "quality", "dp_code": "SQS", "config_hash": "h",
              "total_failed_rows": 3}
    rows = [{"planview_id": "PV", "row_key": str(i), "row_score": 50.0,
             "failed_rules": ["R1"], "row_data": {"A": i}} for i in range(3)]
    store.append_failed_rows("DQS_FAILS_QUALITY_SQS", header, rows)

    assert client.execute.call_count == 2             # chunks of 2 + 1
    sql, values = client.execute.call_args_list[0][0]
    assert "INSERT INTO APPCAT.APPSCHEMA.DQS_FAILS_QUALITY_SQS" in sql
    assert "explode(from_json(%s," in sql
    assert sql.count("%s") == len(values) == 8        # 7 run columns + rows
    assert values[:7] == ["snap_1", "t", "u", "quality", "SQS", "h", 3]
    chunk = json.loads(values[7])
    assert [r["row_key"] for r in chunk] == ["0", "1"]
    # Nested values travel as JSON strings (STRING columns).
    assert json.loads(chunk[1]["failed_rules"]) == ["R1"]
    assert json.loads(chunk[1]["row_data"]) == {"A": 1}


def test_save_failed_rows_is_fire_and_forget(local_store, monkeypatch):
    assert pers.save_failed_rows("quality", "SQS", "snap", [], 0) is True
    store = MagicMock()
    store.append_failed_rows.side_effect = RuntimeError("warehouse down")
    monkeypatch.setattr(pers, "get_store", lambda: store)
    assert pers.save_failed_rows("quality", "SQS", "snap", [{"row_key": "1"}], 1) is False
