"""Shared UI primitives - the design system in code.

Every step composes its page from these. Nothing here touches business
logic. Existing public names (``render_restart_button``,
``render_nav_footer``, ``render_choice_card``) keep their signatures so
step modules and tests that patch them keep working.

New:
- ``page_header(eyebrow, title, subtitle)``  - replaces .step-pill + section_header
- ``step_eyebrow(step)``                     - "Step 4 of 8 · Step-by-step · Cost Estimate"
- ``section_title(n, title, hint)``          - numbered in-page section ("1 Domain")
- ``code_chip(text)`` / ``badge(text, kind)`` / ``status_badge(score, g, y)``
- ``callout(text, kind)``                    - one shape, intents info|ok|warn|err|lab
- ``dp_summary_row(...)``                    - collapsed Data Product header (Steps 3-5)
- ``kv_strip([(label, value), ...])``        - inline metrics (Rows · Columns · Tables)
- ``dist_bar(green, yellow, red)``           - row-distribution bar
- ``progress_bar(pct, kind)``                - single bar (pass rate, weight total)
"""
from __future__ import annotations

import html
from typing import Callable, Iterable, Optional, Sequence, Tuple

import streamlit as st

from utils.helpers import score_bucket

_SELECTED_BADGE = "Selected"
_STATUS_WORD = {"green": "Good", "yellow": "Warning", "red": "Poor"}
_STATUS_CLASS = {"green": "good", "yellow": "warn", "red": "poor"}


# ---------------------------------------------------------------------------
# Text primitives
# ---------------------------------------------------------------------------

def page_header(eyebrow: str, title: str, subtitle: str = "") -> None:
    """Eyebrow (position/context) · h1 · one-line subtitle. Never repeat the
    app name here; the rail already carries it."""
    sub = f'<div class="dq-sub">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="dq-eyebrow">{html.escape(eyebrow)}</div>'
        f'<h1 class="dq-title">{html.escape(title)}</h1>{sub}',
        unsafe_allow_html=True,
    )


def step_eyebrow(step: str | None = None) -> str:
    """'Step 4 of 8 · Step-by-step · Cost Estimate' computed from the visible
    step list, so the number stays honest when sub-steps are hidden."""
    from config.domains import get_active_domain
    from utils.session_state import APP_MODE_ONE_CLICK, _visible_steps

    step = step or st.session_state.get("current_step")
    visible = _visible_steps()
    mode = "One-click" if st.session_state.get("app_mode") == APP_MODE_ONE_CLICK else "Step-by-step"
    parts = []
    if step in visible:
        parts.append(f"Step {visible.index(step) + 1} of {len(visible)}")
    parts.append(mode)
    if st.session_state.get("domain"):
        try:
            parts.append(get_active_domain().name)
        except Exception:
            pass
    return " · ".join(parts)


def section_title(n: int | str, title: str, hint: str = "") -> None:
    hint_html = f'<span class="hint">{html.escape(hint)}</span>' if hint else ""
    st.markdown(
        f'<div class="dq-section"><span class="n">{n}</span>{html.escape(title)}{hint_html}</div>',
        unsafe_allow_html=True,
    )


def code_chip(text: str, brand: bool = False) -> str:
    return f'<span class="dq-code{" brand" if brand else ""}">{html.escape(str(text))}</span>'


def badge(text: str, kind: str = "") -> str:
    """kind: '' (neutral) | 'brand' | 'lab' | 'good' | 'warn' | 'poor'."""
    return f'<span class="dq-badge {kind}">{html.escape(str(text))}</span>'


def status_badge(score: float, green: float, yellow: float, suffix: str = "") -> str:
    """Glyph + word pill (✓ Good / ▲ Warning / ✕ Poor). Glyph comes from CSS
    so colour is never the only cue."""
    bucket = score_bucket(score, green, yellow)
    txt = _STATUS_WORD[bucket] + (f" · {suffix}" if suffix else "")
    return f'<span class="dq-status {_STATUS_CLASS[bucket]}">{html.escape(txt)}</span>'


def status_word(score: float, green: float, yellow: float) -> str:
    return _STATUS_WORD[score_bucket(score, green, yellow)]


def status_class(score: float, green: float, yellow: float) -> str:
    return _STATUS_CLASS[score_bucket(score, green, yellow)]


def callout(text_html: str, kind: str = "info") -> None:
    """kind: info | ok | warn | err | lab. ``text_html`` may contain <b>/<a>."""
    st.markdown(f'<div class="dq-callout {kind}">{text_html}</div>', unsafe_allow_html=True)


def kv_strip(items: Sequence[Tuple[str, str]]) -> str:
    cells = "".join(
        f'<div><div class="k">{html.escape(k)}</div><div class="v">{html.escape(str(v))}</div></div>'
        for k, v in items
    )
    return f'<div class="dq-kv">{cells}</div>'


def dist_bar(green: int, yellow: int, red: int) -> str:
    total = max(green + yellow + red, 1)
    g, y = green / total * 100, yellow / total * 100
    return (
        f'<div class="dq-dist"><span class="g" style="width:{g:.1f}%"></span>'
        f'<span class="y" style="width:{y:.1f}%"></span><span class="r" style="flex:1"></span></div>'
    )


def progress_bar(pct: float, kind: str = "brand") -> str:
    pct = max(0.0, min(100.0, pct))
    return f'<div class="dq-bar"><span class="{kind}" style="width:{pct:.1f}%"></span></div>'


# ---------------------------------------------------------------------------
# Data Product summary row (progressive disclosure for Steps 3-5)
# ---------------------------------------------------------------------------

def dp_summary_row(
    *,
    code: str,
    name: str,
    status_kind: str,          # good | warn | poor | none
    status_text: str,          # "6 CDEs" / "2 required missing"
    meta: str = "",
    expanded: bool,
    key: str,
) -> bool:
    """Header line for a per-DP block. Renders the toggle as a tertiary
    button (chevron) + HTML summary. Returns the new expanded state, which the
    caller stores in ``session_state[f"expanded_{step}"]``."""
    c_btn, c_row = st.columns([0.06, 0.94], vertical_alignment="center")
    with c_btn:
        clicked = st.button("▾" if expanded else "▸", key=key, type="tertiary",
                            help="Collapse" if expanded else "Expand")
    with c_row:
        st.markdown(
            f'<div class="dq-row">{code_chip(code)}<span class="name">{html.escape(name)}</span>'
            f'<span class="dq-status {status_kind}">{html.escape(status_text)}</span>'
            f'<span class="meta">{html.escape(meta)}</span></div>',
            unsafe_allow_html=True,
        )
    return (not expanded) if clicked else expanded


# ---------------------------------------------------------------------------
# Restart (dialog) + footer nav
# ---------------------------------------------------------------------------

def render_restart_button(
    on_restart: Callable[[], None],
    *,
    key: str = "restart_confirm",
    use_container_width: bool = True,
) -> None:
    """Restart as a two-click confirmation. Uses ``st.dialog`` when available
    (≥ 1.35), otherwise the previous popover. Only the inner confirm button
    invokes ``on_restart``."""
    if hasattr(st, "dialog"):
        @st.dialog("Restart and clear everything?")
        def _confirm() -> None:
            st.markdown(
                "This clears all selections, Data Products, rules and scorecards "
                "and returns to the start. Saved projects are not affected."
            )
            c1, c2 = st.columns(2)
            if c1.button("Cancel", key=f"{key}_cancel", use_container_width=True):
                st.rerun()
            if c2.button("Yes, restart", type="primary", key=key, use_container_width=True):
                on_restart()

        if st.button("Restart…", key=f"{key}_open", type="tertiary",
                     use_container_width=use_container_width):
            _confirm()
        return

    with st.popover("Restart…", use_container_width=use_container_width):
        st.markdown("**Restart and clear everything?**")
        if st.button("Yes, restart", type="primary", key=key):
            on_restart()


def render_nav_footer(
    *,
    show_next: bool,
    next_message: str,
    on_back: Callable[[], None],
    on_next: Callable[[], None],
    on_restart: Callable[[], None],
    next_button_label: str = "Next →",
    blocked_message: Optional[str] = None,
    back_label: str = "← Back",
    restart_key: str = "restart_confirm_nav",
) -> None:
    """Sticky footer: Back · Restart… · message · Next. The message is the
    single place a step explains why Next is disabled - steps must not add
    their own st.error recap."""
    with st.container(key="nav_footer"):
        c_back, c_restart, c_msg, c_next = st.columns(
            [1, 1, 5, 1.6], vertical_alignment="center",
        )
        with c_back:
            if st.button(back_label, key="nav_back", use_container_width=True):
                on_back()
        with c_restart:
            render_restart_button(on_restart, key=restart_key)
        with c_msg:
            if show_next and next_message:
                st.markdown(f'<div class="dq-nav-msg">{next_message}</div>', unsafe_allow_html=True)
            elif not show_next and blocked_message:
                st.markdown(
                    f'<div class="dq-nav-msg blocked">&#9650; {blocked_message}</div>',
                    unsafe_allow_html=True,
                )
        with c_next:
            if st.button(next_button_label, key="nav_next", type="primary",
                         disabled=not show_next, use_container_width=True):
                on_next()


# ---------------------------------------------------------------------------
# Choice card (domain / system / mode)
# ---------------------------------------------------------------------------

def render_choice_card(
    *,
    accent: str,                      # kept for signature compatibility; unused
    icon: str,                        # kept for signature compatibility; unused
    title: str,
    code: str,
    description: str,
    select_label: str,
    select_key: str,
    selected: bool,
    multi: bool,
    subtitle: Optional[str] = None,
    placeholder: bool = False,
    desc_min_height_em: float = 0.0,  # kept for signature compatibility; unused
    before_control: Optional[Callable[[], None]] = None,
    after_control: Optional[Callable[[], None]] = None,
    disabled: bool = False,
    disabled_reason: str = "",
) -> bool:
    """One selectable card. Selected state = brand border + soft ring on the
    container (via its ``st-key-`` class) and the control's own state; no
    accent strip, no emoji, no SELECTED pill.

    - ``multi=True``  → checkbox is the control (systems).
    - ``multi=False`` → a full-width button; primary when selected (domain / mode).
    Returns the checkbox state (multi) or whether the button was clicked.
    """
    ckey = f"choice_{select_key}"
    if selected:
        st.markdown(
            f"<style>.st-key-{ckey} div[data-testid='stVerticalBlockBorderWrapper']"
            "{border-color:var(--dq-br)!important;box-shadow:0 0 0 3px var(--dq-br-soft);}</style>",
            unsafe_allow_html=True,
        )
    with st.container(border=True, key=ckey):
        tags = ""
        if placeholder:
            tags += badge("Placeholder", "warn")
        sub = f'<div class="dq-eyebrow" style="margin-top:2px">{html.escape(subtitle)}</div>' if subtitle else ""
        st.markdown(
            f'<div class="dq-choice-title">{html.escape(title)}{tags}'
            f'<span style="margin-left:auto">{code_chip(code)}</span></div>{sub}'
            f'<div class="dq-choice-desc">{html.escape(description)}</div>',
            unsafe_allow_html=True,
        )
        if before_control is not None:
            before_control()
        if disabled and disabled_reason:
            callout(html.escape(disabled_reason), "warn")
        if multi:
            chosen = st.checkbox(select_label, value=selected and not disabled,
                                 key=select_key, disabled=disabled)
        else:
            chosen = st.button(
                select_label if not selected else f"{_SELECTED_BADGE} · continue",
                key=select_key,
                type="primary" if selected else "secondary",
                use_container_width=True,
                disabled=disabled,
            )
        if after_control is not None:
            after_control()
    return chosen


def status_glyph_text(kind: str) -> str:
    """Plain-text glyph for chart labels (Plotly ``text=``) so bars are not
    colour-only: good ✓ · warn ▲ · poor ✕."""
    return {"good": "\u2713", "warn": "\u25B2", "poor": "\u2715"}.get(kind, "")
