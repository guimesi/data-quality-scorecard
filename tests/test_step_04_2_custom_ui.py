"""Unit tests for the Step 4.2 custom-rule UI module.

Targets the helpers that the AppTest-based scenario tests don't exercise:
- the rule-card branch where a previously-saved selection's weight is
  preserved across re-renders
- the empty-selections write path (no rule selected)
- the ``_nav`` Back / disabled-Next branches
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from tests.test_ui_units import _make_fake_st


def test_dp_block_preserves_existing_weight_for_selected_rule():
    """When a rule card is checked AND was previously selected with a weight,
    that weight survives the re-render (covers the prev-weight branch)."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=42.0)],
    )
    fake_st = _make_fake_st(
        checkboxes={"custom_EPT_E1_enabled": True},
    )
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_dp_block("EPT", cfg)

    assert len(cfg.custom_assignments) == 1
    assert cfg.custom_assignments[0].rule_id == "E1"
    assert cfg.custom_assignments[0].weight == 42.0


def test_dp_block_drops_unchecked_rules():
    """A rule card unchecked in the UI must be removed from
    ``custom_assignments``."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=42.0)],
    )
    fake_st = _make_fake_st(
        checkboxes={"custom_EPT_E1_enabled": False},
    )
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_dp_block("EPT", cfg)

    assert cfg.custom_assignments == []


def test_dp_block_empty_state_clears_assignments():
    """For a DP with no catalog rules, ``custom_assignments`` is reset to
    an empty list (covers lines 75-76 in the empty-state path)."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="ADR",
        custom_assignments=[CustomDQRAssignment(rule_id="X1", weight=10.0)],
    )
    fake_st = _make_fake_st()
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_dp_block("ADR", cfg)

    assert cfg.custom_assignments == []


def test_nav_back_click_calls_prev_step():
    import ui.step_04_2_custom_dqr as s4_2

    fake_st = _make_fake_st()
    call_results = iter([True, False, False])
    fake_st.button = MagicMock(side_effect=lambda *a, **kw: next(call_results))
    # ``_nav`` now delegates to ``render_nav_footer`` which has its own
    # ``st`` import; patch both so the helper sees the fake widgets too.
    with patch.object(s4_2, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_04_2_custom_dqr.prev_step") as mock_prev:
        s4_2._nav(show_next=True)
    mock_prev.assert_called_once()


def test_nav_disabled_next_renders_without_action():
    import ui.step_04_2_custom_dqr as s4_2

    fake_st = _make_fake_st()
    fake_st.button = MagicMock(return_value=False)
    with patch.object(s4_2, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_04_2_custom_dqr.next_step") as mock_next, \
         patch("ui.step_04_2_custom_dqr.prev_step") as mock_prev:
        s4_2._nav(show_next=False)
    mock_next.assert_not_called()
    mock_prev.assert_not_called()


def test_nav_next_click_calls_next_step():
    import ui.step_04_2_custom_dqr as s4_2

    fake_st = _make_fake_st()
    # Back=False, Restart=False, Next=True (3-button nav row).
    call_results = iter([False, False, True])
    fake_st.button = MagicMock(side_effect=lambda *a, **kw: next(call_results))
    with patch.object(s4_2, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_04_2_custom_dqr.next_step") as mock_next:
        s4_2._nav(show_next=True)
    mock_next.assert_called_once()


def test_nav_restart_click_calls_restart_app():
    """Restart click on Step 4.2 invokes restart_app (the shared workflow
    reset). We patch the imported alias rather than the underlying helper to
    keep the unit isolated from the heavier reset side effects."""
    import ui.step_04_2_custom_dqr as s4_2

    fake_st = _make_fake_st()
    # Back=False, Restart=True, Next=False
    call_results = iter([False, True, False])
    fake_st.button = MagicMock(side_effect=lambda *a, **kw: next(call_results))
    with patch.object(s4_2, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_04_2_custom_dqr.restart_app") as mock_restart:
        s4_2._nav(show_next=True)
    mock_restart.assert_called_once()


# ---------------------------------------------------------------------------
# Configuration-driven rendering: E4 + E7 selection state and rule_card
# ---------------------------------------------------------------------------

def test_dp_block_user_can_select_e4():
    """Scenario 8: ticking E4 produces a CustomDQRAssignment with rule_id="E4"."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg = DataProductConfig(system_code="EPT", custom_assignments=[])
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E4_enabled": True})
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_dp_block("EPT", cfg)
    assert [a.rule_id for a in cfg.custom_assignments] == ["E4"]


def test_dp_block_user_can_unselect_e4():
    """Scenario 8: unticking E4 removes it from custom_assignments."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[CustomDQRAssignment(rule_id="E4", weight=100)],
    )
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E4_enabled": False})
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_dp_block("EPT", cfg)
    assert cfg.custom_assignments == []


def test_dp_block_user_can_select_e7():
    """Scenario 9: ticking E7 produces a CustomDQRAssignment with rule_id="E7"."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg = DataProductConfig(system_code="EPT", custom_assignments=[])
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E7_enabled": True})
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_dp_block("EPT", cfg)
    assert [a.rule_id for a in cfg.custom_assignments] == ["E7"]


def test_dp_block_user_can_unselect_e7():
    """Scenario 9: unticking E7 removes it from custom_assignments."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[CustomDQRAssignment(rule_id="E7", weight=100)],
    )
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E7_enabled": False})
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_dp_block("EPT", cfg)
    assert cfg.custom_assignments == []


def test_render_rule_card_e7_displays_reference_block():
    """Scenario 10: E7's rule card markdown includes the reference dataset
    metadata (source_column, reference_dataset, reference_column)."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules

    e7 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E7")
    fake_st = _make_fake_st()
    captured_markdown = []

    def capture_markdown(text, *args, **kwargs):
        captured_markdown.append(text)

    fake_st.markdown = MagicMock(side_effect=capture_markdown)
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_rule_card("EPT", e7, selected=False)

    body = "\n\n".join(captured_markdown)
    assert "PLANVIEW_ID" in body                # source column in EPT
    assert "VWS_GP_STANDARD_SHARE" in body      # reference dataset name
    assert "PROJECT_ID" in body                 # reference column
    assert "Reference dataset" in body or "Reference column" in body


# ---------------------------------------------------------------------------
# CDE-coverage validation (new)
# ---------------------------------------------------------------------------


def test_missing_required_cdes_returns_empty_when_all_selected():
    """Required physical columns all present in cfg.cdes → no gaps."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules

    e1 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E1")
    missing = s4_2._missing_required_cdes(
        e1, ["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN", "EXTRA_CDE"]
    )
    assert missing == []


def test_missing_required_cdes_lists_only_unselected_columns():
    """Returns the physical column names not present in cfg.cdes, preserving
    the catalog's declared order."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules

    e1 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E1")
    missing = s4_2._missing_required_cdes(e1, ["CODE_OF_RESOURCE"])
    assert missing == ["STANDARD_ACTIVITY_BREAKDOWN"]


def test_missing_required_cdes_handles_rule_with_no_required_columns():
    """A rule that declares no required columns is always satisfied."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import CustomRuleDef

    rule = CustomRuleDef(
        id="X1", name="No deps", type="Completeness",
        description="", notes="",
    )
    assert s4_2._missing_required_cdes(rule, []) == []
    assert s4_2._missing_required_cdes(rule, ["ANY"]) == []


def test_dp_block_returns_invalid_when_required_cde_missing():
    """Selecting E1 without any CDEs picked → block flag + gap reported."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg = DataProductConfig(system_code="EPT", cdes=[], custom_assignments=[])
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E1_enabled": True})
    with patch.object(s4_2, "st", fake_st):
        valid, gaps = s4_2._render_dp_block("EPT", cfg)
    assert valid is False
    rule_ids = [g[0] for g in gaps]
    assert "E1" in rule_ids
    e1_missing = dict(gaps)["E1"]
    assert "CODE_OF_RESOURCE" in e1_missing
    assert "STANDARD_ACTIVITY_BREAKDOWN" in e1_missing


def test_dp_block_valid_when_all_required_cdes_present():
    """Selecting E1 with both required CDEs picked → no gaps, valid."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        custom_assignments=[],
    )
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E1_enabled": True})
    with patch.object(s4_2, "st", fake_st):
        valid, gaps = s4_2._render_dp_block("EPT", cfg)
    assert valid is True
    assert gaps == []


def test_dp_block_validates_each_selected_rule_independently():
    """Multiple rules selected: E1 covered, E4 not → block, only E4 in gaps."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        cdes=["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        custom_assignments=[],
    )
    fake_st = _make_fake_st(checkboxes={
        "custom_EPT_E1_enabled": True,
        "custom_EPT_E4_enabled": True,  # WBC_LEVEL_1 is missing
    })
    with patch.object(s4_2, "st", fake_st):
        valid, gaps = s4_2._render_dp_block("EPT", cfg)
    assert valid is False
    rule_ids = [g[0] for g in gaps]
    assert rule_ids == ["E4"]
    assert dict(gaps)["E4"] == ["WBC_LEVEL_1"]


def test_dp_block_unselected_rule_does_not_block_even_if_cdes_missing():
    """A Custom DQR the user hasn't ticked never contributes a gap, even if
    its required columns aren't selected as CDEs."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg = DataProductConfig(system_code="EPT", cdes=[], custom_assignments=[])
    fake_st = _make_fake_st()  # all checkboxes default to False
    with patch.object(s4_2, "st", fake_st):
        valid, gaps = s4_2._render_dp_block("EPT", cfg)
    assert valid is True
    assert gaps == []


def test_dp_block_validation_updates_dynamically_when_cde_added():
    """Render once with E1 selected and no CDEs (invalid), then a re-render
    after the user adds the required CDEs flips the validation to valid -
    confirming the UI reacts to ``cfg.cdes`` mutations across reruns."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg = DataProductConfig(system_code="EPT", cdes=[], custom_assignments=[])
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E1_enabled": True})

    with patch.object(s4_2, "st", fake_st):
        valid_before, gaps_before = s4_2._render_dp_block("EPT", cfg)
    assert valid_before is False
    assert gaps_before and gaps_before[0][0] == "E1"

    # Simulate the user going back to Step 3 and adding the required CDEs.
    cfg.cdes = ["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"]
    with patch.object(s4_2, "st", fake_st):
        valid_after, gaps_after = s4_2._render_dp_block("EPT", cfg)
    assert valid_after is True
    assert gaps_after == []


def test_dp_block_no_rules_configured_is_valid():
    """A data product with no custom rules in the catalog is trivially valid
    - there's nothing the user could have selected, nothing to block on."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg = DataProductConfig(system_code="ADR", custom_assignments=[])
    fake_st = _make_fake_st()
    with patch.object(s4_2, "st", fake_st):
        valid, gaps = s4_2._render_dp_block("ADR", cfg)
    assert valid is True
    assert gaps == []


def test_render_rule_card_emits_warning_when_required_cde_missing():
    """Ticked card with missing required CDEs surfaces an st.warning that
    names the missing physical column(s)."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules

    e1 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E1")
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E1_enabled": True})
    fake_st.warning = MagicMock()
    fake_st.success = MagicMock()
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_rule_card("EPT", e1, selected=True, selected_cdes=[])

    fake_st.success.assert_not_called()
    assert fake_st.warning.call_count == 1
    msg = fake_st.warning.call_args.args[0]
    assert "Missing required CDEs" in msg
    assert "CODE_OF_RESOURCE" in msg
    assert "STANDARD_ACTIVITY_BREAKDOWN" in msg


def test_render_rule_card_emits_success_when_all_required_cdes_present():
    """Ticked card with full CDE coverage surfaces the green success badge."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules

    e1 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E1")
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E1_enabled": True})
    fake_st.warning = MagicMock()
    fake_st.success = MagicMock()
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_rule_card(
            "EPT", e1, selected=True,
            selected_cdes=["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        )

    fake_st.warning.assert_not_called()
    assert fake_st.success.call_count == 1
    assert "All required CDEs selected" in fake_st.success.call_args.args[0]


def test_render_rule_card_no_validation_badge_when_unticked():
    """An unticked card never surfaces the CDE-coverage badge - validation
    is scoped to the user's actual selections."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules

    e1 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E1")
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E1_enabled": False})
    fake_st.warning = MagicMock()
    fake_st.success = MagicMock()
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_rule_card("EPT", e1, selected=False, selected_cdes=[])

    fake_st.warning.assert_not_called()
    fake_st.success.assert_not_called()


# ---------------------------------------------------------------------------
# Per-rule options (E3 project-scope toggle)
# ---------------------------------------------------------------------------

def test_render_rule_card_returns_default_params_when_no_options_selected():
    """A card for a rule without options returns an empty params dict so
    legacy assignments (e.g. E1) keep flowing through unchanged."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules

    e1 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E1")
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E1_enabled": True})
    with patch.object(s4_2, "st", fake_st):
        selected, params = s4_2._render_rule_card(
            "EPT", e1, selected=True,
            selected_cdes=["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        )
    assert selected is True
    assert params == {}


def test_render_rule_card_e3_renders_project_scope_toggle_off_by_default():
    """E3 selected with no prior params → the project-scope toggle is
    rendered with its default (off), and params reflect that plus the
    recommended threshold (P90)."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules
    from src.custom_dqr_engine import (
        EPT_E3_PERCENTILE,
        EPT_E3_PROJECT_SCOPED_PARAM,
        EPT_E3_THRESHOLD_PARAM,
    )

    e3 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E3")
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E3_enabled": True})
    with patch.object(s4_2, "st", fake_st):
        selected, params = s4_2._render_rule_card(
            "EPT", e3, selected=True,
            selected_cdes=list(e3.required_columns.values()),
        )
    from src.custom_dqr_engine import EPT_E3_DETECT_UNIFORM_MAPPING_PARAM
    assert selected is True
    assert params == {
        EPT_E3_THRESHOLD_PARAM: EPT_E3_PERCENTILE,
        EPT_E3_PROJECT_SCOPED_PARAM: False,
        EPT_E3_DETECT_UNIFORM_MAPPING_PARAM: False,
    }


def test_render_rule_card_e3_persists_project_scope_toggle_on():
    """User flips the toggle on → params capture
    project_scoped=True (alongside the recommended threshold default)
    and the values would survive into the assignment."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules
    from src.custom_dqr_engine import (
        EPT_E3_PERCENTILE,
        EPT_E3_PROJECT_SCOPED_PARAM,
        EPT_E3_THRESHOLD_PARAM,
    )

    e3 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E3")
    fake_st = _make_fake_st(
        checkboxes={"custom_EPT_E3_enabled": True},
        toggles={f"custom_EPT_E3_opt_{EPT_E3_PROJECT_SCOPED_PARAM}": True},
    )
    with patch.object(s4_2, "st", fake_st):
        selected, params = s4_2._render_rule_card(
            "EPT", e3, selected=True,
            selected_cdes=list(e3.required_columns.values())
            + ["PLANVIEW_ID"],
        )
    from src.custom_dqr_engine import EPT_E3_DETECT_UNIFORM_MAPPING_PARAM
    assert selected is True
    assert params == {
        EPT_E3_THRESHOLD_PARAM: EPT_E3_PERCENTILE,
        EPT_E3_PROJECT_SCOPED_PARAM: True,
        EPT_E3_DETECT_UNIFORM_MAPPING_PARAM: False,
    }


def test_render_rule_card_e3_toggle_hidden_when_unticked():
    """An unticked rule never renders its options block, the toggle
    widget is only shown for selected rules."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules

    e3 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E3")
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E3_enabled": False})
    fake_st.toggle = MagicMock()
    with patch.object(s4_2, "st", fake_st):
        selected, params = s4_2._render_rule_card(
            "EPT", e3, selected=False, selected_cdes=[],
        )
    assert selected is False
    assert params == {}
    fake_st.toggle.assert_not_called()


def test_dp_block_persists_e3_project_scope_param_to_assignment():
    """The dp-block writer must round-trip the toggle into the assignment's
    ``params`` dict so subsequent re-renders see it pre-checked and so the
    dispatcher can read it at evaluation time."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.custom_dqr_engine import EPT_E3_PROJECT_SCOPED_PARAM
    from src.models import DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        cdes=[
            "WBC_LEVEL_5", "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN",
            "TOTAL_HOURS", "TOTAL_COST_USD", "PLANVIEW_ID",
        ],
        custom_assignments=[],
    )
    fake_st = _make_fake_st(
        checkboxes={"custom_EPT_E3_enabled": True},
        toggles={f"custom_EPT_E3_opt_{EPT_E3_PROJECT_SCOPED_PARAM}": True},
    )
    with patch.object(s4_2, "st", fake_st):
        valid, gaps = s4_2._render_dp_block("EPT", cfg)

    assert valid is True
    assert len(cfg.custom_assignments) == 1
    a = cfg.custom_assignments[0]
    assert a.rule_id == "E3"
    # Threshold defaults to the recommended P90; project scope reflects toggle.
    from src.custom_dqr_engine import (
        EPT_E3_DETECT_UNIFORM_MAPPING_PARAM,
        EPT_E3_PERCENTILE,
        EPT_E3_THRESHOLD_PARAM,
    )
    assert a.params == {
        EPT_E3_THRESHOLD_PARAM: EPT_E3_PERCENTILE,
        EPT_E3_PROJECT_SCOPED_PARAM: True,
        EPT_E3_DETECT_UNIFORM_MAPPING_PARAM: False,
    }


def test_dp_block_e3_project_scope_flags_planview_id_gap_when_not_a_cde():
    """Turning on the project-scope toggle adds PLANVIEW_ID to the rule's
    effective required columns; if it isn't a CDE, validation fails."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.custom_dqr_engine import EPT_E3_PROJECT_SCOPED_PARAM
    from src.models import DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        cdes=[
            "WBC_LEVEL_5", "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN",
            "TOTAL_HOURS", "TOTAL_COST_USD",
            # PLANVIEW_ID intentionally omitted.
        ],
        custom_assignments=[],
    )
    fake_st = _make_fake_st(
        checkboxes={"custom_EPT_E3_enabled": True},
        toggles={f"custom_EPT_E3_opt_{EPT_E3_PROJECT_SCOPED_PARAM}": True},
    )
    with patch.object(s4_2, "st", fake_st):
        valid, gaps = s4_2._render_dp_block("EPT", cfg)

    assert valid is False
    assert dict(gaps)["E3"] == ["PLANVIEW_ID"]


def test_dp_block_e3_global_scope_does_not_require_planview_id_cde():
    """With the project-scope toggle off, PLANVIEW_ID is not required -
    only the static required_columns matter for validation."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        cdes=[
            "WBC_LEVEL_5", "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN",
            "TOTAL_HOURS", "TOTAL_COST_USD",
        ],
        custom_assignments=[],
    )
    fake_st = _make_fake_st(
        checkboxes={"custom_EPT_E3_enabled": True},
        # No toggles override → defaults apply (project_scoped=False).
    )
    with patch.object(s4_2, "st", fake_st):
        valid, gaps = s4_2._render_dp_block("EPT", cfg)

    assert valid is True
    assert gaps == []


def test_dp_block_round_trips_existing_e3_params_across_reruns():
    """An assignment that already has params={project_scoped: True} must
    pre-fill the toggle on re-render so the user keeps their selection."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.custom_dqr_engine import EPT_E3_PROJECT_SCOPED_PARAM
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        cdes=[
            "WBC_LEVEL_5", "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN",
            "TOTAL_HOURS", "TOTAL_COST_USD", "PLANVIEW_ID",
        ],
        custom_assignments=[
            CustomDQRAssignment(
                rule_id="E3",
                weight=33.0,
                params={EPT_E3_PROJECT_SCOPED_PARAM: True},
            )
        ],
    )
    captured = {}

    def capture_toggle(_label, value=False, key=None, **kwargs):
        captured[key] = value
        # Echo the supplied default, the user didn't flip it this rerun.
        return value

    fake_st = _make_fake_st(checkboxes={"custom_EPT_E3_enabled": True})
    fake_st.toggle = capture_toggle

    with patch.object(s4_2, "st", fake_st):
        s4_2._render_dp_block("EPT", cfg)

    toggle_key = f"custom_EPT_E3_opt_{EPT_E3_PROJECT_SCOPED_PARAM}"
    assert captured[toggle_key] is True
    from src.custom_dqr_engine import (
        EPT_E3_DETECT_UNIFORM_MAPPING_PARAM,
        EPT_E3_PERCENTILE,
        EPT_E3_THRESHOLD_PARAM,
    )
    assert cfg.custom_assignments[0].params == {
        EPT_E3_THRESHOLD_PARAM: EPT_E3_PERCENTILE,
        EPT_E3_PROJECT_SCOPED_PARAM: True,
        EPT_E3_DETECT_UNIFORM_MAPPING_PARAM: False,
    }
    assert cfg.custom_assignments[0].weight == 33.0


def test_render_blocks_progression_when_any_dp_invalid():
    """The render() Next button is disabled (show_next=False) when a
    selected Custom DQR is missing required CDEs in any data product."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg_ept = DataProductConfig(
        system_code="EPT",
        cdes=[],  # no CDEs picked → E1 selection will be invalid
        custom_assignments=[],
        dqr_sources=["custom"],
    )
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E1_enabled": True})
    fake_st.session_state["configs"] = {"EPT": cfg_ept}
    fake_st.error = MagicMock()

    container_cm = MagicMock()
    container_cm.__enter__ = lambda self: self
    container_cm.__exit__ = lambda self, *a: False
    fake_st.container = MagicMock(return_value=container_cm)

    captured_show_next: list[bool] = []
    real_nav = s4_2._nav
    with patch.object(s4_2, "st", fake_st), \
         patch.object(s4_2, "_nav",
                      side_effect=lambda show_next=False: captured_show_next.append(show_next)):
        s4_2.render()

    assert captured_show_next == [False]
    fake_st.error.assert_called_once()
    err_msg = fake_st.error.call_args.args[0]
    assert "EPT" in err_msg
    assert "E1" in err_msg
    assert "CODE_OF_RESOURCE" in err_msg
    # Sanity check the real _nav still exists (no accidental rebind).
    assert s4_2._nav is real_nav or callable(real_nav)


def test_render_allows_progression_when_all_selections_valid():
    """When every selected Custom DQR has its required CDEs covered,
    render() enables the Next button and emits no error."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg_ept = DataProductConfig(
        system_code="EPT",
        cdes=["CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN"],
        custom_assignments=[],
        dqr_sources=["custom"],
    )
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E1_enabled": True})
    fake_st.session_state["configs"] = {"EPT": cfg_ept}
    fake_st.error = MagicMock()

    container_cm = MagicMock()
    container_cm.__enter__ = lambda self: self
    container_cm.__exit__ = lambda self, *a: False
    fake_st.container = MagicMock(return_value=container_cm)

    captured_show_next: list[bool] = []
    with patch.object(s4_2, "st", fake_st), \
         patch.object(s4_2, "_nav",
                      side_effect=lambda show_next=False: captured_show_next.append(show_next)):
        s4_2.render()

    assert captured_show_next == [True]
    fake_st.error.assert_not_called()


# ---------------------------------------------------------------------------
# Per-rule threshold selectbox (statistical-outlier rules)
# ---------------------------------------------------------------------------


def test_every_statistical_outlier_rule_exposes_threshold_select_option():
    """Each statistical-outlier rule (E3, E6, A3, A7, A8) must expose a
    selectbox threshold option so the user can override the recommended
    default at Step 4.2."""
    from config.custom_dqr_catalog import get_available_custom_dqr_rules

    ept = {r.id: r for r in get_available_custom_dqr_rules("EPT")}
    adr = {r.id: r for r in get_available_custom_dqr_rules("ADR")}
    for code, by_id, rule_ids in (
        ("EPT", ept, ("E3", "E6")),
        ("ADR", adr, ("A3", "A7", "A8")),
    ):
        for rid in rule_ids:
            rule = by_id[rid]
            assert rule.type == "Statistical Outlier", (code, rid)
            assert rule.select_options, (code, rid, "missing select_options")
            sel = rule.select_options[0]
            # Default must round-trip through the choices list.
            values = [v for v, _ in sel.choices]
            assert sel.default in values, (code, rid, sel.default, values)
            # The default's label calls out that it is the recommendation,
            # so the rule card surfaces the same guidance every render.
            default_label = dict(sel.choices)[sel.default]
            assert "recommended" in default_label.lower(), (code, rid)


def test_render_rule_card_e6_renders_threshold_select_with_default():
    """E6 selected with no prior params → the IQR-multiplier selectbox is
    rendered, the segment-by-project-type toggle defaults to off, and the
    params dict captures both the recommended threshold (1.5) and the
    segmentation default (False)."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules
    from src.custom_dqr_engine import (
        EPT_E6_MILD_IQR_MULTIPLIER,
        EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM,
        EPT_E6_THRESHOLD_PARAM,
    )

    e6 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E6")
    fake_st = _make_fake_st(checkboxes={"custom_EPT_E6_enabled": True})
    with patch.object(s4_2, "st", fake_st):
        selected, params = s4_2._render_rule_card(
            "EPT", e6, selected=True,
            selected_cdes=list(e6.required_columns.values()),
        )
    assert selected is True
    assert params == {
        EPT_E6_THRESHOLD_PARAM: EPT_E6_MILD_IQR_MULTIPLIER,
        EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM: False,
    }


def test_render_rule_card_e6_persists_segmentation_toggle_on():
    """User flips the segment-by-project-type toggle on → params capture
    ``segment_by_project_type=True`` alongside the recommended threshold."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules
    from src.custom_dqr_engine import (
        EPT_E6_MILD_IQR_MULTIPLIER,
        EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM,
        EPT_E6_THRESHOLD_PARAM,
    )

    e6 = next(r for r in get_available_custom_dqr_rules("EPT") if r.id == "E6")
    fake_st = _make_fake_st(
        checkboxes={"custom_EPT_E6_enabled": True},
        toggles={
            f"custom_EPT_E6_opt_{EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM}": True
        },
    )
    with patch.object(s4_2, "st", fake_st):
        selected, params = s4_2._render_rule_card(
            "EPT", e6, selected=True,
            selected_cdes=list(e6.required_columns.values()),
        )
    assert selected is True
    assert params == {
        EPT_E6_THRESHOLD_PARAM: EPT_E6_MILD_IQR_MULTIPLIER,
        EPT_E6_SEGMENT_BY_PROJECT_TYPE_PARAM: True,
    }


def test_render_rule_card_a3_persists_user_picked_percentile():
    """When the user picks P95 from the A3 threshold selectbox, the new
    value flows into the params dict (and would be persisted on the
    assignment)."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules
    from src.custom_dqr_engine import (
        ADR_A3_THRESHOLD_CHOICES,
        ADR_A3_THRESHOLD_PARAM,
    )

    a3 = next(r for r in get_available_custom_dqr_rules("ADR") if r.id == "A3")
    p95_label = dict(ADR_A3_THRESHOLD_CHOICES)[0.95]
    fake_st = _make_fake_st(
        checkboxes={"custom_ADR_A3_enabled": True},
        selectboxes={f"custom_ADR_A3_sel_{ADR_A3_THRESHOLD_PARAM}": p95_label},
    )
    with patch.object(s4_2, "st", fake_st):
        selected, params = s4_2._render_rule_card(
            "ADR", a3, selected=True,
            selected_cdes=list(a3.required_columns.values()),
        )
    from src.custom_dqr_engine import (
        ADR_A3_DETECT_UNIFORM_MAPPING_PARAM,
        ADR_A3_PROJECT_SCOPED_PARAM,
    )
    assert selected is True
    assert params == {
        ADR_A3_THRESHOLD_PARAM: 0.95,
        ADR_A3_PROJECT_SCOPED_PARAM: False,
        ADR_A3_DETECT_UNIFORM_MAPPING_PARAM: False,
    }


def test_render_rule_card_a3_persists_project_scope_toggle_on():
    """User flips A3's project-scope toggle on → params capture
    project_scoped=True (alongside the recommended threshold default)
    and the values would survive into the assignment."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules
    from src.custom_dqr_engine import (
        ADR_A3_DETECT_UNIFORM_MAPPING_PARAM,
        ADR_A3_PERCENTILE,
        ADR_A3_PROJECT_SCOPED_PARAM,
        ADR_A3_THRESHOLD_PARAM,
    )

    a3 = next(r for r in get_available_custom_dqr_rules("ADR") if r.id == "A3")
    fake_st = _make_fake_st(
        checkboxes={"custom_ADR_A3_enabled": True},
        toggles={f"custom_ADR_A3_opt_{ADR_A3_PROJECT_SCOPED_PARAM}": True},
    )
    with patch.object(s4_2, "st", fake_st):
        selected, params = s4_2._render_rule_card(
            "ADR", a3, selected=True,
            selected_cdes=list(a3.required_columns.values()),
        )
    assert selected is True
    assert params == {
        ADR_A3_THRESHOLD_PARAM: ADR_A3_PERCENTILE,
        ADR_A3_PROJECT_SCOPED_PARAM: True,
        ADR_A3_DETECT_UNIFORM_MAPPING_PARAM: False,
    }


def test_dp_block_a3_project_scope_flags_planview_id_gap_when_not_a_cde():
    """Turning on A3's project-scope toggle adds PLANVIEW_ID to the rule's
    effective required columns; the static A3 required map already includes
    PLANVIEW_ID, so a CDE list without it must fail validation regardless
    of the toggle - verify the validator still flags the gap when the
    toggle is on."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.custom_dqr_engine import ADR_A3_PROJECT_SCOPED_PARAM
    from src.models import DataProductConfig

    cfg = DataProductConfig(
        system_code="ADR",
        cdes=[
            # PLANVIEW_ID intentionally omitted.
            "COMPLETE_WBC", "COST_TOTAL_HOURS", "COST_TOTAL_COST",
        ],
        custom_assignments=[],
    )
    fake_st = _make_fake_st(
        checkboxes={"custom_ADR_A3_enabled": True},
        toggles={f"custom_ADR_A3_opt_{ADR_A3_PROJECT_SCOPED_PARAM}": True},
    )
    with patch.object(s4_2, "st", fake_st):
        valid, gaps = s4_2._render_dp_block("ADR", cfg)

    assert valid is False
    assert "PLANVIEW_ID" in dict(gaps)["A3"]


def test_render_rule_card_a7_threshold_selectbox_hidden_when_unticked():
    """An unticked outlier rule does not render its threshold selectbox -
    options are scoped to the user's actual selections."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules

    a7 = next(r for r in get_available_custom_dqr_rules("ADR") if r.id == "A7")
    fake_st = _make_fake_st(checkboxes={"custom_ADR_A7_enabled": False})
    fake_st.selectbox = MagicMock()
    with patch.object(s4_2, "st", fake_st):
        selected, params = s4_2._render_rule_card(
            "ADR", a7, selected=False, selected_cdes=[],
        )
    assert selected is False
    assert params == {}
    fake_st.selectbox.assert_not_called()


def test_dp_block_round_trips_existing_threshold_param_to_widget():
    """An assignment that already stores a non-default threshold (P95) must
    pre-select that entry on the selectbox so the user keeps their pick."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.custom_dqr_engine import (
        ADR_A3_THRESHOLD_CHOICES,
        ADR_A3_THRESHOLD_PARAM,
    )
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="ADR",
        cdes=["PLANVIEW_ID", "COMPLETE_WBC", "COST_TOTAL_HOURS", "COST_TOTAL_COST"],
        custom_assignments=[
            CustomDQRAssignment(
                rule_id="A3", weight=10.0,
                params={ADR_A3_THRESHOLD_PARAM: 0.95},
            ),
        ],
    )

    captured_index: dict[str, int] = {}

    def capture_selectbox(label, options, index=0, key=None, **kwargs):
        captured_index[key] = index
        return options[index]

    fake_st = _make_fake_st(checkboxes={"custom_ADR_A3_enabled": True})
    fake_st.selectbox = capture_selectbox
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_dp_block("ADR", cfg)

    widget_key = f"custom_ADR_A3_sel_{ADR_A3_THRESHOLD_PARAM}"
    expected_index = [v for v, _ in ADR_A3_THRESHOLD_CHOICES].index(0.95)
    assert captured_index[widget_key] == expected_index
    from src.custom_dqr_engine import (
        ADR_A3_DETECT_UNIFORM_MAPPING_PARAM,
        ADR_A3_PROJECT_SCOPED_PARAM,
    )
    assert cfg.custom_assignments[0].params == {
        ADR_A3_THRESHOLD_PARAM: 0.95,
        ADR_A3_PROJECT_SCOPED_PARAM: False,
        ADR_A3_DETECT_UNIFORM_MAPPING_PARAM: False,
    }


def test_render_rule_options_survives_default_and_stored_value_both_missing():
    """When BOTH the stored value AND the rule's declared default are absent
    from the current ``choices`` list (e.g. catalog tightened the choices on
    both fronts between runs), ``_render_rule_options`` must still render
    without raising ``ValueError`` from ``list.index()``. It falls back to
    the first available choice."""
    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import CustomRuleDef, CustomRuleSelectOption

    rule = CustomRuleDef(
        id="TEST_RULE",
        name="Test rule",
        type="Statistical Outlier",
        description="",
        notes="",
        select_options=(
            CustomRuleSelectOption(
                key="threshold",
                label="Threshold",
                choices=((0.95, "P95"), (0.99, "P99")),
                default=0.42,  # not in choices either - simulates catalog drift
            ),
        ),
    )

    captured_index: dict[str, int] = {}

    def capture_selectbox(label, options, index=0, key=None, **kwargs):
        captured_index[key] = index
        return options[index]

    fake_st = _make_fake_st()
    fake_st.selectbox = capture_selectbox
    with patch.object(s4_2, "st", fake_st):
        params = s4_2._render_rule_options(
            "ADR", rule, {"threshold": 0.123},  # stored value also missing
        )

    # Did not raise, and the resulting params point at the first choice.
    assert params["threshold"] == 0.95
    assert captured_index["custom_ADR_TEST_RULE_sel_threshold"] == 0


def test_dp_block_falls_back_to_default_when_stored_value_not_in_choices():
    """If a stored threshold value is no longer in the catalog choices
    (e.g. legacy assignment, catalog tightened the list), the widget
    falls back to the recommended default rather than raising."""
    import ui.step_04_2_custom_dqr as s4_2
    from src.custom_dqr_engine import (
        ADR_A3_PERCENTILE,
        ADR_A3_THRESHOLD_CHOICES,
        ADR_A3_THRESHOLD_PARAM,
    )
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="ADR",
        cdes=["PLANVIEW_ID", "COMPLETE_WBC", "COST_TOTAL_HOURS", "COST_TOTAL_COST"],
        custom_assignments=[
            CustomDQRAssignment(
                rule_id="A3", weight=10.0,
                # 0.42 is not in ADR_A3_THRESHOLD_CHOICES.
                params={ADR_A3_THRESHOLD_PARAM: 0.42},
            ),
        ],
    )

    captured_index: dict[str, int] = {}

    def capture_selectbox(label, options, index=0, key=None, **kwargs):
        captured_index[key] = index
        return options[index]

    fake_st = _make_fake_st(checkboxes={"custom_ADR_A3_enabled": True})
    fake_st.selectbox = capture_selectbox
    with patch.object(s4_2, "st", fake_st):
        s4_2._render_dp_block("ADR", cfg)

    widget_key = f"custom_ADR_A3_sel_{ADR_A3_THRESHOLD_PARAM}"
    default_index = [v for v, _ in ADR_A3_THRESHOLD_CHOICES].index(
        ADR_A3_PERCENTILE
    )
    assert captured_index[widget_key] == default_index
    # The widget's selected value replaces the stale entry on the assignment.
    from src.custom_dqr_engine import (
        ADR_A3_DETECT_UNIFORM_MAPPING_PARAM,
        ADR_A3_PROJECT_SCOPED_PARAM,
    )
    assert cfg.custom_assignments[0].params == {
        ADR_A3_THRESHOLD_PARAM: ADR_A3_PERCENTILE,
        ADR_A3_PROJECT_SCOPED_PARAM: False,
        ADR_A3_DETECT_UNIFORM_MAPPING_PARAM: False,
    }
