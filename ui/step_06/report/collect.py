"""Pure adapters: engine objects -> report view models.

Everything here consumes ``ScorecardResult`` / ``DataProductConfig`` /
``DataProduct`` / persisted history and produces plain dicts and lists
for the renderers in :mod:`ui.step_06.report.sections` /
:mod:`ui.step_06.report.tables`. No Streamlit calls anywhere.

Single source of truth - nothing scoring-related is reimplemented:

- rule rows: :mod:`ui.step_06._rule_rows` (shared with the dashboard)
- failing-row selection: ``ui.step_06._drilldown`` helpers
- row enrichment: ``ui.step_06._export`` (reference columns + the
  ``STD ·`` / ``CUSTOM ·`` per-rule column headers)
- history / drift: :mod:`src.run_history`, ``src.ml_lab.compute_drift``
- buckets: :func:`utils.helpers.score_bucket`
"""
from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config.custom_dqr_catalog import effective_required_columns
from src.run_history import config_fingerprint, load_history, score_drop
from ui.step_06._drilldown import (
    _custom_flags,
    _custom_rule_meta,
    _failing_mask,
    _standard_flags,
)
from ui.step_06._export import (
    _reference_columns_for_export,
    _rule_column_specs,
)
from ui.step_06._rule_rows import (
    STATUS_EVALUATED,
    custom_rule_rows,
    standard_rule_rows,
)
from utils.helpers import score_bucket

# Same |Δ| >= 5 pp flag threshold as the dashboard History tab.
DRIFT_RULE_DELTA_THRESHOLD = 5.0


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


def _source_label(has_std: bool, has_custom: bool) -> str:
    if has_std and has_custom:
        return "Standard + Custom"
    if has_custom:
        return "Custom"
    return "Standard"


def _rule_search_terms(rule: Dict) -> str:
    if rule["kind"] == "std":
        return f"{rule['cde']} · {rule['dimension']}".lower()
    return f"{rule['rule_id']} · {rule['name']}".lower()


# ------------------------------------------------------------ per-DP view

def build_dp_view(code: str, dp, result, cfg, ctx) -> Dict:
    """Everything the per-DP section renderer needs, computed once.

    Flags are evaluated once per DP and reused for fail counts, drill
    totals and the embedded row store.
    """
    empty = pd.DataFrame(index=dp.df.index)
    std_flags = _standard_flags(dp, cfg) if cfg.assignments else empty
    cust_flags = _custom_flags(dp, cfg) if cfg.custom_assignments else empty
    all_flags = pd.concat(
        [f for f in (std_flags, cust_flags) if not f.empty], axis=1,
    ) if (not std_flags.empty or not cust_flags.empty) else empty

    ref_df = _reference_columns_for_export(dp, cfg)
    specs = _rule_column_specs(dp.system_code, cfg, std_flags, cust_flags)
    custom_meta = _custom_rule_meta(cfg, dp.system_code)

    std_rows = [dict(r, kind="std") for r in standard_rule_rows(cfg, result)]
    cust_rows = []
    for r in custom_rule_rows(dp.system_code, cfg, result):
        rule = r["rule"]
        cust_rows.append(dict(
            r, kind="custom",
            source_columns=(effective_required_columns(rule, r["params"])
                            if rule is not None else {}),
        ))

    fail_counts: Dict[str, int] = {
        rid: int((~all_flags[rid]).sum())
        for rid in all_flags.columns
    }
    for row in std_rows + cust_rows:
        row["fail_count"] = fail_counts.get(row["rule_id"])
        total = int(result.total_rows)
        row["pass_count"] = (
            total - row["fail_count"] if row["fail_count"] is not None else None
        )

    def drill_total(rule_ids: List[str]) -> Optional[int]:
        mask = _failing_mask(all_flags, rule_ids)
        return None if mask is None else int(mask.sum())

    for row in std_rows + cust_rows:
        row["drill_total"] = (
            drill_total([row["rule_id"]])
            if row["status"] == STATUS_EVALUATED else None
        )

    store_rows, store_json = _build_store(
        dp, result, ref_df, specs, std_flags, cust_flags,
        custom_meta, cfg, ctx,
    )

    view = {
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
        "std_rules": std_rows,
        "custom_rules": cust_rows,
        "cde_items": _cde_items(cfg, result, std_rows, cust_rows,
                                custom_meta, drill_total),
        "dim_items": _dim_items(result, std_rows, cust_rows,
                                custom_meta, drill_total),
        "columns": [str(c) for c in dp.df.columns],
        "ref_columns": [str(c) for c in ref_df.columns],
        "rule_specs": specs,
        "store_rows": store_rows,
        "store_json": store_json,
        "history": build_history_view(code, cust_rows),
    }
    view["not_run"] = (
        [r for r in std_rows if r["status"] != STATUS_EVALUATED]
        + [r for r in cust_rows if r["status"] != STATUS_EVALUATED]
    )
    return view


def _build_store(dp, result, ref_df, specs, std_flags, cust_flags,
                 custom_meta, cfg, ctx) -> Tuple[List[Dict], Dict]:
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
            "f": [
                int(bool(
                    (std_flags if rid in std_flags.columns else cust_flags)
                    .at[idx, rid]
                ))
                for rid, _ in specs
            ],
        })

    rules_meta: Dict[str, Dict] = {}
    for a in cfg.assignments:
        rules_meta[a.rule_id] = {
            "cdes": [a.cde_column], "dim": a.dimension, "kind": "std",
        }
    for rid, (cols, rtype) in custom_meta.items():
        rules_meta[rid] = {"cdes": list(cols), "dim": rtype, "kind": "custom"}

    store_json = {
        "columns": [str(c) for c in dp.df.columns],
        "refColumns": [str(c) for c in ref_df.columns],
        "ruleColumns": [{"id": rid, "header": header} for rid, header in specs],
        "rules": {rid: rules_meta[rid] for rid, _ in specs if rid in rules_meta},
        "store": rows,
    }
    return rows, store_json


def _cde_items(cfg, result, std_rows, cust_rows, custom_meta,
               drill_total) -> List[Dict]:
    """By-CDE list items, ascending score (same blend as the engine:
    Standard rules via their CDE, Custom rules via the columns they read)."""
    items: List[Dict] = []
    for cde, score in sorted(result.cde_scores.items(), key=lambda kv: kv[1]):
        tied = [r for r in std_rows if r["cde"] == cde]
        tied += [
            r for r in cust_rows
            if cde in (custom_meta.get(r["rule_id"], ((), ""))[0])
        ]
        items.append(_group_item(
            name=cde, score=float(score), tied=tied, result=result,
            drill_total=drill_total,
        ))
    return items


def _dim_items(result, std_rows, cust_rows, custom_meta,
               drill_total) -> List[Dict]:
    """By-Dimension list items (Custom rules count via their type)."""
    items: List[Dict] = []
    for dim, score in sorted(result.dimension_scores.items(),
                             key=lambda kv: kv[1]):
        tied = [r for r in std_rows if r["dimension"] == dim]
        tied += [
            r for r in cust_rows
            if custom_meta.get(r["rule_id"], ((), None))[1] == dim
        ]
        items.append(_group_item(
            name=dim, score=float(score), tied=tied, result=result,
            drill_total=drill_total,
        ))
    return items


def _group_item(name: str, score: float, tied: List[Dict], result,
                drill_total) -> Dict:
    evaluated = [r for r in tied if r["status"] == STATUS_EVALUATED]
    rule_ids = [r["rule_id"] for r in evaluated]
    search = " ".join(
        [str(name).lower()] + [_rule_search_terms(r) for r in tied]
    )
    return {
        "name": name,
        "score": score,
        "bucket": score_bucket(score, result.threshold_green,
                               result.threshold_yellow),
        "tied": tied,
        "n_evaluated": len(evaluated),
        "n_tied": len(tied),
        "source": _source_label(
            any(r["kind"] == "std" for r in tied),
            any(r["kind"] == "custom" for r in tied),
        ),
        "total": drill_total(rule_ids) if rule_ids else None,
        "search": search,
    }


# ---------------------------------------------------------------- history

def build_history_view(code: str, cust_rows: List[Dict]) -> Dict:
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
        name_map = {
            r["rule_id"]: f"{r['rule_id']} · {r['name']}" for r in cust_rows
        }
        flagged_total = 0
        tables: Dict[str, List[Dict]] = {}
        for label, table_key, key_col in (
            ("Rules", "rule_table", "rule_id"),
            ("CDEs", "cde_table", "cde"),
            ("Dimensions", "dimension_table", "dimension"),
        ):
            table = raw[table_key]
            flagged = table[table["flagged"]] if not table.empty else table
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
