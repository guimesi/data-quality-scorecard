"""Pure rule-table row builders shared by the Step 6 dashboard and the
Data Quality Report.

The dashboard's "Rules (pass rate)" / "Custom Rules" tabs and the HTML
report's Standard / Custom DQR sections must show the same numbers, so
both build their rows here - one source of truth, no Streamlit imports.

Each row is a plain dict carrying the full picture (id, weight, status,
reason, pass rate, params, and for custom rules the catalog definition);
each caller then projects the fields it displays.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from config.custom_dqr_catalog import get_available_custom_dqr_rules

STATUS_EVALUATED = "Evaluated"
STATUS_NOT_COMPUTED = "Not computed"
STATUS_NOT_EVALUATED = "Not evaluated"


def standard_rule_rows(cfg, result) -> List[Dict]:
    """One dict per Standard assignment, in configuration order.

    ``pass_rate`` is ``None`` when the rule was not computed (the reason
    is in ``reason``); otherwise the engine's pass rate in percent.
    """
    rows: List[Dict] = []
    for a in cfg.assignments:
        reason: Optional[str] = result.not_computed_standard_rules.get(a.rule_id)
        rows.append({
            "rule_id": a.rule_id,
            "cde": a.cde_column,
            "dimension": a.dimension,
            "weight": float(a.weight),
            "params": dict(a.params or {}),
            "status": STATUS_NOT_COMPUTED if reason is not None
                      else STATUS_EVALUATED,
            "reason": reason,
            "pass_rate": None if reason is not None
                         else float(result.rule_pass_rates.get(a.rule_id, 0.0)),
        })
    return rows


def custom_rule_rows(system_code: str, cfg, result) -> List[Dict]:
    """One dict per Custom assignment, in configuration order.

    ``rule`` is the :class:`CustomRuleDef` from the catalog (or ``None``
    for an unknown id - the row degrades to the id, like the dashboard).
    """
    catalog = {r.id: r for r in get_available_custom_dqr_rules(system_code)}
    rows: List[Dict] = []
    for a in cfg.custom_assignments:
        rule = catalog.get(a.rule_id)
        reason: Optional[str] = result.not_evaluated_custom_rules.get(a.rule_id)
        rows.append({
            "rule_id": a.rule_id,
            "name": rule.name if rule is not None else a.rule_id,
            "type": rule.type if rule is not None else "-",
            "blocking": bool(rule is not None and rule.blocking),
            "weight": float(a.weight),
            "params": dict(getattr(a, "params", None) or {}),
            "rule": rule,
            "status": STATUS_NOT_EVALUATED if reason is not None
                      else STATUS_EVALUATED,
            "reason": reason,
            "pass_rate": None if reason is not None
                         else float(result.custom_rule_pass_rates.get(a.rule_id, 0.0)),
        })
    return rows
