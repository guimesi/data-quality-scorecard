"""Pure adapters: engine objects -> report view models.

Everything here consumes ``ScorecardResult`` / ``DataProductConfig`` /
``DataProduct`` / persisted history and produces plain dicts and lists
for the renderers in :mod:`ui.step_06.report.sections` /
:mod:`ui.step_06.report.tables`. No Streamlit calls anywhere.

The report covers DQRs only (the rules formerly called "Custom DQRs"):
Standard DQRs, source weights and the Standard/Custom sub-scores are
not collected. Single source of truth - nothing scoring-related is
reimplemented:

- DQR rows: :mod:`ui.step_06._rule_rows` (shared with the dashboard)
- failing-row selection: ``ui.step_06._drilldown`` helpers
- row enrichment: ``ui.step_06._export`` (reference columns + the
  ``DQR · ID · Name (w=..%)`` per-rule column headers)
- history / drift: :mod:`src.run_history`, ``src.ml_lab.compute_drift``
- buckets: :func:`utils.helpers.score_bucket`
"""
from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config.custom_dqr_catalog import effective_required_columns
from src.run_history import config_fingerprint, load_history, score_drop
from ui.step_06._drilldown import _custom_flags, _custom_rule_meta, _failing_mask
from ui.step_06._export import _reference_columns_for_export, _rule_column_specs
from ui.step_06._rule_rows import STATUS_EVALUATED, custom_rule_rows
from utils.helpers import score_bucket

# Same |Δ| >= 5 pp flag threshold as the dashboard History tab.
DRIFT_RULE_DELTA_THRESHOLD = 5.0

# Prefix of the per-DQR flag columns (``DQR · ID · Name (w=..%)``).
RULE_COLUMN_PREFIX = "DQR"


# --------------------------------------------------------------- primitives

def json_native(value: object) -> object:
    """Coerce a cell value to a JSON-native type.

    ``None`` for NaN/NaT/missing, plain int/float/bool/str pass through,
    numpy scalars unwrap, and everything else (Timestamp, date, Decimal,
    arbitrary objects) becomes ``str(value)``.
    """
    if value is None:
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        f = float(value)
        return f if np.isfinite(f) else None
    if isinstance(value, str):
        return value
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (pd.Timestamp, _dt.datetime, _dt.date, _dt.time,
                          Decimal)):
        return str(value)
    return str(value)


def dqr_label(rule: Dict) -> str:
    """``ID · Name`` - how a DQR is named everywhere in the report."""
    return f"{rule['rule_id']} · {rule['name']}"


# ------------------------------------------------------------ per-DP view

def build_dp_view(code: str, dp, result, cfg, ctx) -> Dict:
    """Everything the per-DP section renderer needs, computed once.

    DQR pass flags are evaluated once per DP and reused for fail counts,
    drill totals and the embedded row store.
    """
    empty = pd.DataFrame(index=dp.df.index)
    flags = _custom_flags(dp, cfg) if cfg.custom_assignments else empty

    ref_df = _reference_columns_for_export(dp, cfg)
    # DQRs only: no Standard flags -> no ``STD ·`` columns.
    specs = _rule_column_specs(dp.system_code, cfg, empty, flags,
                               custom_prefix=RULE_COLUMN_PREFIX)
    meta = _custom_rule_meta(cfg, dp.system_code)

    def drill_total(rule_ids: List[str]) -> Optional[int]:
        mask = _failing_mask(flags, rule_ids)
        return None if mask is None else int(mask.sum())

    total = int(result.total_rows)
    dqrs: List[Dict] = []
    for r in custom_rule_rows(dp.system_code, cfg, result):
        rule = r["rule"]
        rid = r["rule_id"]
        fail = int((~flags[rid]).sum()) if rid in flags.columns else None
        dqrs.append(dict(
            r,
            source_columns=(effective_required_columns(rule, r["params"])
                            if rule is not None else {}),
            fail_count=fail,
            pass_count=(total - fail) if fail is not None else None,
            drill_total=(drill_total([rid])
                         if r["status"] == STATUS_EVALUATED else None),
        ))

    store_rows, store_json = _build_store(dp, result, ref_df, specs, flags,
                                          meta, ctx)
    cde_items, cdes_without_dqr = _cde_items(cfg, result, dqrs, meta,
                                             drill_total)

    return {
        "code": code,
        "name": dp.name,
        "result": result,
        "cfg": cfg,
        "config_hash": config_fingerprint(cfg),
        "bucket": score_bucket(result.overall_score,
                               result.threshold_green,
                               result.threshold_yellow),
        "source_tables": list(dp.source_tables or []),
        "n_rows": int(dp.row_count),
        "n_cols": int(dp.column_count),
        "dqrs": dqrs,
        "not_run": [r for r in dqrs if r["status"] != STATUS_EVALUATED],
        "n_cdes": len(cfg.cdes),
        "cde_items": cde_items,
        "cdes_without_dqr": cdes_without_dqr,
        "dim_items": _dim_items(result, dqrs, meta, drill_total),
        "columns": [str(c) for c in dp.df.columns],
        "ref_columns": [str(c) for c in ref_df.columns],
        "rule_specs": specs,
        "store_rows": store_rows,
        "store_json": store_json,
        "history": build_history_view(code, dqrs),
    }


def _build_store(dp, result, ref_df, specs, flags, meta, ctx
                 ) -> Tuple[List[Dict], Dict]:
    """The per-DP row store: the ``row_store`` lowest-scoring rows, each
    embedded ONCE, plus the metadata the client-side drill-downs need."""
    scores = result.row_scores
    store_idx = scores.sort_values(kind="mergesort").head(
        ctx.caps.row_store).index
    df = dp.df.loc[store_idx] if len(store_idx) else dp.df.iloc[0:0]
    refs = ref_df.loc[store_idx] if len(store_idx) else ref_df.iloc[0:0]

    rows: List[Dict] = []
    for idx in store_idx:
        s = float(scores.loc[idx])
        rows.append({
            "s": round(s, 2),
            "b": score_bucket(s, result.threshold_green,
                              result.threshold_yellow),
            "v": [json_native(df.at[idx, c]) for c in dp.df.columns],
            "r": [json_native(refs.at[idx, c]) for c in ref_df.columns],
            "f": [int(bool(flags.at[idx, rid])) for rid, _ in specs],
        })

    store_json = {
        "columns": [str(c) for c in dp.df.columns],
        "refColumns": [str(c) for c in ref_df.columns],
        "ruleColumns": [{"id": rid, "header": header} for rid, header in specs],
        "rules": {
            rid: {"cdes": list(meta[rid][0]), "dim": meta[rid][1]}
            for rid, _ in specs if rid in meta
        },
        "store": rows,
    }
    return rows, store_json


def _cde_items(cfg, result, dqrs: List[Dict], meta,
               drill_total: Callable) -> Tuple[List[Dict], List[str]]:
    """By-CDE list items (ascending score) + the CDEs no DQR reads.

    A CDE is tied to every DQR whose required columns include it (the
    same roll-up ``compute_scorecard`` uses); CDEs without a DQR are not
    scored - they are returned separately for the intro line.
    """
    items: List[Dict] = []
    without: List[str] = []
    for cde in cfg.cdes:
        tied = [r for r in dqrs if cde in meta.get(r["rule_id"], ((), ""))[0]]
        if not tied:
            without.append(cde)
            continue
        items.append(_group_item(cde, result.cde_scores.get(cde), tied,
                                 result, drill_total))
    items.sort(key=_item_sort_key)
    return items, without


def _dim_items(result, dqrs: List[Dict], meta, drill_total: Callable
               ) -> List[Dict]:
    """By-Dimension list items (a DQR counts via its type). Dimensions the
    engine did not score (their only DQR was not evaluated) do not appear."""
    types = {meta[r["rule_id"]][1] for r in dqrs if r["rule_id"] in meta}
    items: List[Dict] = []
    for dim, score in result.dimension_scores.items():
        if dim not in types:
            continue
        tied = [r for r in dqrs
                if meta.get(r["rule_id"], ((), None))[1] == dim]
        items.append(_group_item(dim, score, tied, result, drill_total))
    items.sort(key=_item_sort_key)
    return items


def _item_sort_key(item: Dict) -> float:
    # Unscored (no evaluated DQR) first, then ascending score - the same
    # order the DQR list uses for not-evaluated rules.
    return -1.0 if item["score"] is None else item["score"]


def _group_item(name: str, score: Optional[float], tied: List[Dict], result,
                drill_total: Callable) -> Dict:
    evaluated = [r for r in tied if r["status"] == STATUS_EVALUATED]
    value = float(score) if (evaluated and score is not None) else None
    return {
        "name": name,
        "score": value,
        "bucket": (score_bucket(value, result.threshold_green,
                                result.threshold_yellow)
                   if value is not None else None),
        "tied": tied,
        "rule_ids": [r["rule_id"] for r in tied],
        "n_evaluated": len(evaluated),
        "n_tied": len(tied),
        "total": (drill_total([r["rule_id"] for r in evaluated])
                  if evaluated else None),
        "search": " ".join(
            [str(name).lower()] + [dqr_label(r).lower() for r in tied]
        ),
    }


# ---------------------------------------------------------------- history

def build_history_view(code: str, dqrs: List[Dict]) -> Dict:
    """Persisted-run history + what-changed drift for one DP.

    Returns ``{"runs": [...], "drop": ..., "drift": ...}`` where ``runs``
    is oldest-first (each with ts/user/score/delta/config hash/changed/
    note) and ``drift`` is ``None`` with fewer than two runs.
    """
    history = load_history(code)
    payloads = [r.get("payload") or {} for r in history]
    hashes = [str(r.get("config_hash", "") or "") for r in history]
    runs: List[Dict] = []
    for i, rec in enumerate(history):
        score = float(payloads[i].get("overall_score", 0.0))
        runs.append({
            "ts": str(rec.get("ts", "") or ""),
            "date": str(rec.get("ts", "") or "")[:10],
            "user": str(rec.get("username", "") or ""),
            "score": score,
            "delta": (score - float(payloads[i - 1].get("overall_score", 0.0))
                      if i > 0 else None),
            "config_hash": hashes[i],
            "changed": i > 0 and hashes[i] != hashes[i - 1],
            "note": ("re-verified (unchanged)"
                     if payloads[i].get("unchanged") else ""),
        })

    drift = None
    if len(history) >= 2:
        # Imported lazily: ml_lab pulls optional heavy deps at import time.
        from src.ml_lab import compute_drift

        raw = compute_drift(payloads[-2], payloads[-1],
                            rule_delta_threshold=DRIFT_RULE_DELTA_THRESHOLD)
        name_map = {r["rule_id"]: dqr_label(r) for r in dqrs}
        flagged_total = 0
        tables: Dict[str, List[Dict]] = {}
        for label, table_key, key_col in (
            ("DQRs", "rule_table", "rule_id"),
            ("CDEs", "cde_table", "cde"),
            ("Dimensions", "dimension_table", "dimension"),
        ):
            table = raw[table_key]
            flagged = table[table["flagged"]] if not table.empty else table
            if key_col == "rule_id" and not flagged.empty:
                # DQRs only: Standard rule ids are ``CDE::Dimension``.
                flagged = flagged[
                    ~flagged[key_col].astype(str).str.contains("::", regex=False)
                ]
            flagged_total += len(flagged)
            tables[label] = [
                {
                    "name": name_map.get(str(row[key_col]), str(row[key_col])),
                    "previous": float(row["score_a"]),
                    "current": float(row["score_b"]),
                    "delta": float(row["delta"]),
                }
                for _, row in flagged.iterrows()
            ]
        drift = {
            "score_delta": float(raw["overall_score_delta"]),
            "psi": raw["psi"],
            "flagged_total": flagged_total,
            "tables": tables,
            "prev": runs[-2],
            "curr": runs[-1],
            "config_changed": runs[-1]["changed"],
        }

    return {"runs": runs, "drop": score_drop(history), "drift": drift}
