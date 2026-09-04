"""Table / list renderers for the Data Quality Report.

Every renderer returns an HTML string using the handoff's exact class
vocabulary (``.gl``, ``.gl-row``, ``.drill``, ``.tv``, ``table.rows``,
``table.compact`` ...) - the embedded CSS and JS select on these names.
All dynamic strings go through :func:`ui.step_06.report.html.esc`,
attributes included.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from ui.step_06._rule_rows import STATUS_EVALUATED
from ui.step_06.report.charts import score_bar
from ui.step_06.report.html import esc, fmt_cell_number, fmt_int

_BUCKET_LABELS = {"green": "Green", "yellow": "Yellow", "red": "Red"}

_NOSCRIPT = (
    "<noscript>Failing-row tables need JavaScript; the "
    '<a href="#{code}-rows">Worst rows</a> table below and the CSV export '
    "carry the same records.</noscript>"
)


def badge(bucket: str) -> str:
    return (f'<span class="badge b-{bucket}"><i></i>'
            f"{_BUCKET_LABELS[bucket]}</span>")


def status_pill(status: str) -> str:
    cls = "p-ok" if status == STATUS_EVALUATED else "p-warn"
    return f'<span class="pill {cls}">{esc(status)}</span>'


def _fmt_param(value: object) -> str:
    if value is None:
        return '<span class="null">null</span>'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set, frozenset)):
        return f"{len(value):,} value(s)"
    if isinstance(value, dict):
        return esc(" · ".join(f"{k}={v}" for k, v in value.items()))
    return esc(value)


def params_kv(params: Dict) -> str:
    if not params:
        return '<span class="muted">none</span>'
    return ('<dl class="kv">' + "".join(
        f"<dt>{esc(k)}</dt><dd>{_fmt_param(v)}</dd>" for k, v in params.items()
    ) + "</dl>")


def selected_options_kv(rule, params: Dict) -> str:
    """The custom rule's toggles / selects with the values used this run."""
    if rule is None or not (rule.options or rule.select_options):
        return '<span class="muted">none</span>'
    parts = []
    for opt in rule.options:
        value = bool(params.get(opt.key, opt.default))
        parts.append(f"<dt>{esc(opt.key)}</dt>"
                     f"<dd>{'true' if value else 'false'}</dd>")
    for opt in rule.select_options:
        value = params.get(opt.key, opt.default)
        label = next((lbl for val, lbl in opt.choices if val == value), None)
        shown = f"{value} ({label})" if label else str(value)
        parts.append(f"<dt>{esc(opt.key)}</dt><dd>{esc(shown)}</dd>")
    return '<dl class="kv">' + "".join(parts) + "</dl>"


def drill_div(code: str, key: str, total: int, label: str) -> str:
    """The lazy drill-down placeholder the embedded JS renders into."""
    return (
        f'<div class="drill" data-drill="{esc(code)}|{esc(key)}" '
        f'data-total="{total}" data-label="{esc(label)}">'
        f'<p class="note"><b>{fmt_int(total)}</b> row(s) fail {esc(label)}. '
        + _NOSCRIPT.format(code=esc(code))
        + '<span class="js-only">Expand to load the lowest-scoring failing '
        "rows.</span></p></div>"
    )


def _drill_or_note(code: str, key: str, total: Optional[int],
                   label: str) -> str:
    if total is None:
        return (f'<p class="note info">No computed rule for {esc(label)} - '
                "the reasons are in the rule tables.</p>")
    if total == 0:
        return (f'<p class="note ok">No failing rows for {esc(label)} - '
                "every row passes.</p>")
    return drill_div(code, key, total, label)


def _tied_rule_li(rule: Dict) -> str:
    if rule["kind"] == "std":
        label = f"{rule['rule_id']}"
        source = f"Standard · w={rule['weight']:.1f}%"
    else:
        label = f"{rule['rule_id']} · {rule['name']}"
        source = f"Custom · w={rule['weight']:.1f}%"
    head = (f"<li><code>{esc(label)}</code> "
            f'<span class="muted">{esc(source)}</span> ')
    if rule["status"] != STATUS_EVALUATED:
        return head + f'<span class="pill p-warn">{esc(rule["status"])}</span></li>'
    fails = rule["fail_count"] if rule["fail_count"] is not None else 0
    return (head + f"<b>{rule['pass_rate']:.1f}%</b> pass · "
            f"{fmt_int(fails)} failing</li>")


# ------------------------------------------------------------- toolbars

def toolbar_sort_only() -> str:
    """Sort + only-below-green toolbar for the CDE / Dimension lists."""
    return (
        '<div class="toolbar js-only">'
        '<button type="button" class="tb" data-sort="score" data-dir="asc">'
        "Sort: score ↑</button>"
        '<button type="button" class="tb" data-sort="name">Sort: name</button>'
        '<label class="tb chk"><input type="checkbox" data-only-issues> '
        "Only below Green</label>"
        '<span class="tb-count muted"></span></div>'
    )


def toolbar_rules(custom: bool) -> str:
    """Filter + sort toolbar for the Standard / Custom rule lists."""
    not_run = ("not-evaluated", "Not evaluated") if custom \
        else ("not-computed", "Not computed")
    blocking = ('<button type="button" class="tb" data-filter="blocking">'
                "Blocking</button>") if custom else ""
    name_label = "Sort: ID" if custom else "Sort: CDE"
    return (
        '<div class="toolbar js-only"><span class="tb-group">'
        '<button type="button" class="tb on" data-filter="all">All</button>'
        '<button type="button" class="tb" data-filter="evaluated">Evaluated</button>'
        f'<button type="button" class="tb" data-filter="{not_run[0]}">'
        f"{not_run[1]}</button>"
        '<button type="button" class="tb" data-filter="below">Below Green</button>'
        + blocking + "</span>"
        '<span class="tb-group">'
        '<button type="button" class="tb" data-sort="score" data-dir="asc">'
        "Sort: pass rate ↑</button>"
        '<button type="button" class="tb" data-sort="weight" data-dir="desc">'
        "Sort: weight ↓</button>"
        f'<button type="button" class="tb" data-sort="name">{name_label}</button>'
        "</span>"
        '<span class="tb-count muted"></span></div>'
    )


# ----------------------------------------------------- CDE / Dimension list

def group_list(view: Dict, items: List[Dict], kind: str) -> str:
    """The By-CDE (``kind="cde"``) / By-Dimension (``kind="dim"``) list."""
    code = view["code"]
    grid = f"{kind}-grid"
    head_label = "CDE" if kind == "cde" else "Dimension"
    tied_heading = ("Rules tied to this CDE" if kind == "cde"
                    else "Rules tied to this dimension")
    rows = []
    for item in items:
        name, score = item["name"], item["score"]
        label = (f"CDE {name}" if kind == "cde" else f"dimension {name}")
        below = "1" if item["bucket"] != "green" else "0"
        rows.append(
            f'<details class="gl-row" data-name="{esc(str(name).lower())}" '
            f'data-score="{score:.2f}" data-below="{below}" '
            f'data-search="{esc(item["search"])}">\n'
            f'<summary class="gl-grid {grid}">'
            f'<span class="c-name"><span class="tv">{esc(name)}</span></span>'
            f'<span class="c-bar">'
            f'{score_bar(score, view["result"].threshold_green, view["result"].threshold_yellow)}'
            "</span>"
            f'<span class="c-num num">{score:.1f}</span>'
            f'<span class="c-badge">{badge(item["bucket"])}</span>'
            f'<span class="c-rules num">{item["n_evaluated"]}/{item["n_tied"]}</span>'
            f'<span class="c-src muted">{esc(item["source"])}</span></summary>\n'
            f'<div class="gl-body"><h5>{tied_heading}</h5>'
            '<ul class="rule-list">'
            + "".join(_tied_rule_li(r) for r in item["tied"])
            + "</ul>"
            + _drill_or_note(code, f"{kind}:{name}", item["total"], label)
            + "</div></details>"
        )
    head = (
        f'<div class="gl-head gl-grid {grid}"><span>{head_label}</span>'
        '<span>Score</span><span class="num">Value</span><span>Status</span>'
        '<span class="num" title="Evaluated / tied rules">Rules</span>'
        "<span>Source</span></div>"
    )
    return f'<div class="gl">{head}{"".join(rows)}</div>'


# -------------------------------------------------------- Standard rules

def _sorted_for_display(rules: List[Dict]) -> List[Dict]:
    """Not-run rules first, then ascending pass rate - the order the
    dashboard uses (``na_position="first"``)."""
    return sorted(
        rules,
        key=lambda r: (-1.0 if r["pass_rate"] is None else r["pass_rate"]),
    )


def std_rules_list(view: Dict) -> str:
    result = view["result"]
    g, y = result.threshold_green, result.threshold_yellow
    rows = []
    for r in _sorted_for_display(view["std_rules"]):
        evaluated = r["status"] == STATUS_EVALUATED
        score_attr = f"{r['pass_rate']:.2f}" if evaluated else "-1"
        status_attr = "evaluated" if evaluated else "not-computed"
        below = "1" if evaluated and r["pass_rate"] < g else "0"
        if evaluated:
            fail_pct = 100.0 - r["pass_rate"]
            bar = f'<span class="c-bar">{score_bar(r["pass_rate"], g, y)}</span>'
            tail = (
                f'<span class="num">{r["pass_rate"]:.1f}%</span>'
                f'<span class="num">{fail_pct:.1f}%</span>'
                f'<span class="num">{fmt_int(r["fail_count"] or 0)}</span>'
            )
            kv_tail = (
                f"<dt>Pass rate</dt><dd>{r['pass_rate']:.1f}% "
                f"({fmt_int(r['pass_count'] or 0)} rows)</dd>"
                f"<dt>Fail rate</dt><dd>{fail_pct:.1f}% "
                f"({fmt_int(r['fail_count'] or 0)} rows)</dd>"
            )
            reason_html = ""
            drill = _drill_or_note(
                view["code"], f"rule:{r['rule_id']}", r["drill_total"],
                f"rule {r['rule_id']}",
            )
        else:
            bar = '<span class="c-bar"><span class="muted">—</span></span>'
            tail = ('<span class="num"><span class="muted">n/a</span></span>'
                    * 3)
            kv_tail = ""
            reason_html = (
                '<p class="callout warn"><b>Not computed.</b> '
                f"{esc(r['reason'])} The rule contributed nothing to the "
                "score; its weight was redistributed across the rules that "
                "evaluated.</p>\n"
            )
            drill = ""
        rows.append(
            f'<details class="gl-row" data-name="{esc(r["rule_id"].lower())}" '
            f'data-score="{score_attr}" data-weight="{r["weight"]:g}" '
            f'data-status="{status_attr}" data-below="{below}" '
            f'data-search="{esc(r["rule_id"].lower())}">\n'
            f'<summary class="gl-grid std-grid">'
            f'<span class="c-name"><span class="tv">{esc(r["cde"])}</span></span>'
            f"<span>{esc(r['dimension'])}</span>"
            f'<span class="num">{r["weight"]:.1f}%</span>'
            f"<span>{status_pill(r['status'])}</span>"
            f"{bar}{tail}</summary>\n"
            f'<div class="gl-body">\n{reason_html}'
            '<div class="two"><div><h5>Rule configuration</h5><dl class="kv">'
            f"<dt>Rule ID</dt><dd><code>{esc(r['rule_id'])}</code></dd>"
            f"<dt>CDE</dt><dd>{esc(r['cde'])}</dd>"
            f"<dt>Dimension</dt><dd>{esc(r['dimension'])}</dd>"
            f"<dt>Weight (Standard source)</dt><dd>{r['weight']:.1f}%</dd>"
            f"<dt>Status</dt><dd>{esc(r['status'])}</dd>{kv_tail}</dl></div>"
            f"<div><h5>Parameters</h5>{params_kv(r['params'])}</div></div>\n"
            f"{drill}</div></details>"
        )
    head = (
        '<div class="gl-head gl-grid std-grid"><span>CDE</span>'
        '<span>Dimension</span><span class="num">Weight</span>'
        "<span>Status</span><span>Pass rate</span>"
        '<span class="num">Pass</span><span class="num">Fail</span>'
        '<span class="num">Failing rows</span></div>'
    )
    return f'<div class="gl">{head}{"".join(rows)}</div>'


# --------------------------------------------------------- Custom rules

def custom_rules_list(view: Dict) -> str:
    result = view["result"]
    g, y = result.threshold_green, result.threshold_yellow
    rows = []
    for r in _sorted_for_display(view["custom_rules"]):
        evaluated = r["status"] == STATUS_EVALUATED
        rule = r["rule"]
        score_attr = f"{r['pass_rate']:.2f}" if evaluated else "-1"
        status_attr = "evaluated" if evaluated else "not-evaluated"
        below = "1" if evaluated and r["pass_rate"] < g else "0"
        blocking_cell = ('<span class="pill p-err">Blocking</span>'
                         if r["blocking"] else '<span class="muted">No</span>')
        search = f"{r['rule_id']} {r['name']} {r['type']}".lower()

        if evaluated:
            bar = f'<span class="c-bar">{score_bar(r["pass_rate"], g, y)}</span>'
            tail = (f'<span class="num">{r["pass_rate"]:.1f}%</span>'
                    f'<span class="num">{fmt_int(r["fail_count"] or 0)}</span>')
            kv_tail = (
                f"<dt>Pass / fail</dt><dd>{fmt_int(r['pass_count'] or 0)} / "
                f"{fmt_int(r['fail_count'] or 0)} rows "
                f"({r['pass_rate']:.1f}% pass)</dd>"
            )
            callout = ""
            drill = _drill_or_note(
                view["code"], f"rule:{r['rule_id']}", r["drill_total"],
                f"custom rule {r['rule_id']} ({r['name']})",
            )
        else:
            bar = '<span class="c-bar"><span class="muted">—</span></span>'
            tail = ('<span class="num"><span class="muted">n/a</span></span>'
                    '<span class="num"><span class="muted">n/a</span></span>')
            kv_tail = ""
            callout = (
                '<p class="callout warn"><b>Not evaluated.</b> '
                f"{esc(r['reason'])} This is not a failure: the rule was "
                "dropped and its weight redistributed across the Custom "
                "rules that evaluated.</p>\n"
            )
            drill = ""

        desc = ""
        if rule is not None:
            desc = f'<p class="desc">{esc(rule.description)}</p>'
            if rule.notes:
                desc += f'<p class="desc muted">{esc(rule.notes)}</p>'

        src_cols = r.get("source_columns") or {}
        src_kv = ('<dl class="kv">' + "".join(
            f"<dt>{esc(alias)}</dt><dd><code>{esc(col)}</code></dd>"
            for alias, col in src_cols.items()
        ) + "</dl>") if src_cols else '<span class="muted">none</span>'

        ref_kv = ""
        if rule is not None and rule.reference:
            ref = rule.reference
            ref_kv = (
                "<h5>Reference dataset</h5>"
                '<dl class="kv"><dt>Dataset</dt>'
                f"<dd><code>{esc(ref.get('reference_dataset', '—'))}</code></dd>"
                f"<dt>Join</dt><dd><code>{esc(ref.get('source_column', '—'))}"
                f"</code> → <code>{esc(ref.get('reference_column', '—'))}"
                "</code></dd></dl>"
            )

        rows.append(
            f'<details class="gl-row" data-name="{esc(r["rule_id"].lower())}" '
            f'data-score="{score_attr}" data-weight="{r["weight"]:g}" '
            f'data-status="{status_attr}" '
            f'data-blocking="{1 if r["blocking"] else 0}" '
            f'data-below="{below}" data-search="{esc(search)}">\n'
            f'<summary class="gl-grid cus-grid">'
            f'<span><code class="rid">{esc(r["rule_id"])}</code></span>'
            f'<span class="c-name"><span class="tv">{esc(r["name"])}</span></span>'
            f'<span class="muted"><span class="tv">{esc(r["type"])}</span></span>'
            f"<span>{blocking_cell}</span>"
            f"<span>{status_pill(r['status'])}</span>"
            f'<span class="num">{r["weight"]:.1f}%</span>'
            f"{bar}{tail}</summary>\n"
            f'<div class="gl-body">\n{callout}{desc}\n'
            '<div class="two"><div><h5>Configuration used</h5><dl class="kv">'
            f"<dt>Rule ID</dt><dd><code>{esc(r['rule_id'])}</code></dd>"
            f"<dt>Type</dt><dd>{esc(r['type'])}</dd>"
            f"<dt>Blocking</dt><dd>{'Yes' if r['blocking'] else 'No'}</dd>"
            f"<dt>Weight (Custom source)</dt><dd>{r['weight']:.1f}%</dd>"
            f"<dt>Status</dt><dd>{esc(r['status'])}</dd>{kv_tail}</dl>"
            f"<h5>Selected options</h5>{selected_options_kv(rule, r['params'])}"
            f"</div><div><h5>Source columns</h5>{src_kv}{ref_kv}</div></div>\n"
            f"{drill}</div></details>"
        )
    head = (
        '<div class="gl-head gl-grid cus-grid"><span>ID</span><span>Name</span>'
        "<span>Type</span><span>Blocking</span><span>Status</span>"
        '<span class="num">Weight</span><span>Pass rate</span>'
        '<span class="num">Pass</span><span class="num">Failing rows</span></div>'
    )
    return f'<div class="gl">{head}{"".join(rows)}</div>'


# ----------------------------------------------------------- worst rows

def _value_cell(v: object) -> str:
    if v is None or v == "":
        return '<td class="null">null</td>'
    if isinstance(v, bool):
        s = esc(str(v))
        return f'<td><span class="tv" title="{s}">{s}</span></td>'
    if isinstance(v, (int, float)):
        return f'<td class="num">{fmt_cell_number(v)}</td>'
    s = esc(str(v))
    return f'<td><span class="tv" title="{s}">{s}</span></td>'


def worst_rows_table(view: Dict, caps) -> str:
    """The static worst-rows table (works without JavaScript). Renders
    the first ``caps.worst_rows`` rows of the embedded store - the same
    records, same order, same formatting as the client-side tables."""
    store = view["store_rows"][:caps.worst_rows]
    if not store:
        return '<p class="note">No rows scored for this Data Product.</p>'
    headers = (
        [("", "row_score"), ("", "status")]
        + [("", c) for c in view["columns"]]
        + [("th-ref", c) for c in view["ref_columns"]]
        + [("th-rule", header) for _, header in view["rule_specs"]]
    )
    thead = "".join(
        f'<th class="{cls}"><span class="tv" title="{esc(h)}">{esc(h)}</span></th>'
        for cls, h in headers
    )
    body_rows = []
    for row in store:
        cells = [
            f'<td class="num"><b>{row["s"]:.2f}</b></td>',
            f"<td>{badge(row['b'])}</td>",
        ]
        cells += [_value_cell(v) for v in row["v"]]
        cells += [_value_cell(v) for v in row["r"]]
        cells += [
            f'<td class="num flag {"f-pass" if f else "f-fail"}">'
            f"{'100' if f else '0'}</td>"
            for f in row["f"]
        ]
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<div class="tw"><table class="rows"><thead><tr>' + thead
        + "</tr></thead><tbody>" + "".join(body_rows)
        + "</tbody></table></div>"
    )


# -------------------------------------------------------------- history

def _delta_cell(delta: Optional[float]) -> str:
    if delta is None:
        return '<td class="num">—</td>'
    cls = "pos" if delta > 0 else ("neg" if delta < 0 else "")
    return f'<td class="num {cls}">{delta:+.2f}</td>'


def run_log_table(runs: List[Dict]) -> str:
    rows = []
    for r in reversed(runs):     # newest first
        changed = ('<span class="pill p-warn">yes</span>' if r["changed"]
                   else "")
        rows.append(
            f"<tr><td>{esc(r['ts'])}</td><td>{esc(r['user'])}</td>"
            f'<td class="num">{r["score"]:.2f}</td>'
            + _delta_cell(r["delta"])
            + f'<td><code title="{esc(r["config_hash"])}">'
            f"{esc(r['config_hash'][:8])}</code></td>"
            f"<td>{changed}</td><td>{esc(r['note'])}</td></tr>"
        )
    return (
        '<div class="tw"><table class="compact"><thead><tr><th>Run (UTC)</th>'
        '<th>User</th><th class="num">Score</th><th class="num">Δ vs prev</th>'
        "<th>Config</th><th>Config changed</th><th>Note</th></tr></thead>"
        "<tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _drift_num(v: float) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) \
        else f"{v:.2f}"


def drift_tables(drift: Dict) -> str:
    parts = []
    for label, singular in (("Rules", "Rules"), ("CDEs", "CDEs"),
                            ("Dimensions", "Dimensions")):
        rows = drift["tables"].get(label) or []
        if not rows:
            continue
        body = "".join(
            f"<tr><td>{esc(t['name'])}</td>"
            f'<td class="num">{_drift_num(t["previous"])}</td>'
            f'<td class="num">{_drift_num(t["current"])}</td>'
            f'<td class="num {"neg" if (t["delta"] or 0) < 0 else "pos"}">'
            f"{t['delta']:+.2f}</td></tr>"
            for t in rows
        )
        parts.append(
            f"<h5>{singular} that moved ≥ "
            f"{drift.get('threshold', 5):g} pp</h5>"
            '<div class="tw"><table class="compact"><thead><tr><th>Name</th>'
            '<th class="num">Previous</th><th class="num">Current</th>'
            '<th class="num">Delta</th></tr></thead><tbody>'
            + body + "</tbody></table></div>"
        )
    return "".join(parts)


# ------------------------------------------------------- config snapshot

def config_snapshot(view: Dict) -> str:
    cfg, result = view["cfg"], view["result"]
    chips = "".join(f"<code>{esc(c)}</code>" for c in cfg.cdes) or \
        '<span class="muted">none</span>'
    sources_kv = "".join(
        f"<dt>{esc(s)}</dt><dd>{w:.0f}%</dd>"
        for s, w in cfg.effective_source_weights().items()
    )
    tables = "<br>".join(
        f"<code>{esc(t)}</code>" for t in view["source_tables"]
    ) or '<span class="muted">—</span>'

    std_rows = "".join(
        f"<tr><td><code>{esc(a.cde_column)}</code></td>"
        f"<td>{esc(a.dimension)}</td>"
        f'<td class="num">{a.weight:.1f}%</td>'
        f"<td>{_inline_params(a.params)}</td></tr>"
        for a in cfg.assignments
    )
    std_table = (
        f"<h5>Standard assignments ({len(cfg.assignments)}) - weights sum to "
        f"{sum(a.weight for a in cfg.assignments):.0f}%</h5>"
        '<div class="tw"><table class="compact"><thead><tr><th>CDE</th>'
        '<th>Dimension</th><th class="num">Weight</th><th>Parameters</th>'
        "</tr></thead><tbody>" + std_rows + "</tbody></table></div>"
    ) if cfg.assignments else \
        '<p class="note">No Standard DQRs configured.</p>'

    cust_rows = "".join(
        f"<tr><td><code>{esc(r['rule_id'])}</code></td>"
        f"<td>{esc(r['name'])}</td>"
        f'<td class="num">{r["weight"]:.1f}%</td>'
        f"<td>{_inline_params(r['params'])}</td></tr>"
        for r in view["custom_rules"]
    )
    cust_table = (
        f"<h5>Custom assignments ({len(view['custom_rules'])}) - weights sum "
        f"to {sum(r['weight'] for r in view['custom_rules']):.0f}%</h5>"
        '<div class="tw"><table class="compact"><thead><tr><th>Rule</th>'
        '<th>Name</th><th class="num">Weight</th><th>Options</th></tr>'
        "</thead><tbody>" + cust_rows + "</tbody></table></div>"
    ) if view["custom_rules"] else \
        '<p class="note">No Custom DQRs configured.</p>'

    return (
        f'<details class="cfg" id="{esc(view["code"])}-config"><summary>'
        "<h3>Configuration used for this run "
        f'<span class="h-sub">config <code>{esc(view["config_hash"])}</code>'
        "</span></h3></summary>\n"
        '<div class="cfg-body">\n<div class="two">\n'
        f"<div><h5>Critical Data Elements ({len(cfg.cdes)})</h5>"
        f'<div class="chips">{chips}</div>\n'
        f'<h5>DQR sources &amp; weights</h5><dl class="kv">{sources_kv}</dl>\n'
        '<h5>Thresholds</h5><dl class="kv">'
        f"<dt>Green</dt><dd>score ≥ {result.threshold_green:g}</dd>"
        f"<dt>Yellow</dt><dd>score ≥ {result.threshold_yellow:g}</dd>"
        f"<dt>Red</dt><dd>score &lt; {result.threshold_yellow:g}</dd></dl></div>\n"
        '<div><h5>Data Product</h5><dl class="kv">'
        f"<dt>System code</dt><dd><code>{esc(view['code'])}</code></dd>"
        f"<dt>Name</dt><dd>{esc(view['name'])}</dd>"
        f"<dt>Rows</dt><dd>{fmt_int(view['n_rows'])}</dd>"
        f"<dt>Columns</dt><dd>{fmt_int(view['n_cols'])}</dd>"
        f"<dt>Source tables</dt><dd>{tables}</dd></dl></div>\n</div>\n"
        + std_table + "\n" + cust_table + "\n</div></details>"
    )


def _inline_params(params: Dict) -> str:
    if not params:
        return '<span class="muted">defaults</span>'
    return " · ".join(
        f"<code>{esc(k)}</code>={_fmt_param(v)}" for k, v in params.items()
    )
