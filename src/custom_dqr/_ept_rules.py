# pyright: reportArgumentType=false, reportOperatorIssue=false
# pyright: reportCallIssue=false, reportReturnType=false
# pyright: reportAttributeAccessIssue=false
"""EPT custom DQR rule checks (E1-E7).

Each ``check_ept_e<N>`` is a callable ``(df) -> pd.Series[bool]`` where True
means the row passes. Statistical rules (E3, E6) accept an optional
``params`` dict to override their default thresholds via the Step 4.2 UI.

See the pragma rationale in ``src/custom_dqr/_adr_rules.py``: the
pandas-stubs typing of ``df[col]`` as ``Series | DataFrame`` produces
hundreds of false positives that ``cast(pd.Series, ...)`` would only
paper over. Runtime correctness is locked down by
``tests/test_custom_dqr_engine.py`` + ``tests/test_dqr_engine_extra.py``.
"""
from __future__ import annotations

from typing import Dict, Tuple, TypedDict

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


class EPTE3Params(TypedDict, total=False):
    """Step 4.2 -> assignment.params shape for EPT E3.

    All keys are optional; missing entries fall back to the module-level
    defaults (``EPT_E3_PERCENTILE`` and ``False`` for the toggles).
    Documented as a TypedDict so the Step 4.2 form, the rule-card render
    and the check itself stay in sync.
    """
    threshold_percentile: float       # EPT_E3_THRESHOLD_PARAM
    project_scoped: bool              # EPT_E3_PROJECT_SCOPED_PARAM
    detect_uniform_mapping: bool      # EPT_E3_DETECT_UNIFORM_MAPPING_PARAM


class EPTE6Params(TypedDict, total=False):
    """Step 4.2 -> assignment.params shape for EPT E6."""
    threshold_iqr_multiplier: float   # EPT_E6_THRESHOLD_PARAM
    segment_by_project_type: bool     # EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM

# EPT custom rules
# =============================================================================

EPT_E1_REQUIRED_COLUMNS = {
    "COR": "CODE_OF_RESOURCE",
    "SAB": "STANDARD_ACTIVITY_BREAKDOWN",
}

EPT_E2_REQUIRED_COLUMNS = {
    "Estimate Basis Date": "CENTROID_DATE",
    "Project Key": "PLANVIEW_ID",
}

EPT_E2_REFERENCE = {
    "reference_dataset": "VWS_GP_STANDARD_SHARE",
    "source_column": "PLANVIEW_ID",      # in EPT
    "reference_column": "PROJECT_ID",    # in VWS_GP_STANDARD_SHARE
    "lookup_column": "COUNTRY",          # populated value to check post-join
}

EPT_E3_REQUIRED_COLUMNS = {
    "WBC Level 5": "WBC_LEVEL_5",
    "COR": "CODE_OF_RESOURCE",
    "SAB": "STANDARD_ACTIVITY_BREAKDOWN",
    "Total Hours": "TOTAL_HOURS",
    "Total Cost (USD)": "TOTAL_COST_USD",
}

# Statistical-threshold parameters. Default scope is global (dataset-wide)
# 90th percentile of WBC-to-ISO ratios; the project-scoped option
# (``EPT_E3_PROJECT_SCOPED_PARAM``) switches the baseline to a per-
# PLANVIEW_ID partition so each project is judged against its own peers.
EPT_E3_PERCENTILE = 0.90
EPT_E3_MATERIALITY_USD = 100_000.0

# Key under which the project-scoped toggle is persisted on the
# CustomDQRAssignment.params dict. The Step 4.2 UI sets it; check_ept_e3
# reads it. Centralised here so the catalog, the engine, and the UI agree
# on a single string identifier.
EPT_E3_PROJECT_SCOPED_PARAM = "project_scoped"
EPT_E3_PROJECT_SCOPED_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
}

# Percentile-threshold customization for E3. The Step 4.2 UI exposes the
# choices below as a selectbox; check_ept_e3 reads
# ``params[EPT_E3_THRESHOLD_PARAM]`` and falls back to ``EPT_E3_PERCENTILE``
# (P90) when the param is absent. Choices are documented in the catalog
# so the rule card surfaces the same recommendation.
EPT_E3_THRESHOLD_PARAM = "threshold_percentile"
EPT_E3_THRESHOLD_CHOICES: Tuple[Tuple[float, str], ...] = (
    (0.75, "P75 - lenient"),
    (0.90, "P90 - recommended"),
    (0.95, "P95 - strict"),
    (0.99, "P99 - very strict"),
)

# Uniform 1:1 mapping detection. Off by default, the rule is opt-in because
# a perfectly uniform distribution can be legitimate on small datasets. When
# the toggle is on, after the regular percentile-based outlier verdict the
# rule ALSO fails every *material* group whose ratio equals 1 (each ISO
# bucket holds exactly one distinct WBC_LEVEL_5). The intent is to catch
# WBC→ISO mappings that are suspiciously uniform, typically a sign that
# the mapping process was bypassed and source codes were copied 1:1 into
# the ISO bucket without aggregating activities. Combined with the
# percentile fail via OR so users keep both signals at once.
EPT_E3_DETECT_UNIFORM_MAPPING_PARAM = "detect_uniform_mapping"

EPT_E4_REQUIRED_COLUMNS = {
    "Level 1": "WBC_LEVEL_1",
}

EPT_E5_REQUIRED_COLUMNS = {
    "Level 1": "WBC_LEVEL_1",
    "Total Hours": "TOTAL_HOURS",
    "Total Cost (USD)": "TOTAL_COST_USD",
    "Total Cost (Local Currency)": "TOTAL_COST_ESTIMATE_CURRENCY",
}

# Case-insensitive regex used to identify FEED / Engineering scope from
# WBC_LEVEL_1. Matches the documented samples, e.g. ``FEED``,
# ``FEED BY CONTRACTOR(S)``, ``250.0-FEED BY CONTRACTOR``,
# ``DETAILED ENGINEERING``, ``ENGINEERING COSTS``. Word boundaries keep
# ``FEEDBACK`` / ``ENGINEERED`` from accidentally matching.
EPT_E5_FEED_ENGINEERING_PATTERN = r"\b(?:FEED|ENGINEERING)\b"

EPT_E6_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
    "Total Hours": "TOTAL_HOURS",
    "Total Cost (USD)": "TOTAL_COST_USD",
    "Total Cost (Local Currency)": "TOTAL_COST_ESTIMATE_CURRENCY",
}

# IQR-based thresholds for the project-level cost-to-hours ratio. The mild
# multiplier defines the PASS / FAIL boundary; the extreme multiplier is
# only used for severity classification (logged in the rule reason, every
# extreme outlier is also a mild outlier and therefore a FAIL).
EPT_E6_MILD_IQR_MULTIPLIER = 1.5
EPT_E6_EXTREME_IQR_MULTIPLIER = 3.0
# Minimum number of projects with calculable ratios required before the IQR
# thresholds are derived. Below this the rule is NOT_APPLICABLE, the
# population is too small to call anything an outlier. When segmentation is
# on, the same minimum is enforced *per segment* - segments under the floor
# are NOT_APPLICABLE so a thinly-populated bucket does not flag every project
# inside it as an outlier of itself.
EPT_E6_MIN_POPULATION = 5

# IQR-multiplier threshold customization for E6. Step 4.2 UI exposes the
# choices below as a selectbox; check_ept_e6 reads
# ``params[EPT_E6_THRESHOLD_PARAM]`` and falls back to
# ``EPT_E6_MILD_IQR_MULTIPLIER`` (1.5×) when the param is absent. A larger
# multiplier widens the PASS band, fewer flagged outliers.
EPT_E6_THRESHOLD_PARAM = "threshold_iqr_multiplier"
EPT_E6_THRESHOLD_CHOICES: Tuple[Tuple[float, str], ...] = (
    (1.5, "Mild (1.5×IQR) - recommended"),
    (2.0, "Moderate (2.0×IQR)"),
    (3.0, "Extreme (3.0×IQR) - lenient"),
)

# Project-type segmentation toggle. When on, every project is tagged with a
# composite segment key derived from the Planview reference dataset
# (``E05_DEPARTMENT`` = brownfield / greenfield, ``BUSINESS`` = business
# line) via ``PLANVIEW_ID → PROJECT_ID``. The IQR thresholds are then
# recomputed *within each segment* before the per-row verdict is applied,
# so a deepwater FPSO is not judged against an onshore-refinery baseline.
# Off by default, the rule keeps its global-IQR behaviour unless the user
# opts in. Projects whose segment lookup is unresolved (missing PLANVIEW_ID,
# unmatched PROJECT_ID, or null/blank E05_DEPARTMENT / BUSINESS) are
# NOT_APPLICABLE → PASS so the segment toggle never double-penalises the
# referential-integrity gap E7 already covers.
EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM = "segment_by_project_type"
EPT_E6_SEGMENT_REFERENCE = {
    "reference_dataset": "VWS_GP_STANDARD_SHARE",
    "source_column": "PLANVIEW_ID",       # in EPT
    "reference_column": "PROJECT_ID",     # in VWS_GP_STANDARD_SHARE
    "segment_columns": ("E05_DEPARTMENT", "BUSINESS"),
}

EPT_E7_REQUIRED_COLUMNS = {
    "Project Key": "PLANVIEW_ID",
}

EPT_E7_REFERENCE = {
    # Lives in the same warehouse / database / schema as the EPT primary
    # table; the reference dataset registry resolves the loader for the
    # active data source (mock vs. Databricks).
    "reference_dataset": "VWS_GP_STANDARD_SHARE",
    "source_column": "PLANVIEW_ID",      # in EPT
    "reference_column": "PROJECT_ID",    # in VWS_GP_STANDARD_SHARE
}


def check_ept_e1(df: pd.DataFrame) -> pd.Series:
    """E1: ISO Code of Account Present. Row passes when *both*
    CODE_OF_RESOURCE and STANDARD_ACTIVITY_BREAKDOWN are populated."""
    return validate_completeness_rule(df, EPT_E1_REQUIRED_COLUMNS.values())


def check_ept_e2(df: pd.DataFrame) -> pd.Series:
    """E2: Location + Estimate Date Present.

    Row passes when *both* hold:
    - ``CENTROID_DATE`` (estimate basis date, in EPT) is non-null/non-blank.
    - ``COUNTRY`` (project location) is non-null/non-blank in the Planview
      reference after joining EPT.PLANVIEW_ID = VWS_GP_STANDARD_SHARE.PROJECT_ID.
      An unmatched PLANVIEW_ID is treated as a missing COUNTRY.

    Raises :class:`CustomRuleNotEvaluated` when the reference dataset is
    unavailable, so the rule never silently passes when the join target is
    missing.
    """
    from src.reference_data import (
        get_reference_dataset,
        get_reference_dataset_error,
    )

    if "CENTROID_DATE" not in df.columns or "PLANVIEW_ID" not in df.columns:
        return pd.Series(False, index=df.index)

    ref_name = EPT_E2_REFERENCE["reference_dataset"]
    reference_df = get_reference_dataset(ref_name)
    if reference_df is None:
        cached_error = get_reference_dataset_error(ref_name)
        detail = f": {cached_error}" if cached_error else ""
        raise CustomRuleNotEvaluated(
            f"EPT E2: '{ref_name}' reference dataset is unavailable{detail}; "
            "COUNTRY linkage cannot be validated."
        )

    centroid_ok = _is_filled(df["CENTROID_DATE"])

    ref_col = EPT_E2_REFERENCE["reference_column"]
    lookup_col = EPT_E2_REFERENCE["lookup_column"]
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
    return centroid_ok & country_ok


def check_ept_e3(
    df: pd.DataFrame, params: EPTE3Params | None = None
) -> pd.Series:
    """E3: Statistical Excessive WBC-to-ISO Mapping.

    Row-level evaluation backed by group-level statistics: an ISO mapping
    (``CODE_OF_RESOURCE`` + ``STANDARD_ACTIVITY_BREAKDOWN``) FAILS when it
    aggregates more distinct ``WBC_LEVEL_5`` values than the 90th-percentile
    ratio observed across all eligible mappings, **and** the mapping is
    material (``SUM(TOTAL_HOURS) > 0`` or
    ``SUM(TOTAL_COST_USD) >= EPT_E3_MATERIALITY_USD``). Every row that
    belongs to a failing group fails; every other row passes.

    ``params[EPT_E3_PROJECT_SCOPED_PARAM]`` (bool, default False) switches
    the percentile baseline:

    - **False**: global scope (default): one P90 across every eligible ISO
      mapping in the dataset.
    - **True**: project scope: the group key becomes
      ``(PLANVIEW_ID, COR, SAB)`` and the P90 is recomputed within each
      ``PLANVIEW_ID`` partition. Every project is therefore judged against
      its own peers, which is the right framing when projects differ in
      maturity / WBC discipline.

    ``params[EPT_E3_THRESHOLD_PARAM]`` (float in (0, 1], default
    :data:`EPT_E3_PERCENTILE` = 0.90) customizes the percentile threshold.
    Choices surfaced in Step 4.2 (:data:`EPT_E3_THRESHOLD_CHOICES`): P75
    (lenient), P90 (recommended), P95 (strict), P99 (very strict). The
    helper :func:`_coerce_threshold` falls back to the default when the
    param is missing or malformed.

    ``params[EPT_E3_DETECT_UNIFORM_MAPPING_PARAM]`` (bool, default False)
    layers a uniform-1:1 detector on top of the percentile fail: when on,
    any material group whose ratio equals 1 also fails (suggesting the WBC
    structure is being copied 1:1 into the ISO bucket rather than
    aggregated). Off by default so existing scorecards stay stable.

    Rows whose ISO key is missing are treated as PASS so E3 does not
    double-penalize E1 (which already flags missing COR/SAB). When project
    scope is on, rows lacking ``PLANVIEW_ID`` are likewise treated as PASS
    (E7 already covers the missing-project linkage).
    """
    p = params or {}
    project_scoped = p.get(EPT_E3_PROJECT_SCOPED_PARAM, False)
    detect_uniform = p.get(EPT_E3_DETECT_UNIFORM_MAPPING_PARAM, False)
    percentile = _coerce_threshold(
        p.get(EPT_E3_THRESHOLD_PARAM), EPT_E3_PERCENTILE
    )

    required = list(EPT_E3_REQUIRED_COLUMNS.values())
    if project_scoped:
        required = required + list(
            EPT_E3_PROJECT_SCOPED_REQUIRED_COLUMNS.values()
        )
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    cor = df["CODE_OF_RESOURCE"]
    sab = df["STANDARD_ACTIVITY_BREAKDOWN"]
    wbc = df["WBC_LEVEL_5"]
    hours = pd.to_numeric(df["TOTAL_HOURS"], errors="coerce").fillna(0.0)
    cost = pd.to_numeric(df["TOTAL_COST_USD"], errors="coerce").fillna(0.0)

    in_scope = _is_filled(cor) & _is_filled(sab)
    if project_scoped:
        in_scope &= _is_filled(df["PLANVIEW_ID"])
    if not in_scope.any():
        return pd.Series(True, index=df.index)

    cor_norm = cor.astype(object).astype(str).str.strip()
    sab_norm = sab.astype(object).astype(str).str.strip()
    if project_scoped:
        pv_norm = df["PLANVIEW_ID"].astype(object).astype(str).str.strip()
        group_id = pd.Series(
            list(zip(pv_norm, cor_norm, sab_norm)), index=df.index
        )
    else:
        group_id = pd.Series(
            list(zip(cor_norm, sab_norm)), index=df.index
        )
    group_id = group_id.where(in_scope)

    wbc_clean = wbc.where(_is_filled(wbc))
    work = pd.DataFrame({
        "_gid": group_id[in_scope],
        "_wbc": wbc_clean[in_scope],
        "_hours": hours[in_scope],
        "_cost": cost[in_scope],
    })
    grouped = work.groupby("_gid", dropna=True, sort=False)
    metrics = pd.DataFrame({
        "ratio": grouped["_wbc"].nunique(dropna=True),
        "hours_sum": grouped["_hours"].sum(),
        "cost_sum": grouped["_cost"].sum(),
    })

    eligible = metrics["ratio"] >= 1
    if not eligible.any():
        return pd.Series(True, index=df.index)

    if project_scoped:
        # Recompute P90 within each PLANVIEW_ID partition so projects with
        # genuinely fine-grained WBC discipline aren't dragged down by
        # peers that aggregate aggressively.
        planview_keys = pd.Index(
            [gid[0] for gid in metrics.index], name="planview"
        )
        ratios_by_pv = (
            metrics.loc[eligible, "ratio"]
            .groupby(planview_keys[eligible], sort=False)
        )
        p90_by_pv = ratios_by_pv.quantile(percentile)
        applicable_p90 = planview_keys.map(p90_by_pv).to_numpy()
    else:
        global_p90 = float(metrics.loc[eligible, "ratio"].quantile(percentile))
        applicable_p90 = pd.Series(global_p90, index=metrics.index).to_numpy()

    metrics["material"] = (metrics["hours_sum"] > 0) | (
        metrics["cost_sum"] >= EPT_E3_MATERIALITY_USD
    )
    outlier_fail = (
        (metrics["ratio"].to_numpy() > applicable_p90)
        & metrics["material"].to_numpy()
    )
    if detect_uniform:
        # Suspiciously uniform 1:1 buckets, each ISO mapping holds exactly
        # one distinct WBC. Layered on top of the percentile fail with OR so
        # both signals coexist when the user opts in. Materiality still
        # applies to keep planning / structural-only rows from flooding.
        uniform_fail = (
            (metrics["ratio"].to_numpy() == 1)
            & metrics["material"].to_numpy()
        )
        metrics["fail"] = outlier_fail | uniform_fail
    else:
        metrics["fail"] = outlier_fail

    fail_lookup = metrics["fail"].to_dict()
    # Cast to nullable bool dtype before fillna so pandas doesn't emit the
    # object→bool downcast FutureWarning when group_id has NaN entries.
    row_fail = (
        group_id.map(fail_lookup)
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )
    return ~row_fail


def check_ept_e4(df: pd.DataFrame) -> pd.Series:
    """E4: Level 1 cost category populated. Row passes when ``WBC_LEVEL_1``
    is non-null and non-blank."""
    return validate_completeness_rule(df, EPT_E4_REQUIRED_COLUMNS.values())


def check_ept_e5(df: pd.DataFrame) -> pd.Series:
    """E5: FEED / Engineering hours estimate present when cost exists.

    A row is in scope when ``WBC_LEVEL_1`` matches
    :data:`EPT_E5_FEED_ENGINEERING_PATTERN` (case-insensitive). For in-scope
    rows the rule compares two derived amounts:

    - ``cost_amount  = COALESCE(TOTAL_COST_USD, TOTAL_COST_ESTIMATE_CURRENCY, 0)``
    - ``hours_amount = COALESCE(TOTAL_HOURS, 0)``

    A row passes when both amounts are present (``> 0``) or both are absent
    (``== 0``); it fails when exactly one side is present (cost without
    hours, or hours without cost). Non-FEED / non-Engineering rows are
    Not Applicable and pass - only the FEED scope is judged here.

    Null numeric inputs are treated as zero. If any required column is
    absent from ``df`` the rule fails for every row (the dataset is
    structurally incomplete, same convention as the other custom rules).
    """
    required = list(EPT_E5_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    wbc1 = df["WBC_LEVEL_1"]
    in_scope = _is_filled(wbc1) & wbc1.astype(object).astype(str).str.contains(
        EPT_E5_FEED_ENGINEERING_PATTERN, case=False, regex=True, na=False
    )

    cost_usd = pd.to_numeric(df["TOTAL_COST_USD"], errors="coerce")
    cost_local = pd.to_numeric(df["TOTAL_COST_ESTIMATE_CURRENCY"], errors="coerce")
    cost_amount = cost_usd.where(cost_usd.notna(), cost_local).fillna(0.0)
    hours_amount = pd.to_numeric(df["TOTAL_HOURS"], errors="coerce").fillna(0.0)

    has_cost = cost_amount > 0
    has_hours = hours_amount > 0
    consistent = (has_cost & has_hours) | (~has_cost & ~has_hours)

    return (~in_scope) | consistent

def check_ept_e6(
    df: pd.DataFrame, params: EPTE6Params | None = None
) -> pd.Series:
    """E6: Cost-to-hours ratio outlier check.

    Aggregates per ``PLANVIEW_ID``:

    - ``cost_amount  = COALESCE(TOTAL_COST_USD, TOTAL_COST_ESTIMATE_CURRENCY, 0)``
    - ``hours_amount = COALESCE(TOTAL_HOURS, 0)``

    Computes ``cost_to_hours_ratio = SUM(cost_amount) / SUM(hours_amount)``
    for every project with ``hours_amount > 0`` and flags projects whose
    ratio falls outside the IQR outlier bounds derived from the project
    population (``Q1 - k*IQR`` … ``Q3 + k*IQR``, where ``k`` defaults to
    :data:`EPT_E6_MILD_IQR_MULTIPLIER` = 1.5 and is customizable via
    ``params[EPT_E6_THRESHOLD_PARAM]``). Every row in a flagged project
    inherits the FAIL, same row-level / group-verdict pattern as E3.

    ``params[EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM]`` (bool, default False)
    switches the IQR baseline to a per-segment one. The segment key is the
    composite ``(E05_DEPARTMENT, BUSINESS)`` tuple looked up from the
    ``VWS_GP_STANDARD_SHARE`` reference via ``PLANVIEW_ID → PROJECT_ID``.
    Each segment derives its own ``Q1 / Q3 / IQR``; a project is only
    judged against peers of the same type, so a deepwater FPSO and an
    onshore refinery are not pooled into the same baseline. Segments below
    :data:`EPT_E6_MIN_POPULATION` are NOT_APPLICABLE → PASS so a thinly
    populated bucket does not turn every project inside it into an outlier
    of itself. Projects whose segment is unresolved (missing PLANVIEW_ID,
    unmatched PROJECT_ID, null/blank ``E05_DEPARTMENT`` / ``BUSINESS``)
    are likewise NOT_APPLICABLE → PASS - E7 / E2 already cover the
    referential-integrity / completeness gap. Raises
    :class:`CustomRuleNotEvaluated` when the toggle is on and the
    reference dataset is unavailable.

    NOT_APPLICABLE cases (treated as PASS so they do not double-penalize
    other rules):

    - Project where ``project_total_hours <= 0``, the ratio cannot be
      calculated; completeness / consistency rules (e.g. E5) cover this.
    - Rows lacking ``PLANVIEW_ID`` - cannot be assigned to a project; E7
      already covers the missing-project linkage.
    - Population (eligible-project count) below
      :data:`EPT_E6_MIN_POPULATION` - too small to derive thresholds.
      When segmentation is on, the same floor is applied per segment.

    Schema-level missing columns make every row fail (same convention as
    the other custom rules).
    """
    p = params or {}
    iqr_multiplier = _coerce_threshold(
        p.get(EPT_E6_THRESHOLD_PARAM),
        EPT_E6_MILD_IQR_MULTIPLIER,
    )
    segmented = p.get(EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM, False)

    required = list(EPT_E6_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    if df.empty:
        return pd.Series(True, index=df.index)

    pv = df["PLANVIEW_ID"]
    cost_usd = pd.to_numeric(df["TOTAL_COST_USD"], errors="coerce")
    cost_local = pd.to_numeric(df["TOTAL_COST_ESTIMATE_CURRENCY"], errors="coerce")
    cost_amount = cost_usd.where(cost_usd.notna(), cost_local).fillna(0.0)
    hours_amount = pd.to_numeric(df["TOTAL_HOURS"], errors="coerce").fillna(0.0)

    in_scope = _is_filled(pv)
    if not in_scope.any():
        return pd.Series(True, index=df.index)

    pv_norm = pv.astype(object).astype(str).str.strip().where(in_scope)
    work = pd.DataFrame({
        "_pv": pv_norm[in_scope],
        "_cost": cost_amount[in_scope],
        "_hours": hours_amount[in_scope],
    })
    grouped = work.groupby("_pv", dropna=True, sort=False)
    project_metrics = pd.DataFrame({
        "cost_sum": grouped["_cost"].sum(),
        "hours_sum": grouped["_hours"].sum(),
    })
    project_metrics["fail"] = False

    eligible = project_metrics["hours_sum"] > 0
    if not eligible.any():
        return pd.Series(True, index=df.index)

    ratios = (
        project_metrics.loc[eligible, "cost_sum"]
        / project_metrics.loc[eligible, "hours_sum"]
    )

    if segmented:
        # Resolve PLANVIEW_ID → segment via the Planview reference; project
        # whose segment cannot be resolved or has any null component is
        # treated as NOT_APPLICABLE → PASS (mirrors the unmatched-key
        # convention used by E2). The lookup is pre-cleaned by
        # ``_resolve_planview_segment_map`` (null/blank dept/business
        # already dropped, every value stripped), so resolution collapses
        # to a single dict-get per project.
        segment_lookup = _resolve_planview_segment_map(
            EPT_E6_SEGMENT_REFERENCE, "EPT E6"
        )
        segments = pd.Series(
            [segment_lookup.get(k) for k in project_metrics.index],
            index=project_metrics.index,
            dtype=object,
        )
        resolved = segments.notna() & eligible
        if not resolved.any():
            return pd.Series(True, index=df.index)

        fails_by_pv: Dict[str, bool] = {}
        ratios_resolved = ratios[resolved.loc[ratios.index]]
        for seg_key, seg_ratios in ratios_resolved.groupby(segments[resolved]):
            if len(seg_ratios) < EPT_E6_MIN_POPULATION:
                continue
            q1 = float(seg_ratios.quantile(0.25))
            q3 = float(seg_ratios.quantile(0.75))
            iqr = q3 - q1
            lower = q1 - iqr_multiplier * iqr
            upper = q3 + iqr_multiplier * iqr
            seg_fail = (seg_ratios < lower) | (seg_ratios > upper)
            for pv_key, failed in seg_fail.items():
                if bool(failed):
                    fails_by_pv[pv_key] = True

        if fails_by_pv:
            project_metrics.loc[
                project_metrics.index.isin(fails_by_pv), "fail"
            ] = True
    else:
        if eligible.sum() < EPT_E6_MIN_POPULATION:
            # Either no project has positive hours, or population is too
            # small to derive statistical thresholds, every row is
            # NOT_APPLICABLE.
            return pd.Series(True, index=df.index)

        q1 = float(ratios.quantile(0.25))
        q3 = float(ratios.quantile(0.75))
        iqr = q3 - q1
        lower_mild = q1 - iqr_multiplier * iqr
        upper_mild = q3 + iqr_multiplier * iqr

        project_metrics.loc[eligible, "fail"] = (
            (ratios < lower_mild) | (ratios > upper_mild)
        ).to_numpy()

    fail_lookup = project_metrics["fail"].to_dict()
    # Cast to nullable bool dtype before fillna so pandas doesn't emit the
    # object→bool downcast FutureWarning when pv_norm has NaN entries.
    row_fail = (
        pv_norm.map(fail_lookup)
        .astype("boolean")
        .fillna(False)
        .astype(bool)
    )
    return ~row_fail


def check_ept_e7(df: pd.DataFrame) -> pd.Series:
    """E7: Project Key linkage. Row passes when ``PLANVIEW_ID`` is filled
    *and* resolves against the ``VWS_GP_STANDARD_SHARE.PROJECT_ID``
    reference column.

    Raises :class:`CustomRuleNotEvaluated` when the reference table is
    unavailable, so the rule never silently passes on missing dependencies.
    The actual loader error (e.g. Databricks auth / missing table) is
    propagated when it was captured by ``prefetch_reference_datasets``.
    """
    # Imported lazily so importing this module doesn't hard-fail when no
    # data source is configured (e.g. during certain test setups).
    from src.reference_data import (
        get_reference_dataset,
        get_reference_dataset_error,
    )

    if "PLANVIEW_ID" not in df.columns:
        return pd.Series(False, index=df.index)
    ref_name = EPT_E7_REFERENCE["reference_dataset"]
    reference_df = get_reference_dataset(ref_name)
    if reference_df is None:
        cached_error = get_reference_dataset_error(ref_name)
        detail = f": {cached_error}" if cached_error else ""
        raise CustomRuleNotEvaluated(
            f"EPT E7: '{ref_name}' reference dataset is unavailable{detail}; "
            "PLANVIEW_ID linkage cannot be validated."
        )
    return validate_referential_integrity_rule(
        df,
        EPT_E7_REFERENCE["source_column"],
        reference_df,
        EPT_E7_REFERENCE["reference_column"],
    )

