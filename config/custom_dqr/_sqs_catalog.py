"""SQS custom rule list (Quality domain).

The SQS rules in :data:`SQS_RULES` are exported as a list of
:class:`CustomRuleDef` (one per ``SQ<N>`` entry). The check callables and
required-column constants live in :mod:`src.custom_dqr_engine` and are
re-exported there from :mod:`src.custom_dqr._sqs_rules`.
"""
from __future__ import annotations

from config.custom_dqr._shared import CustomRuleDef
from src.custom_dqr_engine import (
    SQS_SQ4_REQUIRED_COLUMNS,
    SQS_SQ5_REQUIRED_COLUMNS,
    SQS_SQ6_ALLOWED_VALUES,
    SQS_SQ6_REQUIRED_COLUMNS,
    SQS_SQ7_ALLOWED_VALUES,
    SQS_SQ7_REQUIRED_COLUMNS,
    SQS_SQ8_REQUIRED_COLUMNS,
    SQS_SQ9_ALLOWED_VALUES,
    SQS_SQ9_REQUIRED_COLUMNS,
    SQS_SQ10_COMPLETED_STATUS,
    SQS_SQ10_REQUIRED_COLUMNS,
    check_sqs_sq4,
    check_sqs_sq5,
    check_sqs_sq6,
    check_sqs_sq7,
    check_sqs_sq8,
    check_sqs_sq9,
    check_sqs_sq10,
)

SQS_RULES = [
    CustomRuleDef(
        id="SQ4",
        name="Valid date (EXPECTED_SHIP_DATE)",
        type="Validity",
        description=(
            "Every inspection record's ``EXPECTED_SHIP_DATE`` must be a "
            "valid calendar date (``YYYY-MM-DD`` format) and not NULL. "
            "Invalid or missing dates break shipment sequencing, "
            "logistics planning, and downstream reporting."
        ),
        notes=(
            "The column is stored as ``TIMESTAMP_NTZ``, so Snowflake "
            "enforces well-formed datetime values at ingestion; in "
            "practice the dominant failure mode is NULL. The check "
            "mirrors the SQL spec's defensive round-trip "
            "(``TRY_TO_DATE(TO_VARCHAR(..., 'YYYY-MM-DD'), 'YYYY-MM-DD')``) "
            "via :func:`pandas.to_datetime` with ``errors=\"coerce\"`` so "
            "any value that fails the round-trip (e.g. an out-of-range "
            "date arriving via VARIANT / string path) is also caught. "
            "Rows fail when ``EXPECTED_SHIP_DATE`` is NULL or does not "
            "parse as a valid calendar date."
        ),
        required_columns=dict(SQS_SQ4_REQUIRED_COLUMNS),
        blocking=False,
        check=check_sqs_sq4,
    ),
    CustomRuleDef(
        id="SQ5",
        name="Not after PO Required Ship Date",
        type="Business Rule",
        description=(
            "``EXPECTED_SHIP_DATE`` must not be after "
            "``PO_REQUIRED_SHIP_DATE``: the supplier's projected ship "
            "date has to land on or before the contractual deadline "
            "established in the purchase order. When it slips past "
            "the PO required date, the project faces a likely delivery "
            "delay with downstream logistics and contractual fallout."
        ),
        notes=(
            "Row passes when either date is NULL (the rule cannot be "
            "evaluated without both values; SQ4 already covers the "
            "completeness gap on ``EXPECTED_SHIP_DATE``) or when "
            "``EXPECTED_SHIP_DATE <= PO_REQUIRED_SHIP_DATE``. The "
            "comparison uses strict ``>`` so an expected ship date "
            "equal to the PO required ship date is compliant. Both "
            "columns are ``TIMESTAMP_NTZ`` in Snowflake; the pandas "
            "check uses :func:`pandas.to_datetime` with "
            "``errors=\"coerce\"`` so any value that fails to parse "
            "is treated as NULL (PASS) rather than crashing the "
            "scorecard."
        ),
        required_columns=dict(SQS_SQ5_REQUIRED_COLUMNS),
        blocking=False,
        check=check_sqs_sq5,
    ),
    CustomRuleDef(
        id="SQ6",
        name="Inspection Type value in allowed set",
        type="Validity",
        description=(
            "``INSPECTION_TYPE`` must match one of the controlled "
            "vocabulary values: " + ", ".join(
                f"``{v}``" for v in SQS_SQ6_ALLOWED_VALUES
            ) + ". Off-list values introduce ambiguity, break "
            "category-based aggregations, and can misroute inspection "
            "assignments downstream."
        ),
        notes=(
            "Row passes only when ``INSPECTION_TYPE`` matches one of "
            "the allowed values **verbatim** (case-sensitive, per the "
            "Snowflake ``IN`` operator). Typos, case variants "
            "(``\"source inspection\"``), unexpected categories "
            "(``\"Audit\"``), and NULL values all FAIL. The allowed "
            "list should be reviewed periodically with business "
            "stakeholders so legitimate new categories are added "
            "instead of polluting the FAIL bucket."
        ),
        required_columns=dict(SQS_SQ6_REQUIRED_COLUMNS),
        blocking=False,
        check=check_sqs_sq6,
    ),
    CustomRuleDef(
        id="SQ7",
        name="Work Criticality value in allowed set",
        type="Validity",
        description=(
            "``WORK_CRITICALITY`` must match one of the four "
            "classification levels: " + ", ".join(
                f"``{v}``" for v in SQS_SQ7_ALLOWED_VALUES
            ) + ". The classification drives prioritization of "
            "resources, risk assessment, and downstream reporting; "
            "non-standard values misclassify work priority and skew "
            "every analytic built on top."
        ),
        notes=(
            "Row passes only when ``WORK_CRITICALITY`` matches one of "
            "the allowed values **verbatim** (case-sensitive, per the "
            "Snowflake ``IN`` operator). NULL, empty strings, case "
            "variants (``\"i - high critical\"``), and unexpected "
            "labels (``\"V - Unknown\"``) all FAIL. New classification "
            "levels must be added to "
            "``SQS_SQ7_ALLOWED_VALUES`` in "
            "``src/custom_dqr/_sqs_rules.py`` with a business "
            "justification rather than worked around at the row level."
        ),
        required_columns=dict(SQS_SQ7_REQUIRED_COLUMNS),
        blocking=False,
        check=check_sqs_sq7,
    ),
    CustomRuleDef(
        id="SQ8",
        name="Status required",
        type="Completeness",
        description=(
            "Every inspection record must carry a populated "
            "``STATUS`` value (e.g. ``Pending``, ``In Progress``, "
            "``Completed``). Missing or empty statuses create blind "
            "spots in workflow monitoring, block status-based filters "
            "/ routing, and skew progress reporting."
        ),
        notes=(
            "Row passes when ``STATUS`` is non-null and contains at "
            "least one non-whitespace character (matches the spec "
            "predicate ``STATUS IS NULL OR TRIM(STATUS) = ''``). "
            "NULL, empty string ``\"\"``, and whitespace-only values "
            "all FAIL. Implementation delegates to "
            "``validate_completeness_rule`` so the rule shares its "
            "trimming / null-handling semantics with the EPT / ADR / "
            "ACCE Completeness rules."
        ),
        required_columns=dict(SQS_SQ8_REQUIRED_COLUMNS),
        blocking=False,
        check=check_sqs_sq8,
    ),
    CustomRuleDef(
        id="SQ9",
        name="Status value in allowed set",
        type="Validity",
        description=(
            "``STATUS`` must match one of the 11 canonical workflow "
            "statuses: " + ", ".join(
                f"``{v}``" for v in SQS_SQ9_ALLOWED_VALUES
            ) + ". The status drives workflow logic, automated "
            "transitions, and reporting dashboards; off-list values "
            "fall outside monitoring scope and break automation."
        ),
        notes=(
            "Row passes only when ``STATUS`` matches one of the "
            "allowed values **verbatim** (case-sensitive, per the "
            "Snowflake ``IN`` operator). NULL, unexpected categories "
            "(``\"Cancelled\"``), case variants (``\"approved\"``), "
            "and leading / trailing whitespace (``\" Approved \"``) "
            "all FAIL. Layers on top of SQ8 (Completeness): SQ8 "
            "surfaces NULL / blank gaps, SQ9 surfaces typos and "
            "off-list values. Adding a new legitimate status "
            "requires updating ``SQS_SQ9_ALLOWED_VALUES`` in "
            "``src/custom_dqr/_sqs_rules.py`` with a business "
            "justification rather than a per-row workaround."
        ),
        required_columns=dict(SQS_SQ9_REQUIRED_COLUMNS),
        blocking=False,
        check=check_sqs_sq9,
    ),
    CustomRuleDef(
        id="SQ10",
        name="Status / Expected Ship Date sequencing",
        type="Business Rule",
        description=(
            "When ``STATUS == \"" + SQS_SQ10_COMPLETED_STATUS + "\"`` "
            "the inspection has wrapped up, so ``EXPECTED_SHIP_DATE`` "
            "must not point at a future timestamp. A future ship date "
            "on a completed record is a logical contradiction that "
            "signals premature status closure or a date-entry error "
            "and undermines audit reporting."
        ),
        notes=(
            "Row passes when ``STATUS`` is anything other than "
            "``\"" + SQS_SQ10_COMPLETED_STATUS + "\"``, when "
            "``EXPECTED_SHIP_DATE`` is NULL / unparseable (SQ4 owns "
            "the date-validity gap), or when the date is on or before "
            "``pd.Timestamp.now()``. Row fails only when the status "
            "is exactly ``\"" + SQS_SQ10_COMPLETED_STATUS + "\"`` "
            "**and** the expected ship date resolves to a future "
            "timestamp relative to the moment the check runs - "
            "mirrors the Snowflake spec's "
            "``CURRENT_TIMESTAMP()`` comparison, so results can shift "
            "between runs as records age past the reference time."
        ),
        required_columns=dict(SQS_SQ10_REQUIRED_COLUMNS),
        blocking=False,
        check=check_sqs_sq10,
    ),
]
