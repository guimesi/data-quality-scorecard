"""Tests for the Data Quality Report (HTML) - ``ui/step_06/report``.

The builder is pure, so the generated document is asserted structurally
with an HTML parser (stdlib - no bs4 dependency): content parity with
the dashboard (DQRs only), header metadata, DQR statuses + reasons,
interactivity hooks, escaping guarantees, empty states, caps,
self-containment, print support and a size guard. The Streamlit download
wrapper is exercised with a faked ``st``. The persistence store is
per-test isolated by conftest.
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


def section_of(html: str, anchor: str) -> str:
    """The markup of one ``id="..."`` element up to the next ``<h3``/
    ``</section>`` boundary - enough to scope text assertions."""
    body = html.split(f'id="{anchor}"', 1)[1]
    return re.split(r"<h3 |</section>", body, maxsplit=1)[0]


def _dp(df: pd.DataFrame, code: str = "EPT",
        name: str = "EPT Cost Data") -> DataProduct:
    return DataProduct(
        system_code=code, name=name, df=df,
        source_tables=["T1", "T2"], profiles=profile_dataframe(df),
    )


# The fixture is DQRs only: E1 (reads CODE_OF_RESOURCE + STANDARD_ACTIVITY_
# BREAKDOWN, blocking) and E4 (reads WBC_LEVEL_1). PLANVIEW_ID is a CDE no
# DQR reads, so it lands in the "CDEs with no DQR" intro line.
_CDES = ["PLANVIEW_ID", "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN",
         "WBC_LEVEL_1"]


def _cfg(code: str = "EPT", cdes=None, params=None,
         weights=(60.0, 40.0)) -> DataProductConfig:
    return DataProductConfig(
        system_code=code,
        cdes=list(_CDES if cdes is None else cdes),
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
        custom_assignments=[
            CustomDQRAssignment(rule_id="E1", weight=weights[0],
                                params=dict(params or {})),
            CustomDQRAssignment(rule_id="E4", weight=weights[1]),
        ],
    )


def _fixture(df: pd.DataFrame | None = None):
    df = df if df is not None else pd.DataFrame({
        "PLANVIEW_ID": ["PV-001", None, "PV-003", "PV-004"],
        "CODE_OF_RESOURCE": ["LOC-A", "LOC-B", None, "LOC-D"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV", "PROD", "DEC"],
        "WBC_LEVEL_1": ["L1", None, "L1", "L1"],
    })
    dp = _dp(df)
    cfg = _cfg()
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
    assert "Lowest pass-rate DQRs" in doc.full_text

    # Per-DP section with every sub-anchor the subnav links to.
    for anchor in ("EPT", "EPT-overview", "EPT-cdes", "EPT-dqrs", "EPT-dims",
                   "EPT-rows", "EPT-history", "EPT-config"):
        assert anchor in doc.ids, f"missing anchor {anchor}"

    # Overview: gauge, KPI row (incl. DQRs evaluated), stacked distribution.
    assert doc.count("svg", cls="gauge") == 1
    assert doc.count(cls="stack") == 1
    assert "DQRs evaluated" in doc.full_text
    assert '<span class="v">2<span class="s"> / 2</span></span>' in doc.html
    assert "The overall score is the mean row score" in doc.full_text

    # Breakdowns and the DQR list carry expandable rows.
    assert doc.count("details", cls="gl-row") >= 3   # CDEs + DQRs + dims
    assert "CODE_OF_RESOURCE" in doc.full_text
    assert "Completeness" in doc.full_text
    assert "E1" in doc.full_text and "E4" in doc.full_text
    assert "DQRs tied to this CDE" in doc.html
    assert "DQRs tied to this dimension" in doc.html

    # Lowest-scoring rows: static table with per-DQR flag columns.
    assert doc.count("table", cls="rows") == 1
    assert doc.count("th", cls="th-rule") == 2
    assert "row_score" in doc.full_text

    # History (empty here) + configuration snapshot.
    assert "History" in doc.full_text
    assert doc.count("details", cls="cfg") == 1
    assert "Configuration used for this run" in doc.full_text
    assert "Critical Data Elements" in doc.full_text
    assert "DQR assignments (2)" in doc.full_text

    # Overview numbers match the engine.
    assert f"{result.overall_score:.1f}" in doc.html


def test_report_covers_dqrs_only():
    """No Standard DQRs section, no source weights, no sub-scores, no
    Standard/Custom vocabulary - and the DQR-prefixed flag headers."""
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    doc = Doc(html)
    text = doc.full_text

    assert "Standard DQRs" not in text
    assert "Custom DQRs" not in text
    assert "Custom rules" not in text
    assert "Sources" not in text
    assert doc.count(cls="ov-src") == 0
    assert "Standard assignments" not in text
    assert "DQR sources" not in text
    assert "EPT-std" not in doc.ids and "EPT-custom" not in doc.ids
    assert "Worst rows" not in html
    assert "STD ·" not in html and "CUSTOM ·" not in html

    headers = [d["title"] for d in doc.attrs_of("span", cls="tv")
               if d.get("title", "").startswith("DQR · ")]
    assert "DQR · E1 · ISO Code of Account Present (COR + SAB) (w=60.0%)" in headers
    assert "DQR · E4 · Level 1 cost category populated (w=40.0%)" in headers
    data = report_data(html)
    assert [c["id"] for c in data["dps"]["EPT"]["ruleColumns"]] == ["E1", "E4"]
    assert all(c["header"].startswith("DQR · ")
               for c in data["dps"]["EPT"]["ruleColumns"])

    # The DQR list uses the DQR toolbar (blocking filter, sort by ID).
    dqrs = section_of(html, "EPT-dqrs")
    assert 'data-filter="blocking"' in dqrs
    assert 'data-filter="not-evaluated"' in dqrs
    assert 'data-filter="not-computed"' not in html
    assert "Sort: ID" in dqrs
    assert "Weight (Custom source)" not in html


def test_sections_follow_the_dqr_only_order():
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    order = ["EPT-overview", "EPT-cdes", "EPT-dqrs", "EPT-dims", "EPT-rows",
             "EPT-history", "EPT-config"]
    positions = [html.index(f'id="{a}"') for a in order]
    assert positions == sorted(positions)
    # Sub-nav labels and order.
    subnav = re.search(r'<nav class="subnav"[^>]*>(.*?)</nav>', html).group(1)
    labels = re.findall(r">([^<]+)</a>", subnav)
    assert labels == ["Overview", "CDEs", "DQRs", "Dimensions",
                      "Lowest-scoring rows", "History", "Configuration"]


def test_cdes_without_dqr_listed_in_intro_not_scored():
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    doc = Doc(html)
    cdes = section_of(html, "EPT-cdes")
    assert "3 of 4 critical data elements have DQRs" in doc.full_text
    assert "CDEs with no DQR in this run:" in cdes
    assert "<code>PLANVIEW_ID</code>" in cdes
    names = [d["data-name"] for d in doc.attrs_of("details", cls="gl-row")]
    assert "planview_id" not in names
    assert "code_of_resource" in names and "wbc_level_1" in names
    # Rule IDs column + evaluated/tied counter per CDE.
    assert "Rule IDs" in cdes
    assert '<span class="c-src muted">E1</span>' in cdes
    assert '<span class="c-rules num">1/1</span>' in cdes


def test_report_scores_match_engine_values():
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    for rid in ("E1", "E4"):
        assert f"{result.custom_rule_pass_rates[rid]:.1f}%" in html
    data = report_data(html)
    assert data["green"] == 90.0 and data["yellow"] == 70.0
    dp_data = data["dps"]["EPT"]
    assert dp_data["columns"] == list(dp.df.columns)
    assert dp_data["rules"]["E1"] == {
        "cdes": ["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        "dim": "Completeness",
    }
    # Store rows are the lowest-scoring rows, ascending, each once.
    scores = [r["s"] for r in dp_data["store"]]
    assert scores == sorted(scores)
    assert len(dp_data["store"]) == min(len(dp.df), ReportCaps().row_store)


# ================================================================= metadata


def test_header_title_and_metadata_fields():
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    doc = Doc(html)
    text = doc.full_text
    assert "<h1>Data Quality Scorecard Report - Cost Estimate</h1>" in html
    assert ("<title>Data Quality Scorecard Report - Cost Estimate · "
            "2026-09-03</title>") in html
    assert 'class="rh-lead"' not in html

    header = re.search(r'<dl class="meta">(.*?)</dl>', html, re.S).group(1)
    labels = re.findall(r"<dt>(.*?)</dt>", header)
    assert labels == ["Generated (UTC)", "Generated by", "Project filter",
                      "Run identifier"]
    assert "2026-09-03T21:18:42Z" in header
    assert "tester" in header
    assert "PV-10422" in header and "PV-99999" in header
    assert "run_20260903_211842_beef" in header

    # The other context fields are not rendered anywhere ...
    for absent in ("Step-by-step", "Sample (max", "Q3 baseline",
                   "Execution mode", "Data scope", "Saved project"):
        assert absent not in text, absent


def test_artifact_metadata_keeps_unrendered_context_for_publisher():
    dp, cfg, result = _fixture()
    artifact = build_report(_CTX, {"EPT": result}, {"EPT": dp}, {"EPT": cfg})
    meta = artifact.metadata
    assert meta["mode"] == "step_by_step"
    assert meta["data_scope"] == "sample"
    assert meta["sample_rows_cap"] == 50000
    assert meta["saved_project"] == "Q3 baseline"
    assert meta["threshold_green"] == 90.0 and meta["threshold_yellow"] == 70.0
    assert meta["project_filter"] == ["PV-10422", "PV-99999"]
    assert meta["domain_name"] == "Cost Estimate"
    assert meta["generated_by"] == "tester"


def test_header_metadata_never_invented():
    """Unset context fields render as an em dash, not fabricated values."""
    dp, cfg, result = _fixture()
    ctx = ReportContext(domain_code="cost_estimate", dp_codes=["EPT"],
                        generated_at="2026-09-03T00:00:00Z",
                        threshold_green=90, threshold_yellow=70)
    html = _build(dp, cfg, result, ctx)
    header = re.search(r'<dl class="meta">(.*?)</dl>', html, re.S).group(1)
    assert header.count("—") == 2            # generated-by, run id
    assert '<span class="muted">none</span>' in header   # project filter
    # Domain code stands in for the name in the title.
    assert "<h1>Data Quality Scorecard Report - cost_estimate</h1>" in html


# ========================================================= status + reasons


def test_not_evaluated_dqr_reason_everywhere():
    dp, cfg, result = _fixture()
    result.not_evaluated_custom_rules["E4"] = "reference dataset unavailable"
    html = _build(dp, cfg, result)
    doc = Doc(html)
    text = doc.full_text

    assert "Not evaluated" in text
    assert "reference dataset unavailable" in text
    assert "Not computed" not in text
    # The top-of-section callout lists the skipped DQR.
    assert "1 DQR(s) could not be evaluated" in text
    assert "Reasons are in the DQR table" in text
    assert "1 not evaluated" in text
    # DQRs evaluated KPI
    assert '<span class="v">1<span class="s"> / 2</span></span>' in html

    # No misleading 0% pass rate: the skipped DQR shows n/a and is marked.
    skipped = [d for d in doc.attrs_of("details", cls="gl-row")
               if d.get("data-status") == "not-evaluated"]
    assert len(skipped) == 1
    assert skipped[0]["data-score"] == "-1"
    assert skipped[0]["data-name"] == "e4"
    assert "n/a" in text
    assert "redistributed across the DQRs that evaluated" in text
    # The By-CDE row whose only DQR was skipped is unscored, not 0.
    cdes = section_of(html, "EPT-cdes")
    wbc = re.search(r'<details class="gl-row" data-name="wbc_level_1"[^>]*>',
                    cdes).group(0)
    assert 'data-score="-1"' in wbc and 'data-below="0"' in wbc


def test_summary_flags_skipped_dqrs_and_non_green():
    dp, cfg, result = _fixture()
    result.not_evaluated_custom_rules["E1"] = "boom-reason"
    html = _build(dp, cfg, result)
    summary = html.split('id="summary"')[1].split("</section>")[0]
    assert "boom-reason" in summary
    assert 'href="#EPT-dqrs"' in summary
    assert "E4 · Level 1 cost category populated" in summary
    if result.overall_score < 90:
        assert "are Red." in summary


# ============================================================ interactivity


def test_interactivity_hooks_present():
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    doc = Doc(html)
    assert doc.count("nav", cls="topnav") == 1
    assert doc.count(cls="toolbar") == 3          # cde / dqrs / dim
    assert doc.count("details") >= 3
    assert 'placeholder="Search CDE, dimension, DQR…"' in html
    assert "<script>" in html                     # inline behaviour script
    assert "createElement" in html                # JS builds DOM safely
    assert "innerHTML" not in html                # ... and only safely
    data = report_data(html)
    assert data["caps"] == {"worst_rows": 50, "drill_rows": 200,
                            "row_store": 300}
    # Every drill placeholder carries the engine-computed total.
    drills = doc.attrs_of("div", cls="drill")
    assert drills
    for d in drills:
        assert "data-drill" in d and "data-total" in d and "data-label" in d
        assert int(d["data-total"]) >= 0
    assert any(d["data-label"].startswith("DQR E1 (") for d in drills)
    # Search index is lowercase and covers id, name, type and columns.
    for d in doc.attrs_of("details", cls="gl-row"):
        assert d.get("data-search", "") == d.get("data-search", "").lower()
    e1 = next(d for d in doc.attrs_of("details", cls="gl-row")
              if d.get("data-name") == "e1")
    assert "code_of_resource" in e1["data-search"]
    assert "completeness" in e1["data-search"]


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
        "WBC_LEVEL_1": ["L1", None, "L1", "L1"],
    })
    dp = _dp(df)
    # Hostile CDE name (no DQR reads it -> intro line) + hostile DQR param
    # (rendered in the configuration snapshot).
    cfg = _cfg(cdes=_CDES + [_HOSTILE[3]], params={"note": _HOSTILE[0]})
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    html = _build(dp, cfg, result)

    for payload in _HOSTILE:
        assert payload not in html, f"raw payload leaked: {payload!r}"
    assert "&lt;script&gt;" in html         # escaped text form is present
    assert "&lt;img src=x" in html
    assert "&quot;&gt;&lt;script&gt;alert(2)" in html   # CDE name, escaped

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
    cfg = DataProductConfig(system_code="EPT", dqr_sources=["custom"],
                            source_weights={"custom": 100.0})
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    doc = Doc(_build(dp, cfg, result))
    text = doc.full_text
    assert "No DQRs selected" in text
    assert "No DQRs configured" in text
    assert "No persisted runs yet" in text
    assert "No CDEs selected" in text
    assert "No dimensions scored" in text
    assert "No rows scored" in text
    assert "0 of 0 critical data elements have DQRs" in text


def test_cdes_but_none_with_a_dqr():
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2"],
        "CODE_OF_RESOURCE": ["a", "b"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV"],
        "WBC_LEVEL_1": ["L1", "L1"],
    })
    dp = _dp(df)
    cfg = _cfg(cdes=["PLANVIEW_ID"])
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    doc = Doc(_build(dp, cfg, result))
    assert "0 of 1 critical data elements have DQRs" in doc.full_text
    assert "No CDE has a DQR in this run" in doc.full_text
    assert "CDEs with no DQR in this run: <code>PLANVIEW_ID</code>." in doc.html


def test_all_pass_dp_shows_no_failing_rows_notes():
    df = pd.DataFrame({
        "PLANVIEW_ID": ["PV-1", "PV-2", "PV-3"],
        "CODE_OF_RESOURCE": ["a", "b", "c"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV", "PROD"],
        "WBC_LEVEL_1": ["L1", "L1", "L1"],
    })
    dp = _dp(df)
    cfg = _cfg()
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    assert result.overall_score == 100.0
    doc = Doc(_build(dp, cfg, result))
    assert "No failing rows for" in doc.full_text
    assert doc.count("div", cls="drill") == 0     # nothing to drill into
    assert "Nothing needs attention" in doc.full_text
    assert "every DQR was evaluated" in doc.full_text


# ===================================================================== caps


def test_caps_respected_and_stated():
    n = 400
    df = pd.DataFrame({
        "PLANVIEW_ID": [f"PV-{i}" for i in range(n)],
        "CODE_OF_RESOURCE": [None if i % 2 else f"LOC-{i}" for i in range(n)],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP"] * n,
        "WBC_LEVEL_1": ["L1"] * n,
    })
    dp = _dp(df)
    cfg = _cfg()
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    html = _build(dp, cfg, result)
    doc = Doc(html)
    caps = ReportCaps()

    data = report_data(html)
    store = data["dps"]["EPT"]["store"]
    assert len(store) == caps.row_store            # 300 of 400, once each
    # Static Lowest-scoring rows = first worst_rows of the store.
    body_rows = html.split('<table class="rows">')[1].split("</table>")[0]
    assert body_rows.count("<tr>") == caps.worst_rows + 1   # + header row
    # Caps are stated where they apply and in the footer.
    assert f"Showing the {caps.worst_rows} lowest-scoring rows of 400" in \
        doc.full_text
    assert f"{caps.worst_rows} of 400, ascending by row score" in doc.full_text
    assert f"{caps.row_store} lowest-scoring rows per Data Product" in \
        doc.full_text
    assert f"Lowest-scoring rows table: {caps.worst_rows}" in doc.full_text
    assert f"up to {caps.drill_rows} rows each" in doc.full_text
    assert "Lowest-scoring rows" in html.split("<noscript>")[1].split("</noscript>")[0]
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
                for i in range(37)}
        cols["CODE_OF_RESOURCE"] = [None if j % 3 == 0 else f"COR-{j}"
                                    for j in range(300)]
        cols["STANDARD_ACTIVITY_BREAKDOWN"] = ["EXP"] * 300
        cols["WBC_LEVEL_1"] = ["L1"] * 300
        df = pd.DataFrame(cols)
        # The catalog is keyed by system code, so every synthetic DP uses
        # the EPT rules; the report keys them by the dict code.
        dp = _dp(df, code="EPT", name=f"System {k}")
        cfg = _cfg(cdes=["CODE_OF_RESOURCE", "WBC_LEVEL_1"])
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
    assert all(len(d["columns"]) == 40 for d in data["dps"].values())


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
    for key in ("rule_pass_rates", "custom_rule_pass_rates"):
        prev[key] = {k: min(100.0, v + 15.0) for k, v in prev[key].items()}
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
    assert "that moved ≥ 5 pp" in text                      # drift tables
    assert "Rules that moved" not in text
    # Summary carries the delta + config-changed pill.
    summary = doc.html.split('id="summary"')[1].split("</section>")[0]
    assert "-20.0 pp" in summary
    assert "changed" in summary
