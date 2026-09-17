"""Tests for the DQR source constants and the custom-rule catalog wiring.

Covers user-spec scenarios 6 (EPT → E1), 7 (ADR → DQ-ADR-2), 8 (ACCE → empty).
"""
from __future__ import annotations

from config.custom_dqr_catalog import (
    CUSTOM_DQR_RULES,
    CustomRuleDef,
    get_available_custom_dqr_rules,
)
from config.dqr_sources import (
    ALL_SOURCES,
    SOURCE_CUSTOM,
    SOURCE_LABELS,
    SOURCE_STANDARD,
)


def test_source_constants_are_distinct():
    assert SOURCE_STANDARD != SOURCE_CUSTOM
    assert SOURCE_STANDARD in ALL_SOURCES
    assert SOURCE_CUSTOM in ALL_SOURCES


def test_source_labels_cover_all_sources():
    for src in ALL_SOURCES:
        assert src in SOURCE_LABELS
        assert SOURCE_LABELS[src]


def test_ept_catalog_includes_e1_e2_e3_e4_e5_e6_e7():
    rules = get_available_custom_dqr_rules("EPT")
    assert [r.id for r in rules] == ["E1", "E2", "E3", "E4", "E5", "E6", "E7"]


def test_adr_catalog_active_and_inactive_rules():
    """ADR exposes DQ-ADR-1 (Completeness - ISO COR + SAB lookup), DQ-ADR-4
    (Completeness & Validity), DQ-ADR-5 / DQ-ADR-6 (Consistency - design
    detail / construction hours vs. quantity) and DQ-ADR-9 (Validity -
    MFC vs EMMA) as *active* rules; DQ-ADR-3 (Statistical Outlier -
    WBC-to-ISO mapping aggregation) stays in the catalog as *inactive*.
    DQ-ADR-2 / DQ-ADR-7 / DQ-ADR-8 are retired (see the dedicated test)."""
    rules = get_available_custom_dqr_rules("ADR")
    assert [r.id for r in rules] == [
        "DQ-ADR-1", "DQ-ADR-4", "DQ-ADR-5", "DQ-ADR-6", "DQ-ADR-9"
    ]
    assert all(r.active for r in rules)
    rules = get_available_custom_dqr_rules("ADR", include_inactive=True)
    assert [r.id for r in rules] == [
        "DQ-ADR-1", "DQ-ADR-3", "DQ-ADR-4", "DQ-ADR-5", "DQ-ADR-6", "DQ-ADR-9"
    ]
    by_id = {r.id: r for r in rules}
    assert by_id["DQ-ADR-3"].active is False

    a1 = by_id["DQ-ADR-1"]
    assert a1.type == "Completeness"
    assert a1.required_columns == {
        "Project Key": "PLANVIEW_ID",
        "Complete WBC": "COMPLETE_WBC",
    }
    assert a1.reference == {
        "reference_dataset": "ACCE_COA_MASTER",
        "source_column": "COMPLETE_WBC",
        "reference_column": "ICARUS_COA",
        "lookup_column": "ISO_COR / SAB",
    }

    a3 = by_id["DQ-ADR-3"]
    assert a3.type == "Statistical Outlier"
    assert a3.required_columns == {
        "Project Key": "PLANVIEW_ID",
        "Complete WBC": "COMPLETE_WBC",
        "Total Hours": "COST_TOTAL_HOURS",
        "Total Cost": "COST_TOTAL_COST",
    }
    assert a3.reference == {
        "reference_dataset": "ACCE_COA_MASTER",
        "source_column": "COMPLETE_WBC",
        "reference_column": "ICARUS_COA",
        "lookup_column": "ISO_COR / SAB",
    }

    a4 = by_id["DQ-ADR-4"]
    assert a4.type == "Completeness & Validity"
    assert a4.required_columns == {
        "Project Key": "PLANVIEW_ID",
        "Item Type": "ITEM_TYPE",
        "Item Description": "ITEM_DESCRIPTION",
        "Quantity": "QTY_QUANTITY",
        "Quantity UOM": "QTY_UOM",
    }
    assert a4.reference is None

    a5 = by_id["DQ-ADR-5"]
    assert a5.type == "Consistency"
    assert a5.required_columns == {
        "Quantity": "QTY_QUANTITY",
        "Item Type": "ITEM_TYPE",
        "Key Parameter Names": "DESIGN_KEY_PARAMETER_NAMES",
    }
    assert a5.reference is None

    a6 = by_id["DQ-ADR-6"]
    assert a6.type == "Consistency"
    assert a6.required_columns == {
        "Quantity": "QTY_QUANTITY",
        "Construction Hours": "COST_TOTAL_HOURS",
        "Construction Hours (DB)": "COST_DB_TOTAL_HOURS",
    }
    assert a6.reference is None



def test_adr_retired_rules_keep_their_definitions_outside_the_catalog():
    """DQ-ADR-2 / 7 / 8 were retired on 2026-09-17: gone from every
    catalog view, but their definitions (and check functions) stay in
    ``ADR_RETIRED_RULES`` so historical runs can still be read."""
    from config.custom_dqr._adr_catalog import ADR_RETIRED_RULES
    from config.custom_dqr_catalog import RETIRED_CUSTOM_DQR_RULES
    from src.custom_dqr_engine import (
        ADR_A2_REQUIRED_COLUMNS, ADR_A7_REQUIRED_COLUMNS, ADR_A8_REQUIRED_COLUMNS,
    )
    assert RETIRED_CUSTOM_DQR_RULES["ADR"] is ADR_RETIRED_RULES
    retired = {r.id: r for r in ADR_RETIRED_RULES}
    assert list(retired) == ["DQ-ADR-2", "DQ-ADR-7", "DQ-ADR-8"]
    assert retired["DQ-ADR-2"].required_columns == ADR_A2_REQUIRED_COLUMNS
    assert retired["DQ-ADR-2"].reference["reference_dataset"] == "VWS_GP_STANDARD_SHARE"
    assert retired["DQ-ADR-7"].required_columns == ADR_A7_REQUIRED_COLUMNS
    assert retired["DQ-ADR-8"].required_columns == ADR_A8_REQUIRED_COLUMNS
    listed = {r.id for r in get_available_custom_dqr_rules("ADR", include_inactive=True)}
    assert not listed & set(retired)


def test_acce_exposes_ac1():
    """ACCE exposes AC1 - blocking Completeness rule that joins
    ``COA`` directly to ``ACCE_COA_MASTER.ICARUS_COA`` (no WBC split,
    unlike ADR DQ-ADR-1)."""
    rules = get_available_custom_dqr_rules("ACCE")
    by_id = {r.id: r for r in rules}
    assert "AC1" in by_id
    ac1 = by_id["AC1"]
    assert ac1.type == "Completeness"
    assert ac1.required_columns == {
        "Project Key": "PLANVIEW_ID",
        "Code of Account": "COA",
    }
    assert ac1.reference is not None
    assert ac1.reference["reference_dataset"] == "ACCE_COA_MASTER"
    assert ac1.reference["source_column"] == "COA"
    assert ac1.reference["reference_column"] == "ICARUS_COA"


def test_unknown_data_product_returns_empty_list():
    assert get_available_custom_dqr_rules("FAKE_SYSTEM") == []


def test_get_available_returns_a_copy():
    """Mutating the returned list must not affect the catalog."""
    first = get_available_custom_dqr_rules("EPT")
    first.clear()
    second = get_available_custom_dqr_rules("EPT")
    assert len(second) >= 1


def test_custom_rule_def_default_check_returns_all_true():
    """The default no-op ``check`` keeps the catalog usable when a rule is
    listed without an implementation yet."""
    import pandas as pd

    rule = CustomRuleDef(
        id="X1",
        name="placeholder",
        type="Completeness",
        description="",
        notes="",
    )
    df = pd.DataFrame({"a": [1, 2, 3]})
    assert rule.check(df).all()


def test_catalog_keys_are_known_data_products():
    assert set(CUSTOM_DQR_RULES.keys()) >= {"EPT", "ADR", "ACCE"}


def test_ept_e4_blocking_flag_is_false():
    rule = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E4")


def test_ept_e7_reference_metadata_is_complete():
    rule = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E7")
    assert rule.reference == {
        "reference_dataset": "VWS_GP_STANDARD_SHARE",
        "source_column": "PLANVIEW_ID",
        "reference_column": "PROJECT_ID",
    }


def test_custom_rule_def_reference_defaults_to_none():
    """Rules that don't declare a reference dataset (e.g. completeness rules)
    leave the ``reference`` field at None so the UI can skip the section."""
    rule = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E1")
    assert rule.reference is None
    rule_e4 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E4")
    assert rule_e4.reference is None


def test_ept_e3_catalog_metadata():
    """E3 is a statistical-outlier rule; required columns cover
    the WBC/ISO key and the materiality drivers (hours + cost)."""
    rule = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E3")
    assert rule.type == "Statistical Outlier"
    assert rule.reference is None
    assert rule.required_columns == {
        "WBC Level 5": "WBC_LEVEL_5",
        "COR": "CODE_OF_RESOURCE",
        "SAB": "STANDARD_ACTIVITY_BREAKDOWN",
        "Total Hours": "TOTAL_HOURS",
        "Total Cost (USD)": "TOTAL_COST_USD",
    }


def test_ept_e3_exposes_project_scope_option():
    """E3's option block is what Step 4.2 renders as the project-scope
    toggle, and what feeds CustomDQRAssignment.params at runtime."""
    from src.custom_dqr_engine import (
        EPT_E3_DETECT_UNIFORM_MAPPING_PARAM,
        EPT_E3_PROJECT_SCOPED_PARAM,
    )
    rule = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E3")
    by_key = {opt.key: opt for opt in rule.options}
    assert set(by_key) == {
        EPT_E3_PROJECT_SCOPED_PARAM,
        EPT_E3_DETECT_UNIFORM_MAPPING_PARAM,
    }
    scope_opt = by_key[EPT_E3_PROJECT_SCOPED_PARAM]
    assert scope_opt.default is False
    assert scope_opt.required_columns_when_enabled == {
        "Project Key": "PLANVIEW_ID"
    }
    # The long-form description is what the UI renders inside the
    # "How this option works" expander; sanity-check it explains both modes.
    assert "global" in scope_opt.description.lower()
    assert "project" in scope_opt.description.lower()
    uniform_opt = by_key[EPT_E3_DETECT_UNIFORM_MAPPING_PARAM]
    # Uniform-1:1 detection is opt-in and contributes no extra required cols.
    assert uniform_opt.default is False
    assert uniform_opt.required_columns_when_enabled == {}
    assert "1:1" in uniform_opt.description


def test_effective_required_columns_adds_planview_when_e3_project_scoped():
    """``effective_required_columns`` folds option-contributed extras into
    the static map when the corresponding option is enabled."""
    from config.custom_dqr_catalog import effective_required_columns
    from src.custom_dqr_engine import EPT_E3_PROJECT_SCOPED_PARAM

    rule = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E3")
    base = effective_required_columns(rule, params={})
    assert "PLANVIEW_ID" not in base.values()

    extended = effective_required_columns(
        rule, params={EPT_E3_PROJECT_SCOPED_PARAM: True}
    )
    assert "PLANVIEW_ID" in extended.values()
    # Static columns are still present.
    for col in rule.required_columns.values():
        assert col in extended.values()


def test_effective_required_columns_for_rule_without_options_is_identity():
    """Rules that don't declare options get their static required_columns
    back unchanged regardless of params content."""
    from config.custom_dqr_catalog import effective_required_columns
    rule = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E1")
    assert effective_required_columns(rule, params={"any": True}) == rule.required_columns


def test_sqs_catalog_includes_dq_inspection_12(monkeypatch):
    """SQS (Quality domain) exposes dq-inspection-12 with the documented
    metadata: a Completeness rule on ``TOTAL_CONSUMED_HOURS``
    scoped to Completed inspections, no reference dataset, no options."""
    from config.domains import DOMAIN_QUALITY

    monkeypatch.setattr(
        "config.domains.get_active_domain_code",
        lambda: DOMAIN_QUALITY,
    )
    rules = get_available_custom_dqr_rules("SQS")
    by_id = {r.id: r for r in rules}
    assert "dq-inspection-12" in by_id
    rule = by_id["dq-inspection-12"]
    assert rule.name == "Mandatory on Completion"
    assert rule.type == "Completeness"
    assert rule.reference is None
    assert rule.required_columns == {
        "Status": "STATUS",
        "Total Consumed Hours": "TOTAL_CONSUMED_HOURS",
    }
    assert rule.options == []
    assert rule.select_options == []


def test_sqs_catalog_includes_dq_inspection_13(monkeypatch):
    """SQS exposes dq-inspection-13 - unconditional Completeness on
    ``ALLOTED_HOURS`` with no reference dataset and no options."""
    from config.domains import DOMAIN_QUALITY

    monkeypatch.setattr(
        "config.domains.get_active_domain_code",
        lambda: DOMAIN_QUALITY,
    )
    rules = get_available_custom_dqr_rules("SQS")
    by_id = {r.id: r for r in rules}
    assert "dq-inspection-13" in by_id
    rule = by_id["dq-inspection-13"]
    assert rule.name == "Mandatory Approved Hours"
    assert rule.type == "Completeness"
    assert rule.reference is None
    assert rule.required_columns == {"Alloted Hours": "ALLOTED_HOURS"}
    assert rule.options == []
    assert rule.select_options == []


def test_sqs_catalog_orders_dq_inspection_12_then_13(monkeypatch):
    """SQS catalog ordering pins Step 4.2 card placement:
    dq-inspection-12 → dq-inspection-13."""
    from config.domains import DOMAIN_QUALITY

    monkeypatch.setattr(
        "config.domains.get_active_domain_code",
        lambda: DOMAIN_QUALITY,
    )
    rule_ids = [r.id for r in get_available_custom_dqr_rules("SQS")]
    assert rule_ids == ["dq-inspection-12", "dq-inspection-13"]
