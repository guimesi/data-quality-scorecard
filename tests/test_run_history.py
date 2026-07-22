"""Tests for the run-history service (src/run_history.py) and the Step 6
history UI helpers (ui/step_06/_history.py) - phase 1.

The persistence store is already isolated per test by conftest's autouse
fixture (tmp-dir LocalStore + singleton reset), so these tests exercise
the real read/write path end-to-end.
"""
from __future__ import annotations

import os

# Force mock mode before importing anything that reads settings.
os.environ.setdefault("DATA_SOURCE", "mock")

from unittest.mock import MagicMock

import pandas as pd

import src.run_history as rh
import ui.step_06._history as hist
from src.models import (
    CustomDQRAssignment,
    DataProduct,
    DataProductConfig,
    DQRAssignment,
)
from src.persistence import save_run
from src.profiler import profile_dataframe
from src.scorecard import compute_scorecard


def _ept_dp(df: pd.DataFrame) -> DataProduct:
    return DataProduct(
        system_code="EPT", name="EPT", df=df,
        source_tables=["T"], profiles=profile_dataframe(df),
    )


def _df(fail_rows: int = 1) -> pd.DataFrame:
    ids = ["PV-001", "PV-002", "PV-003", "PV-004"]
    return pd.DataFrame({
        "PLANVIEW_ID": [None] * fail_rows + ids[fail_rows:],
        "CODE_OF_RESOURCE": ["LOC-A", "LOC-B", "LOC-C", "LOC-D"],
    })


def _cfg(weight: float = 100.0) -> DataProductConfig:
    return DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=weight)],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )


def _result(df: pd.DataFrame, cfg: DataProductConfig):
    return compute_scorecard(_ept_dp(df), cfg,
                             threshold_green=90, threshold_yellow=70)


# ============================================================== fingerprints

def test_config_fingerprint_ignores_assignment_order():
    a = DQRAssignment("A", "Completeness", weight=50.0)
    b = DQRAssignment("B", "Uniqueness", weight=50.0)
    cfg1 = DataProductConfig(system_code="EPT", cdes=["A", "B"],
                             assignments=[a, b])
    cfg2 = DataProductConfig(system_code="EPT", cdes=["B", "A"],
                             assignments=[b, a])
    assert rh.config_fingerprint(cfg1) == rh.config_fingerprint(cfg2)


def test_config_fingerprint_changes_on_weight_param_and_custom_changes():
    base = rh.config_fingerprint(_cfg())
    assert rh.config_fingerprint(_cfg(weight=60.0)) != base

    with_params = _cfg()
    with_params.assignments[0].params = {"op": ">="}
    assert rh.config_fingerprint(with_params) != base

    with_custom = _cfg()
    with_custom.custom_assignments = [CustomDQRAssignment(rule_id="E1", weight=100.0)]
    assert rh.config_fingerprint(with_custom) != base


def test_result_fingerprint_tracks_outcome():
    cfg = _cfg()
    r1 = _result(_df(fail_rows=1), cfg)
    r1_again = _result(_df(fail_rows=1), cfg)
    r2 = _result(_df(fail_rows=2), cfg)
    assert rh.result_fingerprint(r1) == rh.result_fingerprint(r1_again)
    assert rh.result_fingerprint(r1) != rh.result_fingerprint(r2)


# ================================================================= recording

def test_record_run_if_new_records_once_per_identical_run():
    cfg = _cfg()
    df = _df()
    dp, result = _ept_dp(df), _result(df, cfg)
    assert rh.record_run_if_new("EPT", dp, result, cfg, "cost_estimate") is True
    assert rh.record_run_if_new("EPT", dp, result, cfg, "cost_estimate") is False
    (run,) = rh.load_history("EPT")
    assert run["config_hash"] == rh.config_fingerprint(cfg)
    assert run["payload"]["source"] == "auto"
    assert run["payload"]["result_fingerprint"] == rh.result_fingerprint(result)
    assert run["payload"]["overall_score"] == result.overall_score


def test_record_run_if_new_records_on_data_change():
    cfg = _cfg()
    df1, df2 = _df(fail_rows=1), _df(fail_rows=2)
    assert rh.record_run_if_new("EPT", _ept_dp(df1), _result(df1, cfg), cfg)
    assert rh.record_run_if_new("EPT", _ept_dp(df2), _result(df2, cfg), cfg)
    assert len(rh.load_history("EPT")) == 2


def test_record_run_if_new_records_on_config_change():
    df = _df()
    dp = _ept_dp(df)
    cfg1, cfg2 = _cfg(), _cfg(weight=60.0)
    assert rh.record_run_if_new("EPT", dp, _result(df, cfg1), cfg1)
    assert rh.record_run_if_new("EPT", dp, _result(df, cfg2), cfg2)
    history = rh.load_history("EPT")
    assert len(history) == 2
    assert history[0]["config_hash"] != history[1]["config_hash"]


def test_load_history_none_returns_every_dp():
    cfg = _cfg()
    df = _df()
    rh.record_run_if_new("EPT", _ept_dp(df), _result(df, cfg), cfg)
    save_run("ADR", "d", {"overall_score": 50.0})
    assert len(rh.load_history(None)) == 2
    assert len(rh.load_history("EPT")) == 1


# ================================================================ score_drop

def _seed_run(dp_code: str, score: float, config_hash: str) -> None:
    save_run(dp_code, "d", {"overall_score": score}, config_hash=config_hash)


def test_score_drop_requires_two_runs():
    assert rh.score_drop([]) is None
    _seed_run("EPT", 90.0, "h1")
    assert rh.score_drop(rh.load_history("EPT")) is None


def test_score_drop_reports_delta_and_config_change():
    _seed_run("EPT", 90.0, "h1")
    _seed_run("EPT", 82.5, "h1")
    drop = rh.score_drop(rh.load_history("EPT"))
    assert drop["delta"] == -7.5
    assert drop["prev_score"] == 90.0
    assert drop["curr_score"] == 82.5
    assert drop["config_changed"] is False
    assert drop["prev_username"]

    _seed_run("EPT", 95.0, "h2")
    drop2 = rh.score_drop(rh.load_history("EPT"))
    assert drop2["delta"] == 12.5
    assert drop2["config_changed"] is True


# ========================================================== Step 6 UI helpers

class _FakeSessionState(dict):
    """Minimal stand-in supporting both dict and attribute access."""
    __getattr__ = dict.__getitem__


def _fake_st(session: _FakeSessionState) -> MagicMock:
    fake = MagicMock()
    fake.session_state = session
    fake.columns.side_effect = lambda n, **kw: [
        MagicMock() for _ in range(n if isinstance(n, int) else len(n))
    ]
    return fake


def test_record_runs_records_and_caches_per_session(monkeypatch):
    cfg = _cfg()
    df = _df()
    dp, result = _ept_dp(df), _result(df, cfg)
    session = _FakeSessionState(
        domain="cost_estimate", data_products={"EPT": dp}, configs={"EPT": cfg},
    )
    monkeypatch.setattr(hist, "st", _fake_st(session))
    hist._record_runs({"EPT": result})
    hist._record_runs({"EPT": result})   # session-cached: no second store hit
    assert len(rh.load_history("EPT")) == 1
    assert session[hist._RECORD_CACHE_KEY]["EPT"] == (
        rh.config_fingerprint(cfg), rh.result_fingerprint(result),
    )


def test_record_runs_skips_dp_missing_from_session(monkeypatch):
    session = _FakeSessionState(domain="", data_products={}, configs={})
    monkeypatch.setattr(hist, "st", _fake_st(session))
    hist._record_runs({"EPT": MagicMock()})
    assert rh.load_history("EPT") == []


def test_drop_alert_fires_beyond_threshold(monkeypatch):
    _seed_run("EPT", 90.0, "h1")
    _seed_run("EPT", 80.0, "h1")   # -10 pp >= default 5 pp threshold
    fake = _fake_st(_FakeSessionState())
    monkeypatch.setattr(hist, "st", fake)
    hist._render_drop_alert("EPT")
    message = fake.error.call_args[0][0]
    assert "10.0 pp" in message
    assert "configuration also changed" not in message


def test_drop_alert_mentions_config_change(monkeypatch):
    _seed_run("EPT", 90.0, "h1")
    _seed_run("EPT", 80.0, "h2")
    fake = _fake_st(_FakeSessionState())
    monkeypatch.setattr(hist, "st", fake)
    hist._render_drop_alert("EPT")
    assert "configuration also changed" in fake.error.call_args[0][0]


def test_drop_alert_silent_on_small_drop_or_no_history(monkeypatch):
    fake = _fake_st(_FakeSessionState())
    monkeypatch.setattr(hist, "st", fake)
    hist._render_drop_alert("EPT")            # no history
    _seed_run("EPT", 90.0, "h1")
    _seed_run("EPT", 88.0, "h1")              # -2 pp < threshold
    hist._render_drop_alert("EPT")
    fake.error.assert_not_called()


def _snapshot_payload(score: float) -> dict:
    return {
        "overall_score": score,
        "rule_pass_rates": {"PLANVIEW_ID::Completeness": score},
        "custom_rule_pass_rates": {},
        "cde_scores": {"PLANVIEW_ID": score},
        "dimension_scores": {"Completeness": score},
        "row_score_hist": None,
    }


def test_history_tab_empty_state(monkeypatch):
    fake = _fake_st(_FakeSessionState())
    monkeypatch.setattr(hist, "st", fake)
    hist._render_history_tab("EPT")
    fake.caption.assert_called_once()
    fake.plotly_chart.assert_not_called()


def test_history_tab_renders_trend_log_and_drift(monkeypatch):
    save_run("EPT", "d", _snapshot_payload(90.0), config_hash="h1")
    save_run("EPT", "d", _snapshot_payload(80.0), config_hash="h2")
    fake = _fake_st(_FakeSessionState())
    monkeypatch.setattr(hist, "st", fake)
    hist._render_history_tab("EPT")
    fake.plotly_chart.assert_called_once()
    # Run log: newest first, with the config-change marker on the second run.
    log = fake.dataframe.call_args_list[0][0][0]
    assert list(log["Score"]) == [80.0, 90.0]
    assert list(log["Config changed"]) == ["yes", ""]
    # Drift section rendered: -10 pp moves are flagged in every scope.
    flagged_tables = fake.dataframe.call_args_list[1:]
    assert flagged_tables, "expected flagged drift tables for a 10 pp move"


def test_history_tab_drift_skips_unflagged_scopes(monkeypatch):
    """Only the scopes that actually moved >= 5 pp render a table (a rule
    move with stable CDE/dimension scores must not render empty tables)."""
    a = _snapshot_payload(90.0)
    b = _snapshot_payload(90.0)
    b["rule_pass_rates"] = {"PLANVIEW_ID::Completeness": 80.0}
    save_run("EPT", "d", a, config_hash="h1")
    save_run("EPT", "d", b, config_hash="h1")
    fake = _fake_st(_FakeSessionState())
    monkeypatch.setattr(hist, "st", fake)
    hist._render_history_tab("EPT")
    # run log + exactly one flagged table (rules), none for CDE/dimension.
    assert len(fake.dataframe.call_args_list) == 2


def test_history_tab_drift_nothing_flagged(monkeypatch):
    a = _snapshot_payload(90.0)
    b = _snapshot_payload(88.0)   # -2 pp everywhere: below the 5 pp flag
    save_run("EPT", "d", a, config_hash="h1")
    save_run("EPT", "d", b, config_hash="h1")
    fake = _fake_st(_FakeSessionState())
    monkeypatch.setattr(hist, "st", fake)
    hist._render_history_tab("EPT")
    assert len(fake.dataframe.call_args_list) == 1   # run log only
    captions = " ".join(str(c[0][0]) for c in fake.caption.call_args_list)
    assert "Nothing moved" in captions


def test_history_tab_single_run_skips_drift(monkeypatch):
    save_run("EPT", "d", _snapshot_payload(90.0), config_hash="h1")
    fake = _fake_st(_FakeSessionState())
    monkeypatch.setattr(hist, "st", fake)
    hist._render_history_tab("EPT")
    fake.plotly_chart.assert_called_once()
    assert len(fake.dataframe.call_args_list) == 1   # run log only, no drift


# ======================================================== ML Lab integration

def test_ml_lab_persisted_snapshots_carry_provenance():
    import ui.step_07._run_history as s7rh
    save_run("EPT", "d", {"id": "snap_x_EPT", "overall_score": 77.0},
             config_hash="h1")
    (snap,) = s7rh._persisted_snapshots()
    assert snap["overall_score"] == 77.0
    assert snap["source"] == "auto"
    assert snap["recorded_by"]
