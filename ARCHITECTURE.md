# ARCHITECTURE.md

Working map for developers in this repo.
The README is the user-facing overview; this file is the working map: where things
live, the patterns that have been deliberately chosen, the test fixtures
that already exist, and the friction points to watch out for.

## What this app is

Streamlit app that walks the user through a workflow to build data-quality
scorecards across domains (Cost Estimate, Quality).

The app opens on a **mode picker** (`mode_selection`, the entry step):

- **One-click mode** (`one_click` step): the user picks only a domain +
  systems, then the app auto-builds everything (custom rules only, required
  CDEs, default options, equal weights, scorecards, CSVs) and lands on the
  dashboard. Logic lives in `src/one_click.py` (UI-free, unit-tested).
- **Step-by-step mode**: the historical manual flow - Step 0 picks a domain;
  Steps 1-6 build CDEs and apply Standard + Custom DQRs; Step 7 is an
  experimental ML Lab on top of the scorecards.

`session_state.app_mode` (`"one_click"` / `"step_by_step"` / `None`, constants
`APP_MODE_*` in `utils/session/state.py`) decides which steps are *visible*
(`STEP_VISIBILITY_PREDICATES` in `utils/session/navigation.py`). It's set by
`set_app_mode` and cleared by `restart_app` (which now returns to
`mode_selection`, not `domain_selection`).

Two data-source modes via `DATA_SOURCE`:

- `mock`: synthetic data from `src/mock_data.py` (default, deterministic).
- `snowflake`: real Snowflake fetch through `src/snowflake_client.py`, which has
  **two interchangeable backends**: the in-platform **Snowpark session**
  (`get_active_session()`) when running inside **Streamlit in Snowflake**, and
  `snowflake.connector` + `externalbrowser` SSO as the **local-dev fallback**.
  The backend is auto-selected; user-supplied filter values are bound
  server-side either way (qmark `?` for Snowpark, pyformat `%s` for the
  connector — translated internally).

Tests always run against `mock` (an autouse fixture in `tests/conftest.py`
pins it regardless of the shell `DATA_SOURCE`).

## Repo layout

The project grew through several refactors that split monolithic files
into per-concern / per-family packages. The legacy module name is kept
as a slim re-export so external callers don't change:

```
app.py                         # Streamlit router (current_step -> renderer)
config/
  settings.py                  # SETTINGS dataclass (env-driven)
  domains.py                   # DomainDef + DOMAINS registry + helpers
  systems.py                   # SystemDef + per-system table + join metadata
  dqr_catalog.py               # 10 Standard DQR dimensions
  dqr_sources.py               # SOURCE_STANDARD / SOURCE_CUSTOM constants
  custom_dqr_catalog.py        # SLIM re-export; assembles CUSTOM_DQR_RULES
  custom_dqr/                  # M6 split (per system)
    _shared.py                 # CustomRuleDef + option-builder helpers
    _ept_catalog.py            # EPT_RULES list
    _adr_catalog.py            # ADR_RULES list
    _acce_catalog.py           # ACCE_RULES list
    _sqs_catalog.py            # SQS_RULES list (Quality domain)
src/
  models.py                    # ColumnProfile / DataProduct / DQRAssignment / ...
  profiler.py                  # column dtype classification + null/duplicate counts
  dqr_engine.py                # Standard DQR (10 dimensions) + dispatcher
  dqr_validation.py            # per-dimension type/param compat checks
  data_product_builder.py      # join system tables -> single DataProduct
  scorecard.py                 # row/CDE/dimension scores -> ScorecardResult
  one_click.py                 # One-click service: run_one_click /
                               #   build_one_click_config / default_rule_params
                               #   (custom-only, required CDEs, equal weights)
  persistence.py               # app-state layer: run history / telemetry / saved
                               #   projects; local JSONL now, DQS_* tables in prod
  reference_data.py            # registry + session-state cache for ref datasets
  snowflake_client.py          # data layer: Snowpark session (SiS) / connector (local)
  mock_data.py                 # deterministic synthetic data builders
  ml_lab.py                    # algorithms used by Step 7
  custom_dqr_engine.py         # SLIM re-export of src/custom_dqr/*
  custom_dqr/                  # C1 split (per family + dispatcher)
    _shared.py                 # CustomRuleNotEvaluated, _is_filled,
                               #   _coerce_threshold, _resolve_planview_segment_map
    _validators.py             # validate_completeness_rule,
                               #   validate_referential_integrity_rule
    _ept_rules.py              # E1-E7 checks + constants
    _adr_rules.py              # A1-A8 checks + constants
    _acce_rules.py             # AC1-AC8 checks + constants
    _sqs_rules.py              # SQ* checks + constants (Quality domain)
    _dispatcher.py             # evaluate_custom_rules(df, assignments, dp)
ui/
  _theme.py                    # inject_global_css() - one consolidated main-area
                               #   stylesheet, injected once in app.main() (H5)
  step_mode_selection.py       # Entry step - One-click vs Step-by-step picker
  step_one_click.py            # One-click - domain + systems + Generate -> dashboard
  step_00_domain_selection.py  # Step 0 - domain picker (Step-by-step)
  step_01_system_selection.py  # Step 1 - systems
  step_02_data_product_review.py
  step_03_cde_selection.py
  step_04_dqr_source_selection.py
  step_04_dqr_assignment.py    # Step 4.1 - Standard assignments
  step_04_2_custom_dqr.py      # Step 4.2 - Custom DQR cards
  step_05_weight_assignment.py
  step_06_dashboard.py         # SLIM orchestrator + page header + nav
  step_06/                     # Dashboard partitioned by concern
    _shared.py                 # _status_class, system icons / accents (CSS now global)
    _export.py                 # CSV / JSON download builders
    _charts.py                 # Plotly gauge + threshold-bar
    _breakdown.py              # DP-card header, source-breakdown, Custom Rules table
    _drilldown.py              # Click a bar / select a rule -> failing rows table
    _dp_dashboard.py           # Per-DP card (gauge + tab row) + cross-DP overview
  step_07_ml_lab.py            # SLIM orchestrator + tab dispatcher
  step_07/                     # B5 split (one module per ML Lab tab)
    _shared.py                 # purple-theme CSS override, banner/empty helpers,
                               #   _ensure_scorecards
    _row_anomalies.py
    _rule_impact.py
    _cde_clusters.py
    _weight_sensitivity.py
    _cross_dp.py
    _run_history.py
    _risk_model.py
    _recommendations.py
    _row_explain.py
utils/
  colors.py                    # STATUS_GREEN/YELLOW/RED - single source for the
                               #   status hexes (charts, helpers, global CSS) (H5)
  helpers.py                   # score_color, score_label, section_header
  ui_components.py             # render_nav_footer, render_restart_button,
                               #   render_choice_card (shared domain/system card)
  session_state.py             # SLIM re-export of utils/session/*
  session/                     # M7 split
    state.py                   # STEPS, init_state, set_domain, set_app_mode,
                               #   APP_MODE_* constants, ...
    navigation.py              # next/prev/restart, _visible_steps (mode-aware),
                               #   _mode_is_step_by_step / _mode_is_one_click, goto, ...
    sidebar.py                 # CSS, brand, progress stepper, filters
tests/
  conftest.py                  # autouse: pin DATA_SOURCE=mock + sample_df
  test_*.py                    # ~1235 tests across 30 modules
  test_one_click.py            # One-click service (src/one_click.py)
  test_step_mode_selection_ui.py  # entry mode picker (AppTest)
  test_step_one_click_ui.py    # One-click step + validations (AppTest)
  test_app_mode_flow.py        # mode on-ramps + flow separation + regression
documents/
  STANDARD_RULES.md            # Standard DQR catalog reference
  CUSTOM_RULES.md              # Custom rules per system reference
  ML_LAB.md, DOCUMENTATION.md, BLOCK_DIAGRAM.md, FLOWCHART.md
```

## How to run things

```bash
# Install (dev)
pip install -r requirements.txt

# Lock (CI/prod)
pip install -r requirements.lock

# Run the app
streamlit run app.py            # also: make run

# Test suite (always uses mock data)
DATA_SOURCE=mock pytest -q      # also: make test

# Lint (matches CI)
ruff check .

# Pre-commit (one-time setup; runs ruff + a handful of file checks on every commit)
pip install pre-commit
pre-commit install
```

The `Makefile` exposes `install / run / test / clean`. CI
([.github/workflows/tests.yml](.github/workflows/tests.yml)) runs
`ruff check`, then `pytest` with `--cov-fail-under=90` (current
coverage is ~97%).

### Deploying to Streamlit in Snowflake (SiS)

Local `streamlit run` is the dev/demo path. **Production runs as Streamlit in
Snowflake**, deployed from this GitHub repo:

- Dependencies come from the Snowflake Anaconda channel via
  [environment.yml](environment.yml) (NOT `requirements*.txt`). Keep the two in
  rough sync, but `environment.yml` is the production source of truth.
- The data layer auto-switches to the active Snowpark session inside SiS (no
  `.env`/connector). See `src/snowflake_client.py`.
- Reference deployment SQL (GitHub Git integration + a least-privilege read-only
  role + `CREATE STREAMLIT`) lives in [deploy/](deploy/) — run it in Snowflake
  with the privileges noted in [deploy/README.md](deploy/README.md).
- `pyproject.toml` `target-version` and CI both track Python 3.11 to match the
  SiS runtime.

## Patterns to follow

### One global stylesheet; themed screens override; colours in one module
Main-area CSS is **not** per-step. `inject_global_css()` in
[ui/_theme.py](ui/_theme.py) holds the one canonical stylesheet (cards,
buttons, pills, metrics, every step/dashboard component class) and is injected
once in `app.main()`, the way `inject_sidebar_css` is. Per-step `_inject_css()`
functions were removed in H5. Only two screens keep a **slim** `_inject_css()`
override, layered on top inside their own `render()` because their colour
identity is deliberate, not drift:

- ML Lab ([ui/step_07/_shared.py](ui/step_07/_shared.py)) - violet card /
  metric re-theme + `.lab-*` classes.
- One-click ([ui/step_one_click.py](ui/step_one_click.py)) - amber
  `.step-pill` / `.sel-chip` + `.oc-rulecount`.

(Step 02 also keeps a one-rule override for its smaller metric *value* size -
globalising it would shrink the Dashboard / ML-Lab numbers.) The three score
status hexes live ONLY in [utils/colors.py](utils/colors.py)
(`STATUS_GREEN/YELLOW/RED`); CSS embeds them via `__GREEN__`/`__YELLOW__`/`__RED__`
sentinels swapped at inject time (brace-safe, no f-string-escaping the sheet).
A re-brand is one edit. Don't reintroduce a per-step `<style>` block or a
hardcoded `#16a34a`/`#eab308`/`#dc2626`.

### Domain / system cards share one renderer
The Step-by-step pickers (Steps 0/1) and One-click render their domain and
system cards through `render_choice_card(...)` in
[utils/ui_components.py](utils/ui_components.py) - same chrome, unified
`Select {name}` verb, one shared selected-state badge. The bits that
legitimately differ per screen are passed in, NOT hardcoded: `multi` picks the
control (button vs checkbox), `before_control` / `after_control` are render
callbacks for the screen-specific metadata (Step-0 systems-row + One-click
rule-count badge go before the control; Step-1 Tables expander goes after), and
`desc_min_height_em` keeps each screen's height. When adding a card, reuse this
renderer and pass a slot - don't fork it or let one screen lose what it showed.

### Slim re-exports preserve public API
When a module grew to thousands of lines we partitioned it but **kept
the legacy module name as a re-export shim** so external imports don't
break:

- `src/custom_dqr_engine.py` -> re-exports from `src/custom_dqr/_*`
- `config/custom_dqr_catalog.py` -> assembles `CUSTOM_DQR_RULES` from
  `config/custom_dqr/_*_catalog.py`
- `utils/session_state.py` -> re-exports from `utils/session/*`
- `ui/step_06_dashboard.py` -> orchestrator on top of `ui/step_06/_*`
  (`_shared`, `_export`, `_charts`, `_breakdown`, `_drilldown`,
  `_dp_dashboard`); the
  test-facing helpers (`_build_rowscores_csv`, `_per_rule_score_columns`,
  `_reference_columns_for_export`, `_status_class`,
  `_render_source_breakdown`) are re-exported on the legacy module.
- `ui/step_07_ml_lab.py` -> re-exports tab renderers from `ui/step_07/_*`

Each shim has an `__all__` listing every re-exported name (including
the private `_helpers` used by tests). Add new symbols to both the
sub-module AND the `__all__` list.

### Per-step `_nav` is a wrapper, not custom code
Steps 02-05 + 04.2 all use the same nav row (Back / Restart / centre
message / Next). The shared renderer lives in
[utils/ui_components.py](utils/ui_components.py) (`render_nav_footer`).
Each step's `_nav(show_next: bool = False)` is a 5-line wrapper that
passes `prev_step` / `next_step` / `restart_app` as callbacks - the
callbacks are passed by reference so tests that `patch("ui.step_X.prev_step")`
still intercept them.

Steps 00 / 01 (Back goes to domain picker), 06 (extra ML Lab button)
and 07 (extra Back-to-Dashboard button) keep bespoke `_nav` because the
layout differs.

### `.index()` calls are guarded
A repeated bug class: `list.index(stored_value)` raises if the catalog
changed between persisted runs. We guard with `try/except ValueError`
+ fallback (see `ui/step_04_dqr_assignment.py:134`,
`ui/step_04_2_custom_dqr.py:123`, `utils/session/navigation.py:next_step`).
When adding a new selectbox, follow the same pattern.

### Silent except is forbidden (with two exceptions)
Audits established the rule: every `except Exception:` either logs
(`logger.warning(..., exc_info=True)`) or has a tight reason in the
comment. The two allowed exceptions are:

1. Defensive last-line fallbacks marked `# pragma: no cover - defensive`
   (e.g. sklearn-missing branches in `src/ml_lab.py`).
2. Streamlit-not-loaded detection in `src/reference_data.py` cache
   helpers - they MUST return `None` outside a Streamlit run.

### Vectorize DQR checks
Standard DQR rules run on potentially large Snowflake frames. Prefer
pandas string accessors (`.str.fullmatch`, `.str.len`),
`pd.Series.duplicated`, or numpy operations over `.apply(lambda v: ...)`.
See `src/dqr_engine.py:_rule_validity` for the regex pattern.

### Rules raise `CustomRuleNotEvaluated`, never silently pass
A custom rule whose dependency is missing (e.g. a reference dataset
failed to load) must raise `CustomRuleNotEvaluated`. The dispatcher
records the reason; Step 6 surfaces a "Not evaluated" warning instead
of treating absent inputs as success.

### Persistence is fire-and-forget, append-only, and backend-switched

`src/persistence.py` owns everything the app writes about itself (run
history, adoption/audit telemetry, saved-project versions). Three rules:

- **Fire-and-forget**: every public function catches storage errors, logs
  them and returns `False` / `[]`. A dead store must never break a render.
- **Append-only**: nothing is ever updated or deleted - a project "save"
  is a new version row, which makes the version list the audit changelog.
  The Snowflake grants enforce this (INSERT+SELECT only, see
  `deploy/03_persistence_tables.sql` - a scoped exception to the app's
  read-only posture documented in `01_least_privilege_role.sql`).
- **Backend via `DQS_PERSISTENCE`** (`local` / `snowflake` / `off`),
  deliberately decoupled from `DATA_SOURCE` so local runs against real
  data keep writing to `.dqs_store/` until the prod tables exist. Writes
  stamp `ts` + `username` (`CURRENT_USER()` in SiS, OS login locally).

Feature code (dashboard history, telemetry, projects) talks only to the
domain API (`save_run` / `log_event` / `save_project_version` / the
`list_*` readers) - never to a store class directly.

### One-click reuses the Step-by-step builders, it doesn't fork them
`src/one_click.py` is deliberately thin: `run_one_click` calls the same
`build_multiple` / `profile_dataframe` / `prefetch_reference_datasets` /
`compute_scorecard` the Step-by-step Steps 2 + 6 use, and `build_one_click_config`
reuses `effective_required_columns` (CDE derivation) and `distribute_equally`
(equal weights). The only One-click-specific logic is "custom source only,
every rule, default params" - so a One-click config equals a Step-by-step config
the user never edited, and the two paths can never drift in how they score.
`default_rule_params(rule)` reproduces what Step 4.2 emits with nothing
toggled. Keep new automation here (UI-free) so it stays unit-testable
without `AppTest`; the `one_click` UI step only wires the result into
session state + the dashboard.

## Test fixtures and helpers

`tests/conftest.py` provides:

- `sample_df`: small DataFrame with deliberate quality issues.
- `_force_mock_data_source` (autouse): pins `SETTINGS.data_source =
  "mock"` regardless of the shell env, so tests never hit Snowflake.

Common helpers introduced when modules were partitioned:

- `_make_fake_st(...)` in [tests/test_ui_units.py](tests/test_ui_units.py):
  builds a MagicMock that mimics Streamlit (text_input, checkbox,
  selectbox, columns, button). Reused by `test_step_04_*` and
  `test_step_07_*` test modules via `from tests.test_ui_units import _make_fake_st`.
- `_patch_session_st(fake_st)` in [tests/test_coverage_gaps.py](tests/test_coverage_gaps.py):
  context manager that patches `st` on every sub-module of
  `utils.session.*` (needed because `utils/session_state.py` is now a
  re-export shim).
- `_patch_step07_st(fake_st)` in [tests/test_step_07_ml_lab_ui.py](tests/test_step_07_ml_lab_ui.py):
  same idea for every sub-module of `ui.step_07.*`.

When a test calls a function that has been split across sub-modules,
patch `st` (or `prev_step`, `next_step`, etc.) on the **module where
the function actually lives now**, not on the legacy re-export.

## Adding things

### A new Standard DQR dimension
Standard DQRs are the 10 fixed dimensions in `config/dqr_catalog.py`.
Adding an 11th is a significant API change - see how `suggest_dimensions_for`
fans out and which steps loop over `DIMENSIONS`. Probably not what you want;
prefer a Custom DQR.

### A new Custom DQR rule (within an existing system)
1. Implement `check_<sys>_<id>(df) -> pd.Series[bool]` in
   `src/custom_dqr/_<sys>_rules.py`. Use `validate_completeness_rule`
   / `validate_referential_integrity_rule` when applicable.
   Raise `CustomRuleNotEvaluated` if a reference dataset is unavailable.
2. Add the rule's constants (`<SYS>_<ID>_REQUIRED_COLUMNS`, optional
   `_REFERENCE`, threshold params) to the same module.
3. Re-export the new symbols from `src/custom_dqr_engine.py` (add to
   the per-family import block AND to `__all__`).
4. Append a `CustomRuleDef(...)` to the relevant
   `config/custom_dqr/_<sys>_catalog.py` list.
5. Import the new check function + constants at the top of that catalog
   file.
6. (Optional) Add unit tests in `tests/test_custom_dqr_engine.py` and
   metadata tests in `tests/test_dqr_sources_config.py`.

### A new ML Lab tab
1. Create `ui/step_07/_<my_tab>.py` with `_render_tab_<my_tab>(code, dp, config, result)`.
   Use `_render_explainer`, `_render_empty` from
   [ui/step_07/_shared.py](ui/step_07/_shared.py).
2. Import the renderer in [ui/step_07_ml_lab.py](ui/step_07_ml_lab.py)
   and wire it into the `st.tabs(...)` block in `render()`.
3. If the new tab needs a `st` mock in tests, add its module to
   `_patch_step07_st` in [tests/test_step_07_ml_lab_ui.py](tests/test_step_07_ml_lab_ui.py).

### A new domain
See the README section "Adding a domain". The TL;DR: create a
`DomainDef`, register it in `DOMAINS`. Per-system custom rules go in
the `DomainDef.custom_rules` dict (the Cost Estimate domain uses the
historical `CUSTOM_DQR_RULES` dict; other domains can supply their own).

## Friction points

- **Two gates in `app.py`, in order**: (1) the *mode gate* routes a
  brand-new session (no `app_mode` AND no `domain`) to `mode_selection`;
  (2) the *domain gate* reroutes any step outside `_DOMAINLESS_STEPS`
  (`{mode_selection, one_click, domain_selection}`) to `domain_selection`
  when `domain` is unset. AppTest-based tests that jump straight to a later
  step must pre-set `app_mode` (usually `"step_by_step"`) **and** `domain`, or the
  gates bounce them back. `_new_app` (test_ui_flow) and the ML Lab /
  step_00 helpers already default `app_mode`.

- **Mode-gated visibility breaks naive nav tests**: `_visible_steps()` now
  filters on `app_mode`, so `next_step` / `prev_step` walks are empty until
  a mode is set. Unit tests that `init_state()` then walk steps must set
  `st.session_state.app_mode = "step_by_step"`. The first visible step is now
  `mode_selection` (not `domain_selection`).

- **One-click's active-domain contract**: `run_one_click(domain_code, ...)`
  resolves the rule catalog through the *active* domain
  (`get_available_custom_dqr_rules` / `compute_scorecard` read
  `get_active_domain`), so the caller must have `st.session_state.domain ==
  domain_code` first. The `one_click` UI guarantees this via `set_domain`;
  tests set `st.session_state["domain"]` (see the `active_domain` context
  manager in [tests/test_one_click.py](tests/test_one_click.py)).

- **`utils.session_state.X` patches**: legacy tests still patch `st` on
  the re-export shim. They MUST use one of the `_patch_*_st` helpers
  (which patch every sub-module). A direct `patch.object(ss_mod, "st", fake)`
  will silently no-op against the sub-module functions.

- **`from __future__ import annotations` everywhere**: type hints are
  evaluated as strings, so missing `from typing import ...` doesn't
  fail at runtime but `ruff check` does catch it (F821).

- **`pyproject.toml` import-root**: explicitly set to `.` (not `src/`)
  in `[tool.pyright]` and `[tool.ruff]` because `src/` is just one of
  several top-level packages alongside `config/`, `ui/`, `utils/`.

- **Per-file pyright pragmas in pandas-heavy modules**: the pandas-stubs
  type `df[col]` as `Series | DataFrame` (because pandas also accepts
  `df[[col1, col2]]` and `df[bool_mask]`), which produces hundreds of
  false-positive errors on call sites that always pass a single string
  column. Affected modules (`src/custom_dqr/_*.py`, `src/dqr_engine.py`,
  `src/profiler.py`, `src/mock_data.py`, `src/data_product_builder.py`,
  `src/snowflake_client.py`, `src/ml_lab.py`, `src/scorecard.py`,
  `src/custom_dqr/_validators.py`) carry a top-of-file `# pyright:`
  pragma silencing the noisy categories
  (`reportArgumentType`, `reportReturnType`, `reportCallIssue`,
  `reportAttributeAccessIssue`, `reportOperatorIssue`). The runtime
  contract is locked down by 1,200+ tests; `cast(pd.Series, ...)` on
  every offending site would be churn with no benefit. Real bugs the
  pragma effort surfaced (and that *were* fixed): `Optional[float]`
  defaults on `compute_scorecard`, `Dict[str, ScorecardResult]` vs
  `Dict[str, object]` mismatch in `_ensure_scorecards`,
  possibly-unbound variables in `_simple_kmeans` /
  `compute_cde_profile_clusters` / `explain_row_score`.
  `ruff check` + `pytest` is what CI enforces; `pyright` is a local
  IDE aid, not a CI gate.

- **`_resolve_planview_segment_map`** is shared across families (E6,
  A7, A8, AC7, AC8) so it lives in [src/custom_dqr/_shared.py](src/custom_dqr/_shared.py),
  not in the EPT module where it was originally defined.

- **ACCE -> ADR dependency**: AC1 and AC8 reuse `_a1_value_valid`,
  `_resolve_coa_master_lookups`, and `_A8_UOM_ALIASES` from
  [src/custom_dqr/_adr_rules.py](src/custom_dqr/_adr_rules.py). Don't
  remove these from ADR even if A1/A8 stop using them.

- **Quality (SQS) catalog wiring**: SQS rules live in the Quality
  domain's `custom_rules` map (set up inside `_build_quality_domain` in
  [config/domains.py](config/domains.py)), **not** in the legacy
  `CUSTOM_DQR_RULES` dict in
  [config/custom_dqr_catalog.py](config/custom_dqr_catalog.py) (which
  backs only Cost Estimate). `get_available_custom_dqr_rules("SQS")`
  resolves through `get_active_domain()`, so tests that exercise SQS
  must switch the active domain (see
  `tests/test_domains.py::test_quality_domain_exposes_sq4` for the
  pattern).

- **Sidebar Project filter is domain-aware**: the filter column lives
  on `DomainDef.project_filter` (`ProjectFilterDef`), defaulting to
  `DEFAULT_PROJECT_FILTER` (`PLANVIEW_ID`). Cost Estimate filters on
  `PLANVIEW_ID`; Quality on `PROJECT_CODE`. `render_planview_filter`
  in [utils/session/sidebar.py](utils/session/sidebar.py) is **gated
  on `session_state.domain`** (no widget without a selected domain),
  reads the column / label / placeholder / help from the active
  `ProjectFilterDef`, and resolves the domain via `get_domain(code)`
  off the patched `st.session_state` (NOT `get_active_domain()`, which
  goes through the real streamlit module and ignores
  `_patch_session_st` in tests). `_apply_planview_filter` in
  [src/data_product_builder.py](src/data_product_builder.py) accepts
  an optional `column=` keyword (default `SHARED_KEY = PLANVIEW_ID`),
  and `build_data_product` / `build_multiple` accept a matching
  `filter_column=` keyword. Step 2 passes
  `get_active_project_filter().column` into `build_multiple` so the
  filter resolves against the right column for the active domain.

- **Project filter is SQL-pushdown, not in-memory**: in Snowflake mode
  `_default_fetcher` builds a per-table fetcher that emits
  `SELECT * FROM primary WHERE filter_column IN (%s, ...)` and, for
  child tables, `WHERE join_key IN (SELECT join_key FROM primary
  WHERE filter_column IN (%s, ...))`. **Do not move this back to
  in-memory.** Before the pushdown, Sample mode's `LIMIT 50000` was
  applied **before** the in-memory filter, so a user filtering on a
  project whose rows weren't in the first 50k saw an empty data
  product (the original 2026-05 bug for PLANVIEW_ID=1101168). The
  in-memory `_apply_planview_filter` is still called but is a no-op
  for Snowflake mode (defense for mock, and a safety net). User
  input flows through `_canonicalize_id` and then via parameterized
  `cursor.execute(sql, params)` - never string-concatenated into the
  SQL, so the filter is injection-safe.

- **`.env.example`**: must contain placeholders only. Real account /
  user / role values belong in `.env` (gitignored). Pre-commit review:
  no real corporate email addresses, no real account identifiers.

- **Mock data determinism**: `src/mock_data.py` uses one shared, stateful
  module RNG. Because every `RNG.choice(...)` advances it, a builder that draws
  from it is only pure if the generator starts from the same place each call -
  so the shared helper `_reseed_rng_for(name)` **reseeds** the RNG from a stable
  hash of the name (`zlib.crc32`, NOT the salted built-in `hash`, so it's stable
  across processes). It is called per **system table** by `fetch_mock_table`
  AND by each **mock reference-dataset** builder that draws from the RNG
  (`_mock_vws_gp_standard_share`; `_mock_acce_coa_master` is a fixed literal and
  needs none). The result: every system table and reference dataset is
  byte-identical on each call regardless of call order. Without it the same
  input returned different data per call and scores drifted run-to-run (and a
  cold-cache reference reload changed E2/E7/segmented-rule results). The
  import-time constants (`_ITEM_ROW_IDS`, `_ITEM_DESIGN_ID`, `_ITEM_UOM`,
  `_UOM_BY_ROW_ID`, `_PLANVIEW_ID_POOL`) are drawn once at import (fixed order)
  and are intentionally NOT reseeded - they're the shared keys system tables
  and reference datasets join on. Relative date columns (e.g.
  `LAST_REPORTED_AT`) anchor to `_MOCK_NOW`, captured once at import, not inline
  `datetime.now()` (which differed by microseconds per build). If you add a
  builder - system table OR reference dataset - call `_reseed_rng_for(<name>)`
  at its start, draw from the module `RNG` (not a fresh generator or global
  `np.random`), and anchor any "recent" dates to `_MOCK_NOW`. The mock data
  itself is now fully deterministic. The ONE thing still wall-clock dependent is
  *outside* the mock data: date-*relative* DQRs (Timeliness / Currency / SQ10)
  compare against the **engine's** real `datetime.now()` (`src/dqr_engine.py`,
  the SQ10 check), so their pass rates drift over calendar time regardless of
  how deterministic the data is.

## CI

Workflow: [.github/workflows/tests.yml](.github/workflows/tests.yml)
runs on `push` to `main` and on PRs. Steps:

1. Install `requirements.txt` + `ruff`.
2. `ruff check .` (lint must pass).
3. `pytest -q --cov=src --cov=utils --cov=config --cov=ui --cov-report=term`
   with `DATA_SOURCE=mock`.

CI does not itself deploy. **Deployment target is Streamlit in Snowflake**,
pulled from this GitHub repo via a Snowflake Git integration (see
[deploy/](deploy/) and the "Deploying to Streamlit in Snowflake" section above).
Locally the app still runs via `streamlit run app.py` for development/demo.
