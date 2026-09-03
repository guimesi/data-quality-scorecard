# pyright: reportArgumentType=false, reportCallIssue=false
# pyright: reportAttributeAccessIssue=false, reportOperatorIssue=false
"""SQS custom DQR rule checks (Quality domain).

Each ``check_sqs_dq_inspection_<N>`` is a callable ``(df) -> pd.Series[bool]``
where True means the row passes. The Quality domain backs a single curated
inspection table ``CT_SQS_AT_INSPECTION``; rules implemented here are
data-product-specific checks layered on top of the 10 Standard DQR
dimensions. Rule ids follow the Quality team's ``dq-inspection-<N>``
naming (the SQL spec exposes each verdict as ``DQ_INSPECTION_<N>_STATUS``).

See the pragma rationale in ``src/custom_dqr/_adr_rules.py``: the
pandas-stubs typing of ``df[col]`` as ``Series | DataFrame`` produces
false positives the runtime contract (locked down by
``tests/test_custom_dqr_engine.py``) already covers.
"""
from __future__ import annotations

import pandas as pd

from src.custom_dqr._shared import _is_filled
from src.custom_dqr._validators import validate_completeness_rule

# =============================================================================
# dq-inspection-12 - Mandatory on Completion (TOTAL_CONSUMED_HOURS)
# =============================================================================
# Dimension: Completeness. Conditional check: when ``STATUS == 'Completed'``
# the inspection has wrapped up, so ``TOTAL_CONSUMED_HOURS`` must be
# recorded. Every other row passes (the rule only applies to completed
# inspections). Mirrors the SQL spec::
#
#     CASE WHEN STATUS = 'Completed' AND TOTAL_CONSUMED_HOURS IS NOT NULL
#              THEN 'PASS'
#          WHEN STATUS = 'Completed' AND TOTAL_CONSUMED_HOURS IS NULL
#              THEN 'FAIL'
#          ELSE 'PASS'
#     END AS DQ_INSPECTION_12_STATUS

SQS_DQ_INSPECTION_12_REQUIRED_COLUMNS = {
    "Status": "STATUS",
    "Total Consumed Hours": "TOTAL_CONSUMED_HOURS",
}

# The "completed" trigger value is exported as a module-level constant so
# tests / UI consumers can read it without re-typing the string. The spec
# compares with SQL ``=``, i.e. case-sensitive and exact - ``"Completed
# (Short Closed)"`` is *not* in scope.
SQS_DQ_INSPECTION_12_COMPLETED_STATUS: str = "Completed"


def check_sqs_dq_inspection_12(df: pd.DataFrame) -> pd.Series:
    """dq-inspection-12: Completed inspections must record
    ``TOTAL_CONSUMED_HOURS``.

    Row passes when **either** of the following holds:

    - ``STATUS`` is not exactly ``"Completed"`` (the rule only applies to
      completed inspections; every other status is out of scope).
    - ``TOTAL_CONSUMED_HOURS`` is populated (non-null; for string-typed
      columns also non-blank, via :func:`_is_filled`).

    Row fails only when ``STATUS == "Completed"`` **and**
    ``TOTAL_CONSUMED_HOURS`` is missing. Schema-level missing columns make
    every row fail (same convention as the other custom rules).
    """
    required = list(SQS_DQ_INSPECTION_12_REQUIRED_COLUMNS.values())
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    completed = df["STATUS"] == SQS_DQ_INSPECTION_12_COMPLETED_STATUS
    fail = completed & ~_is_filled(df["TOTAL_CONSUMED_HOURS"])
    return ~fail


# =============================================================================
# dq-inspection-13 - Mandatory Approved Hours (ALLOTED_HOURS)
# =============================================================================
# Dimension: Completeness. Row passes when ``ALLOTED_HOURS`` is populated.
# Mirrors the SQL spec::
#
#     CASE WHEN ALLOTED_HOURS IS NOT NULL THEN 'PASS'
#          WHEN ALLOTED_HOURS IS NULL THEN 'FAIL'
#          ELSE 'PASS'
#     END AS DQ_INSPECTION_13_STATUS
#
# Delegates to the reusable :func:`validate_completeness_rule` so the rule
# shares its null / blank handling with the other Completeness rules.

SQS_DQ_INSPECTION_13_REQUIRED_COLUMNS = {
    "Alloted Hours": "ALLOTED_HOURS",
}


def check_sqs_dq_inspection_13(df: pd.DataFrame) -> pd.Series:
    """dq-inspection-13: ``ALLOTED_HOURS`` must be populated.

    Row passes when ``ALLOTED_HOURS`` is non-null (and, for string-typed
    columns, not blank / whitespace-only). NULL values FAIL, mirroring the
    spec's ``ALLOTED_HOURS IS NULL`` predicate. Schema-level missing column
    makes every row fail (same convention as the other custom rules).
    """
    return validate_completeness_rule(
        df, SQS_DQ_INSPECTION_13_REQUIRED_COLUMNS.values()
    )
