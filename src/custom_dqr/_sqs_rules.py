# pyright: reportArgumentType=false, reportCallIssue=false
# pyright: reportAttributeAccessIssue=false, reportOperatorIssue=false
"""SQS custom DQR rule checks (Quality domain).

Each ``check_sqs_sq<N>`` is a callable ``(df) -> pd.Series[bool]`` where
True means the row passes. The Quality domain backs a single curated
inspection table ``CT_SQS_AT_INSPECTION``; rules implemented here are
data-product-specific checks layered on top of the 10 Standard DQR
dimensions.

See the pragma rationale in ``src/custom_dqr/_adr_rules.py``: the
pandas-stubs typing of ``df[col]`` as ``Series | DataFrame`` produces
false positives the runtime contract (locked down by
``tests/test_custom_dqr_engine.py``) already covers.
"""
from __future__ import annotations

import pandas as pd

from src.custom_dqr._validators import validate_completeness_rule

# =============================================================================
# SQ4 - Valid Date (EXPECTED_SHIP_DATE)
# =============================================================================
# Dimension: Validity. Row passes when ``EXPECTED_SHIP_DATE`` is non-null and
# parses as a valid calendar date. The SQL spec wraps the check in
# ``TRY_TO_DATE(TO_VARCHAR(EXPECTED_SHIP_DATE, 'YYYY-MM-DD'), 'YYYY-MM-DD')``
# - a defensive round-trip whose pandas equivalent is
# ``pd.to_datetime(..., errors="coerce")``. The column is stored as
# ``TIMESTAMP_NTZ`` so Snowflake enforces well-formed datetimes at ingestion;
# the primary failure mode in production is NULL values, but the round-trip
# is preserved so values arriving via VARIANT / string paths still get
# validated.

SQS_SQ4_REQUIRED_COLUMNS = {
    "Expected Ship Date": "EXPECTED_SHIP_DATE",
}


def check_sqs_sq4(df: pd.DataFrame) -> pd.Series:
    """SQ4: Valid Date.

    Row passes when ``EXPECTED_SHIP_DATE`` is non-null **and** parses as a
    valid calendar date. Implementation mirrors the Snowflake spec
    (``TRY_TO_DATE(TO_VARCHAR(EXPECTED_SHIP_DATE, 'YYYY-MM-DD'),
    'YYYY-MM-DD')``) via :func:`pandas.to_datetime` with
    ``errors="coerce"``: unparseable values land as ``NaT`` and fail
    alongside genuine NULLs. Schema-level missing column makes every row
    fail (same convention as the other custom rules).
    """
    if "EXPECTED_SHIP_DATE" not in df.columns:
        return pd.Series(False, index=df.index)
    parsed = pd.to_datetime(df["EXPECTED_SHIP_DATE"], errors="coerce")
    return parsed.notna()


# =============================================================================
# SQ5 - Not after PO Required Ship Date
# =============================================================================
# Dimension: Business Rule. Row passes when ``EXPECTED_SHIP_DATE`` is on or
# before ``PO_REQUIRED_SHIP_DATE``. NULL on either side is treated as PASS
# (the rule cannot be evaluated without both values - completeness gaps are
# covered separately by SQ4). The comparison uses strict ``>`` so an
# expected ship date equal to the PO required ship date is compliant.

SQS_SQ5_REQUIRED_COLUMNS = {
    "Expected Ship Date": "EXPECTED_SHIP_DATE",
    "PO Required Ship Date": "PO_REQUIRED_SHIP_DATE",
}


def check_sqs_sq5(df: pd.DataFrame) -> pd.Series:
    """SQ5: Expected Ship Date must not be after PO Required Ship Date.

    Row passes when:

    - ``EXPECTED_SHIP_DATE`` is NULL or unparseable, **or**
    - ``PO_REQUIRED_SHIP_DATE`` is NULL or unparseable, **or**
    - ``EXPECTED_SHIP_DATE <= PO_REQUIRED_SHIP_DATE``.

    Row fails only when both dates resolve to a valid datetime and the
    expected ship date is strictly **after** the PO required ship date.
    NULL handling mirrors the Snowflake spec (``WHEN ... IS NULL THEN
    'PASS'``) so this rule never double-penalises completeness gaps SQ4
    already covers. Schema-level missing column makes every row fail
    (same convention as the other custom rules).
    """
    required = list(SQS_SQ5_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    expected = pd.to_datetime(df["EXPECTED_SHIP_DATE"], errors="coerce")
    po_required = pd.to_datetime(df["PO_REQUIRED_SHIP_DATE"], errors="coerce")
    fail = expected.notna() & po_required.notna() & (expected > po_required)
    return ~fail


# =============================================================================
# SQ6 - Inspection Type value in allowed set
# =============================================================================
# Dimension: Validity. Row passes when ``INSPECTION_TYPE`` matches one of
# the controlled-vocabulary values verbatim (case-sensitive). NULL and any
# off-list value FAIL. The allowed set is the SQL spec's literal IN list
# and is exported as a module-level tuple so the catalog / tests / UI
# consumers can read it without re-typing the strings.

SQS_SQ6_REQUIRED_COLUMNS = {
    "Inspection Type": "INSPECTION_TYPE",
}

SQS_SQ6_ALLOWED_VALUES: tuple[str, ...] = (
    "Source Inspection",
    "Supplier Assessment",
    "Expediting",
    "Supplemental Inspection",
)


def check_sqs_sq6(df: pd.DataFrame) -> pd.Series:
    """SQ6: ``INSPECTION_TYPE`` must be one of :data:`SQS_SQ6_ALLOWED_VALUES`.

    Row passes when ``INSPECTION_TYPE`` is non-null and matches one of the
    allowed values verbatim. The match is **case-sensitive** per spec
    (Snowflake's ``IN`` operator), so ``"source inspection"`` is FAIL
    even though it represents the same logical category. NULL values
    FAIL (Snowflake's ``IN`` does not match NULLs). Schema-level missing
    column makes every row fail (same convention as the other custom
    rules).
    """
    if "INSPECTION_TYPE" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["INSPECTION_TYPE"].isin(SQS_SQ6_ALLOWED_VALUES)


# =============================================================================
# SQ7 - Work Criticality value in allowed set
# =============================================================================
# Dimension: Validity. Row passes when ``WORK_CRITICALITY`` matches one of
# the four roman-numeral classification levels verbatim. Mirrors SQ6's
# shape (Snowflake ``IN`` semantics, case-sensitive, NULL → FAIL) against
# a different controlled vocabulary; kept as a parallel check function so
# each rule keeps its own ``check_sqs_sq<N>`` entry point (matches the
# EPT / ADR / ACCE per-rule convention).

SQS_SQ7_REQUIRED_COLUMNS = {
    "Work Criticality": "WORK_CRITICALITY",
}

SQS_SQ7_ALLOWED_VALUES: tuple[str, ...] = (
    "I - High Critical",
    "II - Medium Critical",
    "III - Low Critical",
    "IV - Non Critical",
)


def check_sqs_sq7(df: pd.DataFrame) -> pd.Series:
    """SQ7: ``WORK_CRITICALITY`` must be one of :data:`SQS_SQ7_ALLOWED_VALUES`.

    Row passes when ``WORK_CRITICALITY`` is non-null and matches one of the
    four roman-numeral classification levels verbatim. The match is
    **case-sensitive** per spec (Snowflake's ``IN`` operator), so
    ``"i - high critical"`` and ``"I - HIGH CRITICAL"`` both FAIL. NULL
    values FAIL (Snowflake's ``IN`` does not match NULLs). Empty strings
    likewise FAIL. Schema-level missing column makes every row fail (same
    convention as the other custom rules).
    """
    if "WORK_CRITICALITY" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["WORK_CRITICALITY"].isin(SQS_SQ7_ALLOWED_VALUES)


# =============================================================================
# SQ8 - Status required
# =============================================================================
# Dimension: Completeness. Row passes when ``STATUS`` is non-null and not
# blank / whitespace-only. Mirrors the Snowflake spec
# (``WHEN STATUS IS NULL OR TRIM(STATUS) = '' THEN 'FAIL'``) by delegating
# to the reusable :func:`validate_completeness_rule`, which already applies
# ``_is_filled`` (non-null AND non-blank after trimming string-typed
# values) per the catalog convention.

SQS_SQ8_REQUIRED_COLUMNS = {
    "Status": "STATUS",
}


def check_sqs_sq8(df: pd.DataFrame) -> pd.Series:
    """SQ8: ``STATUS`` must not be NULL or empty / whitespace-only.

    Row passes when ``STATUS`` is non-null and its string value contains
    at least one non-whitespace character. NULL, empty string ``""``,
    and whitespace-only values (``"   "``, tabs, newlines) all FAIL,
    mirroring the spec's ``STATUS IS NULL OR TRIM(STATUS) = ''``
    predicate. Schema-level missing column makes every row fail (same
    convention as the other custom rules).
    """
    return validate_completeness_rule(df, SQS_SQ8_REQUIRED_COLUMNS.values())


# =============================================================================
# SQ9 - Status value in allowed set
# =============================================================================
# Dimension: Validity. Row passes when ``STATUS`` matches one of the 11
# canonical workflow statuses verbatim. Layers on top of SQ8 (which
# guarantees the column is populated and non-blank); SQ9 then enforces
# the controlled vocabulary. Same shape as SQ6 / SQ7 (case-sensitive
# Snowflake ``IN`` semantics, NULL → FAIL); kept as a parallel
# ``check_sqs_sq9`` so each rule keeps its own entry point per the EPT /
# ADR / ACCE convention.

SQS_SQ9_REQUIRED_COLUMNS = {
    "Status": "STATUS",
}

SQS_SQ9_ALLOWED_VALUES: tuple[str, ...] = (
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
)


def check_sqs_sq9(df: pd.DataFrame) -> pd.Series:
    """SQ9: ``STATUS`` must be one of :data:`SQS_SQ9_ALLOWED_VALUES`.

    Row passes when ``STATUS`` is non-null and matches one of the 11
    canonical workflow statuses verbatim. The match is **case-sensitive**
    per spec (Snowflake's ``IN`` operator), so ``"approved"`` and
    ``"APPROVED"`` both FAIL; leading / trailing whitespace likewise
    FAIL (``" Approved "`` is not in the allowed list). NULL values FAIL
    (Snowflake's ``IN`` does not match NULLs). Schema-level missing
    column makes every row fail (same convention as the other custom
    rules).
    """
    if "STATUS" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["STATUS"].isin(SQS_SQ9_ALLOWED_VALUES)


# =============================================================================
# SQ10 - Status / Expected Ship Date sequencing
# =============================================================================
# Dimension: Business Rule. Cross-column constraint: when
# ``STATUS == 'Completed'``, the inspection has wrapped up and the
# ``EXPECTED_SHIP_DATE`` must not be in the future. Every other row
# passes (the rule only applies to completed assignments). Mirrors the
# Snowflake spec's predicate
# ``STATUS = 'Completed' AND EXPECTED_SHIP_DATE > CURRENT_TIMESTAMP()``.

SQS_SQ10_REQUIRED_COLUMNS = {
    "Status": "STATUS",
    "Expected Ship Date": "EXPECTED_SHIP_DATE",
}

# The "completed" trigger value is exported as a module-level constant so
# tests / UI consumers can read it without re-typing the string. Spec is
# case-sensitive on the canonical SQ9 vocabulary value ``"Completed"``.
SQS_SQ10_COMPLETED_STATUS: str = "Completed"


def check_sqs_sq10(df: pd.DataFrame) -> pd.Series:
    """SQ10: Completed inspections must not carry a future
    ``EXPECTED_SHIP_DATE``.

    Row passes when **any** of the following holds:

    - ``STATUS`` is not exactly ``"Completed"`` (the rule only applies
      to completed assignments; every other status is out of scope).
    - ``EXPECTED_SHIP_DATE`` is NULL or unparseable (the rule cannot be
      evaluated without a date; SQ4 covers the completeness gap).
    - ``EXPECTED_SHIP_DATE`` is on or before the current timestamp
      (`pd.Timestamp.now()`).

    Row fails only when ``STATUS == "Completed"`` **and**
    ``EXPECTED_SHIP_DATE`` parses to a future timestamp relative to the
    moment the check runs. The reference time is captured once per call
    so a single batch evaluation is consistent across rows (it can still
    differ between runs, which mirrors the Snowflake spec's use of
    ``CURRENT_TIMESTAMP()``). Schema-level missing columns make every
    row fail (same convention as the other custom rules).
    """
    required = list(SQS_SQ10_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    status = df["STATUS"]
    expected = pd.to_datetime(df["EXPECTED_SHIP_DATE"], errors="coerce")
    now = pd.Timestamp.now()
    fail = (status == SQS_SQ10_COMPLETED_STATUS) & expected.notna() & (
        expected > now
    )
    return ~fail
