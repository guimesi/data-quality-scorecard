# Implementation guide — DQ Scorecard redesign

Companion to the prototype `DQ Scorecard Redesign.dc.html` (light/dark via Tweaks) and `AUDIT.md`. Every item maps a prototype decision to concrete Streamlit (≥ 1.40) code in this repo. Business logic (`src/*`, `config/*`) is untouched.

---

## 0. Design direction

| Axis | Decision |
|---|---|
| Brand / interaction | one blue `#2F52D1` (primary buttons, focus, selection ring, active nav). Set in `config.toml` so native widgets stop rendering Streamlit red. |
| DQ status | Good `#1F7A4D` · Warning `#A8650A` · Poor `#BF3A2F` — same lightness/chroma, hue only. Always paired with a glyph (✓ ▲ ✕) and a word. **Never** used for buttons or "blocking" tags. |
| Feature accents | ML Lab violet `#6B47C9` only on the BETA tag, callout, and its bars. One-click gets **no** colour — it is a "Recommended" brand badge. |
| Neutrals | canvas `#F4F5F7`, surface `#FFF`, subtle `#F7F8FA`, borders `#E2E5EA/#C9CED7`, text `#15181E/#4A5262/#6F7787`. |
| Type | one sans (Streamlit default / system) + mono for codes, IDs, numbers. Sizes: eyebrow 11 · body 13–13.5 · h1 22 · metric 22 · score 34. |
| Shape | radius 10 (cards) / 8 (callouts) / 6 (controls) / 999 (pills). No gradients, no hover shadows. |
| Density | GitHub-like: 12–14 px paddings, 6–8 px table cells. |
| Dark mode | `[theme] base="dark"` in a second config or user toggle; all custom CSS uses `--dq-*` vars so only `:root` changes (see prototype dark tokens). |

---

## 1. Files to change

| File | Change |
|---|---|
| `.streamlit/config.toml` | **new** — see `handoff/.streamlit/config.toml`. |
| `ui/_theme.py` | replace with `handoff/ui/_theme.py` (7 class families, no gradients, 4 `!important`). |
| `app.py` | remove `st.title("Data Quality Scorecard")`; drop `render_sidebar_footer()`; call `render_sidebar_rail()`; keep `inject_global_css()`. |
| `utils/session/sidebar.py` | rewrite render functions as a **rail** (§3). Keep `get_row_limit`, `get_planview_filter`, `_parse_planview_filter_text` unchanged. |
| `utils/session/state.py` | `STEP_LABELS`: `"dqr_source_selection": "DQR sources"`, `"dqr_assignment": "Standard DQRs"`, `"dqr_custom_rules": "Custom DQRs"`, `"dashboard": "Scorecard"`, `"ml_lab": "ML Lab"`, `"adoption": "Usage & audit"`, `"one_click": "Domain & systems"`. |
| `utils/helpers.py` | `_STATUS_LABELS = {"green":"Good","yellow":"Warning","red":"Poor"}`; add `page_header(eyebrow, title, subtitle)` replacing `section_header` + `.step-pill` pairs; add `status_html(score, g, y)` → `<span class="dq-status good">Good</span>`. |
| `utils/ui_components.py` | `render_nav_footer` → sticky container `st.container(key="nav_footer")`; Restart as `st.dialog`; `render_choice_card` slimmed (§4); new `render_dp_summary_row`. |
| `utils/colors.py` | new hexes above (optional but recommended). |
| `ui/step_mode_selection.py` | §5 |
| `ui/step_one_click.py` | §6 |
| `ui/step_00…05` | §7 |
| `ui/step_06_dashboard.py`, `ui/step_06/_dp_dashboard.py`, `_breakdown.py`, `_charts.py` | §8 |
| `ui/step_07/_shared.py`, `ui/step_07_ml_lab.py` | §9 |
| `ui/step_adoption.py` | §10 |
| `tests/*` | §12 |

Delete: `ui/step_02_data_product_review._inject_css`, `ui/step_one_click._inject_css`, the container/metric repaint in `ui/step_07/_shared._inject_css` (keep only `.lab-*` → now `dq-callout.lab` / `dq-badge.lab`).

---

## 2. Page header (every step)

Replace the pair `st.markdown('<div class="step-pill">…')` + `section_header("Step 3 - CDE selection", long caption)` with:

```python
def page_header(eyebrow: str, title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="dq-eyebrow">{html.escape(eyebrow)}</div>'
                f'<h1 class="dq-title">{html.escape(title)}</h1>'
                + (f'<div class="dq-sub">{subtitle}</div>' if subtitle else ""),
                unsafe_allow_html=True)
```

Eyebrow = position + mode + domain (`"Step 4 of 8 · Step-by-step · Cost Estimate"`), computed from `_visible_steps()`. Title = verb phrase, no step number, no "Data Quality Scorecard". Subtitle ≤ 20 words; move everything else to `help=` tooltips. Copy per screen is in the prototype's `header` map.

---

## 3. Sidebar → navigation rail (`utils/session/sidebar.py`)

Order and rules:

1. **Brand row** — `.dq-brand` (mark + "DQ Scorecard" + version). No gradient card, no tagline, no domain icon.
2. **Workspace block** — only when `session_state.domain` is set and step ≠ adoption: domain name, mode badge, systems (mono). Replaces `sidebar_brand_subtitle/tagline`.
3. **Stepper** — title "Steps" (sbs) / "One-click" (oc). Rows `.dq-step done|current|todo`. Make *done* rows clickable: render each as `st.button(label, key=f"rail_{step}", type="tertiary", use_container_width=True)` inside a `.dq-step` wrapper **only for done steps** (`goto(step)`); current/todo stay static HTML. Show `meta` on the Systems row (selected codes) once past it.
4. **Settings** — hidden on `mode_selection` and `adoption`. Two rows, each an `st.popover(label)`:
   - *Dataset* → toggle inside popover; trigger shows badge "Sample · 50k rows" / "Full dataset".
   - *Project filter* → text area inside popover; badge "All projects" / "2 PLANVIEW_IDs".
   Changing either after `data_products` exist must open `st.dialog("Rebuild data products?")` before wiping state — today it silently drops the wizard progress.
5. **Footer** — `Usage & audit` as `st.button(type="tertiary")` → `goto("adoption")` + catalog.schema in mono. Remove the product description paragraph.

Remove: `.sb-*` classes, `render_sidebar_footer`, emoji icons.

---

## 4. Shared components (`utils/ui_components.py`)

**`render_choice_card`** — keep signature; inside: `st.container(border=True, key=f"choice_{select_key}")` so the selected ring can be applied by wrapping in `st.markdown('<div class="dq-choice-on">')`… actually use the key class: emit `<style>.st-key-choice_{key} div[data-testid=stVerticalBlockBorderWrapper]{border-color:var(--dq-br)!important;box-shadow:0 0 0 3px var(--dq-br-soft)}</style>` only when `selected`. Drop `card-accent`, `card-icon`, `desc_min_height_em` (use `st.columns` with equal heights via `vertical_alignment="top"` and short descriptions ≤ 25 words), drop the SELECTED badge (ring + checkbox/radio state is the indicator). Single-select: `st.radio`-like behaviour via `st.button(type="tertiary")`; multi: `st.checkbox`.

**`render_nav_footer`**:
```python
with st.container(key="nav_footer"):
    c_back, c_restart, c_msg, c_next = st.columns([1, 1, 5, 1.4], vertical_alignment="center")
    c_back.button("← Back", ...)
    if c_restart.button("Restart…", type="tertiary"): _confirm_restart()   # st.dialog
    c_msg.markdown(f'<div class="dq-nav-msg {"blocked" if not show_next else ""}">{msg}</div>', ...)
    c_next.button(next_label, type="primary", disabled=not show_next)
```
Message when blocked is the *only* place the block reason appears (remove the per-step `st.error` recaps). Restart via `@st.dialog("Restart and clear everything?")`.

**New `render_dp_summary_row(code, name, status_kind, status_text, meta, expanded, on_toggle)`** — the collapsed header used in Steps 3–5 (`.dq-row`). Steps render only the first invalid DP expanded; valid ones collapse to a one-line summary with ✓. State in `session_state[f"expanded_{step}"]`.

---

## 5. Mode selection (`step_mode_selection.py`)

- `page_header("Start", "Build a Data Quality scorecard", "Choose how to build, or reopen a saved configuration.")`
- `st.segmented_control(["New scorecard", f"Saved projects · {n}"], default=...)` — projects live in the same screen, not appended under `---`.
- Two cards (`st.columns(2)`): title + `dq-badge brand` "Recommended" on One-click; one sentence; `.dq-choice-grid` with **You choose / Automated** rows (copy in prototype); one button — primary on One-click, secondary on Step-by-step. Remove bullets, icons, taglines, `mode-active-pill`.
- Saved projects: replace selectbox+selectbox+button with a list: `st.dataframe(..., on_select="rerun", selection_mode="single-row", column_config=…)` (Project, Domain, Version, Last saved, By) + below it a **Versions** expander for the selected row and an `Open` primary button. Changelog columns: `v`, when, who, what changed, "Open this version" (button per row inside the expander).
- Remove the "Usage & audit" button (now in rail).

## 6. One-click (`step_one_click.py`)

- Layout `st.columns([2.2, 1], gap="large")`. Left: sections `1 Domain` (compact radio cards) and `2 Systems` (checkbox cards with rule-count badge `dq-badge` good/warn; systems with 0 custom rules render at opacity .7 and `disabled=True` on the checkbox, with the reason in the card).
- Right: **Run plan** card — You chose / Automated / Dataset rows (`.dq-choice-grid`), the EPT-skipped `dq-callout warn`, and the single primary button `Generate scorecards for N systems`. Delete `_render_generate_section` prose + the `[1,2,2]` column trick.
- Run: replace `st.spinner` with `st.status("Generating scorecards…", expanded=True)` and `status.update(label=…)` per real phase. `run_one_click` must accept an optional `progress: Callable[[str, str], None]` callback (pure addition, no logic change) called at: loading tables · building Data Products · profiling · applying Custom DQRs · computing scores · preparing exports. Never emit a percentage.
- Footer: Back only (Generate is the forward action).

## 7. Step-by-step steps

**Step 0 Domain** — two choice cards with system chips (`dq-code`). No summary box; footer message "Cost Estimate selected".

**Step 1 Systems** — connection state as one line `● Connected to catalog.schema` (`dq-callout info` without border) instead of `st.success/info`. Cards: checkbox + name + code; tables in an inline expander at the card bottom with PRIMARY as `dq-badge brand`. Remove `.sel-summary` chips (footer message carries the count).

**Step 2 Data Products** — build inside `st.status` (phases: build · profile · reference datasets) that collapses to `✓ Built 2 Data Products from 8 tables in 14 s`. Per DP: one container with header row (code, name, `.dq-kv` Rows/Columns/Tables on the right), source-table chips, preview expander. Remove the 3 `st.metric` and the local `stMetricValue` CSS.

**Step 3 CDEs** — DP summary rows (§4); expanded DP shows: selected chips (with required-by rule ids inline, violet text), a `st.text_input` filter + `Select required by Custom DQRs · N` button on the right, then the `st.data_editor`. Column config: rename `Pick as CDE`→`CDE`, `Custom DQRs`→`Required by` (drop the 🎯 prefix), keep `Null %` as ProgressColumn, hide `Rows` (same for every row) and `Dtype` (show `Type` only; dtype in tooltip). Remove `.ui-tip` paragraph, `.cde-success`, `.cde-empty`; state goes in the summary row + footer message.

**Step 4 DQR sources** — per DP: two toggle-cards (`st.toggle` inside bordered columns; selected card gets brand border). Split as `st.slider` **plus** the two-tone bar (`dq-bar brand/lab`). Remove `st.info("… = 100% (only source selected)")` → one muted sentence.

**Step 4.1 Standard DQRs** — keep the grid; apply `dq-code` for CDE, `dq-status` for computed/not-computed; per-DP collapse rows.

**Step 4.2 Custom DQRs** — rule **rows**, not cards: `st.columns([0.4, 0.8, 4, 1.2, 1.2, 2.2, 0.3])` = toggle · id · name+desc · type badge · blocking (dot + word, `--dq-er` dot only, not a red pill) · coverage (`✓ CDEs covered` / `▲ Missing CDE: X`) · expand. Expanded body (one `st.container` shaded) holds Options (select/toggle inline, no nested expander — description goes to `help=`) and Required source fields as chips coloured by coverage. Remove the duplicated `st.error` recap at the bottom (footer message names the first blocker). `Apply all · N` button in the DP header row.

**Step 5 Weights** — per DP, two columns: Standard (brand square) / Custom (violet square); table header CDE·Dimension·Weight %; `st.number_input(label_visibility="collapsed")`; one `dq-bar` + line `✓ Sums to 100%` / `▲ 15.00% still unassigned`. Delete `st.success/warning` lines and the "Source weights" plain-text duplicate. Next label `Generate scorecard →`.

## 8. Dashboard

Narrative **Overview → problem → diagnosis → detail → action**.

1. Header actions (right of `page_header`): `Save project` (opens `st.dialog` with name + version changelog — replaces the expander), `Export ▾` (`st.popover`: Executive report · per-DP CSV · per-DP JSON · Send to Airtable when configured), `ML Lab` with `dq-badge lab` BETA.
2. One-click summary → one-line `dq-callout info` with `Run details` popover (skipped, warnings, csv errors).
3. **Overview row** `st.columns([1,1,1,1.3])`: one **score card per DP** (`dq-code`, `.dq-score`, `dq-status`, `dq-dist` bar, rows, Δ vs previous run from `run_history`) — clicking selects the DP (`st.button` overlaying the card or a `st.pills` selector directly beneath). Fourth column **Needs attention**: top-4 rules by lowest pass rate across DPs (compute from `result.rule_pass_rates` + `custom_rule_pass_rates`; no new math) with `dq-bar` and link to the DP's Rules tab.
4. **Detail card for the selected DP only** (not all stacked): header = code · name · status · score · thresholds text · Standard/Custom sub-scores with their weights · rows G/Y/R counts. Then `st.tabs(["Rules","Custom rules","CDEs","Dimensions","Failing rows","History"])`.
   - Rules / Custom rules: table sorted worst-first, `Pass rate` as ProgressColumn, `on_select` → **side panel** (`st.columns([1,1])`) with failing rows (`_render_failing_rows`) + "Download failing rows (CSV)". This promotes the existing drill-down from hidden to primary.
   - CDEs / Dimensions: horizontal Plotly bars with `marker_color=score_color`, **plus** text labels ✓/▲/✕ in the bar text so status is not colour-only. Keep `on_select` drill-down.
5. **Remove the gauge** (`_gauge`): the score + status pill + `dq-dist` convey the same in 1/6 of the space. Keep `_threshold_bar` logic but render as the CSS `dq-dist` (counts in header). Remove the 4 `st.metric` duplicates.
6. Drop alert stays, as `dq-callout err` at the top of the detail card.
7. Footer: Back · Restart · message · no Next.

Chart theme: `fig.update_layout(template="plotly_white", font=dict(size=12, color="#4A5262"), margin=dict(t=8,b=8,l=8,r=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")` via one helper `ui/step_06/_charts.apply_theme(fig)`.

## 9. ML Lab

- `page_header("ML Lab · Beta · Cost Estimate", "ML Lab", …)`, header actions: `Engine ▾` popover (sklearn toggle + version) and `← Dashboard`.
- One `dq-callout lab` "Read-only — nothing here changes scores, rules, weights or exports." (≤ 20 words). Remove the 60-word banner.
- DP picker: `st.pills` with `CODE · score` labels; summary line replaces the 4-metric card.
- Tabs without emojis; each tab: one explainer sentence (`dq-sub`) + chart + right column "Reading this" (`sf2` background) with the plain-language takeaway that today is scattered in `_render_explainer` blocks.
- Delete the container/metric repaint. Violet appears only in tag, callout, and chart bars.

## 10. Usage & audit

Admin feel: no cards for KPIs — one bordered strip with 6 cells (`.dq-kv`), plain bar chart, two side-by-side tables, audit trail with a filter `st.text_input`. Rail shows "Admin" with a single row; footer has Back only. No emojis in metric labels.

## 11. Microcopy rules

- Button labels: verb + object, no arrows in emoji (`← Back`, `Next →`, `Generate scorecards for 2 systems`).
- Status words: Good / Warning / Poor (+ thresholds in tooltip). "Skipped" / "Not scored" for absent DPs.
- Remove all implementation explanations ("updates on the same render", "reuses the dashboard's builder", "preserved for parity").
- One sentence per callout; details behind `help=` or a `Details` popover.

## 12. Tests to adapt (no coverage loss)

- `tests/test_ui_units.py`, `test_ui_flow.py`: assertions on `"🟢 Green"` etc. → `"Good"/"Warning"/"Poor"` (`_STATUS_LABELS`). Assertions on `"**Status:**"`, `"**⬇ Export**"`, `"Source weights (set in Step 4)"` plain-text duplicates → remove (those lines are deleted).
- `test_step_mode_selection_ui.py`: project browser now `st.dataframe` + `Open` button; `format_func` on selectbox no longer exists.
- `test_step_one_click_ui.py`: `st.spinner` → `st.status`; new optional `progress` kwarg on `run_one_click` (default `None`, so `test_one_click.py` is unaffected).
- `test_session_state.py`: `STEP_LABELS` values changed; `render_sidebar_footer` removed.
- `test_step_06_*`: `_gauge` removed from `__all__`; `_render_overview_cards` signature unchanged; detail renders only the selected DP — tests iterating all DP cards should select each via `session_state["dash_selected_dp"]`.
- `test_step_04_2_custom_ui.py`: rule "cards" → rows; checkbox key `custom_{sys}_{rule}_enabled` **unchanged** (toggle uses the same key).
- Sidebar tests: `render_sample_mode_toggle`/`render_planview_filter` now render inside `st.popover`; keep widget keys `sample_mode_toggle`, `planview_filter_input`.

## 13. Databricks Apps

- No external assets: fonts fall back to Streamlit's bundled sans; the prototype's IBM Plex is optional (`enableStaticServing=true` + `static/fonts/*.woff2` + `@font-face` in `_theme.py`).
- `st.dialog`, `st.popover`, `st.status`, `st.pills`, `st.segmented_control`, `st.container(key=)` are all ≥ 1.39 core APIs — pin `streamlit>=1.40,<2` in `requirements.txt`.
- Only 5 `data-testid` selectors remain (container border, expander, metric ×3); everything else keys off `.st-key-*` or our own classes.

## 14. Remaining opportunities (not in scope of this pass)

- Replace `consume_scroll_to_top` JS with `st.navigation` pages (URL per step) — larger refactor of `goto`/tests.
- True keyboard focus on choice cards needs a custom component; today the checkbox/button inside is the focusable control.
- Dark mode in Streamlit requires a second `config.toml` or a runtime `st._config` hack; recommend shipping light only in Databricks Apps until Streamlit exposes a public theme switch.
