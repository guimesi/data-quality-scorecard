"""Tests for the executive HTML report (phase 4).

The builder is pure, so content is asserted on the generated HTML
directly; the download wrapper is exercised with a faked ``st``. The
persistence store (for the trend block + telemetry) is per-test isolated
by conftest.
"""
from __future__ import annotations

import os

# Force mock mode before importing anything that reads settings.
os.environ.setdefault("DATA_SOURCE", "mock")

from unittest.mock import MagicMock

import pandas as pd

import ui.step_06._exec_report as er
from src.models import (
    CustomDQRAssignment,
    DataProduct,
    DataProductConfig,
    DQRAssignment,
)
from src.persistence import list_events, save_run
from src.profiler import profile_dataframe
from src.scorecard import compute_scorecard


def _dp(df: pd.DataFrame) -> DataProduct:
    return DataProduct(
        system_code="EPT", name="EPT Cost Data", df=df,
        source_tables=["T"], profiles=profile_dataframe(df),
    )


def _fixture(df: pd.DataFrame | None = None):
    df = df if df is not None else pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", None, "PV-003", "PV-004"],
        "CODE_OF_RESOURCE": ["LOC-A", "LOC-B", None, "LOC-D"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV", "PROD", "DEC"],
    })
    dp = _dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID", "CODE_OF_RESOURCE"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100.0)],
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 50.0, "custom": 50.0},
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=100.0)],
    )
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    return dp, cfg, result


def _build(dp, cfg, result) -> str:
    return er._build_executive_report_html(
        "cost_estimate", {"EPT": result}, {"EPT": dp}, {"EPT": cfg},
    ).decode("utf-8")


# ==================================================================== content

def test_report_carries_every_dashboard_view():
    dp, cfg, result = _fixture()
    html_doc = _build(dp, cfg, result)
    assert html_doc.startswith("<!DOCTYPE html>")
    assert "@media print" in html_doc                      # print stylesheet
    assert "Executive report" in html_doc
    assert "cost_estimate" in html_doc                     # domain in meta
    assert "EPT Cost Data" in html_doc                     # DP section header
    assert "By CDE" in html_doc and "By Dimension" in html_doc
    assert "PLANVIEW_ID" in html_doc                       # CDE bar label
    assert "Standard rules" in html_doc and "Custom rules" in html_doc
    assert "E1" in html_doc                                # custom rule row
    assert "Worst rows" in html_doc
    assert f"{result.overall_score:.1f}" in html_doc       # overview card
    assert "Source weights" in html_doc
    # No external references - the file must be fully self-contained.
    assert "http://" not in html_doc.replace("http://www.w3.org", "")
    assert "https://" not in html_doc


def test_report_escapes_data_values():
    df = pd.DataFrame({
        "PLANVIEW_ID": ["<script>alert(1)</script>", "PV-002"],
        "CODE_OF_RESOURCE": ["LOC-A", "LOC-B"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV"],
    })
    dp, cfg, result = _fixture(df)
    html_doc = _build(dp, cfg, result)
    assert "<script>" not in html_doc
    assert "&lt;script&gt;" in html_doc


def test_report_caps_worst_row_columns_with_note():
    df = pd.DataFrame({f"C{i}": ["x"] * 3 for i in range(12)})
    df["PLANVIEW_ID"] = ["PV-1", None, "PV-3"]
    dp = _dp(df)
    cfg = DataProductConfig(
        system_code="EPT", cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100.0)],
        dqr_sources=["standard"], source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    html_doc = _build(dp, cfg, result)
    assert f"Showing the first {er._MAX_WORST_COLS} of" in html_doc


def test_report_trend_block_needs_two_runs():
    dp, cfg, result = _fixture()
    assert "Score trend" not in _build(dp, cfg, result)

    save_run("EPT", "cost_estimate", {"overall_score": 90.0}, config_hash="h1")
    save_run("EPT", "cost_estimate", {"overall_score": 80.0}, config_hash="h2")
    html_doc = _build(dp, cfg, result)
    assert "Score trend" in html_doc
    assert "<svg" in html_doc and "polyline" in html_doc
    assert "-10.0 pp" in html_doc
    assert "configuration changed" in html_doc             # h1 -> h2


def test_report_not_computed_and_empty_rule_states():
    dp, cfg, result = _fixture()
    result.not_computed_standard_rules["PLANVIEW_ID::Completeness"] = "boom"
    result.not_evaluated_custom_rules["E1"] = "no reference data"
    html_doc = _build(dp, cfg, result)
    assert "Not computed" in html_doc
    assert "Not evaluated" in html_doc

    bare_cfg = DataProductConfig(system_code="EPT")
    assert "No Standard DQRs" in er._rules_table("EPT", result, bare_cfg)
    assert "No Custom DQRs" in er._custom_rules_table(result, bare_cfg)


def test_report_empty_rows_note():
    dp, cfg, result = _fixture()
    result.row_scores = result.row_scores.iloc[0:0]
    assert "No rows scored" in er._worst_rows_table(dp, result)


# ==================================================================== wiring

class _FakeSessionState(dict):
    __getattr__ = dict.__getitem__


def test_download_button_logs_export_event(monkeypatch):
    dp, cfg, result = _fixture()
    fake = MagicMock()
    fake.session_state = _FakeSessionState(
        data_products={"EPT": dp}, configs={"EPT": cfg},
        domain="cost_estimate",
    )
    fake.download_button.return_value = True
    monkeypatch.setattr(er, "st", fake)
    er._render_executive_report_download({"EPT": result})
    (event,) = list_events(event_type="export")
    assert event["payload"] == {"format": "executive_html"}
    assert event["domain_code"] == "cost_estimate"
    payload = fake.download_button.call_args.kwargs["data"]
    assert payload.decode("utf-8").startswith("<!DOCTYPE html>")


def test_download_button_hidden_without_scorecards(monkeypatch):
    fake = MagicMock()
    fake.session_state = _FakeSessionState()
    monkeypatch.setattr(er, "st", fake)
    er._render_executive_report_download({})
    fake.download_button.assert_not_called()
