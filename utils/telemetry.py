"""Session-side telemetry wiring (phase 2).

Streamlit-facing helpers that emit adoption/audit events through the
fire-and-forget persistence layer. ``app.py`` calls both on every render;
session-state guards make them cheap no-ops on reruns:

- :func:`log_app_open_once` - one ``app_open`` event per browser session.
- :func:`log_step_view` - one ``step_view`` event per step *transition*
  (not per rerun), carrying the step name and the active mode/domain.

Feature-specific events (``export``, ``project_saved``,
``project_loaded``) are emitted at their own call sites.
"""
from __future__ import annotations

import streamlit as st

from src.persistence import log_event

_APP_OPEN_KEY = "_telemetry_app_open_logged"
_LAST_STEP_KEY = "_telemetry_last_step"


def log_app_open_once() -> None:
    if st.session_state.get(_APP_OPEN_KEY):
        return
    st.session_state[_APP_OPEN_KEY] = True
    log_event("app_open")


def log_step_view(step: str) -> None:
    if st.session_state.get(_LAST_STEP_KEY) == step:
        return
    st.session_state[_LAST_STEP_KEY] = step
    log_event(
        "step_view",
        {"step": step, "mode": st.session_state.get("app_mode") or ""},
        domain_code=str(st.session_state.get("domain") or ""),
    )
