"""
Global application settings loaded from environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# ``python-dotenv`` is a *local-development* convenience only. It is NOT a
# runtime dependency of Streamlit in Snowflake (it is absent from
# ``environment.yml``), and there is no ``.env`` inside SiS. Import it
# defensively so the module loads in SiS, and rely on the env-var defaults
# below (the Snowpark session supplies identity/warehouse/database/schema).
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - SiS / no python-dotenv installed
    load_dotenv = None

# Load .env from project root when available (local dev only).
_ROOT = Path(__file__).resolve().parent.parent
if load_dotenv is not None:
    load_dotenv(_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    # Data source
    data_source: str = os.getenv("DATA_SOURCE", "mock").lower()

    # Snowflake. Connection details have NO real defaults - they must be
    # supplied via .env (see .env.example). Empty values mean "not configured";
    # snowflake_client only connects when DATA_SOURCE=snowflake, and it already
    # omits an empty warehouse. Do NOT hardcode a real account / warehouse /
    # database / schema here (it would ship an internal identifier in the repo).
    sf_account: str = os.getenv("SNOWFLAKE_ACCOUNT", "")
    sf_user: str = os.getenv("SNOWFLAKE_USER", "")
    sf_authenticator: str = os.getenv("SNOWFLAKE_AUTHENTICATOR", "externalbrowser")
    sf_warehouse: str = os.getenv("SNOWFLAKE_WAREHOUSE", "")
    sf_database: str = os.getenv("SNOWFLAKE_DATABASE", "")
    sf_schema: str = os.getenv("SNOWFLAKE_SCHEMA", "")
    sf_role: str = os.getenv("SNOWFLAKE_ROLE", "")

    # Persistence (run history / telemetry / saved projects).
    # Deliberately decoupled from ``data_source``: a local run can read real
    # data from Snowflake (DATA_SOURCE=snowflake) while still persisting app
    # state to local files until the DQS_* tables exist in production.
    #   local     -> JSON-lines files under ``store_dir`` (default)
    #   snowflake -> DQS_* tables in ``sf_database``.``sf_state_schema``
    #   off       -> no-op (nothing is persisted)
    persistence_backend: str = os.getenv("DQS_PERSISTENCE", "local").lower()
    # Empty = "<project root>/.dqs_store" (resolved in src/persistence.py).
    store_dir: str = os.getenv("DQS_STORE_DIR", "")
    sf_state_schema: str = os.getenv("DQS_STATE_SCHEMA", "DQS_APP_STATE")
    # Step 6 shows a drop alert when a DP's score fell by at least this many
    # percentage points versus the previous persisted run.
    drop_alert_pp: float = float(os.getenv("DQS_DROP_ALERT_PP", "5"))

    # Airtable write-back (Step 6 "Send to Airtable"). Empty token or base
    # means "not configured": the UI hides the button and nothing is sent.
    # In Streamlit in Snowflake the outbound call additionally requires an
    # External Access Integration for api.airtable.com/content.airtable.com.
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

    # Scorecard thresholds
    threshold_green: float = float(os.getenv("THRESHOLD_GREEN", "80"))
    threshold_yellow: float = float(os.getenv("THRESHOLD_YELLOW", "60"))

    # Limits
    max_rows_per_table: int = int(os.getenv("MAX_ROWS_PER_TABLE", "50000"))

    @property
    def is_mock(self) -> bool:
        return self.data_source == "mock"


SETTINGS = Settings()
