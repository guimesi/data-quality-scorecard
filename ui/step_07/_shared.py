"""Shared CSS, banner / empty helpers, and scorecard accessor for Step 7.

Every tab module in :mod:`ui.step_07` imports these primitives so the
visual style stays consistent and the recompute-on-demand fallback for
``scorecards`` (used when the user lands directly on the lab without
running Step 6 first) lives in one place.
"""
from __future__ import annotations

import html
from typing import Dict

import streamlit as st

from config.settings import SETTINGS
from src.models import ScorecardResult
from src.scorecard import compute_scorecard

_SYSTEM_ICONS = {"ADR": "📊", "ACCE": "📈", "EPT": "🗂️"}


def _inject_css() -> None:
    """ML-Lab-local override: the violet theme on top of the global sheet.

    Shared chrome (buttons, hr, tabs, ...) now comes from
    :func:`ui._theme.inject_global_css`; only the purple card-wrapper / metric
    re-theme and the lab-specific ``.lab-*`` classes live here."""
    st.markdown(
        """
        <style>
            div[data-testid="stVerticalBlockBorderWrapper"] {
                border-color: rgba(124, 58, 237, 0.18) !important;
                background: linear-gradient(180deg,
                    rgba(255, 255, 255, 1) 0%,
                    rgba(252, 250, 255, 1) 100%) !important;
            }
            div[data-testid="stVerticalBlockBorderWrapper"]:hover {
                box-shadow: 0 6px 20px rgba(124, 58, 237, 0.08);
            }
            div[data-testid="stMetric"] {
                background: rgba(250, 245, 255, 0.7);
                border: 1px solid rgba(124, 58, 237, 0.08);
            }
            div[data-testid="stMetricLabel"] {
                color: rgba(76, 29, 149, 0.8) !important;
            }

            .lab-pill {
                display: inline-block; padding: 0.25em 0.8em; border-radius: 999px;
                background: linear-gradient(135deg,
                    rgba(124, 58, 237, 0.12) 0%,
                    rgba(168, 85, 247, 0.12) 100%);
                color: #6d28d9;
                font-size: 0.78em; font-weight: 700; letter-spacing: 0.06em;
                text-transform: uppercase; margin-bottom: 0.6em;
            }
            .lab-beta-tag {
                display: inline-block; padding: 0.15em 0.55em; border-radius: 6px;
                background: rgba(234, 88, 12, 0.12); color: #9a3412;
                font-size: 0.7em; font-weight: 800; letter-spacing: 0.08em;
                margin-left: 0.45em; vertical-align: middle;
            }
            .lab-banner {
                padding: 0.7em 1em; border-radius: 12px;
                background: linear-gradient(135deg,
                    rgba(124, 58, 237, 0.06) 0%,
                    rgba(99, 102, 241, 0.06) 100%);
                border: 1px solid rgba(124, 58, 237, 0.18);
                color: #4c1d95; font-size: 0.88em; line-height: 1.45;
                margin-bottom: 0.7em;
            }
            .lab-banner b { color: #5b21b6; }

            .lab-card-title {
                display: flex; align-items: center; gap: 0.55em; margin-bottom: 0.45em;
            }
            .lab-card-title .lab-icon { font-size: 1.4em; line-height: 1; }
            .lab-card-title .lab-title {
                font-size: 1.05em; font-weight: 700; color: #1e1b4b;
            }
            .lab-card-title .lab-tag {
                margin-left: auto; font-size: 0.72em; font-weight: 700;
                color: #6d28d9; background: rgba(124, 58, 237, 0.08);
                padding: 0.2em 0.55em; border-radius: 6px;
            }

            .lab-explain {
                font-size: 0.85em; color: rgba(49, 51, 63, 0.78);
                line-height: 1.5;
                background: rgba(248, 250, 252, 0.7);
                border: 1px dashed rgba(124, 58, 237, 0.22);
                padding: 0.55em 0.8em; border-radius: 8px;
                margin-bottom: 0.55em;
            }
            .lab-explain code {
                background: rgba(124, 58, 237, 0.08);
                color: #5b21b6;
                padding: 0.05em 0.25em; border-radius: 4px;
            }

            .lab-empty {
                padding: 1.2em; text-align: center;
                background: rgba(248, 250, 252, 0.6);
                border: 1px dashed rgba(0, 0, 0, 0.12);
                border-radius: 12px;
                color: rgba(49, 51, 63, 0.7); font-size: 0.9em;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_banner() -> None:
    st.markdown(
        """
        <div class="lab-banner">
            🧪 <b>Experimental ML Lab.</b> Everything on this page is a
            <b>read-only</b> exploration on top of the rules-based scorecard you
            already generated. It will <b>not</b> change any score, any rule,
            any weight or any artefact you exported in Step 6. The
            algorithms below are <b>unsupervised</b> (no labels needed) and
            <b>interpretable</b>, each chart includes a plain-language
            explanation of what it shows. Use these views to spot rows,
            rules and CDEs worth investigating.
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_explainer(text: str) -> None:
    st.markdown(
        f'<div class="lab-explain">{text}</div>',
        unsafe_allow_html=True,
    )


def _render_empty(message: str) -> None:
    st.markdown(
        f'<div class="lab-empty">{html.escape(message)}</div>',
        unsafe_allow_html=True,
    )


def _ensure_scorecards() -> Dict[str, ScorecardResult]:
    """Return scorecards, recomputing if the user navigated directly to the
    lab without rendering Step 6 first. Reuses ``compute_scorecard`` so
    the math is identical to the dashboard."""
    scorecards = st.session_state.get("scorecards", {}) or {}
    dps = st.session_state.get("data_products", {}) or {}
    configs = st.session_state.get("configs", {}) or {}
    if scorecards:
        return scorecards
    if not dps or not configs:
        return {}
    recomputed = {}
    for code, dp in dps.items():
        cfg = configs.get(code)
        if cfg is None or (not cfg.assignments and not cfg.custom_assignments):
            continue
        recomputed[code] = compute_scorecard(
            dp, cfg,
            threshold_green=SETTINGS.threshold_green,
            threshold_yellow=SETTINGS.threshold_yellow,
        )
    st.session_state.scorecards = recomputed
    return recomputed
