# pyright: reportArgumentType=false, reportOperatorIssue=false
# pyright: reportCallIssue=false, reportReturnType=false
# pyright: reportAttributeAccessIssue=false
"""ADR custom DQR rule checks (A1-A8).

ADR rules consume the denormalized data product built by joining the ADR
table to its dependencies. Some are referential (A1 / A2 → ACCE_COA_MASTER),
some statistical (A3 / A7 / A8 / mapping outliers), others completeness or
consistency. Each callable returns ``(df) -> pd.Series[bool]``; True means
the row passes.

The pragma block at the top silences pyright on this file. The
pandas-stubs are aggressive: ``df[col]`` is typed as ``Series | DataFrame``
because pandas allows ``df[bool_mask]`` and ``df[[col1, col2]]`` to share
the same operator; in practice every call site here uses a single string
column and gets a ``Series`` back. The runtime contract is well-tested
(see ``tests/test_custom_dqr_engine.py`` - 100% pass against the mock
data + edge cases), so silencing pyright on the categories dominated by
that ambiguity is the right call - the alternative is hundreds of
``cast(pd.Series, ...)`` annotations with no benefit.
"""
from __future__ import annotations

from typing import Dict, List, Tuple, TypedDict

import numpy as np
import pandas as pd

from src.custom_dqr._shared import (
    CustomRuleNotEvaluated,
    _coerce_threshold,
    _is_filled,
    _resolve_planview_segment_map,
)
from src.custom_dqr._validators import (
    validate_completeness_rule,
    validate_referential_integrity_rule,
)


class ADRA3Params(TypedDict, total=False):
    """Step 4.2 -> assignment.params shape for ADR A3 (mirrors EPT E3)."""
    threshold_percentile: float       # ADR_A3_THRESHOLD_PARAM
    project_scoped: bool              # ADR_A3_PROJECT_SCOPED_PARAM
    detect_uniform_mapping: bool      # ADR_A3_DETECT_UNIFORM_MAPPING_PARAM


class ADRA7Params(TypedDict, total=False):
    """Step 4.2 -> assignment.params shape for ADR A7."""
    threshold_iqr_multiplier: float   # ADR_A7_THRESHOLD_PARAM
    segment_by_project_type: bool     # ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM


class ADRA8Params(TypedDict, total=False):
    """Step 4.2 -> assignment.params shape for ADR A8."""
    threshold_iqr_multiplier: float   # ADR_A8_THRESHOLD_PARAM
    segment_by_project_type: bool     # ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM

# =============================================================================
# ADR custom rules
# =============================================================================

ADR_A1_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
    "Complete WBC": "COMPLETE_WBC",
}

ADR_A1_REFERENCE = {
    "reference_dataset": "ACCE_COA_MASTER",
    "source_column": "COMPLETE_WBC",     # in ADR (first dot segment is the COA group)
    "reference_column": "ICARUS_COA",    # in ACCE_COA_MASTER
    "lookup_column": "ISO_COR / SAB",    # both must resolve to a valid value
}


ADR_A2_REQUIRED_COLUMNS = {
    "Estimate Basis Date": "COST_UPDATE",
    "Project Key": "PLANVIEW_ID",
}

ADR_A2_REFERENCE = {
    "reference_dataset": "VWS_GP_STANDARD_SHARE",
    "source_column": "PLANVIEW_ID",      # in ADR
    "reference_column": "PROJECT_ID",    # in VWS_GP_STANDARD_SHARE
    "lookup_column": "COUNTRY",          # populated value to check post-join
}

# A2 Validity: COST_UPDATE is a fiscal quarter-year period, NOT a calendar
# date. Production values look like "2Q2019", "4Q2015", "3Q2022": a quarter
# digit 1-4, the literal "Q", then a 4-digit year. Case-insensitive on the
# "Q". A populated value that does not match this shape fails A2 on Validity.
ADR_A2_DATE_PATTERN = r"[1-4]Q\d{4}"

# A3: Statistical WBC-to-ISO mapping ratio (ADR).
#
# Mapping-quality statistical rule with row-level verdict. For each
# valid ISO mapping (resolved via the same ``ACCE_COA_MASTER`` lookup
# A1 uses) the rule counts distinct ``COMPLETE_WBC`` values rolling
# through the bucket, and flags mappings whose ratio exceeds the
# global ``P90`` and meets the materiality bar
# (``SUM(TOTAL_HOURS) > 0`` OR ``SUM(TOTAL_COST) >= materiality``).
# Every row of a flagged mapping inherits the FAIL, same row-level /
# group-verdict pattern as E3 / E6 / A8.
#
# Source columns after prefixing on the denormalized data product:
#   - ``COMPLETE_WBC``       - pass-through from the primary item table.
#   - ``PLANVIEW_ID``        - pass-through, used for diagnostics.
#   - ``COST_TOTAL_HOURS``   - SUM of TOTAL_HOURS (from COST results).
#   - ``COST_TOTAL_COST``    - SUM of TOTAL_COST (from COST results).
ADR_A3_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
    "Complete WBC": "COMPLETE_WBC",
    "Total Hours": "COST_TOTAL_HOURS",
    "Total Cost": "COST_TOTAL_COST",
}

ADR_A3_REFERENCE = {
    "reference_dataset": "ACCE_COA_MASTER",
    "source_column": "COMPLETE_WBC",     # in ADR (first dot segment is the COA group)
    "reference_column": "ICARUS_COA",    # in ACCE_COA_MASTER
    "lookup_column": "ISO_COR / SAB",    # mappings derived from the join
}

# Statistical-threshold parameters. Mirrors EPT E3's framing: the ratio
# is judged against the dataset-wide ``P90`` of WBC-to-ISO ratios; the
# materiality filter suppresses false positives from planning /
# structural-only mappings.
ADR_A3_PERCENTILE = 0.90
ADR_A3_MATERIALITY_USD = 100_000.0
# Minimum number of eligible ISO mappings required before the P90 is
# computed. Below this the rule is NOT_APPLICABLE - population too
# small to call any mapping an outlier.
ADR_A3_MIN_MAPPING_POPULATION = 10

# Percentile-threshold customization for A3, mirrors EPT E3's selectbox.
# check_adr_a3 reads ``params[ADR_A3_THRESHOLD_PARAM]`` and falls back to
# ``ADR_A3_PERCENTILE`` (P90) when the param is absent.
ADR_A3_THRESHOLD_PARAM = "threshold_percentile"
ADR_A3_THRESHOLD_CHOICES: Tuple[Tuple[float, str], ...] = (
    (0.75, "P75 - lenient"),
    (0.90, "P90 - recommended"),
    (0.95, "P95 - strict"),
    (0.99, "P99 - very strict"),
)

# Project-scope toggle - A3 mirror of EPT_E3_PROJECT_SCOPED_PARAM. When on,
# the percentile baseline is recomputed *within each PLANVIEW_ID partition*
# instead of globally, so a project with naturally fine-grained WBCs is not
# dragged down by peers that aggregate aggressively. The group key becomes
# ``(PLANVIEW_ID, ISO_COR, SAB)`` and rows lacking PLANVIEW_ID are treated
# as PASS (A2's territory).
ADR_A3_PROJECT_SCOPED_PARAM = "project_scoped"
ADR_A3_PROJECT_SCOPED_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
}

# Uniform 1:1 mapping detection - A3 mirror of EPT_E3_DETECT_UNIFORM_MAPPING_PARAM.
# When on, after the regular percentile fail every *material* (ISO_COR, SAB)
# bucket whose distinct-WBC ratio equals 1 also fails, typically a sign
# that ``COMPLETE_WBC`` codes are being copied 1:1 into the ISO bucket
# rather than aggregated. Default off so existing scorecards stay stable.
ADR_A3_DETECT_UNIFORM_MAPPING_PARAM = "detect_uniform_mapping"


# A4: Core quantities populated & non-negative project totals.
#
# Project-level Completeness + Validity rule with row-level verdict. For
# each ``PLANVIEW_ID`` the rule:
#   1. detects which of the seven core quantity types are *expected*
#      from the project's item types / descriptions;
#   2. detects which core quantity types are *populated* (any positive
#      quantity row classifies into that type);
#   3. fails the project iff at least one expected type is missing;
#   4. fails the project iff its total ``QTY_QUANTITY`` is negative
#      (row-level negatives are allowed; only the project sum is checked).
# Every row of a failing project inherits the FAIL, same row-level /
# group-verdict pattern as E6 / A8.
#
# Source columns after prefixing on the denormalized data product:
#   - ``PLANVIEW_ID``       - pass-through, the project key.
#   - ``ITEM_TYPE``         - pass-through.
#   - ``ITEM_DESCRIPTION``  - pass-through (used for module-scope detection).
#   - ``QTY_QUANTITY``      - SUM of QUANTITY (from QTY results).
#   - ``QTY_UOM``           - first UOM seen per ROW_ID.
ADR_A4_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
    "Item Type": "ITEM_TYPE",
    "Item Description": "ITEM_DESCRIPTION",
    "Quantity": "QTY_QUANTITY",
    "Quantity UOM": "QTY_UOM",
}

# Closed list of piping ITEM_TYPEs. A4's piping classifier is *stricter*
# than A8's (which uses a substring match against "Piping" / "Pipe") -
# the spec lists three explicit types.
_A4_PIPING_ITEM_TYPES = frozenset({
    "EstimateAbovegroundInstrumentPiping",
    "EstimatePipingUnderground",
    "EstimatePipingPneumatic",
})

# Allow-list of (ITEM_TYPE, UOM_lowercased) pairs that count as
# EQUIPMENT_COUNT. A4 is intentionally conservative - a generic
# ``EstimatePump + EA`` does not count; only the specific labels seen
# in production are accepted. Reproduces the spec §8.6 list verbatim.
_A4_EQUIPMENT_PAIRS = frozenset({
    ("EstimatePump", "parallel pumps"),
    ("EstimateElectricMotor", "drivers"),
    ("EstimateCentrifugalCompressor", "compressors"),
    ("EstimateCentrifugalCompressor", "fans"),
    ("EstimateReciprocatingCompressor", "compressors"),
    ("EstimateSteamTurbine", "drivers"),
    ("EstimateGasTurbine", "drivers"),
    ("EstimateHorizontalDrum", "drums"),
    ("EstimateTankage", "tanks"),
    ("EstimateTankage", "order quantity"),
    ("EstimateHairpinExchanger", "hairpin exchangers"),
    ("EstimatePlateExchanger", "plate exchangers"),
    ("EstimatePlateExchanger", "plate exchanger units"),
    ("EstimateAirCooledExchanger", "air-fins"),
    ("EstimateShellAndTubeExchanger", "shells"),
    ("EstimateVerticalPressureVessel", "vertical drum sections"),
})
_A4_EQUIPMENT_ITEM_TYPES = frozenset(t for (t, _) in _A4_EQUIPMENT_PAIRS)

# Instrument-count UOMs. Matched against the lowercased UOM. Mirrors
# spec §8.5 (more compact than A8's TRANSMITTER_COUNT set, which
# overlaps but doesn't include the singular "transmitter" label).
_A4_TRANSMITTER_UOMS = frozenset({
    "transmitter",
    "transmitters",
    "pressure gauges",
    "thermowells",
    "thermocouples",
    "control valves",
    "flow elements",
    "level gauges",
    "level switches",
    "pressure switches",
    "junction boxes",
    "i/p transducers",
    "solenoid valves",
})

# UOMs that count as MODULE_COUNT when the item is a module / modular.
_A4_MODULE_UOMS = frozenset({
    "module", "modules", "each", "ea", "unit", "units",
})

# Length / volume / weight UOMs used by A4's classifiers. Reuses the
# A8 alias map (defined further down) so ``CY`` ↔ ``yd³`` etc.
_A4_LENGTH_UOMS = frozenset({"ft", "m"})
_A4_VOLUME_UOMS = frozenset({"yd³", "m³"})
_A4_WEIGHT_UOMS = frozenset({"t", "t,sht"})

# Ordered list of the seven core quantity types, same order as the
# spec, used to produce stable diagnostics in tests.
_A4_CORE_QUANTITY_TYPES: Tuple[str, ...] = (
    "PIPING_LF",
    "CONCRETE_CY",
    "STEEL_TONS",
    "CABLE_LENGTH",
    "TRANSMITTER_COUNT",
    "EQUIPMENT_COUNT",
    "MODULE_COUNT",
)

# A5: Design details present when quantity exists.
#
# Operates on the denormalized ADR data product (built by
# ``src.data_product_builder.build_data_product``), which left-joins
# ``ADR_FACT_ESTIMATEQTYRESULTS`` (1:N → SUM-aggregated to one row per
# ``ROW_ID`` by the builder) and ``ADR_DIM_ESTIMATEDESIGNDETAILS`` (1:1)
# onto the primary item table. After the join the source columns appear as:
#   - ``QTY_QUANTITY``           - SUM of QUANTITY for the ROW_ID.
#   - ``DESIGN_PARAMETER_VALUE`` - pass-through (already prefixed).
ADR_A5_REQUIRED_COLUMNS = {
    "Quantity": "QTY_QUANTITY",
    "Design Parameter Value": "DESIGN_PARAMETER_VALUE",
}

# A6: Construction hours present when quantity exists.
#
# Operates on the denormalized ADR data product. The hours columns live on
# ``ADR_FACT_ESTIMATECOSTRESULTS`` (1:N child of the item record), so the
# builder aggregates them by SUM per ``ROW_ID`` before the rule sees them.
# Source columns after prefixing:
#   - ``QTY_QUANTITY``         - SUM of QUANTITY (from QTY results).
#   - ``COST_TOTAL_HOURS``     - SUM of TOTAL_HOURS (from COST results).
#   - ``COST_DB_TOTAL_HOURS``  - SUM of DB_TOTAL_HOURS (from COST results).
ADR_A6_REQUIRED_COLUMNS = {
    "Quantity": "QTY_QUANTITY",
    "Construction Hours": "COST_TOTAL_HOURS",
    "Construction Hours (DB)": "COST_DB_TOTAL_HOURS",
}

# A7: Within-discipline quantity / hour ratio outlier detection.
#
# Per-row eligibility: ``QTY_QUANTITY > 0`` and ``COST_TOTAL_HOURS > 0``
# and ``ITEM_TYPE`` / ``QTY_UOM`` populated. Eligible rows compute
# ``HOURS_PER_QUANTITY = COST_TOTAL_HOURS / QTY_QUANTITY``; the population
# is partitioned by ``(ITEM_TYPE, QTY_UOM)`` and IQR thresholds are
# derived per segment.
#
# - ``QTY_QUANTITY``      - SUM of QUANTITY (from QTY results).
# - ``QTY_UOM``           - first UOM seen per ROW_ID (mock: stable per
#   parent; production: ``MAX(QTY_UOM) AS QTY_UOM`` in the SQL spec §14).
# - ``ITEM_TYPE``         - pass-through from the primary item table.
# - ``COST_TOTAL_HOURS``  - SUM of TOTAL_HOURS (from COST results).
ADR_A7_REQUIRED_COLUMNS = {
    "Item Type": "ITEM_TYPE",
    "Quantity": "QTY_QUANTITY",
    "Quantity UOM": "QTY_UOM",
    "Construction Hours": "COST_TOTAL_HOURS",
}

# IQR multipliers for the within-segment outlier boundary. The mild
# multiplier defines the PASS / FAIL boundary; the extreme multiplier is
# kept as a documented constant (used in the rule spec's RULE_DETAIL
# classification), every extreme outlier is also a mild outlier and
# therefore a FAIL, so the Boolean check uses only the mild bound.
ADR_A7_MILD_IQR_MULTIPLIER = 1.5
ADR_A7_EXTREME_IQR_MULTIPLIER = 3.0
# Minimum number of eligible rows in a (ITEM_TYPE, QTY_UOM) segment
# required before IQR thresholds are derived. Below this the segment is
# NOT_APPLICABLE and every row in it passes, the population is too small
# to define an outlier reliably.
ADR_A7_MIN_POPULATION = 10

# IQR-multiplier threshold customization for A7. Step 4.2 UI exposes the
# choices below as a selectbox; check_adr_a7 reads
# ``params[ADR_A7_THRESHOLD_PARAM]`` and falls back to
# ``ADR_A7_MILD_IQR_MULTIPLIER`` (1.5×) when the param is absent.
ADR_A7_THRESHOLD_PARAM = "threshold_iqr_multiplier"
ADR_A7_THRESHOLD_CHOICES: Tuple[Tuple[float, str], ...] = (
    (1.5, "Mild (1.5×IQR) - recommended"),
    (2.0, "Moderate (2.0×IQR)"),
    (3.0, "Extreme (3.0×IQR) - lenient"),
)

# Project-type segmentation toggle for A7, mirrors the E6 toggle. When on,
# the (ITEM_TYPE, QTY_UOM) segment key is extended with a composite
# ``(E05_DEPARTMENT, BUSINESS)`` tuple looked up from the Planview reference
# (``VWS_GP_STANDARD_SHARE``) via ``PLANVIEW_ID → PROJECT_ID``. The IQR is
# then recomputed *within each* ``(ITEM_TYPE, QTY_UOM, E05_DEPARTMENT,
# BUSINESS)`` segment so a deepwater FPSO is not pooled with an onshore
# refinery when checking hours-per-quantity within a discipline. Off by
# default, the rule keeps its (ITEM_TYPE, QTY_UOM)-only behaviour unless
# the user opts in. Rows whose segment cannot be resolved (missing
# PLANVIEW_ID, unmatched PROJECT_ID, null/blank E05_DEPARTMENT / BUSINESS)
# are NOT_APPLICABLE → PASS so the toggle never double-penalises the
# referential-integrity gap A2 / blocking A1 already cover.
ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM = "segment_by_project_type"
ADR_A7_SEGMENT_REFERENCE = {
    "reference_dataset": "VWS_GP_STANDARD_SHARE",
    "source_column": "PLANVIEW_ID",       # in ADR
    "reference_column": "PROJECT_ID",     # in VWS_GP_STANDARD_SHARE
    "segment_columns": ("E05_DEPARTMENT", "BUSINESS"),
}
# Extra column the rule needs when segmentation is on. Step 4.2 folds this
# into the CDE-coverage validation via ``required_columns_when_enabled``
# (see CustomRuleOption) so the user is told to add PLANVIEW_ID to CDEs
# when the toggle is enabled.
ADR_A7_SEGMENT_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
}

# A8: Cross-discipline quantity ratios.
#
# Project-level statistical rule with row-level verdict. Each project
# (``ROOT_ITEM_NAME``) aggregates positive quantities by discipline
# category, computes cross-discipline ratios, and is judged against the
# population of the same ratio across all projects. Every row of a
# project that fails any of its applicable ratios inherits the FAIL -
# same row-level / group-verdict pattern as E6.
#
# Source columns after prefixing on the denormalized data product:
#   - ``ITEM_TYPE``      - pass-through from the primary item table.
#   - ``ROOT_ITEM_NAME`` - pass-through, the project / scope key.
#   - ``QTY_QUANTITY``   - SUM of QUANTITY (from QTY results).
#   - ``QTY_UOM``        - first UOM seen per ROW_ID (mock: stable per
#     parent; production: ``MAX(QTY_UOM)`` per the SQL spec).
ADR_A8_REQUIRED_COLUMNS = {
    "Item Type": "ITEM_TYPE",
    "Root Item Name": "ROOT_ITEM_NAME",
    "Quantity": "QTY_QUANTITY",
    "Quantity UOM": "QTY_UOM",
}

ADR_A8_MILD_IQR_MULTIPLIER = 1.5
ADR_A8_EXTREME_IQR_MULTIPLIER = 3.0
# Minimum number of projects with a calculable ratio required before
# IQR thresholds are derived for that ratio. Below this the ratio is
# NOT_APPLICABLE for every project - too small a population to define
# an outlier reliably (mirrors A7 / E6 conventions).
ADR_A8_MIN_POPULATION = 10

# IQR-multiplier threshold customization for A8. Step 4.2 UI exposes the
# choices below as a selectbox; check_adr_a8 reads
# ``params[ADR_A8_THRESHOLD_PARAM]`` and falls back to
# ``ADR_A8_MILD_IQR_MULTIPLIER`` (1.5×) when the param is absent.
ADR_A8_THRESHOLD_PARAM = "threshold_iqr_multiplier"
ADR_A8_THRESHOLD_CHOICES: Tuple[Tuple[float, str], ...] = (
    (1.5, "Mild (1.5×IQR) - recommended"),
    (2.0, "Moderate (2.0×IQR)"),
    (3.0, "Extreme (3.0×IQR) - lenient"),
)

# Project-type segmentation toggle for A8, mirrors the E6 / A7 toggle.
# When on, the cross-discipline ratio population (one ratio value per
# ``ROOT_ITEM_NAME``) is partitioned by the composite
# ``(E05_DEPARTMENT, BUSINESS)`` tuple looked up from
# ``VWS_GP_STANDARD_SHARE`` via ``PLANVIEW_ID → PROJECT_ID``. The IQR is
# recomputed *within each segment* so a deepwater FPSO is not pooled with
# an onshore refinery when judging cross-discipline shape. The per-segment
# minimum-population floor (``ADR_A8_MIN_POPULATION``) still applies.
# Off by default, the rule keeps its global-IQR behaviour unless the user
# opts in. Projects whose segment cannot be resolved (no associated
# PLANVIEW_ID, unmatched PROJECT_ID, null/blank E05_DEPARTMENT / BUSINESS)
# are NOT_APPLICABLE → PASS so the toggle never double-penalises the
# referential-integrity gap A1 / A2 already cover.
ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM = "segment_by_project_type"
ADR_A8_SEGMENT_REFERENCE = {
    "reference_dataset": "VWS_GP_STANDARD_SHARE",
    "source_column": "PLANVIEW_ID",       # in ADR
    "reference_column": "PROJECT_ID",     # in VWS_GP_STANDARD_SHARE
    "segment_columns": ("E05_DEPARTMENT", "BUSINESS"),
}
# Extra column the rule needs when segmentation is on. Step 4.2 folds this
# into the CDE-coverage validation via ``required_columns_when_enabled``
# (see CustomRuleOption) so the user is told to add PLANVIEW_ID to CDEs
# when the toggle is enabled.
ADR_A8_SEGMENT_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
}

# UOM aliases, the mock and the spec use slightly different spellings
# for the same physical unit (CY ↔ yd³, T ↔ t, M ↔ m, FT ↔ ft). Lowering
# + alias mapping makes the classifier resilient to both conventions
# without rewriting the source data.
_A8_UOM_ALIASES: Dict[str, str] = {
    "cy": "yd³",
    "yds³": "yd³",
    "yd^3": "yd³",
    "m^3": "m³",
    "ft^3": "ft³",
    "m^2": "m²",
    "ft^2": "ft²",
}

# UOM sets used by the discipline classifier (post-normalisation).
_A8_LENGTH_UOMS = frozenset({"ft", "m"})
_A8_WEIGHT_UOMS = frozenset({"t", "t,sht"})
_A8_VOLUME_UOMS = frozenset({"yd³", "m³"})
# UOMs that disqualify a row from EQUIPMENT_COUNT - anything that
# represents length, area, volume, weight, or a known equipment
# subcomponent should not be counted as a major-equipment unit.
_A8_EQUIPMENT_EXCLUDED_UOMS = frozenset({
    "ft", "m", "ft²", "m²", "ft³", "m³", "yd³",
    "t", "t,sht", "lb", "kg",
    "nozzles", "manways", "tubes", "trays",
    "shells", "burners", "supports", "baffles",
})
# ITEM_TYPE values that count as "major equipment" for A8's
# EQUIPMENT_COUNT category. Mirrors the production "Estimate*" labels
# enumerated in the rule spec §9.2.
_A8_EQUIPMENT_ITEM_TYPES = frozenset({
    "EstimatePump",
    "EstimateElectricMotor",
    "EstimateCentrifugalCompressor",
    "EstimateReciprocatingCompressor",
    "EstimateGasTurbine",
    "EstimateSteamTurbine",
    "EstimateVerticalPressureVessel",
    "EstimateHorizontalDrum",
    "EstimateShellAndTubeExchanger",
    "EstimatePlateExchanger",
    "EstimateHairpinExchanger",
    "EstimateAirCooledExchanger",
    "EstimateTankage",
    "EstimateFurnace",
})
# Instrument count UOMs used by TRANSMITTER_COUNT classification.
# Lowercased for membership test against normalised UOMs.
_A8_TRANSMITTER_COUNT_UOMS = frozenset({
    "temperature transmitters",
    "electronic pressure transmitters",
    "electronic differential pressure transmitters",
    "pressure gauges",
    "thermowells",
    "thermocouples",
    "control valves",
    "flow elements",
    "level gauges",
    "level switches",
    "pressure switches",
    "junction boxes",
    "i/p transducers",
    "solenoid valves",
})

# Cross-discipline ratios. Each entry is
# ``ratio_name → (numerator_category, denominator_category)``. Adding a
# new ratio is a one-line change here once the underlying categories
# are produced by ``_classify_a8``.
_A8_RATIOS: Dict[str, Tuple[str, str]] = {
    "PIPE_LENGTH_PER_EQUIPMENT_COUNT": ("PIPE_LENGTH", "EQUIPMENT_COUNT"),
    "CABLE_LENGTH_PER_TRANSMITTER_COUNT": ("CABLE_LENGTH", "TRANSMITTER_COUNT"),
    "STEEL_WEIGHT_PER_CONCRETE_VOLUME": ("STEEL_WEIGHT", "CONCRETE_VOLUME"),
}


def _classify_a8_category(item_type: object, qty_uom: object) -> object:
    """Classify a single (``ITEM_TYPE``, ``QTY_UOM``) pair into one of
    A8's six discipline categories, or ``None`` when the row is not
    eligible for any ratio.

    Categories are checked in priority order so overlapping name patterns
    resolve cleanly, e.g. ``EstimatePiperack + t`` is STEEL_WEIGHT (not
    PIPE_LENGTH) because the weight UOM filter wins, and
    ``EstimateFieldInstrumentGroup + ft`` is CABLE_LENGTH (not
    TRANSMITTER_COUNT) because the length UOM is more specific than the
    count fallback.
    """
    if item_type is None or qty_uom is None:
        return None
    it = str(item_type).strip()
    raw_uom = str(qty_uom).strip().lower()
    if not it or not raw_uom:
        return None
    uom = _A8_UOM_ALIASES.get(raw_uom, raw_uom)

    # STEEL_WEIGHT - Piperack matches "Pipe", so the weight UOM filter
    # has to be checked first to keep "Piperack + t" out of PIPE_LENGTH.
    if ("SteelStructure" in it or "Piperack" in it) and uom in _A8_WEIGHT_UOMS:
        return "STEEL_WEIGHT"

    if (
        ("Foundation" in it or "Concrete" in it)
        and uom in _A8_VOLUME_UOMS
    ):
        return "CONCRETE_VOLUME"

    if ("Piping" in it or "Pipe" in it) and uom in _A8_LENGTH_UOMS:
        return "PIPE_LENGTH"

    if (
        ("Electrical" in it or "FieldInstrument" in it)
        and uom in _A8_LENGTH_UOMS
    ):
        return "CABLE_LENGTH"

    if "FieldInstrument" in it and uom in _A8_TRANSMITTER_COUNT_UOMS:
        return "TRANSMITTER_COUNT"

    if (
        it in _A8_EQUIPMENT_ITEM_TYPES
        and uom not in _A8_EQUIPMENT_EXCLUDED_UOMS
    ):
        return "EQUIPMENT_COUNT"

    return None


def _a1_value_valid(s: pd.Series) -> pd.Series:
    """A resolved ``ISO_COR`` / ``SAB`` value is valid when it is non-null,
    non-blank, and contains neither ``ERROR`` nor ``N/A`` (case-insensitive).

    Used by both the per-row validity test and by the COA-master "best
    available" sort: the master may have multiple rows per ICARUS_COA, so
    we sort invalid rows after valid rows before deduplicating.
    """
    filled = _is_filled(s)
    str_lower = s.astype(object).astype(str).str.lower()
    has_error = str_lower.str.contains("error", regex=False, na=False)
    has_na = str_lower.str.contains("n/a", regex=False, na=False)
    return filled & ~has_error & ~has_na


def _resolve_coa_master_lookups(
    reference_df: pd.DataFrame,
) -> Tuple[pd.Series, pd.Series]:
    """Build the per-``ICARUS_COA`` ``(ISO_COR, SAB)`` lookups used by A1
    and A3.

    The COA master may carry several rows per ``ICARUS_COA`` (one per
    detailed sub-code). The two lookups mirror the SQL spec's
    ``FIRST_VALUE(...) ORDER BY IFF(invalid, 1, 0)`` semantics: invalid
    rows are stable-sorted *after* valid rows, then ``drop_duplicates``
    keeps the first row per group, so a valid mapping wins over an
    ``ERROR`` / ``NULL`` mapping when both exist for the same COA, and
    the resolved value falls back to whatever invalid string is left
    only when no valid one exists (so the validity check downstream
    fails with the actual marker rather than silently passing).

    Both lookups are computed independently - a COA group whose
    ``ISO_COR`` is valid but ``SAB`` is ``ERROR`` still resolves to
    a valid ISO_COR + an invalid SAB.
    """
    ref = reference_df.copy()
    ref["ICARUS_COA"] = (
        ref["ICARUS_COA"].astype(object).astype(str).str.strip()
    )
    ref = ref[ref["ICARUS_COA"] != ""]

    iso_invalid_flag = (~_a1_value_valid(ref["ISO_COR"])).astype(int)
    sab_invalid_flag = (~_a1_value_valid(ref["SAB"])).astype(int)

    iso_lookup = (
        ref.assign(_invalid=iso_invalid_flag.values)
        .sort_values(["ICARUS_COA", "_invalid"], kind="stable")
        .drop_duplicates(subset="ICARUS_COA", keep="first")
        .set_index("ICARUS_COA")["ISO_COR"]
    )
    sab_lookup = (
        ref.assign(_invalid=sab_invalid_flag.values)
        .sort_values(["ICARUS_COA", "_invalid"], kind="stable")
        .drop_duplicates(subset="ICARUS_COA", keep="first")
        .set_index("ICARUS_COA")["SAB"]
    )
    return iso_lookup, sab_lookup


def check_adr_a1(df: pd.DataFrame) -> pd.Series:
    """A1: ISO Code of Account Present (COR + SAB) for ADR.

    Each ADR row carries a Work Breakdown Code in ``COMPLETE_WBC``. The
    rule extracts the leading dot-separated segment (the ICARUS Code of
    Account group), joins it to the ``ACCE_COA_MASTER`` reference table,
    and checks that the resolved ``ISO_COR`` and ``SAB`` are both valid
    (non-null, non-blank, no ``ERROR`` / ``N/A`` markers).

    Row passes when **all three** hold:

    1. ``COMPLETE_WBC`` is non-null and non-blank.
    2. The derived COA group resolves to a valid ``ISO_COR`` in the
       master.
    3. The same COA group resolves to a valid ``SAB`` in the master.

    The master may carry multiple rows per ``ICARUS_COA`` (for sub-codes);
    the rule mirrors the SQL spec by sorting invalid rows after valid
    rows before deduplicating, so each COA group's ``ISO_COR`` / ``SAB``
    is the best available value.

    Raises :class:`CustomRuleNotEvaluated` when the reference dataset is
    unavailable, so the rule never silently passes when the join target
    is missing.
    """
    from src.reference_data import (
        get_reference_dataset,
        get_reference_dataset_error,
    )

    if "COMPLETE_WBC" not in df.columns or "PLANVIEW_ID" not in df.columns:
        return pd.Series(False, index=df.index)

    ref_name = ADR_A1_REFERENCE["reference_dataset"]
    reference_df = get_reference_dataset(ref_name)
    if reference_df is None:
        cached_error = get_reference_dataset_error(ref_name)
        detail = f": {cached_error}" if cached_error else ""
        raise CustomRuleNotEvaluated(
            f"ADR A1: '{ref_name}' reference dataset is unavailable{detail}; "
            "ISO_COR / SAB linkage cannot be validated."
        )

    if (
        "ICARUS_COA" not in reference_df.columns
        or "ISO_COR" not in reference_df.columns
        or "SAB" not in reference_df.columns
    ):
        return pd.Series(False, index=df.index)

    # COA group from COMPLETE_WBC = first dot-separated segment (trimmed).
    wbc = df["COMPLETE_WBC"]
    wbc_filled = _is_filled(wbc)
    coa_group = (
        wbc.astype(object).astype(str).str.strip()
        .str.split(".", n=1).str[0]
    )

    iso_lookup, sab_lookup = _resolve_coa_master_lookups(reference_df)

    iso_resolved = coa_group.map(iso_lookup)
    sab_resolved = coa_group.map(sab_lookup)

    iso_ok = _a1_value_valid(iso_resolved)
    sab_ok = _a1_value_valid(sab_resolved)
    return wbc_filled & iso_ok & sab_ok


def check_adr_a2(df: pd.DataFrame) -> pd.Series:
    """A2: Location + Estimate Date Present & Valid (ADR).

    Mirrors EPT E2 against the ADR data product. Row passes when *all* hold:
    - ``COST_UPDATE`` (estimate basis date, in ADR) is non-null/non-blank
      (**Completeness**).
    - ``COST_UPDATE`` matches the fiscal quarter-year shape ``[1-4]Q\\d{4}``
      (e.g. ``"2Q2019"``, **Validity**); a populated-but-malformed value
      (e.g. ``"N/A"``, ``"2019"``, ``"5Q2019"``) fails the rule even though
      it satisfies completeness.
    - ``COUNTRY`` (project location) is non-null/non-blank in the Planview
      reference after joining ADR.PLANVIEW_ID = VWS_GP_STANDARD_SHARE.PROJECT_ID.
      An unmatched PLANVIEW_ID is treated as a missing COUNTRY.

    Raises :class:`CustomRuleNotEvaluated` when the reference dataset is
    unavailable, so the rule never silently passes when the join target is
    missing.
    """
    from src.reference_data import (
        get_reference_dataset,
        get_reference_dataset_error,
    )

    if "COST_UPDATE" not in df.columns or "PLANVIEW_ID" not in df.columns:
        return pd.Series(False, index=df.index)

    ref_name = ADR_A2_REFERENCE["reference_dataset"]
    reference_df = get_reference_dataset(ref_name)
    if reference_df is None:
        cached_error = get_reference_dataset_error(ref_name)
        detail = f": {cached_error}" if cached_error else ""
        raise CustomRuleNotEvaluated(
            f"ADR A2: '{ref_name}' reference dataset is unavailable{detail}; "
            "COUNTRY linkage cannot be validated."
        )

    # Completeness: the estimate basis date is populated (non-null/non-blank).
    cost_update_filled = _is_filled(df["COST_UPDATE"])
    # Validity: the populated value matches the fiscal quarter-year shape
    # (e.g. "2Q2019"). A filled but malformed value (e.g. "N/A", "2019",
    # "5Q2019") fails Validity even though it satisfies Completeness.
    cost_update_valid = (
        df["COST_UPDATE"]
        .astype(str)
        .str.strip()
        .str.fullmatch(ADR_A2_DATE_PATTERN, case=False)
        .fillna(False)
    )
    cost_update_ok = cost_update_filled & cost_update_valid

    ref_col = ADR_A2_REFERENCE["reference_column"]
    lookup_col = ADR_A2_REFERENCE["lookup_column"]
    if ref_col not in reference_df.columns or lookup_col not in reference_df.columns:
        return pd.Series(False, index=df.index)

    ref = (
        reference_df[[ref_col, lookup_col]]
        .dropna(subset=[ref_col])
        .drop_duplicates(subset=[ref_col])
    )
    lookup = dict(zip(ref[ref_col].astype(str).str.strip(), ref[lookup_col]))

    matched_country = (
        df["PLANVIEW_ID"].astype(str).str.strip().map(lookup)
    )
    country_ok = _is_filled(matched_country)
    return cost_update_ok & country_ok


def check_adr_a3(
    df: pd.DataFrame, params: ADRA3Params | None = None
) -> pd.Series:
    """A3: Statistical WBC-to-ISO mapping ratio (ADR).

    Mapping-quality statistical rule with row-level verdict. For each
    row the rule resolves ``ISO_COR`` and ``SAB`` from the COA master
    (same lookup as A1). Eligible rows - ``COMPLETE_WBC`` filled AND a
    valid ISO mapping - are grouped by ``(ISO_COR, SAB)`` and the
    metric ``WBC_TO_ISO_RATIO = COUNT(DISTINCT COMPLETE_WBC)`` is
    computed per bucket.

    A bucket **fails** when its ratio is strictly greater than the
    global ``P90`` of WBC-to-ISO ratios across all eligible mappings
    AND the bucket is *material* (``SUM(COST_TOTAL_HOURS) > 0`` OR
    ``SUM(COST_TOTAL_COST) >= ADR_A3_MATERIALITY_USD``). Every row in a
    failing bucket inherits the FAIL.

    Rows whose WBC does not resolve to a valid ISO mapping are PASS -
    A1 already covers the WBC / COR / SAB completeness gap, and A3
    must not double-penalise the same row.

    NOT_APPLICABLE → PASS for:

    - WBC missing or unmapped - A1's territory.
    - Resolved ``ISO_COR`` / ``SAB`` invalid (null / blank / `ERROR` /
      `N/A`) - A1's territory.
    - Eligible-mapping population below
      :data:`ADR_A3_MIN_MAPPING_POPULATION` - too small to derive a P90.
    - Bucket not material.

    ``params[ADR_A3_PROJECT_SCOPED_PARAM]`` (bool, default False) switches
    the percentile baseline:

    - **False**: global scope (default): one P90 across every eligible
      ISO mapping in the dataset.
    - **True**: project scope: the group key becomes
      ``(PLANVIEW_ID, ISO_COR, SAB)`` and the P90 is recomputed within
      each ``PLANVIEW_ID`` partition. Every project is therefore judged
      against its own peers, which is the right framing when projects
      differ in maturity / WBC discipline. Rows lacking ``PLANVIEW_ID``
      are treated as PASS (A2 already covers the missing-project
      linkage).

    ``params[ADR_A3_THRESHOLD_PARAM]`` (float in (0, 1], default
    :data:`ADR_A3_PERCENTILE` = 0.90) customizes the percentile threshold, see :data:`ADR_A3_THRESHOLD_CHOICES` for the values surfaced in Step 4.2.

    ``params[ADR_A3_DETECT_UNIFORM_MAPPING_PARAM]`` (bool, default False)
    layers a uniform-1:1 detector on top of the percentile fail: when on,
    any material bucket whose ratio equals 1 also fails. Off by default so
    existing scorecards stay stable.

    Raises :class:`CustomRuleNotEvaluated` when the COA master is
    unavailable so the rule never silently passes when its dependency
    is missing.
    """
    p = params or {}
    project_scoped = p.get(ADR_A3_PROJECT_SCOPED_PARAM, False)
    detect_uniform = p.get(ADR_A3_DETECT_UNIFORM_MAPPING_PARAM, False)
    percentile = _coerce_threshold(
        p.get(ADR_A3_THRESHOLD_PARAM), ADR_A3_PERCENTILE
    )
    required = list(ADR_A3_REQUIRED_COLUMNS.values())
    if project_scoped:
        required = required + list(
            ADR_A3_PROJECT_SCOPED_REQUIRED_COLUMNS.values()
        )
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    from src.reference_data import (
        get_reference_dataset,
        get_reference_dataset_error,
    )

    ref_name = ADR_A3_REFERENCE["reference_dataset"]
    reference_df = get_reference_dataset(ref_name)
    if reference_df is None:
        cached_error = get_reference_dataset_error(ref_name)
        detail = f": {cached_error}" if cached_error else ""
        raise CustomRuleNotEvaluated(
            f"ADR A3: '{ref_name}' reference dataset is unavailable{detail}; "
            "ISO_COR / SAB cannot be resolved."
        )

    if (
        "ICARUS_COA" not in reference_df.columns
        or "ISO_COR" not in reference_df.columns
        or "SAB" not in reference_df.columns
    ):
        return pd.Series(False, index=df.index)

    iso_lookup, sab_lookup = _resolve_coa_master_lookups(reference_df)

    wbc = df["COMPLETE_WBC"]
    wbc_filled = _is_filled(wbc)
    coa_group = (
        wbc.astype(object).astype(str).str.strip()
        .str.split(".", n=1).str[0]
    )
    iso_resolved = coa_group.map(iso_lookup)
    sab_resolved = coa_group.map(sab_lookup)
    has_valid_mapping = (
        wbc_filled
        & _a1_value_valid(iso_resolved)
        & _a1_value_valid(sab_resolved)
    )
    if project_scoped:
        # In project scope, rows lacking PLANVIEW_ID can't be assigned to a
        # project; they pass A3 (A2 already covers the missing-project gap)
        # mirroring E3's project-scope handling.
        has_valid_mapping &= _is_filled(df["PLANVIEW_ID"])
    if not has_valid_mapping.any():
        return pd.Series(True, index=df.index)

    hours = pd.to_numeric(df["COST_TOTAL_HOURS"], errors="coerce").fillna(0.0)
    cost = pd.to_numeric(df["COST_TOTAL_COST"], errors="coerce").fillna(0.0)
    wbc_norm = wbc.astype(object).astype(str).str.strip()

    iso_norm = iso_resolved.astype(object).astype(str).str.strip()
    sab_norm = sab_resolved.astype(object).astype(str).str.strip()
    if project_scoped:
        pv_norm = df["PLANVIEW_ID"].astype(object).astype(str).str.strip()
        group_id = pd.Series(
            list(zip(pv_norm, iso_norm, sab_norm)),
            index=df.index,
            dtype=object,
        )
    else:
        group_id = pd.Series(
            list(zip(iso_norm, sab_norm)), index=df.index, dtype=object
        )
    group_id = group_id.where(has_valid_mapping)

    eligible_idx = df.index[has_valid_mapping]
    work = pd.DataFrame({
        "_gid": group_id.loc[eligible_idx],
        "_wbc": wbc_norm.loc[eligible_idx],
        "_hours": hours.loc[eligible_idx],
        "_cost": cost.loc[eligible_idx],
    })

    grouped = work.groupby("_gid", dropna=True, sort=False)
    metrics = pd.DataFrame({
        "ratio": grouped["_wbc"].nunique(dropna=True),
        "hours_sum": grouped["_hours"].sum(),
        "cost_sum": grouped["_cost"].sum(),
    })
    eligible_groups = metrics["ratio"] >= 1
    if eligible_groups.sum() < ADR_A3_MIN_MAPPING_POPULATION:
        # Population too small to define a meaningful P90, every row
        # passes, mirroring the spec's "insufficient population" branch.
        # In project scope the same floor applies to the *total* number of
        # eligible buckets so a sparse run doesn't synthesise outliers from
        # tiny per-project distributions.
        return pd.Series(True, index=df.index)

    if project_scoped:
        # Recompute P90 within each PLANVIEW_ID partition so projects with
        # genuinely fine-grained WBC discipline aren't dragged down by
        # peers that aggregate aggressively, same construction as E3.
        planview_keys = pd.Index(
            [gid[0] for gid in metrics.index], name="planview"
        )
        ratios_by_pv = (
            metrics.loc[eligible_groups, "ratio"]
            .groupby(planview_keys[eligible_groups], sort=False)
        )
        p90_by_pv = ratios_by_pv.quantile(percentile)
        applicable_p90 = planview_keys.map(p90_by_pv).to_numpy()
    else:
        global_p90 = float(
            metrics.loc[eligible_groups, "ratio"].quantile(percentile)
        )
        applicable_p90 = pd.Series(
            global_p90, index=metrics.index
        ).to_numpy()

    metrics["material"] = (
        (metrics["hours_sum"] > 0)
        | (metrics["cost_sum"] >= ADR_A3_MATERIALITY_USD)
    )
    outlier_fail = (
        (metrics["ratio"].to_numpy() > applicable_p90)
        & metrics["material"].to_numpy()
    )
    if detect_uniform:
        # Suspiciously uniform 1:1 buckets, each ISO bucket holds exactly
        # one distinct COMPLETE_WBC. OR'd with the percentile fail so both
        # signals coexist when the user opts in; materiality still gates
        # both branches to keep planning / structural-only rows out.
        uniform_fail = (
            (metrics["ratio"].to_numpy() == 1)
            & metrics["material"].to_numpy()
        )
        metrics["fail"] = outlier_fail | uniform_fail
    else:
        metrics["fail"] = outlier_fail

    fail_lookup = metrics["fail"].to_dict()
    row_fail = (
        group_id.map(fail_lookup)
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )
    return ~row_fail


def _classify_a4_scope(item_type: object, item_description: object) -> set:
    """Return the set of A4 core quantity types implied by an item's
    ``ITEM_TYPE`` and ``ITEM_DESCRIPTION`` *alone*, i.e. before
    looking at QTY_UOM or QUANTITY. Used to compute the project-level
    ``EXPECTS_*`` flags."""
    scopes: set = set()
    it = "" if item_type is None else str(item_type).strip()
    desc = "" if item_description is None else str(item_description).strip()
    if not it and not desc:
        return scopes

    if it in _A4_PIPING_ITEM_TYPES:
        scopes.add("PIPING_LF")
    if "SteelStructure" in it or "Piperack" in it:
        scopes.add("STEEL_TONS")
    if "Foundation" in it or "Concrete" in it:
        scopes.add("CONCRETE_CY")
    if "Electrical" in it:
        scopes.add("CABLE_LENGTH")
    if "FieldInstrument" in it:
        scopes.add("TRANSMITTER_COUNT")
    if it in _A4_EQUIPMENT_ITEM_TYPES:
        scopes.add("EQUIPMENT_COUNT")
    if (
        "Module" in it or "Modular" in it
        or "Module" in desc or "Modular" in desc
    ):
        scopes.add("MODULE_COUNT")
    return scopes


def _classify_a4_quantity(
    item_type: object, qty_uom: object, item_description: object
) -> object:
    """Classify a single (``ITEM_TYPE``, ``QTY_UOM``, ``ITEM_DESCRIPTION``)
    triple into one of A4's seven core quantity types, or ``None`` when
    the row does not satisfy any of the documented patterns. Called only
    for rows whose quantity is positive (caller checks).
    """
    if item_type is None or qty_uom is None:
        return None
    it = str(item_type).strip()
    raw_uom = str(qty_uom).strip()
    if not it or not raw_uom:
        return None
    uom_lower = raw_uom.lower()
    uom_norm = _A8_UOM_ALIASES.get(uom_lower, uom_lower)

    if it in _A4_PIPING_ITEM_TYPES and uom_norm in _A4_LENGTH_UOMS:
        return "PIPING_LF"

    if (
        ("SteelStructure" in it or "Piperack" in it)
        and uom_norm in _A4_WEIGHT_UOMS
    ):
        return "STEEL_TONS"

    if (
        ("Foundation" in it or "Concrete" in it)
        and uom_norm in _A4_VOLUME_UOMS
    ):
        return "CONCRETE_CY"

    if "Electrical" in it and uom_norm in _A4_LENGTH_UOMS:
        return "CABLE_LENGTH"

    if "FieldInstrument" in it and uom_lower in _A4_TRANSMITTER_UOMS:
        return "TRANSMITTER_COUNT"

    if (it, uom_lower) in _A4_EQUIPMENT_PAIRS:
        return "EQUIPMENT_COUNT"

    desc = "" if item_description is None else str(item_description).strip()
    is_module = (
        "Module" in it or "Modular" in it
        or "Module" in desc or "Modular" in desc
    )
    if is_module and uom_lower in _A4_MODULE_UOMS:
        return "MODULE_COUNT"

    return None


def check_adr_a4(df: pd.DataFrame) -> pd.Series:
    """A4: Core quantities populated (ADR).

    Project-level Completeness rule with row-level verdict. For each
    ``PLANVIEW_ID`` the rule:

    1. determines the project's *expected* core quantity types from the
       per-row scope classification (``ITEM_TYPE`` + ``ITEM_DESCRIPTION``);
    2. determines the project's *populated* core quantity types from
       the per-row quantity classification (positive ``QTY_QUANTITY``
       AND a matching (``ITEM_TYPE``, ``QTY_UOM``) pattern);
    3. flags the project when any expected type lacks a populated row;
    4. flags the project when its total ``QTY_QUANTITY`` sums to a
       *negative* value. Individual rows may legitimately carry negative
       quantities (corrections / reversals), but a project-wide negative
       total is non-physical. Row-level negatives are *not* failed on
       their own - only the project aggregate is.

    Row-level verdict: a row **fails** iff its ``PLANVIEW_ID`` is
    flagged. Rows whose project is unknown (null/blank ``PLANVIEW_ID``)
    pass, they cannot be assigned to a project group.

    Schema-level missing column → all rows fail (same convention as the
    other custom rules).
    """
    required = list(ADR_A4_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    pv = df["PLANVIEW_ID"]
    project_filled = _is_filled(pv)
    if not project_filled.any():
        return pd.Series(True, index=df.index)

    pv_norm = pv.astype(object).astype(str).str.strip().where(project_filled)
    qty = pd.to_numeric(df["QTY_QUANTITY"], errors="coerce").fillna(0.0)
    item_type_str = df["ITEM_TYPE"].astype(object).astype(str).str.strip()
    item_desc_str = df["ITEM_DESCRIPTION"].astype(object).astype(str).str.strip()
    uom_raw = df["QTY_UOM"].astype(object).astype(str).str.strip()
    uom_lower = uom_raw.str.lower()
    uom_norm = uom_lower.map(_A8_UOM_ALIASES).fillna(uom_lower)

    qty_pos = qty > 0

    # Scope detection - independent per category.
    is_piping = item_type_str.isin(_A4_PIPING_ITEM_TYPES)
    is_steel = (
        item_type_str.str.contains("SteelStructure", regex=False, na=False)
        | item_type_str.str.contains("Piperack", regex=False, na=False)
    )
    is_concrete = (
        item_type_str.str.contains("Foundation", regex=False, na=False)
        | item_type_str.str.contains("Concrete", regex=False, na=False)
    )
    is_cable = item_type_str.str.contains("Electrical", regex=False, na=False)
    is_transmitter = item_type_str.str.contains(
        "FieldInstrument", regex=False, na=False
    )
    is_equipment_type = item_type_str.isin(_A4_EQUIPMENT_ITEM_TYPES)
    is_module = (
        item_type_str.str.contains("Module", regex=False, na=False)
        | item_type_str.str.contains("Modular", regex=False, na=False)
        | item_desc_str.str.contains("Module", regex=False, na=False)
        | item_desc_str.str.contains("Modular", regex=False, na=False)
    )

    # Population detection - qty must be positive AND the row's
    # (item_type, uom) pattern matches the category's classification.
    has_piping = qty_pos & is_piping & uom_norm.isin(_A4_LENGTH_UOMS)
    has_steel = qty_pos & is_steel & uom_norm.isin(_A4_WEIGHT_UOMS)
    has_concrete = qty_pos & is_concrete & uom_norm.isin(_A4_VOLUME_UOMS)
    has_cable = qty_pos & is_cable & uom_norm.isin(_A4_LENGTH_UOMS)
    has_transmitter = qty_pos & is_transmitter & uom_lower.isin(
        _A4_TRANSMITTER_UOMS
    )
    pair_series = pd.Series(
        list(zip(item_type_str.tolist(), uom_lower.tolist())),
        index=df.index,
        dtype=object,
    )
    has_equipment = qty_pos & pair_series.isin(_A4_EQUIPMENT_PAIRS)
    has_module = qty_pos & is_module & uom_lower.isin(_A4_MODULE_UOMS)

    flags = pd.DataFrame({
        "_pv": pv_norm,
        "_qty": qty,
        "ep": is_piping, "hp": has_piping,
        "es": is_steel, "hs": has_steel,
        "ec": is_concrete, "hc": has_concrete,
        "ecbl": is_cable, "hcbl": has_cable,
        "et": is_transmitter, "ht": has_transmitter,
        "eq": is_equipment_type, "hq": has_equipment,
        "em": is_module, "hm": has_module,
    }).dropna(subset=["_pv"])

    grouped = flags.groupby("_pv", dropna=True, sort=False)
    _bool_cols = [
        "ep", "hp", "es", "hs", "ec", "hc", "ecbl", "hcbl",
        "et", "ht", "eq", "hq", "em", "hm",
    ]
    proj = grouped[_bool_cols].any()
    # Project-level quantity sanity: individual rows may carry negative
    # quantities (corrections / reversals), but a project whose *total*
    # QTY_QUANTITY sums to a negative value is non-physical and fails.
    proj_qty_negative = grouped["_qty"].sum().reindex(proj.index) < 0
    project_fail = (
        (proj["ep"] & ~proj["hp"])
        | (proj["es"] & ~proj["hs"])
        | (proj["ec"] & ~proj["hc"])
        | (proj["ecbl"] & ~proj["hcbl"])
        | (proj["et"] & ~proj["ht"])
        | (proj["eq"] & ~proj["hq"])
        | (proj["em"] & ~proj["hm"])
        | proj_qty_negative
    )

    failing_projects = set(project_fail[project_fail].index)
    if not failing_projects:
        return pd.Series(True, index=df.index)

    in_failing = (
        pv_norm.isin(failing_projects).fillna(False).astype(bool)
    )
    return ~in_failing


def check_adr_a5(df: pd.DataFrame) -> pd.Series:
    """A5: Design details present when quantity exists (ADR).

    For each estimate item (one row per ``ROW_ID`` in the denormalized data
    product) the rule checks two derived flags:

    - ``HAS_QUANTITY``, the aggregated ``QTY_QUANTITY`` is non-null
      and not equal to zero. ``QTY_QUANTITY`` is the SUM of the underlying
      ``ADR_FACT_ESTIMATEQTYRESULTS.QUANTITY`` rows for the item, applied by
      :func:`src.data_product_builder.build_data_product`.
    - ``HAS_DESIGN_DETAIL``   - ``DESIGN_PARAMETER_VALUE`` is populated
      (non-null and non-blank).

    Pass / fail matrix:

    +--------------+-------------------+-------------+
    | HAS_QUANTITY | HAS_DESIGN_DETAIL | RULE_RESULT |
    +==============+===================+=============+
    |       0      |        0          |    PASS     |
    |       0      |        1          |    PASS     |
    |       1      |        0          |    FAIL     |
    |       1      |        1          |    PASS     |
    +--------------+-------------------+-------------+

    A row fails only when a non-zero quantity exists but the design parameter
    value is missing, the only configuration that prevents the quantity from
    being interpreted, normalized, or compared. Missing required column → all
    rows fail (structural incompleteness, same convention as the other custom
    rules).
    """
    required = list(ADR_A5_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    # NaN → 0 so a missing aggregated quantity is treated as "no quantity".
    # ``pd.to_numeric`` keeps the rule resilient if QTY_QUANTITY arrives as
    # an object-typed column from a heterogeneous source.
    qty = pd.to_numeric(df["QTY_QUANTITY"], errors="coerce").fillna(0.0)
    has_quantity = qty != 0
    has_design_detail = _is_filled(df["DESIGN_PARAMETER_VALUE"])
    return (~has_quantity) | has_design_detail


def check_adr_a6(df: pd.DataFrame) -> pd.Series:
    """A6: Construction hours present when quantity exists (ADR).

    For each estimate item (one row per ``ROW_ID`` in the denormalized data
    product) the rule checks two derived flags:

    - ``HAS_QUANTITY``, the aggregated ``QTY_QUANTITY`` is
      non-null and not equal to zero (same definition as A5).
    - ``HAS_CONSTRUCTION_HOURS``  - at least one of the two hours
      aggregates (``COST_TOTAL_HOURS``, ``COST_DB_TOTAL_HOURS``) is
      strictly greater than zero. Null inputs are coerced to zero;
      negative aggregates do **not** count as hours present (per spec §12).

    Pass / fail matrix:

    +--------------+------------------------+-------------+
    | HAS_QUANTITY | HAS_CONSTRUCTION_HOURS | RULE_RESULT |
    +==============+========================+=============+
    |       0      |           0            |    PASS     |
    |       0      |           1            |    PASS     |
    |       1      |           0            |    FAIL     |
    |       1      |           1            |    PASS     |
    +--------------+------------------------+-------------+

    The rule is **one-directional**: hours without a quantity is allowed
    (PASS). Only quantity-without-hours fails. Missing required column →
    all rows fail (structural incompleteness, same convention as the other
    custom rules).
    """
    required = list(ADR_A6_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    qty = pd.to_numeric(df["QTY_QUANTITY"], errors="coerce").fillna(0.0)
    total_hours = pd.to_numeric(
        df["COST_TOTAL_HOURS"], errors="coerce"
    ).fillna(0.0)
    db_total_hours = pd.to_numeric(
        df["COST_DB_TOTAL_HOURS"], errors="coerce"
    ).fillna(0.0)

    has_quantity = qty != 0
    # Spec §8: hours present only when *strictly* > 0; negatives do not
    # count, so we cannot use ``!= 0`` here.
    has_construction_hours = (total_hours > 0) | (db_total_hours > 0)
    return (~has_quantity) | has_construction_hours


def check_adr_a7(
    df: pd.DataFrame, params: ADRA7Params | None = None
) -> pd.Series:
    """A7: Within-discipline quantity / hour ratio outlier detection.

    Statistical rule with row-level verdict. Eligible rows (``QTY_QUANTITY > 0``
    and ``COST_TOTAL_HOURS > 0`` with both ``ITEM_TYPE`` and ``QTY_UOM``
    populated) compute ``HOURS_PER_QUANTITY = COST_TOTAL_HOURS / QTY_QUANTITY``.
    The eligible population is partitioned by ``(ITEM_TYPE, QTY_UOM)`` and IQR
    bounds are derived per segment:

    - ``Q1 = quantile(0.25)``, ``Q3 = quantile(0.75)``, ``IQR = Q3 - Q1``.
    - ``MILD_LOWER = Q1 - 1.5 * IQR``, ``MILD_UPPER = Q3 + 1.5 * IQR``.

    A row **fails** when its ratio is below the mild lower bound or above
    the mild upper bound. Every other case is treated as PASS:

    - The ratio cannot be calculated (quantity or hours missing / zero /
      negative).
    - ``ITEM_TYPE`` or ``QTY_UOM`` is null/blank, no segment to compare to.
    - Segment population (eligible-row count) is below
      :data:`ADR_A7_MIN_POPULATION` - too small to define an outlier.
    - Segment ``IQR == 0``, no variation, every value is on the median;
      outlier detection is not meaningful.

    ``params[ADR_A7_THRESHOLD_PARAM]`` (float > 0, default
    :data:`ADR_A7_MILD_IQR_MULTIPLIER` = 1.5) customizes the IQR
    multiplier; larger values widen the PASS band, see
    :data:`ADR_A7_THRESHOLD_CHOICES` for the values surfaced in Step 4.2.

    ``params[ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM]`` (bool, default False)
    extends the segment key with a composite ``(E05_DEPARTMENT, BUSINESS)``
    tuple looked up from ``VWS_GP_STANDARD_SHARE`` via
    ``PLANVIEW_ID → PROJECT_ID`` (mirrors the E6 toggle). With it on the
    IQR is recomputed within each
    ``(ITEM_TYPE, QTY_UOM, E05_DEPARTMENT, BUSINESS)`` bucket so a
    deepwater FPSO is not pooled with an onshore refinery when judging
    within-discipline productivity. Segments below
    :data:`ADR_A7_MIN_POPULATION` remain NOT_APPLICABLE → PASS. Rows
    whose segment cannot be resolved (missing PLANVIEW_ID, unmatched
    PROJECT_ID, or null/blank ``E05_DEPARTMENT`` / ``BUSINESS``) are also
    NOT_APPLICABLE → PASS - A1 / A2 already cover the referential gap.
    Raises :class:`CustomRuleNotEvaluated` when the toggle is on and the
    reference dataset is unavailable.

    Schema-level missing columns make every row fail, mirroring the
    convention used by E1 / E3 / E6 / A5 / A6.
    """
    p = params or {}
    iqr_multiplier = _coerce_threshold(
        p.get(ADR_A7_THRESHOLD_PARAM),
        ADR_A7_MILD_IQR_MULTIPLIER,
    )
    segmented = p.get(ADR_A7_SEGMENT_BY_PROJECT_TYPE_PARAM, False)

    required = list(ADR_A7_REQUIRED_COLUMNS.values())
    if segmented:
        required = required + list(ADR_A7_SEGMENT_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    qty = pd.to_numeric(df["QTY_QUANTITY"], errors="coerce")
    hours = pd.to_numeric(df["COST_TOTAL_HOURS"], errors="coerce")
    item_type = df["ITEM_TYPE"]
    qty_uom = df["QTY_UOM"]

    # Eligibility: ratio is defined AND we have a segment to compare to.
    eligible = (
        (qty > 0)
        & (hours > 0)
        & _is_filled(item_type)
        & _is_filled(qty_uom)
    )
    if not eligible.any():
        return pd.Series(True, index=df.index)

    ratio = pd.Series(np.nan, index=df.index, dtype=float)
    ratio.loc[eligible] = (
        hours.loc[eligible].to_numpy() / qty.loc[eligible].to_numpy()
    )

    item_norm = item_type.astype(object).astype(str).str.strip()
    uom_norm = qty_uom.astype(object).astype(str).str.strip()

    # Build the per-row segment key as a *DataFrame* so the groupby below
    # can use pandas' C-fast multi-column path instead of grouping on a
    # Series of Python tuples. At ADR scale (~866k rows) the difference is
    # multiple seconds of CPU.
    gid_cols: List[str] = ["_item", "_uom"]
    gid_frame = pd.DataFrame(
        {"_item": item_norm, "_uom": uom_norm}, index=df.index
    )

    if segmented:
        # Extend the segment key with the project-type tuple resolved via
        # PLANVIEW_ID. Rows whose project-type cannot be resolved (missing
        # PLANVIEW_ID, unmatched PROJECT_ID, or null/blank segment columns)
        # become NOT_APPLICABLE → PASS, mirrors E6's unmatched-key
        # convention.
        #
        # The lookup is pre-cleaned by ``_resolve_planview_segment_map``
        # (null/blank dept/business already dropped, every value stripped),
        # so resolution becomes two vectorized ``Series.map`` calls plus
        # the ``notna()`` mask, no per-row pandas allocations, no
        # per-row ``_is_filled`` rebuilds.
        segment_lookup = _resolve_planview_segment_map(
            ADR_A7_SEGMENT_REFERENCE, "ADR A7"
        )
        dept_lookup = {k: v[0] for k, v in segment_lookup.items()}
        business_lookup = {k: v[1] for k, v in segment_lookup.items()}

        pv_filled = _is_filled(df["PLANVIEW_ID"])
        pv_key = (
            df["PLANVIEW_ID"]
            .astype(object).astype(str).str.strip()
            .where(pv_filled)
        )
        dept_seg = pv_key.map(dept_lookup)
        business_seg = pv_key.map(business_lookup)

        # Tighten eligibility - rows without a resolved project-type tuple
        # are NOT_APPLICABLE → PASS in segmented mode. (Pre-cleaning
        # guarantees dept_seg.notna() ⟺ business_seg.notna(), but we
        # AND both for clarity.)
        resolved = dept_seg.notna() & business_seg.notna()
        eligible = eligible & resolved
        if not eligible.any():
            return pd.Series(True, index=df.index)
        gid_frame["_dept"] = dept_seg
        gid_frame["_business"] = business_seg
        gid_cols = ["_item", "_uom", "_dept", "_business"]

    # Restrict to eligible rows; the groupby works on the trimmed frame
    # while the per-row verdict at the end maps results back to the
    # original index.
    work = gid_frame.loc[eligible].copy()
    work["_ratio"] = ratio.loc[eligible].to_numpy()
    grouped = work.groupby(gid_cols, dropna=True, sort=False)["_ratio"]
    stats = pd.DataFrame({
        "count": grouped.count(),
        "q1": grouped.quantile(0.25),
        "q3": grouped.quantile(0.75),
    })
    stats["iqr"] = stats["q3"] - stats["q1"]
    stats["lower"] = stats["q1"] - iqr_multiplier * stats["iqr"]
    stats["upper"] = stats["q3"] + iqr_multiplier * stats["iqr"]
    # A segment can only produce a FAIL when its population is large
    # enough AND its ratios actually vary - otherwise every row in the
    # segment is treated as NOT_APPLICABLE and passes.
    stats["can_fail"] = (
        (stats["count"] >= ADR_A7_MIN_POPULATION) & (stats["iqr"] > 0)
    )

    # Map per-segment stats back to every row via a merge on the segment
    # columns - pandas does this in C, far cheaper than a Python tuple
    # ``dict.map`` round-trip at this row count.
    merged = gid_frame.merge(
        stats[["lower", "upper", "can_fail"]].reset_index(),
        on=gid_cols, how="left", sort=False,
    )
    merged.index = df.index
    lower = merged["lower"]
    upper = merged["upper"]
    can_fail = merged["can_fail"].astype("boolean").fillna(False).astype(bool)

    out_of_bounds = (ratio < lower) | (ratio > upper)
    fail = (
        eligible
        & can_fail
        & out_of_bounds.fillna(False).astype(bool)
    )
    return ~fail


def check_adr_a8(
    df: pd.DataFrame, params: ADRA8Params | None = None
) -> pd.Series:
    """A8: Cross-discipline quantity ratios (ADR).

    Project-level statistical rule with row-level verdict. For each
    ``ROOT_ITEM_NAME`` (the project / scope key) the rule classifies
    eligible positive-quantity rows into discipline categories
    (PIPE_LENGTH, EQUIPMENT_COUNT, CABLE_LENGTH, TRANSMITTER_COUNT,
    STEEL_WEIGHT, CONCRETE_VOLUME) using ``ITEM_TYPE`` + ``QTY_UOM``
    (see :func:`_classify_a8_category`), aggregates the quantities,
    and computes three cross-discipline ratios:

    - ``PIPE_LENGTH / EQUIPMENT_COUNT``
    - ``CABLE_LENGTH / TRANSMITTER_COUNT``
    - ``STEEL_WEIGHT / CONCRETE_VOLUME``

    For each ratio the population is the set of projects with a
    calculable ratio. IQR mild bounds (``Q1 - 1.5*IQR`` …
    ``Q3 + 1.5*IQR``) are derived from that population, and a project
    is flagged for that ratio when its ratio falls outside the bounds.

    Row-level verdict (interpretation #1, mirrors E6): a row **fails**
    iff its ``ROOT_ITEM_NAME`` is flagged on at least one ratio. Rows
    whose project is unknown (null/blank ``ROOT_ITEM_NAME``) pass, they cannot be assigned to a project group.

    NOT_APPLICABLE → PASS for:

    - Population for a given ratio below
      :data:`ADR_A8_MIN_POPULATION` (too few projects to derive
      thresholds).
    - Population ``IQR == 0`` (no variation across projects).
    - Project's ratio cannot be calculated (numerator or denominator
      sum is zero - discipline simply not present at the right grain).

    ``params[ADR_A8_THRESHOLD_PARAM]`` (float > 0, default
    :data:`ADR_A8_MILD_IQR_MULTIPLIER` = 1.5) customizes the IQR
    multiplier, see :data:`ADR_A8_THRESHOLD_CHOICES` for the values
    surfaced in Step 4.2.

    ``params[ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM]`` (bool, default
    False) partitions the per-ratio IQR baseline by the composite
    ``(E05_DEPARTMENT, BUSINESS)`` tuple looked up from
    ``VWS_GP_STANDARD_SHARE`` via ``PLANVIEW_ID → PROJECT_ID``, mirrors
    the E6 / A7 toggle. With it on, each project is tagged with its
    archetype from the Planview reference and the IQR for each ratio is
    recomputed within each segment, so a deepwater FPSO is not pooled
    with an onshore refinery. Per-segment populations below
    :data:`ADR_A8_MIN_POPULATION` remain NOT_APPLICABLE → PASS.
    Projects whose segment cannot be resolved (no associated
    PLANVIEW_ID, unmatched PROJECT_ID, or null/blank
    ``E05_DEPARTMENT`` / ``BUSINESS``) are also NOT_APPLICABLE → PASS
    - A1 / A2 already cover those gaps. Raises
    :class:`CustomRuleNotEvaluated` when the toggle is on and the
    reference dataset is unavailable.

    Schema-level missing column → all rows fail (same convention as the
    other custom rules).
    """
    p = params or {}
    iqr_multiplier = _coerce_threshold(
        p.get(ADR_A8_THRESHOLD_PARAM),
        ADR_A8_MILD_IQR_MULTIPLIER,
    )
    segmented = p.get(ADR_A8_SEGMENT_BY_PROJECT_TYPE_PARAM, False)

    required = list(ADR_A8_REQUIRED_COLUMNS.values())
    if segmented:
        required = required + list(ADR_A8_SEGMENT_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    qty = pd.to_numeric(df["QTY_QUANTITY"], errors="coerce")
    item_type = df["ITEM_TYPE"]
    qty_uom = df["QTY_UOM"]
    project = df["ROOT_ITEM_NAME"]

    project_norm = project.astype(object).astype(str).str.strip()
    project_filled = _is_filled(project)

    # Per-row eligibility for ratio aggregation.
    eligible = (
        (qty > 0)
        & project_filled
        & _is_filled(item_type)
        & _is_filled(qty_uom)
    )
    if not eligible.any():
        return pd.Series(True, index=df.index)

    # Discipline classification - vectorised over the eligible slice.
    eligible_idx = df.index[eligible]
    categories = pd.Series(
        [
            _classify_a8_category(it, uom)
            for it, uom in zip(
                item_type.loc[eligible_idx],
                qty_uom.loc[eligible_idx],
            )
        ],
        index=eligible_idx,
        dtype=object,
    )

    classified = categories.notna()
    if not classified.any():
        return pd.Series(True, index=df.index)

    classified_idx = categories.index[classified]
    work = pd.DataFrame({
        "_proj": project_norm.loc[classified_idx],
        "_cat": categories.loc[classified_idx],
        "_qty": qty.loc[classified_idx],
    })
    # Per-(project, category) sum gives the discipline total used as
    # numerator / denominator in the cross-discipline ratios.
    proj_cat = (
        work.groupby(["_proj", "_cat"], dropna=True, sort=False)["_qty"]
        .sum()
        .unstack(fill_value=0.0)
    )
    if proj_cat.empty:
        return pd.Series(True, index=df.index)

    # Resolve each project's archetype segment when the toggle is on.
    # ``proj_segment`` maps ROOT_ITEM_NAME → (E05_DEPARTMENT, BUSINESS).
    # Projects with no associated PLANVIEW_ID, an unmatched PROJECT_ID,
    # or a null/blank segment component fall out of the dict entirely
    # and are treated as NOT_APPLICABLE → PASS below. The lookup is
    # pre-cleaned by ``_resolve_planview_segment_map`` (null/blank
    # dept/business already dropped, every value stripped), so each
    # entry pays a single dict-get.
    proj_segment: Dict[str, Tuple[str, str]] = {}
    if segmented:
        segment_lookup = _resolve_planview_segment_map(
            ADR_A8_SEGMENT_REFERENCE, "ADR A8"
        )
        # Pick the first non-blank PLANVIEW_ID per ROOT_ITEM_NAME. A
        # project should normally have a single PLANVIEW_ID across all
        # its rows, but if there are stragglers we still take the first
        # populated value - A1 / A2 already cover the missing-PLANVIEW
        # completeness gap, so A8 only needs *some* anchor to resolve
        # the archetype.
        pv_series = df["PLANVIEW_ID"]
        pv_filled = _is_filled(pv_series)
        pv_norm = pv_series.astype(object).astype(str).str.strip()
        proj_pv_df = pd.DataFrame({
            "_proj": project_norm.where(project_filled & pv_filled),
            "_pv": pv_norm.where(project_filled & pv_filled),
        }).dropna()
        if not proj_pv_df.empty:
            first_pv_by_proj = (
                proj_pv_df.drop_duplicates(subset="_proj", keep="first")
                .set_index("_proj")["_pv"]
                .to_dict()
            )
            for proj_key, pv_key in first_pv_by_proj.items():
                seg = segment_lookup.get(pv_key)
                if seg is not None:
                    proj_segment[proj_key] = seg

    failing_projects: set = set()
    for _, (num_cat, den_cat) in _A8_RATIOS.items():
        if num_cat not in proj_cat.columns or den_cat not in proj_cat.columns:
            continue
        num = proj_cat[num_cat]
        den = proj_cat[den_cat]
        ratio_eligible = (num > 0) & (den > 0)
        if not ratio_eligible.any():
            continue
        ratios = num[ratio_eligible] / den[ratio_eligible]

        if segmented:
            # Drop projects whose segment couldn't be resolved, they are
            # NOT_APPLICABLE → PASS in segmented mode. Then compute the
            # IQR within each resolved segment with the same minimum-
            # population floor.
            seg_index = pd.Series(
                [proj_segment.get(proj) for proj in ratios.index],
                index=ratios.index,
                dtype=object,
            )
            resolved = seg_index.notna()
            if not resolved.any():
                continue
            ratios_resolved = ratios[resolved]
            for seg_key, seg_ratios in ratios_resolved.groupby(
                seg_index[resolved]
            ):
                if len(seg_ratios) < ADR_A8_MIN_POPULATION:
                    continue
                q1 = float(seg_ratios.quantile(0.25))
                q3 = float(seg_ratios.quantile(0.75))
                iqr = q3 - q1
                if iqr <= 0:
                    continue
                lower = q1 - iqr_multiplier * iqr
                upper = q3 + iqr_multiplier * iqr
                bad_mask = (seg_ratios < lower) | (seg_ratios > upper)
                failing_projects.update(
                    seg_ratios.index[bad_mask].tolist()
                )
        else:
            if ratio_eligible.sum() < ADR_A8_MIN_POPULATION:
                continue
            q1 = float(ratios.quantile(0.25))
            q3 = float(ratios.quantile(0.75))
            iqr = q3 - q1
            if iqr <= 0:
                continue
            lower = q1 - iqr_multiplier * iqr
            upper = q3 + iqr_multiplier * iqr
            bad_mask = (ratios < lower) | (ratios > upper)
            failing_projects.update(ratios.index[bad_mask].tolist())

    if not failing_projects:
        return pd.Series(True, index=df.index)

    # Row-level verdict: a row fails iff its (filled) project is in the
    # failing set. Rows with null/blank ROOT_ITEM_NAME pass, they have
    # no project to attach to.
    in_failing = (
        project_norm.where(project_filled).isin(failing_projects)
        .fillna(False)
        .astype(bool)
    )
    return ~in_failing


