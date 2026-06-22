"""Global main-area stylesheet, injected once per render from ``app.main()``.

Before H5 each step shipped its own ``_inject_css()`` with a near-identical
copy of the card / button / pill / metric chrome. They had drifted (hr
margins 0.9-1.2rem, hover shadow 0.06 vs 0.07, card-title icon 1.45 vs
1.55em, ...), so this module is the single canonical source for everything
the Step-by-step wizard and the Dashboard share.

Two screens keep a *slim* per-page override because their colour identity is
deliberate, not drift (see the H5 analysis):

- the ML Lab (:func:`ui.step_07._shared._inject_css`) repaints the card
  wrapper + metric purple and owns the ``.lab-*`` classes;
- One-click (:func:`ui.step_one_click._inject_css`) repaints ``.step-pill``
  amber and owns the ``.oc-*`` classes.

Those overrides inject *after* this sheet (inside their ``render()``), so the
later rule wins for the handful of selectors they re-theme. Step 02 keeps a
one-rule override for its smaller metric *value* size (globalising it would
shrink the Dashboard / ML-Lab metric numbers).

Status fills use ``__GREEN__`` / ``__YELLOW__`` / ``__RED__`` placeholders
swapped for :mod:`utils.colors` constants at inject time - a brace-safe way
to keep the three score colours centralised without f-string-escaping the
whole stylesheet.
"""
from __future__ import annotations

import streamlit as st

from utils.colors import STATUS_GREEN, STATUS_RED, STATUS_YELLOW

# NOTE: status colours appear as __GREEN__/__YELLOW__/__RED__ sentinels and are
# substituted in inject_global_css(); everything else is literal CSS.
_GLOBAL_CSS = """
    /* ===== Shared chrome (canonical, slate, calm interaction) ===== */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px !important;
        border-color: rgba(0, 0, 0, 0.08) !important;
        background: linear-gradient(180deg,
            rgba(255, 255, 255, 1) 0%,
            rgba(250, 250, 253, 1) 100%) !important;
        transition: box-shadow 0.2s ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow: 0 6px 20px rgba(15, 23, 42, 0.06);
    }
    div.stButton > button { border-radius: 10px; font-weight: 500; }
    div[data-testid="stDownloadButton"] > button {
        border-radius: 10px; font-weight: 500;
    }
    details[data-testid="stExpander"] {
        border-radius: 10px !important;
        border: 1px solid rgba(0, 0, 0, 0.06) !important;
        background: rgba(248, 250, 252, 0.5) !important;
    }
    details[data-testid="stExpander"] > summary { font-weight: 500; }
    hr { margin: 1.2rem 0 !important; border-color: rgba(0, 0, 0, 0.06) !important; }

    div[data-testid="stMetric"] {
        background: rgba(248, 250, 252, 0.6);
        border-radius: 10px;
        padding: 0.4em 0.7em;
        border: 1px solid rgba(0, 0, 0, 0.04);
    }
    div[data-testid="stMetricLabel"] {
        font-size: 0.78em !important;
        color: rgba(49, 51, 63, 0.65) !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    button[data-baseweb="tab"] { font-weight: 600 !important; }

    /* ===== Step / status pill (indigo) ===== */
    .step-pill {
        display: inline-block;
        padding: 0.25em 0.8em;
        border-radius: 999px;
        background: rgba(99, 102, 241, 0.1);
        color: #4f46e5;
        font-size: 0.78em;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 0.6em;
    }

    /* ===== Domain / Systems card vocabulary (Steps 0-1) ===== */
    .card-accent { height: 4px; border-radius: 3px; margin: -0.3em 0 0.7em 0; }
    .card-title-row {
        display: flex; align-items: center; gap: 0.55em; margin-bottom: 0.4em;
    }
    .card-title-row .card-icon { font-size: 1.55em; line-height: 1; }
    .card-title-row .card-title {
        font-size: 1.15em; font-weight: 700; color: #0f172a; line-height: 1.2;
    }
    .card-title-row .card-code {
        margin-left: auto; font-size: 0.72em; font-weight: 700; color: #475569;
        background: rgba(15, 23, 42, 0.06); padding: 0.2em 0.55em;
        border-radius: 6px; letter-spacing: 0.04em;
    }
    .card-subtitle {
        color: rgba(49, 51, 63, 0.65); font-size: 0.82em; margin-bottom: 0.4em;
        font-weight: 600; letter-spacing: 0.02em; text-transform: uppercase;
    }
    .domain-placeholder-pill {
        display: inline-block; padding: 0.15em 0.55em; border-radius: 6px;
        background: rgba(234, 179, 8, 0.18); color: #78350f;
        font-size: 0.72em; font-weight: 700; letter-spacing: 0.04em;
        margin-left: 0.4em; vertical-align: middle;
    }
    /* Shared selected-state badge - shown on any selected choice card
       (domain or system, both flows) by render_choice_card. */
    .card-state-badge {
        display: inline-block; padding: 0.15em 0.55em; border-radius: 6px;
        background: rgba(22, 163, 74, 0.15); color: #166534;
        font-size: 0.72em; font-weight: 700; letter-spacing: 0.04em;
        margin-left: 0.4em; vertical-align: middle;
    }
    .domain-systems {
        font-size: 0.78em; color: rgba(49, 51, 63, 0.55); margin-top: 0.4em;
    }
    .domain-systems code {
        background: rgba(15, 23, 42, 0.05); padding: 0.1em 0.4em;
        margin-right: 0.2em; border-radius: 4px; font-size: 0.95em; color: #334155;
    }

    /* ===== Selection summary / chips / empty notices (Steps 0-1) ===== */
    .sel-summary {
        padding: 0.9em 1.1em; border-radius: 12px;
        background: linear-gradient(135deg,
            rgba(22, 163, 74, 0.08) 0%, rgba(34, 197, 94, 0.04) 100%);
        border: 1px solid rgba(22, 163, 74, 0.25);
    }
    .sel-summary-title {
        font-size: 0.78em; font-weight: 700; color: #166534;
        text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.45em;
    }
    .sel-chip {
        display: inline-block; padding: 0.28em 0.7em; margin: 0.15em 0.25em 0.15em 0;
        border-radius: 999px; font-size: 0.82em; font-weight: 600;
        color: #fff; letter-spacing: 0.02em;
    }
    .empty-notice {
        padding: 0.9em 1.1em; border-radius: 10px;
        background: rgba(234, 179, 8, 0.08);
        border: 1px dashed rgba(234, 179, 8, 0.45);
        color: #854d0e; font-size: 0.92em;
    }
    .primary-badge {
        display: inline-block; padding: 0.05em 0.45em; margin-left: 0.4em;
        border-radius: 5px; background: rgba(234, 179, 8, 0.15); color: #b45309;
        font-size: 0.7em; font-weight: 700; letter-spacing: 0.04em;
        vertical-align: middle;
    }
    .table-row {
        border-left: 3px solid rgba(99, 102, 241, 0.25);
        padding-left: 0.65em; margin-bottom: 0.55em;
    }

    /* ===== Data-product card header (Steps 2-5, canonical sizes) ===== */
    .dp-card-accent { height: 4px; border-radius: 3px; margin: -0.3em 0 0.7em 0; }
    .dp-card-title {
        display: flex; align-items: center; gap: 0.55em; margin-bottom: 0.15em;
    }
    .dp-card-title .dp-icon { font-size: 1.45em; line-height: 1; }
    .dp-card-title .dp-name {
        font-size: 1.1em; font-weight: 700; color: #0f172a; line-height: 1.2;
    }
    .dp-card-title .dp-code {
        margin-left: auto; font-size: 0.72em; font-weight: 700; color: #475569;
        background: rgba(15, 23, 42, 0.06); padding: 0.2em 0.55em;
        border-radius: 6px; letter-spacing: 0.04em;
    }
    .dp-source {
        font-size: 0.82em; color: rgba(49, 51, 63, 0.65); margin-bottom: 0.4em;
    }
    .dp-source code {
        background: rgba(15, 23, 42, 0.05); padding: 0.1em 0.35em;
        border-radius: 4px; font-size: 0.95em; color: #334155;
    }
    .dp-meta {
        font-size: 0.82em; color: rgba(49, 51, 63, 0.65); margin-bottom: 0.4em;
    }
    .dp-meta code {
        background: rgba(15, 23, 42, 0.05); padding: 0.08em 0.35em;
        border-radius: 4px; color: #334155;
    }

    /* ===== Filter banner + empty callout (Step 2) ===== */
    .filter-banner {
        padding: 0.85em 1.1em; border-radius: 12px;
        background: linear-gradient(135deg,
            rgba(59, 130, 246, 0.08) 0%, rgba(99, 102, 241, 0.04) 100%);
        border: 1px solid rgba(59, 130, 246, 0.25); margin-bottom: 0.4em;
    }
    .filter-title {
        font-size: 0.78em; font-weight: 700; color: #1e40af;
        text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 0.4em;
    }
    .filter-chip {
        display: inline-block; padding: 0.18em 0.55em; margin: 0.1em 0.2em 0.1em 0;
        border-radius: 6px; background: rgba(59, 130, 246, 0.15); color: #1e3a8a;
        font-size: 0.78em; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-weight: 600;
    }
    .filter-hint {
        font-size: 0.8em; color: rgba(49, 51, 63, 0.65); margin-top: 0.4em;
    }
    .empty-callout {
        padding: 0.85em 1.1em; border-radius: 12px;
        background: rgba(234, 179, 8, 0.08);
        border: 1px solid rgba(234, 179, 8, 0.4); color: #854d0e;
    }
    .empty-callout .empty-chip {
        display: inline-block; padding: 0.15em 0.55em; margin: 0.1em 0.2em 0.1em 0;
        border-radius: 6px; background: rgba(234, 179, 8, 0.18); color: #78350f;
        font-weight: 700; font-size: 0.8em;
    }

    /* ===== Tip callout + CDE summary boxes (Steps 3-4.2) ===== */
    .ui-tip {
        padding: 0.7em 0.95em; border-radius: 10px;
        background: linear-gradient(135deg,
            rgba(99, 102, 241, 0.08) 0%, rgba(59, 130, 246, 0.04) 100%);
        border: 1px solid rgba(99, 102, 241, 0.18);
        color: #312e81; font-size: 0.86em; line-height: 1.5; margin: 0.4em 0;
    }
    .ui-tip code {
        background: rgba(99, 102, 241, 0.12); padding: 0.05em 0.35em;
        border-radius: 4px; font-size: 0.95em;
    }
    .cde-success {
        padding: 0.8em 1em; border-radius: 10px;
        background: linear-gradient(135deg,
            rgba(22, 163, 74, 0.08) 0%, rgba(34, 197, 94, 0.04) 100%);
        border: 1px solid rgba(22, 163, 74, 0.25);
        color: #14532d; font-size: 0.9em; margin-top: 0.4em;
    }
    .cde-success-title {
        font-weight: 700; font-size: 0.78em; text-transform: uppercase;
        letter-spacing: 0.04em; color: #166534; margin-bottom: 0.4em;
    }
    .cde-empty {
        padding: 0.8em 1em; border-radius: 10px;
        background: rgba(234, 179, 8, 0.08);
        border: 1px dashed rgba(234, 179, 8, 0.45);
        color: #854d0e; font-size: 0.9em; margin-top: 0.4em;
    }
    .cde-chip-inline {
        display: inline-block; padding: 0.1em 0.55em; margin: 0.1em 0.2em 0.1em 0;
        border-radius: 999px; background: rgba(22, 163, 74, 0.12); color: #14532d;
        font-size: 0.82em; font-weight: 600;
    }

    /* ===== Weight bar (Step 4 source selection) ===== */
    .weight-bar {
        display: flex; height: 10px; border-radius: 6px; overflow: hidden;
        margin: 0.4em 0 0.3em 0; border: 1px solid rgba(0, 0, 0, 0.05);
    }
    .weight-bar .seg-std { background: linear-gradient(90deg, #6366f1, #4f46e5); }
    .weight-bar .seg-cus { background: linear-gradient(90deg, #f59e0b, #ea580c); }
    .weight-legend {
        display: flex; justify-content: space-between;
        font-size: 0.82em; color: rgba(49, 51, 63, 0.75);
    }
    .weight-legend .lbl-std { color: #4338ca; font-weight: 600; }
    .weight-legend .lbl-cus { color: #b45309; font-weight: 600; }

    /* ===== CDE mini-header + status pills (Step 4.1) ===== */
    .cde-header {
        background: rgba(248, 250, 252, 0.7);
        border: 1px solid rgba(0, 0, 0, 0.05); border-radius: 10px;
        padding: 0.55em 0.8em; margin: 0.6em 0 0.5em 0;
    }
    .cde-header .cde-name {
        font-weight: 700; color: #0f172a; font-size: 0.98em; margin-right: 0.4em;
    }
    .cde-chip {
        display: inline-block; padding: 0.1em 0.5em; margin: 0 0.2em 0 0;
        border-radius: 6px; background: rgba(99, 102, 241, 0.1); color: #4338ca;
        font-size: 0.75em; font-weight: 600;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }
    .cde-chip.chip-warn { background: rgba(234, 179, 8, 0.15); color: #854d0e; }
    .cde-sample { font-size: 0.78em; color: rgba(49, 51, 63, 0.6); margin-top: 0.25em; }
    .dp-status {
        display: flex; gap: 0.5em; flex-wrap: wrap;
        padding: 0.6em 0.85em; border-radius: 10px;
        background: rgba(248, 250, 252, 0.7);
        border: 1px solid rgba(0, 0, 0, 0.05); font-size: 0.85em;
    }
    .status-pill {
        display: inline-block; padding: 0.15em 0.55em;
        border-radius: 6px; font-weight: 600;
    }
    .pill-ok { background: rgba(22, 163, 74, 0.12); color: #166534; }
    .pill-warn { background: rgba(234, 179, 8, 0.18); color: #854d0e; }
    .pill-err { background: rgba(220, 38, 38, 0.12); color: #991b1b; }

    /* ===== Rule card header (Step 4.2) ===== */
    .rule-id {
        display: inline-block; padding: 0.12em 0.55em; border-radius: 6px;
        background: rgba(99, 102, 241, 0.12); color: #4338ca;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        font-weight: 700; font-size: 0.82em; margin-right: 0.4em;
    }
    .rule-name { font-weight: 700; color: #0f172a; font-size: 1.0em; }
    .rule-tag {
        display: inline-block; padding: 0.1em 0.5em; border-radius: 6px;
        font-size: 0.72em; font-weight: 600; margin-right: 0.25em; vertical-align: middle;
    }
    .tag-type   { background: rgba(15, 23, 42, 0.06); color: #334155; }
    .tag-block  { background: rgba(220, 38, 38, 0.12); color: #991b1b; }
    .tag-noblock{ background: rgba(14, 165, 233, 0.12); color: #075985; }

    /* ===== Source summary / section heads / weight rows (Step 5) ===== */
    .src-summary {
        background: rgba(248, 250, 252, 0.7);
        border: 1px solid rgba(0, 0, 0, 0.05); border-radius: 10px;
        padding: 0.7em 0.9em; margin: 0.3em 0 0.5em 0;
    }
    .src-summary-title {
        font-size: 0.72em; font-weight: 700; letter-spacing: 0.05em;
        text-transform: uppercase; color: #64748b; margin-bottom: 0.5em;
    }
    .src-bar {
        display: flex; height: 10px; border-radius: 6px; overflow: hidden;
        margin: 0.4em 0 0.5em 0; border: 1px solid rgba(0, 0, 0, 0.05);
    }
    .src-bar .seg-std { background: linear-gradient(90deg, #6366f1, #4f46e5); }
    .src-bar .seg-cus { background: linear-gradient(90deg, #f59e0b, #ea580c); }
    .src-legend { display: flex; justify-content: space-between; font-size: 0.85em; }
    .src-legend .lbl-std { color: #4338ca; font-weight: 600; }
    .src-legend .lbl-cus { color: #b45309; font-weight: 600; }
    .sec-head {
        display: flex; align-items: center; justify-content: space-between;
        margin: 0.4em 0 0.5em 0;
    }
    .sec-head .sec-title { font-weight: 700; color: #0f172a; font-size: 1.0em; }
    .sec-head .sec-badge {
        display: inline-block; padding: 0.1em 0.55em; margin-left: 0.4em;
        border-radius: 6px; font-size: 0.72em; font-weight: 700; letter-spacing: 0.04em;
    }
    .sec-badge.std { background: rgba(99, 102, 241, 0.12); color: #4338ca; }
    .sec-badge.cus { background: rgba(245, 158, 11, 0.18); color: #b45309; }
    .w-col-head {
        display: flex; font-size: 0.72em; font-weight: 700;
        color: rgba(49, 51, 63, 0.55); text-transform: uppercase;
        letter-spacing: 0.05em; margin-bottom: 0.2em; padding: 0 0.2em;
    }
    .w-col-head .col-a { flex: 3; }
    .w-col-head .col-b { flex: 3; }
    .w-col-head .col-c { flex: 2; text-align: right; }
    .pct-track {
        position: relative; height: 12px; border-radius: 6px;
        background: rgba(15, 23, 42, 0.06); overflow: hidden; margin: 0.4em 0 0.2em 0;
    }
    .pct-fill {
        height: 100%; border-radius: 6px;
        transition: width 0.2s ease, background-color 0.2s ease;
    }
    .pct-fill.ok    { background: linear-gradient(90deg, __GREEN__, #22c55e); }
    .pct-fill.warn  { background: linear-gradient(90deg, __YELLOW__, #f59e0b); }
    .pct-fill.over  { background: linear-gradient(90deg, __RED__, #ef4444); }
    .pct-label {
        display: flex; justify-content: space-between;
        font-size: 0.78em; color: rgba(49, 51, 63, 0.65);
    }

    /* ===== Mode picker cards (entry screen) ===== */
    .mode-title-row {
        display: flex; align-items: center; gap: 0.55em; margin-bottom: 0.2em;
    }
    .mode-title-row .mode-icon { font-size: 1.7em; line-height: 1; }
    .mode-title-row .mode-title { font-size: 1.2em; font-weight: 800; color: #0f172a; }
    .mode-active-pill {
        display: inline-block; padding: 0.15em 0.55em; border-radius: 6px;
        background: rgba(22, 163, 74, 0.15); color: #166534;
        font-size: 0.7em; font-weight: 700; letter-spacing: 0.04em;
        margin-left: 0.4em; vertical-align: middle;
    }
    .mode-tagline {
        color: rgba(49, 51, 63, 0.6); font-size: 0.82em; font-weight: 600;
        text-transform: uppercase; letter-spacing: 0.03em; margin-bottom: 0.5em;
    }
    .mode-desc {
        color: rgba(49, 51, 63, 0.82); font-size: 0.92em; line-height: 1.5;
        margin-bottom: 0.6em; min-height: 3.4em;
    }
    .mode-bullets { list-style: none; padding-left: 0; margin: 0 0 0.4em 0; }
    .mode-bullets li {
        font-size: 0.86em; color: rgba(49, 51, 63, 0.78);
        padding: 0.12em 0 0.12em 1.3em; position: relative; line-height: 1.4;
    }
    .mode-bullets li::before {
        content: "\\2713"; position: absolute; left: 0;
        color: __GREEN__; font-weight: 700;
    }

    /* ===== Dashboard: DP card header + score cards (Step 6) ===== */
    .dp-card-title-row {
        display: flex; align-items: center; gap: 0.55em; margin-bottom: 0.3em;
        flex-wrap: wrap;
    }
    .dp-card-title-row .dp-icon { font-size: 1.6em; line-height: 1; }
    .dp-card-title-row .dp-name {
        font-size: 1.3em; font-weight: 700; color: #0f172a; line-height: 1.1;
    }
    .dp-card-title-row .dp-code {
        font-size: 0.72em; font-weight: 700; color: #475569;
        background: rgba(15, 23, 42, 0.06); padding: 0.2em 0.55em;
        border-radius: 6px; letter-spacing: 0.04em;
    }
    .dp-card-title-row .dp-status-pill {
        margin-left: auto; padding: 0.25em 0.7em; border-radius: 999px;
        font-weight: 700; font-size: 0.82em; letter-spacing: 0.02em;
    }
    .dp-status-pill.s-green { background: rgba(22, 163, 74, 0.14); color: #166534; }
    .dp-status-pill.s-yellow{ background: rgba(234, 179, 8, 0.18); color: #854d0e; }
    .dp-status-pill.s-red   { background: rgba(220, 38, 38, 0.14); color: #991b1b; }
    .score-card {
        border-radius: 12px; padding: 0.9em 1em; border: 1px solid rgba(0, 0, 0, 0.06);
        background: linear-gradient(180deg, rgba(255, 255, 255, 1), rgba(250, 250, 253, 1));
        position: relative; overflow: hidden;
    }
    .score-card .accent-bar {
        position: absolute; left: 0; top: 0; width: 4px; height: 100%;
    }
    .score-card .sys-code {
        font-size: 0.72em; font-weight: 700; letter-spacing: 0.05em;
        color: #475569; text-transform: uppercase;
        background: rgba(15, 23, 42, 0.06); padding: 0.12em 0.5em; border-radius: 6px;
    }
    .score-card .sys-row {
        display: flex; align-items: center; gap: 0.4em; margin-bottom: 0.4em;
    }
    .score-card .sys-icon { font-size: 1.2em; }
    .score-card .score-val {
        font-size: 2em; font-weight: 800; line-height: 1.0; margin: 0.1em 0 0.05em 0;
    }
    .score-card .score-suffix {
        font-size: 0.65em; font-weight: 600; color: rgba(49, 51, 63, 0.55);
        margin-left: 0.2em;
    }
    .score-card .status-label { font-size: 0.85em; font-weight: 600; }
    .src-mini {
        background: rgba(248, 250, 252, 0.7);
        border: 1px solid rgba(0, 0, 0, 0.05); border-radius: 10px;
        padding: 0.55em 0.8em; margin: 0.3em 0;
    }
    .src-mini-title {
        font-size: 0.72em; font-weight: 700; letter-spacing: 0.05em;
        text-transform: uppercase; color: #64748b; margin-bottom: 0.3em;
    }
    .export-title {
        font-size: 0.78em; font-weight: 700; letter-spacing: 0.04em;
        text-transform: uppercase; color: #475569; margin-bottom: 0.35em;
    }
    .worst-banner {
        padding: 0.6em 0.9em; border-radius: 10px;
        background: rgba(220, 38, 38, 0.06);
        border: 1px solid rgba(220, 38, 38, 0.18);
        color: #7f1d1d; font-size: 0.85em; margin-bottom: 0.5em;
    }
"""


def inject_global_css() -> None:
    """Inject the consolidated main-area stylesheet once per render.

    Called from :func:`app.main` (mirroring ``inject_sidebar_css``) so every
    step inherits the same chrome. The two themed screens (ML Lab, One-click)
    layer a slim override on top inside their own ``render()``.
    """
    css = (
        _GLOBAL_CSS
        .replace("__GREEN__", STATUS_GREEN)
        .replace("__YELLOW__", STATUS_YELLOW)
        .replace("__RED__", STATUS_RED)
    )
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
