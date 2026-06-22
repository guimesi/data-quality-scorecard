"""Tests for the One-click automation service (``src.one_click``).

Covers the pure-logic helpers (default params, config building) and the
end-to-end ``run_one_click`` orchestration against mock data, including the
edge cases the feature must validate: no domain, no system, a system with
no custom rules, an empty data product after filtering, and a scorecard
generation failure.

``run_one_click`` resolves the rule catalog through the *active* domain
(``get_active_domain``), so tests that exercise a specific domain set
``st.session_state['domain']`` first - the same contract the One-click UI
satisfies by calling ``set_domain``.
"""
from __future__ import annotations

import contextlib

import pytest
import streamlit as st

from config.custom_dqr._shared import CustomRuleOption, CustomRuleSelectOption
from config.custom_dqr_catalog import CustomRuleDef, get_available_custom_dqr_rules
from config.dqr_sources import SOURCE_CUSTOM, SOURCE_STANDARD
from src.data_product_builder import build_data_product
from src.one_click import (
    OneClickError,
    build_one_click_config,
    default_rule_params,
    run_one_click,
)
from src.profiler import profile_dataframe


@contextlib.contextmanager
def active_domain(code: str):
    """Set the active domain for the duration of the block, then restore it.

    ``run_one_click`` and ``compute_scorecard`` look the rule catalog up via
    the active domain in session state; pinning it here keeps tests isolated
    from whatever a previous test left behind."""
    previous = st.session_state.get("domain")
    st.session_state["domain"] = code
    try:
        yield
    finally:
        if previous is None:
            st.session_state.pop("domain", None)
        else:
            st.session_state["domain"] = previous


def _profiled_dp(system: str):
    dp = build_data_product(system)
    dp.profiles = profile_dataframe(dp.df)
    return dp


# ---------------------------------------------------------------------------
# default_rule_params
# ---------------------------------------------------------------------------

def test_default_rule_params_reads_option_and_select_defaults():
    rule = CustomRuleDef(
        id="X1",
        name="Demo",
        type="Completeness",
        description="d",
        notes="n",
        options=[
            CustomRuleOption(key="flag_on", label="On", default=True),
            CustomRuleOption(key="flag_off", label="Off", default=False),
        ],
        select_options=[
            CustomRuleSelectOption(
                key="pctl", label="P", choices=((90.0, "P90"), (95.0, "P95")),
                default=90.0,
            ),
        ],
    )
    params = default_rule_params(rule)
    assert params == {"pctl": 90.0, "flag_on": True, "flag_off": False}


def test_default_rule_params_empty_for_optionless_rule():
    rule = CustomRuleDef(id="X2", name="n", type="t", description="d", notes="n")
    assert default_rule_params(rule) == {}


# ---------------------------------------------------------------------------
# build_one_click_config
# ---------------------------------------------------------------------------

def test_build_config_is_custom_only_with_equal_weights():
    with active_domain("cost_estimate"):
        dp = _profiled_dp("EPT")
        rules = get_available_custom_dqr_rules("EPT")
        cfg, warnings = build_one_click_config("EPT", dp, rules)

    # Custom source only - never Standard.
    assert cfg.dqr_sources == [SOURCE_CUSTOM]
    assert SOURCE_STANDARD not in cfg.dqr_sources
    assert cfg.source_weights == {SOURCE_CUSTOM: 100.0}
    assert cfg.assignments == []  # no Standard DQR assignments

    # Every available custom rule is selected.
    assert len(cfg.custom_assignments) == len(rules)
    assert {a.rule_id for a in cfg.custom_assignments} == {r.id for r in rules}

    # Weights are distributed equally and sum to 100.
    weights = [a.weight for a in cfg.custom_assignments]
    assert round(sum(weights), 2) == 100.0
    assert max(weights) - min(weights) <= 0.01
    assert not warnings


def test_build_config_selects_only_required_cdes_in_column_order():
    with active_domain("cost_estimate"):
        dp = _profiled_dp("EPT")
        rules = get_available_custom_dqr_rules("EPT")
        cfg, _ = build_one_click_config("EPT", dp, rules)

        # The CDE set is exactly the union of the rules' required columns
        # that exist in the data product - nothing more.
        required = set()
        for rule in rules:
            from config.custom_dqr_catalog import effective_required_columns
            required |= set(
                effective_required_columns(rule, default_rule_params(rule)).values()
            )
        expected = [c for c in dp.df.columns if c in required]
    assert cfg.cdes == expected
    assert cfg.cdes  # EPT rules declare real columns, so this is non-empty
    # No non-required column leaked into the CDE selection.
    assert all(c in required for c in cfg.cdes)


def test_build_config_uses_default_rule_params():
    with active_domain("cost_estimate"):
        dp = _profiled_dp("EPT")
        rules = get_available_custom_dqr_rules("EPT")
        cfg, _ = build_one_click_config("EPT", dp, rules)
        catalog = {r.id: r for r in rules}
    for a in cfg.custom_assignments:
        assert a.params == default_rule_params(catalog[a.rule_id])


# ---------------------------------------------------------------------------
# run_one_click - happy path
# ---------------------------------------------------------------------------

def test_run_one_click_scores_all_cost_estimate_systems():
    with active_domain("cost_estimate"):
        result = run_one_click("cost_estimate", ["EPT", "ADR", "ACCE"])
    assert set(result.scored_systems) == {"EPT", "ADR", "ACCE"}
    assert result.skipped == {}
    for code in ("EPT", "ADR", "ACCE"):
        product = result.products[code]
        assert product.config.dqr_sources == [SOURCE_CUSTOM]
        assert product.scorecard.total_rows > 0
        assert 0.0 <= product.scorecard.overall_score <= 100.0
        # custom-only -> a custom score, no standard score
        assert product.scorecard.standard_score is None
        assert product.scorecard.custom_score is not None


def test_run_one_click_ept_score_invariants():
    """Deterministic invariants of a one-click EPT run, stronger than the bare
    0 <= score <= 100 bound: it is custom-only (no standard score), the overall
    equals the custom score exactly, all seven EPT rules (E1-E7) are evaluated,
    and the overall sits within the min/max of the per-rule pass rates (it is
    their equal-weight mean).

    A hard golden value is intentionally NOT pinned: the mock data builder
    regenerates different EPT values on every call, so the statistical rules
    (E3/E6) and the overall shift run-to-run - the score is not per-call
    deterministic despite ARCHITECTURE.md describing the mock data as deterministic
    (flagged separately). That non-determinism is exactly why the sibling test
    asserts only the 0-100 bound."""
    with active_domain("cost_estimate"):
        result = run_one_click("cost_estimate", ["EPT"])
    sc = result.products["EPT"].scorecard
    assert sc.total_rows > 0
    assert sc.standard_score is None                 # custom-only
    assert sc.custom_score is not None
    assert sc.overall_score == sc.custom_score       # custom-only identity (exact)
    rates = sc.custom_rule_pass_rates
    assert len(rates) == 7                            # E1..E7 all evaluated
    # The overall is the equal-weight combination of the rule pass rates, so it
    # must lie within their range regardless of the (varying) data values.
    assert min(rates.values()) <= sc.overall_score <= max(rates.values())


def test_run_one_click_scorecards_match_their_configs():
    """The scorecard stored by the service equals a fresh recompute from the
    same config - so the dashboard's re-render produces an identical score."""
    from src.scorecard import compute_scorecard

    with active_domain("cost_estimate"):
        result = run_one_click("cost_estimate", ["EPT"])
        product = result.products["EPT"]
        recomputed = compute_scorecard(product.data_product, product.config)
    assert round(product.scorecard.overall_score, 6) == round(
        recomputed.overall_score, 6
    )


def test_run_one_click_csv_is_generatable():
    from ui.step_06._export import _build_rowscores_csv

    with active_domain("cost_estimate"):
        result = run_one_click("cost_estimate", ["EPT"])
        product = result.products["EPT"]
        csv_bytes = _build_rowscores_csv(
            product.data_product, product.scorecard, product.config
        )
    assert b"_row_score" in csv_bytes and b"_status" in csv_bytes
    # One header line + one line per row.
    assert len(csv_bytes.decode().splitlines()) == product.scorecard.total_rows + 1


def test_run_one_click_quality_domain():
    with active_domain("quality"):
        result = run_one_click("quality", ["SQS"])
    assert result.scored_systems == ["SQS"]
    product = result.products["SQS"]
    assert product.config.dqr_sources == [SOURCE_CUSTOM]
    assert len(product.config.custom_assignments) > 0


# ---------------------------------------------------------------------------
# run_one_click - validation / edge cases
# ---------------------------------------------------------------------------

def test_run_one_click_no_domain_raises():
    with pytest.raises(OneClickError, match="No domain"):
        run_one_click("", ["EPT"])


def test_run_one_click_unknown_domain_raises():
    with pytest.raises(OneClickError, match="Unknown domain"):
        run_one_click("nope", ["EPT"])


def test_run_one_click_no_system_raises():
    with pytest.raises(OneClickError, match="No system"):
        run_one_click("cost_estimate", [])


def test_run_one_click_skips_system_without_custom_rules(monkeypatch):
    """A selected system with no applicable custom rules is skipped (not
    scored), with a reason - One-click is custom-only."""
    import src.one_click as oc

    monkeypatch.setattr(oc, "get_available_custom_dqr_rules", lambda code: [])
    with active_domain("cost_estimate"):
        result = run_one_click("cost_estimate", ["EPT"])
    assert result.products == {}
    assert "EPT" in result.skipped
    assert "no Custom DQR rules" in result.skipped["EPT"]


def test_run_one_click_skips_empty_data_product():
    """A project filter that matches no rows yields a 0-row data product,
    which is skipped rather than scored at a meaningless 0."""
    with active_domain("cost_estimate"):
        result = run_one_click(
            "cost_estimate", ["EPT"], planview_filter=["DOES-NOT-EXIST-XYZ"]
        )
    assert result.products == {}
    assert "EPT" in result.skipped
    assert "0 rows" in result.skipped["EPT"]


def test_run_one_click_handles_scorecard_failure(monkeypatch):
    """A scorecard error for one system is captured as a skip reason instead
    of aborting the whole run."""
    import src.one_click as oc

    def _boom(*a, **k):
        raise RuntimeError("scorecard kaboom")

    monkeypatch.setattr(oc, "compute_scorecard", _boom)
    with active_domain("cost_estimate"):
        result = run_one_click("cost_estimate", ["EPT"])
    assert result.products == {}
    assert "scorecard generation failed" in result.skipped["EPT"]


def test_run_one_click_build_failure_raises(monkeypatch):
    """A data-product build failure surfaces as a blocking OneClickError."""
    import src.one_click as oc

    monkeypatch.setattr(
        oc, "build_multiple",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("snowflake down")),
    )
    with active_domain("cost_estimate"):
        with pytest.raises(OneClickError, match="Failed to build data products"):
            run_one_click("cost_estimate", ["EPT"])


def test_run_one_click_warns_on_missing_required_column(monkeypatch):
    """When a rule needs a column absent from the data product, the run still
    succeeds for the other rules but records a warning."""
    import src.one_click as oc

    real_rules = None
    with active_domain("cost_estimate"):
        real_rules = list(get_available_custom_dqr_rules("EPT"))
        # Add a synthetic rule that needs a column EPT does not have.
        ghost = CustomRuleDef(
            id="GHOST",
            name="Ghost",
            type="Completeness",
            description="d",
            notes="n",
            required_columns={"x": "COLUMN_THAT_DOES_NOT_EXIST"},
        )
        monkeypatch.setattr(
            oc, "get_available_custom_dqr_rules",
            lambda code: real_rules + [ghost],
        )
        result = run_one_click("cost_estimate", ["EPT"])
    assert "EPT" in result.products  # still scored
    assert any("COLUMN_THAT_DOES_NOT_EXIST" in w for w in result.warnings)
