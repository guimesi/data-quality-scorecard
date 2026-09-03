# Handoff: DQ Scorecard — UI/UX redesign (Streamlit)

Target repo: `guimesi/data-quality-scorecard`, branch `feature/databricks-app-migration`.
Stack: **Streamlit ≥ 1.40**, Python, Databricks Apps. Keep Streamlit — no frontend framework.

## Overview
Redesign of the whole Data Quality Scorecard app so it reads as an enterprise data-platform product instead of a Streamlit prototype: one navigation rail, one page-header pattern, one card taxonomy, one brand colour plus three DQ status colours, progressive disclosure in the wizard, and a dashboard with an *overview → problem → diagnosis → detail → action* narrative. Business logic (`src/*`, `config/*`, scoring, exports, persistence) must not change.

## About the design files
`prototype/DQ Scorecard Redesign.dc.html` is a **design reference built in HTML** (open it in a browser; needs `support.js` next to it). It is a clickable prototype of intended look and behaviour — **not code to copy**. The task is to recreate these screens **inside the existing Streamlit app** using native widgets (`st.container`, `st.columns`, `st.tabs`, `st.popover`, `st.dialog`, `st.status`, `st.pills`, `st.segmented_control`, `st.dataframe`, `st.data_editor`) plus the centralized stylesheet in `proposed/ui/_theme.py`. Where Streamlit cannot reproduce a detail exactly (e.g. clickable whole-card selection), use the nearest native pattern described in `IMPLEMENTATION.md`.

## Fidelity
**High-fidelity.** Colours, type sizes, spacing, radii and copy in the prototype are final. Recreate as closely as Streamlit allows; the `--dq-*` CSS variables in `_theme.py` are the source of truth.

## Files in this bundle
| File | Purpose |
|---|---|
| `AUDIT.md` | 34 concrete problems found in the current UI, grouped by hierarchy / navigation / wizard / One-click / dashboard / colour / cards / typography / states / a11y / CSS. Read first — each change below resolves one of these. |
| `IMPLEMENTATION.md` | **The work plan.** File-by-file changes, per-screen recipes, microcopy rules, Databricks constraints, and the list of tests to adapt. |
| `proposed/ui/_theme.py` | Drop-in replacement for `ui/_theme.py` (7 class families, CSS variables, 4 `!important`). |
| `proposed/.streamlit/config.toml` | New Streamlit theme (brand primary replaces default red). |
| `prototype/DQ Scorecard Redesign.dc.html` | Clickable reference, 12 screens, light/dark. Use the black top bar to jump between screens. |

## Screens (prototype ↔ repo module)
| # | Screen | Repo | What changes (summary) |
|---|---|---|---|
| 1 | Home — New scorecard / Saved projects | `ui/step_mode_selection.py` | Segmented control; two compact mode cards with "You choose / Automated" grid; "Recommended" badge on One-click; saved projects as a list with per-row Versions expander and Open button. |
| 2 | One-click | `ui/step_one_click.py`, `src/one_click.py` (add optional `progress` callback) | Two numbered sections (Domain radio-cards, System checkbox-cards with rule-count badge; 0-rule systems disabled) + sticky **Run plan** card holding the single primary button; `st.status` with 6 real phases. |
| 3 | Domain | `ui/step_00_domain_selection.py` | Two radio-cards with system chips; no summary box. |
| 4 | Systems | `ui/step_01_system_selection.py` | Connection line, checkbox-cards, inline tables expander with PRIMARY badge. |
| 5 | Data Products | `ui/step_02_data_product_review.py` | `st.status` build (collapses to ✓ line), header with inline Rows/Columns/Tables, source chips, preview expander. |
| 6 | CDEs | `ui/step_03_cde_selection.py` | Per-DP collapsible sections (valid ones collapsed to a ✓ row); selected chips with required-by rule ids; filter + "Select required by Custom DQRs · N"; `data_editor` columns renamed. |
| 7 | DQR sources | `ui/step_04_dqr_source_selection.py` | Two toggle-cards + split slider with two-tone bar. |
| 8 | Custom DQRs | `ui/step_04_2_custom_dqr.py` | Rule **rows** (toggle · id · name · type · blocking · coverage · expand); options inline in expanded body; footer carries the single block reason. |
| 9 | Weights | `ui/step_05_weight_assignment.py` | Standard / Custom side by side, table + number inputs, one bar + one line of state; collapsed rows for valid DPs. |
| 10 | Scorecard (dashboard) | `ui/step_06_dashboard.py`, `ui/step_06/*` | Header actions (Save project dialog · Export popover · ML Lab); overview score cards + **Needs attention**; detail for the selected DP only; tabs with rules table → failing rows side panel; **gauge removed**. |
| 11 | ML Lab | `ui/step_07_ml_lab.py`, `ui/step_07/_shared.py` | Read-only callout, pills DP picker, emoji-free tabs, chart + "Reading this" column; violet only on tag/callout/bars. |
| 12 | Usage & audit | `ui/step_adoption.py` | Admin strip of 6 KPIs, bar chart, two tables, filterable audit trail. |
| — | Rail + footer nav | `utils/session/sidebar.py`, `utils/ui_components.py`, `app.py` | Brand row · Workspace block · clickable stepper · Settings popovers (Dataset, Project filter) · Usage & audit link; sticky footer `Back · Restart… · message · Next`. Remove `st.title`. |

Exact copy for every header, badge, callout and footer message is in the prototype's logic (`header`, `footerMsgs`, card texts) — reuse it verbatim.

## Design tokens
Light (default) — dark values in the prototype `[data-theme="dark"]` block.

| Token | Value | Use |
|---|---|---|
| `--dq-bg` | `#F4F5F7` | app canvas |
| `--dq-sf` / `--dq-sf2` | `#FFFFFF` / `#F7F8FA` | cards / subtle panels, expanded bodies |
| `--dq-bd` / `--dq-bd2` | `#E2E5EA` / `#C9CED7` | borders / control borders |
| `--dq-tx` / `--dq-tx2` / `--dq-tx3` | `#15181E` / `#4A5262` / `#6F7787` | text / secondary / muted |
| `--dq-br` / `--dq-br-h` / `--dq-br-soft` / `--dq-br-tx` | `#2F52D1` / `#2745B3` / `#E8EDFB` / `#2745B3` | brand: primary buttons, selection ring, active nav, badges |
| `--dq-ok` / soft | `#1F7A4D` / `#E1F3E8` | Good (≥ green threshold) — glyph ✓ |
| `--dq-wn` / soft | `#A8650A` / `#FDF0D8` | Warning — glyph ▲ |
| `--dq-er` / soft | `#BF3A2F` / `#FBE6E3` | Poor — glyph ✕ (also blocking dot, drop alert) |
| `--dq-lab` / soft | `#6B47C9` / `#EEE8FB` | ML Lab tag/callout/bars, "required by" rule ids, Custom-source bars |
| `--dq-fill` | `#E7E9EE` | neutral badge / empty bar track |

Type: sans = Streamlit default (prototype uses IBM Plex Sans; optional via static assets); mono = `ui-monospace, Menlo, Consolas` for codes, ids, numbers, table cells.
Scale: eyebrow 11 uppercase `.07em` · captions 12–12.5 · body 13–13.5 · section 14/600 · card title 15–17/600 · h1 22/600 `-.015em` · metric 22 mono · score 34 mono `-.02em`.
Spacing: page padding 36 (26 top) · card padding 14–22 · grid gaps 12–24 · table cell 7–8 × 12 · rail width 232.
Radius: 10 cards · 8 callouts/grids · 6 controls · 5 code chips · 999 pills. Shadow: `0 1px 2px rgba(15,18,25,.05)` only; selected ring `0 0 0 3px --dq-br-soft`. No gradients.

## Interactions & states
- Rail: done steps clickable → `goto(step)`; current highlighted; Settings rows open `st.popover`; changing Dataset/Filter after data exists → `st.dialog` confirm.
- Footer: sticky (`st.container(key="nav_footer")`); Next disabled + amber message when blocked; Restart → `st.dialog`.
- Long operations: `st.status` with real phase labels (no fake %). Phases listed per screen in `IMPLEMENTATION.md` §6–7.
- Selection cards: brand border + 3px soft ring; checkbox/radio glyph inside.
- Dashboard: score card click selects DP; rules row select → failing rows panel; Export popover; Save project dialog with changelog.
- Status never by colour alone: pill = glyph + word; bars get text labels.
- Responsive: ≥ 1240 px full layouts; 1100–1240 px Run-plan aside and Needs-attention stack; < 1100 px 3-up grids → 2-up, rule rows → two lines, dashboard detail stacks. Streamlit equivalent: reduce `st.columns` counts (3 → 2) and stack Rules/Failing rows when `st.columns` would fall below ~300 px each.

## State (session_state additions)
`dash_selected_dp`, `dash_tab`, `expanded_{step}` (per-DP disclosure), `home_tab`, `rail_settings_*` — all UI-only. Existing keys (`app_mode`, `domain`, `selected_systems`, `data_products`, `configs`, `scorecards`, `sample_mode`, `planview_filter`, widget keys) are unchanged so tests keep working.

## Validation checklist (run after implementing)
`pytest -q` — adapt tests listed in `IMPLEMENTATION.md` §12; then manual: One-click end-to-end (mock mode), Step-by-step end-to-end incl. Restart and Back from every step, saved project open, exports, ML Lab, Usage & audit, sidebar toggles with confirm dialog, 1024/1280/1440 widths, `streamlit run app.py` with `DATA_SOURCE=databricks` env present (Databricks Apps startup).

## Suggested Claude Code prompt
> Read `design_handoff_dq_scorecard_redesign/README.md`, `AUDIT.md` and `IMPLEMENTATION.md`. Open the prototype HTML for reference. Implement the redesign in this Streamlit repo following IMPLEMENTATION.md file by file, starting with `config.toml`, `ui/_theme.py`, `app.py`, the rail and `ui_components`, then each step in order, then the dashboard. Do not change anything under `src/` except adding the optional `progress` callback to `run_one_click`. Adapt tests per §12 and run `pytest` after each screen.
