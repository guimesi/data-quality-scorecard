# Data Quality Scorecard App

A Streamlit application for managing **Critical Data Elements (CDEs)** and
**Data Quality Rules (DQRs)** over Data Products. The app is
**multi-domain**: a Step 0 picker selects which domain of data to assess
(initially **Cost Estimate** with ADR / ACCE / EPT, or **Quality** with
SQS) and the rest of the workflow re-parameterises itself
accordingly - tables, schemas, CDEs, standard catalog, custom rules
and per-step copy all follow from the active domain.

The app opens on a **mode picker** that splits into two ways to build a
scorecard:

- **⚡ One-click mode** - the user picks only a **domain** and the
  **systems** to include; the app then automatically selects the required
  CDEs, applies every Custom DQR at its default settings, distributes the
  weights equally, scores each Data Product and prepares the CSV exports,
  landing straight on the dashboard. No further interaction is needed
  unless a blocking validation issue arises.
- **🛠️ Step-by-step mode** - the historical step-by-step workflow described below,
  unchanged: full manual control over sources, CDEs, rule options and
  weights.

See [Application modes](#application-modes-one-click-vs-step-by-step) for the full
contract. The numbered steps below describe the **Step-by-step** flow (One-click
automates the same pipeline end-to-end).

## What the application does

0. **Domain selection (Step 0)**: the user picks the data domain to
   work in. Each domain bundles its own systems, tables, CDE
   suggestions, standard catalog scope and custom DQR rules. Switching
   domain mid-flight resets the in-progress workflow so selections
   from the previous domain don't leak across.
1. **System selection**: within the active domain, the user picks
   which systems to analyse (e.g. ADR / ACCE / EPT for Cost Estimate,
   SQS for Quality). Each card shows the tables that compose
   the system.
2. **Data Product construction**: tables are joined into a single consistent
   table per system:
   - **ADR**: 4 tables joined on `ROW_ID` (PK of `ADR_DIM_ESTIMATEITEMRECORD`)
   - **ACCE**: 4 tables - cost / qty children join on `ROW_ID`; the design
     dimension joins on `DESIGN_ID` (many items can share one design)
   - **EPT**: single table `ONSHORE_CETDATA` used as-is

   `PLANVIEW_ID` **is not used in the join**: it is preserved as a regular
   column in the ADR/ACCE/EPT data products and can be used later for
   cross-system analysis. A sidebar **Project filter** (domain-aware) lets
   the user restrict the entire app to one or more project identifiers. The
   filter column is configured per domain via `DomainDef.project_filter`:
   Cost Estimate filters on `PLANVIEW_ID`, Quality filters on `PROJECT_CODE`.
   The widget is hidden until a domain has been selected at Step 0 (because
   the right column is only known once the domain is known), then applied
   to each system's primary table at build time and cascaded through every
   downstream step (profiling, CDEs, DQRs, scorecard).
3. **Profiling + CDE selection**: full column profiling (dtype, null count/pct,
   duplicates, cardinality, sample) inside an `st.data_editor` grid. The user
   ticks the **Pick as CDE** checkbox per row to promote columns to CDEs.
   Columns required by one or more Custom DQRs are flagged inline (🎯) so the
   user can see which picks unlock which rules in Step 4.2. A per-DP
   **🎯 Select all CDEs required by Custom DQRs** shortcut unions every
   flagged column into the current selection on click (manual picks
   preserved); it is not pre-applied - selection only changes after a click.
4. **DQR sources**: per Data Product, the user picks one or both DQR families:
   - **Standard DQR Rules**: the catalog of 10 dimensions (Accuracy,
     Completeness, Uniqueness, Consistency, Timeliness, Validity, Currency,
     Conformity, Integrity, Precision). Per-rule documentation:
     [documents/STANDARD_RULES.md](documents/STANDARD_RULES.md).
   - **Custom DQR Rules**: data-product-specific rules curated for that
     system. EPT currently ships seven rules (E1–E7) covering completeness,
     referential integrity, FEED/Engineering consistency and statistical
     outliers; ADR ships eight rules (A1 covering blocking ISO COR + SAB
     lookup completeness, A2 covering location + estimate date
     completeness, A3 covering statistical WBC-to-ISO mapping
     aggregation, A4 covering core-quantity completeness per project
     scope, A5 covering design-detail/quantity consistency, A6 covering
     construction-hours/quantity consistency, A7 covering
     within-discipline hours-per-quantity outlier detection, A8 covering
     cross-discipline quantity-ratio outlier detection at the project
     level). ACCE ships the AC1–AC8 series that mirrors A1–A8 against
     the ACCE schema, e.g. AC1 is the blocking ISO COR + SAB lookup,
     joining the first three characters of the 4-character `ACCE.COA`
     to the 3-character `ICARUS_COA` group in the master (the analog
     of ADR's `SPLIT_PART(COMPLETE_WBC, '.', 1)` derivation). The
     Quality domain (SQS) seeds its catalog with `SQ4` (Validity on
     `EXPECTED_SHIP_DATE`), `SQ5` (Business Rule pinning the supplier's
     expected ship date to the PO's contractual deadline), `SQ6`
     (Validity check enforcing the controlled `INSPECTION_TYPE`
     vocabulary), `SQ7` (Validity check enforcing the
     `WORK_CRITICALITY` classification levels), `SQ8` (Completeness
     check pinning a populated `STATUS` on every inspection record),
     `SQ9` (Validity check pinning `STATUS` to the 11 canonical
     workflow statuses), and `SQ10` (Business Rule pinning Completed
     inspections to a non-future expected ship date), and is growing
     as new rules land.
     Per-rule documentation:
     [documents/CUSTOM_RULES.md](documents/CUSTOM_RULES.md).

   When both are selected the user splits a 100% source-level weight between
   them (e.g. Standard 70% / Custom 30%).
   - **Step 4.1 - Standard DQR Rules**: per-CDE dimension assignment with
     live compatibility validation (✅ / ⚠ / ❌ per rule); visited only for
     DPs that picked Standard. **Next** stays disabled while any selected
     dimension/parameter combination is incompatible with the CDE's data type.
     Suggestions are surfaced with a **💡 _suggested_** badge but are NOT
     pre-applied, each DP exposes a **💡 Apply all suggested DQRs**
     shortcut that enables every still-pending suggestion in one click
     (idempotent, manual edits preserved).
   - **Step 4.2 - Custom DQR Rules**: card-based selection over the catalog
     with live CDE-coverage validation; visited only for DPs that picked
     Custom. DPs without any custom rules show a clear empty state. Each
     DP card also exposes a **✓ Select all Custom DQRs** shortcut that
     ticks every rule available for that data product on click (not
     pre-applied; persisted weights / option params survive the bulk-select).
     Statistical-outlier rules (E3, E6, A3, A7, A8, AC3, AC7, AC8)
     additionally surface a **threshold selectbox** on each card -
     pick the percentile (P75 / **P90 default** / P95 / P99 for
     E3 / A3 / AC3) or the IQR multiplier (**1.5× default** / 2.0× /
     3.0× for E6 / A7 / A8 / AC7 / AC8) used to decide what counts
     as an outlier. E3 and A3 also expose two behavioural toggles -
     **project_scoped** (per-`PLANVIEW_ID` percentile baseline) and
     **detect_uniform_mapping** (also fail material 1:1 buckets).
     AC3 only exposes **detect_uniform_mapping**, gated by an
     **80 % portfolio-wide proportion** (every material 1:1 bucket
     fails only when ≥ 80 % of eligible mappings are 1:1). All
     toggles are opt-in and off by default. Defaults reproduce the
     rule's documented baseline, so the rule behaves identically to
     its pre-feature self when the user does not touch the picker.
5. **Weight distribution**: within each active source, the user distributes
   100% across the rules (equal-distribute shortcut + per-widget cap).
6. **Scorecard + Dashboard**: each row receives a score 0–100 combining
   Standard and Custom subscores by their Step-4 source weights:
   `final = w_std * standard_score + w_cus * custom_score`. The dashboard
   shows both subscores, the source weights used, the CDE/dimension
   breakdowns (which blend Standard *and* Custom rules - Custom rules are
   attributed to every CDE in their `required_columns` and to their
   `rule.type` as dimension), a Custom Rules tab with per-rule pass rates
   (including "Not evaluated" warnings when a Custom rule's reference data
   is missing and "Not computed" warnings when a Standard rule's
   configuration was incompatible with the CDE), and the threshold
   distribution (green/yellow/red). Every breakdown is **click-to-drill-down**:
   clicking a bar on the "By CDE" / "By Dimension" charts, or selecting a
   row on the "Rules (pass rate)" / "Custom Rules" tables, surfaces the
   actual data rows that fail the clicked element - worst score first,
   with the same per-rule (100/0) and reference-dataset columns as the
   Worst-rows tab, capped at the 200 worst rows (the CSV export carries
   the full list). The drill-down follows the same Standard + Custom
   blending as the charts themselves, so a bar built from Custom rules
   (e.g. a One-click run) resolves to the rows those Custom rules fail.
   Each card also has a **History** tab: every computed scorecard is
   **auto-persisted** (deduplicated - a rerun of an unchanged dashboard
   records nothing) with who/when and a config fingerprint, feeding a
   score-trend chart (◆ marks config changes), a run log, and a
   **"what changed" diff** vs the previous run (per-rule / per-CDE /
   per-dimension deltas via the ML Lab drift engine). A **drop alert**
   banner appears on the card when the score fell ≥ `DQS_DROP_ALERT_PP`
   (default 5 pp) vs the previous run - flagging when the configuration
   also changed, so a config edit isn't mistaken for a data regression.
   The "Worst rows" tab and the CSV
   export carry one column per Standard *and* Custom rule with the row's
   per-rule score (100 / 0) and the rule weight in the column header, so
   the user can scan a single row and see which rule failures hurt it.
   They also append the **reference-dataset columns** for every
   referential-integrity Custom rule assigned to the Data Product: each
   reference dataset is left-joined onto the rows and its columns carried
   through, suffixed with the origin dataset (e.g.
   `COUNTRY [VWS_GP_STANDARD_SHARE]`), so the master values the rule
   checked against sit next to each row.
7. **🧪 ML Lab (beta)**: an experimental, **read-only** Step 7 that runs
   ML / statistical-analytics views *on top* of the rules-based scorecard.
   Nine tabs in violet/lavender BETA theme: 🔎 Row Anomalies (rare-failure
   score + robust z + optional IsolationForest), 🎯 Rule Impact (exact
   leave-one-out), 🌿 CDE Clustering (k-means + PCA - numpy fallback or
   sklearn), ⚖️ Weight Sensitivity (Dirichlet Monte-Carlo on the Standard
   weights), 🔭 Cross-DP Comparison (robust z across DPs), 📜 Run History
   (snapshot + drift via PSI + KS + per-rule / per-CDE / per-dim Δ; JSON /
   CSV upload temporarily under maintenance), 🧠 Risk Model (logistic
   regression on per-rule fail flags
   → which rules best segregate RED rows), 💡 DQR Recommendations
   (cross-DP profile-similarity + heuristics), and 🧩 Row Explainability
   (SHAP-equivalent waterfall decomposition of `100 − row_score` into
   per-CDE deficits). scikit-learn is a soft dependency, every algorithm
   has a numpy fallback and the `🔬 Use scikit-learn` toggle activates the
   swap-ins only when the library is importable. Per-algorithm reference:
   [documents/ML_LAB.md](documents/ML_LAB.md).

## Application modes: One-click vs Step-by-step

The very first screen (`mode_selection`, before Step 0) asks the user to
choose how to build the scorecards. The chosen mode is stored in
`session_state.app_mode` and decides which steps are visible from then on;
**Restart** clears the mode and returns here.

### ⚡ One-click mode

Goal: a complete set of scorecards from just two choices. The single
`one_click` step asks for a **domain** and the **systems**, then a
**Generate** click runs the whole pipeline automatically:

- **Custom rules only** - the Custom DQR source is selected at 100% (no
  Standard rules).
- **Every Custom DQR** available for each system is applied, each with its
  **default options / parameters / toggles** (nothing changed). The default
  params are exactly what Step 4.2 produces when the user touches nothing,
  so a One-click config is identical to an untouched Step-by-step one.
- **Only the required CDEs** are selected - the union of the columns those
  rules declare, in data-product column order.
- **Weights are distributed equally** within the Custom source (the same
  `distribute_equally` helper Step 5 uses), summing to 100%.
- **Scorecards are computed** with the same engine the dashboard uses, and
  the **CSV export** is validated up-front.
- The user **lands on the dashboard** with a one-time summary banner; the
  per-Data-Product CSV / JSON download buttons are the existing ones.

The automation logic lives in `src/one_click.py` (`run_one_click`,
`build_one_click_config`, `default_rule_params`) - a Streamlit-free,
unit-tested service that the `one_click` UI step wires into session state.

**Validations / edge cases** (all surfaced without crashing):

| Situation | Behaviour |
|-----------|-----------|
| No domain selected | Generate disabled with a notice |
| No system selected | Generate disabled with a notice |
| A selected system has no applicable Custom DQRs | warned and skipped; if *no* selected system has rules, Generate is blocked |
| A rule's required column is missing from the data product | warning; the rule is marked "Not evaluated" downstream |
| Project filter matches 0 rows for a system | that system is skipped with a reason |
| Scorecard generation fails for a system | that system is skipped (the run continues for the others) |
| CSV export fails for a system | recorded and surfaced on the dashboard; the (valid) scorecards still show |

**Assumptions / limitations.** One-click is intentionally **custom-only**:
it does not apply Standard DQRs, does not expose rule options, and does not
let the user re-weight rules. For any of that, use Step-by-step mode. One-click
also follows the active sidebar **Sample mode** and **Project filter** just
like the manual flow.

### 🛠️ Step-by-step mode

Identical to the historical app: picking Step-by-step routes to Step 0 (domain
selection) and the user walks every step manually (Steps 0-6 + the optional
ML Lab), with all sources, options, toggles, CDE selections, weight
configuration, scorecard generation and CSV/JSON exports available exactly
as before. Nothing in the Step-by-step flow changed.

### 📂 Saved projects (versioned, with audit changelog)

From the dashboard, **💾 Save as project** captures the whole
configuration - domain, systems, CDEs, Standard/Custom rules with params,
and every weight (never the data) - under a project name. Saves are
**append-only versions** stamped with who/when plus a human-readable
summary of what changed vs the previous version (rules added/removed,
weights/params changed, ...), so the version list *is* the audit
changelog. Once at least one project exists, the start screen gains an
**Open a saved project** section: pick a project (and optionally an older
version), and the app rebuilds the data products fresh, applies the saved
configuration, and lands on the dashboard in Step-by-step mode - every
step stays editable, and saving again creates the next version. Storage
goes through the persistence layer (`DQS_PERSISTENCE`).

### 📑 Executive report (HTML, print-to-PDF)

The dashboard's **📑 Executive report (HTML)** button downloads a fully
self-contained HTML file - no external scripts, fonts or images - with
every dashboard view: the cross-DP overview, each DP's score / threshold
distribution / source weights, the By-CDE and By-Dimension breakdowns
(HTML/CSS bars), the Standard and Custom rule tables, the worst rows, and
the persisted score trend with the delta vs the previous run. A
`@media print` stylesheet keeps it A4-friendly (one DP per page, colors
preserved), so **Ctrl+P → Save as PDF** produces the shareable executive
PDF without any PDF library - the pragmatic path inside Streamlit in
Snowflake, where PDF-generation packages are unavailable.

### 📊 Adoption & audit (admin page)

The app records adoption/audit telemetry through the same fire-and-forget
persistence layer: one `app_open` per session, one `step_view` per step
transition (with mode + domain), every CSV/JSON `export`, and
`project_saved` / `project_loaded` - each stamped with the acting user
(`CURRENT_USER()` in SiS, OS login locally). The **📊 Usage & audit**
button on the start screen opens a standalone admin page with headline
counters (unique users, app opens, scorecard runs, exports, project
saves/loads), a runs-per-week trend, adoption by domain/system, per-user
activity, and the unified audit trail. **Authorization stays with
Snowflake roles/grants** (see `deploy/`) - the app measures what
authorized users did; it does not gate who may enter.

## Project structure

Several modules that grew past a few hundred lines were partitioned into
per-concern packages. The legacy module name is kept as a slim
re-export shim so external callers don't change. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the layout's working map (intended audience:
onboarding engineers).

```
data_quality_app/
├── app.py                       # Streamlit router (current_step -> renderer)
├── requirements.txt             # Top-level deps with version caps (LOCAL dev / CI)
├── requirements.lock            # Pinned versions for reproducible LOCAL/CI installs
├── environment.yml              # SiS production deps (Snowflake Anaconda channel)
├── deploy/                      # SiS deployment reference SQL (role + CREATE STREAMLIT)
├── pyproject.toml               # ruff + pyright config (no build metadata)
├── README.md
├── ARCHITECTURE.md              # Onboarding map of the layout & patterns
├── .env.example                 # Placeholders only - never commit real creds
├── .gitignore
├── .github/workflows/tests.yml  # CI: ruff + pytest with coverage
├── config/
│   ├── settings.py              # General settings (thresholds, mock/snowflake mode)
│   ├── domains.py               # Domain registry (Cost Estimate, Quality, ...)
│   ├── systems.py               # SystemDef / TableDef + Cost Estimate ADR/ACCE/EPT
│   ├── dqr_catalog.py           # 10 Standard DQR dimensions
│   ├── dqr_sources.py           # "standard" / "custom" source identifiers
│   ├── custom_dqr_catalog.py    # SLIM re-export; assembles CUSTOM_DQR_RULES
│   └── custom_dqr/              # M6 split (per system)
│       ├── _shared.py           # CustomRuleDef + option-builder helpers
│       ├── _ept_catalog.py      # EPT_RULES list (E1-E7)
│       ├── _adr_catalog.py      # ADR_RULES list (A1-A8)
│       ├── _acce_catalog.py     # ACCE_RULES list (AC1-AC8)
│       └── _sqs_catalog.py      # SQS_RULES list (Quality domain - SQ*)
├── src/
│   ├── models.py                # Dataclasses (CDE, DQRAssignment, Scorecard)
│   ├── snowflake_client.py      # Snowflake data layer (Snowpark in SiS / connector locally)
│   ├── mock_data.py             # Synthetic data generator (demo mode)
│   ├── data_product_builder.py  # Joins → Data Product
│   ├── profiler.py              # Column profiling
│   ├── dqr_engine.py            # Standard DQR (10 dimensions) + dispatcher
│   ├── dqr_validation.py        # Per-dimension compatibility checks (Step 4.1 / Step 6)
│   ├── reference_data.py        # Reference dataset registry (e.g. project_master)
│   ├── persistence.py           # Run history / telemetry / saved projects (local ⇄ Snowflake)
│   ├── run_history.py           # Auto-snapshot service: fingerprints, dedup, drop detection
│   ├── projects.py              # Saved projects: versioned config capture + audit changelog
│   ├── telemetry.py             # Adoption/audit metrics for the 📊 Adoption admin page
│   ├── scorecard.py             # Score computation (standard + custom combined)
│   ├── one_click.py             # ⚡ One-click automation service (custom-only, equal weights)
│   ├── ml_lab.py                # 🧪 ML Lab algorithms (Step 7, beta) - read-only
│   ├── custom_dqr_engine.py     # SLIM re-export of src/custom_dqr/*
│   └── custom_dqr/              # C1 split (per family + dispatcher)
│       ├── _shared.py           # CustomRuleNotEvaluated + reusable helpers
│       ├── _validators.py       # validate_completeness / referential_integrity
│       ├── _ept_rules.py        # E1-E7 checks + constants + EPTE3/E6Params
│       ├── _adr_rules.py        # A1-A8 checks + constants + ADRA3/A7/A8Params
│       ├── _acce_rules.py       # AC1-AC8 checks + constants + ACCEAC3/AC7/AC8Params
│       ├── _sqs_rules.py        # SQ* checks + constants (Quality domain)
│       └── _dispatcher.py       # evaluate_custom_rules(df, assignments, dp)
├── ui/
│   ├── step_mode_selection.py            # Initial step - One-click vs Step-by-step picker
│   ├── step_one_click.py                 # ⚡ One-click - domain + systems + Generate
│   ├── step_00_domain_selection.py
│   ├── step_01_system_selection.py
│   ├── step_02_data_product_review.py
│   ├── step_03_cde_selection.py
│   ├── step_04_dqr_source_selection.py    # Step 4 - Standard / Custom selector
│   ├── step_04_dqr_assignment.py          # Step 4.1 - Standard DQR assignment
│   ├── step_04_2_custom_dqr.py            # Step 4.2 - Custom DQR rule cards
│   ├── step_05_weight_assignment.py
│   ├── step_06_dashboard.py               # SLIM orchestrator + page header + nav
│   ├── step_06/                           # Dashboard partitioned by concern
│   │   ├── _shared.py          # CSS, _status_class, system icons / accents
│   │   ├── _export.py          # CSV / JSON download builders
│   │   ├── _charts.py          # Plotly gauge + threshold-bar
│   │   ├── _breakdown.py       # DP-card header, source-breakdown, Custom Rules table
│   │   ├── _drilldown.py       # Click a bar / select a rule -> failing rows table
│   │   ├── _history.py         # Auto-record runs + drop alert + History tab
│   │   ├── _projects.py        # Save-as-project panel + version changelog
│   │   ├── _exec_report.py     # 📑 Self-contained executive HTML report (print-to-PDF)
│   │   └── _dp_dashboard.py    # Per-DP card (gauge + tab row) + cross-DP overview
│   ├── step_adoption.py                   # 📊 Adoption & audit admin page (usage + audit trail)
│   ├── step_07_ml_lab.py                  # SLIM orchestrator + tab dispatcher
│   └── step_07/                           # B5 split (one module per ML Lab tab)
│       ├── _shared.py           # CSS, banner/empty helpers, _ensure_scorecards
│       ├── _row_anomalies.py    # 🔎 Row Anomalies
│       ├── _rule_impact.py      # 🎯 Rule Impact
│       ├── _cde_clusters.py     # 🌿 CDE Clustering
│       ├── _weight_sensitivity.py  # ⚖️ Weight Sensitivity
│       ├── _cross_dp.py         # 🔭 Cross-DP Comparison
│       ├── _run_history.py      # 📜 Run History
│       ├── _risk_model.py       # 🧠 Risk Model
│       ├── _recommendations.py  # 💡 DQR Recommendations
│       └── _row_explain.py      # 🧩 Row Explainability
├── utils/
│   ├── helpers.py
│   ├── ui_components.py         # render_nav_footer (shared Back/Restart/Next row)
│   ├── session_state.py         # SLIM re-export of utils/session/*
│   └── session/                 # M7 split
│       ├── state.py             # STEPS, init_state, set_domain, ...
│       ├── navigation.py        # next/prev/restart, _visible_steps, goto, ...
│       └── sidebar.py           # CSS, brand, progress stepper, filters
└── tests/                       # 1,200+ tests across 30 modules; conftest pins DATA_SOURCE=mock
    ├── conftest.py
    ├── test_profiler.py
    ├── test_dqr_engine.py
    ├── test_dqr_engine_extra.py
    ├── test_dqr_validation.py
    ├── test_dqr_sources_config.py
    ├── test_custom_dqr_engine.py
    ├── test_custom_dqr_catalogs.py        # M6 catalog invariants (A6)
    ├── test_step_04_source_selection_ui.py
    ├── test_step_04_2_custom_ui.py
    ├── test_scorecard.py
    ├── test_data_product_builder.py
    ├── test_models.py                     # dataclass contracts (A6)
    ├── test_reference_data.py             # cache + loader contracts (A6)
    ├── test_mock_data.py                  # mock builder shape (A6)
    ├── test_domains.py                    # registry + active-domain helpers
    ├── test_helpers.py
    ├── test_session_state.py
    ├── test_snowflake_client.py
    ├── test_coverage_gaps.py
    ├── test_misc_gaps.py
    ├── test_ui_flow.py                    # End-to-end via streamlit.testing.AppTest
    ├── test_ui_units.py
    ├── test_step_00_domain_ui.py
    ├── test_step_mode_selection_ui.py     # Initial mode picker (One-click / Step-by-step)
    ├── test_step_one_click_ui.py          # ⚡ One-click step + validations
    ├── test_one_click.py                  # One-click service (src/one_click.py)
    ├── test_app_mode_flow.py              # Mode on-ramps + flow separation + regression
    ├── test_persistence.py                # Persistence layer (identity + 3 backends)
    ├── test_run_history.py                # Run-history service + Step 6 history UI
    ├── test_projects.py                   # Saved projects: service + save panel + loader
    ├── test_telemetry.py                  # Adoption metrics + logging helpers + admin page
    ├── test_exec_report.py                # Executive HTML report builder + download wiring
    ├── test_step_06_dashboard_export.py
    ├── test_step_06_drilldown.py          # Click-to-drill-down helpers (Step 6 tabs)
    ├── test_step_07_ml_lab_ui.py
    └── test_ml_lab.py
```

## Installation

```bash
# 1. Create and activate a venv
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 2. Install dependencies
# For day-to-day development (latest patches within the supported majors):
pip install -r requirements.txt
# For a reproducible install (CI, prod, repro of a bug):
pip install -r requirements.lock

# 3. Copy the environment file
cp .env.example .env
# Edit .env with your Snowflake credentials (or leave DATA_SOURCE=mock)

# 4. (Optional) Wire pre-commit hooks so ``git commit`` runs ruff first
pip install pre-commit
pre-commit install
```

After upgrading or adding a dependency, regenerate the lockfile so CI stays
reproducible:

```bash
pip install -r requirements.txt
pip freeze > requirements.lock
```

## How to run

### Locally (development / demo)

```bash
streamlit run app.py
```

Runs on your machine against mock data by default (or Snowflake via
`externalbrowser` SSO when `DATA_SOURCE=snowflake`). This is the path used for
local demos.

### Production: Streamlit in Snowflake (SiS)

In production the app is deployed as a **Streamlit in Snowflake** app from this
GitHub repository (Projects → Streamlit in the Snowflake account). Differences
from local execution:

- The app obtains its Snowflake handle from the **active Snowpark session**
  (`get_active_session()`) — there is no `.env`, no `externalbrowser`, and no
  `snowflake.connector`. The data layer (`src/snowflake_client.py`) selects this
  backend automatically inside Snowflake and falls back to the local connector
  otherwise.
- Python dependencies are resolved from the **Snowflake Anaconda channel** via
  [`environment.yml`](environment.yml) — **not** from `requirements*.txt`
  (which remain local-dev / CI only).
- Authentication is the viewer's Snowflake login; data access is the app's
  Snowflake role — run it under a dedicated **least-privilege, read-only** role.

Reference deployment scripts (GitHub Git integration + least-privilege role +
`CREATE STREAMLIT`) live in [`deploy/`](deploy/) — see
[`deploy/README.md`](deploy/README.md).

## Operating modes

The `DATA_SOURCE` variable controls the data source:

- `DATA_SOURCE=mock` - generates synthetic in-memory data with deliberately
  injected quality problems (ideal for demo and development).
- `DATA_SOURCE=snowflake` - reads from Snowflake. **Inside Streamlit in
  Snowflake** the app uses the active Snowpark session (`get_active_session()`);
  **for local development** it connects via `snowflake.connector` with
  `externalbrowser` authentication. The data layer picks the backend
  automatically. (Locally, `DATA_SOURCE` is read from `.env`; in SiS it defaults
  to its built-in value since there is no `.env`.)

Separately, `DQS_PERSISTENCE` controls where the app **persists its own
state** (run history, adoption/audit telemetry, saved projects - see
`src/persistence.py`): `local` (default - JSON-lines files under
`.dqs_store/`, git-ignored), `snowflake` (append-only `DQS_*` tables,
created via [`deploy/03_persistence_tables.sql`](deploy/03_persistence_tables.sql)),
or `off`. It is deliberately independent of `DATA_SOURCE`, so a local run
can read real Snowflake data while still persisting state to local files.
Every write stamps the acting user (`CURRENT_USER()` inside SiS, the OS
login locally) and is **fire-and-forget**: a storage failure is logged and
swallowed, never breaking the dashboard.

## Multi-domain architecture

The app runs the same DQ workflow against any registered
domain. A *domain* bundles:

- **Systems** - `SystemDef`s with their tables, join keys, primary
  table flag and optional per-row derivations.
- **Custom DQR catalog** - per-system list of `CustomRuleDef`s.
- **Visual metadata** - icon, accent colour, sidebar tagline,
  per-system icons / accents for the cards downstream of Step 0.
- **Project filter** - a `ProjectFilterDef` declaring the column the
  sidebar Project filter targets (Cost Estimate filters on
  `PLANVIEW_ID`; Quality filters on `PROJECT_CODE`). Defaults to
  `DEFAULT_PROJECT_FILTER` when omitted, so existing domains keep the
  historical `PLANVIEW_ID` behaviour for free.
- **Placeholder flag** - `True` while the schema and curated rules
  are still being defined, surfaced as a `BETA · PLACEHOLDER` pill on
  the Step 0 card.

`config/domains.py` is the registry. Two domains ship today:

| Code | Name | Systems | Status |
|------|------|---------|--------|
| `cost_estimate` | Cost Estimate | ADR, ACCE, EPT | Production (23 custom rules) |
| `quality` | Quality | SQS | Beta (SQ4 - Validity on `EXPECTED_SHIP_DATE`, SQ5 - Business Rule for PO ship-date alignment, SQ6 - Validity on `INSPECTION_TYPE`, SQ7 - Validity on `WORK_CRITICALITY`, SQ8 - Completeness on `STATUS`, SQ9 - Validity on the `STATUS` workflow vocabulary, SQ10 - Business Rule pinning Completed inspections to a non-future ship date) |

### Adding a new domain

1. **Define the systems**. In `config/domains.py` (or in a separate
   module imported from it), build a `Dict[str, SystemDef]`. Each
   `SystemDef` lists the tables, the join keys and the primary table.
   Reuse `config.systems.SystemDef` / `TableDef` directly - the shapes
   are domain-agnostic.
2. **Define the custom rules**. Build a `Dict[str, List[CustomRuleDef]]`
   keyed by system code (empty lists are fine if you don't have rules
   yet - the UI shows a clear empty-state callout in Step 4.2).
3. **Add mock fixtures** in `src/mock_data.py` for each new table the
   domain introduces. Register them in `_MOCK_REGISTRY`. The Snowflake
   path doesn't need any code change - the existing
   `_default_fetcher` already routes `SystemDef.tables[*].name` through
   the shared client.
4. **Add the `DomainDef`** to `config.domains.DOMAINS`:

   ```python
   DOMAINS["safety"] = DomainDef(
       code="safety",
       name="Safety",
       subtitle="Incidents · Audits",
       description="Track safety incidents and audit DQ.",
       icon="🦺",
       accent="#f97316",
       tagline="Build CDE-driven scorecards over safety records.",
       page_title="DQ Scorecard - Safety",
       sidebar_brand_subtitle="SAFETY",
       systems=SAFETY_SYSTEMS,
       custom_rules=SAFETY_CUSTOM_RULES,
       system_icons={"INCIDENTS": "⚠️", "AUDITS": "🔎"},
       system_accents={"INCIDENTS": "#dc2626", "AUDITS": "#f97316"},
       # Optional: override the sidebar Project filter column. Defaults
       # to PLANVIEW_ID (DEFAULT_PROJECT_FILTER) when omitted.
       project_filter=ProjectFilterDef(
           column="INCIDENT_ID",
           label="INCIDENT_ID(s)",
           placeholder="INC-00001\nINC-00002",
           help="Restrict the app to one or more incidents.",
       ),
   )
   ```

5. **Done.** No other code change. Every step downstream of Step 0
   reads `get_active_domain()` and re-parameterises itself. The Step 0
   card, sidebar brand, system cards (Step 1), the sidebar Project
   filter (uses the domain's `project_filter.column`) and Step 4.2
   custom-rule cards all pick up the new domain automatically.

### How Cost Estimate and Quality are loaded

`config.domains._build_cost_estimate_domain()` wraps the historical
`config.systems.SYSTEMS` dict and the legacy
`config.custom_dqr_catalog.CUSTOM_DQR_RULES` dict one-for-one. Cost
Estimate therefore stays the byte-for-byte same data shape as it was
before the multi-domain refactor - any test that pins the Cost
Estimate code path still asserts on the exact same SystemDef objects.

`config.domains._build_quality_domain()` defines a single system
(`SQS`) backed by the curated inspection table
`CT_SQS_AT_INSPECTION`. In Snowflake mode the table is read from
`INGESTION_DB.GP_QUALITY` - set `SNOWFLAKE_DATABASE=INGESTION_DB` and
`SNOWFLAKE_SCHEMA=GP_QUALITY` in `.env` before running the workflow
against Quality. A synthetic generator in `src.mock_data` mirrors the
inspection-table shape for demo mode. The Quality team is finalizing
the broader catalog; the domain seeds it with `SQ4` (Validity on
`EXPECTED_SHIP_DATE`) and grows from there.

## Configuring custom DQR rules

Each Data Product can have its own catalog of custom rules. The
`config/custom_dqr_catalog.py` and `src/custom_dqr_engine.py` modules are slim
re-export shims; the rules physically live in the per-system files
`config/custom_dqr/_<sys>_catalog.py` and `src/custom_dqr/_<sys>_rules.py`.

The steps below add a rule to the **Cost Estimate** catalog (assembled into
`CUSTOM_DQR_RULES`). Rules for other domains - e.g. Quality/SQS - attach
through that domain's `DomainDef.custom_rules` map instead of `CUSTOM_DQR_RULES`
(see ARCHITECTURE.md: "Adding a new Custom DQR rule" and the "Quality (SQS) catalog
wiring" note). To add a rule for an existing Cost Estimate data product:

1. Implement (or reuse) a check function `(df) -> pd.Series[bool]` in
   `src/custom_dqr_engine.py`. Two reusable validators are exposed there:
   - `validate_completeness_rule(df, required_columns)` - used by E1 / E4
     and by any future Completeness rule.
   - `validate_referential_integrity_rule(source_df, source_column,
     reference_df, reference_column)` - used by E7 and any future
     Referential Integrity rule.

   Statistical-outlier rules (E3, E6, A3, A7, A8, AC3, AC7, AC8)
   compute group-level metrics inside their own `check` function and
   propagate the per-group verdict back to every row of the failing
   group. Each one accepts a `params` argument and reads its
   threshold from `params[<RULE>_THRESHOLD_PARAM]` so the user can
   pick a percentile (P75 / **P90 default** / P95 / P99 for E3 / A3 /
   AC3) or IQR multiplier (**1.5× default** / 2.0× / 3.0× for E6 /
   A7 / A8 / AC7 / AC8) in Step 4.2.
2. Add a `CustomRuleDef(...)` entry to the relevant list in
   `CUSTOM_DQR_RULES`. Required fields: `id`, `name`, `type` (e.g.
   `"Completeness"`, `"Consistency"`, `"Referential Integrity"`,
   `"Statistical Outlier"`), `description`, `notes`, `required_columns`
   (alias → physical column), `blocking` flag, and `check` callable.
   Referential-integrity rules also set the optional `reference` field -
   `{"reference_dataset": "...", "source_column": "...",
   "reference_column": "...", "lookup_column": "..."}`, which the UI
   surfaces in Step 4.2. Per-rule **options** come in two flavours:
   `CustomRuleOption` renders as a toggle (used by E3 / A3 for the
   `project_scoped` and `detect_uniform_mapping` switches), and
   `CustomRuleSelectOption` renders as a selectbox (used by every
   statistical-outlier rule to expose a customizable threshold -
   percentile for E3 / A3, IQR multiplier for E6 / A7 / A8). Values flow
   through to the `check` callable's `params` argument and can extend
   the rule's required CDEs when enabled (E3's project-scope toggle
   demands `PLANVIEW_ID` only when the user turns it on; A3's
   project-scope toggle has no extra coverage cost since `PLANVIEW_ID`
   is already required; threshold selectboxes never extend required
   columns, they only customize numeric cutoffs).
3. If your rule depends on a reference dataset, register a loader in
   `src/reference_data.py`. Custom rules whose dependency is unavailable
   must raise `CustomRuleNotEvaluated` from `src.custom_dqr_engine` -
   never silently pass. The dispatcher records the reason and Step 6
   surfaces a "Not evaluated" warning so the gap is visible.
4. The new rule appears automatically in Step 4.2 for that data product.
   Step 5 picks it up for rule-level weight distribution (single-rule
   selections auto-pin to 100%); Step 6 reports its pass rate (or
   "Not evaluated" status) in the "Custom Rules" tab.

EPT seeds **seven** custom rules, ADR seeds **eight**, and ACCE seeds
its parallel AC1… catalog (mirroring A1–A8 against the ACCE schema)
out of the box. Full per-rule documentation lives in
[documents/CUSTOM_RULES.md](documents/CUSTOM_RULES.md); the headline list is:

| Data Product | ID | Name | Type | Blocking |
|--------------|----|------|------|----------|
| EPT | E1 | ISO Code of Account Present (COR + SAB)               | Completeness         | Yes |
| EPT | E2 | Location + estimate date present                       | Completeness         | No  |
| EPT | E3 | Statistical Excessive WBC to ISO Mapping               | Statistical Outlier  | No  |
| EPT | E4 | Level 1 cost category populated                        | Completeness         | No  |
| EPT | E5 | FEED / Engineering hours estimate present when cost exists | Consistency      | No  |
| EPT | E6 | Cost-to-hours ratio outlier check                      | Statistical Outlier  | No  |
| EPT | E7 | Project Key linkage                                    | Referential Integrity| Yes |
| ADR | A1 | ISO Code of Account present (COR + SAB)                | Completeness         | Yes |
| ADR | A2 | Location + estimate date present & valid               | Completeness & Validity | No  |
| ADR | A3 | Statistical WBC-to-ISO mapping ratio                   | Statistical Outlier  | No  |
| ADR | A4 | Core quantities populated & non-negative project totals | Completeness & Validity | No  |
| ADR | A5 | Design details present when quantity exists           | Consistency          | No  |
| ADR | A6 | Construction hours present when quantity exists       | Consistency          | No  |
| ADR | A7 | Within-discipline quantity / hour ratio outlier        | Statistical Outlier  | No  |
| ADR | A8 | Cross-discipline quantity ratios                       | Statistical Outlier  | No  |
| ACCE | AC1 | ISO Code of Account present (COR + SAB) - `COA[:3]` lookup    | Completeness | Yes |
| ACCE | AC2 | Location + estimate date present & valid (uses `JOB_NO`)   | Completeness & Validity | No  |
| ACCE | AC3 | Statistical COA-to-ISO mapping ratio                       | Statistical Outlier | No |
| ACCE | AC4 | Core quantities populated & non-negative project totals (via `DESCRIPTION`) | Completeness & Validity | No |
| ACCE | AC5 | Design details present when quantity exists                | Consistency | No |
| ACCE | AC6 | Construction hours present when quantity exists (`COST_MH`) | Consistency | No |
| ACCE | AC7 | Within-discipline quantity / hour ratio outlier (`DESCRIPTION`; optional project-type segmentation) | Statistical Outlier | No |
| ACCE | AC8 | Cross-discipline quantity ratios (`COMPONENT_SOURCE`; optional project-type segmentation) | Statistical Outlier | No |
| SQS | SQ4 | Valid date (`EXPECTED_SHIP_DATE`)                          | Validity            | No |
| SQS | SQ5 | Not after PO Required Ship Date (`EXPECTED_SHIP_DATE` vs `PO_REQUIRED_SHIP_DATE`) | Business Rule | No |
| SQS | SQ6 | Inspection Type value in allowed set (`INSPECTION_TYPE`)   | Validity            | No |
| SQS | SQ7 | Work Criticality value in allowed set (`WORK_CRITICALITY`) | Validity            | No |
| SQS | SQ8 | Status required (`STATUS` populated, non-blank)            | Completeness        | No |
| SQS | SQ9 | Status value in allowed set (`STATUS` in 11 canonical workflow statuses) | Validity | No |
| SQS | SQ10 | Status / Expected Ship Date sequencing (Completed → ship date not future) | Business Rule | No |

E2 / E7 / A2 / AC2 depend on the `VWS_GP_STANDARD_SHARE` reference
table (loaded from the same warehouse / database / schema as the
primary table in Snowflake mode, or from the deterministic project
pool in mock mode); E6, A7, A8, AC7, and AC8 optionally depend on
the same table when their `segment_by_project_type` toggle is on
(lookup `E05_DEPARTMENT` + `BUSINESS` to derive the project archetype
the IQR is computed within); A1, A3, AC1, and AC3 depend on
`ACCE_COA_MASTER`
(loaded from `INGESTION_DB.GP_ADF_CSE` in Snowflake mode, or from a
fixed COA-group pool in mock mode). A1 / AC1 validate the COR/SAB
resolution by joining a 3-character ICARUS_COA group against the
master - ADR derives the group via `SPLIT_PART(COMPLETE_WBC, '.', 1)`,
ACCE via the first three characters of the 4-character `COA`. A3 /
AC3 measure distinct-source-code aggregation per resolved bucket (A3
counts distinct `COMPLETE_WBC`, AC3 counts distinct `COA` over the
*full* 4-character value); A2 / AC2 validate `COUNTRY` +
estimate-basis date (present **and** in the fiscal quarter-year format)
/ gate via the Planview join. The reference
tables are **eager-loaded in Step 2** alongside the system tables and
cached in session state, so Step 6 (and the Restart button) never
re-open a Snowflake connection. The rules raise
`CustomRuleNotEvaluated` with the underlying loader error when their
reference table is unavailable.

## Customising for your real systems

Edit **`config/systems.py`** to adjust table names. The default schema reflects:

- **ADR** → `ADR_DIM_ESTIMATEITEMRECORD` (primary, PK=`ROW_ID`) + `ADR_FACT_ESTIMATECOSTRESULTS` + `ADR_FACT_ESTIMATEQTYRESULTS` + `ADR_DIM_ESTIMATEDESIGNDETAILS`
- **ACCE** → `ACCE_ESTIMATEITEMRECORD` (primary, PK=`ROW_ID`) + `ACCE_ESTIMATECOSTRESULTS` + `ACCE_ESTIMATEQTYRESULTS` + `ACCE_ESTIMATEDESIGNDETAILS`
- **EPT** → single table `ONSHORE_CETDATA` (key `PLANVIEW_ID`)

Internal joins use **`ROW_ID`** (PK of the estimate item) for ADR's children
and for ACCE's cost / qty children. ACCE's design dimension is the exception:
it joins on **`DESIGN_ID`** (FK on the primary - many items can reference the
same design). Cross-system linking is done via **`PLANVIEW_ID`** (project
grain), preserved in the primary table of each system.

## Running the tests

The project ships 1,200+ tests across 30 modules covering every production
module under `app.py`, `config/`, `src/`, `ui/`, and `utils/` - including
27 dedicated tests for the experimental ML Lab. The full suite runs in
under 10 seconds.

```bash
# Run all tests
pytest tests/ -v

# Run with coverage (production code only)
pytest --cov=app --cov=src --cov=config --cov=utils --cov=ui --cov-report=term

# Full coverage report (including test files themselves)
pytest --cov=. --cov-report=term-missing
```

### Test layout

- **Engine / backend** (`test_profiler.py`, `test_dqr_engine*.py`,
  `test_dqr_validation.py`, `test_custom_dqr_engine.py`, `test_scorecard.py`,
  `test_data_product_builder.py`, `test_misc_gaps.py`), pure-Python tests
  for profiling, Standard / Custom DQR rules, validation, scoring, and
  helpers.
- **Snowflake client** (`test_snowflake_client.py`), the `snowflake.connector`
  module is mocked, so tests run without network access or credentials.
- **Source-selection / Custom UI** (`test_dqr_sources_config.py`,
  `test_step_04_source_selection_ui.py`, `test_step_04_2_custom_ui.py`) -
  Step 4 source picker, Custom rule cards, per-rule options, and the live
  CDE-coverage validator.
- **UI end-to-end** (`test_ui_flow.py`) - drives the full Streamlit app via
  `streamlit.testing.v1.AppTest`. Each step is exercised in isolation by
  pre-populating `session_state` (avoids cross-step widget-tracking issues).
- **UI unit tests** (`test_ui_units.py`), each per-dimension parameter editor
  in Step 4.1 (Validity regex, Accuracy min/max, Consistency operator, etc.)
  and the weight buttons in Step 5 are tested with a `MagicMock` streamlit
  module; Step 3 grid / chip-strip helpers are also exercised.
- **🧪 ML Lab** (`test_ml_lab.py`) - 27 tests covering every public function in
  `src/ml_lab.py`: rule-flag matrix alignment, anomaly ranking (numpy + the
  IsolationForest sklearn path), exact LOO baseline equality with
  `result.standard_score`, k-means/PCA shapes (numpy + sklearn paths),
  weight-perturbation distribution, cross-DP robust-z flagging, JSON / CSV
  snapshot round-trips, PSI ≈ 0 sanity + |Δ| threshold flagging in
  `compute_drift`, logistic regression (numpy + sklearn), DQR-recommendation
  heuristics, and the row-explainability waterfall summing exactly to
  `100 − row_score`.

Tests use the `DATA_SOURCE=mock` path by default, no Snowflake credentials
are required.

## Documentation index

In addition to this README, see:

- [documents/DOCUMENTATION.md](documents/DOCUMENTATION.md) - full technical
  documentation (domain concepts, module reference, scoring rules,
  extension points).
- [documents/STANDARD_RULES.md](documents/STANDARD_RULES.md) - per-dimension
  reference for the 10 Standard DQRs (semantics, parameters, supported
  column types, edge cases).
- [documents/CUSTOM_RULES.md](documents/CUSTOM_RULES.md) - per-rule reference
  for the EPT custom catalog (E1–E7), the ADR custom catalog (A1, A2,
  A3, A4, A5, A6, A7, A8), the ACCE custom catalog (AC1, …), and the
  SQS / Quality custom catalog (SQ4, SQ5, SQ6, SQ7, SQ8, SQ9, SQ10, …)
  - including required columns, reference data, options, and pass/fail
  conventions.
- [documents/ML_LAB.md](documents/ML_LAB.md) - 🧪 **ML Lab (beta)** reference:
  philosophy, module API (`src/ml_lab.py`), per-algorithm math (robust-z +
  rare-failure anomalies, exact LOO rule impact, k-means + PCA clustering,
  Dirichlet weight perturbation, cross-DP robust-z, PSI / KS drift,
  logistic-regression risk model, profile-similarity DQR recommendations,
  SHAP-equivalent row-deficit waterfall), snapshot schema, 9-tab UI walk,
  optional scikit-learn swap-ins, testing, extension recipes and known
  limitations.
- [documents/BLOCK_DIAGRAM.md](documents/BLOCK_DIAGRAM.md) - module / layer
  block diagram (Mermaid).
- [documents/FLOWCHART.md](documents/FLOWCHART.md) - end-to-end user / data
  flowchart (Mermaid).
