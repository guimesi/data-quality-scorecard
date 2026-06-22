"""
Step 3: CDE selection.

For each Data Product, the user marks Critical Data Elements (CDEs) directly
inside a unified profile grid. Each row is one source column with its dtype,
null %, distinct count, duplicate count and sample values; the user toggles
the **Pick as CDE** checkbox to add or remove the column from the selection.

Above the grid, a chip-strip lists the columns currently selected as CDEs.
Each chip carries a native HTML ``title`` tooltip with the column's full
profile, so the user can re-read the metadata at a glance without scrolling
back to its row in the grid.

Why no drag-and-drop?
---------------------
The previous implementation used ``streamlit-sortables`` for a left/right
drag-and-drop. In practice the widget's component-state synchronization had
two problems:

1. Dragged items would occasionally vanish without landing in the right-hand
   container - likely because the component re-emitted partial state across
   reruns when both lists were re-derived from the parent's session state.
2. The hover legend rendered above the widget always reflected the *previous*
   render's selection, since the widget mutates session state mid-render.

A ``st.data_editor`` checkbox grid is fully Streamlit-native, treats each
selection as a deterministic edit on a DataFrame, and re-renders top-to-bottom
on every change, so the chip-strip and the success / warning banners stay in
lockstep with the actual ``cfg.cdes`` value.
"""
from __future__ import annotations

import html
from typing import Dict, List

import pandas as pd
import streamlit as st

from config.custom_dqr_catalog import get_available_custom_dqr_rules
from src.models import ColumnProfile
from utils.helpers import section_header
from utils.session_state import next_step, prev_step, restart_app
from utils.ui_components import render_nav_footer

# Symbol used to flag columns that are required by at least one Custom DQR.
# Distinct from the ⭐ used for "selected CDE" so the two cues don't collide
# in the chip strip / grid.
_CUSTOM_DQR_FLAG = "🎯"

# Visual identity per system, mirrors Step 1 / Step 2 for visual coherence.
_SYSTEM_ICONS = {"ADR": "📊", "ACCE": "📈", "EPT": "🗂️"}
_SYSTEM_ACCENTS = {"ADR": "#3b82f6", "ACCE": "#8b5cf6", "EPT": "#0ea5e9"}
_DEFAULT_ACCENT = "#6366f1"


# Chip styling for the hover-info badges rendered above the grid.
# Kept inline (no global stylesheet) so the rendering stays a self-contained
# concern of this step.
_CHIP_STYLE = (
    "display:inline-block;"
    "padding:3px 11px;"
    "margin:3px 4px 3px 0;"
    "border:1px solid rgba(99,102,241,0.25);"
    "border-radius:999px;"
    "background:linear-gradient(180deg, rgba(238,242,255,0.9), rgba(248,250,252,0.85));"
    "font-size:0.82em;"
    "font-family:'Source Sans Pro', sans-serif;"
    "color:#1f2937;"
    "cursor:help;"
    "transition:transform 0.1s ease, box-shadow 0.1s ease;"
)

# The "Pick as CDE" checkbox is the only editable cell. Every other column in
# the grid is read-only profile metadata; locking them prevents accidental
# typos that would produce a noisy diff between the grid and ``cfg.cdes``.
_PICK_COLUMN = "Pick as CDE"
_CUSTOM_DQR_COLUMN = "Custom DQRs"
_READ_ONLY_COLUMNS: List[str] = [
    "Column", _CUSTOM_DQR_COLUMN, "Type", "Dtype", "Rows", "Null %",
    "Distinct", "Duplicates", "Sample",
]


def _build_required_columns_map(system_code: str) -> Dict[str, List[str]]:
    """Return ``physical_column → [rule_id, ...]`` for every column the
    Custom DQR catalog needs for ``system_code``.

    Includes both static ``required_columns`` and any extras a rule's
    options would need when toggled on, since Step 3 happens *before* the
    user picks options in Step 4.2 - surfacing the union lets the user
    ship a CDE selection that supports any rule path they may take.
    Order is preserved: rules are listed in catalog order, and within a
    column the rule IDs follow the order in which the rule first declared
    the column."""
    out: Dict[str, List[str]] = {}
    for rule in get_available_custom_dqr_rules(system_code):
        seen: set = set()
        for col in rule.required_columns.values():
            if col in seen:
                continue
            seen.add(col)
            out.setdefault(col, []).append(rule.id)
        for opt in rule.options:
            for col in opt.required_columns_when_enabled.values():
                if col in seen:
                    continue
                seen.add(col)
                out.setdefault(col, []).append(rule.id)
    return out


def _format_profile_tooltip(profile: ColumnProfile) -> str:
    """Build the multi-line text that backs a chip's HTML ``title``
    attribute. Browsers render ``title`` text on hover with native styling,
    and newlines must be encoded as ``\\n`` so they survive HTML attribute
    parsing."""
    sample_preview = ", ".join(str(v) for v in profile.sample_values[:5]) or "-"
    range_line = ""
    if profile.min_value is not None or profile.max_value is not None:
        range_line = f"\nRange: {profile.min_value} → {profile.max_value}"
    return (
        f"Column: {profile.name}\n"
        f"Dtype: {profile.dtype} (group: {profile.column_type_group})\n"
        f"Rows: {profile.total_rows:,}\n"
        f"Nulls: {profile.null_count:,} ({profile.null_pct}%)\n"
        f"Distinct: {profile.distinct_count:,}\n"
        f"Duplicates: {profile.duplicate_count:,}"
        f"{range_line}\n"
        f"Sample: {sample_preview}"
    )


def _render_selected_cde_legend(
    columns: List[str],
    profiles: Dict[str, ColumnProfile],
    required_by_rule: Dict[str, List[str]],
) -> None:
    """Render a chip-strip of the currently-selected CDEs. Each chip carries
    the column's full profile in its ``title`` attribute - hover surfaces
    the same data shown in the row below, so the user can re-confirm a pick
    without scrolling. When a column is required by one or more Custom DQRs
    the chip also surfaces the rule IDs inline (with the 🎯 cue) so the
    user can see at a glance which picks are powering which rules."""
    if not columns:
        st.markdown(
            "<div class='cde-empty'>"
            "⚠️ No CDE selected yet - pick at least one in the grid below."
            "</div>",
            unsafe_allow_html=True,
        )
        return

    chips: List[str] = []
    for col in columns:
        profile = profiles.get(col)
        if profile is None:
            tooltip = f"Column: {col}\n(no profile available)"
        else:
            tooltip = _format_profile_tooltip(profile)
        rule_ids = required_by_rule.get(col, [])
        if rule_ids:
            tooltip += f"\nRequired by Custom DQRs: {', '.join(rule_ids)}"
            suffix = (
                f" <span style='color:#7c3aed; font-weight:600;'>"
                f"{_CUSTOM_DQR_FLAG} {html.escape(', '.join(rule_ids))}</span>"
            )
        else:
            suffix = ""
        chips.append(
            f'<span style="{_CHIP_STYLE}" title="{html.escape(tooltip)}">'
            f"⭐ {html.escape(col)}{suffix}</span>"
        )
    st.markdown(
        f"<div style='margin-bottom:0.4em;'>"
        f"<div style='font-size:0.85em; color:rgba(49,51,63,0.7); "
        f"margin-bottom:0.3em;'>"
        f"<b>⭐ Selected CDEs ({len(columns)})</b> - hover any badge for the full "
        f"profile · {_CUSTOM_DQR_FLAG} marks columns required by a Custom DQR"
        f"</div>"
        f"<div>{''.join(chips)}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )


def _distinct_sample_for(dp, col: str, n: int = 3) -> List:
    """Return up to ``n`` distinct non-null values from ``dp.df[col]``,
    preserving first-occurrence order.

    Step 3's grid surfaces distinct values (rather than the first N raw
    values from the profile) so a column with many repeated values still
    yields a useful preview of its domain. ``pd.Series.drop_duplicates``
    preserves source order, so the preview lines up with what the user
    would see scrolling the column."""
    if col not in dp.df.columns:
        return []
    distinct = dp.df[col].dropna().drop_duplicates().head(n).tolist()
    return [v.item() if hasattr(v, "item") else v for v in distinct]


def _build_profile_grid(
    dp,
    current_cdes: List[str],
    required_by_rule: Dict[str, List[str]],
) -> pd.DataFrame:
    """Return one row per source column with its profile + a Pick checkbox.
    The DataFrame is the input/output contract of the data-editor, so the
    column order of ``dp.df`` is preserved, that ordering then flows into
    ``cfg.cdes`` for downstream displays.

    ``required_by_rule`` (column → list of Custom DQR rule IDs) drives the
    ``Custom DQRs`` column: rows where the source column powers at least
    one rule are flagged with the 🎯 cue followed by the rule IDs (e.g.
    ``🎯 E1, E3``); other rows leave the cell empty.

    The ``Sample`` cell shows the first 3 *distinct* non-null values of
    each source column (via :func:`_distinct_sample_for`) instead of the
    first 3 raw values stored on the profile - a column with a lot of
    repeated values then surfaces a more useful preview of its domain."""
    show_custom_dqr_col = bool(required_by_rule)
    rows = []
    for col in dp.df.columns:
        profile = dp.profiles.get(col)
        row: Dict[str, object] = {
            _PICK_COLUMN: col in current_cdes,
            "Column": col,
        }
        if show_custom_dqr_col:
            rule_ids = required_by_rule.get(col, [])
            row[_CUSTOM_DQR_COLUMN] = (
                f"{_CUSTOM_DQR_FLAG} {', '.join(rule_ids)}" if rule_ids else ""
            )
        row.update({
            "Type": profile.column_type_group if profile is not None else "-",
            "Dtype": profile.dtype if profile is not None else "-",
            "Rows": profile.total_rows if profile is not None else 0,
            "Null %": profile.null_pct if profile is not None else 0.0,
            "Distinct": profile.distinct_count if profile is not None else 0,
            "Duplicates": profile.duplicate_count if profile is not None else 0,
            "Sample": (
                ", ".join(str(v) for v in _distinct_sample_for(dp, col, 3))
                if profile is not None else ""
            ),
        })
        rows.append(row)
    return pd.DataFrame(rows)


def _dp_card_header(code: str, dp) -> None:
    """Render the per-card icon, name, code pill, accent strip and metadata
    line. Visually equivalent to the title used in earlier versions, just
    more polished."""
    icon = _SYSTEM_ICONS.get(code, "📦")
    accent = _SYSTEM_ACCENTS.get(code, _DEFAULT_ACCENT)
    st.markdown(
        f"""
        <div class="dp-card-accent" style="background: {accent};"></div>
        <div class="dp-card-title">
            <span class="dp-icon">{icon}</span>
            <span class="dp-name">{html.escape(dp.name)}</span>
            <span class="dp-code">{html.escape(code)}</span>
        </div>
        <div class="dp-meta">
            <b>{dp.row_count:,}</b> rows · <b>{dp.column_count}</b> columns
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_dp_block(system_code: str, dp) -> None:
    """Render the chip-strip + profile-grid selection UI for one DP.

    Two contracts have to hold for the user-perceived behavior to match the
    expectation "one click ticks the row":

    1. **Stable data_editor input across reruns.** Streamlit's
       ``st.data_editor`` discards every accumulated user edit whenever the
       input DataFrame's *content* changes between reruns (documented
       behavior, it's how the widget supports externally-driven refreshes).
       If we rebuild the grid from ``cfg.cdes`` each render, then a click
       updates ``cfg.cdes``, the *next* render feeds the editor a different
       input DataFrame, and the click is wiped before it ever takes effect.
       The user sees the row stay unticked, has to click again on the now-
       restored base, and only the *second* click "sticks". To prevent
       this, we cache the input DataFrame in ``session_state`` keyed by
       ``id(dp)``, the cache is invalidated only when the underlying
       ``DataProduct`` instance actually changes (revisit to Step 2,
       Restart). Within a single step-3 session the input is bit-identical
       across reruns and the editor preserves the click.

    2. **Render order matters.** The chip-strip and the success banner
       have to use the *post-edit* selection, not ``cfg.cdes`` from before
       ``data_editor`` returned. We reserve an ``st.empty`` slot above the
       grid and populate it *after* reading the edited DataFrame, so the
       chips and the banner always agree on the same render.
    """
    cfg = st.session_state.configs[system_code]
    required_by_rule = _build_required_columns_map(system_code)

    # Cache the editor's base DataFrame across reruns. ``id(dp)`` is stable
    # while the user is in Step 3 and changes whenever Step 2 rebuilds the
    # data products (e.g., user changed the system selection in Step 1, hit
    # Restart, or toggled Sample mode). Keying both the cached base AND the
    # editor's widget key on ``id(dp)`` guarantees a clean reset whenever
    # the underlying data changes, and a *bit-stable* input across the
    # clicks the user makes within a single step-3 session.
    dp_token = id(dp)
    base_key = f"cde_grid_base_{system_code}_{dp_token}"
    editor_key = f"cde_grid_{system_code}_{dp_token}"
    select_all_key = f"cde_select_all_required_{system_code}_{dp_token}"

    if base_key not in st.session_state:
        # First entry to this step (or DP changed): seed the grid from
        # cfg.cdes so any existing picks appear ticked on render 1.
        st.session_state[base_key] = _build_profile_grid(
            dp, list(cfg.cdes), required_by_rule
        )

    # Placeholder slot for the chip-strip - visually above the grid, but
    # populated *after* the editor applies the user's tick (see contract #2).
    chip_slot = st.empty()

    if required_by_rule:
        st.markdown(
            f"""
            <div class="ui-tip">
                💡 Tick the <b>Pick as CDE</b> column on each row you want to mark
                as a Critical Data Element. Rows flagged {_CUSTOM_DQR_FLAG} in
                the <b>Custom DQRs</b> column are required by one or more Custom
                DQR rules in Step 4.2 - pick those CDEs if you want to apply the
                listed rules, or use the
                <b>{_CUSTOM_DQR_FLAG} Select all CDEs required by Custom DQRs</b>
                shortcut below to tick every flagged row at once. The badges above
                and the success banner below update on the same render, one click
                is enough.
            </div>
            """,
            unsafe_allow_html=True,
        )
        # One-click shortcut to tick every column that powers a Custom DQR.
        # The button is rendered before the data_editor so that, on the
        # rerun triggered by the click, we can rebuild the cached base
        # DataFrame *before* the editor consumes it, the new ticks then
        # land on the very next render without an extra rerun. Existing CDE
        # picks are unioned in source-column order so manual picks survive.
        action_col, _ = st.columns([2, 3])
        with action_col:
            if st.button(
                f"{_CUSTOM_DQR_FLAG} Select all CDEs required by Custom DQRs "
                f"({len(required_by_rule)})",
                key=select_all_key,
                help=(
                    "Mark every column flagged in the Custom DQRs column as a "
                    "CDE. Existing CDE picks are preserved."
                ),
                use_container_width=True,
            ):
                required_cols = set(required_by_rule.keys())
                current_cdes = set(cfg.cdes)
                new_cdes = [
                    col for col in dp.df.columns
                    if col in current_cdes or col in required_cols
                ]
                cfg.cdes = new_cdes
                # Rebuild the cached base so the editor reflects the union on
                # this very render, the data_editor sees a new content-shape,
                # discards any accumulated edits, and shows the new picks.
                st.session_state[base_key] = _build_profile_grid(
                    dp, new_cdes, required_by_rule
                )
                # Drop the editor's stored widget state for good measure so the
                # next render starts from the fresh base with no stale edits.
                if editor_key in st.session_state:
                    del st.session_state[editor_key]
    else:
        st.markdown(
            """
            <div class="ui-tip">
                💡 Tick the <b>Pick as CDE</b> column on each row you want to mark
                as a Critical Data Element. The badges above and the success
                banner below update on the same render, one click is enough.
            </div>
            """,
            unsafe_allow_html=True,
        )

    edited = st.data_editor(
        st.session_state[base_key],
        column_config={
            _PICK_COLUMN: st.column_config.CheckboxColumn(
                _PICK_COLUMN,
                help="Tick to include this column as a CDE.",
                default=False,
            ),
            _CUSTOM_DQR_COLUMN: st.column_config.TextColumn(
                _CUSTOM_DQR_COLUMN,
                help=(
                    "Custom DQRs (Step 4.2) that need this column. "
                    f"{_CUSTOM_DQR_FLAG} marks columns you should pick as "
                    "CDEs to enable the listed rules."
                ),
                width="small",
            ),
            "Null %": st.column_config.ProgressColumn(
                "Null %", min_value=0, max_value=100, format="%.1f%%",
            ),
            "Sample": st.column_config.TextColumn(
                "Sample (first 3 distinct values)", width="medium",
            ),
        },
        disabled=_READ_ONLY_COLUMNS,
        hide_index=True,
        use_container_width=True,
        height=380,
        key=editor_key,
    )

    # Sync back to session state. The grid preserves source-column order, so
    # ``cfg.cdes`` lines up with ``dp.df.columns`` for downstream displays.
    # Cast to bool so any odd object-dtype values from an empty grid don't
    # break the boolean filter.
    new_cdes = edited.loc[edited[_PICK_COLUMN].astype(bool), "Column"].tolist()
    cfg.cdes = new_cdes

    # Now populate the chip-strip slot with the post-edit selection (see
    # contract #2 above).
    with chip_slot.container():
        _render_selected_cde_legend(new_cdes, dp.profiles, required_by_rule)

    # Post-grid summary, same semantics as the previous st.success /
    # st.warning, just unified into colour-coded callouts.
    if new_cdes:
        inline_chips = "".join(
            f'<span class="cde-chip-inline">⭐ {html.escape(c)}</span>'
            for c in new_cdes
        )
        st.markdown(
            f"""
            <div class="cde-success">
                <div class="cde-success-title">
                    ✅ {len(new_cdes)} CDE(s) selected for this Data Product
                </div>
                <div>{inline_chips}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='cde-empty'>"
            "⚠️ No CDE selected yet for this Data Product."
            "</div>",
            unsafe_allow_html=True,
        )


def render() -> None:

    # ── Intro ────────────────────────────────────────────────────────────
    st.markdown('<div class="step-pill">Step 3 · CDE Selection</div>',
                unsafe_allow_html=True)
    section_header(
        "Step 3 - CDE selection",
        "Mark the columns considered critical (CDEs) using the **Pick as CDE** "
        "checkbox on each row. Profile info (null %, distinct count, sample "
        "values) is shown inline so you can decide without leaving the grid. "
        f"Columns flagged {_CUSTOM_DQR_FLAG} in the **Custom DQRs** column "
        "are required by one or more Custom DQR rules you can apply in Step "
        "4.2 - the cell lists the rule IDs (e.g. `E1, E3`) so you know which "
        "rules each pick will enable. Selected columns appear as badges above "
        "the grid - hover any badge for the column's full profile.",
    )

    dps = st.session_state.data_products
    if not dps:
        st.error("🚫 Data products not built. Go back to step 2.")
        _nav()
        return

    st.markdown("---")

    for code, dp in dps.items():
        with st.container(border=True):
            _dp_card_header(code, dp)
            _render_dp_block(code, dp)

    st.markdown("---")
    any_cdes = any(cfg.cdes for cfg in st.session_state.configs.values())
    _nav(show_next=any_cdes)


def _nav(show_next: bool = False) -> None:
    render_nav_footer(
        show_next=show_next,
        next_message=(
            "Next step → review and apply Data Quality Rules to the selected CDEs."
        ),
        blocked_message=(
            "Pick at least one CDE in any Data Product to enable the next step."
        ),
        on_back=prev_step,
        on_next=next_step,
        on_restart=restart_app,
    )
