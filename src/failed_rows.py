"""Failed rows of a run: the data rows failing at least one evaluated rule.

Companion of the run history: whenever :func:`src.run_history.record_run_if_new`
records a run, the rows behind its non-passing results are stored too, in
one ``DQS_FAILS_<DOMAIN>_<DP>`` table per (domain, data product) - see
:func:`src.persistence.save_failed_rows`. ``RUN_ID`` there is the DQS_RUNS
payload ``id``, so the two join one-to-many.

One record per failing data row:

- ``planview_id`` - the project key, when the DP carries it;
- ``row_key``     - ``ROW_ID`` when the DP has one, else the row's position
  in the data product;
- ``row_score``   - the row's combined 0-100 score;
- ``failed_rules``- ids of the rules the row fails (Standard ids are
  ``<CDE>::<Dimension>``, Custom ids are catalog codes);
- ``row_data``    - the row's values for the CDEs and the columns the
  Custom rules read (not the whole, wide data product row).

Rules that were not computed / not evaluated produce no flags and so never
mark a row as failed. At most ``SETTINGS.fails_max_rows`` rows are kept per
run, lowest score first; the full count travels as ``total_failed_rows``.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import pandas as pd

from config.settings import SETTINGS
from config.systems import SHARED_KEY
from src.custom_dqr_engine import evaluate_custom_rules
from src.dqr_engine import evaluate_all_safe
from src.persistence import save_failed_rows

logger = logging.getLogger(__name__)

_ROW_ID_COLUMN = "ROW_ID"


def _pass_flags(dp, config) -> pd.DataFrame:
    """Per-row pass flags (True = pass), one column per evaluated rule."""
    parts: List[pd.DataFrame] = []
    if config.assignments:
        parts.append(evaluate_all_safe(dp.df, config.assignments, dp.profiles)[0])
    if config.custom_assignments:
        parts.append(evaluate_custom_rules(
            dp.df, config.custom_assignments, dp.system_code)[0])
    parts = [p for p in parts if p.shape[1]]
    if not parts:
        return pd.DataFrame(index=dp.df.index)
    return pd.concat(parts, axis=1)


def _data_columns(dp, config) -> List[str]:
    """CDEs plus the columns the selected Custom rules read."""
    from config.custom_dqr_catalog import (
        effective_required_columns,
        get_available_custom_dqr_rules,
    )

    columns = list(config.cdes)
    if config.custom_assignments:
        catalog = {r.id: r for r in get_available_custom_dqr_rules(
            dp.system_code, include_inactive=True)}
        for a in config.custom_assignments:
            rule = catalog.get(a.rule_id)
            if rule is not None:
                columns.extend(effective_required_columns(
                    rule, getattr(a, "params", None) or {}).values())
    return [c for c in dict.fromkeys(columns) if c in dp.df.columns]


def collect_failed_rows(dp, result, config,
                        max_rows: int) -> Tuple[List[Dict[str, Any]], int]:
    """``(rows, total_failed)``: the ``max_rows`` lowest-scoring failing
    rows as plain dicts, and how many rows fail in total."""
    flags = _pass_flags(dp, config)
    if flags.shape[1] == 0:
        return [], 0
    failing = ~flags.all(axis=1)
    total = int(failing.sum())
    if total == 0:
        return [], 0

    scores = result.row_scores.reindex(dp.df.index)
    keep = scores[failing].sort_values(kind="stable").index[:max_rows]
    subset = dp.df.loc[keep]
    rule_ids = flags.columns.to_numpy()
    failed_rules = [rule_ids[~passed].tolist()
                    for passed in flags.loc[keep].to_numpy(dtype=bool)]
    data = subset[_data_columns(dp, config)].astype(object)
    data = data.where(data.notna(), None).to_dict("records")

    def _text(column: str, fallback) -> List[Any]:
        if column not in subset.columns:
            return list(fallback)
        return [None if pd.isna(v) else str(v) for v in subset[column]]

    planview = _text(SHARED_KEY, [None] * len(keep))
    row_keys = _text(_ROW_ID_COLUMN, (str(i) for i in keep))
    rows = [
        {
            "planview_id": planview[i],
            "row_key": row_keys[i],
            "row_score": None if pd.isna(score) else round(float(score), 2),
            "failed_rules": failed_rules[i],
            "row_data": data[i],
        }
        for i, score in enumerate(scores.loc[keep])
    ]
    return rows, total


def record_failed_rows(run_id: str, dp_code: str, domain_code: str, dp,
                       result, config, config_hash: str = "") -> bool:
    """Store the failed rows of the just-recorded run ``run_id``.

    Fire-and-forget like the rest of persistence: returns False (and logs)
    instead of raising. Skipped when the feature is off
    (``DQS_FAILS_MAX_ROWS=0``) or the run has no domain (no table to
    write to).
    """
    max_rows = SETTINGS.fails_max_rows
    if max_rows <= 0 or not domain_code:
        return False
    try:
        rows, total = collect_failed_rows(dp, result, config, max_rows)
    except Exception:
        logger.warning("Failed-rows collection failed for %s", dp_code,
                       exc_info=True)
        return False
    if total > len(rows):
        logger.info("%s run %s: storing %d of %d failed rows (DQS_FAILS_MAX_ROWS)",
                    dp_code, run_id, len(rows), total)
    return save_failed_rows(domain_code, dp_code, run_id, rows, total,
                            config_hash=config_hash)
