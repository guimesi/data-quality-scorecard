"""
Step 4.2: Custom DQR rules.

For each Data Product that selected the "custom" source in Step 4, render
the catalog of data-product-specific rules as cards. Visible by default:
rule id, name, type, short description, blocking flag, and a checkbox to
opt the rule into the scoring. Inside an expander: notes, required source
columns, and the technical mapping.

Selections are persisted as ``CustomDQRAssignment`` objects in
``DataProductConfig.custom_assignments``.

CDE-coverage validation
-----------------------
Each Custom DQR declares the source columns it needs in
``CustomRuleDef.required_columns`` (alias → physical column name). When the
user ticks a rule, we compare those required physical columns against the
CDEs already selected in Step 3 (``DataProductConfig.cdes``):

- All required columns are CDEs → green "All required CDEs selected" badge.
- One or more missing → yellow warning listing the missing columns. The
  rule remains selected (so the user can fix the gap without losing their
  pick), but Step 4.2 blocks progression to the next step until every
  selected rule's required columns are covered.

A rule with an empty ``required_columns`` map (or one with no entry for
this data product) never blocks - there's nothing to validate.
"""
from __future__ import annotations

import html
from typing import Any, Dict, List, Tuple

import streamlit as st

from config.custom_dqr_catalog import (
    CustomRuleDef,
    effective_required_columns,
    get_available_custom_dqr_rules,
)
from config.dqr_sources import SOURCE_CUSTOM
from src.models import CustomDQRAssignment, DataProductConfig
from utils.helpers import section_header
from utils.session_state import next_step, prev_step, restart_app
from utils.ui_components import render_nav_footer

_SYSTEM_ICONS = {"ADR": "📊", "ACCE": "📈", "EPT": "🗂️"}
_SYSTEM_ACCENTS = {"ADR": "#3b82f6", "ACCE": "#8b5cf6", "EPT": "#0ea5e9"}
_DEFAULT_ACCENT = "#6366f1"


def _dp_card_header(code: str) -> None:
    icon = _SYSTEM_ICONS.get(code, "📦")
    accent = _SYSTEM_ACCENTS.get(code, _DEFAULT_ACCENT)
    st.markdown(
        f"""
        <div class="dp-card-accent" style="background: {accent};"></div>
        <div class="dp-card-title">
            <span class="dp-icon">{icon}</span>
            <span class="dp-name">{html.escape(code)}</span>
            <span class="dp-code">{html.escape(code)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _missing_required_cdes(
    rule: CustomRuleDef,
    selected_cdes: List[str],
    params: Dict[str, Any] | None = None,
) -> List[str]:
    """Return the physical column names that ``rule`` needs but are missing
    from ``selected_cdes``.

    The catalog stores ``required_columns`` as a mapping ``alias → physical
    column``; we validate against the physical column name because that is
    what Step 3 records in ``cfg.cdes``. ``params`` lets us pull in any
    extra columns contributed by enabled options (e.g. E3's
    project-scoped toggle adds ``PLANVIEW_ID``). Order is preserved (dict
    iteration in Python 3.7+) so the warning message reads in the same
    order as the rule definition."""
    required = effective_required_columns(rule, params)
    if not required:
        return []
    cde_set = set(selected_cdes)
    return [col for col in required.values() if col not in cde_set]


def _render_validation_status(missing: List[str]) -> None:
    """Render the green / yellow CDE-coverage badge for one rule card."""
    if not missing:
        st.success("✅ All required CDEs selected")
        return
    st.warning(
        "⚠ Missing required CDEs for this Custom DQR: "
        + ", ".join(f"`{c}`" for c in missing)
    )


def _render_rule_options(
    system_code: str,
    rule: CustomRuleDef,
    current_params: Dict[str, Any],
) -> Dict[str, Any]:
    """Render the rule's user-configurable options (toggle + selectbox)
    plus an inline "How this option works" expander, and return the
    resulting params dict. Called only when the rule is selected.

    Widget keys are namespaced by system + rule id + option key so two
    data products selecting the same rule keep independent widget state.
    """
    if not rule.options and not rule.select_options:
        return {}
    new_params: Dict[str, Any] = dict(current_params)
    st.markdown("**⚙️ Options**")
    for sel in rule.select_options:
        widget_key = f"custom_{system_code}_{rule.id}_sel_{sel.key}"
        values = [v for v, _ in sel.choices]
        labels = [lbl for _, lbl in sel.choices]
        current = current_params.get(sel.key, sel.default)
        try:
            index = values.index(current)
        except ValueError:
            # Stored value is not one of the current choices (e.g. catalog
            # tightened the list since the assignment was saved). Fall back
            # to the recommended default; if that's also gone, pick the
            # first available option so the render never raises.
            try:
                index = values.index(sel.default)
            except ValueError:
                index = 0
        chosen_label = st.selectbox(
            sel.label,
            options=labels,
            index=index,
            key=widget_key,
            help=sel.help or None,
        )
        new_params[sel.key] = values[labels.index(chosen_label)]
        if sel.description:
            with st.expander("How this option works", expanded=False):
                st.markdown(sel.description)
    for opt in rule.options:
        widget_key = f"custom_{system_code}_{rule.id}_opt_{opt.key}"
        default = bool(current_params.get(opt.key, opt.default))
        value = st.toggle(
            opt.label,
            value=default,
            key=widget_key,
            help=opt.help or None,
        )
        new_params[opt.key] = bool(value)
        if opt.description:
            with st.expander("How this option works", expanded=False):
                st.markdown(opt.description)
    return new_params


def _render_rule_card(
    system_code: str,
    rule: CustomRuleDef,
    selected: bool,
    selected_cdes: List[str] | None = None,
    current_params: Dict[str, Any] | None = None,
) -> Tuple[bool, Dict[str, Any]]:
    """Render one rule card. Returns ``(selection_state, params)``.

    When the rule is selected (post-toggle), the card surfaces a
    CDE-coverage badge: success when every ``required_columns`` entry -
    plus any extras contributed by enabled options - is among
    ``selected_cdes``, otherwise a warning listing the gaps. ``params``
    carries the values of every option toggle, ready to be persisted on
    the assignment so the engine's dispatcher can route them to the
    rule's ``check`` callable."""
    blocking_class = "tag-block" if rule.blocking else "tag-noblock"
    blocking_label = "🚫 Blocking" if rule.blocking else "ℹ Non-blocking"
    current_params = dict(current_params or {})
    with st.container(border=True):
        header_cols = st.columns([6, 1])
        with header_cols[0]:
            st.markdown(
                f"""
                <div style="margin-bottom: 0.35em;">
                    <span class="rule-id">{html.escape(rule.id)}</span>
                    <span class="rule-name">{html.escape(rule.name)}</span>
                </div>
                <div style="margin-bottom: 0.4em;">
                    <span class="rule-tag tag-type">type: {html.escape(str(rule.type))}</span>
                    <span class="rule-tag {blocking_class}">{blocking_label}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(rule.description)
        with header_cols[1]:
            # Lazy-init session_state and drop ``value=`` so the
            # "value was overridden by session state" warning never fires
            # when the Select-all-Custom-DQRs handler pre-sets this key.
            checkbox_key = f"custom_{system_code}_{rule.id}_enabled"
            if checkbox_key not in st.session_state:
                st.session_state[checkbox_key] = selected
            new_state = st.checkbox(
                "Apply",
                key=checkbox_key,
                label_visibility="visible",
            )

        new_params: Dict[str, Any] = dict(current_params)
        if new_state:
            new_params = _render_rule_options(
                system_code, rule, current_params
            )
            missing = _missing_required_cdes(
                rule, list(selected_cdes or []), new_params
            )
            _render_validation_status(missing)

        with st.expander("🔍 Details", expanded=False):
            if rule.notes:
                st.markdown(f"**📝 Notes**\n\n{rule.notes}")
            if rule.required_columns:
                lines = [
                    f"- {alias} → `{col}`"
                    for alias, col in rule.required_columns.items()
                ]
                st.markdown(
                    "**🔗 Required source fields:**\n\n" + "\n".join(lines)
                )
            if rule.reference:
                ref_lines = [
                    f"- Source column: `{rule.reference.get('source_column', '-')}`",
                    f"- Reference dataset: `{rule.reference.get('reference_dataset', '-')}`",
                    f"- Reference column: `{rule.reference.get('reference_column', '-')}`",
                ]
                st.markdown(
                    "**📚 Reference dataset (referential integrity):**\n\n"
                    + "\n".join(ref_lines)
                )
    return new_state, new_params


def _render_dp_block(
    system_code: str, cfg: DataProductConfig
) -> Tuple[bool, List[Tuple[str, List[str]]]]:
    """Render the Custom DQR cards for one Data Product.

    Returns ``(is_valid, gaps)`` where ``gaps`` is a list of
    ``(rule_id, missing_columns)`` for every selected rule whose required
    columns are not fully covered by ``cfg.cdes``. ``is_valid`` is True when
    ``gaps`` is empty (no selection → nothing to block on)."""
    rules = get_available_custom_dqr_rules(system_code)
    _dp_card_header(system_code)

    if not rules:
        st.info(
            "ℹ️ No custom DQR rules are currently configured for this data product."
        )
        cfg.custom_assignments = []
        return True, []

    # One-click shortcut: tick every Apply checkbox for this data product.
    # The button is rendered before the rule cards so that, on the rerun
    # triggered by the click, we can pre-populate each checkbox's
    # ``session_state`` value *before* the widgets instantiate. Streamlit's
    # widget protocol then picks up the pre-set value on its first call
    # this render, so the cards display ticked and ``_render_rule_card``
    # returns ``new_state=True``, no extra rerun needed.
    select_all_key = f"custom_select_all_{system_code}"
    action_col, _ = st.columns([2, 3])
    with action_col:
        if st.button(
            f"✓ Select all Custom DQRs ({len(rules)})",
            key=select_all_key,
            help=(
                "Apply every Custom DQR available for this data product. "
                "Selections are persisted as ``CustomDQRAssignment`` entries "
                "and per-rule options keep their previously stored values."
            ),
            use_container_width=True,
        ):
            for rule in rules:
                st.session_state[f"custom_{system_code}_{rule.id}_enabled"] = True

    st.markdown(
        f"<div style='font-size:0.85em; color:rgba(49,51,63,0.65); margin:0.4em 0;'>"
        f"📋 {len(rules)} rule(s) available for this Data Product"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Map existing selections to look up weights + per-rule params so they
    # survive re-renders.
    existing = {a.rule_id: a for a in cfg.custom_assignments}
    new_assignments: List[CustomDQRAssignment] = []
    gaps: List[Tuple[str, List[str]]] = []
    for rule in rules:
        prev = existing.get(rule.id)
        was_selected = prev is not None
        prev_params = dict(prev.params) if prev is not None else {}
        is_selected, params = _render_rule_card(
            system_code,
            rule,
            was_selected,
            selected_cdes=list(cfg.cdes),
            current_params=prev_params,
        )
        if is_selected:
            new_assignments.append(
                CustomDQRAssignment(
                    rule_id=rule.id,
                    weight=prev.weight if prev is not None else 0.0,
                    params=params,
                )
            )
            missing = _missing_required_cdes(rule, list(cfg.cdes), params)
            if missing:
                gaps.append((rule.id, missing))
    cfg.custom_assignments = new_assignments
    return not gaps, gaps


def render() -> None:
    st.markdown('<div class="step-pill">Step 4.2 · Custom DQR Rules</div>',
                unsafe_allow_html=True)
    section_header(
        "Step 4.2 - Custom DQR Rules",
        "Pick the data-product-specific rules to apply. Each rule shows its "
        "type, business rationale, and required source fields.",
    )

    configs = st.session_state.configs
    rendered_any = False
    all_valid = True
    blocked_summary: List[str] = []
    for code, cfg in configs.items():
        if SOURCE_CUSTOM not in cfg.effective_dqr_sources():
            continue
        rendered_any = True
        with st.container(border=True):
            valid, gaps = _render_dp_block(code, cfg)
        if not valid:
            all_valid = False
            for rule_id, missing in gaps:
                blocked_summary.append(
                    f"**{code} · {rule_id}** is missing: "
                    + ", ".join(f"`{c}`" for c in missing)
                )

    if not rendered_any:
        st.info(
            "ℹ️ No Data Product selected the Custom DQR source. "
            "Go back to Step 4 to add it, or continue."
        )

    st.markdown("---")
    if rendered_any and not all_valid:
        st.error(
            "❌ Cannot continue - some selected Custom DQRs are missing the CDEs "
            "they need to run. Either go back to Step 3 to add the missing "
            "CDEs, or unselect the affected rule(s):\n\n- "
            + "\n- ".join(blocked_summary)
        )

    _nav(show_next=all_valid)


def _nav(show_next: bool = False) -> None:
    render_nav_footer(
        show_next=show_next,
        next_message="Next step → fine-tune dimension weights for the final score.",
        on_back=prev_step,
        on_next=next_step,
        on_restart=restart_app,
    )
