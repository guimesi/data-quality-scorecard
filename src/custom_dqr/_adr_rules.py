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

import re
from typing import Dict, List, Optional, Tuple, TypedDict

import numpy as np
import pandas as pd

from src.custom_dqr._shared import (
    CustomRuleNotEvaluated,
    _coerce_threshold,
    _is_filled,
    _resolve_planview_segment_map,
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


class ADRA9Params(TypedDict, total=False):
    """Step 4.2 -> assignment.params shape for ADR A9."""
    tolerance_pct: float              # ADR_A9_TOLERANCE_PARAM
    period_policy: str                # ADR_A9_PERIOD_POLICY_PARAM
    fail_without_reference: bool      # ADR_A9_FAIL_WITHOUT_REFERENCE_PARAM


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
    ("EstimateTankage", "m³"),
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

# Length / volume / weight / area UOMs used by A4's classifiers. Reuses the
# A8 alias map (defined further down) so ``CY`` ↔ ``yd³`` etc.
# The steel and concrete sets are unit-system-neutral: they accept any
# physical measurement (imperial or metric) that represents the
# discipline's quantity, not just the historically predominant UOM.
_A4_LENGTH_UOMS = frozenset({"ft", "m"})
_A4_AREA_UOMS = frozenset({"ft²", "m²", "yd²"})
_A4_VOLUME_UOMS = frozenset({"yd³", "m³"})
_A4_WEIGHT_UOMS = frozenset({"t", "t,sht"})
# Steel: weight (original) + length + area (metric fix).
_A4_STEEL_UOMS = _A4_WEIGHT_UOMS | _A4_LENGTH_UOMS | _A4_AREA_UOMS
# Concrete: volume (original) + weight + area (metric fix).
_A4_CONCRETE_UOMS = _A4_VOLUME_UOMS | _A4_WEIGHT_UOMS | _A4_AREA_UOMS

# A5: Key design details present when quantity exists.
#
# Operates on the denormalized ADR data product (built by
# ``src.data_product_builder.build_data_product``). ``ADR_DIM_ESTIMATE-
# DESIGNDETAILS`` is 1:N on ``ROW_ID`` (one row per parameter, ~10 per
# item in production). Because the builder keeps only the *first* value
# of a text column when it collapses 1:N rows, the rule cannot read
# ``DESIGN_PARAMETER_NAME`` / ``DESIGN_PARAMETER_VALUE`` directly - it
# would see one arbitrary parameter per item. Instead the ADR TableDef
# (``config/systems.py``) derives ``DESIGN_KEY_PARAMETER_NAMES`` per row
# (the parameter name when its value is populated) and joins the per-item
# values into one pipe-separated list, so the rule can ask "does *any*
# populated parameter carry the expected COA prefix?".
#
# The rule is type-aware: for each ``ITEM_TYPE`` with a known ACCE COA
# prefix mapping, at least one populated parameter name must start with
# the expected prefix. Item types not in the mapping fall back to "any
# populated design parameter" (the original A5 behaviour).
#
# Source columns on the denormalized data product:
#   - ``QTY_QUANTITY``               - SUM of QUANTITY for the ROW_ID.
#   - ``ITEM_TYPE``                  - pass-through from the primary table.
#   - ``DESIGN_KEY_PARAMETER_NAMES`` - derived: ``name1|name2|...`` of the
#     parameters whose value is populated; null when none is.
ADR_A5_REQUIRED_COLUMNS = {
    "Quantity": "QTY_QUANTITY",
    "Item Type": "ITEM_TYPE",
    "Key Parameter Names": "DESIGN_KEY_PARAMETER_NAMES",
}
ADR_A5_NAME_SEPARATOR = "|"

# ITEM_TYPE → expected COA design-parameter prefix(es). Derived from
# production data: each prefix has ≥ 90% coverage within its item type.
# The match is starts-with (not exact) so composite prefixes such as
# ``314.0,315.2,316.0-Diameter-Section-1`` (vertical vessels) still
# resolve. Prefixes without a minor digit (``302.``, ``337.``) cover every
# sub-account of that COA group.
_A5_KEY_DESIGN_PREFIX: Dict[str, Tuple[str, ...]] = {
    "EstimateAbovegroundInstrumentPiping": ("313.1",),
    "EstimatePipingUnderground": ("313.2",),
    "EstimatePipingPneumatic": ("339.0",),
    "EstimatePump": ("324.0",),
    "EstimateElectricMotor": ("301.0",),
    "EstimateCentrifugalCompressor": ("302.",),
    "EstimateReciprocatingCompressor": ("303.0",),
    "EstimateHorizontalDrum": ("315.1",),
    "EstimateVerticalPressureVessel": ("314.0",),
    "EstimateShellAndTubeExchanger": ("311.1",),
    "EstimatePlateExchanger": ("312.0",),
    "EstimateHairpinExchanger": ("311.2",),
    "EstimateAirCooledExchanger": ("310.0",),
    "EstimateTankage": ("326.0",),
    "EstimateFurnace": ("317.0",),
    "EstimateSteelStructure": ("318.0",),
    "EstimatePiperack": ("318.0",),
    "EstimateFoundation": ("308.0",),
    "EstimateConcreteStructure": ("308.0",),
    "EstimateMiscellaneousConcrete": ("308.0",),
    "EstimateElectricalPowerGroup": ("337.",),
    "EstimateFieldInstrumentGroup": ("322.0",),
    "EstimateInsulation": ("348.0",),
    "EstimatePaint": ("349.0",),
    "EstimateFireproofing": ("306.0",),
    "EstimateExcavation": ("307.0",),
    "EstimateTrenching": ("307.0",),
    "EstimatePiling": ("309.0",),
    "EstimateRoadWalkFence": ("328.0",),
    "EstimatePaving": ("308.0",),
    "EstimateBuilding": ("321.0",),
    "EstimateSteamTurbine": ("304.0",),
    "EstimateGasTurbine": ("305.0",),
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


# A9: Base material factor validation (MFC vs EMMA Market Analysis).
#
# Validity rule at the ROW_ID grain. ADR cost results carry two *material
# factor codes* - ``BASE_MATERIAL_MFC`` and ``VENDOR_SHOP_FAB_MFC`` (e.g.
# ``313.01``) - that point at a published EMMA factor for a location and
# a cost-update period. The factor actually applied to the estimate is
# the ratio ``<COST> / <DB_COST>`` (localized cost over database cost),
# confirmed against production: the median ratio per code falls inside
# the EMMA factor range for that code. The rule therefore:
#
#   1. skips a factor field whose code is null / blank (NOT_APPLICABLE);
#   2. fails a code of ``0`` or ``80`` (no factor available, manual
#      intervention placeholder);
#   3. fails a code unknown to EMMA in any location / period;
#   4. resolves the item's location (``PLANVIEW_ID`` → Planview
#      ``COUNTRY`` → ISO-2 prefix of EMMA ``locationCode``) and period
#      (``COST_UPDATE`` ``nQYYYY`` → exact or nearest EMMA period, per the
#      card option); a row that cannot be resolved, or whose (code,
#      location, period) has no EMMA row, is NO_REFERENCE - PASS unless
#      the "fail without reference" toggle is on;
#   5. compares the effective factor with every EMMA factor of that code
#      in the country's sites for the period and fails when the *closest*
#      one still deviates more than the tolerance (card option, default
#      ±10% per the data owner).
#
# ``SPEC_S_C_MFC`` is deliberately not validated: Specialty Contractor
# cost is estimated from labour hours, the MFC there is not used.
#
# Source columns on the denormalized data product (cost results are 1:1
# per ROW_ID in production, so the builder's sum / first are identity):
#   - ``PLANVIEW_ID``                   - project key (location lookup).
#   - ``COST_UPDATE``                   - estimate basis period (nQYYYY).
#   - ``COST_BASE_MATERIAL_MFC``        - base material factor code.
#   - ``COST_VENDOR_SHOP_FAB_MFC``      - vendor shop fabrication code.
#   - ``COST_BASE_MATERIAL_COST`` / ``COST_DB_BASE_MATERIAL_COST``
#   - ``COST_VENDOR_SHOP_FAB_COST`` / ``COST_DB_VENDOR_SHOP_FAB_COST``
ADR_A9_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
    "Estimate Basis Date": "COST_UPDATE",
    "Base Material MFC": "COST_BASE_MATERIAL_MFC",
    "Vendor Shop Fab MFC": "COST_VENDOR_SHOP_FAB_MFC",
    "Base Material Cost": "COST_BASE_MATERIAL_COST",
    "DB Base Material Cost": "COST_DB_BASE_MATERIAL_COST",
    "Vendor Shop Fab Cost": "COST_VENDOR_SHOP_FAB_COST",
    "DB Vendor Shop Fab Cost": "COST_DB_VENDOR_SHOP_FAB_COST",
}
# EMMA reference (``mfc`` table). The loader aliases the camelCase source
# columns to these canonical names.
ADR_A9_REFERENCE = {
    "reference_dataset": "MFC",
    "source_column": "COST_BASE_MATERIAL_MFC / COST_VENDOR_SHOP_FAB_MFC",
    "reference_column": "CODE",
    "lookup_column": "FACTOR_VALUE (per LOCATION_CODE + PERIOD)",
}
ADR_A9_MFC_COLUMNS: Tuple[str, ...] = (
    "CODE", "LOCATION_CODE", "PERIOD", "FACTOR_VALUE",
)
# Location resolution reuses the A2 Planview join.
ADR_A9_LOCATION_REFERENCE = {
    "reference_dataset": "VWS_GP_STANDARD_SHARE",
    "source_column": "PLANVIEW_ID",
    "reference_column": "PROJECT_ID",
    "lookup_column": "COUNTRY",
}
# (label, code column, localized cost column, database cost column)
ADR_A9_FACTOR_FIELDS: Tuple[Tuple[str, str, str, str], ...] = (
    ("BM", "COST_BASE_MATERIAL_MFC",
     "COST_BASE_MATERIAL_COST", "COST_DB_BASE_MATERIAL_COST"),
    ("VSF", "COST_VENDOR_SHOP_FAB_MFC",
     "COST_VENDOR_SHOP_FAB_COST", "COST_DB_VENDOR_SHOP_FAB_COST"),
)
# Tolerance on the relative deviation |effective - EMMA| / EMMA.
ADR_A9_TOLERANCE_PARAM = "tolerance_pct"
ADR_A9_TOLERANCE = 0.10
ADR_A9_TOLERANCE_CHOICES: Tuple[Tuple[float, str], ...] = (
    (0.10, "±10% - recommended"),
    (0.15, "±15%"),
    (0.20, "±20%"),
    (0.25, "±25% - calibration"),
)
# Which EMMA period to compare against. ``nearest`` picks the EMMA period
# closest to the item's COST_UPDATE (ties → the earlier one); ``exact``
# requires the same period and otherwise yields NO_REFERENCE.
ADR_A9_PERIOD_POLICY_PARAM = "period_policy"
ADR_A9_PERIOD_POLICY = "nearest"
ADR_A9_PERIOD_POLICY_CHOICES: Tuple[Tuple[str, str], ...] = (
    ("nearest", "Nearest EMMA period - recommended"),
    ("exact", "Exact period only"),
)
# When on, rows whose (code, location, period) has no EMMA reference fail
# instead of passing as NO_REFERENCE.
ADR_A9_FAIL_WITHOUT_REFERENCE_PARAM = "fail_without_reference"
# Codes the data owner flags as "no factor available" placeholders.
ADR_A9_SENTINEL_CODES: Tuple[float, ...] = (0.0, 80.0)

# Per-field statuses / reasons surfaced by ``_evaluate_adr_a9``.
A9_PASS = "PASS"
A9_FAIL = "FAIL"
A9_NO_REFERENCE = "NO_REFERENCE"
A9_NOT_APPLICABLE = "NOT_APPLICABLE"

# Planview ``COUNTRY`` → ISO-2 prefix of EMMA ``locationCode``. Keys are
# lower-cased; a bare 2-letter alpha value is accepted as-is (``UK`` is
# normalised to ``GB``).
_A9_COUNTRY_TO_ISO2: Dict[str, str] = {
    "united states": "US", "united states of america": "US", "usa": "US",
    "canada": "CA", "mexico": "MX", "brazil": "BR", "brasil": "BR",
    "argentina": "AR", "guyana": "GY",
    "united kingdom": "GB", "uk": "GB", "great britain": "GB",
    "netherlands": "NL", "the netherlands": "NL", "belgium": "BE",
    "germany": "DE", "france": "FR", "italy": "IT", "spain": "ES",
    "norway": "NO",
    "china": "CN", "singapore": "SG", "japan": "JP",
    "south korea": "KR", "korea": "KR", "republic of korea": "KR",
    "india": "IN", "malaysia": "MY", "indonesia": "ID", "thailand": "TH",
    "vietnam": "VN", "viet nam": "VN", "philippines": "PH",
    "australia": "AU", "papua new guinea": "PG",
    "saudi arabia": "SA", "qatar": "QA", "united arab emirates": "AE",
    "uae": "AE", "iraq": "IQ", "kazakhstan": "KZ",
    "nigeria": "NG", "angola": "AO", "mozambique": "MZ",
}
_A9_PERIOD_PATTERN = r"^([1-4])Q(\d{4})$"

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
    "yd^2": "yd²",
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
        and uom_norm in _A4_STEEL_UOMS
    ):
        return "STEEL_TONS"

    if (
        ("Foundation" in it or "Concrete" in it)
        and uom_norm in _A4_CONCRETE_UOMS
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
    has_steel = qty_pos & is_steel & uom_norm.isin(_A4_STEEL_UOMS)
    has_concrete = qty_pos & is_concrete & uom_norm.isin(_A4_CONCRETE_UOMS)
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
    """A5: Key design details present when quantity exists (ADR).

    Type-aware Consistency rule evaluated at the ``ROW_ID`` grain. For
    each estimate item the rule derives:

    - ``HAS_QUANTITY`` - the aggregated ``QTY_QUANTITY`` is non-null and
      not equal to zero (negative counts as non-zero).
    - ``KNOWN_TYPE`` - ``ITEM_TYPE`` is in ``_A5_KEY_DESIGN_PREFIX``.
    - ``HAS_KEY_DESIGN`` - at least one entry of the pipe-separated
      ``DESIGN_KEY_PARAMETER_NAMES`` starts with one of the prefixes
      expected for the item type. Entries only exist for parameters
      whose value is populated (see ``_adr_design_derive``).
    - ``HAS_ANY_DESIGN`` - ``DESIGN_KEY_PARAMETER_NAMES`` is non-empty,
      i.e. at least one design parameter carries a value (the original
      A5 check).

    Pass / fail matrix (rows with ``HAS_QUANTITY = 0`` always pass):

    +------------+----------------+----------------+-------------+
    | KNOWN_TYPE | HAS_KEY_DESIGN | HAS_ANY_DESIGN | RULE_RESULT |
    +============+================+================+=============+
    |     1      |       1        |       -        |    PASS     |
    |     1      |       0        |       -        |    FAIL     |
    |     0      |       -        |       1        |    PASS     |
    |     0      |       -        |       0        |    FAIL     |
    +------------+----------------+----------------+-------------+

    The prefix match is starts-with per entry, so composite names such
    as ``314.0,315.2,316.0-Diameter-Section-1`` resolve to ``314.0``.
    Schema-level missing column → all rows fail (same convention as the
    other custom rules).
    """
    required = list(ADR_A5_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    # NaN → 0 so a missing aggregated quantity is treated as "no quantity".
    qty = pd.to_numeric(df["QTY_QUANTITY"], errors="coerce").fillna(0.0)
    has_quantity = qty != 0
    if not has_quantity.any():
        return pd.Series(True, index=df.index)

    item_type = df["ITEM_TYPE"].astype(object).astype(str).str.strip()
    names_col = df["DESIGN_KEY_PARAMETER_NAMES"]
    has_any_design = _is_filled(names_col)
    names = names_col.astype(object).astype(str).where(has_any_design, "")

    known_type = item_type.isin(_A5_KEY_DESIGN_PREFIX.keys())
    has_key_design = pd.Series(False, index=df.index)
    sep = re.escape(ADR_A5_NAME_SEPARATOR)
    for it, prefixes in _A5_KEY_DESIGN_PREFIX.items():
        it_mask = item_type == it
        if not it_mask.any():
            continue
        # An entry matches when the prefix sits at the start of the string
        # or right after a separator (optional whitespace tolerated).
        alternatives = "|".join(re.escape(p) for p in prefixes)
        pattern = rf"(?:^|{sep})\s*(?:{alternatives})"
        name_match = names.str.contains(pattern, regex=True, na=False)
        has_key_design = has_key_design | (it_mask & name_match)

    # Known types need the key parameter; unknown types keep the original
    # any-populated-parameter check.
    design_ok = (known_type & has_key_design) | (~known_type & has_any_design)
    return (~has_quantity) | design_ok


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


# =============================================================================
# A9 helpers
# =============================================================================

def _a9_country_to_iso2(value: object) -> Optional[str]:
    """Map a Planview ``COUNTRY`` (name or code) to the ISO-2 prefix used
    by EMMA ``locationCode``; ``None`` when it cannot be resolved."""
    if value is None or value != value:
        return None
    text = str(value).strip()
    if not text:
        return None
    key = text.lower()
    if key in _A9_COUNTRY_TO_ISO2:
        return _A9_COUNTRY_TO_ISO2[key]
    if len(text) == 2 and text.isalpha():
        return text.upper()
    return None


def _a9_period_ordinal(series: pd.Series) -> pd.Series:
    """``nQYYYY`` → ``YYYY * 4 + (n - 1)`` (float; NaN when malformed)."""
    text = series.astype(object).astype(str).str.strip().str.upper()
    parts = text.str.extract(_A9_PERIOD_PATTERN)
    quarter = pd.to_numeric(parts[0], errors="coerce")
    year = pd.to_numeric(parts[1], errors="coerce")
    return year * 4 + (quarter - 1)


def _a9_code_key(series: pd.Series) -> Tuple[pd.Series, pd.Series]:
    """Normalise an MFC code column.

    Returns ``(key, numeric)``: ``key`` is the 2-decimal string form used
    to join the EMMA reference (``313.1`` and ``313.10`` collapse, and
    the float noise in ``mfc.code`` such as ``308.02999`` rounds away);
    non-numeric populated values keep their stripped text so they miss
    the lookup and surface as UNKNOWN_CODE. ``numeric`` is the parsed
    float (NaN when not numeric) used for the 0 / 80 sentinel check."""
    text = series.astype(object).astype(str).str.strip()
    numeric = pd.to_numeric(text, errors="coerce")
    key = numeric.round(2).map(
        lambda v: None if pd.isna(v) else f"{v:.2f}"
    )
    key = key.where(key.notna(), text)
    return key, numeric


def _a9_load_references() -> Tuple[pd.DataFrame, Dict[str, Optional[str]]]:
    """Load and pre-clean the EMMA ``MFC`` reference and the Planview
    ``PLANVIEW_ID → ISO-2`` map. Raises ``CustomRuleNotEvaluated`` when
    either dataset is unavailable or lacks its required columns."""
    from src.reference_data import (
        get_reference_dataset,
        get_reference_dataset_error,
    )

    mfc_name = ADR_A9_REFERENCE["reference_dataset"]
    mfc = get_reference_dataset(mfc_name)
    if mfc is None:
        cached_error = get_reference_dataset_error(mfc_name)
        detail = f": {cached_error}" if cached_error else ""
        raise CustomRuleNotEvaluated(
            f"ADR A9: '{mfc_name}' reference dataset is unavailable{detail}; "
            "material factor codes cannot be validated against EMMA."
        )
    mfc = mfc.rename(columns={c: str(c).upper() for c in mfc.columns})
    missing = [c for c in ADR_A9_MFC_COLUMNS if c not in mfc.columns]
    if missing:
        raise CustomRuleNotEvaluated(
            f"ADR A9: '{mfc_name}' is missing required columns {missing}; "
            "material factor codes cannot be validated against EMMA."
        )
    code_key, _ = _a9_code_key(mfc["CODE"])
    emma = pd.DataFrame({
        "code_key": code_key,
        "prefix": (
            mfc["LOCATION_CODE"].astype(object).astype(str).str.strip()
            .str.split(".").str[0].str.upper()
        ),
        "period": _a9_period_ordinal(mfc["PERIOD"]),
        "factor": pd.to_numeric(mfc["FACTOR_VALUE"], errors="coerce"),
    })
    emma = emma[
        emma["code_key"].notna() & emma["prefix"].ne("")
        & emma["period"].notna() & emma["factor"].notna()
        & (emma["factor"] > 0)
    ].drop_duplicates()

    loc_name = ADR_A9_LOCATION_REFERENCE["reference_dataset"]
    planview = get_reference_dataset(loc_name)
    if planview is None:
        cached_error = get_reference_dataset_error(loc_name)
        detail = f": {cached_error}" if cached_error else ""
        raise CustomRuleNotEvaluated(
            f"ADR A9: '{loc_name}' reference dataset is unavailable{detail}; "
            "project location cannot be resolved for the EMMA lookup."
        )
    ref_col = ADR_A9_LOCATION_REFERENCE["reference_column"]
    lookup_col = ADR_A9_LOCATION_REFERENCE["lookup_column"]
    if ref_col not in planview.columns or lookup_col not in planview.columns:
        raise CustomRuleNotEvaluated(
            f"ADR A9: '{loc_name}' is missing '{ref_col}' / '{lookup_col}'; "
            "project location cannot be resolved for the EMMA lookup."
        )
    ref = (
        planview[[ref_col, lookup_col]]
        .dropna(subset=[ref_col])
        .drop_duplicates(subset=[ref_col])
    )
    iso_by_project = {
        str(k).strip(): _a9_country_to_iso2(v)
        for k, v in zip(ref[ref_col], ref[lookup_col])
    }
    return emma, iso_by_project


def _a9_pick_period(
    item_period: pd.Series, emma_periods: np.ndarray, policy: str
) -> pd.Series:
    """Resolve the EMMA period ordinal to compare each row against."""
    if emma_periods.size == 0:
        return pd.Series(np.nan, index=item_period.index)
    if policy == "exact":
        return item_period.where(item_period.isin(emma_periods))
    # nearest: closest EMMA period, ties → the earlier one.
    values = item_period.to_numpy(dtype=float)
    out = np.full(values.shape, np.nan)
    valid = ~np.isnan(values)
    if valid.any():
        pos = np.searchsorted(emma_periods, values[valid], side="left")
        lo = np.clip(pos - 1, 0, emma_periods.size - 1)
        hi = np.clip(pos, 0, emma_periods.size - 1)
        d_lo = np.abs(values[valid] - emma_periods[lo])
        d_hi = np.abs(values[valid] - emma_periods[hi])
        out[valid] = np.where(d_lo <= d_hi, emma_periods[lo], emma_periods[hi])
    return pd.Series(out, index=item_period.index)


def _evaluate_adr_a9(
    df: pd.DataFrame, params: ADRA9Params | None = None
) -> pd.DataFrame:
    """Per-row, per-factor evaluation behind :func:`check_adr_a9`.

    Returns a DataFrame indexed like ``df`` with, for each factor field
    (``bm`` / ``vsf``): ``<f>_status`` (PASS / FAIL / NO_REFERENCE /
    NOT_APPLICABLE), ``<f>_reason``, ``<f>_effective`` (the applied
    factor), ``<f>_reference`` (the closest EMMA factor) and
    ``<f>_deviation`` (relative, fraction); plus ``location`` (ISO-2),
    ``period_used`` (EMMA period ordinal) and ``row_status``. Useful for
    the calibration the data owner asked for and for drill-down.
    Assumes the required columns are present (the caller checks).
    """
    p = params or {}
    tolerance = _coerce_threshold(p.get(ADR_A9_TOLERANCE_PARAM), ADR_A9_TOLERANCE)
    policy = str(p.get(ADR_A9_PERIOD_POLICY_PARAM) or ADR_A9_PERIOD_POLICY)
    if policy not in ("nearest", "exact"):
        policy = ADR_A9_PERIOD_POLICY
    fail_without_reference = bool(
        p.get(ADR_A9_FAIL_WITHOUT_REFERENCE_PARAM, False)
    )

    emma, iso_by_project = _a9_load_references()
    known_codes = set(emma["code_key"])
    emma_periods = np.sort(emma["period"].unique().astype(float))

    out = pd.DataFrame(index=df.index)
    pv = df["PLANVIEW_ID"].astype(object).astype(str).str.strip()
    pv_filled = _is_filled(df["PLANVIEW_ID"])
    out["location"] = pv.map(iso_by_project).where(pv_filled)
    item_period = _a9_period_ordinal(df["COST_UPDATE"])
    out["period_used"] = _a9_pick_period(item_period, emma_periods, policy)

    for label, code_col, cost_col, db_col in ADR_A9_FACTOR_FIELDS:
        f = label.lower()
        status = pd.Series(A9_NOT_APPLICABLE, index=df.index, dtype=object)
        reason = pd.Series("NULL_MFC", index=df.index, dtype=object)
        effective = pd.Series(np.nan, index=df.index)
        reference = pd.Series(np.nan, index=df.index)
        deviation = pd.Series(np.nan, index=df.index)

        filled = _is_filled(df[code_col])
        code_key, code_num = _a9_code_key(df[code_col])
        sentinel = filled & code_num.isin(ADR_A9_SENTINEL_CODES)
        status[sentinel] = A9_FAIL
        reason[sentinel & (code_num == 0)] = "ZERO_MFC"
        reason[sentinel & (code_num == 80)] = "VALUE_80_NO_FACTOR"

        unknown = filled & ~sentinel & ~code_key.isin(known_codes)
        status[unknown] = A9_FAIL
        reason[unknown] = "UNKNOWN_CODE"

        pending = filled & ~sentinel & ~unknown
        no_location = pending & out["location"].isna()
        status[no_location] = A9_NO_REFERENCE
        reason[no_location] = "NO_LOCATION"
        no_period = pending & ~no_location & out["period_used"].isna()
        status[no_period] = A9_NO_REFERENCE
        reason[no_period] = "NO_PERIOD"
        pending &= ~no_location & ~no_period

        cost = pd.to_numeric(df[cost_col], errors="coerce")
        db_cost = pd.to_numeric(df[db_col], errors="coerce")
        eff = (cost / db_cost).where(db_cost > 0)
        effective[pending] = eff[pending]
        no_eff = pending & eff.isna()
        status[no_eff] = A9_NOT_APPLICABLE
        reason[no_eff] = "NULL_EFFECTIVE_FACTOR"
        pending &= ~no_eff

        if pending.any():
            rows = pd.DataFrame({
                "_idx": df.index[pending],
                "code_key": code_key[pending].to_numpy(),
                "prefix": out["location"][pending].to_numpy(),
                "period": out["period_used"][pending].to_numpy(),
                "eff": eff[pending].to_numpy(),
            })
            merged = rows.merge(
                emma, on=["code_key", "prefix", "period"], how="inner"
            )
            if not merged.empty:
                merged["dev"] = (merged["eff"] - merged["factor"]).abs() / merged["factor"]
                best = (
                    merged.sort_values("dev")
                    .drop_duplicates(subset=["_idx"])
                    .set_index("_idx")
                )
                matched = pd.Series(False, index=df.index)
                matched[best.index] = True
                deviation[best.index] = best["dev"]
                reference[best.index] = best["factor"]
                within = matched & (deviation <= tolerance)
                status[within] = A9_PASS
                reason[within] = "WITHIN_TOLERANCE"
                over = matched & (deviation > tolerance)
                status[over] = A9_FAIL
                reason[over] = "DEVIATION_GT_TOLERANCE"
            else:
                matched = pd.Series(False, index=df.index)
            no_ref = pending & ~matched
            status[no_ref] = A9_NO_REFERENCE
            reason[no_ref] = "NO_REFERENCE_FOR_LOCATION_PERIOD"

        out[f"{f}_status"] = status
        out[f"{f}_reason"] = reason
        out[f"{f}_effective"] = effective
        out[f"{f}_reference"] = reference
        out[f"{f}_deviation"] = deviation

    statuses = [out[f"{lab.lower()}_status"] for lab, *_ in ADR_A9_FACTOR_FIELDS]
    any_fail = pd.Series(False, index=df.index)
    any_no_ref = pd.Series(False, index=df.index)
    any_pass = pd.Series(False, index=df.index)
    for st in statuses:
        any_fail |= st.eq(A9_FAIL)
        any_no_ref |= st.eq(A9_NO_REFERENCE)
        any_pass |= st.eq(A9_PASS)
    row_status = pd.Series(A9_NOT_APPLICABLE, index=df.index, dtype=object)
    row_status[any_pass] = A9_PASS
    row_status[any_no_ref & ~any_pass] = A9_NO_REFERENCE
    if fail_without_reference:
        row_status[any_no_ref] = A9_FAIL
    row_status[any_fail] = A9_FAIL
    out["row_status"] = row_status
    return out


def check_adr_a9(
    df: pd.DataFrame, params: ADRA9Params | None = None
) -> pd.Series:
    """A9: Base material factor validation - MFC vs EMMA (ADR).

    Validity rule at the ROW_ID grain. For each of the two material
    factor codes (``COST_BASE_MATERIAL_MFC``, ``COST_VENDOR_SHOP_FAB_MFC``)
    the rule derives the *effective* factor applied to the estimate
    (``<COST> / <DB_COST>``) and compares it with the EMMA factor
    published for that code at the project's location (Planview
    ``COUNTRY`` → ISO-2 prefix of ``locationCode``, any site of the
    country) and cost-update period (exact or nearest EMMA period, per
    ``params[period_policy]``).

    Per factor field:

    - code null / blank → NOT_APPLICABLE;
    - code ``0`` or ``80`` → FAIL (no factor available placeholder);
    - code unknown to EMMA (any location / period) → FAIL;
    - location or period unresolvable, or no EMMA row for (code,
      location, period) → NO_REFERENCE (PASS unless
      ``params[fail_without_reference]``);
    - ``DB_COST`` null / non-positive → NOT_APPLICABLE;
    - closest EMMA factor deviates more than ``params[tolerance_pct]``
      (default ±10%) → FAIL, otherwise PASS.

    Row verdict: FAIL when any factor field fails; otherwise PASS
    (NOT_APPLICABLE and NO_REFERENCE rows pass). ``SPEC_S_C_MFC`` is not
    validated (specialty contractor cost is hours-based).

    Raises :class:`CustomRuleNotEvaluated` when the EMMA ``MFC`` or the
    Planview reference is unavailable. Schema-level missing column → all
    rows fail (same convention as the other custom rules).
    """
    required = list(ADR_A9_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)
    result = _evaluate_adr_a9(df, params)
    return result["row_status"].ne(A9_FAIL)
