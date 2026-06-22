# pyright: reportReturnType=false
"""
Data Quality Rule (DQR) engine.

Each DQR is executed as a function that takes:
  - a DataFrame
  - a CDE column name
  - a params dict
and returns a pandas Boolean Series (True = row passes the rule).

The engine dispatches by dimension name. Users can edit params per rule
through the UI.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config.dqr_catalog import DIMENSIONS, suggest_dimensions_for
from src.models import ColumnProfile, DQRAssignment

logger = logging.getLogger(__name__)


# =============================================================================
# Rule implementations (one per dimension)
# =============================================================================

def _rule_completeness(df: pd.DataFrame, col: str, params: Dict[str, Any]) -> pd.Series:
    s = df[col]
    result = s.notna()
    if not params.get("allow_empty_string", False):
        # String empty is also considered missing
        if pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s):
            result &= s.astype(str).str.strip().ne("")
    return result


def _rule_uniqueness(df: pd.DataFrame, col: str, params: Dict[str, Any]) -> pd.Series:
    """A row passes if its value in `col` is unique in the column (appears once).

    Uses ``duplicated(keep=False)`` (vectorized in C). Matches the previous
    ``map(value_counts(dropna=False)) == 1`` semantics: a single NaN counts
    as "unique" (nullness is Completeness' concern), but two-or-more NaNs
    fail because each occurrence is a duplicate of the other.
    """
    return ~df[col].duplicated(keep=False)


def _rule_validity(df: pd.DataFrame, col: str, params: Dict[str, Any]) -> pd.Series:
    """Regex match and/or length bounds. Datetime and numeric also validated by type."""
    s = df[col]
    regex = params.get("regex")
    min_len = params.get("min_length")
    max_len = params.get("max_length")

    result = pd.Series(True, index=df.index)

    # Type-specific validity
    if pd.api.types.is_datetime64_any_dtype(s):
        # Already parsed successfully as datetime → valid
        result &= s.notna()
    elif pd.api.types.is_numeric_dtype(s):
        result &= s.notna() & np.isfinite(s.fillna(np.nan))
    else:
        if regex:
            # Vectorized regex via pandas' C-level str accessor; NaN
            # propagates as NaN which the outer ``s.notna()`` mask zeroes
            # out below (and ``evaluate_rule`` ``fillna(False)`` covers
            # any straggler).
            result &= s.astype(str).str.fullmatch(regex).fillna(False)
        if min_len is not None:
            result &= s.astype(str).str.len() >= int(min_len)
        if max_len is not None:
            result &= s.astype(str).str.len() <= int(max_len)
        # Nulls are considered invalid under Validity
        result &= s.notna()
    return result


def _rule_accuracy(df: pd.DataFrame, col: str, params: Dict[str, Any]) -> pd.Series:
    """Value within [min_value, max_value] if provided."""
    s = df[col]
    result = pd.Series(True, index=df.index)
    min_v = params.get("min_value")
    max_v = params.get("max_value")
    if min_v is not None:
        result &= s >= float(min_v)
    if max_v is not None:
        result &= s <= float(max_v)
    # Nulls are treated as failing accuracy
    result &= s.notna()
    return result.fillna(False)


def _rule_consistency(df: pd.DataFrame, col: str, params: Dict[str, Any]) -> pd.Series:
    """Compare col against another column using an operator."""
    compare = params.get("compare_column")
    op = params.get("operator", "<=")
    result = pd.Series(True, index=df.index)
    if not compare or compare not in df.columns:
        return result  # no-op if not configured
    a = df[col]
    b = df[compare]
    both_present = a.notna() & b.notna()
    if op == "<=":
        test = a <= b
    elif op == ">=":
        test = a >= b
    elif op == "<":
        test = a < b
    elif op == ">":
        test = a > b
    elif op == "==":
        test = a == b
    elif op == "!=":
        test = a != b
    else:
        return result
    return (test & both_present) | (~both_present)


def _rule_timeliness(df: pd.DataFrame, col: str, params: Dict[str, Any]) -> pd.Series:
    """Max lag (in days) between `col` and today. Works only for date-like columns."""
    s = pd.to_datetime(df[col], errors="coerce", utc=True).dt.tz_localize(None)
    max_lag = int(params.get("max_lag_days", 30))
    ref = pd.Timestamp(datetime.now())
    lag = (ref - s).dt.days
    return (lag <= max_lag) & s.notna()


def _rule_currency(df: pd.DataFrame, col: str, params: Dict[str, Any]) -> pd.Series:
    """Similar to timeliness but typically a larger window (freshness)."""
    s = pd.to_datetime(df[col], errors="coerce", utc=True).dt.tz_localize(None)
    max_age = int(params.get("max_age_days", 365))
    ref = pd.Timestamp(datetime.now())
    age = (ref - s).dt.days
    return (age <= max_age) & s.notna()


def _rule_conformity(df: pd.DataFrame, col: str, params: Dict[str, Any]) -> pd.Series:
    """Value is in the provided allowed_values set."""
    allowed = params.get("allowed_values") or []
    if not allowed:
        return pd.Series(True, index=df.index)
    return df[col].isin(allowed)


def _rule_integrity(df: pd.DataFrame, col: str, params: Dict[str, Any]) -> pd.Series:
    """Value exists in a reference_values list (referential integrity)."""
    refs = params.get("reference_values") or []
    if not refs:
        # Fallback: non-null means passes (better than always True)
        return df[col].notna()
    return df[col].isin(refs)


def _rule_precision(df: pd.DataFrame, col: str, params: Dict[str, Any]) -> pd.Series:
    """Numeric values have at most max_decimals decimals.

    Vectorized via numpy: scale by ``10**max_decimals`` and check that the
    result is within a small tolerance of an integer. The tolerance
    absorbs float-representation noise (e.g. ``0.1 * 100 == 10.000...001``)
    while still catching genuinely over-precise values.
    """
    s = df[col]
    max_decimals = int(params.get("max_decimals", 2))
    if not pd.api.types.is_numeric_dtype(s):
        return pd.Series(True, index=df.index)
    factor = 10 ** max_decimals
    scaled = s.astype(float) * factor
    remainder = (scaled - scaled.round()).abs()
    # NaN fails the rule (matches the original ``_ok`` contract).
    return s.notna() & (remainder < 1e-9)


# =============================================================================
# Dispatcher
# =============================================================================

_DISPATCH = {
    "Completeness": _rule_completeness,
    "Uniqueness": _rule_uniqueness,
    "Validity": _rule_validity,
    "Accuracy": _rule_accuracy,
    "Consistency": _rule_consistency,
    "Timeliness": _rule_timeliness,
    "Currency": _rule_currency,
    "Conformity": _rule_conformity,
    "Integrity": _rule_integrity,
    "Precision": _rule_precision,
}


def evaluate_rule(df: pd.DataFrame, assignment: DQRAssignment) -> pd.Series:
    func = _DISPATCH.get(assignment.dimension)
    if func is None:
        raise KeyError(f"Dimension not implemented: {assignment.dimension}")
    result = func(df, assignment.cde_column, assignment.params or {})
    # Ensure Boolean + aligned
    return result.fillna(False).astype(bool)


def evaluate_all(df: pd.DataFrame, assignments: List[DQRAssignment]) -> pd.DataFrame:
    """Return a DataFrame with one Boolean column per rule_id (True = pass).

    Raises whatever the underlying rule raises - used by callers that have
    already pre-validated assignments. Defensive callers (e.g. the
    scorecard) should use :func:`evaluate_all_safe` instead.
    """
    out = pd.DataFrame(index=df.index)
    for a in assignments:
        out[a.rule_id] = evaluate_rule(df, a)
    return out


def evaluate_all_safe(
    df: pd.DataFrame,
    assignments: List[DQRAssignment],
    profiles: Optional[Dict[str, ColumnProfile]] = None,
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Like :func:`evaluate_all`, but never raises.

    - Pre-validates each assignment via :mod:`src.dqr_validation` and skips
      any rule that has a blocking compatibility error (recorded in the
      returned ``not_computed`` map with a human-readable reason).
    - Wraps the rule body in ``try/except`` so an unexpected runtime error
      (e.g. a TypeError comparing date with float that the static
      validation didn't anticipate) does not crash Step 6, the rule is
      marked "Not computed" and the dashboard still renders the rest.

    Returns ``(results_df, not_computed)`` where ``results_df`` carries one
    Boolean column per *successfully evaluated* ``rule_id``.
    """
    # Imported lazily to avoid a circular import: dqr_validation depends on
    # dqr_catalog which is also imported at the top of this file.
    from src.dqr_validation import validate_assignments_for_dp

    results: Dict[str, pd.Series] = {}
    not_computed: Dict[str, str] = {}
    if not assignments:
        return pd.DataFrame(index=df.index), not_computed

    # When the caller did not supply profiles (legacy fixtures, ad-hoc
    # scoring, etc.) we skip the static compatibility check entirely and
    # still rely on the per-rule try/except below to keep Step 6 from
    # crashing. Production always supplies ``dp.profiles``.
    reports = (
        validate_assignments_for_dp(assignments, profiles)
        if profiles else {}
    )

    for a in assignments:
        report = reports.get(a.rule_id)
        if report is not None and not report.is_valid:
            not_computed[a.rule_id] = (
                report.reason_string() or "Invalid configuration."
            )
            continue
        try:
            results[a.rule_id] = evaluate_rule(df, a)
        except Exception as exc:  # pragma: no cover - defensive last line
            # Broad on purpose: this is the last line of defense for Step 6,
            # any unexpected failure must downgrade to "Not computed" instead
            # of crashing the dashboard. Logged so prod runs leave a trail
            # the user can dig into rather than a silent swallow.
            logger.warning(
                "Standard DQR %s raised; marking as Not computed",
                a.rule_id,
                exc_info=True,
            )
            not_computed[a.rule_id] = (
                f"Unable to compute this Standard DQR: {exc}"
            )

    if not results:
        return pd.DataFrame(index=df.index), not_computed
    return pd.DataFrame(results, index=df.index), not_computed


# =============================================================================
# Suggestion helpers
# =============================================================================

def suggest_assignments_for_cde(profile: ColumnProfile) -> List[DQRAssignment]:
    """Return initial DQR assignments for one CDE, based on its profile."""
    dims = suggest_dimensions_for(profile.column_type_group, profile.name)
    assignments: List[DQRAssignment] = []
    for d in dims:
        params = dict(DIMENSIONS[d].default_params)
        # Pre-fill parameters from the profile where it helps
        if d == "Accuracy" and profile.min_value is not None and profile.max_value is not None:
            try:
                params["min_value"] = float(profile.min_value)
                params["max_value"] = float(profile.max_value)
            except (TypeError, ValueError):
                pass
        if d == "Conformity" and profile.distinct_count <= 30:
            # Not auto-filling allowed_values to force the user to confirm the domain.
            pass
        assignments.append(DQRAssignment(cde_column=profile.name, dimension=d, params=params))
    return assignments
