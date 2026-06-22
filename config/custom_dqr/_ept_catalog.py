"""EPT custom rule list.

The EPT rules in :data:`EPT_RULES` are exported as a list of
:class:`CustomRuleDef` (one per E1..E7 entry). The check callables and
constants live in :mod:`src.custom_dqr_engine` and are re-exported there
from :mod:`src.custom_dqr._ept_rules`.
"""
from __future__ import annotations

from config.custom_dqr._shared import (
    CustomRuleDef,
    CustomRuleOption,
    _iqr_threshold_option,
    _percentile_threshold_option,
    _uniform_mapping_option,
)
from src.custom_dqr_engine import (
    EPT_E1_REQUIRED_COLUMNS,
    EPT_E2_REFERENCE,
    EPT_E2_REQUIRED_COLUMNS,
    EPT_E3_DETECT_UNIFORM_MAPPING_PARAM,
    EPT_E3_MATERIALITY_USD,
    EPT_E3_PERCENTILE,
    EPT_E3_PROJECT_SCOPED_PARAM,
    EPT_E3_PROJECT_SCOPED_REQUIRED_COLUMNS,
    EPT_E3_REQUIRED_COLUMNS,
    EPT_E3_THRESHOLD_CHOICES,
    EPT_E3_THRESHOLD_PARAM,
    EPT_E4_REQUIRED_COLUMNS,
    EPT_E5_REQUIRED_COLUMNS,
    EPT_E6_MILD_IQR_MULTIPLIER,
    EPT_E6_REQUIRED_COLUMNS,
    EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM,
    EPT_E6_THRESHOLD_CHOICES,
    EPT_E6_THRESHOLD_PARAM,
    EPT_E7_REFERENCE,
    EPT_E7_REQUIRED_COLUMNS,
    check_ept_e1,
    check_ept_e2,
    check_ept_e3,
    check_ept_e4,
    check_ept_e5,
    check_ept_e6,
    check_ept_e7,
)

EPT_RULES = [
    CustomRuleDef(
        id="E1",
        name="ISO Code of Account Present (COR + SAB)",
        type="Completeness",
        description=(
            "Every cost record has the required information to select the "
            "correct EMMA normalization factor."
        ),
        notes=(
            "Without COR/SAB, cost data cannot be normalized. This is a "
            "blocking gap."
        ),
        required_columns=dict(EPT_E1_REQUIRED_COLUMNS),
        blocking=True,
        check=check_ept_e1,
    ),
    CustomRuleDef(
        id="E2",
        name="Location + estimate date present",
        type="Completeness",
        description=(
            "Each EPT record carries the estimate basis date "
            "(CENTROID_DATE) and a project location (COUNTRY) resolved "
            "via the Planview reference dataset."
        ),
        notes=(
            "COUNTRY is the project site location; CENTROID_DATE is the "
            "estimate basis date (not data entry date). If PLANVIEW_ID "
            "does not match any PROJECT_ID in the Planview reference, "
            "COUNTRY is treated as missing. Both inputs are required to "
            "select the correct CU period for EMMA normalization."
        ),
        required_columns=dict(EPT_E2_REQUIRED_COLUMNS),
        blocking=False,
        check=check_ept_e2,
        reference=dict(EPT_E2_REFERENCE),
    ),
    CustomRuleDef(
        id="E3",
        name="Statistical Excessive WBC to ISO Mapping",
        type="Statistical Outlier",
        description=(
            "Flags ISO mappings (CODE_OF_RESOURCE + STANDARD_ACTIVITY_"
            "BREAKDOWN) that aggregate more distinct WBC_LEVEL_5 "
            f"activities than the {int(EPT_E3_PERCENTILE * 100)}th-"
            "percentile ratio observed across all eligible mappings, "
            "indicating potential loss of operational detail."
        ),
        notes=(
            "Contextual statistical rule: the threshold is derived from "
            "the data's distribution of WBC-to-ISO ratios, not a fixed "
            "limit. A FAIL only fires when the mapping is also material "
            "- SUM(TOTAL_HOURS) > 0 OR "
            f"SUM(TOTAL_COST_USD) >= {int(EPT_E3_MATERIALITY_USD):,} USD"
            " - to suppress false positives from planning / "
            "structural-only records. Default scope is global / "
            "dataset-wide; the project-scope toggle on the rule card "
            "switches the percentile to a per-PLANVIEW_ID baseline."
        ),
        required_columns=dict(EPT_E3_REQUIRED_COLUMNS),
        blocking=False,
        check=check_ept_e3,
        select_options=[
            _percentile_threshold_option(
                EPT_E3_THRESHOLD_PARAM,
                EPT_E3_THRESHOLD_CHOICES,
                EPT_E3_PERCENTILE,
            ),
        ],
        options=[
            CustomRuleOption(
                key=EPT_E3_PROJECT_SCOPED_PARAM,
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
                    "`COUNT(DISTINCT WBC_LEVEL_5)` is computed across "
                    "every eligible ISO mapping in the dataset. Every "
                    "mapping is judged against the same dataset-wide "
                    "baseline - best when you want a single benchmark "
                    "and projects share comparable WBC discipline.\n\n"
                    "**On (project scope):** the group key becomes "
                    "`(PLANVIEW_ID, COR, SAB)` and the P90 is "
                    "recomputed *within each PLANVIEW_ID partition* "
                    "(`PARTITION BY PLANVIEW_ID`). Each project gets "
                    "its **own** statistical baseline, so a project "
                    "with naturally fine-grained WBCs is not dragged "
                    "down by peers that aggregate aggressively. "
                    "Requires `PLANVIEW_ID` to be a CDE; rows missing "
                    "PLANVIEW_ID are treated as PASS (E7 already "
                    "covers the missing-project linkage)."
                ),
                required_columns_when_enabled=dict(
                    EPT_E3_PROJECT_SCOPED_REQUIRED_COLUMNS
                ),
            ),
            _uniform_mapping_option(EPT_E3_DETECT_UNIFORM_MAPPING_PARAM),
        ],
    ),
    CustomRuleDef(
        id="E4",
        name="Level 1 cost category populated",
        type="Completeness",
        description=(
            "Even if granular cost categories are not available, Level 1 "
            "must exist."
        ),
        notes=(
            "Ideally cost is broken down by category. Level 1 is the "
            "minimum acceptable granularity."
        ),
        required_columns=dict(EPT_E4_REQUIRED_COLUMNS),
        blocking=False,
        check=check_ept_e4,
    ),
    CustomRuleDef(
        id="E5",
        name="FEED / Engineering hours estimate present when cost exists",
        type="Consistency",
        description=(
            "For FEED / Engineering records (identified from "
            "WBC_LEVEL_1) cost and hours must appear together: a row "
            "with a positive cost and zero TOTAL_HOURS - or with hours "
            "but no cost - fails. Both populated, or both absent, pass."
        ),
        notes=(
            "Scope is determined by a case-insensitive match on "
            "WBC_LEVEL_1 (FEED, FEED BY CONTRACTOR(S), DETAILED "
            "ENGINEERING, ENGINEERING COSTS, …). cost_amount = "
            "COALESCE(TOTAL_COST_USD, TOTAL_COST_ESTIMATE_CURRENCY, 0); "
            "hours_amount = COALESCE(TOTAL_HOURS, 0). Null values are "
            "treated as zero - a value is 'present' only when > 0. "
            "Non-FEED rows are Not Applicable and pass."
        ),
        required_columns=dict(EPT_E5_REQUIRED_COLUMNS),
        blocking=False,
        check=check_ept_e5,
    ),
    CustomRuleDef(
        id="E6",
        name="Cost-to-hours ratio outlier check",
        type="Statistical Outlier",
        description=(
            "Flags projects whose total-cost / total-hours ratio is a "
            "statistical outlier (IQR mild bounds) compared with the "
            "broader project population - a hint that cost or hours may "
            "be missing, mis-allocated, or recorded in the wrong unit."
        ),
        notes=(
            "Project-level ratio, row-level verdict: cost_amount = "
            "COALESCE(TOTAL_COST_USD, TOTAL_COST_ESTIMATE_CURRENCY, 0); "
            "hours_amount = COALESCE(TOTAL_HOURS, 0); aggregated by "
            "PLANVIEW_ID. Thresholds are derived from the data using the "
            "IQR method (PASS within Q1-1.5*IQR … Q3+1.5*IQR). Projects "
            "with project_total_hours <= 0, rows lacking PLANVIEW_ID, "
            "and runs with fewer than the minimum number of eligible "
            "projects are NOT_APPLICABLE and pass - completeness rules "
            "(E5) and project-linkage (E7) cover those gaps separately. "
            "The project-type segmentation toggle on the rule card "
            "recomputes the IQR baseline within each (E05_DEPARTMENT, "
            "BUSINESS) bucket resolved via the Planview reference, so a "
            "deepwater FPSO is not pooled with an onshore refinery."
        ),
        required_columns=dict(EPT_E6_REQUIRED_COLUMNS),
        blocking=False,
        check=check_ept_e6,
        select_options=[
            _iqr_threshold_option(
                EPT_E6_THRESHOLD_PARAM,
                EPT_E6_THRESHOLD_CHOICES,
                EPT_E6_MILD_IQR_MULTIPLIER,
            ),
        ],
        options=[
            CustomRuleOption(
                key=EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM,
                label="Segment by project type before computing statistics",
                default=False,
                help=(
                    "When on, the IQR thresholds are recomputed within "
                    "each (E05_DEPARTMENT, BUSINESS) segment instead of "
                    "globally - a deepwater FPSO is no longer judged "
                    "against an onshore refinery."
                ),
                description=(
                    "**How this option works**\n\n"
                    "**Off (default - global scope):** one set of "
                    "`Q1 / Q3 / IQR` is derived across every eligible "
                    "project in the dataset, and every project is "
                    "judged against the same dataset-wide PASS band.\n\n"
                    "**On (segmented scope):** each project is tagged "
                    "with a composite segment key "
                    "`(E05_DEPARTMENT, BUSINESS)` looked up from the "
                    "`VWS_GP_STANDARD_SHARE` reference via "
                    "`PLANVIEW_ID → PROJECT_ID`. The IQR is recomputed "
                    "**within each segment**, so a deepwater FPSO and "
                    "an onshore refinery are no longer pooled into the "
                    "same baseline. Segments with fewer than the "
                    "minimum project population are NOT_APPLICABLE "
                    "(pass) so a thinly-populated bucket does not flag "
                    "every project inside it as an outlier of itself. "
                    "Projects whose segment cannot be resolved "
                    "(missing PLANVIEW_ID, unmatched PROJECT_ID, or "
                    "null `E05_DEPARTMENT` / `BUSINESS`) are likewise "
                    "PASS - E7 / E2 already cover those gaps."
                ),
            ),
        ],
    ),
    CustomRuleDef(
        id="E7",
        name="Project Key linkage",
        type="Referential Integrity",
        description=(
            "EPT record can be joined to the project master via a valid "
            "project identifier."
        ),
        notes=(
            "If a EPT record cannot join to the project master, it is "
            "orphaned and cannot be used in the integrated data product."
        ),
        required_columns=dict(EPT_E7_REQUIRED_COLUMNS),
        blocking=True,
        check=check_ept_e7,
        reference=dict(EPT_E7_REFERENCE),
    ),
]
