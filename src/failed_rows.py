"""Failed rows of a scorecard: the data rows failing at least one evaluated rule.

:func:`failed_rows_frame` builds the table behind both Step 6 actions -
the CSV download and "Save failed rows" - and the scheduled job's write:
one row per failing data row, lowest score first, with only the columns
the rules work on:

- ``row_score``   - the row's combined 0-100 score;
- ``failed_rules``- ids of the rules the row fails (Standard ids are
  ``<CDE>::<Dimension>``, Custom ids are catalog codes);
- the key columns ``PLANVIEW_ID`` / ``ROW_ID`` when the DP has them;
- the CDE columns of the configuration;
- the reference-dataset columns the Custom rules compared against (same
  join as the Step 6 exports, suffixed ``[<dataset>]``).

Rules that were not computed / not evaluated produce no flags and so never
mark a row as failed. ``max_rows`` (``SETTINGS.fails_max_rows``, 0 = all)
caps the frame; the full count is returned alongside.

:func:`save_failed_rows_for_run` persists the frame as *the* content of
the (domain, DP)'s ``DQS_FAILS_<DOMAIN>_<DP>`` table (previous run
replaced) - see :func:`src.persistence.save_failed_rows`. It is called
on demand (Step 6 button) and by the scheduled job, never automatically
on a dashboard render: for a large DP the write takes minutes.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import pandas as pd

from config.settings import SETTINGS
from config.systems import SHARED_KEY
from src.custom_dqr_engine import evaluate_custom_rules
from src.dqr_engine import evaluate_all_safe
from src.persistence import list_runs, save_failed_rows

logger = logging.getLogger(__name__)

_ROW_ID_COLUMN = "ROW_ID"
SCORE_COLUMN = "row_score"
RULES_COLUMN = "failed_rules"


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


def _key_and_cde_columns(dp, config) -> List[str]:
    columns = [SHARED_KEY, _ROW_ID_COLUMN, *config.cdes]
    return [c for c in dict.fromkeys(columns) if c in dp.df.columns]


def failed_rows_frame(dp, result, config,
                      max_rows: int = 0) -> Tuple[pd.DataFrame, int]:
    """``(frame, total_failed)``: the failing rows (at most ``max_rows``
    when > 0), lowest score first, and how many rows fail in total."""
    # Imported lazily: the reference-column join lives with the exports.
    from ui.step_06._export import _reference_columns_for_export

    flags = _pass_flags(dp, config)
    if flags.shape[1] == 0:
        return pd.DataFrame(), 0
    failing = ~flags.all(axis=1)
    total = int(failing.sum())
    if total == 0:
        return pd.DataFrame(), 0

    scores = result.row_scores.reindex(dp.df.index)
    keep = scores[failing].sort_values(kind="stable").index
    if max_rows > 0:
        keep = keep[:max_rows]
    rule_ids = flags.columns.to_numpy()
    frame = dp.df.loc[keep, _key_and_cde_columns(dp, config)].copy()
    frame.insert(0, RULES_COLUMN, [
        rule_ids[~passed].tolist()
        for passed in flags.loc[keep].to_numpy(dtype=bool)
    ])
    frame.insert(0, SCORE_COLUMN, scores.loc[keep].round(2))
    references = _reference_columns_for_export(dp, config)
    for column in references.columns:
        frame[column] = references.loc[keep, column]
    return frame, total


def frame_to_records(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    """The persistence rows of :func:`failed_rows_frame`'s output:
    ``{planview_id, row_key, row_score, failed_rules, row_data}`` with
    ``row_data`` holding every other column (NaN -> null)."""
    if frame.empty:
        return []
    data_cols = [c for c in frame.columns
                 if c not in (SCORE_COLUMN, RULES_COLUMN, SHARED_KEY, _ROW_ID_COLUMN)]
    data = frame[data_cols].astype(object)
    data = data.where(data.notna(), None).to_dict("records")

    def _text(column: str, fallback) -> List[Optional[str]]:
        if column not in frame.columns:
            return list(fallback)
        return [None if pd.isna(v) else str(v) for v in frame[column]]

    planview = _text(SHARED_KEY, [None] * len(frame))
    row_keys = _text(_ROW_ID_COLUMN, (str(i) for i in frame.index))
    scores = frame[SCORE_COLUMN].tolist()
    rules = frame[RULES_COLUMN].tolist()
    return [
        {
            "planview_id": planview[i],
            "row_key": row_keys[i],
            "row_score": None if pd.isna(scores[i]) else float(scores[i]),
            "failed_rules": list(rules[i]),
            "row_data": data[i],
        }
        for i in range(len(frame))
    ]


def current_run_id(dp_code: str, result) -> str:
    """The DQS_RUNS id of the run ``result`` belongs to: the DP's latest
    persisted run when its result fingerprint matches, else a fresh
    ``unrecorded_...`` id (history off, or the run was never recorded)."""
    from src.run_history import result_fingerprint

    last = list_runs(dp_code=dp_code, limit=1)
    if last:
        payload = last[-1].get("payload") or {}
        if payload.get("result_fingerprint") == result_fingerprint(result):
            return str(payload.get("id") or "")
    stamp = datetime.now().isoformat(timespec="seconds")
    return f"unrecorded_{stamp}_{dp_code}"


def save_failed_rows_for_run(domain_code: str, dp_code: str, dp, result, config,
                             config_hash: str = "",
                             run_id: Optional[str] = None,
                             frame: Optional[Tuple[pd.DataFrame, int]] = None,
                             progress: Optional[Callable[[int, int], None]] = None,
                             ) -> Tuple[int, int]:
    """Replace the (domain, DP)'s failed-rows table with this scorecard's
    failing rows. Returns ``(rows written, total failing)``.

    ``frame`` is an already computed :func:`failed_rows_frame` result (the
    UI reuses one for the CSV and the save); ``progress(done, total)`` is
    reported after every chunk written. Raises on a storage failure (the
    callers - a button, the job - report it), unlike the fire-and-forget
    run history.
    """
    if frame is None:
        frame = failed_rows_frame(dp, result, config, SETTINGS.fails_max_rows)
    table, total = frame
    rows = frame_to_records(table)
    if run_id is None:
        run_id = current_run_id(dp_code, result)
    if not save_failed_rows(domain_code, dp_code, run_id, rows, total,
                            config_hash=config_hash, progress=progress):
        raise RuntimeError(
            f"Could not write the failed rows of {dp_code} - see the app log "
            "(is the DQS_FAILS table created and granted?)")
    logger.info("%s: %d of %d failed rows saved (run %s)", dp_code, len(rows),
                total, run_id)
    return len(rows), total
