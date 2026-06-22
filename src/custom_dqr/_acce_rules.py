# pyright: reportArgumentType=false, reportOperatorIssue=false
# pyright: reportCallIssue=false, reportReturnType=false
# pyright: reportAttributeAccessIssue=false
"""ACCE custom DQR rule checks (AC1-AC8).

The ACCE family mirrors ADR's structure (same families, different source
columns and reference datasets) so most rules share the same group-verdict
template adapted to ACCE column names.

See the pragma rationale in ``src/custom_dqr/_adr_rules.py`` - the same
reasoning applies here: pandas-stubs typing of ``df[col]`` as
``Series | DataFrame`` produces hundreds of false-positive errors that
``cast(pd.Series, ...)`` would only paper over. The runtime contract is
locked down by ``tests/test_custom_dqr_engine.py``.
"""
from __future__ import annotations

from typing import Dict, List, Tuple, TypedDict

import numpy as np
import pandas as pd


class ACCEAC3Params(TypedDict, total=False):
    """Step 4.2 -> assignment.params shape for ACCE AC3 (mirrors EPT E3)."""
    threshold_percentile: float       # ACCE_AC3_THRESHOLD_PARAM
    detect_uniform_mapping: bool      # ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM


class ACCEAC7Params(TypedDict, total=False):
    """Step 4.2 -> assignment.params shape for ACCE AC7."""
    threshold_iqr_multiplier: float   # ACCE_AC7_THRESHOLD_PARAM
    segment_by_project_type: bool     # ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM


class ACCEAC8Params(TypedDict, total=False):
    """Step 4.2 -> assignment.params shape for ACCE AC8."""
    threshold_iqr_multiplier: float   # ACCE_AC8_THRESHOLD_PARAM
    segment_by_project_type: bool     # ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM


# ACCE rules reuse ADR primitives: AC1 mirrors A1's value-validation and
# COA-master lookup.
from src.custom_dqr._adr_rules import (
    _a1_value_valid,
    _resolve_coa_master_lookups,
)
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

# =============================================================================
# ACCE custom rules
# =============================================================================

ACCE_AC1_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
    "Code of Account": "COA",
}

ACCE_AC1_REFERENCE = {
    "reference_dataset": "ACCE_COA_MASTER",
    "source_column": "COA",              # in ACCE (direct numeric COA code)
    "reference_column": "ICARUS_COA",    # in ACCE_COA_MASTER
    "lookup_column": "ISO_COR / SAB",    # both must resolve to a valid value
}


ACCE_AC2_REQUIRED_COLUMNS = {
    "Estimate Job Number": "JOB_NO",
    "Project Key": "PLANVIEW_ID",
}

ACCE_AC2_REFERENCE = {
    "reference_dataset": "VWS_GP_STANDARD_SHARE",
    "source_column": "PLANVIEW_ID",      # in ACCE
    "reference_column": "PROJECT_ID",    # in VWS_GP_STANDARD_SHARE
    "lookup_column": "COUNTRY",          # populated value to check post-join
}

# AC2 Validity: JOB_NO is ACCE's estimate-job/period proxy, a fiscal
# quarter-year token optionally suffixed with a revision marker. Live
# values: "2Q23 RP1", "2Q24", "2Q25", "4Q23". The check is *structural*,
# not an enum, so new quarters/years pass automatically and the column can
# grow new values without a code change: a quarter digit 1-4, the literal
# "Q" (case-insensitive), a 2-digit year, then an optional
# whitespace-separated suffix (e.g. " RP1"). A populated value that does
# not start with this token (e.g. "2023", "Q2-23", "5Q23") fails Validity.
ACCE_AC2_JOB_NO_PATTERN = r"[1-4]Q\d{2}(\s.*)?"


# AC3: Statistical COA-to-ISO mapping ratio (ACCE).
#
# Mapping-quality statistical rule with row-level verdict. Mirrors ADR
# A3 against the ACCE schema:
#
#   - ADR groups COMPLETE_WBC rows by SPLIT_PART(.,'.',1) → ICARUS_COA
#     before computing COUNT(DISTINCT COMPLETE_WBC) per (ISO_COR, SAB)
#     bucket. ACCE takes the leading three characters of the 4-char
#     COA as the lookup key, then counts distinct *full* COA values
#     per bucket, typically lower than ADR's WBC_TO_ISO_RATIO
#     because ACCE granularity is capped at ten 4-char codes per
#     3-char ICARUS_COA group.
#   - Materiality, P90 baseline, and minimum-population floor mirror
#     A3. The percentile is recomputed from the data on every run
#     (no fixed benchmark). The materiality columns differ: ACCE
#     uses ``COST_MH`` (sourced from ``MH`` on
#     ``ACCE_ESTIMATECOSTRESULTS``) for construction hours and
#     ``COST_TOTAL_COST`` for total cost. ADR uses
#     ``COST_TOTAL_HOURS`` + ``COST_TOTAL_COST``.
#   - The project-scope toggle present on A3 is *not* exposed by AC3
#     per the rule spec - AC3 only ships the percentile threshold and
#     the uniform-detection toggle.
#   - Uniform detection on AC3 is gated by a *portfolio-wide
#     proportion*: when ≥ ACCE_AC3_UNIFORM_THRESHOLD (default 80%) of
#     eligible mappings have ratio == 1, every material 1:1 bucket
#     fails. A3 flags every material 1:1 bucket unconditionally when
#     its toggle is on, which is a stricter signal. AC3's relaxed
#     version reflects that ACCE COA codes are inherently coarser, so
#     a small handful of legitimate 1:1 mappings is not by itself a
#     mapping-discipline issue.
ACCE_AC3_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
    "Code of Account": "COA",
    # ACCE stores construction hours in ``MH`` on
    # ``ACCE_ESTIMATECOSTRESULTS``; the data-product builder prefixes
    # that to ``COST_MH``. The ADR equivalent is
    # ``COST_TOTAL_HOURS`` (sourced from ``TOTAL_HOURS``).
    "Construction Hours": "COST_MH",
    "Total Cost": "COST_TOTAL_COST",
}

ACCE_AC3_REFERENCE = {
    "reference_dataset": "ACCE_COA_MASTER",
    "source_column": "COA",              # in ACCE (direct numeric COA code)
    "reference_column": "ICARUS_COA",    # in ACCE_COA_MASTER
    "lookup_column": "ISO_COR / SAB",    # mappings derived from the join
}

# Statistical-threshold parameters. Same framing as A3 - percentile
# baseline plus materiality filter to suppress structural-only
# mappings.
ACCE_AC3_PERCENTILE = 0.90
ACCE_AC3_MATERIALITY_USD = 100_000.0
# Minimum number of eligible ISO mappings required before the P90 is
# computed. Below this the rule is NOT_APPLICABLE - population too
# small to call any mapping an outlier.
ACCE_AC3_MIN_MAPPING_POPULATION = 10

# Percentile-threshold customization - mirror of E3 / A3 selectbox.
# check_acce_ac3 reads ``params[ACCE_AC3_THRESHOLD_PARAM]`` and falls
# back to ``ACCE_AC3_PERCENTILE`` (P90) when the param is absent.
ACCE_AC3_THRESHOLD_PARAM = "threshold_percentile"
ACCE_AC3_THRESHOLD_CHOICES: Tuple[Tuple[float, str], ...] = (
    (0.75, "P75 - lenient"),
    (0.90, "P90 - recommended"),
    (0.95, "P95 - strict"),
    (0.99, "P99 - very strict"),
)

# Uniform 1:1 mapping detection. Unlike A3 (which flags every material
# 1:1 bucket when its toggle is on), AC3's uniform check is gated by a
# portfolio-wide proportion: when ≥ ACCE_AC3_UNIFORM_THRESHOLD of
# eligible mappings have ratio == 1, every material 1:1 bucket fails.
# The wider gate reflects that ACCE COA codes are inherently coarser,
# so a few legitimate 1:1 mappings shouldn't trip the rule.
ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM = "detect_uniform_mapping"
ACCE_AC3_UNIFORM_THRESHOLD = 0.80


# AC4: Core quantities populated & non-negative project totals (ACCE).
#
# Project-level Completeness + Validity rule with row-level verdict. For
# each ``PLANVIEW_ID`` the rule checks that (a) every core quantity type
# the project's scope implies is actually populated by at least one row,
# and (b) the project's combined quantity total
# (``SUM(KEY_QTY) + SUM(OTHER_QTY)``) is not negative. Individual rows
# may carry negative quantities (corrections / reversals); only the
# project aggregate is checked.
#
# Both scope detection and population detection key off
# ``DESCRIPTION`` - an explicit allow-list of estimate-line labels per
# core type, matched case-insensitively on ``UPPER(TRIM(DESCRIPTION))``.
# This replaced the former ``ACCT`` account-code classifier (the
# discipline codes like ``3-PIP`` / ``4-CIV`` no longer drive the rule).
# A core type is *populated* for a project when at least one row whose
# ``DESCRIPTION`` is in the type's list also carries a positive quantity
# (``KEY_QTY > 0`` OR ``OTHER_QTY > 0``) in a matching unit
# (``KEY_UNITS`` OR ``OTHER_UNITS`` in the type's UOM set). The KEY /
# OTHER quantity and unit slots are read separately rather than through
# the coalesced ``QTY_QUANTITY`` / ``QTY_UOM`` columns.
#
# Source columns on the denormalized ACCE data product (the qty child
# table is prefixed ``QTY_`` by the builder; the KEY / OTHER columns
# survive the per-``ROW_ID`` aggregation - numerics summed, units kept
# as the first non-null):
#   - ``PLANVIEW_ID``     - pass-through, the project key.
#   - ``DESCRIPTION``     - pass-through (drives scope + population).
#   - ``QTY_KEY_QTY``     - SUM of KEY_QTY per ROW_ID.
#   - ``QTY_OTHER_QTY``   - SUM of OTHER_QTY per ROW_ID.
#   - ``QTY_KEY_UNITS``   - first KEY_UNITS seen per ROW_ID.
#   - ``QTY_OTHER_UNITS`` - first OTHER_UNITS seen per ROW_ID.
ACCE_AC4_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
    "Item Description": "DESCRIPTION",
    "Key Quantity": "QTY_KEY_QTY",
    "Other Quantity": "QTY_OTHER_QTY",
    "Key Units": "QTY_KEY_UNITS",
    "Other Units": "QTY_OTHER_UNITS",
}

# DESCRIPTION → core quantity type. Both scope and population detection
# use these explicit value lists (matched on ``UPPER(TRIM(DESCRIPTION))``);
# population layers a UOM + positive-quantity constraint on top.
# MODULE_COUNT keeps a substring match (``MODULE`` / ``MODULAR``)
# instead of an exact list.
_AC4_PIPING_DESCRIPTIONS = frozenset({
    "PIPING",
    "CS PIPE ERECTION",
    "SS PIPE ERECTION",
    "KCS PIPE ERECTION",
    "NON-METAL PIPE ERECTION",
    "MISC.METAL PIPE ERECTION",
    "LINED PIPE ERECTION",
    "3.5NI PIPE ERECTION",
    "SS304 PIPE ERECTION",
    "FIREWATER PIPING",
    "INSTRUMENT PIPING",
    "PNEUMATIC TUBING",
    "AIR SUPPLY PIPING",
    "OTHER EQUIPMENT PIPE",
    "PIPELINE-FAB. & INSTALL",
    "PIPELINE MISC. PIPING",
})
_AC4_CONCRETE_DESCRIPTIONS = frozenset({
    "CONCRETE",
    "CONCRETE POUR AND FINISH",
    "OTHER EQUIP. CONCRETE",
    "FOUNDATION ACCESSORIES",
})
_AC4_STEEL_DESCRIPTIONS = frozenset({
    "STEEL",
    "STEEL STRUCTURES",
    "STEEL TOWERS",
    "STEEL TRUSSES",
    "PIPERACK STEEL",
    "TUBULAR STEEL",
    "EQUIPMENT SUPPORT STEEL",
    "SUBSTATION STEEL",
    "MISCELLANEOUS STEEL ITEM",
    "HANDRAIL AND TOEPLATE ST",
    "FABRICATED PLATE",
    "PLATFORMS",
    "LADDERS",
    "FLOORING & STAIR TREADS",
    "STEEL UNLOAD & HANDLING",
})
_AC4_CABLE_DESCRIPTIONS = frozenset({
    "ELECTRICAL",
    "WIRE/CABLE - LV",
    "WIRE/CABLE - MV",
    "WIRE/CABLE - HV",
    "WIRE/CABLE - CV",
    "WIRE/CABLE - LIGHTING",
    "CONDUIT",
    "CONDUIT & FITTINGS",
    "CONDUIT FITTINGS",
    "CABLE TRAYS",
    "UNDERGROUND CABLE DUCT",
    "BUS DUCT - MV/HV",
    "BUS DUCT - LV",
})
_AC4_INSTRUMENT_DESCRIPTIONS = frozenset({
    "INSTRUMENTATION",
    "TEMPERATURE INSTRUMENTS",
    "FLOW INSTRUMENTS",
    "LEVEL INSTRUMENTS",
    "PRESSURE INSTRUMENTS",
    "MOTION INSTRUMENTS",
    "ANALYZERS",
    "ORIFICE PLATES",
})
_AC4_EQUIPMENT_DESCRIPTIONS = frozenset({
    "CENTRIFUGAL PUMPS",
    "CENTRIFUGAL PUMPS - HIGH",
    "CENTRIFUGAL PUMPS - API",
    "CENTRIFUGAL PUMPS - ANSI",
    "CENTRIFUGAL PUMPS - CENT",
    "RECIPROCATING PUMPS",
    "SLURRY PUMPS",
    "S&T EXCHANGER",
    "S&T EXCHANGER - CS",
    "S&T EXCHANGER - KCS",
    "S&T EXCHANGER - 2.25CR",
    "MISC. HEAT EXCHANGERS",
    "DOUBLE PIPE EXCHANGERS",
    "AIR COOLER",
    "AIR COOLER - CS",
    "AIR COOLER - KCS",
    "REBOILERS",
    "REBOILERS - CS",
    "REBOILERS - KCS",
    "WASTE HEAT BOILERS",
    "COOLING TOWERS",
    "HORZ. VESSELS",
    "HORZ. VESSELS - CS",
    "HORZ. VESSELS - 316SS",
    "HORZ. VESSELS - KCS",
    "VERTICAL VESSELS",
    "VERTICAL VESSELS - CS",
    "VERTICAL VESSELS - 316SS",
    "VERTICAL VESSELS - KCS",
    "AGITATED VESSELS",
    "STORAGE VESSELS",
    "ATMOSPHERIC STORAGE TANK",
    "ATM. STORAGE TANK - CS",
    "ATM. STORAGE TANK - 316S",
    "ATM. STORAGE TANK - KCS",
    "PRESSURIZED STORAGE TANK",
    "SEPARATORS",
    "CENTRIFUGAL COMPRESSORS",
    "RECIPROCATING COMPRESSOR",
    "TURBO-EXPAND. COMPRESSOR",
    "GAS TURBINES",
    "FANS AND BLOWERS",
    "MIXERS",
    "FILTERS",
    "CENTRIFUGES",
    "DRYERS",
    "CONVEYORS",
    "EJECTORS",
    "FLARES",
    "FURNACE VERT",
    "FLUID SEPARATION EQUIP.",
    "WATER TREATING UNITS",
    "REFRIGERATION UNITS",
    "CRANES, HOISTS, ETC",
    "MATERIALS HANDLING EQUIP",
    "CRUSHERS,BREAKERS",
    "THICKENERS,CLARIFIERS",
    "PULVERIZERS",
    "MISC. PACKAGE UNITS",
    "SPECIAL EQUIPMENT ITEM",
    "SPECIAL PLANT ITEM",
    "MISCELLANEOUS EQUIPMENT",
    "OTHER EQUIPMENT ITEMS",
})

# Module scope is a substring match on ``DESCRIPTION`` (``MODULE`` /
# ``MODULAR``) rather than an exact-value list.
_AC4_MODULE_DESC_PATTERNS = ("MODULE", "MODULAR")

# UOM sets, compared against ``UPPER(TRIM(units))`` directly - no alias
# normalization, the lists carry the canonical spellings the SQL spec
# matches against (both the unicode ``M³`` and ASCII ``M3`` / ``YD3``
# forms are listed where they appear in production extracts).
_AC4_LENGTH_UOMS = frozenset({"FEET", "FT", "M", "METERS", "LF"})
_AC4_VOLUME_UOMS = frozenset({"CY", "M3", "YD3", "YDS", "M³"})
_AC4_WEIGHT_UOMS = frozenset({"TONS", "TONNE", "TON", "T"})
_AC4_COUNT_UOMS = frozenset({"EACH", "EA", "ITEM(S)", "ITEM", "ITEMS"})

# Ordered list of the seven core quantity types, same order as the
# ADR A4 list, kept identical so diagnostics line up across systems.
_AC4_CORE_QUANTITY_TYPES: Tuple[str, ...] = (
    "PIPING_LF",
    "CONCRETE_CY",
    "STEEL_TONS",
    "CABLE_LENGTH",
    "TRANSMITTER_COUNT",
    "EQUIPMENT_COUNT",
    "MODULE_COUNT",
)

# Drives both the vectorized check and the scalar classifiers. Each
# entry pairs a core type with its DESCRIPTION allow-list (``None`` for
# the MODULE substring match) and its UOM set.
_AC4_CATEGORY_SPECS: Tuple[Tuple[str, object, frozenset], ...] = (
    ("PIPING_LF", _AC4_PIPING_DESCRIPTIONS, _AC4_LENGTH_UOMS),
    ("CONCRETE_CY", _AC4_CONCRETE_DESCRIPTIONS, _AC4_VOLUME_UOMS),
    ("STEEL_TONS", _AC4_STEEL_DESCRIPTIONS, _AC4_WEIGHT_UOMS),
    ("CABLE_LENGTH", _AC4_CABLE_DESCRIPTIONS, _AC4_LENGTH_UOMS),
    ("TRANSMITTER_COUNT", _AC4_INSTRUMENT_DESCRIPTIONS, _AC4_COUNT_UOMS),
    ("EQUIPMENT_COUNT", _AC4_EQUIPMENT_DESCRIPTIONS, _AC4_COUNT_UOMS),
    ("MODULE_COUNT", None, _AC4_COUNT_UOMS),
)


# AC5: Design details present when quantity exists (ACCE).
#
# Row-level Consistency rule: a row fails only when a positive
# quantity exists *and* the item carries no usable design parameter.
# Two flags drive the verdict:
#
#   - ``HAS_QUANTITY`` - at least one split quantity slot is strictly
#     positive (``QTY_KEY_QTY > 0`` OR ``QTY_OTHER_QTY > 0``). Each is
#     the per-``ROW_ID`` SUM of ``KEY_QTY`` / ``OTHER_QTY`` from
#     ``ACCE_ESTIMATEQTYRESULTS`` (applied by the builder).
#   - ``HAS_DESIGN_DETAIL`` - the joined design row carries BOTH a
#     ``DESIGN_PROPERTY`` (the parameter name) AND a ``DESIGN_VALUE``
#     (the parameter value), each non-null and non-blank. Requiring the
#     name alongside the value answers the "120 m of what?"
#     interpretability question - a bare value with no named parameter
#     is not a usable design detail. The two columns are ``PROPERTY`` /
#     ``VALUE`` from ``ACCE_ESTIMATEDESIGNDETAILS`` (joined on
#     ``DESIGN_ID``) after the builder applies the ``DESIGN_`` prefix.
ACCE_AC5_REQUIRED_COLUMNS = {
    "Key Quantity": "QTY_KEY_QTY",
    "Other Quantity": "QTY_OTHER_QTY",
    "Design Parameter Name": "DESIGN_PROPERTY",
    "Design Parameter Value": "DESIGN_VALUE",
}


# AC6: Construction hours present when quantity exists (ACCE).
#
# One-directional Consistency rule: a row fails only when a positive
# quantity exists AND the construction-hours aggregate is not strictly
# greater than zero. Two flags drive the verdict:
#
#   - ``HAS_QUANTITY`` - at least one split quantity slot is strictly
#     positive (``QTY_KEY_QTY > 0`` OR ``QTY_OTHER_QTY > 0``). Each is
#     the per-``ROW_ID`` SUM of ``KEY_QTY`` / ``OTHER_QTY`` from
#     ``ACCE_ESTIMATEQTYRESULTS`` (applied by the builder).
#   - ``HAS_CONSTRUCTION_HOURS`` - ``COST_MH`` (sourced from ``MH`` on
#     ``ACCE_ESTIMATECOSTRESULTS``, SUM-aggregated per ``ROW_ID`` and
#     prefixed ``COST_`` by the builder) is strictly greater than zero.
#     ACCE does **not** segregate Design-Build hours into a separate
#     column, so AC6 consults only ``COST_MH``.
ACCE_AC6_REQUIRED_COLUMNS = {
    "Key Quantity": "QTY_KEY_QTY",
    "Other Quantity": "QTY_OTHER_QTY",
    "Construction Hours": "COST_MH",
}


# AC7: Within-discipline quantity / hour ratio outlier (ACCE).
#
# Per-row statistical rule. Eligible rows compute
# ``HOURS_PER_QUANTITY = COST_MH / QTY_QUANTITY``; the population is
# partitioned by ``(DESCRIPTION, QTY_UOM)`` and IQR bounds are derived
# per segment. Structural notes:
#
#   - The segment key is the *raw* ``UPPER(TRIM(DESCRIPTION))`` value
#     (the estimate-line label) paired with the effective UOM - not a
#     category mapping (unlike AC8) and no longer ``ACCT``.
#   - ``QTY_QUANTITY`` is ``COALESCE(KEY_QTY, 0) + COALESCE(OTHER_QTY,
#     0)`` from the split slots; a row is eligible when ``KEY_QTY > 0``
#     OR ``OTHER_QTY > 0``.
#   - The effective UOM is ``COALESCE(KEY_UNITS, OTHER_UNITS)`` on
#     ``UPPER(TRIM(...))``.
#   - The construction-hours column is ``COST_MH`` (sourced from
#     ``MH`` on ``ACCE_ESTIMATECOSTRESULTS``).
#   - The ``segment_by_project_type`` toggle extends the segment key
#     with the ``(E05_DEPARTMENT, BUSINESS)`` archetype via a
#     ``PLANVIEW_ID`` Planview lookup.
ACCE_AC7_REQUIRED_COLUMNS = {
    "Item Description": "DESCRIPTION",
    "Key Quantity": "QTY_KEY_QTY",
    "Other Quantity": "QTY_OTHER_QTY",
    "Key Units": "QTY_KEY_UNITS",
    "Other Units": "QTY_OTHER_UNITS",
    "Construction Hours": "COST_MH",
}

# IQR multipliers. ``MILD`` is the FAIL boundary used by the Boolean
# check; ``EXTREME`` is documented for future severity classification
# but not consulted by the rule today (every extreme outlier is also
# a mild outlier, so the mild bound is sufficient).
ACCE_AC7_MILD_IQR_MULTIPLIER = 1.5
ACCE_AC7_EXTREME_IQR_MULTIPLIER = 3.0
# Segments with fewer than this many eligible rows are
# NOT_APPLICABLE → every row in the segment passes. Mirrors A7.
ACCE_AC7_MIN_POPULATION = 10

# IQR-multiplier customization - selectbox on the rule card. The
# check reads ``params[ACCE_AC7_THRESHOLD_PARAM]`` and falls back to
# :data:`ACCE_AC7_MILD_IQR_MULTIPLIER` (1.5×) when the param is
# absent. Choices mirror A7 / A8 / E6 so the selectbox semantics stay
# in lockstep across systems.
ACCE_AC7_THRESHOLD_PARAM = "threshold_iqr_multiplier"
ACCE_AC7_THRESHOLD_CHOICES: Tuple[Tuple[float, str], ...] = (
    (1.5, "1.5×IQR (mild) - recommended"),
    (2.0, "2.0×IQR"),
    (3.0, "3.0×IQR (extreme)"),
)

# Project-type segmentation toggle for AC7, mirrors the toggle A7
# exposes against the ADR data product. When on, the per-segment IQR
# baseline used to flag outliers is partitioned by the composite
# ``(E05_DEPARTMENT, BUSINESS)`` tuple looked up from
# ``VWS_GP_STANDARD_SHARE`` via ``PLANVIEW_ID → PROJECT_ID``. The IQR
# is recomputed within each
# ``(DESCRIPTION, QTY_UOM, E05_DEPARTMENT, BUSINESS)`` bucket so a
# deepwater FPSO is not pooled with an onshore refinery when judging
# within-discipline productivity. The per-segment
# minimum-population floor (``ACCE_AC7_MIN_POPULATION``) still
# applies. Off by default, the rule keeps its
# ``(DESCRIPTION, QTY_UOM)``-only behaviour unless the user opts in.
# Rows whose segment cannot be resolved (missing PLANVIEW_ID, unmatched
# PROJECT_ID, null/blank E05_DEPARTMENT / BUSINESS) are
# NOT_APPLICABLE → PASS so the toggle never double-penalises the
# referential-integrity gap AC1 / AC2 already cover.
ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM = "segment_by_project_type"
ACCE_AC7_SEGMENT_REFERENCE = {
    "reference_dataset": "VWS_GP_STANDARD_SHARE",
    "source_column": "PLANVIEW_ID",       # in ACCE
    "reference_column": "PROJECT_ID",     # in VWS_GP_STANDARD_SHARE
    "segment_columns": ("E05_DEPARTMENT", "BUSINESS"),
}
# Extra column the rule needs when segmentation is on. Step 4.2 folds
# this into the CDE-coverage validation via
# ``required_columns_when_enabled`` (see CustomRuleOption) so the
# user is told to add PLANVIEW_ID to the CDEs when the toggle is
# enabled.
ACCE_AC7_SEGMENT_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
}


# AC8: Cross-discipline quantity ratios (ACCE).
#
# Project-level statistical rule with row-level verdict. Eligible
# positive-quantity rows are classified into six discipline categories
# off ``DESCRIPTION`` + the split unit columns (see
# :func:`_classify_ac8_category_acce`), their quantities are summed by
# ``(COMPONENT_SOURCE, category)``, and three cross-discipline ratios
# are computed per project. IQR mild bounds across the project
# population flag projects whose proportion sits outside the typical
# range.
#
# Structural notes:
#
#   - Project key is ``COMPONENT_SOURCE`` (ACCE's project-scope column).
#   - Classifier keys off ``DESCRIPTION`` (the same per-discipline
#     value lists AC4 uses) plus a per-category UOM gate read from the
#     split ``KEY_UNITS`` / ``OTHER_UNITS`` slots - replacing the
#     former ``ACCT`` + ``QTY_UOM`` classifier.
#   - Per-row quantity is ``COALESCE(KEY_QTY, 0) + COALESCE(OTHER_QTY,
#     0)``; a row is eligible when ``KEY_QTY > 0`` OR ``OTHER_QTY > 0``.
#   - The ``segment_by_project_type`` toggle partitions the per-ratio
#     IQR baseline by archetype via a ``PLANVIEW_ID`` Planview lookup.
ACCE_AC8_REQUIRED_COLUMNS = {
    "Project Scope": "COMPONENT_SOURCE",
    "Item Description": "DESCRIPTION",
    "Key Quantity": "QTY_KEY_QTY",
    "Other Quantity": "QTY_OTHER_QTY",
    "Key Units": "QTY_KEY_UNITS",
    "Other Units": "QTY_OTHER_UNITS",
}

# IQR multipliers, same shape as A8. ``MILD`` is the FAIL boundary
# used by the Boolean check; ``EXTREME`` is documented for future
# severity classification.
ACCE_AC8_MILD_IQR_MULTIPLIER = 1.5
ACCE_AC8_EXTREME_IQR_MULTIPLIER = 3.0
# Per-ratio populations with fewer eligible projects than this are
# NOT_APPLICABLE → every project on that ratio passes.
ACCE_AC8_MIN_POPULATION = 10

# IQR-multiplier customization - selectbox on the rule card. The
# check reads ``params[ACCE_AC8_THRESHOLD_PARAM]`` and falls back to
# :data:`ACCE_AC8_MILD_IQR_MULTIPLIER` (1.5×) when the param is
# absent. Choices in lockstep with A7 / A8 / E6 / AC7.
ACCE_AC8_THRESHOLD_PARAM = "threshold_iqr_multiplier"
ACCE_AC8_THRESHOLD_CHOICES: Tuple[Tuple[float, str], ...] = (
    (1.5, "1.5×IQR (mild) - recommended"),
    (2.0, "2.0×IQR"),
    (3.0, "3.0×IQR (extreme)"),
)

# Project-type segmentation toggle for AC8, mirrors the toggle A8
# exposes against the ADR data product. When on, the cross-discipline
# ratio population (one ratio value per ``COMPONENT_SOURCE``) is
# partitioned by the composite ``(E05_DEPARTMENT, BUSINESS)`` tuple
# looked up from ``VWS_GP_STANDARD_SHARE`` via
# ``PLANVIEW_ID → PROJECT_ID``. The IQR is recomputed *within each
# segment* so a deepwater FPSO is not pooled with an onshore refinery
# when judging cross-discipline shape. The per-segment
# minimum-population floor (``ACCE_AC8_MIN_POPULATION``) still
# applies. Off by default. Projects whose segment cannot be resolved
# (no associated PLANVIEW_ID, unmatched PROJECT_ID, null/blank
# E05_DEPARTMENT / BUSINESS) are NOT_APPLICABLE → PASS so the toggle
# never double-penalises the referential-integrity gap AC1 / AC2
# already cover.
ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM = "segment_by_project_type"
ACCE_AC8_SEGMENT_REFERENCE = {
    "reference_dataset": "VWS_GP_STANDARD_SHARE",
    "source_column": "PLANVIEW_ID",       # in ACCE
    "reference_column": "PROJECT_ID",     # in VWS_GP_STANDARD_SHARE
    "segment_columns": ("E05_DEPARTMENT", "BUSINESS"),
}
ACCE_AC8_SEGMENT_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
}

# AC8-specific UOM sets, compared against ``UPPER(TRIM(units))``
# directly (no alias normalization, matching the SQL's
# ``KEY_UNITS IN (...) OR OTHER_UNITS IN (...)`` comparison). AC8's
# volume set admits the bare ``YD`` spelling where AC4's admits ``YDS``;
# length / weight / count carry the same spellings as AC4's but are kept
# as their own sets so a future AC4 edit cannot silently move AC8.
_AC8_LENGTH_UOMS = frozenset({"FEET", "FT", "M", "METERS", "LF"})
_AC8_VOLUME_UOMS = frozenset({"CY", "M3", "YD3", "YD", "M³"})
_AC8_WEIGHT_UOMS = frozenset({"TONS", "TONNE", "TON", "T"})
_AC8_COUNT_UOMS = frozenset({"EACH", "EA", "ITEM", "ITEMS", "ITEM(S)"})

# AC8 equipment DESCRIPTION allow-list. Identical to AC4's equipment
# list except the AC8 SQL spec spells the turbo-expander compressor
# ``TURBO-EXPAND, COMPRESSOR`` (comma) where AC4 uses a period, so the
# list is spelled out here rather than reusing AC4's. The other five
# discipline lists are byte-identical to AC4's and are reused directly
# in ``_AC8_CATEGORY_SPECS`` below.
_AC8_EQUIPMENT_DESCRIPTIONS = frozenset({
    "CENTRIFUGAL PUMPS",
    "CENTRIFUGAL PUMPS - HIGH",
    "CENTRIFUGAL PUMPS - API",
    "CENTRIFUGAL PUMPS - ANSI",
    "CENTRIFUGAL PUMPS - CENT",
    "RECIPROCATING PUMPS",
    "SLURRY PUMPS",
    "S&T EXCHANGER",
    "S&T EXCHANGER - CS",
    "S&T EXCHANGER - KCS",
    "S&T EXCHANGER - 2.25CR",
    "MISC. HEAT EXCHANGERS",
    "DOUBLE PIPE EXCHANGERS",
    "AIR COOLER",
    "AIR COOLER - CS",
    "AIR COOLER - KCS",
    "REBOILERS",
    "REBOILERS - CS",
    "REBOILERS - KCS",
    "WASTE HEAT BOILERS",
    "COOLING TOWERS",
    "HORZ. VESSELS",
    "HORZ. VESSELS - CS",
    "HORZ. VESSELS - 316SS",
    "HORZ. VESSELS - KCS",
    "VERTICAL VESSELS",
    "VERTICAL VESSELS - CS",
    "VERTICAL VESSELS - 316SS",
    "VERTICAL VESSELS - KCS",
    "AGITATED VESSELS",
    "STORAGE VESSELS",
    "ATMOSPHERIC STORAGE TANK",
    "ATM. STORAGE TANK - CS",
    "ATM. STORAGE TANK - 316S",
    "ATM. STORAGE TANK - KCS",
    "PRESSURIZED STORAGE TANK",
    "SEPARATORS",
    "CENTRIFUGAL COMPRESSORS",
    "RECIPROCATING COMPRESSOR",
    "TURBO-EXPAND, COMPRESSOR",
    "GAS TURBINES",
    "FANS AND BLOWERS",
    "MIXERS",
    "FILTERS",
    "CENTRIFUGES",
    "DRYERS",
    "CONVEYORS",
    "EJECTORS",
    "FLARES",
    "FURNACE VERT",
    "FLUID SEPARATION EQUIP.",
    "WATER TREATING UNITS",
    "REFRIGERATION UNITS",
    "CRANES, HOISTS, ETC",
    "MATERIALS HANDLING EQUIP",
    "CRUSHERS,BREAKERS",
    "THICKENERS,CLARIFIERS",
    "PULVERIZERS",
    "MISC. PACKAGE UNITS",
    "SPECIAL EQUIPMENT ITEM",
    "SPECIAL PLANT ITEM",
    "MISCELLANEOUS EQUIPMENT",
    "OTHER EQUIPMENT ITEMS",
})

# ACCE discipline classifier. Each tuple pairs a category with its
# DESCRIPTION allow-list and its eligible UOM set. The piping / concrete
# / steel / cable / instrument lists are the same taxonomy AC4 keys off
# (both rules compare ``UPPER(TRIM(DESCRIPTION))``), so they are reused;
# equipment uses AC8's own comma-variant list.
_AC8_CATEGORY_SPECS: Tuple[Tuple[str, frozenset, frozenset], ...] = (
    ("STEEL_WEIGHT",      _AC4_STEEL_DESCRIPTIONS,      _AC8_WEIGHT_UOMS),
    ("CONCRETE_VOLUME",   _AC4_CONCRETE_DESCRIPTIONS,   _AC8_VOLUME_UOMS),
    ("PIPE_LENGTH",       _AC4_PIPING_DESCRIPTIONS,     _AC8_LENGTH_UOMS),
    ("CABLE_LENGTH",      _AC4_CABLE_DESCRIPTIONS,      _AC8_LENGTH_UOMS),
    ("TRANSMITTER_COUNT", _AC4_INSTRUMENT_DESCRIPTIONS, _AC8_COUNT_UOMS),
    ("EQUIPMENT_COUNT",   _AC8_EQUIPMENT_DESCRIPTIONS,  _AC8_COUNT_UOMS),
)

# Cross-discipline ratios evaluated per project, same shape as A8.
# Each entry is ``ratio_name → (numerator_category, denominator_category)``.
# Adding a new ratio is a one-line change here once the underlying
# categories are produced by ``_classify_ac8_category_acce``.
_AC8_RATIOS: Dict[str, Tuple[str, str]] = {
    "PIPE_LENGTH_PER_EQUIPMENT_COUNT": ("PIPE_LENGTH", "EQUIPMENT_COUNT"),
    "CABLE_LENGTH_PER_TRANSMITTER_COUNT": ("CABLE_LENGTH", "TRANSMITTER_COUNT"),
    "STEEL_WEIGHT_PER_CONCRETE_VOLUME": ("STEEL_WEIGHT", "CONCRETE_VOLUME"),
}


def check_acce_ac1(df: pd.DataFrame) -> pd.Series:
    """AC1: ISO Code of Account Present (COR + SAB) for ACCE.

    Mirrors :func:`check_adr_a1` against the ACCE schema. Each ACCE
    estimate item row carries the Code of Account directly in the
    ``COA`` field (a numeric code), so unlike ADR the rule does not need
    to extract a leading dot-separated segment - ``COA`` is joined as-is
    to ``ACCE_COA_MASTER.ICARUS_COA`` and the resolved ``ISO_COR`` /
    ``SAB`` are checked for validity.

    Row passes when **all three** hold:

    1. ``COA`` is non-null and non-blank.
    2. ``COA`` resolves to a valid ``ISO_COR`` in the master.
    3. ``COA`` resolves to a valid ``SAB`` in the master.

    The master may carry multiple rows per ``ICARUS_COA`` (one per
    detailed sub-code); :func:`_resolve_coa_master_lookups` picks the
    best-available mapping (preferring valid over ``ERROR`` / ``NULL``
    rows), same semantics as A1.

    Raises :class:`CustomRuleNotEvaluated` when the reference dataset is
    unavailable, so the rule never silently passes when the join target
    is missing.
    """
    from src.reference_data import (
        get_reference_dataset,
        get_reference_dataset_error,
    )

    if "COA" not in df.columns or "PLANVIEW_ID" not in df.columns:
        return pd.Series(False, index=df.index)

    ref_name = ACCE_AC1_REFERENCE["reference_dataset"]
    reference_df = get_reference_dataset(ref_name)
    if reference_df is None:
        cached_error = get_reference_dataset_error(ref_name)
        detail = f": {cached_error}" if cached_error else ""
        raise CustomRuleNotEvaluated(
            f"ACCE AC1: '{ref_name}' reference dataset is unavailable{detail}; "
            "ISO_COR / SAB linkage cannot be validated."
        )

    if (
        "ICARUS_COA" not in reference_df.columns
        or "ISO_COR" not in reference_df.columns
        or "SAB" not in reference_df.columns
    ):
        return pd.Series(False, index=df.index)

    coa = df["COA"]
    coa_filled = _is_filled(coa)
    # ACCE source data carries 4-character COA codes (e.g. ``3131``,
    # ``6320``) that roll up to a 3-character ``ICARUS_COA`` group in
    # the COA master (e.g. ``313``, ``632``). Take the first three
    # characters as the lookup key, the analog of ADR's
    # ``SPLIT_PART(COMPLETE_WBC, '.', 1)`` derivation. Stringify +
    # strip both sides so numeric / string column dtypes line up.
    coa_key = coa.astype(object).astype(str).str.strip().str[:3]

    iso_lookup, sab_lookup = _resolve_coa_master_lookups(reference_df)

    iso_resolved = coa_key.map(iso_lookup)
    sab_resolved = coa_key.map(sab_lookup)

    iso_ok = _a1_value_valid(iso_resolved)
    sab_ok = _a1_value_valid(sab_resolved)
    return coa_filled & iso_ok & sab_ok


def check_acce_ac2(df: pd.DataFrame) -> pd.Series:
    """AC2: Location + Estimate Date Present & Valid (ACCE).

    Mirrors :func:`check_adr_a2` against the ACCE data product. Row
    passes when *all* hold:

    - ``JOB_NO`` (estimate job / period, used as the estimate-date proxy
      in ACCE) is non-null and non-blank (**Completeness**).
    - ``JOB_NO`` matches the fiscal quarter-year token ``[1-4]Q<YY>``
      with an optional whitespace-separated revision suffix - e.g.
      ``2Q23 RP1``, ``2Q24``, ``2Q25``, ``4Q23`` (**Validity**). The
      check is structural, not an enum, so newly-ingested quarters/years
      pass automatically; a populated-but-malformed value (e.g. ``2023``,
      ``Q2-23``, ``5Q23``) fails even though it satisfies completeness.
    - ``COUNTRY`` (project location) is non-null and non-blank in the
      Planview reference after joining ``ACCE.PLANVIEW_ID =
      VWS_GP_STANDARD_SHARE.PROJECT_ID``. An unmatched ``PLANVIEW_ID``
      is treated as a missing ``COUNTRY``.

    Raises :class:`CustomRuleNotEvaluated` when the reference dataset
    is unavailable, so the rule never silently passes when the join
    target is missing.
    """
    from src.reference_data import (
        get_reference_dataset,
        get_reference_dataset_error,
    )

    if "JOB_NO" not in df.columns or "PLANVIEW_ID" not in df.columns:
        return pd.Series(False, index=df.index)

    ref_name = ACCE_AC2_REFERENCE["reference_dataset"]
    reference_df = get_reference_dataset(ref_name)
    if reference_df is None:
        cached_error = get_reference_dataset_error(ref_name)
        detail = f": {cached_error}" if cached_error else ""
        raise CustomRuleNotEvaluated(
            f"ACCE AC2: '{ref_name}' reference dataset is unavailable{detail}; "
            "COUNTRY linkage cannot be validated."
        )

    # Completeness: the estimate job / period is populated.
    job_no_filled = _is_filled(df["JOB_NO"])
    # Validity: the populated value starts with the fiscal quarter-year
    # token (optional revision suffix). A filled but malformed value fails.
    job_no_valid = (
        df["JOB_NO"]
        .astype(str)
        .str.strip()
        .str.fullmatch(ACCE_AC2_JOB_NO_PATTERN, case=False)
        .fillna(False)
    )
    job_no_ok = job_no_filled & job_no_valid

    ref_col = ACCE_AC2_REFERENCE["reference_column"]
    lookup_col = ACCE_AC2_REFERENCE["lookup_column"]
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
    return job_no_ok & country_ok


def check_acce_ac3(
    df: pd.DataFrame, params: ACCEAC3Params | None = None
) -> pd.Series:
    """AC3: Statistical COA-to-ISO mapping ratio (ACCE).

    Mapping-quality statistical rule with row-level verdict. Mirrors
    :func:`check_adr_a3` against the ACCE schema, with two notable
    differences:

    1. The per-bucket metric is ``COUNT(DISTINCT COA)`` (not
       ``COUNT(DISTINCT COMPLETE_WBC)``). ACCE stores the Code of
       Account directly in ``COA`` and joins it to
       ``ACCE_COA_MASTER.ICARUS_COA`` without splitting a WBC string.
    2. The optional uniform-1:1 detector is gated by a portfolio-wide
       proportion: when ≥ :data:`ACCE_AC3_UNIFORM_THRESHOLD` (default
       80 %) of eligible mappings have ratio == 1, every material 1:1
       bucket fails. A3 flags every material 1:1 bucket unconditionally
       when its toggle is on, which is a stricter signal. AC3's wider
       gate reflects that ACCE COA codes are inherently coarser.

    Row passes when its ``(ISO_COR, SAB)`` bucket is not flagged. Every
    NOT_APPLICABLE row also passes:

    - ``COA`` missing or unmapped - AC1's territory.
    - Resolved ``ISO_COR`` / ``SAB`` invalid - AC1's territory.
    - Eligible-mapping population below
      :data:`ACCE_AC3_MIN_MAPPING_POPULATION` - too few buckets to
      derive a P90.
    - Bucket not material.

    ``params[ACCE_AC3_THRESHOLD_PARAM]`` (float in (0, 1], default
    :data:`ACCE_AC3_PERCENTILE` = 0.90) customizes the percentile
    threshold, see :data:`ACCE_AC3_THRESHOLD_CHOICES`.

    ``params[ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM]`` (bool, default
    False) enables the uniform-detection branch.

    Raises :class:`CustomRuleNotEvaluated` when the COA master is
    unavailable so the rule never silently passes when its dependency
    is missing.
    """
    p = params or {}
    detect_uniform = p.get(ACCE_AC3_DETECT_UNIFORM_MAPPING_PARAM, False)
    percentile = _coerce_threshold(
        p.get(ACCE_AC3_THRESHOLD_PARAM), ACCE_AC3_PERCENTILE
    )
    required = list(ACCE_AC3_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    from src.reference_data import (
        get_reference_dataset,
        get_reference_dataset_error,
    )

    ref_name = ACCE_AC3_REFERENCE["reference_dataset"]
    reference_df = get_reference_dataset(ref_name)
    if reference_df is None:
        cached_error = get_reference_dataset_error(ref_name)
        detail = f": {cached_error}" if cached_error else ""
        raise CustomRuleNotEvaluated(
            f"ACCE AC3: '{ref_name}' reference dataset is unavailable{detail}; "
            "ISO_COR / SAB cannot be resolved."
        )

    if (
        "ICARUS_COA" not in reference_df.columns
        or "ISO_COR" not in reference_df.columns
        or "SAB" not in reference_df.columns
    ):
        return pd.Series(False, index=df.index)

    iso_lookup, sab_lookup = _resolve_coa_master_lookups(reference_df)

    coa = df["COA"]
    coa_filled = _is_filled(coa)
    # ACCE source data carries 4-character COA codes that roll up to a
    # 3-character ``ICARUS_COA`` group in the master. Use the first
    # three characters as the lookup key (same as AC1) but keep the
    # full COA value for the per-bucket ``COUNT(DISTINCT COA)`` -
    # otherwise multiple distinct 4-char COAs sharing a 3-char prefix
    # would collapse to a single key and the aggregation metric would
    # always read as 1 per (ISO_COR, SAB) bucket.
    coa_str = coa.astype(object).astype(str).str.strip()
    coa_key = coa_str.str[:3]
    iso_resolved = coa_key.map(iso_lookup)
    sab_resolved = coa_key.map(sab_lookup)
    has_valid_mapping = (
        coa_filled
        & _a1_value_valid(iso_resolved)
        & _a1_value_valid(sab_resolved)
    )
    if not has_valid_mapping.any():
        return pd.Series(True, index=df.index)

    hours = pd.to_numeric(df["COST_MH"], errors="coerce").fillna(0.0)
    cost = pd.to_numeric(df["COST_TOTAL_COST"], errors="coerce").fillna(0.0)

    iso_norm = iso_resolved.astype(object).astype(str).str.strip()
    sab_norm = sab_resolved.astype(object).astype(str).str.strip()
    group_id = pd.Series(
        list(zip(iso_norm, sab_norm)), index=df.index, dtype=object
    )
    group_id = group_id.where(has_valid_mapping)

    eligible_idx = df.index[has_valid_mapping]
    work = pd.DataFrame({
        "_gid": group_id.loc[eligible_idx],
        # Use the *full* (untruncated) COA so each distinct 4-char value
        # contributes to the bucket's COUNT(DISTINCT COA).
        "_coa": coa_str.loc[eligible_idx],
        "_hours": hours.loc[eligible_idx],
        "_cost": cost.loc[eligible_idx],
    })

    grouped = work.groupby("_gid", dropna=True, sort=False)
    metrics = pd.DataFrame({
        "ratio": grouped["_coa"].nunique(dropna=True),
        "hours_sum": grouped["_hours"].sum(),
        "cost_sum": grouped["_cost"].sum(),
    })
    eligible_groups = metrics["ratio"] >= 1
    if eligible_groups.sum() < ACCE_AC3_MIN_MAPPING_POPULATION:
        # Population too small to define a meaningful P90, every row
        # passes, mirroring the spec's "insufficient population" branch.
        return pd.Series(True, index=df.index)

    global_p = float(
        metrics.loc[eligible_groups, "ratio"].quantile(percentile)
    )

    metrics["material"] = (
        (metrics["hours_sum"] > 0)
        | (metrics["cost_sum"] >= ACCE_AC3_MATERIALITY_USD)
    )
    outlier_fail = (
        (metrics["ratio"].to_numpy() > global_p)
        & metrics["material"].to_numpy()
    )
    if detect_uniform:
        # Portfolio-wide uniform-mapping detector: trip only when
        # ≥ ACCE_AC3_UNIFORM_THRESHOLD of eligible mappings have
        # ratio == 1 (i.e. the ISO classification is effectively just
        # relabeling COA codes 1:1 across the whole portfolio). When
        # tripped, every *material* 1:1 bucket fails. OR'd with the
        # percentile fail; materiality still gates both branches.
        eligible_ratios = metrics.loc[eligible_groups, "ratio"]
        uniform_share = float((eligible_ratios == 1).mean())
        if uniform_share >= ACCE_AC3_UNIFORM_THRESHOLD:
            uniform_fail = (
                (metrics["ratio"].to_numpy() == 1)
                & metrics["material"].to_numpy()
            )
            metrics["fail"] = outlier_fail | uniform_fail
        else:
            metrics["fail"] = outlier_fail
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


def _ac4_qty_positive(value: object) -> bool:
    """True when ``value`` coerces to a number strictly greater than 0.
    Null / blank / non-numeric inputs are treated as not-populated."""
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _classify_ac4_scope_acce(description: object) -> set:
    """Return the set of AC4 core quantity types implied by an item's
    ``DESCRIPTION`` *alone*, i.e. before looking at units or quantity.
    Used to compute the project-level ``EXPECTS_*`` flags. Matching is
    case-insensitive against the per-type ``DESCRIPTION`` allow-lists
    (MODULE_COUNT is a ``MODULE`` / ``MODULAR`` substring match)."""
    scopes: set = set()
    desc = "" if description is None else str(description).strip().upper()
    if not desc:
        return scopes
    for cat, descriptions, _uom in _AC4_CATEGORY_SPECS:
        if descriptions is None:  # MODULE_COUNT - substring match
            if any(pat in desc for pat in _AC4_MODULE_DESC_PATTERNS):
                scopes.add(cat)
        elif desc in descriptions:
            scopes.add(cat)
    return scopes


def _classify_ac4_quantity_acce(
    description: object,
    key_units: object,
    other_units: object,
    key_qty: object,
    other_qty: object,
) -> object:
    """Classify a single denormalized qty row into one of AC4's seven
    core quantity types, or ``None`` when it does not *populate* any
    type. A row populates a type when its ``DESCRIPTION`` is in the
    type's allow-list (MODULE: ``MODULE`` / ``MODULAR`` substring), at
    least one of ``KEY_QTY`` / ``OTHER_QTY`` is strictly positive, and
    at least one of ``KEY_UNITS`` / ``OTHER_UNITS`` is in the type's
    UOM set."""
    if not (_ac4_qty_positive(key_qty) or _ac4_qty_positive(other_qty)):
        return None
    desc = "" if description is None else str(description).strip().upper()
    ku = "" if key_units is None else str(key_units).strip().upper()
    ou = "" if other_units is None else str(other_units).strip().upper()
    for cat, descriptions, uom in _AC4_CATEGORY_SPECS:
        if descriptions is None:  # MODULE_COUNT - substring match
            in_scope = any(pat in desc for pat in _AC4_MODULE_DESC_PATTERNS)
        else:
            in_scope = desc in descriptions
        if in_scope and (ku in uom or ou in uom):
            return cat
    return None


def check_acce_ac4(df: pd.DataFrame) -> pd.Series:
    """AC4: Core quantities populated & non-negative project totals (ACCE).

    Project-level Completeness + Validity rule with row-level verdict.
    For each ``PLANVIEW_ID`` the rule:

    1. determines the project's *expected* core quantity types from the
       per-row scope classification (``DESCRIPTION`` allow-lists);
    2. determines the project's *populated* core quantity types from the
       per-row quantity classification (``DESCRIPTION`` in the type's
       list AND a positive ``KEY_QTY`` / ``OTHER_QTY`` AND a matching
       ``KEY_UNITS`` / ``OTHER_UNITS``);
    3. flags the project when any expected type lacks a populated row;
    4. flags the project when its combined quantity total
       (``SUM(KEY_QTY) + SUM(OTHER_QTY)`` across the project) is
       *negative*. Individual rows may legitimately carry negative
       quantities (corrections / reversals) - only the project aggregate
       is checked, and a total of exactly zero passes.

    Row-level verdict: a row **fails** iff its ``PLANVIEW_ID`` is
    flagged. Rows whose project is unknown (null/blank ``PLANVIEW_ID``)
    pass, they cannot be assigned to a project group.

    Schema-level missing column → all rows fail (same convention as
    the other custom rules).
    """
    required = list(ACCE_AC4_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    pv = df["PLANVIEW_ID"]
    project_filled = _is_filled(pv)
    if not project_filled.any():
        return pd.Series(True, index=df.index)

    pv_norm = pv.astype(object).astype(str).str.strip().where(project_filled)
    desc_upper = (
        df["DESCRIPTION"].astype(object).astype(str).str.strip().str.upper()
    )
    key_qty = pd.to_numeric(df["QTY_KEY_QTY"], errors="coerce").fillna(0.0)
    other_qty = pd.to_numeric(df["QTY_OTHER_QTY"], errors="coerce").fillna(0.0)
    qty_pos = (key_qty > 0) | (other_qty > 0)
    key_u = (
        df["QTY_KEY_UNITS"].astype(object).astype(str).str.strip().str.upper()
    )
    other_u = (
        df["QTY_OTHER_UNITS"].astype(object).astype(str).str.strip().str.upper()
    )

    # Per-category scope (DESCRIPTION) and population (DESCRIPTION + qty
    # + UOM) flags, evaluated independently - a row can contribute to
    # more than one core type, exactly as the SQL's per-category MAX().
    flags = {"_pv": pv_norm}
    for cat, descriptions, uom in _AC4_CATEGORY_SPECS:
        if descriptions is None:  # MODULE_COUNT - substring match
            in_scope = (
                desc_upper.str.contains("MODULE", regex=False, na=False)
                | desc_upper.str.contains("MODULAR", regex=False, na=False)
            )
        else:
            in_scope = desc_upper.isin(descriptions)
        uom_match = key_u.isin(uom) | other_u.isin(uom)
        flags[f"e_{cat}"] = in_scope
        flags[f"h_{cat}"] = in_scope & qty_pos & uom_match

    fl = pd.DataFrame(flags).dropna(subset=["_pv"])
    proj = fl.groupby("_pv", dropna=True, sort=False).any()
    project_fail = pd.Series(False, index=proj.index)
    for cat, _descriptions, _uom in _AC4_CATEGORY_SPECS:
        project_fail = project_fail | (proj[f"e_{cat}"] & ~proj[f"h_{cat}"])

    # Project-level quantity sanity (Validity): the combined KEY + OTHER
    # quantity total per project must not be negative. Row-level negatives
    # are allowed; only the project aggregate fails.
    qty_by_project = (
        pd.DataFrame({"_pv": pv_norm, "_q": key_qty + other_qty})
        .dropna(subset=["_pv"])
        .groupby("_pv", sort=False)["_q"]
        .sum()
    )
    project_fail = project_fail | (qty_by_project.reindex(proj.index) < 0)

    failing_projects = set(project_fail[project_fail].index)
    if not failing_projects:
        return pd.Series(True, index=df.index)

    in_failing = (
        pv_norm.isin(failing_projects).fillna(False).astype(bool)
    )
    return ~in_failing


def check_acce_ac5(df: pd.DataFrame) -> pd.Series:
    """AC5: Design details present when quantity exists (ACCE).

    Row-level Consistency rule. For each estimate item (one row per
    ``ROW_ID`` in the denormalized data product) the rule derives
    two flags:

    - ``HAS_QUANTITY``     - at least one split quantity slot is
      strictly positive (``QTY_KEY_QTY > 0`` OR ``QTY_OTHER_QTY > 0``).
      Each is the per-``ROW_ID`` SUM of ``KEY_QTY`` / ``OTHER_QTY``
      from ``ACCE_ESTIMATEQTYRESULTS`` (applied by the data-product
      builder). A null / zero / negative quantity in both slots counts
      as "no quantity".
    - ``HAS_DESIGN_DETAIL`` - the item's design row carries BOTH a
      populated ``DESIGN_PROPERTY`` (parameter name) AND a populated
      ``DESIGN_VALUE`` (parameter value), each non-null and non-blank.
      The source columns are ``PROPERTY`` / ``VALUE`` from
      ``ACCE_ESTIMATEDESIGNDETAILS``, joined on ``DESIGN_ID``; the
      builder applies the ``DESIGN_`` prefix.

    A row fails only when a positive quantity exists but no usable
    design detail (named parameter + value) is present, the gap that
    prevents the quantity from being interpreted, normalized, or
    compared.

    Pass / fail matrix:

    +--------------+-------------------+-------------+
    | HAS_QUANTITY | HAS_DESIGN_DETAIL | RULE_RESULT |
    +==============+===================+=============+
    |       0      |        0          |    PASS     |
    |       0      |        1          |    PASS     |
    |       1      |        0          |    FAIL     |
    |       1      |        1          |    PASS     |
    +--------------+-------------------+-------------+

    Missing required column → all rows fail (structural
    incompleteness, same convention as the other custom rules).
    """
    required = list(ACCE_AC5_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    key_qty = pd.to_numeric(df["QTY_KEY_QTY"], errors="coerce").fillna(0.0)
    other_qty = pd.to_numeric(df["QTY_OTHER_QTY"], errors="coerce").fillna(0.0)
    has_quantity = (key_qty > 0) | (other_qty > 0)
    has_design_detail = (
        _is_filled(df["DESIGN_PROPERTY"]) & _is_filled(df["DESIGN_VALUE"])
    )
    return (~has_quantity) | has_design_detail


def check_acce_ac6(df: pd.DataFrame) -> pd.Series:
    """AC6: Construction hours present when quantity exists (ACCE).

    Row-level Consistency rule. For each estimate item the rule checks
    two derived flags:

    - ``HAS_QUANTITY`` - at least one split quantity slot is strictly
      positive (``QTY_KEY_QTY > 0`` OR ``QTY_OTHER_QTY > 0``). Each is
      the per-``ROW_ID`` SUM of ``KEY_QTY`` / ``OTHER_QTY``. A null /
      zero / negative quantity in both slots counts as "no quantity".
    - ``HAS_CONSTRUCTION_HOURS``  - ``COST_MH`` is strictly greater
      than zero. Null inputs are coerced to zero; negative
      aggregates do **not** count as hours present, so the
      comparison is ``> 0`` (not ``!= 0``). Unlike A6, ACCE has no
      separate Design-Build hours column, the rule consults only
      ``COST_MH``.

    Pass / fail matrix:

    +--------------+------------------------+-------------+
    | HAS_QUANTITY | HAS_CONSTRUCTION_HOURS | RULE_RESULT |
    +==============+========================+=============+
    |       0      |           0            |    PASS     |
    |       0      |           1            |    PASS     |
    |       1      |           0            |    FAIL     |
    |       1      |           1            |    PASS     |
    +--------------+------------------------+-------------+

    The rule is **one-directional**: hours without a quantity is
    allowed (PASS). Only quantity-without-hours fails. Missing
    required column → all rows fail (structural incompleteness, same
    convention as the other custom rules).
    """
    required = list(ACCE_AC6_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    key_qty = pd.to_numeric(df["QTY_KEY_QTY"], errors="coerce").fillna(0.0)
    other_qty = pd.to_numeric(df["QTY_OTHER_QTY"], errors="coerce").fillna(0.0)
    mh = pd.to_numeric(df["COST_MH"], errors="coerce").fillna(0.0)

    has_quantity = (key_qty > 0) | (other_qty > 0)
    # Strictly > 0 so negative aggregates don't count as hours present.
    has_construction_hours = mh > 0
    return (~has_quantity) | has_construction_hours


def check_acce_ac7(
    df: pd.DataFrame, params: ACCEAC7Params | None = None
) -> pd.Series:
    """AC7: Within-discipline quantity / hour ratio outlier (ACCE).

    Per-row Statistical Outlier rule. Eligible rows
    (``KEY_QTY > 0`` OR ``OTHER_QTY > 0``; AND ``COST_MH > 0``; AND a
    non-blank ``DESCRIPTION`` and effective UOM) compute
    ``HOURS_PER_QUANTITY = COST_MH / QTY_QUANTITY`` where
    ``QTY_QUANTITY = COALESCE(KEY_QTY, 0) + COALESCE(OTHER_QTY, 0)``.
    The eligible population is partitioned by ``(DESCRIPTION, QTY_UOM)``
    - the raw ``UPPER(TRIM(DESCRIPTION))`` value paired with the
    effective UOM ``COALESCE(KEY_UNITS, OTHER_UNITS)`` - and IQR bounds
    are derived per segment:

    - ``Q1 = quantile(0.25)``, ``Q3 = quantile(0.75)``,
      ``IQR = Q3 - Q1``.
    - ``MILD_LOWER = Q1 - k * IQR``, ``MILD_UPPER = Q3 + k * IQR``
      (where ``k`` defaults to :data:`ACCE_AC7_MILD_IQR_MULTIPLIER`
      and is customizable via ``params``).

    A row **fails** when its ratio is below the mild lower bound or
    above the mild upper bound. Every other case is treated as PASS:

    - Ratio cannot be calculated (no positive quantity, or hours
      missing / zero / negative) - AC6 already covers the
      missing-hours case for positive quantities.
    - ``DESCRIPTION`` or the effective UOM is null/blank, no segment
      to compare against.
    - Segment population (eligible-row count) is below
      :data:`ACCE_AC7_MIN_POPULATION` - too small to define an
      outlier.
    - Segment ``IQR == 0``, no variation across the segment, every
      observation sits on the median; outlier detection is not
      meaningful.

    ``params[ACCE_AC7_THRESHOLD_PARAM]`` (float > 0, default
    :data:`ACCE_AC7_MILD_IQR_MULTIPLIER` = 1.5) customizes the IQR
    multiplier; larger values widen the PASS band, see
    :data:`ACCE_AC7_THRESHOLD_CHOICES` for the values surfaced in
    Step 4.2.

    ``params[ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM]`` (bool, default
    False) extends the segment key with a composite
    ``(E05_DEPARTMENT, BUSINESS)`` tuple looked up from
    ``VWS_GP_STANDARD_SHARE`` via ``PLANVIEW_ID → PROJECT_ID``
    (mirrors the A7 toggle). With it on the IQR is recomputed within
    each ``(DESCRIPTION, QTY_UOM, E05_DEPARTMENT, BUSINESS)`` bucket so
    a deepwater FPSO is not pooled with an onshore refinery when
    judging within-discipline productivity. Segments below
    :data:`ACCE_AC7_MIN_POPULATION` remain NOT_APPLICABLE → PASS.
    Rows whose segment cannot be resolved (missing PLANVIEW_ID,
    unmatched PROJECT_ID, or null/blank ``E05_DEPARTMENT`` /
    ``BUSINESS``) are also NOT_APPLICABLE → PASS - AC1 / AC2 already
    cover the referential gap. Raises
    :class:`CustomRuleNotEvaluated` when the toggle is on and the
    reference dataset is unavailable.

    Schema-level missing columns make every row fail, mirroring the
    convention used by the other custom rules.
    """
    p = params or {}
    iqr_multiplier = _coerce_threshold(
        p.get(ACCE_AC7_THRESHOLD_PARAM),
        ACCE_AC7_MILD_IQR_MULTIPLIER,
    )
    segmented = p.get(ACCE_AC7_SEGMENT_BY_PROJECT_TYPE_PARAM, False)

    required = list(ACCE_AC7_REQUIRED_COLUMNS.values())
    if segmented:
        required = required + list(ACCE_AC7_SEGMENT_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    key_qty = pd.to_numeric(df["QTY_KEY_QTY"], errors="coerce").fillna(0.0)
    other_qty = pd.to_numeric(df["QTY_OTHER_QTY"], errors="coerce").fillna(0.0)
    qty = key_qty + other_qty
    hours = pd.to_numeric(df["COST_MH"], errors="coerce")
    description = df["DESCRIPTION"]
    key_units = df["QTY_KEY_UNITS"]
    other_units = df["QTY_OTHER_UNITS"]

    # Effective UOM = COALESCE(KEY_UNITS, OTHER_UNITS), uppercased.
    key_u = key_units.astype(object).astype(str).str.strip().str.upper()
    other_u = other_units.astype(object).astype(str).str.strip().str.upper()
    key_units_filled = _is_filled(key_units)
    uom_norm = key_u.where(key_units_filled, other_u)
    uom_filled = key_units_filled | _is_filled(other_units)

    desc_norm = description.astype(object).astype(str).str.strip().str.upper()

    # Eligibility: ratio is defined AND we have a segment to compare to.
    eligible = (
        ((key_qty > 0) | (other_qty > 0))
        & (hours > 0)
        & _is_filled(description)
        & uom_filled
    )
    if not eligible.any():
        return pd.Series(True, index=df.index)

    ratio = pd.Series(np.nan, index=df.index, dtype=float)
    ratio.loc[eligible] = (
        hours.loc[eligible].to_numpy() / qty.loc[eligible].to_numpy()
    )

    # Build the per-row segment key as a *DataFrame* so the groupby below
    # can use pandas' C-fast multi-column path instead of grouping on a
    # Series of Python tuples.
    gid_frame = pd.DataFrame(
        {"_desc": desc_norm, "_uom": uom_norm}, index=df.index
    )
    gid_cols: List[str] = ["_desc", "_uom"]

    if segmented:
        # Extend the segment key with the project-type tuple resolved
        # via PLANVIEW_ID. Rows whose project-type cannot be resolved
        # become NOT_APPLICABLE → PASS, mirrors A7's segmented
        # convention.
        segment_lookup = _resolve_planview_segment_map(
            ACCE_AC7_SEGMENT_REFERENCE, "ACCE AC7"
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

        # Pre-cleaning in ``_resolve_planview_segment_map`` guarantees
        # ``dept_seg.notna() ⟺ business_seg.notna()``; we AND both for
        # clarity, matching the A7 implementation.
        resolved = dept_seg.notna() & business_seg.notna()
        eligible = eligible & resolved
        if not eligible.any():
            return pd.Series(True, index=df.index)
        gid_frame["_dept"] = dept_seg
        gid_frame["_business"] = business_seg
        gid_cols = ["_desc", "_uom", "_dept", "_business"]

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
        (stats["count"] >= ACCE_AC7_MIN_POPULATION) & (stats["iqr"] > 0)
    )

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


def _classify_ac8_category_acce(
    description: object, key_units: object, other_units: object
) -> object:
    """Classify a single (``DESCRIPTION``, ``KEY_UNITS``, ``OTHER_UNITS``)
    row into one of AC8's six discipline categories, or ``None`` when the
    row is not eligible for any ratio.

    A row classifies when its ``DESCRIPTION`` is in a category's
    allow-list AND at least one of ``KEY_UNITS`` / ``OTHER_UNITS`` is in
    that category's UOM set (all compared on ``UPPER(TRIM(...))``). The
    six discipline allow-lists are disjoint, so the first match is the
    only match. Rows whose description / units satisfy no category
    contribute to no ratio.
    """
    desc = "" if description is None else str(description).strip().upper()
    if not desc:
        return None
    ku = "" if key_units is None else str(key_units).strip().upper()
    ou = "" if other_units is None else str(other_units).strip().upper()
    for category, descriptions, uom in _AC8_CATEGORY_SPECS:
        if desc in descriptions and (ku in uom or ou in uom):
            return category
    return None


def check_acce_ac8(
    df: pd.DataFrame, params: ACCEAC8Params | None = None
) -> pd.Series:
    """AC8: Cross-discipline quantity ratios (ACCE).

    Project-level Statistical Outlier rule with row-level verdict.
    For each ``COMPONENT_SOURCE`` the rule classifies eligible
    positive-quantity rows into discipline categories (PIPE_LENGTH,
    EQUIPMENT_COUNT, CABLE_LENGTH, TRANSMITTER_COUNT, STEEL_WEIGHT,
    CONCRETE_VOLUME) off ``DESCRIPTION`` + the split unit columns (see
    :func:`_classify_ac8_category_acce`), aggregates the quantities
    (``COALESCE(KEY_QTY, 0) + COALESCE(OTHER_QTY, 0)``), and computes
    three cross-discipline ratios:

    - ``PIPE_LENGTH / EQUIPMENT_COUNT``
    - ``CABLE_LENGTH / TRANSMITTER_COUNT``
    - ``STEEL_WEIGHT / CONCRETE_VOLUME``

    For each ratio the population is the set of projects with a
    calculable ratio. IQR mild bounds (``Q1 - k·IQR`` …
    ``Q3 + k·IQR``) are derived from that population, and a project
    is flagged for that ratio when its ratio falls outside the bounds.

    Row-level verdict: a row **fails** iff its ``COMPONENT_SOURCE`` is
    flagged on at least one ratio. Rows whose project is unknown
    (null/blank ``COMPONENT_SOURCE``) pass, they cannot be assigned to a
    project group.

    NOT_APPLICABLE → PASS for:

    - Population for a given ratio below
      :data:`ACCE_AC8_MIN_POPULATION` (too few projects to derive
      thresholds).
    - Population ``IQR == 0`` (no variation across projects).
    - Project's ratio cannot be calculated (numerator or denominator
      sum is zero - discipline simply not present at the right grain).

    ``params[ACCE_AC8_THRESHOLD_PARAM]`` (float > 0, default
    :data:`ACCE_AC8_MILD_IQR_MULTIPLIER` = 1.5) customizes the IQR
    multiplier, see :data:`ACCE_AC8_THRESHOLD_CHOICES` for the
    values surfaced in Step 4.2.

    ``params[ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM]`` (bool, default
    False) partitions the per-ratio IQR baseline by the composite
    ``(E05_DEPARTMENT, BUSINESS)`` tuple looked up from
    ``VWS_GP_STANDARD_SHARE`` via ``PLANVIEW_ID → PROJECT_ID``
    (mirrors the A8 toggle). With it on, each project is tagged with
    its archetype from the Planview reference and the IQR for each
    ratio is recomputed within each segment, so a deepwater FPSO is
    not pooled with an onshore refinery. Per-segment populations
    below :data:`ACCE_AC8_MIN_POPULATION` remain NOT_APPLICABLE →
    PASS. Projects whose segment cannot be resolved (no associated
    PLANVIEW_ID, unmatched PROJECT_ID, or null/blank
    ``E05_DEPARTMENT`` / ``BUSINESS``) are also NOT_APPLICABLE → PASS
    - AC1 / AC2 already cover those gaps. Raises
    :class:`CustomRuleNotEvaluated` when the toggle is on and the
    reference dataset is unavailable.

    Schema-level missing column → all rows fail (same convention as
    the other custom rules).
    """
    p = params or {}
    iqr_multiplier = _coerce_threshold(
        p.get(ACCE_AC8_THRESHOLD_PARAM),
        ACCE_AC8_MILD_IQR_MULTIPLIER,
    )
    segmented = p.get(ACCE_AC8_SEGMENT_BY_PROJECT_TYPE_PARAM, False)

    required = list(ACCE_AC8_REQUIRED_COLUMNS.values())
    if segmented:
        required = required + list(ACCE_AC8_SEGMENT_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    # Per-row quantity is COALESCE(KEY_QTY, 0) + COALESCE(OTHER_QTY, 0);
    # a row is eligible when either slot is strictly positive.
    key_qty = pd.to_numeric(df["QTY_KEY_QTY"], errors="coerce").fillna(0.0)
    other_qty = pd.to_numeric(df["QTY_OTHER_QTY"], errors="coerce").fillna(0.0)
    qty = key_qty + other_qty
    description = df["DESCRIPTION"]
    key_units = df["QTY_KEY_UNITS"]
    other_units = df["QTY_OTHER_UNITS"]
    project = df["COMPONENT_SOURCE"]

    project_norm = project.astype(object).astype(str).str.strip()
    project_filled = _is_filled(project)

    # Per-row eligibility for ratio aggregation: positive quantity in
    # either slot, a project key, a description, and at least one unit.
    eligible = (
        ((key_qty > 0) | (other_qty > 0))
        & project_filled
        & _is_filled(description)
        & (_is_filled(key_units) | _is_filled(other_units))
    )
    if not eligible.any():
        return pd.Series(True, index=df.index)

    # Discipline classification - vectorised over the eligible slice.
    eligible_idx = df.index[eligible]
    categories = pd.Series(
        [
            _classify_ac8_category_acce(desc, ku, ou)
            for desc, ku, ou in zip(
                description.loc[eligible_idx],
                key_units.loc[eligible_idx],
                other_units.loc[eligible_idx],
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
    # ``proj_segment`` maps ``COMPONENT_SOURCE → (E05_DEPARTMENT, BUSINESS)``.
    # Projects with no associated PLANVIEW_ID, an unmatched PROJECT_ID,
    # or a null/blank segment component fall out of the dict entirely
    # and are treated as NOT_APPLICABLE → PASS below. Pre-cleaning in
    # ``_resolve_planview_segment_map`` keeps the per-project lookup at
    # one dict-get.
    proj_segment: Dict[str, Tuple[str, str]] = {}
    if segmented:
        segment_lookup = _resolve_planview_segment_map(
            ACCE_AC8_SEGMENT_REFERENCE, "ACCE AC8"
        )
        # Pick the first non-blank PLANVIEW_ID per COMPONENT_SOURCE. A
        # project should normally have a single PLANVIEW_ID across all
        # its rows, but if there are stragglers we still take the first
        # populated value - AC1 / AC2 already cover the missing-PLANVIEW
        # completeness gap, so AC8 only needs *some* anchor to resolve
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
    for _, (num_cat, den_cat) in _AC8_RATIOS.items():
        if num_cat not in proj_cat.columns or den_cat not in proj_cat.columns:
            continue
        num = proj_cat[num_cat]
        den = proj_cat[den_cat]
        # SQL uses ``NULLIF(den, 0)`` - a ratio is calculable as long as
        # the denominator is non-zero; ``num = 0`` is a legitimate
        # data point (``0/5 = 0``) and contributes to the population
        # and percentile baseline.
        ratio_eligible = den > 0
        if not ratio_eligible.any():
            continue
        ratios = num[ratio_eligible] / den[ratio_eligible]

        if segmented:
            # Drop projects whose segment couldn't be resolved, they
            # are NOT_APPLICABLE → PASS in segmented mode. Then
            # compute the IQR within each resolved segment with the
            # same minimum-population floor.
            seg_index = pd.Series(
                [proj_segment.get(proj) for proj in ratios.index],
                index=ratios.index,
                dtype=object,
            )
            resolved = seg_index.notna()
            if not resolved.any():
                continue
            ratios_resolved = ratios[resolved]
            for _seg_key, seg_ratios in ratios_resolved.groupby(
                seg_index[resolved]
            ):
                if len(seg_ratios) < ACCE_AC8_MIN_POPULATION:
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
            if ratio_eligible.sum() < ACCE_AC8_MIN_POPULATION:
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
    # failing set. Rows with null/blank COMPONENT_SOURCE pass.
    in_failing = (
        project_norm.where(project_filled).isin(failing_projects)
        .fillna(False)
        .astype(bool)
    )
    return ~in_failing


