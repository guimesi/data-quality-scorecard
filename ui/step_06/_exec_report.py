"""Executive HTML report for the Step 6 dashboard (phase 4).

Builds a fully **self-contained** HTML file - no external scripts, fonts
or images - carrying every dashboard view: cross-DP overview, per-DP
score + threshold distribution, By-CDE / By-Dimension breakdowns (pure
HTML/CSS bars, no plotly payload), Standard and Custom rule tables, the
worst rows, and the persisted score trend (inline SVG) with the delta vs
the previous run.

A ``@media print`` stylesheet keeps it A4-friendly (one DP per page,
colors preserved), so **Ctrl+P → Save as PDF** produces the shareable
executive PDF without any PDF library - keeping the runtime image
slim (no PDF-generation packages needed).

Every dynamic string is HTML-escaped. The builder is pure (no Streamlit
calls) so it is unit-testable; only the small download wrapper at the
bottom touches ``st``.
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Dict, List

import streamlit as st

from config.dqr_sources import SOURCE_LABELS
from src.persistence import current_username, log_event
from src.run_history import load_history, score_drop
from utils.helpers import score_bucket, score_color, score_label

_BUCKET_COLORS = {"green": "#16a34a", "yellow": "#d97706", "red": "#dc2626"}
_MAX_WORST_ROWS = 10
_MAX_WORST_COLS = 8

_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Arial, sans-serif; color: #1f2937;
       margin: 2rem auto; max-width: 1080px; padding: 0 1rem; }
h1 { margin-bottom: 0.2rem; }
h2 { border-bottom: 2px solid #e5e7eb; padding-bottom: 0.3rem; margin-top: 0; }
h3 { margin: 1.1rem 0 0.4rem; }
.meta { color: #6b7280; font-size: 0.9rem; margin-bottom: 1.4rem; }
.overview { display: flex; gap: 0.8rem; flex-wrap: wrap; margin: 1rem 0 1.6rem; }
.score-card { border: 1px solid #e5e7eb; border-radius: 10px; padding: 0.8rem 1.1rem;
              min-width: 150px; }
.score-card .code { font-weight: 600; color: #6b7280; font-size: 0.85rem; }
.score-card .val { font-size: 1.7rem; font-weight: 700; }
.pill { display: inline-block; border-radius: 999px; padding: 0.1rem 0.65rem;
        color: #fff; font-size: 0.8rem; font-weight: 600; }
.dp-section { border: 1px solid #e5e7eb; border-radius: 12px;
              padding: 1.2rem 1.4rem; margin-bottom: 1.6rem; }
.kpis { display: flex; gap: 1.6rem; flex-wrap: wrap; margin: 0.6rem 0 0.9rem; }
.kpi .label { color: #6b7280; font-size: 0.8rem; }
.kpi .value { font-size: 1.15rem; font-weight: 600; }
.bar-row { display: flex; align-items: center; gap: 0.6rem; margin: 0.22rem 0; }
.bar-label { flex: 0 0 260px; font-size: 0.85rem; overflow: hidden;
             text-overflow: ellipsis; white-space: nowrap; }
.bar-track { flex: 1; background: #f3f4f6; border-radius: 6px; height: 14px; }
.bar-fill { height: 100%; border-radius: 6px; }
.bar-value { flex: 0 0 52px; text-align: right; font-size: 0.85rem;
             font-variant-numeric: tabular-nums; }
table { border-collapse: collapse; width: 100%; font-size: 0.82rem; }
th, td { border: 1px solid #e5e7eb; padding: 0.3rem 0.5rem; text-align: left; }
th { background: #f9fafb; }
.trend { margin-top: 0.4rem; }
.note { color: #6b7280; font-size: 0.8rem; }
.delta-drop { color: #dc2626; font-weight: 600; }
.delta-up { color: #16a34a; font-weight: 600; }
@media print {
  body { margin: 0.5cm; max-width: none; }
  .dp-section { page-break-inside: avoid; border: none; padding: 0; }
  .dp-section + .dp-section { page-break-before: always; }
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
"""


def _esc(value: object) -> str:
    return html.escape(str(value))


def _pill(score: float, green: float, yellow: float) -> str:
    bucket = score_bucket(score, green, yellow)
    return (
        f'<span class="pill" style="background:{_BUCKET_COLORS[bucket]}">'
        f"{_esc(score_label(score, green, yellow))}</span>"
    )


def _bar_rows(scores: Dict[str, float], green: float, yellow: float) -> str:
    rows = []
    for name, value in sorted(scores.items(), key=lambda kv: kv[1]):
        color = score_color(value, green, yellow)
        width = max(0.0, min(100.0, float(value)))
        rows.append(
            '<div class="bar-row">'
            f'<div class="bar-label">{_esc(name)}</div>'
            f'<div class="bar-track"><div class="bar-fill" '
            f'style="width:{width:.1f}%;background:{color}"></div></div>'
            f'<div class="bar-value">{value:.1f}</div>'
            "</div>"
        )
    return "".join(rows)


def _table(headers: List[str], rows: List[List[object]]) -> str:
    head = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _rules_table(code: str, result, cfg) -> str:
    rows = []
    for a in cfg.assignments:
        reason = result.not_computed_standard_rules.get(a.rule_id)
        rows.append([
            a.cde_column, a.dimension, f"{a.weight:.1f}%",
            "Not computed" if reason else
            f"{result.rule_pass_rates.get(a.rule_id, 0.0):.1f}%",
        ])
    if not rows:
        return '<p class="note">No Standard DQRs for this Data Product.</p>'
    return _table(["CDE", "Dimension", "Weight", "Pass rate"], rows)


def _custom_rules_table(result, cfg) -> str:
    rows = []
    for a in cfg.custom_assignments:
        reason = result.not_evaluated_custom_rules.get(a.rule_id)
        rows.append([
            a.rule_id, f"{a.weight:.1f}%",
            "Not evaluated" if reason else
            f"{result.custom_rule_pass_rates.get(a.rule_id, 0.0):.1f}%",
        ])
    if not rows:
        return '<p class="note">No Custom DQRs for this Data Product.</p>'
    return _table(["Rule", "Weight", "Pass rate"], rows)


def _worst_rows_table(dp, result) -> str:
    scores = result.row_scores
    if len(scores) == 0:
        return '<p class="note">No rows scored.</p>'
    worst_idx = scores.sort_values().head(_MAX_WORST_ROWS).index
    columns = list(dp.df.columns)[:_MAX_WORST_COLS]
    headers = ["row_score"] + columns
    rows = []
    for idx in worst_idx:
        rows.append([f"{scores.loc[idx]:.1f}"]
                    + [dp.df.at[idx, c] for c in columns])
    note = ""
    if len(dp.df.columns) > _MAX_WORST_COLS:
        note = (
            f'<p class="note">Showing the first {_MAX_WORST_COLS} of '
            f"{len(dp.df.columns)} columns - the CSV export carries them "
            "all.</p>"
        )
    return _table(headers, rows) + note


def _trend_block(code: str) -> str:
    """Inline-SVG score trend + delta vs the previous run (persisted
    history, phase 1). Empty string when fewer than two runs exist."""
    history = load_history(code)
    if len(history) < 2:
        return ""
    scores = [
        float((r.get("payload") or {}).get("overall_score", 0.0))
        for r in history
    ]
    width, height, pad = 320, 64, 6
    n = len(scores)
    points = " ".join(
        f"{pad + i * (width - 2 * pad) / (n - 1):.1f},"
        f"{height - pad - (s / 100.0) * (height - 2 * pad):.1f}"
        for i, s in enumerate(scores)
    )
    drop = score_drop(history)
    delta = drop["delta"]
    cls = "delta-drop" if delta < 0 else "delta-up"
    changed = " (configuration changed)" if drop["config_changed"] else ""
    return (
        '<h3>Score trend</h3><div class="trend">'
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        'xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{width}" height="{height}" fill="#f9fafb" rx="6"/>'
        f'<polyline points="{points}" fill="none" stroke="#3b82f6" '
        'stroke-width="2"/></svg>'
        f'<div>Last change: <span class="{cls}">{delta:+.1f} pp</span> vs the '
        f"previous run ({drop['prev_score']:.1f} → {drop['curr_score']:.1f})"
        f"{_esc(changed)} · {n} run(s) recorded</div></div>"
    )


def _dp_section(code: str, dp, result, cfg) -> str:
    g, y = result.threshold_green, result.threshold_yellow
    source_weights = " · ".join(
        f"{_esc(SOURCE_LABELS.get(s, s))}: {w:.0f}%"
        for s, w in (result.source_weights or {}).items()
    )
    subscores = []
    if result.standard_score is not None:
        subscores.append(f"Standard {result.standard_score:.1f}")
    if result.custom_score is not None:
        subscores.append(f"Custom {result.custom_score:.1f}")
    kpis = [
        ("Overall score", f"{result.overall_score:.1f} / 100"),
        ("Total rows", f"{result.total_rows:,}"),
        ("🟢 Green", f"{result.rows_green:,}"),
        ("🟡 Yellow", f"{result.rows_yellow:,}"),
        ("🔴 Red", f"{result.rows_red:,}"),
    ]
    if subscores:
        kpis.append(("Subscores", " · ".join(subscores)))
    kpi_html = "".join(
        f'<div class="kpi"><div class="label">{_esc(label)}</div>'
        f'<div class="value">{_esc(value)}</div></div>'
        for label, value in kpis
    )
    parts = [
        '<div class="dp-section">',
        f"<h2>{_esc(dp.name)} <small>({_esc(code)})</small> "
        f"{_pill(result.overall_score, g, y)}</h2>",
        f'<div class="kpis">{kpi_html}</div>',
    ]
    if source_weights:
        parts.append(f'<p class="note">Source weights: {source_weights}</p>')
    if result.cde_scores:
        parts.append("<h3>By CDE</h3>" + _bar_rows(result.cde_scores, g, y))
    if result.dimension_scores:
        parts.append("<h3>By Dimension</h3>"
                     + _bar_rows(result.dimension_scores, g, y))
    parts.append("<h3>Standard rules</h3>" + _rules_table(code, result, cfg))
    parts.append("<h3>Custom rules</h3>" + _custom_rules_table(result, cfg))
    parts.append(
        f"<h3>Worst rows (lowest {_MAX_WORST_ROWS})</h3>"
        + _worst_rows_table(dp, result)
    )
    parts.append(_trend_block(code))
    parts.append("</div>")
    return "".join(parts)


def _build_executive_report_html(domain_code: str, scorecards: Dict[str, object],
                                 dps: Dict[str, object],
                                 configs: Dict[str, object]) -> bytes:
    """The full self-contained report as UTF-8 bytes."""
    generated_at = datetime.now().isoformat(timespec="seconds")
    overview_cards = "".join(
        '<div class="score-card">'
        f'<div class="code">{_esc(code)}</div>'
        f'<div class="val" style="color:'
        f'{score_color(r.overall_score, r.threshold_green, r.threshold_yellow)}">'
        f"{r.overall_score:.1f}</div>"
        f"{_pill(r.overall_score, r.threshold_green, r.threshold_yellow)}"
        "</div>"
        for code, r in scorecards.items()
    )
    sections = "".join(
        _dp_section(code, dps[code], result, configs[code])
        for code, result in scorecards.items()
        if code in dps and code in configs
    )
    body = (
        "<h1>📊 Data Quality Scorecard - Executive report</h1>"
        f'<div class="meta">Domain: <b>{_esc(domain_code or "-")}</b> · '
        f"Generated (local): {_esc(generated_at)} · "
        f"By: {_esc(current_username())} · "
        f"{len(scorecards)} Data Product(s) · "
        "Print with Ctrl+P for a shareable PDF.</div>"
        f'<div class="overview">{overview_cards}</div>'
        f"{sections}"
    )
    doc = (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>DQ Scorecard - Executive report</title>"
        f"<style>{_CSS}</style></head><body>{body}</body></html>"
    )
    return doc.encode("utf-8")


def _render_executive_report_download(scorecards: Dict[str, object]) -> None:
    """Step 6 download button; logs an ``export`` telemetry event on click."""
    dps = st.session_state.get("data_products") or {}
    configs = st.session_state.get("configs") or {}
    domain_code = str(st.session_state.get("domain", "") or "")
    if not scorecards:
        return
    data = _build_executive_report_html(domain_code, scorecards, dps, configs)
    if st.download_button(
        "📑 Executive report (HTML)",
        data=data,
        file_name="dq_scorecard_executive_report.html",
        mime="text/html",
        key="dl_exec_report",
        help="Self-contained HTML with every dashboard view - overview, "
             "breakdowns, rules, worst rows and score trends. Open it and "
             "press Ctrl+P to save as a shareable PDF.",
    ):
        log_event("export", {"format": "executive_html"}, domain_code)
    _render_airtable_push(domain_code, scorecards, data)


def _render_airtable_push(domain_code: str, scorecards: Dict[str, object],
                          html_bytes: bytes) -> None:
    """Send-to-Airtable button (phase 5). Hidden unless AIRTABLE_* is
    configured; failures surface as an inline error, never a crash."""
    from src.airtable_push import (
        AirtablePushError,
        is_configured,
        push_executive_report,
    )

    if not is_configured():
        return
    if st.button(
        "📤 Send to Airtable",
        key="btn_airtable_push",
        help="Upserts this domain's record in the Airtable results table "
             "(score, status, per-DP breakdown) and attaches the executive "
             "HTML report, giving data owners the full picture in Airtable.",
    ):
        try:
            record_ids = push_executive_report(domain_code, scorecards,
                                               html_bytes)
        except AirtablePushError as exc:
            st.error(f"Airtable push failed: {exc}")
        else:
            log_event("export", {"format": "airtable_push",
                                 "record_ids": record_ids}, domain_code)
            st.success(
                f"Results sent to Airtable - {len(record_ids)} system "
                "record(s) updated, executive report attached to each."
            )
