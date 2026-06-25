"""ACCE custom rule list."""
from __future__ import annotations

from config.custom_dqr._shared import (
    CustomRuleDef,
    CustomRuleOption,
    _iqr_threshold_option,
    _percentile_threshold_option,
)
from src.custom_dqr_engine import (
    ACCE_AC1_REFERENCE,
    ACCE_AC1_REQUIRED_COLUMNS,
    ACCE_AC2_REFERENCE,
    ACCE_AC2_REQUIRED_COLUMNS,
    ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM,
    ACCE_AC3_MATERIALITY_USD,
    ACCE_AC3_MIN_MAPPING_POPULATION,
    ACCE_AC3_PERCENTILE,
    ACCE_AC3_REFERENCE,
    ACCE_AC3_REQUIRED_COLUMNS,
    ACCE_AC3_THRESHOLD_CHOICES,
    ACCE_AC3_THRESHOLD_PARAM,
    ACCE_AC3_UNIFORM_THRESHOLD,
    ACCE_AC4_REQUIRED_COLUMNS,
    ACCE_AC5_REQUIRED_COLUMNS,
    ACCE_AC6_REQUIRED_COLUMNS,
    ACCE_AC7_MILD_IQR_MULTIPLIER,
    ACCE_AC7_MIN_POPULATION,
    ACCE_AC7_REQUIRED_COLUMNS,
    ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM,
    ACCE_AC7_SEGMENT_REQUIRED_COLUMNS,
    ACCE_AC7_THRESHOLD_CHOICES,
    ACCE_AC7_THRESHOLD_PARAM,
    ACCE_AC8_MILD_IQR_MULTIPLIER,
    ACCE_AC8_MIN_POPULATION,
    ACCE_AC8_REQUIRED_COLUMNS,
    ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM,
    ACCE_AC8_SEGMENT_REQUIRED_COLUMNS,
    ACCE_AC8_THRESHOLD_CHOICES,
    ACCE_AC8_THRESHOLD_PARAM,
    check_acce_ac1,
    check_acce_ac2,
    check_acce_ac3,
    check_acce_ac4,
    check_acce_ac5,
    check_acce_ac6,
    check_acce_ac7,
    check_acce_ac8,
)

ACCE_RULES = [
    CustomRuleDef(
        id="AC1",
        name="ISO Code of Account present (COR + SAB)",
        type="Completeness",
        description=(
            "Every ACCE estimate item row must carry a ``COA`` "
            "value (numeric Code of Account code) that resolves "
            "to both a valid ISO Code of Resource (``ISO_COR``) "
            "and a valid Standard Activity Breakdown (``SAB``) "
            "in the COA master. Without those codes, ACCE cost "
            "data cannot be normalized via the EMMA factor for "
            "cross-project benchmarking - a blocking gap."
        ),
        notes=(
            "Row-level Completeness with a join to the "
            "``ACCE_COA_MASTER`` reference dataset. Unlike ADR's "
            "A1 (which extracts the COA group from "
            "``COMPLETE_WBC`` via ``SPLIT_PART(..., '.', 1)``), "
            "ACCE stores the COA code directly in the ``COA`` "
            "field - the lookup is a direct ``COA`` → "
            "``ICARUS_COA`` join, no transformation needed. The "
            "master may carry multiple rows per ICARUS_COA - the "
            "rule picks the best-available mapping (preferring "
            "non-null, non-error values). ``ISO_COR`` and ``SAB`` "
            "are considered invalid when null, blank, or "
            "containing the ``ERROR`` / ``N/A`` markers. Rows "
            "fail when ``COA`` is missing, when the value does "
            "not resolve to a valid ``ISO_COR``, or when it does "
            "not resolve to a valid ``SAB``. The rule raises "
            "``CustomRuleNotEvaluated`` when the reference "
            "dataset is unavailable so the gap is never silent."
        ),
        required_columns=dict(ACCE_AC1_REQUIRED_COLUMNS),
        blocking=True,
        check=check_acce_ac1,
        reference=dict(ACCE_AC1_REFERENCE),
    ),
    CustomRuleDef(
        id="AC2",
        name="Location + estimate date present & valid",
        type="Completeness & Validity",
        description=(
            "Each ACCE record carries the estimate job / period "
            "(``JOB_NO``) in the fiscal quarter-year format "
            "(e.g. ``2Q23 RP1``), and a project location "
            "(``COUNTRY``) resolved via the Planview reference "
            "dataset. Mirrors ADR A2 against the ACCE schema, "
            "swapping ``COST_UPDATE`` (ADR's estimate basis date) "
            "for ``JOB_NO`` (ACCE's estimate-job/period proxy)."
        ),
        notes=(
            "``COUNTRY`` is the project site location; "
            "``JOB_NO`` is the estimate job / period "
            "(e.g. 2Q23 RP1, 2Q24, 2Q25, 4Q23) - the ACCE proxy for "
            "the estimate date. ``JOB_NO`` must be both populated "
            "(Completeness) and start with the fiscal quarter-year "
            "token [1-4]Q<YY> with an optional revision suffix "
            "(Validity); the check is structural so newly-ingested "
            "quarters/years pass automatically, while a populated but "
            "malformed value fails. If ``PLANVIEW_ID`` does not match "
            "any ``PROJECT_ID`` in the Planview reference, "
            "``COUNTRY`` is treated as missing. All inputs are "
            "required to select the correct CU period for EMMA "
            "normalization. The rule raises "
            "``CustomRuleNotEvaluated`` when the reference "
            "dataset is unavailable so the gap is never silent."
        ),
        required_columns=dict(ACCE_AC2_REQUIRED_COLUMNS),
        blocking=False,
        check=check_acce_ac2,
        reference=dict(ACCE_AC2_REFERENCE),
    ),
    CustomRuleDef(
        id="AC3",
        name="Statistical COA-to-ISO mapping ratio",
        type="Statistical Outlier",
        description=(
            "Flags ACCE ISO mappings (``ISO_COR + SAB`` resolved "
            "from ``COA`` via the COA master) that aggregate more "
            "distinct ``COA`` values than the global "
            f"{int(ACCE_AC3_PERCENTILE * 100)}th-percentile ratio "
            "observed across the ACCE portfolio - indicating the "
            "ISO bucket may be hiding meaningful source-system "
            "detail."
        ),
        notes=(
            "Mapping-quality statistical rule with a row-level "
            "verdict. Mirrors ADR A3 against the ACCE schema, "
            "swapping ``COUNT(DISTINCT COMPLETE_WBC)`` for "
            "``COUNT(DISTINCT COA)`` because ACCE stores the "
            "Code of Account directly (no ``SPLIT_PART`` "
            "derivation). The metric is computed per "
            "``(ISO_COR, SAB)`` bucket; the threshold is the "
            f"global {int(ACCE_AC3_PERCENTILE * 100)}th-percentile "
            "ratio across all eligible mappings, recomputed from "
            "the data on every run (no fixed benchmark). A bucket "
            "fails only when its ratio is strictly greater than "
            "the percentile AND the bucket is *material* - "
            f"``SUM(COST_MH) > 0`` OR "
            f"``SUM(COST_TOTAL_COST) >= "
            f"{int(ACCE_AC3_MATERIALITY_USD):,} USD`` - to "
            "suppress false positives from planning / "
            "structural-only mappings. Rows whose ``COA`` does not "
            "resolve to a valid ``ISO_COR`` / ``SAB`` are PASS - "
            "AC1 already covers that completeness gap and AC3 "
            "must not double-penalise. Eligible-mapping "
            f"populations below {ACCE_AC3_MIN_MAPPING_POPULATION} "
            "are NOT_APPLICABLE and pass. Unlike A3, AC3 does "
            "**not** expose a project-scope toggle - the "
            "percentile baseline is always portfolio-wide. The "
            "rule raises ``CustomRuleNotEvaluated`` when the COA "
            "master is unavailable so the gap is never silent."
        ),
        required_columns=dict(ACCE_AC3_REQUIRED_COLUMNS),
        blocking=False,
        check=check_acce_ac3,
        reference=dict(ACCE_AC3_REFERENCE),
        select_options=[
            _percentile_threshold_option(
                ACCE_AC3_THRESHOLD_PARAM,
                ACCE_AC3_THRESHOLD_CHOICES,
                ACCE_AC3_PERCENTILE,
            ),
        ],
        options=[
            CustomRuleOption(
                key=ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM,
                label="Detect uniform 1:1 mappings (portfolio-wide)",
                default=False,
                help=(
                    "When on, every material 1:1 bucket fails - but "
                    "only when ≥ "
                    f"{int(ACCE_AC3_UNIFORM_THRESHOLD * 100)}% of "
                    "eligible mappings in the portfolio are 1:1. "
                    "Off by default."
                ),
                description=(
                    "**How this option works**\n\n"
                    "On top of the percentile-based outlier check, the "
                    "rule layers a portfolio-wide uniform-mapping "
                    "detector. Unlike ADR A3 (which fails every "
                    "material 1:1 bucket the moment its toggle is on), "
                    "AC3 only trips the uniform branch when the "
                    "*proportion* of eligible mappings with "
                    "`ratio == 1` reaches "
                    f"{int(ACCE_AC3_UNIFORM_THRESHOLD * 100)}% - i.e. "
                    "the ISO classification is effectively just "
                    "relabeling COA codes 1:1 across the whole "
                    "portfolio, not just a handful of buckets. When "
                    "the gate trips, every material 1:1 bucket inherits "
                    "the FAIL. The wider gate reflects that ACCE COA "
                    "codes are inherently coarser than ADR's WBCs, so "
                    "a few legitimate 1:1 mappings should not by "
                    "themselves trigger the rule. The percentile fail "
                    "and the uniform-1:1 fail combine with OR - "
                    "materiality still gates both branches to keep "
                    "planning / structural-only rows out."
                ),
            ),
        ],
    ),
    CustomRuleDef(
        id="AC4",
        name="Core quantities populated & non-negative project totals",
        type="Completeness & Validity",
        description=(
            "Validates that each ACCE project has its applicable "
            "core quantity types populated, and that the project's "
            "total quantity is not negative. The seven core types "
            "(piping LF, concrete CY, steel tons, cable length, "
            "transmitter / instrument count, equipment count, "
            "module count) are evaluated relative to the project "
            "scope - only types implied by the project's "
            "``DESCRIPTION`` are required."
        ),
        notes=(
            "Project-level rule with row-level verdict. Both scope "
            "and population detection key off ``DESCRIPTION`` - an "
            "explicit allow-list of estimate-line labels per core "
            "type (e.g. ``PIPING`` / ``CS PIPE ERECTION`` for "
            "piping, ``CONCRETE`` / ``FOUNDATION ACCESSORIES`` for "
            "concrete), matched case-insensitively; MODULE_COUNT "
            "keeps a ``MODULE`` / ``MODULAR`` substring match. For "
            "each ``PLANVIEW_ID`` the rule first determines which "
            "core types the project's scope implies, then checks "
            "that each one is populated by at least one row whose "
            "``DESCRIPTION`` is in the type's list, with a positive "
            "quantity (``KEY_QTY`` or ``OTHER_QTY`` > 0) carried in "
            "a matching unit (``KEY_UNITS`` or ``OTHER_UNITS`` in "
            "the type's UOM set). A project fails when any expected "
            "type lacks a populated row, OR when its combined "
            "quantity total (SUM(KEY_QTY) + SUM(OTHER_QTY)) is "
            "negative. Individual rows may carry negative quantities "
            "(corrections / reversals); only a project-wide negative "
            "total fails. Every row of a failing project inherits "
            "the FAIL. Schema-level missing column → all rows fail. "
            "Rows lacking ``PLANVIEW_ID`` pass - they can't be "
            "attached to a project group."
        ),
        required_columns=dict(ACCE_AC4_REQUIRED_COLUMNS),
        blocking=False,
        check=check_acce_ac4,
    ),
    CustomRuleDef(
        id="AC5",
        name="Design details present when quantity exists",
        type="Consistency",
        description=(
            "Each ACCE estimate item with a positive aggregated "
            "quantity (``QTY_KEY_QTY`` or ``QTY_OTHER_QTY`` > 0) "
            "must carry a usable design parameter - BOTH a named "
            "``DESIGN_PROPERTY`` and a populated ``DESIGN_VALUE`` "
            "from the design-details child table. Quantities "
            "without supporting design context cannot be "
            "normalized, compared across items, or validated "
            "downstream."
        ),
        notes=(
            "Row-level Consistency: a row fails only when at least "
            "one quantity slot is strictly positive AND the item "
            "lacks a usable design detail. ACCE's split quantities "
            "are the per-``ROW_ID`` SUMs of ``KEY_QTY`` / "
            "``OTHER_QTY`` from ``ACCE_ESTIMATEQTYRESULTS``; a "
            "null / zero / negative quantity in both slots counts "
            "as 'no quantity' (PASS). ``DESIGN_PROPERTY`` / "
            "``DESIGN_VALUE`` are the ``PROPERTY`` / ``VALUE`` "
            "fields from ``ACCE_ESTIMATEDESIGNDETAILS`` joined via "
            "``DESIGN_ID`` - BOTH must be non-null and non-blank "
            "(a bare value with no named parameter is not a usable "
            "detail). Items without a ``DESIGN_ID`` or with no "
            "matching design row are treated as having no design "
            "detail. Missing required column → all rows fail."
        ),
        required_columns=dict(ACCE_AC5_REQUIRED_COLUMNS),
        blocking=False,
        check=check_acce_ac5,
    ),
    CustomRuleDef(
        id="AC6",
        name="Construction hours present when quantity exists",
        type="Consistency",
        description=(
            "Each ACCE estimate item with a positive aggregated "
            "quantity (``QTY_KEY_QTY`` or ``QTY_OTHER_QTY`` > 0) "
            "must also have strictly positive construction hours "
            "(``COST_MH``) so productivity (hours / unit) and EMMA "
            "normalization can be derived. One-directional: "
            "hours-without-quantity is PASS, only "
            "quantity-without-hours fails."
        ),
        notes=(
            "Row-level Consistency. ACCE's split quantities are the "
            "per-``ROW_ID`` SUMs of ``KEY_QTY`` / ``OTHER_QTY`` from "
            "``ACCE_ESTIMATEQTYRESULTS``; a null / zero / negative "
            "quantity in both slots counts as 'no quantity' (PASS). "
            "The construction-hours column is ``COST_MH`` (sourced "
            "from ``MH`` on ``ACCE_ESTIMATECOSTRESULTS``); ACCE has "
            "no separate Design-Build hours column, so the check "
            "uses only ``COST_MH``. The hours comparison is strictly "
            "``> 0`` - null is coerced to zero and negative "
            "aggregates do not count as hours present. Missing "
            "required column → all rows fail."
        ),
        required_columns=dict(ACCE_AC6_REQUIRED_COLUMNS),
        blocking=False,
        check=check_acce_ac6,
    ),
    CustomRuleDef(
        id="AC7",
        name="Within-discipline quantity / hour ratio outlier",
        type="Statistical Outlier",
        description=(
            "Flags ACCE items whose hours-per-quantity ratio sits "
            "far outside the IQR band of its peer group "
            "(same ``DESCRIPTION`` + same ``QTY_UOM``). The segment "
            "key is the raw ``DESCRIPTION`` value (estimate-line "
            "label) paired with the effective UOM; construction "
            "hours come from ``COST_MH`` (sourced from ``MH``), and "
            "quantity is ``KEY_QTY + OTHER_QTY``."
        ),
        notes=(
            "Per-row Statistical Outlier with a row-level verdict. "
            "Eligible rows (``KEY_QTY > 0`` OR ``OTHER_QTY > 0``; "
            "AND ``COST_MH > 0``; AND a non-blank ``DESCRIPTION`` "
            "and effective UOM) compute "
            "``HOURS_PER_QUANTITY = COST_MH / QTY_QUANTITY`` where "
            "``QTY_QUANTITY = COALESCE(KEY_QTY, 0) + "
            "COALESCE(OTHER_QTY, 0)``; the eligible population is "
            "partitioned by ``(DESCRIPTION, QTY_UOM)`` (raw "
            "``UPPER(TRIM(DESCRIPTION))`` + effective UOM "
            "``COALESCE(KEY_UNITS, OTHER_UNITS)``) and IQR bounds "
            "are derived per segment (``Q1 - k·IQR`` … "
            "``Q3 + k·IQR``, with ``k`` "
            f"selectable on the rule card - **{ACCE_AC7_MILD_IQR_MULTIPLIER}× "
            "mild default**, 2.0×, or 3.0× extreme). Segments "
            f"below {ACCE_AC7_MIN_POPULATION} eligible rows or "
            "with ``IQR == 0`` are NOT_APPLICABLE and pass; rows "
            "that lack a calculable ratio (no positive qty, or "
            "missing / zero / negative hours) or whose segment key "
            "is blank are also NOT_APPLICABLE and pass - AC6 "
            "covers the missing-hours-with-quantity gap. The "
            "segment key starts at ``(DESCRIPTION, QTY_UOM)`` "
            "and is optionally extended with the project-type "
            "tuple via the ``segment_by_project_type`` toggle."
        ),
        required_columns=dict(ACCE_AC7_REQUIRED_COLUMNS),
        blocking=False,
        check=check_acce_ac7,
        select_options=[
            _iqr_threshold_option(
                ACCE_AC7_THRESHOLD_PARAM,
                ACCE_AC7_THRESHOLD_CHOICES,
                ACCE_AC7_MILD_IQR_MULTIPLIER,
            ),
        ],
        options=[
            CustomRuleOption(
                key=ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM,
                label="Segment by project type before computing statistics",
                default=False,
                help=(
                    "When on, the IQR thresholds are recomputed within "
                    "each (DESCRIPTION, QTY_UOM, E05_DEPARTMENT, "
                    "BUSINESS) segment instead of just "
                    "(DESCRIPTION, QTY_UOM) - a deepwater FPSO is no "
                    "longer judged against an onshore refinery within "
                    "the same discipline."
                ),
                description=(
                    "**How this option works**\n\n"
                    "**Off (default - discipline-only scope):** the "
                    "IQR is derived per `(DESCRIPTION, QTY_UOM)` "
                    "segment across every eligible item in the "
                    "dataset. Every row is judged against the "
                    "discipline's dataset-wide PASS band.\n\n"
                    "**On (project-type scope):** each row is tagged "
                    "with a composite project-type key "
                    "`(E05_DEPARTMENT, BUSINESS)` looked up from the "
                    "`VWS_GP_STANDARD_SHARE` reference via "
                    "`PLANVIEW_ID → PROJECT_ID` - the same lookup "
                    "E6 / A7 / A8 use. The segment key becomes "
                    "`(DESCRIPTION, QTY_UOM, E05_DEPARTMENT, "
                    "BUSINESS)` and "
                    "the IQR is recomputed within each bucket, so a "
                    "deepwater FPSO and an onshore refinery are no "
                    "longer pooled into the same baseline at the "
                    "discipline level. Segments with fewer than the "
                    "minimum row population are NOT_APPLICABLE (pass) "
                    "so a thinly-populated bucket does not flag every "
                    "row inside it as an outlier of itself. Rows "
                    "whose project-type cannot be resolved (missing "
                    "PLANVIEW_ID, unmatched PROJECT_ID, or null "
                    "`E05_DEPARTMENT` / `BUSINESS`) are PASS - "
                    "AC1 / AC2 already cover those gaps."
                ),
                required_columns_when_enabled=dict(
                    ACCE_AC7_SEGMENT_REQUIRED_COLUMNS
                ),
            ),
        ],
    ),
    CustomRuleDef(
        id="AC8",
        name="Cross-discipline quantity ratios",
        type="Statistical Outlier",
        description=(
            "Flags ACCE projects whose cross-discipline quantity "
            "proportions (pipe / equipment, cable / transmitter, "
            "steel / concrete) sit far outside the IQR band of "
            "the peer-project population. The project key is "
            "``COMPONENT_SOURCE`` and the classifier keys off "
            "``DESCRIPTION`` (per-discipline value lists, the same "
            "taxonomy AC4 uses) plus a per-category unit gate read "
            "from the split ``KEY_UNITS`` / ``OTHER_UNITS`` slots."
        ),
        notes=(
            "Project-level Statistical Outlier with a row-level "
            "verdict. Classifies eligible positive-quantity rows "
            "into six discipline categories off ``DESCRIPTION`` + "
            "the split unit columns (a row classifies when its "
            "``DESCRIPTION`` is in a category's allow-list and "
            "``KEY_UNITS`` or ``OTHER_UNITS`` is in that "
            "category's UOM family), sums the per-row quantity "
            "(``COALESCE(KEY_QTY, 0) + COALESCE(OTHER_QTY, 0)``) "
            "by ``(COMPONENT_SOURCE, category)``, and computes "
            "three cross-discipline ratios (pipe/equipment, "
            "cable/transmitter, steel/concrete). For each ratio, "
            "projects whose value falls outside the population "
            "IQR bounds (multiplier ``k`` selectable on the rule "
            f"card - **{ACCE_AC8_MILD_IQR_MULTIPLIER}× mild "
            "default**, 2.0×, or 3.0× extreme) are flagged; "
            "every row of a flagged project inherits the FAIL. "
            f"Ratios with population below {ACCE_AC8_MIN_POPULATION} "
            "projects or ``IQR == 0``, rows without a project / "
            "classifiable category, and rows whose "
            "``COMPONENT_SOURCE`` is blank are NOT_APPLICABLE and "
            "pass. The ``segment_by_project_type`` toggle, when "
            "on, partitions the per-ratio IQR baseline by the "
            "composite ``(E05_DEPARTMENT, BUSINESS)`` tuple "
            "resolved from ``VWS_GP_STANDARD_SHARE`` via "
            "``PLANVIEW_ID → PROJECT_ID`` - mirrors A8's toggle."
        ),
        required_columns=dict(ACCE_AC8_REQUIRED_COLUMNS),
        blocking=False,
        check=check_acce_ac8,
        select_options=[
            _iqr_threshold_option(
                ACCE_AC8_THRESHOLD_PARAM,
                ACCE_AC8_THRESHOLD_CHOICES,
                ACCE_AC8_MILD_IQR_MULTIPLIER,
            ),
        ],
        options=[
            CustomRuleOption(
                key=ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM,
                label="Segment by project type before computing statistics",
                default=False,
                help=(
                    "When on, the per-ratio IQR is recomputed within "
                    "each (E05_DEPARTMENT, BUSINESS) segment instead "
                    "of across the whole dataset - a deepwater FPSO "
                    "is no longer judged against an onshore refinery."
                ),
                description=(
                    "**How this option works**\n\n"
                    "**Off (default - global scope):** for each "
                    "cross-discipline ratio the IQR is derived "
                    "across every eligible project in the dataset, "
                    "and every project is judged against the same "
                    "dataset-wide PASS band.\n\n"
                    "**On (segmented scope):** each project is tagged "
                    "with a composite segment key "
                    "`(E05_DEPARTMENT, BUSINESS)` looked up from the "
                    "`VWS_GP_STANDARD_SHARE` reference via "
                    "`PLANVIEW_ID → PROJECT_ID` - the same lookup "
                    "E6 / A7 / A8 / AC7 use. For each ratio the IQR "
                    "is recomputed **within each segment**, so a "
                    "deepwater FPSO and an onshore refinery are no "
                    "longer pooled into the same baseline. Segments "
                    "with fewer than the minimum project population "
                    "are NOT_APPLICABLE (pass) so a thinly-populated "
                    "bucket does not flag every project inside it "
                    "as an outlier of itself. Projects whose "
                    "project-type cannot be resolved (no associated "
                    "PLANVIEW_ID, unmatched PROJECT_ID, or null "
                    "`E05_DEPARTMENT` / `BUSINESS`) are PASS - "
                    "AC1 / AC2 already cover those gaps."
                ),
                required_columns_when_enabled=dict(
                    ACCE_AC8_SEGMENT_REQUIRED_COLUMNS
                ),
            ),
        ],
    ),
]
