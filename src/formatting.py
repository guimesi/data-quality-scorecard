"""Display formatting shared by the Streamlit dashboard and the HTML report.

Scores and pass rates are **floored**, never rounded, before they are
shown: a rule that fails 179 of 835,280 rows passes 99.979% of them, and
rounding that to one decimal printed ``100.0%`` next to a non-empty list
of failing rows (ACCE, 2026-10-30). With two floored decimals the same
rule reads ``99.97%`` and ``100.00%`` is reserved for a rule - or a data
product - with nothing failing. The stored values (``DQS_RULE_SCORES``,
the run history, the config JSON) keep their own precision; this module
only governs what people read.
"""
from __future__ import annotations

import math
from decimal import ROUND_FLOOR, Decimal
from typing import Optional

SCORE_DECIMALS: int = 2


def floor_pct(value: object, decimals: int = SCORE_DECIMALS) -> Optional[float]:
    """Floor ``value`` (a 0-100 score or percentage) to ``decimals`` places.

    Returns ``None`` for ``None`` / non-numeric input and ``nan`` for
    ``nan`` so callers can keep their own "not computed" rendering. Uses
    ``Decimal`` on the float's shortest repr, so ``96.1`` stays ``96.1``
    instead of the ``96.09`` a naive ``math.floor(v * 100) / 100`` yields.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v):
        return float("nan")
    if math.isinf(v):
        return v
    quantum = Decimal(1).scaleb(-int(decimals))
    return float(Decimal(repr(v)).quantize(quantum, rounding=ROUND_FLOOR))


def fmt_score(value: object, decimals: int = SCORE_DECIMALS, missing: str = "n/a") -> str:
    """``99.97`` style text for a 0-100 score (floored, fixed decimals)."""
    floored = floor_pct(value, decimals)
    if floored is None or math.isnan(floored):
        return missing
    return f"{floored:.{int(decimals)}f}"


def fmt_pct(value: object, decimals: int = SCORE_DECIMALS, missing: str = "n/a") -> str:
    """``99.97%`` style text for a pass rate (floored, fixed decimals)."""
    text = fmt_score(value, decimals, missing)
    return text if text == missing else f"{text}%"


PCT_COLUMN_FORMAT: str = f"%.{SCORE_DECIMALS}f%%"
"""``st.column_config`` format string matching :func:`fmt_pct`."""
