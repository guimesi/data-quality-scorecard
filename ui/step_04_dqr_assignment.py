"""
Step 4.1: Standard DQR assignment.

Iterated only for Data Products whose Step-4 selection includes the
"standard" DQR source. For each CDE in those products, the app:

- marks the dimensions that ``suggest_assignments_for_cde`` would propose
  with a 💡 *suggested* badge, but does **not** auto-apply them, the user
  starts with an empty selection and decides which dimensions to enable
- exposes a per-DP **💡 Apply all suggested DQRs** shortcut that ticks
  every still-pending suggestion across this DP's CDEs in one click
  (existing user-edited assignments are preserved)
- lets the user toggle which dimensions to apply
- exposes key parameters (e.g. min/max, regex, allowed values) inline
- runs a per-rule compatibility check (see :mod:`src.dqr_validation`) and
  surfaces ✅ / ⚠ / ❌ status next to each dimension; **Next** is disabled
  while any DP carries an error-severity issue so Step 6 never trips on a
  configuration that the engine cannot compute.

The result is persisted as DQRAssignment objects in the data product's config.
"""
from __future__ import annotations

import html
from typing import Dict, List, Tuple

import streamlit as st

from config.dqr_catalog import DIMENSIONS, list_dimensions
from config.dqr_sources import SOURCE_STANDARD
from src.dqr_engine import suggest_assignments_for_cde
from src.dqr_validation import (
    DQRValidationReport,
    validate_assignment,
)
from src.models import DQRAssignment
from utils.helpers import section_header
from utils.session_state import next_step, prev_step, restart_app
from utils.ui_components import render_nav_footer

_SYSTEM_ICONS = {"ADR": "📊", "ACCE": "📈", "EPT": "🗂️"}
_SYSTEM_ACCENTS = {"ADR": "#3b82f6", "ACCE": "#8b5cf6", "EPT": "#0ea5e9"}
_DEFAULT_ACCENT = "#6366f1"


def _dp_card_header(code: str, dp, cfg) -> None:
    icon = _SYSTEM_ICONS.get(code, "📦")
    accent = _SYSTEM_ACCENTS.get(code, _DEFAULT_ACCENT)
    cdes_html = " ".join(
        f"<code>{html.escape(c)}</code>" for c in cfg.cdes
    )
    st.markdown(
        f"""
        <div class="dp-card-accent" style="background: {accent};"></div>
        <div class="dp-card-title">
            <span class="dp-icon">{icon}</span>
            <span class="dp-name">{html.escape(dp.name)}</span>
            <span class="dp-code">{html.escape(code)}</span>
        </div>
        <div class="dp-meta"><b>{len(cfg.cdes)} CDE(s):</b> {cdes_html}</div>
        """,
        unsafe_allow_html=True,
    )


def _render_param_editor(key_prefix: str, dimension: str, current: Dict) -> Dict:
    """Render parameter inputs inline and return updated params dict."""
    params = dict(current)

    if dimension == "Completeness":
        params["allow_empty_string"] = st.checkbox(
            "Accept empty string as filled",
            value=bool(params.get("allow_empty_string", False)),
            key=f"{key_prefix}_allow_empty",
        )

    elif dimension == "Validity":
        params["regex"] = st.text_input(
            "Validity regex (optional)",
            value=params.get("regex") or "",
            key=f"{key_prefix}_regex",
        ).strip() or None
        c1, c2 = st.columns(2)
        with c1:
            v = st.text_input(
                "Min length",
                value=str(params.get("min_length") or ""),
                key=f"{key_prefix}_minlen",
            )
            params["min_length"] = int(v) if v.strip().isdigit() else None
        with c2:
            v = st.text_input(
                "Max length",
                value=str(params.get("max_length") or ""),
                key=f"{key_prefix}_maxlen",
            )
            params["max_length"] = int(v) if v.strip().isdigit() else None

    elif dimension == "Accuracy":
        c1, c2 = st.columns(2)
        with c1:
            v = st.text_input(
                "Min value",
                value="" if params.get("min_value") is None else str(params["min_value"]),
                key=f"{key_prefix}_min",
            )
            try:
                params["min_value"] = float(v) if v.strip() else None
            except ValueError:
                params["min_value"] = None
        with c2:
            v = st.text_input(
                "Max value",
                value="" if params.get("max_value") is None else str(params["max_value"]),
                key=f"{key_prefix}_max",
            )
            try:
                params["max_value"] = float(v) if v.strip() else None
            except ValueError:
                params["max_value"] = None

    elif dimension == "Consistency":
        c1, c2 = st.columns(2)
        with c1:
            params["compare_column"] = st.text_input(
                "Compare with column",
                value=params.get("compare_column") or "",
                key=f"{key_prefix}_cmpcol",
            ).strip() or None
        with c2:
            operator_choices = ["<=", "<", ">=", ">", "==", "!="]
            stored_op = params.get("operator", "<=")
            try:
                op_index = operator_choices.index(stored_op)
            except ValueError:
                op_index = 0
            params["operator"] = st.selectbox(
                "Operator",
                options=operator_choices,
                index=op_index,
                key=f"{key_prefix}_op",
            )

    elif dimension == "Timeliness":
        params["max_lag_days"] = st.number_input(
            "Max lag (days)",
            min_value=1, value=int(params.get("max_lag_days", 30)),
            key=f"{key_prefix}_lag",
        )

    elif dimension == "Currency":
        params["max_age_days"] = st.number_input(
            "Maximum age (days)",
            min_value=1, value=int(params.get("max_age_days", 365)),
            key=f"{key_prefix}_age",
        )

    elif dimension == "Conformity":
        raw = st.text_input(
            "Allowed values (comma-separated)",
            value=", ".join(str(x) for x in (params.get("allowed_values") or [])),
            key=f"{key_prefix}_allowed",
        )
        params["allowed_values"] = [v.strip() for v in raw.split(",") if v.strip()]

    elif dimension == "Integrity":
        raw = st.text_input(
            "Allowed reference values (comma-separated)",
            value=", ".join(str(x) for x in (params.get("reference_values") or [])),
            key=f"{key_prefix}_refs",
        )
        params["reference_values"] = [v.strip() for v in raw.split(",") if v.strip()]

    elif dimension == "Precision":
        params["max_decimals"] = st.number_input(
            "Maximum decimal places",
            min_value=0, max_value=10,
            value=int(params.get("max_decimals", 2)),
            key=f"{key_prefix}_decimals",
        )

    elif dimension == "Uniqueness":
        st.caption("No parameters - row passes if value is unique in the column.")

    return params


def _render_validation_feedback(report: DQRValidationReport) -> None:
    """Render the validation outcome inside an expander.

    The pattern mirrors Step 4.2's per-rule cards: ✅ when the configuration
    is compatible, ⚠ for warnings (informational), ❌ for errors (blocks
    Next). Each error/warning carries the underlying message + an optional
    suggestion so the user knows how to fix it without leaving the step.
    """
    if not report.issues:
        st.success("✅ Configuration is compatible with the selected CDE.")
        return
    for issue in report.errors:
        body = f"❌ {issue.message}"
        if issue.suggestion:
            body += f"\n\n_{issue.suggestion}_"
        st.error(body)
    for issue in report.warnings:
        body = f"⚠ {issue.message}"
        if issue.suggestion:
            body += f"\n\n_{issue.suggestion}_"
        st.warning(body)


def _expander_status_tag(report: DQRValidationReport) -> str:
    """Compact icon shown in the expander label so the user spots problems
    without opening every dimension."""
    if not report.is_valid:
        return " · ❌"
    if report.has_warnings:
        return " · ⚠"
    return " · ✅"


def _pending_suggestions_for_dp(dp, cfg) -> List[Tuple[str, DQRAssignment]]:
    """Return ``(cde, suggested_assignment)`` pairs for every suggestion
    that is *not yet* applied to ``cfg``.

    Drives the count in the "Apply all suggested DQRs" button label and the
    list of assignments the click handler appends. A suggestion is treated
    as pending when its ``dimension`` is missing from the CDE's current
    ``cfg.assignments`` - manually-applied assignments are never
    overwritten, so the button can be clicked multiple times safely and
    only fills gaps."""
    pending: List[Tuple[str, DQRAssignment]] = []
    for cde in cfg.cdes:
        profile = dp.profiles.get(cde)
        if profile is None:
            continue
        applied = {a.dimension for a in cfg.get_assignments_for(cde)}
        for sug in suggest_assignments_for_cde(profile):
            if sug.dimension not in applied:
                pending.append((cde, sug))
    return pending


def _render_apply_all_suggestions_button(system_code: str, dp, cfg) -> None:
    """Render the per-DP "💡 Apply all suggested DQRs" shortcut.

    When clicked, every still-pending suggestion (computed by
    :func:`_pending_suggestions_for_dp`) is appended to ``cfg.assignments``
    *before* the CDE blocks render. We also pre-populate each suggestion's
    Apply-checkbox key in ``st.session_state`` so the widgets honor the
    new state on this very render, no extra rerun required. The
    suggestion's profile-aware params (e.g. Accuracy's ``min_value`` /
    ``max_value`` pre-filled from the column profile) are carried through
    intact because the assignment we append is the one returned by
    ``suggest_assignments_for_cde``."""
    pending = _pending_suggestions_for_dp(dp, cfg)
    if not pending:
        st.caption(
            "💡 Every suggested DQR has already been applied for this Data "
            "Product. Tick a dimension below to add more, or untick to drop one."
        )
        return
    action_col, _ = st.columns([2, 3])
    with action_col:
        if st.button(
            f"💡 Apply all suggested DQRs ({len(pending)})",
            key=f"apply_all_suggestions_{system_code}",
            help=(
                "Apply every dimension still tagged 💡 _suggested_ for this "
                "Data Product. Suggestions you have already enabled are kept "
                "as-is and your manual edits are preserved."
            ),
            use_container_width=True,
        ):
            for cde, sug in pending:
                cfg.assignments.append(sug)
                # Pre-set the Apply-checkbox key so the widget instantiates as
                # ticked on this same render. Streamlit honors session_state
                # values set before a widget's first call.
                st.session_state[f"{system_code}_{cde}_{sug.dimension}_enabled"] = True


def _render_cde_header(cde: str, profile) -> None:
    """Polished mini-header rendered above each CDE's dimension list."""
    null_chip_cls = "cde-chip chip-warn" if (profile.null_pct or 0) >= 20 else "cde-chip"
    sample = ", ".join(str(s) for s in profile.sample_values[:3]) or "-"
    st.markdown(
        f"""
        <div class="cde-header">
            <span class="cde-name">🔑 {html.escape(cde)}</span>
            <span class="cde-chip">{html.escape(str(profile.dtype))}</span>
            <span class="cde-chip">group: {html.escape(str(profile.column_type_group))}</span>
            <span class="{null_chip_cls}">nulls: {profile.null_pct}%</span>
            <span class="cde-chip">distinct: {profile.distinct_count}</span>
            <div class="cde-sample">Sample: {html.escape(sample)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_cde_block(
    system_code: str,
    cde: str,
    profile,
    dp_profiles: Dict,
    config,
) -> List[DQRValidationReport]:
    """Render the DQR assignment block for a single CDE.

    Returns the list of validation reports for the *enabled* assignments -
    Step 4.1's :func:`render` aggregates these across all DPs to gate Next.

    Suggestions are no longer auto-applied. Dimensions that
    ``suggest_assignments_for_cde`` would propose render with a
    💡 *suggested* badge in the expander label, but their Apply checkbox
    defaults to off; the user opts in explicitly (per-row checkbox or the
    per-DP **Apply all suggested DQRs** shortcut).
    """
    # Existing assignments for this CDE - only the ones the user has
    # explicitly opted into (manually or via the apply-all shortcut).
    existing: Dict[str, DQRAssignment] = {
        a.dimension: a for a in config.get_assignments_for(cde)
    }
    # Suggestions are computed independently so the 💡 _suggested_ tag
    # stays accurate even after the user has unticked the dimension.
    suggested: Dict[str, DQRAssignment] = {
        a.dimension: a for a in suggest_assignments_for_cde(profile)
    }

    _render_cde_header(cde, profile)

    new_assignments: List[DQRAssignment] = []
    reports: List[DQRValidationReport] = []
    for dim in list_dimensions():
        dim_def = DIMENSIONS[dim]
        key_prefix = f"{system_code}_{cde}_{dim}"
        default_on = dim in existing
        is_suggested = dim in suggested
        suggested_tag = " · 💡 _suggested_" if is_suggested else ""

        # Pre-compute a status tag from the *existing* state so the
        # expander label communicates compatibility at a glance, even when
        # collapsed. After the inner widgets run we re-validate against the
        # user's edits to drive the inline feedback below.
        prelim_report = (
            validate_assignment(existing[dim], profile, dp_profiles)
            if dim in existing
            else None
        )
        status_tag = _expander_status_tag(prelim_report) if prelim_report else ""

        with st.expander(
            f"`{dim}`{suggested_tag}{status_tag}",
            expanded=default_on,
        ):
            # Lazy-init session_state and drop ``value=`` so the
            # "value was overridden by session state" warning never fires
            # when the Apply-all-suggested handler pre-sets this key.
            # First render seeds session_state from ``default_on``; later
            # renders carry the user's choice (or the button-applied True).
            enabled_key = f"{key_prefix}_enabled"
            if enabled_key not in st.session_state:
                st.session_state[enabled_key] = default_on
            enabled = st.checkbox(
                f"Apply `{dim}` to CDE `{cde}`",
                key=enabled_key,
            )
            st.caption(dim_def.description)
            if enabled:
                # Carry through the suggestion's profile-aware params (e.g.
                # Accuracy min/max from the profile) when the user opts in
                # via the per-row checkbox without having clicked the
                # apply-all shortcut first.
                fallback = suggested.get(dim) or DQRAssignment(
                    cde, dim, dict(dim_def.default_params)
                )
                current_params = existing.get(dim, fallback).params
                updated = _render_param_editor(key_prefix, dim, current_params)
                assignment = DQRAssignment(
                    cde_column=cde,
                    dimension=dim,
                    params=updated,
                    weight=existing.get(dim, DQRAssignment(cde, dim)).weight,
                )
                new_assignments.append(assignment)
                report = validate_assignment(assignment, profile, dp_profiles)
                _render_validation_feedback(report)
                reports.append(report)

    # Replace assignments for this CDE
    config.assignments = [
        a for a in config.assignments if a.cde_column != cde
    ] + new_assignments
    return reports


def _render_dp_status(dp_reports: List[DQRValidationReport], dp_name: str, code: str) -> bool:
    """Render the bottom-of-card status row and return whether the DP has
    blocking errors. Visual replacement for the old st.error/st.warning,
    but emits the same st.error/st.warning underneath when issues exist so
    the user still gets the strong, dismissible alert."""
    dp_errors = sum(1 for r in dp_reports if not r.is_valid)
    dp_warnings = sum(1 for r in dp_reports if r.is_valid and r.has_warnings)
    dp_ok = len(dp_reports) - dp_errors - dp_warnings

    pills = [
        f'<span class="status-pill pill-ok">✅ {dp_ok} OK</span>',
        f'<span class="status-pill pill-warn">⚠ {dp_warnings} warning(s)</span>',
        f'<span class="status-pill pill-err">❌ {dp_errors} error(s)</span>',
        f'<span class="status-pill" style="background:rgba(99,102,241,0.1); color:#4338ca;">'
        f'Σ {len(dp_reports)} rule(s)</span>',
    ]
    st.markdown(
        f"<div class='dp-status'>{''.join(pills)}</div>",
        unsafe_allow_html=True,
    )

    if dp_errors:
        st.error(
            f"❌ {dp_errors} incompatible Standard DQR "
            f"configuration(s) for **{dp_name}**: fix the highlighted "
            f"issue(s) before continuing."
        )
        return True
    if dp_warnings:
        st.warning(
            f"⚠ {dp_warnings} Standard DQR configuration(s) carry "
            f"warnings for **{dp_name}** (non-blocking)."
        )
    return False


def render() -> None:
    st.markdown('<div class="step-pill">Step 4.1 · Standard DQR Rules</div>',
                unsafe_allow_html=True)
    section_header(
        "Step 4.1 - Standard DQR Rules",
        "Pick the dimensions to apply per CDE. Dimensions tagged "
        "**💡 _suggested_** are the ones we recommend for each CDE based on "
        "its profile - they are **not** pre-applied; tick the **Apply** "
        "checkbox to enable one, or use the per-DP **💡 Apply all suggested "
        "DQRs** shortcut to enable every still-pending suggestion at once. "
        "Each rule is validated against the CDE's data type before you continue.",
    )

    dps = st.session_state.data_products
    configs = st.session_state.configs

    rendered_any = False
    all_reports: List[DQRValidationReport] = []
    invalid_dps: List[str] = []
    for code, dp in dps.items():
        cfg = configs[code]
        if not cfg.cdes:
            continue
        if SOURCE_STANDARD not in cfg.effective_dqr_sources():
            continue
        rendered_any = True

        dp_reports: List[DQRValidationReport] = []
        with st.container(border=True):
            _dp_card_header(code, dp, cfg)
            _render_apply_all_suggestions_button(code, dp, cfg)
            st.markdown("---")
            for cde in cfg.cdes:
                profile = dp.profiles.get(cde)
                if profile is None:
                    continue
                reports = _render_cde_block(
                    code, cde, profile, dp.profiles, cfg,
                )
                dp_reports.extend(reports)
                st.markdown("")

            blocking = _render_dp_status(dp_reports, dp.name, code)
            if blocking:
                invalid_dps.append(code)
        all_reports.extend(dp_reports)

    st.markdown("---")
    standard_configs = [
        c for c in configs.values() if SOURCE_STANDARD in c.effective_dqr_sources()
    ]
    total_rules = sum(len(c.assignments) for c in standard_configs)
    any_rules = total_rules > 0
    has_errors = any(not r.is_valid for r in all_reports)

    if not rendered_any:
        st.info(
            "ℹ️ Nothing to configure for the Standard DQR source on this step. "
            "You can continue."
        )
        _nav(show_next=True)
        return
    if has_errors:
        st.error(
            "❌ Resolve the incompatible Standard DQR configurations above to "
            "continue. Step 6 cannot compute these rules safely."
        )
    elif any_rules:
        st.success(f"✅ Total Standard DQRs defined: **{total_rules}**")
    else:
        st.warning("⚠ Enable at least one DQR on at least one CDE to continue.")

    _nav(show_next=any_rules and not has_errors)


def _nav(show_next: bool = False) -> None:
    render_nav_footer(
        show_next=show_next,
        next_message="Next step → Custom DQR rules and overall weighting.",
        on_back=prev_step,
        on_next=next_step,
        on_restart=restart_app,
    )
