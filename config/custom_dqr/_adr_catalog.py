"""ADR custom rule list."""
from __future__ import annotations

from config.custom_dqr._shared import (
    CustomRuleDef,
    CustomRuleOption,
    _iqr_threshold_option,
    _percentile_threshold_option,
    _uniform_mapping_option,
)
from src.custom_dqr_engine import (
    ADR_A1_REFERENCE,
    ADR_A1_REQUIRED_COLUMNS,
    ADR_A2_REFERENCE,
    ADR_A2_REQUIRED_COLUMNS,
    ADR_A3_DETECT_UNIFORM_MAPPING_PARAM,
    ADR_A3_MATERIALITY_USD,
    ADR_A3_MIN_MAPPING_POPULATION,
    ADR_A3_PERCENTILE,
    ADR_A3_PROJECT_SCOPED_PARAM,
    ADR_A3_PROJECT_SCOPED_REQUIRED_COLUMNS,
    ADR_A3_REFERENCE,
    ADR_A3_REQUIRED_COLUMNS,
    ADR_A3_THRESHOLD_CHOICES,
    ADR_A3_THRESHOLD_PARAM,
    ADR_A4_REQUIRED_COLUMNS,
    ADR_A5_REQUIRED_COLUMNS,
    ADR_A6_REQUIRED_COLUMNS,
    ADR_A7_EXTREME_IQR_MULTIPLIER,
    ADR_A7_MILD_IQR_MULTIPLIER,
    ADR_A7_MIN_POPULATION,
    ADR_A7_REQUIRED_COLUMNS,
    ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM,
    ADR_A7_SEGMENT_REQUIRED_COLUMNS,
    ADR_A7_THRESHOLD_CHOICES,
    ADR_A7_THRESHOLD_PARAM,
    ADR_A8_EXTREME_IQR_MULTIPLIER,
    ADR_A8_MILD_IQR_MULTIPLIER,
    ADR_A8_MIN_POPULATION,
    ADR_A8_REQUIRED_COLUMNS,
    ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM,
    ADR_A8_SEGMENT_REQUIRED_COLUMNS,
    ADR_A8_THRESHOLD_CHOICES,
    ADR_A8_THRESHOLD_PARAM,
    check_adr_a1,
    check_adr_a2,
    check_adr_a3,
    check_adr_a4,
    check_adr_a5,
    check_adr_a6,
    check_adr_a7,
    check_adr_a8,
)

ADR_RULES = [
    CustomRuleDef(
        id="A1",
        name="ISO Code of Account present (COR + SAB)",
        type="Completeness",
        description=(
            "Every ADR estimate item row must carry a "
            "``COMPLETE_WBC`` whose leading dot-separated segment "
            "(the ICARUS Code of Account group) resolves to both a "
            "valid ISO Code of Resource (``ISO_COR``) and a valid "
            "Standard Activity Breakdown (``SAB``) in the COA "
            "master. Without those codes, cost data cannot be "
            "normalized via the EMMA factor - a blocking gap."
        ),
        notes=(
            "Row-level Completeness with a join to the "
            "``ACCE_COA_MASTER`` reference dataset. The COA group "
            "is the first segment of ``COMPLETE_WBC`` before the "
            "first dot (e.g. ``313.1.10.10`` → ``313``). The master "
            "may carry multiple rows per ICARUS_COA - the rule "
            "picks the best-available mapping (preferring "
            "non-null, non-error values). ``ISO_COR`` and ``SAB`` "
            "are considered invalid when null, blank, or "
            "containing the ``ERROR`` / ``N/A`` markers. Rows fail "
            "when ``COMPLETE_WBC`` is missing, when the derived "
            "COA group does not resolve to a valid ``ISO_COR``, "
            "or when it does not resolve to a valid ``SAB``. The "
            "rule raises ``CustomRuleNotEvaluated`` when the "
            "reference dataset is unavailable so the gap is never "
            "silent."
        ),
        required_columns=dict(ADR_A1_REQUIRED_COLUMNS),
        blocking=True,
        check=check_adr_a1,
        reference=dict(ADR_A1_REFERENCE),
    ),
    CustomRuleDef(
        id="A2",
        name="Location + estimate date present & valid",
        type="Completeness & Validity",
        description=(
            "Each ADR record carries the estimate basis date "
            "(COST_UPDATE) in the fiscal quarter-year format (e.g. "
            "'2Q2019'), and a project location (COUNTRY) resolved via "
            "the Planview reference dataset."
        ),
        notes=(
            "COUNTRY is the project site location; COST_UPDATE is the "
            "estimate basis date (not data entry date). COST_UPDATE must "
            "be both populated (Completeness) and match the fiscal "
            "quarter-year shape [1-4]Q<YYYY>, e.g. '2Q2019' (Validity) - "
            "a populated but malformed value fails. If PLANVIEW_ID does "
            "not match any PROJECT_ID in the Planview reference, COUNTRY "
            "is treated as missing. All inputs are required to select the "
            "correct CU period for EMMA normalization."
        ),
        required_columns=dict(ADR_A2_REQUIRED_COLUMNS),
        blocking=False,
        check=check_adr_a2,
        reference=dict(ADR_A2_REFERENCE),
    ),
    CustomRuleDef(
        id="A3",
        name="Statistical WBC-to-ISO mapping ratio",
        type="Statistical Outlier",
        description=(
            "Flags ADR ISO mappings (``ISO_COR + SAB`` resolved "
            "from ``COMPLETE_WBC`` via the COA master) that "
            "aggregate more distinct ``COMPLETE_WBC`` values than "
            "the global "
            f"{int(ADR_A3_PERCENTILE * 100)}th-percentile ratio "
            "observed across the ADR portfolio - indicating the "
            "ISO bucket may be hiding meaningful source-system "
            "detail."
        ),
        notes=(
            "Mapping-quality statistical rule with a row-level "
            "verdict, mirroring EPT E3 against ADR. The metric is "
            "``COUNT(DISTINCT COMPLETE_WBC)`` per "
            "``(ISO_COR, SAB)`` bucket; the threshold is the "
            f"global {int(ADR_A3_PERCENTILE * 100)}th-percentile "
            "ratio across all eligible mappings, recomputed from "
            "the data on every run (no fixed benchmark). A bucket "
            "fails only when its ratio is strictly greater than "
            "the P90 AND the bucket is *material* - "
            f"``SUM(COST_TOTAL_HOURS) > 0`` OR ``SUM(COST_TOTAL_COST) "
            f">= {int(ADR_A3_MATERIALITY_USD):,} USD`` - to "
            "suppress false positives from planning / "
            "structural-only mappings. Rows whose WBC does not "
            "resolve to a valid ``ISO_COR`` / ``SAB`` are PASS - "
            "A1 already covers that completeness gap and A3 must "
            "not double-penalise. Eligible-mapping populations "
            f"below {ADR_A3_MIN_MAPPING_POPULATION} are NOT_APPLICABLE "
            "and pass. Default scope is global / dataset-wide; the "
            "project-scope toggle on the rule card switches the "
            "percentile to a per-PLANVIEW_ID baseline (mirrors EPT "
            "E3). The rule raises ``CustomRuleNotEvaluated`` when "
            "the COA master is unavailable so the gap is never "
            "silent."
        ),
        required_columns=dict(ADR_A3_REQUIRED_COLUMNS),
        blocking=False,
        check=check_adr_a3,
        reference=dict(ADR_A3_REFERENCE),
        select_options=[
            _percentile_threshold_option(
                ADR_A3_THRESHOLD_PARAM,
                ADR_A3_THRESHOLD_CHOICES,
                ADR_A3_PERCENTILE,
            ),
        ],
        options=[
            CustomRuleOption(
                key=ADR_A3_PROJECT_SCOPED_PARAM,
                label="Compute percentile per project (PLANVIEW_ID)",
                default=False,
                help=(
                    "When on, the nth-percentile threshold is "
                    "computed within each PLANVIEW_ID partition "
                    "instead of globally."
                ),
                description=(
                    "**How this option works**\n\n"
                    "**Off (default - global scope):** one P90 of "
                    "`COUNT(DISTINCT COMPLETE_WBC)` is computed "
                    "across every eligible (ISO_COR, SAB) bucket in "
                    "the dataset. Every mapping is judged against "
                    "the same dataset-wide baseline - best when you "
                    "want a single benchmark and projects share "
                    "comparable WBC discipline.\n\n"
                    "**On (project scope):** the group key becomes "
                    "`(PLANVIEW_ID, ISO_COR, SAB)` and the P90 is "
                    "recomputed *within each PLANVIEW_ID partition* "
                    "(`PARTITION BY PLANVIEW_ID`). Each project gets "
                    "its **own** statistical baseline, so a project "
                    "with naturally fine-grained WBCs is not dragged "
                    "down by peers that aggregate aggressively. "
                    "Requires `PLANVIEW_ID` to be a CDE; rows missing "
                    "PLANVIEW_ID are treated as PASS (A2 already "
                    "covers the missing-project linkage)."
                ),
                required_columns_when_enabled=dict(
                    ADR_A3_PROJECT_SCOPED_REQUIRED_COLUMNS
                ),
            ),
            _uniform_mapping_option(ADR_A3_DETECT_UNIFORM_MAPPING_PARAM),
        ],
    ),
    CustomRuleDef(
        id="A4",
        name="Core quantities populated & non-negative project totals",
        type="Completeness & Validity",
        description=(
            "Validates that each ADR project has its applicable "
            "core quantity types populated, and that the project's "
            "total quantity is not negative. The seven core types "
            "(piping LF, concrete CY, steel tons, cable length, "
            "transmitter / instrument count, equipment count, "
            "module count) are evaluated relative to the project "
            "scope - only types implied by the project's "
            "``ITEM_TYPE`` / ``ITEM_DESCRIPTION`` are required."
        ),
        notes=(
            "Project-level rule with row-level verdict: every row "
            "of a project that fails inherits the FAIL (same "
            "row-level / group-verdict pattern as E6 / A8). For "
            "each ``PLANVIEW_ID`` the rule first determines which "
            "core quantity types are *expected* from the per-row "
            "scope classification (``ITEM_TYPE`` + "
            "``ITEM_DESCRIPTION``), then which ones are *populated* "
            "(positive ``QTY_QUANTITY`` AND a matching "
            "(``ITEM_TYPE``, ``QTY_UOM``) pattern). A project fails "
            "iff any expected type lacks a populated row, OR its "
            "total ``QTY_QUANTITY`` sums to a negative value. "
            "Individual rows may carry negative quantities "
            "(corrections / reversals); only a project-wide "
            "negative total fails. Rows with null/blank "
            "``PLANVIEW_ID`` pass - they cannot be assigned to a "
            "project group. The classifier intentionally uses a "
            "conservative allow-list for EQUIPMENT_COUNT (specific "
            "(ITEM_TYPE, UOM) pairs) and for piping / cable / "
            "transmitter to avoid counting subcomponents or "
            "off-discipline UOMs."
        ),
        required_columns=dict(ADR_A4_REQUIRED_COLUMNS),
        blocking=False,
        check=check_adr_a4,
    ),
    CustomRuleDef(
        id="A5",
        name="Design details present when quantity exists",
        type="Consistency",
        description=(
            "When an estimate item has a non-zero quantity, at least "
            "one design parameter value must also be populated for the "
            "same ROW_ID - otherwise the quantity cannot be interpreted, "
            "normalized, or compared."
        ),
        notes=(
            "Evaluated at the ROW_ID grain on the denormalized data "
            "product. ``QTY_QUANTITY`` is the SUM of "
            "ADR_FACT_ESTIMATEQTYRESULTS.QUANTITY for the item (the "
            "builder aggregates the 1:N child rows); a row is treated "
            "as having a quantity when that sum is non-null and not "
            "equal to zero. ``DESIGN_PARAMETER_VALUE`` comes from the "
            "1:1 ADR_DIM_ESTIMATEDESIGNDETAILS join and is considered "
            "present when populated (non-null, non-blank). The current "
            "version does not validate the *type* of design detail - "
            "any populated value is sufficient. Items with no non-zero "
            "quantity are out of scope and pass."
        ),
        required_columns=dict(ADR_A5_REQUIRED_COLUMNS),
        blocking=False,
        check=check_adr_a5,
    ),
    CustomRuleDef(
        id="A6",
        name="Construction hours present when quantity exists",
        type="Consistency",
        description=(
            "When an estimate item has a non-zero quantity, "
            "construction hours must also be populated for the same "
            "ROW_ID - otherwise productivity metrics such as hours "
            "per unit cannot be calculated."
        ),
        notes=(
            "Evaluated at the ROW_ID grain on the denormalized data "
            "product. ``QTY_QUANTITY`` is the SUM of "
            "ADR_FACT_ESTIMATEQTYRESULTS.QUANTITY; ``COST_TOTAL_HOURS`` "
            "and ``COST_DB_TOTAL_HOURS`` are the SUMs of the matching "
            "hours columns from ADR_FACT_ESTIMATECOSTRESULTS (the "
            "builder aggregates the 1:N child rows). Construction "
            "hours are considered present when at least one of the two "
            "aggregates is strictly greater than zero - null inputs "
            "are coerced to zero, and negative aggregates do not "
            "count. The rule is one-directional: hours-without-"
            "quantity passes; only quantity-without-hours fails."
        ),
        required_columns=dict(ADR_A6_REQUIRED_COLUMNS),
        blocking=False,
        check=check_adr_a6,
    ),
    CustomRuleDef(
        id="A7",
        name="Within-discipline quantity / hour ratio outlier",
        type="Statistical Outlier",
        description=(
            "Flags estimate items whose hours-per-quantity ratio "
            "(``COST_TOTAL_HOURS / QTY_QUANTITY``) is a statistical "
            "outlier compared to other items in the same "
            "(``ITEM_TYPE``, ``QTY_UOM``) population - IQR mild "
            "bounds derived from the segment itself, no fixed "
            "benchmark."
        ),
        notes=(
            "Per-row ratio, segment-level threshold. Eligible rows "
            "(``QTY_QUANTITY > 0`` AND ``COST_TOTAL_HOURS > 0`` with "
            "``ITEM_TYPE`` and ``QTY_UOM`` populated) compute the "
            "ratio; the population is partitioned by ``(ITEM_TYPE, "
            "QTY_UOM)`` and IQR thresholds (``Q1 - "
            f"{ADR_A7_MILD_IQR_MULTIPLIER:g} * IQR`` … ``Q3 + "
            f"{ADR_A7_MILD_IQR_MULTIPLIER:g} * IQR``) are derived per "
            "segment. The "
            f"{ADR_A7_EXTREME_IQR_MULTIPLIER:g}× extreme multiplier "
            "is documented for severity classification - every "
            "extreme outlier is also a mild outlier, so the Boolean "
            "result uses only the mild bound. NOT_APPLICABLE → PASS "
            "for: ratio cannot be calculated (qty/hours missing or "
            "non-positive); ``ITEM_TYPE`` or ``QTY_UOM`` blank; "
            f"segment population below {ADR_A7_MIN_POPULATION}; "
            "segment IQR equals zero (no variation). The project-type "
            "segmentation toggle on the rule card extends the segment "
            "key with (E05_DEPARTMENT, BUSINESS) resolved via the "
            "Planview reference (``PLANVIEW_ID → PROJECT_ID``), so a "
            "deepwater FPSO is no longer pooled with an onshore "
            "refinery when judging within-discipline productivity. "
            "Failed records should be reviewed, not auto-corrected "
            "- the rule identifies anomalies, not errors."
        ),
        required_columns=dict(ADR_A7_REQUIRED_COLUMNS),
        blocking=False,
        check=check_adr_a7,
        select_options=[
            _iqr_threshold_option(
                ADR_A7_THRESHOLD_PARAM,
                ADR_A7_THRESHOLD_CHOICES,
                ADR_A7_MILD_IQR_MULTIPLIER,
            ),
        ],
        options=[
            CustomRuleOption(
                key=ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM,
                label="Segment by project type before computing statistics",
                default=False,
                help=(
                    "When on, the IQR thresholds are recomputed within "
                    "each (ITEM_TYPE, QTY_UOM, E05_DEPARTMENT, "
                    "BUSINESS) segment instead of just (ITEM_TYPE, "
                    "QTY_UOM) - a deepwater FPSO is no longer judged "
                    "against an onshore refinery within the same "
                    "discipline."
                ),
                description=(
                    "**How this option works**\n\n"
                    "**Off (default - discipline-only scope):** the "
                    "IQR is derived per `(ITEM_TYPE, QTY_UOM)` segment "
                    "across every eligible item in the dataset. Every "
                    "row is judged against the discipline's "
                    "dataset-wide PASS band.\n\n"
                    "**On (project-type scope):** each row is tagged "
                    "with a composite project-type key "
                    "`(E05_DEPARTMENT, BUSINESS)` looked up from the "
                    "`VWS_GP_STANDARD_SHARE` reference via "
                    "`PLANVIEW_ID → PROJECT_ID` - the same lookup E6 "
                    "uses. The segment key becomes `(ITEM_TYPE, "
                    "QTY_UOM, E05_DEPARTMENT, BUSINESS)` and the IQR "
                    "is recomputed within each bucket, so a deepwater "
                    "FPSO and an onshore refinery are no longer pooled "
                    "into the same baseline at the discipline level. "
                    "Segments with fewer than the minimum row "
                    "population are NOT_APPLICABLE (pass) so a "
                    "thinly-populated bucket does not flag every row "
                    "inside it as an outlier of itself. Rows whose "
                    "project-type cannot be resolved (missing "
                    "PLANVIEW_ID, unmatched PROJECT_ID, or null "
                    "`E05_DEPARTMENT` / `BUSINESS`) are PASS - A1 / "
                    "A2 already cover those gaps."
                ),
                required_columns_when_enabled=dict(
                    ADR_A7_SEGMENT_REQUIRED_COLUMNS
                ),
            ),
        ],
    ),
    CustomRuleDef(
        id="A8",
        name="Cross-discipline quantity ratios",
        type="Statistical Outlier",
        description=(
            "Validates the overall *shape* of each project. For "
            "every ``ROOT_ITEM_NAME`` the rule classifies eligible "
            "quantities into discipline categories "
            "(PIPE_LENGTH, EQUIPMENT_COUNT, CABLE_LENGTH, "
            "TRANSMITTER_COUNT, STEEL_WEIGHT, CONCRETE_VOLUME) "
            "from ``ITEM_TYPE`` + ``QTY_UOM``, computes "
            "cross-discipline ratios (e.g. pipe length per "
            "equipment count), and flags projects whose ratio is a "
            "statistical outlier compared to peer projects."
        ),
        notes=(
            "Project-level statistical rule with row-level verdict: "
            "every row of a project that is flagged on at least one "
            "ratio inherits the FAIL (same row-level / "
            "group-verdict pattern as E6). Eligible rows are "
            "positive-quantity rows with ``ITEM_TYPE``, ``QTY_UOM``, "
            "and ``ROOT_ITEM_NAME`` populated; rows the classifier "
            "doesn't recognise simply don't contribute to a ratio. "
            "Per-ratio populations are derived from projects whose "
            "numerator and denominator quantities are both > 0; IQR "
            "mild bounds (``Q1 - "
            f"{ADR_A8_MILD_IQR_MULTIPLIER:g} * IQR`` … ``Q3 + "
            f"{ADR_A8_MILD_IQR_MULTIPLIER:g} * IQR``) flag outlier "
            "projects. The "
            f"{ADR_A8_EXTREME_IQR_MULTIPLIER:g}× extreme multiplier "
            "is documented for severity classification only - every "
            "extreme outlier is also a mild outlier, so the Boolean "
            "result uses only the mild bound. NOT_APPLICABLE → PASS "
            "for: rows with null/blank ``ROOT_ITEM_NAME``; ratios "
            f"with population below {ADR_A8_MIN_POPULATION} "
            "projects; ratios where the population IQR equals zero. "
            "The project-type segmentation toggle on the rule card "
            "partitions the per-ratio IQR population by "
            "(E05_DEPARTMENT, BUSINESS) resolved via the Planview "
            "reference (``PLANVIEW_ID → PROJECT_ID``), so a "
            "deepwater FPSO is not pooled with an onshore refinery. "
            "A failed project should be reviewed; the rule "
            "identifies statistical anomalies, not errors."
        ),
        required_columns=dict(ADR_A8_REQUIRED_COLUMNS),
        blocking=False,
        check=check_adr_a8,
        select_options=[
            _iqr_threshold_option(
                ADR_A8_THRESHOLD_PARAM,
                ADR_A8_THRESHOLD_CHOICES,
                ADR_A8_MILD_IQR_MULTIPLIER,
            ),
        ],
        options=[
            CustomRuleOption(
                key=ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM,
                label="Segment by project type before computing statistics",
                default=False,
                help=(
                    "When on, the per-ratio IQR is recomputed within "
                    "each (E05_DEPARTMENT, BUSINESS) segment instead "
                    "of across the whole dataset - a deepwater FPSO "
                    "is no longer judged against an onshore "
                    "refinery."
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
                    "E6 / A7 use. For each ratio the IQR is "
                    "recomputed **within each segment**, so a "
                    "deepwater FPSO and an onshore refinery are no "
                    "longer pooled into the same baseline. Segments "
                    "with fewer than the minimum project population "
                    "are NOT_APPLICABLE (pass) so a thinly-populated "
                    "bucket does not flag every project inside it "
                    "as an outlier of itself. Projects whose "
                    "project-type cannot be resolved (no associated "
                    "PLANVIEW_ID, unmatched PROJECT_ID, or null "
                    "`E05_DEPARTMENT` / `BUSINESS`) are PASS - "
                    "A1 / A2 already cover those gaps."
                ),
                required_columns_when_enabled=dict(
                    ADR_A8_SEGMENT_REQUIRED_COLUMNS
                ),
            ),
        ],
    ),
]
