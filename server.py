"""ASGI entry point: the Streamlit app plus the ``/reports`` routes.

Run with:  streamlit run server.py      (what app.yaml does in Databricks Apps)
      or:  uvicorn server:app --port 8501

``streamlit run`` detects the ``st.App`` instance below and serves it
with uvicorn: the Streamlit UI (``app.py``) on ``/`` and the stored
Data Quality Reports on ``/reports/<run_id>`` (see
:mod:`src.report_routes`). ``streamlit run app.py`` still works for a
UI-only local session (no ``/reports`` routes).
"""
from __future__ import annotations

# Same OS-trust-store injection as app.py, applied before any HTTPS client
# (the Volume-backed report store talks to the Databricks Files API and a
# /reports request may arrive before the first Streamlit session runs).
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:  # pragma: no cover - truststore not installed
    pass

import streamlit as st

from src.report_routes import report_routes

app = st.App("app.py", routes=report_routes())
