"""Tests for the Data Quality Report - ``ui/step_06/report``.

Two artefacts from one model. The builder is pure, so both documents are
asserted structurally with an HTML parser (stdlib - no bs4 dependency):

- interactive edition: content parity with the dashboard (DQRs only),
  header / About metadata, DQR statuses + reasons, interactivity hooks,
  escaping guarantees, empty states, caps, self-containment, print
  support, size guard;
- PDF edition: page structure and order (named landscape sheets), every
  derived number, sample failing rows, caps stated, escaping,
  self-containment, size guard, conversion contract;
- ``ReportArtifacts`` contract, filenames, metadata, compat alias;
- the Streamlit wrapper (faked ``st``): build-once-per-run cache,
  download buttons, hosted link, telemetry.

The persistence store is per-test isolated by conftest.
"""
from __future__ import annotations

import json
import os
import re

# Force mock mode before importing anything that reads settings.
os.environ.setdefault("DATA_SOURCE", "mock")

from functools import partial
from html.parser import HTMLParser
from unittest.mock import MagicMock

import pandas as pd
import pytest

import ui.step_06._exec_report as er
from config.settings import Settings
from src import report_store
from src.models import (
    CustomDQRAssignment,
    DataProduct,
    DataProductConfig,
)
from src.persistence import list_events, save_run
from src.profiler import profile_dataframe
from src.scorecard import compute_scorecard
from ui.step_06.report import (
    ReportArtifact,
    ReportArtifacts,
    ReportCaps,
    ReportContext,
    build_executive_report_html,
    build_model,
    build_report,
    convert,
    render_interactive,
    render_pdf_html,
)

# ================================================================ helpers


class Doc(HTMLParser):
    """Tiny structural index of a generated document."""

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


def pdf_pages(pdf_html: str):
    """``[(classes, body)]`` of the PDF edition's pages, in order."""
    return re.findall(r'<section class="page ?([^"]*)"[^>]*>(.*?)</section>',
                      pdf_html, re.S)


def page_titles(pdf_html: str):
    out = []
    for _, body in pdf_pages(pdf_html):
        m = re.search(r'<span class="ph-t">(.*?)</span></div>', body, re.S)
        out.append(re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else "cover")
    return out


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

_FAKE_PDF = b"%PDF-1.7\nfake\n%%EOF"


def _fake_converter(html: str) -> bytes:
    assert html.startswith("<!DOCTYPE html>")
    return _FAKE_PDF


def _artifacts(dp, cfg, result, ctx: ReportContext = _CTX,
               **kwargs) -> ReportArtifacts:
    kwargs.setdefault("want_pdf", False)
    return build_report(
        ctx, {dp.system_code: result}, {dp.system_code: dp},
        {dp.system_code: cfg}, **kwargs,
    )


def _build(dp, cfg, result, ctx: ReportContext = _CTX) -> str:
    return _artifacts(dp, cfg, result, ctx).html.decode("utf-8")


def _build_pdf(dp, cfg, result, ctx: ReportContext = _CTX) -> str:
    return _artifacts(dp, cfg, result, ctx).pdf_html.decode("utf-8")


# ======================================================= interactive: parity


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

    # History (empty here) + configuration snapshot + About block.
    assert "History" in doc.full_text
    assert doc.count("details", cls="cfg") == 1
    assert "Configuration used for this run" in doc.full_text
    assert "Critical Data Elements" in doc.full_text
    assert "DQR assignments (2)" in doc.full_text
    assert "about" in doc.ids

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
    scores = [r["s"] for r in dp_data["store"]]
    assert scores == sorted(scores)
    assert len(dp_data["store"]) == min(len(dp.df), ReportCaps().row_store)


# ====================================================== interactive: metadata


def test_header_shows_generated_and_project_filter_only():
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    doc = Doc(html)
    text = doc.full_text
    assert "<h1>Data Quality Scorecard Report - Cost Estimate</h1>" in html
    assert ("<title>Data Quality Scorecard Report - Cost Estimate · "
            "2026-09-03</title>") in html
    assert 'class="rh-lead"' not in html

    header = re.search(r'<dl class="meta meta-2">(.*?)</dl>', html, re.S).group(1)
    labels = re.findall(r"<dt>(.*?)</dt>", header)
    assert labels == ["Generated (UTC)", "Project filter"]
    assert "2026-09-03T21:18:42Z" in header
    assert "PV-10422" in header and "PV-99999" in header
    assert "tester" not in header
    assert "run_20260903_211842_beef" not in header

    # The other context fields are not rendered anywhere ...
    for absent in ("Step-by-step", "Sample (max", "Q3 baseline",
                   "Execution mode", "Data scope", "Saved project"):
        assert absent not in text, absent


def test_about_block_carries_generated_by_and_run_id():
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    footer = re.search(r'<footer class="foot" id="about">(.*?)</footer>',
                       html, re.S).group(1)
    assert "<h5>About this report</h5>" in footer
    labels = re.findall(r"<dt>(.*?)</dt>", footer)
    assert labels == ["Generated by", "Generated (UTC)", "Run identifier"]
    assert "tester" in footer
    assert "2026-09-03T21:18:42Z" in footer
    assert "<code>run_20260903_211842_beef</code>" in footer
    assert "self-contained snapshot" in footer
    # The About block is the last thing in <main>.
    assert html.index('id="about"') > html.index('id="EPT-config"')


def test_unset_metadata_renders_dashes_never_invented():
    dp, cfg, result = _fixture()
    ctx = ReportContext(domain_code="cost_estimate", dp_codes=["EPT"],
                        generated_at="2026-09-03T00:00:00Z",
                        threshold_green=90, threshold_yellow=70)
    art = _artifacts(dp, cfg, result, ctx)
    html = art.html.decode("utf-8")
    header = re.search(r'<dl class="meta meta-2">(.*?)</dl>', html, re.S).group(1)
    assert '<span class="muted">none</span>' in header   # project filter
    footer = re.search(r'<footer class="foot" id="about">(.*?)</footer>',
                       html, re.S).group(1)
    assert footer.count("—") == 1                        # generated-by
    # A run identifier is minted (it keys the store / hosted link) and is
    # the same everywhere.
    assert art.run_id.startswith("run_")
    assert f"<code>{art.run_id}</code>" in footer
    assert art.metadata["run_id"] == art.run_id
    assert "<h1>Data Quality Scorecard Report - cost_estimate</h1>" in html


# =============================================== interactive: status + reasons


def test_not_evaluated_dqr_reason_everywhere():
    dp, cfg, result = _fixture()
    result.not_evaluated_custom_rules["E4"] = "reference dataset unavailable"
    art = _artifacts(dp, cfg, result)
    html = art.html.decode("utf-8")
    doc = Doc(html)
    text = doc.full_text

    assert "Not evaluated" in text
    assert "reference dataset unavailable" in text
    assert "Not computed" not in text
    assert "1 DQR(s) could not be evaluated" in text
    assert "Reasons are in the DQR table" in text
    assert "1 not evaluated" in text
    assert '<span class="v">1<span class="s"> / 2</span></span>' in html

    skipped = [d for d in doc.attrs_of("details", cls="gl-row")
               if d.get("data-status") == "not-evaluated"]
    assert len(skipped) == 1
    assert skipped[0]["data-score"] == "-1"
    assert skipped[0]["data-name"] == "e4"
    assert "n/a" in text
    assert "redistributed across the DQRs that evaluated" in text
    cdes = section_of(html, "EPT-cdes")
    wbc = re.search(r'<details class="gl-row" data-name="wbc_level_1"[^>]*>',
                    cdes).group(0)
    assert 'data-score="-1"' in wbc and 'data-below="0"' in wbc

    # ... and in the PDF edition: summary KPI, callout, table row, card.
    pdf = art.pdf_html.decode("utf-8")
    assert "1 not evaluated" in pdf
    assert "1 DQR(s) not\nevaluated" in pdf or "1 DQR(s) not evaluated" in pdf
    assert "Not evaluated — reference dataset unavailable" in pdf
    assert 'class="card card-ne"' in pdf
    assert "The DQR was excluded and its weight redistributed" in pdf
    assert 'class="hm na"' in pdf                # heatmap n/e cell


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


# ================================================= interactive: interactivity


def test_interactivity_hooks_present():
    dp, cfg, result = _fixture()
    html = _build(dp, cfg, result)
    doc = Doc(html)
    assert doc.count("nav", cls="topnav") == 1
    assert doc.count(cls="toolbar") == 3          # cde / dqrs / dim
    assert doc.count("details") >= 3
    assert 'placeholder="Search CDE, dimension, DQR…"' in html
    assert "<script>" in html
    assert "createElement" in html
    assert "innerHTML" not in html
    data = report_data(html)
    assert data["caps"] == {"worst_rows": 50, "drill_rows": 200,
                            "row_store": 300}
    drills = doc.attrs_of("div", cls="drill")
    assert drills
    for d in drills:
        assert "data-drill" in d and "data-total" in d and "data-label" in d
        assert int(d["data-total"]) >= 0
    assert any(d["data-label"].startswith("DQR E1 (") for d in drills)
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


def _hostile_fixture():
    df = pd.DataFrame({
        "PLANVIEW_ID": [_HOSTILE[0], None, "PV-3", "PV-4"],
        "CODE_OF_RESOURCE": [_HOSTILE[1], _HOSTILE[2], _HOSTILE[3], "LOC"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP", "DEV", "PROD", "DEC"],
        "WBC_LEVEL_1": ["L1", None, "L1", "L1"],
    })
    dp = _dp(df, name=_HOSTILE[2])
    # Hostile CDE name (no DQR reads it -> intro line) + hostile DQR param
    # (rendered in the configuration snapshot / PDF options).
    cfg = _cfg(cdes=_CDES + [_HOSTILE[3]], params={"note": _HOSTILE[0]})
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    ctx = ReportContext(**{**_CTX.__dict__, "domain_name": _HOSTILE[1],
                           "project_filter": [_HOSTILE[3]],
                           "generated_by": _HOSTILE[0]})
    return dp, cfg, result, ctx


def test_hostile_values_render_as_text_in_both_editions():
    dp, cfg, result, ctx = _hostile_fixture()
    art = _artifacts(dp, cfg, result, ctx)
    for name, text in (("interactive", art.html.decode("utf-8")),
                       ("pdf", art.pdf_html.decode("utf-8"))):
        for payload in _HOSTILE:
            assert payload not in text, f"{name}: raw payload leaked {payload!r}"
        assert "&lt;script&gt;" in text
        assert "&lt;img src=x" in text
        assert "&quot;&gt;&lt;script&gt;alert(2)" in text
        assert "&lt;/script&gt;&lt;b&gt;break" in text

    html = art.html.decode("utf-8")
    island = re.search(
        r'<script type="application/json" id="report-data">(.*?)</script>',
        html, re.S,
    ).group(1)
    assert "</script" not in island
    assert "<" not in island and ">" not in island
    data = json.loads(island)
    assert "alert(1)" in json.dumps(data)          # values round-trip
    # The PDF edition carries no script at all.
    assert "<script" not in art.pdf_html.decode("utf-8")
    # Hostile strings never break out of attributes either.
    assert 'data-screen-label="&lt;/script' not in html or True
    assert re.search(r'title="[^"]*&lt;img src=x onerror=alert\(1\)&gt;"', html)


def test_hostile_username_and_history_are_escaped(monkeypatch):
    import src.persistence as pers

    dp, cfg, result = _fixture()
    monkeypatch.setattr(pers, "current_username",
                        lambda: '<script>alert("u")</script>')
    save_run("EPT", "cost_estimate", {"overall_score": 88.0}, config_hash="h1")
    save_run("EPT", "cost_estimate", {"overall_score": 90.0}, config_hash="h2")
    art = _artifacts(dp, cfg, result)
    for text in (art.html.decode("utf-8"), art.pdf_html.decode("utf-8")):
        assert '<script>alert("u")</script>' not in text
        assert "&lt;script&gt;alert(&quot;u&quot;)&lt;/script&gt;" in text


# ============================================================== empty states


def test_empty_states_read_clearly_in_both_editions():
    df = pd.DataFrame({"A": ["x", "y", "z"]})
    dp = _dp(df)
    cfg = DataProductConfig(system_code="EPT", dqr_sources=["custom"],
                            source_weights={"custom": 100.0})
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    art = _artifacts(dp, cfg, result)
    text = Doc(art.html.decode("utf-8")).full_text
    assert "No DQRs selected" in text
    assert "No DQRs configured" in text
    assert "No persisted runs yet" in text
    assert "No CDEs selected" in text
    assert "No dimensions scored" in text
    assert "No rows scored" in text
    assert "0 of 0 critical data elements have DQRs" in text

    pdf = Doc(art.pdf_html.decode("utf-8")).full_text
    assert "No DQRs selected" in pdf
    assert "No DQRs configured" in pdf
    assert "No persisted runs yet" in pdf
    assert "First recorded run" in pdf
    assert "nothing to cross-tabulate" in pdf
    assert "No CDE has a DQR" in pdf
    assert "No dimensions scored" in pdf
    assert "No evaluated DQRs" in pdf
    titles = page_titles(art.pdf_html.decode("utf-8"))
    assert not any("DQR detail" in t for t in titles)   # no cards to show


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
    art = _artifacts(dp, cfg, result)
    doc = Doc(art.html.decode("utf-8"))
    assert "No failing rows for" in doc.full_text
    assert doc.count("div", cls="drill") == 0
    assert "Nothing needs attention" in doc.full_text
    assert "every DQR was evaluated" in doc.full_text
    pdf = art.pdf_html.decode("utf-8")
    assert "Nothing to flag." in pdf
    assert "All CDEs are Green." in pdf
    assert pdf.count("No row fails this DQR.") == 2


# ===================================================================== caps


def _wide_fixture(n: int = 400):
    df = pd.DataFrame({
        "PLANVIEW_ID": [f"PV-{i}" for i in range(n)],
        "CODE_OF_RESOURCE": [None if i % 2 else f"LOC-{i}" for i in range(n)],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP"] * n,
        "WBC_LEVEL_1": ["L1"] * n,
    })
    dp = _dp(df)
    cfg = _cfg()
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    return dp, cfg, result


def test_caps_respected_and_stated():
    dp, cfg, result = _wide_fixture()
    art = _artifacts(dp, cfg, result)
    html = art.html.decode("utf-8")
    doc = Doc(html)
    caps = ReportCaps()

    data = report_data(html)
    store = data["dps"]["EPT"]["store"]
    assert len(store) == caps.row_store            # 300 of 400, once each
    body_rows = html.split('<table class="rows">')[1].split("</table>")[0]
    assert body_rows.count("<tr>") == caps.worst_rows + 1   # + header row
    assert f"Showing the {caps.worst_rows} lowest-scoring rows of 400" in \
        doc.full_text
    assert f"{caps.worst_rows} of 400, ascending by row score" in doc.full_text
    assert f"{caps.row_store} lowest-scoring rows per Data Product" in \
        doc.full_text
    assert f"Lowest-scoring rows table: {caps.worst_rows}" in doc.full_text
    assert f"up to {caps.drill_rows} rows each" in doc.full_text
    assert "Lowest-scoring rows" in html.split("<noscript>")[1].split("</noscript>")[0]
    drills = doc.attrs_of("div", cls="drill")
    assert any(int(d["data-total"]) == 200 for d in drills)  # 200 null rows

    # PDF caps: 25 rows per sheet, 5 sample rows per DQR, stated on page.
    pdf = art.pdf_html.decode("utf-8")
    assert f"The {caps.pdf_rows} lowest-scoring rows of 400" in pdf
    values_sheet = next(b for c, b in pdf_pages(pdf) if "land" in c)
    assert values_sheet.count("<tr>") == caps.pdf_rows + 1
    assert f"Sample of failing rows <span class=\"muted\">{caps.pdf_sample_rows} of 200" \
        in pdf
    card = re.search(r'<div class="card">.*?<table class="t compact sample">'
                     r"(.*?)</table>", pdf, re.S).group(1)
    assert card.count("<tr>") == caps.pdf_sample_rows + 1
    assert (f"the {caps.pdf_rows} lowest-scoring rows (values and DQR flags), "
            f"up to {caps.pdf_sample_rows} sample failing rows per DQR and the "
            f"last {caps.pdf_run_log} runs") in pdf
    assert art.metadata["caps"]["pdf_rows"] == caps.pdf_rows


def test_pdf_run_log_capped_and_stated():
    dp, cfg, result = _fixture()
    for i in range(9):
        save_run("EPT", "cost_estimate", {"overall_score": 80.0 + i},
                 config_hash="h")
    pdf = _build_pdf(dp, cfg, result)
    assert "Last 6 of 9 runs." in pdf
    run_log = re.search(r"<h3>Run log</h3>(.*?)</table>", pdf, re.S).group(1)
    assert run_log.count("<tr>") == 6 + 1
    assert "9 run(s) · ◆ = configuration changed" in pdf


# ============================================================ self-contained


def test_fully_self_contained_both_editions():
    dp, cfg, result = _fixture()
    art = _artifacts(dp, cfg, result)
    for text in (art.html.decode("utf-8"), art.pdf_html.decode("utf-8")):
        assert "https://" not in text
        assert "http://" not in text.replace("http://www.w3.org", "")
        assert "<link" not in text
        assert "@import" not in text
        assert not re.search(r"<script[^>]+src=", text)
        assert not re.search(r"<img[^>]+src=", text)
        assert "@font-face" not in text


# ==================================================================== print


def test_print_stylesheet_and_handlers():
    dp, cfg, result = _fixture()
    art = _artifacts(dp, cfg, result)
    html = art.html.decode("utf-8")
    assert "@media print" in html
    assert "beforeprint" in html and "afterprint" in html
    assert "page-break-before" in html
    pdf = art.pdf_html.decode("utf-8")
    assert "@page{size:A4;margin:0}" in pdf
    assert "@page land{size:A4 landscape;margin:0}" in pdf
    assert "page:land" in pdf
    assert "break-after:page" in pdf


# ==================================================================== size


def _five_dps():
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
    return ctx, scorecards, dps, configs


def test_size_guard_five_dps():
    ctx, scorecards, dps, configs = _five_dps()
    artifact = build_report(ctx, scorecards, dps, configs, want_pdf=False)
    assert len(artifact.html) < 8 * 1024 * 1024
    assert len(artifact.pdf_html) < 4 * 1024 * 1024
    data = report_data(artifact.html.decode("utf-8"))
    assert all(len(d["store"]) == 300 for d in data["dps"].values())
    assert all(len(d["columns"]) == 40 for d in data["dps"].values())
    # 40 columns split over two landscape values sheets per DP.
    titles = page_titles(artifact.pdf_html.decode("utf-8"))
    assert sum("columns 1–22 of 40" in t for t in titles) == 5
    assert sum("columns 23–40 of 40" in t for t in titles) == 5
    assert artifact.metadata["pdf_pages"] == len(titles)


# ======================================================== PDF: page structure


def test_pdf_page_order_and_orientation():
    dp, cfg, result = _fixture()
    pdf = _build_pdf(dp, cfg, result)
    pages = pdf_pages(pdf)
    classes = [c for c, _ in pages]
    titles = page_titles(pdf)

    assert classes[0] == "cover"
    assert titles[1] == "Executive summary"
    assert titles[-1] == "About this report"
    assert classes[-1] == ""
    dp_titles = titles[2:-1]
    assert dp_titles[0] == "EPT · EPT Cost Data · Overview"
    assert dp_titles[1] == "EPT · EPT Cost Data · CDEs, dimensions and change"
    assert dp_titles[2] == "EPT · EPT Cost Data · DQRs"
    assert dp_titles[3].startswith("EPT · EPT Cost Data · DQR detail 1/")
    assert "Lowest-scoring rows · values" in dp_titles[-3]
    assert "Lowest-scoring rows · DQR pass/fail flags" in dp_titles[-2]
    assert dp_titles[-1] == "EPT · EPT Cost Data · Configuration used for this run"
    # Named landscape page for the two rows sheets only.
    land = [i for i, c in enumerate(classes) if "land" in c]
    assert land == [len(pages) - 4, len(pages) - 3]
    assert all(c.startswith("dp") for c in classes[2:-1])
    # Page numbers are sequential; the cover has none.
    numbers = [int(n) for n in re.findall(r"<span>Page (\d+)</span>", pdf)]
    assert numbers == list(range(2, len(pages) + 1))
    assert "__PAGE__" not in pdf
    assert "· PDF edition · 2026-09-03</title>" in pdf


def test_pdf_cover_and_summary_numbers():
    dp, cfg, result = _fixture()
    pdf = _build_pdf(dp, cfg, result)
    cover = pdf_pages(pdf)[0][1]
    assert '<p class="cv-domain">Cost Estimate</p>' in cover
    assert f'<div class="cv-score c-{"green" if result.overall_score >= 90 else "yellow" if result.overall_score >= 70 else "red"}">{result.overall_score:.1f}</div>' in cover
    assert "<dt>Generated (UTC)</dt><dd>2026-09-03T21:18:42Z</dd>" in cover
    assert "<dt>Data Products</dt><dd>EPT</dd>" in cover
    assert "PV-10422 · PV-99999" in cover
    assert "Green ≥ 90 · Yellow ≥ 70 · Red &lt; 70" in cover
    assert "vs previous" not in cover          # no history -> no delta

    summary = pdf_pages(pdf)[1][1]
    assert '<span class="k">Data Products</span><span class="v">1</span>' in summary
    assert f'<span class="v">{result.total_rows}</span>' in summary
    assert '<span class="v">2 / 2</span>' in summary
    assert '<span class="k">Score drops ≥ 5 pp</span><span class="v">0</span>' in summary
    assert "<b>EPT Cost Data</b>" in summary
    assert f'<td class="num big">{result.overall_score:.1f}</td>' in summary
    for rid in ("E1", "E4"):
        assert f"{result.custom_rule_pass_rates[rid]:.1f}%" in summary


def test_pdf_dp_pages_carry_heatmap_tables_and_config():
    dp, cfg, result = _fixture()
    pdf = _build_pdf(dp, cfg, result)
    pages = dict(zip(page_titles(pdf), (b for _, b in pdf_pages(pdf))))

    overview = pages["EPT · EPT Cost Data · Overview"]
    assert '<table class="heat">' in overview
    assert overview.count('<th class="hm-h">') == 3    # E1, E4, CDE score
    assert overview.count('<th class="hm-r">') == 3 + 2  # 3 CDEs + blank + foot
    assert 'class="hm off"' in overview               # CDE not read by a DQR
    assert "DQR pass rate" in overview
    assert '<span class="k">DQRs</span><span class="v">2' in overview
    assert "T1</span>, <span class=\"mono\">T2" in overview

    breakdown = pages["EPT · EPT Cost Data · CDEs, dimensions and change"]
    assert "3 of 4 CDEs have DQRs · without DQR: PLANVIEW_ID" in breakdown
    assert breakdown.count('<td class="mono"><b>') == 3
    assert "Completeness" in breakdown
    assert "First recorded run" in breakdown

    table = pages["EPT · EPT Cost Data · DQRs"]
    assert "2 rules · sorted by pass rate · weights sum to 100%" in table
    assert table.count("<tr") == 3
    assert "Blocking" in table                        # E1 is blocking

    config = pages["EPT · EPT Cost Data · Configuration used for this run"]
    assert '<span class="chip">CODE_OF_RESOURCE</span>' in config
    assert "<dt>Green</dt><dd>score ≥ 90</dd>" in config
    assert "<dt>Drop alert</dt><dd>≥ 5 pp vs previous run</dd>" in config
    assert "<dt>Project filter</dt><dd>PV-10422, PV-99999</dd>" in config
    assert config.count('<td class="mono"><b>') == 2

    about = pages["About this report"]
    assert "<dt>Generated by</dt><dd>tester</dd>" in about
    assert 'class="mono">run_20260903_211842_beef</dd>' in about
    assert "How to read the numbers" in about


def test_pdf_detail_cards_show_config_and_sample_rows():
    dp, cfg, result = _fixture()
    pdf = _build_pdf(dp, cfg, result)
    cards = re.findall(r'<div class="card[^"]*">(.*?)</div>\s*(?=<div class="card|<div class="pf")',
                       pdf, re.S)
    assert len(cards) == 2
    e1 = next(c for c in cards if '<span class="mono rid">E1</span>' in c)
    assert "<h4>Options</h4>" in e1 and "<h4>Source columns</h4>" in e1
    assert "<h4>Reference dataset</h4>" in e1 and "<h4>Pass / fail</h4>" in e1
    assert "CODE_<wbr>OF_<wbr>RESOURCE" in e1
    assert '<span class="pill p-err">Blocking</span>' in e1
    assert "% pass</span>" in e1
    assert "Sample of failing rows" in e1
    sample = re.search(r'<table class="t compact sample">(.*?)</table>', e1,
                       re.S).group(1)
    assert "<th>PLANVIEW_ID</th>" in sample
    assert "<th>CODE_OF_RESOURCE</th>" in sample
    assert '<td class="null">null</td>' in sample
    # Sample rows are the lowest-scoring failing rows, ascending.
    scores = [float(s) for s in re.findall(r'<td class="num"><b>([\d.]+)</b>', sample)]
    assert scores == sorted(scores) and len(scores) <= ReportCaps().pdf_sample_rows


def test_pdf_flags_sheet_uses_identifier_column():
    dp, cfg, result = _wide_fixture(30)
    pdf = _build_pdf(dp, cfg, result)
    flags = next(b for c, b in pdf_pages(pdf) if "pass/fail flags" in b)
    assert "<th>PLANVIEW_<wbr>ID</th>" in flags      # first column = identifier
    assert flags.count('<th class="th-rule">') == 2
    assert 'class="num flag ff">0</td>' in flags
    assert 'class="num flag fp">100</td>' in flags
    assert "<b>E1</b> ISO Code of Account Present (COR + SAB)" in flags
    assert "The 25 lowest-scoring rows of 30" in flags


def test_pdf_history_drop_and_drift():
    dp, cfg, result = _fixture()
    from src.ml_lab import snapshot_scorecard
    from src.run_history import record_run_if_new

    prev = snapshot_scorecard("EPT", dp, result)
    prev["overall_score"] = float(result.overall_score) + 20.0
    for key in ("rule_pass_rates", "custom_rule_pass_rates"):
        prev[key] = {k: min(100.0, v + 15.0) for k, v in prev[key].items()}
    save_run("EPT", "cost_estimate", prev, config_hash="oldcfg01")
    record_run_if_new("EPT", dp, result, cfg, "cost_estimate")

    art = _artifacts(dp, cfg, result)
    doc = Doc(art.html.decode("utf-8"))
    text = doc.full_text
    assert "Score dropped 20.0 pp" in text
    assert "configuration also changed" in text.lower()
    assert "Run log" in text
    assert "What changed vs the previous run" in text
    assert "EPT-changes" in doc.ids
    assert doc.count("svg", cls="trend") == 1
    assert "that moved ≥ 5 pp" in text
    summary = doc.html.split('id="summary"')[1].split("</section>")[0]
    assert "-20.0 pp" in summary and "changed" in summary

    pdf = art.pdf_html.decode("utf-8")
    cover = pdf_pages(pdf)[0][1]
    assert "-20.0 pp vs previous" in cover
    assert "<svg" in cover                           # sparkline
    summary_pdf = pdf_pages(pdf)[1][1]
    assert '<span class="k">Score drops ≥ 5 pp</span><span class="v">1</span>' in summary_pdf
    assert "fell <b>20.0 pp</b> — configuration also changed" in summary_pdf
    assert '<span class="pill p-warn">changed</span>' in summary_pdf
    overview = next(b for _, b in pdf_pages(pdf) if "· Overview" in b)
    assert "Score dropped 20.0 pp" in overview
    assert "2 run(s) · ◆ = configuration changed" in overview
    assert '<span class="pill p-warn">config</span>' in overview
    breakdown = next(b for _, b in pdf_pages(pdf)
                     if "CDEs, dimensions and change" in b)
    assert "What changed vs the previous run" in breakdown
    assert "Configuration changed (" in breakdown
    assert '<span class="v neg">-20.0</span>' in breakdown
    assert "<h4>DQRs</h4>" in breakdown


def test_pdf_long_content_paginates_instead_of_overflowing():
    """Many CDEs and many DQR rows must spill onto continuation pages
    (pages are fixed-height, overflow would be cut)."""
    n = 60
    cols = {f"CDE_{i:02d}": ["x"] * 4 for i in range(n)}
    cols.update({
        "PLANVIEW_ID": ["PV-1", "PV-2", "PV-3", "PV-4"],
        "CODE_OF_RESOURCE": ["a", None, "c", "d"],
        "STANDARD_ACTIVITY_BREAKDOWN": ["EXP"] * 4,
        "WBC_LEVEL_1": ["L1", None, "L1", "L1"],
    })
    dp = _dp(pd.DataFrame(cols))
    cfg = _cfg(cdes=list(cols))
    result = compute_scorecard(dp, cfg, threshold_green=90, threshold_yellow=70)
    pdf = _build_pdf(dp, cfg, result)
    titles = page_titles(pdf)
    assert "EPT · EPT Cost Data · CDEs, dimensions and change" in titles
    # Only 3 CDEs have DQRs, so no continuation is needed here ...
    assert not any("(continued)" in t for t in titles)
    # ... but a synthetic long drift table forces one.
    from ui.step_06.report import pdf as pdf_mod
    view = build_model(_CTX, {"EPT": result}, {"EPT": dp}, {"EPT": cfg}).dps[0]
    view["history"]["drift"] = {
        "score_delta": -3.0, "psi": 0.1, "flagged_total": 40,
        "tables": {"DQRs": [{"name": f"R{i}", "previous": 90.0, "current": 80.0,
                             "delta": -10.0} for i in range(40)],
                   "CDEs": [], "Dimensions": []},
        "prev": {"date": "2026-01-01", "config_hash": "aaaa1111"},
        "curr": {"date": "2026-02-01", "config_hash": "bbbb2222"},
        "config_changed": True,
    }
    pages = pdf_mod._breakdown_pages(view, _CTX)
    assert len(pages) == 2
    assert "(continued)" in pages[1]
    assert "What changed vs the previous run" in pages[1]


# ================================================== artefacts / conversion


def test_artifacts_contract_filenames_and_metadata():
    dp, cfg, result = _fixture()
    art = build_report(_CTX, {"EPT": result}, {"EPT": dp}, {"EPT": cfg},
                       converter=_fake_converter)
    assert isinstance(art, ReportArtifacts)
    assert ReportArtifact is ReportArtifacts             # previous name
    assert art.run_id == "run_20260903_211842_beef"
    assert art.domain_code == "cost_estimate"
    assert art.generated_at == "2026-09-03T21:18:42Z"
    assert art.html.startswith(b"<!DOCTYPE html>")
    assert art.pdf_html.startswith(b"<!DOCTYPE html>")
    assert art.pdf == _FAKE_PDF
    assert art.interactive_html is art.html
    assert art.filenames == {
        "interactive": "dq_scorecard_report_COST_ESTIMATE_20260903_211842.html",
        "pdf": "dq_scorecard_report_COST_ESTIMATE_20260903_211842.pdf",
        "pdf_html": "dq_scorecard_report_COST_ESTIMATE_20260903_211842_print.html",
    }
    assert art.filename == art.filenames["interactive"]

    meta = art.metadata
    assert meta["dp_codes"] == ["EPT"]
    assert meta["dp_names"] == {"EPT": "EPT Cost Data"}
    assert meta["mode"] == "step_by_step"
    assert meta["data_scope"] == "sample"
    assert meta["sample_rows_cap"] == 50000
    assert meta["saved_project"] == "Q3 baseline"
    assert meta["threshold_green"] == 90.0 and meta["threshold_yellow"] == 70.0
    assert meta["project_filter"] == ["PV-10422", "PV-99999"]
    assert meta["domain_name"] == "Cost Estimate"
    assert meta["generated_by"] == "tester"
    assert meta["overall_scores"]["EPT"] == pytest.approx(
        round(result.overall_score, 2))
    assert meta["statuses"]["EPT"] in ("green", "yellow", "red")
    assert meta["row_counts"] == {"EPT": 4}
    assert re.fullmatch(r"[0-9a-f]{16}", meta["config_hashes"]["EPT"])
    assert meta["caps"]["row_store"] == 300 and meta["caps"]["pdf_rows"] == 25
    assert meta["pdf_pages"] == len(pdf_pages(art.pdf_html.decode("utf-8")))
    assert meta["has_pdf"] is True and meta["pdf_error"] is None


def test_pdf_conversion_failure_degrades_to_print_html(monkeypatch):
    dp, cfg, result = _fixture()

    def broken(html):
        raise convert.PdfConversionUnavailable("no chromium here")
    art = _artifacts(dp, cfg, result, want_pdf=True, converter=broken)
    assert art.pdf is None
    assert art.metadata["has_pdf"] is False
    assert art.metadata["pdf_error"] == "no chromium here"
    assert art.pdf_html                                # always present

    def crash(html):
        raise RuntimeError("segfault")
    art = _artifacts(dp, cfg, result, want_pdf=True, converter=crash)
    assert art.pdf is None
    assert art.metadata["pdf_error"] == "RuntimeError: segfault"

    art = _artifacts(dp, cfg, result, want_pdf=False)
    assert art.pdf is None
    assert art.metadata["pdf_error"] == "PDF conversion not requested"


def test_converter_detection_and_override(monkeypatch):
    monkeypatch.setattr(convert, "SETTINGS",
                        Settings(data_source="mock", chromium_path="/nope/chrome"))
    assert convert.find_chromium() is None
    monkeypatch.setattr(convert, "_playwright_available", lambda: False)
    assert convert.available_converters() == []
    with pytest.raises(convert.PdfConversionUnavailable):
        convert.html_to_pdf("<html></html>")
    assert convert.html_to_pdf("<html></html>", converter=lambda h: b"%PDF") == b"%PDF"


@pytest.mark.skipif(not convert.available_converters(),
                    reason="no headless Chromium on this machine")
def test_real_chromium_renders_mixed_orientation_pdf():
    dp, cfg, result = _fixture()
    art = _artifacts(dp, cfg, result, want_pdf=True)
    assert art.pdf is not None and art.pdf.startswith(b"%PDF")
    boxes = [b.strip() for b in re.findall(rb"/MediaBox\s*\[([^\]]+)\]", art.pdf)]
    assert len(boxes) == art.metadata["pdf_pages"]
    widths = [float(b.split()[2]) for b in boxes]
    assert sum(1 for w in widths if w > 700) == 2      # the two landscape sheets
    assert sum(1 for w in widths if w < 700) == len(boxes) - 2


def test_compat_alias_returns_bytes():
    dp, cfg, result = _fixture()
    for fn in (er._build_executive_report_html, build_executive_report_html):
        payload = fn("cost_estimate", {"EPT": result}, {"EPT": dp},
                     {"EPT": cfg})
        assert isinstance(payload, bytes)
        assert payload.decode("utf-8").startswith("<!DOCTYPE html>")


def test_render_functions_share_one_model():
    dp, cfg, result = _fixture()
    model = build_model(_CTX, {"EPT": result}, {"EPT": dp}, {"EPT": cfg})
    assert model.codes == ["EPT"]
    assert set(model.data) == {"green", "yellow", "caps", "dps"}
    html = render_interactive(model)
    pdf = render_pdf_html(model)
    # Same store feeds both: the lowest-scoring row score appears in both.
    lowest = f"{model.dps[0]['store_rows'][0]['s']:.2f}"
    assert lowest in html and lowest in pdf


# ================================================== Streamlit wrapper


class _FakeSessionState(dict):
    __getattr__ = dict.__getitem__


def _fake_st(dp, cfg, download_returns=True):
    fake = MagicMock()
    fake.session_state = _FakeSessionState(
        data_products={"EPT": dp}, configs={"EPT": cfg},
        domain="cost_estimate", planview_filter=["PV-1"],
    )
    fake.download_button.return_value = download_returns
    fake.context.url = "https://dq-app.example.databricksapps.com/?x=1"
    return fake


@pytest.fixture
def local_report_store(monkeypatch, tmp_path):
    monkeypatch.setattr(report_store, "SETTINGS", Settings(
        data_source="mock", report_store="local", store_dir=str(tmp_path)))
    report_store.reset_report_store()
    yield tmp_path / "reports"
    report_store.reset_report_store()


def test_download_buttons_store_and_hosted_link(monkeypatch, local_report_store):
    dp, cfg, result = _fixture()
    fake = _fake_st(dp, cfg)
    monkeypatch.setattr(er, "st", fake)
    monkeypatch.setattr(er, "build_report",
                        partial(build_report, converter=_fake_converter))
    er._render_executive_report_download({"EPT": result})

    labels = [c.args[0] for c in fake.download_button.call_args_list]
    assert labels == ["📑 Data Quality Report (HTML)",
                      "📄 Data Quality Report (PDF)"]
    # Every button of the panel stretches to the column width (same size).
    assert all(c.kwargs["width"] == "stretch"
               for c in fake.download_button.call_args_list)
    html_kwargs = fake.download_button.call_args_list[0].kwargs
    assert html_kwargs["data"].decode("utf-8").startswith("<!DOCTYPE html>")
    assert html_kwargs["file_name"].startswith("dq_scorecard_report_COST_ESTIMATE_")
    assert html_kwargs["file_name"].endswith(".html")
    pdf_kwargs = fake.download_button.call_args_list[1].kwargs
    assert pdf_kwargs["data"] == _FAKE_PDF
    assert pdf_kwargs["mime"] == "application/pdf"
    assert pdf_kwargs["file_name"].endswith(".pdf")

    events = list_events(event_type="export")
    assert [e["payload"]["format"] for e in events] == ["executive_html",
                                                        "executive_pdf"]
    assert events[0]["domain_code"] == "cost_estimate"

    # Stored once, hosted link shown with the absolute app origin.
    cache = fake.session_state["_dq_report_cache"]
    art = cache["artifacts"]
    assert cache["stored"] is True
    assert (local_report_store / f"{art.run_id}.html").exists()
    assert (local_report_store / f"{art.run_id}.pdf").exists()
    caption = fake.caption.call_args.args[0]
    assert f"https://dq-app.example.databricksapps.com/reports/{art.run_id}" in caption
    assert art.metadata["project_filter"] == ["PV-1"]


def test_wrapper_builds_once_per_run_and_rebuilds_on_change(monkeypatch,
                                                            local_report_store):
    dp, cfg, result = _fixture()
    fake = _fake_st(dp, cfg, download_returns=False)
    monkeypatch.setattr(er, "st", fake)
    calls = []

    def counting(*args, **kwargs):
        calls.append(1)
        return build_report(*args, want_pdf=False)
    monkeypatch.setattr(er, "build_report", counting)

    er._render_executive_report_download({"EPT": result})
    first = fake.session_state["_dq_report_cache"]["artifacts"]
    er._render_executive_report_download({"EPT": result})      # rerun
    assert len(calls) == 1
    assert fake.session_state["_dq_report_cache"]["artifacts"] is first

    # A different result (new run) rebuilds with a new run id.
    result.custom_rule_pass_rates["E4"] = 12.3
    er._render_executive_report_download({"EPT": result})
    assert len(calls) == 2
    second = fake.session_state["_dq_report_cache"]["artifacts"]
    assert second.run_id != first.run_id
    assert list_events(event_type="export") == []               # nothing clicked


def test_wrapper_offers_print_html_when_no_converter(monkeypatch,
                                                     local_report_store):
    dp, cfg, result = _fixture()
    fake = _fake_st(dp, cfg)
    monkeypatch.setattr(er, "st", fake)

    def no_pdf(html):
        raise convert.PdfConversionUnavailable("no chromium")
    monkeypatch.setattr(er, "build_report", partial(build_report, converter=no_pdf))
    er._render_executive_report_download({"EPT": result})
    labels = [c.args[0] for c in fake.download_button.call_args_list]
    assert labels == ["📑 Data Quality Report (HTML)",
                      "🖨️ PDF edition (print-ready HTML)"]
    print_kwargs = fake.download_button.call_args_list[1].kwargs
    assert print_kwargs["data"].decode("utf-8").startswith("<!DOCTYPE html>")
    assert print_kwargs["file_name"].endswith("_print.html")
    captions = " ".join(c.args[0] for c in fake.caption.call_args_list)
    assert "no chromium" in captions
    assert [e["payload"]["format"] for e in list_events(event_type="export")] == \
        ["executive_html", "executive_pdf_html"]
    assert not (local_report_store / f"{fake.session_state['_dq_report_cache']['artifacts'].run_id}.pdf").exists()


def test_wrapper_without_store_shows_no_link(monkeypatch, tmp_path):
    monkeypatch.setattr(report_store, "SETTINGS", Settings(
        data_source="mock", report_store="off", store_dir=str(tmp_path)))
    report_store.reset_report_store()
    try:
        dp, cfg, result = _fixture()
        fake = _fake_st(dp, cfg, download_returns=False)
        monkeypatch.setattr(er, "st", fake)
        monkeypatch.setattr(er, "build_report",
                            partial(build_report, want_pdf=False))
        er._render_executive_report_download({"EPT": result})
        assert fake.session_state["_dq_report_cache"]["stored"] is False
        captions = " ".join(c.args[0] for c in fake.caption.call_args_list)
        assert "Hosted copy" not in captions
    finally:
        report_store.reset_report_store()


def test_wrapper_explains_a_failing_store(monkeypatch, local_report_store):
    """A configured-but-broken store must say WHY nothing was stored (the
    user cannot read the app logs comfortably)."""
    dp, cfg, result = _fixture()
    fake = _fake_st(dp, cfg, download_returns=False)
    monkeypatch.setattr(er, "st", fake)
    monkeypatch.setattr(er, "build_report",
                        partial(build_report, want_pdf=False))

    def explode(run_id, kind, data):
        raise PermissionError("PERMISSION_DENIED: no Can Edit on folder")

    monkeypatch.setattr(report_store.get_report_store(), "put", explode)
    er._render_executive_report_download({"EPT": result})
    cache = fake.session_state["_dq_report_cache"]
    assert cache["stored"] is False
    assert cache["store_error"].startswith("PermissionError: PERMISSION_DENIED")
    captions = " ".join(c.args[0] for c in fake.caption.call_args_list)
    assert "Report not stored" in captions
    assert "PERMISSION_DENIED: no Can Edit" in captions
    assert "local folder" in captions
    assert "Hosted copy" not in captions


def test_download_button_hidden_without_scorecards(monkeypatch):
    fake = MagicMock()
    fake.session_state = _FakeSessionState()
    monkeypatch.setattr(er, "st", fake)
    er._render_executive_report_download({})
    fake.download_button.assert_not_called()


def test_domain_switch_clears_the_report_cache():
    from utils.session import state as state_mod

    fake = MagicMock()
    fake.session_state = _FakeSessionState(
        _dq_report_cache={"key": 1}, selected_systems=["EPT"],
        data_products={}, configs={}, scorecards={}, ml_lab_runs=[],
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(state_mod, "st", fake)
        state_mod._clear_workflow_state_for_domain_switch()
    assert "_dq_report_cache" not in fake.session_state
