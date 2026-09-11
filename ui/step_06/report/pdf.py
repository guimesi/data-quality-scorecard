"""PDF edition renderer: the paginated A4 HTML the PDF is printed from.

A port of the handoff's ``reference/generate_pdf.js`` fed by the same
:class:`~ui.step_06.report.models.ReportModel` as the interactive
edition, so both artefacts describe the same records. Page order:

cover → executive summary → per Data Product: overview (gauge,
distribution, trend, run log, CDE × DQR heatmap) · CDEs / dimensions /
what changed · DQR table · DQR detail cards (2 per page: description,
options, columns, reference, sample failing rows) · Lowest-scoring rows
(landscape sheets: values, then DQR flags) · configuration used → About.

Every page is a ``<section class="page">`` sized by ``PDF_CSS``
(``@page A4``; the rows sheets use the named ``land`` page, so headless
Chromium emits mixed orientation from one conversion). Progressive
disclosure is by page order, not by interaction: no JavaScript at all.
Every dynamic string goes through :func:`ui.step_06.report.html.esc`.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from ui.step_06._rule_rows import STATUS_EVALUATED
from ui.step_06._shared import _DEFAULT_ACCENT, _SYSTEM_ACCENTS
from ui.step_06.report import collect
from ui.step_06.report.charts import (
    pdf_gauge_svg,
    pdf_trend_svg,
    spark_svg,
    stack_svg,
)
from ui.step_06.report.html import esc, fmt_cell_number, fmt_int
from ui.step_06.report.models import ReportCaps, ReportContext, ReportModel
from ui.step_06.report.sections import report_title
from ui.step_06.report.styles import PDF_CSS
from ui.step_06.report.tables import selected_options_kv
from utils.helpers import score_bucket

_LABEL = {"green": "Green", "yellow": "Yellow", "red": "Red"}
_SAMPLE_VALUE_CHARS = 40
_SHEET_VALUE_CHARS = 24

# Pagination budget. A4 portrait leaves ~950 px of content between the
# page header and the footer; blocks are costed in estimated pixels
# (measured on rendered pages: compact table row 24 px, 9pt text line
# 16.5 px, kv row 18 px) and packed greedily so no page overflows its
# fixed height (``.page`` is ``overflow:hidden`` - overflowing content
# would be silently cut, not moved to the next page).
_PAGE_PX = 940
_ROW_PX = 24
_TEXT_PX = 16.5
_KV_PX = 18
_CDE_ROWS_PER_CHUNK = 30

# Small additions on top of the verbatim ``PDF_CSS`` (layout safety only):
# the sample tables must never grow wider than the card, and the
# configuration table headers must not collide.
_PDF_CSS_EXTRA = (
    ".sample{table-layout:fixed}.sample th:first-child,.sample td:first-child"
    "{width:56px}table.cfgt th{letter-spacing:0}"
)


# ------------------------------------------------------------- primitives

def _f1(x: float) -> str:
    return f"{float(x):.1f}"


def _pct(part: int, total: int) -> str:
    return f"{part / total * 100:.1f}%" if total else "0.0%"


def _signed(x: float, suffix: str = "") -> str:
    return f"{x:+.1f}{suffix}"


def _badge(score: float, g: float, y: float) -> str:
    b = score_bucket(score, g, y)
    return f'<span class="badge b-{b}"><i></i>{_LABEL[b]}</span>'


def _bucket_badge(bucket: str) -> str:
    return f'<span class="badge b-{bucket}"><i></i>{_LABEL[bucket]}</span>'


def _bar(score: float, g: float, y: float) -> str:
    width = max(0.0, min(100.0, float(score)))
    return (f'<span class="bar"><span class="f-{score_bucket(score, g, y)}" '
            f'style="width:{width:.1f}%"></span></span>')


def _dash() -> str:
    return '<span class="muted">—</span>'


def _cell(value: object, limit: int) -> str:
    """A table cell for a store value (``null`` when missing, numbers
    right-aligned, long strings cut to ``limit`` characters)."""
    if value is None or value == "":
        return '<td class="null">null</td>'
    if isinstance(value, bool):
        return f"<td>{esc(value)}</td>"
    if isinstance(value, (int, float)):
        return f'<td class="num">{_fmt_num(value)}</td>'
    text = str(value)
    if len(text) > limit:
        text = text[:limit - 1] + "…"
    return f"<td>{esc(text)}</td>"


def _fmt_num(value: object) -> str:
    """Numbers as the interactive edition prints them, but floats capped
    at 4 decimals - the fixed-width PDF cells cannot show 17 digits."""
    if isinstance(value, float) and not value.is_integer():
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return fmt_cell_number(value)


def _lines(text: object, per_line: int) -> int:
    """Estimated wrapped lines of ``text`` at ``per_line`` characters."""
    n = len(str(text or ""))
    return (n + per_line - 1) // per_line if n else 0


def _hb(name: str) -> str:
    """Header text with soft breaks after underscores (narrow columns)."""
    return esc(name).replace("_", "_<wbr>")


def _ref_name(column: str) -> str:
    """``COL [DATASET]`` -> ``COL``."""
    return column.split(" [", 1)[0]


def _ref_dataset(column: str) -> str:
    return column.split(" [", 1)[1].rstrip("]") if " [" in column else ""


def _sorted_dqrs(view: Dict) -> List[Dict]:
    """Not-evaluated DQRs first, then ascending pass rate."""
    return sorted(view["dqrs"],
                  key=lambda r: -1.0 if r["pass_rate"] is None else r["pass_rate"])


def _evaluated(view: Dict) -> List[Dict]:
    return [r for r in view["dqrs"] if r["status"] == STATUS_EVALUATED]


def _drop(view: Dict) -> Optional[Dict]:
    return view["history"]["drop"]


# ----------------------------------------------------------- page chrome

def _page_head(ctx: ReportContext, title: str, sub: str = "") -> str:
    domain = ctx.domain_name or ctx.domain_code
    sub_html = f' <span class="muted">· {sub}</span>' if sub else ""
    return (
        '<div class="ph"><span class="ph-k">Data Quality Scorecard · '
        f'{esc(domain)}</span><span class="ph-t">{title}{sub_html}</span></div>'
    )


def _page_foot(ctx: ReportContext) -> str:
    return (
        f'<div class="pf"><span>{esc(report_title(ctx))} · '
        f'{esc((ctx.generated_at or "")[:10])}</span>'
        "<span>Page __PAGE__</span></div>"
    )


# ------------------------------------------------------------------ cover

def _cover(model: ReportModel) -> str:
    ctx = model.ctx
    g, y = ctx.threshold_green, ctx.threshold_yellow
    chips = []
    for v in model.dps:
        score = float(v["result"].overall_score)
        drop = _drop(v)
        delta = (f" · {_signed(drop['delta'], ' pp')} vs previous"
                 if drop is not None else "")
        chips.append(
            f'<div class="cv-dp"><div class="cv-code">{esc(v["code"])}</div>'
            f'<div class="cv-name">{esc(v["name"])}</div>'
            f'<div class="cv-score c-{v["bucket"]}">{_f1(score)}</div>'
            f'<div class="cv-sub">{_LABEL[v["bucket"]]}{esc(delta)}</div>'
            + spark_svg(v["history"]["runs"], g, y, 120, 30) + "</div>"
        )
    projects = " · ".join(esc(p) for p in ctx.project_filter) or "none"
    domain = ctx.domain_name or ctx.domain_code
    return (
        '<section class="page cover"><div class="cv-top">'
        '<span class="cv-kicker">Data Quality Scorecard</span>'
        "<h1>Data Quality<br>Scorecard Report</h1>"
        f'<p class="cv-domain">{esc(domain)}</p></div>\n'
        f'<div class="cv-grid">{"".join(chips)}</div>\n'
        '<dl class="cv-meta"><div><dt>Generated (UTC)</dt>'
        f"<dd>{esc(ctx.generated_at) if ctx.generated_at else '—'}</dd></div>"
        f"<div><dt>Data Products</dt><dd>"
        f"{' · '.join(esc(c) for c in model.codes) or '—'}</dd></div>"
        f"<div><dt>Project filter</dt><dd>{projects}</dd></div>"
        f"<div><dt>Thresholds</dt><dd>Green ≥ {g:g} · Yellow ≥ {y:g} · "
        f"Red &lt; {y:g}</dd></div></dl>\n"
        '<div class="cv-foot">Complete edition · scores, CDEs, every DQR with '
        "its configuration and sample failing rows, lowest-scoring rows, "
        "history and the configuration behind each number. An interactive "
        "version with full drill-downs is available in the Data Quality "
        "Scorecard app.</div></section>"
    )


# ---------------------------------------------------------------- summary

def _summary_page(model: ReportModel) -> str:
    ctx = model.ctx
    g, y = ctx.threshold_green, ctx.threshold_yellow
    dps = model.dps

    rows = []
    for v in dps:
        r = v["result"]
        drop = _drop(v)
        if drop is None:
            delta_cell = f'<td class="num">{_dash()}</td>'
            config_cell = '<td><span class="muted">—</span></td>'
        else:
            cls = "neg" if drop["delta"] < 0 else "pos"
            delta_cell = f'<td class="num {cls}">{_signed(drop["delta"], " pp")}</td>'
            config_cell = ('<td><span class="pill p-warn">changed</span></td>'
                           if drop["config_changed"]
                           else '<td><span class="muted">same</span></td>')
        rows.append(
            f'<tr><td><b>{esc(v["name"])}</b><br><span class="muted mono">'
            f'{esc(v["code"])}</span></td>'
            f'<td class="num big">{_f1(r.overall_score)}</td>'
            f"<td>{_bucket_badge(v['bucket'])}</td>"
            f'<td class="num">{fmt_int(r.total_rows)}</td>'
            f"<td>{stack_svg(r.rows_green, r.rows_yellow, r.rows_red, 200, 10)}"
            f'<div class="dist-l"><span>{_pct(r.rows_green, r.total_rows)}</span>'
            f"<span>{_pct(r.rows_yellow, r.total_rows)}</span>"
            f"<span>{_pct(r.rows_red, r.total_rows)}</span></div></td>"
            + delta_cell
            + f"<td>{spark_svg(v['history']['runs'], g, y)}</td>"
            + config_cell + "</tr>"
        )

    # KPIs
    n_green = sum(1 for v in dps if v["bucket"] == "green")
    n_yellow = sum(1 for v in dps if v["bucket"] == "yellow")
    n_red = sum(1 for v in dps if v["bucket"] == "red")
    total_rows = sum(int(v["result"].total_rows) for v in dps)
    red_rows = sum(int(v["result"].rows_red) for v in dps)
    n_eval = sum(len(_evaluated(v)) for v in dps)
    n_rules = sum(len(v["dqrs"]) for v in dps)
    not_run = [(v, r) for v in dps for r in v["not_run"]]
    drops = [v for v in dps if _drop(v) is not None
             and _drop(v)["delta"] <= -ctx.drop_alert_pp]
    kpis = [
        ("Data Products", str(len(dps)),
         f"{n_green} Green · {n_yellow} Yellow · {n_red} Red"),
        ("Rows evaluated", fmt_int(total_rows),
         f"{fmt_int(red_rows)} Red rows ({_pct(red_rows, total_rows)})"),
        ("DQRs evaluated", f"{n_eval} / {n_rules}",
         f"{len(not_run)} not evaluated"),
        (f"Score drops ≥ {ctx.drop_alert_pp:g} pp", str(len(drops)),
         esc(", ".join(v["code"] for v in drops) or "none")),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><span class="k">{k}</span><span class="v">{v}</span>'
        f'<span class="s">{s}</span></div>' for k, v, s in kpis
    )

    # Needs attention
    attention: List[str] = []
    for v in sorted((v for v in dps if v["bucket"] != "green"),
                    key=lambda v: float(v["result"].overall_score)):
        r = v["result"]
        attention.append(
            f"<li>{_bucket_badge(v['bucket'])} <b>{esc(v['code'])}</b> scores "
            f"<b>{_f1(r.overall_score)}</b>; {fmt_int(r.rows_red)} rows "
            f"({_pct(r.rows_red, r.total_rows)}) are Red.</li>"
        )
    for v in drops:
        drop = _drop(v)
        config = (" — configuration also changed" if drop["config_changed"]
                  else "")
        attention.append(
            f'<li><span class="pill p-err">drop</span> <b>{esc(v["code"])}</b> '
            f"fell <b>{_f1(abs(drop['delta']))} pp</b>{config}.</li>"
        )
    for v, r in not_run:
        attention.append(
            '<li><span class="pill p-warn">not evaluated</span> '
            f'<b>{esc(v["code"])}</b> · <span class="mono">{esc(r["rule_id"])}'
            f"</span> — {esc(r['reason'] or '')}</li>"
        )
    if not attention:
        attention.append('<li class="muted">Nothing to flag.</li>')

    # Lowest-scoring CDEs / DQRs across Data Products
    cdes = sorted(
        ((item, v) for v in dps for item in v["cde_items"]
         if item["score"] is not None and item["bucket"] != "green"),
        key=lambda pair: pair[0]["score"],
    )[:6]
    cde_html = "".join(
        f'<li><span class="w num">{_f1(item["score"])}</span>'
        f"{_bucket_badge(item['bucket'])}"
        f'<span class="mono nw">{esc(v["code"])} {esc(item["name"])}</span></li>'
        for item, v in cdes
    ) or '<li class="muted">All CDEs are Green.</li>'
    rules = sorted(
        ((r, v) for v in dps for r in _evaluated(v)),
        key=lambda pair: pair[0]["pass_rate"],
    )[:6]
    rule_html = "".join(
        f'<li><span class="w num">{_f1(r["pass_rate"])}%</span>'
        f'<span class="mono">{esc(v["code"])} {esc(r["rule_id"])}</span>'
        f'<span title="{esc(r["name"])}">{esc(r["name"])}</span></li>'
        for r, v in rules
    ) or '<li class="muted">No evaluated DQRs.</li>'

    return (
        '<section class="page">' + _page_head(ctx, "Executive summary")
        + f'\n<div class="kpis">{kpi_html}</div>\n'
        '<table class="t exec"><thead><tr><th>Data Product</th>'
        '<th class="num">Score</th><th>Status</th><th class="num">Rows</th>'
        '<th>Green / Yellow / Red</th><th class="num">Δ vs previous</th>'
        "<th>Trend</th><th>Config</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>\n"
        f'<h3>Needs attention</h3><ul class="plain attn">{"".join(attention)}</ul>\n'
        '<div class="cols2 lists"><div><h3>Lowest-scoring CDEs</h3>'
        f'<ul class="plain tight">{cde_html}</ul></div>\n'
        '<div><h3>Lowest pass-rate DQRs</h3>'
        f'<ul class="plain tight">{rule_html}</ul></div>\n</div>'
        + _page_foot(ctx) + "</section>"
    )


# ------------------------------------------------------------- DP pages

def _heatmap(view: Dict) -> str:
    r = view["result"]
    g, y = r.threshold_green, r.threshold_yellow
    rules = view["dqrs"]
    cdes = view["cde_items"]        # unscored first, then ascending score
    if not rules or not cdes:
        return ('<p class="muted">No CDE has a DQR in this run - nothing to '
                "cross-tabulate.</p>")

    def cell(rule: Dict) -> str:
        if rule["status"] != STATUS_EVALUATED:
            return (f'<td class="hm na" title="{esc(rule["rule_id"])} not '
                    'evaluated">n/e</td>')
        pr = rule["pass_rate"]
        return f'<td class="hm hm-{score_bucket(pr, g, y)}">{_f1(pr)}</td>'

    head = "".join(
        f'<th class="hm-h"><div><span>{esc(r_["rule_id"])}</span></div></th>'
        for r_ in rules
    )
    body = []
    for item in cdes:
        tied = set(item["rule_ids"])
        cells = "".join(cell(r_) if r_["rule_id"] in tied else
                        '<td class="hm off"></td>' for r_ in rules)
        if item["score"] is None:
            tail = '<td class="hm-s na">n/e</td>'
        else:
            tail = (f'<td class="hm-s hm-{item["bucket"]}"><b>'
                    f"{_f1(item['score'])}</b></td>")
        body.append(f'<tr><th class="hm-r">{esc(item["name"])}</th>{cells}{tail}</tr>')
    foot = "".join(
        (f'<td class="hm-s hm-{score_bucket(r_["pass_rate"], g, y)}"><b>'
         f"{_f1(r_['pass_rate'])}</b></td>")
        if r_["status"] == STATUS_EVALUATED else '<td class="hm-s na">n/e</td>'
        for r_ in rules
    )
    return (
        '<table class="heat"><thead><tr><th class="hm-r"></th>' + head
        + '<th class="hm-h"><div><span>CDE score</span></div></th></tr></thead>'
        f"<tbody>{''.join(body)}"
        f'<tr class="hm-foot"><th class="hm-r">DQR pass rate</th>{foot}<td></td>'
        "</tr></tbody></table>\n"
        '<p class="cap">A shaded cell means the DQR reads that CDE; the value '
        "is the DQR pass rate. CDE score = mean pass rate of its DQRs. n/e = "
        "not evaluated in this run.</p>"
    )


def _run_log(view: Dict, caps: ReportCaps) -> str:
    runs = view["history"]["runs"]
    if not runs:
        return '<p class="muted">No persisted runs yet.</p>'
    shown = list(reversed(runs))[:caps.pdf_run_log]
    rows = []
    for r_ in shown:
        d = r_["delta"]
        if d is None:
            delta = f'<td class="num">{_dash()}</td>'
        else:
            delta = f'<td class="num {"neg" if d < 0 else "pos"}">{_signed(d)}</td>'
        pill = '<span class="pill p-warn">config</span>' if r_["changed"] else ""
        rows.append(
            f"<tr><td>{esc(r_['date'])}</td><td class=\"muted\">{esc(r_['user'])}"
            f'</td><td class="num"><b>{_f1(r_["score"])}</b></td>{delta}'
            f"<td>{pill}</td></tr>"
        )
    cap = (f'<p class="cap">Last {len(shown)} of {len(runs)} runs.</p>'
           if len(runs) > len(shown) else "")
    return (
        '<table class="t compact"><thead><tr><th>Run</th><th>User</th>'
        '<th class="num">Score</th><th class="num">Δ</th><th></th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>{cap}"
    )


def _alerts(view: Dict, ctx: ReportContext) -> str:
    parts = []
    drop = _drop(view)
    if drop is not None and drop["delta"] <= -ctx.drop_alert_pp:
        config = (" <b>The configuration also changed</b> — see What changed "
                  "before attributing the drop to the data."
                  if drop["config_changed"] else "")
        parts.append(
            f'<div class="callout err"><b>Score dropped {_f1(abs(drop["delta"]))} '
            f"pp</b> vs the previous run ({_f1(drop['prev_score'])} → "
            f"{_f1(drop['curr_score'])}, {esc(str(drop['prev_ts'])[:10])})."
            f"{config}</div>"
        )
    if view["not_run"]:
        ids = ", ".join(f'<span class="mono">{esc(r["rule_id"])}</span>'
                        for r in view["not_run"])
        parts.append(
            f'<div class="callout warn"><b>{len(view["not_run"])} DQR(s) not '
            f"evaluated</b> ({ids}) — excluded from the score, weights "
            "redistributed. Reasons in the DQR table.</div>"
        )
    return "".join(parts)


def _overview_page(view: Dict, ctx: ReportContext) -> str:
    r = view["result"]
    g, y = r.threshold_green, r.threshold_yellow
    total = r.total_rows
    runs = view["history"]["runs"]
    dist = (("green", "Green", r.rows_green, f"≥ {g:g}"),
            ("yellow", "Yellow", r.rows_yellow, f"{y:g}–{g:g}"),
            ("red", "Red", r.rows_red, f"&lt; {y:g}"))
    kpis = (
        f'<div class="kpi"><span class="k">Rows</span><span class="v">'
        f"{fmt_int(total)}</span></div>"
        + "".join(
            f'<div class="kpi"><span class="k"><i class="dot d-{k}"></i>{lbl} '
            f'<span class="muted">{t}</span></span><span class="v">{_pct(n, total)}'
            f'</span><span class="s">{fmt_int(n)} rows</span></div>'
            for k, lbl, n, t in dist
        )
        + f'<div class="kpi"><span class="k">DQRs</span><span class="v">'
        f'{len(_evaluated(view))}<span class="muted"> / {len(view["dqrs"])}'
        f'</span></span><span class="s">evaluated</span></div>'
    )
    sources = ", ".join(f'<span class="mono">{esc(t)}</span>'
                        for t in view["source_tables"]) or "—"
    if runs:
        trend = (f'<h3>Score trend <span class="muted">{len(runs)} run(s) · '
                 "◆ = configuration changed</span></h3>"
                 + pdf_trend_svg(runs, g, y))
    else:
        trend = ('<h3>Score trend</h3><p class="muted">No persisted runs yet '
                 "- the trend appears once runs are recorded.</p>")
    return (
        _page_head(ctx, f"{esc(view['code'])} · {esc(view['name'])}", "Overview")
        + '\n<div class="dp-hero"><div class="dp-g">'
        + pdf_gauge_svg(r.overall_score, g, y, 170)
        + f"<div>{_bucket_badge(view['bucket'])}</div></div>\n"
        f'<div class="dp-dist"><div class="kpis sm">{kpis}</div>'
        + stack_svg(r.rows_green, r.rows_yellow, r.rows_red, 460, 16)
        + f'<p class="cap">{fmt_int(view["n_cols"])} columns · {sources}</p>'
        "</div></div>\n"
        + _alerts(view, ctx)
        + f'\n<div class="cols2 trendrow"><div>{trend}</div>'
        f"<div><h3>Run log</h3>{_run_log(view, ctx.caps)}</div></div>\n"
        f"<h3>CDE × DQR heatmap</h3>{_heatmap(view)}"
    )


def _breakdown_pages(view: Dict, ctx: ReportContext) -> List[str]:
    """By CDE / By dimension / What changed, packed into as many pages as
    the content needs (long CDE lists and drift tables never overflow)."""
    r = view["result"]
    g, y = r.threshold_green, r.threshold_yellow

    def score_cells(item: Dict) -> str:
        if item["score"] is None:
            return (f"<td>{_dash()}</td><td class=\"num\"><b>n/e</b></td>"
                    '<td><span class="pill p-warn">Not evaluated</span></td>')
        return (f"<td>{_bar(item['score'], g, y)}</td>"
                f'<td class="num"><b>{_f1(item["score"])}</b></td>'
                f"<td>{_bucket_badge(item['bucket'])}</td>")

    cde_rows = [
        f'<tr><td class="mono"><b>{esc(item["name"])}</b></td>{score_cells(item)}'
        f'<td class="num">{item["n_evaluated"]}/{item["n_tied"]}</td>'
        f'<td class="mono muted">{esc(", ".join(item["rule_ids"]))}</td></tr>'
        for item in view["cde_items"]
    ]
    without = view["cdes_without_dqr"]
    without_txt = (" · without DQR: " + ", ".join(esc(c) for c in without)
                   if without else "")
    cde_heading = (
        f'<h3>By CDE <span class="muted">{len(view["cde_items"])} of '
        f'{view["n_cdes"]} CDEs have DQRs{without_txt}</span></h3>\n'
    )

    def cde_table(rows: List[str], cont: bool) -> str:
        if not rows:
            return cde_heading + '<p class="muted">No CDE has a DQR in this run.</p>'
        head = (cde_heading if not cont else
                '<h3>By CDE <span class="muted">continued</span></h3>\n')
        return (
            head + '<table class="t compact"><thead><tr><th>CDE</th><th>Score</th>'
            '<th class="num"></th><th>Status</th><th class="num">DQRs</th>'
            f"<th>Rule IDs</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )
    dim_rows = "".join(
        f"<tr><td>{esc(item['name'])}</td>{score_cells(item)}</tr>"
        for item in view["dim_items"]
    )
    dim_table = (
        f'<table class="t compact dims"><tbody>{dim_rows}</tbody></table>'
        if view["dim_items"] else
        '<p class="muted">No dimensions scored for this Data Product.</p>'
    )

    # What changed
    drift = view["history"]["drift"]
    if drift is None:
        changed = ('<div class="box"><h3>What changed</h3><p class="muted">'
                   "First recorded run — no comparison available.</p></div>")
    else:
        d = drift["score_delta"]
        prev, curr = drift["prev"], drift["curr"]
        warn = ""
        if drift["config_changed"]:
            warn = (
                '<p class="cfg-warn">Configuration changed (<span class="mono">'
                f'{esc(prev["config_hash"][:8])}</span> → <span class="mono">'
                f'{esc(curr["config_hash"][:8])}</span>). Part of the movement '
                "may come from rule / weight changes, not from the data.</p>"
            )
        psi = "—" if drift["psi"] is None else f"{drift['psi']:.3f}"

        def table(label: str) -> str:
            rows = drift["tables"].get(label) or []
            if not rows:
                return f'<h4>{label}</h4><p class="muted">none</p>'
            body = "".join(
                f"<tr><td>{esc(t['name'])}</td>"
                f'<td class="num muted nw">{_f1(t["previous"])} →</td>'
                f'<td class="num nw"><b>{_f1(t["current"])}</b></td>'
                f'<td class="num {"neg" if t["delta"] < 0 else "pos"}">'
                f"{_signed(t['delta'])}</td></tr>"
                for t in rows
            )
            return (f"<h4>{label}</h4>"
                    f'<table class="t compact"><tbody>{body}</tbody></table>')

        detail = (
            f'<div class="cols2 drift"><div>{table("DQRs")}</div>'
            f'<div>{table("CDEs")}{table("Dimensions")}</div></div>'
            if drift["flagged_total"] else
            '<p class="muted">Nothing moved ≥ 5 pp.</p>'
        )
        changed = (
            '<div class="box"><h3>What changed vs the previous run '
            f'<span class="muted">{esc(prev["date"])} → {esc(curr["date"])}'
            f"</span></h3>{warn}"
            '<div class="kpis sm"><div class="kpi"><span class="k">Score Δ</span>'
            f'<span class="v {"neg" if d < 0 else "pos"}">{_signed(d)}</span></div>'
            f'<div class="kpi"><span class="k">PSI</span><span class="v">{psi}'
            "</span></div>"
            '<div class="kpi"><span class="k">Flagged (|Δ| ≥ 5 pp)</span>'
            f'<span class="v">{drift["flagged_total"]}</span></div></div>'
            f"{detail}</div>"
        )
    # Blocks with their estimated height in px, packed greedily.
    blocks: List[Tuple[float, str]] = []
    chunks = [cde_rows[i:i + _CDE_ROWS_PER_CHUNK]
              for i in range(0, len(cde_rows), _CDE_ROWS_PER_CHUNK)] or [[]]
    for k, chunk in enumerate(chunks):
        blocks.append((62 + _ROW_PX * len(chunk), cde_table(chunk, cont=k > 0)))
    blocks.append((40 + _ROW_PX * max(1, len(view["dim_items"])),
                   "\n<h3>By dimension</h3>" + dim_table))
    if drift is None:
        changed_cost = 110.0
    else:
        tables = drift["tables"]
        left = 40 * len(tables.get("DQRs") or [])
        right = (_ROW_PX * (len(tables.get("CDEs") or [])
                            + len(tables.get("Dimensions") or [])) + 60)
        changed_cost = 200 + (max(left, right) if drift["flagged_total"] else 24)
    blocks.append((changed_cost, "\n" + changed))

    pages: List[str] = []
    current: List[str] = []
    used = 0.0
    for cost, html in blocks:
        if current and used + cost > _PAGE_PX:
            pages.append("".join(current))
            current, used = [], 0.0
        current.append(html)
        used += cost
    if current:
        pages.append("".join(current))
    title = f"{esc(view['code'])} · {esc(view['name'])}"
    return [
        _page_head(ctx, title, "CDEs, dimensions and change"
                   + (" (continued)" if i else "")) + "\n" + body
        for i, body in enumerate(pages)
    ]


def _dqr_table_page(view: Dict, ctx: ReportContext) -> str:
    r = view["result"]
    g, y = r.threshold_green, r.threshold_yellow
    rows = []
    for rule in _sorted_dqrs(view):
        ok = rule["status"] == STATUS_EVALUATED
        reason = ("" if ok else
                  f'<div class="reason">Not evaluated — {esc(rule["reason"] or "")}</div>')
        blocking = '<span class="pill p-err">Blocking</span>' if rule["blocking"] else ""
        bar = _bar(rule["pass_rate"], g, y) if ok else _dash()
        rate = (f"{_f1(rule['pass_rate'])}%" if ok
                else '<span class="pill p-warn">n/e</span>')
        fails = fmt_int(rule["fail_count"] or 0) if ok else "—"
        rows.append(
            f'<tr class="{"" if ok else "ne"}"><td class="mono"><b>'
            f'{esc(rule["rule_id"])}</b></td><td>{esc(rule["name"])}{reason}</td>'
            f'<td class="muted">{esc(rule["type"])}</td><td>{blocking}</td>'
            f'<td class="num">{_f1(rule["weight"])}%</td><td>{bar}</td>'
            f'<td class="num">{rate}</td><td class="num">{fails}</td></tr>'
        )
    weight_sum = sum(rule["weight"] for rule in view["dqrs"])
    table = (
        '<table class="t rules"><thead><tr><th>ID</th><th>Rule</th><th>Type</th>'
        '<th></th><th class="num">Weight</th><th>Pass rate</th>'
        '<th class="num"></th><th class="num">Failing rows</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
        if rows else '<p class="muted">No DQRs selected for this Data Product.</p>'
    )
    return (
        _page_head(ctx, f"{esc(view['code'])} · {esc(view['name'])}", "DQRs")
        + f'\n<h3>DQRs <span class="muted">{len(view["dqrs"])} rules · sorted by '
        f"pass rate · weights sum to {weight_sum:.0f}%</span></h3>\n" + table
        + '\n<p class="cap">Each DQR is detailed on the following pages: '
        "description, configuration, source columns, reference dataset and a "
        "sample of the lowest-scoring rows that fail it.</p>"
    )


def _card(view: Dict, rule: Dict, ctx: ReportContext) -> str:
    r = view["result"]
    g, y = r.threshold_green, r.threshold_yellow
    ok = rule["status"] == STATUS_EVALUATED
    rule_def = rule["rule"]
    status = (
        f'<span class="badge b-{score_bucket(rule["pass_rate"], g, y)}"><i></i>'
        f'{_f1(rule["pass_rate"])}% pass</span>' if ok else
        '<span class="pill p-warn">Not evaluated</span>'
    )
    blocking = '<span class="pill p-err">Blocking</span>' if rule["blocking"] else ""
    reason = ("" if ok else
              f'<p class="reason"><b>Not evaluated.</b> {esc(rule["reason"] or "")} '
              "The DQR was excluded and its weight redistributed; this is not a "
              "failure.</p>")
    desc = notes = ""
    if rule_def is not None:
        desc = f'<p class="desc">{esc(rule_def.description)}</p>'
        if rule_def.notes:
            notes = f'<p class="desc muted">{esc(rule_def.notes)}</p>'
    src = rule.get("source_columns") or {}
    src_kv = ('<dl class="kv">' + "".join(
        f'<dt>{esc(k)}</dt><dd class="mono">{_hb(str(v))}</dd>' for k, v in src.items()
    ) + "</dl>") if src else '<p class="muted">none</p>'
    ref = getattr(rule_def, "reference", None) if rule_def is not None else None
    ref_kv = (
        f'<dl class="kv"><dt>Dataset</dt><dd class="mono">'
        f'{esc(ref.get("reference_dataset", "—"))}</dd><dt>Join</dt>'
        f'<dd class="mono">{esc(ref.get("source_column", "—"))} → '
        f'{esc(ref.get("reference_column", "—"))}</dd></dl>'
        if ref else '<p class="muted">none</p>'
    )
    passfail = (
        f'<h4>Pass / fail</h4><p class="m0">{fmt_int(rule["pass_count"] or 0)} / '
        f'{fmt_int(rule["fail_count"] or 0)} rows</p>' if ok else ""
    )
    return (
        f'<div class="card{"" if ok else " card-ne"}"><div class="card-h">'
        f'<span class="mono rid">{esc(rule["rule_id"])}</span>'
        f'<b class="card-t">{esc(rule["name"])}</b>{blocking}{status}'
        f'<span class="muted">w={_f1(rule["weight"])}% · {esc(rule["type"])}</span>'
        f"</div>\n{reason}{desc}{notes}\n"
        f'<div class="cols3 cfg"><div><h4>Options</h4>'
        f'{selected_options_kv(rule_def, rule["params"])}</div>'
        f"<div><h4>Source columns</h4>{src_kv}</div>"
        f"<div><h4>Reference dataset</h4>{ref_kv}{passfail}</div></div>\n"
        + (_sample_table(view, rule, ctx.caps) if ok else "") + "</div>"
    )


def _sample_table(view: Dict, rule: Dict, caps: ReportCaps) -> str:
    fail_total = rule["fail_count"] or 0
    if not fail_total:
        return '<p class="cap">No row fails this DQR.</p>'
    rows = collect.sample_failing_rows(view, rule["rule_id"], caps.pdf_sample_rows)
    if not rows:
        return (f'<p class="cap">{fmt_int(fail_total)} rows fail this DQR, none '
                f"among the {fmt_int(len(view['store_rows']))} lowest-scoring "
                "rows embedded in this report.</p>")
    col_idx = collect.sample_columns(view, rule)
    ref_idx = collect.reference_columns_for_rule(view, rule)
    head = (
        '<th class="num">Row score</th>'
        + "".join(f"<th>{esc(view['columns'][i])}</th>" for i in col_idx)
        + "".join(f'<th class="ref">{esc(_ref_name(view["ref_columns"][i]))}</th>'
                  for i in ref_idx)
    )
    body = "".join(
        f'<tr><td class="num"><b>{row["s"]:.2f}</b></td>'
        + "".join(_cell(row["v"][i], _SAMPLE_VALUE_CHARS) for i in col_idx)
        + "".join(_cell(row["r"][i], _SAMPLE_VALUE_CHARS) for i in ref_idx)
        + "</tr>"
        for row in rows
    )
    return (
        f'<h4>Sample of failing rows <span class="muted">{len(rows)} of '
        f"{fmt_int(fail_total)} · lowest row score first</span></h4>"
        f'<table class="t compact sample"><thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table>"
    )


def _card_cost(view: Dict, rule: Dict, caps: ReportCaps) -> float:
    """Estimated height of a DQR detail card in px (see ``_PAGE_PX``)."""
    ok = rule["status"] == STATUS_EVALUATED
    rule_def = rule["rule"]
    desc = getattr(rule_def, "description", "") if rule_def is not None else ""
    notes = getattr(rule_def, "notes", "") if rule_def is not None else ""
    src = rule.get("source_columns") or {}
    n_opts = (len(rule_def.options) + len(rule_def.select_options)
              if rule_def is not None else 0)
    src_lines = sum(max(_lines(alias, 16), _lines(col, 13)) for alias, col in src.items())
    ref_lines = 2 if getattr(rule_def, "reference", None) else 1
    cost = 115.0 + (30 if not ok else 0)
    cost += _TEXT_PX * (_lines(desc, 105) + _lines(notes, 105))
    cost += _KV_PX * max(n_opts or 1, src_lines or 1, ref_lines + (3 if ok else 0))
    if ok:
        n_sample = min(len(collect.sample_failing_rows(view, rule["rule_id"],
                                                       caps.pdf_sample_rows)),
                       caps.pdf_sample_rows)
        cost += 22 + 23 * n_sample if n_sample else 20
    return cost


def _detail_pages(view: Dict, ctx: ReportContext) -> List[str]:
    """DQR detail cards packed greedily by estimated height (a page holds as
    many cards as fit; a very long card gets a page of its own)."""
    rules = _sorted_dqrs(view)
    groups: List[List[Dict]] = []
    current: List[Dict] = []
    used = 0.0
    for rule in rules:
        cost = _card_cost(view, rule, ctx.caps)
        if current and used + cost > _PAGE_PX:
            groups.append(current)
            current, used = [], 0.0
        current.append(rule)
        used += cost
    if current:
        groups.append(current)
    title = f"{esc(view['code'])} · {esc(view['name'])}"
    return [
        _page_head(ctx, title, f"DQR detail {i + 1}/{len(groups)}")
        + "".join(_card(view, rule, ctx) for rule in group)
        for i, group in enumerate(groups)
    ]


def _lead_cells(row: Dict) -> str:
    return (f'<td class="num"><b>{row["s"]:.2f}</b></td>'
            f"<td>{_bucket_badge(row['b'])}</td>")


def _column_chunks(view: Dict, caps: ReportCaps) -> List[List[Tuple[str, int, str]]]:
    """The values sheets' data columns as ``(kind, index, header)`` chunks
    (``kind`` = ``v`` for Data Product columns, ``r`` for reference ones)."""
    cols: List[Tuple[str, int, str]] = (
        [("v", i, c) for i, c in enumerate(view["columns"])]
        + [("r", i, c) for i, c in enumerate(view["ref_columns"])]
    )
    size = max(1, caps.pdf_sheet_columns)
    return [cols[i:i + size] for i in range(0, len(cols), size)] or [[]]


def _values_sheets(view: Dict, ctx: ReportContext) -> List[str]:
    caps = ctx.caps
    rows = view["store_rows"][:caps.pdf_rows]
    total = view["result"].total_rows
    title = f"{esc(view['code'])} · {esc(view['name'])}"
    intro = (
        f'<p class="cap m0">The {len(rows)} lowest-scoring rows of '
        f"{fmt_int(total)}, ascending by row score. The CSV export and the "
        "interactive report carry more rows.</p>"
    )
    if not rows:
        return [_page_head(ctx, title, "Lowest-scoring rows · values")
                + '<p class="muted">No rows scored for this Data Product.</p>']
    chunks = _column_chunks(view, caps)
    n_cols = len(view["columns"]) + len(view["ref_columns"])
    datasets = []
    for c in view["ref_columns"]:
        ds = _ref_dataset(c)
        if ds and ds not in datasets:
            datasets.append(ds)
    legend = " · ".join(
        f"<b>{esc(ds)}</b>: " + ", ".join(
            esc(_ref_name(c)) for c in view["ref_columns"] if _ref_dataset(c) == ds)
        for ds in datasets
    )
    sheets = []
    for k, chunk in enumerate(chunks):
        first = sum(len(c) for c in chunks[:k]) + 1
        last = first + len(chunk) - 1
        sub = "Lowest-scoring rows · values"
        if len(chunks) > 1:
            sub += f" · columns {first}–{last} of {n_cols}"
        head = "".join(
            (f'<th class="th-ref">{_hb(_ref_name(c))}</th>' if kind == "r"
             else f"<th>{_hb(c)}</th>")
            for kind, _, c in chunk
        )
        body = "".join(
            "<tr>" + _lead_cells(row)
            + "".join(_cell(row[kind][i], _SHEET_VALUE_CHARS) for kind, i, _ in chunk)
            + "</tr>"
            for row in rows
        )
        has_ref = any(kind == "r" for kind, _, _ in chunk)
        legend_html = (
            f'<p class="cap">Blue headers are reference-dataset fields joined '
            f"by the DQRs — {legend}.</p>" if has_ref and legend else ""
        )
        sheets.append(
            _page_head(ctx, title, sub) + intro
            + f'\n<div class="rows-wrap"><table class="t rows" style="--cols:{2 + len(chunk)}">'
            f"<thead><tr><th>row score</th><th>status</th>{head}</tr></thead>"
            f"<tbody>{body}</tbody></table></div>\n{legend_html}"
        )
    return sheets


def _flags_sheet(view: Dict, ctx: ReportContext) -> str:
    caps = ctx.caps
    rows = view["store_rows"][:caps.pdf_rows]
    total = view["result"].total_rows
    title = f"{esc(view['code'])} · {esc(view['name'])}"
    head_title = "Lowest-scoring rows · DQR pass/fail flags"
    if not rows:
        return (_page_head(ctx, title, head_title)
                + '<p class="muted">No rows scored for this Data Product.</p>')
    id_idx = collect.id_column_index(view)
    id_name = view["columns"][id_idx] if view["columns"] else "row"
    by_id = {r["rule_id"]: r for r in view["dqrs"]}
    specs = view["rule_specs"]
    head = "".join(
        f'<th class="th-rule">{esc(rid)}<br><span class="muted">'
        f'w={_f1(by_id[rid]["weight"]) if rid in by_id else "?"}%</span></th>'
        for rid, _ in specs
    )
    body = "".join(
        "<tr>" + _lead_cells(row)
        + _cell(row["v"][id_idx] if view["columns"] else None, _SHEET_VALUE_CHARS)
        + "".join(f'<td class="num flag {"fp" if f else "ff"}">{100 if f else 0}</td>'
                  for f in row["f"])
        + "</tr>"
        for row in rows
    )
    legend = " · ".join(
        f"<b>{esc(rid)}</b> {esc(by_id[rid]['name'])}" for rid, _ in specs
        if rid in by_id
    )
    intro = (
        f'<p class="cap m0">The {len(rows)} lowest-scoring rows of '
        f"{fmt_int(total)}, ascending by row score. The CSV export and the "
        "interactive report carry more rows.</p>"
    )
    return (
        _page_head(ctx, title, head_title) + intro
        + f'\n<div class="rows-wrap"><table class="t rows flags" style="--cols:{3 + len(specs)}">'
        f"<thead><tr><th>row_score</th><th>status</th><th>{_hb(id_name)}</th>{head}"
        f"</tr></thead><tbody>{body}</tbody></table></div>\n"
        '<p class="cap">100 = the row passes the DQR, 0 = it fails; w = the '
        "DQR's share of the row score. DQRs not evaluated in this run have no "
        f"column. {legend}</p>"
    )


def _config_page(view: Dict, ctx: ReportContext) -> str:
    r = view["result"]
    cfg = view["cfg"]
    g, y = r.threshold_green, r.threshold_yellow
    chips = "".join(f'<span class="chip">{esc(c)}</span>' for c in cfg.cdes) \
        or '<span class="muted">none</span>'
    sources = "<br>".join(f'<span class="mono">{esc(t)}</span>'
                          for t in view["source_tables"]) or "—"
    projects = ", ".join(esc(p) for p in ctx.project_filter) or "none"

    def params_html(rule: Dict) -> str:
        params = rule["params"] or {}
        if not params:
            return '<span class="muted">defaults</span>'
        return "<br>".join(f"{esc(k)}={esc(v)}" for k, v in params.items())

    rows = "".join(
        f'<tr><td class="mono"><b>{esc(rule["rule_id"])}</b></td>'
        f"<td>{esc(rule['name'])}</td><td class=\"muted\">{esc(rule['type'])}</td>"
        f"<td>{'yes' if rule['blocking'] else ''}</td>"
        f'<td class="num">{_f1(rule["weight"])}%</td>'
        f'<td class="mono sm">{params_html(rule)}</td>'
        f'<td class="mono sm">'
        f"{esc(', '.join(str(c).split(' ')[0] for c in (rule.get('source_columns') or {}).values()))}"
        "</td></tr>"
        for rule in view["dqrs"]
    )
    weight_sum = sum(rule["weight"] for rule in view["dqrs"])
    table = (
        '<table class="t compact cfgt"><colgroup><col style="width:38px">'
        '<col style="width:30%"><col style="width:13%"><col style="width:58px">'
        '<col style="width:56px"><col><col style="width:22%"></colgroup>'
        "<thead><tr><th>Rule</th><th>Name</th><th>Type</th><th>Blocking</th>"
        '<th class="num">Weight</th><th>Options</th><th>Columns</th></tr></thead>'
        f"<tbody>{rows}</tbody></table>"
        if rows else '<p class="muted">No DQRs configured.</p>'
    )
    return (
        _page_head(ctx, f"{esc(view['code'])} · {esc(view['name'])}",
                   "Configuration used for this run")
        + f'\n<p class="cap m0">Configuration <span class="mono">'
        f'{esc(view["config_hash"])}</span> — every number in this Data '
        "Product's pages was produced with exactly this set-up.</p>\n"
        '<div class="cols2"><div><h3>Critical Data Elements '
        f'<span class="muted">{len(cfg.cdes)}</span></h3>'
        f'<div class="chips">{chips}</div>'
        f'<h3>Thresholds</h3><dl class="kv"><dt>Green</dt><dd>score ≥ {g:g}</dd>'
        f"<dt>Yellow</dt><dd>score ≥ {y:g}</dd><dt>Red</dt><dd>score &lt; {y:g}"
        f"</dd><dt>Drop alert</dt><dd>≥ {ctx.drop_alert_pp:g} pp vs previous run"
        "</dd></dl></div>\n"
        '<div><h3>Data Product</h3><dl class="kv"><dt>System code</dt>'
        f'<dd class="mono">{esc(view["code"])}</dd><dt>Name</dt>'
        f"<dd>{esc(view['name'])}</dd><dt>Rows</dt><dd>{fmt_int(view['n_rows'])}"
        f"</dd><dt>Columns</dt><dd>{fmt_int(view['n_cols'])}</dd>"
        f"<dt>Source tables</dt><dd>{sources}</dd><dt>Project filter</dt>"
        f"<dd>{projects}</dd></dl></div></div>\n"
        f'<h3>DQR assignments <span class="muted">{len(view["dqrs"])} rules · '
        f"weights sum to {weight_sum:.0f}%</span></h3>\n" + table
    )


def _dp_pages(view: Dict, ctx: ReportContext) -> List[Tuple[str, str]]:
    """``(page classes, body)`` for one Data Product."""
    pages: List[Tuple[str, str]] = [
        ("dp", _overview_page(view, ctx)),
    ]
    pages += [("dp", body) for body in _breakdown_pages(view, ctx)]
    pages.append(("dp", _dqr_table_page(view, ctx)))
    pages += [("dp", body) for body in _detail_pages(view, ctx)]
    pages += [("dp land", body) for body in _values_sheets(view, ctx)]
    pages.append(("dp land", _flags_sheet(view, ctx)))
    pages.append(("dp", _config_page(view, ctx)))
    return pages


# ------------------------------------------------------------------ about

def _about_page(model: ReportModel) -> str:
    ctx = model.ctx
    g, y = ctx.threshold_green, ctx.threshold_yellow
    domain = ctx.domain_name or ctx.domain_code
    dps = "<br>".join(f"{esc(v['code'])} — {esc(v['name'])}" for v in model.dps) \
        or "—"
    configs = "<br>".join(
        f'<span class="mono">{esc(v["code"])} {esc(v["config_hash"])}</span>'
        for v in model.dps
    ) or "—"
    projects = ", ".join(esc(p) for p in ctx.project_filter) or "none"
    caps = ctx.caps
    return (
        '<section class="page">' + _page_head(ctx, "About this report")
        + '\n<div class="cols2"><div><h3>Scope of this run</h3><dl class="kv">'
        f'<dt>Domain</dt><dd>{esc(domain)} <span class="mono">'
        f'{esc(ctx.domain_code)}</span></dd><dt>Data Products</dt><dd>{dps}</dd>'
        f"<dt>Project filter</dt><dd>{projects}</dd><dt>Generated (UTC)</dt>"
        f"<dd>{esc(ctx.generated_at) if ctx.generated_at else '—'}</dd>"
        f"<dt>Generated by</dt><dd>{esc(ctx.generated_by) if ctx.generated_by else '—'}"
        f'</dd><dt>Run identifier</dt><dd class="mono">'
        f"{esc(ctx.run_id) if ctx.run_id else '—'}</dd>"
        f"<dt>Configurations</dt><dd>{configs}</dd></dl>"
        f'<h3>What this edition contains</h3><p class="cap m0">Per Data Product: '
        f"the {caps.pdf_rows} lowest-scoring rows (values and DQR flags), up to "
        f"{caps.pdf_sample_rows} sample failing rows per DQR and the last "
        f"{caps.pdf_run_log} runs of the run log. The interactive edition embeds "
        f"the {caps.row_store} lowest-scoring rows per Data Product; the CSV "
        "export carries every row.</p></div>\n"
        '<div><h3>How to read the numbers</h3><ul class="notes">'
        "<li><b>Row score</b> — weighted pass/fail of the evaluated DQRs for one "
        "row (100 = all pass). <b>Overall score</b> — mean row score.</li>"
        f"<li><b>Status</b> — Green ≥ {g:g}, Yellow ≥ {y:g}, Red &lt; {y:g}; "
        "applied to rows, CDEs, dimensions and Data Products alike.</li>"
        "<li><b>CDE / dimension score</b> — unweighted mean of the pass rates of "
        "the DQRs tied to them.</li>"
        "<li><b>Not evaluated</b> — the DQR could not run (missing column, empty "
        "sample…). It is excluded and its weight redistributed; it is <em>not</em> "
        "a failure.</li>"
        "<li><b>Configuration changed</b> — the rule set or weights differ from "
        "the previous run; compare scores with care.</li>"
        "<li><b>PSI</b> — population stability index of the row-score "
        "distribution vs the previous run (≥ 0.1 notable, ≥ 0.25 major).</li></ul>"
        "<h3>Where to go deeper</h3><p>The interactive report in the Data Quality "
        "Scorecard app adds full drill-downs (every failing row per CDE, "
        "dimension and DQR, up to the embedded cap), search and filters, and the "
        "complete run log.</p></div></div>\n"
        + _page_foot(ctx) + "</section>"
    )


# ------------------------------------------------------------ document

def render_pdf_html(model: ReportModel) -> str:
    """The complete paginated HTML of the PDF edition."""
    ctx = model.ctx
    pages: List[str] = [_cover(model), _summary_page(model)]
    for view in model.dps:
        accent = _SYSTEM_ACCENTS.get(view["code"], _DEFAULT_ACCENT)
        for cls, body in _dp_pages(view, ctx):
            pages.append(
                f'<section class="page {cls}" style="--accent:{accent}">'
                f"{body}{_page_foot(ctx)}</section>"
            )
    pages.append(_about_page(model))
    numbered = [p.replace("__PAGE__", str(i + 1), 1) for i, p in enumerate(pages)]
    title = f"{report_title(ctx)} · PDF edition · {(ctx.generated_at or '')[:10]}"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{esc(title)}</title><style>{PDF_CSS}{_PDF_CSS_EXTRA}</style>"
        "</head><body>\n"
        + "\n".join(numbered) + "\n</body></html>"
    )


def count_pages(pdf_html: str) -> int:
    return pdf_html.count('<section class="page')


__all__: Sequence[str] = ("render_pdf_html", "count_pages")
