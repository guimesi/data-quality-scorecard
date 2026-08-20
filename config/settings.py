"""
Global application settings loaded from environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# ``python-dotenv`` is a *local-development* convenience only. In Databricks
# Apps configuration arrives as real environment variables (app.yaml +
# platform-injected identity), so there is no ``.env`` in production. Import
# it defensively and rely on the env-var defaults below.
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - no python-dotenv installed
    load_dotenv = None

# Load .env from project root when available (local dev only).
_ROOT = Path(__file__).resolve().parent.parent
if load_dotenv is not None:
    load_dotenv(_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    # Data source
    data_source: str = os.getenv("DATA_SOURCE", "mock").lower()

    # Databricks. All application tables live in a single Unity Catalog
    # namespace whose defaults below are the known location of the migrated
    # tables. Identity (host + credentials) is NOT configured here: it is
    # resolved by ``databricks.sdk.core.Config`` - the service-principal
    # OAuth env vars injected by Databricks Apps in production, or
    # DATABRICKS_HOST / DATABRICKS_TOKEN from ``.env`` in local dev. Both
    # paths are headless (no browser auth).
    dbx_catalog: str = os.getenv("DATABRICKS_CATALOG", "entai_sandbox_catalog")
    dbx_schema: str = os.getenv("DATABRICKS_SCHEMA", "data_quality_scorecards")
    # SQL Warehouse: either the full HTTP path, or just the warehouse id
    # (what a Databricks App receives when a sql-warehouse resource is
    # attached). The client builds ``/sql/1.0/warehouses/<id>`` from the id.
    dbx_http_path: str = os.getenv("DATABRICKS_SQL_HTTP_PATH", "")
    dbx_warehouse_id: str = os.getenv("DATABRICKS_WAREHOUSE_ID", "")

    # Persistence (run history / telemetry / saved projects).
    # Deliberately decoupled from ``data_source``: a local run can read real
    # data from Databricks (DATA_SOURCE=databricks) while still persisting
    # app state to local files.
    #   local      -> JSON-lines files under ``store_dir`` (default)
    #   databricks -> DQS_* tables in ``dbx_catalog``.``dbx_state_schema``
    #   off        -> no-op (nothing is persisted)
    persistence_backend: str = os.getenv("DQS_PERSISTENCE", "local").lower()
    # Empty = "<project root>/.dqs_store" (resolved in src/persistence.py).
    store_dir: str = os.getenv("DQS_STORE_DIR", "")
    # Schema holding the DQS_* app-state tables. Empty = same schema as the
    # data tables (``dbx_schema``).
    dbx_state_schema: str = os.getenv("DQS_STATE_SCHEMA", "")
    # Step 6 shows a drop alert when a DP's score fell by at least this many
    # percentage points versus the previous persisted run.
    drop_alert_pp: float = float(os.getenv("DQS_DROP_ALERT_PP", "5"))

    # Airtable write-back (Step 6 "Send to Airtable"). Empty token or base
    # means "not configured": the UI hides the button and nothing is sent.
    # Databricks Apps have outbound internet access, so no extra network
    # configuration is needed there.
    airtable_token: str = os.getenv("AIRTABLE_TOKEN", "")
    airtable_base_id: str = os.getenv("AIRTABLE_BASE_ID", "")
    airtable_table: str = os.getenv("AIRTABLE_TABLE", "DQ Scorecard Results")
    # One record per (domain, system): the upsert merges on the key field
    # (domain) plus the system field, so ADR/ACCE/EPT runs never overwrite
    # each other. The attachment field receives the executive HTML report.
    airtable_key_field: str = os.getenv("AIRTABLE_KEY_FIELD", "Name")
    airtable_system_field: str = os.getenv("AIRTABLE_SYSTEM_FIELD", "System")
    airtable_attachment_field: str = os.getenv(
        "AIRTABLE_ATTACHMENT_FIELD", "Executive Report")
    # Airtable's upload endpoint APPENDS attachments; by default the push
    # prunes the field back to just the newest report so the record stays
    # consistent with its (replaced) score fields. Set true to keep every
    # report as attachment history instead.
    airtable_keep_old_reports: bool = os.getenv(
        "AIRTABLE_KEEP_OLD_REPORTS", "").lower() in ("1", "true", "yes")

    # Scorecard thresholds
    threshold_green: float = float(os.getenv("THRESHOLD_GREEN", "80"))
    threshold_yellow: float = float(os.getenv("THRESHOLD_YELLOW", "60"))

    # Limits
    max_rows_per_table: int = int(os.getenv("MAX_ROWS_PER_TABLE", "50000"))

    @property
    def is_mock(self) -> bool:
        return self.data_source == "mock"


SETTINGS = Settings()
