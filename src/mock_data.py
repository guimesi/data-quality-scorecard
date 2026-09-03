# pyright: reportArgumentType=false, reportCallIssue=false
"""
Generator of synthetic data that mimics the real ADR / ACCE / EPT schema.

Grain reference:
 - Project level ............ PLANVIEW_ID     (~50 projects)
 - Item level ............... ROW_ID          (~300 items, one per primary row)
 - Cost/qty results ......... 1:N per ROW_ID  (~4 result rows per item)

Mock data includes *deliberate* quality issues to exercise every DQR:
 - null PLANVIEW_IDs
 - duplicated ROW_IDs in primary tables (PK violations)
 - null values in key metrics
 - out-of-range costs / quantities
 - stale / future-dated timestamps
 - invalid classification codes
 - excess decimal places

Used when DATA_SOURCE=mock. Do NOT rely on it outside of demo/dev.
"""
from __future__ import annotations

import zlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# Module-level RNG. The import-time constants below (``_ITEM_ROW_IDS``,
# ``_ITEM_DESIGN_ID``, ``_ITEM_UOM`` ...) draw from it once, in a fixed order,
# so they are stable. ``fetch_mock_table`` then *reseeds* this generator per
# table name before each build (see there), so every fetch of a given table
# returns identical content regardless of call order - the generator is shared
# and stateful, so without that reseed the same table returned different data
# on each call.
_MOCK_BASE_SEED = 42
RNG = np.random.default_rng(seed=_MOCK_BASE_SEED)

# Reference "now" for the relative date columns (e.g. LAST_REPORTED_AT),
# captured ONCE at import. Using ``datetime.now()`` inline made every build of
# the same table differ by microseconds, so ``fetch_mock_table`` was not
# byte-identical across calls; freezing it here keeps date columns stable per
# call (and keeps them recent relative to the run, so date-relative rules still
# see realistic lags).
_MOCK_NOW = datetime.now()


def _reseed_rng_for(name: str) -> None:
    """Reset the shared module RNG to a deterministic, per-name state.

    The RNG is shared and stateful, so a builder that draws from it is only
    pure if the generator starts from the same place every call. Reseeding from
    a stable hash of ``name`` (``zlib.crc32``, NOT the salted built-in ``hash``)
    makes each builder a pure function of its name, independent of how many
    other builders ran before it. Used by both ``fetch_mock_table`` (system
    tables) and the mock reference-dataset builders.
    """
    global RNG
    RNG = np.random.default_rng(
        seed=_MOCK_BASE_SEED ^ zlib.crc32(name.encode("utf-8"))
    )

# Grain sizes
N_PROJECTS = 50          # unique PLANVIEW_IDs
N_ITEMS = 300            # unique ROW_IDs in primary tables (= ~6 per project)
RESULTS_PER_ITEM = 4     # average child rows per ROW_ID in cost/qty tables


# =============================================================================
# Shared keys
# =============================================================================

def _build_planview_id_pool() -> List[str]:
    """Pool of PLANVIEW_IDs used across all systems (cross-system linking)."""
    return [f"PV-{i:05d}" for i in range(1, N_PROJECTS + 1)]


def _assign_planview_id_to_items(planview_id_pool: List[str]) -> List:
    """Assign a PLANVIEW_ID to each of the N_ITEMS item rows (~6 items/project),
    injecting ~3% nulls to simulate missing project linkage."""
    assigned = RNG.choice(planview_id_pool, size=N_ITEMS).astype(object).tolist()
    null_idx = RNG.choice(N_ITEMS, size=int(0.03 * N_ITEMS), replace=False)
    for i in null_idx:
        assigned[i] = None
    return assigned


def _build_row_ids() -> List[str]:
    """One ROW_ID per estimate item. Injects a handful of duplicates to
    exercise Uniqueness rule violations on what should be a PK."""
    base = [f"ROW-{i:06d}" for i in range(1, N_ITEMS + 1)]
    # Inject 4 duplicate ROW_IDs (PK violation)
    dup_targets = RNG.choice(N_ITEMS, size=5, replace=False)
    for i in dup_targets[:-1]:
        base[i] = base[dup_targets[-1]]
    return base


# Build once so all mock tables share consistent keys
_PLANVIEW_ID_POOL: List[str] = _build_planview_id_pool()
_ITEM_PLANVIEW_ID: List = _assign_planview_id_to_items(_PLANVIEW_ID_POOL)
_ITEM_ROW_IDS: List[str] = _build_row_ids()
# Populated by ``_mock_acce_estimateitemrecord`` so the qty-mock
# generator can correlate ``QTY_UOM`` with the parent item's ``ACCT``
# (used by AC4). Defaults to an empty dict - falsy when AC4-relevant
# mocks haven't been requested, so callers can opt out cleanly.
_ITEM_ACCT: Dict[str, str] = {}


def _assign_item_types() -> List:
    """Assign an ``ITEM_TYPE`` to each estimate item (~5% nulls). The pool
    is small and weighted so a handful of dominant types get enough
    population in the (ITEM_TYPE, QTY_UOM) segmentation A7 uses for IQR
    outlier detection. The names mirror the production "Estimate*"
    labels referenced by the A8 cross-discipline classifier so demo
    mode can also exercise that rule."""
    types = [
        "EstimateFoundation",
        "EstimateStructuralSteel",
        "EstimateAbovegroundInstrumentPiping",
        "EstimateElectricalPowerGroup",
        "EstimateBuriedCablingGroup",
    ]
    weights = [0.30, 0.22, 0.20, 0.15, 0.13]
    assigned = RNG.choice(types, size=N_ITEMS, p=weights).astype(object).tolist()
    null_idx = RNG.choice(N_ITEMS, size=max(1, int(0.05 * N_ITEMS)), replace=False)
    for i in null_idx:
        assigned[i] = None
    return assigned


def _assign_root_item_names() -> List:
    """Assign a ``ROOT_ITEM_NAME`` to each estimate item, the project /
    scope grouping key A8 uses to aggregate cross-discipline quantities.
    A small pool concentrates the population per project so the IQR
    population test for A8 has enough samples in mock mode."""
    names = [f"PROJECT-{i:03d}" for i in range(1, 21)]   # 20 projects
    assigned = RNG.choice(names, size=N_ITEMS).astype(object).tolist()
    null_idx = RNG.choice(N_ITEMS, size=max(1, int(0.04 * N_ITEMS)), replace=False)
    for i in null_idx:
        assigned[i] = None
    return assigned


def _assign_component_sources() -> List:
    """Assign a ``COMPONENT_SOURCE`` to each ACCE estimate item - the
    project-scope grouping key AC8 aggregates cross-discipline
    quantities by. A small pool concentrates the population per scope so
    AC8's per-ratio IQR population floor has enough samples in mock mode.
    A few nulls give AC8 real NOT_APPLICABLE rows."""
    sources = [f"COMP-{i:03d}" for i in range(1, 21)]   # 20 component sources
    assigned = RNG.choice(sources, size=N_ITEMS).astype(object).tolist()
    null_idx = RNG.choice(N_ITEMS, size=max(1, int(0.04 * N_ITEMS)), replace=False)
    for i in null_idx:
        assigned[i] = None
    return assigned


def _assign_item_uoms() -> List[str]:
    """Assign a UOM to each estimate item - used by the QTY child mock to
    keep all of an item's quantity rows on the same UOM (real estimates
    almost always do). Without this, the data product builder's "first"
    aggregation would surface a near-random UOM per ROW_ID and shatter the
    A7 segmentation. The pool is intentionally small and weighted to
    concentrate population per (ITEM_TYPE, UOM) segment."""
    uoms = ["CY", "T", "M", "FT"]
    weights = [0.32, 0.24, 0.24, 0.20]
    return RNG.choice(uoms, size=N_ITEMS, p=weights).astype(object).tolist()


_ITEM_TYPE: List = _assign_item_types()
_ITEM_UOM: List[str] = _assign_item_uoms()
_ITEM_ROOT_NAME: List = _assign_root_item_names()
_ITEM_COMPONENT_SOURCE: List = _assign_component_sources()


# ACCE design dimension - keyed by DESIGN_ID (not ROW_ID). Multiple item
# records may reference the same design (standardised equipment), so the
# pool is intentionally smaller than N_ITEMS. ~6% of items have a null
# DESIGN_ID to exercise the unmatched-left-join path.
_N_DESIGNS = 80
_DESIGN_ID_POOL: List[str] = [f"DSN-{i:05d}" for i in range(1, _N_DESIGNS + 1)]


def _assign_design_ids() -> List:
    assigned = RNG.choice(_DESIGN_ID_POOL, size=N_ITEMS).astype(object).tolist()
    null_idx = RNG.choice(N_ITEMS, size=max(1, int(0.06 * N_ITEMS)), replace=False)
    for i in null_idx:
        assigned[i] = None
    return assigned


_ITEM_DESIGN_ID: List = _assign_design_ids()
# Lookup used by the QTY child generator so child rows for a given ROW_ID
# all share the parent's UOM. ``_build_row_ids`` injects a few duplicate
# ROW_IDs to exercise Uniqueness violations; the duplicate keys collapse
# here (last write wins), which is fine, the duplicate rows aren't the
# realism case we're trying to model.
_UOM_BY_ROW_ID: Dict[str, str] = dict(zip(_ITEM_ROW_IDS, _ITEM_UOM))


# =============================================================================
# ADR - primary + cost results + qty results
# =============================================================================

def _mock_adr_dim_estimateitemrecord() -> pd.DataFrame:
    n = N_ITEMS
    estimate_classes = ["CLASS_1", "CLASS_2", "CLASS_3", "CLASS_4", "CLASS_5", "BAD"]
    statuses = ["DRAFT", "APPROVED", "LOCKED", "ARCHIVED", "UNKNOWN"]
    # COST_UPDATE is a fiscal quarter-year period in prod (e.g. "2Q2019"),
    # not a calendar date - A2 checks both Completeness and that the value
    # matches the [1-4]Q<YYYY> shape (Validity).
    cost_update = [
        f"{int(RNG.integers(1, 5))}Q{int(RNG.integers(2015, 2025))}"
        for _ in range(n)
    ]
    # Inject ~5% null COST_UPDATE so A2 has estimate-basis-date gaps to flag
    # (Completeness), plus ~2% malformed values so A2's Validity branch has
    # something to flag too (e.g. "5Q2019", "2019", "Q2-2019").
    cost_update_null_idx = RNG.choice(n, size=max(1, int(0.05 * n)), replace=False)
    for i in cost_update_null_idx:
        cost_update[i] = None
    _bad_cost_update_pool = ["5Q2019", "2019", "Q2-2019", "2Q19"]
    cost_update_bad_idx = RNG.choice(
        [i for i in range(n) if i not in set(cost_update_null_idx)],
        size=max(1, int(0.02 * n)),
        replace=False,
    )
    for i in cost_update_bad_idx:
        cost_update[i] = _bad_cost_update_pool[int(RNG.integers(0, len(_bad_cost_update_pool)))]
    # COMPLETE_WBC drives A1 (ISO COR + SAB lookup). Most rows reference
    # COA groups present in the ACCE_COA_MASTER mock; ~3% are null/blank
    # and ~5% reference an "orphan" COA group (no master row → A1 FAIL).
    valid_coa_pool = [
        "311", "312", "313", "314", "317", "318", "321", "322",
        "323", "324", "325", "326", "327", "328", "329", "330",
    ]
    error_coa_pool = [
        "315",   # ISO_COR has 'ERROR: #N/A' in master → A1 FAIL
        "316",   # SAB has 'ERROR: #N/A' in master    → A1 FAIL
        "319",   # ISO_COR is NULL in master          → A1 FAIL
        "320",   # SAB is NULL in master              → A1 FAIL
    ]
    orphan_coa_pool = ["909", "888"]   # not in ACCE_COA_MASTER → A1 FAIL
    coa_choices = (
        [(g, 0.85 / len(valid_coa_pool)) for g in valid_coa_pool]
        + [(g, 0.10 / len(error_coa_pool)) for g in error_coa_pool]
        + [(g, 0.05 / len(orphan_coa_pool)) for g in orphan_coa_pool]
    )
    coa_groups, coa_weights = zip(*coa_choices)
    chosen_coa = RNG.choice(coa_groups, size=n, p=coa_weights)
    complete_wbc = [
        f"{coa}.{int(RNG.integers(0, 9))}.{int(RNG.integers(1, 30))}.{int(RNG.integers(1, 30))}"
        for coa in chosen_coa
    ]
    null_wbc_idx = RNG.choice(n, size=max(1, int(0.03 * n)), replace=False)
    for i in null_wbc_idx:
        complete_wbc[i] = None
    df = pd.DataFrame({
        "ROW_ID": _ITEM_ROW_IDS,
        "PLANVIEW_ID": _ITEM_PLANVIEW_ID,
        "ITEM_TYPE": _ITEM_TYPE,
        "ROOT_ITEM_NAME": _ITEM_ROOT_NAME,
        "COMPLETE_WBC": complete_wbc,
        "ESTIMATE_CLASS": RNG.choice(estimate_classes, size=n, p=[0.2, 0.25, 0.25, 0.15, 0.1, 0.05]),
        "ITEM_DESCRIPTION": [f"ADR estimate item {i}" for i in range(1, n + 1)],
        "ITEM_STATUS": RNG.choice(statuses, size=n, p=[0.25, 0.45, 0.2, 0.05, 0.05]),
        "BASE_DATE": [
            datetime(2024, 1, 1) + timedelta(days=int(RNG.integers(0, 500)))
            for _ in range(n)
        ],
        "COST_UPDATE": cost_update,
        "CREATED_AT": [
            datetime(2023, 1, 1) + timedelta(days=int(RNG.integers(0, 900)))
            for _ in range(n)
        ],
        "LAST_UPDATED_AT": [
            _MOCK_NOW - timedelta(days=int(RNG.integers(0, 900)))
            for _ in range(n)
        ],
    })
    return df


def _explode_children(row_ids: List[str], avg_per_parent: int = RESULTS_PER_ITEM) -> List[str]:
    """Return a list of ROW_IDs (with repetition) for child-table rows.
    Each parent has a random count around `avg_per_parent`."""
    out: List[str] = []
    for rid in row_ids:
        k = int(max(1, RNG.integers(avg_per_parent - 1, avg_per_parent + 3)))
        out.extend([rid] * k)
    return out


def _mock_adr_fact_estimatecostresults() -> pd.DataFrame:
    parent_ids = _ITEM_ROW_IDS
    exploded = _explode_children(parent_ids)
    n = len(exploded)
    df = pd.DataFrame({
        "ROW_ID": exploded,
        "COST_TYPE": RNG.choice(["LABOR", "MATERIAL", "EQUIPMENT", "SUBCONTRACT"], size=n),
        "CURRENCY": RNG.choice(["USD", "EUR", "GBP", "CAD", "XXX"], size=n, p=[0.5, 0.25, 0.1, 0.1, 0.05]),
        "COST_AMOUNT": RNG.lognormal(mean=13, sigma=1.3, size=n).round(6),  # excess decimals
        "ESCALATION_PCT": RNG.uniform(-5, 15, size=n).round(2),
        # Construction hours - drives A6. Lognormal so the bulk of rows have
        # positive hours and a minority of items end up with both hours
        # columns at zero (FAIL when their quantity is non-zero).
        "TOTAL_HOURS": RNG.lognormal(mean=3.5, sigma=1.0, size=n).round(2),
        "DB_TOTAL_HOURS": RNG.lognormal(mean=3.0, sigma=1.0, size=n).round(2),
        # TOTAL_COST - separate from COST_AMOUNT so A3's materiality
        # filter (SUM(TOTAL_COST) >= threshold) operates on the
        # spec-named column without conflating with the existing
        # currency-tagged COST_AMOUNT.
        "TOTAL_COST": RNG.lognormal(mean=11.0, sigma=1.2, size=n).round(2),
    })
    # Inject ~5% nulls in COST_AMOUNT
    null_idx = RNG.choice(n, size=int(0.05 * n), replace=False)
    df.loc[null_idx, "COST_AMOUNT"] = np.nan
    # Zero-out both hours columns on ~6% of cost rows so a chunk of items
    # end up with HAS_CONSTRUCTION_HOURS = 0 → A6 has real FAIL cases
    # whenever the matching QTY row has a non-zero quantity.
    zero_hours_idx = RNG.choice(n, size=max(1, int(0.06 * n)), replace=False)
    df.loc[zero_hours_idx, "TOTAL_HOURS"] = 0.0
    df.loc[zero_hours_idx, "DB_TOTAL_HOURS"] = 0.0
    # Null patterns on each hours column independently - exercises the
    # "either-or" branch of A6 (one column null, the other populated).
    null_total_idx = RNG.choice(n, size=max(1, int(0.04 * n)), replace=False)
    df.loc[null_total_idx, "TOTAL_HOURS"] = np.nan
    null_db_idx = RNG.choice(n, size=max(1, int(0.04 * n)), replace=False)
    df.loc[null_db_idx, "DB_TOTAL_HOURS"] = np.nan
    return df


def _mock_adr_fact_estimateqtyresults() -> pd.DataFrame:
    parent_ids = _ITEM_ROW_IDS
    exploded = _explode_children(parent_ids)
    n = len(exploded)
    # All child rows for the same parent share the parent's UOM - drives
    # the (ITEM_TYPE, QTY_UOM) segmentation A7 needs to find populations
    # large enough for IQR outlier detection. Falls back to "EA" only if
    # the lookup misses (shouldn't happen unless mock keys diverge).
    row_uoms = [_UOM_BY_ROW_ID.get(rid, "EA") for rid in exploded]
    df = pd.DataFrame({
        "ROW_ID": exploded,
        "COMMODITY_CODE": RNG.choice(["COM-A", "COM-B", "COM-C", "COM-D", None], size=n, p=[0.3, 0.3, 0.2, 0.15, 0.05]),
        "UOM": row_uoms,
        "QUANTITY": RNG.lognormal(mean=4, sigma=1.5, size=n).round(3),
        "UNIT_RATE": RNG.lognormal(mean=6, sigma=0.8, size=n).round(4),
    })
    # Inject some negative quantities (impossible → fails Accuracy)
    bad_idx = RNG.choice(n, size=int(0.02 * n), replace=False)
    df.loc[bad_idx, "QUANTITY"] = -df.loc[bad_idx, "QUANTITY"]
    return df


def _mock_adr_dim_estimatedesigndetails() -> pd.DataFrame:
    """Engineering design parameters per estimate item. 1:1 with the primary
    table on ROW_ID. Includes deliberate gaps (null specs, out-of-range
    values) so DQRs targeting the design table have failures to detect."""
    n = N_ITEMS
    materials = ["CS", "SS-304", "SS-316", "DUPLEX", "INCONEL", "UNK"]
    services = ["GAS", "OIL", "WATER", "STEAM", "MIXED"]
    design_codes = ["ASME-B31.3", "ASME-B31.4", "ASME-B31.8", "API-650", "BAD-CODE"]
    # Free-text design parameter (e.g. material grade, schedule, nominal size).
    # Drives A5: row passes when populated, fails when null/blank and a non-zero
    # quantity exists for the same ROW_ID.
    parameter_values = [
        f"PARAM-{int(RNG.integers(1, 999)):03d}" for _ in range(n)
    ]
    df = pd.DataFrame({
        "ROW_ID": _ITEM_ROW_IDS,
        "DESIGN_PRESSURE_BAR": RNG.uniform(1, 250, size=n).round(2),
        "DESIGN_TEMPERATURE_C": RNG.uniform(-50, 600, size=n).round(1),
        "MATERIAL_SPEC": RNG.choice(materials, size=n, p=[0.35, 0.2, 0.2, 0.1, 0.1, 0.05]),
        "SERVICE_TYPE": RNG.choice(services, size=n),
        "DIAMETER_MM": RNG.choice([50, 100, 150, 200, 300, 500, 800, 1200], size=n),
        "WALL_THICKNESS_MM": RNG.uniform(3, 50, size=n).round(2),
        "CORROSION_ALLOWANCE_MM": RNG.uniform(0, 6, size=n).round(2),
        "DESIGN_CODE": RNG.choice(design_codes, size=n, p=[0.4, 0.2, 0.2, 0.15, 0.05]),
        "DESIGN_PARAMETER_VALUE": parameter_values,
    })
    # Inject ~4% nulls in MATERIAL_SPEC and ~3% in DESIGN_PRESSURE_BAR
    null_mat_idx = RNG.choice(n, size=int(0.04 * n), replace=False)
    df.loc[null_mat_idx, "MATERIAL_SPEC"] = None
    null_pres_idx = RNG.choice(n, size=int(0.03 * n), replace=False)
    df.loc[null_pres_idx, "DESIGN_PRESSURE_BAR"] = np.nan
    # Inject ~8% null + ~3% blank/whitespace DESIGN_PARAMETER_VALUE so A5 has
    # real FAIL cases in mock mode (quantity is non-zero for ~all rows).
    null_param_idx = RNG.choice(n, size=max(1, int(0.08 * n)), replace=False)
    df.loc[null_param_idx, "DESIGN_PARAMETER_VALUE"] = None
    blank_pool = [i for i in range(n) if i not in set(null_param_idx)]
    blank_param_idx = RNG.choice(
        blank_pool, size=max(1, int(0.03 * n)), replace=False
    )
    df.loc[blank_param_idx, "DESIGN_PARAMETER_VALUE"] = "   "
    return df


# =============================================================================
# ACCE - primary + cost results + qty results
# =============================================================================

def _mock_acce_estimateitemrecord() -> pd.DataFrame:
    n = N_ITEMS
    phases = ["FEL1", "FEL2", "FEL3", "EXEC", "CLOSE", "UNK"]
    # COA pool - drives AC1 / AC3. ACCE source data carries 4-character
    # COA codes that roll up to a 3-character ``ICARUS_COA`` group in
    # the master (e.g. ``3131`` → ``313``). The pool below mirrors that
    # shape: most rows pick a 4-char COA whose 3-char prefix is a valid
    # ICARUS_COA in the mock master, plus a handful of "error-marker" /
    # orphan prefixes and nulls / blanks so every FAIL path (missing
    # COA, orphan COA, COA resolving to invalid ISO_COR or SAB) is
    # exercised in mock mode. AC3 also benefits from the 4-char
    # granularity - multiple distinct 4-char COAs sharing a 3-char
    # prefix contribute to the bucket's ``COUNT(DISTINCT COA)``.
    coa_pool = [
        # Valid 4-char COAs whose 3-char prefix resolves cleanly.
        "3110", "3111",
        "3120", "3121",
        "3130", "3131", "3132",          # extras share prefix 313 → AC3 ratio
        "3140", "3141",
        "3170", "3171",
        "3180", "3181",
        "3210", "3211",
        "3220", "3221",
        "3230", "3231",
        "3240", "3241",
        "3250", "3251",
        "3260", "3261",
        "3270", "3271",
        "3280", "3281",
        "3290", "3291",
        "3300", "3301",
        # 3-char prefixes that resolve to invalid ISO_COR / SAB in master.
        "3150",  # invalid ISO_COR (prefix 315)
        "3160",  # invalid SAB     (prefix 316)
        "3190",  # null ISO_COR    (prefix 319)
        "3200",  # null SAB        (prefix 320)
        # Orphan - prefix 999 has no master row.
        "9999",
    ]
    # JOB_NO drives AC2 - estimate job / period used as the
    # estimate-basis-date proxy in ACCE. Most rows are populated with a
    # valid quarter-period label; the null/blank pool below gives AC2
    # real "missing estimate date" FAIL cases (mirrors COST_UPDATE in
    # the ADR mock). The pool reflects the live values (quarter +
    # optional revision suffix) and may grow as new periods are ingested.
    job_no_pool = ["2Q23 RP1", "2Q24", "2Q25", "4Q23"]
    job_no = list(RNG.choice(job_no_pool, size=n))
    # ACCT is the mock's internal discipline generator key - it seeds
    # the per-discipline ``DESCRIPTION`` pools below (and the UOM
    # correlation in the qty child table) but is NOT emitted as a data
    # product column: AC4 / AC7 / AC8 classify off ``DESCRIPTION`` and no
    # rule reads ACCT, so it stays a local generator variable only.
    # Weights skew toward equipment / piping / civil / steel, the
    # disciplines that dominate the production portfolio - so AC4 mostly
    # sees full-scope projects (every core type expected) and mock-mode
    # FAIL cases come from the random UOM distribution in the qty child
    # table not always matching the discipline's expected unit family.
    acct_pool = [
        "2-EQP",     # equipment count
        "3-PIP",     # piping LF
        "4-CIV",     # civil - concrete / foundations DESCRIPTION pool
        "5-STL",     # steel tons
        "6-INST",    # instrument / transmitter count
        "7-ELC",     # electrical / cable length
        "8-OTHER",   # off-pattern; draws DESCRIPTIONs AC4 ignores
    ]
    acct_weights = [0.20, 0.20, 0.18, 0.14, 0.10, 0.12, 0.06]
    acct = list(RNG.choice(acct_pool, size=n, p=acct_weights))
    # DESCRIPTION - estimate-line label. AC4 classifies scope +
    # population off ``DESCRIPTION`` (an explicit per-discipline
    # allow-list of canonical labels) and AC7 segments by the raw
    # ``(DESCRIPTION, UOM)`` value, so each row draws a label from its
    # discipline's pool - with the discipline's *dominant* label
    # (pool[0]) carrying ~80% of the rows so AC7's per-description
    # segments clear the population floor in mock mode. ``8-OTHER``
    # rows draw off-pattern labels AC4 ignores (no core type implied).
    # A sparse fraction of equipment rows draw a MODULE / MODULAR
    # label - they keep the equipment discipline's count UOM so module
    # scope can be populated - mirroring the spec note that ACCE rarely
    # carries module-scope items.
    desc_pool_by_acct = {
        "2-EQP": [
            "CENTRIFUGAL PUMPS", "RECIPROCATING PUMPS", "S&T EXCHANGER",
            "AIR COOLER", "HORZ. VESSELS", "VERTICAL VESSELS",
            "STORAGE VESSELS", "GAS TURBINES", "FANS AND BLOWERS",
        ],
        "3-PIP": [
            "PIPING", "CS PIPE ERECTION", "SS PIPE ERECTION",
            "FIREWATER PIPING", "INSTRUMENT PIPING",
        ],
        "4-CIV": [
            "CONCRETE", "CONCRETE POUR AND FINISH",
            "FOUNDATION ACCESSORIES", "OTHER EQUIP. CONCRETE",
        ],
        "5-STL": [
            "STEEL", "STEEL STRUCTURES", "PIPERACK STEEL",
            "PLATFORMS", "LADDERS",
        ],
        "6-INST": [
            "INSTRUMENTATION", "FLOW INSTRUMENTS", "PRESSURE INSTRUMENTS",
            "TEMPERATURE INSTRUMENTS", "LEVEL INSTRUMENTS",
        ],
        "7-ELC": [
            "ELECTRICAL", "WIRE/CABLE - LV", "WIRE/CABLE - MV",
            "CONDUIT", "CABLE TRAYS",
        ],
    }
    desc_pool_offpattern = [
        "SITE PREPARATION", "GENERAL WORKS", "TEMPORARY FACILITIES",
    ]
    desc_pool_module = ["PROCESS MODULE", "MODULAR SKID"]
    description = []
    for i in range(n):
        a = acct[i]
        if a == "2-EQP" and RNG.random() < 0.08:
            description.append(RNG.choice(desc_pool_module))
        else:
            pool = desc_pool_by_acct.get(a, desc_pool_offpattern)
            # Concentrate on the discipline's dominant label so AC7's
            # per-(DESCRIPTION, UOM) segments are well-populated; the
            # remainder spreads across the rest of the pool for variety.
            if a in desc_pool_by_acct and RNG.random() < 0.8:
                description.append(pool[0])
            else:
                description.append(RNG.choice(pool))
    # Stash ACCT per ROW_ID so the qty-mock generator can optionally
    # correlate UOM with the parent discipline (used below to produce
    # at least one populated quantity per project / discipline pair).
    global _ITEM_ACCT
    _ITEM_ACCT = dict(zip(_ITEM_ROW_IDS, acct))
    df = pd.DataFrame({
        "ROW_ID": _ITEM_ROW_IDS,
        "PLANVIEW_ID": _ITEM_PLANVIEW_ID,
        "DESIGN_ID": _ITEM_DESIGN_ID,
        "COA": RNG.choice(coa_pool, size=n),
        "JOB_NO": job_no,
        "DESCRIPTION": description,
        # ``PROJECT_NAME`` reuses the shared ``_ITEM_ROOT_NAME``
        # assignment so ACCE and ADR refer to the same logical projects
        # across systems.
        "PROJECT_NAME": _ITEM_ROOT_NAME,
        # ``COMPONENT_SOURCE`` is AC8's project-scope grouping key, used
        # to aggregate cross-discipline quantities into the per-project
        # ratios. Its own small pool concentrates the population per
        # scope so AC8's IQR population floor is met in mock mode.
        "COMPONENT_SOURCE": _ITEM_COMPONENT_SOURCE,
        "PROJECT_PHASE": RNG.choice(phases, size=n, p=[0.2, 0.25, 0.2, 0.25, 0.05, 0.05]),
        "BENCHMARK_SCORE": RNG.uniform(0, 100, size=n).round(1),
        "APPROVAL_DATE": [
            datetime(2023, 1, 1) + timedelta(days=int(RNG.integers(0, 900)))
            for _ in range(n)
        ],
        "LAST_UPDATED_AT": [
            _MOCK_NOW - timedelta(days=int(RNG.integers(0, 500)))
            for _ in range(n)
        ],
    })
    null_idx = RNG.choice(n, size=int(0.04 * n), replace=False)
    df.loc[null_idx, "BENCHMARK_SCORE"] = np.nan
    # Inject ~3% null + ~2% blank COA so AC1 also exercises the
    # "missing COA" FAIL path, not only the orphan / invalid-marker
    # paths driven by coa_pool.
    null_coa_idx = RNG.choice(n, size=max(1, int(0.03 * n)), replace=False)
    df.loc[null_coa_idx, "COA"] = None
    blank_pool = [i for i in range(n) if i not in set(null_coa_idx)]
    blank_coa_idx = RNG.choice(
        blank_pool, size=max(1, int(0.02 * n)), replace=False
    )
    df.loc[blank_coa_idx, "COA"] = "   "
    # Inject ~5% null + ~2% empty-string JOB_NO so AC2 has
    # estimate-job/period gaps to flag on Completeness (mirrors the ~5%
    # null COST_UPDATE rate in the ADR mock). The empty string reproduces
    # the blank value the live JOB_NO column actually carries, so mock-mode
    # AC2 exercises the same blank-handling path (_is_filled) as production.
    null_job_no_idx = RNG.choice(n, size=max(1, int(0.05 * n)), replace=False)
    df.loc[null_job_no_idx, "JOB_NO"] = None
    blank_job_no_pool = [i for i in range(n) if i not in set(null_job_no_idx)]
    blank_job_no_idx = RNG.choice(
        blank_job_no_pool, size=max(1, int(0.02 * n)), replace=False
    )
    df.loc[blank_job_no_idx, "JOB_NO"] = ""
    # Inject ~2% populated-but-malformed JOB_NO so AC2's Validity branch
    # has FAIL cases too (mirrors the malformed COST_UPDATE in the ADR
    # mock). These don't match the [1-4]Q<YY> token. These draws are the
    # last RNG use in the builder, so they don't shift any other column's
    # stream (determinism preserved).
    used_idx = set(null_job_no_idx) | set(blank_job_no_idx)
    bad_job_no_pool = ["2023", "Q2-23", "5Q23", "2Q"]
    bad_job_no_idx = RNG.choice(
        [i for i in range(n) if i not in used_idx],
        size=max(1, int(0.02 * n)),
        replace=False,
    )
    for i in bad_job_no_idx:
        df.loc[i, "JOB_NO"] = bad_job_no_pool[int(RNG.integers(0, len(bad_job_no_pool)))]
    return df


def _mock_acce_estimatecostresults() -> pd.DataFrame:
    parent_ids = _ITEM_ROW_IDS
    exploded = _explode_children(parent_ids)
    n = len(exploded)
    df = pd.DataFrame({
        "ROW_ID": exploded,
        "CATEGORY": RNG.choice(["DIRECT", "INDIRECT", "OWNER", "OTHER", "BAD"], size=n, p=[0.4, 0.25, 0.2, 0.1, 0.05]),
        "COST_AMOUNT": RNG.lognormal(mean=13.5, sigma=1.2, size=n).round(2),
        "CONTINGENCY_PCT": RNG.uniform(0, 60, size=n).round(2),  # some >40 (implausible)
        # Construction hours and total cost - drive AC3's materiality
        # filter (``SUM(COST_MH) > 0`` OR
        # ``SUM(COST_TOTAL_COST) >= materiality``). The ACCE source
        # column is ``MH`` (man-hours), which the data-product builder
        # prefixes to ``COST_MH``; the cost column ``TOTAL_COST`` is
        # prefixed to ``COST_TOTAL_COST``. Lognormal so the bulk of
        # buckets clear the materiality bar; a small minority is
        # zeroed out below to give the immaterial-bucket branch a
        # non-empty population.
        "MH": RNG.lognormal(mean=3.5, sigma=1.0, size=n).round(2),
        "TOTAL_COST": RNG.lognormal(mean=11.0, sigma=1.2, size=n).round(2),
    })
    null_idx = RNG.choice(n, size=int(0.03 * n), replace=False)
    df.loc[null_idx, "COST_AMOUNT"] = np.nan
    # Zero-out hours + cost on ~6% of rows so a chunk of (ISO_COR, SAB)
    # buckets ends up immaterial → AC3 has real NOT_APPLICABLE coverage.
    zero_idx = RNG.choice(n, size=max(1, int(0.06 * n)), replace=False)
    df.loc[zero_idx, "MH"] = 0.0
    df.loc[zero_idx, "TOTAL_COST"] = 0.0
    return df


def _mock_acce_estimateqtyresults() -> pd.DataFrame:
    """Mirrors the real ``ACCE_ESTIMATEQTYRESULTS`` schema, which carries
    quantity + UOM as two parallel pairs:

      - ``KEY_QTY`` / ``KEY_UNITS``       - primary slot
      - ``OTHER_QTY`` / ``OTHER_UNITS``   - fallback slot

    Each row has **one** slot populated (the other side is null); the
    builder's ``_acce_qty_derive`` hook applies
    ``COALESCE(KEY_*, OTHER_*)`` row-by-row before aggregating, so
    AC5 / AC7 / AC8 see a single ``QTY_QUANTITY`` / ``QTY_UOM`` column
    pair on the data product. AC4 instead reads the split
    ``QTY_KEY_QTY`` / ``QTY_OTHER_QTY`` / ``QTY_KEY_UNITS`` /
    ``QTY_OTHER_UNITS`` columns (which survive aggregation alongside the
    coalesced pair) and treats a row as populated when either slot is
    positive and carries a matching unit.

    UOM is correlated with the parent item's ``ACCT`` (populated by
    ``_mock_acce_estimateitemrecord`` into ``_ITEM_ACCT``) so AC4 has
    coherent per-discipline populations in mock mode: ~70% of rows
    pick a UOM consistent with the discipline's expected core type
    (e.g. ``3-PIP`` → ``FEET`` / ``M``), and ~30% pick a UOM from a
    generic random pool, those mismatches are exactly what AC4
    surfaces as project-level FAILs. The qty mock falls back to the
    legacy uncorrelated distribution when ``_ITEM_ACCT`` is empty (qty
    mock requested before the primary mock).
    """
    parent_ids = _ITEM_ROW_IDS
    exploded = _explode_children(parent_ids)
    n = len(exploded)
    # A single canonical spelling per discipline. AC7 segments by the
    # raw ``(DESCRIPTION, UPPER(TRIM(UOM)))`` value, and distinct
    # spellings (``FEET`` vs ``FT``) are distinct segment keys - so the
    # discipline-correlated ~70% of rows all share ONE spelling to keep
    # each segment above the population floor. The ~30% generic-pool
    # rows still spread across off-discipline UOMs, which is exactly
    # what AC4 surfaces as project-level FAILs.
    acct_uom_pools = {
        "2-EQP": ["EACH"],
        "3-PIP": ["FEET"],
        "4-CIV": ["CY"],
        "5-STL": ["TONS"],
        "6-INST": ["EACH"],
        "7-ELC":  ["FEET"],
    }
    generic_uom_pool = ["EA", "M", "M2", "M3", "KG", "T", "ITEMS"]

    base_quantities = RNG.lognormal(mean=4.2, sigma=1.4, size=n).round(3)
    key_qty: List[Optional[float]] = []
    other_qty: List[Optional[float]] = []
    key_units: List[Optional[str]] = []
    other_units: List[Optional[str]] = []
    # ~80% of rows populate the primary slot (KEY_*); the remaining ~20%
    # populate the fallback slot (OTHER_*). Within each row's chosen
    # slot the ACCT-correlated UOM convention is preserved.
    for i, row_id in enumerate(exploded):
        acct = _ITEM_ACCT.get(row_id)
        pool = acct_uom_pools.get(acct) if acct else None
        if pool and RNG.random() < 0.70:
            uom = str(RNG.choice(pool))
        else:
            uom = str(RNG.choice(generic_uom_pool))
        qty = float(base_quantities[i])
        if RNG.random() < 0.80:
            key_qty.append(qty)
            key_units.append(uom)
            other_qty.append(None)
            other_units.append(None)
        else:
            key_qty.append(None)
            key_units.append(None)
            other_qty.append(qty)
            other_units.append(uom)
    df = pd.DataFrame({
        "ROW_ID": exploded,
        "COMMODITY_CODE": RNG.choice(["COM-A", "COM-B", "COM-C", "COM-D", None], size=n, p=[0.35, 0.3, 0.2, 0.1, 0.05]),
        "KEY_QTY": key_qty,
        "OTHER_QTY": other_qty,
        "KEY_UNITS": key_units,
        "OTHER_UNITS": other_units,
        "UNIT_RATE": RNG.lognormal(mean=5.8, sigma=0.7, size=n).round(4),
    })
    return df


def _mock_acce_estimatedesigndetails() -> pd.DataFrame:
    """Equipment design attributes, one row per DESIGN_ID. Joined to the
    ACCE primary on DESIGN_ID (many items can share a single design).

    ``PROPERTY`` / ``VALUE`` are the design-parameter name / value
    columns on the real ``ACCE_ESTIMATEDESIGNDETAILS`` table; after the
    builder applies the ``DESIGN_`` prefix they surface on the data
    product as ``DESIGN_PROPERTY`` / ``DESIGN_VALUE``. AC5 requires
    BOTH populated to count an item as having a usable design detail,
    so the mock injects independent null/blank gaps into each so AC5
    sees the "value with no named parameter" and "named parameter with
    no value" FAIL paths in mock mode.
    """
    n = _N_DESIGNS
    materials = ["CS", "SS-304", "SS-316", "DUPLEX", "INCONEL", "UNK"]
    services = ["GAS", "OIL", "WATER", "STEAM", "MIXED"]
    design_codes = ["ASME-B31.3", "ASME-B31.4", "ASME-B31.8", "API-650", "BAD-CODE"]
    property_names = [
        "DESIGN PRESSURE", "DESIGN TEMPERATURE", "DIAMETER",
        "WALL THICKNESS", "MATERIAL", "CORROSION ALLOWANCE",
    ]
    parameter_names = list(RNG.choice(property_names, size=n))
    parameter_values = [
        f"PARAM-{int(RNG.integers(1, 999)):03d}" for _ in range(n)
    ]
    df = pd.DataFrame({
        "DESIGN_ID": _DESIGN_ID_POOL,
        "DESIGN_PRESSURE_BAR": RNG.uniform(1, 250, size=n).round(2),
        "DESIGN_TEMPERATURE_C": RNG.uniform(-50, 600, size=n).round(1),
        "MATERIAL_SPEC": RNG.choice(materials, size=n, p=[0.35, 0.2, 0.2, 0.1, 0.1, 0.05]),
        "SERVICE_TYPE": RNG.choice(services, size=n),
        "DIAMETER_MM": RNG.choice([50, 100, 150, 200, 300, 500, 800, 1200], size=n),
        "WALL_THICKNESS_MM": RNG.uniform(3, 50, size=n).round(2),
        "CORROSION_ALLOWANCE_MM": RNG.uniform(0, 6, size=n).round(2),
        "DESIGN_CODE": RNG.choice(design_codes, size=n, p=[0.4, 0.2, 0.2, 0.15, 0.05]),
        "PROPERTY": parameter_names,
        "VALUE": parameter_values,
    })
    null_mat_idx = RNG.choice(n, size=max(1, int(0.04 * n)), replace=False)
    df.loc[null_mat_idx, "MATERIAL_SPEC"] = None
    null_pres_idx = RNG.choice(n, size=max(1, int(0.03 * n)), replace=False)
    df.loc[null_pres_idx, "DESIGN_PRESSURE_BAR"] = np.nan
    null_param_idx = RNG.choice(n, size=max(1, int(0.08 * n)), replace=False)
    df.loc[null_param_idx, "VALUE"] = None
    blank_pool = [i for i in range(n) if i not in set(null_param_idx)]
    blank_param_idx = RNG.choice(
        blank_pool, size=max(1, int(0.03 * n)), replace=False
    )
    df.loc[blank_param_idx, "VALUE"] = "   "
    # Independent gaps in PROPERTY so AC5 sees items whose value is
    # present but the parameter is un-named (the "120 m of what?" case).
    null_prop_idx = RNG.choice(n, size=max(1, int(0.05 * n)), replace=False)
    df.loc[null_prop_idx, "PROPERTY"] = None
    return df


# =============================================================================
# EPT - single table
# =============================================================================

def _mock_onshore_cetdata() -> pd.DataFrame:
    """Project-level reference data. 1 row per PLANVIEW_ID (but with some missing
    ids and a couple of duplicates to stress-test quality rules)."""
    ids = list(_PLANVIEW_ID_POOL)
    # Inject some nulls and duplicates
    null_idx = RNG.choice(len(ids), size=3, replace=False)
    for i in null_idx:
        ids[i] = None
    dup_idx = RNG.choice([i for i in range(len(ids)) if ids[i] is not None], size=2, replace=False)
    ids[dup_idx[0]] = ids[dup_idx[1]]

    n = len(ids)
    code_of_location = RNG.choice(
        ["LOC-A", "LOC-B", "LOC-C", "LOC-D"], size=n
    ).astype(object)
    standard_activity_breakdown = RNG.choice(
        ["EXPLORATION", "DEVELOPMENT", "PRODUCTION", "DECOMMISSIONING"], size=n
    ).astype(object)
    # Mix in a handful of FEED / Engineering labels (E5 scope) alongside the
    # generic L1_* categories so the rule has natural in-scope rows. Weights
    # keep FEED/Engineering a minority, mirrors the ~5–10% share seen in
    # production EPT extracts.
    wbc_level_1 = RNG.choice(
        [
            "L1_CAPEX", "L1_OPEX", "L1_LABOR", "L1_MATERIAL", "L1_OTHER",
            "250.0-FEED BY CONTRACTOR(S)", "FEED BY CONTRACTOR",
            "230.0-DETAILED ENGINEERING", "ENGINEERING COSTS",
        ],
        size=n,
        p=[0.20, 0.20, 0.18, 0.17, 0.15, 0.03, 0.03, 0.02, 0.02],
    ).astype(object)
    # Inject completeness gaps so the EPT custom rules have real failures
    # to detect: ~5% null CODE_OF_RESOURCE (E1), ~3% blank
    # STANDARD_ACTIVITY_BREAKDOWN (E1), ~4% null WBC_LEVEL_1 + ~2% blank
    # WBC_LEVEL_1 (E4), and a couple of orphan PLANVIEW_IDs (E7).
    cor_null_idx = RNG.choice(n, size=max(1, int(0.05 * n)), replace=False)
    for i in cor_null_idx:
        code_of_location[i] = None
    sab_blank_idx = RNG.choice(n, size=max(1, int(0.03 * n)), replace=False)
    for i in sab_blank_idx:
        standard_activity_breakdown[i] = ""
    wbc_null_idx = RNG.choice(n, size=max(1, int(0.04 * n)), replace=False)
    for i in wbc_null_idx:
        wbc_level_1[i] = None
    wbc_blank_idx = RNG.choice(n, size=max(1, int(0.02 * n)), replace=False)
    for i in wbc_blank_idx:
        wbc_level_1[i] = "   "
    # Inject ~2 orphan PLANVIEW_IDs (not in the master pool) so E7 has
    # referential-integrity failures distinct from the null PLANVIEW_ID rows.
    orphan_idx = RNG.choice(
        [i for i in range(n) if ids[i] is not None], size=2, replace=False
    )
    for i in orphan_idx:
        ids[i] = f"PV-ORPHAN-{i:03d}"

    centroid_date = [
        datetime(2022, 6, 1) + timedelta(days=int(RNG.integers(0, 1200)))
        for _ in range(n)
    ]
    # Inject ~5% null CENTROID_DATE so E2 has estimate-basis-date gaps.
    centroid_null_idx = RNG.choice(n, size=max(1, int(0.05 * n)), replace=False)
    for i in centroid_null_idx:
        centroid_date[i] = None

    # WBC_LEVEL_5 (operational detail) and the materiality drivers used by
    # E3. Each row gets a randomly drawn detailed WBC label plus per-row
    # hours and USD cost. Hours are sampled from a heavy-tailed distribution
    # so most ISO mappings are easily material; cost uses a lognormal so a
    # few rows clear the 100k USD threshold even before aggregation.
    wbc_level_5_pool = [f"WBC5-{i:03d}" for i in range(1, 26)]
    wbc_level_5 = RNG.choice(wbc_level_5_pool, size=n).astype(object)
    total_hours = RNG.lognormal(mean=4.0, sigma=1.2, size=n).round(1)
    total_cost_usd = RNG.lognormal(mean=11.5, sigma=1.4, size=n).round(2)
    # Local-currency cost mirrors USD with a project-specific FX multiplier
    # (3x–6x) so it's plausibly the same amount in a non-USD currency.
    # Most rows have both fields populated; a slice has USD null so E5's
    # COALESCE fallback path is exercised in mock mode.
    fx_multiplier = RNG.uniform(3.0, 6.0, size=n)
    total_cost_estimate_currency = (total_cost_usd * fx_multiplier).round(2)
    # ~6% of rows have USD null but the local-currency value populated -
    # cost_amount must fall back to TOTAL_COST_ESTIMATE_CURRENCY.
    cost_usd_null_idx = RNG.choice(
        n, size=max(1, int(0.06 * n)), replace=False
    )
    for i in cost_usd_null_idx:
        total_cost_usd[i] = float("nan")
    # ~3% of rows have neither cost nor hours - natural PASS for E5
    # (both-absent branch).
    both_zero_idx = RNG.choice(
        [i for i in range(n) if i not in set(cost_usd_null_idx)],
        size=max(1, int(0.03 * n)),
        replace=False,
    )
    for i in both_zero_idx:
        total_cost_usd[i] = 0.0
        total_cost_estimate_currency[i] = 0.0
        total_hours[i] = 0.0
    # Force-stamp a single ISO mapping with many distinct WBC_LEVEL_5 values
    # so E3 has at least one over-aggregating outlier to detect in mock mode.
    outlier_idx = RNG.choice(n, size=min(8, n), replace=False)
    for k, i in enumerate(outlier_idx):
        code_of_location[i] = "LOC-A"
        standard_activity_breakdown[i] = "EXPLORATION"
        wbc_level_5[i] = f"WBC5-OUTLIER-{k:02d}"
        total_cost_usd[i] = max(
            total_cost_usd[i] if pd.notna(total_cost_usd[i]) else 0.0,
            250_000.0,
        )
    # Re-assert at least one blank ``STANDARD_ACTIVITY_BREAKDOWN`` *after*
    # the outlier overwrite - otherwise a small EPT pool (N_PROJECTS=50)
    # combined with the 3% injection rate could land its single blank on
    # an outlier index, get overwritten to "EXPLORATION", and leave the
    # SAB column gap-free. Without a guaranteed gap, E1 would have no
    # SAB failures to detect in mock mode and
    # ``test_ept_mock_data_includes_cor_and_sab`` would flake based on
    # RNG state.
    non_outlier = [i for i in range(n) if i not in set(outlier_idx)]
    if non_outlier:
        standard_activity_breakdown[non_outlier[0]] = ""
    # Force-stamp a deterministic block of FEED / Engineering rows so E5
    # has both PASS and FAIL examples regardless of dataset size:
    #   - 2 rows: cost present, hours zero       → FAIL (cost-no-hours)
    #   - 2 rows: hours present, both costs zero → FAIL (hours-no-cost)
    #   - 1 row : USD null, currency populated   → PASS via fallback
    feed_labels = [
        "250.0-FEED BY CONTRACTOR(S)",
        "FEED BY CONTRACTOR",
        "230.0-DETAILED ENGINEERING",
        "ENGINEERING COSTS",
        "FEED BY CONTRACTOR(S)",
    ]
    e5_seed_idx = RNG.choice(n, size=min(5, n), replace=False)
    for k, i in enumerate(e5_seed_idx):
        wbc_level_1[i] = feed_labels[k]
        if k < 2:                               # cost-without-hours FAIL
            total_hours[i] = 0.0
            total_cost_usd[i] = 75_000.0
            total_cost_estimate_currency[i] = 300_000.0
        elif k < 4:                             # hours-without-cost FAIL
            total_hours[i] = max(float(total_hours[i]), 500.0)
            total_cost_usd[i] = 0.0
            total_cost_estimate_currency[i] = 0.0
        else:                                   # currency-fallback PASS
            total_cost_usd[i] = float("nan")
            total_cost_estimate_currency[i] = 180_000.0
            total_hours[i] = max(float(total_hours[i]), 400.0)

    df = pd.DataFrame({
        "PLANVIEW_ID": ids,
        "PROJECT_NAME": [f"Onshore Project {chr(65 + (i % 26))}{i:04d}" for i in range(n)],
        "BUSINESS_UNIT": RNG.choice(["UPSTREAM", "DOWNSTREAM", "CHEMICALS", "LNG", "UNKNOWN"], size=n),
        "COUNTRY": RNG.choice(["BR", "US", "UK", "NL", "ZZ"], size=n, p=[0.35, 0.25, 0.2, 0.15, 0.05]),
        "PROJECT_STATUS": RNG.choice(["ACTIVE", "ON_HOLD", "CANCELLED", "CLOSED"], size=n),
        "CODE_OF_RESOURCE": code_of_location,
        "STANDARD_ACTIVITY_BREAKDOWN": standard_activity_breakdown,
        "WBC_LEVEL_1": wbc_level_1,
        "WBC_LEVEL_5": wbc_level_5,
        "TOTAL_HOURS": total_hours,
        "TOTAL_COST_USD": total_cost_usd,
        "TOTAL_COST_ESTIMATE_CURRENCY": total_cost_estimate_currency,
        "CENTROID_DATE": centroid_date,
        "SCOPE_CONFIDENCE": RNG.uniform(0, 1, size=n).round(3),
        "CET_REVIEW_DATE": [
            datetime(2022, 1, 1) + timedelta(days=int(RNG.integers(0, 1500)))
            for _ in range(n)
        ],
        "LAST_REPORTED_AT": [
            _MOCK_NOW - timedelta(days=int(RNG.integers(0, 500)))
            for _ in range(n)
        ],
    })
    return df


def _mock_acce_coa_master() -> pd.DataFrame:
    """Reference dataset used by A1 and A3 - maps the leading 3-digit
    COA group derived from ``COMPLETE_WBC`` to ``ISO_COR`` and ``SAB``.

    The pool is deterministic so unit-test fixtures don't have to mock
    the whole loader. A handful of error / null entries mirror the
    production COA master's "I haven't been mapped yet" rows (so A1 has
    FAIL cases against every documented invalid marker), and the valid
    pool is intentionally large enough, and overlapping - to give A3
    enough distinct ``(ISO_COR, SAB)`` buckets to cross its
    population threshold and exhibit at least one over-aggregating
    mapping in mock mode.
    """
    rows = [
        # Valid mappings - A1 PASS. The (ISO_COR, SAB) buckets are
        # mostly unique so each COA group has its own ISO mapping;
        # ICARUS_COA 313 / 322 / 327 deliberately collapse onto the
        # *same* ISO bucket to give A3 an over-aggregating example
        # (multiple distinct WBCs flowing through one ISO mapping).
        ("311", "C1.6",     "S3.2.2"),
        ("312", "C1.7",     "S3.2.3"),
        ("313", "C2.12.1",  "S3.2.2"),
        ("314", "C2.13",    "S3.4"),
        ("317", "C3.2",     "S2.5"),
        ("318", "C3.3",     "S2.6"),
        ("321", "C4.2",     "S4.1"),
        ("322", "C2.12.1",  "S3.2.2"),    # duplicate bucket with 313
        ("323", "C5.1",     "S5.1"),
        ("324", "C5.2",     "S5.2"),
        ("325", "C5.3",     "S5.3"),
        ("326", "C6.1",     "S6.1"),
        ("327", "C2.12.1",  "S3.2.2"),    # duplicate bucket with 313 / 322
        ("328", "C7.1",     "S7.1"),
        ("329", "C7.2",     "S7.2"),
        ("330", "C7.3",     "S7.3"),
        # Error / null markers - A1 FAIL on lookup.
        ("315", "ERROR: #N/A", "S2.1"),     # invalid ISO_COR
        ("316", "C3.1",     "ERROR: #N/A"), # invalid SAB
        ("319", None,       "S3.1"),         # null ISO_COR
        ("320", "C4.1",     None),           # null SAB
        # Multiple rows for the same ICARUS_COA - A1 must prefer the
        # valid mapping per spec §9 (FIRST_VALUE ORDER BY invalid-flag).
        ("314", "ERROR: stale", "ERROR: stale"),
        ("321", None, None),
    ]
    return pd.DataFrame(rows, columns=["ICARUS_COA", "ISO_COR", "SAB"])


def _mock_vws_gp_standard_share() -> pd.DataFrame:
    """Reference dataset used by referential-integrity rules such as EPT
    E7 (PROJECT_ID lookup) and the E2 country-coverage join. Mirrors the
    production ``VWS_GP_STANDARD_SHARE`` view, one row per canonical
    project, identified by ``PROJECT_ID``, plus ``COUNTRY`` for the
    project location lookup, ``E05_DEPARTMENT`` for brownfield/greenfield
    classification, and ``BUSINESS`` for business-line segmentation
    (both consumed by E6 when the segment-by-project-type toggle is on).
    Orphan PLANVIEW_IDs injected into EPT will not appear here and
    therefore fail the lookup.
    """
    # Reseed so this reference is deterministic per call regardless of how many
    # system tables / other references were built first - it's loaded via the
    # reference registry, not fetch_mock_table, so it needs its own reseed.
    _reseed_rng_for("VWS_GP_STANDARD_SHARE")
    project_ids = list(_PLANVIEW_ID_POOL)
    n = len(project_ids)
    countries = RNG.choice(
        ["BR", "US", "UK", "NL", "ZZ"], size=n, p=[0.35, 0.25, 0.2, 0.15, 0.05]
    ).astype(object)
    # Inject a few null/blank COUNTRY values so E2 has real country gaps to
    # detect distinct from the unmatched-PLANVIEW_ID failures.
    null_idx = RNG.choice(n, size=max(1, int(0.06 * n)), replace=False)
    for i in null_idx:
        countries[i] = None
    departments = RNG.choice(
        ["BROWNFIELD", "GREENFIELD"], size=n, p=[0.55, 0.45]
    ).astype(object)
    businesses = RNG.choice(
        ["UPSTREAM", "DOWNSTREAM", "CHEMICAL", "LNG"],
        size=n,
        p=[0.40, 0.30, 0.20, 0.10],
    ).astype(object)
    return pd.DataFrame({
        "PROJECT_ID": project_ids,
        "COUNTRY": countries,
        "E05_DEPARTMENT": departments,
        "BUSINESS": businesses,
    })


# =============================================================================
# Quality domain - mock data for CT_SQS_AT_INSPECTION
# =============================================================================
# The Quality domain ships a single curated inspection table; the mock
# generator below mirrors that shape so the rest of the pipeline can run
# in demo mode. The curated rules (``dq-inspection-12`` / ``-13``) key on
# ``STATUS``, ``TOTAL_CONSUMED_HOURS`` and ``ALLOTED_HOURS``; the other
# columns carry the real table's controlled vocabularies plus deliberate
# gaps (nulls, off-list values, duplicate PKs, out-of-range scores) so the
# Standard DQR catalog stays meaningful in demo mode.

_SQS_INSPECTION_RESULTS = ["PASS", "FAIL", "OBSERVATION"]
# ``INSPECTION_TYPE`` controlled vocabulary, plus a handful of off-list
# values (mis-cased, typos, unexpected categories) so Validity-style
# Standard rules have FAIL cases in mock mode.
_SQS_INSPECTION_TYPES_ALLOWED = [
    "Source Inspection",
    "Supplier Assessment",
    "Expediting",
    "Supplemental Inspection",
]
_SQS_INSPECTION_TYPES_OFFLIST = [
    "source inspection",      # case mismatch
    "Audit",                  # unexpected category
    "Expedite",               # typo / variant
]
# ``WORK_CRITICALITY`` classification levels. Same shape as
# ``INSPECTION_TYPE``: an allowed-vocabulary pool plus a handful of off-list
# values.
_SQS_WORK_CRITICALITY_ALLOWED = [
    "I - High Critical",
    "II - Medium Critical",
    "III - Low Critical",
    "IV - Non Critical",
]
_SQS_WORK_CRITICALITY_OFFLIST = [
    "i - high critical",      # case mismatch
    "V - Unknown",            # off-list classification
    "",                       # empty string
]
# ``STATUS`` is the trigger column for ``dq-inspection-12`` (only rows
# with the exact value ``"Completed"`` are in scope). The allowed pool
# mirrors the 11 canonical workflow statuses; the off-list pool covers
# typos, case mismatch, leading/trailing whitespace and off-list
# categories.
_SQS_INSPECTION_STATUSES_ALLOWED = [
    "Approved",
    "Inspection In Progress",
    "Completed",
    "Inspection Approved",
    "Pending SER Review",
    "Additional Funding Requested",
    "Deprecated",
    "Pending Review",
    "Completed (Short Closed)",
    "Inspection Rejected",
    "OAP Pending",
]
_SQS_INSPECTION_STATUSES_OFFLIST = [
    "Cancelled",       # unexpected category
    "approved",        # case mismatch
    " Approved ",      # surrounding whitespace
    "In Progress",     # off-list (canonical form is "Inspection In Progress")
]


def _mock_ct_sqs_at_inspection() -> pd.DataFrame:
    """Mock for the curated ``CT_SQS_AT_INSPECTION`` table.

    One row per inspection event, keyed by ``INSPECTION_ID`` and linked
    to a project via ``PLANVIEW_ID``. Mirrors the Cost Estimate
    primary-table pattern (PK + project key + a handful of attributes
    + deliberate gaps) so Step 2 / Step 3 have something realistic to
    profile.
    """
    n = N_ITEMS
    inspection_ids = [f"INS-{i:06d}" for i in range(1, n + 1)]
    dup_targets = RNG.choice(n, size=4, replace=False)
    for i in dup_targets[:-1]:
        inspection_ids[i] = inspection_ids[dup_targets[-1]]

    planview = RNG.choice(_PLANVIEW_ID_POOL, size=n).astype(object).tolist()
    for i in RNG.choice(n, size=max(1, int(0.03 * n)), replace=False):
        planview[i] = None

    # PROJECT_CODE is the sidebar Project-filter column for the Quality
    # domain (see config.domains._build_quality_domain). One PROJECT_CODE
    # per PLANVIEW_ID so the filter resolves cleanly to a subset of
    # inspections; nulls propagate from the PLANVIEW_ID column so the
    # 3% gap stays visible at the project-grain level too.
    _SQS_PROJECT_CODE_POOL = [f"QPC-{i:03d}" for i in range(1, len(_PLANVIEW_ID_POOL) + 1)]
    _planview_to_project_code = {
        pv: _SQS_PROJECT_CODE_POOL[i] for i, pv in enumerate(_PLANVIEW_ID_POOL)
    }
    project_code = [
        _planview_to_project_code[pv] if pv is not None else None for pv in planview
    ]

    # ~86% of rows pick from the allowed set; ~10% pick an off-list
    # value; ~4% NULL.
    allowed_weight = 0.86
    offlist_weight = 0.10
    inspection_types: list = []
    for _ in range(n):
        roll = RNG.random()
        if roll < allowed_weight:
            inspection_types.append(str(RNG.choice(_SQS_INSPECTION_TYPES_ALLOWED)))
        elif roll < allowed_weight + offlist_weight:
            inspection_types.append(str(RNG.choice(_SQS_INSPECTION_TYPES_OFFLIST)))
        else:
            inspection_types.append(None)
    # Guarantee at least one each of off-list and NULL even on small N so
    # the demo stays deterministic.
    off_idx, null_idx_st = RNG.choice(n, size=2, replace=False)
    inspection_types[int(off_idx)] = "source inspection"
    inspection_types[int(null_idx_st)] = None

    # WORK_CRITICALITY: same mix as INSPECTION_TYPE - ~86% allowed, ~10%
    # off-list, ~4% NULL. Guaranteed seeding for the off-list + NULL
    # buckets keeps the demo deterministic at any N.
    work_criticality: list = []
    for _ in range(n):
        roll = RNG.random()
        if roll < 0.86:
            work_criticality.append(str(RNG.choice(_SQS_WORK_CRITICALITY_ALLOWED)))
        elif roll < 0.96:
            work_criticality.append(str(RNG.choice(_SQS_WORK_CRITICALITY_OFFLIST)))
        else:
            work_criticality.append(None)
    wc_off_idx, wc_null_idx = RNG.choice(n, size=2, replace=False)
    work_criticality[int(wc_off_idx)] = "i - high critical"
    work_criticality[int(wc_null_idx)] = None

    results = RNG.choice(_SQS_INSPECTION_RESULTS, size=n,
                         p=[0.65, 0.20, 0.15]).astype(object).tolist()
    # STATUS: ~83% allowed, ~9% off-list, ~5% NULL, ~3% whitespace-only.
    # Guaranteed seeding of each bucket keeps the demo deterministic at
    # any N.
    statuses: list = []
    for _ in range(n):
        roll = RNG.random()
        if roll < 0.83:
            statuses.append(str(RNG.choice(_SQS_INSPECTION_STATUSES_ALLOWED)))
        elif roll < 0.92:
            statuses.append(str(RNG.choice(_SQS_INSPECTION_STATUSES_OFFLIST)))
        else:
            statuses.append(None)
    null_idx = RNG.choice(n, size=max(1, int(0.05 * n)), replace=False)
    for i in null_idx:
        statuses[int(i)] = None
    blank_pool = [i for i in range(n) if statuses[i] is not None]
    for i in RNG.choice(blank_pool, size=max(1, int(0.03 * n)), replace=False):
        statuses[int(i)] = "   "
    # Force-seed at least one off-list status so the off-list bucket is
    # populated even at small N (the random draw can otherwise miss it).
    forced_offlist = RNG.choice([
        i for i in range(n) if statuses[i] not in (None,) and (statuses[i] or "").strip() != ""
    ])
    statuses[int(forced_offlist)] = "Cancelled"

    scores = RNG.normal(loc=85.0, scale=10.0, size=n).clip(0, 100).tolist()
    for i in RNG.choice(n, size=max(1, int(0.05 * n)), replace=False):
        scores[i] = None
    for i in RNG.choice(n, size=max(1, int(0.02 * n)), replace=False):
        scores[i] = -1.0

    inspection_date = [
        datetime(2024, 1, 1) + timedelta(days=int(RNG.integers(0, 730)))
        for _ in range(n)
    ]
    for i in RNG.choice(n, size=max(1, int(0.03 * n)), replace=False):
        inspection_date[i] = None

    inspector = [f"INSP-{int(RNG.integers(1, 25)):03d}" for _ in range(n)]
    for i in RNG.choice(n, size=max(1, int(0.04 * n)), replace=False):
        inspector[i] = None

    # EXPECTED_SHIP_DATE is a TIMESTAMP in the source system, so ingestion
    # enforces well-formed datetimes upstream - the realistic gap is NULL
    # (~6%).
    expected_ship_date = [
        datetime(2024, 1, 1) + timedelta(days=int(RNG.integers(30, 900)))
        for _ in range(n)
    ]
    for i in RNG.choice(n, size=max(1, int(0.06 * n)), replace=False):
        expected_ship_date[i] = None

    # PO_REQUIRED_SHIP_DATE: most rows land 0-30 days AFTER the expected
    # ship date (contractual buffer > projected ship); ~10% land 1-20 days
    # *before* it; ~5% nulls. The base is the same ``expected_ship_date[i]``
    # whenever it's populated, otherwise an independent date.
    po_required_ship_date: list = []
    fail_idx = set(RNG.choice(n, size=max(1, int(0.10 * n)), replace=False).tolist())
    null_idx = set(RNG.choice(n, size=max(1, int(0.05 * n)), replace=False).tolist())
    for i in range(n):
        if i in null_idx:
            po_required_ship_date.append(None)
            continue
        base = expected_ship_date[i] or (
            datetime(2024, 1, 1) + timedelta(days=int(RNG.integers(30, 900)))
        )
        if i in fail_idx:
            offset = -int(RNG.integers(1, 21))    # before expected → FAIL
        else:
            offset = int(RNG.integers(0, 31))     # on/after expected → PASS
        po_required_ship_date.append(base + timedelta(days=offset))

    # ALLOTED_HOURS drives dq-inspection-13 (Completeness): the approved
    # hours budget must be populated on every record. ~7% NULL gives the
    # rule real FAIL cases; a guaranteed NULL seed keeps the FAIL path
    # reachable at any N.
    alloted_hours = RNG.integers(8, 200, size=n).astype(float).tolist()
    for i in RNG.choice(n, size=max(1, int(0.07 * n)), replace=False):
        alloted_hours[int(i)] = None

    # TOTAL_CONSUMED_HOURS drives dq-inspection-12 (Completeness on
    # completion): only rows with STATUS == "Completed" are in scope, and
    # those must carry consumed hours. ~15% NULL overall (open
    # inspections legitimately have no consumed hours yet). Force-seed
    # two Completed rows outside the NULL / blank / off-list STATUS seeds
    # above: one with NULL hours (FAIL) and one populated (PASS) so both
    # branches are reachable in demo mode at any N.
    total_consumed_hours: list = []
    for i in range(n):
        if RNG.random() < 0.15:
            total_consumed_hours.append(None)
            continue
        base_hours = alloted_hours[i] if alloted_hours[i] is not None else 80.0
        total_consumed_hours.append(
            round(float(base_hours) * float(RNG.uniform(0.6, 1.3)), 1)
        )
    completed_pool = [
        i for i in range(n)
        if statuses[i] not in (None, "   ", "Cancelled")
        and i != int(forced_offlist)
    ]
    if len(completed_pool) >= 2:
        dq12_fail_idx, dq12_pass_idx = RNG.choice(
            completed_pool, size=2, replace=False
        )
        statuses[int(dq12_fail_idx)] = "Completed"
        statuses[int(dq12_pass_idx)] = "Completed"
        total_consumed_hours[int(dq12_fail_idx)] = None
        total_consumed_hours[int(dq12_pass_idx)] = 96.5

    return pd.DataFrame({
        "INSPECTION_ID": inspection_ids,
        "PLANVIEW_ID": planview,
        "PROJECT_CODE": project_code,
        "INSPECTION_TYPE": inspection_types,
        "WORK_CRITICALITY": work_criticality,
        "INSPECTION_DATE": inspection_date,
        "INSPECTOR_ID": inspector,
        "RESULT": results,
        "STATUS": statuses,
        "SCORE": scores,
        "EXPECTED_SHIP_DATE": expected_ship_date,
        "PO_REQUIRED_SHIP_DATE": po_required_ship_date,
        "ALLOTED_HOURS": alloted_hours,
        "TOTAL_CONSUMED_HOURS": total_consumed_hours,
    })


# =============================================================================
# Public API
# =============================================================================

_MOCK_REGISTRY = {
    # ADR
    "ADR_DIM_ESTIMATEITEMRECORD": _mock_adr_dim_estimateitemrecord,
    "ADR_FACT_ESTIMATECOSTRESULTS": _mock_adr_fact_estimatecostresults,
    "ADR_FACT_ESTIMATEQTYRESULTS": _mock_adr_fact_estimateqtyresults,
    "ADR_DIM_ESTIMATEDESIGNDETAILS": _mock_adr_dim_estimatedesigndetails,
    # ACCE
    "ACCE_ESTIMATEITEMRECORD": _mock_acce_estimateitemrecord,
    "ACCE_ESTIMATECOSTRESULTS": _mock_acce_estimatecostresults,
    "ACCE_ESTIMATEQTYRESULTS": _mock_acce_estimateqtyresults,
    "ACCE_ESTIMATEDESIGNDETAILS": _mock_acce_estimatedesigndetails,
    # EPT
    "ONSHORE_CETDATA": _mock_onshore_cetdata,
    # Quality
    "CT_SQS_AT_INSPECTION": _mock_ct_sqs_at_inspection,
}


def fetch_mock_table(table_name: str) -> pd.DataFrame:
    """Build (or rebuild) a mock table by name.

    Deterministic per input: the shared module RNG is reseeded from the table
    name before each build, so calling this twice for the same table returns
    byte-identical content regardless of how many other tables were built in
    between (the generator is shared + stateful, so without the reseed each
    call advanced it and produced different data). The seed uses ``zlib.crc32``
    rather than the salted built-in ``hash`` so it is stable across processes.
    The cross-table join-key constants are import-time and unaffected.
    """
    if table_name not in _MOCK_REGISTRY:
        raise KeyError(
            f"No mock generator for table: {table_name}. "
            f"Known: {sorted(_MOCK_REGISTRY)}"
        )
    _reseed_rng_for(table_name)
    gen = _MOCK_REGISTRY[table_name]
    return gen()


def list_mock_tables() -> Dict[str, str]:
    return {name: "mock" for name in _MOCK_REGISTRY}
