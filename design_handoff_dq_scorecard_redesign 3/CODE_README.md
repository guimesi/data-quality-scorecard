# Ready-made code — how to apply

Everything under `code/` is a drop-in for the same path in the repo. Copy first, then adapt the remaining steps mechanically.

## 1. Copy these files (overwrite)

```
code/app.py                          → app.py
code/.streamlit/config.toml          → .streamlit/config.toml        (from ../proposed/)
code/ui/_theme.py                    → ui/_theme.py
code/utils/ui_components.py          → utils/ui_components.py
code/utils/session/sidebar.py        → utils/session/sidebar.py
code/ui/step_mode_selection.py       → ui/step_mode_selection.py
code/ui/step_one_click.py            → ui/step_one_click.py
code/ui/step_03_cde_selection.py     → ui/step_03_cde_selection.py
code/ui/step_06_dashboard.py         → ui/step_06_dashboard.py
code/ui/step_06/_overview.py         → ui/step_06/_overview.py   (new)
code/ui/step_06/_dp_dashboard.py     → ui/step_06/_dp_dashboard.py
```

Then two one-line edits:
- `utils/session/state.py` → `STEP_LABELS`: `"one_click": "Domain & systems"`, `"dqr_source_selection": "DQR sources"`, `"dqr_assignment": "Standard DQRs"`, `"dqr_custom_rules": "Custom DQRs"`, `"dashboard": "Scorecard"`, `"ml_lab": "ML Lab"`, `"adoption": "Usage & audit"`.
- `utils/colors.py` → `STATUS_GREEN = "#1F7A4D"`, `STATUS_YELLOW = "#A8650A"`, `STATUS_RED = "#BF3A2F"`.
- `src/one_click.py` → add `progress: Callable[[str, str], None] | None = None` to `run_one_click` and call `progress("Loading tables", …)`, `progress("Building Data Products", …)`, `progress("Profiling columns", …)`, `progress("Applying Custom DQRs", f"{n} rules")`, `progress("Computing scores")` at the existing phase boundaries. Nothing else changes.

Run `streamlit run app.py` (DATA_SOURCE=mock) and check Home, One-click, CDEs, Scorecard against the prototype before touching anything else.

## 2. Convert the remaining steps — same recipe every time

For each of `step_00_domain_selection.py`, `step_01_system_selection.py`, `step_02_data_product_review.py`, `step_04_dqr_source_selection.py`, `step_04_dqr_assignment.py`, `step_04_2_custom_dqr.py`, `step_05_weight_assignment.py`, `step_07_ml_lab.py` (+ `step_07/_shared.py`), `step_adoption.py`:

1. Replace the `.step-pill` markdown + `section_header(...)` with
   `page_header(step_eyebrow(), "<verb phrase>", "<≤ 20 words>")` — titles/subtitles are in the prototype's `header` map.
2. Delete every local `_SYSTEM_ICONS`, `_SYSTEM_ACCENTS`, `_DEFAULT_ACCENT`, `_inject_css`, `_dp_card_header`. Use `code_chip(code)` + a bold name, or `dp_summary_row(...)` for per-DP blocks.
3. Replace `st.success/info/warning/error` *status text* with `callout(text, kind)`; keep `st.error` only for real exceptions.
4. Replace `.sel-summary`, `.empty-notice`, `.cde-*`, `.ui-tip`, `.src-*`, `.weight-*`, `.pct-*`, `.rule-*`, `.lab-*` HTML with `badge`, `status_badge`, `progress_bar`, `dist_bar`, `kv_strip`, `callout`.
5. Remove the "preserved for parity" plain-text duplicates (`**Status:**`, `**⬇ Export**`, `**Source weights…**`, duplicated captions).
6. Nav: `render_nav_footer(...)` with the block reason as `blocked_message`; delete per-step `st.error` recaps of the same reason.
7. Per-DP steps (04, 04.2, 05): wrap each DP in `st.container(border=True)`; header via `dp_summary_row`; only the first invalid DP expanded (see `step_03` for the pattern with `session_state["expanded_<step>"]`).
8. No emojis anywhere (labels, buttons, tabs, metric names, column names).

Specific notes:
- **step_01**: connection banner → `callout("● Connected to <code>catalog.schema</code>", "info")`; tables expander inside the card via `after_control`.
- **step_02**: build inside `st.status("Building Data Products…", expanded=True)` → `status.update(label="Built N Data Products from M tables", state="complete", expanded=False)`; header row = `code_chip + name` left, `kv_strip([("Rows", …), ("Columns", …), ("Tables", …)])` right; drop the 3 `st.metric`.
- **step_04_dqr_assignment (4.1)**: follow the recipe in `FEATURE_INVENTORY.md` (CDE rows × 10 dimension toggles, inline params, validation status, first blocker in the footer).
- **step_04**: two bordered columns with `st.toggle` each; split via `st.slider` + `progress_bar(std, "brand")` legend line "Standard 70% · Custom 30%".
- **step_04_2**: rule rows `st.columns([0.5, 0.9, 4, 1.2, 1.2, 2.4, 0.4])` = toggle (keep key `custom_{sys}_{rule}_enabled`) · `code_chip(id)` · name + muted description · `badge(type)` · blocking (dot + word) · coverage (`dq-status good/warn`) · expand (tertiary button). Options render inline in the expanded body; `help=` instead of nested "How this option works" expanders.
- **step_05**: two columns Standard / Custom, table header via HTML, `st.number_input(label_visibility="collapsed")`, footer of each column = `progress_bar(total, "good"|"warn")` + one line `✓ Sums to 100%` / `▲ 15.00% still unassigned`. Delete the `st.success/warning` lines.
- **step_07**: header actions via `st.columns` right-aligned: `st.popover("Engine")` (sklearn toggle) and `← Dashboard`; `callout("<b>Read-only</b> — nothing here changes scores, rules, weights or exports.", "lab")`; DP picker `st.pills`; tabs without emojis; each tab = one-sentence explainer + chart + "Reading this" column. Delete the container/metric repaint in `_shared._inject_css` (keep the function as a no-op).
- **step_adoption**: KPIs as `kv_strip` in one bordered container; `page_header("Admin", "Usage & audit", …)`; Back only.

## 3. Tests to touch (expected failures after copying)

- `test_step_mode_selection_ui.py::test_sidebar_progress_shows_only_mode_step_before_pick` — passes (`Progress · Step 1 of 1`).
- `test_session_state.py::test_render_progress_sidebar_marks_current_bold` — passes (`class="dq-step sb-step current"` contains `sb-step current`).
- `test_ui_units.py` / `test_ui_flow.py`: remove assertions on `"**Status:**"`, `"**⬇ Export**"`, `"Source weights (set in Step 4)"`, emoji labels (`"🟢 Green"` in UI strings — `score_label` itself is unchanged for CSV exports).
- `test_step_06_*`: `_gauge` removed from `__all__`; detail renders only `dash_selected_dp` (default = worst score) — set `at.session_state["dash_selected_dp"] = "<code>"` when a test needs another DP. Download buttons keep keys `dl_csv_{code}` / `dl_json_{code}` (now inside the Export popover).
- `test_step_one_click_ui.py`: `st.spinner` → `st.status`; disabled checkbox for 0-rule systems (key unchanged `oneclick_sys_{code}`).
- `test_step_04_2_custom_ui.py`: rows instead of cards; checkbox keys unchanged.

## 4. Feature safety

Before finishing each module, tick it off in `FEATURE_INVENTORY.md` — every current feature has a row there; nothing may be removed, only re-homed (e.g. Airtable → Export popover).

## 5. Prompt for Claude Code (paste as-is)

> In `design_handoff_dq_scorecard_redesign/code/` there are finished files. Step 1: copy every file to the same path in the repo (overwrite), apply the three one-line edits in `design_handoff_dq_scorecard_redesign/CODE_README.md §1`, run `streamlit run app.py` with `DATA_SOURCE=mock` and confirm Home, One-click, CDEs and Scorecard render without exceptions. Do NOT redesign, rename, or "improve" these files. Never remove a feature: check `FEATURE_INVENTORY.md` for where each one now lives. Step 2: convert the remaining step modules one at a time following `CODE_README.md §2`, using only the helpers in `utils/ui_components.py` — no new CSS, no new classes, no emojis, no `st.title`. After each module run `pytest -q tests/` and fix only the assertions listed in §3. Stop and show me a screenshot after each module.
