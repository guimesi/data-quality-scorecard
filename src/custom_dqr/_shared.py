# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false
"""Shared primitives for the custom DQR rule families.

Holds the dependency-free helpers and exceptions consumed by every rule
module (``_ept_rules``, ``_adr_rules``, ``_acce_rules``) and by the
dispatcher. The split keeps the per-family rule modules import-free of
each other.

Pyright pragmas: pandas-stubs typing noise (``df[col]`` typed as
``Series | DataFrame``) - see ``_adr_rules.py`` for the full rationale.
"""
from __future__ import annotations

import inspect
from functools import lru_cache
from typing import Callable, Dict, Tuple, TypedDict


class SegmentReferenceConfig(TypedDict):
    """Shape of the ``*_SEGMENT_REFERENCE`` dicts (one per parametric rule).

    Documents what :func:`_resolve_planview_segment_map` expects so pyright
    can carry the inner types through the function body. The dict literals
    in the per-family modules (e.g. ``EPT_E6_SEGMENT_REFERENCE``) match
    this shape verbatim.
    """
    reference_dataset: str
    reference_column: str
    segment_columns: Tuple[str, ...]

import numpy as np
import pandas as pd


@lru_cache(maxsize=None)
def _check_supports_params(check: Callable) -> bool:
    """True when a custom rule's ``check`` callable declares a ``params``
    parameter and can therefore be driven from ``CustomDQRAssignment.params``.
    Cached because the catalog is static and inspect.signature is non-trivial.
    """
    try:
        return "params" in inspect.signature(check).parameters
    except (TypeError, ValueError):
        return False


class CustomRuleNotEvaluated(Exception):
    """Raised by a custom rule's ``check`` function when its dependencies
    (e.g. a reference dataset) are unavailable. The dispatcher records the
    reason and surfaces a "not evaluated" state in Step 6, the rule must
    never silently pass when its inputs are missing.
    """


def _coerce_threshold(value: object, default: float) -> float:
    """Return ``value`` as a float when it's a finite, positive number;
    otherwise return ``default``. Used by every statistical-outlier check
    to read its user-customizable threshold from
    ``CustomDQRAssignment.params`` without blowing up on stale / malformed
    entries (e.g. a leftover string from a UI re-render). The lower bound
    is "positive" because both percentile (0,1] and IQR-multiplier (>0)
    inputs need it; a zero or negative threshold would silently disable
    the rule."""
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not np.isfinite(f) or f <= 0:
        return default
    return f


def _is_filled(series: pd.Series) -> pd.Series:
    """Return True for rows where ``series`` is non-null and (if string-like)
    not blank/whitespace-only. Same semantics as the shelf Completeness rule
    with ``allow_empty_string=False``.
    """
    result = series.notna()
    if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
        result &= series.astype(str).str.strip().ne("")
    return result


def _resolve_planview_segment_map(
    reference_config: SegmentReferenceConfig, rule_label: str
) -> Dict[str, Tuple[str, str]]:
    """Build the ``PLANVIEW_ID → (E05_DEPARTMENT, BUSINESS)`` lookup used by
    the project-type segmentation toggle on E6, A7, A8, AC7 and AC8. Every
    one of those rules joins PLANVIEW_ID to the same Planview reference
    table and reads the same segment columns, so the resolution logic is
    shared across families.

    ``reference_config`` carries the same shape as ``EPT_E6_SEGMENT_REFERENCE``
    et al.: ``reference_dataset``, ``reference_column``, ``segment_columns``.
    ``rule_label`` is prefixed onto raised errors so the user can tell
    *which* rule's segmentation is failing.

    Raises :class:`CustomRuleNotEvaluated` when the reference dataset is
    unavailable (or its required columns are missing) so the segmented mode
    never silently degrades to a no-op. The non-segmented paths keep their
    legacy behaviour and never call this helper.
    """
    from src.reference_data import (
        get_reference_dataset,
        get_reference_dataset_error,
    )

    ref_name = reference_config["reference_dataset"]
    reference_df = get_reference_dataset(ref_name)
    if reference_df is None:
        cached_error = get_reference_dataset_error(ref_name)
        detail = f": {cached_error}" if cached_error else ""
        raise CustomRuleNotEvaluated(
            f"{rule_label}: '{ref_name}' reference dataset is unavailable"
            f"{detail}; project-type segmentation cannot be applied."
        )

    ref_col = reference_config["reference_column"]
    seg_cols = reference_config["segment_columns"]
    missing = [c for c in (ref_col, *seg_cols) if c not in reference_df.columns]
    if missing:
        raise CustomRuleNotEvaluated(
            f"{rule_label}: '{ref_name}' is missing required columns "
            f"{missing}; project-type segmentation cannot be applied."
        )

    # Pre-clean once: drop rows where the key OR any segment column is
    # null/blank, and pre-strip every value. The resulting dict's
    # ``.get(pv)`` returns either a fully-resolved ``(dept, business)``
    # tuple of stripped strings, or ``None``, callers never need to
    # re-check fillness per-row, which matters because A7 / A8 may face
    # ADR's ~866k-row scale.
    ref = (
        reference_df[[ref_col, *seg_cols]]
        .dropna(subset=[ref_col, *seg_cols])
        .drop_duplicates(subset=[ref_col])
    )
    if ref.empty:
        return {}
    # Cast and strip every column once (vectorized), the per-row
    # whitespace-blank check below is a `len(stripped) > 0` test.
    stripped = {
        c: ref[c].astype(object).astype(str).str.strip()
        for c in (ref_col, *seg_cols)
    }
    keep = stripped[ref_col].ne("")
    for c in seg_cols:
        keep &= stripped[c].ne("")
    if not keep.any():
        return {}
    keys = stripped[ref_col][keep]
    seg_pairs = list(zip(*(stripped[c][keep] for c in seg_cols)))
    return dict(zip(keys, seg_pairs))
