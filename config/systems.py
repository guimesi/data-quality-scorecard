"""
Definition of source systems (ADR, ACCE, EPT), their tables,
internal join keys, and the shared identifier that links them.

Schema reference:
 - ADR - primary: ADR_DIM_ESTIMATEITEMRECORD (PK = ROW_ID)
            children join on ROW_ID: ADR_FACT_ESTIMATECOSTRESULTS,
                                      ADR_FACT_ESTIMATEQTYRESULTS,
                                      ADR_DIM_ESTIMATEDESIGNDETAILS
 - ACCE  - primary: ACCE_ESTIMATEITEMRECORD (PK = ROW_ID)
            children join on ROW_ID: ACCE_ESTIMATECOSTRESULTS,
                                      ACCE_ESTIMATEQTYRESULTS
            children join on DESIGN_ID: ACCE_ESTIMATEDESIGNDETAILS
 - EPT - single table: ONSHORE_CETDATA

Across the three systems, the linking column is PLANVIEW_ID (at the
project grain), present in the primary tables and ONSHORE_CETDATA.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

if TYPE_CHECKING:
    import pandas as pd

# Column name that links records ACROSS ADR, ACCE, and EPT (project grain).
# Not used for internal joins within a system, those use ROW_ID (or whatever
# each TableDef.join_key specifies).
SHARED_KEY: str = "PLANVIEW_ID"


@dataclass(frozen=True)
class TableDef:
    """One source table inside a system."""
    name: str
    description: str
    # Column used to join this table with the primary/parent table within the
    # same system. For the primary table itself this is effectively the PK.
    join_key: str
    # True for the single "fact/primary" table of the system. Other tables are
    # LEFT-joined to it in a star pattern.
    is_primary: bool = False
    # Optional short prefix for this table's columns (to avoid collisions after
    # joining). If None, a default is derived from the table name.
    column_prefix: Optional[str] = None
    # Optional row-level derivation applied after prefixing but *before* any
    # group-by aggregation. Used when the SQL source spec includes per-row
    # transforms that the generic builder cannot infer, e.g. ACCE's
    # ``QTY_QUANTITY = COALESCE(KEY_QTY, OTHER_QTY)`` and
    # ``QTY_UOM = COALESCE(KEY_UNITS, OTHER_UNITS)``, which must happen
    # row-by-row (otherwise ``SUM(KEY_QTY) + SUM(OTHER_QTY)`` would
    # double-count rows where both sides are populated).
    derive_columns: Optional[Callable[["pd.DataFrame"], "pd.DataFrame"]] = None


@dataclass(frozen=True)
class SystemDef:
    """A source system made of one or more tables."""
    code: str
    name: str
    description: str
    tables: List[TableDef]

    @property
    def primary_table(self) -> TableDef:
        for t in self.tables:
            if t.is_primary:
                return t
        raise ValueError(f"System {self.code} has no primary table defined.")

    @property
    def table_names(self) -> List[str]:
        return [t.name for t in self.tables]


def _acce_qty_derive(df: "pd.DataFrame") -> "pd.DataFrame":
    """Apply ACCE's per-row COALESCE before the builder aggregates 1:N qty
    rows by ``ROW_ID``.

    The real ``ACCE_ESTIMATEQTYRESULTS`` table carries two parallel pairs
    of columns - ``KEY_QTY`` / ``OTHER_QTY`` and ``KEY_UNITS`` /
    ``OTHER_UNITS``. The SQL spec resolves each row's effective quantity
    and UOM with ``COALESCE(KEY_*, OTHER_*)`` *before* summing across
    rows for the same ``ROW_ID``. Without this hook the builder would
    sum ``KEY_QTY`` and ``OTHER_QTY`` independently and the consumer
    (AC4 / AC5 / AC7 / AC8) would have no single ``QTY_QUANTITY`` to
    read.

    Columns produced (after the builder's ``QTY_`` prefix):
      - ``QTY_QUANTITY = COALESCE(QTY_KEY_QTY, QTY_OTHER_QTY)``
      - ``QTY_UOM      = COALESCE(QTY_KEY_UNITS, QTY_OTHER_UNITS)``
    """
    if "QTY_KEY_QTY" in df.columns and "QTY_OTHER_QTY" in df.columns:
        df["QTY_QUANTITY"] = df["QTY_KEY_QTY"].fillna(df["QTY_OTHER_QTY"])
    if "QTY_KEY_UNITS" in df.columns and "QTY_OTHER_UNITS" in df.columns:
        df["QTY_UOM"] = df["QTY_KEY_UNITS"].fillna(df["QTY_OTHER_UNITS"])
    return df


# =============================================================================
# System definitions
# =============================================================================

SYSTEMS: Dict[str, SystemDef] = {
    "ADR": SystemDef(
        code="ADR",
        name="ADR Cost Estimate",
        description=(
            "Primary cost estimate system. Fact table ADR_DIM_ESTIMATEITEMRECORD "
            "(grain = estimate item, PK = ROW_ID) with cost and quantity "
            "detail tables joined on ROW_ID. PLANVIEW_ID is the project key."
        ),
        tables=[
            TableDef(
                name="ADR_DIM_ESTIMATEITEMRECORD",
                description=(
                    "Item record / fact master. One row per estimate item. "
                    "Contains ROW_ID (PK) and PLANVIEW_ID (project)."
                ),
                join_key="ROW_ID",
                is_primary=True,
            ),
            TableDef(
                name="ADR_FACT_ESTIMATECOSTRESULTS",
                description=(
                    "Cost results breakdown per estimate item. 1:N on ROW_ID "
                    "(multiple cost lines per item - labor, material, etc.)."
                ),
                join_key="ROW_ID",
                column_prefix="COST",
            ),
            TableDef(
                name="ADR_FACT_ESTIMATEQTYRESULTS",
                description=(
                    "Quantity results breakdown per estimate item. 1:N on "
                    "ROW_ID (multiple qty lines per item - by UOM / commodity)."
                ),
                join_key="ROW_ID",
                column_prefix="QTY",
            ),
            TableDef(
                name="ADR_DIM_ESTIMATEDESIGNDETAILS",
                description=(
                    "Engineering design parameters (design specs) per estimate "
                    "line item. 1:1 on ROW_ID."
                ),
                join_key="ROW_ID",
                column_prefix="DESIGN",
            ),
        ],
    ),
    "ACCE": SystemDef(
        code="ACCE",
        name="ACCE Cost Estimate",
        description=(
            "Parallel cost estimate system used for cross-reconciliation with "
            "ADR. Same grain and join pattern: ESTIMATEITEMRECORD is the fact, "
            "cost/qty results are 1:N child tables on ROW_ID. Design specs "
            "live on a separate dimension joined via DESIGN_ID (multiple "
            "items can share one design)."
        ),
        tables=[
            TableDef(
                name="ACCE_ESTIMATEITEMRECORD",
                description=(
                    "Item record / fact master. One row per estimate item. "
                    "Contains ROW_ID (PK), PLANVIEW_ID (project), and "
                    "DESIGN_ID (FK → ACCE_ESTIMATEDESIGNDETAILS)."
                ),
                join_key="ROW_ID",
                is_primary=True,
            ),
            TableDef(
                name="ACCE_ESTIMATECOSTRESULTS",
                description=(
                    "Cost results breakdown per estimate item. 1:N on ROW_ID."
                ),
                join_key="ROW_ID",
                column_prefix="COST",
            ),
            TableDef(
                name="ACCE_ESTIMATEQTYRESULTS",
                description=(
                    "Quantity results breakdown per estimate item. 1:N on "
                    "ROW_ID. Carries ``KEY_QTY`` / ``OTHER_QTY`` and "
                    "``KEY_UNITS`` / ``OTHER_UNITS`` parallel pairs; the "
                    "builder hook resolves each row's effective quantity "
                    "and UOM via COALESCE before aggregating."
                ),
                join_key="ROW_ID",
                column_prefix="QTY",
                derive_columns=_acce_qty_derive,
            ),
            TableDef(
                name="ACCE_ESTIMATEDESIGNDETAILS",
                description=(
                    "Equipment design attributes (dimensions, properties, "
                    "specifications). Joined to the item record on DESIGN_ID "
                    "(many items can reference the same design)."
                ),
                join_key="DESIGN_ID",
                column_prefix="DESIGN",
            ),
        ],
    ),
    "EPT": SystemDef(
        code="EPT",
        name="EPT - Onshore CET Data",
        description=(
            "Single-table system. ONSHORE_CETDATA holds project-level "
            "reference data, keyed by PLANVIEW_ID."
        ),
        tables=[
            TableDef(
                name="ONSHORE_CETDATA",
                description="Project-level reference table. Keyed by PLANVIEW_ID.",
                join_key="PLANVIEW_ID",
                is_primary=True,
            ),
        ],
    ),
}


def _active_systems() -> Dict[str, SystemDef]:
    """Return the systems registry for the active domain.

    Cost Estimate's systems live in this module's ``SYSTEMS`` global and
    are also referenced by the Cost Estimate :class:`DomainDef`, so the
    two sources stay in sync. Quality (and any future domain) ship their
    own ``systems`` mapping inside their ``DomainDef``.
    """
    # Imported lazily to avoid a circular import at module load: the
    # domain registry imports SYSTEMS from this module to build the
    # Cost Estimate domain.
    from config.domains import get_active_domain

    return get_active_domain().systems


def get_system(code: str) -> SystemDef:
    """Return the ``SystemDef`` for ``code`` in the active domain.

    Cost Estimate keeps the original ``SYSTEMS`` keys (ADR/ACCE/EPT) so
    every caller that previously looked codes up in this registry sees
    identical behaviour. Other domains expose their own codes via the
    domain registry.
    """
    registry = _active_systems()
    if code not in registry:
        raise KeyError(f"Unknown system: {code}. Available: {list(registry.keys())}")
    return registry[code]


def list_system_codes() -> List[str]:
    return list(_active_systems().keys())
