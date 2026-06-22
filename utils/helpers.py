"""
Misc UI / data helpers.
"""
from __future__ import annotations

from typing import List

import pandas as pd
import streamlit as st

from utils.colors import STATUS_GREEN, STATUS_RED, STATUS_YELLOW

_STATUS_COLORS = {"green": STATUS_GREEN, "yellow": STATUS_YELLOW, "red": STATUS_RED}
_STATUS_LABELS = {"green": "🟢 Green", "yellow": "🟡 Yellow", "red": "🔴 Red"}


def score_bucket(score: float, green_threshold: float, yellow_threshold: float) -> str:
    """Return the status bucket - ``"green"`` / ``"yellow"`` / ``"red"`` - for a
    score against the two thresholds.

    Single source of the ``>= green`` / ``>= yellow`` / else rule that every
    status presentation derives from: the colour (:func:`score_color`), the
    label (:func:`score_label`), the dashboard CSS class (``_status_class``) and
    the CSV ``_status`` column all map this bucket to their own vocabulary."""
    if score >= green_threshold:
        return "green"
    if score >= yellow_threshold:
        return "yellow"
    return "red"


def score_color(score: float, green_threshold: float, yellow_threshold: float) -> str:
    return _STATUS_COLORS[score_bucket(score, green_threshold, yellow_threshold)]


def score_label(score: float, green_threshold: float, yellow_threshold: float) -> str:
    return _STATUS_LABELS[score_bucket(score, green_threshold, yellow_threshold)]


def distribute_equally(n: int) -> List[float]:
    """Return n weights summing exactly to 100, as close to equal as possible.

    Works in integer cents (1/100 of a percent) to avoid floating-point drift,
    then spreads the unavoidable remainder one cent at a time across the first
    few items, so the maximum difference between any two weights is at most
    0.01, instead of concentrating all the residual on the last item."""
    if n <= 0:
        return []
    total_cents = 10000  # 100.00%
    base_cents, remainder_cents = divmod(total_cents, n)
    return [
        (base_cents + (1 if i < remainder_cents else 0)) / 100.0
        for i in range(n)
    ]


def format_value(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        if pd.isna(v):
            return "-"
        if abs(v) >= 1000:
            return f"{v:,.2f}"
        return f"{v:.4f}".rstrip("0").rstrip(".")
    return str(v)


def section_header(title: str, subtitle: str = "") -> None:
    st.markdown(f"### {title}")
    if subtitle:
        st.caption(subtitle)
