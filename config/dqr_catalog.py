"""
Catalog of the 10 Data Quality dimensions supported by the application.

Each dimension has:
- name: canonical name used throughout the app
- description: short description for the UI
- applies_to: column types for which the dimension is typically suggested
- default_params: default parameters (editable by the user in the UI)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

# Column type groups used for automatic suggestion
COLUMN_TYPE_NUMERIC = "numeric"
COLUMN_TYPE_INTEGER = "integer"
COLUMN_TYPE_FLOAT = "float"
COLUMN_TYPE_DATETIME = "datetime"
COLUMN_TYPE_DATE = "date"
COLUMN_TYPE_BOOLEAN = "boolean"
COLUMN_TYPE_STRING = "string"
COLUMN_TYPE_CATEGORICAL = "categorical"
COLUMN_TYPE_ID = "id"  # string/int identifiers (heuristic: col ends in _ID)


@dataclass(frozen=True)
class DimensionDef:
    name: str
    description: str
    applies_to: List[str]          # column-type groups typically suggested for
    default_params: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# The 10 DQ dimensions
# =============================================================================

DIMENSIONS: Dict[str, DimensionDef] = {
    "Completeness": DimensionDef(
        name="Completeness",
        description="The column is populated (non-null / non-empty).",
        applies_to=[
            COLUMN_TYPE_NUMERIC, COLUMN_TYPE_INTEGER, COLUMN_TYPE_FLOAT,
            COLUMN_TYPE_DATETIME, COLUMN_TYPE_DATE, COLUMN_TYPE_BOOLEAN,
            COLUMN_TYPE_STRING, COLUMN_TYPE_CATEGORICAL, COLUMN_TYPE_ID,
        ],
        default_params={"allow_empty_string": False},
    ),
    "Uniqueness": DimensionDef(
        name="Uniqueness",
        description="The column value is unique within the data product.",
        applies_to=[COLUMN_TYPE_ID, COLUMN_TYPE_STRING, COLUMN_TYPE_INTEGER],
        default_params={},
    ),
    "Validity": DimensionDef(
        name="Validity",
        description="Value conforms to a format/pattern (regex, type, acceptable range).",
        applies_to=[
            COLUMN_TYPE_STRING, COLUMN_TYPE_ID, COLUMN_TYPE_DATETIME,
            COLUMN_TYPE_DATE, COLUMN_TYPE_NUMERIC,
        ],
        default_params={"regex": None, "min_length": None, "max_length": None},
    ),
    "Accuracy": DimensionDef(
        name="Accuracy",
        description="Value is within an expected range (plausibility check).",
        applies_to=[COLUMN_TYPE_NUMERIC, COLUMN_TYPE_INTEGER, COLUMN_TYPE_FLOAT],
        default_params={"min_value": None, "max_value": None},
    ),
    "Consistency": DimensionDef(
        name="Consistency",
        description="Value is consistent with another column (cross-field check).",
        applies_to=[
            COLUMN_TYPE_NUMERIC, COLUMN_TYPE_STRING, COLUMN_TYPE_CATEGORICAL,
            COLUMN_TYPE_DATE, COLUMN_TYPE_DATETIME,
        ],
        default_params={"compare_column": None, "operator": "<="},
    ),
    "Timeliness": DimensionDef(
        name="Timeliness",
        description="Data was recorded/updated within the expected SLA.",
        applies_to=[COLUMN_TYPE_DATETIME, COLUMN_TYPE_DATE],
        default_params={"max_lag_days": 30},
    ),
    "Currency": DimensionDef(
        name="Currency",
        description="Data is current (date within a recent window).",
        applies_to=[COLUMN_TYPE_DATETIME, COLUMN_TYPE_DATE],
        default_params={"max_age_days": 365},
    ),
    "Conformity": DimensionDef(
        name="Conformity",
        description="Value belongs to an allowed domain/catalog.",
        applies_to=[COLUMN_TYPE_STRING, COLUMN_TYPE_CATEGORICAL],
        default_params={"allowed_values": []},
    ),
    "Integrity": DimensionDef(
        name="Integrity",
        description="Referential integrity: FK exists in the reference set.",
        applies_to=[COLUMN_TYPE_ID, COLUMN_TYPE_STRING, COLUMN_TYPE_INTEGER],
        default_params={"reference_values": []},
    ),
    "Precision": DimensionDef(
        name="Precision",
        description="Number of decimal places / expected granularity.",
        applies_to=[COLUMN_TYPE_FLOAT, COLUMN_TYPE_NUMERIC],
        default_params={"max_decimals": 2},
    ),
}


def list_dimensions() -> List[str]:
    return list(DIMENSIONS.keys())


def get_dimension(name: str) -> DimensionDef:
    if name not in DIMENSIONS:
        raise KeyError(f"Unknown dimension: {name}")
    return DIMENSIONS[name]


def suggest_dimensions_for(column_type: str, col_name: str) -> List[str]:
    """Return list of dimension names that apply to a given column type + name."""
    suggested = []
    normalized_name = (col_name or "").lower()
    is_id_like = (
        column_type == COLUMN_TYPE_ID
        or normalized_name.endswith("_id")
        or normalized_name == "id"
        or "planview" in normalized_name
    )

    for dim_name, dim in DIMENSIONS.items():
        if column_type in dim.applies_to:
            suggested.append(dim_name)
        elif is_id_like and COLUMN_TYPE_ID in dim.applies_to:
            suggested.append(dim_name)

    # Always suggest Completeness (core sanity check)
    if "Completeness" not in suggested:
        suggested.insert(0, "Completeness")

    # ID-like columns should get Uniqueness (safety net; the main loop
    # already adds it via applies_to, but this guards against future config
    # changes to the Uniqueness dimension).
    if is_id_like and "Uniqueness" not in suggested:  # pragma: no cover
        suggested.append("Uniqueness")

    return suggested
