"""SQS custom rule list (Quality domain).

The SQS rules in :data:`SQS_RULES` are exported as a list of
:class:`CustomRuleDef` (one per ``dq-inspection-<N>`` entry). The check
callables and required-column constants live in :mod:`src.custom_dqr_engine`
and are re-exported there from :mod:`src.custom_dqr._sqs_rules`.
"""
from __future__ import annotations

from config.custom_dqr._shared import CustomRuleDef
from src.custom_dqr_engine import (
    SQS_DQ_INSPECTION_12_COMPLETED_STATUS,
    SQS_DQ_INSPECTION_12_REQUIRED_COLUMNS,
    SQS_DQ_INSPECTION_13_REQUIRED_COLUMNS,
    check_sqs_dq_inspection_12,
    check_sqs_dq_inspection_13,
)

SQS_RULES = [
    CustomRuleDef(
        id="dq-inspection-12",
        name="Mandatory on Completion",
        type="Completeness",
        description=(
            "Total Consumed Hours must be recorded for completed "
            "inspections: when ``STATUS`` is ``\""
            + SQS_DQ_INSPECTION_12_COMPLETED_STATUS
            + "\"``, ``TOTAL_CONSUMED_HOURS`` must not be NULL. "
            "Required for utilization, cost and performance reporting."
        ),
        notes=(
            "Row passes when ``STATUS`` is anything other than ``\""
            + SQS_DQ_INSPECTION_12_COMPLETED_STATUS
            + "\"`` (the rule only applies to completed inspections) or "
            "when ``TOTAL_CONSUMED_HOURS`` is populated. Row fails only "
            "when the status is exactly ``\""
            + SQS_DQ_INSPECTION_12_COMPLETED_STATUS
            + "\"`` **and** the hours are missing - mirrors the SQL spec "
            "``STATUS = 'Completed' AND TOTAL_CONSUMED_HOURS IS NULL`` "
            "(case-sensitive; ``\"Completed (Short Closed)\"`` is out of "
            "scope). Technical validation: *Inspection Status = "
            "'Completed' -> Total Consumed Hours IS NOT NULL*."
        ),
        required_columns=dict(SQS_DQ_INSPECTION_12_REQUIRED_COLUMNS),
        blocking=False,
        check=check_sqs_dq_inspection_12,
    ),
    CustomRuleDef(
        id="dq-inspection-13",
        name="Mandatory Approved Hours",
        type="Completeness",
        description=(
            "Alloted Hours must be populated before an inspection "
            "assignment is issued: ``ALLOTED_HOURS`` must not be NULL on "
            "any inspection record. Required for resource planning and "
            "budgeting."
        ),
        notes=(
            "Row passes when ``ALLOTED_HOURS`` is non-null; NULL values "
            "FAIL - mirrors the SQL spec ``ALLOTED_HOURS IS NULL``. "
            "Implementation delegates to ``validate_completeness_rule`` "
            "so the rule shares its null-handling semantics with the "
            "EPT / ADR / ACCE Completeness rules (a string-typed blank "
            "value also fails). Technical validation: *Value IS NOT "
            "NULL*."
        ),
        required_columns=dict(SQS_DQ_INSPECTION_13_REQUIRED_COLUMNS),
        blocking=False,
        check=check_sqs_dq_inspection_13,
    ),
]
