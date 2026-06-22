"""Shared UI helpers used by multiple Step modules.

Extracted from the per-step ``_nav`` helpers (Steps 02-05) that were
near-identical: a 4-column Back / Restart / message / Next row that only
varied in the centre message, the Next button label, and the
blocked-state message.

Each step still exposes a local ``_nav(show_next: bool = False)`` wrapper
so existing tests that ``patch.object(step_module, "_nav", ...)`` keep
working unchanged. The wrapper forwards to :func:`render_nav_footer`
with the step-specific copy plus the step's bound
``prev_step`` / ``next_step`` / ``restart_app`` callbacks - that way
tests which patch those names on the step module still intercept the
clicks (the names are looked up in the step's namespace at call time).

Steps 00/01 (Back goes to the domain picker), 06 (Dashboard has an "ML
Lab" extra button) and 07 (ML Lab has a "Back to Dashboard" extra) keep
their bespoke ``_nav`` because the layout differs.
"""
from __future__ import annotations

import html
from typing import Callable, Optional

import streamlit as st

# Selected-state badge wording, shared by every choice card in both flows.
# Approved in the M10 visual review (chosen from ACTIVE / SELECTED / ✓ Selected);
# change this one constant to re-word the badge everywhere.
_SELECTED_BADGE = "✓ Selected"


def render_restart_button(
    on_restart: Callable[[], None],
    *,
    key: str = "restart_confirm",
    use_container_width: bool = True,
) -> None:
    """Render Restart as a two-click confirmation.

    Restart wipes the entire workflow (selected systems, data products,
    configs, scorecards, ML Lab runs) *and* the active domain + mode, then
    returns to the mode picker - an irreversible action. To stop an accidental
    single click from discarding a long configuration session, the reset lives
    behind a popover: the user clicks "Restart" to open it, then "Yes, restart"
    to confirm. Only that inner confirm button invokes ``on_restart``.

    ``key`` must be unique per page so two nav rows can't collide on the
    confirm button's widget key.
    """
    with st.popover("🔄 Restart", use_container_width=use_container_width):
        st.markdown("**Restart and clear everything?**")
        st.caption(
            "This clears all selections, data products, configs and "
            "scorecards and returns to the mode picker. It can't be undone."
        )
        if st.button("Yes, restart", type="primary", key=key):
            on_restart()


def render_nav_footer(
    *,
    show_next: bool,
    next_message: str,
    on_back: Callable[[], None],
    on_next: Callable[[], None],
    on_restart: Callable[[], None],
    next_button_label: str = "Next ➡",
    blocked_message: Optional[str] = None,
) -> None:
    """Render the standard Back / Restart / message / Next row.

    ``show_next=True`` renders the centre message and enables the Next
    button. ``show_next=False`` optionally renders ``blocked_message``
    (in the warning colour) and disables the Next button.

    The click handlers (``on_back`` / ``on_next`` / ``on_restart``) are
    passed in by the caller so a step's tests can still patch the
    ``prev_step`` / ``next_step`` / ``restart_app`` names in the step's
    own module namespace.
    """
    c1, c2, c_mid, c3 = st.columns([1, 1, 4, 1])
    with c1:
        if st.button("⬅ Back", use_container_width=True):
            on_back()
    with c2:
        render_restart_button(on_restart, key="restart_confirm_nav")
    with c_mid:
        if show_next:
            st.markdown(
                "<div style='text-align: center; padding-top: 0.55em; "
                "color: rgba(49,51,63,0.6); font-size: 0.85em;'>"
                f"{next_message}"
                "</div>",
                unsafe_allow_html=True,
            )
        elif blocked_message:
            st.markdown(
                "<div style='text-align: center; padding-top: 0.55em; "
                "color: rgba(234, 88, 12, 0.75); font-size: 0.85em;'>"
                f"{blocked_message}"
                "</div>",
                unsafe_allow_html=True,
            )
    with c3:
        if show_next:
            if st.button(
                next_button_label, type="primary",
                use_container_width=True,
            ):
                on_next()
        else:
            st.button(
                next_button_label, disabled=True,
                use_container_width=True,
            )


def render_choice_card(
    *,
    accent: str,
    icon: str,
    title: str,
    code: str,
    description: str,
    select_label: str,
    select_key: str,
    selected: bool,
    multi: bool,
    subtitle: Optional[str] = None,
    placeholder: bool = False,
    desc_min_height_em: float = 8.0,
    before_control: Optional[Callable[[], None]] = None,
    after_control: Optional[Callable[[], None]] = None,
) -> bool:
    """Render one selectable choice card (a domain or a system) in a bordered
    container. Shared by the Step-by-step picker (Steps 0/1) and One-click so
    the two flows render identical card chrome.

    Only the bits that legitimately differ per screen are passed in:

    - ``multi`` chooses the selection control: a checkbox (multi-select
      systems) or a Select button (single-select domain, ``type="primary"``
      when ``selected``). ``select_label`` is the unified verb, e.g.
      ``"Select Cost Estimate"``.
    - ``before_control`` / ``after_control`` are optional render callbacks for
      the screen-specific metadata, so the merge loses nothing: Step-0's
      systems-row and One-click's rule-count badge render *before* the control;
      Step-1's Tables expander renders *after* it.
    - ``selected`` drives the shared header state badge (``_SELECTED_BADGE``);
      ``placeholder`` renders the BETA·PLACEHOLDER pill; ``subtitle`` (domain
      only) and ``desc_min_height_em`` (8.0 step-by-step, 4.2 One-click) keep
      each screen's current look.

    Returns the selection signal for this run: the checkbox state when
    ``multi`` is True, else whether the button was clicked. The caller owns the
    side effect (``set_domain`` + rerun, or appending to the selection list).
    """
    with st.container(border=True):
        placeholder_pill = (
            '<span class="domain-placeholder-pill">BETA · PLACEHOLDER</span>'
            if placeholder else ""
        )
        state_badge = (
            f'<span class="card-state-badge">{html.escape(_SELECTED_BADGE)}</span>'
            if selected else ""
        )
        subtitle_html = (
            f'<div class="card-subtitle">{html.escape(subtitle)}</div>'
            if subtitle else ""
        )
        st.markdown(
            f"""
            <div class="card-accent" style="background: {accent};"></div>
            <div class="card-title-row">
                <span class="card-icon">{html.escape(icon)}</span>
                <span class="card-title">{html.escape(title)}{placeholder_pill}{state_badge}</span>
                <span class="card-code">{html.escape(code)}</span>
            </div>
            {subtitle_html}
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div style="min-height: {desc_min_height_em}em; color: rgba(49, 51, 63, 0.78);
                font-size: 0.9em; line-height: 1.5; margin-bottom: 0.5em;">
                {html.escape(description)}
            </div>
            """,
            unsafe_allow_html=True,
        )
        if before_control is not None:
            before_control()
        if multi:
            chosen = st.checkbox(select_label, value=selected, key=select_key)
        else:
            chosen = st.button(
                select_label,
                key=select_key,
                type="primary" if selected else "secondary",
                use_container_width=True,
            )
        if after_control is not None:
            after_control()
    return chosen
