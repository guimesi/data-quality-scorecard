# Feature inventory — nothing gets dropped

Every user-facing capability of the current app, where it lives in the redesign, and its status.
**Legend** — Proto: visible in the HTML prototype · Code: implemented in `code/` · Recipe: covered by `CODE_README.md §2` instructions (Claude Code converts it) · Keep: untouched module.

| Area | Feature (current app) | Redesign location | Proto | Code | Notes |
|---|---|---|---|---|---|
| Home | Mode cards One-click / Step-by-step | Home · New scorecard | ✓ | ✓ | copy shortened, "Recommended" badge |
| Home | Open a saved project (+ version picker, changelog) | Home · Saved projects tab | ✓ | ✓ | list + Versions expander + Open |
| Home | Usage & audit button | Rail footer link | ✓ | ✓ | moved out of the flow |
| One-click | Domain + systems, rule-count badge | One-click | ✓ | ✓ | 0-rule systems disabled with reason |
| One-click | Pre-validation (no domain / no system / no rules) | Run plan callouts | ✓ | ✓ | |
| One-click | Generate → dashboard | Run plan button | ✓ | ✓ | `st.status` phases (needs `progress` kwarg) |
| One-click | Summary banner (scored / skipped / warnings / CSV errors) | Dashboard top line + **Run details** popover | ✓ | ✓ | |
| Step 0 | Domain cards, placeholder badge, systems row | Domain | ✓ | Recipe | |
| Step 1 | Mock / Databricks connection banner | Systems · connection line | ✓ (connected) | Recipe | mock variant: same line, "Mock data · set DATA_SOURCE=databricks" |
| Step 1 | System cards + tables expander + PRIMARY | Systems | ✓ | Recipe | |
| Step 2 | Build with spinner, filter banner, empty-filter callout, reference-dataset errors | Data Products | ✓ (build status) | Recipe | filter banner → `callout("Project filter · N ids", "info")`; ref-dataset errors → `callout(..., "warn")` with expander for details |
| Step 2 | Metrics + preview | Data Products | ✓ | Recipe | |
| Step 3 | Profile grid, Pick checkbox, chips w/ tooltip, Select-all-required | CDEs | ✓ | ✓ | tooltip → hover on grid row (data_editor `help`), chips keep rule ids |
| **Step 4.1** | **Standard DQRs per CDE × 10 dimensions, suggestions, apply-all-suggested, inline params, validation ✓/▲/✕, Next gating** | **Standard DQRs** (new screen in proto) | ✓ | Recipe | was missing from the prototype — added; see recipe below |
| Step 4 | Source checkboxes + split slider | DQR sources | ✓ | Recipe | |
| Step 4.2 | Rule cards, Apply, options (select/toggle), details, CDE coverage, select-all, blocking gate | Custom DQRs | ✓ | Recipe | rows instead of cards; keys unchanged |
| Step 5 | Standard/Custom weights, distribute equally, 100% gating | Weights | ✓ | Recipe | |
| Dashboard | Overview per DP | Score cards | ✓ | ✓ | + Δ vs previous run, + Needs attention |
| Dashboard | Gauge | removed | — | — | replaced by score + status + distribution bar (same numbers) |
| Dashboard | Threshold bar + 4 metrics | Header strip (rows G/Y/R) + `dist_bar` | ✓ | ✓ | |
| Dashboard | Source weights + sub-scores | Header strip | ✓ | ✓ | |
| Dashboard | Tabs By CDE / By Dimension (click drill-down) | CDEs / Dimensions tabs | ✓ (CDEs) | ✓ | glyph labels on bars |
| Dashboard | Rules table + drill-down | Rules tab (side panel) | ✓ | ✓ | |
| Dashboard | Custom rules table + drill-down + not-evaluated warnings | Custom rules tab | placeholder | ✓ | `_render_custom_rules_table` unchanged |
| Dashboard | Worst rows | Failing rows tab | placeholder | ✓ | |
| Dashboard | History tab (trend, run log, what changed) | History tab | placeholder | ✓ | `_render_history_tab` unchanged |
| Dashboard | Drop alert | Detail card top | — | ✓ | `_render_drop_alert` unchanged |
| Dashboard | CSV / JSON per DP | **Export** popover | ✓ | ✓ | keys `dl_csv_*` / `dl_json_*` kept |
| Dashboard | Executive report (HTML) | **Export** popover | ✓ | ✓ | |
| Dashboard | **Send to Airtable** | **Export** popover (when configured) | ✓ | ✓ | `_render_airtable_push` unchanged, called via `_render_executive_report_download` |
| Dashboard | Save as project + changelog | **Save project** dialog | ✓ (button) | ✓ | `_render_project_save_panel` unchanged inside `st.dialog` |
| Dashboard | ML Lab button | Header action | ✓ | ✓ | |
| Dashboard | Failed-DP error list | callout | — | ✓ | |
| ML Lab | Banner, sklearn badge/toggle, DP picker, 9 tabs, overview metrics, back to dashboard | ML Lab | ✓ (1 tab) | Recipe | all 9 tab modules untouched; only chrome changes |
| Usage & audit | 6 KPIs, last activity, runs/week, by system, by user, audit trail, back | Usage & audit | ✓ (by-user table omitted in proto) | Recipe | keep all tables |
| Sidebar | Brand, progress, sample-mode toggle, project filter, footer version | Rail | ✓ | ✓ | toggle/filter in popovers; confirm dialog before wiping data |
| Nav | Back / Next / Restart (confirm) / scroll-to-top | Footer + `consume_scroll_to_top` | ✓ | ✓ | Restart = `st.dialog` |
| Telemetry | app_open, step_view, export, project events | unchanged | — | Keep | |
| Persistence / Databricks | all | unchanged | — | Keep | |

## Step 4.1 recipe (Standard DQRs) — add to CODE_README §2

`ui/step_04_dqr_assignment.py`:
- `page_header(step_eyebrow(), "Apply Standard DQRs", "Pick the dimensions to check on each CDE. Suggested ones come from the column profile; each rule is validated against the data type.")`
- Per DP: `st.container(border=True)`; header row = `code_chip(code)` + name + `"{n} CDEs · {m} rules applied"` + status badge (`poor` if any error, `warn` if warnings, `good` otherwise) + right-aligned `Apply all suggested · N` (existing `apply_all_suggestions_{code}` key).
- Per CDE: `dp_summary_row`-style line (mono column name · type/nulls/distinct · status · "N suggested" · "k of 10"); expanded body lists the 10 dimensions as rows: `st.toggle` (key `{sys}_{cde}_{dim}_enabled`, unchanged) · name + `badge("Suggested","brand")` when pending · inline params (`_render_param_editor`, unchanged) shown only when on · validation as `dq-status good/warn/poor` + message (`_render_validation_feedback` → single line each; suggestion text into `help=`).
- Only the first CDE with an error/no rules starts expanded (`session_state["expanded_std_{code}"]`).
- Delete `_render_cde_header` HTML, `_render_dp_status` pills + `st.error/warning` duplicates; the footer message carries the first blocker: `blocked_message="ADR · PLANVIEW_ID · Uniqueness is incompatible — turn it off or pick another dimension"`.
- Keep: `_pending_suggestions_for_dp`, `_render_param_editor`, validation gating logic.

## Out of scope (unchanged, flagged for later)
- `ui/step_06/_exec_report.py` — the exported HTML still uses the old colours and emoji headings; restyle with the new tokens in a follow-up (pure template change).
- `src/*` — no changes except the optional `progress` callback.
