# pyright: reportArgumentType=false
"""
Column profiling utilities.

Produces a ColumnProfile for each column: null counts/pct, dtype group,
distinct count, duplicate count, sample values, min/max.
"""
from __future__ import annotations

from typing import Dict

import pandas as pd

from config.dqr_catalog import (
    COLUMN_TYPE_BOOLEAN,
    COLUMN_TYPE_CATEGORICAL,
    COLUMN_TYPE_DATE,
    COLUMN_TYPE_DATETIME,
    COLUMN_TYPE_FLOAT,
    COLUMN_TYPE_ID,
    COLUMN_TYPE_INTEGER,
    COLUMN_TYPE_NUMERIC,
    COLUMN_TYPE_STRING,
)
from src.models import ColumnProfile


def classify_column(series: pd.Series, col_name: str) -> str:
    """Return one of the COLUMN_TYPE_* groups for this series."""
    name_lower = (col_name or "").lower()
    # Heuristic: columns whose name ends with _id, equals "id", or
    # contains "planview" are treated as identifiers
    if name_lower.endswith("_id") or name_lower == "id" or "planview" in name_lower:
        return COLUMN_TYPE_ID

    dtype = series.dtype

    if pd.api.types.is_bool_dtype(dtype):
        return COLUMN_TYPE_BOOLEAN
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return COLUMN_TYPE_DATETIME
    if pd.api.types.is_integer_dtype(dtype):
        return COLUMN_TYPE_INTEGER
    if pd.api.types.is_float_dtype(dtype):
        return COLUMN_TYPE_FLOAT
    if pd.api.types.is_numeric_dtype(dtype):
        return COLUMN_TYPE_NUMERIC
    if isinstance(dtype, pd.CategoricalDtype):
        return COLUMN_TYPE_CATEGORICAL

    # Object/string: try to detect low-cardinality -> categorical
    non_null = series.dropna()
    if len(non_null) > 0:
        # Try datetime parse on a sample (silently - heuristic probe only).
        # Only suppress the categories pandas actually emits from
        # ``to_datetime`` so unrelated warnings (e.g. real deprecation
        # signals from other libs running in the same thread) still surface.
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning)
            warnings.filterwarnings("ignore", category=FutureWarning)
            try:
                sample = non_null.iloc[: min(100, len(non_null))]
                parsed = pd.to_datetime(sample, errors="raise", format="mixed")
                if len(parsed) > 0 and parsed.notna().all():
                    return COLUMN_TYPE_DATETIME
            except Exception:  # nosec B110 - best-effort datetime sniff; a parse failure just means "not a datetime column", so we deliberately fall through to the categorical/string heuristics below
                pass
        ratio = non_null.nunique(dropna=True) / max(1, len(non_null))
        if ratio < 0.1 and non_null.nunique(dropna=True) <= 50:
            return COLUMN_TYPE_CATEGORICAL
    return COLUMN_TYPE_STRING


def _safe_min(series: pd.Series):
    try:
        return series.dropna().min()
    except Exception:
        return None


def _safe_max(series: pd.Series):
    try:
        return series.dropna().max()
    except Exception:
        return None


def profile_column(df: pd.DataFrame, col: str) -> ColumnProfile:
    series = df[col]
    total = len(series)
    nulls = int(series.isna().sum())
    null_pct = (nulls / total * 100.0) if total else 0.0
    distinct = int(series.nunique(dropna=True))
    # Duplicate count = (non-null count) - distinct count
    non_null_count = total - nulls
    duplicate_count = max(0, non_null_count - distinct)

    sample = series.dropna().head(5).tolist()
    # Convert numpy/pandas types to native for cleaner display
    sample = [s.item() if hasattr(s, "item") else s for s in sample]

    col_type_group = classify_column(series, col)

    min_v = _safe_min(series) if col_type_group in (
        COLUMN_TYPE_INTEGER, COLUMN_TYPE_FLOAT, COLUMN_TYPE_NUMERIC,
        COLUMN_TYPE_DATETIME, COLUMN_TYPE_DATE,
    ) else None
    max_v = _safe_max(series) if col_type_group in (
        COLUMN_TYPE_INTEGER, COLUMN_TYPE_FLOAT, COLUMN_TYPE_NUMERIC,
        COLUMN_TYPE_DATETIME, COLUMN_TYPE_DATE,
    ) else None

    return ColumnProfile(
        name=col,
        dtype=str(series.dtype),
        column_type_group=col_type_group,
        total_rows=total,
        null_count=nulls,
        null_pct=round(null_pct, 2),
        distinct_count=distinct,
        duplicate_count=duplicate_count,
        sample_values=sample,
        min_value=min_v,
        max_value=max_v,
    )


def profile_dataframe(df: pd.DataFrame) -> Dict[str, ColumnProfile]:
    return {col: profile_column(df, col) for col in df.columns}


def profiles_to_table(profiles: Dict[str, ColumnProfile]) -> pd.DataFrame:
    """Convert profiles dict to a pandas DataFrame for Streamlit display."""
    rows = []
    for p in profiles.values():
        rows.append({
            "Column": p.name,
            "Dtype": p.dtype,
            "Type Group": p.column_type_group,
            "Rows": p.total_rows,
            "Nulls": p.null_count,
            "Null %": p.null_pct,
            "Distinct": p.distinct_count,
            "Duplicates": p.duplicate_count,
            "Sample": ", ".join(str(v) for v in p.sample_values[:3]),
        })
    return pd.DataFrame(rows)
