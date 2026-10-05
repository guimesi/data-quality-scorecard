"""Per-rule score history: one ``DQS_RULE_SCORES`` row per recorded run and rule.

The run history (:mod:`src.run_history`) keeps every rule's pass rate
inside the DQS_RUNS JSON payload; this module writes the same numbers as
a flat, queryable table so the trend of a single rule is one ``WHERE
RULE_ID = ...`` away. Written automatically whenever a run is recorded,
keyed by the run's snapshot ``id`` (``RUN_ID``).

One row per rule the run evaluated:

- Standard rules: ``rule_id`` is ``<CDE>::<Dimension>``, ``rule_type``
  ``Standard``, ``cde`` / ``dimension`` split from the id, ``rule_name``
  the dimension;
- Custom rules: ``rule_id`` is the catalog code, ``rule_type`` ``Custom``,
  ``rule_name`` / ``dimension`` (the rule's ``type``) from the catalog.

Rules that were not computed / not evaluated have no pass rate and get no
row.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.persistence import save_rule_scores

logger = logging.getLogger(__name__)


def rule_score_rows(dp_code: str, result: Any) -> List[Dict[str, Any]]:
    """The DQS_RULE_SCORES rows of one scorecard result (pure)."""
    rows: List[Dict[str, Any]] = []
    for rule_id, rate in result.rule_pass_rates.items():
        cde, _, dimension = str(rule_id).partition("::")
        rows.append({
            "rule_id": str(rule_id), "rule_type": "Standard",
            "rule_name": dimension, "cde": cde, "dimension": dimension,
            "score": round(float(rate), 4),
        })
    if result.custom_rule_pass_rates:
        # Imported lazily: the catalog pulls in the rule implementations.
        from config.custom_dqr_catalog import get_available_custom_dqr_rules

        catalog = {r.id: r for r in get_available_custom_dqr_rules(
            dp_code, include_inactive=True)}
        for rule_id, rate in result.custom_rule_pass_rates.items():
            rule = catalog.get(rule_id)
            rows.append({
                "rule_id": str(rule_id), "rule_type": "Custom",
                "rule_name": rule.name if rule else "",
                "cde": None,
                "dimension": rule.type if rule else "",
                "score": round(float(rate), 4),
            })
    return rows


def record_rule_scores(run_id: str, dp_code: str, domain_code: str, result: Any,
                       config_hash: str = "") -> bool:
    """Store the per-rule scores of the just-recorded run ``run_id``.
    Fire-and-forget: returns False (and logs) instead of raising."""
    try:
        rows = rule_score_rows(dp_code, result)
    except Exception:
        logger.warning("Rule-score rows failed for %s", dp_code, exc_info=True)
        return False
    return save_rule_scores(domain_code, dp_code, run_id, rows,
                            config_hash=config_hash)
