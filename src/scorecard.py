"""
Scorecard computation.

Given a Data Product and a list of DQR assignments with weights, computes:
- per-row score (0-100)
- per-rule pass rate
- per-CDE score
- per-dimension score
- bucket counts (green / yellow / red) based on thresholds

DQRs come from one or two *sources*:

- ``standard``: the catalog of 10 dimensions (existing behavior).
- ``custom``: data-product-specific rules from ``config.custom_dqr_catalog``.

The user picks one or both in Step 4 and assigns a percentage weight to each
in Step 5. The final per-row score is a weighted average across the active
sources; ``overall_score`` is the mean of those row scores, which by linearity
equals ``Σ_source w_source * source_overall``.

Configs created before the source-selection feature land here with
``dqr_sources=[]`` and ``source_weights={}``. The :meth:`DataProductConfig.
effective_dqr_sources` shim defaults them to "standard" with weight 100, so
existing fixtures and tests still produce identical scores.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config.dqr_sources import SOURCE_CUSTOM, SOURCE_STANDARD
from config.settings import SETTINGS
from src.custom_dqr_engine import evaluate_custom_rules
from src.dqr_engine import evaluate_all_safe
from src.models import (
    CustomDQRAssignment,
    DataProduct,
    DataProductConfig,
    DQRAssignment,
    ScorecardResult,
)

# =============================================================================
# Weight helpers
# =============================================================================

def _normalize_weights(assignments: List[DQRAssignment]) -> np.ndarray:
    """Return weights as a numpy array normalized so they sum to 1.0.

    If all weights are zero, falls back to equal weights."""
    w = np.array([a.weight for a in assignments], dtype=float)
    total = w.sum()
    if total <= 0:
        return np.ones_like(w) / max(len(w), 1)
    return w / total


def _normalize_custom_weights(assignments: List[CustomDQRAssignment]) -> np.ndarray:
    w = np.array([a.weight for a in assignments], dtype=float)
    total = w.sum()
    if total <= 0:
        return np.ones_like(w) / max(len(w), 1)
    return w / total


# =============================================================================
# Per-source row scores
# =============================================================================

def _compute_standard_row_scores(
    dp: DataProduct, config: DataProductConfig
) -> Tuple[pd.Series, Dict[str, float], Dict[str, str]]:
    """Return ``(row_scores 0-100, rule_pass_rates, not_computed)``.

    Rules whose configuration is incompatible with the CDE's data type (or
    that raise an unexpected error during evaluation) are surfaced in
    ``not_computed`` and then *dropped* from the score: the row score is a
    weighted average over only the rules that evaluated, with their weights
    renormalized to sum to 1 (see ``_normalize_weights``). A dropped rule does
    NOT pull the score toward 0 - its weight is absorbed by the survivors, so
    the score reflects only what could actually be measured. Step 6 surfaces
    the ``not_computed`` list separately instead of crashing.
    """
    if not config.assignments:
        return (
            pd.Series(0.0, index=dp.df.index, name="standard_row_score"),
            {},
            {},
        )
    rule_results, not_computed = evaluate_all_safe(
        dp.df, config.assignments, dp.profiles,
    )
    if rule_results.shape[1] == 0:
        return (
            pd.Series(0.0, index=dp.df.index, name="standard_row_score"),
            {},
            not_computed,
        )
    evaluated = [a for a in config.assignments if a.rule_id in rule_results.columns]
    weights = _normalize_weights(evaluated)
    row_scores = (rule_results.to_numpy(dtype=float) * weights).sum(axis=1) * 100
    row_scores = pd.Series(row_scores, index=dp.df.index, name="standard_row_score")
    rule_pass_rates = {
        col: float(rule_results[col].mean() * 100.0) for col in rule_results.columns
    }
    return row_scores, rule_pass_rates, not_computed


def _compute_custom_row_scores(
    dp: DataProduct, config: DataProductConfig
) -> Tuple[pd.Series, Dict[str, float], Dict[str, str]]:
    """Return ``(row_scores 0-100, custom_rule_pass_rates, not_evaluated)``.

    When the user selected the Custom source but picked zero rules, score is
    0 (not vacuously 100) so an empty selection doesn't inflate the overall
    score.

    Rules whose ``check`` raised :class:`CustomRuleNotEvaluated` are surfaced
    in ``not_evaluated`` and then *dropped* from the score: weights are
    renormalized over only the rules that evaluated, so a not-evaluated rule's
    weight is absorbed by the survivors rather than scored as 0. They are not
    silently passed either - the dashboard shows the ``not_evaluated`` list."""
    if not config.custom_assignments:
        return (
            pd.Series(0.0, index=dp.df.index, name="custom_row_score"),
            {},
            {},
        )
    rule_results, not_evaluated = evaluate_custom_rules(
        dp.df, config.custom_assignments, dp.system_code
    )
    if rule_results.shape[1] == 0:
        return (
            pd.Series(0.0, index=dp.df.index, name="custom_row_score"),
            {},
            not_evaluated,
        )
    weights = _normalize_custom_weights(
        [a for a in config.custom_assignments if a.rule_id in rule_results.columns]
    )
    row_scores = (rule_results.to_numpy(dtype=float) * weights).sum(axis=1) * 100
    row_scores = pd.Series(row_scores, index=dp.df.index, name="custom_row_score")
    pass_rates = {
        col: float(rule_results[col].mean() * 100.0) for col in rule_results.columns
    }
    return row_scores, pass_rates, not_evaluated


# =============================================================================
# Public API
# =============================================================================

def _check_unique_rule_ids(assignments, kind: str) -> None:
    """Raise a clear error if a rule_id repeats within one source's assignments.

    A duplicate would make the ``evaluated`` assignment list longer than the
    distinct result columns, so ``rule_results.to_numpy() * weights`` would fail
    with a cryptic numpy broadcast error (and the per-rule pass-rate dict would
    silently collide on the repeated key). Fail fast with a readable message
    instead - the dashboard's per-DP guard then surfaces it as a scored-failed
    banner rather than a blank page."""
    seen: set = set()
    dupes: List[str] = []
    for a in assignments or []:
        if a.rule_id in seen:
            dupes.append(a.rule_id)
        seen.add(a.rule_id)
    if dupes:
        raise ValueError(
            f"Duplicate {kind} rule_id(s) in this configuration: "
            f"{', '.join(sorted(set(dupes)))}. Each rule may be assigned once."
        )


def compute_scorecard(
    dp: DataProduct,
    config: DataProductConfig,
    threshold_green: Optional[float] = None,
    threshold_yellow: Optional[float] = None,
) -> ScorecardResult:
    threshold_green = threshold_green if threshold_green is not None else SETTINGS.threshold_green
    threshold_yellow = threshold_yellow if threshold_yellow is not None else SETTINGS.threshold_yellow

    if not config.assignments and not config.custom_assignments:
        return ScorecardResult(
            system_code=dp.system_code,
            overall_score=0.0,
            row_scores=pd.Series([], dtype=float),
            rule_pass_rates={},
            cde_scores={},
            dimension_scores={},
            total_rows=dp.row_count,
            rows_green=0,
            rows_yellow=0,
            rows_red=dp.row_count,
            threshold_green=threshold_green,
            threshold_yellow=threshold_yellow,
            standard_score=None,
            custom_score=None,
            source_weights={},
            custom_rule_pass_rates={},
            not_evaluated_custom_rules={},
            not_computed_standard_rules={},
        )

    _check_unique_rule_ids(config.assignments, "Standard")
    _check_unique_rule_ids(config.custom_assignments, "Custom")

    sources = config.effective_dqr_sources()
    source_weights = config.effective_source_weights()

    standard_row_scores: pd.Series
    custom_row_scores: pd.Series
    standard_score = None
    custom_score = None
    rule_pass_rates: Dict[str, float] = {}
    custom_rule_pass_rates: Dict[str, float] = {}
    not_evaluated_custom_rules: Dict[str, str] = {}
    not_computed_standard_rules: Dict[str, str] = {}

    if SOURCE_STANDARD in sources:
        standard_row_scores, rule_pass_rates, not_computed_standard_rules = (
            _compute_standard_row_scores(dp, config)
        )
        standard_score = float(standard_row_scores.mean()) if len(standard_row_scores) else 0.0
    else:
        standard_row_scores = pd.Series(0.0, index=dp.df.index, name="standard_row_score")

    if SOURCE_CUSTOM in sources:
        custom_row_scores, custom_rule_pass_rates, not_evaluated_custom_rules = (
            _compute_custom_row_scores(dp, config)
        )
        custom_score = float(custom_row_scores.mean()) if len(custom_row_scores) else 0.0
    else:
        custom_row_scores = pd.Series(0.0, index=dp.df.index, name="custom_row_score")

    # Combined per-row score: linear combination of source row scores by their
    # source weights (as fractions). When only one source is active, that
    # source's row scores pass through unchanged.
    w_std = float(source_weights.get(SOURCE_STANDARD, 0.0)) / 100.0
    w_cus = float(source_weights.get(SOURCE_CUSTOM, 0.0)) / 100.0
    weight_total = w_std + w_cus
    if weight_total <= 0:
        # Defensive fallback - should not happen because effective_source_weights
        # always assigns 100 to the lone source.
        combined_row_scores = pd.Series(0.0, index=dp.df.index, name="row_score")
    else:
        # Renormalize so partial-zero edge cases (e.g. only standard active but
        # source_weights miswritten) still produce a well-defined score.
        w_std_n = w_std / weight_total
        w_cus_n = w_cus / weight_total
        combined_row_scores = (
            w_std_n * standard_row_scores + w_cus_n * custom_row_scores
        ).rename("row_score")

    # Per-CDE scores: mean of pass rates of every rule tied to that CDE -
    # Standard rules via ``a.cde_column``, Custom rules via the
    # ``required_columns`` declared in the rule catalog (each required column
    # is treated as a CDE the rule depends on, so a custom rule contributes
    # to every CDE it reads from). When only the Custom source is selected
    # this keeps the dashboard's "By CDE" tab populated instead of showing
    # every CDE at 0.
    # Only roll up rules that actually produced a pass rate. Rules in
    # ``not_computed_standard_rules`` / ``not_evaluated_custom_rules`` are
    # excluded from the mean - consistent with the row score, which also drops
    # them (their weight is renormalized across the surviving rules, not scored
    # as 0). Inflating the per-CDE / per-dimension means with literal zeros
    # would instead mask which rules are healthy on a partially-broken
    # configuration.
    custom_rule_cdes: Dict[str, List[str]] = {}
    custom_rule_types: Dict[str, str] = {}
    if config.custom_assignments:
        # Imported lazily - catalog imports from ``src.custom_dqr_engine``
        # which already imports from ``src.models``; importing at module
        # top would risk a circular import.
        from config.custom_dqr_catalog import (
            effective_required_columns,
            get_available_custom_dqr_rules,
        )
        catalog = {r.id: r for r in get_available_custom_dqr_rules(dp.system_code)}
        for a in config.custom_assignments:
            rule = catalog.get(a.rule_id)
            if rule is None:
                continue
            req = effective_required_columns(rule, getattr(a, "params", None) or {})
            custom_rule_cdes[a.rule_id] = list(req.values())
            custom_rule_types[a.rule_id] = rule.type

    cde_scores: Dict[str, float] = {}
    for cde in config.cdes:
        contributions: List[float] = []
        for a in config.assignments:
            if a.cde_column == cde and a.rule_id in rule_pass_rates:
                contributions.append(rule_pass_rates[a.rule_id])
        for rule_id, cols in custom_rule_cdes.items():
            if cde in cols and rule_id in custom_rule_pass_rates:
                contributions.append(custom_rule_pass_rates[rule_id])
        cde_scores[cde] = float(np.mean(contributions)) if contributions else 0.0

    dimension_scores: Dict[str, float] = {}
    dims_used = sorted(
        {a.dimension for a in config.assignments}
        | set(custom_rule_types.values())
    )
    for d in dims_used:
        contributions: List[float] = []
        for a in config.assignments:
            if a.dimension == d and a.rule_id in rule_pass_rates:
                contributions.append(rule_pass_rates[a.rule_id])
        for rule_id, rule_type in custom_rule_types.items():
            if rule_type == d and rule_id in custom_rule_pass_rates:
                contributions.append(custom_rule_pass_rates[rule_id])
        if contributions:
            dimension_scores[d] = float(np.mean(contributions))

    rows_green = int((combined_row_scores >= threshold_green).sum())
    rows_red = int((combined_row_scores < threshold_yellow).sum())
    rows_yellow = int(dp.row_count - rows_green - rows_red)

    overall = float(combined_row_scores.mean()) if len(combined_row_scores) else 0.0

    return ScorecardResult(
        system_code=dp.system_code,
        overall_score=overall,
        row_scores=combined_row_scores,
        rule_pass_rates=rule_pass_rates,
        cde_scores=cde_scores,
        dimension_scores=dimension_scores,
        total_rows=dp.row_count,
        rows_green=rows_green,
        rows_yellow=rows_yellow,
        rows_red=rows_red,
        threshold_green=threshold_green,
        threshold_yellow=threshold_yellow,
        standard_score=standard_score,
        custom_score=custom_score,
        source_weights=source_weights,
        custom_rule_pass_rates=custom_rule_pass_rates,
        not_evaluated_custom_rules=not_evaluated_custom_rules,
        not_computed_standard_rules=not_computed_standard_rules,
    )
