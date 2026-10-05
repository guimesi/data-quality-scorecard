"""Tests for the failed rows (``src/failed_rows.py``, the Step 6 actions in
``ui/step_06/_failed_rows.py``) and the row-table side of
``src/persistence.py`` (``write_rows`` / ``save_failed_rows``)."""
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
                        store_dir=str(tmp_path))
    monkeypatch.setattr(pers, "SETTINGS", settings)
    monkeypatch.setattr(fr, "SETTINGS", settings)
    pers.reset_store()
    yield tmp_path
    pers.reset_store()


def _read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


# ==================================================================== frame

def test_frame_has_failing_rows_worst_first_with_rule_columns_only():
    dp, cfg = _dp(), _cfg()
    frame, total = fr.failed_rows_frame(dp, compute_scorecard(dp, cfg), cfg)
    assert total == 3 and len(frame) == 3            # r1 passes everything
    # Only the keys + CDEs travel - NOT_A_CDE stays out.
    assert list(frame.columns) == ["row_score", "failed_rules", "PLANVIEW_ID",
                                   "ROW_ID", "AMOUNT"]
    assert frame["row_score"].tolist() == [50.0, 50.0, 50.0]
    by_key = frame.set_index("ROW_ID")
    assert by_key.loc["r2", "failed_rules"] == ["PLANVIEW_ID::Completeness"]
    assert by_key.loc["r3", "failed_rules"] == ["AMOUNT::Completeness"]


def test_frame_cap_keeps_the_worst_rows_but_reports_the_full_count():
    dp, cfg = _dp(), _cfg()
    frame, total = fr.failed_rows_frame(dp, compute_scorecard(dp, cfg), cfg,
                                        max_rows=2)
    assert len(frame) == 2 and total == 3


def test_frame_includes_reference_columns(monkeypatch):
    dp, cfg = _dp(), _cfg()
    refs = pd.DataFrame({"OWNER [REF]": ["o1", "o2", "o3", "o4"]}, index=dp.df.index)
    import ui.step_06._export as export
    monkeypatch.setattr(export, "_reference_columns_for_export", lambda *a: refs)
    frame, _ = fr.failed_rows_frame(dp, compute_scorecard(dp, cfg), cfg)
    assert frame.set_index("ROW_ID").loc["r3", "OWNER [REF]"] == "o3"


def test_frame_is_empty_without_failures_or_rules():
    dp, cfg = _dp(), _cfg()
    dp.df = dp.df.iloc[[0]]
    frame, total = fr.failed_rows_frame(dp, compute_scorecard(dp, cfg), cfg)
    assert frame.empty and total == 0
    empty = DataProductConfig(system_code="EPT")
    frame, total = fr.failed_rows_frame(_dp(), compute_scorecard(_dp(), empty), empty)
    assert frame.empty and total == 0


# ================================================================== records

def test_records_carry_keys_score_rules_and_cde_data():
    dp, cfg = _dp(), _cfg()
    frame, _ = fr.failed_rows_frame(dp, compute_scorecard(dp, cfg), cfg)
    rows = {r["row_key"]: r for r in fr.frame_to_records(frame)}
    assert set(rows) == {"r2", "r3", "r4"}
    assert rows["r2"]["planview_id"] is None and rows["r3"]["planview_id"] == "PV-3"
    assert rows["r3"]["row_score"] == 50.0
    assert rows["r3"]["failed_rules"] == ["AMOUNT::Completeness"]
    # row_data: the CDE / reference columns only, NaN -> null.
    assert rows["r3"]["row_data"] == {"AMOUNT": None}
    assert rows["r2"]["row_data"] == {"AMOUNT": 20.0}


def test_records_without_row_id_use_the_row_position():
    dp, cfg = _dp(), _cfg()
    dp.df = dp.df.drop(columns=["ROW_ID"])
    frame, _ = fr.failed_rows_frame(dp, compute_scorecard(dp, cfg), cfg)
    assert sorted(r["row_key"] for r in fr.frame_to_records(frame)) == ["1", "2", "3"]
    assert fr.frame_to_records(pd.DataFrame()) == []


# ===================================================================== save

def test_save_replaces_the_previous_run(local_store):
    dp, cfg = _dp(), _cfg()
    result = compute_scorecard(dp, cfg)
    assert fr.save_failed_rows_for_run("cost_estimate", "EPT", dp, result, cfg,
                                       run_id="snap_a") == (3, 3)
    path = local_store / "dqs_fails_cost_estimate_ept.jsonl"
    assert {r["run_id"] for r in _read(path)} == {"snap_a"}
    dp.df = dp.df.iloc[[0, 1]]
    result = compute_scorecard(dp, cfg)
    assert fr.save_failed_rows_for_run("cost_estimate", "EPT", dp, result, cfg,
                                       run_id="snap_b") == (1, 1)
    stored = _read(path)
    assert len(stored) == 1 and stored[0]["run_id"] == "snap_b"
    assert stored[0]["total_failed_rows"] == 1 and stored[0]["dp_code"] == "EPT"


def test_save_uses_the_recorded_run_id_when_the_result_matches(local_store):
    dp, cfg = _dp(), _cfg()
    result = compute_scorecard(dp, cfg)
    assert rh.record_run_if_new("EPT", dp, result, cfg, "cost_estimate")
    run_id = pers.list_runs("EPT")[-1]["payload"]["id"]
    assert fr.current_run_id("EPT", result) == run_id
    fr.save_failed_rows_for_run("cost_estimate", "EPT", dp, result, cfg)
    stored = _read(local_store / "dqs_fails_cost_estimate_ept.jsonl")
    assert {r["run_id"] for r in stored} == {run_id}
    # A result that was never recorded gets an "unrecorded" id.
    dp.df = dp.df.iloc[[0, 1]]
    assert fr.current_run_id("EPT", compute_scorecard(dp, cfg)).startswith(
        "unrecorded_")


def test_save_raises_when_the_store_rejects_the_write(local_store, monkeypatch):
    dp, cfg = _dp(), _cfg()
    monkeypatch.setattr(fr, "save_failed_rows", lambda *a, **k: False)
    with pytest.raises(RuntimeError, match="Could not write"):
        fr.save_failed_rows_for_run("cost_estimate", "EPT", dp,
                                    compute_scorecard(dp, cfg), cfg, run_id="x")


def test_recording_a_run_does_not_write_failed_rows(local_store):
    """Saving failed rows is explicit (button / job), never a side effect
    of a dashboard render."""
    dp, cfg = _dp(), _cfg()
    assert rh.record_run_if_new("EPT", dp, compute_scorecard(dp, cfg), cfg,
                                "cost_estimate") is True
    assert not list(local_store.glob("dqs_fails_*"))


def test_table_name_is_per_domain_and_data_product():
    assert pers.fails_table_name("cost_estimate", "ADR") == "DQS_FAILS_COST_ESTIMATE_ADR"
    assert pers.fails_table_name("quality", "SQS") == "DQS_FAILS_QUALITY_SQS"
    assert pers.fails_table_name("a;b", "x y") == "DQS_FAILS_A_B_X_Y"   # [A-Z0-9_] only


# =============================================================== databricks

def _dbx_store(monkeypatch, chunk_chars=900000):
    monkeypatch.setattr(pers, "SETTINGS", Settings(
        data_source="databricks", persistence_backend="databricks",
        dbx_catalog="APPCAT", dbx_schema="APPSCHEMA", dbx_state_schema="",
        fails_chunk_chars=chunk_chars,
    ))
    client = MagicMock()
    store = pers.DatabricksStore()
    monkeypatch.setattr(store, "_client", lambda: client)
    return store, client


def test_databricks_replace_empties_the_table_then_inserts_in_chunks(monkeypatch):
    """Chunks are cut by parameter size (Databricks caps one statement's
    parameters at 1 MiB): with a limit that fits two rows, three rows take
    two INSERTs, and the caller is told the progress after each."""
    store, client = _dbx_store(monkeypatch)
    header = {"run_id": "snap_1", "ts": "t", "username": "u",
              "domain_code": "quality", "dp_code": "SQS", "config_hash": "h",
              "total_failed_rows": 3}
    rows = [{"planview_id": "PV", "row_key": str(i), "row_score": 50.0,
             "failed_rules": ["R1"], "row_data": {"A": i}} for i in range(3)]
    one_row = len(json.dumps(rows[0], separators=(",", ":"))) + 40
    monkeypatch.setattr(pers, "SETTINGS", Settings(
        data_source="databricks", persistence_backend="databricks",
        dbx_catalog="APPCAT", dbx_schema="APPSCHEMA",
        fails_chunk_chars=2 * one_row + 1))
    progress = []
    store.write_rows("DQS_FAILS_QUALITY_SQS", header, rows,
                     pers._FAILS_ROW_STRUCT, replace=True,
                     progress=lambda d, t: progress.append((d, t)))

    statements = [c[0] for c in client.execute.call_args_list]
    assert statements[0] == ("DELETE FROM APPCAT.APPSCHEMA.DQS_FAILS_QUALITY_SQS",)
    assert len(statements) == 3                        # delete + 2 chunks
    assert progress == [(2, 3), (3, 3)]
    for _, values in statements[1:]:
        assert len(values[7]) <= 2 * one_row + 1       # never above the limit
    sql, values = statements[1]
    assert "INSERT INTO APPCAT.APPSCHEMA.DQS_FAILS_QUALITY_SQS" in sql
    assert "explode(from_json(%s, 'array<struct<planview_id:string," in sql
    assert sql.count("%s") == len(values) == 8         # 7 header cols + rows
    assert values[:7] == ["snap_1", "t", "u", "quality", "SQS", "h", 3]
    chunk = json.loads(values[7])
    assert [r["row_key"] for r in chunk] == ["0", "1"]
    # Nested values travel as JSON strings (STRING columns).
    assert json.loads(chunk[1]["failed_rules"]) == ["R1"]
    assert json.loads(chunk[1]["row_data"]) == {"A": 1}


def test_databricks_append_does_not_delete(monkeypatch):
    store, client = _dbx_store(monkeypatch)
    store.write_rows("DQS_RULE_SCORES", {"run_id": "s", "ts": "t"},
                     [{"rule_id": "R1", "score": 1.0}],
                     {"rule_id": "string", "score": "double"})
    (sql, values), = [c[0] for c in client.execute.call_args_list]
    assert sql.startswith("INSERT INTO APPCAT.APPSCHEMA.DQS_RULE_SCORES (RUN_ID, TS, RULE_ID, SCORE)")
    assert json.loads(values[2]) == [{"rule_id": "R1", "score": 1.0}]


def test_save_failed_rows_is_fire_and_forget(local_store, monkeypatch):
    store = MagicMock()
    store.write_rows.side_effect = RuntimeError("warehouse down")
    monkeypatch.setattr(pers, "get_store", lambda: store)
    assert pers.save_failed_rows("quality", "SQS", "snap", [{"row_key": "1"}], 1) is False
    # An empty run still replaces (clears) the table.
    store.write_rows.side_effect = None
    assert pers.save_failed_rows("quality", "SQS", "snap", [], 0) is True
    assert store.write_rows.call_args[1]["replace"] is True


# ======================================================================= UI

def test_csv_download_builds_the_failed_rows_on_click():
    import ui.step_06._failed_rows as ui_fr

    dp, cfg = _dp(), _cfg()
    data = ui_fr._failed_rows_csv(dp, compute_scorecard(dp, cfg), cfg)
    text = data.decode("utf-8-sig")
    lines = text.split("\r\n")
    assert lines[0] == "row_score,failed_rules,PLANVIEW_ID,ROW_ID,AMOUNT"
    assert len([ln for ln in lines if ln]) == 4            # header + 3 rows
    assert '"[""PLANVIEW_ID::Completeness""]"' in text
    empty = DataProductConfig(system_code="EPT")
    assert ui_fr._failed_rows_csv(_dp(), compute_scorecard(_dp(), empty),
                                  empty) == b"row_score,failed_rules\r\n"


def test_save_button_reports_rows_and_logs(local_store, monkeypatch):
    import ui.step_06._failed_rows as ui_fr

    dp, cfg = _dp(), _cfg()
    result = compute_scorecard(dp, cfg)
    fake_st = MagicMock()
    fake_st.session_state = {"domain": "cost_estimate"}
    fake_st.button.return_value = True
    fake_st.download_button.return_value = False
    fake_st.columns.return_value = (MagicMock(), MagicMock())
    events = []
    monkeypatch.setattr(ui_fr, "st", fake_st)
    monkeypatch.setattr(ui_fr, "SETTINGS", pers.SETTINGS)
    monkeypatch.setattr(ui_fr, "log_event", lambda *a, **k: events.append(a))
    ui_fr._render_failed_rows_actions("EPT", dp, result, cfg)
    # Both buttons "clicked": the CSV is built and offered, the save runs.
    fake_st.success.assert_called_once()
    assert "3 failed row(s) saved" in fake_st.success.call_args[0][0]
    assert [e[1]["format"] for e in events] == ["failed_rows_csv",
                                                 "failed_rows_table"]
    stored = _read(local_store / "dqs_fails_cost_estimate_ept.jsonl")
    assert len(stored) == 3
    fake_st.download_button.assert_called_once()
    assert fake_st.download_button.call_args[1]["data"].startswith(
        b"\xef\xbb\xbfrow_score,failed_rules")
    # The frame was collected once and shared by the two actions.
    assert fake_st.spinner.call_count == 1


def test_save_button_failure_is_an_inline_error(local_store, monkeypatch):
    import ui.step_06._failed_rows as ui_fr

    dp, cfg = _dp(), _cfg()
    fake_st = MagicMock()
    fake_st.session_state = {"domain": "cost_estimate"}
    fake_st.button.return_value = True
    fake_st.download_button.return_value = False
    fake_st.columns.return_value = (MagicMock(), MagicMock())
    monkeypatch.setattr(ui_fr, "st", fake_st)
    monkeypatch.setattr(ui_fr, "SETTINGS", pers.SETTINGS)
    monkeypatch.setattr(fr, "save_failed_rows", lambda *a, **k: False)
    ui_fr._render_failed_rows_actions("EPT", dp, compute_scorecard(dp, cfg), cfg)
    fake_st.error.assert_called_once()
    fake_st.success.assert_not_called()
