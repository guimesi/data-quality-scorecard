# ACCE in Airtable: CDEs and Data Quality Rules

Ready-to-type records for the ACCE data product in the Airtable governance
base: the Critical Data Elements (table **Data Quality Fields**) and the
custom rules (table **Data Quality Rules**). Compiled on 2026-11-06 from the
rule catalog (`config/custom_dqr/_acce_catalog.py`), the data product
definition (`config/systems.py`) and the production review of 2026-10-28/30
(see `documents/CUSTOM_RULES.md`, "Quick reference (ACCE)").

Constants for every CDE: **Data Product** = `ACCE`, **Data Domain** = `Cost`,
**Data Quality Field Code** = `CDE-ACCE-<Field Name>`.

## How the app links results to these records

The results push (`src/airtable_results.py`) swaps the app-side values for
Airtable record links:

- **CDE link.** The app looks for the column name *it* uses in the data
  product inside the Airtable field **Column Name**. Columns of the primary
  table keep their physical name (`PLANVIEW_ID`, `COA`, `DESCRIPTION`);
  columns of the child tables get a prefix (`QTY_`, `COST_`), and the design
  table is collapsed into one derived column, `DESIGN_KEY_PARAMETER_NAMES`.
  Those prefixed / derived names do **not** exist in Databricks. The Column
  Name cell accepts several names separated by commas, so list the physical
  column first (for people) and the app column after it (for the link). A
  record that fills Column Name is matched on that field alone; the Field
  Name alias fallback only applies to records whose Column Name is empty,
  and `_CDE_ALIASES` has no ACCE entries.
- **Rule link.** The app looks for the rule id (`DQ-ACCE-1`, …) in any text
  field of the rule record, so **Data Quality Code** is enough.
- Nothing is created automatically in the governance tables; the records
  below are typed by hand.

## CDEs (table "Data Quality Fields")

| Data Quality Field Code | Field Name | Table Name or File Name | Column Name | Data Type | Data Sample | GP Data Quality Rules |
|---|---|---|---|---|---|---|
| CDE-ACCE-Planview ID | Planview ID | ACCE_ESTIMATEITEMRECORD | PLANVIEW_ID | *to confirm* | 1106771 | DQ-ACCE-1, DQ-ACCE-4 |
| CDE-ACCE-Code of Account (COA) | Code of Account (COA) | ACCE_ESTIMATEITEMRECORD | COA | *to confirm* | *to confirm* | DQ-ACCE-1, DQ-ACCE-5 |
| CDE-ACCE-Item Description | Item Description | ACCE_ESTIMATEITEMRECORD | DESCRIPTION | Text | CS PIPE ERECTION | DQ-ACCE-4, DQ-ACCE-5 |
| CDE-ACCE-Key Quantity | Key Quantity | ACCE_ESTIMATEQTYRESULTS | KEY_QTY, QTY_KEY_QTY | *to confirm* | *to confirm* | DQ-ACCE-4, DQ-ACCE-5, DQ-ACCE-6 |
| CDE-ACCE-Other Quantity | Other Quantity | ACCE_ESTIMATEQTYRESULTS | OTHER_QTY, QTY_OTHER_QTY | *to confirm* | *to confirm* | DQ-ACCE-4, DQ-ACCE-5, DQ-ACCE-6 |
| CDE-ACCE-Key Quantity Unit of Measure (UOM) | Key Quantity Unit of Measure (UOM) | ACCE_ESTIMATEQTYRESULTS | KEY_UNITS, QTY_KEY_UNITS | Text | M | DQ-ACCE-4 |
| CDE-ACCE-Other Quantity Unit of Measure (UOM) | Other Quantity Unit of Measure (UOM) | ACCE_ESTIMATEQTYRESULTS | OTHER_UNITS, QTY_OTHER_UNITS | Text | EACH | DQ-ACCE-4 |
| CDE-ACCE-Construction Hours (MH) | Construction Hours (MH) | ACCE_ESTIMATECOSTRESULTS | MH, COST_MH | *to confirm* | *to confirm* | DQ-ACCE-6 |
| CDE-ACCE-Labor Cost | Labor Cost | ACCE_ESTIMATECOSTRESULTS | LABOR_COST, COST_LABOR_COST | *to confirm* | *to confirm* | DQ-ACCE-6 |
| CDE-ACCE-Design Property | Design Property | ACCE_ESTIMATEDESIGNDETAILS | PROPERTY, VALUE, DESIGN_KEY_PARAMETER_NAMES | Text | Item type | DQ-ACCE-5 |

### Why "Design Property" is one CDE built from two columns

`ACCE_ESTIMATEDESIGNDETAILS` is Aspen's equipment design report in a tall
(key / value) layout: one row per design parameter, `PROPERTY` naming the
parameter and `VALUE` holding its content (about 21 rows per `DESIGN_ID` in
production). Neither column is a business data element on its own; the
parameter only exists as the pair. The data product builder collapses the
pair, per item, into `DESIGN_KEY_PARAMETER_NAMES`: the pipe-separated list
of property names whose value is populated (`Item type|Source of quote|Total
weight`). DQ-ACCE-5 reads only that derived column. ADR follows the same
pattern with its single "Design Parameter" CDE over
`DESIGN_PARAMETER_NAME` / `DESIGN_PARAMETER_VALUE`.

If two records are preferred (one per physical column), only one of them
may list `DESIGN_KEY_PARAMETER_NAMES` in Column Name; two matches leave the
link empty.

### Filling the missing types and samples

One query per table, each returning one row (Databricks SQL editor,
`entai_sandbox_catalog.data_quality_scorecards`):

```sql
SELECT PLANVIEW_ID, typeof(PLANVIEW_ID) AS t_pv, COA, typeof(COA) AS t_coa
FROM entai_sandbox_catalog.data_quality_scorecards.ACCE_ESTIMATEITEMRECORD LIMIT 1;

SELECT KEY_QTY, typeof(KEY_QTY) AS t_key, OTHER_QTY, typeof(OTHER_QTY) AS t_other
FROM entai_sandbox_catalog.data_quality_scorecards.ACCE_ESTIMATEQTYRESULTS
WHERE KEY_QTY > 0 AND OTHER_QTY > 0 LIMIT 1;

SELECT MH, typeof(MH) AS t_mh, LABOR_COST, typeof(LABOR_COST) AS t_labor
FROM entai_sandbox_catalog.data_quality_scorecards.ACCE_ESTIMATECOSTRESULTS
WHERE MH > 0 AND LABOR_COST > 0 LIMIT 1;

SELECT PROPERTY, VALUE, typeof(VALUE) AS t_value
FROM entai_sandbox_catalog.data_quality_scorecards.ACCE_ESTIMATEDESIGNDETAILS
WHERE VALUE IS NOT NULL LIMIT 1;
```

Inactive DQ-ACCE-3 is not listed above. If it is ever reactivated it adds
one CDE, Total Cost (`ACCE_ESTIMATECOSTRESULTS.TOTAL_COST`, app column
`COST_TOTAL_COST`), and joins Planview ID, Code of Account (COA) and
Construction Hours (MH).

## Rules (table "Data Quality Rules")

Only the four active rules. DQ-ACCE-3 (Statistical COA-to-ISO mapping
ratio) is inactive, like DQ-ADR-3; DQ-ACCE-2, 7 and 8 are retired.

### DQ-ACCE-1

- **Data Quality Code:** DQ-ACCE-1
- **Rule Number:** 1
- **Rule Name:** ISO Code of Account present (COR + SAB)
- **Dimension:** Completeness
- **CDE(s):** Planview ID, Code of Account (COA)
- **Description:** Every ACCE estimate line must carry a Code of Account
  (COA) whose 3-character ICARUS group resolves to a valid ISO Code of
  Resource (ISO_COR) and a valid Standard Activity Breakdown (SAB) in
  ACCE_COA_MASTER. Without both codes the line cannot be normalized through
  the EMMA factor for cross-project cost benchmarking.
- **Technical Validation:** Take the first three characters of COA and look
  them up in ACCE_COA_MASTER on ICARUS_COA. The line passes when COA is not
  null or blank, the lookup returns an ISO_COR that is not null, blank or
  marked ERROR / N/A, and the same lookup returns a SAB that is not null,
  blank or marked ERROR / N/A. Any other case fails. When the master has
  several rows for the same group, the best valid pair is used.
- **Exception Scenario:** None at row level. If ACCE_COA_MASTER is
  unavailable the rule is reported as "Not evaluated" instead of failing
  every row.

### DQ-ACCE-4

- **Data Quality Code:** DQ-ACCE-4
- **Rule Number:** 4
- **Rule Name:** Core quantities populated & non-negative project totals
- **Dimension:** Completeness & Validity
- **CDE(s):** Planview ID, Item Description, Key Quantity, Other Quantity,
  Key Quantity Unit of Measure (UOM), Other Quantity Unit of Measure (UOM)
- **Description:** For each project (PLANVIEW_ID), every core quantity type
  implied by the project scope must be populated, and the project total
  quantity must not be negative. The seven core types are piping length,
  concrete quantity, steel quantity, cable length, instrument count,
  equipment count and module count. A type is expected when at least one
  line carries a DESCRIPTION of that type; it is populated when such a line
  has a positive quantity in a unit of the matching family. All lines of a
  failing project fail.
- **Technical Validation:** Evaluated per project (PLANVIEW_ID), with the
  verdict inherited by every line of the project. For each of the seven
  core quantity types (piping length, concrete, steel, cable length,
  instrument count, equipment count, module count): the type is expected
  when at least one line of the project has a DESCRIPTION in that type's
  list; it is populated when at least one of those lines has KEY_QTY or
  OTHER_QTY greater than zero and KEY_UNITS or OTHER_UNITS in the type's
  unit family (length units for piping and cable; count units for
  instruments, equipment and modules; weight, length or area units for
  steel; volume, weight or area units for concrete). The project fails when
  any expected type is not populated, or when the sum of KEY_QTY plus the
  sum of OTHER_QTY across the project is negative. Otherwise it passes.
- **Exception Scenario:** Lines without PLANVIEW_ID pass (no project to
  group by). A project with no expected core type passes. Individual lines
  may carry negative quantities (corrections); only a negative project
  total fails.

### DQ-ACCE-5

- **Data Quality Code:** DQ-ACCE-5
- **Rule Number:** 5
- **Rule Name:** Key design details present when quantity exists
- **Dimension:** Consistency
- **CDE(s):** Item Description, Code of Account (COA), Key Quantity, Other
  Quantity, Design Property
- **Description:** An equipment line (DESCRIPTION in the DQ-ACCE-4 equipment
  list) with a positive quantity must have at least one design property
  populated in ACCE_ESTIMATEDESIGNDETAILS for its DESIGN_ID. When the COA
  has an entry in the COA-to-key-property mapping, one of those key
  properties must be populated; otherwise any named, populated property is
  accepted. The pass rate is computed over the lines in scope.
- **Technical Validation:** Evaluated per estimate line (ROW_ID). The line
  is in scope when its DESCRIPTION is in the equipment list and the sum of
  KEY_QTY or the sum of OTHER_QTY is greater than zero. Lines out of scope
  are not applicable and count as pass. For a line in scope, read the rows
  of ACCE_ESTIMATEDESIGNDETAILS with the same DESIGN_ID and keep those whose
  VALUE is not null or blank. If the line's COA has an entry in the
  COA-to-key-property mapping, the line passes when one of those key
  properties is among the populated ones. If the COA is not mapped, the
  line passes when at least one populated property has a non-blank PROPERTY
  name. Otherwise, including lines with no DESIGN_ID or no design rows, it
  fails.
- **Exception Scenario:** Non-equipment lines (plant and area bulks such as
  piping, concrete, steel, cable) and lines without a positive quantity are
  out of scope: they pass and are not counted in the denominator. The
  COA-to-key-property mapping is empty today, so in practice any named
  property with a value is enough. An equipment line with no DESIGN_ID or
  no design rows fails.

### DQ-ACCE-6

- **Data Quality Code:** DQ-ACCE-6
- **Rule Number:** 6
- **Rule Name:** Construction hours present when quantity exists
- **Dimension:** Consistency
- **CDE(s):** Key Quantity, Other Quantity, Construction Hours (MH), Labor
  Cost
- **Description:** An estimate line with a positive quantity and a positive
  labor cost must carry positive construction hours (MH), so productivity
  (hours per unit) and EMMA normalization can be derived. The check is
  one-directional: hours without quantity pass; only quantity without hours
  fails. The pass rate is computed over the lines in scope.
- **Technical Validation:** Evaluated per estimate line (ROW_ID), with
  quantities, hours and labor cost summed from the quantity and cost tables.
  The line is in scope when the sum of KEY_QTY or the sum of OTHER_QTY is
  greater than zero and the sum of LABOR_COST is greater than zero. Lines
  out of scope are not applicable and count as pass. A line in scope passes
  when the sum of MH is greater than zero and fails otherwise. Null hours
  count as zero.
- **Exception Scenario:** Material and subcontract lines (LABOR_COST ≤ 0)
  and lines without a positive quantity are out of scope: they pass and are
  not counted in the denominator. Aspen splits a component into material,
  shop-fab and erection lines, and only the erection line carries hours, so
  this is expected behavior. Null hours count as zero.
