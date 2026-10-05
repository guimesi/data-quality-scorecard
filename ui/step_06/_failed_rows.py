"""Step 6 failed-rows actions: CSV download and "Save failed rows".

Both work on :func:`src.failed_rows.failed_rows_frame` - the rows failing
at least one rule, lowest score first, with only the columns the rules
use (keys, CDEs, reference-dataset columns). Collecting them re-evaluates
every rule, so the frame is built once per (result, configuration) on the
first click, in the script thread (reference datasets live in session
state), cached in ``st.session_state`` and shared by both actions:

- "CSV (failed rows)" builds the file and then offers it for download;
- "Save failed rows" replaces the (domain, DP)'s ``DQS_FAILS_<DOMAIN>_<DP>``
  table, chunk by chunk with a progress bar - for a large DP it takes
  minutes, which is why it is a button and never a render side effect.
"""
from __future__ import annotations

import io
import json
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import streamlit as st

from config.settings import SETTINGS
from src.persistence import log_event
from ui.step_06._export import _sanitize_csv_cell

_CACHE_KEY = "_failed_rows_cache"


def _cache(code: str) -> Dict[str, Any]:
    return st.session_state.setdefault(_CACHE_KEY, {}).setdefault(code, {})


def _frame_for(code: str, dp, result, cfg) -> Tuple[pd.DataFrame, int]:
    """The failed-rows frame of this scorecard, computed once per
    (result fingerprint, config fingerprint) and kept in session state."""
    from src.failed_rows import failed_rows_frame
    from src.run_history import config_fingerprint, result_fingerprint

    key = (result_fingerprint(result), config_fingerprint(cfg))
    entry = _cache(code)
    if entry.get("key") != key:
        with st.spinner(f"Collecting the failed rows of {code}…"):
            frame, total = failed_rows_frame(dp, result, cfg, SETTINGS.fails_max_rows)
        entry.clear()
        entry.update({"key": key, "frame": frame, "total": total})
    return entry["frame"], entry["total"]


def _csv_bytes(frame: pd.DataFrame) -> bytes:
    from src.failed_rows import RULES_COLUMN

    if frame.empty:
        return b"row_score,failed_rules\r\n"
    out = frame.copy()
    out[RULES_COLUMN] = out[RULES_COLUMN].map(lambda ids: json.dumps(list(ids)))
    for column in out.columns:
        if out[column].dtype == object:
            out[column] = out[column].map(_sanitize_csv_cell)
    buf = io.StringIO()
    out.to_csv(buf, index=False, lineterminator="\r\n")
    return buf.getvalue().encode("utf-8-sig")


def _failed_rows_csv(dp, result, cfg) -> bytes:
    """CSV of the failing rows (test seam; the UI goes through the cache)."""
    from src.failed_rows import failed_rows_frame

    frame, _ = failed_rows_frame(dp, result, cfg, SETTINGS.fails_max_rows)
    return _csv_bytes(frame)


def _render_failed_rows_actions(code: str, dp, result, cfg) -> None:
    """The two buttons side by side under the row-score exports, then the
    download link / save note once there is one."""
    domain_code = str(st.session_state.get("domain", "") or "")
    d1, d2 = st.columns(2)
    with d1:
        if st.button(
            "CSV (failed rows)",
            key=f"btn_failed_csv_{code}",
            width="stretch",
            help="Builds a CSV of the rows failing at least one rule, worst "
                 "first, with the failed rule ids, the CDE columns and the "
                 "reference columns the rules used.",
        ):
            frame, total = _frame_for(code, dp, result, cfg)
            entry = _cache(code)
            entry["csv"] = _csv_bytes(frame)
            entry["csv_rows"] = len(frame)
            log_event("export", {"format": "failed_rows_csv", "dp": code,
                                 "rows": len(frame), "total": total}, domain_code)
    with d2:
        if SETTINGS.persistence_backend != "off" and st.button(
            "💾 Save failed rows",
            key=f"btn_failed_save_{code}",
            width="stretch",
            help="Replaces the content of this Data Product's DQS_FAILS "
                 "table with the failing rows of this run. Takes a while on "
                 "a large Data Product.",
        ):
            _save(code, dp, result, cfg, domain_code)

    entry = _cache(code)
    csv: Optional[bytes] = entry.get("csv")
    if csv is not None:
        st.download_button(
            f"⬇ Download {entry.get('csv_rows', 0):,} failed row(s) (CSV)",
            data=csv,
            file_name=f"{code}_failed_rows.csv",
            mime="text/csv",
            width="stretch",
            key=f"dl_failed_{code}",
        )
    if entry.get("saved"):
        st.caption(entry["saved"])


def _save(code: str, dp, result, cfg, domain_code: str) -> None:
    from src.failed_rows import save_failed_rows_for_run
    from src.persistence import fails_table_name
    from src.run_history import config_fingerprint

    table = fails_table_name(domain_code, code)
    frame = _frame_for(code, dp, result, cfg)
    bar = st.progress(0.0, text=f"Writing failed rows to {table}…")

    def _progress(done: int, total: int) -> None:
        bar.progress(done / max(total, 1),
                     text=f"Writing failed rows to {table}: {done:,} / {total:,}")

    try:
        written, total = save_failed_rows_for_run(
            domain_code, code, dp, result, cfg,
            config_hash=config_fingerprint(cfg), frame=frame, progress=_progress)
    except Exception as exc:
        bar.empty()
        st.error(f"Failed rows not saved: {exc}")
        return
    bar.empty()
    note = f"{written:,} failed row(s) saved to `{table}`"
    if total > written:
        note += f" ({total:,} fail in total - capped by DQS_FAILS_MAX_ROWS)"
    _cache(code)["saved"] = note
    log_event("export", {"format": "failed_rows_table", "dp": code,
                         "rows": written, "total": total}, domain_code)
    st.success(note)
