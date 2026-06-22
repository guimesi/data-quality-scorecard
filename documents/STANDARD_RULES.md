# Standard DQR Rules - Reference

The Standard source of the Data Quality Scorecard App ships **10 dimensions**
that every Data Product can opt into. They live in
[config/dqr_catalog.py](../config/dqr_catalog.py) (catalog metadata) and
[src/dqr_engine.py](../src/dqr_engine.py) (rule implementations).

> **Note:** Standard DQRs are a **Step-by-step-mode** feature. ⚡ One-click mode is
> intentionally **custom-only** and does not apply any of these dimensions -
> to score with Standard rules, choose 🛠️ Step-by-step at the entry step.

Each dimension has the same shape:

- A **check function** `(df, col, params) -> pd.Series[bool]` (True = row
  passes).
- A **catalog entry** (`DimensionDef`) declaring its description, the column
  type groups it is applicable to, and its default parameters.
- A **compatibility validator** in [src/dqr_validation.py](../src/dqr_validation.py)
  that is consumed both by Step 4.1 (UI gating) and by `evaluate_all_safe`
  (defensive scoring).

Selected per CDE in **Step 4.1 - Standard DQR Assignment**, weighted in
**Step 5 - Weight Assignment**, and combined with Custom DQRs in **Step 6 -
Dashboard** via the source-level weights set in Step 4.

---

## Column-type groups

Catalog and validator share a small fixed alphabet of column-type groups
(defined in [config/dqr_catalog.py](../config/dqr_catalog.py)):

| Group              | Examples                                  |
|--------------------|-------------------------------------------|
| `numeric` / `integer` / `float` | `TOTAL_COST_USD`, `ROW_ID`     |
| `date` / `datetime`             | `CENTROID_DATE`, `LAST_UPDATED`|
| `string` / `categorical`        | `WBC_LEVEL_1`, `STATUS_CODE`   |
| `id`                            | `PLANVIEW_ID`, columns ending in `_ID` |
| `boolean`                       | `IS_ACTIVE`                    |

The validator groups them into three families for cross-column comparisons:
**numeric** (`numeric/integer/float`), **temporal** (`date/datetime`),
**textual** (`string/categorical/id`), plus `boolean` standing alone.

---

## Quick reference

| # | Dimension | What it checks | Required parameters | Compatible CDE groups |
|---|-----------|----------------|---------------------|------------------------|
| 1 | Completeness | Non-null (and optionally non-blank) value | `allow_empty_string` *(bool, default False)* | numeric, temporal, textual, boolean |
| 2 | Uniqueness | Each value appears exactly once | - | numeric, temporal, textual |
| 3 | Validity | Format / regex / length / type | `regex`, `min_length`, `max_length` | numeric, temporal, textual |
| 4 | Accuracy | Value within `[min_value, max_value]` | `min_value`, `max_value` | numeric |
| 5 | Consistency | Cross-field comparison | `compare_column`, `operator` | numeric, temporal, textual, boolean |
| 6 | Timeliness | `today − value ≤ max_lag_days` | `max_lag_days` *(default 30)* | temporal |
| 7 | Currency | `today − value ≤ max_age_days` | `max_age_days` *(default 365)* | temporal |
| 8 | Conformity | `value ∈ allowed_values` | `allowed_values` | textual, numeric, boolean |
| 9 | Integrity | `value ∈ reference_values` | `reference_values` | textual, numeric |
| 10 | Precision | Decimal places ≤ `max_decimals` | `max_decimals` *(default 2)* | numeric |

A row that does not pass, or whose `params` are incompatible with the CDE
type - is flagged in the per-rule pass-rate table on the dashboard. Rules
that fail Step 4.1 validation are recorded in
`ScorecardResult.not_computed_standard_rules` and contribute **0** to the
standard subscore (they do **not** crash the dashboard).

---

## 1. Completeness

**Implementation:** `_rule_completeness` in [src/dqr_engine.py](../src/dqr_engine.py).

A row passes when the CDE column is **non-null**. When `allow_empty_string`
is `False` (the default), string columns also fail on blank / whitespace-only
values - `"   "` is treated as missing.

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `allow_empty_string` | `bool` | `False` | When `True`, an empty string passes as long as the value is not `NaN`. |

**Compatible CDE groups:** numeric, temporal, textual, boolean.

**Notes:**

- Most universally applicable rule - `suggest_dimensions_for(...)` always
  appends it, so every CDE can carry at least a Completeness check.
- For Custom DQRs that require multiple columns to be filled (e.g. EPT-E1),
  the Custom engine reuses the same semantics via
  [`validate_completeness_rule`](../src/custom_dqr/_validators.py) (also
  re-exported from `src.custom_dqr_engine`).

---

## 2. Uniqueness

**Implementation:** `_rule_uniqueness`.

A row passes when the value of the CDE column appears **exactly once** in
that column (`~df[col].duplicated(keep=False)`). A single NaN counts as
unique (nullness is Completeness' concern); two or more NaNs each fail.

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| *(none)* | - | - | - |

**Compatible CDE groups:** numeric, temporal, textual.

**Notes:**

- Duplicates **and** the rows that produce them all fail (every occurrence
  reports the same row-level `False`).
- `suggest_dimensions_for` adds Uniqueness automatically when the column
  name ends in `_id`, equals `id`, or contains `planview`, i.e. anything
  that looks like a primary / foreign key.

---

## 3. Validity

**Implementation:** `_rule_validity`.

Polymorphic by column type:

- **Datetime**: passes when the value parses as a non-null datetime (the
  type itself is the validity check; `regex` / length params are
  ignored - Step 4.1 surfaces a *warning*).
- **Numeric**: passes when the value is non-null and finite (no `Inf`).
  `regex` / length params are ignored - Step 4.1 surfaces a *warning*.
- **Textual**: when `regex` is provided, full-matched against the regex.
  `min_length` / `max_length` apply when set. Nulls always fail under
  Validity.

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `regex` | `str?` | `None` | Full-match regex (textual columns only). |
| `min_length` | `int?` | `None` | Inclusive minimum string length. |
| `max_length` | `int?` | `None` | Inclusive maximum string length. |

**Compatible CDE groups:** numeric, temporal, textual.

**Validator rules ([dqr_validation._validate_validity](../src/dqr_validation.py)):**

- `min_length > max_length` → blocking error.
- Text-style params (`regex` / lengths) on a numeric or temporal CDE →
  warning ("falls back to a finite-number / parsable-date check").

---

## 4. Accuracy

**Implementation:** `_rule_accuracy`.

A row passes when the numeric CDE value satisfies
`min_value ≤ value ≤ max_value` (only the bounds the user set are checked;
`None` means the bound is unconstrained). Nulls always fail.

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `min_value` | `float?` | `None` | Inclusive lower bound. |
| `max_value` | `float?` | `None` | Inclusive upper bound. |

**Compatible CDE groups:** numeric.

**Validator rules:**

- Non-numeric CDE → blocking error ("`Accuracy` is not applicable to a
  text/date column").
- `min_value > max_value` → blocking error.
- Non-numeric literals in `min_value` / `max_value` → blocking error.

**Suggestion behavior:** `suggest_assignments_for_cde` pre-fills `min_value`
and `max_value` from the CDE's profile (`min_value` / `max_value`) when both
are present and convertible to floats - saving the user a manual transcription
of the observed range.

---

## 5. Consistency

**Implementation:** `_rule_consistency`.

Cross-column comparison between the CDE (`col`) and a second column
(`compare_column`). The row passes when:

- both values are present **and** the operator yields `True`, OR
- at least one of the values is null (no-data ↦ no-violation).

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `compare_column` | `str` | `None` | Other column in the Data Product to compare against. |
| `operator` | `str` | `"<="` | One of `<=`, `<`, `>=`, `>`, `==`, `!=`. |

**Compatible CDE groups:** numeric, temporal, textual, boolean.

**Validator rules:**

- `compare_column` must be set, must differ from the CDE column, and must
  exist in the Data Product profile.
- The CDE and `compare_column` must share a category family - numeric ↔
  numeric, temporal ↔ temporal, textual ↔ textual, boolean ↔ boolean.
  Otherwise → blocking error (e.g. comparing a `date` CDE against a
  numeric column).
- Ordering operators (`<`, `<=`, `>`, `>=`) on a boolean CDE → warning.

---

## 6. Timeliness

**Implementation:** `_rule_timeliness`.

A row passes when `today − value ≤ max_lag_days` and `value` is non-null.
The CDE column is coerced to UTC datetime via `pd.to_datetime(..., utc=True)`
and stripped of TZ.

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `max_lag_days` | `int` | `30` | Inclusive freshness window in days. |

**Compatible CDE groups:** date, datetime.

**Validator rules:**

- Non-temporal CDE → blocking error.
- `max_lag_days` non-numeric or `≤ 0` → blocking error.

---

## 7. Currency

**Implementation:** `_rule_currency`.

Same shape as Timeliness, semantically wider, typically used as a
"is the data still recent enough?" check with a multi-month window.

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `max_age_days` | `int` | `365` | Inclusive freshness window in days. |

**Compatible CDE groups:** date, datetime.

**Validator rules:**

- Non-temporal CDE → blocking error.
- `max_age_days` non-numeric or `≤ 0` → blocking error.

---

## 8. Conformity

**Implementation:** `_rule_conformity`.

A row passes when the CDE value is in the user-supplied `allowed_values`
list. When the list is empty, the rule passes every row (it is essentially
a no-op until the user fills the domain). Nulls fail.

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `allowed_values` | `list` | `[]` | Permitted values. |

**Compatible CDE groups:** textual, numeric, boolean.

**Validator rules:**

- Non-numeric literals in `allowed_values` on a numeric CDE → warning ("they
  will never match"). The user can still ship the rule, but is told the
  domain is incompatible.

---

## 9. Integrity

**Implementation:** `_rule_integrity`.

Lightweight referential-integrity check: a row passes when the CDE value
appears in the user-supplied `reference_values` list. When the list is
empty, the rule degrades to a non-null check (better than always-passing).

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `reference_values` | `list` | `[]` | Acceptable foreign keys. |

**Compatible CDE groups:** textual, numeric.

**Validator rules:** same warning as Conformity for non-numeric literals on
a numeric CDE.

**When to use the Custom Referential Integrity instead.** Standard-Integrity
is a *literal* whitelist - appropriate when the reference set is small and
stable (e.g. an enum). For genuine FK lookups against a reference table
(e.g. `PLANVIEW_ID` ∈ `VWS_GP_STANDARD_SHARE.PROJECT_ID`), use the **Custom**
Referential Integrity rule (see [CUSTOM_RULES.md → E7](CUSTOM_RULES.md#e7))
which loads the reference table dynamically and raises
`CustomRuleNotEvaluated` when the dependency is missing.

---

## 10. Precision

**Implementation:** `_rule_precision`.

A row passes when the CDE value's number of decimal places is ≤
`max_decimals`. Implemented vectorized via numpy: the value is scaled by
`10**max_decimals` and passes when the scaled result is within a small
tolerance (`1e-9`) of an integer (`(scaled - scaled.round()).abs() <
1e-9`). The tolerance absorbs float-representation noise (e.g.
`0.1 * 100 == 10.000…001`) while still catching genuinely over-precise
values; `NaN` fails. Non-numeric columns no-op (always pass) so a
misconfigured rule never zero-bombs the score.

| Parameter | Type | Default | Effect |
|-----------|------|---------|--------|
| `max_decimals` | `int` | `2` | Inclusive maximum decimal places. |

**Compatible CDE groups:** numeric, float.

**Validator rules:**

- Non-numeric CDE → blocking error (the rule body would silently no-op).
- `max_decimals` non-integer or negative → blocking error.

---

## Suggestion heuristic

[`suggest_dimensions_for(column_type, col_name)`](../config/dqr_catalog.py)
maps a profile to an initial set of dimensions (used by Step 4.1's
"suggest" path):

- Every dimension whose `applies_to` includes the CDE's column-type group
  is added.
- Columns that look like an identifier (group is `id`, name ends in `_id`,
  name equals `id`, or contains `planview`) additionally pick up
  `Uniqueness` and `Integrity` even if their dtype isn't classified as
  `id`.
- `Completeness` is always added - minimum sanity check on every CDE.

`suggest_assignments_for_cde(profile)` then turns the suggested list into
ready-to-edit `DQRAssignment` objects, pre-filling `Accuracy.min_value` /
`Accuracy.max_value` from the profile when both are present.

> **The suggester drives the badge, not the selection.** Step 4.1 does **not** auto-apply these assignments, the user lands on the step with an empty selection and a **💡 _suggested_** badge on every dimension that `suggest_assignments_for_cde` would propose for the CDE's profile. The user either ticks dimensions individually or uses the per-DP **💡 Apply all suggested DQRs** shortcut, which appends every still-pending suggestion to `cfg.assignments` and pre-sets the Apply-checkbox session-state keys so the cards instantiate ticked on the same render. The profile-aware params carry through, so Accuracy lands with `min_value` / `max_value` already populated. Re-clicking the button is a no-op for already-applied suggestions; once every suggestion is applied the button is replaced by an "already applied" caption.

---

## How rules combine into the Standard subscore

Inside the Standard source, each `DQRAssignment` carries a weight in
`[0, 100]`. After Step 5 these weights sum to 100 (or are normalized to
equal weights if all are zero). The standard row score is:

```
standard_row_score = Σ(rule_pass[i] × w_i) × 100
```

Per-rule pass rates (`mean(pass column)`), per-CDE scores, and per-dimension
scores are derived from the same Boolean matrix and surfaced in Step 6's
breakdown tables.

The Standard subscore is then combined with the Custom subscore via the
Step-4 source-level weights:

```
final = (w_std/100) × standard_score + (w_cus/100) × custom_score
```

See [DOCUMENTATION.md §4.6](DOCUMENTATION.md#46-weights--scoring) for the
full scoring math and edge cases (empty Custom selection, missing required
columns, configs missing `dqr_sources`).

---

## Compatibility validation

Step 4.1 disables **Next** while any selected `(CDE, dimension, params)`
configuration is incompatible - for example:

- Accuracy assigned to a text CDE (blocking error).
- Consistency comparing a date CDE against a numeric column (blocking
  error).
- Validity regex on a numeric CDE (warning, non-blocking).
- `min_value > max_value` in Accuracy (blocking error).

The same validator runs again inside `evaluate_all_safe` so even a Step 4.1
escape hatch (or a future code path that bypasses the UI) cannot crash
Step 6: incompatible rules are recorded in
`ScorecardResult.not_computed_standard_rules` (`rule_id → reason`) and the
dashboard renders a yellow "Not computed" warning per skipped rule. See
[DOCUMENTATION.md §4.4c](DOCUMENTATION.md#44c-standard-dqr-compatibility-validation)
for the full validator matrix.

---

## Adding a new dimension

1. Append a `DimensionDef(...)` entry in
   [config/dqr_catalog.py](../config/dqr_catalog.py) - name, description,
   `applies_to`, default params.
2. Implement `_rule_<name>(df, col, params) -> pd.Series[bool]` in
   [src/dqr_engine.py](../src/dqr_engine.py) and register it in `_DISPATCH`.
3. Register the dimension in `DIMENSION_SUPPORTED_GROUPS` in
   [src/dqr_validation.py](../src/dqr_validation.py); add a per-dimension
   parameter validator if any cross-parameter checks are needed.
4. Surface the parameter editor in
   [ui/step_04_dqr_assignment.py](../ui/step_04_dqr_assignment.py) so the
   user can tune the new params from Step 4.1.
5. Add tests in `tests/test_dqr_engine_extra.py` (rule edge cases) and
   `tests/test_dqr_validation.py` (validation matrix). The
   `test_every_dimension_has_a_compatibility_entry` guard catches step 3
   omissions automatically.

---

See also: [CUSTOM_RULES.md](CUSTOM_RULES.md), [DOCUMENTATION.md](DOCUMENTATION.md),
[BLOCK_DIAGRAM.md](BLOCK_DIAGRAM.md), [FLOWCHART.md](FLOWCHART.md).
