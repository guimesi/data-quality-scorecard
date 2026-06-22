"""Invariants for the per-system catalog modules introduced by M6.

After splitting :mod:`config.custom_dqr_catalog` into per-system files
(:mod:`config.custom_dqr._ept_catalog`, ``._adr_catalog``, ``._acce_catalog``),
these tests pin the structural invariants that hold across families so
future edits to a single catalog don't silently break the others:

- every rule's ``check`` is a callable
- every rule's ``required_columns`` is a non-empty dict (or empty for
  rules that scan the entire frame)
- every ``CustomRuleSelectOption.default`` is one of its ``choices``
- the union of catalog rule ids matches what ``get_available_custom_dqr_rules``
  surfaces for the Cost Estimate domain
"""
from __future__ import annotations

import pandas as pd

from config.custom_dqr._acce_catalog import ACCE_RULES
from config.custom_dqr._adr_catalog import ADR_RULES
from config.custom_dqr._ept_catalog import EPT_RULES
from config.custom_dqr._shared import (
    CustomRuleDef,
    CustomRuleOption,
    CustomRuleSelectOption,
    effective_required_columns,
)
from config.custom_dqr._sqs_catalog import SQS_RULES
from config.custom_dqr_catalog import (
    CUSTOM_DQR_RULES,
    get_available_custom_dqr_rules,
)

ALL_RULES: list[CustomRuleDef] = [*EPT_RULES, *ADR_RULES, *ACCE_RULES, *SQS_RULES]


# ---------------------------------------------------------------------------
# Each catalog list is non-empty and items are CustomRuleDef
# ---------------------------------------------------------------------------

def test_ept_catalog_is_non_empty_list_of_custom_rule_defs():
    assert EPT_RULES
    assert all(isinstance(r, CustomRuleDef) for r in EPT_RULES)


def test_adr_catalog_is_non_empty_list_of_custom_rule_defs():
    assert ADR_RULES
    assert all(isinstance(r, CustomRuleDef) for r in ADR_RULES)


def test_acce_catalog_is_non_empty_list_of_custom_rule_defs():
    assert ACCE_RULES
    assert all(isinstance(r, CustomRuleDef) for r in ACCE_RULES)


def test_sqs_catalog_is_non_empty_list_of_custom_rule_defs():
    """SQS (Quality domain) ships its first curated rule (SQ4)."""
    assert SQS_RULES
    assert all(isinstance(r, CustomRuleDef) for r in SQS_RULES)


# ---------------------------------------------------------------------------
# Assembly: CUSTOM_DQR_RULES dict mirrors the per-system lists
# ---------------------------------------------------------------------------

def test_combined_catalog_matches_per_system_lists():
    """``CUSTOM_DQR_RULES`` is assembled from the three per-system lists; if a
    new system is added but forgotten in the dict, this test will catch it.

    SQS lives in the Quality domain's ``custom_rules`` map (not the legacy
    ``CUSTOM_DQR_RULES`` dict that backs the Cost Estimate domain), so it
    is not asserted here - see ``tests/test_domains.py`` for that coverage.
    """
    assert CUSTOM_DQR_RULES["EPT"] is EPT_RULES
    assert CUSTOM_DQR_RULES["ADR"] is ADR_RULES
    assert CUSTOM_DQR_RULES["ACCE"] is ACCE_RULES


# ---------------------------------------------------------------------------
# Per-rule invariants
# ---------------------------------------------------------------------------

def test_every_rule_has_unique_id_within_its_system():
    """Two rules in the same system sharing an id would silently shadow each
    other in the dispatcher and the UI."""
    for system, rules in CUSTOM_DQR_RULES.items():
        ids = [r.id for r in rules]
        assert len(ids) == len(set(ids)), f"Duplicate rule id in {system}: {ids}"


def test_every_rule_has_callable_check():
    for rule in ALL_RULES:
        assert callable(rule.check), rule.id


def test_every_rule_has_non_empty_name_and_type():
    for rule in ALL_RULES:
        assert rule.name, rule.id
        assert rule.type, rule.id


def test_every_select_option_default_is_in_choices():
    """A select option whose default isn't one of its choices would crash the
    rule card on first render (the selectbox can't find an index for an
    unknown value). M6 split the catalog by system so this guard is even more
    important - a typo in one file no longer fails when loading the others."""
    for rule in ALL_RULES:
        for sel in rule.select_options:
            assert isinstance(sel, CustomRuleSelectOption), rule.id
            values = [v for v, _ in sel.choices]
            assert sel.default in values, (rule.id, sel.key, sel.default, values)


def test_every_option_required_columns_is_str_mapping():
    """``required_columns_when_enabled`` feeds into ``effective_required_columns``;
    any non-string keys / values would break the dict-update there."""
    for rule in ALL_RULES:
        for opt in rule.options:
            assert isinstance(opt, CustomRuleOption), rule.id
            for k, v in opt.required_columns_when_enabled.items():
                assert isinstance(k, str), (rule.id, opt.key)
                assert isinstance(v, str), (rule.id, opt.key)


# ---------------------------------------------------------------------------
# Smoke: every check runs on an empty DataFrame without raising
# ---------------------------------------------------------------------------

def test_every_check_handles_empty_dataframe_without_raising():
    """Rules use the engine's ``_is_filled`` / ``validate_completeness_rule``
    helpers which all special-case empty input. This catches a future rule
    author who forgets the guard - the dispatcher already routes
    ``CustomRuleNotEvaluated`` so we ignore it here on purpose."""
    from src.custom_dqr_engine import CustomRuleNotEvaluated

    empty = pd.DataFrame()
    for rule in ALL_RULES:
        try:
            # Some checks take a ``params`` kwarg, some don't; the dispatcher
            # introspects to decide. We use the engine's own helper.
            from src.custom_dqr_engine import _check_supports_params
            if _check_supports_params(rule.check):
                out = rule.check(empty, params={})
            else:
                out = rule.check(empty)
        except CustomRuleNotEvaluated:
            # Rules that depend on a missing reference dataset raise this.
            # Acceptable: the dispatcher records it as "Not evaluated".
            continue
        assert isinstance(out, pd.Series), rule.id
        assert len(out) == 0


# ---------------------------------------------------------------------------
# get_available_custom_dqr_rules surfaces every catalog rule
# ---------------------------------------------------------------------------

def test_get_available_surfaces_every_ept_rule():
    """The active domain defaults to Cost Estimate, which wraps the three
    catalog lists. ``get_available_custom_dqr_rules`` therefore must return
    every EPT rule when asked for the EPT data product."""
    surfaced_ids = [r.id for r in get_available_custom_dqr_rules("EPT")]
    catalog_ids = [r.id for r in EPT_RULES]
    assert surfaced_ids == catalog_ids


def test_get_available_surfaces_every_adr_rule():
    surfaced_ids = [r.id for r in get_available_custom_dqr_rules("ADR")]
    catalog_ids = [r.id for r in ADR_RULES]
    assert surfaced_ids == catalog_ids


def test_get_available_surfaces_every_acce_rule():
    surfaced_ids = [r.id for r in get_available_custom_dqr_rules("ACCE")]
    catalog_ids = [r.id for r in ACCE_RULES]
    assert surfaced_ids == catalog_ids


# ---------------------------------------------------------------------------
# effective_required_columns shared by all systems
# ---------------------------------------------------------------------------

def test_effective_required_columns_no_options_returns_static_dict():
    """A rule without options short-circuits in
    :func:`effective_required_columns`; the static ``required_columns`` is
    returned as-is."""
    rule = CustomRuleDef(
        id="X", name="x", type="Completeness",
        description="", notes="",
        required_columns={"alias": "PHYSICAL"},
    )
    assert effective_required_columns(rule) == {"alias": "PHYSICAL"}


def test_effective_required_columns_disabled_option_does_not_contribute():
    rule = CustomRuleDef(
        id="X", name="x", type="Completeness",
        description="", notes="",
        required_columns={"a": "A"},
        options=[
            CustomRuleOption(
                key="opt", label="Opt",
                default=False,
                required_columns_when_enabled={"b": "B"},
            ),
        ],
    )
    # Default off → "b" must not appear in the effective requirements.
    assert effective_required_columns(rule) == {"a": "A"}


def test_effective_required_columns_enabled_option_merges():
    rule = CustomRuleDef(
        id="X", name="x", type="Completeness",
        description="", notes="",
        required_columns={"a": "A"},
        options=[
            CustomRuleOption(
                key="opt", label="Opt",
                default=False,
                required_columns_when_enabled={"b": "B"},
            ),
        ],
    )
    out = effective_required_columns(rule, {"opt": True})
    assert out == {"a": "A", "b": "B"}


def test_effective_required_columns_does_not_overwrite_static_keys():
    """If an option's key collides with a static required column, the
    static side wins (the option is additive only)."""
    rule = CustomRuleDef(
        id="X", name="x", type="Completeness",
        description="", notes="",
        required_columns={"a": "STATIC"},
        options=[
            CustomRuleOption(
                key="opt", label="Opt",
                default=True,
                required_columns_when_enabled={"a": "FROM_OPTION"},
            ),
        ],
    )
    out = effective_required_columns(rule, {"opt": True})
    assert out == {"a": "STATIC"}
