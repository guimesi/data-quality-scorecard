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

    # Scorecard thresholds
    threshold_green: float = float(os.getenv("THRESHOLD_GREEN", "80"))
    threshold_yellow: float = float(os.getenv("THRESHOLD_YELLOW", "60"))

    # Limits
    max_rows_per_table: int = int(os.getenv("MAX_ROWS_PER_TABLE", "50000"))

    @property
    def is_mock(self) -> bool:
        return self.data_source == "mock"


SETTINGS = Settings()
