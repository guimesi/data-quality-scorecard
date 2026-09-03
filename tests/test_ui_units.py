"""Unit-level tests for UI helper functions that are hard to exercise
through AppTest (parameter editors per dimension, weight buttons, etc.).

Each test mocks the streamlit module to capture / control widget
interactions directly.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers: a tiny streamlit stand-in
# ---------------------------------------------------------------------------

class FakeSessionState(dict):
    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(item) from e

    def __setattr__(self, key, value):
        self[key] = value


def _make_fake_st(
    *,
    text_inputs: dict[str, str] | None = None,
    number_inputs: dict[str, float] | None = None,
    checkboxes: dict[str, bool] | None = None,
    toggles: dict[str, bool] | None = None,
    selectboxes: dict[str, str] | None = None,
    button_returns: dict[str, bool] | None = None,
):
    """Build a MagicMock that mimics streamlit for our purposes."""
    text_inputs = text_inputs or {}
    number_inputs = number_inputs or {}
    checkboxes = checkboxes or {}
    toggles = toggles or {}
    selectboxes = selectboxes or {}
    button_returns = button_returns or {}

    fake = MagicMock()
    fake.session_state = FakeSessionState()

    def text_input(label, value="", key=None, **kwargs):
        return text_inputs.get(key, value)

    def number_input(label, *, min_value=0, max_value=None, value=0, step=1, key=None, **kwargs):
        return number_inputs.get(key, value)

    def checkbox(label, value=False, key=None, **kwargs):
        return checkboxes.get(key, value)

    def toggle(label, value=False, key=None, **kwargs):
        return toggles.get(key, value)

    def selectbox(label, options, index=0, key=None, **kwargs):
        if key in selectboxes:
            return selectboxes[key]
        return options[index]

    def button(label, *, key=None, **kwargs):
        return button_returns.get(key, False)

    def columns(spec, **_kwargs):
        # Return len(spec) columns; each column is also a no-op context
        n = spec if isinstance(spec, int) else len(spec)
        return [_fake_column() for _ in range(n)]

    fake.text_input = text_input
    fake.number_input = number_input
    fake.checkbox = checkbox
    fake.toggle = toggle
    fake.selectbox = selectbox
    fake.button = button
    fake.columns = columns
    fake.rerun = MagicMock()
    # ``render_restart_button`` wraps its confirm body in ``st.dialog``;
    # a no-op decorator runs that body inline so the confirm click reaches
    # ``on_restart`` in unit tests.
    fake.dialog = lambda *a, **k: (lambda fn: fn)
    return fake


def _fake_column():
    col = MagicMock()
    col.__enter__ = lambda self: self
    col.__exit__ = lambda self, *a: False
    return col


# ---------------------------------------------------------------------------
# step_04_dqr_assignment._render_param_editor, one per dimension
# ---------------------------------------------------------------------------

def test_param_editor_completeness_sets_allow_empty():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(checkboxes={"x_allow_empty": True})
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Completeness", {})
    assert out["allow_empty_string"] is True


def test_param_editor_validity_with_regex_and_lengths():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(text_inputs={
        "x_regex": r"\d+",
        "x_minlen": "3",
        "x_maxlen": "10",
    })
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Validity", {})
    assert out["regex"] == r"\d+"
    assert out["min_length"] == 3
    assert out["max_length"] == 10


def test_param_editor_validity_blank_strings_become_none():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(text_inputs={"x_regex": "", "x_minlen": "", "x_maxlen": ""})
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Validity", {})
    assert out["regex"] is None
    assert out["min_length"] is None
    assert out["max_length"] is None


def test_param_editor_accuracy_parses_floats():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(text_inputs={"x_min": "1.5", "x_max": "9.9"})
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Accuracy", {})
    assert out["min_value"] == 1.5
    assert out["max_value"] == 9.9


def test_param_editor_accuracy_non_numeric_falls_back_to_none():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(text_inputs={"x_min": "not-a-number", "x_max": "also-bad"})
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Accuracy", {})
    assert out["min_value"] is None
    assert out["max_value"] is None


def test_param_editor_accuracy_empty_keeps_none():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(text_inputs={"x_min": "", "x_max": ""})
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Accuracy", {"min_value": 1.0, "max_value": 2.0})
    assert out["min_value"] is None
    assert out["max_value"] is None


def test_param_editor_consistency_sets_compare_and_op():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(
        text_inputs={"x_cmpcol": "OTHER_COL"},
        selectboxes={"x_op": ">="},
    )
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Consistency", {})
    assert out["compare_column"] == "OTHER_COL"
    assert out["operator"] == ">="


def test_param_editor_consistency_empty_compare():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(text_inputs={"x_cmpcol": ""})
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Consistency", {})
    assert out["compare_column"] is None


def test_param_editor_consistency_unknown_operator_falls_back_without_raising():
    """A legacy/corrupt ``operator`` value that is not one of the catalog
    choices must not crash the editor. The selectbox falls back to the first
    operator (``"<="``) so the user can pick a valid one."""
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st()
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Consistency", {"operator": "≠"})
    assert out["operator"] == "<="


def test_param_editor_timeliness_number_input():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(number_inputs={"x_lag": 45})
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Timeliness", {})
    assert out["max_lag_days"] == 45


def test_param_editor_currency_number_input():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(number_inputs={"x_age": 180})
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Currency", {})
    assert out["max_age_days"] == 180


def test_param_editor_conformity_parses_csv():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(text_inputs={"x_allowed": "A, B , C"})
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Conformity", {})
    assert out["allowed_values"] == ["A", "B", "C"]


def test_param_editor_integrity_parses_csv():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(text_inputs={"x_refs": "r1, r2"})
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Integrity", {})
    assert out["reference_values"] == ["r1", "r2"]


def test_param_editor_precision_number_input():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st(number_inputs={"x_decimals": 4})
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Precision", {})
    assert out["max_decimals"] == 4


def test_param_editor_uniqueness_caption():
    from ui.step_04_dqr_assignment import _render_param_editor
    fake_st = _make_fake_st()
    with patch("ui.step_04_dqr_assignment.st", fake_st):
        out = _render_param_editor("x", "Uniqueness", {})
    # Should be a pass-through (no param changes)
    assert out == {}


# ---------------------------------------------------------------------------
# step_04 _nav disabled Next branch
# ---------------------------------------------------------------------------

def test_step4_nav_disabled_next():
    """Covers the disabled Next branch."""
    import ui.step_04_dqr_assignment as s4
    fake_st = _make_fake_st()
    with patch.object(s4, "st", fake_st), \
         patch("utils.ui_components.st", fake_st):
        s4._nav(show_next=False)


def test_step4_nav_next_click_calls_next_step():
    """Covers the active Next click path (`next_step()` call)."""
    import ui.step_04_dqr_assignment as s4
    fake_st = _make_fake_st()
    fake_st.button = MagicMock(return_value=True)
    with patch.object(s4, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_04_dqr_assignment.next_step") as mock_next, \
         patch("ui.step_04_dqr_assignment.prev_step") as mock_prev:
        s4._nav(show_next=True)
        mock_next.assert_called_once()
        mock_prev.assert_called_once()


# ---------------------------------------------------------------------------
# step_05_weight_assignment
# ---------------------------------------------------------------------------

def test_step5_render_standard_weights_empty_returns_zero():
    """Empty Standard assignments → early return with zero total."""
    import ui.step_05_weight_assignment as s5
    from src.models import DataProductConfig
    cfg = DataProductConfig(system_code="X", assignments=[])
    fake_st = _make_fake_st()
    with patch.object(s5, "st", fake_st):
        total = s5._render_standard_weights("X", cfg)
    assert total == 0.0


def test_step5_render_custom_weights_empty_returns_zero():
    """Empty Custom assignments → early return with zero total."""
    import ui.step_05_weight_assignment as s5
    from src.models import DataProductConfig
    cfg = DataProductConfig(system_code="X", custom_assignments=[])
    fake_st = _make_fake_st()
    with patch.object(s5, "st", fake_st):
        total = s5._render_custom_weights("X", cfg)
    assert total == 0.0


def test_step5_render_standard_weights_distribute_equally_button_clicked():
    """The Standard 'Distribute equally' button splits 100% across rules."""
    import ui.step_05_weight_assignment as s5
    from src.models import DataProductConfig, DQRAssignment

    cfg = DataProductConfig(
        system_code="X",
        assignments=[
            DQRAssignment("A", "Completeness", weight=0),
            DQRAssignment("B", "Completeness", weight=0),
        ],
    )
    fake_st = _make_fake_st(
        button_returns={"equal_std_X": True},   # Simulate clicking the button
    )
    with patch.object(s5, "st", fake_st):
        s5._render_standard_weights("X", cfg)

    assert cfg.assignments[0].weight == 50.0
    assert cfg.assignments[1].weight == 50.0
    fake_st.rerun.assert_called_once()


def test_step5_render_custom_weights_distribute_equally_button_clicked():
    """The Custom 'Distribute equally' button splits 100% across selected
    custom rules."""
    import ui.step_05_weight_assignment as s5
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[
            CustomDQRAssignment(rule_id="E1", weight=0),
            CustomDQRAssignment(rule_id="E2", weight=0),
        ],
    )
    fake_st = _make_fake_st(
        button_returns={"equal_cus_EPT": True},
    )
    with patch.object(s5, "st", fake_st):
        s5._render_custom_weights("EPT", cfg)

    assert cfg.custom_assignments[0].weight == 50.0
    assert cfg.custom_assignments[1].weight == 50.0
    fake_st.rerun.assert_called_once()


def test_step5_render_custom_weights_falls_back_to_rule_id_when_unknown():
    """Custom rule whose id isn't in the catalog falls back to showing the
    raw rule_id as the human label."""
    import ui.step_05_weight_assignment as s5
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[CustomDQRAssignment(rule_id="UNKNOWN", weight=100)],
    )
    fake_st = _make_fake_st()
    with patch.object(s5, "st", fake_st):
        total = s5._render_custom_weights("EPT", cfg)
    assert total == 100.0


def test_step5_only_e4_selected_starts_blank():
    """Custom rule weights now start at 0%, the user must explicitly type a
    value or click 'Distribute equally', mirroring the Standard rules UX."""
    import ui.step_05_weight_assignment as s5
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[CustomDQRAssignment(rule_id="E4", weight=0)],
    )
    fake_st = _make_fake_st()
    with patch.object(s5, "st", fake_st):
        total = s5._render_custom_weights("EPT", cfg)
    assert total == 0.0
    assert cfg.custom_assignments[0].weight == 0.0


def test_step5_only_e7_selected_starts_blank():
    """Symmetric to E4 - single Custom rule no longer auto-pins to 100%."""
    import ui.step_05_weight_assignment as s5
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[CustomDQRAssignment(rule_id="E7", weight=0)],
    )
    fake_st = _make_fake_st()
    with patch.object(s5, "st", fake_st):
        total = s5._render_custom_weights("EPT", cfg)
    assert total == 0.0
    assert cfg.custom_assignments[0].weight == 0.0


def test_step5_multiple_custom_rules_start_blank():
    """Multiple Custom rules no longer auto-distribute, each starts at 0%
    until the user fills the weights or clicks 'Distribute equally'."""
    import ui.step_05_weight_assignment as s5
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[
            CustomDQRAssignment(rule_id="E1", weight=0),
            CustomDQRAssignment(rule_id="E4", weight=0),
            CustomDQRAssignment(rule_id="E7", weight=0),
        ],
    )
    fake_st = _make_fake_st()
    with patch.object(s5, "st", fake_st):
        total = s5._render_custom_weights("EPT", cfg)
    assert total == 0.0
    assert all(a.weight == 0.0 for a in cfg.custom_assignments)


def test_step5_custom_distribute_equally_button_after_blank_initial_render():
    """Confirms the user-driven path: rules render blank, then clicking
    'Distribute equally' splits 100% across them."""
    import ui.step_05_weight_assignment as s5
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[
            CustomDQRAssignment(rule_id="E1", weight=0),
            CustomDQRAssignment(rule_id="E7", weight=0),
        ],
    )
    fake_st = _make_fake_st(button_returns={"equal_cus_EPT": True})
    with patch.object(s5, "st", fake_st):
        s5._render_custom_weights("EPT", cfg)
    assert cfg.custom_assignments[0].weight == 50.0
    assert cfg.custom_assignments[1].weight == 50.0


def test_step5_render_custom_weights_clamps_overflow_to_max_allowed():
    """A pre-stored weight exceeding the per-widget cap is clamped down so
    the running total stays ≤ 100% (covers the per-widget cap branch in the
    Custom rules section)."""
    import ui.step_05_weight_assignment as s5
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[
            CustomDQRAssignment(rule_id="E1", weight=80),
            CustomDQRAssignment(rule_id="E2", weight=80),
        ],
    )
    fake_st = _make_fake_st()
    with patch.object(s5, "st", fake_st):
        total = s5._render_custom_weights("EPT", cfg)
    assert total <= 100.0 + 0.01


def test_step5_render_dp_block_warns_when_custom_under_100():
    """Custom rules summing < 100 emits a 'still needed' warning and marks
    the DP invalid (covers lines 183-187)."""
    import ui.step_05_weight_assignment as s5
    from src.models import CustomDQRAssignment, DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[CustomDQRAssignment(rule_id="E1", weight=10)],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    fake_st = _make_fake_st()
    with patch.object(s5, "st", fake_st):
        valid = s5._render_dp_block("EPT", cfg)
    assert valid is False


def test_step5_render_dp_block_warns_when_custom_selected_but_no_rules():
    """Selecting Custom in Step 4 but choosing zero rules in 4.2 fires a
    dedicated warning (covers lines 188-192)."""
    import ui.step_05_weight_assignment as s5
    from src.models import DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        custom_assignments=[],
        dqr_sources=["custom"],
        source_weights={"custom": 100.0},
    )
    fake_st = _make_fake_st()
    with patch.object(s5, "st", fake_st):
        s5._render_dp_block("EPT", cfg)
    # Warning was emitted via st.warning(...)
    assert any(
        "Custom DQR source is selected but no rules were chosen" in str(args)
        for call in fake_st.warning.call_args_list
        for args in [call.args]
    )


def test_step5_nav_disabled_next_renders_without_action():
    import ui.step_05_weight_assignment as s5

    fake_st = _make_fake_st()
    fake_st.button = MagicMock(return_value=False)
    with patch.object(s5, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_05_weight_assignment.next_step") as mock_next, \
         patch("ui.step_05_weight_assignment.prev_step") as mock_prev:
        s5._nav(show_next=False)
    mock_next.assert_not_called()
    mock_prev.assert_not_called()


def test_step5_nav_back_click_calls_prev_step():
    import ui.step_05_weight_assignment as s5

    fake_st = _make_fake_st()
    call_results = iter([True, False, False])
    fake_st.button = MagicMock(side_effect=lambda *a, **kw: next(call_results))
    with patch.object(s5, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_05_weight_assignment.prev_step") as mock_prev:
        s5._nav(show_next=True)
    mock_prev.assert_called_once()


def test_step5_nav_next_click_calls_next_step():
    """Only the Next button fires next_step. The nav button order is Back,
    the Restart popover's confirm, then Next, so [False, False, True] clicks
    Next alone (Back / Restart stay un-clicked)."""
    import ui.step_05_weight_assignment as s5

    fake_st = _make_fake_st()
    call_results = iter([False, False, True])
    fake_st.button = MagicMock(side_effect=lambda *a, **kw: next(call_results))
    with patch.object(s5, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_05_weight_assignment.next_step") as mock_next, \
         patch("ui.step_05_weight_assignment.prev_step") as mock_prev:
        s5._nav(show_next=True)
    mock_next.assert_called_once()
    mock_prev.assert_not_called()


# ---------------------------------------------------------------------------
# step_06_dashboard helpers - _render_source_breakdown branches
# ---------------------------------------------------------------------------

def test_dashboard_source_breakdown_returns_when_no_subscores_present():
    """If a ScorecardResult declares source_weights but somehow neither
    subscore is set, the helper bails out before rendering metric tiles
    (defensive branch in the dashboard)."""
    import pandas as pd

    import ui.step_06_dashboard as s6
    from src.models import ScorecardResult

    result = ScorecardResult(
        system_code="X",
        overall_score=0.0,
        row_scores=pd.Series([], dtype=float),
        rule_pass_rates={},
        cde_scores={},
        dimension_scores={},
        total_rows=0,
        rows_green=0, rows_yellow=0, rows_red=0,
        threshold_green=80, threshold_yellow=60,
        standard_score=None,
        custom_score=None,
        source_weights={"standard": 100.0},
    )
    fake_st = _make_fake_st()
    with patch.object(s6, "st", fake_st):
        s6._render_source_breakdown(result)


def test_dashboard_source_breakdown_returns_when_no_source_weights():
    """When ``source_weights`` is empty (e.g. zero-rule fallback), the
    helper short-circuits before doing anything."""
    import pandas as pd

    import ui.step_06_dashboard as s6
    from src.models import ScorecardResult

    result = ScorecardResult(
        system_code="X",
        overall_score=0.0,
        row_scores=pd.Series([], dtype=float),
        rule_pass_rates={},
        cde_scores={},
        dimension_scores={},
        total_rows=0,
        rows_green=0, rows_yellow=0, rows_red=0,
        threshold_green=80, threshold_yellow=60,
        source_weights={},
    )
    fake_st = _make_fake_st()
    with patch.object(s6, "st", fake_st):
        s6._render_source_breakdown(result)


def test_step5_nav_buttons_prev_and_disabled_next():
    """Covers prev_step click + disabled Next rendering."""
    import ui.step_05_weight_assignment as s5

    fake_st = _make_fake_st()
    fake_st.button = MagicMock(return_value=True)
    with patch.object(s5, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_05_weight_assignment.prev_step") as mock_prev:
        s5._nav(show_next=False)
        mock_prev.assert_called_once()


def test_step5_nav_all_buttons_invoke_their_callbacks():
    """When every nav button reports a click, each wires through to its own
    callback - Back -> prev_step, the Restart popover's confirm -> restart_app,
    Next -> next_step. Distinct from the Next-only test above; both run now
    (they previously shared a name, so the first was silently shadowed - M4)."""
    import ui.step_05_weight_assignment as s5
    fake_st = _make_fake_st()
    fake_st.button = MagicMock(return_value=True)
    with patch.object(s5, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_05_weight_assignment.next_step") as mock_next, \
         patch("ui.step_05_weight_assignment.prev_step") as mock_prev, \
         patch("ui.step_05_weight_assignment.restart_app") as mock_restart:
        s5._nav(show_next=True)
        mock_next.assert_called_once()
        mock_prev.assert_called_once()
        mock_restart.assert_called_once()


# ---------------------------------------------------------------------------
# step_03_cde_selection._nav disabled next branch
# ---------------------------------------------------------------------------

def test_step3_nav_back_click():
    import ui.step_03_cde_selection as s3
    fake_st = _make_fake_st()
    fake_st.button = MagicMock(return_value=True)
    with patch.object(s3, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_03_cde_selection.prev_step") as mock_prev, \
         patch("ui.step_03_cde_selection.next_step") as mock_next:
        s3._nav(show_next=True)
        mock_prev.assert_called_once()
        mock_next.assert_called_once()


def test_step3_nav_disabled_next():
    """Covers line 148 (disabled next button rendering)."""
    import ui.step_03_cde_selection as s3
    fake_st = _make_fake_st()
    fake_st.button = MagicMock(return_value=False)
    with patch.object(s3, "st", fake_st), \
         patch("utils.ui_components.st", fake_st):
        s3._nav(show_next=False)


def test_step3_nav_restart_click_calls_restart_app():
    """Covers the Restart button branch (Feature 3) - clicking it calls
    ``restart_app`` so all workflow state is cleared."""
    import ui.step_03_cde_selection as s3

    fake_st = _make_fake_st()
    # Back=False, Restart=True, Next=False
    call_results = iter([False, True, False])
    fake_st.button = MagicMock(side_effect=lambda *a, **kw: next(call_results))
    with patch.object(s3, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_03_cde_selection.restart_app") as mock_restart:
        s3._nav(show_next=True)
    mock_restart.assert_called_once()


def test_step3_build_profile_grid_preserves_column_order():
    """The grid's row order mirrors ``dp.df.columns`` so ``cfg.cdes`` ends
    up in source order - essential for the deterministic downstream
    displays (Step 4.1 iterates CDEs in the same order)."""
    import pandas as pd

    import ui.step_03_cde_selection as s3
    from src.models import ColumnProfile, DataProduct

    df = pd.DataFrame({"A": [1, 2], "B": [3, 4], "C": [5, 6]})
    profiles = {
        col: ColumnProfile(
            name=col, dtype="int64", column_type_group="integer",
            total_rows=2, null_count=0, null_pct=0.0,
            distinct_count=2, duplicate_count=0, sample_values=[1, 2],
        )
        for col in df.columns
    }
    dp = DataProduct(
        system_code="X", name="X_DP", df=df, source_tables=["t"], profiles=profiles,
    )
    grid = s3._build_profile_grid(dp, current_cdes=["B"], required={})
    assert list(grid["Column"]) == ["A", "B", "C"]
    assert list(grid["CDE"]) == [False, True, False]


def test_step3_render_dp_block_caches_base_grid_across_reruns():
    """Regression: the base DataFrame fed to ``st.data_editor`` MUST be
    bit-stable across reruns within a single step-3 session.

    Streamlit discards every accumulated user edit when the editor's input
    DataFrame content changes between reruns. If we rebuilt the grid each
    render from ``cfg.cdes``, then a click would update ``cfg.cdes``, the
    next rerun would feed a *different* base, and the click would be wiped
    before it could land. Users would be forced to click each row twice.

    This test asserts the cache: the same DataFrame object is reused across
    reruns as long as ``id(dp)`` is unchanged."""
    import pandas as pd

    import ui.step_03_cde_selection as s3
    from src.models import ColumnProfile, DataProduct, DataProductConfig

    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    profiles = {
        col: ColumnProfile(
            name=col, dtype="int64", column_type_group="integer",
            total_rows=2, null_count=0, null_pct=0.0,
            distinct_count=2, duplicate_count=0, sample_values=[1, 2],
        )
        for col in df.columns
    }
    dp = DataProduct(
        system_code="X", name="X_DP", df=df, source_tables=["t"],
        profiles=profiles,
    )

    fake_st = _make_fake_st()
    fake_st.session_state["configs"] = {"X": DataProductConfig(system_code="X")}

    # Capture the DataFrame each call sees as the editor's input.
    captured_inputs: list[int] = []

    def fake_data_editor(df_in, **kwargs):
        captured_inputs.append(id(df_in))
        # Simulate the user ticking row B on the *first* render. Subsequent
        # renders return the same picks because Streamlit's stored edits
        # would still be applied to the cached base.
        out = df_in.copy()
        out["CDE"] = [False, True]
        return out

    fake_st.data_editor = fake_data_editor

    # Stub out the chip-slot empty() / container() context managers and the
    # other rendering primitives so we can call _render_dp_block multiple
    # times without spurious errors.
    container_cm = MagicMock()
    container_cm.__enter__ = lambda self: self
    container_cm.__exit__ = lambda self, *a: False
    empty_slot = MagicMock()
    empty_slot.container = MagicMock(return_value=container_cm)
    fake_st.empty = MagicMock(return_value=empty_slot)

    with patch.object(s3, "st", fake_st):
        # Three back-to-back renders simulate three Streamlit reruns
        # within the same step-3 session (e.g. user clicks then clicks
        # again then clicks a third time).
        s3._render_dp_block("X", dp)
        first_call_input = captured_inputs[-1]

        s3._render_dp_block("X", dp)
        s3._render_dp_block("X", dp)

    # All three reruns received the *same DataFrame instance* as input.
    # That's the contract: input never changes within a session, so
    # data_editor preserves the user's edits and a single click suffices.
    assert len(captured_inputs) == 3
    assert all(i == first_call_input for i in captured_inputs)
    # And cfg.cdes correctly reflects the editor's final returned state.
    assert fake_st.session_state["configs"]["X"].cdes == ["B"]


def test_step3_render_dp_block_invalidates_cache_when_dp_instance_changes():
    """When Step 2 rebuilds (e.g., the user revisited Step 1 to change the
    system selection, or hit Restart), the ``DataProduct`` instance is new.
    The Step 3 cache key includes ``id(dp)``, so the base grid is rebuilt
    cleanly, no stale picks from a previous workflow leak through."""
    import pandas as pd

    import ui.step_03_cde_selection as s3
    from src.models import ColumnProfile, DataProduct, DataProductConfig

    def make_dp() -> DataProduct:
        df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        profiles = {
            col: ColumnProfile(
                name=col, dtype="int64", column_type_group="integer",
                total_rows=2, null_count=0, null_pct=0.0,
                distinct_count=2, duplicate_count=0, sample_values=[1, 2],
            )
            for col in df.columns
        }
        return DataProduct(
            system_code="X", name="X_DP", df=df, source_tables=["t"],
            profiles=profiles,
        )

    dp_v1 = make_dp()
    dp_v2 = make_dp()  # new instance - id() differs
    assert id(dp_v1) != id(dp_v2)

    fake_st = _make_fake_st()
    fake_st.session_state["configs"] = {"X": DataProductConfig(system_code="X")}

    captured_inputs: list[int] = []

    def fake_data_editor(df_in, **kwargs):
        captured_inputs.append(id(df_in))
        return df_in

    fake_st.data_editor = fake_data_editor
    container_cm = MagicMock()
    container_cm.__enter__ = lambda self: self
    container_cm.__exit__ = lambda self, *a: False
    empty_slot = MagicMock()
    empty_slot.container = MagicMock(return_value=container_cm)
    fake_st.empty = MagicMock(return_value=empty_slot)

    with patch.object(s3, "st", fake_st):
        s3._render_dp_block("X", dp_v1)
        first_input = captured_inputs[-1]

        # New DP instance → cache must be rebuilt. Rendering with dp_v2
        # should NOT reuse dp_v1's cached DataFrame.
        s3._render_dp_block("X", dp_v2)
        second_input = captured_inputs[-1]

    assert first_input != second_input, (
        "Step 3 must invalidate the cached grid when the DataProduct "
        "instance changes (e.g., after a Restart or Step 2 rebuild)."
    )


def test_step3_render_dp_block_chips_reflect_post_edit_selection():
    """Regression: the chip-strip + success banner must reflect the
    *post-edit* selection on the same render.

    Before the fix, the chip-strip rendered from ``current_cdes`` (the
    selection the user *had* before clicking) while the banner reflected the
    edited DataFrame returned by ``st.data_editor``. The two drifted by one
    click and users felt the tick "didn't register".

    Here we simulate a click that adds a CDE: ``cfg.cdes`` starts empty but
    the data_editor returns a DataFrame with one row marked as picked. Both
    the chip-strip *and* the banner must reference that one new pick, not
    the empty pre-edit list.
    """
    import pandas as pd

    import ui.step_03_cde_selection as s3
    from src.models import ColumnProfile, DataProduct, DataProductConfig

    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    profiles = {
        col: ColumnProfile(
            name=col, dtype="int64", column_type_group="integer",
            total_rows=2, null_count=0, null_pct=0.0,
            distinct_count=2, duplicate_count=0, sample_values=[1, 2],
        )
        for col in df.columns
    }
    dp = DataProduct(
        system_code="X", name="X_DP", df=df, source_tables=["t"],
        profiles=profiles,
    )

    fake_st = _make_fake_st()
    fake_st.session_state["configs"] = {"X": DataProductConfig(system_code="X")}

    # Simulate the user's click: editor returns ``B`` already ticked. The
    # function under test should derive ``cfg.cdes = ["B"]`` *and* drive
    # both the chip-strip and the success banner from that value.
    edited_df = pd.DataFrame({
        "CDE": [False, True],
        "Column": ["A", "B"],
        "Type": ["integer", "integer"],
        "Dtype": ["int64", "int64"],
        "Rows": [2, 2],
        "Null %": [0.0, 0.0],
        "Distinct": [2, 2],
        "Duplicates": [0, 0],
        "Sample": ["1, 2", "3, 4"],
    })
    fake_st.data_editor = MagicMock(return_value=edited_df)

    # Capture every chip-strip / banner emission so we can verify both
    # surfaces agree on the new selection.
    captured_markdowns: list[str] = []
    captured_successes: list[str] = []
    fake_st.markdown = MagicMock(
        side_effect=lambda t, **kw: captured_markdowns.append(t)
    )
    fake_st.success = MagicMock(
        side_effect=lambda t: captured_successes.append(t)
    )

    # ``st.empty`` and its ``.container()`` - both must yield a
    # context-manager that simply forwards calls to fake_st.
    empty_slot = MagicMock()
    container_cm = MagicMock()
    container_cm.__enter__ = lambda self: self
    container_cm.__exit__ = lambda self, *a: False
    empty_slot.container = MagicMock(return_value=container_cm)
    fake_st.empty = MagicMock(return_value=empty_slot)

    with patch.object(s3, "st", fake_st):
        s3._render_dp_block("X", dp)

    # cfg.cdes was updated from the edited DataFrame, not from the stale
    # empty input list.
    assert fake_st.session_state["configs"]["X"].cdes == ["B"]

    # Chip-strip reflects the *new* selection: exactly one chip, for B.
    chips = [m for m in captured_markdowns if 'class="dq-code brand"' in m]
    assert len(chips) == 1
    assert chips[0].count('class="dq-code brand"') == 1
    assert ">B" in chips[0]
    # Success widget is no longer used for the per-DP banner.
    assert captured_successes == []


def test_step3_build_profile_grid_sample_uses_distinct_values():
    """Step 3's ``Sample`` cell surfaces the first 3 *distinct* non-null
    values of each source column (preserving first-occurrence order), not
    the first 3 raw values from the profile - a column with lots of
    repeats still yields a useful preview of its domain."""
    import pandas as pd

    import ui.step_03_cde_selection as s3
    from src.models import ColumnProfile, DataProduct

    # Column A repeats "X" four times before introducing a new value; the
    # raw first-3 sample would be ["X", "X", "X"] but the distinct sample
    # must be ["X", "Y", "Z"].
    df = pd.DataFrame({
        "A": ["X", "X", "X", "X", "Y", "Z", "Y"],
        "B": [1, 1, 1, 1, 1, 1, 1],
    })
    profiles = {
        col: ColumnProfile(
            name=col, dtype="object", column_type_group="text",
            total_rows=len(df), null_count=0, null_pct=0.0,
            distinct_count=df[col].nunique(), duplicate_count=0,
            sample_values=list(df[col].head(5)),
        )
        for col in df.columns
    }
    dp = DataProduct(
        system_code="X", name="X_DP", df=df, source_tables=["t"],
        profiles=profiles,
    )
    grid = s3._build_profile_grid(dp, current_cdes=[], required={})

    a_sample = grid.loc[grid["Column"] == "A", "Sample"].iloc[0]
    assert a_sample == "X, Y, Z"
    # Column with a single distinct value caps at that one value.
    b_sample = grid.loc[grid["Column"] == "B", "Sample"].iloc[0]
    assert b_sample == "1"


def test_step3_distinct_sample_for_skips_nulls():
    """Null / NaN entries are dropped before deduping so a column whose
    first few rows are missing still surfaces real domain values."""
    import pandas as pd

    import ui.step_03_cde_selection as s3
    from src.models import DataProduct

    df = pd.DataFrame({"A": [None, None, "alpha", "alpha", "beta", "gamma"]})
    dp = DataProduct(
        system_code="X", name="X_DP", df=df, source_tables=["t"], profiles={},
    )
    assert s3._distinct_sample_for(dp, "A", 3) == ["alpha", "beta", "gamma"]


def test_step3_build_profile_grid_handles_missing_profile_gracefully():
    """A column without a profile entry still gets a row - defensive
    rendering for any data-product where the profiler missed a column."""
    import pandas as pd

    import ui.step_03_cde_selection as s3
    from src.models import DataProduct

    df = pd.DataFrame({"A": [1], "B": [2]})
    dp = DataProduct(
        system_code="X", name="X_DP", df=df, source_tables=["t"], profiles={},
    )
    grid = s3._build_profile_grid(dp, current_cdes=[], required={})
    assert list(grid["Column"]) == ["A", "B"]
    assert list(grid["Type"]) == ["-", "-"]
    assert list(grid["Sample"]) == ["", ""]


# ---------------------------------------------------------------------------
# Step 1: Restart button branch (Feature 3)
# ---------------------------------------------------------------------------

def test_step1_restart_click_calls_restart_app():
    """Step 1's nav row exposes a Restart button alongside Next; clicking it
    invokes ``restart_app`` so the user can wipe all selections."""
    import ui.step_01_system_selection as s1

    fake_st = _make_fake_st()
    # Step 1 calls ``st.columns(..., gap="medium")`` for the system cards
    # layout - extend the fake to swallow that kwarg.

    def columns_with_kwargs(spec, **_kw):
        n = spec if isinstance(spec, int) else len(spec)
        return [_fake_column() for _ in range(n)]

    fake_st.columns = columns_with_kwargs
    # Three button calls in Step 1's nav (now that Step 0 sits in front of
    # it): Back (1st, not clicked), Restart (2nd, clicked), Next (3rd,
    # not clicked). Restart must wire through to ``restart_app``.
    call_results = iter([False, True, False])
    fake_st.button = MagicMock(side_effect=lambda *a, **kw: next(call_results))
    fake_st.checkbox = MagicMock(return_value=False)

    # Stub the bordered-container context manager used inside the system
    # cards (``with st.container(border=True):``).
    fake_container = MagicMock()
    fake_container.__enter__ = lambda self: self
    fake_container.__exit__ = lambda self, *a: False
    fake_st.container = MagicMock(return_value=fake_container)

    fake_expander = MagicMock()
    fake_expander.__enter__ = lambda self: self
    fake_expander.__exit__ = lambda self, *a: False
    fake_st.expander = MagicMock(return_value=fake_expander)

    fake_st.session_state["selected_systems"] = []
    # Step 1's Restart now routes through the shared ``render_restart_button``
    # helper in utils.ui_components, so patch ``st`` there too (the confirm
    # button is the 2nd of the three nav button calls).
    with patch.object(s1, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_01_system_selection.restart_app") as mock_restart, \
         patch("ui.step_01_system_selection.next_step") as mock_next:
        s1.render()
    mock_restart.assert_called_once()
    mock_next.assert_not_called()


# ---------------------------------------------------------------------------
# step_02_data_product_review._nav Next click
# ---------------------------------------------------------------------------

def test_step2_nav_next_click():
    import ui.step_02_data_product_review as s2
    fake_st = _make_fake_st()
    fake_st.button = MagicMock(return_value=True)
    with patch.object(s2, "st", fake_st), \
         patch("utils.ui_components.st", fake_st), \
         patch("ui.step_02_data_product_review.next_step") as mock_next, \
         patch("ui.step_02_data_product_review.prev_step") as mock_prev:
        s2._nav(show_next=True)
        mock_next.assert_called()
        mock_prev.assert_called()


# ---------------------------------------------------------------------------
# step_04 "Apply all suggested DQRs" shortcut (per data product)
# ---------------------------------------------------------------------------

def test_step4_pending_suggestions_empty_when_all_applied():
    """When every suggested dimension is already assigned, the pending list
    is empty and the per-DP shortcut should render its "already applied"
    caption instead of the button."""
    # Build a tiny dp + matching cfg with every suggestion pre-applied.
    import pandas as pd

    import ui.step_04_dqr_assignment as s4
    from src.dqr_engine import suggest_assignments_for_cde
    from src.models import DataProduct, DataProductConfig
    from src.profiler import profile_dataframe
    df = pd.DataFrame({"PLANVIEW_ID": ["P1", "P2", "P3"]})
    dp = DataProduct(
        system_code="EPT", name="EPT", df=df,
        source_tables=["t"], profiles=profile_dataframe(df),
    )
    cfg = DataProductConfig(system_code="EPT", cdes=["PLANVIEW_ID"])
    for a in suggest_assignments_for_cde(dp.profiles["PLANVIEW_ID"]):
        cfg.assignments.append(a)

    pending = s4._pending_suggestions_for_dp(dp, cfg)
    assert pending == []


def test_step4_pending_suggestions_lists_only_missing_dimensions():
    """A suggestion whose ``dimension`` is already present in
    ``cfg.assignments`` for the CDE must NOT appear in the pending list, that's the contract that keeps the apply-all click idempotent."""
    import pandas as pd

    import ui.step_04_dqr_assignment as s4
    from src.dqr_engine import suggest_assignments_for_cde
    from src.models import DataProduct, DataProductConfig
    from src.profiler import profile_dataframe
    df = pd.DataFrame({"PLANVIEW_ID": ["P1", "P2", "P3"]})
    dp = DataProduct(
        system_code="EPT", name="EPT", df=df,
        source_tables=["t"], profiles=profile_dataframe(df),
    )
    suggested = suggest_assignments_for_cde(dp.profiles["PLANVIEW_ID"])
    # Apply only the first suggestion; the rest stay pending.
    cfg = DataProductConfig(
        system_code="EPT", cdes=["PLANVIEW_ID"], assignments=[suggested[0]],
    )

    pending_dims = [d for _cde, a in s4._pending_suggestions_for_dp(dp, cfg)
                    for d in [a.dimension]]
    assert suggested[0].dimension not in pending_dims
    # And every remaining suggested dimension must appear.
    for sug in suggested[1:]:
        assert sug.dimension in pending_dims


def test_step4_apply_all_button_appends_and_sets_session_state():
    """Clicking the per-DP shortcut appends every pending suggestion to
    ``cfg.assignments`` and pre-populates each suggestion's Apply-checkbox
    session-state key so the widgets honor the new state on this same
    render, no extra rerun required."""
    from unittest.mock import patch as _patch

    import pandas as pd

    import ui.step_04_dqr_assignment as s4
    from src.dqr_engine import suggest_assignments_for_cde
    from src.models import DataProduct, DataProductConfig
    from src.profiler import profile_dataframe
    df = pd.DataFrame({"PLANVIEW_ID": ["P1", "P2", "P3"]})
    dp = DataProduct(
        system_code="EPT", name="EPT", df=df,
        source_tables=["t"], profiles=profile_dataframe(df),
    )
    cfg = DataProductConfig(system_code="EPT", cdes=["PLANVIEW_ID"])

    fake_st = _make_fake_st(
        button_returns={"apply_all_suggestions_EPT": True},
    )
    with _patch.object(s4, "st", fake_st):
        s4._render_apply_all_suggestions_button("EPT", dp, cfg)

    # Every suggested dimension is now applied.
    expected_dims = {
        a.dimension for a in suggest_assignments_for_cde(dp.profiles["PLANVIEW_ID"])
    }
    assert {a.dimension for a in cfg.assignments} == expected_dims
    # And every suggestion's checkbox key is pre-set in session_state.
    for dim in expected_dims:
        key = f"EPT_PLANVIEW_ID_{dim}_enabled"
        assert fake_st.session_state.get(key) is True


def test_step4_apply_all_button_not_clicked_leaves_cfg_unchanged():
    """Without a click, the shortcut renders but has no side effects -
    ``cfg.assignments`` stays empty and no checkbox key is forced on."""
    from unittest.mock import patch as _patch

    import pandas as pd

    import ui.step_04_dqr_assignment as s4
    from src.models import DataProduct, DataProductConfig
    from src.profiler import profile_dataframe
    df = pd.DataFrame({"PLANVIEW_ID": ["P1", "P2"]})
    dp = DataProduct(
        system_code="EPT", name="EPT", df=df,
        source_tables=["t"], profiles=profile_dataframe(df),
    )
    cfg = DataProductConfig(system_code="EPT", cdes=["PLANVIEW_ID"])

    fake_st = _make_fake_st()
    fake_st.button = MagicMock(return_value=False)
    with _patch.object(s4, "st", fake_st):
        s4._render_apply_all_suggestions_button("EPT", dp, cfg)

    assert cfg.assignments == []
    assert not any(
        k.startswith("EPT_PLANVIEW_ID_") and k.endswith("_enabled")
        for k in fake_st.session_state.keys()
    )


def test_step4_apply_all_button_preserves_carried_params_from_suggestion():
    """The suggestion's profile-aware params (e.g. Accuracy pre-fills
    ``min_value`` / ``max_value`` from the column's profile) flow through
    to the appended assignment so the user gets sensible defaults without
    re-typing them."""
    from unittest.mock import patch as _patch

    import pandas as pd

    import ui.step_04_dqr_assignment as s4
    from src.models import DataProduct, DataProductConfig
    from src.profiler import profile_dataframe
    df = pd.DataFrame({"AMOUNT": [10.0, 20.0, 30.0, 40.0]})
    dp = DataProduct(
        system_code="EPT", name="EPT", df=df,
        source_tables=["t"], profiles=profile_dataframe(df),
    )
    cfg = DataProductConfig(system_code="EPT", cdes=["AMOUNT"])

    fake_st = _make_fake_st(
        button_returns={"apply_all_suggestions_EPT": True},
    )
    with _patch.object(s4, "st", fake_st):
        s4._render_apply_all_suggestions_button("EPT", dp, cfg)

    accuracy = next(
        (a for a in cfg.assignments if a.dimension == "Accuracy"), None,
    )
    assert accuracy is not None, "Accuracy should be one of the suggestions"
    assert accuracy.params.get("min_value") == 10.0
    assert accuracy.params.get("max_value") == 40.0


# ---------------------------------------------------------------------------
# step_03 "Select all CDEs required by Custom DQRs" shortcut
# ---------------------------------------------------------------------------

def _step3_render_harness(df, dp, cfg, fake_st):
    """Wire the streamlit fakes that ``_render_dp_block`` needs (``st.empty``,
    ``st.data_editor``, ``configs``) so a single render runs end-to-end.

    The fake data_editor echoes its input back so ``cfg.cdes`` ends up
    reflecting whatever ``Pick as CDE`` column the button code rebuilt into
    the cached base DataFrame."""
    fake_st.session_state["configs"] = {dp.system_code: cfg}

    captured_inputs: list = []

    def fake_data_editor(df_in, **kwargs):
        captured_inputs.append(df_in)
        return df_in

    fake_st.data_editor = fake_data_editor
    container_cm = MagicMock()
    container_cm.__enter__ = lambda self: self
    container_cm.__exit__ = lambda self, *a: False
    empty_slot = MagicMock()
    empty_slot.container = MagicMock(return_value=container_cm)
    fake_st.empty = MagicMock(return_value=empty_slot)
    return captured_inputs


def test_step3_select_all_required_button_unions_picks_in_source_order():
    """Clicking the 'Select all CDEs required by Custom DQRs' button picks
    every column flagged in the ``Custom DQRs`` cell as a CDE on the same
    render, in source-column order, while preserving any pre-existing
    manual picks (so the user doesn't lose CDEs they already chose)."""
    import pandas as pd

    import ui.step_03_cde_selection as s3
    from src.models import ColumnProfile, DataProduct, DataProductConfig

    df = pd.DataFrame({
        "CODE_OF_RESOURCE": [1],
        "STANDARD_ACTIVITY_BREAKDOWN": [2],
        "OTHER": [3],
        "WBC_LEVEL_1": [4],
    })
    profiles = {
        col: ColumnProfile(
            name=col, dtype="object", column_type_group="text",
            total_rows=1, null_count=0, null_pct=0.0,
            distinct_count=1, duplicate_count=0, sample_values=[1],
        )
        for col in df.columns
    }
    dp = DataProduct(
        system_code="EPT", name="EPT_DP", df=df, source_tables=["t"],
        profiles=profiles,
    )
    cfg = DataProductConfig(system_code="EPT", cdes=["OTHER"])

    fake_st = _make_fake_st()
    _step3_render_harness(df, dp, cfg, fake_st)
    select_all_key = f"cde_select_all_required_EPT_{id(dp)}"
    fake_st.button = MagicMock(
        side_effect=lambda *a, **kw: kw.get("key") == select_all_key
    )

    with patch.object(s3, "st", fake_st):
        s3._render_dp_block("EPT", dp)

    # OTHER (manual pick) is preserved; each EPT-Custom-DQR-required column
    # present in ``dp.df`` is added. CODE_OF_RESOURCE and
    # STANDARD_ACTIVITY_BREAKDOWN power E1/E3; WBC_LEVEL_1 powers E4/E5.
    # Order matches dp.df.columns so downstream displays stay deterministic.
    assert cfg.cdes == [
        "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN",
        "OTHER", "WBC_LEVEL_1",
    ]


def test_step3_select_all_required_button_not_pre_applied():
    """Without a click on the shortcut, ``cfg.cdes`` is left exactly as the
    user had it, the button only takes effect after the user clicks. This
    is the contract the user asked for: no pre-application."""
    import pandas as pd

    import ui.step_03_cde_selection as s3
    from src.models import ColumnProfile, DataProduct, DataProductConfig

    df = pd.DataFrame({
        "CODE_OF_RESOURCE": [1],
        "STANDARD_ACTIVITY_BREAKDOWN": [2],
        "OTHER": [3],
    })
    profiles = {
        col: ColumnProfile(
            name=col, dtype="object", column_type_group="text",
            total_rows=1, null_count=0, null_pct=0.0,
            distinct_count=1, duplicate_count=0, sample_values=[1],
        )
        for col in df.columns
    }
    dp = DataProduct(
        system_code="EPT", name="EPT_DP", df=df, source_tables=["t"],
        profiles=profiles,
    )
    cfg = DataProductConfig(system_code="EPT", cdes=["OTHER"])

    fake_st = _make_fake_st()
    _step3_render_harness(df, dp, cfg, fake_st)
    # Default: every button returns False (no click on the shortcut).
    fake_st.button = MagicMock(return_value=False)

    with patch.object(s3, "st", fake_st):
        s3._render_dp_block("EPT", dp)

    # Untouched: only the user's manual pick survives.
    assert cfg.cdes == ["OTHER"]


def test_step3_select_all_required_button_hidden_when_no_required_columns():
    """If no Custom DQR in the catalog declares required columns for this
    system, the shortcut is never instantiated - there's nothing for it to
    select. Asserts the button-key never appears in the captured calls."""
    import pandas as pd

    import ui.step_03_cde_selection as s3
    from src.models import ColumnProfile, DataProduct, DataProductConfig

    df = pd.DataFrame({"A": [1]})
    profiles = {
        "A": ColumnProfile(
            name="A", dtype="object", column_type_group="text",
            total_rows=1, null_count=0, null_pct=0.0,
            distinct_count=1, duplicate_count=0, sample_values=[1],
        )
    }
    dp = DataProduct(
        system_code="UNKNOWN_SYS", name="UNKNOWN_DP", df=df, source_tables=["t"],
        profiles=profiles,
    )
    cfg = DataProductConfig(system_code="UNKNOWN_SYS")

    fake_st = _make_fake_st()
    _step3_render_harness(df, dp, cfg, fake_st)
    captured_button_keys: list[str] = []

    def capture_button(label, **kw):
        captured_button_keys.append(kw.get("key") or "")
        return False

    fake_st.button = MagicMock(side_effect=capture_button)

    with patch.object(s3, "st", fake_st):
        s3._render_dp_block("UNKNOWN_SYS", dp)

    # required_by_rule is empty for an unknown system, so the shortcut is
    # not rendered. The _nav row outside this block renders its own buttons
    # but _render_dp_block itself instantiates none in this branch.
    assert not any("cde_select_all_required_" in k for k in captured_button_keys)


def test_step3_select_all_required_button_rebuilds_base_and_clears_editor():
    """The click handler must (a) rebuild the cached base DataFrame with
    the new ``Pick as CDE`` column set on every required row and (b) drop
    the editor's stored widget state so a fresh edit cycle starts on the
    next render. Without (a) the editor would keep showing the stale base;
    without (b) Streamlit's accumulated edits could override the new base."""
    import pandas as pd

    import ui.step_03_cde_selection as s3
    from src.models import ColumnProfile, DataProduct, DataProductConfig

    df = pd.DataFrame({
        "CODE_OF_RESOURCE": [1],
        "STANDARD_ACTIVITY_BREAKDOWN": [2],
        "OTHER": [3],
    })
    profiles = {
        col: ColumnProfile(
            name=col, dtype="object", column_type_group="text",
            total_rows=1, null_count=0, null_pct=0.0,
            distinct_count=1, duplicate_count=0, sample_values=[1],
        )
        for col in df.columns
    }
    dp = DataProduct(
        system_code="EPT", name="EPT_DP", df=df, source_tables=["t"],
        profiles=profiles,
    )
    cfg = DataProductConfig(system_code="EPT", cdes=[])

    fake_st = _make_fake_st()
    _step3_render_harness(df, dp, cfg, fake_st)
    # Pre-seed an editor-state entry to confirm the click handler clears it.
    editor_key = f"cde_grid_EPT_{id(dp)}"
    fake_st.session_state[editor_key] = {"edited_rows": {0: {"CDE": True}}}
    select_all_key = f"cde_select_all_required_EPT_{id(dp)}"
    fake_st.button = MagicMock(
        side_effect=lambda *a, **kw: kw.get("key") == select_all_key
    )

    with patch.object(s3, "st", fake_st):
        s3._render_dp_block("EPT", dp)

    # The editor widget state was cleared so it can re-read the rebuilt
    # base cleanly on the next render.
    assert editor_key not in fake_st.session_state
    # The rebuilt base DataFrame ticks the required columns.
    base_key = f"cde_grid_base_EPT_{id(dp)}"
    base = fake_st.session_state[base_key]
    picked = list(base.loc[base["CDE"], "Column"])
    assert "CODE_OF_RESOURCE" in picked
    assert "STANDARD_ACTIVITY_BREAKDOWN" in picked


# ---------------------------------------------------------------------------
# step_04_2 "Select all Custom DQRs" shortcut (per data product)
# ---------------------------------------------------------------------------

def test_step4_2_select_all_button_sets_every_rule_checkbox_in_session_state():
    """Clicking the per-DP 'Select all Custom DQRs' button must pre-populate
    every rule checkbox's ``session_state`` key to True before the rule
    cards render. Streamlit then honors the pre-set value on first widget
    instantiation, so every card displays ticked and the dp-block writer
    persists a CustomDQRAssignment for each rule."""
    from unittest.mock import patch as _patch

    import ui.step_04_2_custom_dqr as s4_2
    from config.custom_dqr_catalog import get_available_custom_dqr_rules
    from src.models import DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT",
        cdes=[
            # Cover every required column across EPT custom rules so the
            # CDE-coverage validation doesn't drown the test in gaps.
            "CODE_OF_RESOURCE", "STANDARD_ACTIVITY_BREAKDOWN",
            "CENTROID_DATE", "PLANVIEW_ID",
            "WBC_LEVEL_5", "WBC_LEVEL_1",
            "TOTAL_HOURS", "TOTAL_COST_USD", "TOTAL_COST_ESTIMATE_CURRENCY",
        ],
        custom_assignments=[],
    )

    select_all_key = "custom_select_all_EPT"

    def fake_button(label, *, key=None, **kwargs):
        return key == select_all_key

    # checkbox honors session_state if set, mirrors Streamlit semantics for
    # the post-click rerender path.
    def fake_checkbox(label, value=False, key=None, **kwargs):
        if key in fake_st.session_state:
            return bool(fake_st.session_state[key])
        return bool(value)

    fake_st = _make_fake_st()
    fake_st.button = fake_button
    fake_st.checkbox = fake_checkbox

    with _patch.object(s4_2, "st", fake_st):
        valid, gaps = s4_2._render_dp_block("EPT", cfg)

    rules = get_available_custom_dqr_rules("EPT")
    for r in rules:
        key = f"custom_EPT_{r.id}_enabled"
        assert fake_st.session_state.get(key) is True, (
            f"expected session_state[{key}] = True after select-all click"
        )
    assert {a.rule_id for a in cfg.custom_assignments} == {r.id for r in rules}
    assert valid is True
    assert gaps == []


def test_step4_2_select_all_button_not_pre_applied_without_click():
    """Without a click, the shortcut is rendered but has no side effects, no rule checkbox is forced True, and assignments reflect whatever the
    user already had in cfg.custom_assignments. The rule cards still
    lazy-init their session-state key from ``selected`` (False for rules
    not yet in cfg.custom_assignments), which is the idiomatic Streamlit
    pattern that suppresses the value-vs-session-state warning."""
    from unittest.mock import patch as _patch

    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg = DataProductConfig(
        system_code="EPT", cdes=[], custom_assignments=[],
    )

    fake_st = _make_fake_st()
    fake_st.button = MagicMock(return_value=False)

    with _patch.object(s4_2, "st", fake_st):
        valid, gaps = s4_2._render_dp_block("EPT", cfg)

    # No checkbox session_state key was forced to True, every key the
    # rule cards lazy-init lands as False (no rule was previously selected).
    truthy_enabled_keys = [
        k for k in fake_st.session_state.keys()
        if k.startswith("custom_EPT_")
        and k.endswith("_enabled")
        and fake_st.session_state[k]
    ]
    assert truthy_enabled_keys == []
    # And no assignment ended up persisted because every checkbox defaulted
    # to False (the fake's per-key default).
    assert cfg.custom_assignments == []
    assert valid is True
    assert gaps == []


def test_step4_2_select_all_button_does_not_render_for_dps_without_rules():
    """A data product without rules in the catalog skips the shortcut, the
    empty-state path returns early before the button is instantiated."""
    from unittest.mock import patch as _patch

    import ui.step_04_2_custom_dqr as s4_2
    from src.models import DataProductConfig

    cfg = DataProductConfig(system_code="UNKNOWN_DP", custom_assignments=[])
    captured_keys: list[str] = []

    def fake_button(label, *, key=None, **kwargs):
        captured_keys.append(key or "")
        return False

    fake_st = _make_fake_st()
    fake_st.button = fake_button

    with _patch.object(s4_2, "st", fake_st):
        valid, gaps = s4_2._render_dp_block("UNKNOWN_DP", cfg)

    assert "custom_select_all_UNKNOWN_DP" not in captured_keys
    assert valid is True
    assert gaps == []
