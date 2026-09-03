"""Canonical status colours (Green / Yellow / Red).

Single source of truth for the three score-status fills used across the
Plotly charts, the score helpers, and the consolidated stylesheet
(:func:`ui._theme.inject_global_css`). Importing from here means a re-brand
is one edit instead of the ~20 scattered hex literals this module replaced.

Kept dependency-free (no imports) so any layer - ``utils``, ``ui``, future
``config`` - can import it without risking a cycle.
"""
from __future__ import annotations

STATUS_GREEN = "#1F7A4D"
STATUS_YELLOW = "#A8650A"
STATUS_RED = "#BF3A2F"
