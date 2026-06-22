"""Contract tests for the dataclasses in src/models.py.

These pin the public-shape behaviour of the models the rest of the app
relies on: default factories don't share state across instances, derived
properties (rule_id, row_count, weights_sum) match the field values, and
the backward-compat shims on DataProductConfig
(effective_dqr_sources / effective_source_weights) keep working when the
new source-selection fields are absent.
"""
from __future__ import annotations

import pandas as pd

from src.models import (
    ColumnProfile,
    CustomDQRAssignment,
    DataProduct,
    DataProductConfig,
    DQRAssignment,
    ScorecardResult,
)

# ---------------------------------------------------------------------------
# ColumnProfile
# ---------------------------------------------------------------------------

def test_column_profile_defaults_are_independent_per_instance():
    """The mutable default (``sample_values``) must use ``field(default_factory=list)``
    so two instances don't share the same list."""
    a = ColumnProfile(
        name="A", dtype="int64", column_type_group="numeric",
        total_rows=10, null_count=0, null_pct=0.0,
        distinct_count=10, duplicate_count=0,
    )
    b = ColumnProfile(
        name="B", dtype="int64", column_type_group="numeric",
        total_rows=10, null_count=0, null_pct=0.0,
        distinct_count=10, duplicate_count=0,
    )
    a.sample_values.append(1)
    assert b.sample_values == []


# ---------------------------------------------------------------------------
# DataProduct
# ---------------------------------------------------------------------------

def test_data_product_row_and_column_counts_match_dataframe():
    df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6], "z": [7, 8, 9]})
    dp = DataProduct(system_code="EPT", name="ept", df=df, source_tables=["EPT"])
    assert dp.row_count == 3
    assert dp.column_count == 3


def test_data_product_handles_empty_dataframe():
    dp = DataProduct(
        system_code="EPT", name="ept",
        df=pd.DataFrame(), source_tables=[],
    )
    assert dp.row_count == 0
    assert dp.column_count == 0
    assert dp.profiles == {}


# ---------------------------------------------------------------------------
# DQRAssignment
# ---------------------------------------------------------------------------

def test_dqr_assignment_rule_id_combines_column_and_dimension():
    a = DQRAssignment(cde_column="AMOUNT", dimension="Validity", weight=10.0)
    assert a.rule_id == "AMOUNT::Validity"


def test_dqr_assignment_params_default_is_empty_dict_per_instance():
    a = DQRAssignment(cde_column="X", dimension="Completeness")
    b = DQRAssignment(cde_column="Y", dimension="Completeness")
    a.params["regex"] = r"\d+"
    assert b.params == {}


# ---------------------------------------------------------------------------
# CustomDQRAssignment
# ---------------------------------------------------------------------------

def test_custom_dqr_assignment_defaults():
    c = CustomDQRAssignment(rule_id="E1")
    assert c.weight == 0.0
    assert c.params == {}


def test_custom_dqr_assignment_params_not_shared_between_instances():
    a = CustomDQRAssignment(rule_id="E1")
    b = CustomDQRAssignment(rule_id="E2")
    a.params["threshold"] = 0.9
    assert b.params == {}


# ---------------------------------------------------------------------------
# DataProductConfig
# ---------------------------------------------------------------------------

def test_data_product_config_get_assignments_for_filters_by_column():
    cfg = DataProductConfig(
        system_code="EPT",
        assignments=[
            DQRAssignment(cde_column="A", dimension="Validity", weight=10.0),
            DQRAssignment(cde_column="A", dimension="Accuracy", weight=20.0),
            DQRAssignment(cde_column="B", dimension="Validity", weight=30.0),
        ],
    )
    a_only = cfg.get_assignments_for("A")
    assert [x.dimension for x in a_only] == ["Validity", "Accuracy"]
    assert cfg.get_assignments_for("MISSING") == []


def test_data_product_config_weights_sum():
    cfg = DataProductConfig(
        system_code="EPT",
        assignments=[
            DQRAssignment(cde_column="A", dimension="Validity", weight=30.0),
            DQRAssignment(cde_column="B", dimension="Accuracy", weight=70.0),
        ],
    )
    assert cfg.weights_sum() == 100.0


def test_data_product_config_weights_sum_empty_is_zero():
    cfg = DataProductConfig(system_code="EPT")
    assert cfg.weights_sum() == 0.0


def test_effective_dqr_sources_falls_back_to_standard_when_empty():
    """Configs created before the source-selection feature have no
    ``dqr_sources`` field; the shim must still flow them through as
    ``["standard"]`` so Steps 5/6 keep working."""
    cfg = DataProductConfig(system_code="EPT")
    assert cfg.effective_dqr_sources() == ["standard"]


def test_effective_dqr_sources_returns_copy_not_alias():
    """Mutating the returned list must not corrupt the config."""
    cfg = DataProductConfig(system_code="EPT", dqr_sources=["standard", "custom"])
    out = cfg.effective_dqr_sources()
    out.append("synthetic")
    assert cfg.dqr_sources == ["standard", "custom"]


def test_effective_source_weights_single_source_defaults_to_100():
    cfg = DataProductConfig(system_code="EPT", dqr_sources=["standard"])
    assert cfg.effective_source_weights() == {"standard": 100.0}


def test_effective_source_weights_splits_evenly_across_multiple_sources():
    cfg = DataProductConfig(
        system_code="EPT", dqr_sources=["standard", "custom"],
    )
    assert cfg.effective_source_weights() == {"standard": 50.0, "custom": 50.0}


def test_effective_source_weights_passes_explicit_weights_through():
    cfg = DataProductConfig(
        system_code="EPT",
        dqr_sources=["standard", "custom"],
        source_weights={"standard": 70.0, "custom": 30.0},
    )
    assert cfg.effective_source_weights() == {"standard": 70.0, "custom": 30.0}


def test_effective_source_weights_returns_copy_not_alias():
    cfg = DataProductConfig(
        system_code="EPT",
        dqr_sources=["standard"],
        source_weights={"standard": 100.0},
    )
    out = cfg.effective_source_weights()
    out["custom"] = 0.0
    assert cfg.source_weights == {"standard": 100.0}


# ---------------------------------------------------------------------------
# ScorecardResult
# ---------------------------------------------------------------------------

def test_scorecard_result_default_optional_fields():
    """The not_evaluated / not_computed maps are critical for Step 6's
    "Not evaluated" warning - their defaults must be independent dicts
    so one scorecard's failures don't leak into another."""
    s1 = ScorecardResult(
        system_code="EPT",
        overall_score=85.0,
        row_scores=pd.Series([85.0]),
        rule_pass_rates={},
        cde_scores={},
        dimension_scores={},
        total_rows=1,
        rows_green=1, rows_yellow=0, rows_red=0,
        threshold_green=80.0, threshold_yellow=60.0,
    )
    s2 = ScorecardResult(
        system_code="ADR",
        overall_score=70.0,
        row_scores=pd.Series([70.0]),
        rule_pass_rates={},
        cde_scores={},
        dimension_scores={},
        total_rows=1,
        rows_green=0, rows_yellow=1, rows_red=0,
        threshold_green=80.0, threshold_yellow=60.0,
    )
    s1.not_evaluated_custom_rules["E7"] = "missing reference"
    s1.not_computed_standard_rules["AMOUNT::Validity"] = "dtype mismatch"
    s1.custom_rule_pass_rates["E1"] = 0.5
    s1.source_weights["standard"] = 100.0

    assert s2.not_evaluated_custom_rules == {}
    assert s2.not_computed_standard_rules == {}
    assert s2.custom_rule_pass_rates == {}
    assert s2.source_weights == {}
    assert s2.standard_score is None
    assert s2.custom_score is None
