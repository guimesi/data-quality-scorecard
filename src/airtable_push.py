"""Write-back of scorecard results to Airtable (Step 6, phase 5).

Data owners manage rules and CDEs in an Airtable base; this module closes
the loop by pushing each run's outcome back there so they get the full
project view without opening Streamlit:

1. **Upsert** one record per domain in the results table
   (``PATCH /v0/{base}/{table}`` with ``performUpsert`` merging on the
   configured key field), carrying the summary fields: overall score,
   status, per-DP breakdown, timestamp and the user who ran it.
2. **Attach** the self-contained executive HTML report to that record via
   Airtable's direct upload endpoint
   (``POST content.airtable.com/v0/{base}/{record}/{field}/uploadAttachment``,
   base64 payload, hard 5 MB API limit).

Configuration lives in ``config.settings`` (AIRTABLE_* env vars); with no
token/base configured the feature is invisible in the UI. Errors never
crash the dashboard: every HTTP/transport failure is normalized into
:class:`AirtablePushError` with a short actionable message.

SiS note: in Streamlit in Snowflake, outbound HTTPS requires an External
Access Integration covering ``api.airtable.com`` and
``content.airtable.com``; without it the request fails and surfaces here
as an :class:`AirtablePushError`.
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Dict
from urllib.parse import quote

import requests

from config.settings import SETTINGS
from src.persistence import current_username
from utils.helpers import score_label

API_ROOT = "https://api.airtable.com/v0"
CONTENT_ROOT = "https://content.airtable.com/v0"
# Airtable's uploadAttachment endpoint rejects payloads above 5 MB.
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
_TIMEOUT_S = 30


class AirtablePushError(RuntimeError):
    """Any failure while sending results to Airtable."""


def is_configured() -> bool:
    return bool(SETTINGS.airtable_token and SETTINGS.airtable_base_id)


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {SETTINGS.airtable_token}",
        "Content-Type": "application/json",
    }


def _request(method: str, url: str, payload: dict) -> dict:
    try:
        resp = requests.request(
            method, url, json=payload, headers=_headers(), timeout=_TIMEOUT_S,
        )
    except requests.RequestException as exc:  # DNS, timeout, egress blocked…
        raise AirtablePushError(f"Could not reach Airtable: {exc}") from exc
    if not resp.ok:
        raise AirtablePushError(
            f"Airtable returned {resp.status_code}: {resp.text[:300]}"
        )
    return resp.json()


def build_summary_fields(domain_code: str,
                         scorecards: Dict[str, object]) -> Dict[str, object]:
    """The upsert payload minus the attachment (pure, unit-testable)."""
    scores = [r.overall_score for r in scorecards.values()]
    overall = sum(scores) / len(scores) if scores else 0.0
    per_dp = " · ".join(
        f"{code}: {r.overall_score:.1f}" for code, r in scorecards.items()
    )
    return {
        SETTINGS.airtable_key_field: domain_code,
        "Overall Score": round(overall, 1),
        "Status": score_label(
            overall, SETTINGS.threshold_green, SETTINGS.threshold_yellow),
        "Data Products": per_dp,
        "Last Run": datetime.now().isoformat(timespec="seconds"),
        "Run By": current_username(),
    }


def _upsert_record(fields: Dict[str, object]) -> str:
    """Create-or-update the domain's record; returns the Airtable record id."""
    url = f"{API_ROOT}/{SETTINGS.airtable_base_id}/{quote(SETTINGS.airtable_table)}"
    payload = {
        "performUpsert": {"fieldsToMergeOn": [SETTINGS.airtable_key_field]},
        # typecast lets Airtable auto-create select options (e.g. Status).
        "typecast": True,
        "records": [{"fields": fields}],
    }
    data = _request("PATCH", url, payload)
    try:
        return data["records"][0]["id"]
    except (KeyError, IndexError) as exc:
        raise AirtablePushError(
            f"Unexpected Airtable upsert response: {data}") from exc


def _upload_report(record_id: str, filename: str, html_bytes: bytes) -> None:
    if len(html_bytes) > MAX_ATTACHMENT_BYTES:
        raise AirtablePushError(
            f"Report is {len(html_bytes) / 1024 / 1024:.1f} MB - Airtable "
            "attachments are limited to 5 MB."
        )
    url = (
        f"{CONTENT_ROOT}/{SETTINGS.airtable_base_id}/{record_id}/"
        f"{quote(SETTINGS.airtable_attachment_field)}/uploadAttachment"
    )
    _request("POST", url, {
        "contentType": "text/html",
        "filename": filename,
        "file": base64.b64encode(html_bytes).decode("ascii"),
    })


def push_executive_report(domain_code: str, scorecards: Dict[str, object],
                          html_bytes: bytes) -> str:
    """Upsert the domain's result record and attach the executive report.

    Returns the Airtable record id (useful for the UI success message).
    Raises :class:`AirtablePushError` on any failure, including when the
    feature is not configured.
    """
    if not is_configured():
        raise AirtablePushError(
            "Airtable is not configured - set AIRTABLE_TOKEN and "
            "AIRTABLE_BASE_ID (see .env.example)."
        )
    record_id = _upsert_record(build_summary_fields(domain_code, scorecards))
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    _upload_report(
        record_id, f"dq_scorecard_{domain_code or 'report'}_{stamp}.html",
        html_bytes,
    )
    return record_id
