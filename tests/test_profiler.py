"""Tests for the profiler module."""
import pandas as pd

from config.dqr_catalog import (
    COLUMN_TYPE_CATEGORICAL,
    COLUMN_TYPE_DATETIME,
    COLUMN_TYPE_FLOAT,
    COLUMN_TYPE_ID,
)
from src.profiler import classify_column, profile_column, profile_dataframe


def test_classify_id_column(sample_df):
    assert classify_column(sample_df["PLANVIEW_ID"], "PLANVIEW_ID") == COLUMN_TYPE_ID


def test_classify_float_column(sample_df):
    assert classify_column(sample_df["AMOUNT"], "AMOUNT") == COLUMN_TYPE_FLOAT


def test_classify_datetime_column(sample_df):
    assert classify_column(sample_df["DATE_COL"], "DATE_COL") == COLUMN_TYPE_DATETIME


def test_classify_low_cardinality_becomes_categorical():
    s = pd.Series(["A", "B", "A", "A", "B", "B"] * 5)
    # 2 distinct values in 30 rows -> categorical
    assert classify_column(s, "CAT") == COLUMN_TYPE_CATEGORICAL


def test_profile_counts_nulls_and_dups(sample_df):
    p = profile_column(sample_df, "PLANVIEW_ID")
    assert p.total_rows == 5
    assert p.null_count == 1
    # 4 non-null values, 3 distinct -> 1 duplicate
    assert p.distinct_count == 3
    assert p.duplicate_count == 1


def test_profile_dataframe_all_columns(sample_df):
    profiles = profile_dataframe(sample_df)
    assert set(profiles.keys()) == set(sample_df.columns)
    for p in profiles.values():
        assert p.total_rows == 5
