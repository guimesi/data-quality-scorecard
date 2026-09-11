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
| `databricks/03_report_volume.sql` | Unity Catalog Volume `dq_reports` (+ grants) holding every run's Data Quality Report artefacts, served at `/reports/<run_id>` | schema owner, once per environment |

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
5b. **Report store (hosted Data Quality Reports)** - no admin needed:
   1. In the workspace browser create a folder, e.g.
      `Workspace → Users → <you> → dq_reports`.
   2. On that folder choose **Share** and add the app's service principal
      (the `app-xxxx ...` identity shown on the app page) with **Can
      Manage** (verified: *Can Edit* is not enough for the Workspace API
      to create the per-domain sub-folders and files).
   3. In `app.yaml` set `DQS_REPORT_WORKSPACE_DIR` to the folder
      (`/Workspace/Users/<you>/dq_reports`); `DQS_REPORT_STORE` is already
      `workspace`.
   The app then serves every run at `https://<app-url>/reports/<run_id>`
   (index at `/reports`) and the newest run of a domain at the fixed link
   `https://<app-url>/reports/latest/<DOMAIN>` (`/pdf` for the PDF) - what
   to paste in SharePoint or behind an Airtable button. Files also appear
   in the folder, so the PDF can be downloaded from the workspace browser:
   one sub-folder per domain, files named
   `<DOMAIN>__<DP1-DP2>__<YYYYMMDD_HHMMSS>_<hex>.html|.pdf|.print.html|.json`
   (the run id), so "which domain, which systems, when" is readable at a
   glance.
   Retention: `DQS_REPORT_KEEP_RUNS` newest runs per domain (default 30).
   Per-file limit of the Workspace API: 10 MB.
   Alternative with a Unity Catalog admin: `DQS_REPORT_STORE=volume` +
   `DQS_REPORT_VOLUME`, after `databricks/03_report_volume.sql`. Set
   `DQS_REPORT_STORE=off` to disable hosting (downloads keep working).
5c. **(Optional) PDF edition**: the PDF is rendered by headless Chromium.
   The Apps container has none by default, so the app offers the
   print-ready HTML instead (Ctrl+P in Chrome/Edge produces the same PDF).
   To render server-side, add `playwright` to `requirements.txt` and make
   the Chromium download available to the container (e.g.
   `playwright install chromium` in a custom start command, with
   `PLAYWRIGHT_BROWSERS_PATH` on a writable path), or point
   `DQS_CHROMIUM_PATH` at a Chromium binary available in the image.
5d. **(Optional) SharePoint publishing** (Step 6 "Publish to SharePoint",
   `src/sharepoint_push.py`): the app uploads each run's PDF, interactive
   HTML and a metadata `.json` (with the hosted `/reports/<run_id>` link)
   to a document library through Microsoft Graph, under
   `<SHAREPOINT_FOLDER>/<DOMAIN>/`, plus fixed-name `_latest` copies for
   static links. IT steps (Entra ID + SharePoint admin):
   1. Register an application in Entra ID (*App registrations → New*),
      note the **Tenant ID** and **Application (client) ID**, create a
      **client secret** (note its expiry - it must be rotated).
   2. API permissions → *Microsoft Graph → Application permissions* →
      **`Sites.Selected`** → *Grant admin consent*. This permission alone
      gives access to no site.
   3. Grant the app **write** on the target site only, e.g. with PnP
      PowerShell: `Grant-PnPAzureADAppSitePermission -AppId <client-id>
      -DisplayName "DQ Scorecard" -Site https://<host>.sharepoint.com/sites/<name>
      -Permissions Write`, or `POST /sites/{site-id}/permissions` in Graph
      by a site owner.
   4. On the app: store the secret in the app secret resource
      **`sharepoint-client-secret`** and fill `SHAREPOINT_TENANT_ID`,
      `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_SITE`
      (`<host>.sharepoint.com:/sites/<name>` or the Graph site id) and,
      optionally, `SHAREPOINT_DRIVE_ID` / `SHAREPOINT_FOLDER` in `app.yaml`.
      The button stays hidden until the four required values are set.
   Outbound HTTPS to `login.microsoftonline.com` and
   `graph.microsoft.com` is all the network needs.
6. **Deploy the code**: from the repo root either
   ```bash
   databricks sync --watch . /Workspace/Users/<you>/dq-scorecard   # dev loop
   databricks apps deploy dq-scorecard --source-code-path /Workspace/Users/<you>/dq-scorecard
   ```
   or connect the repo in the workspace UI and press **Deploy**. The
   platform installs `requirements.txt` and runs the `command` from
   `app.yaml` (`streamlit run server.py` - the `st.App` entry point that
   serves the Streamlit UI plus the `/reports` routes; `streamlit run
   app.py` is the UI-only local equivalent).
7. **Share the app**: app page → *Permissions* → grant **Can use** to the
   user groups who should open it. App viewers authenticate with their
   own Databricks identity; the app forwards it (HTTP headers) into the
   run history / telemetry as `username`.

8. **Scheduled runs without the UI (Databricks Job)**: the scorecard +
   report can run on a schedule with no Streamlit involved -
   `src/scheduled_report.py` scores a domain (One-click pipeline),
   records the run history, builds both report editions, stores them in
   the same report folder the app serves (`/reports/<run_id>`,
   `/reports/latest/<DOMAIN>`) and pushes the scores to Airtable when
   configured. Set it up once:
   1. **Job** → *Create job*, task type **Notebook**, source **Git**
      (this repository, the branch to run), path
      `deploy/databricks/scheduled_report_job` (the notebook in
      `deploy/databricks/scheduled_report_job.py`). Or import
      `deploy/databricks/job_dq_report.json` after replacing its `<...>`
      placeholders (`databricks jobs create --json @…`).
   2. **Compute**: a small single-node job cluster. For the PDF edition
      attach `deploy/databricks/init_chromium.sh` as a workspace-file init
      script (installs Playwright's Chromium with its system libraries).
      Without it the notebook tries `playwright install chromium` itself
      and, failing that, stores the print-ready HTML instead of the PDF.
   3. **Parameters** (notebook base parameters): `domain`, optional
      `systems` (empty = every system of the domain), `project_filter`,
      `warehouse_id` (the SQL warehouse the app uses),
      `report_workspace_dir` (the same folder as `app.yaml`), `want_pdf`,
      and for Airtable `airtable_base_id` + the secret scope/key holding
      the token (`databricks secrets create-scope dq-scorecard`,
      `databricks secrets put-secret dq-scorecard airtable-token`).
   4. **Schedule** (e.g. weekdays 06:00 `America/Sao_Paulo`) and a failure
      e-mail. The run **fails** when no system could be scored or the
      report could not be stored; the JSON summary at the end of the run
      output says why (`skipped`, `store_error`, `airtable_error`).
   The job runs as its owner: the data tables, the `DQS_*` tables and the
   report folder are accessed with your identity, so nothing new has to
   be granted. Locally the same entry point runs against mock data:
   `DATA_SOURCE=mock python scripts/run_scheduled_report.py --domain cost_estimate --no-pdf`.

## Environment matrix

| Context | Identity | Warehouse | Config source |
|---|---|---|---|
| Databricks Apps (prod) | app service principal (OAuth, injected) | app resource `sql-warehouse` | `app.yaml` |
| Local dev vs real data | your PAT (`DATABRICKS_TOKEN`) | `DATABRICKS_WAREHOUSE_ID` in `.env` | `.env` (see `.env.example`) |
| Local dev / demo | none needed | none | `DATA_SOURCE=mock` (default) |
| Scheduled Job | the job owner (notebook auth) | `warehouse_id` parameter | notebook parameters (`scheduled_report_job.py`) |

## Manual steps checklist (things the repo cannot do for you)

- [ ] Migrate/refresh the data tables into
      `entai_sandbox_catalog.data_quality_scorecards`
- [ ] Create the app and attach the SQL Warehouse (resource key
      `sql-warehouse`, Can use)
- [ ] Run `02_persistence_tables.sql`, then `01_grants.sql` (needs the
      app's service principal id)
- [ ] Configure Airtable secrets on the app (optional feature)
- [ ] SharePoint publishing (optional): Entra app registration with
      `Sites.Selected`, write grant on the target site, secret resource
      `sharepoint-client-secret`, `SHAREPOINT_*` values in `app.yaml`
- [ ] Report store: create the `dq_reports` workspace folder, share it
      with the app's service principal (Can Manage), set
      `DQS_REPORT_WORKSPACE_DIR` (or `03_report_volume.sql` + `volume`,
      or `DQS_REPORT_STORE=off`)
- [ ] Scheduled runs (optional): create the Job from
      `job_dq_report.json` / the notebook, attach `init_chromium.sh`,
      set the parameters and the schedule
- [ ] Decide on the PDF edition: print-ready HTML (default) or a
      Chromium in the container (optional)
- [ ] Grant *Can use* on the app to the intended user groups
