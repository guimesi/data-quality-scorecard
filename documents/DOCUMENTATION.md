# Data Quality Scorecard App - Technical Documentation

## 1. Overview

The **Data Quality Scorecard App** is a Streamlit-based web application that lets data stewards define, execute, and visualize data quality (DQ) assessments across multi-table source systems. It joins source tables into denormalized **Data Products**, lets users curate **Critical Data Elements (CDEs)**, configure **Data Quality Rules (DQRs)** across 10 dimensions, distribute weights across rules, and produces a **Scorecard** with row-level, CDE-level, and dimension-level metrics.

The app is **multi-domain**: a Step 0 picker decides which *domain* of data the workflow assesses. The historical Cost Estimate domain (ADR / ACCE / EPT) ships alongside a Quality domain (SQS, beta - schema wired against `CT_SQS_AT_INSPECTION` with 7 curated rules, SQ4-SQ10); other domains can be registered without touching the workflow UI - see §4.0 below.

The app opens on a **mode picker** that branches into **⚡ One-click** (pick a domain + systems, then the app auto-builds everything and lands on the dashboard) and **🛠️ Step-by-step** (the manual workflow below). See §4.7 for the full contract; the rest of this document describes the Step-by-step flow, which One-click reuses end-to-end.

A read-only experimental **🧪 ML Lab** (Step 7) sits on top of the rules-based scorecard with unsupervised analytics, run-history drift (PSI / KS), supervised RED-row discrimination, profile-similarity DQR recommendations and SHAP-equivalent row explainability. The lab adds no required dependencies (scikit-learn is a soft dependency; numpy fallbacks ship). See [ML_LAB.md](ML_LAB.md) for the deep dive.

It supports two operating modes:

| Mode | Description | When to use |
|------|-------------|-------------|
| `mock` (default) | Synthetic ADR / ACCE / EPT data with intentional defects | Demo, dev, testing |
| `databricks` | Live Databricks — SQL Warehouse queries against Unity Catalog; headless auth (app service-principal OAuth inside Databricks Apps; `DATABRICKS_HOST` + `DATABRICKS_TOKEN` for local dev) | Production assessments |

---

## 2. Tech Stack

- **Python 3.10+**
- **Streamlit**: UI framework (uses `st.data_editor` for the CDE selection grid in Step 3)
- **Pandas / NumPy**: profiling, joins, scoring, ML Lab fallbacks
- **Plotly**: gauges, charts, waterfalls, drift visualisations
- **databricks-sql-connector / databricks-sdk**: Databricks SQL Warehouse client + headless auth resolution
- **python-dotenv**: environment configuration
- **pytest / pytest-cov**: testing (1,200+ tests across 30 modules; ML Lab adds 27)
- **scikit-learn** *(optional)* - unlocks `IsolationForest`, `KMeans`, `PCA`, `LogisticRegression` swap-ins in Step 7. The lab works without it (numpy fallbacks); install only if you want the toggle.

Build commands ([Makefile](../Makefile)):

```bash
make install   # pip install -r requirements.txt
make run       # streamlit run app.py
make test      # pytest tests/ -v
make clean     # remove caches & coverage artifacts
```

---

## 3. Repository Layout

```
data-quality-app/
├── app.py                    # Streamlit entry point
├── pyproject.toml            # ruff + pyright config (no build metadata)
├── ARCHITECTURE.md           # Onboarding map of the layout & patterns
├── .github/workflows/tests.yml  # CI: ruff lint + pytest with coverage
├── config/                   # Domain registry, system catalog, settings
│   ├── settings.py
│   ├── domains.py            # Domain registry (Cost Estimate, Quality, ...)
│   ├── systems.py            # SystemDef / TableDef + Cost Estimate ADR/ACCE/EPT
│   ├── dqr_catalog.py        # 10 DQ dimensions (Standard source)
│   ├── dqr_sources.py        # Source-id constants (standard / custom)
│   ├── custom_dqr_catalog.py # SLIM re-export; assembles CUSTOM_DQR_RULES
│   └── custom_dqr/           # Catalog partitioned by system (M6)
│       ├── _shared.py        # CustomRuleDef + option-builder helpers
│       ├── _ept_catalog.py   # EPT_RULES list (E1-E7)
│       ├── _adr_catalog.py   # ADR_RULES list (A1-A8)
│       ├── _acce_catalog.py  # ACCE_RULES list (AC1-AC8)
│       └── _sqs_catalog.py   # SQS_RULES list (SQ4-SQ10, Quality domain)
├── src/                      # Core business logic
│   ├── models.py
│   ├── profiler.py
│   ├── dqr_engine.py         # Standard-DQR engine (10 dimensions)
│   ├── dqr_validation.py     # Standard-DQR compatibility layer (Step 4.1 / Step 6)
│   ├── reference_data.py     # Reference dataset registry (project_master, ...)
│   ├── data_product_builder.py
│   ├── scorecard.py
│   ├── one_click.py          # One-click service (UI-free): run_one_click / build_one_click_config
│   ├── ml_lab.py             # 🧪 ML Lab algorithms (Step 7, beta), see ML_LAB.md
│   ├── mock_data.py
│   ├── persistence.py        # Run history / telemetry / saved projects (F0 foundation)
│   ├── run_history.py        # Auto-snapshot service (fingerprints, dedup, drop detection)
│   ├── projects.py           # Saved projects (versioned config capture + audit changelog)
│   ├── telemetry.py          # Adoption/audit metrics for the 📊 Adoption page
│   ├── databricks_client.py
│   ├── custom_dqr_engine.py  # SLIM re-export of src/custom_dqr/*
│   └── custom_dqr/           # Custom-DQR engine partitioned by family (C1)
│       ├── _shared.py        # CustomRuleNotEvaluated + reusable predicates +
│       │                     #   _resolve_planview_segment_map (shared by E6/A7/A8/AC7/AC8)
│       ├── _validators.py    # validate_completeness / referential_integrity
│       ├── _ept_rules.py     # E1-E7 checks + constants + EPTE3/E6Params (TypedDicts)
│       ├── _adr_rules.py     # A1-A8 checks + constants + ADRA3/A7/A8Params
│       ├── _acce_rules.py    # AC1-AC8 checks + constants + ACCEAC3/AC7/AC8Params
│       ├── _sqs_rules.py     # SQ4-SQ10 checks + constants (Quality domain)
│       └── _dispatcher.py    # evaluate_custom_rules(df, assignments, dp)
├── ui/                       # Streamlit UI (mode picker entry → One-click or Step-by-step Step 0 + steps with 4.x sub-steps + 🧪 lab)
│   ├── _theme.py                             # inject_global_css() - one consolidated main-area stylesheet (H5)
│   ├── step_mode_selection.py                # Entry - One-click vs Step-by-step picker
│   ├── step_one_click.py                     # One-click - domain + systems + Generate -> dashboard
│   ├── step_00_domain_selection.py           # 0 - Cost Estimate / Quality / ... (Step-by-step)
│   ├── step_01_system_selection.py
│   ├── step_02_data_product_review.py
│   ├── step_03_cde_selection.py
│   ├── step_04_dqr_source_selection.py    # 4 - pick Standard / Custom / both
│   ├── step_04_dqr_assignment.py          # 4.1 - Standard rule assignment
│   ├── step_04_2_custom_dqr.py            # 4.2 - Custom rule cards
│   ├── step_05_weight_assignment.py
│   ├── step_06_dashboard.py                  # SLIM orchestrator + page header + nav
│   ├── step_06/                              # Dashboard partitioned by concern
│   │   ├── _shared.py                        # CSS, _status_class, system icons / accents
│   │   ├── _export.py                        # CSV / JSON download builders
│   │   ├── _charts.py                        # Plotly gauge + threshold-bar
│   │   ├── _breakdown.py                     # DP-card header, source-breakdown, Custom Rules table
│   │   ├── _drilldown.py                     # Click a bar / select a rule -> failing rows table
│   │   ├── _history.py                       # Auto-record runs + drop alert + History tab
│   │   ├── _projects.py                      # Save-as-project panel + version changelog
│   │   ├── _exec_report.py                   # Self-contained executive HTML report (print-to-PDF)
│   │   └── _dp_dashboard.py                  # Per-DP card (gauge + tab row) + cross-DP overview
│   ├── step_07_ml_lab.py                  # SLIM orchestrator + tab dispatcher
│   └── step_07/                           # ML Lab tabs partitioned (B5)
│       ├── _shared.py                     # CSS, banner/empty helpers, _ensure_scorecards
│       ├── _row_anomalies.py              # 🔎 Row Anomalies
│       ├── _rule_impact.py                # 🎯 Rule Impact
│       ├── _cde_clusters.py               # 🌿 CDE Clustering
│       ├── _weight_sensitivity.py         # ⚖️ Weight Sensitivity
│       ├── _cross_dp.py                   # 🔭 Cross-DP Comparison
│       ├── _run_history.py                # 📜 Run History
│       ├── _risk_model.py                 # 🧠 Risk Model
│       ├── _recommendations.py            # 💡 DQR Recommendations
│       └── _row_explain.py                # 🧩 Row Explainability
├── utils/                    # Session state & helpers
│   ├── colors.py            # STATUS_GREEN/YELLOW/RED - single source for status hexes (H5)
│   ├── helpers.py
│   ├── ui_components.py      # render_nav_footer (shared Back/Restart/Next row)
│   ├── session_state.py      # SLIM re-export of utils/session/*
│   └── session/              # Session state partitioned by concern (M7)
│       ├── state.py          # STEPS, init_state, set_domain, ...
│       ├── navigation.py     # next/prev/restart, _visible_steps, goto, ...
│       └── sidebar.py        # CSS, brand, progress stepper, filters
├── tests/                    # 1,200+ tests across 30 modules; conftest pins DATA_SOURCE=mock
└── documents/                # Specs, decks, this documentation (incl. ML_LAB.md)
```

### Re-export pattern (audit-driven refactors)

The `_*` packages above were carved out of monolithic modules that had
grown past 1.4-3.9k lines each (audits **C1**, **M6**, **M7**, **B5**).
Each refactor kept the legacy module name as a slim re-export shim,
preserving every public symbol via an `__all__` block so external
callers don't need to update imports. The pattern is documented in
[ARCHITECTURE.md](../ARCHITECTURE.md#patterns-to-follow); follow it when
partitioning the next monolith.

---

## 4. Domain Concepts

### 4.0 Data Domains

A **domain** is the top-level scope chosen at Step 0 - the user picks which family of data the workflow will assess. Each domain bundles its own systems, custom DQR catalog and visual identity, defined declaratively as a `DomainDef` in [config/domains.py](../config/domains.py):

```python
@dataclass(frozen=True)
class DomainDef:
    code: str                     # session-state identifier
    name: str                     # human label (Step 0 card)
    subtitle: str                 # short under-the-name descriptor
    description: str              # 2-4 sentence card body
    icon: str                     # emoji
    accent: str                   # hex color
    tagline: str                  # sidebar brand tagline
    page_title: str               # set_page_config() title
    sidebar_brand_subtitle: str   # short subtitle in sidebar brand
    systems: Dict[str, SystemDef] # domain-scoped systems
    custom_rules: Dict[str, List[CustomRuleDef]]
    system_icons: Dict[str, str]  = field(default_factory=dict)
    system_accents: Dict[str, str] = field(default_factory=dict)
    reference_dataset_loaders: Dict[str, Any] = field(default_factory=dict)
    placeholder: bool = False     # surfaced as BETA pill on Step 0
```

Two domains ship out of the box:

| Code | Name | Systems | Status |
|------|------|---------|--------|
| `cost_estimate` | Cost Estimate | ADR, ACCE, EPT | Production - 23 curated custom rules |
| `quality` | Quality | SQS | Beta - `CT_SQS_AT_INSPECTION` (`INGESTION_DB.GP_QUALITY`); 7 curated rules (SQ4-SQ10) |

`session_state["domain"]` carries the active code. `config.systems.get_system`, `config.custom_dqr_catalog.get_available_custom_dqr_rules` and the Step 0/1 UI all read through `config.domains.get_active_domain()` so swapping domain re-parameterises every downstream step automatically.

**Switching domains mid-flight** wipes `selected_systems`, `data_products`, `configs`, `scorecards` and `ml_lab_runs` so partial selections from the previous domain don't leak across. The sidebar's `sample_mode` and `planview_filter` (UI-side preferences) survive the switch.

**Restart** returns to Step 0 and clears `domain` so the user re-picks - useful for switching late in the flow.

**Adding a new domain** is additive: define its `DomainDef`, add it to `config.domains.DOMAINS`, register mock fixtures in `src/mock_data.py` for any new tables, and the rest of the app picks it up. See the *Adding a new domain* section in the [README](../README.md).

### 4.1 Source Systems

Defined in [config/systems.py](../config/systems.py) as `SystemDef` / `TableDef` dataclasses:

| System | Primary Table | Joined Tables | Join Key |
|--------|---------------|---------------|----------|
| **ADR** | `ADR_DIM_ESTIMATEITEMRECORD` | `ADR_FACT_ESTIMATECOSTRESULTS`, `ADR_FACT_ESTIMATEQTYRESULTS`, `ADR_DIM_ESTIMATEDESIGNDETAILS` | `ROW_ID` |
| **ACCE**  | `ACCE_ESTIMATEITEMRECORD`  | `ACCE_ESTIMATECOSTRESULTS`, `ACCE_ESTIMATEQTYRESULTS` | `ROW_ID` |
| **ACCE**  | `ACCE_ESTIMATEITEMRECORD`  | `ACCE_ESTIMATEDESIGNDETAILS` | `DESIGN_ID` (FK on the primary; many items can share one design) |
| **EPT** | `ONSHORE_CETDATA`         | _(none)_                                    | `PLANVIEW_ID` |

All systems preserve `PLANVIEW_ID` as the project grain for cross-system analysis.

### 4.2 Data Product

A **Data Product** is a denormalized DataFrame produced by joining a system's tables. For 1:N relationships (e.g., multiple cost rows per estimate item), the builder aggregates: numeric columns are **summed**, non-numeric columns take **first non-null**. Non-primary table columns are **prefixed** to avoid name collisions.

### 4.3 Critical Data Element (CDE)

A user-curated subset of columns from a Data Product that warrant quality monitoring (e.g., `PLANVIEW_ID`, `COST_ESTIMATE`, `STATUS_CODE`). Selected in Step 3 by ticking the **Pick as CDE** checkbox in the unified profile grid (`st.data_editor`). Each row of the grid surfaces the column's dtype, null %, distinct count, duplicate count, and a sample of values, so the user has the metadata they need to decide inline. Above the grid, a chip-strip lists the columns currently picked as CDEs and each chip carries a native HTML `title` tooltip with the full profile - hover surfaces dtype / nulls / distinct / sample without scrolling.

> **🎯 Select all CDEs required by Custom DQRs.** Each DP card in Step 3 also exposes a one-click shortcut that ticks every column flagged in the **Custom DQRs** cell (the union of every Custom DQR's static `required_columns` and any extras contributed by per-rule options for that system). The button is **not pre-applied**: selection only changes after the user clicks it - and it **preserves** any CDE the user has already picked manually, unioning the two sets in source-column order. Under the hood the click handler rebuilds the cached base DataFrame fed to `st.data_editor` with the new picks ticked and clears the editor's stored widget state, so the new ticks land on the very next render with no extra rerun. The shortcut is hidden when the catalog declares no required columns for the system (e.g. an unknown data product) because there is nothing to pre-select.

> **Why no drag-and-drop?** An earlier revision used `streamlit-sortables` for a left/right drag-and-drop. In practice the widget's component-state sync caused two visible bugs: (1) dragged columns occasionally vanished without landing in the Selected box, and (2) the hover legend rendered above the widget always reflected the previous render's selection. The data-editor checkbox grid is fully Streamlit-native, treats each pick as a deterministic edit on a DataFrame, and re-renders top-to-bottom on every change, so the chip-strip and the success/warning banners stay in lockstep with the actual `cfg.cdes` value.

> **Why we cache the editor's input DataFrame.** `st.data_editor` discards every accumulated user edit whenever its input DataFrame's content changes between reruns (this is documented Streamlit behavior - it lets callers force-refresh the grid by feeding a new DataFrame). If we rebuilt the grid each render from `cfg.cdes`, the first click would update `cfg.cdes`, the next rerun would feed the editor a *different* base DataFrame, and the click would be wiped before it could land. The user would have to click each row twice. To avoid that, [ui/step_03_cde_selection.py](../ui/step_03_cde_selection.py) caches the editor's base DataFrame in `st.session_state` keyed by `id(dp)`, the cache is invalidated only when the underlying `DataProduct` instance actually changes (Step 2 rebuild, Restart, a Sample-mode toggle, or a change to the sidebar Project filter). Within a single Step 3 session the input is bit-identical across reruns and the editor preserves the click. The widget's own `key=` is suffixed with the same `id(dp)` so a fresh DP also gets a fresh widget identity, preventing stale widget state from leaking across workflow runs.

### 4.4 Data Quality Rule (DQR)

A `DQRAssignment` ties one **dimension** + **parameters** + **weight** to one CDE. A single CDE can carry multiple rules (e.g., Accuracy *and* Uniqueness on an ID column).

### 4.4a DQR Sources

Each Data Product opts into one or both of the following **DQR sources** in
Step 4 ([config/dqr_sources.py](../config/dqr_sources.py)):

| Source | Where rules come from | Carried as |
|--------|-----------------------|------------|
| **Standard** | The 10-dimension catalog at [config/dqr_catalog.py](../config/dqr_catalog.py); per-CDE assignments edited in Step 4.1 | `DQRAssignment` in `config.assignments` |
| **Custom**   | Data-product-specific catalog at [config/custom_dqr_catalog.py](../config/custom_dqr_catalog.py); selected in Step 4.2 | `CustomDQRAssignment` in `config.custom_assignments` |

When both sources are active, the user splits a 100% **source-level weight**
between them in Step 4 (e.g. Standard 70% / Custom 30%). When only one source
is active its weight is auto-pinned at 100%.

### 4.4b Custom DQR Catalog

The per-data-product catalog lives in [config/custom_dqr_catalog.py](../config/custom_dqr_catalog.py)
as `CUSTOM_DQR_RULES: Dict[str, List[CustomRuleDef]]`. Each entry exposes:

| Field | Meaning |
|-------|---------|
| `id` | Stable identifier shown in the UI (e.g. `"E1"`, `"E4"`, `"E7"`) and used as `rule_id` in scoring |
| `name` | Human label |
| `type` | Category - `"Completeness"`, `"Referential Integrity"`, or `"Statistical Outlier"` today |
| `description`, `notes` | Visible / expandable text in the rule card |
| `required_columns` | Mapping of business alias → physical column name |
| `blocking` | If True, the rule's failure represents a blocking gap |
| `check` | `(df) -> pd.Series[bool]` callable, True = row passes |
| `reference` | Optional. For Referential Integrity rules: `{"reference_dataset": str, "source_column": str, "reference_column": str}` |
| `options` | Optional. List of `CustomRuleOption` entries - per-rule toggles surfaced in Step 4.2; their values are persisted to `CustomDQRAssignment.params` and routed to the rule's `check` callable when it accepts a `params` argument. Used by E3 and A3 (project-scope + uniform-1:1 mapping detection toggles). |
| `select_options` | Optional. List of `CustomRuleSelectOption(key, label, choices, default, help, description)` entries - per-rule selectboxes surfaced in Step 4.2; values are persisted to `CustomDQRAssignment.params` and routed to the rule's `check` callable. Used by every statistical-outlier rule (E3, E6, A3, A7, A8, AC3, AC7, AC8) to expose a customizable threshold (percentile for E3 / A3 / AC3; IQR multiplier for E6 / A7 / A8 / AC7 / AC8). The default in each entry is the rule's documented baseline (P90 / 1.5×IQR), so the rule behaves identically to its pre-feature self when the user does not touch the picker. |

EPT ships seven custom rules, ADR ships eight, and ACCE ships the
AC1… series (a parallel catalog that mirrors A1–A8 against the ACCE
schema) out of the box:

| Rule | Type | Blocking | Required column(s) | Reference | What it checks |
|------|------|----------|--------------------|-----------|-----------------|
| **E1**: ISO Code of Account Present (COR + SAB) | Completeness | Yes | `CODE_OF_RESOURCE`, `STANDARD_ACTIVITY_BREAKDOWN` | - | Both populated so cost data can be normalized via the EMMA factor. |
| **E2**: Location + estimate date present | Completeness | No | `CENTROID_DATE`, `PLANVIEW_ID` | `VWS_GP_STANDARD_SHARE` (EPT.PLANVIEW_ID → VWS_GP_STANDARD_SHARE.PROJECT_ID, lookup `COUNTRY`) | Estimate basis date is filled and the project's COUNTRY resolves via the Planview reference join. |
| **E3**: Statistical Excessive WBC to ISO Mapping | Statistical Outlier | No | `WBC_LEVEL_5`, `CODE_OF_RESOURCE`, `STANDARD_ACTIVITY_BREAKDOWN`, `TOTAL_HOURS`, `TOTAL_COST_USD` (+ `PLANVIEW_ID` when the project-scope toggle is on) | - | ISO mappings whose distinct-`WBC_LEVEL_5` count exceeds the configured percentile baseline (P75 / **P90 default** / P95 / P99 - selectable on the rule card; global by default; per `PLANVIEW_ID` when the project-scope toggle is on) **and** are material (`SUM(TOTAL_HOURS) > 0` or `SUM(TOTAL_COST_USD) ≥ 100k USD`) are flagged as over-aggregating. The optional `detect_uniform_mapping` toggle additionally fails material buckets whose ratio is exactly 1 - surfaces suspiciously uniform 1:1 mappings (OR'd with the percentile branch). |
| **E4**: Level 1 cost category populated | Completeness | No | `WBC_LEVEL_1` | - | Level 1 cost category is at minimum populated even when finer levels are absent. |
| **E5**: FEED / Engineering hours estimate present when cost exists | Consistency | No | `WBC_LEVEL_1`, `TOTAL_HOURS`, `TOTAL_COST_USD`, `TOTAL_COST_ESTIMATE_CURRENCY` | - | For FEED / Engineering rows (`WBC_LEVEL_1` matches `\b(FEED\|ENGINEERING)\b`), cost and hours must be both present (`> 0`) or both absent. Non-FEED rows are Not Applicable and pass. |
| **E6**: Cost-to-hours ratio outlier check | Statistical Outlier | No | `PLANVIEW_ID`, `TOTAL_HOURS`, `TOTAL_COST_USD`, `TOTAL_COST_ESTIMATE_CURRENCY` | `VWS_GP_STANDARD_SHARE` (only when `segment_by_project_type` is on - `PLANVIEW_ID → PROJECT_ID`, lookup `E05_DEPARTMENT` + `BUSINESS`) | Per-project `SUM(cost) / SUM(hours)` is computed (cost falls back to `TOTAL_COST_ESTIMATE_CURRENCY` when USD is null) and projects whose ratio falls outside the IQR bounds (`Q1 - k·IQR` … `Q3 + k·IQR`, with `k` selectable on the rule card - **1.5× mild default**, 2.0×, or 3.0× extreme) of the eligible-project population are flagged. When the `segment_by_project_type` toggle is on, the IQR is recomputed **within each (E05_DEPARTMENT, BUSINESS) segment** resolved via the Planview reference - a deepwater FPSO is not pooled with an onshore refinery. Projects with no hours, rows lacking `PLANVIEW_ID`, runs below the minimum population threshold (applied per segment in segmented mode), and projects with an unresolved segment (segmented mode only) are Not Applicable and pass. |
| **E7**: Project Key linkage | Referential Integrity | Yes | `PLANVIEW_ID` | `VWS_GP_STANDARD_SHARE` (EPT.PLANVIEW_ID → VWS_GP_STANDARD_SHARE.PROJECT_ID) | EPT record can be joined to the project master via a valid project identifier. |
| **A1** (ADR) - ISO Code of Account present (COR + SAB) | Completeness | Yes | `PLANVIEW_ID`, `COMPLETE_WBC` | `ACCE_COA_MASTER` (`SPLIT_PART(COMPLETE_WBC, '.', 1) → ICARUS_COA`, lookup `ISO_COR` and `SAB`) | Each ADR row's `COMPLETE_WBC` must resolve to a valid `ISO_COR` and a valid `SAB` via the COA master. Validity rejects null / blank / `ERROR` / `N/A` markers. The master may carry multiple rows per `ICARUS_COA`, the rule picks the best-available mapping (preferring valid over invalid). Without `COR` / `SAB`, cost data cannot be normalized via EMMA - blocking gap. |
| **A2** (ADR) - Location + estimate date present & valid | Completeness & Validity | No | `COST_UPDATE`, `PLANVIEW_ID` | `VWS_GP_STANDARD_SHARE` (ADR.PLANVIEW_ID → VWS_GP_STANDARD_SHARE.PROJECT_ID, lookup `COUNTRY`) | Estimate basis date is filled, matches the fiscal quarter-year format `[1-4]Q<YYYY>` (e.g. `2Q2019`), and the project's COUNTRY resolves via the Planview reference join. Mirrors EPT E2 against the ADR data product. |
| **A3** (ADR) - Statistical WBC-to-ISO mapping ratio | Statistical Outlier | No | `PLANVIEW_ID`, `COMPLETE_WBC`, `COST_TOTAL_HOURS`, `COST_TOTAL_COST` | `ACCE_COA_MASTER` (`SPLIT_PART(COMPLETE_WBC, '.', 1) → ICARUS_COA`, lookup `ISO_COR` and `SAB`) | Mirrors EPT E3 against ADR. Resolves `(ISO_COR, SAB)` from `COMPLETE_WBC` via the COA master, computes `WBC_TO_ISO_RATIO = COUNT(DISTINCT COMPLETE_WBC)` per bucket, derives the configured percentile cutoff (P75 / **P90 default** / P95 / P99 - selectable on the rule card; global by default; per `PLANVIEW_ID` when the project-scope toggle is on), and flags material buckets whose ratio exceeds it. The optional `detect_uniform_mapping` toggle additionally fails material buckets whose ratio is exactly 1 - surfaces suspiciously uniform 1:1 mappings (OR'd with the percentile branch). Rows whose WBC does not resolve to a valid ISO mapping are PASS - A1 already covers that completeness gap. |
| **A4** (ADR) - Core quantities populated & non-negative project totals | Completeness & Validity | No | `PLANVIEW_ID`, `ITEM_TYPE`, `ITEM_DESCRIPTION`, `QTY_QUANTITY`, `QTY_UOM` | - | Project-level rule with row-level verdict. For each `PLANVIEW_ID` the rule detects which of seven core quantity types (piping LF, concrete CY, steel tons, cable length, transmitter / instrument count, equipment count, module count) the project's scope implies, then checks that each one is populated by at least one positive-quantity row whose (`ITEM_TYPE`, `QTY_UOM`) classifies into that type. Project fails when any expected type lacks a populated row, **or** when the project's total `QTY_QUANTITY` sums to a negative value (individual negative rows are allowed - only the project aggregate is checked). Every row of a failing project inherits the FAIL. |
| **A5** (ADR) - Design details present when quantity exists | Consistency | No | `QTY_QUANTITY`, `DESIGN_PARAMETER_VALUE` | - | Items with a non-zero aggregated quantity (`SUM(ADR_FACT_ESTIMATEQTYRESULTS.QUANTITY) <> 0`) must carry at least one populated `DESIGN_PARAMETER_VALUE` from `ADR_DIM_ESTIMATEDESIGNDETAILS`; items with no non-zero quantity are out of scope and pass. |
| **A6** (ADR) - Construction hours present when quantity exists | Consistency | No | `QTY_QUANTITY`, `COST_TOTAL_HOURS`, `COST_DB_TOTAL_HOURS` | - | Items with a non-zero aggregated quantity must also have at least one of `SUM(ADR_FACT_ESTIMATECOSTRESULTS.TOTAL_HOURS)` or `SUM(ADR_FACT_ESTIMATECOSTRESULTS.DB_TOTAL_HOURS)` strictly greater than zero - productivity (hours / unit) cannot be derived otherwise. One-directional: hours-without-quantity passes, only quantity-without-hours fails. |
| **A7** (ADR) - Within-discipline quantity / hour ratio outlier | Statistical Outlier | No | `ITEM_TYPE`, `QTY_QUANTITY`, `QTY_UOM`, `COST_TOTAL_HOURS` (+ `PLANVIEW_ID` when `segment_by_project_type` is on) | `VWS_GP_STANDARD_SHARE` (only when `segment_by_project_type` is on - `PLANVIEW_ID → PROJECT_ID`, lookup `E05_DEPARTMENT` + `BUSINESS`) | Computes per-row `HOURS_PER_QUANTITY = COST_TOTAL_HOURS / QTY_QUANTITY` for items with both > 0, partitions by `(ITEM_TYPE, QTY_UOM)` (default) or by `(ITEM_TYPE, QTY_UOM, E05_DEPARTMENT, BUSINESS)` when the `segment_by_project_type` toggle is on, derives IQR thresholds (`Q1 - k·IQR` … `Q3 + k·IQR`, with `k` selectable on the rule card - **1.5× mild default**, 2.0×, or 3.0× extreme) per segment, and flags rows whose ratio is outside the segment range. Segments below the minimum population (default 10) or with `IQR == 0`, rows that lack a calculable ratio, and (in segmented mode) rows whose project-type cannot be resolved via the Planview reference are NOT_APPLICABLE and pass. |
| **A8** (ADR) - Cross-discipline quantity ratios | Statistical Outlier | No | `ITEM_TYPE`, `ROOT_ITEM_NAME`, `QTY_QUANTITY`, `QTY_UOM` (+ `PLANVIEW_ID` when `segment_by_project_type` is on) | `VWS_GP_STANDARD_SHARE` (only when `segment_by_project_type` is on - `PLANVIEW_ID → PROJECT_ID`, lookup `E05_DEPARTMENT` + `BUSINESS`) | Classifies eligible quantities into discipline categories (PIPE_LENGTH, EQUIPMENT_COUNT, CABLE_LENGTH, TRANSMITTER_COUNT, STEEL_WEIGHT, CONCRETE_VOLUME) using `ITEM_TYPE` + `QTY_UOM`, aggregates per `ROOT_ITEM_NAME`, and computes cross-discipline ratios (pipe/equipment, cable/transmitter, steel/concrete). For each ratio, projects whose value falls outside the population IQR bounds (multiplier `k` selectable on the rule card - **1.5× mild default**, 2.0×, or 3.0× extreme) are flagged; every row of a flagged project inherits the FAIL. When the `segment_by_project_type` toggle is on the per-ratio IQR is recomputed **within each (E05_DEPARTMENT, BUSINESS) segment** resolved via the Planview reference (the per-segment population floor still applies). Ratios with population below 10 (per segment in segmented mode) or `IQR == 0`, rows without a project / classifiable category, and (in segmented mode) projects whose project-type cannot be resolved are NOT_APPLICABLE and pass. |
| **AC1** (ACCE) - ISO Code of Account present (COR + SAB) | Completeness | Yes | `PLANVIEW_ID`, `COA` | `ACCE_COA_MASTER` (`COA[:3] → ICARUS_COA`; lookup `ISO_COR` and `SAB`) | Mirrors ADR A1 against the ACCE schema. ACCE source data carries 4-character `COA` codes (e.g. `3131`) whose **leading 3 characters** are the ICARUS_COA group (`313`), the analog of ADR's `SPLIT_PART(COMPLETE_WBC, '.', 1)` derivation. Validity rejects null / blank / `ERROR` / `N/A` markers; best-available mapping prefers valid over invalid rows when the master carries duplicates. Without `COR` / `SAB`, ACCE cost data cannot be normalized via EMMA - blocking gap. |
| **AC2** (ACCE) - Location + estimate date present & valid | Completeness & Validity | No | `JOB_NO`, `PLANVIEW_ID` | `VWS_GP_STANDARD_SHARE` (ACCE.PLANVIEW_ID → VWS_GP_STANDARD_SHARE.PROJECT_ID, lookup `COUNTRY`) | Mirrors ADR A2 against the ACCE schema. ACCE uses `JOB_NO` (the estimate job / period - `2Q23 RP1`, `2Q24`, `2Q25`, `4Q23`, …) as the estimate-basis-date proxy in place of ADR's `COST_UPDATE`. Row passes when `JOB_NO` is filled, matches the fiscal quarter-year token `[1-4]Q<YY>` with an optional revision suffix (structural check, so new quarters/years pass automatically; malformed values fail), AND `PLANVIEW_ID` resolves to a project whose `COUNTRY` is populated in the Planview reference. |
| **AC3** (ACCE) - Statistical COA-to-ISO mapping ratio | Statistical Outlier | No | `PLANVIEW_ID`, `COA`, `COST_MH`, `COST_TOTAL_COST` | `ACCE_COA_MASTER` (`COA[:3] → ICARUS_COA`; resolves `ISO_COR` and `SAB`) | Mirrors ADR A3 against the ACCE schema. Resolves `(ISO_COR, SAB)` by joining the first three characters of the 4-character `COA` to `ICARUS_COA` (the analog of A3's `SPLIT_PART` derivation), then computes `COA_TO_ISO_RATIO = COUNT(DISTINCT COA)` per bucket over the **full** 4-character `COA` value (not the truncated lookup key - so multiple distinct codes sharing a prefix contribute to the ratio individually). Materiality (`SUM(COST_MH) > 0` OR `SUM(COST_TOTAL_COST) ≥ 100k USD` - ACCE's construction-hours column is `COST_MH`, sourced from `MH` on `ACCE_ESTIMATECOSTRESULTS`; ADR's analog is `COST_TOTAL_HOURS`), the percentile baseline (P75 / **P90 default** / P95 / P99, selectable on the rule card), and the min-population floor (default 10) mirror A3. Unlike A3, **no project-scope toggle**: the baseline is always portfolio-wide. The optional `detect_uniform_mapping` toggle additionally fails material 1:1 buckets when ≥ 80 % of eligible mappings are 1:1 (portfolio-wide gate; wider than A3's per-bucket trigger because ACCE COA granularity is capped at ten 4-character codes per 3-character group). Rows whose COA prefix doesn't resolve to a valid ISO mapping are PASS - AC1 already covers that gap. |
| **AC4** (ACCE) - Core quantities populated & non-negative project totals | Completeness & Validity | No | `PLANVIEW_ID`, `DESCRIPTION`, `QTY_KEY_QTY`, `QTY_OTHER_QTY`, `QTY_KEY_UNITS`, `QTY_OTHER_UNITS` | - | Project-level rule with row-level verdict; mirrors ADR A4 against the ACCE schema. The classifier swaps ADR's `ITEM_TYPE` substring sweep for explicit **`DESCRIPTION` value lists** matched on `UPPER(TRIM(DESCRIPTION))` (e.g. `PIPING` / `CS PIPE ERECTION` for piping, `CENTRIFUGAL PUMPS` / `S&T EXCHANGER` for equipment); `MODULE_COUNT` keeps a `MODULE` / `MODULAR` substring match. Both the scope and population sides use the same `DESCRIPTION` lists. Quantities come from the **split** columns `QTY_KEY_QTY` / `QTY_OTHER_QTY` with units `QTY_KEY_UNITS` / `QTY_OTHER_UNITS`: a type is populated when **either** qty slot is > 0 **and** **either** unit is in the type's UOM set (compared on `UPPER(TRIM(units))`, no alias normalization). For each `PLANVIEW_ID` the rule determines which of seven core quantity types (piping LF, concrete CY, steel tons, cable length, transmitter / instrument count, equipment count, module count) the project's scope implies, then checks each is populated by at least one qualifying positive-quantity row. Project fails when any expected type lacks a populated row, **or** when the project's combined quantity total `SUM(QTY_KEY_QTY) + SUM(QTY_OTHER_QTY)` sums to a negative value (individual negative rows are allowed - only the project aggregate is checked). Every row of a failing project inherits the FAIL. Rows lacking `PLANVIEW_ID` pass - they can't be attached to a project group. |
| **AC5** (ACCE) - Design details present when quantity exists | Consistency | No | `QTY_KEY_QTY`, `QTY_OTHER_QTY`, `DESIGN_PROPERTY`, `DESIGN_VALUE` | - | Mirrors ADR A5 against the ACCE schema. A row fails only when the item has a strictly-positive aggregated quantity AND its design details are missing. Quantity is the per-`ROW_ID` aggregate of the split `QTY_KEY_QTY` / `QTY_OTHER_QTY` columns from `ACCE_ESTIMATEQTYRESULTS`; the design side requires **both** a named parameter `DESIGN_PROPERTY` and a `DESIGN_VALUE` (source `PROPERTY` / `VALUE` on `ACCE_ESTIMATEDESIGNDETAILS`, joined via `DESIGN_ID`, surfaced with the `DESIGN_` prefix) - the "120 m of what?" interpretability gate, stricter than A5 which checks only the value. The quantity gate is strictly positive: null, zero, **and negative** aggregates are out of scope and pass. |
| **AC6** (ACCE) - Construction hours present when quantity exists | Consistency | No | `QTY_KEY_QTY`, `QTY_OTHER_QTY`, `COST_MH` | - | Mirrors ADR A6 against the ACCE schema, with two structural differences: (1) the construction-hours column is `COST_MH` (sourced from `MH` on `ACCE_ESTIMATECOSTRESULTS`), not `COST_TOTAL_HOURS`, the ADR analog. (2) ACCE has no separate Design-Build hours column, so the check uses only `COST_MH` (equivalent to A6's `COST_TOTAL_HOURS > 0 OR COST_DB_TOTAL_HOURS > 0` when only one hours column exists). Quantity is the aggregated split `QTY_KEY_QTY` / `QTY_OTHER_QTY`; the hours comparison is strictly `> 0` - null is coerced to zero and negative aggregates do not count as hours present. One-directional: hours-without-quantity is PASS; only quantity-without-hours fails. Missing required column → all rows fail. |
| **AC7** (ACCE) - Within-discipline quantity / hour ratio outlier | Statistical Outlier | No | `DESCRIPTION`, `QTY_KEY_QTY`, `QTY_OTHER_QTY`, `QTY_KEY_UNITS`, `QTY_OTHER_UNITS`, `COST_MH` (+ `PLANVIEW_ID` when `segment_by_project_type` is on) | `VWS_GP_STANDARD_SHARE` (only when `segment_by_project_type` is on - `PLANVIEW_ID → PROJECT_ID`, lookup `E05_DEPARTMENT` + `BUSINESS`) | Mirrors ADR A7 against the ACCE schema with two structural differences: (1) the IQR segment key is `(DESCRIPTION, QTY_UOM)` - partitioning on the raw `UPPER(TRIM(DESCRIPTION))` estimate-line label paired with the effective UOM `COALESCE(KEY_UNITS, OTHER_UNITS)`, finer-grained (per-label) than ADR's discipline-level `ITEM_TYPE`. (2) construction hours come from `COST_MH` (sourced from `MH`), not `COST_TOTAL_HOURS`. Eligible rows compute `HOURS_PER_QUANTITY = COST_MH / <aggregated split quantity>`; per-segment IQR bounds (`Q1 - k·IQR` … `Q3 + k·IQR`, with `k` selectable on the rule card - **1.5× mild default**, 2.0×, or 3.0× extreme) flag outliers. When the `segment_by_project_type` toggle is on the IQR is recomputed within each `(DESCRIPTION, QTY_UOM, E05_DEPARTMENT, BUSINESS)` segment resolved via the Planview reference. Segments below the minimum population (default 10, per-segment in segmented mode) or with `IQR == 0`, rows that lack a calculable ratio or a blank `DESCRIPTION` / UOM, and (in segmented mode) rows whose project-type cannot be resolved are NOT_APPLICABLE and pass. |
| **AC8** (ACCE) - Cross-discipline quantity ratios | Statistical Outlier | No | `COMPONENT_SOURCE`, `DESCRIPTION`, `QTY_KEY_QTY`, `QTY_OTHER_QTY`, `QTY_KEY_UNITS`, `QTY_OTHER_UNITS` (+ `PLANVIEW_ID` when `segment_by_project_type` is on) | `VWS_GP_STANDARD_SHARE` (only when `segment_by_project_type` is on - `PLANVIEW_ID → PROJECT_ID`, lookup `E05_DEPARTMENT` + `BUSINESS`) | Mirrors ADR A8 against the ACCE schema with two structural differences: (1) the project / scope key is `COMPONENT_SOURCE` (not ADR's `ROOT_ITEM_NAME`). (2) the category classifier uses the same **`DESCRIPTION` value lists** AC4 uses, gated by a `QTY_KEY_UNITS` / `QTY_OTHER_UNITS` family match, instead of substring sweeps over `Estimate*` labels. (AC8's volume / equipment value sets differ slightly from AC4's - e.g. AC8 admits `YD` where AC4 admits `YDS`.) Classifies eligible quantities into six discipline categories, aggregates per `(COMPONENT_SOURCE, category)`, and computes three cross-discipline ratios (pipe/equipment, cable/transmitter, steel/concrete) - a ratio is calculable whenever the **denominator** is `> 0` (`NULLIF(den, 0)` semantics), so a project with `num = 0` contributes a valid `0` ratio to the population. Per-ratio IQR bounds (`k` selectable - **1.5× mild default**, 2.0×, or 3.0× extreme) flag projects whose value falls outside the band; every row of a flagged project inherits the FAIL. When the `segment_by_project_type` toggle is on the per-ratio IQR is recomputed within each `(E05_DEPARTMENT, BUSINESS)` segment resolved via the first non-blank `PLANVIEW_ID` seen per `COMPONENT_SOURCE` (per-segment population floor still applies). Ratios with population below 10 (per segment in segmented mode) or `IQR == 0`, rows without a project / classifiable category, and (in segmented mode) projects whose project-type cannot be resolved are NOT_APPLICABLE and pass. |

#### How E3 statistical-outlier validation works

`check_ept_e3` ([src/custom_dqr_engine.py](../src/custom_dqr_engine.py)) groups rows by ISO mapping (`CODE_OF_RESOURCE` + `STANDARD_ACTIVITY_BREAKDOWN`), computes per-group metrics - `ratio = COUNT(DISTINCT WBC_LEVEL_5)`, `hours_sum`, `cost_sum`, and derives a single `P90` threshold across all eligible mappings (`ratio >= 1`). A group fails when `ratio > P90` AND it is **material** (`hours_sum > 0` or `cost_sum >= EPT_E3_MATERIALITY_USD`, default 100k USD); every row inside a failing group inherits the FAIL.

Design notes:

- **Row-level verdict, group-level threshold.** Each row inherits its mapping's pass/fail so the rule plugs into the same per-row scoring pipeline as E1/E2/E4/E7, no special handling in `evaluate_custom_rules` or the dispatcher.
- **Distinct counting follows SQL semantics.** Null/blank `WBC_LEVEL_5` values do not contribute to the distinct count (mirrors `COUNT(DISTINCT col)`), so blank-WBC rows can't fabricate an outlier.
- **Missing ISO key passes E3.** Rows with null/blank `CODE_OF_RESOURCE` or `STANDARD_ACTIVITY_BREAKDOWN` are treated as PASS - E1 already flags those gaps, and E3 cannot meaningfully evaluate over-aggregation when there is no ISO bucket. This avoids double-penalising the same row.
- **Materiality filter prevents false positives.** Planning / structural-only mappings (zero hours and trivial cost) are exempt regardless of their ratio, per spec §11.
- **Scope toggle.** The rule card in Step 4.2 exposes a **"Compute percentile per project (PLANVIEW_ID)"** switch (`CustomRuleOption` with `key="project_scoped"`). Default is **off**: the global / dataset baseline. Turning it **on** flips `check_ept_e3` to group by `(PLANVIEW_ID, COR, SAB)` and recompute the percentile within each `PLANVIEW_ID` partition (`PARTITION BY PLANVIEW_ID`), so each project is judged against its own peers. The Step 4.2 card includes a *"How this option works"* expander that summarises both modes; it also adds `PLANVIEW_ID` to the rule's effective required columns when the toggle is on, so CDE-coverage validation catches missing project keys before the user can advance. Rows lacking `PLANVIEW_ID` in project mode are treated as PASS (E7 already covers the missing-project linkage).
- **Threshold picker.** The rule card also exposes a `threshold_percentile` selectbox (`CustomRuleSelectOption`). Default is **P90** (the rule's documented baseline); choices are P75 (lenient), **P90 (recommended)**, P95 (strict), P99 (very strict). `check_ept_e3` reads the picked value via `_coerce_threshold(params[…], EPT_E3_PERCENTILE)` and applies it whether the scope is global or per-project. Choosing a higher percentile raises the cutoff, so only the most extreme mappings fail; a lower percentile makes the rule more sensitive.
- **Uniform 1:1 detection toggle.** The rule card also exposes a **"Detect uniform 1:1 mappings"** switch (`CustomRuleOption` with `key="detect_uniform_mapping"`). Default is **off**. When **on**, after the percentile fail every *material* group whose `ratio == 1` (each ISO bucket holds exactly one distinct `WBC_LEVEL_5`) also fails - surfaces mappings that are suspiciously uniform (typically a sign that the mapping process was bypassed and source codes were copied 1:1 into the ISO bucket instead of being aggregated). The percentile and uniform-1:1 branches combine with **OR** so both signals coexist when enabled; the materiality filter still gates both so planning / structural-only buckets are not flagged. Off by default because a small / early dataset can legitimately show `ratio == 1` for every bucket. No additional CDEs are required.

#### How A3 statistical-outlier validation works

`check_adr_a3` ([src/custom_dqr_engine.py](../src/custom_dqr_engine.py)) mirrors `check_ept_e3` against the ADR data product: it resolves `(ISO_COR, SAB)` from each row's `COMPLETE_WBC` via the `ACCE_COA_MASTER` join (same lookup as A1), groups eligible rows by `(ISO_COR, SAB)`, computes `ratio = COUNT(DISTINCT COMPLETE_WBC)` per bucket along with `hours_sum` / `cost_sum`, and derives a single `P90` across all eligible mappings. A bucket fails when `ratio > P90` AND it is material (`hours_sum > 0` or `cost_sum >= ADR_A3_MATERIALITY_USD`, default 100k USD); every row in a failing bucket inherits the FAIL.

The two behavioural toggles surfaced on the E3 card are exposed identically on A3:

- **Scope toggle (`project_scoped`).** Default off. When on the group key becomes `(PLANVIEW_ID, ISO_COR, SAB)` and the P90 is recomputed within each `PLANVIEW_ID` partition. Rows lacking `PLANVIEW_ID` are treated as PASS (A2 covers the missing-project linkage). `PLANVIEW_ID` is already in A3's static required columns, so the CDE-coverage check enforces it regardless of the toggle.
- **Uniform 1:1 detection toggle (`detect_uniform_mapping`).** Default off. When on, every *material* bucket with `ratio == 1` also fails - OR'd with the percentile branch, materiality still gates both. Same semantics and rationale as E3.

Rows whose WBC does not resolve to a valid `ISO_COR` / `SAB` are PASS regardless of either toggle - A1 already covers that completeness gap. The eligible-mapping population floor (`ADR_A3_MIN_MAPPING_POPULATION`, default 10) applies to the total bucket count in both scope modes; below that the rule short-circuits to PASS.

#### Per-rule options (`CustomRuleOption` / `CustomRuleSelectOption`) and the dispatcher

The Custom DQR catalog supports two flavours of per-rule **options** in addition to the static metadata:

- **`CustomRuleOption(key, label, default, help, description, required_columns_when_enabled)`**: boolean toggle, rendered as `st.toggle`. Used by E3 and A3 for `project_scoped` (per-`PLANVIEW_ID` percentile baseline) and `detect_uniform_mapping` (uniform-1:1 mapping detection).
- **`CustomRuleSelectOption(key, label, choices, default, help, description)`**: single-choice picker, rendered as `st.selectbox`. `choices` is an ordered list of `(value, label)` pairs and the picked value is persisted as-is. Used by every statistical-outlier rule (E3, E6, A3, A7, A8) to expose a threshold picker (percentile for E3 / A3 with choices P75 / **P90 default** / P95 / P99; IQR multiplier for E6 / A7 / A8 with choices **1.5× default** / 2.0× / 3.0×).

Shared semantics:

- **Storage.** Each option's value lives at `CustomDQRAssignment.params[key]` and survives Step 4.2 re-renders, Step 5 weight edits, and the Step 6 evaluation pipeline.
- **Dispatch.** `evaluate_custom_rules` inspects each rule's `check` callable; when it declares a `params` argument (today: every outlier rule plus any future rule that opts in), the dispatcher passes `assignment.params` through. Checks that don't declare `params` are called with the legacy single-argument signature so existing rules keep working unchanged.
- **CDE-coverage validation.** `effective_required_columns(rule, params)` folds `required_columns_when_enabled` from each *enabled* toggle into the rule's static `required_columns`. Step 4.2 uses this composed map so flipping E3's project-scope toggle on immediately demands `PLANVIEW_ID` as a CDE. A3 already requires `PLANVIEW_ID` regardless of the toggle, so its project-scope flip has no extra coverage cost; the `detect_uniform_mapping` toggle on either rule contributes no extra columns. `select_options` do not contribute extra columns, they only customize numeric thresholds.
- **Robustness.** Outlier checks coerce the threshold via `_coerce_threshold(value, default)` ([src/custom_dqr_engine.py](../src/custom_dqr_engine.py)) - stale or malformed values (`None`, strings, negatives, zero) silently fall back to the catalog default rather than disabling the rule.

#### How E4 completeness validation works

`check_ept_e4` delegates to `validate_completeness_rule(df, ["WBC_LEVEL_1"])` ([src/custom_dqr_engine.py](../src/custom_dqr_engine.py)). A row passes when `WBC_LEVEL_1` is non-null AND non-blank (whitespace-only is treated as blank). When the column is missing the rule fails for every row, same semantics as the shelf Completeness dimension with `allow_empty_string=False`.

#### How E5 FEED / Engineering consistency validation works

`check_ept_e5` ([src/custom_dqr_engine.py](../src/custom_dqr_engine.py)) scopes evaluation to FEED / Engineering rows by case-insensitive regex match of `WBC_LEVEL_1` against `EPT_E5_FEED_ENGINEERING_PATTERN` (`\b(?:FEED|ENGINEERING)\b`, so `FEEDBACK` / `ENGINEERED` don't accidentally match). For in-scope rows it computes `cost_amount = COALESCE(TOTAL_COST_USD, TOTAL_COST_ESTIMATE_CURRENCY, 0)` and `hours_amount = COALESCE(TOTAL_HOURS, 0)`; the row passes when both are present (`> 0`) or both absent (`== 0`). Non-FEED rows are Not Applicable and always pass.

#### How E6 cost-to-hours ratio outlier validation works

`check_ept_e6` ([src/custom_dqr_engine.py](../src/custom_dqr_engine.py)) aggregates rows by `PLANVIEW_ID` to derive `cost_sum = SUM(cost_amount)` and `hours_sum = SUM(hours_amount)` per project (with the same `cost_amount` / `hours_amount` COALESCE used by E5). It then computes `cost_to_hours_ratio = cost_sum / hours_sum` for the **eligible-project population** (`hours_sum > 0`) and derives IQR thresholds from that distribution: `Q1 - 1.5*IQR` … `Q3 + 1.5*IQR`. A project FAILS when its ratio is below the lower bound or above the upper bound; every row in a flagged project inherits the FAIL.

Design notes:

- **Project-level ratio, row-level verdict.** Same row-inheritance pattern as E3: each row inherits its project's pass/fail so the rule plugs into the same per-row scoring pipeline as E1 / E2 / E4 / E5 / E7, no special handling in `evaluate_custom_rules`.
- **Cost fallback.** When `TOTAL_COST_USD` is null the row's contribution falls back to `TOTAL_COST_ESTIMATE_CURRENCY`; populated zeros in `TOTAL_COST_USD` win over the local-currency fallback (SQL COALESCE semantics).
- **Thresholds derived from the data.** No fixed cost-per-hour benchmark is hard-coded, the IQR multiplier is the only knob. `EPT_E6_MILD_IQR_MULTIPLIER` (1.5×, recommended default) and `EPT_E6_EXTREME_IQR_MULTIPLIER` (3.0×, lenient) are exposed as a selectbox on the Step 4.2 rule card (`threshold_iqr_multiplier`) and persisted to `CustomDQRAssignment.params`. `check_ept_e6` reads the chosen value via `_coerce_threshold(params[…], EPT_E6_MILD_IQR_MULTIPLIER)`.
- **Project-type segmentation toggle (`segment_by_project_type`).** When on, each `PLANVIEW_ID` is tagged with its `(E05_DEPARTMENT, BUSINESS)` segment from the `VWS_GP_STANDARD_SHARE` reference (`PLANVIEW_ID → PROJECT_ID`), the IQR thresholds are recomputed **within each segment**, and the per-segment minimum-population floor is applied so a thinly-populated bucket does not flag every project as an outlier of itself. Projects whose segment cannot be resolved (unmatched `PROJECT_ID`, or null/blank `E05_DEPARTMENT` / `BUSINESS`) are NOT_APPLICABLE → PASS - E7 / E2 already cover those gaps. The reference dataset must be available when the toggle is on; `check_ept_e6` raises `CustomRuleNotEvaluated` rather than silently falling back to the global IQR.
- **NOT_APPLICABLE → PASS.** The rule emits a Boolean per row; there is no separate NA bucket. Cases that the spec marks NOT_APPLICABLE are mapped to PASS to avoid double-counting against rules that already cover those gaps:
  - Project with `hours_sum <= 0`, the ratio cannot be calculated; E5 already flags FEED cost-without-hours.
  - Rows with null/blank `PLANVIEW_ID` - cannot be assigned to a project; E7 covers the missing-project linkage.
  - Eligible-project population below `EPT_E6_MIN_POPULATION` (default 5) - too small to define an outlier. In segmented mode the floor is applied per segment.
  - Project whose segment is unresolved (segmented mode only), see the segmentation bullet above.
- **Negative or zero costs are not exempt.** If a project's `cost_sum <= 0` while peers are positive, the resulting ratio naturally falls outside the lower IQR bound and the project is flagged for review (matches the spec recommendation in §14).
- **Schema-level missing column → all rows fail**, mirroring the convention used by E1 / E3 / E4 / E5.

#### How E7 referential integrity validation works

`check_ept_e7` resolves the `VWS_GP_STANDARD_SHARE` reference DataFrame via `src.reference_data.get_reference_dataset("VWS_GP_STANDARD_SHARE")`, then calls `validate_referential_integrity_rule(df, "PLANVIEW_ID", reference_df, "PROJECT_ID")`. A row passes when EPT's `PLANVIEW_ID` is non-blank AND its (string-stripped) value appears in the reference table's `PROJECT_ID` column.

The reference data registry lives in [src/reference_data.py](../src/reference_data.py). The `VWS_GP_STANDARD_SHARE` loader resolves to:

- **Mock mode**: `_mock_vws_gp_standard_share()` - returns the deterministic project pool keyed by `PROJECT_ID`.
- **Databricks mode**: `DatabricksClient.fetch_table("VWS_GP_STANDARD_SHARE")` - uses the same SQL Warehouse and Unity Catalog namespace configured for the EPT primary table.

#### Eager loading (Step 2) and caching

`prefetch_reference_datasets(names)` is called from Step 2 right after the source tables are built, with the names returned by `required_reference_datasets_for_systems(selected_systems)`. The fetched DataFrames (and any loader error strings) are cached in `st.session_state["_reference_datasets"]`. As a result:

- The Databricks round-trip happens **once**, alongside the system table fetches, not lazily during Step 6.
- Subsequent dashboard re-renders (including the implicit re-render that fires when the user clicks **Restart** in Step 6) hit the cache instead of reconnecting.
- Load errors are surfaced **immediately** in Step 2 as a yellow warning identifying the dataset and the underlying error message, so the user knows up-front which Custom rules will be marked Not evaluated in Step 6.

The cache is cleared automatically on the **Sample mode** toggle, on a change to the **Project filter** (domain-aware - `PLANVIEW_ID` for Cost Estimate, `PROJECT_CODE` for Quality, configured per `DomainDef.project_filter`), and on the **Restart** button (`clear_reference_cache()`); the next visit to Step 2 re-fetches.

When the loader returns `None` (connector missing, network failure, missing table) or raised an exception captured during prefetch, `check_ept_e7` raises `CustomRuleNotEvaluated` with the cached error appended to the message. The dispatcher records the reason in `ScorecardResult.not_evaluated_custom_rules`, omits the rule from the Boolean results (so it doesn't silently pass), and Step 6 renders a yellow "Not evaluated" warning in the Custom Rules tab.

#### CDE-coverage validation in Step 4.2

When the user ticks a Custom DQR card, [ui/step_04_2_custom_dqr.py](../ui/step_04_2_custom_dqr.py) compares the rule's `required_columns` (physical column names) against the CDEs already picked in Step 3 (`DataProductConfig.cdes`):

- **All required columns are CDEs** → the card surfaces a green `✅ All required CDEs selected` badge.
- **One or more required columns are missing** → the card surfaces a yellow `⚠ Missing required CDEs for this Custom DQR: <columns>` warning. The selection is **not auto-removed** (so the user keeps their pick and can fix the gap), but Step 4.2 disables the **Next** button and renders a top-level `st.error` summarizing every blocking gap across all data products.

The validation is metadata-driven: any rule with a non-empty `required_columns` map is validated automatically, no per-rule branching. A rule with no required columns (or a data product with no rules in the catalog) is trivially valid and never blocks. Validation re-runs on every Streamlit rerun, so adding or removing CDEs in Step 3, or unticking the affected Custom DQR - flips the status without leaving the step.

For example, ticking **E1** in EPT requires `CODE_OF_RESOURCE` and `STANDARD_ACTIVITY_BREAKDOWN` to be in `cfg.cdes`; ticking **E7** requires `PLANVIEW_ID`. If the user picks E1 + E4 but only `CODE_OF_RESOURCE` is a CDE, both `E1 → STANDARD_ACTIVITY_BREAKDOWN` and `E4 → WBC_LEVEL_1` appear in the blocking summary and Next stays disabled until either the missing CDEs are added in Step 3 or the offending rules are unticked.

> **✓ Select all Custom DQRs (per data product).** Each DP card in Step 4.2 exposes a one-click shortcut that ticks every Custom DQR available for that data product. The button is **not pre-applied**: assignments only change after the user clicks it, and persisted per-rule weights / option params (e.g. E3's / A3's project-scope and uniform-1:1 toggles, E1's stored weight from Step 5) are preserved across the bulk-select because each rule's session-state key is set independently and the dp-block writer continues to read `existing = {a.rule_id: a for a in cfg.custom_assignments}` on the same render. The shortcut is hidden for data products whose catalog entry is empty.

### 4.4c Standard DQR compatibility validation

Step 4.1 runs every selected dimension through a per-CDE compatibility check
before allowing the user to advance, so that Step 6 never crashes on a
configuration the engine cannot evaluate. The check lives in
[src/dqr_validation.py](../src/dqr_validation.py) and is consumed by both
the UI and the scoring pipeline.

> **💡 Suggestions are not pre-applied.** `suggest_assignments_for_cde(profile)` still drives the per-CDE recommendation, but Step 4.1 no longer seeds `cfg.assignments` with those suggestions on first render. Instead, every suggested dimension is rendered with a **💡 _suggested_** badge next to its expander label while the Apply checkbox stays off. Each DP card exposes a **💡 Apply all suggested DQRs (N)** shortcut that, on click, appends every still-pending suggestion (computed by `_pending_suggestions_for_dp`) to `cfg.assignments` and pre-sets each suggestion's Apply-checkbox key in `st.session_state` so the widgets honor the new state on the same render. The shortcut is idempotent - re-clicking after the user refines the selection only fills the gaps; manual edits and previously-applied suggestions survive. When every suggestion is already applied the button is replaced by a "every suggested DQR has already been applied" caption. The profile-aware params produced by the suggester (e.g. Accuracy's `min_value` / `max_value` pre-filled from the column profile) flow through to the appended assignment so the user gets sensible defaults without re-typing them.

- **Step 4.1 UI** ([ui/step_04_dqr_assignment.py](../ui/step_04_dqr_assignment.py))
  validates each enabled assignment against the CDE's `column_type_group`.
  Each dimension expander shows ✅ when compatible, ⚠ for non-blocking
  warnings, ❌ for blocking errors, alongside the **💡 _suggested_** badge
  when the dimension is one of `suggest_assignments_for_cde`'s recommendations
  for the CDE. Errors carry a short explanation and a
  suggestion (e.g. *"This configuration is not compatible. The selected CDE
  is a date/datetime column, but the comparison column is numeric. Please
  select a compatible date/datetime column or adjust the dimension
  configuration."*). Validation re-runs on every Streamlit rerun so changing
  the CDE, the dimension, the comparison column, the operator, the
  threshold/value, or any other parameter immediately flips the badge, and
  Next stays disabled until every DP is error-free.
- **Step 6 scoring** ([src/scorecard.py](../src/scorecard.py)) uses
  `evaluate_all_safe`, which pre-validates each rule and skips any whose
  configuration the validator flagged as incompatible. Skipped rules are
  recorded in `ScorecardResult.not_computed_standard_rules` (rule_id →
  reason) and contribute 0 to the standard subscore instead of crashing the
  dashboard. Even on the unhappy path the engine wraps each rule body in
  `try/except`, so a runtime error escaping a rule the validator missed is
  still recorded as Not computed (with the exception message) rather than
  bubbling up as a TypeError. Step 6's *Rules (pass rate)* tab adds a
  **Status** column ("Evaluated" / "Not computed") and renders a yellow
  warning per skipped rule.

The validator maps each dimension to a set of supported CDE column-type
groups, plus per-dimension parameter rules:

| Dimension | Supported CDE groups | Cross-parameter checks |
|-----------|----------------------|------------------------|
| Completeness | numeric, text, date/datetime, boolean | - |
| Uniqueness | numeric, text, date/datetime | - |
| Validity | numeric, text, date/datetime | regex/length warnings on numeric/date; min_length ≤ max_length |
| Accuracy | numeric | min_value ≤ max_value |
| Consistency | numeric, text, date/datetime, boolean | compare_column must exist, must differ from CDE, must share a category (numeric↔numeric, date↔date, text↔text, boolean↔boolean); ordering operators on boolean → warning |
| Timeliness | date/datetime | max_lag_days is a positive integer |
| Currency | date/datetime | max_age_days is a positive integer |
| Conformity | text, numeric, boolean | non-numeric allowed_values on a numeric CDE → warning |
| Integrity | text, numeric | non-numeric reference_values on a numeric CDE → warning |
| Precision | numeric | max_decimals ≥ 0 |

`DQRValidationReport.is_valid` is True when no error-severity issues are
present; warnings are informational and never block. Adding a new dimension
without registering it in `DIMENSION_SUPPORTED_GROUPS` is caught by
`tests/test_dqr_validation.py::test_every_dimension_has_a_compatibility_entry`.

### 4.5 The 10 DQ Dimensions

Defined in [config/dqr_catalog.py](../config/dqr_catalog.py); each dimension declares the column types it applies to and its default parameters.

| # | Dimension | What it checks | Example parameters |
|---|-----------|----------------|--------------------|
| 1 | **Completeness** | Non-null, non-empty values | `allow_empty_string` |
| 2 | **Uniqueness** | Each value appears at most once | _(none)_ |
| 3 | **Validity** | Format/regex, length bounds, type validity | `regex`, `min_length`, `max_length` |
| 4 | **Accuracy** | Value within expected range | `min_value`, `max_value` |
| 5 | **Consistency** | Cross-field logical validation | `compare_column`, `operator` |
| 6 | **Timeliness** | Recorded within SLA from today | `max_lag_days` |
| 7 | **Currency** | Data is recent | `max_age_days` |
| 8 | **Conformity** | Value in allowed domain/catalog | `allowed_values` |
| 9 | **Integrity** | Referential integrity (FK ∈ reference set) | `reference_values` |
| 10 | **Precision** | Numeric granularity (max decimal places) | `max_decimals` |

The helper `suggest_dimensions_for(profile)` heuristically recommends dimensions per column (e.g., `_ID` suffix → Uniqueness + Integrity; numeric → Accuracy + Precision).

### 4.6 Weights & Scoring

Scoring runs per source, then combines via the source-level weights set in Step 4:

- **Within Standard**: each `DQRAssignment` carries a weight in `[0, 100]` summing to 100. Weights are normalized to sum to `1.0` (or equal weights if all are zero), and the **standard row score** = `Σ(rule_pass[i] × w[i]) × 100`. In the Step 5 UI the inputs start blank, the user either fills them in directly (per-rule cap keeps Σ ≤ 100) or clicks **Distribute equally** to split 100% across the rules.
- **Within Custom**: each `CustomDQRAssignment` carries the analogous weight inside the Custom source. Same normalization, same per-row formula. The Step 5 UI mirrors the Standard section: inputs start blank, with a **Distribute equally** button for one-click 100% across the selected rules. (Earlier revisions auto-pinned the weights on first render, that behavior was removed for consistency with the Standard flow.)
- **Combined per-row score** = `(w_std/100) × standard_row_score + (w_cus/100) × custom_row_score` where `w_std`, `w_cus` are the Step-4 source-level weights. Single-source DPs pass through unchanged (the absent source contributes 0 with weight 0).
- **Overall score** = mean of combined per-row scores. By linearity of mean, this equals `(w_std × standard_overall + w_cus × custom_overall) / 100` - matching the user-facing example: `final = (Standard × 0.70) + (Custom × 0.30)`.
- **Per-rule pass rate** is reported per source: standard rules in `result.rule_pass_rates`, custom rules in `result.custom_rule_pass_rates`.
- **Per-CDE / per-dimension score** = simple (unweighted) mean of pass rates across every rule tied to the CDE / dimension, blended across both sources. Step 5 rule weights intentionally do not enter this mean - the breakdown is a data-health diagnostic, not a decomposition of the weighted score (the weight-aware view is ML Lab's 🎯 Rule Impact tab); a caption on both tabs states this to the user. Standard rules are matched via `DQRAssignment.cde_column` and `dimension`; Custom rules are matched via each rule's `required_columns` (every required column is treated as a CDE the rule contributes to) and `rule.type` (used as the dimension). When only Custom is selected the "By CDE" / "By Dimension" tabs stay populated instead of falling back to zeros. Rules in `not_computed_standard_rules` / `not_evaluated_custom_rules` are excluded from the mean so a partial failure doesn't drag the breakdown down with implicit zeros.
- **Drill-down to failing rows** (`ui/step_06/_drilldown.py`): every Step 6 breakdown is clickable. Clicking a bar on the "By CDE" / "By Dimension" charts (Plotly `on_select`), or selecting a row on the "Rules (pass rate)" / "Custom Rules" tables (`st.dataframe` single-row selection), renders the data rows that fail the clicked element - worst combined row score first, capped at the 200 worst (the CSV export carries the full list), enriched with the same per-rule 100/0 columns and reference-dataset columns as the Worst-rows tab. The rule set behind each bar mirrors the chart's own blending: Standard rules match via `cde_column` / `dimension`, Custom rules via their effective `required_columns` / `rule.type` - so a bar produced by Custom rules only (e.g. a One-click run) still drills down correctly. Elements whose rules were all "Not computed" / "Not evaluated" show the reason instead of an empty table.
- **Buckets** (configurable, default 80 / 60 / <60): `green` / `yellow` / `red`, applied to the combined per-row score.

**Edge cases**:
- Custom selected with zero rules → `custom_score = 0` (not vacuously 100), warned in Step 6.
- Required columns missing for a custom rule (e.g. EPT schema drift dropping `CODE_OF_RESOURCE`) → the rule fails for every row instead of raising, so the pipeline keeps producing a usable scorecard.
- Configs missing `dqr_sources` (legacy fixtures or pre-feature data) default to `["standard"]` with weight 100, the prior behavior is preserved byte-for-byte.

### 4.7 Application modes: One-click vs Step-by-step

The app's entry step (`mode_selection`) stores the chosen mode in
`session_state.app_mode` and decides which steps are visible from then on
(`STEP_VISIBILITY_PREDICATES` in `utils/session/navigation.py`). **Restart**
clears `app_mode` and returns here. The mode is set by `set_app_mode`
(idempotent; switching modes wipes the downstream workflow artefacts so a
half-built flow never leaks across).

**⚡ One-click mode** (`one_click` step + `src/one_click.py`) takes only a
**domain** + **systems** and, on **Generate**, runs the whole Step-by-step pipeline
with a fixed default configuration:

| Aspect | One-click behaviour |
|--------|---------------------|
| DQR sources | **Custom only**, at 100% (`source_weights = {"custom": 100}`); no Standard rules |
| Rules | **Every** Custom DQR for each system, each with its **default** options/parameters (`default_rule_params` = an untouched Step 4.2 params dict) |
| CDEs | **Only the required ones** - the union of the rules' `effective_required_columns`, in Data-Product column order |
| Weights | **Distributed equally** within the Custom source via `distribute_equally` (Σ = 100) |
| Scorecards | Computed with `compute_scorecard` - identical to an equivalent hand-built Step-by-step config |
| CSV/JSON | The dashboard's existing per-Data-Product download buttons; One-click validates CSV generation up-front |
| Result | Lands on the dashboard with a one-time summary banner (`one_click_summary`) |

Because `build_one_click_config` reuses the same `effective_required_columns`
+ `distribute_equally` the manual steps use, and `default_rule_params`
reproduces an untouched Step 4.2, **a One-click config equals a Step-by-step config
the user never edited** - the two flows can never drift in how they score.

**Validations / edge cases** (surfaced, never crashing): no domain or no
system → Generate disabled; a selected system with no custom rules →
warned and skipped (blocking only when *no* selected system has rules); a
rule's required column absent from the Data Product → warning, the rule is
"Not evaluated" downstream; project filter matching 0 rows for a system →
that system skipped; a scorecard or CSV-export failure for a system →
recorded (the run continues for the others; nothing-scored keeps the user
on the step).

**Assumptions / limitations.** One-click is intentionally **custom-only** -
no Standard DQRs, no rule options, no manual re-weighting. For any of those,
use **🛠️ Step-by-step mode**, which is the unchanged historical workflow (Steps 0-6
+ ML Lab) with full control over every source, CDE, option and weight.
Both modes honour the sidebar **Sample mode** and **Project filter**.

---

## 5. Module Reference

### 5.1 Configuration (`config/`)

| File | Responsibility |
|------|----------------|
| [config/settings.py](../config/settings.py) | Immutable `Settings` dataclass: data source, Unity Catalog location (`DATABRICKS_CATALOG` / `DATABRICKS_SCHEMA`), SQL Warehouse (`DATABRICKS_WAREHOUSE_ID` / `DATABRICKS_SQL_HTTP_PATH`), score thresholds, max rows per table. Loads `.env` for **local dev** (import is optional — inside Databricks Apps configuration arrives as real env vars from `app.yaml` plus the platform-injected identity, so there is no `.env`) |
| [config/systems.py](../config/systems.py) | `SystemDef` / `TableDef` definitions for ADR, ACCE, EPT |
| [config/dqr_catalog.py](../config/dqr_catalog.py) | Catalog of the 10 standard dimensions + `suggest_dimensions_for()` heuristic |
| [config/dqr_sources.py](../config/dqr_sources.py) | `SOURCE_STANDARD`, `SOURCE_CUSTOM`, `SOURCE_LABELS` |
| [config/custom_dqr_catalog.py](../config/custom_dqr_catalog.py) | `CustomRuleDef` + `CUSTOM_DQR_RULES` per data product + `get_available_custom_dqr_rules()`. SLIM re-export; the per-system rule lists live in [config/custom_dqr/](../config/custom_dqr/) (`_ept_catalog.py` / `_adr_catalog.py` / `_acce_catalog.py`) and the dataclasses + option builders in `_shared.py`. |

### 5.2 Core Logic (`src/`)

| File | Responsibility |
|------|----------------|
| [src/models.py](../src/models.py) | Dataclasses: `ColumnProfile`, `DataProduct`, `DQRAssignment`, `CustomDQRAssignment`, `DataProductConfig` (with `dqr_sources` / `source_weights` / `custom_assignments`), `ScorecardResult` (with `standard_score` / `custom_score` / `source_weights` / `custom_rule_pass_rates`) |
| [src/profiler.py](../src/profiler.py) | `classify_column`, `profile_column`, `profile_dataframe`, `profiles_to_table` |
| [src/dqr_engine.py](../src/dqr_engine.py) | 10 standard rule implementations + `evaluate_rule`, `evaluate_all`, `evaluate_all_safe` (defensive variant used by the scorecard), `suggest_assignments_for_cde` |
| [src/dqr_validation.py](../src/dqr_validation.py) | Standard-DQR compatibility layer: `DIMENSION_SUPPORTED_GROUPS`, `validate_assignment`, `validate_assignments_for_dp`, `DQRValidationReport` / `DQRValidationIssue` |
| [src/custom_dqr_engine.py](../src/custom_dqr_engine.py) | Custom rule check functions (E1-E7, A1-A8, AC1-AC8) + reusable validators (`validate_completeness_rule`, `validate_referential_integrity_rule`) + `evaluate_custom_rules` dispatcher + `_check_supports_params` introspection + `CustomRuleNotEvaluated` exception + per-rule `TypedDict` params (`EPTE3Params`, `EPTE6Params`, `ADRA3Params`, `ADRA7Params`, `ADRA8Params`, `ACCEAC3Params`, `ACCEAC7Params`, `ACCEAC8Params`). SLIM re-export; implementations live in [src/custom_dqr/](../src/custom_dqr/): `_shared.py` (errors + helpers), `_validators.py`, `_ept_rules.py` (E1-E7), `_adr_rules.py` (A1-A8), `_acce_rules.py` (AC1-AC8), `_dispatcher.py`. |
| [src/reference_data.py](../src/reference_data.py) | Reference dataset registry - `get_reference_dataset`, `prefetch_reference_datasets` (eager-loaded in Step 2), `get_reference_dataset_error`, `clear_reference_cache`, `required_reference_datasets_for_systems` |
| [src/data_product_builder.py](../src/data_product_builder.py) | Joins source tables into a `DataProduct`; pluggable fetcher (mock vs. Databricks) |
| [src/scorecard.py](../src/scorecard.py) | `compute_scorecard`: per-source row scoring, source-weighted combination, threshold bucketing |
| [src/one_click.py](../src/one_click.py) | ⚡ **One-click automation service** (UI-free). `run_one_click(domain, systems, …)` builds + profiles each Data Product, prefetches reference datasets, applies the default custom-only config and computes scorecards; `build_one_click_config` derives the required CDEs and equal weights; `default_rule_params` reproduces an untouched Step 4.2 params dict. Returns an `OneClickResult` (scored products + skipped reasons + warnings); raises `OneClickError` for blocking input/build failures. Reuses `build_multiple` / `profile_dataframe` / `prefetch_reference_datasets` / `compute_scorecard` / `effective_required_columns` / `distribute_equally`. |
| [src/ml_lab.py](../src/ml_lab.py) | 🧪 **ML Lab algorithms** (Step 7, beta). Public functions: `build_rule_flag_matrix`, `compute_row_anomalies`, `compute_rule_impact`, `compute_cde_profile_clusters`, `simulate_weight_perturbation`, `compare_data_products`, `snapshot_scorecard`, `load_snapshot_from_json`, `load_snapshot_from_csv`, `compute_drift` (PSI + KS), `train_risk_classifier`, `recommend_dqrs_for_cde`, `explain_row_score`, `sklearn_status`. Pure numpy/pandas with **optional** sklearn swap-ins (IsolationForest, KMeans, PCA, LogisticRegression) detected lazily. Read-only - never mutates the main flow's state. See [ML_LAB.md](ML_LAB.md). |
| [src/mock_data.py](../src/mock_data.py) | Deterministic synthetic data generator with injected defects (incl. `CODE_OF_RESOURCE` / `STANDARD_ACTIVITY_BREAKDOWN` for EPT, plus `WBC_LEVEL_5` / `TOTAL_HOURS` / `TOTAL_COST_USD` exercising the E3 statistical outlier detector) |
| [src/databricks_client.py](../src/databricks_client.py) | `DatabricksClient` data layer over a **Databricks SQL Warehouse** (`databricks-sql-connector`). Auth is headless via `databricks.sdk.core.Config` - the app service principal's OAuth env vars inside Databricks Apps, `DATABRICKS_HOST` + `DATABRICKS_TOKEN` from `.env` locally; no browser auth path. Callers keep building `%s` placeholders; the client translates them to named parameters (`:p0`, `:p1`, …) bound server-side. `fetch_table` uses the Arrow path (`fetchall_arrow`), `fetch_query` uses `fetchall`; column names are normalized to UPPERCASE. A shared client (`get_shared_client` / `close_shared_client`) reuses one connection per Streamlit run. `execute()` is the persistence layer's write path (INSERT into the DQS_* app-state tables); data reads stay on the fetch methods. |
| [src/run_history.py](../src/run_history.py) | **Run-history service** (phase 1). `config_fingerprint` (stable hash of CDEs/rules/params/weights/sources; assignment order-insensitive) and `result_fingerprint` (hash of the scoring outcome) drive dedup; `record_run_if_new` persists an ML-Lab-compatible snapshot (`snapshot_scorecard`) via `save_run` unless both fingerprints match the last persisted run; `load_history` returns runs (with who/when/config_hash); `score_drop` compares the two most recent runs and flags whether the config changed alongside the score. |
| [src/telemetry.py](../src/telemetry.py) | **Adoption & audit metrics** (phase 2) - UI-free aggregations over persisted events/runs/project versions for the 📊 Adoption page: `adoption_overview` (headline counters + last activity), `runs_per_week` (ISO-week trend), `runs_by_system` (adoption per domain/DP), `user_activity` (per-user rollup + last seen), `recent_activity` (unified audit trail, newest first, capped). Nothing here writes. |
| [src/projects.py](../src/projects.py) | **Saved projects** (phase 3). `serialize_project` / `deserialize_project` round-trip the full configuration (domain, systems, CDEs, rules, params, weights - never the data); `change_summary` produces the human-readable "what changed" line (systems/CDEs/rules added-removed, weight/param changes, source changes; name lists > 3 collapse to counts); `save_project` appends an immutable version (v1 = "Project created.") and logs a `project_saved` event; `list_projects` / `get_project` back the browser. Version list = audit changelog. |
| [src/persistence.py](../src/persistence.py) | **Persistence layer** (F0 foundation for run history, adoption/audit telemetry and saved projects). `current_username()` (the viewer identity forwarded by Databricks Apps via HTTP headers / OS login locally, cached); three backends selected by `DQS_PERSISTENCE` - `LocalStore` (JSON-lines under `.dqs_store/`, default), `DatabricksStore` (append-only `DQS_RUNS`/`DQS_EVENTS`/`DQS_PROJECTS` tables, [deploy/databricks/02_persistence_tables.sql](../deploy/databricks/02_persistence_tables.sql)), `NullStore` (`off`). Domain API: `save_run`/`list_runs`, `log_event`/`list_events`, `save_project_version`/`list_project_versions` (append-only versions = audit changelog). Every write stamps `ts` + `username`; every function is fire-and-forget (storage failures log + degrade, never raise). |

### 5.3 UI Steps (`ui/`)

| Step | File | Purpose |
|------|------|---------|
| Entry | [ui/step_mode_selection.py](../ui/step_mode_selection.py) | **Mode picker** - choose ⚡ One-click or 🛠️ Step-by-step; sets `app_mode` and routes onward. Once at least one project exists, an **📂 Open a saved project** section lists projects (with per-version audit changelog); opening one rebuilds the data products fresh, applies the saved configuration, logs a `project_loaded` event and lands on the dashboard in Step-by-step mode |
| One-click | [ui/step_one_click.py](../ui/step_one_click.py) | ⚡ **One-click** - pick a domain + systems, then **Generate** runs [src/one_click.py](../src/one_click.py) and lands on the dashboard. Validates: no domain / no system / no applicable custom rules / nothing scored / CSV failure |
| 0 | [ui/step_00_domain_selection.py](../ui/step_00_domain_selection.py) | Pick the data domain (Step-by-step) |
| 1 | [ui/step_01_system_selection.py](../ui/step_01_system_selection.py) | Pick which systems to analyze |
| 2 | [ui/step_02_data_product_review.py](../ui/step_02_data_product_review.py) | Build & review each Data Product (profiles, samples) |
| 3 | [ui/step_03_cde_selection.py](../ui/step_03_cde_selection.py) | Pick CDEs via the **Pick as CDE** checkbox column in a profile grid; selected columns appear as hover-tooltip badges above the grid |
| 4 | [ui/step_04_dqr_source_selection.py](../ui/step_04_dqr_source_selection.py) | Pick Standard / Custom / both per DP; split source-level weight |
| 4.1 | [ui/step_04_dqr_assignment.py](../ui/step_04_dqr_assignment.py) | Assign standard dimensions + edit parameters per CDE (only DPs with `standard`); per-rule compatibility validation drives ✅/⚠/❌ badges and gates **Next** until every error is resolved |
| 4.2 | [ui/step_04_2_custom_dqr.py](../ui/step_04_2_custom_dqr.py) | Pick custom rules from the per-DP catalog (only DPs with `custom`) |
| 5 | [ui/step_05_weight_assignment.py](../ui/step_05_weight_assignment.py) | Distribute 100 points across rules in each active source |
| 6 | [ui/step_06_dashboard.py](../ui/step_06_dashboard.py) | Scorecard dashboard (standard + custom subscores, custom rules tab) + CSV / JSON export. Clicking a By-CDE / By-Dimension bar or selecting a Rules / Custom Rules table row drills down to the failing data rows ([ui/step_06/_drilldown.py](../ui/step_06/_drilldown.py)). Every computed scorecard is auto-persisted (deduplicated) and surfaced on a per-DP **History** tab - score trend (◆ = config change), run log (who/when/config), "what changed" drift vs the previous run - plus a drop-alert banner when the score fell ≥ `DQS_DROP_ALERT_PP` (default 5 pp) ([ui/step_06/_history.py](../ui/step_06/_history.py)). A **💾 Save as project** panel captures the whole configuration as a new immutable version with an audit changelog ([ui/step_06/_projects.py](../ui/step_06/_projects.py)), and a **📑 Executive report (HTML)** button downloads a fully self-contained report with every dashboard view (HTML/CSS bars + inline-SVG trend, `@media print` stylesheet → Ctrl+P for a shareable PDF) ([ui/step_06/_exec_report.py](../ui/step_06/_exec_report.py)). Nav row exposes a **🧪 ML Lab (beta)** button that opens Step 7. |
| 7 | [ui/step_07_ml_lab.py](../ui/step_07_ml_lab.py) | 🧪 **ML Lab (beta)** orchestrator + tab dispatcher: wires the 9 read-only analytics tabs into `st.tabs(...)`. Each tab is its own module in [ui/step_07/](../ui/step_07/): 🔎 `_row_anomalies.py` · 🎯 `_rule_impact.py` · 🌿 `_cde_clusters.py` · ⚖️ `_weight_sensitivity.py` · 🔭 `_cross_dp.py` · 📜 `_run_history.py` · 🧠 `_risk_model.py` · 💡 `_recommendations.py` · 🧩 `_row_explain.py` (shared CSS + helpers in `_shared.py`). Violet/lavender BETA theme + 🔬 *Use scikit-learn* toggle. See [ML_LAB.md](ML_LAB.md). |
| Admin | [ui/step_adoption.py](../ui/step_adoption.py) | 📊 **Adoption & audit** - standalone admin page reached from the entry screen ("📊 Usage & audit" button; visible in the stepper only while inside). Headline counters (unique users, app opens, runs, exports, project saves/loads), runs-per-week trend, adoption by domain/system, per-user activity and the unified audit trail - all computed by [src/telemetry.py](../src/telemetry.py) from persisted events/runs/versions. Authorization stays with Databricks app permissions + Unity Catalog grants; this page only measures what authorized users did. |

### 5.4 Utilities (`utils/`)

| File | Responsibility |
|------|----------------|
| [utils/session_state.py](../utils/session_state.py) | SLIM re-export. Public surface: `init_state`, `set_domain`, `set_app_mode` + `APP_MODE_*` constants, navigation (`goto`, `next_step`, `prev_step`), `restart_app` (returns to the mode picker), `consume_scroll_to_top`, progress sidebar, sample-mode toggle, project filter, `_ml_lab_visible` / `_mode_is_step_by_step` / `_mode_is_one_click` predicates. Implementations partitioned by concern in [utils/session/](../utils/session/): `state.py` (STEPS + init + domain + `app_mode`), `navigation.py` (next / prev / restart + `app_mode`-aware visibility), `sidebar.py` (CSS + brand + filters). |
| [utils/ui_components.py](../utils/ui_components.py) | `render_nav_footer` - the shared Back / Restart / centre-message / Next row used by Steps 02-05 + 04.2. Callbacks (`on_back`, `on_next`, `on_restart`) are passed in so per-step tests that patch `prev_step` / `next_step` / `restart_app` on their module still intercept clicks. |
| [utils/helpers.py](../utils/helpers.py) | `score_color`, `score_label`, `distribute_equally`, `format_value`, `section_header` |
| [utils/telemetry.py](../utils/telemetry.py) | Session-side telemetry wiring called by `app.py` on every render: `log_app_open_once` (one `app_open` event per browser session) and `log_step_view` (one `step_view` event per step *transition*, with mode + domain). Session-state guards make both no-ops on reruns; writes go through the fire-and-forget persistence layer. |

---

## 6. Configuration

Copy [.env.example](../.env.example) to `.env` and edit:

```bash
# Data source
DATA_SOURCE=mock                # or "databricks"

# Databricks (only when DATA_SOURCE=databricks; local dev only -
# Databricks Apps injects host + service-principal credentials)
DATABRICKS_HOST=...
DATABRICKS_TOKEN=...
DATABRICKS_WAREHOUSE_ID=...     # or DATABRICKS_SQL_HTTP_PATH=...
# DATABRICKS_CATALOG=entai_sandbox_catalog
# DATABRICKS_SCHEMA=data_quality_scorecards

# Score thresholds (0–100)
THRESHOLD_GREEN=80
THRESHOLD_YELLOW=60

# Sampling
MAX_ROWS_PER_TABLE=50000
```

A **Sample Mode** sidebar toggle caps each table to `MAX_ROWS_PER_TABLE`; toggling invalidates cached data products, configs, and scorecards.

A **Project filter** sidebar input (`render_planview_filter`) accepts one or more project identifiers (separated by commas, spaces or newlines) and restricts the entire workflow to those projects. The filter is **domain-aware**: each `DomainDef` declares its `ProjectFilterDef` (Cost Estimate → `PLANVIEW_ID`, Quality → `PROJECT_CODE`), and the widget label / placeholder / help / target column come from the active domain. The widget is **hidden entirely until Step 0 has set a domain** (no filter column is meaningful without an active domain). The filter is applied inside `build_data_product` against each system's primary table on the domain's configured column - child tables join on `ROW_ID` (Cost Estimate) so they inherit the restriction transparently; the Quality domain's single SQS table is filtered directly. Changing the filter invalidates the same caches as the Sample-mode toggle (`data_products`, `configs`, `scorecards`, and the reference-dataset cache) so Step 2 rebuilds with the new scope on the next render. An empty input means "all projects" (no filter).

---

## 7. Running the App

```bash
# 1. Install
make install

# 2. Configure
cp .env.example .env
# edit .env (defaults are fine for mock mode)

# 3. Launch
make run
# opens http://localhost:8501
```

Walk the eight steps top-to-bottom (Step 0 domain pick → Steps 1-6 → optional Step 7 ML Lab); each step writes to `st.session_state` and the sidebar shows progress.

---

## 8. Testing

```bash
make test
# or with coverage:
DATA_SOURCE=mock pytest --cov=app --cov=src --cov=config --cov=utils --cov=ui --cov-report=term

# lint (matches CI):
ruff check .
```

The autouse `_force_mock_data_source` fixture in
[tests/conftest.py](../tests/conftest.py) pins `SETTINGS.data_source =
"mock"` regardless of the shell `DATA_SOURCE`, so no test ever hits
Databricks. CI ([.github/workflows/tests.yml](../.github/workflows/tests.yml))
runs `ruff check` first, then `pytest -q` with coverage.

| Test module | Covers |
|-------------|--------|
| [tests/test_profiler.py](../tests/test_profiler.py) | Column classification & profiling |
| [tests/test_dqr_engine.py](../tests/test_dqr_engine.py) | Core rule evaluation |
| [tests/test_dqr_engine_extra.py](../tests/test_dqr_engine_extra.py) | Edge cases for all 10 dimensions |
| [tests/test_dqr_validation.py](../tests/test_dqr_validation.py) | Per-dimension compatibility validation: numeric vs. datetime CDE × dimension/parameter combinations, dynamic re-validation when CDE / dimension / compare_column / operator change |
| [tests/test_scorecard.py](../tests/test_scorecard.py) | Weight normalization & scoring |
| [tests/test_data_product_builder.py](../tests/test_data_product_builder.py) | Joins, prefixing, 1:N aggregation |
| [tests/test_helpers.py](../tests/test_helpers.py) | Color / label / weight utilities |
| [tests/test_session_state.py](../tests/test_session_state.py) | Navigation & sample toggle |
| [tests/test_databricks_client.py](../tests/test_databricks_client.py) | Databricks client (mocked) |
| [tests/test_persistence.py](../tests/test_persistence.py) | Persistence layer: identity resolution (forwarded Databricks Apps headers / OS fallback / cache), Local/Databricks/Null backends, backend selection via `DQS_PERSISTENCE`, fire-and-forget degradation, project-version increments, `DatabricksClient.execute` bind paths |
| [tests/test_run_history.py](../tests/test_run_history.py) | Run-history service + Step 6 history UI: fingerprint stability/sensitivity, record dedup (rerun vs data change vs config change), `score_drop` deltas + config-change flag, session-cached recording, drop-alert thresholds, History-tab trend/log/drift rendering, ML Lab persisted-snapshot merge |
| [tests/test_projects.py](../tests/test_projects.py) | Saved projects: serialization round-trip, change-summary cases (rules/CDEs/systems added-removed, weights/params, sources, domain, name-list capping), versioned saves + changelog + telemetry events, browser listing/opening, loader (rebuild, prefetch, corrupt record, unknown domain, build failure) |
| [tests/test_telemetry.py](../tests/test_telemetry.py) | Adoption/audit: overview counters, ISO-week run trend (incl. unparsable timestamps), per-system/per-user rollups, unified audit trail (merging, detail formats, limit), session-once `app_open` / transition-only `step_view` logging, Adoption page rendering (empty + populated + back nav) |
| [tests/test_exec_report.py](../tests/test_exec_report.py) | Executive HTML report: every dashboard view present + self-contained (no external URLs), HTML-escaping of data values, worst-row column capping, trend block gating (≥ 2 persisted runs; SVG + delta + config-change note), Not computed / Not evaluated / empty states, download wiring + `export` telemetry event |
| [tests/test_misc_gaps.py](../tests/test_misc_gaps.py) | Coverage gap closers |
| [tests/test_ui_flow.py](../tests/test_ui_flow.py) | End-to-end via `streamlit.testing.v1.AppTest` |
| [tests/test_ui_units.py](../tests/test_ui_units.py) | Per-dimension param editors, weight buttons, Step 3 hover legend + grid helpers, Restart-button branches |
| [tests/test_ml_lab.py](../tests/test_ml_lab.py) | 🧪 ML Lab (27 tests): rule-flag matrix alignment, anomaly ranking (incl. sklearn IsolationForest path), `compute_rule_impact` baseline equality with `result.standard_score`, LOO renormalisation correctness, CDE clustering (numpy + sklearn paths), weight-perturbation distribution shape, cross-DP outlier flagging, snapshot/JSON/CSV round-trips, `compute_drift` (PSI ≈ 0 for identical snapshots, |Δ| threshold flagging), risk classifier (numpy LR + sklearn LR), DQR recommendation heuristics, row-score waterfall decomposition (sums exactly to `100 − row_score`), `sklearn_status()` shape |

---

## 9. Outputs

Step 6 exposes two downloads:

- **CSV**: every row of the data product plus per-row score, threshold status (GREEN / YELLOW / RED), and one column per **Standard *and* Custom** rule with the row's score on that rule (`100` for pass, `0` for fail). Each rule column header embeds the rule's weight (e.g. `STD · MAINT_TM · Completeness (w=12.5%)`, `CUSTOM · E1 · ISO Code of Account Present (w=20.0%)`) so the user can scan a single row and immediately spot which failures hurt the score the most. The export also appends the **reference-dataset columns** for every referential-integrity Custom rule assigned to the data product: each named reference dataset (e.g. `VWS_GP_STANDARD_SHARE`, `ACCE_COA_MASTER`) is left-joined onto the rows on the rule's source → reference key and every reference column is carried through, suffixed with its origin dataset (e.g. `COUNTRY [VWS_GP_STANDARD_SHARE]`, `ISO_COR [ACCE_COA_MASTER]`) so its provenance is unambiguous. A dataset reached by several rules is joined once; an unmatched key leaves the reference cells blank. The join key mirrors what the rules themselves build (`PLANVIEW_ID → PROJECT_ID` directly, ACCE `COA[:3]`, ADR `COMPLETE_WBC` leading dot-segment), so the appended values line up with the master rows the rule evaluated against. The "Worst rows" tab in Step 6 mirrors the same per-rule **and** reference columns for the 50 lowest-scoring rows, and the click-to-drill-down tables (bar / rule-row selection on the Step 6 tabs) reuse the identical enrichment for the rows failing the clicked element.
- **JSON**: the full `DataProductConfig` (CDEs, assignments, weights) and a scorecard summary (overall score, bucket counts, per-CDE and per-dimension scores).

---

## 10. Extending the App

| You want to… | Where to change |
|--------------|-----------------|
| Add a new source system | [config/systems.py](../config/systems.py) - declare `SystemDef` + `TableDef`s |
| Add a new standard DQ dimension | [config/dqr_catalog.py](../config/dqr_catalog.py) (catalog entry) + [src/dqr_engine.py](../src/dqr_engine.py) (`_rule_<name>` function) + UI editor in [ui/step_04_dqr_assignment.py](../ui/step_04_dqr_assignment.py) |
| Add a new custom DQR rule for a data product | Implement a `check(df) -> pd.Series[bool]` in the relevant `src/custom_dqr/_<system>_rules.py` (e.g. `_ept_rules.py` for an EPT rule) - reuse `validate_completeness_rule` or `validate_referential_integrity_rule` from `_validators.py` for the common cases. Add the rule's constants (`<SYS>_<ID>_REQUIRED_COLUMNS`, optional `_REFERENCE`, threshold params, and a `TypedDict` for any parametric options) to the same file. Re-export the new symbols from [src/custom_dqr_engine.py](../src/custom_dqr_engine.py) (per-family import block + `__all__`). Append a `CustomRuleDef(...)` to the relevant list in `config/custom_dqr/_<system>_catalog.py`. For referential-integrity rules also set the `reference` field and register the dataset loader in [src/reference_data.py](../src/reference_data.py); rules whose dependency is missing must `raise CustomRuleNotEvaluated` rather than silently passing. The rule appears automatically in Step 4.2, Step 5, and Step 6's Custom Rules tab. See [ARCHITECTURE.md](../ARCHITECTURE.md) for the full checklist. |
| Add a new data fetcher (e.g., BigQuery) | Implement a fetcher with the same shape used by [src/data_product_builder.py](../src/data_product_builder.py); wire it via [config/settings.py](../config/settings.py) |
| Adjust score thresholds | `.env` (`THRESHOLD_GREEN`, `THRESHOLD_YELLOW`) |
| Tweak suggestion heuristics | `suggest_dimensions_for()` in [config/dqr_catalog.py](../config/dqr_catalog.py) |
| Add a new ML Lab algorithm | Append a function to [src/ml_lab.py](../src/ml_lab.py) (keep numpy fallback + optional sklearn swap-in gated by `use_sklearn`), then add a `_render_tab_<name>` + a `tab_<name>` to [ui/step_07_ml_lab.py](../ui/step_07_ml_lab.py)'s `st.tabs([...])`. See [ML_LAB.md §9](ML_LAB.md#9-extending-the-lab) for the pattern. |
| Persist `ml_lab_runs` between sessions | Today the history is session-local. Hook into `init_state` / `restart_app` and the 📜 Run History tab's snapshot / clear handlers to read/write `~/.dq_scorecard/history/*.json`. |

---

## 11. Cross-cutting Workflow Behaviors

### 11.1 Step navigation row

Every step renders the same three-button nav at the bottom (the `mode_selection` entry step and Step 0 omit Back since they precede the rest; Step 6 omits Next since it is the last). The set of *visible* steps depends on `app_mode`: Step-by-step shows Steps 0-6 (+ ML Lab), One-click shows only the `one_click` step + the dashboard.

| Button | Action | Where the click is handled |
|--------|--------|----------------------------|
| **⬅ Back** | Move to the previous *visible* step (sub-steps 4.1 / 4.2 are skipped when no DP opted into their source; the Step-by-step / One-click steps of the *other* mode are never in the visible list). | `utils.session_state.prev_step` |
| **🔄 Restart** | Wipe `selected_systems`, `data_products`, `configs`, `scorecards`, `domain`, **`app_mode`** and the `one_click_summary` banner, clear the reference-dataset cache, close the shared Databricks client, and jump back to the **mode picker** (`mode_selection`). | `utils.session_state.restart_app` |
| **Next ➡** / **Generate Scorecard ➡** | Move to the next visible step. Disabled while step-specific validation is failing (e.g. Step 3 needs ≥ 1 CDE; Step 5 needs Σ rule weights = 100% per active source). In One-click mode the forward action is **⚡ Generate scorecards**, which jumps straight to the dashboard. | `utils.session_state.next_step` |

Restart is intentionally available on every step, so the user can always abort the workflow (or switch modes) without hunting for the dashboard. The button is rendered inline next to **Back** for visual consistency.

### 11.2 Scroll-to-top after step transitions

`utils.session_state.goto` flips a `_scroll_to_top` flag in `st.session_state` before calling `st.rerun()`. On the next render, `app.main()` invokes `consume_scroll_to_top()` *before* any visible widget; that helper emits a height-zero `streamlit.components.v1.html` iframe whose script calls `window.parent.scrollTo({top: 0, behavior: 'instant'})`. Because the iframe is same-origin with the Streamlit host page, the call succeeds and the user lands at the new step's header instead of mid-scroll. The flag is cleared in the same call so a normal in-step interaction (e.g. ticking a CDE checkbox) does **not** force a scroll-to-top.

### 11.3 Project filter (sidebar)

`utils.session_state.render_planview_filter` exposes a textarea in the sidebar that parses one or more project identifiers (commas, semicolons, whitespace and newlines all work as separators; duplicates are dropped while preserving first-occurrence order). The widget is **domain-aware** and **gated on `session_state.domain`**: it is hidden entirely until Step 0 has set a domain, then reads its label, placeholder, help text and target column from `get_active_domain().project_filter` (a `ProjectFilterDef`). The two domains shipped today configure it as:

| Domain | `project_filter.column` | Widget label |
|--------|-------------------------|--------------|
| Cost Estimate (`cost_estimate`) | `PLANVIEW_ID` | `PLANVIEW_ID(s)` |
| Quality (`quality`) | `PROJECT_CODE` | `PROJECT_CODE(s)` |

New domains add their own `ProjectFilterDef` to `DomainDef.project_filter` (or omit it to inherit `DEFAULT_PROJECT_FILTER`, which keeps the historical `PLANVIEW_ID` behaviour). The parsed list is stored in `st.session_state.planview_filter` (key kept for back-compat - it now holds whatever identifier the active domain filters on) and read by Step 2 via `get_planview_filter()`. Step 2 passes it through to `build_multiple(..., planview_ids=..., filter_column=get_active_project_filter().column)`, which calls `_apply_planview_filter` on each system's primary table before the child joins run, so all of profiling, CDE selection, DQR evaluation and the scorecard operate on the filtered scope. Step 2 also renders a banner naming the active identifiers and warns if any system ended up with zero rows after filtering. Changing the filter invalidates `data_products`, `configs`, `scorecards` and the reference-dataset cache (same behavior as the Sample-mode toggle); the Restart button clears it back to "all projects".

---

## 12. 🧪 ML Lab (Step 7, beta)

The ML Lab is the experimental Machine-Learning / statistical-analytics sandbox of the application. It runs on top of the rules-based scorecard and never changes any score, weight or rule the main flow produced. This section is a high-level summary; full reference (algorithms, formulas, parameters, snapshot schema, drift conventions, limitations, extension points) lives in [ML_LAB.md](ML_LAB.md).

### 12.1 What it does

| Tab | Purpose | Backed by |
|-----|---------|-----------|
| 🔎 **Row Anomalies** | Surface rows whose pattern of rule failures is statistically rare. | Robust z-score on `row_score` + `Σ -log(fail_rate)` rare-failure score (+ optional `IsolationForest` blend at 30% weight when sklearn is on). |
| 🎯 **Rule Impact** | Show which rules are load-bearing vs. dragging the score. | Exact leave-one-out (`baseline − loo`) - linear in pass-rates, so analytical not Monte-Carlo. |
| 🌿 **CDE Clustering** | Group CDEs that "behave the same". | Robust-standardized profile features → k-means + PCA-2D. Numpy fallback or `sklearn.cluster.KMeans` + `sklearn.decomposition.PCA`. |
| ⚖️ **Weight Sensitivity** | Stress-test the Standard sub-score against weight perturbations. | Dirichlet Monte-Carlo around the current weights; concentration parametrised by a `jitter` slider. |
| 🔭 **Cross-DP Comparison** | Flag DPs whose overall score sits far from peers. | Robust z (MAD); `|z| > 1.5` → `Anomalous`. |
| 📜 **Run History** | Capture / export scorecard snapshots and inspect drift. Step 6 runs are now **auto-persisted** (`src/run_history.py`) and appear here with `source=auto`, surviving Restart. *(JSON / CSV upload still under maintenance.)* | Auto-persisted runs merged with session snapshots (`st.session_state.ml_lab_runs`) + PSI + KS + per-rule / per-CDE / per-dim Δ tables. Upload loaders (`load_snapshot_from_json` / `load_snapshot_from_csv`) retained. |
| 🧠 **Risk Model** | Discover which rules best segregate RED rows. | L2-logistic regression on per-rule fail flags, target = `row_score < threshold_yellow`. sklearn LR or numpy gradient-descent LR. |
| 💡 **DQR Recommendations** | Suggest DQRs to add per CDE. | Cosine similarity on robust-standardized profile vectors (cross-DP neighbours) + profile heuristics. |
| 🧩 **Row Explainability** | Decompose `100 − row_score` into per-CDE deficits. | Exact decomposition (score is linear); rendered as a Plotly waterfall. |

### 12.2 Guarantees

- **Read-only.** The lab never mutates `data_products`, `configs`, `scorecards`, `selected_systems`, `planview_filter`, `sample_mode` or any rule definition. It only writes to its own session-state key, `ml_lab_runs`.
- **Unsupervised first.** The only "supervised" view (Risk Model) derives its labels from the same RED-row threshold the user already configured, so it works on any single run with no extra data.
- **Soft sklearn dependency.** `requirements.txt` lists `scikit-learn>=1.3.0` and the lab will use it if importable; if it isn't, every algorithm runs on its numpy fallback. The header shows a `🔬 sklearn x.y.z` badge or `sklearn not installed` accordingly.
- **Restart-safe.** `restart_app()` clears `ml_lab_runs` alongside the rest of the workflow's state.

### 12.3 Where it lives

| File | Role |
|------|------|
| [src/ml_lab.py](../src/ml_lab.py) | All algorithms (snapshot, drift, anomalies, LOO, clustering, weight perturb, cross-DP, risk classifier, DQR reco, row explainability). |
| [ui/step_07_ml_lab.py](../ui/step_07_ml_lab.py) | Streamlit renderer (9 tabs, BETA theme, sklearn toggle, DP picker). |
| [tests/test_ml_lab.py](../tests/test_ml_lab.py) | 27 unit tests covering every public function (numpy + sklearn paths where applicable). |
| [documents/ML_LAB.md](ML_LAB.md) | **Per-algorithm reference**, including math, parameters, snapshot schema, PSI / KS conventions, limitations, extension recipes. |

### 12.4 When to use which tab

| Question the user is asking | Tab |
|-----------------------------|-----|
| "Which rows look weird *even if their score isn't the worst*?" | 🔎 Row Anomalies |
| "If I remove this rule, what happens to the source score?" | 🎯 Rule Impact |
| "Are any of my CDEs behaving alike?" | 🌿 CDE Clustering |
| "How sensitive is my score to the exact weights I picked?" | ⚖️ Weight Sensitivity |
| "Is one DP scoring very differently from the others?" | 🔭 Cross-DP Comparison |
| "Did my score get better/worse since last time?" | 📜 Run History |
| "Which rule failures best predict that a row will be RED?" | 🧠 Risk Model |
| "Am I missing obvious DQRs on any CDE?" | 💡 DQR Recommendations |
| "Why is *this specific row* RED?" | 🧩 Row Explainability |

---

## 13. Companion Diagrams

- **Block Diagram** → [BLOCK_DIAGRAM.md](BLOCK_DIAGRAM.md) - components and dependencies (incl. the Step 7 ML Lab block + sub-diagram).
- **Flowchart** → [FLOWCHART.md](FLOWCHART.md) - end-to-end user/data flow (incl. the dedicated Step 7 sub-flow).
- **Standard Rules Reference** → [STANDARD_RULES.md](STANDARD_RULES.md) - per-dimension semantics, parameters, supported column types.
- **Custom Rules Reference** → [CUSTOM_RULES.md](CUSTOM_RULES.md) - per-rule reference for the EPT custom catalog (E1–E7), the ADR custom catalog (A1–A8), and the ACCE custom catalog (AC1, …).
- **ML Lab Reference** → [ML_LAB.md](ML_LAB.md) - per-algorithm reference for the experimental Step 7.
