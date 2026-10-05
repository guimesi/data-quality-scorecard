"""Step 6 failed-rows actions: CSV download and "Save failed rows".

Both work on :func:`src.failed_rows.failed_rows_frame` - the rows failing
at least one rule, lowest score first, with only the columns the rules
use (keys, CDEs, reference-dataset columns). The CSV is built on click
(``st.download_button`` takes a callable), so rendering the dashboard
never pays for it; the save replaces the (domain, DP)'s
``DQS_FAILS_<DOMAIN>_<DP>`` table and is explicit on purpose - for a
large DP it takes minutes.
"""
from __future__ import annotations

import io
import json
from typing import Any

import streamlit as st

from config.settings import SETTINGS
from src.persistence import log_event
from ui.step_06._export import _sanitize_csv_cell

_SAVED_KEY = "_failed_rows_saved"


def _failed_rows_csv(dp, result, cfg) -> bytes:
    from src.failed_rows import RULES_COLUMN, failed_rows_frame

    frame, _ = failed_rows_frame(dp, result, cfg, SETTINGS.fails_max_rows)
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


def _render_failed_rows_actions(code: str, dp, result, cfg) -> None:
    """The two buttons, side by side, under the row-score exports."""
    domain_code = str(st.session_state.get("domain", "") or "")
    d1, d2 = st.columns(2)
    with d1:
        if st.download_button(
            "CSV (failed rows)",
            data=lambda: _failed_rows_csv(dp, result, cfg),
            file_name=f"{code}_failed_rows.csv",
            mime="text/csv",
            width="stretch",
            key=f"dl_failed_{code}",
            help="Rows failing at least one rule, worst first, with the "
                 "failed rule ids, the CDE columns and the reference columns "
                 "the rules used.",
        ):
            log_event("export", {"format": "failed_rows_csv", "dp": code},
                      domain_code)
    with d2:
        if SETTINGS.persistence_backend == "off":
            return
        if st.button(
            "💾 Save failed rows",
            key=f"btn_failed_{code}",
            width="stretch",
            help="Replaces the content of this Data Product's "
                 "DQS_FAILS table with the failing rows of this run. "
                 "Takes a while on a large Data Product.",
        ):
            _save(code, dp, result, cfg, domain_code)
    saved: Any = st.session_state.get(_SAVED_KEY, {}).get(code)
    if saved:
        st.caption(saved)


def _save(code: str, dp, result, cfg, domain_code: str) -> None:
    from src.failed_rows import save_failed_rows_for_run
    from src.persistence import fails_table_name
    from src.run_history import config_fingerprint

    table = fails_table_name(domain_code, code)
    try:
        with st.spinner(f"Writing failed rows to {table}…"):
            written, total = save_failed_rows_for_run(
                domain_code, code, dp, result, cfg,
                config_hash=config_fingerprint(cfg))
    except Exception as exc:
        st.error(f"Failed rows not saved: {exc}")
        return
    note = f"{written:,} failed row(s) saved to `{table}`"
    if total > written:
        note += f" ({total:,} fail in total - capped by DQS_FAILS_MAX_ROWS)"
    st.session_state.setdefault(_SAVED_KEY, {})[code] = note
    log_event("export", {"format": "failed_rows_table", "dp": code,
                         "rows": written, "total": total}, domain_code)
    st.success(note)
