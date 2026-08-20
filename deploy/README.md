# Deploy — Databricks Apps

This app is deployed as a **Databricks App** (serverless container running
Streamlit). All data access is headless: the app's **service principal**
authenticates via OAuth injected by the platform, and queries run on a SQL
Warehouse against Unity Catalog. There is no browser-based auth anywhere in
the runtime.

## What's in this folder

| File | Purpose | Who runs it |
|---|---|---|
| `databricks/01_grants.sql` | Least-privilege Unity Catalog grants for the app's service principal | catalog admin, once per environment |
| `databricks/02_persistence_tables.sql` | DDL for the `DQS_RUNS` / `DQS_EVENTS` / `DQS_PROJECTS` app-state tables | schema owner, once per environment |

The runtime configuration itself lives at the repo root in
[`app.yaml`](../app.yaml) (start command + env vars + SQL Warehouse
resource mapping).

## Prerequisites

1. **Tables migrated.** Every application table (system tables, reference
   datasets `VWS_GP_STANDARD_SHARE` / `ACCE_COA_MASTER`, and the SQS
   inspection table) exists in
   `entai_sandbox_catalog.data_quality_scorecards.<TABLE_NAME>` with the
   same table names as the original Snowflake tables.
2. **A SQL Warehouse** the app can use (serverless recommended; small
   sizes are fine — the app reads with `SELECT`/`LIMIT` and writes only
   tiny app-state rows).

## Deploy steps

1. **Create the app** (workspace → *Compute → Apps → Create app*, or
   `databricks apps create dq-scorecard`). Creating it provisions the
   app's service principal.
2. **Attach the SQL Warehouse as an app resource** with permission
   *Can use* and resource key **`sql-warehouse`** — `app.yaml` maps that
   resource to the `DATABRICKS_WAREHOUSE_ID` env var. A different key
   breaks the mapping.
3. **Create the app-state tables**: run
   `databricks/02_persistence_tables.sql` on the warehouse.
   (Alternative while testing: set `DQS_PERSISTENCE=off` in `app.yaml`.)
4. **Grant data access**: run `databricks/01_grants.sql`, replacing
   `<APP_SERVICE_PRINCIPAL>` with the app's service principal id (shown
   on the app page).
5. **(Optional) Airtable write-back**: add `AIRTABLE_TOKEN` (as an app
   secret) and `AIRTABLE_BASE_ID` to the app's environment. Leave unset
   to hide the feature.
6. **Deploy the code**: from the repo root either
   ```bash
   databricks sync --watch . /Workspace/Users/<you>/dq-scorecard   # dev loop
   databricks apps deploy dq-scorecard --source-code-path /Workspace/Users/<you>/dq-scorecard
   ```
   or connect the repo in the workspace UI and press **Deploy**. The
   platform installs `requirements.txt` and runs the `command` from
   `app.yaml`.
7. **Share the app**: app page → *Permissions* → grant **Can use** to the
   user groups who should open it. App viewers authenticate with their
   own Databricks identity; the app forwards it (HTTP headers) into the
   run history / telemetry as `username`.

## Environment matrix

| Context | Identity | Warehouse | Config source |
|---|---|---|---|
| Databricks Apps (prod) | app service principal (OAuth, injected) | app resource `sql-warehouse` | `app.yaml` |
| Local dev vs real data | your PAT (`DATABRICKS_TOKEN`) | `DATABRICKS_WAREHOUSE_ID` in `.env` | `.env` (see `.env.example`) |
| Local dev / demo | none needed | none | `DATA_SOURCE=mock` (default) |

## Manual steps checklist (things the repo cannot do for you)

- [ ] Migrate/refresh the data tables into
      `entai_sandbox_catalog.data_quality_scorecards`
- [ ] Create the app and attach the SQL Warehouse (resource key
      `sql-warehouse`, Can use)
- [ ] Run `02_persistence_tables.sql`, then `01_grants.sql` (needs the
      app's service principal id)
- [ ] Configure Airtable secrets on the app (optional feature)
- [ ] Grant *Can use* on the app to the intended user groups
