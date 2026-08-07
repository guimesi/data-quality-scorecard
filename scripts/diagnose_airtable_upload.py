"""Diagnose the Airtable attachment upload path from this machine.

Run from the project root (reads the same .env the app uses):

    python scripts/diagnose_airtable_upload.py            # tiny upload
    python scripts/diagnose_airtable_upload.py --size 800000

It exercises the exact calls the Step 6 push makes, one at a time, and
prints status + response BODY for each - the body is what tells an
Airtable rejection ({"error": ...} JSON) apart from a corporate proxy
block page (HTML/text). Steps:

1. GET one record from the results table (host api.airtable.com).
2. Upload a throwaway attachment to that record's attachment field
   (host content.airtable.com) - delete it in Airtable afterwards.

Nothing here touches the app's own data beyond that test attachment.
"""
from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import truststore
    truststore.inject_into_ssl()
    print("truststore: injected (OS trust store in use)")
except ImportError:
    print("truststore: NOT installed - pip install -r requirements.txt")

import requests

from config.settings import SETTINGS


def _show(step: str, resp: requests.Response) -> None:
    body = resp.text[:500].replace(SETTINGS.airtable_token, "***")
    print(f"{step}: HTTP {resp.status_code}")
    print(f"  body: {body}")
    print()


def _app_path() -> int:
    """Reproduce the button's exact flow with the app's own functions:
    upsert a throwaway (__diagnostic__/TEST) row, then upload to the
    record id the upsert just returned - the one step the standalone
    upload test cannot cover. Delete the row in Airtable afterwards."""
    from types import SimpleNamespace

    from src import airtable_push as ap

    fake_result = SimpleNamespace(overall_score=99.9, threshold_green=80.0,
                                  threshold_yellow=60.0)
    fields = ap.build_record_fields("__diagnostic__", "TEST", fake_result)
    print(f"upserting row: {fields}")
    try:
        record_ids = ap._upsert_records([fields])
        print(f"upsert OK -> record {record_ids[0]}, uploading now...")
        ap._upload_report(record_ids[0], "diagnose_app_path.html",
                          b"<html>app-path diagnostic</html>")
    except ap.AirtablePushError as exc:
        print(f"FAILED: {exc}")
        return 2
    print("App path worked end to end - delete the '__diagnostic__' row "
          "in Airtable. If the button still fails, the difference is in "
          "the Streamlit process (stale env), not in the flow.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=3,
                        help="attachment payload size in bytes (default 3)")
    parser.add_argument("--app-path", action="store_true",
                        help="reproduce the exact Step 6 push flow "
                             "(upsert then immediate upload)")
    args = parser.parse_args()

    if not (SETTINGS.airtable_token and SETTINGS.airtable_base_id):
        print("AIRTABLE_TOKEN / AIRTABLE_BASE_ID missing in .env - abort.")
        return 1

    if args.app_path:
        return _app_path()

    print(f"base:  {SETTINGS.airtable_base_id}")
    print(f"table: {SETTINGS.airtable_table!r}")
    print(f"attachment field: {SETTINGS.airtable_attachment_field!r}")
    print(f"token: {SETTINGS.airtable_token[:8]}*** "
          f"({len(SETTINGS.airtable_token)} chars)")
    print(f"payload size: {args.size} bytes")
    print()

    headers = {"Authorization": f"Bearer {SETTINGS.airtable_token}"}

    # 1) Read one record (api.airtable.com) ------------------------------
    url = (f"https://api.airtable.com/v0/{SETTINGS.airtable_base_id}/"
           f"{quote(SETTINGS.airtable_table)}?maxRecords=1")
    try:
        r1 = requests.get(url, headers=headers, timeout=30)
    except requests.RequestException as exc:
        print(f"READ: transport error - {exc}")
        return 1
    _show("READ (api.airtable.com)", r1)
    if not r1.ok:
        print("Reading failed - fix this before testing uploads.")
        return 1
    records = r1.json().get("records", [])
    if not records:
        print("Table has no records - run the app push once (the upsert "
              "works) so there is a record to attach to, then rerun.")
        return 1
    record_id = records[0]["id"]
    print(f"using record: {record_id} "
          f"(fields: {list(records[0].get('fields', {}))})")
    print()

    # 2) Upload a tiny attachment (content.airtable.com) -----------------
    payload = b"x" * args.size
    url = (f"https://content.airtable.com/v0/{SETTINGS.airtable_base_id}/"
           f"{record_id}/{quote(SETTINGS.airtable_attachment_field)}/"
           "uploadAttachment")
    print(f"upload url: {url}")
    try:
        r2 = requests.post(
            url,
            headers={**headers, "Content-Type": "application/json"},
            json={"contentType": "text/plain",
                  "filename": "diagnose_test.txt",
                  "file": base64.b64encode(payload).decode("ascii")},
            timeout=60,
        )
    except requests.RequestException as exc:
        print(f"UPLOAD: transport error - {exc}")
        return 1
    _show("UPLOAD (content.airtable.com)", r2)

    if r2.ok:
        print("Upload worked - delete 'diagnose_test.txt' from the record "
              "in Airtable. If the app still fails, compare its error URL "
              "with the upload url above.")
    else:
        print("Upload refused - send the full output above (token is "
              "already masked) for diagnosis.")
    return 0 if r2.ok else 2


if __name__ == "__main__":
    sys.exit(main())
