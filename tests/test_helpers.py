"""Tests for utils/helpers.py (pure functions and the Streamlit section_header)."""
from __future__ import annotations

from unittest.mock import patch

from utils.helpers import (
    distribute_equally,
    format_value,
    score_color,
    score_label,
    section_header,
)


def test_score_color_green():
    assert score_color(95, green_threshold=80, yellow_threshold=60) == "#16a34a"


def test_score_color_yellow():
    assert score_color(70, green_threshold=80, yellow_threshold=60) == "#eab308"


def test_score_color_red():
    assert score_color(10, green_threshold=80, yellow_threshold=60) == "#dc2626"


def test_score_label_green():
    assert "Green" in score_label(85, 80, 60)


def test_score_label_yellow():
    assert "Yellow" in score_label(70, 80, 60)


def test_score_label_red():
    assert "Red" in score_label(30, 80, 60)


def test_score_color_label_boundaries_are_inclusive():
    """The thresholds are inclusive lower bounds: a score exactly at the green
    threshold is green, one exactly at the yellow threshold is yellow, and
    anything below the yellow threshold is red. The interior-value tests above
    never touch the exact 80 / 60 edges - pin them here."""
    assert score_color(80, 80, 60) == "#16a34a"      # exactly green -> green
    assert "Green" in score_label(80, 80, 60)
    assert score_color(60, 80, 60) == "#eab308"      # exactly yellow -> yellow
    assert "Yellow" in score_label(60, 80, 60)
    assert score_color(79.999, 80, 60) == "#eab308"  # just below green -> yellow
    assert score_color(59.999, 80, 60) == "#dc2626"  # just below yellow -> red
    assert "Red" in score_label(59.999, 80, 60)


def test_distribute_equally_zero():
    assert distribute_equally(0) == []


def test_distribute_equally_negative():
    assert distribute_equally(-3) == []


def test_distribute_equally_one():
    assert distribute_equally(1) == [100.0]


def test_distribute_equally_three_sums_to_100():
    weights = distribute_equally(3)
    assert len(weights) == 3
    assert round(sum(weights), 2) == 100.0


def test_distribute_equally_spreads_residual_evenly():
    """Residual cents are distributed one per item, so the max difference
    between any two weights is at most 0.01."""
    weights = distribute_equally(7)
    assert sum(weights) == 100.0
    assert round(max(weights) - min(weights), 2) <= 0.01
    # First few items absorb the +0.01 cents; remaining items stay at base
    assert weights[0] >= weights[-1]


def test_distribute_equally_no_remainder_gives_perfectly_equal_weights():
    """When 100 / n is exact, all weights are identical."""
    for n in (2, 4, 5, 8, 10, 20, 25, 50, 100):
        weights = distribute_equally(n)
        assert len(set(weights)) == 1, f"n={n} should be perfectly equal"
        assert sum(weights) == 100.0


def test_distribute_equally_always_sums_to_exactly_100():
    """Sum must round to exactly 100 for every n, with at most 0.01 spread."""
    for n in range(1, 101):
        weights = distribute_equally(n)
        assert round(sum(weights), 2) == 100.0, f"n={n} sum={sum(weights)}"
        assert round(max(weights) - min(weights), 2) <= 0.01


def test_format_value_none():
    assert format_value(None) == "-"


def test_format_value_nan():
    assert format_value(float("nan")) == "-"


def test_format_value_large_float():
    assert format_value(1234.5) == "1,234.50"


def test_format_value_small_float_strips_zeros():
    # 1.5 -> "1.5000".rstrip("0") -> "1.5"
    assert format_value(1.5) == "1.5"


def test_format_value_integer_like_float():
    # 10.0 -> "10.0000" -> "10"
    assert format_value(10.0) == "10"


def test_format_value_string():
    assert format_value("hello") == "hello"


def test_format_value_int():
    assert format_value(42) == "42"


def test_section_header_without_subtitle():
    """section_header is a thin Streamlit wrapper; ensure it calls st.markdown."""
    with patch("utils.helpers.st") as mock_st:
        section_header("Title")
        mock_st.markdown.assert_called_once_with("### Title")
        mock_st.caption.assert_not_called()


def test_section_header_with_subtitle():
    with patch("utils.helpers.st") as mock_st:
        section_header("Title", "Sub")
        mock_st.markdown.assert_called_once_with("### Title")
        mock_st.caption.assert_called_once_with("Sub")
