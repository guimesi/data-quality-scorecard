"""
Data classes (models) used across the application.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class ColumnProfile:
    name: str
    dtype: str
    column_type_group: str   # one of COLUMN_TYPE_* from config.dqr_catalog
    total_rows: int
    null_count: int
    null_pct: float
    distinct_count: int
    duplicate_count: int
    sample_values: List[Any] = field(default_factory=list)
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None


@dataclass
class DataProduct:
    system_code: str
    name: str
    df: pd.DataFrame
    source_tables: List[str]
    profiles: Dict[str, ColumnProfile] = field(default_factory=dict)

    @property
    def row_count(self) -> int:
        return len(self.df)

    @property
    def column_count(self) -> int:
        return len(self.df.columns)


@dataclass
class DQRAssignment:
    """A single Data Quality Rule assigned to a single CDE column."""
    cde_column: str
    dimension: str                       # one of the 10 dimensions
    params: Dict[str, Any] = field(default_factory=dict)
    weight: float = 0.0                  # 0 to 100

    @property
    def rule_id(self) -> str:
        return f"{self.cde_column}::{self.dimension}"


@dataclass
class CustomDQRAssignment:
    """A data-product-specific custom DQR selected by the user.

    Descriptive metadata (name, description, required columns, ...) lives in
    ``config.custom_dqr_catalog``; this object only carries the user's
    selection (rule_id), weight inside the Custom source, and any per-rule
    runtime options (``params``) flipped in Step 4.2 - for example E3's
    ``project_scoped`` toggle that switches the percentile from a global
    baseline to a per-PLANVIEW_ID one.
    """
    rule_id: str
    weight: float = 0.0                  # 0 to 100, summed within Custom source
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataProductConfig:
    """All DQ configuration for one data product."""
    system_code: str
    cdes: List[str] = field(default_factory=list)
    assignments: List[DQRAssignment] = field(default_factory=list)

    # Source-level configuration (Step 4 selection screen)
    dqr_sources: List[str] = field(default_factory=list)        # ["standard", "custom"]
    source_weights: Dict[str, float] = field(default_factory=dict)
    custom_assignments: List[CustomDQRAssignment] = field(default_factory=list)

    def get_assignments_for(self, cde_column: str) -> List[DQRAssignment]:
        return [a for a in self.assignments if a.cde_column == cde_column]

    def weights_sum(self) -> float:
        return sum(a.weight for a in self.assignments)

    def effective_dqr_sources(self) -> List[str]:
        """Return ``dqr_sources`` or fall back to ``["standard"]``.

        Backward-compat shim so configs created before the source-selection
        feature still flow through Steps 5/6 and ``compute_scorecard``.
        """
        return list(self.dqr_sources) if self.dqr_sources else ["standard"]

    def effective_source_weights(self) -> Dict[str, float]:
        """Return ``source_weights`` or default to 100% on the only source."""
        if self.source_weights:
            return dict(self.source_weights)
        sources = self.effective_dqr_sources()
        return {sources[0]: 100.0} if len(sources) == 1 else {s: 100.0 / len(sources) for s in sources}


@dataclass
class ScorecardResult:
    system_code: str
    overall_score: float                 # 0-100, mean of combined row scores
    row_scores: pd.Series                # per-row 0-100 (combined across sources)
    rule_pass_rates: Dict[str, float]    # rule_id -> pct rows passing (Standard only)
    cde_scores: Dict[str, float]         # cde_column -> mean score (Standard only)
    dimension_scores: Dict[str, float]   # dimension -> mean score (Standard only)
    total_rows: int
    rows_green: int
    rows_yellow: int
    rows_red: int
    threshold_green: float
    threshold_yellow: float
    # Source-level breakdown
    standard_score: Optional[float] = None       # 0-100 or None when Standard not selected
    custom_score: Optional[float] = None         # 0-100 or None when Custom not selected
    source_weights: Dict[str, float] = field(default_factory=dict)
    custom_rule_pass_rates: Dict[str, float] = field(default_factory=dict)  # rule_id -> %
    # Custom rules whose dependencies (e.g. a reference dataset) were missing
    # at evaluation time. Maps rule_id -> human-readable reason. Surfaced in
    # Step 6 so the user sees the failure explicitly instead of a silent pass.
    not_evaluated_custom_rules: Dict[str, str] = field(default_factory=dict)
    # Standard DQRs that could not be computed, either because Step 4.1
    # validation flagged the configuration as incompatible with the CDE's
    # data type, or because an unexpected runtime error escaped the rule
    # body. Maps rule_id -> reason. The rule contributes 0 to the score
    # instead of crashing the dashboard.
    not_computed_standard_rules: Dict[str, str] = field(default_factory=dict)
