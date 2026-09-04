"""Tests for the Data Quality Report (HTML) - ``ui/step_06/report``.

The builder is pure, so the generated document is asserted structurally
with an HTML parser (stdlib - no bs4 dependency): content parity with
the dashboard, header metadata, rule statuses + reasons, interactivity
hooks, escaping guarantees, empty states, caps, self-containment, print
support and a size guard. The Streamlit download wrapper is exercised
with a faked ``st``. The persistence store is per-test isolated by
conftest.
"""
from __future__ import annotations

import json
import os
import re

# Force mock mode before importing anything that reads settings.
os.environ.setdefault("DATA_SOURCE", "mock")

from html.parser import HTMLParser
from unittest.mock import MagicMock

import pandas as pd
import pytest

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
from ui.step_06.report import (
    ReportCaps,
    ReportContext,
    build_executive_report_html,
    build_report,
)

# ================================================================ helpers


class Doc(HTMLParser):
    """Tiny structural index of the generated document."""

    def __init__(self, html: str):
        super().__init__()
        self.elements = []          # (tag, attrs dict)
        self.ids = set()
        self.class_counts = {}
        self._stack = []
        self._capture_id = None
        self._captured = []
        self.text = []
        self.feed(html)
        self.html = html

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        self.elements.append((tag, d))
        if "id" in d:
            self.ids.add(d["id"])
        for c in (d.get("class") or "").split():
            self.class_counts[c] = self.class_counts.get(c, 0) + 1

    def handle_data(self, data):
        if data.strip():
            self.text.append(data)

    # -- queries ---------------------------------------------------------
    def count(self, tag=None, cls=None):
        n = 0
        for t, d in self.elements:
            if tag and t != tag:
                continue
            if cls and cls not in (d.get("class") or "").split():
                continue
            n += 1
        return n

    def attrs_of(self, tag, cls=None):
        return [d for t, d in self.elements
                if t == tag and (cls is None
                                 or cls in (d.get("class") or "").split())]

    @property
    def full_text(self):
        return " ".join(self.text)


def report_data(html: str) -> dict:
    island = re.search(
        r'<script type="application/json" id="report-data">(.*?)</script>',
        html, re.S,
    )
    assert island, "#report-data island missing"
    return json.loads(island.group(1))


def _dp(df: pd.DataFrame, code: str = "EPT",
        name: str = "EPT Cost Data") -> DataProduct:
    return DataProduct(
        system_code=code, name=name, df=df,
        source_tables=["T1", "T2"], profiles=profile_dataframe(df),
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


_CTX = ReportContext(
    domain_code="cost_estimate",
    domain_name="Cost Estimate",
    dp_codes=["EPT"],
    generated_at="2026-09-03T21:18:42Z",
    generated_by="tester",
    mode="step_by_step",
    data_scope="sample",
    sample_rows_cap=50000,
    project_filter=["PV-10422", "PV-99999"],
    threshold_green=90.0,
    threshold_yellow=70.0,
    saved_project="Q3 baseline",
    run_id="run_20260903_211842_beef",
)


def _build(dp, cfg, result, ctx: ReportContext = _CTX) -> str:
    return build_report(
        ctx, {dp.system_code: result}, {dp.system_code: dp},
        {dp.system_code: cfg},
    ).html.decode("utf-8")


# ============================================================ content parity


def test_report_carries_every_dashboard_view():
    dp, cfg, result = _fixture()
    doc = Doc(_build(dp, cfg, result))

    # Executive summary: cross-DP table + attention lists.
    assert "summary" in doc.ids
    assert doc.count("table", cls="exec") == 1
    assert "Needs attention" in doc.full_text
    assert "Lowest-scoring CDEs" in doc.full_text
    assert "Lowest pass-rate rules" in doc.full_text

    # Per-DP section with every sub-anchor the subnav links to.
    for anchor in ("EPT", "EPT-overview", "EPT-cdes", "EPT-dims", "EPT-std",
                   "EPT-custom", "EPT-rows", "EPT-history", "EPT-config"):
        assert anchor in doc.ids, f"missing anchor {anchor}"

    # Overview: gauge, KPI row, stacked distribution, sources card.
    assert doc.count("svg", cls="gauge") == 1
    assert doc.count(cls="stack") == 1
    assert doc.count(cls="ov-src") == 1
    assert "Sources" in doc.full_text
    assert re.search(r"Overall = .*mean row score", doc.full_text) or \
        "the overall combines them" in doc.full_text

    # Breakdowns and rule sections carry expandable rows.
    assert doc.count("details", cls="gl-row") >= 3   # CDEs + dims + rules
    assert "PLANVIEW_ID" in doc.full_text
    assert "Completeness" in doc.full_text
    assert "E1" in doc.full_text

    # Worst rows: static table with per-rule flag columns.
    assert doc.count("table", cls="rows") == 1
    assert doc.count("th", cls="th-rule") >= 1
    assert "row_score" in doc.full_text

    # History (empty here) + configuration snapshot.
    assert "History" in doc.full_text
    assert doc.count("details", cls="cfg") == 1
    assert "Configuration used for this run" in doc.full_text
    assert "Critical Data Elements" in doc.full_text

    # Overview numbers match the engine.
    assert f"{result.overall_score:.1f}" in doc.html


def test_report_scores_match_engine_values():
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    pass_rate = result.rule_pass_rates["PLANVIEW_ID::Completeness"]
    assert f"{pass_rate:.1f}%" in html
    data = report_data(html)
    assert data["green"] == 90.0 and data["yellow"] == 70.0
    dp_data = data["dps"]["EPT"]
    assert dp_data["columns"] == list(dp.df.columns)
    # Store rows are the lowest-scoring rows, ascending, each once.
    scores = [r["s"] for r in dp_data["store"]]
    assert scores == sorted(scores)
    assert len(dp_data["store"]) == min(len(dp.df), ReportCaps().row_store)


# ================================================================= metadata


def test_header_metadata_fields():
    dp, cfg, result = _fixture()
    doc = Doc(_build(dp, cfg, result))
    text = doc.full_text
    assert "Cost Estimate" in text and "cost_estimate" in text
    assert "2026-09-03T21:18:42Z" in text
    assert "tester" in text
    assert "Step-by-step" in text
    assert "Sample (max 50,000 rows per table)" in text
    assert "PV-10422" in text and "PV-99999" in text
    assert "Green ≥ 90" in text and "Yellow ≥ 70" in text
    assert "Q3 baseline" in text
    assert "run_20260903_211842_beef" in text


def test_header_metadata_never_invented():
    """Unset context fields render as an em dash, not fabricated values."""
    dp, cfg, result = _fixture()
    ctx = ReportContext(domain_code="cost_estimate", dp_codes=["EPT"],
                        generated_at="2026-09-03T00:00:00Z",
                        threshold_green=90, threshold_yellow=70)
    doc = Doc(_build(dp, cfg, result, ctx))
    # mode, scope, saved project, run id, generated-by -> 5 dashes minimum
    assert doc.html.count("—") >= 5
    assert "One-click" not in doc.full_text
    assert "Full dataset" not in doc.full_text


# ========================================================= status + reasons


def test_not_computed_and_not_evaluated_reasons():
    dp, cfg, result = _fixture()
    result.not_computed_standard_rules["PLANVIEW_ID::Completeness"] = (
        "Dimension requires a date column"
    )
    result.not_evaluated_custom_rules["E1"] = "reference dataset unavailable"
    doc = Doc(_build(dp, cfg, result))

    assert "Not computed" in doc.full_text
    assert "Dimension requires a date column" in doc.full_text
    assert "Not evaluated" in doc.full_text
    assert "reference dataset unavailable" in doc.full_text
    # The top-of-section callout lists the skipped rules.
    assert "could not be run" in doc.full_text

    # No misleading 0% pass rate: skipped rules show n/a and are marked.
    skipped = [d for d in doc.attrs_of("details", cls="gl-row")
               if d.get("data-status") in ("not-computed", "not-evaluated")]
    assert len(skipped) == 2
    assert all(d.get("data-score") == "-1" for d in skipped)
    assert "n/a" in doc.full_text


def test_summary_flags_skipped_rules_and_non_green():
    dp, cfg, result = _fixture()
    result.not_evaluated_custom_rules["E1"] = "boom-reason"
    html = _build(dp, cfg, result)
    summary = html.split('id="summary"')[1].split("</section>")[0]
    assert "boom-reason" in summary
    if result.overall_score < 90:
        assert "are Red." in summary


# ============================================================ interactivity


def test_interactivity_hooks_present():
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    doc = Doc(html)
    assert doc.count("nav", cls="topnav") == 1
    assert doc.count(cls="toolbar") >= 4          # cde/dim/std/custom
    assert doc.count("details") >= 3
    assert "<script>" in html                     # inline behaviour script
    assert "createElement" in html                # JS builds DOM safely
    assert "innerHTML" not in html                # ... and only safely
    data = report_data(html)
    assert data["caps"] == {"worst_rows": 50, "drill_rows": 200,
                            "row_store": 300}
    # Every drill placeholder carries the engine-computed total.
    for d in doc.attrs_of("div", cls="drill"):
        assert "data-drill" in d and "data-total" in d and "data-label" in d
        assert int(d["data-total"]) >= 0
    # Search index is lowercase.
    for d in doc.attrs_of("details", cls="gl-row"):
        assert d.get("data-search", "") == d.get("data-search", "").lower()


# ====================================================================== XSS


_HOSTILE = [
    '<script>alert("xss")</script>',
    "<img src=x onerror=alert(1)>",
    "</script><b>break</b>",
    '"><script>alert(2)</script>',
]


def test_hostile_values_render_as_text_everywhere():
    df = pd.DataFrame({
        "PLANVIEW_ID": [_HOSTILE[0], None, "PV-3", "PV-4"],
        "CODE_OF_RESOURCE": [_HOSTILE[1], _HOSTILE[2], _HOSTILE[3], "LOC"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV", "PROD", "DEC"],
    })
    dp = _dp(df)
    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["PLANVIEW_ID", "CODE_OF_RESOURCE"],
        assignments=[
            DQRAssignment("PLANVIEW_ID", "Completeness", weight=50.0,
                          params={"note": _HOSTILE[0]}),
            DQRAssignment("CODE_OF_RESOURCE", "Completeness", weight=50.0),
        ],
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    html = _build(dp, cfg, result)

    for payload in _HOSTILE:
        assert payload not in html, f"raw payload leaked: {payload!r}"
    assert "&lt;script&gt;" in html         # escaped text form is present
    assert "&lt;img src=x" in html

    # The JSON island cannot be broken out of.
    island = re.search(
        r'<script type="application/json" id="report-data">(.*?)</script>',
        html, re.S,
    ).group(1)
    assert "</script" not in island
    assert "<" not in island and ">" not in island
    # ... and still round-trips to the original values.
    data = json.loads(island)
    values = json.dumps(data)
    assert "alert(1)" in values


def test_hostile_username_and_domain_are_escaped(monkeypatch):
    import src.persistence as pers

    dp, cfg, result = _fixture()
    monkeypatch.setattr(pers, "current_username",
                        lambda: '<script>alert("u")</script>')
    save_run("EPT", "cost_estimate", {"overall_score": 88.0}, config_hash="h1")
    save_run("EPT", "cost_estimate", {"overall_score": 90.0}, config_hash="h2")
    html = _build(dp, cfg, result)
    assert '<script>alert("u")</script>' not in html
    assert "&lt;script&gt;alert(&quot;u&quot;)&lt;/script&gt;" in html


# ============================================================== empty states


def test_empty_states_read_clearly():
    df = pd.DataFrame({"A": ["x", "y", "z"]})
    dp = _dp(df)
    cfg = DataProductConfig(system_code="EPT", dqr_sources=["standard"],
                            source_weights={"standard": 100.0})
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    doc = Doc(_build(dp, cfg, result))
    text = doc.full_text
    assert "No Standard DQRs defined" in text
    assert "No custom rules selected" in text
    assert "No persisted runs yet" in text
    assert "No CDEs selected" in text
    assert "No dimensions scored" in text


def test_all_pass_dp_shows_no_failing_rows_notes():
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2", "PV-3"],
        "CODE_OF_RESOURCE": ["a", "b", "c"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV", "PROD"],
    })
    dp = _dp(df)
    cfg = DataProductConfig(
        system_code="EPT", cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100.0)],
        dqr_sources=["standard"], source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    assert result.overall_score == 100.0
    doc = Doc(_build(dp, cfg, result))
    assert "No failing rows for" in doc.full_text
    assert doc.count("div", cls="drill") == 0     # nothing to drill into
    assert "Nothing needs attention" in doc.full_text


# ===================================================================== caps


def test_caps_respected_and_stated():
    n = 400
    df = pd.DataFrame({
        "PLANVIEW_ID": [None if i % 2 else f"PV-{i}" for i in range(n)],
        "CODE_OF_RESOURCE": [f"LOC-{i}" for i in range(n)],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP"] * n,
    })
    dp = _dp(df)
    cfg = DataProductConfig(
        system_code="EPT", cdes=["PLANVIEW_ID"],
        assignments=[DQRAssignment("PLANVIEW_ID", "Completeness", weight=100.0)],
        dqr_sources=["standard"], source_weights={"standard": 100.0},
    )
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    html = _build(dp, cfg, result)
    doc = Doc(html)
    caps = ReportCaps()

    data = report_data(html)
    store = data["dps"]["EPT"]["store"]
    assert len(store) == caps.row_store            # 300 of 400, once each
    # Static worst rows = first worst_rows of the store.
    body_rows = html.split('<table class="rows">')[1].split("</table>")[0]
    assert body_rows.count("<tr>") == caps.worst_rows + 1   # + header row
    # Caps are stated where they apply and in the footer.
    assert f"Showing the {caps.worst_rows} lowest-scoring rows of 400" in \
        doc.full_text
    assert f"{caps.row_store} lowest-scoring rows per Data Product" in \
        doc.full_text
    assert f"up to {caps.drill_rows} rows each" in doc.full_text
    # Drill totals come from the engine, not from the capped store.
    drills = doc.attrs_of("div", cls="drill")
    assert any(int(d["data-total"]) == 200 for d in drills)  # 200 null rows


# ============================================================ self-contained


def test_fully_self_contained():
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    assert "https://" not in html
    assert "http://" not in html.replace("http://www.w3.org", "")
    assert "<link" not in html
    assert "@import" not in html
    assert not re.search(r"<script[^>]+src=", html)
    assert not re.search(r"<img[^>]+src=", html)   # no external images either


# ==================================================================== print


def test_print_stylesheet_and_handlers():
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    assert "@media print" in html
    assert "beforeprint" in html and "afterprint" in html
    assert "page-break-before" in html


# ==================================================================== size


def test_size_guard_five_dps():
    dps, configs, scorecards = {}, {}, {}
    for k in range(5):
        code = f"SY{k}"
        cols = {f"C{i:02d}": [f"v{i}_{j}" for j in range(300)]
                for i in range(39)}
        cols["PLANVIEW_ID"] = [None if j % 3 == 0 else f"PV-{j}"
                               for j in range(300)]
        df = pd.DataFrame(cols)
        dp = _dp(df, code=code, name=f"System {k}")
        cfg = DataProductConfig(
            system_code=code, cdes=["PLANVIEW_ID"],
            assignments=[DQRAssignment("PLANVIEW_ID", "Completeness",
                                       weight=100.0)],
            dqr_sources=["standard"], source_weights={"standard": 100.0},
        )
        dps[code] = dp
        configs[code] = cfg
        scorecards[code] = compute_scorecard(
            dp, cfg, threshold_green=90, threshold_yellow=70,
        )
    ctx = ReportContext(domain_code="d", dp_codes=list(dps),
                        generated_at="2026-09-03T00:00:00Z",
                        threshold_green=90, threshold_yellow=70)
    artifact = build_report(ctx, scorecards, dps, configs)
    assert len(artifact.html) < 8 * 1024 * 1024
    # 40 columns x 300 rows x 5 DPs all embedded exactly once.
    data = report_data(artifact.html.decode("utf-8"))
    assert all(len(d["store"]) == 300 for d in data["dps"].values())


# ================================================== compatibility + wiring


def test_compat_alias_returns_bytes():
    dp, cfg, result = _fixture()
    for fn in (er._build_executive_report_html, build_executive_report_html):
        payload = fn("cost_estimate", {"EPT": result}, {"EPT": dp},
                     {"EPT": cfg})
        assert isinstance(payload, bytes)
        assert payload.decode("utf-8").startswith("<!DOCTYPE html>")


def test_artifact_filename_and_metadata():
    dp, cfg, result = _fixture()
    artifact = build_report(_CTX, {"EPT": result}, {"EPT": dp}, {"EPT": cfg})
    assert artifact.filename == "dq_scorecard_report_COST_ESTIMATE_20260903_211842.html"
    assert artifact.metadata["dp_codes"] == ["EPT"]
    assert artifact.metadata["run_id"] == "run_20260903_211842_beef"
    assert artifact.metadata["overall_scores"]["EPT"] == pytest.approx(
        round(result.overall_score, 2))


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
    kwargs = fake.download_button.call_args.kwargs
    assert kwargs["data"].decode("utf-8").startswith("<!DOCTYPE html>")
    assert kwargs["file_name"].startswith("dq_scorecard_report_COST_ESTIMATE_")
    assert kwargs["file_name"].endswith(".html")
    label = fake.download_button.call_args.args[0]
    assert "Data Quality Report (HTML)" in label


def test_download_button_hidden_without_scorecards(monkeypatch):
    fake = MagicMock()
    fake.session_state = _FakeSessionState()
    monkeypatch.setattr(er, "st", fake)
    er._render_executive_report_download({})
    fake.download_button.assert_not_called()


# ================================================================== history


def test_history_drop_alert_and_drift():
    dp, cfg, result = _fixture()
    from src.ml_lab import snapshot_scorecard
    from src.run_history import record_run_if_new

    prev = snapshot_scorecard("EPT", dp, result)
    prev["overall_score"] = float(result.overall_score) + 20.0
    prev["rule_pass_rates"] = {
        k: min(100.0, v + 15.0) for k, v in prev["rule_pass_rates"].items()
    }
    save_run("EPT", "cost_estimate", prev, config_hash="oldcfg01")
    record_run_if_new("EPT", dp, result, cfg, "cost_estimate")

    doc = Doc(_build(dp, cfg, result))
    text = doc.full_text
    assert "Score dropped 20.0 pp" in text                  # drop callout
    assert "configuration also changed" in text.lower()
    assert "Run log" in text
    assert "What changed vs the previous run" in text
    assert "EPT-changes" in doc.ids
    assert doc.count("svg", cls="trend") == 1
    assert "that moved ≥ 5 pp" in text                      # drift table
    # Summary carries the delta + config-changed pill.
    summary = doc.html.split('id="summary"')[1].split("</section>")[0]
    assert "-20.0 pp" in summary
    assert "changed" in summary
