"""Canonical status colours (Green / Yellow / Red).

Single source of truth for the three score-status fills used across the
Plotly charts, the score helpers, and the consolidated stylesheet
(:func:`ui._theme.inject_global_css`). Importing from here means a re-brand
is one edit instead of the ~20 scattered hex literals this module replaced.

Kept dependency-free (no imports) so any layer - ``utils``, ``ui``, future
``config`` - can import it without risking a cycle.
"""
from __future__ import annotations

STATUS_GREEN = "#16a34a"
STATUS_YELLOW = "#eab308"
STATUS_RED = "#dc2626"
