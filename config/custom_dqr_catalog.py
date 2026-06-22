"""Custom DQR catalog - public entry point.

Each entry is a :class:`CustomRuleDef` carrying the metadata shown to the
user in Step 4.2 (id, name, type, description, notes, required columns,
optional reference dataset, blocking flag) plus a ``check`` callable that
evaluates the rule row-by-row.

The implementation has been partitioned by system into
:mod:`config.custom_dqr`. This module re-exports the public names so
external callers (the UI, the domain registry, the tests) keep importing
from ``config.custom_dqr_catalog`` exactly as before.

To add a rule:

1. Implement (or reuse) a ``check(df) -> pd.Series[bool]`` in
   :mod:`src.custom_dqr_engine`. Reusable validators are exposed there
   (``validate_completeness_rule``, ``validate_referential_integrity_rule``).
2. Append a new ``CustomRuleDef(...)`` to the relevant
   ``config/custom_dqr/_<system>_catalog.py`` list.

Data products without any custom rules keep an empty list, the UI shows
a clear empty-state message in Step 4.2.
"""
from __future__ import annotations

from typing import Dict, List

from config.custom_dqr._acce_catalog import ACCE_RULES
from config.custom_dqr._adr_catalog import ADR_RULES
from config.custom_dqr._ept_catalog import EPT_RULES
from config.custom_dqr._shared import (
    CustomRuleDef,
    CustomRuleOption,
    CustomRuleSelectOption,
    effective_required_columns,
)

CUSTOM_DQR_RULES: Dict[str, List[CustomRuleDef]] = {
    "EPT": EPT_RULES,
    "ADR": ADR_RULES,
    "ACCE": ACCE_RULES,
}


def get_available_custom_dqr_rules(data_product: str) -> List[CustomRuleDef]:
    """Return the list of custom rules configured for ``data_product`` in
    the *active domain*.

    The legacy ``CUSTOM_DQR_RULES`` dict in this module continues to be
    the source of truth for the Cost Estimate domain (it's reused
    verbatim by ``config.domains._build_cost_estimate_domain``). Other
    domains carry their own per-system rule lists inside their
    ``DomainDef`` and are looked up here.

    Unknown data products return an empty list (no error) so the UI can show
    its empty-state message.
    """
    from config.domains import get_active_domain

    domain_rules = get_active_domain().custom_rules
    return list(domain_rules.get(data_product, []))


__all__ = [
    "CUSTOM_DQR_RULES",
    "CustomRuleDef",
    "CustomRuleOption",
    "CustomRuleSelectOption",
    "effective_required_columns",
    "get_available_custom_dqr_rules",
]
