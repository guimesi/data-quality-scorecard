"""Status helper and per-system icons/accents for Step 6.

Every sub-module of :mod:`ui.step_06` imports these primitives so the
threshold buckets and accents stay consistent across DP cards, overview
tiles, and the export buttons. (Card CSS now lives in the global stylesheet,
:func:`ui._theme.inject_global_css`.)
"""
from __future__ import annotations

from utils.helpers import score_bucket

# Package-internal surface: every ui.step_06 sub-module imports these.
__all__ = ["_SYSTEM_ICONS", "_SYSTEM_ACCENTS", "_DEFAULT_ACCENT", "_status_class"]

_SYSTEM_ICONS = {"ADR": "📊", "ACCE": "📈", "EPT": "🗂️"}
_SYSTEM_ACCENTS = {"ADR": "#3b82f6", "ACCE": "#8b5cf6", "EPT": "#0ea5e9"}
_DEFAULT_ACCENT = "#6366f1"


def _status_class(score: float, green: float, yellow: float) -> str:
    """CSS status class (``s-green`` / ``s-yellow`` / ``s-red``) for a score."""
    return f"s-{score_bucket(score, green, yellow)}"
