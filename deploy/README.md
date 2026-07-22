# Streamlit in Snowflake (SiS) — deployment scripts

> **⚠ SUPERSEDED (July 2026):** the deployment now follows the **EM platform CI/CD
> template** (GitHub Actions + Snow CLI + key-pair auth + Azure Key Vault) — see
> **[`em_pipeline/`](em_pipeline/)** for the adapted pipeline, admin SQL and migration
> checklist, and `deploy_files/` for the pristine template copies. The SQL below
> describes the earlier Snowflake-native Git-integration model: `02_sis_deploy.sql`
> is fully superseded (no PAT/SECRET/API INTEGRATION/GIT REPOSITORY in the new model);
> `01_least_privilege_role.sql`'s data grants are carried into
> `em_pipeline/ADMIN_SETUP.sql`. Kept for reference.

Reference SQL to deploy `data-quality-scorecard` as a **Streamlit in Snowflake** app
from this GitHub repository, with a **least-privilege, read-only** role.

> These are **templates**. Replace every `<PLACEHOLDER>` before running. Nothing here is
> executed automatically — run them yourself in Snowsight / SnowSQL with the privileges
> noted in each file. Syntax is standard as of the Snowflake docs reviewed, but a few
> clauses vary by account/edition — the **VERIFY** notes flag those; cross-check against
> Snowsight before relying on them.

## Run order

1. **`01_least_privilege_role.sql`** — creates the read-only app role + grants.
   Run as `SECURITYADMIN`/`ACCOUNTADMIN` (role creation + grants).
2. **`02_sis_deploy.sql`** — creates the GitHub secret, API integration, Git repository,
   and the Streamlit object; grants app access to viewers.
   Mixed privileges: the API integration step needs `ACCOUNTADMIN`; the rest can run as
   the app role / `SYSADMIN`.
3. **`03_persistence_tables.sql`** *(optional; still current — not superseded by the
   EM pipeline)* — creates the `DQS_APP_STATE` schema + append-only `DQS_RUNS` /
   `DQS_EVENTS` / `DQS_PROJECTS` tables for run history, telemetry and saved
   projects (`src/persistence.py`), and grants the app role **INSERT+SELECT on
   those tables only** — a deliberate, scoped exception to the read-only posture
   of `01`. Only needed once the app runs with `DQS_PERSISTENCE=snowflake`;
   until then the app persists to local files and never touches these tables.

## Placeholders you must fill in

| Placeholder | Meaning | Likely value (from the repo) |
|---|---|---|
| `<APP_DB>` / `<APP_SCHEMA>` | where the app objects (secret, git repo, streamlit) live | e.g. `INSIGHTS_DB` / a dedicated `APPS` schema |
| `<WAREHOUSE>` | warehouse the app queries run on | `TRUSTED_WH` |
| `<DEPLOY_BRANCH>` | branch SiS pulls from | `dev` for testing, `main` once merged |
| `<GH_ORG>` / `<GH_USER>` / `<GH_PAT>` | GitHub org, a username, and a Personal Access Token (read access to the repo) | — |
| `<VIEWER_ROLE>` | role(s) whose users may open the app | — |
| data schemas | the schemas the app reads | `INSIGHTS_DB.UC_GP_CSC` (Cost Estimate), `INGESTION_DB.GP_QUALITY` (Quality) |

## Two things to confirm in your account while deploying

1. **Package versions** — when the Streamlit object builds, confirm `plotly` / `scikit-learn`
   resolve from the Snowflake Anaconda channel (Snowsight → app → Packages). Tighten the
   pins in `../environment.yml` if needed. `environment.yml` must sit at the repo root
   (it does) so SiS picks it up.
2. **Manual smoke test** — the Snowpark data path can't be tested locally (our unit tests
   run in mock mode). After deploy, switch the app to Snowflake mode and confirm a data
   product builds + a scorecard renders.

## Repository contents: runtime vs dev-only (C2)

The SiS Git integration **stages the whole repository**, but only a subset is used by the
running app. SiS serves no files from a web root (it runs `MAIN_FILE`), so the extra files
are **not a direct exposure** — but knowing the split keeps the deployment understandable
and the production surface minimal.

**Runtime (used by the deployed app):**

- `app.py` — the `MAIN_FILE` entry point
- `src/`, `config/`, `ui/`, `utils/` — application code imported by `app.py`
- `environment.yml` — the production dependency manifest (Anaconda channel)

**Dev / CI only (present in the repo but NOT used by the running app):**

- `tests/` — test suite (runs in CI / locally, never in SiS)
- `documents/`, `README.md`, `ARCHITECTURE.md`, `odin/` — documentation / compliance
- `notebooks/` — developer notebooks. ⚠ `notebooks/data_product_preview.ipynb` contains a
  **Snowflake connection example**; it reads credentials from the environment and holds no
  secret, but review it before it ships in the deploy source and keep it free of real
  account values.
- `requirements.txt` / `requirements.lock` — local/CI deps (PyPI); **superseded in SiS by
  `environment.yml`**
- `deploy/`, `.github/`, `pyproject.toml`, `Makefile`, `.pre-commit-config.yaml`,
  `.env.example` — tooling / deployment / config (not imported at runtime)
- `.env` — **gitignored and never committed** (local dev only; not present in SiS)

No application code imports anything from the dev-only paths, so the running SiS app loads
only the Runtime set above plus its declared dependencies.
