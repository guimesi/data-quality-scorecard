"""Global stylesheet - the only CSS in the app. Injected once from ``app.main``.

Rules:
- one brand colour, three DQ status colours, one lab accent (tags/bars only)
- CSS variables (--dq-*) so a dark theme is a :root swap
- ``!important`` only on the 4 Streamlit resets that need it
- Streamlit hooks via ``st.container(key=...)`` → ``.st-key-*`` where possible
Status colours come from ``utils.colors`` via the __GREEN__/__YELLOW__/__RED__
sentinels. Recommended values there: #1F7A4D / #A8650A / #BF3A2F.
"""
from __future__ import annotations

import streamlit as st

from utils.colors import STATUS_GREEN, STATUS_RED, STATUS_YELLOW

_GLOBAL_CSS = """
:root {
  --dq-bg:#F4F5F7; --dq-sf:#FFFFFF; --dq-sf2:#F7F8FA; --dq-bd:#E2E5EA; --dq-bd2:#C9CED7;
  --dq-tx:#15181E; --dq-tx2:#4A5262; --dq-tx3:#6F7787;
  --dq-br:#2F52D1; --dq-br-h:#2745B3; --dq-br-soft:#E8EDFB; --dq-br-tx:#2745B3;
  --dq-ok:__GREEN__; --dq-ok-soft:#E1F3E8; --dq-wn:__YELLOW__; --dq-wn-soft:#FDF0D8; --dq-er:__RED__; --dq-er-soft:#FBE6E3;
  --dq-lab:#6B47C9; --dq-lab-soft:#EEE8FB; --dq-fill:#E7E9EE;
  --dq-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --dq-r:8px; --dq-r-sm:6px;
}

/* ---- Streamlit resets ---- */
.block-container { padding-top:1.4rem!important; padding-bottom:6rem; max-width:1280px; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius:10px!important; border-color:var(--dq-bd)!important; background:var(--dq-sf)!important; }
details[data-testid="stExpander"] { border-radius:var(--dq-r); border:1px solid var(--dq-bd); background:var(--dq-sf2); }
details[data-testid="stExpander"] summary { font-size:13px; font-weight:500; }
div.stButton > button, div[data-testid="stDownloadButton"] > button { border-radius:var(--dq-r-sm); font-weight:500; font-size:13px; }
div[data-testid="stMetric"] { background:transparent; border:0; padding:0; }
div[data-testid="stMetricLabel"] { font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--dq-tx3); }
div[data-testid="stMetricValue"] { font-family:var(--dq-mono); font-size:22px; font-weight:500; }
button[data-baseweb="tab"] { font-weight:500; font-size:13px; }
button[data-baseweb="tab"][aria-selected="true"] { font-weight:600; }
hr { margin:.9rem 0; border-color:var(--dq-bd); }
h1, h2, h3 { letter-spacing:-.01em; }
code { font-family:var(--dq-mono); font-size:.92em; background:var(--dq-fill); border-radius:4px; padding:.05em .3em; }

/* ---- Page header / sections ---- */
.dq-eyebrow { font-size:11px; text-transform:uppercase; letter-spacing:.07em; color:var(--dq-tx3); font-weight:500; margin-bottom:4px; }
h1.dq-title { font-size:22px; font-weight:600; letter-spacing:-.015em; line-height:1.2; color:var(--dq-tx); margin:0; padding:0; }
.dq-sub { font-size:13.5px; color:var(--dq-tx2); margin:4px 0 14px; max-width:680px; }
.dq-section { display:flex; align-items:baseline; gap:10px; font-weight:600; font-size:14px; margin:.4rem 0 .5rem; }
.dq-section .n { font-family:var(--dq-mono); font-size:12px; color:var(--dq-tx3); font-weight:400; }
.dq-section .hint { font-size:12.5px; color:var(--dq-tx3); font-weight:400; }

/* ---- Choice card ---- */
.dq-choice-title { display:flex; align-items:center; gap:10px; font-weight:600; font-size:15px; }
.dq-choice-desc { color:var(--dq-tx2); font-size:13px; margin:6px 0 10px; }
.dq-choice-grid { display:grid; grid-template-columns:auto 1fr; gap:6px 14px; font-size:13px; padding:12px 14px; border-radius:var(--dq-r); background:var(--dq-sf2); border:1px solid var(--dq-bd); margin-bottom:10px; }
.dq-choice-grid .k { color:var(--dq-tx3); font-size:11px; text-transform:uppercase; letter-spacing:.06em; padding-top:2px; }

/* ---- Badges / chips ---- */
.dq-badge { display:inline-block; font-size:11.5px; padding:1px 8px; border-radius:999px; background:var(--dq-fill); color:var(--dq-tx2); font-weight:500; vertical-align:middle; white-space:nowrap; }
.dq-badge.brand { background:var(--dq-br-soft); color:var(--dq-br-tx); font-weight:600; }
.dq-badge.lab { background:var(--dq-lab-soft); color:var(--dq-lab); font-weight:600; letter-spacing:.04em; font-size:10px; }
.dq-badge.good { background:var(--dq-ok-soft); color:var(--dq-ok); }
.dq-badge.warn { background:var(--dq-wn-soft); color:var(--dq-wn); }
.dq-badge.poor { background:var(--dq-er-soft); color:var(--dq-er); }
.dq-code { display:inline-block; font-family:var(--dq-mono); font-size:11.5px; padding:1px 7px; border-radius:5px; background:var(--dq-fill); color:var(--dq-tx2); vertical-align:middle; }
.dq-code.brand { background:var(--dq-br-soft); color:var(--dq-br-tx); }

/* ---- Status (glyph + word) ---- */
.dq-status { display:inline-flex; align-items:center; gap:5px; font-size:12.5px; padding:2px 9px; border-radius:999px; font-weight:500; white-space:nowrap; vertical-align:middle; }
.dq-status.good { background:var(--dq-ok-soft); color:var(--dq-ok); }
.dq-status.warn { background:var(--dq-wn-soft); color:var(--dq-wn); }
.dq-status.poor { background:var(--dq-er-soft); color:var(--dq-er); }
.dq-status.none { background:var(--dq-fill); color:var(--dq-tx3); }
.dq-status::before { font-weight:700; }
.dq-status.good::before { content:"\\2713"; }
.dq-status.warn::before { content:"\\25B2"; }
.dq-status.poor::before { content:"\\2715"; }
.dq-score { font-family:var(--dq-mono); font-size:34px; font-weight:500; letter-spacing:-.02em; line-height:1; }
.dq-score.good { color:var(--dq-ok); } .dq-score.warn { color:var(--dq-wn); } .dq-score.poor { color:var(--dq-er); } .dq-score.none { color:var(--dq-tx3); }
.dq-dist { display:flex; height:6px; border-radius:3px; overflow:hidden; background:var(--dq-fill); }
.dq-dist .g { background:var(--dq-ok); } .dq-dist .y { background:var(--dq-wn); } .dq-dist .r { background:var(--dq-er); }
.dq-bar { height:6px; border-radius:3px; background:var(--dq-fill); overflow:hidden; }
.dq-bar > span { display:block; height:100%; }
.dq-bar .good { background:var(--dq-ok); } .dq-bar .warn { background:var(--dq-wn); } .dq-bar .poor { background:var(--dq-er); }
.dq-bar .brand { background:var(--dq-br); } .dq-bar .lab { background:var(--dq-lab); }

/* ---- Callout ---- */
.dq-callout { display:flex; gap:10px; align-items:flex-start; padding:9px 14px; border-radius:var(--dq-r); font-size:12.5px; margin:4px 0 10px; }
.dq-callout.info { background:var(--dq-sf); border:1px solid var(--dq-bd); color:var(--dq-tx2); }
.dq-callout.ok { background:var(--dq-ok-soft); color:var(--dq-ok); }
.dq-callout.warn { background:var(--dq-wn-soft); color:var(--dq-wn); }
.dq-callout.err { background:var(--dq-er-soft); color:var(--dq-er); }
.dq-callout.lab { background:var(--dq-lab-soft); color:var(--dq-lab); }
.dq-callout b { font-weight:600; }

/* ---- KV strip / summary row ---- */
.dq-kv { display:flex; gap:26px; }
.dq-kv .k { font-size:10.5px; text-transform:uppercase; letter-spacing:.06em; color:var(--dq-tx3); }
.dq-kv .v { font-family:var(--dq-mono); font-size:15px; font-weight:500; }
.dq-row { display:flex; align-items:center; gap:12px; padding:4px 0; font-size:13px; }
.dq-row .name { font-weight:600; }
.dq-row .meta { color:var(--dq-tx3); font-size:12.5px; margin-left:auto; }

/* ---- Score card (dashboard overview) ---- */
.dq-scorecard { display:flex; flex-direction:column; gap:10px; }
.dq-scorecard .head { display:flex; align-items:center; gap:8px; font-size:12.5px; color:var(--dq-tx3); }
.dq-scorecard .head b { font-family:var(--dq-mono); font-weight:500; color:var(--dq-tx); }
.dq-scorecard .line { display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }
.dq-scorecard .foot { display:flex; justify-content:space-between; font-size:12px; color:var(--dq-tx3); font-family:var(--dq-mono); }
.dq-attn { display:grid; grid-template-columns:44px 1fr 46px; gap:10px; align-items:center; font-size:12.5px; margin-bottom:8px; }
.dq-attn .dp { font-family:var(--dq-mono); font-size:11.5px; color:var(--dq-tx3); }
.dq-attn .pct { font-family:var(--dq-mono); font-size:12px; text-align:right; }
.dq-attn .name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

/* ---- Sidebar rail ---- */
section[data-testid="stSidebar"] > div:first-child { background:var(--dq-sf); border-right:1px solid var(--dq-bd); }
section[data-testid="stSidebar"] .block-container { padding-top:1rem; }
.dq-brand { display:flex; align-items:center; gap:9px; padding:2px 4px 10px; }
.dq-brand .mark { width:22px; height:22px; border-radius:6px; background:var(--dq-br); color:#fff; display:flex; align-items:center; justify-content:center; font-size:10px; font-weight:600; }
.dq-brand .name { font-weight:600; font-size:13.5px; }
.dq-brand .ver { margin-left:auto; font-family:var(--dq-mono); font-size:10.5px; color:var(--dq-tx3); }
.dq-rail-title { font-size:10.5px; text-transform:uppercase; letter-spacing:.06em; color:var(--dq-tx3); padding:12px 4px 6px; }
.dq-ctx { display:flex; flex-direction:column; gap:6px; padding:10px; border:1px solid var(--dq-bd); border-radius:var(--dq-r); background:var(--dq-sf2); margin-bottom:4px; }
.dq-step { display:flex; align-items:center; gap:10px; padding:6px; border-radius:var(--dq-r-sm); font-size:13px; color:var(--dq-tx3); }
.dq-step .mk { width:20px; height:20px; border-radius:999px; display:inline-flex; align-items:center; justify-content:center; font-size:11px; font-weight:600; border:1px solid var(--dq-bd2); flex:none; }
.dq-step.done { color:var(--dq-tx2); } .dq-step.done .mk { background:var(--dq-br-soft); color:var(--dq-br-tx); border-color:var(--dq-br-soft); }
.dq-step.current { color:var(--dq-tx); font-weight:600; background:var(--dq-sf2); } .dq-step.current .mk { background:var(--dq-br); color:#fff; border-color:var(--dq-br); }
.dq-step .meta { margin-left:auto; font-size:11px; color:var(--dq-tx3); font-weight:400; }
.dq-setting { display:flex; align-items:center; gap:8px; font-size:12.5px; color:var(--dq-tx2); padding:2px 6px 8px; }
.dq-setting .dq-badge { margin-left:auto; }
section[data-testid="stSidebar"] div[data-testid="stPopover"] > button { width:100%; justify-content:space-between; font-size:12.5px; border-color:var(--dq-bd); }
.dq-rail-footer { border-top:1px solid var(--dq-bd); margin-top:14px; }
.dq-rail-loc { font-family:var(--dq-mono); font-size:10.5px; color:var(--dq-tx3); padding:0 6px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }

/* ---- Sticky footer nav ---- */
.st-key-nav_footer { position:sticky; bottom:0; z-index:5; background:var(--dq-sf); border-top:1px solid var(--dq-bd); padding:8px 0 4px; margin-top:1rem; }
.dq-nav-msg { font-size:12.5px; color:var(--dq-tx3); text-align:right; }
.dq-nav-msg.blocked { color:var(--dq-wn); font-weight:500; }

/* ---- Tables (HTML helpers) ---- */
.dq-table { border-collapse:collapse; width:100%; font-size:12.5px; }
.dq-table th { text-align:left; padding:8px 12px; font-weight:500; color:var(--dq-tx3); font-size:11px; text-transform:uppercase; letter-spacing:.05em; background:var(--dq-sf2); border-bottom:1px solid var(--dq-bd); }
.dq-table td { padding:7px 12px; border-bottom:1px solid var(--dq-bd); }
.dq-table .num { text-align:right; font-family:var(--dq-mono); }
.dq-table .mono { font-family:var(--dq-mono); font-size:12px; }
"""


def inject_global_css() -> None:
    css = (
        _GLOBAL_CSS.replace("__GREEN__", STATUS_GREEN)
        .replace("__YELLOW__", STATUS_YELLOW)
        .replace("__RED__", STATUS_RED)
    )
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
