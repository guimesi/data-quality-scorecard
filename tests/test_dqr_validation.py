"""Tests for the Standard DQR compatibility-validation layer.

The compatibility checks live in :mod:`src.dqr_validation` and feed both
Step 4.1 (visual feedback + Next-button gating) and Step 6's defensive
evaluator (rules with errors are recorded as Not computed instead of
crashing the dashboard).

Each test pins one acceptance-criterion scenario from the feature spec.
"""
from __future__ import annotations

from src.dqr_validation import (
    DIMENSION_SUPPORTED_GROUPS,
    DQRValidationIssue,
    DQRValidationReport,
    validate_assignment,
    validate_assignments_for_dp,
)
from src.models import ColumnProfile, DQRAssignment

# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------

def _profile(name: str, group: str, dtype: str = "object") -> ColumnProfile:
    return ColumnProfile(
        name=name, dtype=dtype, column_type_group=group,
        total_rows=10, null_count=0, null_pct=0.0,
        distinct_count=10, duplicate_count=0, sample_values=[],
    )


def _profiles(*entries) -> dict:
    return {p.name: p for p in entries}


# ---------------------------------------------------------------------------
# Scenario 1: valid configuration for a numeric CDE
# ---------------------------------------------------------------------------

def test_valid_accuracy_on_numeric_cde():
    profile = _profile("AMOUNT", "float", dtype="float64")
    assignment = DQRAssignment(
        cde_column="AMOUNT", dimension="Accuracy",
        params={"min_value": 0, "max_value": 1000},
    )
    report = validate_assignment(assignment, profile, _profiles(profile))
    assert report.is_valid
    assert report.issues == ()


def test_valid_completeness_on_any_type():
    """Completeness is the universal baseline - every column type passes."""
    for group in ("string", "id", "integer", "float", "boolean", "datetime"):
        profile = _profile("X", group)
        report = validate_assignment(
            DQRAssignment("X", "Completeness"), profile, _profiles(profile),
        )
        assert report.is_valid, f"Completeness should accept {group}"


# ---------------------------------------------------------------------------
# Scenario 2: invalid datetime CDE compared against a numeric column
# ---------------------------------------------------------------------------

def test_invalid_consistency_datetime_vs_numeric():
    """The exact regression from the feature brief: a datetime CDE
    configured to compare against a numeric column would crash deep in
    pandas with ``TypeError: '>=' not supported between instances of
    'datetime.date' and 'float'``. Validation must catch this in 4.1."""
    cde = _profile("DATE_COL", "datetime", dtype="datetime64[ns]")
    cmp = _profile("AMOUNT", "float", dtype="float64")
    assignment = DQRAssignment(
        cde_column="DATE_COL",
        dimension="Consistency",
        params={"compare_column": "AMOUNT", "operator": ">="},
    )
    report = validate_assignment(assignment, cde, _profiles(cde, cmp))
    assert not report.is_valid
    msg = report.errors[0].message
    assert "date/datetime" in msg
    assert "numeric" in msg
    # The user-facing suggestion guides them to a fix.
    assert any(
        "compatible" in (i.suggestion or "").lower() for i in report.errors
    )


# ---------------------------------------------------------------------------
# Scenario 3: valid datetime-vs-datetime consistency
# ---------------------------------------------------------------------------

def test_valid_consistency_datetime_vs_datetime():
    start = _profile("START_DATE", "datetime")
    end = _profile("END_DATE", "datetime")
    assignment = DQRAssignment(
        cde_column="START_DATE",
        dimension="Consistency",
        params={"compare_column": "END_DATE", "operator": "<="},
    )
    report = validate_assignment(assignment, start, _profiles(start, end))
    assert report.is_valid


# ---------------------------------------------------------------------------
# Scenario 4: invalid operator usage for incompatible data types
# ---------------------------------------------------------------------------

def test_invalid_unknown_consistency_operator():
    p = _profile("A", "float")
    other = _profile("B", "float")
    assignment = DQRAssignment(
        "A", "Consistency",
        params={"compare_column": "B", "operator": "~="},
    )
    report = validate_assignment(assignment, p, _profiles(p, other))
    assert not report.is_valid
    assert any("Unknown operator" in e.message for e in report.errors)


def test_warning_ordering_operator_on_boolean():
    """Boolean comparisons via ``<`` are technically possible in pandas but
    almost never the user's intent - surface a warning."""
    p = _profile("FLAG_A", "boolean")
    other = _profile("FLAG_B", "boolean")
    assignment = DQRAssignment(
        "FLAG_A", "Consistency",
        params={"compare_column": "FLAG_B", "operator": "<"},
    )
    report = validate_assignment(assignment, p, _profiles(p, other))
    assert report.is_valid  # non-blocking
    assert report.has_warnings


# ---------------------------------------------------------------------------
# Scenario 5: multiple Standard DQRs, only one is invalid
# ---------------------------------------------------------------------------

def test_multiple_assignments_only_one_invalid():
    date_cde = _profile("EVENT_DATE", "datetime")
    amount_cde = _profile("AMOUNT", "float")
    assignments = [
        DQRAssignment("AMOUNT", "Accuracy", params={"min_value": 0, "max_value": 100}),
        DQRAssignment("EVENT_DATE", "Currency", params={"max_age_days": 365}),
        DQRAssignment(
            "EVENT_DATE", "Consistency",
            params={"compare_column": "AMOUNT", "operator": ">="},
        ),
    ]
    profiles = _profiles(date_cde, amount_cde)
    reports = validate_assignments_for_dp(assignments, profiles)
    invalid = {rid: r for rid, r in reports.items() if not r.is_valid}
    assert len(invalid) == 1
    assert "EVENT_DATE::Consistency" in invalid


# ---------------------------------------------------------------------------
# Other dimension/type edge cases
# ---------------------------------------------------------------------------

def test_accuracy_on_string_cde_is_an_error():
    profile = _profile("CATEGORY", "string")
    assignment = DQRAssignment("CATEGORY", "Accuracy")
    report = validate_assignment(assignment, profile, _profiles(profile))
    assert not report.is_valid
    assert "not applicable" in report.errors[0].message


def test_timeliness_on_string_cde_is_an_error():
    profile = _profile("NAME", "string")
    report = validate_assignment(
        DQRAssignment("NAME", "Timeliness", params={"max_lag_days": 30}),
        profile, _profiles(profile),
    )
    assert not report.is_valid


def test_currency_on_datetime_cde_is_valid():
    profile = _profile("EVENT_DATE", "datetime")
    report = validate_assignment(
        DQRAssignment("EVENT_DATE", "Currency", params={"max_age_days": 365}),
        profile, _profiles(profile),
    )
    assert report.is_valid


def test_precision_on_string_cde_is_an_error():
    profile = _profile("CATEGORY", "string")
    report = validate_assignment(
        DQRAssignment("CATEGORY", "Precision", params={"max_decimals": 2}),
        profile, _profiles(profile),
    )
    assert not report.is_valid


def test_accuracy_min_greater_than_max_is_an_error():
    profile = _profile("AMOUNT", "float")
    report = validate_assignment(
        DQRAssignment(
            "AMOUNT", "Accuracy",
            params={"min_value": 100, "max_value": 0},
        ),
        profile, _profiles(profile),
    )
    assert not report.is_valid
    assert any("greater than max" in e.message for e in report.errors)


def test_validity_text_params_on_numeric_cde_warns():
    profile = _profile("AMOUNT", "float")
    report = validate_assignment(
        DQRAssignment("AMOUNT", "Validity", params={"regex": r"\d+"}),
        profile, _profiles(profile),
    )
    assert report.is_valid  # non-blocking
    assert report.has_warnings


def test_validity_min_len_greater_than_max_len_errors():
    profile = _profile("CODE", "string")
    report = validate_assignment(
        DQRAssignment(
            "CODE", "Validity",
            params={"min_length": 10, "max_length": 3},
        ),
        profile, _profiles(profile),
    )
    assert not report.is_valid


def test_consistency_missing_compare_column_in_dp_is_an_error():
    profile = _profile("A", "float")
    report = validate_assignment(
        DQRAssignment(
            "A", "Consistency",
            params={"compare_column": "DOES_NOT_EXIST", "operator": "<="},
        ),
        profile, _profiles(profile),
    )
    assert not report.is_valid


def test_consistency_unconfigured_compare_column_is_an_error():
    """An enabled Consistency dimension with no compare_column is silently
    a no-op in the engine - surface it as an error so the user is forced
    to configure it instead of producing a vacuously-passing rule."""
    profile = _profile("A", "float")
    report = validate_assignment(
        DQRAssignment("A", "Consistency", params={}),
        profile, _profiles(profile),
    )
    assert not report.is_valid


def test_consistency_compare_to_self_is_an_error():
    profile = _profile("A", "float")
    report = validate_assignment(
        DQRAssignment(
            "A", "Consistency",
            params={"compare_column": "A", "operator": "<="},
        ),
        profile, _profiles(profile),
    )
    assert not report.is_valid


def test_conformity_non_numeric_allowed_values_on_numeric_cde_warns():
    profile = _profile("AMOUNT", "float")
    report = validate_assignment(
        DQRAssignment(
            "AMOUNT", "Conformity",
            params={"allowed_values": ["100", "abc", "200"]},
        ),
        profile, _profiles(profile),
    )
    assert report.is_valid
    assert report.has_warnings
    assert any("not numeric" in w.message for w in report.warnings)


def test_integrity_non_numeric_references_on_numeric_cde_warns():
    profile = _profile("ITEM_ID", "integer")
    report = validate_assignment(
        DQRAssignment(
            "ITEM_ID", "Integrity",
            params={"reference_values": ["1", "two", "3"]},
        ),
        profile, _profiles(profile),
    )
    assert report.is_valid
    assert report.has_warnings


def test_timeliness_non_positive_lag_is_an_error():
    profile = _profile("D", "datetime")
    report = validate_assignment(
        DQRAssignment("D", "Timeliness", params={"max_lag_days": 0}),
        profile, _profiles(profile),
    )
    assert not report.is_valid


def test_currency_non_integer_age_is_an_error():
    profile = _profile("D", "datetime")
    report = validate_assignment(
        DQRAssignment("D", "Currency", params={"max_age_days": "not-a-number"}),
        profile, _profiles(profile),
    )
    assert not report.is_valid


def test_validate_assignment_without_profile_errors():
    report = validate_assignment(
        DQRAssignment("MISSING", "Completeness"), profile=None,
    )
    assert not report.is_valid
    assert "no column profile" in report.errors[0].message


# ---------------------------------------------------------------------------
# Scenario 7: dynamic validation as the user changes the configuration
# ---------------------------------------------------------------------------

def test_dynamic_validation_flips_when_compare_column_changes():
    """When the user swaps the comparison column from numeric to date,
    validation transitions from invalid → valid on the next call."""
    date_cde = _profile("EVENT_DATE", "datetime")
    end_date = _profile("END_DATE", "datetime")
    amount = _profile("AMOUNT", "float")
    profiles = _profiles(date_cde, end_date, amount)

    # First config - numeric compare column → invalid.
    bad = DQRAssignment(
        "EVENT_DATE", "Consistency",
        params={"compare_column": "AMOUNT", "operator": "<="},
    )
    assert not validate_assignment(bad, date_cde, profiles).is_valid

    # User changes compare_column to a datetime column → valid.
    good = DQRAssignment(
        "EVENT_DATE", "Consistency",
        params={"compare_column": "END_DATE", "operator": "<="},
    )
    assert validate_assignment(good, date_cde, profiles).is_valid


def test_dynamic_validation_flips_when_dimension_changes():
    """Switching the dimension from Accuracy (numeric-only) to Completeness
    (any type) flips validation from invalid → valid for a string CDE."""
    profile = _profile("CATEGORY", "string")
    profiles = _profiles(profile)

    bad = DQRAssignment("CATEGORY", "Accuracy")
    assert not validate_assignment(bad, profile, profiles).is_valid

    good = DQRAssignment("CATEGORY", "Completeness")
    assert validate_assignment(good, profile, profiles).is_valid


# ---------------------------------------------------------------------------
# Catalog completeness: every dimension is in the supported-groups map
# ---------------------------------------------------------------------------

def test_every_dimension_has_a_compatibility_entry():
    """All 10 standard dimensions must declare which CDE groups they
    accept. Adding a new dimension without an entry is a configuration
    bug we want to fail loudly during testing."""
    from config.dqr_catalog import list_dimensions
    for dim in list_dimensions():
        assert dim in DIMENSION_SUPPORTED_GROUPS


# ---------------------------------------------------------------------------
# Report convenience properties
# ---------------------------------------------------------------------------

def test_report_classifies_errors_and_warnings():
    issues = (
        DQRValidationIssue("error", "boom"),
        DQRValidationIssue("warning", "tip"),
    )
    report = DQRValidationReport(issues=issues)
    assert not report.is_valid
    assert report.has_warnings
    assert report.errors == (issues[0],)
    assert report.warnings == (issues[1],)
    assert "boom" in report.reason_string()


def test_empty_report_is_valid():
    assert DQRValidationReport().is_valid
    assert not DQRValidationReport().has_warnings
    assert DQRValidationReport().reason_string() == ""
