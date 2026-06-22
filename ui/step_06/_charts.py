"""Plotly chart builders for Step 6 (gauge + threshold bar)."""
from __future__ import annotations

import plotly.graph_objects as go

from utils.colors import STATUS_GREEN, STATUS_RED, STATUS_YELLOW
from utils.helpers import score_color


def _gauge(score: float, title: str, green: float, yellow: float) -> go.Figure:
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": " / 100", "font": {"size": 28}},
        title={"text": title, "font": {"size": 14}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1},
            "bar": {"color": score_color(score, green, yellow)},
            "steps": [
                {"range": [0, yellow], "color": "#fee2e2"},
                {"range": [yellow, green], "color": "#fef3c7"},
                {"range": [green, 100], "color": "#dcfce7"},
            ],
            "threshold": {
                "line": {"color": "black", "width": 2},
                "thickness": 0.75,
                "value": score,
            },
        },
    ))
    fig.update_layout(height=240, margin=dict(t=40, b=10, l=10, r=10))
    return fig


def _threshold_bar(result) -> go.Figure:
    total = max(result.total_rows, 1)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=["Distribution"], x=[result.rows_green], name="🟢 Green",
        orientation="h", marker_color=STATUS_GREEN,
        text=f"{result.rows_green} ({result.rows_green/total*100:.1f}%)",
        textposition="inside",
    ))
    fig.add_trace(go.Bar(
        y=["Distribution"], x=[result.rows_yellow], name="🟡 Yellow",
        orientation="h", marker_color=STATUS_YELLOW,
        text=f"{result.rows_yellow} ({result.rows_yellow/total*100:.1f}%)",
        textposition="inside",
    ))
    fig.add_trace(go.Bar(
        y=["Distribution"], x=[result.rows_red], name="🔴 Red",
        orientation="h", marker_color=STATUS_RED,
        text=f"{result.rows_red} ({result.rows_red/total*100:.1f}%)",
        textposition="inside",
    ))
    fig.update_layout(
        barmode="stack", height=140, showlegend=True,
        margin=dict(t=10, b=10, l=10, r=10),
        xaxis_title="Rows", yaxis=dict(showticklabels=False),
    )
    return fig
