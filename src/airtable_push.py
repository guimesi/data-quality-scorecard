"""Write-back of scorecard results to Airtable (Step 6, phase 5).

Data owners manage rules and CDEs in an Airtable base; this module closes
the loop by pushing each run's outcome back there so they get the full
project view without opening Streamlit:

1. **Upsert** one record per (domain, system) in the results table
   (``PATCH /v0/{base}/{table}`` with ``performUpsert`` merging on the
   key field + system field, so an EPT run never overwrites the ADR row),
   carrying that system's overall score, status, timestamp and the user
   who ran it.
2. **Attach** the self-contained executive HTML report to each upserted
   record via Airtable's direct upload endpoint
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
import time
from datetime import datetime
from typing import Any, Dict, List
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
# content.airtable.com may lag behind api.airtable.com: uploading to a
# record the upsert JUST created can 403 with the generic
# INVALID_PERMISSIONS_OR_MODEL_NOT_FOUND until the record propagates, so
# the upload retries a few times before giving up.
_UPLOAD_ATTEMPTS = 4
_UPLOAD_RETRY_WAIT_S = 2.0


class AirtablePushError(RuntimeError):
    """Any failure while sending results to Airtable."""


def is_configured() -> bool:
    return bool(SETTINGS.airtable_token and SETTINGS.airtable_base_id)


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {SETTINGS.airtable_token}",
        "Content-Type": "application/json",
    }


def _request(method: str, url: str, payload: dict, step: str) -> dict:
    """``step`` names the call in errors ("record upsert" / "report
    upload") - essential to tell an Airtable rejection from a corporate
    proxy blocking one of the two hosts or payload sizes."""
    try:
        resp = requests.request(
            method, url, json=payload, headers=_headers(), timeout=_TIMEOUT_S,
        )
    except requests.RequestException as exc:  # DNS, timeout, egress blocked…
        raise AirtablePushError(
            f"Could not reach Airtable during {step}: {exc}") from exc
    if not resp.ok:
        raise AirtablePushError(
            f"Airtable returned {resp.status_code} during {step} "
            f"({url.split('?')[0]}): {resp.text[:400]}"
        )
    try:
        return resp.json()
    except ValueError as exc:  # non-JSON body (e.g. a proxy block page)
        raise AirtablePushError(
            f"Non-JSON response during {step} "
            f"(status {resp.status_code}): {resp.text[:400]}") from exc


def build_record_fields(domain_code: str, dp_code: str,
                        result: Any) -> Dict[str, object]:
    """One system's upsert payload minus the attachment (pure,
    unit-testable). Status uses the thresholds the scorecard was actually
    computed with, matching the dashboard pill."""
    return {
        SETTINGS.airtable_key_field: domain_code,
        SETTINGS.airtable_system_field: dp_code,
        "Overall Score": round(result.overall_score, 1),
        "Status": score_label(result.overall_score, result.threshold_green,
                              result.threshold_yellow),
        "Last Run": datetime.now().isoformat(timespec="seconds"),
        "Run By": current_username(),
    }


def _upsert_records(records: List[Dict[str, object]]) -> List[str]:
    """Create-or-update one record per system, merging on
    (key field, system field) so systems of the same domain coexist as
    separate rows. Returns the Airtable record ids in request order."""
    url = f"{API_ROOT}/{SETTINGS.airtable_base_id}/{quote(SETTINGS.airtable_table)}"
    payload = {
        "performUpsert": {"fieldsToMergeOn": [
            SETTINGS.airtable_key_field, SETTINGS.airtable_system_field,
        ]},
        # typecast lets Airtable auto-create select options (e.g. Status).
        "typecast": True,
        "records": [{"fields": fields} for fields in records],
    }
    data = _request("PATCH", url, payload, step="record upsert")
    try:
        ids = [r["id"] for r in data["records"]]
        if len(ids) != len(records):
            raise KeyError("record count mismatch")
        return ids
    except (KeyError, IndexError, TypeError) as exc:
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
    payload = {
        # Deliberately NOT text/html: the org's Airtable policy rejects
        # text/html uploads with a generic 403 (confirmed by A/B tests -
        # the .html filename itself is fine). Declared as text/plain the
        # upload passes, and the downloaded .html still opens normally
        # in a browser; only Airtable's inline preview shows source.
        "contentType": "text/plain",
        "filename": filename,
        "file": base64.b64encode(html_bytes).decode("ascii"),
    }
    for attempt in range(1, _UPLOAD_ATTEMPTS + 1):
        try:
            _request("POST", url, payload, step="report upload")
            return
        except AirtablePushError as exc:
            # Only a 403 right after the upsert smells like propagation
            # lag; anything else (401, 404, 413, transport) is final.
            if "403" not in str(exc) or attempt == _UPLOAD_ATTEMPTS:
                raise
            time.sleep(_UPLOAD_RETRY_WAIT_S)


def push_executive_report(domain_code: str, scorecards: Dict[str, Any],
                          html_bytes: bytes) -> List[str]:
    """Upsert one result record per system in ``scorecards`` and attach
    the executive report to each.

    Returns the Airtable record ids (useful for the UI success message).
    Raises :class:`AirtablePushError` on any failure, including when the
    feature is not configured.
    """
    if not is_configured():
        raise AirtablePushError(
            "Airtable is not configured - set AIRTABLE_TOKEN and "
            "AIRTABLE_BASE_ID (see .env.example)."
        )
    if not scorecards:
        raise AirtablePushError("No scorecard results to send.")
    codes = list(scorecards)
    record_ids = _upsert_records(
        [build_record_fields(domain_code, code, scorecards[code])
         for code in codes]
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    for code, record_id in zip(codes, record_ids):
        _upload_report(
            record_id,
            f"dq_scorecard_{domain_code or 'report'}_{code}_{stamp}.html",
            html_bytes,
        )
    return record_ids
