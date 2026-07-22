"""Run-history service (phase 1): auto-persisted scorecard snapshots.

UI-free layer between Step 6 and :mod:`src.persistence`. Every dashboard
render records one snapshot per Data Product - unless nothing changed
since the last persisted run - so the History tab can show a score trend,
a "what changed" diff against the previous run, and a drop alert, all
surviving Restart and new sessions.

Two fingerprints drive the dedup:

- :func:`config_fingerprint` - stable hash of the scoring configuration
  (CDEs, rules, params, weights, sources). Stored on the run record so
  readers can tell "the data changed" apart from "the config changed".
- :func:`result_fingerprint` - hash of the scoring outcome. A rerun with
  identical config *and* identical result records nothing.

Snapshots reuse :func:`src.ml_lab.snapshot_scorecard`, so persisted runs
are directly consumable by the ML Lab's Run History / drift tooling.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from src.persistence import list_runs, save_run


def _sha16(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def config_fingerprint(config) -> str:
    """Stable 16-hex-char hash of everything that affects scoring.

    Assignments are sorted by rule id so a mere reordering in session
    state does not read as a configuration change.
    """
    canonical = {
        "cdes": sorted(config.cdes),
        "assignments": sorted(
            (
                {
                    "cde": a.cde_column,
                    "dimension": a.dimension,
                    "weight": round(float(a.weight), 6),
                    "params": a.params or {},
                }
                for a in config.assignments
            ),
            key=lambda d: (d["cde"], d["dimension"]),
        ),
        "custom_assignments": sorted(
            (
                {
                    "rule_id": a.rule_id,
                    "weight": round(float(a.weight), 6),
                    "params": a.params or {},
                }
                for a in config.custom_assignments
            ),
            key=lambda d: d["rule_id"],
        ),
        "sources": config.effective_dqr_sources(),
        "source_weights": {
            k: round(float(v), 6)
            for k, v in config.effective_source_weights().items()
        },
    }
    return _sha16(canonical)


def result_fingerprint(result) -> str:
    """16-hex-char hash of the scoring outcome (rounded to avoid float
    noise re-recording identical runs)."""
    canonical = {
        "overall": round(float(result.overall_score), 4),
        "total_rows": int(result.total_rows),
        "buckets": [int(result.rows_green), int(result.rows_yellow),
                    int(result.rows_red)],
        "rule_pass_rates": {
            k: round(float(v), 4) for k, v in result.rule_pass_rates.items()
        },
        "custom_rule_pass_rates": {
            k: round(float(v), 4)
            for k, v in result.custom_rule_pass_rates.items()
        },
    }
    return _sha16(canonical)


def record_run_if_new(dp_code: str, dp, result, config,
                      domain_code: str = "") -> bool:
    """Persist a snapshot of this run unless it duplicates the last one.

    Returns True when a new run was recorded. Dedup key = (config
    fingerprint, result fingerprint) of the most recent persisted run for
    this DP - Streamlit reruns of an unchanged dashboard record nothing,
    while either a config edit or a data change records a new run.
    Storage failures degrade to False (persistence is fire-and-forget).
    """
    # Imported lazily: ml_lab pulls optional heavy deps at module import.
    from src.ml_lab import snapshot_scorecard

    cfg_hash = config_fingerprint(config)
    res_fp = result_fingerprint(result)
    last = list_runs(dp_code=dp_code, limit=1)
    if last:
        prev = last[-1]
        if (prev.get("config_hash") == cfg_hash
                and (prev.get("payload") or {}).get("result_fingerprint") == res_fp):
            return False
    snapshot = snapshot_scorecard(dp_code, dp, result)
    snapshot["source"] = "auto"
    snapshot["result_fingerprint"] = res_fp
    return save_run(dp_code, domain_code, snapshot, config_hash=cfg_hash)


def load_history(dp_code: Optional[str],
                 limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Persisted run records oldest-first (``dp_code=None`` = every DP).

    Each record carries ``ts`` / ``username`` / ``config_hash`` plus the
    ML-Lab-compatible snapshot under ``payload``.
    """
    return list_runs(dp_code=dp_code, limit=limit)


def score_drop(history: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Compare the two most recent runs of ``history``.

    Returns ``None`` with fewer than two runs, else a dict with
    ``delta`` (current − previous, negative = drop), both scores, the
    previous run's ``ts`` / ``username``, and ``config_changed`` (True
    when the drop coincides with a configuration change - essential
    context before blaming the data).
    """
    if len(history) < 2:
        return None
    prev, curr = history[-2], history[-1]
    prev_score = float((prev.get("payload") or {}).get("overall_score", 0.0))
    curr_score = float((curr.get("payload") or {}).get("overall_score", 0.0))
    return {
        "delta": curr_score - prev_score,
        "prev_score": prev_score,
        "curr_score": curr_score,
        "prev_ts": prev.get("ts", ""),
        "prev_username": prev.get("username", ""),
        "config_changed": prev.get("config_hash") != curr.get("config_hash"),
    }
