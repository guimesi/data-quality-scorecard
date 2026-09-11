"""Publish a run's Data Quality Report to a SharePoint document library
(Microsoft Graph, application permissions).

What gets published for one :class:`~ui.step_06.report.models.ReportArtifacts`
(the publisher contract), under ``<SHAREPOINT_FOLDER>/<DOMAIN>/``:

- ``dq_scorecard_report_<DOMAIN>_<stamp>.pdf``   the PDF edition (when it
  could be rendered) - renders natively in the SharePoint browser viewer;
- ``dq_scorecard_report_<DOMAIN>_<stamp>.html``  the interactive edition,
  for download (SharePoint sanitises ``.html`` on display, so the file is
  a "download and open locally" artefact there);
- ``dq_scorecard_report_<DOMAIN>_<stamp>.json``  the run metadata plus the
  hosted link (``/reports/<run_id>`` on the app) for anyone wiring library
  columns or a Power Automate flow;
- ``dq_scorecard_report_<DOMAIN>_latest.pdf`` / ``_latest.html``  fixed-name
  copies overwritten on every publish, so a static link (an Airtable
  button, a SharePoint page) always opens the newest report.

Authentication is the OAuth2 **client-credentials** flow of an Entra ID
app registration (``SHAREPOINT_TENANT_ID`` / ``SHAREPOINT_CLIENT_ID`` /
``SHAREPOINT_CLIENT_SECRET``) with the Graph application permission
``Sites.Selected`` granted on the target site only - no user token, no
credentials in the repo (see ``deploy/README.md``). The target site is
``SHAREPOINT_SITE`` (a Graph site id or ``<host>:/sites/<name>``);
``SHAREPOINT_DRIVE_ID`` optionally pins a specific document library
(default: the site's default library).

Uploads below :data:`SIMPLE_UPLOAD_LIMIT` go through the simple
``PUT .../content`` call; larger files (a PDF with many Data Products)
use an upload session in :data:`CHUNK_SIZE` pieces. Throttling
(``429`` / ``503`` with ``Retry-After``) is retried a few times. Every
failure is normalised into :class:`SharePointPushError` with a short
actionable message; nothing here can crash the dashboard.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from config.settings import SETTINGS

logger = logging.getLogger(__name__)

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
LOGIN_ROOT = "https://login.microsoftonline.com"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"

# Graph's simple upload accepts up to 4 MB; above that an upload session
# is required. Chunks must be multiples of 320 KiB.
SIMPLE_UPLOAD_LIMIT = 4 * 1024 * 1024
CHUNK_SIZE = 20 * 320 * 1024  # 6.25 MiB, a multiple of 320 KiB as Graph requires
_TIMEOUT_S = 60
_RETRY_ATTEMPTS = 4
_RETRY_WAIT_S = 2.0
_RETRY_STATUSES = (429, 503, 504)


class SharePointPushError(RuntimeError):
    """Any failure while publishing to SharePoint."""


@dataclass(frozen=True)
class PublishedFile:
    name: str
    web_url: str
    size: int


@dataclass(frozen=True)
class PublishResult:
    folder_path: str
    files: List[PublishedFile] = field(default_factory=list)

    @property
    def pdf_url(self) -> Optional[str]:
        return next((f.web_url for f in self.files
                     if f.name.endswith(".pdf") and "_latest" not in f.name), None)

    @property
    def latest_pdf_url(self) -> Optional[str]:
        return next((f.web_url for f in self.files
                     if f.name.endswith("_latest.pdf")), None)


def is_configured() -> bool:
    return bool(SETTINGS.sharepoint_tenant_id and SETTINGS.sharepoint_client_id
                and SETTINGS.sharepoint_client_secret and SETTINGS.sharepoint_site)


# =============================================================================
# HTTP plumbing
# =============================================================================

def _request(method: str, url: str, *, step: str, token: Optional[str] = None,
             json_body: Any = None, data: Any = None,
             headers: Optional[Dict[str, str]] = None,
             ok_statuses: tuple = ()) -> requests.Response:
    """One Graph/login call with throttling retries. ``step`` names the
    call in error messages so a Graph rejection can be told apart from a
    proxy block or a permissions problem. ``ok_statuses`` lists non-2xx
    statuses the caller handles itself (e.g. 409 on folder creation)."""
    hdrs = dict(headers or {})
    if token:
        hdrs["Authorization"] = f"Bearer {token}"
    resp = None
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            resp = requests.request(method, url, json=json_body, data=data,
                                    headers=hdrs, timeout=_TIMEOUT_S)
        except requests.RequestException as exc:  # DNS, timeout, egress
            raise SharePointPushError(
                f"Could not reach Microsoft Graph during {step}: {exc}") from exc
        if resp.status_code in _RETRY_STATUSES and attempt < _RETRY_ATTEMPTS:
            wait = resp.headers.get("Retry-After")
            try:
                wait_s = float(wait) if wait else _RETRY_WAIT_S * attempt
            except ValueError:
                wait_s = _RETRY_WAIT_S * attempt
            time.sleep(min(wait_s, 30.0))
            continue
        break
    assert resp is not None
    if resp.ok or resp.status_code in ok_statuses:
        return resp
    raise SharePointPushError(
        f"Microsoft Graph returned {resp.status_code} during {step} "
        f"({url.split('?')[0]}): {_error_text(resp)}"
    )


def _error_text(resp: requests.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            return f"{err.get('code', '')}: {err.get('message', '')}"[:400]
    except ValueError:
        pass
    return (resp.text or "")[:400]


def _json(resp: requests.Response, step: str) -> Dict[str, Any]:
    try:
        body = resp.json()
    except ValueError as exc:
        raise SharePointPushError(
            f"Non-JSON response during {step} (status {resp.status_code}): "
            f"{(resp.text or '')[:400]}") from exc
    if not isinstance(body, dict):
        raise SharePointPushError(f"Unexpected response during {step}: {body!r}")
    return body


def acquire_token() -> str:
    """Client-credentials token for Graph (application permissions)."""
    url = f"{LOGIN_ROOT}/{SETTINGS.sharepoint_tenant_id}/oauth2/v2.0/token"
    resp = _request("POST", url, step="token request", data={
        "grant_type": "client_credentials",
        "client_id": SETTINGS.sharepoint_client_id,
        "client_secret": SETTINGS.sharepoint_client_secret,
        "scope": GRAPH_SCOPE,
    })
    token = _json(resp, "token request").get("access_token")
    if not token:
        raise SharePointPushError("Token response carried no access_token")
    return str(token)


def resolve_drive_id(token: str) -> str:
    """The document library to write to: ``SHAREPOINT_DRIVE_ID`` when set,
    else the default library of ``SHAREPOINT_SITE`` (a site id or
    ``<host>:/sites/<name>`` - Graph resolves both forms)."""
    if SETTINGS.sharepoint_drive_id:
        return SETTINGS.sharepoint_drive_id
    site = SETTINGS.sharepoint_site
    resp = _request("GET", f"{GRAPH_ROOT}/sites/{site}/drive", token=token,
                    step="site/drive lookup")
    drive_id = _json(resp, "site/drive lookup").get("id")
    if not drive_id:
        raise SharePointPushError(f"Site {site!r} has no default document library")
    return str(drive_id)


def _encode_path(path: str) -> str:
    return "/".join(quote(seg, safe="") for seg in path.strip("/").split("/") if seg)


def ensure_folder(token: str, drive_id: str, path: str) -> None:
    """Create ``path`` (every segment) under the drive root; an existing
    folder is fine (Graph answers 409 nameAlreadyExists)."""
    parent = ""
    for seg in [s for s in path.strip("/").split("/") if s]:
        url = (f"{GRAPH_ROOT}/drives/{drive_id}/root"
               + (f":/{_encode_path(parent)}:" if parent else "") + "/children")
        _request("POST", url, token=token, step=f"folder '{seg}' creation",
                 json_body={"name": seg, "folder": {},
                            "@microsoft.graph.conflictBehavior": "fail"},
                 ok_statuses=(409,))
        parent = f"{parent}/{seg}" if parent else seg


def upload_file(token: str, drive_id: str, path: str, data: bytes) -> PublishedFile:
    """Upload ``data`` to ``path`` (drive-relative), replacing an existing
    file. Simple PUT below :data:`SIMPLE_UPLOAD_LIMIT`, upload session in
    :data:`CHUNK_SIZE` pieces above it."""
    item_url = f"{GRAPH_ROOT}/drives/{drive_id}/root:/{_encode_path(path)}:"
    name = path.rsplit("/", 1)[-1]
    if len(data) <= SIMPLE_UPLOAD_LIMIT:
        resp = _request(
            "PUT", f"{item_url}/content?@microsoft.graph.conflictBehavior=replace",
            token=token, step=f"upload of {name}", data=data,
            headers={"Content-Type": "application/octet-stream"})
        item = _json(resp, f"upload of {name}")
    else:
        resp = _request(
            "POST", f"{item_url}/createUploadSession", token=token,
            step=f"upload session for {name}",
            json_body={"item": {"@microsoft.graph.conflictBehavior": "replace",
                                "name": name}})
        upload_url = _json(resp, f"upload session for {name}").get("uploadUrl")
        if not upload_url:
            raise SharePointPushError(f"No uploadUrl for {name}")
        item = {}
        total = len(data)
        for start in range(0, total, CHUNK_SIZE):
            chunk = data[start:start + CHUNK_SIZE]
            end = start + len(chunk) - 1
            resp = _request(
                "PUT", upload_url, step=f"chunk {start}-{end} of {name}",
                data=chunk, headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end}/{total}",
                })
            if resp.status_code in (200, 201):
                item = _json(resp, f"upload of {name}")
    return PublishedFile(name=str(item.get("name") or name),
                         web_url=str(item.get("webUrl") or ""),
                         size=int(item.get("size") or len(data)))


# =============================================================================
# Domain API
# =============================================================================

def publish_plan(artifacts, hosted_url: Optional[str] = None
                 ) -> List[tuple]:
    """``[(drive-relative path, bytes), ...]`` that :func:`publish_report`
    uploads for ``artifacts`` - pure, so the exact file set is testable
    without Graph."""
    domain = (artifacts.domain_code or "report").upper()
    folder = f"{SETTINGS.sharepoint_folder.strip('/')}/{domain}"
    names = artifacts.filenames
    latest = f"dq_scorecard_report_{domain}_latest"
    meta = {
        "run_id": artifacts.run_id,
        "domain_code": artifacts.domain_code,
        "generated_at": artifacts.generated_at,
        "hosted_url": hosted_url,
        "filenames": dict(names),
        "has_pdf": artifacts.pdf is not None,
        **{k: v for k, v in artifacts.metadata.items()
           if k not in ("run_id", "domain_code", "generated_at")},
    }
    plan: List[tuple] = []
    if artifacts.pdf:
        plan.append((f"{folder}/{names['pdf']}", artifacts.pdf))
    plan.append((f"{folder}/{names['interactive']}", artifacts.html))
    plan.append((f"{folder}/{names['interactive'][:-5]}.json",
                 json.dumps(meta, indent=2, default=str).encode("utf-8")))
    if artifacts.pdf:
        plan.append((f"{folder}/{latest}.pdf", artifacts.pdf))
    plan.append((f"{folder}/{latest}.html", artifacts.html))
    return plan


def publish_report(artifacts, hosted_url: Optional[str] = None) -> PublishResult:
    """Publish ``artifacts`` to the configured SharePoint library.

    Raises :class:`SharePointPushError` on any failure, including when
    the feature is not configured. Returns the published files with
    their SharePoint web URLs.
    """
    if not is_configured():
        raise SharePointPushError(
            "SharePoint publishing is not configured - set "
            "SHAREPOINT_TENANT_ID, SHAREPOINT_CLIENT_ID, "
            "SHAREPOINT_CLIENT_SECRET and SHAREPOINT_SITE (see .env.example)."
        )
    plan = publish_plan(artifacts, hosted_url)
    token = acquire_token()
    drive_id = resolve_drive_id(token)
    folder = plan[0][0].rsplit("/", 1)[0]
    ensure_folder(token, drive_id, folder)
    files = [upload_file(token, drive_id, path, data) for path, data in plan]
    logger.info("Published %d file(s) to SharePoint folder %s", len(files), folder)
    return PublishResult(folder_path=folder, files=files)
