"""
Initial step: Mode selection.

The new entry point of the app. Before anything else, the user chooses how
they want to build their scorecards:

- **One-click**: pick a domain + systems, then the app automates the rest
  (CDEs, custom rules, default options, equal weights, scorecards, CSVs).
- **Step-by-step**: the historical manual flow - full control over every step.

This step only sets ``session_state.app_mode`` and routes onward; it owns
no workflow data of its own. Visual identity mirrors Step 0 (domain
selection) so the two early screens read as one coherent on-ramp.
"""
from __future__ import annotations

import html

import streamlit as st

from utils.helpers import section_header
from utils.session_state import (
    APP_MODE_ONE_CLICK,
    APP_MODE_STEP_BY_STEP,
    goto,
    set_app_mode,
)

# Card content for the two modes. Order is the display order (One-click
# first - it's the recommended fast path for most users).
_MODE_CARDS = (
    {
        "mode": APP_MODE_ONE_CLICK,
        "icon": "⚡",
        "title": "One-click mode",
        "accent": "#f59e0b",
        "tagline": "Fastest path to a scorecard",
        "next_step": "one_click",
        "description": (
            "Pick a domain and the systems to include - the app does the "
            "rest automatically."
        ),
        "bullets": [
            "Selects only the CDEs the custom rules need",
            "Applies every Custom DQR with its default options",
            "Distributes rule weights equally",
            "Generates the scorecards and CSV exports",
        ],
    },
    {
        "mode": APP_MODE_STEP_BY_STEP,
        "icon": "🛠️",
        "title": "Step-by-step mode",
        "accent": "#4f46e5",
        "tagline": "Full manual control",
        "next_step": "domain_selection",
        "description": (
            "The original step-by-step workflow. Customise every choice "
            "exactly as before."
        ),
        "bullets": [
            "Choose Standard and/or Custom DQR sources",
            "Hand-pick CDEs and tune every rule option",
            "Set source and rule weights yourself",
            "Review, then export from the dashboard",
        ],
    },
)


def _mode_card(card: dict, is_active: bool) -> None:
    """Render one mode card and wire its Select button."""
    active_pill = (
        '<span class="mode-active-pill">SELECTED</span>' if is_active else ""
    )
    bullets = "".join(
        f"<li>{html.escape(b)}</li>" for b in card["bullets"]
    )
    st.markdown(
        f"""
        <div class="card-accent" style="background: {card['accent']};"></div>
        <div class="mode-title-row">
            <span class="mode-icon">{html.escape(card['icon'])}</span>
            <span class="mode-title">{html.escape(card['title'])}{active_pill}</span>
        </div>
        <div class="mode-tagline">{html.escape(card['tagline'])}</div>
        <div class="mode-desc">{html.escape(card['description'])}</div>
        <ul class="mode-bullets">{bullets}</ul>
        """,
        unsafe_allow_html=True,
    )
    label = "✓ Selected" if is_active else f"Start {card['title'].split(' mode')[0]}"
    if st.button(
        label,
        key=f"mode_pick_{card['mode']}",
        type="primary" if is_active else "secondary",
        use_container_width=True,
    ):
        set_app_mode(card["mode"])
        goto(card["next_step"])


def render() -> None:

    st.markdown(
        '<div class="step-pill">Start · Choose how to build</div>',
        unsafe_allow_html=True,
    )
    section_header(
        "How do you want to build your scorecards?",
        "Pick **One-click** to go from domain + systems straight to finished "
        "scorecards, or **Step-by-step** for the full step-by-step workflow with "
        "manual control over every CDE, rule, option and weight. You can "
        "restart and switch modes at any time.",
    )

    active_mode = st.session_state.get("app_mode")
    cols = st.columns(len(_MODE_CARDS), gap="large")
    for card, col in zip(_MODE_CARDS, cols):
        with col:
            with st.container(border=True):
                _mode_card(card, is_active=(card["mode"] == active_mode))
