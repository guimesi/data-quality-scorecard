# pyright: reportArgumentType=false
"""One-click automation service.

Given a domain and a list of systems, this module reproduces the manual
Step-by-step workflow with a fixed, default configuration so the user gets a full
set of scorecards from just two choices (domain + systems):

- **Custom DQR source only** - no Standard rules (the One-click contract
  is "score with the curated custom rules").
- **Every Custom DQR** available for each system, each with its *default*
  options / parameters (nothing toggled).
- **CDEs limited** to the source columns those rules require.
- **Rule weights distributed equally** within the Custom source.
- **Scorecards computed** with the same engine the dashboard uses, so a
  One-click run and an equivalent hand-built Step-by-step run produce identical
  scorecards.

This module performs **no Streamlit I/O**. The One-click UI step
(:mod:`ui.step_one_click`) wires the result into ``session_state`` and the
dashboard, and turns the CSV/JSON exports on. Keeping the logic here means
it can be unit-tested without a Streamlit run.

Active-domain contract
----------------------
``compute_scorecard`` and ``evaluate_custom_rules`` resolve the rule
catalog through the *active* domain (``get_active_domain``), so the caller
must have set ``st.session_state.domain == domain_code`` before invoking
:func:`run_one_click`. The One-click UI guarantees this by calling
``set_domain`` when the user picks a domain; tests set
``st.session_state["domain"]`` directly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from config.custom_dqr_catalog import (
    effective_required_columns,
    get_available_custom_dqr_rules,
)
from config.domains import get_domain
from config.dqr_sources import SOURCE_CUSTOM
from config.systems import SHARED_KEY
from src.data_product_builder import build_multiple
from src.models import (
    CustomDQRAssignment,
    DataProduct,
    DataProductConfig,
    ScorecardResult,
)
from src.profiler import profile_dataframe
from src.reference_data import (
    prefetch_reference_datasets,
    required_reference_datasets_for_systems,
)
from src.scorecard import compute_scorecard

logger = logging.getLogger(__name__)

# Session-state key the One-click UI uses to hand a one-time summary
# (systems scored / skipped / warnings / CSV-export errors) to the
# dashboard, which renders it as a banner. Defined here - a UI-free module
# both UI sides import - so neither UI step depends on the other.
ONE_CLICK_SUMMARY_KEY = "one_click_summary"


class OneClickError(Exception):
    """Raised for blocking validation failures that the One-click UI should
    surface to the user (no domain, no system, build failure). Per-system
    issues that don't block the whole run are recorded as ``skipped`` /
    ``warnings`` on :class:`OneClickResult` instead."""


@dataclass
class OneClickProduct:
    """A single system that One-click built, configured and scored."""
    system_code: str
    data_product: DataProduct
    config: DataProductConfig
    scorecard: ScorecardResult


@dataclass
class OneClickResult:
    """Outcome of a One-click run.

    ``products`` holds only the systems that were configured *and* scored.
    ``skipped`` maps each system that was dropped to a human-readable
    reason (no custom rules, empty after filter, scorecard failure).
    ``warnings`` are non-blocking notes surfaced to the user (e.g. a rule
    whose required column is missing).
    """
    domain_code: str
    requested_systems: List[str]
    products: Dict[str, OneClickProduct] = field(default_factory=dict)
    skipped: Dict[str, str] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    @property
    def scored_systems(self) -> List[str]:
        return list(self.products.keys())

    @property
    def data_products(self) -> Dict[str, DataProduct]:
        return {c: p.data_product for c, p in self.products.items()}

    @property
    def configs(self) -> Dict[str, DataProductConfig]:
        return {c: p.config for c, p in self.products.items()}

    @property
    def scorecards(self) -> Dict[str, ScorecardResult]:
        return {c: p.scorecard for c, p in self.products.items()}


def default_rule_params(rule) -> Dict[str, object]:
    """Return the params dict a rule would have with *nothing* toggled.

    Mirrors exactly what Step 4.2's ``_render_rule_options`` produces when
    the user leaves every option / selectbox at its default, so a One-click
    config is byte-identical to an Step-by-step config the user never touched.
    """
    params: Dict[str, object] = {}
    for sel in rule.select_options:
        params[sel.key] = sel.default
    for opt in rule.options:
        params[opt.key] = bool(opt.default)
    return params


def build_one_click_config(
    system_code: str,
    dp: DataProduct,
    rules,
) -> Tuple[DataProductConfig, List[str]]:
    """Build the One-click :class:`DataProductConfig` for one system.

    Selects the Custom source at 100%, applies every ``rule`` with its
    default params, derives the CDE list from the union of the rules'
    required source columns (preserving data-product column order), and
    distributes rule weights equally within the Custom source.

    Returns ``(config, warnings)``. ``warnings`` flags rules whose required
    columns are absent from the data product (they'll be marked "Not
    evaluated" downstream) and the degenerate "no required CDEs" case.
    """
    # Local import: keeps src/ free of a module-level utils/ (streamlit)
    # dependency while still reusing the canonical equal-split helper.
    from utils.helpers import distribute_equally

    warnings: List[str] = []
    df_columns = list(dp.df.columns)
    df_column_set = set(df_columns)

    weights = distribute_equally(len(rules))
    custom_assignments: List[CustomDQRAssignment] = []
    required_union: set = set()
    for rule, weight in zip(rules, weights):
        params = default_rule_params(rule)
        required_cols = list(effective_required_columns(rule, params).values())
        required_union.update(required_cols)
        missing = [c for c in required_cols if c not in df_column_set]
        if missing:
            warnings.append(
                f"{system_code} · {rule.id} requires column(s) "
                f"{', '.join(missing)} not present in the data product - "
                "the rule will be marked Not evaluated."
            )
        custom_assignments.append(
            CustomDQRAssignment(rule_id=rule.id, weight=weight, params=params)
        )

    # CDEs = the required columns that actually exist, in DP column order so
    # the selection lines up with every downstream display (mirrors Step 3).
    cdes = [c for c in df_columns if c in required_union]
    if not cdes:
        warnings.append(
            f"{system_code}: the selected Custom DQRs declare no source "
            "columns present in the data product, so no CDEs were "
            "auto-selected."
        )

    cfg = DataProductConfig(
        system_code=system_code,
        cdes=cdes,
        assignments=[],                       # One-click never uses Standard
        dqr_sources=[SOURCE_CUSTOM],
        source_weights={SOURCE_CUSTOM: 100.0},
        custom_assignments=custom_assignments,
    )
    return cfg, warnings


def run_one_click(
    domain_code: str,
    systems: Iterable[str],
    *,
    row_limit: Optional[int] = None,
    planview_filter: Optional[Iterable[str]] = None,
    filter_column: str = SHARED_KEY,
    progress: Callable[[str, str], None] | None = None,
) -> OneClickResult:
    """Run the full One-click pipeline for ``systems`` in ``domain_code``.

    Builds each system's data product, prefetches any reference datasets
    its custom rules need, applies the default custom-only configuration,
    and computes the scorecard. Systems with no custom rules, no rows after
    the project filter, or a scorecard failure are recorded in
    ``result.skipped`` rather than aborting the whole run.

    Raises :class:`OneClickError` for blocking input problems (no domain,
    no system, or a data-product build failure) so the UI can surface them
    and keep the user on the One-click step.
    """
    if not domain_code:
        raise OneClickError("No domain selected. Pick a domain to continue.")
    try:
        get_domain(domain_code)  # validates the code
    except KeyError as e:
        raise OneClickError(f"Unknown domain: {domain_code}.") from e

    system_list = [s for s in (systems or [])]
    if not system_list:
        raise OneClickError("No system selected. Pick at least one system.")

    result = OneClickResult(domain_code=domain_code, requested_systems=system_list)

    def _progress(phase: str, detail: str = "") -> None:
        if progress is not None:
            progress(phase, detail)

    # 1. Build + profile the data products for every selected system.
    _progress("Loading tables", ", ".join(system_list))
    try:
        dps = build_multiple(
            system_list,
            row_limit=row_limit,
            planview_ids=list(planview_filter) if planview_filter else None,
            filter_column=filter_column,
        )
    except Exception as e:  # broad: surface build/Databricks errors to the UI
        logger.warning("One-click data-product build failed", exc_info=True)
        raise OneClickError(f"Failed to build data products: {e}") from e
    _progress("Building Data Products", f"{len(dps)} systems")
    _progress("Profiling columns", f"{sum(len(dp.df.columns) for dp in dps.values())} columns")
    for dp in dps.values():
        dp.profiles = profile_dataframe(dp.df)

    # 2. Eager-load reference datasets so referential-integrity rules score
    #    instead of being marked Not evaluated (parity with Step 2).
    ref_names = required_reference_datasets_for_systems(system_list)
    if ref_names:
        prefetch_reference_datasets(ref_names)

    # 3. Configure + score each system.
    n_rules = sum(len(get_available_custom_dqr_rules(c)) for c in system_list)
    _progress("Applying Custom DQRs", f"{n_rules} rules")
    for code in system_list:
        dp = dps[code]
        rules = get_available_custom_dqr_rules(code)
        if not rules:
            result.skipped[code] = (
                "no Custom DQR rules are configured for this system"
            )
            continue
        if dp.row_count == 0:
            result.skipped[code] = "the project filter matched 0 rows"
            continue

        cfg, warnings = build_one_click_config(code, dp, rules)
        result.warnings.extend(warnings)
        _progress("Computing scores", code)
        try:
            scorecard = compute_scorecard(dp, cfg)
        except Exception as e:  # defensive: a rule bug must not abort the run
            logger.warning(
                "One-click scorecard failed for %s", code, exc_info=True
            )
            result.skipped[code] = f"scorecard generation failed: {e}"
            continue
        result.products[code] = OneClickProduct(
            system_code=code,
            data_product=dp,
            config=cfg,
            scorecard=scorecard,
        )

    return result
