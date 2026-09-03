"""
Domain registry.

A *domain* is a top-level scope the user picks in Step 0 before any other
step of the app runs. Each domain bundles the systems / tables, the
custom DQR catalog, and the visual metadata (icon, accent, copy) used
throughout the rest of the workflow.

The domain layer is intentionally additive: every step downstream of
Step 0 still talks to ``SYSTEMS``-like and ``CUSTOM_DQR_RULES``-like
structures, only now those structures come from the active domain
instead of being a global module-level dict. The original Cost Estimate
domain wraps the historical globals one-for-one so the existing flow is
preserved byte-for-byte.

Adding a new domain:
1. Define its systems (or reuse a partial subset) and custom-rule catalog.
2. Add a ``DomainDef`` entry to ``DOMAINS`` with the new code, label,
   description, systems dict, custom rules dict, and (optionally)
   custom system icons / accents.
3. Tests in ``tests/test_domain_registry.py`` will pick it up
   automatically and verify the registry stays self-consistent.

No other code change should be required. The Streamlit UI reads
everything through ``get_active_domain()``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from config.custom_dqr_catalog import CustomRuleDef
    from config.systems import SystemDef


DOMAIN_COST_ESTIMATE: str = "cost_estimate"
DOMAIN_QUALITY: str = "quality"


@dataclass(frozen=True)
class ProjectFilterDef:
    """Per-domain sidebar project-filter configuration.

    Each domain decides which column its sidebar "Project filter" widget
    targets (Cost Estimate filters on ``PLANVIEW_ID``; Quality filters on
    ``PROJECT_CODE``). Holding the column + UI copy on the domain keeps
    the sidebar renderer generic and lets new domains pick their own
    filter column without touching shared code.
    """
    column: str
    label: str
    placeholder: str
    help: str
    pill_singular: str = "project"
    pill_plural: str = "projects"


DEFAULT_PROJECT_FILTER: ProjectFilterDef = ProjectFilterDef(
    column="PLANVIEW_ID",
    label="PLANVIEW_ID(s)",
    placeholder="PV-00001\nPV-00002",
    help=(
        "Restrict the entire app to one or more projects. "
        "Separate multiple IDs with commas, spaces or new lines. "
        "Leave empty to use all projects."
    ),
)


@dataclass(frozen=True)
class DomainDef:
    """A self-contained scope of the app.

    Attributes:
        code: stable identifier persisted in session state.
        name: short human label shown in Step 0 cards and the sidebar.
        subtitle: short descriptor placed under the name on the Step 0 card.
        description: 2-4 sentence card body.
        icon: emoji rendered on the Step 0 card and the sidebar.
        accent: hex color for the card accent strip / chip.
        tagline: one-liner used in the sidebar brand tagline.
        page_title: ``st.set_page_config`` title for the domain (browser tab).
        sidebar_brand_subtitle: short uppercase label rendered next to the
            sidebar brand title (typically a list of system codes).
        systems: ``SystemDef`` registry for the domain. Keyed by system code.
        custom_rules: per-system list of ``CustomRuleDef`` (the structure
            previously held by ``config.custom_dqr_catalog.CUSTOM_DQR_RULES``).
        system_icons / system_accents: optional override for per-system
            visual identity. Steps that render system chips look these up;
            missing codes fall back to a neutral default.
        reference_dataset_loaders: optional registry of reference dataset
            loaders specific to this domain. Keys are logical reference
            names, values are zero-arg callables returning a DataFrame or
            ``None``. Loaders are merged with the global registry in
            ``src.reference_data`` when the domain becomes active.
        placeholder: True when the domain ships with TODO content rather
            than fully wired tables and rules. The Step 0 card surfaces
            this to set expectations.
    """
    code: str
    name: str
    subtitle: str
    description: str
    icon: str
    accent: str
    tagline: str
    page_title: str
    sidebar_brand_subtitle: str
    systems: Dict[str, "SystemDef"]
    custom_rules: Dict[str, List["CustomRuleDef"]]
    system_icons: Dict[str, str] = field(default_factory=dict)
    system_accents: Dict[str, str] = field(default_factory=dict)
    reference_dataset_loaders: Dict[str, Any] = field(default_factory=dict)
    placeholder: bool = False
    project_filter: ProjectFilterDef = DEFAULT_PROJECT_FILTER

    @property
    def system_codes(self) -> List[str]:
        return list(self.systems.keys())


def _build_cost_estimate_domain() -> DomainDef:
    """Wrap the historical ``SYSTEMS`` / ``CUSTOM_DQR_RULES`` globals into a
    DomainDef. Cost Estimate stays the *exact* same data shape as before;
    this is just where it gets registered."""
    # Local imports so importing config.domains doesn't drag pandas/streamlit
    # into pure-config consumers that don't need it.
    from config.custom_dqr_catalog import CUSTOM_DQR_RULES as _COST_CUSTOM_RULES
    from config.systems import SYSTEMS as _COST_SYSTEMS

    return DomainDef(
        code=DOMAIN_COST_ESTIMATE,
        name="Cost Estimate",
        subtitle="ADR · ACCE · EPT",
        description=(
            "The original domain. Joins ADR, ACCE and EPT cost-estimate "
            "tables into one Data Product per system and applies the "
            "standard 10-dimension catalog plus 23 curated custom rules "
            "to score each project's cost estimate quality."
        ),
        icon="💰",
        accent="#4f46e5",
        tagline="Build CDE-driven Data Quality scorecards across cost-estimate systems.",
        page_title="DQ Scorecard - Cost Estimate (ADR / ACCE / EPT)",
        sidebar_brand_subtitle="ADR · ACCE · EPT",
        systems=_COST_SYSTEMS,
        custom_rules=_COST_CUSTOM_RULES,
        system_icons={"ADR": "📊", "ACCE": "📈", "EPT": "🗂️"},
        system_accents={"ADR": "#3b82f6", "ACCE": "#8b5cf6", "EPT": "#0ea5e9"},
        reference_dataset_loaders={},  # registered globally in src.reference_data
        placeholder=False,
        project_filter=DEFAULT_PROJECT_FILTER,
    )


def _build_quality_domain() -> DomainDef:
    """Quality domain.

    Single-system domain (``SQS``, Quality Management System) backed by
    the curated inspection table ``CT_SQS_AT_INSPECTION``, read from the
    same Unity Catalog namespace as every other table (see
    ``SETTINGS.dbx_catalog`` / ``SETTINGS.dbx_schema``).

    Curated DQR rules are defined with the Quality team and live in
    ``config.custom_dqr._sqs_catalog`` (``dq-inspection-12`` - Completeness
    on ``TOTAL_CONSUMED_HOURS`` for completed inspections,
    ``dq-inspection-13`` - Completeness on ``ALLOTED_HOURS``). The mock
    generator in ``src.mock_data`` mirrors the inspection-table shape so
    the rest of the pipeline can be exercised end-to-end in demo mode.
    """
    from config.custom_dqr._sqs_catalog import SQS_RULES
    from config.systems import SystemDef, TableDef

    sqs_system = SystemDef(
        code="SQS",
        name="Quality Management System",
        description=(
            "Curated inspection records for the Quality domain. Single "
            "table ``CT_SQS_AT_INSPECTION`` keyed by ``PLANVIEW_ID`` "
            "(project grain)."
        ),
        tables=[
            TableDef(
                name="CT_SQS_AT_INSPECTION",
                description=(
                    "Curated SQS inspection table. One row per "
                    "inspection event, linked to a project via "
                    "``PLANVIEW_ID``."
                ),
                join_key="PLANVIEW_ID",
                is_primary=True,
            ),
        ],
    )

    return DomainDef(
        code=DOMAIN_QUALITY,
        name="Quality",
        subtitle="SQS",
        description=(
            "Same seven-step DQ workflow as Cost Estimate, applied to "
            "the curated SQS inspection table ``CT_SQS_AT_INSPECTION`` "
            "with curated DQR rules defined with the Quality team."
        ),
        icon="✅",
        accent="#10b981",
        tagline="Build CDE-driven Data Quality scorecards across quality systems.",
        page_title="DQ Scorecard - Quality (SQS)",
        sidebar_brand_subtitle="SQS",
        systems={"SQS": sqs_system},
        custom_rules={"SQS": list(SQS_RULES)},
        system_icons={"SQS": "🛡️"},
        system_accents={"SQS": "#10b981"},
        reference_dataset_loaders={},
        placeholder=False,
        project_filter=ProjectFilterDef(
            column="PROJECT_CODE",
            label="PROJECT_CODE(s)",
            placeholder="QPC-001\nQPC-002",
            help=(
                "Restrict the entire app to one or more projects. "
                "Separate multiple PROJECT_CODE values with commas, "
                "spaces or new lines. Leave empty to use all projects."
            ),
        ),
    )


# Domain registry - ordered. Cost Estimate stays first so the default UI
# pick matches the historical behaviour for returning users.
DOMAINS: Dict[str, DomainDef] = {
    DOMAIN_COST_ESTIMATE: _build_cost_estimate_domain(),
    DOMAIN_QUALITY: _build_quality_domain(),
}


_DEFAULT_DOMAIN_CODE: str = DOMAIN_COST_ESTIMATE


def list_domain_codes() -> List[str]:
    return list(DOMAINS.keys())


def get_domain(code: str) -> DomainDef:
    if code not in DOMAINS:
        raise KeyError(f"Unknown domain: {code}. Available: {list(DOMAINS.keys())}")
    return DOMAINS[code]


def get_default_domain_code() -> str:
    return _DEFAULT_DOMAIN_CODE


def register_domain(domain: DomainDef) -> None:
    """Register a new domain at runtime.

    Useful for tests that exercise the "new domain can be added without
    touching the main flow" guarantee. Raises ``ValueError`` on duplicate
    codes so callers spot accidental shadowing.
    """
    if domain.code in DOMAINS:
        raise ValueError(f"Domain '{domain.code}' is already registered.")
    DOMAINS[domain.code] = domain


def unregister_domain(code: str) -> None:
    """Drop a domain from the registry. Intended for test cleanup."""
    DOMAINS.pop(code, None)


def get_active_domain_code() -> str:
    """Return the active domain code from Streamlit session state.

    Falls back to the default when called outside a Streamlit run or
    before Step 0 has set the value, so library-level consumers never
    crash on a missing session.
    """
    try:
        import streamlit as st
        return st.session_state.get("domain", _DEFAULT_DOMAIN_CODE) or _DEFAULT_DOMAIN_CODE
    except Exception:
        return _DEFAULT_DOMAIN_CODE


def get_active_domain() -> DomainDef:
    """Return the currently active ``DomainDef``."""
    return get_domain(get_active_domain_code())


def get_active_project_filter() -> ProjectFilterDef:
    """Return the sidebar ``ProjectFilterDef`` for the active domain.

    Lives next to :func:`get_active_domain` so the sidebar renderer
    and the data-product builder share one resolution path. Falls back
    to :data:`DEFAULT_PROJECT_FILTER` (``PLANVIEW_ID``) when the active
    domain doesn't override it.
    """
    return get_active_domain().project_filter


def get_active_data_location() -> tuple[str, str]:
    """Return ``(catalog, schema)`` where the application tables live.

    Every domain reads from the single Unity Catalog namespace configured
    in ``SETTINGS`` (default ``entai_sandbox_catalog.data_quality_scorecards``)
    - the migration consolidated the formerly per-domain Snowflake
    databases into one schema. Imported lazily by the Step 1 banner.
    """
    from config.settings import SETTINGS

    return SETTINGS.dbx_catalog, SETTINGS.dbx_schema
