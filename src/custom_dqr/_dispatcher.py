"""Dispatcher: evaluate a list of CustomDQRAssignments against the catalog."""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

import pandas as pd

from src.custom_dqr._shared import (
    CustomRuleNotEvaluated,
    _check_supports_params,
)
from src.models import CustomDQRAssignment

logger = logging.getLogger(__name__)


def evaluate_custom_rules(
    df: pd.DataFrame,
    assignments: List[CustomDQRAssignment],
    data_product: str,
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Return ``(results_df, not_evaluated)``.

    - ``results_df``: one Boolean column per *evaluated* rule_id.
    - ``not_evaluated``: ``rule_id`` → human-readable reason, populated when
      a rule's ``check`` raises :class:`CustomRuleNotEvaluated` *or* any other
      unexpected exception. The rule is omitted from ``results_df`` so the
      remaining rules' weights renormalize across what actually ran.

    Mirrors :func:`src.dqr_engine.evaluate_all_safe`: an unexpected error in a
    custom check (a rule bug, an unforeseen data shape) is downgraded to "Not
    evaluated" and logged, never propagated - otherwise a single bad rule
    would crash the whole Step 6 dashboard.

    Rules unknown for the ``data_product`` in the catalog are skipped silently.
    """
    # Imported lazily to avoid a circular import (catalog imports check fns
    # from this module).
    from config.custom_dqr_catalog import get_available_custom_dqr_rules

    out = pd.DataFrame(index=df.index)
    not_evaluated: Dict[str, str] = {}
    if not assignments:
        return out, not_evaluated
    catalog = {r.id: r for r in get_available_custom_dqr_rules(data_product)}
    for a in assignments:
        rule = catalog.get(a.rule_id)
        if rule is None:
            continue
        try:
            if _check_supports_params(rule.check):
                params = dict(getattr(a, "params", None) or {})
                raw = rule.check(df, params=params)
            else:
                raw = rule.check(df)
            result = raw.fillna(False).astype(bool)
        except CustomRuleNotEvaluated as exc:
            not_evaluated[a.rule_id] = str(exc)
            continue
        except Exception as exc:
            # Broad on purpose: last line of defense for Step 6. An
            # unexpected failure in a custom check (rule bug, unforeseen data
            # shape) must downgrade to "Not evaluated" instead of crashing the
            # dashboard. Logged with a traceback so prod runs leave a trail.
            logger.warning(
                "Custom DQR %s raised; marking as Not evaluated",
                a.rule_id,
                exc_info=True,
            )
            not_evaluated[a.rule_id] = (
                f"Unable to evaluate this Custom DQR: {exc}"
            )
            continue
        out[a.rule_id] = result
    return out, not_evaluated
