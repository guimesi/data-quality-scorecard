"""Shared dataclasses and option-builder helpers for the custom DQR catalog.

Holds:

- :class:`CustomRuleOption` / :class:`CustomRuleSelectOption` / :class:`CustomRuleDef`:
  the data shapes that describe a rule card.
- :func:`_percentile_threshold_option` / :func:`_uniform_mapping_option` /
  :func:`_iqr_threshold_option`: builders for the recurring toggles and
  selectboxes (centralised so E3 / A3 and E6 / A7 / A8 / AC7 / AC8 stay in
  lockstep).
- :func:`effective_required_columns`: composes a rule's static
  ``required_columns`` with extras contributed by enabled options. Used by
  Step 4.2's CDE-coverage validation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class CustomRuleOption:
    """A user-toggleable option exposed on a custom rule card in Step 4.2.

    Each option is rendered as an ``st.toggle`` below the rule's description.
    The selected value is persisted to ``CustomDQRAssignment.params[key]``
    and consumed by the rule's ``check`` callable when it accepts a
    ``params`` argument (see ``src.custom_dqr_engine._check_supports_params``).

    ``required_columns_when_enabled`` lists extra source columns that become
    required when the toggle is on; Step 4.2 folds them into the CDE-coverage
    validation so the user can't ship a configuration that the rule would
    reject at evaluation time.
    """
    key: str                                   # stored at assignment.params[key]
    label: str                                 # short toggle label
    default: bool = False
    help: str = ""                             # tooltip on the toggle widget
    description: str = ""                      # markdown shown below the toggle
    required_columns_when_enabled: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomRuleSelectOption:
    """A user-selectable option (``st.selectbox``) on a custom rule card.

    Used by statistical-outlier rules to let the user pick a threshold
    (percentile or IQR multiplier). The selected value is persisted to
    ``CustomDQRAssignment.params[key]`` and consumed by the rule's
    ``check`` callable.

    ``choices`` is an ordered list of ``(value, label)`` pairs. ``value``
    is what gets stored in ``params``; ``label`` is what the user sees in
    the dropdown. The label is the right place to call out which choice
    is the recommended baseline (e.g. ``"P90 - recommended"``).
    """
    key: str
    label: str
    choices: Tuple[Tuple[Any, str], ...]
    default: Any                               # must match one of choices[*][0]
    help: str = ""
    description: str = ""


@dataclass(frozen=True)
class CustomRuleDef:
    id: str
    name: str
    type: str                                  # e.g. "Completeness", "Referential Integrity"
    description: str
    notes: str
    required_columns: Dict[str, str] = field(default_factory=dict)
    blocking: bool = False
    check: Callable[..., pd.Series] = lambda df: pd.Series(True, index=df.index)
    # Optional metadata for referential-integrity rules. When set, the UI
    # surfaces the reference dataset + source/reference column mapping in
    # the rule card's expandable details.
    reference: Optional[Dict[str, str]] = None
    # Per-rule toggleable options. Empty by default; Step 4.2 only renders
    # the option block for rules that declare at least one entry.
    options: List[CustomRuleOption] = field(default_factory=list)
    # Per-rule single-choice options (``st.selectbox``). Used for the
    # statistical-outlier threshold pickers (E3 / E6 / A3 / A7 / A8) where
    # the user picks one value from a small, curated list. Defaults to
    # empty so non-outlier rules don't render a selectbox they don't need.
    select_options: List[CustomRuleSelectOption] = field(default_factory=list)


_PERCENTILE_OPTION_DESCRIPTION = (
    "**How this option works**\n\n"
    "The rule flags an outlier when its ratio is strictly greater "
    "than this percentile of the eligible-mapping distribution. "
    "Raising the threshold (P95 / P99) makes the rule **stricter** "
    "- only the most extreme mappings are flagged. Lowering it "
    "(P75) makes it **more sensitive**: a broader slice of the "
    "tail is flagged. The default (**P90**) is the recommended "
    "starting point and matches the rule specification."
)

_IQR_OPTION_DESCRIPTION = (
    "**How this option works**\n\n"
    "The rule uses the IQR (interquartile range) method: a value "
    "is flagged when it falls outside `Q1 − k·IQR … Q3 + k·IQR`, "
    "where `k` is this multiplier. A **larger** `k` widens the "
    "PASS band - fewer flagged outliers, more lenient. A **smaller** "
    "`k` narrows the band - more sensitive. The default "
    "(**1.5×IQR - mild outliers**) is the textbook recommendation "
    "and the rule's documented baseline."
)


def _percentile_threshold_option(
    param: str, choices: Tuple[Tuple[float, str], ...], default: float
) -> CustomRuleSelectOption:
    """Build the percentile-threshold selectbox shared by E3 and A3.

    Centralised so the two rules stay in lockstep on label / help / default
    semantics - there is one recommendation, surfaced identically wherever
    the percentile picker shows up."""
    return CustomRuleSelectOption(
        key=param,
        label="Percentile threshold",
        choices=choices,
        default=default,
        help=(
            "Outlier threshold: ratios strictly greater than this "
            "percentile of the eligible-mapping distribution fail. "
            "P90 is recommended."
        ),
        description=_PERCENTILE_OPTION_DESCRIPTION,
    )


_UNIFORM_MAPPING_OPTION_DESCRIPTION = (
    "**How this option works**\n\n"
    "On top of the percentile-based outlier check, the rule also flags "
    "any *material* ISO bucket whose distinct-WBC ratio is exactly **1** "
    "- i.e. one WBC per ISO mapping. A perfectly uniform 1:1 distribution "
    "is usually a sign that the mapping process was bypassed and source "
    "codes were copied 1:1 into the ISO bucket instead of being "
    "aggregated. **Off by default** because a small / early dataset can "
    "legitimately show ratio = 1 for every bucket; turn it on when you "
    "want to surface mapping discipline issues. The percentile fail and "
    "the uniform-1:1 fail combine with OR - both signals coexist when "
    "the toggle is on."
)


def _uniform_mapping_option(param: str) -> "CustomRuleOption":
    """Build the uniform-1:1 mapping toggle shared by E3 and A3.

    Centralised so the two rules stay in lockstep on label / help / default
    - there is one recommendation, surfaced identically wherever the
    uniform-detection toggle shows up."""
    return CustomRuleOption(
        key=param,
        label="Detect uniform 1:1 mappings",
        default=False,
        help=(
            "When on, ISO buckets whose distinct-WBC ratio equals 1 are "
            "also flagged as FAIL (suspiciously uniform mapping). "
            "Off by default."
        ),
        description=_UNIFORM_MAPPING_OPTION_DESCRIPTION,
    )


def _iqr_threshold_option(
    param: str, choices: Tuple[Tuple[float, str], ...], default: float
) -> CustomRuleSelectOption:
    """Build the IQR-multiplier selectbox shared by E6 / A7 / A8."""
    return CustomRuleSelectOption(
        key=param,
        label="IQR multiplier",
        choices=choices,
        default=default,
        help=(
            "Outlier band width: values outside Q1 − k·IQR … Q3 + k·IQR "
            "fail. 1.5× (mild) is recommended."
        ),
        description=_IQR_OPTION_DESCRIPTION,
    )


def effective_required_columns(
    rule: "CustomRuleDef", params: Optional[Dict[str, object]] = None
) -> Dict[str, str]:
    """Compose the rule's static ``required_columns`` with any extras
    contributed by enabled options. The Step 4.2 CDE-coverage check uses
    this to validate against the *active* configuration (so a user that
    flips on E3's project-scoped toggle is also told to add ``PLANVIEW_ID``
    to the CDEs)."""
    out = dict(rule.required_columns)
    if not rule.options:
        return out
    p = params or {}
    for opt in rule.options:
        if not bool(p.get(opt.key, opt.default)):
            continue
        for alias, col in opt.required_columns_when_enabled.items():
            out.setdefault(alias, col)
    return out
