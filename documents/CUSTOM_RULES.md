# Custom DQR Rules - Reference

The Custom source of the Data Quality Scorecard App carries
**data-product-specific** rules - domain logic that does not fit the 10
generic Standard dimensions.

> **⚡ One-click mode applies this entire catalog.** When the user picks
> One-click at the entry step, [src/one_click.py](../src/one_click.py)
> selects **every** Custom DQR listed here for each chosen system, each at
> its **default** options/parameters (the same values a Step 4.2 card shows
> untouched - see `default_rule_params`), auto-selects only the CDEs those
> rules require, and distributes the rule weights equally. The Step-by-step flow
> (below) is where the user picks rules and tunes options manually.

The public entry points
[config/custom_dqr_catalog.py](../config/custom_dqr_catalog.py) (catalog
metadata) and [src/custom_dqr_engine.py](../src/custom_dqr_engine.py)
(check functions) are slim re-export shims; the implementations are
partitioned by system / family inside
[config/custom_dqr/](../config/custom_dqr/) (`_ept_catalog.py` /
`_adr_catalog.py` / `_acce_catalog.py` / `_sqs_catalog.py` for the
per-system rule lists, `_shared.py` for the dataclasses and
option-builder helpers) and
[src/custom_dqr/](../src/custom_dqr/) (`_ept_rules.py`, `_adr_rules.py`,
`_acce_rules.py`, `_sqs_rules.py` for the checks + constants +
`TypedDict` params, `_validators.py` for the reusable validators,
`_shared.py` for the helpers and the `CustomRuleNotEvaluated` exception,
`_dispatcher.py` for `evaluate_custom_rules`).

The catalog is keyed by Data Product (`ADR`, `ACCE`, `EPT`, `SQS`).
**EPT** ships seven rules out of the box (E1 – E7), **ADR** ships eight
(A1, A2, A3, A4, A5, A6, A7, A8), **ACCE** ships its own per-rule
catalog (AC1, …) that mirrors the ADR rules against the ACCE schema,
and **SQS** (Quality domain) seeds its catalog with `SQ4` (Validity on
`EXPECTED_SHIP_DATE`), `SQ5` (Business Rule comparing
`EXPECTED_SHIP_DATE` to `PO_REQUIRED_SHIP_DATE`), `SQ6` (Validity on
the `INSPECTION_TYPE` controlled vocabulary), `SQ7` (Validity on the
`WORK_CRITICALITY` classification levels), `SQ8` (Completeness on
`STATUS`), `SQ9` (Validity on the `STATUS` workflow vocabulary), and
`SQ10` (Business Rule pinning Completed inspections to a non-future
`EXPECTED_SHIP_DATE`). Data products without any rules in their
catalog render an empty-state in Step 4.2.

A user opts into a Custom rule from a card in **Step 4.2 - Custom DQR
Cards**, weights it in **Step 5**, and the dashboard reports its row-level
verdict (or *Not evaluated* status) in the **Custom Rules** tab of Step 6.

---

## Catalog data model

Each rule is a `CustomRuleDef` with the following fields
([config/custom_dqr_catalog.py](../config/custom_dqr_catalog.py)):

| Field | Meaning |
|-------|---------|
| `id` | Stable identifier shown in the UI (e.g. `"E1"`, `"E7"`) and used as `rule_id` in scoring. |
| `name` | Human label for the rule card. |
| `type` | Category - currently `"Completeness"`, `"Consistency"`, `"Referential Integrity"`, `"Statistical Outlier"`, `"Validity"`, or `"Business Rule"`. |
| `description` | One-paragraph blurb shown by default on the rule card. |
| `notes` | Long-form explanation, placed inside an expander on the card. |
| `required_columns` | Mapping `business alias → physical column name`. The Step 3 grid uses this to flag CDEs that unlock the rule (🎯) and Step 4.2 validates that every selected rule's required CDEs are picked. |
| `blocking` | When `True` the rule's failure represents a blocking gap in EPT's data quality narrative, the catalog still scores it like any other rule, but the type ↔ blocking pairing is shown to the user as a stronger signal. |
| `check` | `(df) -> pd.Series[bool]` (or `(df, params=...) -> pd.Series[bool]` for rules with options). True = row passes. |
| `reference` | Optional. For Referential Integrity rules: `{"reference_dataset": str, "source_column": str, "reference_column": str, "lookup_column": str?}`. The UI surfaces it in the rule card details. |
| `options` | Optional list of `CustomRuleOption(key, label, default, help, description, required_columns_when_enabled)`. Each option is rendered as an `st.toggle` below the rule's description; its value is persisted to `CustomDQRAssignment.params[key]` and routed to the check callable when it accepts a `params` argument. |
| `select_options` | Optional list of `CustomRuleSelectOption(key, label, choices, default, help, description)`. Each option is rendered as an `st.selectbox` below the rule's description; `choices` is an ordered list of `(value, label)` pairs and the picked value is persisted to `CustomDQRAssignment.params[key]`. Used by every statistical-outlier rule (E3, E6, A3, A7, A8, AC3, AC7, AC8) to expose a customizable threshold (percentile or IQR multiplier), see [Outlier thresholds](#outlier-thresholds-e3--e6--a3--a7--a8--ac3--ac7--ac8). |

`effective_required_columns(rule, params)` composes the static
`required_columns` map with whatever extras enabled options contribute via
`required_columns_when_enabled`. Step 4.2 uses this composed map so that
flipping an option on (e.g. E3's project-scope toggle) immediately demands
the additional CDE. (`select_options` never contribute extra required
columns, they only customize numeric thresholds.)

### Behavioural toggles (E3 / A3 / AC3 / E6 / A7 / A8 / AC7 / AC8)

In addition to the threshold selectbox, the statistical-outlier
rules expose behavioural toggles on their rule cards:

| Rule(s) | Toggle | Default | Effect (when on) |
|---|---|---|---|
| **E3 / A3** | `project_scoped` | `False` | Recompute the percentile baseline *within each `PLANVIEW_ID` partition* instead of globally. E3 adds `PLANVIEW_ID` to the required-CDE list; A3 already requires it. Rows lacking `PLANVIEW_ID` are PASS (E7 / A2 cover the missing-project linkage). AC3 does **not** expose this toggle, its baseline is always portfolio-wide. |
| **E3 / A3** | `detect_uniform_mapping` | `False` | After the percentile fail, additionally fail every *material* group whose `ratio == 1` - surfaces suspiciously uniform 1:1 mappings. Both branches combine with **OR**; materiality still gates both. |
| **AC3** | `detect_uniform_mapping` | `False` | After the percentile fail, **also** fail every material 1:1 bucket, but only when ≥ `ACCE_AC3_UNIFORM_THRESHOLD` (default **80 %**) of eligible mappings in the portfolio are 1:1. The wider gate reflects that ACCE COA codes are inherently coarser than ADR's WBCs, so a few legitimate 1:1 mappings should not by themselves trip the rule. |
| **E6 / A7 / A8 / AC7 / AC8** | `segment_by_project_type` | `False` | Extend the IQR segment key with the composite `(E05_DEPARTMENT, BUSINESS)` tuple resolved from `VWS_GP_STANDARD_SHARE` via `PLANVIEW_ID → PROJECT_ID`. A7 extends `(ITEM_TYPE, QTY_UOM)` and AC7 extends `(DESCRIPTION, QTY_UOM)` → `(…, E05_DEPARTMENT, BUSINESS)`; A8 / AC8 / E6 partition the per-ratio / per-project IQR baseline by `(E05_DEPARTMENT, BUSINESS)` alone. Per-segment populations below the rule's minimum-population floor stay NOT_APPLICABLE → PASS. Rows / projects whose segment cannot be resolved (missing PLANVIEW_ID, unmatched PROJECT_ID, or null/blank `E05_DEPARTMENT` / `BUSINESS`) are also NOT_APPLICABLE → PASS - completeness rules already cover those gaps. When the toggle is on and the reference dataset is unavailable, the check raises `CustomRuleNotEvaluated`. |

All toggles are opt-in so the rule's pre-feature behaviour is
preserved when the user does not touch them. The toggle param keys
(`EPT_E3_PROJECT_SCOPED_PARAM`, `EPT_E3_DETECT_UNIFORM_MAPPING_PARAM`,
`EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM`,
`ADR_A3_PROJECT_SCOPED_PARAM`, `ADR_A3_DETECT_UNIFORM_MAPPING_PARAM`,
`ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM`,
`ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM`,
`ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM`,
`ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM`,
`ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM`) live alongside their
threshold counterparts in
[src/custom_dqr_engine.py](../src/custom_dqr_engine.py).

### Outlier thresholds (E3 / E6 / A3 / A7 / A8 / AC3 / AC7 / AC8)

Every `"Statistical Outlier"` rule exposes a single-choice threshold
selectbox on its Step 4.2 card. The default is the rule's documented
baseline (P90 for percentile-based rules, 1.5×IQR for IQR-based ones) so
the rule behaves identically to its pre-feature self when the user does
not touch the picker; a non-default choice is persisted to
`CustomDQRAssignment.params[<RULE>_THRESHOLD_PARAM]` and routed through
the check callable.

| Rule | Param key | Choices (recommended in **bold**) | Default constant |
|------|-----------|-----------------------------------|------------------|
| **E3** | `threshold_percentile` | P75, **P90**, P95, P99 | `EPT_E3_PERCENTILE = 0.90` |
| **E6** | `threshold_iqr_multiplier` | **1.5×IQR (mild)**, 2.0×IQR, 3.0×IQR (extreme) | `EPT_E6_MILD_IQR_MULTIPLIER = 1.5` |
| **A3** | `threshold_percentile` | P75, **P90**, P95, P99 | `ADR_A3_PERCENTILE = 0.90` |
| **A7** | `threshold_iqr_multiplier` | **1.5×IQR (mild)**, 2.0×IQR, 3.0×IQR (extreme) | `ADR_A7_MILD_IQR_MULTIPLIER = 1.5` |
| **A8** | `threshold_iqr_multiplier` | **1.5×IQR (mild)**, 2.0×IQR, 3.0×IQR (extreme) | `ADR_A8_MILD_IQR_MULTIPLIER = 1.5` |
| **AC3** | `threshold_percentile` | P75, **P90**, P95, P99 | `ACCE_AC3_PERCENTILE = 0.90` |
| **AC7** | `threshold_iqr_multiplier` | **1.5×IQR (mild)**, 2.0×IQR, 3.0×IQR (extreme) | `ACCE_AC7_MILD_IQR_MULTIPLIER = 1.5` |
| **AC8** | `threshold_iqr_multiplier` | **1.5×IQR (mild)**, 2.0×IQR, 3.0×IQR (extreme) | `ACCE_AC8_MILD_IQR_MULTIPLIER = 1.5` |

Param keys and choice lists live in [src/custom_dqr_engine.py](../src/custom_dqr_engine.py)
(`<RULE>_THRESHOLD_PARAM`, `<RULE>_THRESHOLD_CHOICES`); both are
re-exported from the per-family modules in `src/custom_dqr/`. Stale /
malformed values fall back to the default via
`_coerce_threshold(value, default)`, so an assignment carrying a value
no longer in the catalog never silently disables the rule.

Each parametric rule also declares a `TypedDict` (`EPTE3Params`,
`EPTE6Params`, `ADRA3Params`, `ADRA7Params`, `ADRA8Params`,
`ACCEAC3Params`, `ACCEAC7Params`, `ACCEAC8Params`) describing the
shape of `assignment.params`. They are `total=False`, so a missing key
falls back to the module-level default. The TypedDicts are documentation
for IDE / type-checker use; `_coerce_threshold` still handles legacy
string values at runtime.

**Semantics.**
- *Percentile-based* (E3, A3, AC3): raising the threshold (P95,
  P99) makes the rule **stricter**: only the most extreme mappings
  are flagged. Lowering it (P75) makes it **more sensitive**.
- *IQR-based* (E6, A7, A8, AC7, AC8): raising the multiplier (2.0×,
  3.0×) **widens the PASS band**: fewer flagged outliers, more
  lenient. Lowering it would narrow the band; the catalog only
  exposes values ≥ 1.5× because going below the textbook mild bound
  produces noise, not signal.

### How a rule signals failure

There are three failure shapes:

| Outcome | How the check signals it | Where it surfaces |
|---------|--------------------------|-------------------|
| Row fails the rule | Returns `False` for that row | Counted in pass-rate; affects custom row score |
| **Required column missing** from `df` | Returns an all-`False` Series (the dataset is structurally incomplete) | Pass-rate = 0%; rule still appears in the dashboard |
| **Reference dataset missing** (Snowflake error, missing table, …) | Raises `CustomRuleNotEvaluated` | Recorded in `not_evaluated_custom_rules`; rule omitted from the Boolean results; Step 6 renders a yellow *Not evaluated* warning |

The third shape is critical: a rule **must never silently pass** when its
inputs are missing, that would hide the gap in the score.

---

## Quick reference (EPT)

| Rule | Name | Type | Blocking | Required columns | Reference data | Options |
|------|------|------|----------|------------------|----------------|---------|
| **E1** | ISO Code of Account Present (COR + SAB)               | Completeness         | Yes | `CODE_OF_RESOURCE`, `STANDARD_ACTIVITY_BREAKDOWN` | - | - |
| **E2** | Location + estimate date present                       | Completeness         | No  | `CENTROID_DATE`, `PLANVIEW_ID` | `VWS_GP_STANDARD_SHARE` (lookup `COUNTRY`) | - |
| **E3** | Statistical Excessive WBC to ISO Mapping               | Statistical Outlier  | No  | `WBC_LEVEL_5`, `CODE_OF_RESOURCE`, `STANDARD_ACTIVITY_BREAKDOWN`, `TOTAL_HOURS`, `TOTAL_COST_USD` (+ `PLANVIEW_ID` when project-scope is on) | - | `threshold_percentile` (select, default P90), `project_scoped` (bool), `detect_uniform_mapping` (bool) |
| **E4** | Level 1 cost category populated                        | Completeness         | No  | `WBC_LEVEL_1` | - | - |
| **E5** | FEED / Engineering hours estimate present when cost exists | Consistency      | No  | `WBC_LEVEL_1`, `TOTAL_HOURS`, `TOTAL_COST_USD`, `TOTAL_COST_ESTIMATE_CURRENCY` | - | - |
| **E6** | Cost-to-hours ratio outlier check                      | Statistical Outlier  | No  | `PLANVIEW_ID`, `TOTAL_HOURS`, `TOTAL_COST_USD`, `TOTAL_COST_ESTIMATE_CURRENCY` | `VWS_GP_STANDARD_SHARE` (only when `segment_by_project_type` is on - lookup `E05_DEPARTMENT` + `BUSINESS`) | `threshold_iqr_multiplier` (select, default 1.5×), `segment_by_project_type` (bool) |
| **E7** | Project Key linkage                                    | Referential Integrity| Yes | `PLANVIEW_ID` | `VWS_GP_STANDARD_SHARE` (`PLANVIEW_ID → PROJECT_ID`) | - |

## Quick reference (ADR)

| Rule | Name | Type | Blocking | Required columns | Reference data | Options |
|------|------|------|----------|------------------|----------------|---------|
| **A1** | ISO Code of Account present (COR + SAB)                | Completeness         | Yes | `PLANVIEW_ID`, `COMPLETE_WBC` | `ACCE_COA_MASTER` (`SPLIT_PART(COMPLETE_WBC, '.', 1) → ICARUS_COA`, lookup `ISO_COR` + `SAB`) | - |
| **A2** | Location + estimate date present & valid               | Completeness & Validity | No  | `COST_UPDATE`, `PLANVIEW_ID` | `VWS_GP_STANDARD_SHARE` (lookup `COUNTRY`) | - |
| **A3** | Statistical WBC-to-ISO mapping ratio                   | Statistical Outlier  | No  | `PLANVIEW_ID`, `COMPLETE_WBC`, `COST_TOTAL_HOURS`, `COST_TOTAL_COST` | `ACCE_COA_MASTER` (lookup `ISO_COR` + `SAB`) | `threshold_percentile` (select, default P90), `project_scoped` (bool), `detect_uniform_mapping` (bool) |
| **A4** | Core quantities populated & non-negative project totals | Completeness & Validity | No  | `PLANVIEW_ID`, `ITEM_TYPE`, `ITEM_DESCRIPTION`, `QTY_QUANTITY`, `QTY_UOM` | - | - |
| **A5** | Design details present when quantity exists            | Consistency          | No  | `QTY_QUANTITY`, `DESIGN_PARAMETER_VALUE` | - | - |
| **A6** | Construction hours present when quantity exists        | Consistency          | No  | `QTY_QUANTITY`, `COST_TOTAL_HOURS`, `COST_DB_TOTAL_HOURS` | - | - |
| **A7** | Within-discipline quantity / hour ratio outlier        | Statistical Outlier  | No  | `ITEM_TYPE`, `QTY_QUANTITY`, `QTY_UOM`, `COST_TOTAL_HOURS` (+ `PLANVIEW_ID` when `segment_by_project_type` is on) | `VWS_GP_STANDARD_SHARE` (only when `segment_by_project_type` is on - lookup `E05_DEPARTMENT` + `BUSINESS`) | `threshold_iqr_multiplier` (select, default 1.5×), `segment_by_project_type` (bool) |
| **A8** | Cross-discipline quantity ratios                       | Statistical Outlier  | No  | `ITEM_TYPE`, `ROOT_ITEM_NAME`, `QTY_QUANTITY`, `QTY_UOM` (+ `PLANVIEW_ID` when `segment_by_project_type` is on) | `VWS_GP_STANDARD_SHARE` (only when `segment_by_project_type` is on - lookup `E05_DEPARTMENT` + `BUSINESS`) | `threshold_iqr_multiplier` (select, default 1.5×), `segment_by_project_type` (bool) |

## Quick reference (ACCE)

ACCE rules mirror the ADR rules' business logic against the ACCE schema, see the [ADR → ACCE column mapping](#adr--acce-column-mapping) below
for the field-level substitutions (e.g. `COMPLETE_WBC` → `COA`,
`COST_UPDATE` → `JOB_NO`, `ITEM_TYPE` → `DESCRIPTION`).

| Rule | Name | Type | Blocking | Required columns | Reference data | Options |
|------|------|------|----------|------------------|----------------|---------|
| **AC1** | ISO Code of Account present (COR + SAB) | Completeness | Yes | `PLANVIEW_ID`, `COA` | `ACCE_COA_MASTER` (`COA[:3] → ICARUS_COA` - leading 3 characters of the 4-char ACCE COA; lookup `ISO_COR` + `SAB`) | - |
| **AC2** | Location + estimate date present & valid | Completeness & Validity | No | `JOB_NO`, `PLANVIEW_ID` | `VWS_GP_STANDARD_SHARE` (lookup `COUNTRY`) | - |
| **AC3** | Statistical COA-to-ISO mapping ratio | Statistical Outlier | No | `PLANVIEW_ID`, `COA`, `COST_MH`, `COST_TOTAL_COST` | `ACCE_COA_MASTER` (`COA[:3] → ICARUS_COA`; lookup `ISO_COR` + `SAB`) | `threshold_percentile` (select, default P90), `detect_uniform_mapping` (bool - 80 % portfolio gate) |
| **AC4** | Core quantities populated & non-negative project totals | Completeness & Validity | No | `PLANVIEW_ID`, `DESCRIPTION`, `QTY_KEY_QTY`, `QTY_OTHER_QTY`, `QTY_KEY_UNITS`, `QTY_OTHER_UNITS` | - | - |
| **AC5** | Design details present when quantity exists | Consistency | No | `QTY_KEY_QTY`, `QTY_OTHER_QTY`, `DESIGN_PROPERTY`, `DESIGN_VALUE` | - | - |
| **AC6** | Construction hours present when quantity exists | Consistency | No | `QTY_KEY_QTY`, `QTY_OTHER_QTY`, `COST_MH` | - | - |
| **AC7** | Within-discipline quantity / hour ratio outlier | Statistical Outlier | No | `DESCRIPTION`, `QTY_KEY_QTY`, `QTY_OTHER_QTY`, `QTY_KEY_UNITS`, `QTY_OTHER_UNITS`, `COST_MH` (+ `PLANVIEW_ID` when `segment_by_project_type` is on) | `VWS_GP_STANDARD_SHARE` (only when `segment_by_project_type` is on - lookup `E05_DEPARTMENT` + `BUSINESS`) | `threshold_iqr_multiplier` (select, default 1.5×), `segment_by_project_type` (bool) |
| **AC8** | Cross-discipline quantity ratios | Statistical Outlier | No | `COMPONENT_SOURCE`, `DESCRIPTION`, `QTY_KEY_QTY`, `QTY_OTHER_QTY`, `QTY_KEY_UNITS`, `QTY_OTHER_UNITS` (+ `PLANVIEW_ID` when `segment_by_project_type` is on) | `VWS_GP_STANDARD_SHARE` (only when `segment_by_project_type` is on - lookup `E05_DEPARTMENT` + `BUSINESS`) | `threshold_iqr_multiplier` (select, default 1.5×), `segment_by_project_type` (bool) |

## Quick reference (SQS - Quality domain)

| Rule | Name | Type | Blocking | Required columns | Reference data | Options |
|------|------|------|----------|------------------|----------------|---------|
| **SQ4** | Valid date (`EXPECTED_SHIP_DATE`) | Validity | No | `EXPECTED_SHIP_DATE` | - | - |
| **SQ5** | Not after PO Required Ship Date | Business Rule | No | `EXPECTED_SHIP_DATE`, `PO_REQUIRED_SHIP_DATE` | - | - |
| **SQ6** | Inspection Type value in allowed set | Validity | No | `INSPECTION_TYPE` | - (fixed list: `Source Inspection`, `Supplier Assessment`, `Expediting`, `Supplemental Inspection`) | - |
| **SQ7** | Work Criticality value in allowed set | Validity | No | `WORK_CRITICALITY` | - (fixed list: `I - High Critical`, `II - Medium Critical`, `III - Low Critical`, `IV - Non Critical`) | - |
| **SQ8** | Status required | Completeness | No | `STATUS` | - | - |
| **SQ9** | Status value in allowed set | Validity | No | `STATUS` | - (11 canonical workflow statuses; see SQ9 section for the list) | - |
| **SQ10** | Status / Expected Ship Date sequencing | Business Rule | No | `STATUS`, `EXPECTED_SHIP_DATE` | - | - |

---

## Reusable validators

Two helpers in [src/custom_dqr_engine.py](../src/custom_dqr_engine.py) let
new rules reuse the structural checks every Custom rule needs:

- **`validate_completeness_rule(df, required_columns)`**: every column
  must be non-null and (string-typed) non-blank for the row to pass; if
  any required column is absent from `df`, the rule fails for every row.
  Used by E1, E4, and SQ8.
- **`validate_referential_integrity_rule(source_df, source_column,
  reference_df, reference_column)`**, the source value is non-blank and
  its string-stripped form appears in the reference column. A missing
  source/reference *column* makes every row fail; a missing reference
  *dataset* should be signalled by raising `CustomRuleNotEvaluated`
  before invoking the validator. Used by E7.

Statistical-outlier rules (E3, E6, A3, A7, A8) compute group-level metrics
inside their own check function and propagate the per-group verdict back to
every row of the failing group, same row-level / group-verdict pattern, no
shared helper because the metrics differ. Each of these rules accepts a
`params` argument and reads its threshold from
`params[<RULE>_THRESHOLD_PARAM]` (percentile for E3 / A3, IQR multiplier
for E6 / A7 / A8); `_coerce_threshold(value, default)` keeps stale or
malformed values from disabling the rule.

---

## Reference-data registry & eager loading

Custom rules that need a reference dataset (E2, E7, A1, A2, A3) resolve
it via [src/reference_data.py](../src/reference_data.py):

- `prefetch_reference_datasets(names)` is called from **Step 2** right
  after the system tables are built, with the names returned by
  `required_reference_datasets_for_systems(selected_systems)`. The
  fetched DataFrames (and any loader error strings) are cached in
  `st.session_state["_reference_datasets"]`.
- The Snowflake round-trip happens **once**, alongside the system
  table fetches, not lazily during Step 6. Subsequent re-renders
  (including the implicit re-render after a Step 6 *Restart*) hit the
  cache instead of reconnecting.
- Load errors are surfaced **immediately** in Step 2 as a yellow warning
  identifying the dataset and the underlying error message, so the user
  knows up-front which Custom rules will be marked *Not evaluated* in
  Step 6.

The cache is cleared on **Sample mode** toggle, on a change to the **Project filter**
(PLANVIEW_ID), and on **Restart** (`clear_reference_cache()`); the next visit to
Step 2 re-fetches.

When the loader returns `None` (connector missing, network failure,
missing table) or raised an exception captured during prefetch, the
relevant rule (`check_ept_e2` / `check_ept_e7` / `check_ept_e6` (only
when `segment_by_project_type` is on) / `check_adr_a1` /
`check_adr_a2` / `check_adr_a3` / `check_adr_a7` (only when
`segment_by_project_type` is on) / `check_adr_a8` (only when
`segment_by_project_type` is on) / `check_acce_ac1` /
`check_acce_ac2` / `check_acce_ac3` / `check_acce_ac7` (only when
`segment_by_project_type` is on) / `check_acce_ac8` (only when
`segment_by_project_type` is on)) raises `CustomRuleNotEvaluated`
with the cached error message appended.

### Reference datasets in use

| Dataset | Loaded from | Consumers |
|---------|-------------|-----------|
| `VWS_GP_STANDARD_SHARE` | `{SF_DATABASE}.{SF_SCHEMA}.VWS_GP_STANDARD_SHARE` | E2 (lookup `COUNTRY`), E6 (lookup `E05_DEPARTMENT` + `BUSINESS` - only when `segment_by_project_type` is on), E7 (`PLANVIEW_ID → PROJECT_ID`), A2 (lookup `COUNTRY`), A7 (lookup `E05_DEPARTMENT` + `BUSINESS` - only when `segment_by_project_type` is on), A8 (lookup `E05_DEPARTMENT` + `BUSINESS` - only when `segment_by_project_type` is on), AC2 (lookup `COUNTRY`), AC7 (lookup `E05_DEPARTMENT` + `BUSINESS` - only when `segment_by_project_type` is on), AC8 (lookup `E05_DEPARTMENT` + `BUSINESS` - only when `segment_by_project_type` is on) |
| `ACCE_COA_MASTER`       | `INGESTION_DB.GP_ADF_CSE.ACCE_COA_MASTER`         | A1 + A3 + AC1 + AC3 (`ICARUS_COA → ISO_COR + SAB`). A1 / AC1 validate the resolution (ADR via a `SPLIT_PART(COMPLETE_WBC, '.', 1)` derivation, ACCE via the **first three characters** of the 4-character `COA` - the analog of ADR's split); A3 measures distinct-`COMPLETE_WBC` aggregation per resolved bucket; AC3 measures distinct-`COA` aggregation (over the *full* 4-character `COA`, not the truncated lookup key) per resolved bucket. |

---

## E1: ISO Code of Account Present (COR + SAB)

- **Type:** Completeness · **Blocking:** Yes
- **Implementation:** `check_ept_e1` →
  `validate_completeness_rule(df, ["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"])`.

A row passes when **both** `CODE_OF_RESOURCE` and
`STANDARD_ACTIVITY_BREAKDOWN` are populated (non-null AND non-blank). When
either column is absent from the schema the rule fails for every row.

**Why it matters.** Without COR + SAB, EPT cost data cannot be normalized
via the EMMA factor, the row is unusable for downstream cost analytics.

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| COR   | `CODE_OF_RESOURCE` |
| SAB   | `STANDARD_ACTIVITY_BREAKDOWN` |

---

## E2: Location + Estimate Date Present

- **Type:** Completeness · **Blocking:** No
- **Implementation:** `check_ept_e2` (uses `_is_filled` directly + a join
  against the Planview reference).
- **Reference dataset:** `VWS_GP_STANDARD_SHARE`
  (`EPT.PLANVIEW_ID → VWS_GP_STANDARD_SHARE.PROJECT_ID`, lookup `COUNTRY`).

A row passes when **both** hold:

1. `CENTROID_DATE` (estimate basis date, in EPT) is non-null and non-blank.
2. `COUNTRY` (project location) is non-null and non-blank in the Planview
   reference, **after** joining `EPT.PLANVIEW_ID` against
   `VWS_GP_STANDARD_SHARE.PROJECT_ID`. An unmatched `PLANVIEW_ID` is
   treated as a missing `COUNTRY` (i.e. the row fails E2).

**Why it matters.** COUNTRY + CENTROID_DATE together pick the correct CU
period for EMMA normalization. CENTROID_DATE is the *estimate basis date*,
not the data-entry date.

**Failure modes:**

- Missing `CENTROID_DATE` or `PLANVIEW_ID` column → all rows fail.
- Reference dataset unavailable → `CustomRuleNotEvaluated` (Step 6 shows
  *Not evaluated*).
- Reference dataset present but missing `PROJECT_ID` / `COUNTRY` → all
  rows fail.

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| Estimate Basis Date | `CENTROID_DATE` |
| Project Key         | `PLANVIEW_ID`   |

---

## E3: Statistical Excessive WBC to ISO Mapping

- **Type:** Statistical Outlier · **Blocking:** No
- **Implementation:** `check_ept_e3(df, params)` (params-aware).

Group-level statistical rule with a row-level verdict, every row inherits
its mapping's pass/fail so the rule plugs into the same per-row scoring
pipeline as E1 / E2 / E4 / E5 / E7.

### Default scope (project_scoped = False)

1. Group rows by ISO mapping `(CODE_OF_RESOURCE, STANDARD_ACTIVITY_BREAKDOWN)`.
2. Per group compute:
   - `ratio = COUNT(DISTINCT WBC_LEVEL_5)` (null/blank WBC values are
     excluded, mirrors `COUNT(DISTINCT col)` SQL semantics).
   - `hours_sum = SUM(TOTAL_HOURS)` (null → 0).
   - `cost_sum = SUM(TOTAL_COST_USD)` (null → 0).
3. Compute one global `P90 = quantile(ratio, 0.90)` across all eligible
   mappings (`ratio ≥ 1`).
4. A group **fails** when `ratio > P90` **and** the group is *material*
   (`hours_sum > 0` or `cost_sum ≥ EPT_E3_MATERIALITY_USD`, default
   100,000 USD). Every row inside a failing group inherits the FAIL.
5. Rows whose ISO key (COR/SAB) is null/blank are treated as PASS - E1
   already flags those gaps and E3 cannot meaningfully evaluate
   over-aggregation when the bucket is missing.

### Project scope (project_scoped = True, opt-in via the rule card)

- The group key becomes `(PLANVIEW_ID, COR, SAB)` and the P90 is
  recomputed *within each PLANVIEW_ID partition* (`PARTITION BY
  PLANVIEW_ID`). Each project gets its own statistical baseline, so a
  project with naturally fine-grained WBC discipline isn't dragged down
  by peers that aggregate aggressively.
- `PLANVIEW_ID` becomes a **required column** (Step 4.2 folds it into the
  CDE-coverage check via `required_columns_when_enabled`).
- Rows lacking `PLANVIEW_ID` in project mode are treated as PASS - E7
  already covers the missing-project linkage.

### Uniform 1:1 mapping detection (detect_uniform_mapping = True, opt-in)

- Off by default. When on, after the regular percentile-based outlier
  verdict the rule **also** fails every *material* group whose
  `ratio == 1` (each ISO bucket holds exactly one distinct
  `WBC_LEVEL_5`). The intent is to surface mappings that are
  suspiciously uniform, typically a sign that the mapping process was
  bypassed and source codes were copied 1:1 into the ISO bucket
  instead of being aggregated.
- The percentile fail and the uniform-1:1 fail combine with **OR**: both signals coexist when the toggle is on.
- The materiality filter still applies, so planning / structural-only
  buckets with `ratio == 1` are not flagged.
- Off by default because a small / early dataset can legitimately show
  `ratio == 1` for every bucket; turn it on when you want to surface
  mapping-discipline issues.
- No extra required columns, the existing `WBC_LEVEL_5` + COR/SAB
  inputs are sufficient.

### Materiality filter

`EPT_E3_MATERIALITY_USD` (default 100,000 USD) suppresses false positives
from planning / structural-only mappings: a mapping with
`hours_sum == 0` and `cost_sum < threshold` is exempt regardless of its
ratio. The filter gates both the percentile and uniform-1:1 branches
when the latter is enabled.

### Inputs

| Alias | Physical column | Required when |
|-------|-----------------|----------------|
| WBC Level 5             | `WBC_LEVEL_5`                  | always |
| COR                     | `CODE_OF_RESOURCE`             | always |
| SAB                     | `STANDARD_ACTIVITY_BREAKDOWN`  | always |
| Total Hours             | `TOTAL_HOURS`                  | always |
| Total Cost (USD)        | `TOTAL_COST_USD`               | always |
| Project Key             | `PLANVIEW_ID`                  | when `project_scoped = True` |

### Options

| Key | Widget | Default | Effect |
|-----|--------|---------|--------|
| `threshold_percentile` | `st.selectbox` | `0.90` (P90) | Percentile cutoff applied to the WBC-to-ISO ratio distribution. Choices: P75 (lenient), **P90 (recommended)**, P95 (strict), P99 (very strict). |
| `project_scoped` | `st.toggle` | `False` | Switches the percentile baseline from global to per-`PLANVIEW_ID`. |
| `detect_uniform_mapping` | `st.toggle` | `False` | When on, *material* groups with `ratio == 1` also fail (OR'd with the percentile branch) - surfaces suspiciously uniform 1:1 mappings. |

---

## E4: Level 1 cost category populated

- **Type:** Completeness · **Blocking:** No
- **Implementation:** `check_ept_e4` →
  `validate_completeness_rule(df, ["WBC_LEVEL_1"])`.

A row passes when `WBC_LEVEL_1` is non-null and non-blank (whitespace-only
is treated as blank, same semantics as the Standard Completeness
dimension with `allow_empty_string=False`). Missing column → all rows
fail.

**Why it matters.** Ideally cost is broken down by category at multiple
WBC levels, but Level 1 is the *minimum acceptable granularity* - a row
without it cannot participate in any cost-category roll-up.

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| Level 1 | `WBC_LEVEL_1` |

---

## E5: FEED / Engineering hours estimate present when cost exists

- **Type:** Consistency · **Blocking:** No
- **Implementation:** `check_ept_e5`.

A row is **in scope** when `WBC_LEVEL_1` matches the case-insensitive
regex `\b(?:FEED|ENGINEERING)\b` (so `FEED`, `FEED BY CONTRACTOR(S)`,
`250.0-FEED BY CONTRACTOR`, `DETAILED ENGINEERING`, `ENGINEERING COSTS`
all match, but `FEEDBACK` / `ENGINEERED` don't).

For in-scope rows the rule compares two derived amounts:

```
cost_amount  = COALESCE(TOTAL_COST_USD, TOTAL_COST_ESTIMATE_CURRENCY, 0)
hours_amount = COALESCE(TOTAL_HOURS, 0)
```

A row passes when:

- **both amounts are present (`> 0`)**, or
- **both amounts are absent (`== 0`)**.

It fails when exactly one side is present (cost without hours, or hours
without cost). Null numeric inputs are treated as zero; a value is
"present" only when strictly `> 0`.

**Non-FEED rows are Not Applicable and pass**: only the FEED / Engineering
scope is judged here.

**Failure modes:**

- Missing required column (`WBC_LEVEL_1`, `TOTAL_HOURS`, `TOTAL_COST_USD`,
  `TOTAL_COST_ESTIMATE_CURRENCY`) → all rows fail (structural
  incompleteness).

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| Level 1                      | `WBC_LEVEL_1`                   |
| Total Hours                  | `TOTAL_HOURS`                   |
| Total Cost (USD)             | `TOTAL_COST_USD`                |
| Total Cost (Local Currency)  | `TOTAL_COST_ESTIMATE_CURRENCY`  |

---

## E6: Cost-to-hours ratio outlier check

- **Type:** Statistical Outlier · **Blocking:** No
- **Implementation:** `check_ept_e6`.
- **Optional reference dataset:** `VWS_GP_STANDARD_SHARE`
  (`PLANVIEW_ID → PROJECT_ID`, lookup `E05_DEPARTMENT` + `BUSINESS`).
  Only consulted when the `segment_by_project_type` toggle is on; the
  default global-IQR path runs without any reference.

Project-level outlier detection with a row-level verdict.

### Algorithm

1. Aggregate per `PLANVIEW_ID`:

   ```
   cost_amount  = COALESCE(TOTAL_COST_USD, TOTAL_COST_ESTIMATE_CURRENCY, 0)
   hours_amount = COALESCE(TOTAL_HOURS, 0)
   cost_sum     = SUM(cost_amount)
   hours_sum    = SUM(hours_amount)
   ```

2. For projects with `hours_sum > 0`, compute the ratio
   `cost_to_hours_ratio = cost_sum / hours_sum`.
3. From the **eligible-project population** derive IQR thresholds:
   `Q1 - 1.5 × IQR` … `Q3 + 1.5 × IQR`
   (`EPT_E6_MILD_IQR_MULTIPLIER = 1.5`; the 3.0 extreme multiplier is
   used only for severity classification, every extreme outlier is
   already a mild outlier and therefore a FAIL). When
   `segment_by_project_type` is on the IQR is recomputed **within each
   segment** instead, see [Project-type segmentation](#project-type-segmentation-segment_by_project_type).
4. A project **fails** when its ratio is below the lower bound or above
   the upper bound (of its segment in segmented mode, of the global
   population otherwise). Every row in a flagged project inherits the
   FAIL.

### NOT_APPLICABLE (treated as PASS) cases

E6 does not surface a separate "NA" bucket, it returns Booleans only.
The cases below are mapped to PASS to avoid double-counting against rules
that already cover those gaps:

- **Project where `hours_sum ≤ 0`**: the ratio cannot be calculated; E5
  already flags FEED cost-without-hours.
- **Rows with null/blank `PLANVIEW_ID`**: cannot be assigned to a
  project; E7 already covers the missing-project linkage.
- **Eligible-project population below `EPT_E6_MIN_POPULATION` (default 5)**: too small to define an outlier population. When segmentation is on,
  the same floor is applied **per segment** so a thinly-populated bucket
  does not flag every project inside it as an outlier of itself.
- **Project whose segment cannot be resolved** (only when segmentation
  is on) - unmatched `PROJECT_ID`, or null/blank `E05_DEPARTMENT` /
  `BUSINESS` from the join - NOT_APPLICABLE → PASS. E7 / E2 already
  cover those referential / completeness gaps.

### Notes

- **Cost fallback.** When `TOTAL_COST_USD` is null the row's contribution
  falls back to `TOTAL_COST_ESTIMATE_CURRENCY`; populated zeros in
  `TOTAL_COST_USD` win over the local-currency fallback (SQL COALESCE
  semantics).
- **Thresholds derived from the data.** No fixed cost-per-hour benchmark
  is hard-coded, the IQR multipliers are the only knobs.
- **Negative or zero costs are not exempt.** If a project's
  `cost_sum ≤ 0` while peers are positive, the resulting ratio naturally
  falls outside the lower IQR bound and the project is flagged for
  review.
- **Schema-level missing column → all rows fail**, mirroring the
  convention used by E1 / E3 / E4 / E5.
- **Segmented mode requires the reference.** When
  `segment_by_project_type` is on and `VWS_GP_STANDARD_SHARE` is
  unavailable (or is missing `E05_DEPARTMENT` / `BUSINESS`), the rule
  raises `CustomRuleNotEvaluated`, it never silently falls back to the
  global IQR baseline.

### Project-type segmentation (`segment_by_project_type`)

Cost-per-hour expectations differ wildly across project archetypes - a
deepwater FPSO and an onshore refinery sit in opposite corners of the
ratio distribution. Pooling them into one IQR pulls the global bounds
wide enough that genuine outliers within each archetype hide in the
middle. The segmentation toggle splits the population before deriving
the IQR.

When on:

1. Each `PLANVIEW_ID` is joined to `VWS_GP_STANDARD_SHARE` on
   `PLANVIEW_ID = PROJECT_ID` to recover its archetype tags
   (`E05_DEPARTMENT` for brownfield / greenfield, `BUSINESS` for the
   business line, e.g. upstream / downstream / chemical / LNG).
2. Projects are grouped by the **composite key**
   `(E05_DEPARTMENT, BUSINESS)`. Each segment derives its own `Q1`,
   `Q3`, and IQR; the PASS band is segment-local.
3. The same per-segment minimum-population floor
   (`EPT_E6_MIN_POPULATION`) applies - segments with fewer eligible
   projects fall through to NOT_APPLICABLE → PASS.

When off (default) the rule behaves exactly as it did before this
feature, one global IQR across the dataset.

### Inputs

| Alias | Physical column |
|-------|-----------------|
| Project Key                  | `PLANVIEW_ID`                   |
| Total Hours                  | `TOTAL_HOURS`                   |
| Total Cost (USD)             | `TOTAL_COST_USD`                |
| Total Cost (Local Currency)  | `TOTAL_COST_ESTIMATE_CURRENCY`  |

### Options

| Key | Widget | Default | Effect |
|-----|--------|---------|--------|
| `threshold_iqr_multiplier` | `st.selectbox` | `1.5` | IQR multiplier used to derive the PASS band `Q1 − k·IQR … Q3 + k·IQR`. Choices: **1.5×IQR (mild - recommended)**, 2.0×IQR, 3.0×IQR (extreme). Larger values widen the PASS band, fewer flagged outliers. |
| `segment_by_project_type` | `st.toggle` | `False` | When on, the IQR baseline is computed within each `(E05_DEPARTMENT, BUSINESS)` segment resolved via `VWS_GP_STANDARD_SHARE`. Off → one global IQR across every eligible project. |

---

## E7: Project Key linkage

- **Type:** Referential Integrity · **Blocking:** Yes
- **Implementation:** `check_ept_e7` → resolves the
  `VWS_GP_STANDARD_SHARE` reference DataFrame and delegates to
  `validate_referential_integrity_rule(df, "PLANVIEW_ID", reference_df, "PROJECT_ID")`.
- **Reference dataset:** `VWS_GP_STANDARD_SHARE`
  (`EPT.PLANVIEW_ID → VWS_GP_STANDARD_SHARE.PROJECT_ID`).

A row passes when `PLANVIEW_ID` is non-null, non-blank, **and** its
string-stripped value appears in the reference table's `PROJECT_ID`
column.

**Why it matters.** A row that cannot be joined to the project master is
orphaned, it cannot participate in cross-system roll-ups (which use
`PLANVIEW_ID` as the project grain).

**Failure modes:**

- Missing `PLANVIEW_ID` column → all rows fail.
- Reference dataset unavailable → `CustomRuleNotEvaluated` (Step 6 shows
  *Not evaluated*; the underlying loader error is propagated when it was
  captured by `prefetch_reference_datasets`).

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| Project Key | `PLANVIEW_ID` |

---

## A1: ISO Code of Account Present (COR + SAB) - ADR

- **Type:** Completeness · **Blocking:** **Yes** · **Data product:** ADR
- **Implementation:** `check_adr_a1` (uses `_a1_value_valid` for the
  ISO_COR / SAB markers + a join against the COA master).
- **Reference dataset:** `ACCE_COA_MASTER`
  (`SPLIT_PART(ADR.COMPLETE_WBC, '.', 1) → ACCE_COA_MASTER.ICARUS_COA`,
  lookup `ISO_COR` and `SAB`).

A row passes when **all three** hold:

1. `COMPLETE_WBC` is non-null and non-blank.
2. The leading dot-segment (the ICARUS Code of Account group) resolves
   to a valid `ISO_COR` in the COA master.
3. The same COA group resolves to a valid `SAB` in the COA master.

`ISO_COR` / `SAB` are considered **invalid** when null, blank, or when
the value contains the substrings `ERROR` or `N/A` (case-insensitive).
Both markers cover the spectrum of COA-master "I haven't been mapped
yet" rows seen in production (e.g. `ERROR: #N/A`, raw `#N/A`, blank).

### COA derivation

```
COA_GROUP = SPLIT_PART(COMPLETE_WBC, '.', 1)
```

Examples:

| `COMPLETE_WBC` | Derived COA group |
|---|---|
| `313.1.10.10` | `313` |
| `322.0.5.18`  | `322` |
| `337.1.10.20` | `337` |
| `NULL` / blank | (rule fails, no derivation) |

### "Best-available" mapping when the master has duplicates

The COA master may carry several rows for the same `ICARUS_COA` (one
per detailed sub-code). The rule mirrors the SQL spec's
`FIRST_VALUE(...) ORDER BY IFF(invalid, 1, 0)` semantics by stable-
sorting invalid rows after valid rows, then deduplicating per
`ICARUS_COA`. The resolved `ISO_COR` and `SAB` are therefore the best
available values for that COA group:

- a valid mapping wins over an `ERROR` / `NULL` mapping;
- if no valid mapping exists, an invalid one is kept (so the validity
  check fails with the actual marker rather than silently passing).

The two lookups are computed independently - a COA group whose
`ISO_COR` is valid but `SAB` is `ERROR` still fails the rule.

### Why it matters

`ISO_COR` and `SAB` together pick the EMMA normalization factor for
cost benchmarking. Without them, ADR cost data cannot be normalized
across projects, the row is unusable for downstream cost analytics.
Hence A1 is **blocking**.

### Failure modes

- Missing `COMPLETE_WBC` or `PLANVIEW_ID` column → all rows fail.
- Reference dataset unavailable → `CustomRuleNotEvaluated` (Step 6
  shows *Not evaluated*).
- Reference dataset present but missing `ICARUS_COA` / `ISO_COR` /
  `SAB` columns → all rows fail.

### Inputs

| Alias            | Physical column |
|------------------|-----------------|
| Project Key      | `PLANVIEW_ID`   |
| Complete WBC     | `COMPLETE_WBC`  |

### Decision matrix

| `COMPLETE_WBC`        | Resolved `ISO_COR` | Resolved `SAB` | Result   |
|-----------------------|--------------------|----------------|----------|
| Missing / blank       | (any)              | (any)          | **FAIL** |
| Present, COA orphan   | NaN (no master row)| NaN            | **FAIL** |
| Present               | invalid            | (any)          | **FAIL** |
| Present               | valid              | invalid        | **FAIL** |
| Present               | valid              | valid          | PASS     |

---

## A2: Location + Estimate Date Present & Valid (ADR)

- **Type:** Completeness & Validity · **Blocking:** No · **Data product:** ADR
- **Implementation:** `check_adr_a2` (uses `_is_filled` for completeness +
  a `str.fullmatch` against `ADR_A2_DATE_PATTERN` for validity + a join
  against the Planview reference). Mirrors `check_ept_e2` but operates on
  the ADR data product and uses `COST_UPDATE` as the estimate basis date.
- **Reference dataset:** `VWS_GP_STANDARD_SHARE`
  (`ADR.PLANVIEW_ID → VWS_GP_STANDARD_SHARE.PROJECT_ID`, lookup `COUNTRY`).

A row passes when **all** hold:

1. `COST_UPDATE` (estimate basis date, in ADR) is non-null and non-blank
   (**Completeness**).
2. `COST_UPDATE` matches the fiscal quarter-year shape `[1-4]Q<YYYY>` — a
   quarter digit `1`-`4`, the literal `Q` (case-insensitive), then a 4-digit
   year, e.g. `2Q2019`, `4Q2015`, `3Q2022` (**Validity**). A populated but
   malformed value (e.g. `"N/A"`, `"2019"`, `"5Q2019"`) fails the rule even
   though it satisfies completeness. `COST_UPDATE` is a fiscal *period*, not
   a calendar date.
3. `COUNTRY` (project location) is non-null and non-blank in the Planview
   reference, **after** joining `ADR.PLANVIEW_ID` against
   `VWS_GP_STANDARD_SHARE.PROJECT_ID`. An unmatched `PLANVIEW_ID` is
   treated as a missing `COUNTRY` (i.e. the row fails A2).

**Why it matters.** COUNTRY + COST_UPDATE together pick the correct CU
period for EMMA normalization. COST_UPDATE is the *estimate basis date*
(a fiscal quarter, e.g. `2Q2019`), not the data-entry date.

**Failure modes:**

- Missing `COST_UPDATE` or `PLANVIEW_ID` column → all rows fail.
- `COST_UPDATE` populated but not in the `[1-4]Q<YYYY>` format → that row
  fails (Validity).
- Reference dataset unavailable → `CustomRuleNotEvaluated` (Step 6 shows
  *Not evaluated*).
- Reference dataset present but missing `PROJECT_ID` / `COUNTRY` → all
  rows fail.

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| Estimate Basis Date | `COST_UPDATE` |
| Project Key         | `PLANVIEW_ID` |

---

## A3: Statistical WBC-to-ISO mapping ratio (ADR)

- **Type:** Statistical Outlier · **Blocking:** No · **Data product:** ADR
- **Implementation:** `check_adr_a3` (with `_resolve_coa_master_lookups`
  shared with A1).
- **Reference dataset:** `ACCE_COA_MASTER`
  (`SPLIT_PART(ADR.COMPLETE_WBC, '.', 1) → ICARUS_COA`, lookup
  `ISO_COR` and `SAB`).

A3 is the statistical counterpart of A1: where A1 enforces that every
row resolves to a valid `ISO_COR + SAB`, A3 asks whether each ISO
bucket *holds too many distinct ADR WBCs*. A high `WBC_TO_ISO_RATIO`
means many ADR `COMPLETE_WBC` strings collapse through the same
3-digit COA group into the same ISO mapping, and the rule flags the
buckets that aggregate beyond what the ADR portfolio's distribution
considers normal.

A3 mirrors EPT E3 against the ADR data product. Same row-level
verdict / group-level threshold pattern, same materiality framing,
same global-`P90` baseline, but the ratio is sourced from
`COUNT(DISTINCT COMPLETE_WBC)` per resolved `(ISO_COR, SAB)` bucket
instead of `COUNT(DISTINCT WBC_LEVEL_5)` per ISO key. A3 also exposes
the same two opt-in toggles as E3: **project-scoped percentile**
(per-`PLANVIEW_ID` baseline) and **uniform 1:1 mapping detection**.

### Algorithm

1. **Per-row eligibility.** A row enters the aggregation when:

   ```
   COMPLETE_WBC populated
   AND ICARUS_COA (= SPLIT_PART(COMPLETE_WBC, '.', 1)) resolves to a
       valid ISO_COR in the COA master
   AND the same COA group resolves to a valid SAB in the COA master
   ```

   Validity rejects null / blank / `ERROR` / `N/A` (case-insensitive), same `_a1_value_valid` semantics A1 uses. Rows that fail any of
   these are **PASS** for A3 because A1 already covers the WBC / COR /
   SAB completeness gap.

2. **Bucket metric.** Group eligible rows by `(ISO_COR, SAB)`, then:

   ```
   WBC_TO_ISO_RATIO = COUNT(DISTINCT COMPLETE_WBC)
   hours_sum         = SUM(COST_TOTAL_HOURS)   (null → 0)
   cost_sum          = SUM(COST_TOTAL_COST)    (null → 0)
   ```

3. **Global P90.** Across all eligible buckets (`ratio ≥ 1`):

   ```
   P90_WBC_TO_ISO_RATIO = quantile(WBC_TO_ISO_RATIO, 0.90)
   ```

4. **Materiality.** A bucket is *material* when:

   ```
   hours_sum > 0
   OR cost_sum >= ADR_A3_MATERIALITY_USD   (default 100,000)
   ```

5. **Per-bucket verdict.** A bucket **fails** when:

   ```
   ratio > P90 AND material
   ```

6. **Row-level verdict.** Every row whose resolved `(ISO_COR, SAB)`
   bucket is flagged inherits the FAIL. Every other eligible row, plus
   every NOT_APPLICABLE row, passes.

### Project scope (project_scoped = True, opt-in via the rule card)

- The group key becomes `(PLANVIEW_ID, ISO_COR, SAB)` and the P90 is
  recomputed *within each PLANVIEW_ID partition* (`PARTITION BY
  PLANVIEW_ID`). Each project gets its own statistical baseline, so a
  project with naturally fine-grained WBC discipline isn't dragged down
  by peers that aggregate aggressively.
- `PLANVIEW_ID` was already in A3's static `required_columns`, so the
  CDE-coverage check already enforces it; the toggle additionally
  treats rows lacking `PLANVIEW_ID` as PASS (A2 already covers the
  missing-project linkage).
- Mirrors EPT E3's `project_scoped` toggle, same wording, same
  behaviour, same per-project P90 framing.

### Uniform 1:1 mapping detection (detect_uniform_mapping = True, opt-in)

- Off by default. When on, after the regular percentile-based outlier
  verdict the rule **also** fails every *material* bucket whose
  `ratio == 1` (each `(ISO_COR, SAB)` bucket holds exactly one distinct
  `COMPLETE_WBC`). A suspiciously uniform 1:1 distribution is usually
  a sign that the mapping process was bypassed and source codes were
  copied 1:1 into the ISO bucket instead of being aggregated.
- The percentile fail and the uniform-1:1 fail combine with **OR**: both signals coexist when the toggle is on.
- The materiality filter still applies, so planning / structural-only
  buckets with `ratio == 1` are not flagged.
- Off by default because a small / early dataset can legitimately show
  `ratio == 1` for every bucket; turn it on when you want to surface
  mapping-discipline issues.

### NOT_APPLICABLE (treated as PASS) cases

A3 returns Booleans only. These cases collapse to PASS so they don't
double-penalise A1 / structural completeness:

- **`COMPLETE_WBC` missing**: A1's territory.
- **Resolved `ISO_COR` / `SAB` invalid** (null / blank / `ERROR` /
  `N/A`) - A1's territory.
- **Eligible-mapping population below `ADR_A3_MIN_MAPPING_POPULATION`**
  (default `10`) - too few buckets to derive a meaningful P90.
- **Bucket not material**: planning / structural-only mappings are
  exempt regardless of how many distinct WBCs flow through them.

### ADR-specific interpretation note

ADR's ISO mapping is derived from only the *first* segment of
`COMPLETE_WBC`, so detailed WBCs like `313.1.10.10`, `313.1.20.10`,
`313.1.55.30` all collapse onto the same `ICARUS_COA = 313` and
therefore the same `(ISO_COR, SAB)`. The `WBC_TO_ISO_RATIO` can
naturally be high - A3 is measuring the *loss of detail* created by
the available mapping path. A `FAIL` should be read as a **mapping
quality concern that warrants SME review**, not as a definitive
"this data is wrong" signal.

It's also possible for a small number of mapping-level failures to
affect a large number of ADR rows (when one over-aggregating bucket
covers many estimate items). When interpreting A3, look at both the
mapping-level fail rate and the row-level impact count.

### Why it matters

`ISO_COR` and `SAB` together pick the EMMA normalization factor; the
analytic granularity of the normalized comparison is bounded by how
many distinct ADR WBCs roll through one bucket. When that count is far
above the portfolio norm, the ISO bucket is hiding meaningful
source-system detail and the comparison's resolving power degrades.

### Failure modes

- Missing `PLANVIEW_ID`, `COMPLETE_WBC`, `COST_TOTAL_HOURS`, or
  `COST_TOTAL_COST` column → all rows fail (structural
  incompleteness; same convention as the other custom rules).
- Reference dataset unavailable → `CustomRuleNotEvaluated` (Step 6
  shows *Not evaluated*).
- Reference dataset present but missing `ICARUS_COA` / `ISO_COR` /
  `SAB` columns → all rows fail.

### Inputs

| Alias              | Physical column      |
|--------------------|----------------------|
| Project Key        | `PLANVIEW_ID`        |
| Complete WBC       | `COMPLETE_WBC`       |
| Total Hours        | `COST_TOTAL_HOURS`   |
| Total Cost         | `COST_TOTAL_COST`    |

### Options

| Key | Widget | Default | Effect |
|-----|--------|---------|--------|
| `threshold_percentile` | `st.selectbox` | `0.90` (P90) | Percentile cutoff applied to the WBC-to-ISO ratio distribution. Choices: P75 (lenient), **P90 (recommended)**, P95 (strict), P99 (very strict). |
| `project_scoped` | `st.toggle` | `False` | Switches the percentile baseline from global to per-`PLANVIEW_ID` (group key becomes `(PLANVIEW_ID, ISO_COR, SAB)`). |
| `detect_uniform_mapping` | `st.toggle` | `False` | When on, *material* buckets with `ratio == 1` also fail (OR'd with the percentile branch) - surfaces suspiciously uniform 1:1 mappings. |

### Tunables

| Constant                          | Default     | Effect |
|-----------------------------------|------------:|--------|
| `ADR_A3_PERCENTILE`               | `0.90`      | Default percentile (overridable via the `threshold_percentile` option). Defines the PASS / FAIL boundary on the bucket ratio (`ratio > P` ⇒ candidate FAIL). |
| `ADR_A3_MATERIALITY_USD`          | `100_000.0` | Below-threshold buckets with zero hours are NOT_APPLICABLE (every row passes). |
| `ADR_A3_MIN_MAPPING_POPULATION`   | `10`        | Below-threshold populations skip percentile computation entirely (every row passes). Same floor applies to the total bucket count in project scope. |

### Decision matrix

| Valid ISO mapping | Material bucket | `ratio` vs P90 | `detect_uniform_mapping` | Result |
|---|---|---|---|---|
| No                | (any)           | (any)          | (any)  | PASS *(A1 territory)* |
| Yes               | No              | (any)          | (any)  | PASS |
| Yes               | Yes             | ≤ P90          | Off    | PASS |
| Yes               | Yes             | ≤ P90, `ratio == 1` | On | **FAIL** *(uniform branch)* |
| Yes               | Yes             | ≤ P90, `ratio > 1`  | On | PASS |
| Yes               | Yes             | > P90          | (any)  | **FAIL** *(percentile branch)* |
| Yes (any)         | (any)           | population < `ADR_A3_MIN_MAPPING_POPULATION` | (any) | PASS |

In **project scope** (`project_scoped = True`) every P90 comparison
above is local to the row's `PLANVIEW_ID`; rows lacking `PLANVIEW_ID`
pass regardless of bucket state.

---

## A4: Core quantities populated & non-negative project totals (ADR)

- **Type:** Completeness & Validity · **Blocking:** No · **Data product:** ADR
- **Implementation:** `check_adr_a4` (with `_classify_a4_scope` and
  `_classify_a4_quantity` for the discipline mapping).

A4 is a **project-level Completeness & Validity rule with a row-level
verdict**. For each `PLANVIEW_ID` it asks two questions: (a) of the seven
core quantity types this project's scope implies, is each one actually
populated? and (b) is the project's *total* `QTY_QUANTITY` non-negative?

The seven core quantity types are: piping LF, concrete CY, steel tons,
cable length, transmitter / instrument count, equipment count, module
count. The rule does *not* require every project to carry all seven -
completeness is judged **relative to the project's own scope**.

### Algorithm

For each `PLANVIEW_ID`:

1. **Determine expected core quantity types.** A type is *expected*
   when at least one item in the project has an `ITEM_TYPE` /
   `ITEM_DESCRIPTION` that matches its scope pattern (see classifier
   table below). Quantity and UOM are **not** consulted at this step
   - an item type that *implies* the scope is enough.

2. **Determine populated core quantity types.** A type is *populated*
   when at least one item in the project has a strictly positive
   `QTY_QUANTITY` AND its (`ITEM_TYPE`, `QTY_UOM`) classifies into
   that core type (per the right-hand column of the classifier
   table).

3. **Compare expected vs. populated.** A project is flagged when there
   is at least one core type where `EXPECTS_X = 1` AND `HAS_X = 0`.

4. **Check the project quantity total (Validity).** A project is also
   flagged when its total `QTY_QUANTITY` (the SUM across every row of
   the project) is **strictly negative**. Individual rows may carry
   negative quantities (corrections / reversals) without failing - only
   the project aggregate is checked. A total of exactly zero is *not*
   negative and passes. Project **fails** A4 iff it is flagged by step 3
   **or** step 4.

5. **Row-level verdict.** A row fails iff its `PLANVIEW_ID` is
   flagged. Rows with null/blank `PLANVIEW_ID` pass, they cannot be
   assigned to a project group (E7 / A2 already cover the missing-
   project linkage).

### Discipline classifier (scope detection vs. population detection)

Some categories use *broader* patterns for scope detection than for
population detection - by design. For example, an item with
`ITEM_TYPE = EstimatePump` implies equipment scope regardless of UOM,
but only the specific (`EstimatePump`, `Parallel Pumps`) pair counts
as a populated equipment quantity. This split mirrors the spec's
distinction between "what the project implies" and "what counts as a
populated quantity for that scope".

| Core type           | Scope detection (`ITEM_TYPE` / `ITEM_DESCRIPTION`)                                              | Population detection (`ITEM_TYPE`, `QTY_UOM`)                                                                |
|---------------------|------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| `PIPING_LF`         | `ITEM_TYPE` ∈ { `EstimateAbovegroundInstrumentPiping`, `EstimatePipingUnderground`, `EstimatePipingPneumatic` } | scope match AND UOM ∈ { `ft`, `m` }                                                                          |
| `CONCRETE_CY`       | `ITEM_TYPE` contains `Foundation` or `Concrete`                                                 | scope match AND UOM ∈ { `yd³`, `m³` } (`CY`, `yds³` aliased)                                                 |
| `STEEL_TONS`        | `ITEM_TYPE` contains `SteelStructure` or `Piperack`                                             | scope match AND UOM ∈ { `t`, `t,sht` }                                                                       |
| `CABLE_LENGTH`      | `ITEM_TYPE` contains `Electrical` (intentionally not `FieldInstrument`, see notes)             | scope match AND UOM ∈ { `ft`, `m` }                                                                          |
| `TRANSMITTER_COUNT` | `ITEM_TYPE` contains `FieldInstrument`                                                          | scope match AND UOM ∈ { `transmitter`, `transmitters`, `pressure gauges`, `thermowells`, `thermocouples`, `control valves`, `flow elements`, `level gauges`, `level switches`, `pressure switches`, `junction boxes`, `i/p transducers`, `solenoid valves` } |
| `EQUIPMENT_COUNT`   | `ITEM_TYPE` ∈ the major-equipment allow-list (`EstimatePump`, `EstimateGasTurbine`, `EstimateTankage`, …) | exact (`ITEM_TYPE`, `UOM`) pair on the allow-list (e.g. `EstimatePump + parallel pumps`, `EstimateTankage + tanks`) |
| `MODULE_COUNT`      | `ITEM_TYPE` *or* `ITEM_DESCRIPTION` contains `Module` or `Modular`                              | scope match AND UOM ∈ { `module`, `modules`, `each`, `ea`, `unit`, `units` }                                  |

UOM matching is case-insensitive after stripping. The A8 alias map
(`CY` ↔ `yd³`, `yds³` ↔ `yd³`, `m^3` ↔ `m³`, …) is reused so the
classifier is robust to source-system spelling variation.

### Why scope ≠ population (the asymmetry)

A natural question: why does scope detection accept any UOM but
population detection require a specific UOM? Because that's exactly
what A4 is checking - *did the project record the right kind of
quantity?* If a foundation item is recorded with `QTY_UOM = "EA"`
instead of `yd³`, the project still has concrete scope (the item type
implies it), but no `CONCRETE_CY` quantity is populated → FAIL. That
mismatch is what A4 surfaces.

### Failure modes

- Missing required column → all rows fail (structural incompleteness;
  same convention as the other custom rules).
- Project with at least one expected core type and no matching
  populated row → all rows of that project fail.

### Notes

- **Conservative classifier.** The (item type, UOM) allow-list for
  EQUIPMENT_COUNT and the closed list of piping ITEM_TYPEs are
  intentionally narrow. The intent is to count *major equipment items*, not nozzles, manways, trays, baffles, mist eliminators, peep
  doors, or other subcomponents. Expanding the allow-list is a
  one-line change once business signs off on the new pairs.
- **CABLE_LENGTH excludes FieldInstrument.** A8 maps
  `EstimateFieldInstrumentGroup + ft/m` to `CABLE_LENGTH`; A4
  intentionally does not, per spec §8.4 ("conservative … unless
  approved by business review").
- **Module scope is sparse.** `MODULE_COUNT` will rarely be expected
  in real datasets; the rule still evaluates it for completeness.
- **A row's `PLANVIEW_ID` may be filled even when its scope /
  population row doesn't classify.** That row simply does not
  contribute to any `EXPECTS_*` or `HAS_*` flag. Its project's pass /
  fail is decided by the rest of the project's rows.

### Inputs

| Alias              | Physical column      |
|--------------------|----------------------|
| Project Key        | `PLANVIEW_ID`        |
| Item Type          | `ITEM_TYPE`          |
| Item Description   | `ITEM_DESCRIPTION`   |
| Quantity           | `QTY_QUANTITY`       |
| Quantity UOM       | `QTY_UOM`            |

### Decision matrix (per project)

| Condition                                                  | Project verdict |
|------------------------------------------------------------|-----------------|
| At least one `EXPECTS_X = 1` AND `HAS_X = 0`                | **FAIL**        |
| Every `EXPECTS_X = 1` has a matching `HAS_X = 1`            | PASS            |
| No core type is expected (project too small / off-pattern)  | PASS            |

---

## A5: Design details present when quantity exists (ADR)

- **Type:** Consistency · **Blocking:** No · **Data product:** ADR
- **Implementation:** `check_adr_a5`.

A row passes when one of the following holds:

1. The estimate item has **no non-zero quantity** (out-of-scope, treated
   as PASS).
2. The estimate item has a **non-zero quantity** *and* a populated
   `DESIGN_PARAMETER_VALUE`.

A row fails when a non-zero quantity exists *but* no design parameter
value is present for the same `ROW_ID`.

### Where the inputs come from

A5 operates on the **denormalized ADR data product** built by
[src/data_product_builder.py](../src/data_product_builder.py), which
left-joins the child tables onto the primary item record:

| Source table                          | Source column           | Denormalized column      | Notes |
|---------------------------------------|-------------------------|--------------------------|-------|
| `ADR_FACT_ESTIMATEQTYRESULTS` (1:N)   | `QUANTITY`              | `QTY_QUANTITY`           | The builder aggregates the 1:N child rows by `ROW_ID` (`SUM` for numeric columns), so `QTY_QUANTITY` is the **sum** of the underlying `QUANTITY` rows for that item. |
| `ADR_DIM_ESTIMATEDESIGNDETAILS` (1:1) | `DESIGN_PARAMETER_VALUE`| `DESIGN_PARAMETER_VALUE` | 1:1 join, the column is preserved as-is (already prefixed with `DESIGN_`). |

### Pass / fail matrix

| `HAS_QUANTITY` | `HAS_DESIGN_DETAIL` | Result |
|---:|---:|---|
| 0 | 0 | PASS |
| 0 | 1 | PASS |
| 1 | 0 | **FAIL** |
| 1 | 1 | PASS |

Where:

- `HAS_QUANTITY = (QTY_QUANTITY is non-null) AND (QTY_QUANTITY <> 0)`.
  Null quantities are treated as zero - a row is "with quantity" only
  when the aggregate is genuinely non-zero. Negative aggregates count as
  non-zero (the rule does not validate sign).
- `HAS_DESIGN_DETAIL = DESIGN_PARAMETER_VALUE is non-null and non-blank`
  (whitespace-only strings are treated as blank, same `_is_filled`
  semantics used by E1 / E4 / A2).

### Why it matters

A quantity without supporting design information cannot be normalized,
compared across items, or validated, the analytical value of the
estimate drops sharply. A5 is the lightweight gate that surfaces the
most consequential omission: **a quantity exists but the engineering
context that explains it does not.**

### Failure modes

- Missing `QTY_QUANTITY` or `DESIGN_PARAMETER_VALUE` column → all rows
  fail (structural incompleteness; same convention as the other custom
  rules).

### Notes

- The current version does not validate the *type* of design detail, any populated `DESIGN_PARAMETER_VALUE` is sufficient. Adding a
  required-parameter list (e.g. material grade, schedule, nominal size)
  is a future extension.
- Because the data product builder aggregates `QUANTITY` by `SUM`, two
  child rows with equal-and-opposite values (e.g. `+5` and `-5`) collapse
  to a zero aggregate and the rule treats the item as "no quantity". In
  practice this is a degenerate case for ADR estimates - quantities are
  typically non-negative, and the SQL implementation in §14 of the rule
  spec mirrors the same behaviour via `COUNT_IF(QUANTITY <> 0) > 0`,
  which would also flag at least one non-zero row in either direction.

### Inputs

| Alias                    | Physical column          |
|--------------------------|--------------------------|
| Quantity                 | `QTY_QUANTITY`           |
| Design Parameter Value   | `DESIGN_PARAMETER_VALUE` |

---

## A6: Construction hours present when quantity exists (ADR)

- **Type:** Consistency · **Blocking:** No · **Data product:** ADR
- **Implementation:** `check_adr_a6`.

A row passes when one of the following holds:

1. The estimate item has **no non-zero quantity** (out-of-scope, treated
   as PASS, same one-directional framing as A5).
2. The estimate item has a **non-zero quantity** *and* at least one of
   the two construction-hours aggregates is strictly greater than zero.

A row fails when a non-zero quantity exists *but* both
`COST_TOTAL_HOURS` and `COST_DB_TOTAL_HOURS` are zero / null / negative
for the same `ROW_ID`.

### Where the inputs come from

A6 operates on the **denormalized ADR data product**. Both the quantity
and the hours columns live on 1:N child tables of the item record, so
[src/data_product_builder.py](../src/data_product_builder.py) aggregates
them by `ROW_ID` (`SUM` for numeric columns) before the rule runs:

| Source table                          | Source column      | Denormalized column     | Notes |
|---------------------------------------|--------------------|-------------------------|-------|
| `ADR_FACT_ESTIMATEQTYRESULTS` (1:N)   | `QUANTITY`         | `QTY_QUANTITY`          | Sum of all quantity rows for the item, same input A5 uses. |
| `ADR_FACT_ESTIMATECOSTRESULTS` (1:N)  | `TOTAL_HOURS`      | `COST_TOTAL_HOURS`      | Sum of construction hours across cost rows. |
| `ADR_FACT_ESTIMATECOSTRESULTS` (1:N)  | `DB_TOTAL_HOURS`   | `COST_DB_TOTAL_HOURS`   | Sum of the alternate hours source - A6 accepts either. |

### Pass / fail matrix

| `HAS_QUANTITY` | `HAS_CONSTRUCTION_HOURS` | Result |
|---:|---:|---|
| 0 | 0 | PASS |
| 0 | 1 | PASS |
| 1 | 0 | **FAIL** |
| 1 | 1 | PASS |

Where:

- `HAS_QUANTITY = (QTY_QUANTITY is non-null) AND (QTY_QUANTITY <> 0)`.
  Same definition as A5 - null and zero quantities both count as "no
  quantity"; negative aggregates count as non-zero.
- `HAS_CONSTRUCTION_HOURS = (COST_TOTAL_HOURS > 0) OR (COST_DB_TOTAL_HOURS > 0)`.
  Null inputs are coerced to zero. Per spec §12 negative aggregates do
  **not** count as hours present, so the comparison is strictly `> 0`
  (not `<> 0`).

### Why it matters

Quantity and construction hours together drive productivity analysis
(hours per unit, unit-rate benchmarking, EMMA normalization). A
quantity without matching hours is not useful for productivity work,
which is the primary reason ADR estimates are consumed downstream.

### Failure modes

- Missing `QTY_QUANTITY`, `COST_TOTAL_HOURS`, or `COST_DB_TOTAL_HOURS`
  column → all rows fail (structural incompleteness; same convention as
  the other custom rules).

### Notes

- **One-directional check.** Hours without a quantity is **PASS**, not
  fail - A6 only enforces the implication
  `quantity ⇒ construction hours`. Items with hours but no quantity are
  out of scope.
- **Either column is sufficient.** A6 does not require both
  `TOTAL_HOURS` and `DB_TOTAL_HOURS` to be populated; one positive
  aggregate is enough.
- **Aggregation caveat.** Because the data product builder aggregates
  by `SUM`, a hypothetical row pattern like `+10` and `-10` collapses to
  a zero aggregate, the rule then treats the item as having no hours.
  The rule's row-level SQL spec (§14) uses
  `COUNT_IF(COALESCE(TOTAL_HOURS, 0) > 0 OR COALESCE(DB_TOTAL_HOURS, 0) > 0) > 0`
  which would still flag a positive row in either direction; in
  practice ADR construction hours are non-negative so the two
  formulations agree on real data.

### Inputs

| Alias                       | Physical column         |
|-----------------------------|-------------------------|
| Quantity                    | `QTY_QUANTITY`          |
| Construction Hours          | `COST_TOTAL_HOURS`      |
| Construction Hours (DB)     | `COST_DB_TOTAL_HOURS`   |

---

## A7: Within-discipline quantity / hour ratio outlier (ADR)

- **Type:** Statistical Outlier · **Blocking:** No · **Data product:** ADR
- **Implementation:** `check_adr_a7`.
- **Optional reference dataset:** `VWS_GP_STANDARD_SHARE`
  (`PLANVIEW_ID → PROJECT_ID`, lookup `E05_DEPARTMENT` + `BUSINESS`).
  Only consulted when the `segment_by_project_type` toggle is on; the
  default discipline-only path runs without any reference.

A per-item statistical rule with row-level verdict. A7 looks for items
whose **hours-per-quantity ratio** is unusual *within its peer group*, same `ITEM_TYPE` and same `QTY_UOM`. The threshold is derived from
the segment itself (IQR), not from a fixed benchmark.

### Algorithm

1. **Per-row eligibility.** A row enters the population only when:

   ```
   QTY_QUANTITY > 0
   AND COST_TOTAL_HOURS > 0
   AND ITEM_TYPE  is non-null / non-blank
   AND QTY_UOM    is non-null / non-blank
   ```

   Anything else is **not applicable** and passes (the rule cannot
   produce a verdict without a calculable ratio and a segment to
   compare against).

2. **Ratio.** For each eligible row:

   ```
   HOURS_PER_QUANTITY = COST_TOTAL_HOURS / QTY_QUANTITY
   ```

   Both numerator and denominator are SUM-aggregated by `ROW_ID` upstream
   (the data product builder collapses the 1:N child rows of the cost
   and quantity facts).

3. **Segment statistics.** Eligible rows are partitioned by
   `(ITEM_TYPE, QTY_UOM)` (default) or by the extended key
   `(ITEM_TYPE, QTY_UOM, E05_DEPARTMENT, BUSINESS)` when the
   `segment_by_project_type` toggle is on
   (see [Project-type segmentation](#project-type-segmentation-segment_by_project_type-a7)).
   For each segment:

   ```
   Q1   = quantile(HOURS_PER_QUANTITY, 0.25)
   Q3   = quantile(HOURS_PER_QUANTITY, 0.75)
   IQR  = Q3 - Q1
   ```

4. **Mild bounds (the FAIL boundary).**

   ```
   MILD_LOWER = Q1 - 1.5 × IQR
   MILD_UPPER = Q3 + 1.5 × IQR
   ```

   A row **fails** when its ratio is below `MILD_LOWER` or above
   `MILD_UPPER`.

   The 3.0× extreme multiplier is documented as a constant
   (`ADR_A7_EXTREME_IQR_MULTIPLIER`) so future code can classify
   severity, but the Boolean check uses only the mild bound, every
   extreme outlier is also a mild outlier and therefore a FAIL.

### NOT_APPLICABLE (treated as PASS) cases

A7 does not surface a separate "NA" bucket, it returns Booleans only.
The cases below are mapped to PASS to avoid double-counting against
rules that already cover those gaps:

- **Ratio cannot be calculated** (qty or hours missing / zero / negative)
  - A6 covers the missing-hours case for non-zero quantities.
- **`ITEM_TYPE` or `QTY_UOM` blank**: no segment to compare against.
- **Segment population below `ADR_A7_MIN_POPULATION`** (default `10`)
  - too small to derive thresholds. When `segment_by_project_type` is
  on, the same floor is applied **per extended segment** so a
  thinly-populated `(ITEM_TYPE, QTY_UOM, E05_DEPARTMENT, BUSINESS)`
  bucket does not flag every row inside it as an outlier of itself.
- **Segment `IQR == 0`**: no variation across the segment, every
  observation sits on the median; outlier detection is not meaningful.
- **Row whose project-type cannot be resolved** (only when
  `segment_by_project_type` is on) - missing `PLANVIEW_ID`, unmatched
  `PROJECT_ID`, or null/blank `E05_DEPARTMENT` / `BUSINESS` from the
  join - NOT_APPLICABLE → PASS. A1 / A2 already cover the
  referential-integrity / completeness gap.

### Where the inputs come from

A7 operates on the **denormalized ADR data product**. `ITEM_TYPE` is a
pass-through from the primary item table; the other three columns come
from the SUM-aggregated 1:N child tables:

| Source table                          | Source column   | Denormalized column   | Notes |
|---------------------------------------|-----------------|-----------------------|-------|
| `ADR_DIM_ESTIMATEITEMRECORD` (1:1)    | `ITEM_TYPE`     | `ITEM_TYPE`           | Pass-through. |
| `ADR_FACT_ESTIMATEQTYRESULTS` (1:N)   | `QUANTITY`      | `QTY_QUANTITY`        | Sum across qty rows for the item. |
| `ADR_FACT_ESTIMATEQTYRESULTS` (1:N)   | `QTY_UOM`       | `QTY_UOM`             | The data product builder applies `first` aggregation for non-numeric columns; the SQL spec uses `MAX(QTY_UOM)`. Real estimates keep one UOM per item, so both formulations agree on production data. |
| `ADR_FACT_ESTIMATECOSTRESULTS` (1:N)  | `TOTAL_HOURS`   | `COST_TOTAL_HOURS`    | Sum across cost rows for the item. |

### Why it matters

A7 is the productivity sanity check. Hours per cubic yard, hours per
ton, hours per metre, these ratios are tight within a discipline
because they reflect physical effort. A row that lies far outside its
segment's IQR almost always points to one of: an incorrect quantity, an
incorrect hours total, a UOM mismatch, or a genuinely unusual project
condition. A7 surfaces those rows for review; it does **not** assert
they are wrong.

### Notes

- **Thresholds are derived from the data**, not hard-coded. There is no
  "correct" hours-per-quantity ratio, the rule benchmarks each item
  against its own peers.
- **Discipline-only is the default cut.** The `(ITEM_TYPE, QTY_UOM)`
  segment is the recommended initial baseline; the project-type
  segmentation toggle extends the key for users who need it (see
  below).
- **Schema-level missing column → all rows fail**, mirroring the
  convention used by E1 / E3 / E4 / E6 / A5 / A6. When
  `segment_by_project_type` is on, `PLANVIEW_ID` becomes structurally
  required too - Step 4.2's CDE-coverage badge surfaces the gap before
  the rule is even allowed to run.
- **Segmented mode requires the reference.** When
  `segment_by_project_type` is on and `VWS_GP_STANDARD_SHARE` is
  unavailable (or missing `E05_DEPARTMENT` / `BUSINESS`), the rule
  raises `CustomRuleNotEvaluated`, it never silently falls back to the
  discipline-only IQR baseline.
- **Failed records are review candidates, not errors.** A FAIL means
  the ratio is unusual; it does not prove the data is wrong. The
  threshold should be revisited after the first profiling pass.

### Project-type segmentation (`segment_by_project_type`, A7)

Hours-per-quantity expectations differ even within a single discipline
across project archetypes - a brownfield refinery brownfield tie-in and
a greenfield deepwater FPSO can need wildly different labour for the
same `(ITEM_TYPE, QTY_UOM)`. Pooling them widens the discipline-only
IQR enough that genuine within-archetype outliers hide in the middle.
The toggle splits the population before deriving the IQR, mirrors the
[E6 segmentation toggle](#project-type-segmentation-segment_by_project_type).

When on:

1. Each row's `PLANVIEW_ID` is joined to `VWS_GP_STANDARD_SHARE` on
   `PLANVIEW_ID = PROJECT_ID` to recover its archetype tags
   (`E05_DEPARTMENT` for brownfield / greenfield, `BUSINESS` for the
   business line, e.g. upstream / downstream / chemical / LNG).
2. The segment key becomes the **composite tuple** `(ITEM_TYPE,
   QTY_UOM, E05_DEPARTMENT, BUSINESS)`. Each bucket derives its own
   `Q1`, `Q3`, and IQR; the PASS band is bucket-local.
3. The same per-segment minimum-population floor
   (`ADR_A7_MIN_POPULATION`) applies - segments with fewer eligible
   rows fall through to NOT_APPLICABLE → PASS.
4. Rows whose project-type cannot be resolved (missing `PLANVIEW_ID`,
   unmatched `PROJECT_ID`, null `E05_DEPARTMENT` / `BUSINESS`) are
   NOT_APPLICABLE → PASS.

When off (default) the rule behaves exactly as it did before this
feature, one IQR per `(ITEM_TYPE, QTY_UOM)` across the dataset.

### Inputs

| Alias                  | Physical column      |
|------------------------|----------------------|
| Item Type              | `ITEM_TYPE`          |
| Quantity               | `QTY_QUANTITY`       |
| Quantity UOM           | `QTY_UOM`            |
| Construction Hours     | `COST_TOTAL_HOURS`   |
| Project Key *(when `segment_by_project_type` is on)* | `PLANVIEW_ID` |

### Options

| Key | Widget | Default | Effect |
|-----|--------|---------|--------|
| `threshold_iqr_multiplier` | `st.selectbox` | `1.5` | IQR multiplier used to derive the per-segment PASS band. Choices: **1.5×IQR (mild - recommended)**, 2.0×IQR, 3.0×IQR (extreme). |
| `segment_by_project_type` | `st.toggle` | `False` | When on, the IQR baseline is computed within each `(ITEM_TYPE, QTY_UOM, E05_DEPARTMENT, BUSINESS)` segment resolved via `VWS_GP_STANDARD_SHARE`. Off → one IQR per `(ITEM_TYPE, QTY_UOM)` across every eligible row. |

### Tunables

| Constant                         | Default | Effect |
|----------------------------------|--------:|--------|
| `ADR_A7_MILD_IQR_MULTIPLIER`     | `1.5`   | Default IQR multiplier (overridable via the `threshold_iqr_multiplier` option). Defines the PASS / FAIL boundary (`Q1 - k·IQR` … `Q3 + k·IQR`). |
| `ADR_A7_EXTREME_IQR_MULTIPLIER`  | `3.0`   | Documented for severity classification; not consulted by the Boolean check today. |
| `ADR_A7_MIN_POPULATION`          | `10`    | Segments with fewer eligible rows are NOT_APPLICABLE (every row passes). When `segment_by_project_type` is on, the floor is applied per extended segment. |

---

## A8: Cross-discipline quantity ratios (ADR)

- **Type:** Statistical Outlier · **Blocking:** No · **Data product:** ADR
- **Implementation:** `check_adr_a8` (with `_classify_a8_category` for
  the discipline mapping).
- **Optional reference dataset:** `VWS_GP_STANDARD_SHARE`
  (`PLANVIEW_ID → PROJECT_ID`, lookup `E05_DEPARTMENT` + `BUSINESS`).
  Only consulted when the `segment_by_project_type` toggle is on; the
  default global-IQR path runs without any reference.

A8 validates the **overall shape of each project**. Where A7 looks at
hours-per-quantity within a single discipline, A8 looks at the
*proportions between* disciplines - pipe length per equipment count,
cable length per transmitter count, steel weight per concrete volume.
A project whose proportions sit far from the population peer projects
is flagged for review.

### Algorithm

1. **Per-row eligibility.** A row enters the aggregation when:

   ```
   QTY_QUANTITY > 0
   AND ROOT_ITEM_NAME populated
   AND ITEM_TYPE     populated
   AND QTY_UOM       populated
   ```

2. **Discipline classification.** Each eligible row is mapped to one
   of six categories using `ITEM_TYPE` + `QTY_UOM` (priority order
   handles overlapping name patterns, e.g. `Piperack + t` resolves to
   `STEEL_WEIGHT` rather than `PIPE_LENGTH`):

   | Category             | `ITEM_TYPE` contains            | `QTY_UOM` (post-normalisation) |
   |----------------------|----------------------------------|--------------------------------|
   | `STEEL_WEIGHT`       | `SteelStructure` or `Piperack`   | `t`, `t,sht` |
   | `CONCRETE_VOLUME`    | `Foundation` or `Concrete`       | `yd³`, `m³` (`CY`, `yds³` aliased) |
   | `PIPE_LENGTH`        | `Piping` or `Pipe`               | `ft`, `m` |
   | `CABLE_LENGTH`       | `Electrical` or `FieldInstrument`| `ft`, `m` |
   | `TRANSMITTER_COUNT`  | `FieldInstrument`                | one of the instrument-count UOMs (`Temperature Transmitters`, `Pressure Gauges`, …) |
   | `EQUIPMENT_COUNT`    | one of the major-equipment `Estimate*` types (`EstimatePump`, `EstimateGasTurbine`, …) | anything **not** in the length / area / volume / weight / subcomponent exclusion list |

   Rows the classifier does not recognise are **not eligible** for any
   ratio and have no effect on the result.

3. **Aggregate by `(ROOT_ITEM_NAME, category)`.** `_qty` is summed, the discipline-level total used as numerator or denominator.

4. **Compute cross-discipline ratios per project.** A8 currently
   evaluates three:

   ```
   PIPE_LENGTH      / EQUIPMENT_COUNT
   CABLE_LENGTH     / TRANSMITTER_COUNT
   STEEL_WEIGHT     / CONCRETE_VOLUME
   ```

   A project is included in a ratio's population when **both**
   numerator and denominator totals are strictly greater than zero.

5. **Per-ratio IQR bounds across projects.** For each ratio:

   ```
   Q1   = quantile(RATIO_VALUE, 0.25)
   Q3   = quantile(RATIO_VALUE, 0.75)
   IQR  = Q3 - Q1
   MILD_LOWER = Q1 - 1.5 × IQR
   MILD_UPPER = Q3 + 1.5 × IQR
   ```

   A project is **flagged on this ratio** when its ratio is below the
   lower bound or above the upper bound. The 3.0× extreme multiplier
   is documented for severity classification, every extreme outlier
   is already a mild outlier and therefore a FAIL, so the Boolean
   check uses only the mild bound.

   When the `segment_by_project_type` toggle is on, this step is run
   **within each `(E05_DEPARTMENT, BUSINESS)` segment** instead of
   across the dataset, see
   [Project-type segmentation](#project-type-segmentation-segment_by_project_type-a8).

6. **Row-level verdict.** A row **fails** A8 iff its
   `ROOT_ITEM_NAME` is flagged on at least one of the ratios computed
   above. Rows whose project is unknown (null / blank
   `ROOT_ITEM_NAME`) pass, they cannot be assigned to a project
   group.

### NOT_APPLICABLE (treated as PASS) cases

A8 returns Booleans only. These cases collapse to PASS so they don't
double-penalise rules that already cover those gaps:

- **Row's `ROOT_ITEM_NAME` is null / blank**: no project to attach to.
- **Row's quantity / item-type / UOM cannot be classified**: the row
  contributes to no ratio and therefore can't trigger one.
- **Per-ratio population below `ADR_A8_MIN_POPULATION`** (default
  `10`) - too few projects to derive thresholds for that specific
  ratio. When `segment_by_project_type` is on the same floor is
  applied **per segment**, so a thinly-populated bucket does not
  flag every project inside it as an outlier of itself.
- **Per-ratio population `IQR == 0`**: every project's ratio sits on
  the median; outlier detection is not meaningful.
- **Project whose project-type cannot be resolved** (only when
  `segment_by_project_type` is on), no associated `PLANVIEW_ID`,
  unmatched `PROJECT_ID`, or null/blank `E05_DEPARTMENT` /
  `BUSINESS` - NOT_APPLICABLE → PASS. A1 / A2 already cover the
  referential / completeness gaps.

### Where the inputs come from

A8 operates on the **denormalized ADR data product**. `ITEM_TYPE` and
`ROOT_ITEM_NAME` are pass-throughs from the primary item table; the
QTY columns come from the SUM-aggregated 1:N child:

| Source table                          | Source column     | Denormalized column | Notes |
|---------------------------------------|-------------------|---------------------|-------|
| `ADR_DIM_ESTIMATEITEMRECORD` (1:1)    | `ITEM_TYPE`       | `ITEM_TYPE`         | Pass-through. |
| `ADR_DIM_ESTIMATEITEMRECORD` (1:1)    | `ROOT_ITEM_NAME`  | `ROOT_ITEM_NAME`    | Pass-through, the project / scope key. |
| `ADR_FACT_ESTIMATEQTYRESULTS` (1:N)   | `QUANTITY`        | `QTY_QUANTITY`      | Sum across qty rows for the item. |
| `ADR_FACT_ESTIMATEQTYRESULTS` (1:N)   | `QTY_UOM`         | `QTY_UOM`           | Builder applies `first` aggregation; the SQL spec uses `MAX(QTY_UOM)`. Real estimates carry one UOM per item, so both formulations agree on production data. |

### Why it matters

Absolute quantities can vary wildly across projects (a 10 km pipe rack
vs. a 200 km offshore manifold), but the **proportion** between
disciplines is driven by physical reality - you can't have a hundred
pumps without commensurate piping and cable. When that proportion
breaks, it's almost always a sign of: data-entry error, missing
quantities for one discipline, UOM mismatch, mis-classified scope, or
a genuinely unusual project. A8 surfaces those projects for review.

### Notes

- **One project, multiple ratio results.** A project can fail one
  ratio and pass another. The Boolean per-row output collapses across
  ratios - a project with at least one flagged ratio is failing.
- **Classification is intentionally specific.** The category mappings
  reference real production `Estimate*` labels; the rule will mostly
  PASS in datasets that haven't been profiled against those names yet.
  Recommended next step is to expand `_A8_EQUIPMENT_ITEM_TYPES` /
  `_A8_TRANSMITTER_COUNT_UOMS` after a profiling pass on real data.
- **UOM aliases.** `CY` ↔ `yd³`, `yds³` ↔ `yd³` and similar
  superscript-vs-`^N` spellings normalise so the classifier is robust
  to source-system variation.
- **Schema-level missing column → all rows fail**, mirroring the
  convention used by E1 / E3 / E6 / A5 / A6 / A7. When
  `segment_by_project_type` is on, `PLANVIEW_ID` becomes structurally
  required too - Step 4.2's CDE-coverage badge surfaces the gap
  before the rule is even allowed to run.
- **Segmented mode requires the reference.** When
  `segment_by_project_type` is on and `VWS_GP_STANDARD_SHARE` is
  unavailable (or missing `E05_DEPARTMENT` / `BUSINESS`), the rule
  raises `CustomRuleNotEvaluated`, it never silently falls back to
  the global IQR baseline.
- **Failed projects are review candidates, not errors.** A FAIL means
  the project's shape is unusual; it does not prove the data is wrong.
  The rule only identifies statistical anomalies.

### Project-type segmentation (`segment_by_project_type`, A8)

Cross-discipline proportions differ across project archetypes - a
greenfield FPSO and a brownfield refinery sit at very different points
on the steel-to-concrete or pipe-to-equipment scale. Pooling them
widens the global IQR enough that genuine within-archetype outliers
hide in the middle. The toggle splits the population before deriving
the per-ratio IQR, mirrors the
[E6](#project-type-segmentation-segment_by_project_type) and
[A7](#project-type-segmentation-segment_by_project_type-a7) toggles.

When on:

1. Each project's `PLANVIEW_ID` (the first non-blank value across the
   project's rows) is joined to `VWS_GP_STANDARD_SHARE` on
   `PLANVIEW_ID = PROJECT_ID` to recover its archetype tags
   (`E05_DEPARTMENT` for brownfield / greenfield, `BUSINESS` for the
   business line, e.g. upstream / downstream / chemical / LNG).
2. For each cross-discipline ratio the project population is partitioned
   by `(E05_DEPARTMENT, BUSINESS)`. Each segment derives its own `Q1`,
   `Q3`, and IQR; the PASS band is segment-local.
3. The same per-ratio minimum-population floor
   (`ADR_A8_MIN_POPULATION`) applies - segments with fewer projects on
   that ratio fall through to NOT_APPLICABLE → PASS.
4. Projects whose project-type cannot be resolved (no associated
   `PLANVIEW_ID`, unmatched `PROJECT_ID`, null `E05_DEPARTMENT` /
   `BUSINESS`) are NOT_APPLICABLE → PASS.

When off (default) the rule behaves exactly as it did before this
feature, one IQR per ratio across the dataset.

### Inputs

| Alias                  | Physical column      |
|------------------------|----------------------|
| Item Type              | `ITEM_TYPE`          |
| Root Item Name         | `ROOT_ITEM_NAME`     |
| Quantity               | `QTY_QUANTITY`       |
| Quantity UOM           | `QTY_UOM`            |
| Project Key *(when `segment_by_project_type` is on)* | `PLANVIEW_ID` |

### Options

| Key | Widget | Default | Effect |
|-----|--------|---------|--------|
| `threshold_iqr_multiplier` | `st.selectbox` | `1.5` | IQR multiplier used to derive each cross-discipline ratio's PASS band. Choices: **1.5×IQR (mild - recommended)**, 2.0×IQR, 3.0×IQR (extreme). |
| `segment_by_project_type` | `st.toggle` | `False` | When on, each cross-discipline ratio's IQR baseline is computed within each `(E05_DEPARTMENT, BUSINESS)` segment resolved via `VWS_GP_STANDARD_SHARE`. Off → one global IQR per ratio across every eligible project. |

### Tunables

| Constant                         | Default | Effect |
|----------------------------------|--------:|--------|
| `ADR_A8_MILD_IQR_MULTIPLIER`     | `1.5`   | Default IQR multiplier (overridable via the `threshold_iqr_multiplier` option). Defines the PASS / FAIL boundary (`Q1 - k·IQR` … `Q3 + k·IQR`). |
| `ADR_A8_EXTREME_IQR_MULTIPLIER`  | `3.0`   | Documented for severity classification; not consulted by the Boolean check today. |
| `ADR_A8_MIN_POPULATION`          | `10`    | Ratios with fewer projects in the population are NOT_APPLICABLE (every project on that ratio passes). When `segment_by_project_type` is on the floor is applied per segment. |

### Ratios evaluated today

| Ratio                                | Numerator           | Denominator          |
|--------------------------------------|---------------------|----------------------|
| `PIPE_LENGTH_PER_EQUIPMENT_COUNT`    | `PIPE_LENGTH`       | `EQUIPMENT_COUNT`    |
| `CABLE_LENGTH_PER_TRANSMITTER_COUNT` | `CABLE_LENGTH`      | `TRANSMITTER_COUNT`  |
| `STEEL_WEIGHT_PER_CONCRETE_VOLUME`   | `STEEL_WEIGHT`      | `CONCRETE_VOLUME`    |

Adding a new ratio is a one-line change in `_A8_RATIOS` once the
underlying categories are produced by `_classify_a8_category`.

---

## ADR → ACCE column mapping

ACCE rules replicate the ADR rules' business logic against the ACCE
schema. The denormalized ACCE data product surfaces the columns below;
every rule (AC1, …) reads from this denormalized view exactly like
ADR rules read from theirs.

| ADR column (denormalized) | ACCE column (denormalized) | Source table | Notes |
|---|---|---|---|
| `COMPLETE_WBC` | `COA` | `ACCE_ESTIMATEITEMRECORD` | ADR uses a dot-delimited WBC whose first segment is the 3-character ICARUS Code of Account group (`SPLIT_PART(COMPLETE_WBC, '.', 1)`). ACCE uses a 4-character numeric COA code whose **leading 3 characters** are the ICARUS group (e.g. `3131 → 313`). AC1 / AC3 take the first three characters of `COA` before joining to `ACCE_COA_MASTER.ICARUS_COA` - the analog of ADR's `SPLIT_PART` derivation. |
| `COST_UPDATE` | `JOB_NO` | `ACCE_ESTIMATEITEMRECORD` | ADR uses `COST_UPDATE` as the estimate basis date; ACCE uses `JOB_NO` (estimate job / period, e.g. `2Q23 RP1`) as proxy. |
| `ITEM_TYPE` | `DESCRIPTION` | `ACCE_ESTIMATEITEMRECORD` | ADR classifies discipline via `Estimate*` item-type substring sweeps. ACCE's discipline classifier (AC4 / AC7 / AC8) keys off the `DESCRIPTION` estimate-line label instead - the former `ACCT` account-code classifier (`2-EQP`, `3-PIP`, …) was retired, so ADR's `ITEM_TYPE` role is now served by the same `DESCRIPTION` column below. |
| `ITEM_DESCRIPTION` | `DESCRIPTION` | `ACCE_ESTIMATEITEMRECORD` | Item description field - also the discipline classifier (see the `ITEM_TYPE` row above). |
| `ROOT_ITEM_NAME` | `PROJECT_NAME` | `ACCE_ESTIMATEITEMRECORD` | Project / scope grouping key. |
| `PLANVIEW_ID` | `PLANVIEW_ID` | `ACCE_ESTIMATEITEMRECORD` | Same field name. |
| `QTY_QUANTITY` | `QTY_QUANTITY` | Derived: row-level `COALESCE(KEY_QTY, OTHER_QTY)` → SUM per ROW_ID. Applied by the builder's `derive_columns` hook on the `ACCE_ESTIMATEQTYRESULTS` `TableDef` so the COALESCE happens *before* the group-by SUM. | ADR carries one quantity column; ACCE has two parallel pairs (`KEY_QTY` / `OTHER_QTY`) that must be merged row-by-row, then summed. |
| `QTY_UOM` | `QTY_UOM` | Derived: row-level `COALESCE(KEY_UNITS, OTHER_UNITS)` → `FIRST` per ROW_ID (same hook). | Same merge logic on the UOM side; aggregation is `FIRST` (non-null) because UOMs are categorical. |
| `COST_TOTAL_HOURS` | `COST_MH` | Derived: `MH` from `ACCE_ESTIMATECOSTRESULTS` | ACCE stores construction hours in `MH`; after the COST prefix the denormalized column is **`COST_MH`** (not `COST_TOTAL_HOURS`). AC3, AC6, and AC7 all read from `COST_MH` on ACCE. |
| `COST_DB_TOTAL_HOURS` | - (not available) | - | ACCE does not separate database hours; the ACCE counterpart of A6 uses **`COST_MH` only**. |
| `COST_TOTAL_COST` | `COST_TOTAL_COST` | Derived: `TOTAL_COST` from `ACCE_ESTIMATECOSTRESULTS` | Direct mapping. |
| `DESIGN_PARAMETER_VALUE` | `DESIGN_VALUE` | Derived: `VALUE` from `ACCE_ESTIMATEDESIGNDETAILS` (builder prefixes with `DESIGN_`) | Design property value (1:N child of the item record). ADR's analogue column is `DESIGN_PARAMETER_VALUE`; ACCE source column is `VALUE` so the prefixed result is **`DESIGN_VALUE`**: different physical column name. |

---

## ADR → ACCE Rule Logic Equivalence Summary

The column mapping above shows *which fields* move where; this table
shows *how the rule's logic* differs across the two systems. Every
ACCE rule preserves the business intent of its ADR counterpart, the
differences below are mechanical adaptations to ACCE's schema.

| Aspect | ADR | ACCE | Difference |
|---|---|---|---|
| **AC1 COA derivation** | `SPLIT_PART(COMPLETE_WBC, '.', 1)` → lookup | `COA[:3]` → lookup | ACCE stores a 4-char `COA` whose leading 3 chars are the ICARUS group; the slice is the analog of ADR's dot-split. |
| **AC2 Date proxy** | `COST_UPDATE` | `JOB_NO` | Different field name, same role, the estimate-basis-date proxy used by the EMMA normalization period selector. Both carry a Validity format check, but the shapes differ: A2's `COST_UPDATE` is a 4-digit-year quarter (`[1-4]Q<YYYY>`, e.g. `2Q2019`); AC2's `JOB_NO` is a 2-digit-year quarter with an optional revision suffix (`[1-4]Q<YY>`, e.g. `2Q23 RP1`). |
| **AC4 Negative-total check** | Project fails when `SUM(QTY_QUANTITY) < 0` | Project fails when `SUM(QTY_KEY_QTY) + SUM(QTY_OTHER_QTY) < 0` | Same Validity concept (a project's quantities must not net negative); ACCE sums both split quantity slots since it has no single coalesced quantity column in AC4's input set. Row-level negatives are allowed in both. |
| **AC3 Ratio numerator** | `COUNT(DISTINCT COMPLETE_WBC)` | `COUNT(DISTINCT COA)` (over the full 4-char `COA`) | Different granularity - ACCE's metric counts distinct 4-char codes per resolved bucket, naturally capped at ten per 3-char ICARUS group; same statistical (IQR-bound) logic. |
| **AC4 Discipline keys** | `ITEM_TYPE` (pattern-matched `Estimate*` labels) | `DESCRIPTION` (explicit per-core-type value lists, e.g. `PIPING` / `CS PIPE ERECTION` for piping, `CENTRIFUGAL PUMPS` / `S&T EXCHANGER` for equipment), matched on `UPPER(TRIM(DESCRIPTION))`; `MODULE_COUNT` keeps a `MODULE` / `MODULAR` substring match | ACCE classifies straight off the estimate-line label rather than a discipline account code; both scope and population use the same `DESCRIPTION` lists. |
| **AC4 Quantity / UOM source** | Coalesced `QTY_QUANTITY` + `QTY_UOM` (sum / first per item) | Split `QTY_KEY_QTY` / `QTY_OTHER_QTY` and `QTY_KEY_UNITS` / `QTY_OTHER_UNITS`; a type is populated when **either** slot has qty > 0 and **either** unit is in the type's UOM set, compared on `UPPER(TRIM(units))` with no alias normalization | Mirrors the SQL spec's per-row `(KEY_QTY > 0 OR OTHER_QTY > 0)` and `(KEY_UNITS IN (...) OR OTHER_UNITS IN (...))` before the project-level `MAX()`. |
| **AC5 Design source** | `DESIGN_PARAMETER_VALUE` (1:1 join on `ROW_ID`); any non-null value suffices | `DESIGN_PROPERTY` + `DESIGN_VALUE` (source columns `PROPERTY` / `VALUE` on `ACCE_ESTIMATEDESIGNDETAILS`, joined via `DESIGN_ID` - builder prefixes with `DESIGN_`) | ACCE requires BOTH a named parameter and a value (the "120 m of what?" interpretability gate); A5 checks only the value. Also: AC5's quantity gate is strictly positive (negatives are "no quantity"). |
| **AC6 Hours source** | `COST_TOTAL_HOURS` OR `COST_DB_TOTAL_HOURS` | **`COST_MH` only** (sourced from `MH` on `ACCE_ESTIMATECOSTRESULTS`) | ACCE has no separate Design-Build hours column; AC6 evaluates only `COST_MH`. Equivalent to A6's two-column OR when only one hours column exists. |
| **AC7 Segment keys** | `(ITEM_TYPE, QTY_UOM)` | `(DESCRIPTION, QTY_UOM)` | Same per-segment IQR logic; AC7 partitions by the raw `UPPER(TRIM(DESCRIPTION))` value + effective UOM (`COALESCE(KEY_UNITS, OTHER_UNITS)`) - finer-grained (per-label) than ADR's discipline-level types. |
| **AC8 Project key** | `ROOT_ITEM_NAME` | `COMPONENT_SOURCE` | Same field semantics, the project / scope grouping key; different column name. |
| **AC8 Category classifier** | Pattern-match on `ITEM_TYPE` + `QTY_UOM`, plus a closed `(ITEM_TYPE, UOM)` allow-list for `EQUIPMENT_COUNT` | `DESCRIPTION` value lists (the same taxonomy AC4 uses) gated by a `KEY_UNITS` / `OTHER_UNITS` family match | ACCE keys off the estimate-line label rather than a discipline code. **AC8's volume set differs from AC4's**: AC8 admits `YD` where AC4 admits `YDS`; the equipment list spells `TURBO-EXPAND, COMPRESSOR` (comma) where AC4 uses a period. |
| **AC8 Ratio eligibility** | (n/a - A8's ratio logic is the same shape) | A ratio is calculable when the **denominator > 0** (`NULLIF(den, 0)`); the numerator is allowed to be `0`. A project with no pipe but some equipment contributes a valid `0` ratio to the population. | Locked-in for SQL parity. Differs from a naïve `num > 0 AND den > 0` filter that would silently drop legitimate zero-ratio projects. |
| **AC3 project scope** | `params["project_scoped"]` recomputes the percentile baseline within each `PLANVIEW_ID` partition | - (not exposed) | AC3's baseline is always portfolio-wide; ACCE COA granularity is already coarser so per-project scope adds noise. |
| **AC3 uniform 1:1 detection** | Flags every material 1:1 bucket when the toggle is on | Flags material 1:1 buckets only when ≥ 80 % (`ACCE_AC3_UNIFORM_THRESHOLD`) of eligible mappings in the portfolio are 1:1 | The wider gate reflects that ACCE COA codes are inherently coarser, so a handful of legitimate 1:1 mappings should not by themselves trip the rule. |
| **AC7 / AC8 project scope** | `params["segment_by_project_type"]` extends the IQR partition with `(E05_DEPARTMENT, BUSINESS)` from Planview | Same toggle exposed as `params["segment_by_project_type"]` | Identical semantics - off by default. AC7 extends `(DESCRIPTION, QTY_UOM)` → `(DESCRIPTION, QTY_UOM, E05_DEPARTMENT, BUSINESS)`; AC8 partitions the per-ratio IQR baseline by `(E05_DEPARTMENT, BUSINESS)`. When on, the Planview reference must be available or the check raises `CustomRuleNotEvaluated`. |

---

## AC1: ISO Code of Account Present (COR + SAB) - ACCE

- **Type:** Completeness · **Blocking:** **Yes** · **Data product:** ACCE
- **Implementation:** `check_acce_ac1` (reuses `_a1_value_valid` for the
  ISO_COR / SAB markers and `_resolve_coa_master_lookups` for the
  best-available join semantics - both shared with A1).
- **Reference dataset:** `ACCE_COA_MASTER`
  (`ACCE.COA[:3] → ACCE_COA_MASTER.ICARUS_COA`, lookup `ISO_COR` and
  `SAB`).

A row passes when **all three** hold:

1. `COA` is non-null and non-blank.
2. The first three characters of `COA` resolve to a valid `ISO_COR`
   in the COA master.
3. The same three-character prefix resolves to a valid `SAB` in the
   COA master.

`ISO_COR` / `SAB` are considered **invalid** when null, blank, or when
the value contains the substrings `ERROR` or `N/A` (case-insensitive), same validity helper as A1.

### COA derivation

ACCE source data carries 4-character `COA` codes (e.g. `3131`,
`6320`); the master keys (`ICARUS_COA`) are the 3-character group
prefixes (e.g. `313`, `632`). AC1 takes the **first three
characters** of `COA` as the lookup key, the analog of A1's
`SPLIT_PART(COMPLETE_WBC, '.', 1)` derivation:

```
ACCE_COA_PREFIX = COA[:3]
```

Examples:

| `COA` | Derived prefix | `ACCE_COA_MASTER.ICARUS_COA` match |
|---|---|---|
| `6320` | `632` | `632` |
| `3131` | `313` | `313` |
| `9210` | `921` | `921` |
| NULL / blank | - | (rule fails, no derivation) |

The lookup tolerates either a string `COA` column or a numeric one
(Snowflake may cast the field as `int64`); both sides of the join
are stringified + stripped + sliced to the first three characters
before `.map()`.

### "Best-available" mapping when the master has duplicates

Identical to A1, see [the A1 section](#a1--iso-code-of-account-present-cor--sab--adr).
`_resolve_coa_master_lookups` is shared, so a `COA` value with one
valid + one `ERROR` row in the master resolves to the valid pair, and
a fully-invalid group still surfaces an `ERROR` marker so the validity
check fails (no silent pass).

### Why it matters

`ISO_COR` and `SAB` together pick the EMMA normalization factor for
cost benchmarking. Without them, ACCE cost data cannot be normalized
across projects, the row is unusable for downstream cross-project
cost analytics. Hence AC1 is **blocking** (same rationale as A1 and
EPT E1).

### Failure modes

- Missing `COA` or `PLANVIEW_ID` column → all rows fail.
- Reference dataset unavailable → `CustomRuleNotEvaluated` (Step 6
  shows *Not evaluated*).
- Reference dataset present but missing `ICARUS_COA` / `ISO_COR` /
  `SAB` columns → all rows fail.

### Inputs

| Alias | Physical column |
|---|---|
| Project Key | `PLANVIEW_ID` |
| Code of Account | `COA` |

### Decision matrix

| `COA` | Resolved `ISO_COR` | Resolved `SAB` | Result |
|---|---|---|---|
| Missing / blank | (any) | (any) | **FAIL** |
| Present, COA orphan | NaN (no master row) | NaN | **FAIL** |
| Present | invalid | (any) | **FAIL** |
| Present | valid | invalid | **FAIL** |
| Present | valid | valid | PASS |

---

## AC2: Location + Estimate Date Present & Valid (ACCE)

- **Type:** Completeness & Validity · **Blocking:** No · **Data product:** ACCE
- **Implementation:** `check_acce_ac2` (uses `_is_filled` for completeness
  + a `str.fullmatch` against `ACCE_AC2_JOB_NO_PATTERN` for validity + a
  join against the Planview reference). Mirrors `check_adr_a2` against
  the ACCE data product, swapping `COST_UPDATE` (ADR's estimate basis
  date) for `JOB_NO` (ACCE's estimate-job/period proxy).
- **Reference dataset:** `VWS_GP_STANDARD_SHARE`
  (`ACCE.PLANVIEW_ID → VWS_GP_STANDARD_SHARE.PROJECT_ID`, lookup
  `COUNTRY`).

A row passes when **all** hold:

1. `JOB_NO` (estimate job / period, in ACCE) is non-null and
   non-blank (**Completeness**).
2. `JOB_NO` starts with the fiscal quarter-year token `[1-4]Q<YY>` — a
   quarter digit `1`-`4`, the literal `Q` (case-insensitive), a 2-digit
   year — optionally followed by a whitespace-separated revision suffix,
   e.g. `2Q23 RP1`, `2Q24`, `4Q23` (**Validity**). The check is
   *structural*, not an enum, so newly-ingested quarters/years pass
   automatically; a populated but malformed value (e.g. `2023`, `Q2-23`,
   `5Q23`) fails even though it satisfies completeness.
3. `COUNTRY` (project location) is non-null and non-blank in the
   Planview reference, **after** joining `ACCE.PLANVIEW_ID` against
   `VWS_GP_STANDARD_SHARE.PROJECT_ID`. An unmatched `PLANVIEW_ID` is
   treated as a missing `COUNTRY` (i.e. the row fails AC2).

**Why it matters.** COUNTRY + JOB_NO together pick the correct CU
period for EMMA normalization. `JOB_NO` is the *estimate job / period*
(e.g. `2Q23 RP1`, `2Q24`, `2Q25`, `4Q23`), the ACCE proxy
for the estimate date; ADR uses `COST_UPDATE` for the same role. New
period values may be ingested over time — the structural Validity check
accepts them without a code change as long as they keep the
quarter-year shape.

### Failure modes

- Missing `JOB_NO` or `PLANVIEW_ID` column → all rows fail.
- `JOB_NO` populated but not in the `[1-4]Q<YY>` format → that row
  fails (Validity).
- Reference dataset unavailable → `CustomRuleNotEvaluated` (Step 6
  shows *Not evaluated*).
- Reference dataset present but missing `PROJECT_ID` / `COUNTRY` →
  all rows fail.

### Inputs

| Alias | Physical column |
|---|---|
| Estimate Job Number | `JOB_NO` |
| Project Key | `PLANVIEW_ID` |

---

## AC3: Statistical COA-to-ISO mapping ratio (ACCE)

- **Type:** Statistical Outlier · **Blocking:** No · **Data product:** ACCE
- **Implementation:** `check_acce_ac3` (with `_resolve_coa_master_lookups`
  shared with AC1).
- **Reference dataset:** `ACCE_COA_MASTER`
  (`ACCE.COA[:3] → ICARUS_COA`, lookup `ISO_COR` and `SAB`).
- **Join key vs distinct count.** The lookup uses the first three
  characters of `COA` (same derivation as AC1) so multiple distinct
  4-character source COAs sharing a 3-character prefix all resolve
  to the same `(ISO_COR, SAB)` bucket. The per-bucket
  `COUNT(DISTINCT COA)` metric, however, runs over the **full**
  4-character `COA` value, so multiple 4-character codes sharing a
  prefix contribute to the bucket's ratio individually rather than
  collapsing to one.

AC3 is the statistical counterpart of AC1: where AC1 enforces that
every row resolves to a valid `ISO_COR + SAB`, AC3 asks whether each
ISO bucket *holds too many distinct ACCE `COA`s*. A high
`COA_TO_ISO_RATIO` means many ACCE `COA` values collapse into the same
ISO mapping, and the rule flags the buckets that aggregate beyond
what the ACCE portfolio's distribution considers normal.

AC3 mirrors ADR A3 against the ACCE data product. Same row-level
verdict / group-level threshold pattern, same materiality framing,
same global-P90 baseline, but the ratio is sourced from
`COUNT(DISTINCT COA)` per resolved `(ISO_COR, SAB)` bucket instead of
`COUNT(DISTINCT COMPLETE_WBC)`.

### Algorithm

1. **Per-row eligibility.** A row enters the aggregation when:

   ```
   COA populated
   AND COA[:3] resolves to a valid ISO_COR in the COA master
   AND the same prefix resolves to a valid SAB in the COA master
   ```

   Validity rejects null / blank / `ERROR` / `N/A` (case-insensitive), same `_a1_value_valid` semantics AC1 uses. Rows that fail any of
   these are **PASS** for AC3 because AC1 already covers the COA /
   COR / SAB completeness gap.

2. **Bucket metric.** Group eligible rows by `(ISO_COR, SAB)`, then:

   ```
   COA_TO_ISO_RATIO = COUNT(DISTINCT COA)        (over the full 4-char COA)
   hours_sum        = SUM(COST_MH)               (null → 0)
   cost_sum         = SUM(COST_TOTAL_COST)       (null → 0)
   ```

   `COST_MH` is ACCE's construction-hours column, sourced from
   `MH` on `ACCE_ESTIMATECOSTRESULTS` and prefixed by the
   data-product builder. ADR's analog is `COST_TOTAL_HOURS`
   (sourced from `TOTAL_HOURS`).

   Note: the distinct count uses the *full* 4-character `COA`, not
   the 3-character lookup prefix, so multiple distinct codes sharing
   a prefix contribute to the ratio individually.

3. **Global P90.** Across all eligible buckets (`ratio ≥ 1`):

   ```
   P90_COA_TO_ISO_RATIO = quantile(COA_TO_ISO_RATIO, 0.90)
   ```

   The percentile is user-customizable via the `threshold_percentile`
   selectbox, see [Outlier thresholds](#outlier-thresholds-e3--e6--a3--a7--a8--ac3).

4. **Materiality.** A bucket is *material* when:

   ```
   hours_sum > 0
   OR cost_sum >= ACCE_AC3_MATERIALITY_USD    (default 100,000)
   ```

5. **Per-bucket verdict.** A bucket **fails** when:

   ```
   ratio > P90 AND material
   ```

6. **Row-level verdict.** Every row whose resolved `(ISO_COR, SAB)`
   bucket is flagged inherits the FAIL. Every other eligible row,
   plus every NOT_APPLICABLE row, passes.

### NOT_APPLICABLE (treated as PASS) cases

- **`COA` missing**: AC1's territory.
- **Resolved `ISO_COR` / `SAB` invalid** (null / blank / `ERROR` /
  `N/A`) - AC1's territory.
- **Eligible-mapping population below
  `ACCE_AC3_MIN_MAPPING_POPULATION`** (default `10`) - too few
  buckets to derive a meaningful P90.
- **Bucket not material**: planning / structural-only mappings are
  exempt regardless of how many distinct COAs flow through them.

### ACCE-specific interpretation note

ADR's per-bucket ratio runs over `COUNT(DISTINCT COMPLETE_WBC)`,
counting every distinct dot-delimited WBC string under a 3-character
COA group. ACCE's ratio runs over `COUNT(DISTINCT COA)`, the full
4-character COA - under the same 3-character ICARUS_COA group. The
two metrics measure the same *kind* of over-aggregation
(source-system detail collapsing into a single ISO bucket), but
ACCE's granularity is capped at ten distinct codes per 3-character
prefix (the trailing digit of the 4-character COA), whereas ADR's
WBC granularity is unbounded. As a result the `COA_TO_ISO_RATIO` in
ACCE is naturally lower than ADR's `WBC_TO_ISO_RATIO`, and a FAIL
should still be read as a **mapping-quality concern that warrants
SME review**, not as a definitive "this data is wrong" signal.

### Uniform 1:1 mapping detection (opt-in toggle)

When `detect_uniform_mapping = True`, AC3 layers a portfolio-wide
uniform detector on top of the percentile fail. Unlike A3, which
flags every material 1:1 bucket the moment its toggle is on - AC3
only trips the uniform branch when the *proportion* of eligible
mappings with `ratio == 1` reaches `ACCE_AC3_UNIFORM_THRESHOLD`
(default **80 %**). When the gate trips, every material 1:1 bucket
fails; the percentile fail and the uniform fail combine with **OR**,
and materiality still gates both.

The wider gate reflects that ACCE COA codes are inherently coarser
than ADR's WBCs - a handful of legitimate 1:1 mappings should not
by itself trigger the rule.

### Why it matters

`ISO_COR` and `SAB` together pick the EMMA normalization factor;
the analytic granularity of the normalized comparison is bounded by
how many distinct ACCE COAs roll through one ISO bucket. When that
count is far above the portfolio norm, the ISO bucket is hiding
meaningful source-system detail and the comparison's resolving
power degrades.

### Failure modes

- Missing `PLANVIEW_ID`, `COA`, `COST_MH`, or `COST_TOTAL_COST`
  column → all rows fail (structural incompleteness; same convention
  as the other custom rules).
- Reference dataset unavailable → `CustomRuleNotEvaluated` (Step 6
  shows *Not evaluated*).
- Reference dataset present but missing `ICARUS_COA` / `ISO_COR` /
  `SAB` columns → all rows fail.

### Inputs

| Alias | Physical column |
|---|---|
| Project Key | `PLANVIEW_ID` |
| Code of Account | `COA` |
| Construction Hours | `COST_MH` |
| Total Cost | `COST_TOTAL_COST` |

### Options

| Key | Widget | Default | Effect |
|---|---|---|---|
| `threshold_percentile` | `st.selectbox` | `0.90` (P90) | Percentile cutoff applied to the COA-to-ISO ratio distribution. Choices: P75 (lenient), **P90 (recommended)**, P95 (strict), P99 (very strict). |
| `detect_uniform_mapping` | `st.toggle` | `False` | Enables the portfolio-wide uniform-mapping detector described above. |

### Tunables

| Constant | Default | Effect |
|---|---|---|
| `ACCE_AC3_PERCENTILE` | `0.90` | Default percentile (overridable via the `threshold_percentile` option). Defines the PASS / FAIL boundary on the bucket ratio (`ratio > P` ⇒ candidate FAIL). |
| `ACCE_AC3_MATERIALITY_USD` | `100_000.0` | Below-threshold buckets with zero hours are NOT_APPLICABLE (every row passes). |
| `ACCE_AC3_MIN_MAPPING_POPULATION` | `10` | Below-threshold populations skip percentile computation entirely (every row passes). |
| `ACCE_AC3_UNIFORM_THRESHOLD` | `0.80` | Proportion of eligible 1:1 mappings that triggers the uniform-detection branch when the toggle is on. |

### Decision matrix

| Valid ISO mapping | Material bucket | `ratio` vs P90 | Result |
|---|---|---|---|
| No | (any) | (any) | PASS *(AC1 territory)* |
| Yes | No | (any) | PASS |
| Yes | Yes | ≤ P90 | PASS |
| Yes | Yes | > P90 | **FAIL** |
| Yes (any) | (any) | population < `ACCE_AC3_MIN_MAPPING_POPULATION` | PASS |

---

## AC4: Core quantities populated & non-negative project totals (ACCE)

- **Type:** Completeness & Validity · **Blocking:** No · **Data product:** ACCE
- **Implementation:** `check_acce_ac4` (with `_classify_ac4_scope_acce`
  and `_classify_ac4_quantity_acce` for the discipline mapping).

AC4 is a **project-level Completeness & Validity rule with a row-level
verdict**. For each `PLANVIEW_ID` it asks two questions: (a) of the seven
core quantity types this project's scope implies, is each one actually
populated? and (b) is the project's combined quantity total
(`SUM(QTY_KEY_QTY) + SUM(QTY_OTHER_QTY)`) non-negative?

The seven core quantity types are: piping LF, concrete CY, steel
tons, cable length, transmitter / instrument count, equipment count,
module count. The rule does *not* require every project to carry all
seven - completeness is judged **relative to the project's own
scope**.

### Algorithm

For each `PLANVIEW_ID`:

1. **Determine expected core quantity types.** A type is *expected*
   when at least one item in the project has a `DESCRIPTION` in that
   type's allow-list (see classifier table below; MODULE_COUNT is a
   `MODULE` / `MODULAR` substring match). Quantity and UOM are
   **not** consulted at this step - a description that *implies* the
   scope is enough.

2. **Determine populated core quantity types.** A type is *populated*
   when at least one item in the project has its `DESCRIPTION` in
   that type's allow-list AND a strictly positive quantity
   (`QTY_KEY_QTY > 0` OR `QTY_OTHER_QTY > 0`) AND a matching unit
   (`QTY_KEY_UNITS` OR `QTY_OTHER_UNITS` in the type's UOM set).

3. **Compare expected vs. populated.** A project is flagged when there
   is at least one core type where `EXPECTS_X = 1` AND `HAS_X = 0`.

4. **Check the project quantity total (Validity).** A project is also
   flagged when its combined quantity total —
   `SUM(QTY_KEY_QTY) + SUM(QTY_OTHER_QTY)` across every row of the
   project — is **strictly negative**. Individual rows may carry
   negative quantities (corrections / reversals) without failing; only
   the project aggregate is checked, and a total of exactly zero passes.
   Project **fails** AC4 iff it is flagged by step 3 **or** step 4.

5. **Row-level verdict.** A row fails iff its `PLANVIEW_ID` is
   flagged. Rows with null/blank `PLANVIEW_ID` pass, they cannot
   be assigned to a project group.

### Discipline classifier (scope detection vs. population detection)

ACCE classifies discipline off the `DESCRIPTION` estimate-line label -
an explicit per-core-type allow-list matched on `UPPER(TRIM(DESCRIPTION))`
(the former `ACCT` account-code classifier was retired). **Both** the
scope and population sides use the same `DESCRIPTION` lists; population
layers a UOM + positive-quantity constraint on top. MODULE_COUNT is the
only type that uses a substring match (`MODULE` / `MODULAR`) instead of
an exact list.

| Core type | Scope detection (`DESCRIPTION`) | Population detection (`DESCRIPTION` + UOM + qty) |
|---|---|---|
| `PIPING_LF` | `DESCRIPTION` ∈ piping list (`PIPING`, `CS PIPE ERECTION`, `FIREWATER PIPING`, …) | scope match AND UOM ∈ { `FEET`, `FT`, `M`, `METERS`, `LF` } |
| `CONCRETE_CY` | `DESCRIPTION` ∈ concrete list (`CONCRETE`, `CONCRETE POUR AND FINISH`, `FOUNDATION ACCESSORIES`, `OTHER EQUIP. CONCRETE`) | scope match AND UOM ∈ { `CY`, `M3`, `YD3`, `YDS`, `M³` } |
| `STEEL_TONS` | `DESCRIPTION` ∈ steel list (`STEEL`, `STEEL STRUCTURES`, `PIPERACK STEEL`, …) | scope match AND UOM ∈ { `TONS`, `TONNE`, `TON`, `T` } |
| `CABLE_LENGTH` | `DESCRIPTION` ∈ cable / electrical list (`ELECTRICAL`, `WIRE/CABLE - LV`, `CONDUIT`, `CABLE TRAYS`, …) | scope match AND UOM ∈ { `FEET`, `FT`, `M`, `METERS`, `LF` } |
| `TRANSMITTER_COUNT` | `DESCRIPTION` ∈ instrument list (`INSTRUMENTATION`, `FLOW INSTRUMENTS`, `PRESSURE INSTRUMENTS`, …) | scope match AND UOM ∈ { `EACH`, `EA`, `ITEM(S)`, `ITEM`, `ITEMS` } |
| `EQUIPMENT_COUNT` | `DESCRIPTION` ∈ equipment list (`CENTRIFUGAL PUMPS`, `S&T EXCHANGER`, `HORZ. VESSELS`, `GAS TURBINES`, …) | scope match AND UOM ∈ { `EACH`, `EA`, `ITEM(S)`, `ITEM`, `ITEMS` } |
| `MODULE_COUNT` | `DESCRIPTION` contains `MODULE` or `MODULAR` (substring) | scope match AND UOM ∈ { `EACH`, `EA`, `ITEM(S)`, `ITEM`, `ITEMS` } |

UOM matching is case-insensitive (`UPPER(TRIM(units))`) and compared
directly against the canonical spellings in each type's UOM set -
**no alias normalization** is applied on AC4 (unlike AC8, which uses
the shared `_A8_UOM_ALIASES` map). The full per-type `DESCRIPTION`
allow-lists live in `src/custom_dqr/_acce_rules.py`
(`_AC4_*_DESCRIPTIONS`); the abbreviated examples above are
representative, not exhaustive.

### Why scope ≠ population (the asymmetry)

Same reasoning as A4: scope detection accepts any UOM (a matching
`DESCRIPTION` alone implies the scope), but population detection
requires a specific UOM family. If a piping item is recorded with a
count unit (`EA`) instead of a length unit (`FEET`), the project still
has piping scope, but no `PIPING_LF` quantity is populated - FAIL.
That mismatch is what AC4 surfaces. Both sides share the same
`DESCRIPTION` allow-lists, so the asymmetry is purely the UOM +
positive-quantity gate that population adds on top of scope; there is
no per-type special case (the historical `CONCRETE_CY` carve-out that
checked only an account code + UOM was removed when the classifier
moved to `DESCRIPTION`).

### Why DESCRIPTION instead of ITEM_TYPE / ACCT

ADR labels its discipline via `ITEM_TYPE` strings like
`EstimatePump`, `EstimateSteelStructure` - A4 detects scope via
substring matches on those labels. ACCE originally mirrored this with
the `ACCT` account code (`2-EQP`, `3-PIP`, …), but that classifier was
retired: AC4 / AC7 / AC8 now key off the `DESCRIPTION` estimate-line
label, an explicit per-core-type allow-list matched on
`UPPER(TRIM(DESCRIPTION))`. The description carries the finer-grained
signal the account code lacked (e.g. it distinguishes concrete from
other civil scope and surfaces module-scope items), so a single
column drives both scope and population without a separate discipline
code.

### Failure modes

- Missing required column → all rows fail (structural
  incompleteness; same convention as the other custom rules).
- Project with at least one expected core type and no matching
  populated row → all rows of that project fail.

### Notes

- **Conservative `EQUIPMENT_COUNT`.** The UOM allow-list for
  equipment is intentionally narrow (count UOMs only, not
  weight / area). The intent is to count *major equipment items*,
  not every equipment-labelled row. Expanding the allow-list is a
  one-line change once business signs off on the additional UOMs.
- **Module scope is sparse.** `MODULE_COUNT` depends on the
  `DESCRIPTION` field containing `MODULE` or `MODULAR`, this will
  rarely be expected in ACCE datasets; the rule still evaluates
  it for completeness.

### Inputs

| Alias | Physical column |
|---|---|
| Project Key | `PLANVIEW_ID` |
| Item Description | `DESCRIPTION` |
| Key Quantity | `QTY_KEY_QTY` |
| Other Quantity | `QTY_OTHER_QTY` |
| Key Units | `QTY_KEY_UNITS` |
| Other Units | `QTY_OTHER_UNITS` |

### Decision matrix (per project)

| Condition | Project verdict |
|---|---|
| At least one `EXPECTS_X = 1` AND `HAS_X = 0` | **FAIL** |
| Every `EXPECTS_X = 1` has a matching `HAS_X = 1` | PASS |
| No core type is expected (project too small / off-pattern) | PASS |

---

## AC5: Design details present when quantity exists (ACCE)

- **Type:** Consistency · **Blocking:** No · **Data product:** ACCE
- **Implementation:** `check_acce_ac5`

A row passes when one of the following holds:

1. The estimate item has **no positive quantity** (out-of-scope,
   treated as PASS).
2. The estimate item has a **positive quantity** *and* a usable
   design detail - BOTH a named `DESIGN_PROPERTY` and a populated
   `DESIGN_VALUE`.

A row fails when a positive quantity exists *but* no usable design
detail (named parameter + value) is present for the same item.

### Where the inputs come from

AC5 operates on the **denormalized ACCE data product** built by the
data-product builder, which left-joins the child tables onto the
primary item record. The split quantity slots and the design columns
survive the per-`ROW_ID` / per-`DESIGN_ID` aggregation:

| Source table | Source column | Denormalized column | Notes |
|---|---|---|---|
| `ACCE_ESTIMATEQTYRESULTS` (1:N) | `KEY_QTY` | `QTY_KEY_QTY` | `SUM(KEY_QTY)` per item. |
| `ACCE_ESTIMATEQTYRESULTS` (1:N) | `OTHER_QTY` | `QTY_OTHER_QTY` | `SUM(OTHER_QTY)` per item. |
| `ACCE_ESTIMATEDESIGNDETAILS` (1:N) | `PROPERTY` | `DESIGN_PROPERTY` | Builder prefixes child columns with `DESIGN_`. The parameter **name**. |
| `ACCE_ESTIMATEDESIGNDETAILS` (1:N) | `VALUE` | `DESIGN_VALUE` | The parameter **value**. Existence check requires both `PROPERTY` and `VALUE` non-blank for the item's `DESIGN_ID`. |

### Pass / fail matrix

| `HAS_QUANTITY` | `HAS_DESIGN_DETAIL` | Result |
|---|---|---|
| 0 | 0 | PASS |
| 0 | 1 | PASS |
| 1 | 0 | **FAIL** |
| 1 | 1 | PASS |

Where:

- `HAS_QUANTITY = (QTY_KEY_QTY > 0) OR (QTY_OTHER_QTY > 0)`. Each slot
  is the per-`ROW_ID` SUM of `KEY_QTY` / `OTHER_QTY`. Null, zero, and
  **negative** aggregates in both slots all count as "no quantity"
  (the check is strictly positive).
- `HAS_DESIGN_DETAIL = DESIGN_PROPERTY is non-blank AND DESIGN_VALUE
  is non-blank` (whitespace-only strings are treated as blank, same
  `_is_filled` semantics used by AC1 / AC2). A bare value with no
  named parameter - the "120 m of what?" case - is **not** a usable
  detail.

### Why it matters

A quantity without supporting design information cannot be
normalized, compared across items, or validated, the analytical
value of the estimate drops sharply. AC5 is the lightweight gate
that surfaces the most consequential omission: **a quantity exists
but the engineering context that explains it does not.** Requiring a
named parameter alongside the value closes the loophole where a
stray value with no parameter name would otherwise satisfy the rule.

### Failure modes

- Missing any of `QTY_KEY_QTY`, `QTY_OTHER_QTY`, `DESIGN_PROPERTY`,
  or `DESIGN_VALUE` → all rows fail (structural incompleteness; same
  convention as the other custom rules).

### Notes

- The rule does not validate the *type* of design detail - any
  populated `(PROPERTY, VALUE)` pair in `ACCE_ESTIMATEDESIGNDETAILS`
  is sufficient. ACCE stores detailed properties (diameter, pressure,
  temperature, weight) which could enable stricter validation in a
  future extension.
- The `DESIGN_ID` join (item ↔ design) is the key link. Items
  without a `DESIGN_ID`, or whose `DESIGN_ID` has no matching rows
  in the design table, will have no design detail and will fail
  if quantity > 0.

### Inputs

| Alias | Physical column |
|---|---|
| Key Quantity | `QTY_KEY_QTY` |
| Other Quantity | `QTY_OTHER_QTY` |
| Design Parameter Name | `DESIGN_PROPERTY` |
| Design Parameter Value | `DESIGN_VALUE` |

---

## AC6: Construction hours present when quantity exists (ACCE)

- **Type:** Consistency · **Blocking:** No · **Data product:** ACCE
- **Implementation:** `check_acce_ac6`

A row passes when one of the following holds:

1. The estimate item has **no positive quantity** (out-of-scope,
   treated as PASS, same one-directional framing as AC5).
2. The estimate item has a **positive quantity** *and* the
   construction-hours aggregate is strictly greater than zero.

A row fails when a positive quantity exists *but* `COST_MH` is
zero / null / negative for the same item.

### Where the inputs come from

AC6 operates on the **denormalized ACCE data product**. Both the
quantity and the hours columns live on 1:N child tables of the item
record:

| Source table | Source column | Denormalized column | Notes |
|---|---|---|---|
| `ACCE_ESTIMATEQTYRESULTS` (1:N) | `KEY_QTY` | `QTY_KEY_QTY` | `SUM(KEY_QTY)` per item, same split inputs AC5 uses. |
| `ACCE_ESTIMATEQTYRESULTS` (1:N) | `OTHER_QTY` | `QTY_OTHER_QTY` | `SUM(OTHER_QTY)` per item. |
| `ACCE_ESTIMATECOSTRESULTS` (1:N) | `MH` | `COST_MH` | Sum of man-hours across cost rows. **Note:** ADR's analog is `COST_TOTAL_HOURS` (sourced from `TOTAL_HOURS`); ACCE's source column is `MH`, prefixed by the builder to `COST_MH`. |

### Pass / fail matrix

| `HAS_QUANTITY` | `HAS_CONSTRUCTION_HOURS` | Result |
|---|---|---|
| 0 | 0 | PASS |
| 0 | 1 | PASS |
| 1 | 0 | **FAIL** |
| 1 | 1 | PASS |

Where:

- `HAS_QUANTITY = (QTY_KEY_QTY > 0) OR (QTY_OTHER_QTY > 0)`. Same
  definition as AC5 - null, zero, and **negative** aggregates in both
  slots all count as "no quantity" (the check is strictly positive).
- `HAS_CONSTRUCTION_HOURS = (COST_MH > 0)`. Null inputs are coerced
  to zero. Negative aggregates do **not** count as hours present,
  so the comparison is strictly `> 0` (not `<> 0`).

### ACCE-specific note on DB_TOTAL_HOURS

Unlike ADR (which has both `COST_TOTAL_HOURS` and
`COST_DB_TOTAL_HOURS` and accepts either), ACCE does not segregate
Design-Build hours into a separate column. The rule therefore
evaluates only `COST_MH` (sourced from `MH`):

```
HAS_CONSTRUCTION_HOURS = (COST_MH > 0)
```

This is equivalent to ADR's
`(COST_TOTAL_HOURS > 0) OR (COST_DB_TOTAL_HOURS > 0)` when only
one hours column exists.

### Why it matters

Quantity and construction hours together drive productivity
analysis (hours per unit, unit-rate benchmarking, EMMA
normalization). A quantity without matching hours is not useful
for productivity work, which is the primary reason ACCE estimates
are consumed downstream.

### Failure modes

- Missing any of `QTY_KEY_QTY`, `QTY_OTHER_QTY`, or `COST_MH` column
  → all rows fail (structural incompleteness; same convention as the
  other custom rules).

### Notes

- **One-directional check.** Hours without a quantity is **PASS**,
  not fail - AC6 only enforces the implication
  `quantity → construction hours`. Items with hours but no
  quantity are out of scope.
- **Aggregation caveat.** Because the data-product builder
  aggregates by SUM, hypothetical equal-and-opposite values
  collapse to zero, the rule then treats the item as having no
  hours. In practice ACCE man-hours are non-negative.

### Inputs

| Alias | Physical column |
|---|---|
| Key Quantity | `QTY_KEY_QTY` |
| Other Quantity | `QTY_OTHER_QTY` |
| Construction Hours | `COST_MH` |

---

## AC7: Within-discipline quantity / hour ratio outlier (ACCE)

- **Type:** Statistical Outlier · **Blocking:** No · **Data product:** ACCE
- **Implementation:** `check_acce_ac7`

A per-item Statistical Outlier rule with row-level verdict. AC7
looks for items whose **hours-per-quantity ratio** is unusual
*within its peer group*, same raw `DESCRIPTION` (estimate-line
label) and same `QTY_UOM`. The threshold is derived from the segment
itself (IQR), not from a fixed benchmark.

### Algorithm

1. **Per-row eligibility.** A row enters the population only when:

   ```
   (KEY_QTY > 0 OR OTHER_QTY > 0)
   AND COST_MH        > 0
   AND DESCRIPTION    is non-null / non-blank
   AND effective UOM  is non-null / non-blank
   ```

   Anything else is **not applicable** and passes, the rule cannot
   produce a verdict without a calculable ratio and a segment to
   compare against.

2. **Ratio.** For each eligible row:

   ```
   QTY_QUANTITY       = COALESCE(KEY_QTY, 0) + COALESCE(OTHER_QTY, 0)
   HOURS_PER_QUANTITY = COST_MH / QTY_QUANTITY
   ```

   The split quantities and hours are SUM-aggregated by `ROW_ID`
   upstream (the data-product builder collapses the 1:N child rows
   of the cost and quantity facts).

3. **Segment statistics.** Eligible rows are partitioned by
   `(DESCRIPTION, QTY_UOM)` - the raw `UPPER(TRIM(DESCRIPTION))` value
   paired with the effective UOM `COALESCE(KEY_UNITS, OTHER_UNITS)`.
   For each segment:

   ```
   Q1  = quantile(HOURS_PER_QUANTITY, 0.25)
   Q3  = quantile(HOURS_PER_QUANTITY, 0.75)
   IQR = Q3 - Q1
   ```

4. **Mild bounds (the FAIL boundary).**

   ```
   MILD_LOWER = Q1 - k · IQR
   MILD_UPPER = Q3 + k · IQR
   ```

   where `k` defaults to `ACCE_AC7_MILD_IQR_MULTIPLIER` (1.5×) and
   is customizable via the `threshold_iqr_multiplier` selectbox.
   A row **fails** when its ratio is below `MILD_LOWER` or above
   `MILD_UPPER`.

   The 3.0× extreme multiplier
   (`ACCE_AC7_EXTREME_IQR_MULTIPLIER`) is documented as a constant
   so future code can classify severity, but the Boolean check uses
   only the mild bound, every extreme outlier is also a mild
   outlier and therefore a FAIL.

### NOT_APPLICABLE (treated as PASS) cases

AC7 does not surface a separate "NA" bucket, it returns Booleans
only. The cases below map to PASS to avoid double-counting against
rules that already cover those gaps:

- **Ratio cannot be calculated** (no positive qty, or hours missing
  / zero / negative) - AC6 covers the missing-hours case for
  positive quantities.
- **`DESCRIPTION` or the effective UOM blank**: no segment to compare
  against.
- **Segment population below `ACCE_AC7_MIN_POPULATION`** (default
  `10`) - too small to derive thresholds.
- **Segment `IQR == 0`**: no variation across the segment, every
  observation sits on the median; outlier detection is not
  meaningful.

### Where the inputs come from

AC7 operates on the **denormalized ACCE data product**. `DESCRIPTION`
is a pass-through from the primary item table; the split quantity /
unit columns and hours come from the SUM-aggregated 1:N child tables:

| Source table | Source column | Denormalized column | Notes |
|---|---|---|---|
| `ACCE_ESTIMATEITEMRECORD` (1:1) | `DESCRIPTION` | `DESCRIPTION` | Pass-through. The raw estimate-line label; the segment key uses `UPPER(TRIM(...))`. |
| `ACCE_ESTIMATEQTYRESULTS` (1:N) | `KEY_QTY` | `QTY_KEY_QTY` | `SUM(KEY_QTY)` per item. |
| `ACCE_ESTIMATEQTYRESULTS` (1:N) | `OTHER_QTY` | `QTY_OTHER_QTY` | `SUM(OTHER_QTY)` per item. |
| `ACCE_ESTIMATEQTYRESULTS` (1:N) | `KEY_UNITS` | `QTY_KEY_UNITS` | First non-null per item. Effective UOM = `COALESCE(KEY_UNITS, OTHER_UNITS)`. |
| `ACCE_ESTIMATEQTYRESULTS` (1:N) | `OTHER_UNITS` | `QTY_OTHER_UNITS` | First non-null per item. |
| `ACCE_ESTIMATECOSTRESULTS` (1:N) | `MH` | `COST_MH` | Sum of man-hours across cost rows. **Note:** ADR's analog is `COST_TOTAL_HOURS` (sourced from `TOTAL_HOURS`); ACCE's source is `MH`. |

### Why it matters

AC7 is the productivity sanity check. Hours per foot of pipe, hours
per cubic yard of concrete, hours per ton of steel, these ratios
are tight within a discipline because they reflect physical effort.
A row that lies far outside its segment's IQR almost always points
to one of: an incorrect quantity, an incorrect hours total, a UOM
mismatch, or a genuinely unusual project condition. AC7 surfaces
those rows for review; it does **not** assert they are wrong.

### Differences from ADR A7

| Aspect | A7 (ADR) | AC7 (ACCE) |
|---|---|---|
| Segment key | `(ITEM_TYPE, QTY_UOM)` (substring match on `Estimate*` labels) | `(DESCRIPTION, QTY_UOM)` (raw `UPPER(TRIM(DESCRIPTION))` value + effective UOM) |
| Quantity | `SUM(QUANTITY)` per item | `COALESCE(KEY_QTY, 0) + COALESCE(OTHER_QTY, 0)`; eligible when either slot > 0 |
| Hours column | `COST_TOTAL_HOURS` (sourced from `TOTAL_HOURS`) | `COST_MH` (sourced from `MH`) |
| Project-scope toggle | `segment_by_project_type` extends the key with `(E05_DEPARTMENT, BUSINESS)` from Planview | Same toggle exposed - extends `(DESCRIPTION, QTY_UOM)` → `(DESCRIPTION, QTY_UOM, E05_DEPARTMENT, BUSINESS)` |
| Reference dataset | `VWS_GP_STANDARD_SHARE` (only when toggle on) | Same - `VWS_GP_STANDARD_SHARE` is only consulted when the toggle is on |

### Notes

- **Thresholds are derived from the data**, not hard-coded. There
  is no "correct" hours-per-quantity ratio, the rule benchmarks
  each item against its own peers.
- **Segmentation uses the raw `DESCRIPTION` value** (estimate-line
  label) - finer-grained than ADR's `Estimate*` types, so segments
  are per-label rather than per-discipline.
- **Schema-level missing column → all rows fail**, mirroring the
  convention used by all other custom rules.
- **Failed records are review candidates, not errors.** A FAIL
  means the ratio is unusual; it does not prove the data is wrong.

### Inputs

| Alias | Physical column |
|---|---|
| Item Description | `DESCRIPTION` |
| Key Quantity | `QTY_KEY_QTY` |
| Other Quantity | `QTY_OTHER_QTY` |
| Key Units | `QTY_KEY_UNITS` |
| Other Units | `QTY_OTHER_UNITS` |
| Construction Hours | `COST_MH` |
| Project Key (only when `segment_by_project_type` is on) | `PLANVIEW_ID` |

### Options

| Key | Widget | Default | Effect |
|---|---|---|---|
| `threshold_iqr_multiplier` | `st.selectbox` | `1.5` | IQR multiplier used to derive the per-segment PASS band. Choices: **1.5×IQR (mild - recommended)**, 2.0×IQR, 3.0×IQR (extreme). |
| `segment_by_project_type` | `st.toggle` | `False` | Extend the IQR segment key with the composite project-type tuple `(E05_DEPARTMENT, BUSINESS)` resolved from `VWS_GP_STANDARD_SHARE` via `PLANVIEW_ID → PROJECT_ID`. When on the segment becomes `(DESCRIPTION, QTY_UOM, E05_DEPARTMENT, BUSINESS)`; rows whose project-type cannot be resolved are NOT_APPLICABLE → PASS; the rule raises `CustomRuleNotEvaluated` when the reference dataset is unavailable. |

### Tunables

| Constant | Default | Effect |
|---|---|---|
| `ACCE_AC7_MILD_IQR_MULTIPLIER` | `1.5` | Default IQR multiplier (overridable via the `threshold_iqr_multiplier` option). Defines the PASS / FAIL boundary (`Q1 - k·IQR` … `Q3 + k·IQR`). |
| `ACCE_AC7_EXTREME_IQR_MULTIPLIER` | `3.0` | Documented for severity classification; not consulted by the Boolean check today. |
| `ACCE_AC7_MIN_POPULATION` | `10` | Segments with fewer eligible rows are NOT_APPLICABLE (every row passes). Applies per-segment in segmented mode. |

---

## AC8: Cross-discipline quantity ratios (ACCE)

- **Type:** Statistical Outlier · **Blocking:** No · **Data product:** ACCE
- **Implementation:** `check_acce_ac8` (with
  `_classify_ac8_category_acce` for the discipline mapping).

AC8 validates the **overall shape of each project**. Where AC7 looks
at hours-per-quantity within a single discipline, AC8 looks at the
proportions *between* disciplines - pipe length per equipment count,
cable length per transmitter count, steel weight per concrete
volume. A project whose proportions sit far from the peer-project
population is flagged for review.

### Algorithm

1. **Per-row eligibility.** A row enters the aggregation when:

   ```
   (KEY_QTY > 0 OR OTHER_QTY > 0)
   AND COMPONENT_SOURCE populated
   AND DESCRIPTION      populated
   AND (KEY_UNITS populated OR OTHER_UNITS populated)
   ```

2. **Discipline classification.** Each eligible row is mapped to one
   of six categories using `DESCRIPTION` (an explicit per-discipline
   value list, the same taxonomy AC4 uses) plus a per-category unit
   gate: the row classifies when its `DESCRIPTION` is in the list AND
   `KEY_UNITS` **or** `OTHER_UNITS` is in the category's UOM family
   (all compared on `UPPER(TRIM(...))`):

| Category | `DESCRIPTION` list (examples) | `KEY_UNITS` / `OTHER_UNITS` family |
|---|---|---|
| `STEEL_WEIGHT` | `STEEL`, `STEEL STRUCTURES`, `PIPERACK STEEL`, … | `TONS`, `TONNE`, `TON`, `T` |
| `CONCRETE_VOLUME` | `CONCRETE`, `FOUNDATION ACCESSORIES`, … | `CY`, `M3`, `YD3`, `YD`, `M³` |
| `PIPE_LENGTH` | `PIPING`, `CS PIPE ERECTION`, `FIREWATER PIPING`, … | `FEET`, `FT`, `M`, `METERS`, `LF` |
| `CABLE_LENGTH` | `ELECTRICAL`, `WIRE/CABLE - LV`, `CABLE TRAYS`, … | `FEET`, `FT`, `M`, `METERS`, `LF` |
| `TRANSMITTER_COUNT` | `INSTRUMENTATION`, `FLOW INSTRUMENTS`, … | `EACH`, `EA`, `ITEM`, `ITEMS`, `ITEM(S)` |
| `EQUIPMENT_COUNT` | `CENTRIFUGAL PUMPS`, `S&T EXCHANGER`, … | `EACH`, `EA`, `ITEM`, `ITEMS`, `ITEM(S)` |

> **AC8's volume UOM set differs from AC4's.** AC8 admits the bare
> `YD` spelling where AC4 admits `YDS`; the length / weight / count
> sets carry the same spellings. The six `DESCRIPTION` lists match
> AC4's taxonomy except AC8's equipment list spells the
> turbo-expander compressor `TURBO-EXPAND, COMPRESSOR` (comma) where
> AC4 uses a period.

Rows the classifier does not recognise are **not eligible** for any
ratio and have no effect on the result.

3. **Aggregate by `(COMPONENT_SOURCE, category)`.** The per-row
   quantity `COALESCE(KEY_QTY, 0) + COALESCE(OTHER_QTY, 0)` is summed,
   the discipline-level total used as numerator or denominator.

4. **Compute cross-discipline ratios per project.** AC8 evaluates
   three:

   ```
   PIPE_LENGTH    / EQUIPMENT_COUNT
   CABLE_LENGTH   / TRANSMITTER_COUNT
   STEEL_WEIGHT   / CONCRETE_VOLUME
   ```

   A project is included in a ratio's population when the
   **denominator** is strictly greater than zero (`NULLIF(den, 0)`
   semantics). The **numerator may be `0`**: a project with no
   pipe but with equipment contributes a valid `0` ratio that
   participates in the population baseline and is judged against
   the IQR.

5. **Per-ratio IQR bounds across projects.** For each ratio:

   ```
   Q1         = quantile(RATIO_VALUE, 0.25)
   Q3         = quantile(RATIO_VALUE, 0.75)
   IQR        = Q3 - Q1
   MILD_LOWER = Q1 - k · IQR
   MILD_UPPER = Q3 + k · IQR
   ```

   where `k` defaults to `ACCE_AC8_MILD_IQR_MULTIPLIER` (1.5×) and
   is customizable via the `threshold_iqr_multiplier` selectbox.
   A project is **flagged on this ratio** when its ratio is below
   the lower bound or above the upper bound. The 3.0× extreme
   multiplier (`ACCE_AC8_EXTREME_IQR_MULTIPLIER`) is documented for
   severity classification, every extreme outlier is already a
   mild outlier and therefore a FAIL, so the Boolean check uses
   only the mild bound.

6. **Row-level verdict.** A row **fails** AC8 iff its
   `COMPONENT_SOURCE` is flagged on at least one of the ratios above.
   Rows whose project is unknown (null / blank `COMPONENT_SOURCE`)
   pass, they cannot be assigned to a project group.

### NOT_APPLICABLE (treated as PASS) cases

- **Row's `COMPONENT_SOURCE` is null / blank**: no project to attach
  to.
- **Row's quantity / `DESCRIPTION` / units cannot be classified**:
  the row contributes to no ratio and therefore can't trigger one.
- **Per-ratio population below `ACCE_AC8_MIN_POPULATION`** (default
  `10`) - too few projects to derive thresholds for that specific
  ratio.
- **Per-ratio population `IQR == 0`**: every project's ratio sits
  on the median; outlier detection is not meaningful.

### Where the inputs come from

AC8 operates on the **denormalized ACCE data product**.
`COMPONENT_SOURCE` and `DESCRIPTION` are pass-throughs from the
primary item table; the split QTY columns survive the 1:N child
aggregation (numerics summed, units kept as the first non-null):

| Source table | Source column | Denormalized column | Notes |
|---|---|---|---|
| `ACCE_ESTIMATEITEMRECORD` (1:1) | `COMPONENT_SOURCE` | `COMPONENT_SOURCE` | Pass-through. The project / scope key. |
| `ACCE_ESTIMATEITEMRECORD` (1:1) | `DESCRIPTION` | `DESCRIPTION` | Pass-through. Drives the discipline classifier. |
| `ACCE_ESTIMATEQTYRESULTS` (1:N) | `KEY_QTY` | `QTY_KEY_QTY` | `SUM(KEY_QTY)` per item. |
| `ACCE_ESTIMATEQTYRESULTS` (1:N) | `OTHER_QTY` | `QTY_OTHER_QTY` | `SUM(OTHER_QTY)` per item. |
| `ACCE_ESTIMATEQTYRESULTS` (1:N) | `KEY_UNITS` | `QTY_KEY_UNITS` | First non-null per item. |
| `ACCE_ESTIMATEQTYRESULTS` (1:N) | `OTHER_UNITS` | `QTY_OTHER_UNITS` | First non-null per item. |

### Why it matters

Absolute quantities can vary wildly across projects, but the
**proportion** between disciplines is driven by physical reality -
you can't have a hundred pumps without commensurate piping and
cable. When that proportion breaks, it's almost always a sign of:
data-entry error, missing quantities for one discipline, UOM
mismatch, mis-classified scope, or a genuinely unusual project.
AC8 surfaces those projects for review; it does **not** assert
they are wrong.

### Differences from ADR A8

| Aspect | A8 (ADR) | AC8 (ACCE) |
|---|---|---|
| Project key | `ROOT_ITEM_NAME` | `COMPONENT_SOURCE` |
| Classifier | Substring sweep over `Estimate*` `ITEM_TYPE` labels, per-(`ITEM_TYPE`, `UOM`) allow-list for `EQUIPMENT_COUNT` | `DESCRIPTION` value lists (per discipline) gated by a `KEY_UNITS` / `OTHER_UNITS` family match |
| Quantity | `SUM(QUANTITY)` per item | `COALESCE(KEY_QTY, 0) + COALESCE(OTHER_QTY, 0)` per row, summed per project |
| Project-scope toggle | `segment_by_project_type` partitions per-ratio IQR by `(E05_DEPARTMENT, BUSINESS)` from Planview | Same toggle exposed - partitions per-ratio IQR by `(E05_DEPARTMENT, BUSINESS)` (resolved via the first non-blank `PLANVIEW_ID` per `COMPONENT_SOURCE`) |
| Reference dataset | `VWS_GP_STANDARD_SHARE` (only when toggle on) | Same - `VWS_GP_STANDARD_SHARE` is only consulted when the toggle is on |

### Notes

- **One project, multiple ratio results.** A project can fail one
  ratio and pass another. The Boolean per-row output collapses
  across ratios - a project with at least one flagged ratio is
  failing.
- **Classification uses `DESCRIPTION` value lists instead of ADR's
  `ITEM_TYPE` substrings.** The six per-discipline lists are the same
  taxonomy AC4 keys off; a row classifies when its `DESCRIPTION` is in
  a list and either unit slot is in the category's UOM family.
- **UOM matching is case-insensitive** after `UPPER(TRIM(...))`, with
  no alias normalization (the lists carry the canonical spellings).
- **Schema-level missing column → all rows fail**, mirroring the
  convention used by all other custom rules.
- **Failed projects are review candidates, not errors.** A FAIL
  means the project's shape is unusual; it does not prove the
  data is wrong.

### Inputs

| Alias | Physical column |
|---|---|
| Project Scope | `COMPONENT_SOURCE` |
| Item Description | `DESCRIPTION` |
| Key Quantity | `QTY_KEY_QTY` |
| Other Quantity | `QTY_OTHER_QTY` |
| Key Units | `QTY_KEY_UNITS` |
| Other Units | `QTY_OTHER_UNITS` |
| Project Key (only when `segment_by_project_type` is on) | `PLANVIEW_ID` |

### Options

| Key | Widget | Default | Effect |
|---|---|---|---|
| `threshold_iqr_multiplier` | `st.selectbox` | `1.5` | IQR multiplier used to derive each cross-discipline ratio's PASS band. Choices: **1.5×IQR (mild - recommended)**, 2.0×IQR, 3.0×IQR (extreme). |
| `segment_by_project_type` | `st.toggle` | `False` | Partition each per-ratio IQR baseline by the composite project-type tuple `(E05_DEPARTMENT, BUSINESS)` resolved from `VWS_GP_STANDARD_SHARE` via the first non-blank `PLANVIEW_ID` seen per `COMPONENT_SOURCE`. Per-segment populations below `ACCE_AC8_MIN_POPULATION` stay NOT_APPLICABLE → PASS; projects whose project-type cannot be resolved are NOT_APPLICABLE → PASS; the rule raises `CustomRuleNotEvaluated` when the reference dataset is unavailable. |

### Tunables

| Constant | Default | Effect |
|---|---|---|
| `ACCE_AC8_MILD_IQR_MULTIPLIER` | `1.5` | Default IQR multiplier (overridable via the `threshold_iqr_multiplier` option). Defines the PASS / FAIL boundary (`Q1 - k·IQR` … `Q3 + k·IQR`). |
| `ACCE_AC8_EXTREME_IQR_MULTIPLIER` | `3.0` | Documented for severity classification; not consulted by the Boolean check today. |
| `ACCE_AC8_MIN_POPULATION` | `10` | Ratios with fewer projects in the population are NOT_APPLICABLE (every project on that ratio passes). Applies per-segment in segmented mode. |

### Ratios evaluated today

| Ratio | Numerator | Denominator |
|---|---|---|
| `PIPE_LENGTH_PER_EQUIPMENT_COUNT` | `PIPE_LENGTH` | `EQUIPMENT_COUNT` |
| `CABLE_LENGTH_PER_TRANSMITTER_COUNT` | `CABLE_LENGTH` | `TRANSMITTER_COUNT` |
| `STEEL_WEIGHT_PER_CONCRETE_VOLUME` | `STEEL_WEIGHT` | `CONCRETE_VOLUME` |

Adding a new ratio is a one-line change in `_AC8_RATIOS` once the
underlying categories are produced by
`_classify_ac8_category_acce`.

---

## SQ4: Valid date (EXPECTED_SHIP_DATE) - SQS

- **Type:** Validity · **Blocking:** No · **Data product:** SQS (Quality domain)
- **Implementation:** `check_sqs_sq4` (uses `pd.to_datetime(..., errors="coerce")` directly).
- **Reference dataset:** *(none)*

A row passes when `EXPECTED_SHIP_DATE` is **non-null** **and** parses as
a valid calendar date. The check mirrors the Snowflake spec's defensive
round-trip
(`TRY_TO_DATE(TO_VARCHAR(EXPECTED_SHIP_DATE, 'YYYY-MM-DD'), 'YYYY-MM-DD')`)
via `pandas.to_datetime` with `errors="coerce"`: unparseable values land
as `NaT` and fail alongside genuine NULLs. The schema-level missing
column makes every row fail (same convention as the other custom rules).

**Why it matters.** `EXPECTED_SHIP_DATE` drives shipment sequencing,
logistics planning, and downstream reporting in the SQS inspection
workflow. Missing or invalid dates break the downstream pipeline and
distort throughput metrics.

**Failure scenarios.**

| Scenario | Example value | Result |
|----------|---------------|--------|
| Valid date | `2024-06-15 00:00:00` (TIMESTAMP_NTZ) | PASS |
| NULL value | `NULL` | FAIL |
| Invalid date (loaded via VARIANT/string) | `"2024-13-40"` | FAIL |

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| Expected Ship Date | `EXPECTED_SHIP_DATE` |

**Implementation notes.** The column is stored as `TIMESTAMP_NTZ`, so
Snowflake enforces well-formed datetime values at ingestion. In
production the dominant failure mode is NULL; the round-trip parser is
preserved for defensive coverage of values arriving via VARIANT / string
paths.

---

## SQ5: Not after PO Required Ship Date - SQS

- **Type:** Business Rule · **Blocking:** No · **Data product:** SQS (Quality domain)
- **Implementation:** `check_sqs_sq5` (uses `pd.to_datetime(..., errors="coerce")` for both columns then compares with `>`).
- **Reference dataset:** *(none)*

A row passes when **any** of the following holds:

1. `EXPECTED_SHIP_DATE` is NULL or unparseable.
2. `PO_REQUIRED_SHIP_DATE` is NULL or unparseable.
3. `EXPECTED_SHIP_DATE <= PO_REQUIRED_SHIP_DATE`.

A row fails only when **both** dates resolve to valid datetimes **and**
the expected ship date is strictly **after** the PO required ship date.
The comparison uses `>` so equal dates are compliant. NULL handling
mirrors the Snowflake spec (`WHEN ... IS NULL THEN 'PASS'`) so SQ5
never double-penalises the completeness gap SQ4 already covers. The
schema-level missing column makes every row fail (same convention as
the other custom rules).

**Why it matters.** `EXPECTED_SHIP_DATE` is the supplier's projected
ship date; `PO_REQUIRED_SHIP_DATE` is the contractual deadline on the
purchase order. When the projected ship date slips past the PO required
date, the project faces a likely delivery delay with downstream
logistics and contractual fallout.

**Failure scenarios.**

| Scenario | `EXPECTED_SHIP_DATE` | `PO_REQUIRED_SHIP_DATE` | Result |
|----------|----------------------|-------------------------|--------|
| Expected before PO required | `2024-06-10` | `2024-06-15` | PASS |
| Expected equals PO required | `2024-06-15` | `2024-06-15` | PASS |
| Expected after PO required | `2024-06-20` | `2024-06-15` | **FAIL** |
| `EXPECTED_SHIP_DATE` is NULL | `NULL` | `2024-06-15` | PASS |
| `PO_REQUIRED_SHIP_DATE` is NULL | `2024-06-10` | `NULL` | PASS |
| Both are NULL | `NULL` | `NULL` | PASS |

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| Expected Ship Date | `EXPECTED_SHIP_DATE` |
| PO Required Ship Date | `PO_REQUIRED_SHIP_DATE` |

**Implementation notes.** Both columns are `TIMESTAMP_NTZ` in Snowflake
so the comparison maps directly to `pandas` after
`pd.to_datetime(..., errors="coerce")` is applied to each side -
unparseable strings collapse to `NaT` and inherit the NULL-PASS branch.
Equality is intentionally treated as compliant per spec
(`EXPECTED_SHIP_DATE > PO_REQUIRED_SHIP_DATE` is the FAIL predicate).

---

## SQ6: Inspection Type value in allowed set - SQS

- **Type:** Validity · **Blocking:** No · **Data product:** SQS (Quality domain)
- **Implementation:** `check_sqs_sq6` →
  `df["INSPECTION_TYPE"].isin(SQS_SQ6_ALLOWED_VALUES)`.
- **Reference dataset:** *(none - the allowed set is a module-level tuple)*

A row passes when `INSPECTION_TYPE` matches one of the allowed values
**verbatim**:

| Allowed value |
|---------------|
| `Source Inspection` |
| `Supplier Assessment` |
| `Expediting` |
| `Supplemental Inspection` |

The match is **case-sensitive** per the Snowflake `IN` operator -
`"source inspection"` is FAIL even though it represents the same
logical category. NULL values FAIL (Snowflake's `IN` does not match
NULLs). Schema-level missing column makes every row fail (same
convention as the other custom rules).

**Why it matters.** `INSPECTION_TYPE` drives downstream reporting,
resource allocation, and cost estimation. Off-list values break
category-based aggregations and can misroute inspection assignments;
keeping the vocabulary controlled preserves the integrity of those
workflows.

**Failure scenarios.**

| Scenario | Example value | Result |
|----------|---------------|--------|
| Allowed value | `Source Inspection` | PASS |
| Allowed value | `Supplier Assessment` | PASS |
| NULL value | `NULL` | **FAIL** |
| Unexpected value | `Audit` | **FAIL** |
| Typo / case mismatch | `source inspection` | **FAIL** |
| Variant / wrong form | `Expedite` | **FAIL** |

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| Inspection Type | `INSPECTION_TYPE` |

**Implementation notes.** The allowed list is exposed as
`SQS_SQ6_ALLOWED_VALUES` (immutable tuple) on
[src/custom_dqr_engine.py](../src/custom_dqr_engine.py); rule callers
or tests that need to assert against it should import from the engine
shim rather than re-typing the strings. Review the allowed set
periodically with business stakeholders so legitimate new categories
are added instead of polluting the FAIL bucket.

---

## SQ7: Work Criticality value in allowed set - SQS

- **Type:** Validity · **Blocking:** No · **Data product:** SQS (Quality domain)
- **Implementation:** `check_sqs_sq7` →
  `df["WORK_CRITICALITY"].isin(SQS_SQ7_ALLOWED_VALUES)`.
- **Reference dataset:** *(none - the allowed set is a module-level tuple)*

A row passes when `WORK_CRITICALITY` matches one of the four
classification levels **verbatim**:

| Allowed value | Description |
|---------------|-------------|
| `I - High Critical` | Highest priority classification |
| `II - Medium Critical` | Medium priority classification |
| `III - Low Critical` | Low priority classification |
| `IV - Non Critical` | Non-critical classification |

The match is **case-sensitive** per the Snowflake `IN` operator -
`"i - high critical"` and `"I - HIGH CRITICAL"` both FAIL. NULL values
FAIL (Snowflake's `IN` does not match NULLs). Empty strings likewise
FAIL. Schema-level missing column makes every row fail (same
convention as the other custom rules).

**Why it matters.** `WORK_CRITICALITY` drives prioritization of
resources, risk assessment, and downstream reporting. Non-standard
values misclassify work priority and skew every analytic built on top.

**Failure scenarios.**

| Scenario | Example value | Result |
|----------|---------------|--------|
| Valid value – High | `I - High Critical` | PASS |
| Valid value – Medium | `II - Medium Critical` | PASS |
| Valid value – Low | `III - Low Critical` | PASS |
| Valid value – Non Critical | `IV - Non Critical` | PASS |
| NULL value | `NULL` | **FAIL** |
| Typo or case variation | `I - High critical` | **FAIL** |
| Unexpected value | `V - Unknown` | **FAIL** |
| Empty string | `""` | **FAIL** |

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| Work Criticality | `WORK_CRITICALITY` |

**Implementation notes.** The allowed list is exposed as
`SQS_SQ7_ALLOWED_VALUES` (immutable tuple) on
[src/custom_dqr_engine.py](../src/custom_dqr_engine.py); rule callers
or tests should import from the engine shim rather than re-typing the
roman-numeral strings. Adding a new classification level requires
updating the tuple **and** a business-justification entry, not a
per-row workaround.

---

## SQ8: Status required - SQS

- **Type:** Completeness · **Blocking:** No · **Data product:** SQS (Quality domain)
- **Implementation:** `check_sqs_sq8` →
  `validate_completeness_rule(df, ["STATUS"])`.
- **Reference dataset:** *(none)*

A row passes when `STATUS` is non-null **and** contains at least one
non-whitespace character. Mirrors the Snowflake spec predicate
`STATUS IS NULL OR TRIM(STATUS) = ''` by delegating to
`validate_completeness_rule`, which already applies `_is_filled`
(`Series.notna()` plus trim-and-compare-to-empty for string-typed
columns) - the same semantics every other Completeness rule
(`E1`, `E4`, …) uses. Schema-level missing column makes every row fail.

**Why it matters.** `STATUS` tracks the lifecycle of each inspection
record (e.g. `Pending`, `In Progress`, `Completed`). Missing or empty
values create blind spots in workflow monitoring, break status-based
filtering / routing, and skew progress reporting.

**Failure scenarios.**

| Scenario | Example value | Result |
|----------|---------------|--------|
| Populated status | `Completed` | PASS |
| Populated status | `In Progress` | PASS |
| NULL value | `NULL` | **FAIL** |
| Empty string | `""` | **FAIL** |
| Whitespace only | `"   "` (spaces / tabs / newlines) | **FAIL** |

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| Status | `STATUS` |

**Implementation notes.** Reusing `validate_completeness_rule` keeps
SQ8 in lockstep with the EPT / ADR / ACCE Completeness rules: same
NULL handling, same string-trim convention, same all-FAIL response
when the column is structurally absent from the data product.

---

## SQ9: Status value in allowed set - SQS

- **Type:** Validity · **Blocking:** No · **Data product:** SQS (Quality domain)
- **Implementation:** `check_sqs_sq9` →
  `df["STATUS"].isin(SQS_SQ9_ALLOWED_VALUES)`.
- **Reference dataset:** *(none - the allowed set is a module-level tuple)*

A row passes when `STATUS` matches one of the 11 canonical workflow
statuses **verbatim**:

| # | Allowed value |
|---|---------------|
| 1 | `Approved` |
| 2 | `Inspection In Progress` |
| 3 | `Completed` |
| 4 | `Inspection Approved` |
| 5 | `Pending SER Review` |
| 6 | `Additional Funding Requested` |
| 7 | `Deprecated` |
| 8 | `Pending Review` |
| 9 | `Completed (Short Closed)` |
| 10 | `Inspection Rejected` |
| 11 | `OAP Pending` |

The match is **case-sensitive** per the Snowflake `IN` operator -
`"approved"` and `"APPROVED"` both FAIL. Leading / trailing whitespace
also FAIL (`" Approved "` is not in the allowed list because `isin`
performs exact equality). NULL values FAIL (Snowflake's `IN` does not
match NULLs). Schema-level missing column makes every row fail.

**Why it matters.** `STATUS` drives workflow logic, automated
transitions, and reporting dashboards. Off-list values fall outside
monitoring scope, break status-based routing, and skew KPIs.

**Layering with SQ8.** SQ8 (Completeness) and SQ9 (Validity) cover the
same column on purpose:

| Row value | SQ8 (`STATUS` populated) | SQ9 (`STATUS` in allowed set) |
|-----------|--------------------------|-------------------------------|
| `Approved` | PASS | PASS |
| `Cancelled` (off-list) | PASS | **FAIL** |
| `NULL` | **FAIL** | **FAIL** |
| `"   "` (whitespace) | **FAIL** | **FAIL** |

SQ8 surfaces NULL / blank gaps; SQ9 surfaces typos, case variants and
unauthorised categories. Enable both for full coverage on `STATUS`.

**Failure scenarios.**

| Scenario | Example value | Result |
|----------|---------------|--------|
| Valid status | `Approved` | PASS |
| Valid status | `Inspection In Progress` | PASS |
| NULL value | `NULL` | **FAIL** |
| Unexpected status | `Cancelled` | **FAIL** |
| Case mismatch | `approved` | **FAIL** |
| Leading / trailing spaces | `" Approved "` | **FAIL** |

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| Status | `STATUS` |

**Implementation notes.** The allowed list is exposed as
`SQS_SQ9_ALLOWED_VALUES` (immutable tuple) on
[src/custom_dqr_engine.py](../src/custom_dqr_engine.py); rule callers
or tests should import from the engine shim rather than re-typing the
11 strings. Adding a new legitimate status requires updating the tuple
**and** a business-justification entry, not a per-row workaround.

---

## SQ10: Status / Expected Ship Date sequencing - SQS

- **Type:** Business Rule · **Blocking:** No · **Data product:** SQS (Quality domain)
- **Implementation:** `check_sqs_sq10` (cross-column check; uses
  `pd.Timestamp.now()` for the reference time and
  `pd.to_datetime(..., errors="coerce")` for the ship date).
- **Reference dataset:** *(none)*

A row passes when **any** of the following holds:

1. `STATUS` is anything other than `"Completed"` (the rule only applies
   to completed assignments).
2. `EXPECTED_SHIP_DATE` is NULL or unparseable (SQ4 owns the
   date-validity gap).
3. `EXPECTED_SHIP_DATE` is on or before `pd.Timestamp.now()`.

A row fails only when `STATUS == "Completed"` **and**
`EXPECTED_SHIP_DATE` resolves to a strictly future timestamp relative
to the reference time. The check captures `pd.Timestamp.now()` once per
call so a single batch evaluation is internally consistent across rows
- the reference still drifts between runs, which mirrors the Snowflake
spec's use of `CURRENT_TIMESTAMP()`. Schema-level missing columns make
every row fail.

**Why it matters.** `STATUS` and `EXPECTED_SHIP_DATE` together encode
the inspection lifecycle. When an assignment is `"Completed"`,
shipment has concluded; a future ship date on that record is a logical
contradiction that signals premature status closure or a date-entry
error and undermines audit reporting.

**Failure scenarios.**

| Scenario | `STATUS` | `EXPECTED_SHIP_DATE` | Result |
|----------|----------|----------------------|--------|
| Completed with past date | `Completed` | `2024-03-15` | PASS |
| Completed with future date | `Completed` | `2027-12-01` | **FAIL** |
| In-progress with future date | `Approved` | `2027-12-01` | PASS |
| Completed with NULL date | `Completed` | `NULL` | PASS |
| Non-completed status | `Pending Review` | `2024-01-01` | PASS |

**Inputs:**

| Alias | Physical column |
|-------|-----------------|
| Status | `STATUS` |
| Expected Ship Date | `EXPECTED_SHIP_DATE` |

**Implementation notes.** The trigger value is exposed as
`SQS_SQ10_COMPLETED_STATUS = "Completed"` on
[src/custom_dqr_engine.py](../src/custom_dqr_engine.py); the match is
exact and case-sensitive, so `"completed"` / `"COMPLETED"` are out of
scope (SQ9 separately catches the case-mismatch on `STATUS`). The
reference-time semantics mean a Completed row whose ship date was
future at ingestion can flip from FAIL to PASS purely with the passage
of time - this is a deliberate echo of the Snowflake spec, and the
intended audit signal is *current* sequencing integrity.

---

## CDE-coverage validation in Step 4.2

When the user ticks a Custom DQR card,
[ui/step_04_2_custom_dqr.py](../ui/step_04_2_custom_dqr.py) compares the
rule's `effective_required_columns(...)` (physical column names, including
extras contributed by enabled options) against the CDEs already picked
in Step 3 (`DataProductConfig.cdes`):

- **All required columns are CDEs** → green ✅ badge.
- **One or more required columns are missing** → yellow ⚠ warning. The
  selection is **not auto-removed** (so the user keeps the pick and can
  fix the gap), but Step 4.2 disables **Next** and renders a top-level
  `st.error` summarizing every blocking gap across all data products.

The validation is metadata-driven: any rule with a non-empty
`required_columns` map (or any enabled option with
`required_columns_when_enabled`) is validated automatically. A rule with
no required columns is trivially valid and never blocks. Validation
re-runs on every Streamlit rerun, so adding or removing CDEs in Step 3, or unticking the affected Custom DQR - flips the status without leaving
the step.

> **Tip.** Step 3 surfaces a 🎯 cue on rows whose physical column is
> required by at least one Custom DQR (rule IDs are listed inline, e.g.
> `🎯 E1, E3`). The same chip is rendered on the corresponding selected-CDE
> badge above the grid, so the user can see which picks are powering
> which rules. Each Step 3 DP card also exposes a
> **🎯 Select all CDEs required by Custom DQRs** shortcut that unions
> every flagged column into the current selection on click (manual picks
> are preserved). The button is not pre-applied - `cfg.cdes` only changes
> after the user clicks it, and is hidden for systems whose catalog
> declares no required columns.

### Bulk-selecting every Custom DQR for a data product

Each Step 4.2 DP card carries a **✓ Select all Custom DQRs** shortcut next
to the rule cards. Clicking it pre-populates every rule checkbox's
`session_state` entry to True before the cards render, so the user's
Apply ticks land on the same render and the dp-block writer persists a
`CustomDQRAssignment` for each rule. The shortcut is **not pre-applied**: the user must click it explicitly, and any previously-stored weight
or option params (e.g. E3's `project_scoped` toggle) are preserved across
the bulk-select because the writer re-reads `cfg.custom_assignments`
when deciding what to carry forward. The shortcut is hidden for data
products whose catalog entry is empty.

---

## Per-rule options (`CustomRuleOption`)

`CustomRuleOption(key, label, default, help, description, required_columns_when_enabled)`
exposes a per-rule toggle below the rule's description in Step 4.2:

- **Storage.** The toggle's value lives at `CustomDQRAssignment.params[key]`
  and survives Step 4.2 re-renders, Step 5 weight edits, and the Step 6
  evaluation pipeline.
- **Dispatch.** `evaluate_custom_rules` inspects each rule's `check`
  callable; when it declares a `params` argument (today:
  `check_ept_e3`, `check_ept_e6`, `check_adr_a3`, `check_adr_a7`,
  `check_adr_a8`), the dispatcher passes `assignment.params` through.
  Checks that don't declare `params` are called with the legacy
  single-argument signature so existing rules keep working unchanged.
- **CDE-coverage validation.** `effective_required_columns(rule, params)`
  folds `required_columns_when_enabled` from each *enabled* option into
  the rule's static `required_columns`. Step 4.2 uses this composed map
  so flipping E3's project-scope toggle on immediately demands
  `PLANVIEW_ID` as a CDE.

---

## How rules combine into the Custom subscore

Inside the Custom source, each `CustomDQRAssignment` carries a weight in
`[0, 100]`. After Step 5 these weights sum to 100 (or are normalized to
equal weights if all are zero). The custom row score is:

```
custom_row_score = Σ(rule_pass[i] × w_i) × 100
```

Rules whose `check` raised `CustomRuleNotEvaluated` are omitted from the
Boolean matrix (recorded in `not_evaluated_custom_rules`); the surviving
rules' weights are renormalized to sum to 1.0 so a *Not evaluated* rule
doesn't artificially deflate the subscore. A rule that fails for every
row (e.g. a structural-incompleteness all-False Series) **is** counted, that's the point.

The Custom subscore is then combined with the Standard subscore via the
Step-4 source-level weights:

```
final = (w_std/100) × standard_score + (w_cus/100) × custom_score
```

See [DOCUMENTATION.md §4.6](DOCUMENTATION.md#46-weights--scoring) for the
full scoring math and edge cases.

---

## Adding a new Custom DQR rule

1. Implement (or reuse) a `check(df) -> pd.Series[bool]` (or
   `check(df, params) -> pd.Series[bool]` if you need user-toggleable
   options) in [src/custom_dqr_engine.py](../src/custom_dqr_engine.py).

   Reusable helpers:
   - `validate_completeness_rule(df, required_columns)`, same semantics
     as Standard Completeness with `allow_empty_string=False`. Returns
     all-False if any required column is missing.
   - `validate_referential_integrity_rule(source_df, source_column,
     reference_df, reference_column)` - non-blank source value present in
     the reference column. Raise `CustomRuleNotEvaluated` *before*
     calling this helper if your reference dataset is missing.
   - For statistical-outlier rules, replicate the E3 / E6 pattern:
     compute group-level metrics and propagate the per-group verdict
     back to every row of the failing group.

2. Append a `CustomRuleDef(...)` to the relevant data-product list in
   [config/custom_dqr_catalog.py](../config/custom_dqr_catalog.py).
   - Set `required_columns` (alias → physical column).
   - Set `blocking` if the rule represents a blocking gap (used by Step
     4.2 to colour the rule card).
   - For Referential Integrity rules, also set `reference` -
     `{"reference_dataset": "...", "source_column": "...",
     "reference_column": "...", "lookup_column": "..."}`, and register
     a loader in [src/reference_data.py](../src/reference_data.py). The
     rule's `check` must raise `CustomRuleNotEvaluated` when the loader
     returns `None` so the dependency gap is surfaced.
   - For toggleable behavior, declare `options=[CustomRuleOption(...)]`.
     The `check` callable must accept a `params=` keyword for the
     dispatcher to forward the values.

3. Add the new rule's required columns to `src/mock_data.py` if they
   aren't already part of the synthetic generator - otherwise the demo
   mode will hit "structurally incomplete" failures.

4. Cover it in tests (`tests/test_custom_dqr_engine.py` for the check
   function, `tests/test_step_04_2_custom_ui.py` for the rule card and
   per-rule options if any).

The new rule appears automatically in **Step 4.2** for that data product,
**Step 5** picks it up for rule-level weight distribution (single-rule
selections auto-pin to 100%), and **Step 6** reports its pass rate (or
*Not evaluated* status) in the Custom Rules tab.

---

See also: [STANDARD_RULES.md](STANDARD_RULES.md), [DOCUMENTATION.md](DOCUMENTATION.md),
[BLOCK_DIAGRAM.md](BLOCK_DIAGRAM.md), [FLOWCHART.md](FLOWCHART.md).
