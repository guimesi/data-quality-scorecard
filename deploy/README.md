# Streamlit in Snowflake (SiS) — deployment scripts

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
