# pyright: reportArgumentType=false
"""Reusable validators shared by the custom DQR rule families.

- :func:`validate_completeness_rule`: row passes when every required column
  is non-null and non-blank (used by E1, E4, etc.).
- :func:`validate_referential_integrity_rule`: row passes when the source
  value resolves against a reference dataset column (used by E7, A1, AC1).
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from src.custom_dqr._shared import _is_filled


def validate_completeness_rule(
    df: pd.DataFrame, required_columns: Iterable[str]
) -> pd.Series:
    """A row passes when every column in ``required_columns`` is non-null and
    non-blank. If any required column is absent from ``df`` the rule fails
    for every row (the dataset is structurally incomplete)."""
    required = list(required_columns)
    if any(col not in df.columns for col in required):
        return pd.Series(False, index=df.index)
    ok = pd.Series(True, index=df.index)
    for col in required:
        ok &= _is_filled(df[col])
    return ok


def validate_referential_integrity_rule(
    source_df: pd.DataFrame,
    source_column: str,
    reference_df: pd.DataFrame,
    reference_column: str,
) -> pd.Series:
    """A row passes when ``source_df[source_column]`` is non-null, non-blank,
    *and* its (string-stripped) value appears in
    ``reference_df[reference_column]``.

    Missing source/reference columns make every row fail, the integrity
    check cannot be applied to data that doesn't exist. To signal a missing
    *dataset* (vs. a missing column) callers should raise
    :class:`CustomRuleNotEvaluated` before invoking this validator.
    """
    if source_column not in source_df.columns:
        return pd.Series(False, index=source_df.index)
    if reference_column not in reference_df.columns:
        return pd.Series(False, index=source_df.index)

    s = source_df[source_column]
    fill_ok = _is_filled(s)
    ref_values = (
        reference_df[reference_column]
        .dropna()
        .astype(str)
        .str.strip()
    )
    in_ref = s.astype(str).str.strip().isin(set(ref_values))
    return fill_ok & in_ref
