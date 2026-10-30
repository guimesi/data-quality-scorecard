"""Floored score / pass-rate formatting (``src.formatting``).

A rule failing 179 of 835,280 rows passes 99.979% of them; rounded to one
decimal that read ``100.0%`` next to a non-empty failed-rows list. Scores
are now floored to two decimals, so ``100.00`` means "nothing failed".
"""
from __future__ import annotations

import math

import pytest

from src.formatting import PCT_COLUMN_FORMAT, floor_pct, fmt_pct, fmt_score


@pytest.mark.parametrize("value, expected", [
    (100.0, 100.0),
    (99.97857, 99.97),          # 179 fails of 835,280 rows - never 100
    (99.99785, 99.99),          # 18 fails of 835,280 rows
    (99.999999, 99.99),
    (96.1, 96.1),               # float repr is exact: no 96.09 artefact
    (58.7, 58.7),
    (0.0, 0.0),
    (0.004, 0.0),
    (12.345, 12.34),
    ("75.5", 75.5),             # numeric strings coerce
])
def test_floor_pct_floors_to_two_decimals(value, expected):
    assert floor_pct(value) == pytest.approx(expected)


def test_floor_pct_respects_decimals_argument():
    assert floor_pct(99.97857, 1) == 99.9
    assert floor_pct(99.97857, 0) == 99.0
    assert floor_pct(99.97857, 4) == 99.9785


def test_floor_pct_keeps_missing_values_distinct():
    assert floor_pct(None) is None
    assert floor_pct("n/a") is None
    assert math.isnan(floor_pct(float("nan")))
    assert floor_pct(float("inf")) == float("inf")


def test_fmt_score_and_fmt_pct_render_fixed_two_decimals():
    assert fmt_score(99.97857) == "99.97"
    assert fmt_score(100.0) == "100.00"
    assert fmt_score(75.0) == "75.00"
    assert fmt_pct(99.99785) == "99.99%"
    assert fmt_pct(100) == "100.00%"
    assert fmt_pct(0) == "0.00%"


def test_fmt_helpers_render_missing_values_as_text():
    assert fmt_score(None) == "n/a"
    assert fmt_pct(float("nan")) == "n/a"
    assert fmt_pct(None, missing="-") == "-"


def test_hundred_percent_only_when_nothing_failed():
    total = 835_280
    for fails in (1, 18, 179, 197):
        assert fmt_pct((total - fails) / total * 100) != "100.00%"
    assert fmt_pct(total / total * 100) == "100.00%"


def test_column_format_matches_the_text_helpers():
    assert PCT_COLUMN_FORMAT == "%.2f%%"
    assert (PCT_COLUMN_FORMAT % floor_pct(99.97857)) == fmt_pct(99.97857)
