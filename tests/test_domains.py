"""Tests for the multi-domain layer.

Cover four areas:
1. Registry shape - both shipped domains are well-formed.
2. Cost Estimate parity - the pre-domain code paths still wire to the
   historical ADR / ACCE / EPT systems and 23 custom rules.
3. Quality domain - tables, rules and mock data load through the same
   builder pipeline that Cost Estimate uses.
4. Session state - picking, switching and clearing the active domain.
5. Extensibility - registering a new domain at runtime doesn't disturb
   the existing ones and is immediately reachable through every helper.
"""
from __future__ import annotations

import pytest

from config.custom_dqr_catalog import get_available_custom_dqr_rules
from config.domains import (
    DEFAULT_PROJECT_FILTER,
    DOMAIN_COST_ESTIMATE,
    DOMAIN_QUALITY,
    DOMAINS,
    DomainDef,
    ProjectFilterDef,
    get_active_domain,
    get_active_domain_code,
    get_active_project_filter,
    get_default_domain_code,
    get_domain,
    list_domain_codes,
    register_domain,
    unregister_domain,
)
from config.systems import SystemDef, TableDef, get_system, list_system_codes

# ---------------------------------------------------------------------------
# 1. Registry shape
# ---------------------------------------------------------------------------

def test_registry_lists_both_initial_domains():
    codes = list_domain_codes()
    assert DOMAIN_COST_ESTIMATE in codes
    assert DOMAIN_QUALITY in codes


def test_default_domain_is_cost_estimate():
    """Returning users land on the historical default so the introduction
    of Step 0 is non-disruptive when re-entering the app."""
    assert get_default_domain_code() == DOMAIN_COST_ESTIMATE


def test_get_domain_unknown_raises():
    with pytest.raises(KeyError, match="Unknown domain"):
        get_domain("not_a_real_domain")


def test_every_domain_has_required_fields():
    for code, domain in DOMAINS.items():
        assert domain.code == code
        assert domain.name, f"{code}: missing name"
        assert domain.icon, f"{code}: missing icon"
        assert domain.accent.startswith("#"), f"{code}: accent must be hex"
        # systems is allowed to be empty *only* if explicitly intended;
        # both shipped domains have at least one system.
        assert domain.systems, f"{code}: at least one system expected"
        # custom_rules keys must be a subset of systems keys - guards
        # against typos that would silently hide a curated rule.
        assert set(domain.custom_rules).issubset(set(domain.systems)), (
            f"{code}: custom_rules references unknown systems"
        )


def test_every_domain_declares_a_project_filter():
    """The sidebar Project filter is domain-aware, every registered
    ``DomainDef`` must surface a non-empty ``ProjectFilterDef`` so the
    sidebar widget renders sensible copy."""
    for code, domain in DOMAINS.items():
        pf = domain.project_filter
        assert isinstance(pf, ProjectFilterDef), f"{code}: project_filter missing"
        assert pf.column, f"{code}: project_filter.column empty"
        assert pf.label, f"{code}: project_filter.label empty"
        assert pf.placeholder, f"{code}: project_filter.placeholder empty"
        assert pf.help, f"{code}: project_filter.help empty"


def test_default_project_filter_targets_planview_id():
    """``DEFAULT_PROJECT_FILTER`` preserves the historical Cost Estimate
    behaviour so domains that omit ``project_filter`` keep filtering on
    ``PLANVIEW_ID``."""
    assert DEFAULT_PROJECT_FILTER.column == "PLANVIEW_ID"
    assert "PLANVIEW_ID" in DEFAULT_PROJECT_FILTER.label


def test_cost_estimate_project_filter_is_planview_id():
    """Cost Estimate keeps filtering on ``PLANVIEW_ID`` - the original
    cross-system project key shared by ADR / ACCE / EPT."""
    pf = DOMAINS[DOMAIN_COST_ESTIMATE].project_filter
    assert pf.column == "PLANVIEW_ID"
    assert pf.label == "PLANVIEW_ID(s)"


def test_quality_project_filter_is_project_code():
    """Quality switches the filter to ``PROJECT_CODE`` so the SQS flow
    matches the column the Quality team wants to slice by."""
    pf = DOMAINS[DOMAIN_QUALITY].project_filter
    assert pf.column == "PROJECT_CODE"
    assert pf.label == "PROJECT_CODE(s)"


def test_get_active_project_filter_follows_session_state(monkeypatch):
    """``get_active_project_filter()`` must resolve via the active
    domain, not via a hardcoded default - flipping ``session_state.domain``
    must immediately surface the new domain's filter config."""
    state = _session_state_dict(monkeypatch)
    monkeypatch.setitem(state, "domain", DOMAIN_COST_ESTIMATE)
    assert get_active_project_filter().column == "PLANVIEW_ID"
    monkeypatch.setitem(state, "domain", DOMAIN_QUALITY)
    assert get_active_project_filter().column == "PROJECT_CODE"


# ---------------------------------------------------------------------------
# 2. Cost Estimate parity
# ---------------------------------------------------------------------------

def test_cost_estimate_domain_keeps_adr_acce_ept(monkeypatch):
    """The Cost Estimate domain must expose the exact same three systems
    as the pre-domain build."""
    monkeypatch.setitem(_session_state_dict(monkeypatch), "domain",
                         DOMAIN_COST_ESTIMATE)
    assert set(list_system_codes()) == {"ADR", "ACCE", "EPT"}
    adr = get_system("ADR")
    assert adr.primary_table.name == "ADR_DIM_ESTIMATEITEMRECORD"


def test_cost_estimate_domain_keeps_full_custom_rule_catalog(monkeypatch):
    """The Cost Estimate domain wraps the legacy ``CUSTOM_DQR_RULES``
    dict so the curated rule catalogs are unchanged."""
    monkeypatch.setitem(_session_state_dict(monkeypatch), "domain",
                         DOMAIN_COST_ESTIMATE)
    adr_rules = get_available_custom_dqr_rules("ADR")
    acce_rules = get_available_custom_dqr_rules("ACCE")
    ept_rules = get_available_custom_dqr_rules("EPT")
    # 8 + 8 + 7 = 23 historical custom rules.
    assert len(adr_rules) + len(acce_rules) + len(ept_rules) == 23


def test_cost_estimate_data_product_builds_unchanged(monkeypatch):
    """Building a Cost Estimate data product must work exactly as before
    the domain refactor (smoke test of the full ADR build pipeline)."""
    monkeypatch.setitem(_session_state_dict(monkeypatch), "domain",
                         DOMAIN_COST_ESTIMATE)
    from src.data_product_builder import build_data_product
    dp = build_data_product("EPT")
    assert dp.system_code == "EPT"
    assert dp.row_count > 0
    assert "PLANVIEW_ID" in dp.df.columns


# ---------------------------------------------------------------------------
# 3. Quality domain
# ---------------------------------------------------------------------------

def test_quality_domain_has_single_sqs_system(monkeypatch):
    monkeypatch.setitem(_session_state_dict(monkeypatch), "domain", DOMAIN_QUALITY)
    assert set(list_system_codes()) == {"SQS"}
    sqs = get_system("SQS")
    assert sqs.primary_table.name == "CT_SQS_AT_INSPECTION"
    # CT_SQS_AT_INSPECTION is the sole table; PLANVIEW_ID is the
    # cross-system project key.
    assert sqs.table_names == ["CT_SQS_AT_INSPECTION"]
    assert sqs.primary_table.join_key == "PLANVIEW_ID"


def test_quality_domain_is_marked_placeholder():
    """The Quality domain ships with no curated rules yet, so the
    Step 0 card needs to set expectations - the flag must be true."""
    assert DOMAINS[DOMAIN_QUALITY].placeholder is True


def test_quality_domain_data_product_builds(monkeypatch):
    """Quality flows through the same builder as Cost Estimate - the
    single-table SQS system must yield a non-empty data product."""
    monkeypatch.setitem(_session_state_dict(monkeypatch), "domain", DOMAIN_QUALITY)
    from src.data_product_builder import build_data_product
    dp = build_data_product("SQS")
    assert dp.system_code == "SQS"
    assert dp.row_count > 0
    assert "PLANVIEW_ID" in dp.df.columns
    assert "INSPECTION_ID" in dp.df.columns


def test_quality_domain_exposes_sq4(monkeypatch):
    """Quality ships its first curated rule (SQ4 - Validity on
    ``EXPECTED_SHIP_DATE``). The list will grow as the Quality team
    finalizes additional rules."""
    monkeypatch.setitem(_session_state_dict(monkeypatch), "domain", DOMAIN_QUALITY)
    rules = get_available_custom_dqr_rules("SQS")
    by_id = {r.id: r for r in rules}
    assert "SQ4" in by_id
    sq4 = by_id["SQ4"]
    assert sq4.type == "Validity"
    assert sq4.blocking is False
    assert sq4.required_columns == {
        "Expected Ship Date": "EXPECTED_SHIP_DATE",
    }


def test_quality_domain_exposes_sq5(monkeypatch):
    """SQ5 (Business Rule) compares ``EXPECTED_SHIP_DATE`` to
    ``PO_REQUIRED_SHIP_DATE`` - the contractual deadline."""
    monkeypatch.setitem(_session_state_dict(monkeypatch), "domain", DOMAIN_QUALITY)
    rules = get_available_custom_dqr_rules("SQS")
    by_id = {r.id: r for r in rules}
    assert "SQ5" in by_id
    sq5 = by_id["SQ5"]
    assert sq5.type == "Business Rule"
    assert sq5.blocking is False
    assert sq5.required_columns == {
        "Expected Ship Date": "EXPECTED_SHIP_DATE",
        "PO Required Ship Date": "PO_REQUIRED_SHIP_DATE",
    }


def test_quality_domain_exposes_sq6(monkeypatch):
    """SQ6 (Validity) constrains ``INSPECTION_TYPE`` to the controlled
    vocabulary; case-sensitive per the Snowflake ``IN`` operator."""
    monkeypatch.setitem(_session_state_dict(monkeypatch), "domain", DOMAIN_QUALITY)
    rules = get_available_custom_dqr_rules("SQS")
    by_id = {r.id: r for r in rules}
    assert "SQ6" in by_id
    sq6 = by_id["SQ6"]
    assert sq6.type == "Validity"
    assert sq6.blocking is False
    assert sq6.required_columns == {
        "Inspection Type": "INSPECTION_TYPE",
    }


def test_quality_domain_exposes_sq7(monkeypatch):
    """SQ7 (Validity) constrains ``WORK_CRITICALITY`` to the four
    roman-numeral classification levels."""
    monkeypatch.setitem(_session_state_dict(monkeypatch), "domain", DOMAIN_QUALITY)
    rules = get_available_custom_dqr_rules("SQS")
    by_id = {r.id: r for r in rules}
    assert "SQ7" in by_id
    sq7 = by_id["SQ7"]
    assert sq7.type == "Validity"
    assert sq7.blocking is False
    assert sq7.required_columns == {
        "Work Criticality": "WORK_CRITICALITY",
    }


def test_quality_domain_exposes_sq8(monkeypatch):
    """SQ8 (Completeness) enforces a populated ``STATUS`` value -
    NULL or whitespace-only FAILs."""
    monkeypatch.setitem(_session_state_dict(monkeypatch), "domain", DOMAIN_QUALITY)
    rules = get_available_custom_dqr_rules("SQS")
    by_id = {r.id: r for r in rules}
    assert "SQ8" in by_id
    sq8 = by_id["SQ8"]
    assert sq8.type == "Completeness"
    assert sq8.blocking is False
    assert sq8.required_columns == {"Status": "STATUS"}


def test_quality_domain_exposes_sq9(monkeypatch):
    """SQ9 (Validity) constrains ``STATUS`` to the 11 canonical
    workflow statuses (case-sensitive Snowflake ``IN`` semantics)."""
    monkeypatch.setitem(_session_state_dict(monkeypatch), "domain", DOMAIN_QUALITY)
    rules = get_available_custom_dqr_rules("SQS")
    by_id = {r.id: r for r in rules}
    assert "SQ9" in by_id
    sq9 = by_id["SQ9"]
    assert sq9.type == "Validity"
    assert sq9.blocking is False
    assert sq9.required_columns == {"Status": "STATUS"}


def test_quality_domain_exposes_sq10(monkeypatch):
    """SQ10 (Business Rule) pins Completed inspections to a non-future
    ``EXPECTED_SHIP_DATE`` - a cross-column sequencing constraint."""
    monkeypatch.setitem(_session_state_dict(monkeypatch), "domain", DOMAIN_QUALITY)
    rules = get_available_custom_dqr_rules("SQS")
    by_id = {r.id: r for r in rules}
    assert "SQ10" in by_id
    sq10 = by_id["SQ10"]
    assert sq10.type == "Business Rule"
    assert sq10.blocking is False
    assert sq10.required_columns == {
        "Status": "STATUS",
        "Expected Ship Date": "EXPECTED_SHIP_DATE",
    }


# ---------------------------------------------------------------------------
# 4. Session state - pick / switch / clear
# ---------------------------------------------------------------------------

def test_set_domain_persists_to_session_state(fake_st_for_domains):
    from utils.session_state import set_domain
    set_domain(DOMAIN_QUALITY)
    assert fake_st_for_domains.session_state["domain"] == DOMAIN_QUALITY


def test_set_domain_rejects_unknown(fake_st_for_domains):
    from utils.session_state import set_domain
    with pytest.raises(KeyError):
        set_domain("not_a_real_domain")


def test_switching_domain_clears_workflow_state(fake_st_for_domains):
    """Picking a new domain must wipe in-flight Cost Estimate state so
    a leftover ``selected_systems=["ADR"]`` doesn't leak into the new
    Quality flow (where ADR is not a valid system)."""
    from utils.session_state import set_domain
    fake_st_for_domains.session_state["domain"] = DOMAIN_COST_ESTIMATE
    fake_st_for_domains.session_state["selected_systems"] = ["ADR"]
    fake_st_for_domains.session_state["data_products"] = {"ADR": object()}
    fake_st_for_domains.session_state["configs"] = {"ADR": object()}
    fake_st_for_domains.session_state["scorecards"] = {"ADR": object()}
    fake_st_for_domains.session_state["ml_lab_runs"] = [{"x": 1}]
    fake_st_for_domains.session_state["planview_filter"] = ["PV-001"]

    set_domain(DOMAIN_QUALITY)

    assert fake_st_for_domains.session_state["domain"] == DOMAIN_QUALITY
    assert fake_st_for_domains.session_state["selected_systems"] == []
    assert fake_st_for_domains.session_state["data_products"] == {}
    assert fake_st_for_domains.session_state["configs"] == {}
    assert fake_st_for_domains.session_state["scorecards"] == {}
    assert fake_st_for_domains.session_state["ml_lab_runs"] == []
    # planview_filter is a UI-side preference - it's *not* cleared on
    # domain switch.
    assert fake_st_for_domains.session_state["planview_filter"] == ["PV-001"]


def test_repicking_same_domain_is_a_noop(fake_st_for_domains):
    """Clicking the active domain card again must NOT wipe the user's
    in-progress workflow - the button is idempotent on purpose."""
    from utils.session_state import set_domain
    fake_st_for_domains.session_state["domain"] = DOMAIN_COST_ESTIMATE
    fake_st_for_domains.session_state["selected_systems"] = ["ADR"]

    set_domain(DOMAIN_COST_ESTIMATE)

    assert fake_st_for_domains.session_state["selected_systems"] == ["ADR"]


def test_get_active_domain_falls_back_outside_streamlit(monkeypatch):
    """Library callers (e.g. unit tests that import config.systems
    without a Streamlit session) must still get *some* domain back."""
    # Simulate no streamlit by raising on import
    import builtins
    real_import = builtins.__import__

    def raising_import(name, *a, **kw):
        if name == "streamlit":
            raise RuntimeError("not in streamlit")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", raising_import)
    assert get_active_domain_code() == DOMAIN_COST_ESTIMATE
    assert get_active_domain().code == DOMAIN_COST_ESTIMATE


def test_require_active_domain_raises_without_one(fake_st_for_domains):
    from utils.session_state import require_active_domain
    fake_st_for_domains.session_state["domain"] = None
    with pytest.raises(RuntimeError, match="No active domain"):
        require_active_domain()


def test_require_active_domain_returns_code(fake_st_for_domains):
    from utils.session_state import require_active_domain
    fake_st_for_domains.session_state["domain"] = DOMAIN_COST_ESTIMATE
    assert require_active_domain() == DOMAIN_COST_ESTIMATE


# ---------------------------------------------------------------------------
# 5. Extensibility - register a new domain at runtime
# ---------------------------------------------------------------------------

def test_register_new_domain_makes_it_visible_everywhere(monkeypatch):
    """A new domain registered at runtime must show up in every helper
    that surfaces the registry - lookups, the active-domain getter,
    and the system / custom-rule resolvers - without any other code
    change."""
    new = DomainDef(
        code="test_safety",
        name="Test - Safety",
        subtitle="STS",
        description="Smoke-test domain.",
        icon="🚧",
        accent="#f97316",
        tagline="Build scorecards for safety records.",
        page_title="DQ Scorecard - Test Safety",
        sidebar_brand_subtitle="STS",
        systems={
            "STS": SystemDef(
                code="STS",
                name="Safety Tracking System",
                description="Test system",
                tables=[
                    TableDef(
                        name="STS_INCIDENTS",
                        description="Incidents",
                        join_key="INCIDENT_ID",
                        is_primary=True,
                    )
                ],
            )
        },
        custom_rules={"STS": []},
    )
    try:
        register_domain(new)
        assert "test_safety" in list_domain_codes()
        # The system registry resolved through the active domain still
        # works.
        monkeypatch.setitem(_session_state_dict(monkeypatch), "domain",
                             "test_safety")
        assert list_system_codes() == ["STS"]
        assert get_active_domain().code == "test_safety"
        assert get_available_custom_dqr_rules("STS") == []
    finally:
        unregister_domain("test_safety")


def test_register_duplicate_domain_raises():
    with pytest.raises(ValueError, match="already registered"):
        register_domain(DOMAINS[DOMAIN_COST_ESTIMATE])


# ---------------------------------------------------------------------------
# DomainDef.system_codes property
# ---------------------------------------------------------------------------

def test_system_codes_property_preserves_insertion_order():
    """Step 1 renders system chips in the order ``system_codes`` returns;
    a dict that didn't preserve insertion order would shuffle the chips
    between Python versions."""
    cost = DOMAINS[DOMAIN_COST_ESTIMATE]
    expected = list(cost.systems.keys())
    assert cost.system_codes == expected


def test_system_codes_returns_a_fresh_list_each_call():
    """Mutating the returned list must not corrupt the underlying dict."""
    cost = DOMAINS[DOMAIN_COST_ESTIMATE]
    a = cost.system_codes
    a.append("FAKE")
    assert "FAKE" not in cost.system_codes


# ---------------------------------------------------------------------------
# get_active_snowflake_location
# ---------------------------------------------------------------------------

def test_get_active_snowflake_location_falls_back_to_settings(monkeypatch):
    """Cost Estimate leaves ``snowflake_database`` / ``snowflake_schema``
    empty; the helper must therefore fall back to ``SETTINGS``."""
    from config import settings as settings_mod
    from config.domains import get_active_snowflake_location

    state = _session_state_dict(monkeypatch)
    state["domain"] = DOMAIN_COST_ESTIMATE
    monkeypatch.setattr(
        settings_mod, "SETTINGS",
        settings_mod.Settings(
            data_source="mock",
            sf_database="FALLBACK_DB",
            sf_schema="FALLBACK_SCHEMA",
        ),
    )
    db, schema = get_active_snowflake_location()
    assert (db, schema) == ("FALLBACK_DB", "FALLBACK_SCHEMA")


def test_get_active_snowflake_location_uses_domain_override(monkeypatch):
    """Quality sets explicit ``snowflake_database`` / ``snowflake_schema`` on
    its DomainDef; those win over ``SETTINGS`` so the user doesn't have to
    edit ``.env`` between Cost Estimate and Quality runs."""
    from config import settings as settings_mod
    from config.domains import DOMAIN_QUALITY, get_active_snowflake_location

    state = _session_state_dict(monkeypatch)
    state["domain"] = DOMAIN_QUALITY
    monkeypatch.setattr(
        settings_mod, "SETTINGS",
        settings_mod.Settings(
            data_source="mock",
            sf_database="SHOULD_BE_IGNORED",
            sf_schema="SHOULD_BE_IGNORED",
        ),
    )
    db, schema = get_active_snowflake_location()
    # Quality is set to INGESTION_DB.GP_QUALITY in the DomainDef registry.
    assert db == "INGESTION_DB"
    assert schema == "GP_QUALITY"


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

class _FakeSessionState(dict):
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(item) from e

    def __setattr__(self, key, value):
        self[key] = value


class _FakeStreamlit:
    def __init__(self):
        self.session_state = _FakeSessionState()


@pytest.fixture
def fake_st_for_domains(monkeypatch):
    """Inject a fake Streamlit into both ``utils.session`` sub-modules and
    ``config.domains`` so the test exercises the real switching logic
    against a controllable session-state dict.

    M7 partitioned ``utils/session_state.py`` into a re-export shim plus
    :mod:`utils.session.state` / ``.navigation`` / ``.sidebar`` - each of
    them imports ``streamlit`` at top level, so we patch all three.
    """
    fake = _FakeStreamlit()
    from utils.session import navigation as nav_mod
    from utils.session import sidebar as sidebar_mod
    from utils.session import state as state_mod
    monkeypatch.setattr(state_mod, "st", fake)
    monkeypatch.setattr(nav_mod, "st", fake)
    monkeypatch.setattr(sidebar_mod, "st", fake)
    # config.domains imports streamlit lazily inside ``get_active_domain_code``,
    # so we patch ``sys.modules`` to make ``import streamlit`` return fake.
    import sys
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    return fake


def _session_state_dict(monkeypatch):
    """Return a dict that ``config.domains.get_active_domain_code`` will
    read through. Setting the ``domain`` key on it has the same effect
    as the user picking a domain in Step 0."""
    fake = _FakeStreamlit()
    import sys
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    return fake.session_state
