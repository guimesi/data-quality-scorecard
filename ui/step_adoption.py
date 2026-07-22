"""📊 Adoption & audit - standalone admin page (phase 2).

Read-only view over the telemetry the app records through the
persistence layer: headline adoption counters, the scorecard-run trend,
per-domain/system adoption, per-user activity, and a unified audit
trail. Reached from the entry screen; not part of the scoring flow.

Authorization is deliberately out of scope here - who can open the app
at all is governed by Snowflake roles/grants (see deploy/). This page
measures and audits what authorized users did.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.telemetry import (
    adoption_overview,
    recent_activity,
    runs_by_system,
    runs_per_week,
    user_activity,
)
from utils.helpers import section_header
from utils.session_state import goto


def _render_overview_tiles() -> None:
    overview = adoption_overview()
    tiles = [
        ("👥 Unique users", overview["unique_users"]),
        ("🚪 App opens", overview["app_opens"]),
        ("🧮 Scorecard runs", overview["scorecard_runs"]),
        ("⬇ Exports", overview["exports"]),
        ("💾 Project saves", overview["projects_saved"]),
        ("📂 Project loads", overview["projects_loaded"]),
    ]
    cols = st.columns(len(tiles))
    for col, (label, value) in zip(cols, tiles):
        col.metric(label, f"{value:,}")
    if overview["last_activity"]:
        st.caption(f"Last recorded activity (UTC): {overview['last_activity']}")


def _render_runs_trend() -> None:
    trend = runs_per_week()
    st.markdown("##### 📈 Scorecard runs per week")
    if trend.empty:
        st.caption("No scorecard runs recorded yet.")
        return
    fig = go.Figure(go.Bar(
        x=trend["week"], y=trend["runs"], marker_color="#3b82f6",
        text=trend["runs"], textposition="outside",
    ))
    fig.update_layout(
        height=240,
        yaxis=dict(title="Runs", rangemode="tozero"),
        margin=dict(t=20, b=20, l=20, r=20),
    )
    st.plotly_chart(fig, use_container_width=True, key="adoption_runs_trend")


def _render_tables() -> None:
    st.markdown("##### 🗺️ Adoption by domain / system")
    by_system = runs_by_system()
    if by_system.empty:
        st.caption("No scorecard runs recorded yet.")
    else:
        st.dataframe(by_system, use_container_width=True, hide_index=True,
                     height=200)

    st.markdown("##### 👥 Activity by user")
    per_user = user_activity()
    if per_user.empty:
        st.caption("No activity recorded yet.")
    else:
        st.dataframe(per_user, use_container_width=True, hide_index=True,
                     height=200)

    st.markdown("##### 📜 Audit trail (most recent first)")
    trail = recent_activity(limit=100)
    if trail.empty:
        st.caption("Nothing recorded yet.")
    else:
        st.dataframe(trail, use_container_width=True, hide_index=True,
                     height=320)


def render() -> None:
    st.markdown('<div class="step-pill">Admin · Adoption &amp; audit</div>',
                unsafe_allow_html=True)
    section_header(
        "📊 Adoption & audit",
        "Usage recorded by the app through the persistence layer: who "
        "accessed it, what was generated and exported, and a full audit "
        "trail. Access to the app itself is governed by Snowflake roles; "
        "this page only measures what authorized users did.",
    )
    _render_overview_tiles()
    st.markdown("---")
    _render_runs_trend()
    _render_tables()
    st.markdown("---")
    if st.button("⬅ Back to start", key="adoption_back",
                 use_container_width=False):
        goto("mode_selection")
