"""
Standard DQR compatibility validation.

Each of the 10 standard dimensions declares which CDE column-type groups it
can sensibly run against and which parameter shapes are compatible with that
CDE. This module is consumed by:

- **Step 4.1** ([ui/step_04_dqr_assignment.py](../ui/step_04_dqr_assignment.py))
  to surface per-dimension visual feedback and gate the **Next** button while
  any error is unresolved.
- **Step 6 / scorecard** ([src/scorecard.py](../src/scorecard.py)) as a
  defensive guard: rules with validation errors are skipped (and recorded in
  ``ScorecardResult.not_computed_standard_rules``) instead of crashing the
  pipeline.

The validation answers two distinct questions:

1. *Is the dimension applicable to the CDE's data type?*, e.g. Accuracy on
   a string column makes no sense.
2. *Are the user's parameters compatible with the CDE's data type?*, e.g.
   a Consistency rule comparing a date CDE against a numeric column would
   raise ``TypeError`` deep inside pandas during scoring.

Issues carry a severity (``"error"`` blocks Next; ``"warning"`` is purely
informational) and an optional suggestion string so the UI can guide the
user toward a compatible configuration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

from config.dqr_catalog import (
    COLUMN_TYPE_BOOLEAN,
    COLUMN_TYPE_CATEGORICAL,
    COLUMN_TYPE_DATE,
    COLUMN_TYPE_DATETIME,
    COLUMN_TYPE_FLOAT,
    COLUMN_TYPE_ID,
    COLUMN_TYPE_INTEGER,
    COLUMN_TYPE_NUMERIC,
    COLUMN_TYPE_STRING,
)
from src.models import ColumnProfile, DQRAssignment

# =============================================================================
# Type-group families
# =============================================================================

NUMERIC_GROUPS: Set[str] = {
    COLUMN_TYPE_NUMERIC, COLUMN_TYPE_INTEGER, COLUMN_TYPE_FLOAT,
}
TEMPORAL_GROUPS: Set[str] = {COLUMN_TYPE_DATE, COLUMN_TYPE_DATETIME}
TEXTUAL_GROUPS: Set[str] = {
    COLUMN_TYPE_STRING, COLUMN_TYPE_CATEGORICAL, COLUMN_TYPE_ID,
}

# Which CDE column-type groups a dimension can sensibly run against. A CDE
# whose group is *not* in the set raises an error in
# :func:`validate_assignment` - Step 4.1 disables Next until the user either
# unticks the dimension or picks a compatible CDE.
DIMENSION_SUPPORTED_GROUPS: Dict[str, Set[str]] = {
    "Completeness": (
        NUMERIC_GROUPS | TEMPORAL_GROUPS | TEXTUAL_GROUPS | {COLUMN_TYPE_BOOLEAN}
    ),
    "Uniqueness": NUMERIC_GROUPS | TEMPORAL_GROUPS | TEXTUAL_GROUPS,
    "Validity": NUMERIC_GROUPS | TEMPORAL_GROUPS | TEXTUAL_GROUPS,
    "Accuracy": NUMERIC_GROUPS,
    "Consistency": (
        NUMERIC_GROUPS | TEMPORAL_GROUPS | TEXTUAL_GROUPS | {COLUMN_TYPE_BOOLEAN}
    ),
    "Timeliness": TEMPORAL_GROUPS,
    "Currency": TEMPORAL_GROUPS,
    "Conformity": TEXTUAL_GROUPS | NUMERIC_GROUPS | {COLUMN_TYPE_BOOLEAN},
    "Integrity": TEXTUAL_GROUPS | NUMERIC_GROUPS,
    "Precision": NUMERIC_GROUPS,
}

VALID_CONSISTENCY_OPERATORS: Tuple[str, ...] = (
    "<=", "<", ">=", ">", "==", "!=",
)


# =============================================================================
# Data classes
# =============================================================================

@dataclass(frozen=True)
class DQRValidationIssue:
    """One validation finding. ``severity`` is ``"error"`` (blocking) or
    ``"warning"`` (informational)."""
    severity: str
    message: str
    suggestion: Optional[str] = None


@dataclass(frozen=True)
class DQRValidationReport:
    """Outcome of validating a single :class:`DQRAssignment`."""
    issues: Tuple[DQRValidationIssue, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        """No error-severity issues - Step 4.1 lets the user advance and
        Step 6 will compute the rule."""
        return not any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity == "warning" for i in self.issues)

    @property
    def errors(self) -> Tuple[DQRValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "error")

    @property
    def warnings(self) -> Tuple[DQRValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "warning")

    def reason_string(self) -> str:
        """Single-line, human-readable summary of *blocking* issues - used by
        :class:`ScorecardResult.not_computed_standard_rules`."""
        parts = [i.message for i in self.errors]
        return "; ".join(parts) if parts else ""


# =============================================================================
# Helpers
# =============================================================================

def _category_label(group: Optional[str]) -> str:
    """Friendly label used in user-facing messages."""
    if group in NUMERIC_GROUPS:
        return "numeric"
    if group in TEMPORAL_GROUPS:
        return "date/datetime"
    if group in TEXTUAL_GROUPS:
        return "text"
    if group == COLUMN_TYPE_BOOLEAN:
        return "boolean"
    return str(group) if group is not None else "unknown"


def _category_set_label(groups: Iterable[str]) -> str:
    """Comma-separated, deduplicated labels - e.g. ``"numeric, text"``."""
    return ", ".join(sorted({_category_label(g) for g in groups}))


def _categories_compatible(
    a: Optional[str], b: Optional[str]
) -> bool:
    """Loose compatibility for cross-column comparisons (Consistency)."""
    if a is None or b is None:
        return False
    if a in NUMERIC_GROUPS and b in NUMERIC_GROUPS:
        return True
    if a in TEMPORAL_GROUPS and b in TEMPORAL_GROUPS:
        return True
    if a in TEXTUAL_GROUPS and b in TEXTUAL_GROUPS:
        return True
    if a == COLUMN_TYPE_BOOLEAN and b == COLUMN_TYPE_BOOLEAN:
        return True
    return False


def _looks_numeric(value) -> bool:
    if value is None:
        return False
    try:
        float(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False


# =============================================================================
# Public API
# =============================================================================

def validate_assignment(
    assignment: DQRAssignment,
    profile: Optional[ColumnProfile],
    profiles: Optional[Dict[str, ColumnProfile]] = None,
) -> DQRValidationReport:
    """Return a :class:`DQRValidationReport` for ``assignment``.

    Parameters
    ----------
    assignment
        The user's selection (CDE column + dimension + parameters).
    profile
        Profile for ``assignment.cde_column``. Pass ``None`` only if the
        column has no profile, that itself becomes a blocking error.
    profiles
        Full per-column profile map for the data product. Required for
        cross-column dimensions (Consistency); ignored otherwise.
    """
    profiles = profiles or {}
    issues: List[DQRValidationIssue] = []
    params = assignment.params or {}
    dim = assignment.dimension

    if profile is None:
        return DQRValidationReport(issues=(
            DQRValidationIssue(
                severity="error",
                message=(
                    f"CDE `{assignment.cde_column}` has no column profile, so "
                    f"`{dim}` cannot be validated."
                ),
                suggestion="Re-pick the CDE in Step 3 so its profile is built.",
            ),
        ))

    supported = DIMENSION_SUPPORTED_GROUPS.get(dim)
    if supported is not None and profile.column_type_group not in supported:
        issues.append(DQRValidationIssue(
            severity="error",
            message=(
                f"`{dim}` is not applicable to a "
                f"{_category_label(profile.column_type_group)} column "
                f"(`{profile.name}`)."
            ),
            suggestion=(
                f"Pick a compatible column or choose a different dimension. "
                f"Compatible types: {_category_set_label(supported)}."
            ),
        ))

    # Parameter-level checks. These run even when the dimension/CDE pair is
    # incompatible, because the user may fix the parameter side first.
    if dim == "Validity":
        issues.extend(_validate_validity(profile, params))
    elif dim == "Accuracy":
        issues.extend(_validate_accuracy(profile, params))
    elif dim == "Consistency":
        issues.extend(_validate_consistency(profile, params, profiles))
    elif dim == "Timeliness":
        issues.extend(_validate_positive_int(params, "max_lag_days", "Max lag (days)"))
    elif dim == "Currency":
        issues.extend(_validate_positive_int(params, "max_age_days", "Maximum age (days)"))
    elif dim == "Conformity":
        issues.extend(_validate_value_list(
            profile, params, key="allowed_values", noun="allowed value",
        ))
    elif dim == "Integrity":
        issues.extend(_validate_value_list(
            profile, params, key="reference_values", noun="reference value",
        ))
    elif dim == "Precision":
        issues.extend(_validate_precision(profile, params))

    return DQRValidationReport(issues=tuple(issues))


def validate_assignments_for_dp(
    assignments: Iterable[DQRAssignment],
    profiles: Dict[str, ColumnProfile],
) -> Dict[str, DQRValidationReport]:
    """Validate every assignment for a Data Product.

    Returns a dict keyed by ``DQRAssignment.rule_id`` so callers can look
    up the report next to the matching scorecard entry.
    """
    reports: Dict[str, DQRValidationReport] = {}
    for a in assignments:
        profile = profiles.get(a.cde_column)
        reports[a.rule_id] = validate_assignment(a, profile, profiles)
    return reports


# =============================================================================
# Per-dimension parameter validators
# =============================================================================

def _validate_validity(
    profile: ColumnProfile, params: Dict
) -> List[DQRValidationIssue]:
    issues: List[DQRValidationIssue] = []
    regex = params.get("regex")
    min_len = params.get("min_length")
    max_len = params.get("max_length")
    text_only = bool(regex) or min_len is not None or max_len is not None

    if text_only and profile.column_type_group in NUMERIC_GROUPS:
        issues.append(DQRValidationIssue(
            severity="warning",
            message=(
                "Regex / length bounds are ignored for numeric columns - "
                "Validity falls back to a finite-number check."
            ),
            suggestion="Clear these fields to silence this warning.",
        ))
    elif text_only and profile.column_type_group in TEMPORAL_GROUPS:
        issues.append(DQRValidationIssue(
            severity="warning",
            message=(
                "Regex / length bounds are ignored for date/datetime columns - "
                "Validity falls back to a parsable-date check."
            ),
            suggestion="Clear these fields to silence this warning.",
        ))

    if min_len is not None and max_len is not None:
        try:
            if int(min_len) > int(max_len):
                issues.append(DQRValidationIssue(
                    severity="error",
                    message="Min length cannot be greater than max length.",
                    suggestion="Swap the values or clear one of them.",
                ))
        except (TypeError, ValueError):
            issues.append(DQRValidationIssue(
                severity="error",
                message="Min length and max length must be integers.",
            ))
    return issues


def _validate_accuracy(
    profile: ColumnProfile, params: Dict
) -> List[DQRValidationIssue]:
    issues: List[DQRValidationIssue] = []
    if profile.column_type_group not in NUMERIC_GROUPS:
        # The dimension-supported check already errored, no extra value here.
        return issues
    mn = params.get("min_value")
    mx = params.get("max_value")
    if mn is not None and mx is not None:
        try:
            if float(mn) > float(mx):
                issues.append(DQRValidationIssue(
                    severity="error",
                    message="Min value cannot be greater than max value.",
                    suggestion="Swap the bounds or clear one of them.",
                ))
        except (TypeError, ValueError):
            issues.append(DQRValidationIssue(
                severity="error",
                message="Accuracy bounds must be numeric.",
            ))
    return issues


def _validate_consistency(
    profile: ColumnProfile,
    params: Dict,
    profiles: Dict[str, ColumnProfile],
) -> List[DQRValidationIssue]:
    issues: List[DQRValidationIssue] = []
    compare = params.get("compare_column")
    op = params.get("operator", "<=")

    if op not in VALID_CONSISTENCY_OPERATORS:
        issues.append(DQRValidationIssue(
            severity="error",
            message=f"Unknown operator `{op}`.",
            suggestion=f"Pick one of {', '.join(VALID_CONSISTENCY_OPERATORS)}.",
        ))

    if not compare:
        issues.append(DQRValidationIssue(
            severity="error",
            message="Consistency needs a comparison column.",
            suggestion=(
                "Select a column from the same Data Product to compare "
                "the CDE against."
            ),
        ))
        return issues

    if compare == profile.name:
        issues.append(DQRValidationIssue(
            severity="error",
            message=(
                "Comparison column must be different from the CDE itself."
            ),
        ))
        return issues

    cmp_profile = profiles.get(compare)
    if cmp_profile is None:
        issues.append(DQRValidationIssue(
            severity="error",
            message=(
                f"Comparison column `{compare}` does not exist in this "
                f"Data Product."
            ),
            suggestion="Pick a column that is part of the joined Data Product.",
        ))
        return issues

    if not _categories_compatible(
        profile.column_type_group, cmp_profile.column_type_group
    ):
        issues.append(DQRValidationIssue(
            severity="error",
            message=(
                f"This configuration is not compatible. The selected CDE "
                f"`{profile.name}` is a "
                f"{_category_label(profile.column_type_group)} column, but the "
                f"comparison column `{compare}` is "
                f"{_category_label(cmp_profile.column_type_group)}."
            ),
            suggestion=(
                f"Please select a compatible "
                f"{_category_label(profile.column_type_group)} column or "
                f"adjust the dimension configuration."
            ),
        ))
        return issues

    if op in ("<", "<=", ">", ">=") and profile.column_type_group == COLUMN_TYPE_BOOLEAN:
        issues.append(DQRValidationIssue(
            severity="warning",
            message=(
                "Ordering operators on boolean columns rarely make sense - "
                "consider `==` or `!=`."
            ),
        ))
    return issues


def _validate_positive_int(
    params: Dict, key: str, label: str
) -> List[DQRValidationIssue]:
    value = params.get(key)
    if value is None:
        return []
    try:
        n = int(value)
    except (TypeError, ValueError):
        return [DQRValidationIssue(
            severity="error",
            message=f"{label} must be an integer.",
        )]
    if n <= 0:
        return [DQRValidationIssue(
            severity="error",
            message=f"{label} must be a positive integer.",
        )]
    return []


def _validate_value_list(
    profile: ColumnProfile,
    params: Dict,
    *,
    key: str,
    noun: str,
) -> List[DQRValidationIssue]:
    """Catch the case where the user typed non-numeric literals into the
    allowed/reference list of a numeric CDE, those entries can never match
    and would silently sink the pass rate."""
    values = params.get(key) or []
    if not values:
        return []
    if profile.column_type_group in NUMERIC_GROUPS:
        bad = [v for v in values if not _looks_numeric(v)]
        if bad:
            preview = ", ".join(str(v) for v in bad[:3])
            if len(bad) > 3:
                preview += ", …"
            return [DQRValidationIssue(
                severity="warning",
                message=(
                    f"Some {noun}s are not numeric ({preview}); they will "
                    f"never match a "
                    f"{_category_label(profile.column_type_group)} CDE."
                ),
                suggestion="Replace them with numeric literals.",
            )]
    return []


def _validate_precision(
    profile: ColumnProfile, params: Dict
) -> List[DQRValidationIssue]:
    if profile.column_type_group not in NUMERIC_GROUPS:
        return []
    md = params.get("max_decimals")
    if md is None:
        return []
    try:
        n = int(md)
    except (TypeError, ValueError):
        return [DQRValidationIssue(
            severity="error",
            message="Max decimals must be an integer.",
        )]
    if n < 0:
        return [DQRValidationIssue(
            severity="error",
            message="Max decimals must be ≥ 0.",
        )]
    return []
