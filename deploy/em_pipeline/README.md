# EM CI/CD pipeline — migration package for the org repo

This folder stages everything needed to deploy `data-quality-scorecard` through the
Data Warehousing Platform Team's GitHub Actions template (Snow CLI + key-pair auth +
Azure Key Vault + Erebor). The pristine template files the team provided live in
`../deploy_files/` for reference; the files here are the **adapted, ready-to-use**
versions for this app.

> **This model replaces the Snowflake-native Git-integration deploy** described in
> `../01_least_privilege_role.sql` / `../02_sis_deploy.sql` (PAT-as-SECRET, API
> INTEGRATION, GIT REPOSITORY, CREATE STREAMLIT ROOT_LOCATION). `02` is fully
> superseded; `01`'s data-grant content is carried into `ADMIN_SETUP.sql`.

## What goes where in the EM org repo

| File (here) | Destination in the org repo |
|---|---|
| `/.github/workflows/CICD.yml` | already in place at `.github/workflows/CICD.yml` (moved here from this folder) |
| `/snowflake.yml` (repo root) | repo root — already in place when the code is copied |
| `/config.toml` (repo root) | repo root — already in place when the code is copied |
| `ADMIN_SETUP.sql` | not committed to the pipeline — run manually by the Snowflake admin, once per environment |
| whole app source (`app.py`, `src/`, `ui/`, `config/`, `utils/`, `environment.yml`, `tests/`, `.github/workflows/tests.yml` + `security.yml`) | copied as-is; the app is NOT moved into `STREAMLIT_APPS/` (see below) |

**Why no `STREAMLIT_APPS/` folder:** Snow CLI artifacts cannot reference paths outside
the project directory, and this app is multi-module (`app.py` imports `src/`, `ui/`,
`config/`, `utils/`). Keeping the repo root as the Snow CLI project preserves local
development (`streamlit run app.py`) and the ~1,250 tests unchanged. The template's
`STREAMLIT_APPS/` layout is for repos hosting multiple single-file apps.

**Dropped from the template (Streamlit-only scope):** the SQL migration machinery —
SnowSQL install, `OrderScriptsBasedOnDependencyV2.py`, `RemovePrePostDuplicatesV2.py`,
`deploy_dbobjectsV2.sh`, `Migrate/Pre|Post`, `APPS/object_hierarchy.txt`. The app only
reads existing data; it creates no DB objects. If DB migrations are ever needed,
restore those steps/files from the template (the two helper `.py` files must be copied
from the template repo — they were not provided in `deploy_files/`).

## GitHub configuration (Settings → Secrets and variables → Actions)

**Secrets**

| Name | Purpose |
|---|---|
| `AZURE_CLIENT_ID` | Erebor scan (`actions-erebor` input) |
| `AZURE_CREDENTIALS` | `azure/login@v2` service-principal JSON. ⚠ The template README omits this but its own CICD.yml requires it |
| `PAT` | listed by the template README for Erebor; the workflow we kept does not echo it (template line removed per its own security note) |

**Variables**

| Name | Value |
|---|---|
| `VAULT_NAME` | Azure Key Vault name |
| `SNOWSQL_ACCOUNT` | Snowflake account identifier |
| `WAREHOUSE` | warehouse for deploys + app queries (also feeds `snowflake.yml` via `ctx.env`) |
| `STREAMLIT_OWNER_ROLE` | `DQS_STREAMLIT_OWNER` (created in `ADMIN_SETUP.sql`) |
| `SNOWSQL_USER_DEV/ACC/PRD` | CI/CD service users (created in `ADMIN_SETUP.sql`) |
| `KEY_NAME_DEV/ACC/PRD` | Key Vault secret names holding each private key |
| `PASSPHRASE_NAME_DEV/ACC/PRD` | Key Vault secret names holding each passphrase |
| `APP_DATABASE_DEV/ACC/PRD` | **new (this app):** database where the Streamlit object + stage live per env |
| `APP_SCHEMA` | **new (this app):** schema for the Streamlit object + stage |

## Platform prerequisites (owned by admins — see template README §Prerequisites)

1. Azure Key Vault + the 6 secrets (3 private keys, 3 passphrases); key pairs generated
   per the template README (`openssl genrsa 2048 | openssl pkcs8 ...`).
2. Snowflake service users with `RSA_PUBLIC_KEY` set (`ADMIN_SETUP.sql` §2).
3. Roles/warehouse/app DB+schema/data grants (`ADMIN_SETUP.sql` §§1,3–6).
4. Repo created inside the EM GitHub org (the Erebor action `EMOrg-Prd/actions-erebor`
   and org-level OIDC/vars do not work from a personal repo).
5. Branch protection on `main` (PRD) — also an open Odin follow-up.

## Branch mapping (template standard)

`development` → DEV · `acceptance` → ACC · `main` → PRD.
This repo's branches were aligned accordingly (`dev` renamed to `development`;
`acceptance` created). `tests.yml`/`security.yml` triggers updated to match.

## VERIFY on first pipeline run

- Snowflake CLI 3.x accepts the root `snowflake.yml` (definition_version 2) and
  directory entries in `artifacts` (fallback: globs `src/**/*.py`, …).
- `snow streamlit deploy` auto-creates stage `DQS_APP_STAGE` under
  `APP_DATABASE_*.APP_SCHEMA` (role has CREATE STAGE).
- `--private-key-file` flag name on the pinned CLI version.
- Erebor action version (`@v5`) still current with the platform team.
- After first deploy: grant viewers USAGE on the STREAMLIT object (`ADMIN_SETUP.sql` §7)
  and run the post-deploy smoke test (switch app to Snowflake mode; build a data
  product; render a scorecard) — an open item in `odin/sis_migration_changes.md`.

## Docs to reconcile after the move (Odin)

The Odin assessment (`odin/`) still describes the Snowflake-native Git-integration
deploy (PAT-as-SECRET, Git repository object). Once this pipeline is confirmed,
update: `architecture_design_and_threat_modeling.md`, `authentication.md` (Service
Authentication), `cryptography.md`/`iot_security.md` (secret management → key-pair in
Azure Key Vault), `malicious_code.md` (deploy path), `sis_migration_changes.md` (§5),
and mark **Erebor as integrated in CI** (currently listed as a pending follow-up).
