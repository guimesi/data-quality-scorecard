# Databricks notebook source
# MAGIC %md
# MAGIC # DQ Scorecard - scheduled report
# MAGIC
# MAGIC Runs the scorecard for one domain and publishes the Data Quality
# MAGIC Report **without opening the Streamlit app**: history recorded,
# MAGIC interactive HTML + PDF stored in the report-store workspace folder
# MAGIC (served by the app at `/reports/<run_id>` and `/reports/latest/<DOMAIN>`),
# MAGIC scores pushed to Airtable when configured.
# MAGIC
# MAGIC Meant to be scheduled as a **Databricks Job** whose source is this
# MAGIC repository (Git source, branch of your choice) and whose task is this
# MAGIC notebook - see `deploy/README.md`, step 8, and `job_dq_report.json`.
# MAGIC The job runs as *you* (or whoever owns it): it reads the data tables and
# MAGIC writes the `DQS_*` tables and the report folder with that identity, so
# MAGIC no extra grants are needed beyond what the dashboard already uses.
# MAGIC
# MAGIC Parameters (job "base parameters" / notebook widgets):
# MAGIC
# MAGIC | name | example | meaning |
# MAGIC |---|---|---|
# MAGIC | `domain` | `cost_estimate` | domain code (required) |
# MAGIC | `systems` | `ACCE,ADR` | system codes; empty = every system of the domain |
# MAGIC | `project_filter` | `PV-10422,PV-10587` | PLANVIEW ids; empty = no filter |
# MAGIC | `warehouse_id` | `abc123def456` | SQL Warehouse id (same one the app uses) |
# MAGIC | `report_workspace_dir` | `/Workspace/Users/you@corp.com/dq_reports` | report-store folder (same as `app.yaml`) |
# MAGIC | `want_pdf` | `true` | render the PDF (needs Chromium, see `init_chromium.sh`) |
# MAGIC | `airtable_base_id` | `appXXXX` | Airtable base; empty = no push |
# MAGIC | `airtable_secret_scope` / `airtable_secret_key` | `dq-scorecard` / `airtable-token` | where the Airtable token lives |

# COMMAND ----------

# MAGIC %pip install -q -r ../../requirements.txt
# MAGIC %pip install -q playwright

# COMMAND ----------

dbutils.library.restartPython()  # noqa: F821 - Databricks runtime global

# COMMAND ----------

import os
import subprocess
import sys

# The notebook lives in deploy/databricks/ of the repo checkout; the code
# imports from the repo root.
ROOT = os.path.abspath(os.path.join(os.getcwd(), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

dbutils.widgets.text("domain", "cost_estimate")  # noqa: F821
dbutils.widgets.text("systems", "")  # noqa: F821
dbutils.widgets.text("project_filter", "")  # noqa: F821
dbutils.widgets.text("warehouse_id", "")  # noqa: F821
dbutils.widgets.text("report_workspace_dir", "")  # noqa: F821
dbutils.widgets.dropdown("want_pdf", "true", ["true", "false"])  # noqa: F821
dbutils.widgets.text("airtable_base_id", "")  # noqa: F821
dbutils.widgets.text("airtable_secret_scope", "dq-scorecard")  # noqa: F821
dbutils.widgets.text("airtable_secret_key", "airtable-token")  # noqa: F821


def _w(name: str) -> str:
    return dbutils.widgets.get(name).strip()  # noqa: F821


# Same environment the app runs with (app.yaml), minus the app-only bits.
os.environ["DATA_SOURCE"] = "databricks"
os.environ["DQS_PERSISTENCE"] = "databricks"
if _w("warehouse_id"):
    os.environ["DATABRICKS_WAREHOUSE_ID"] = _w("warehouse_id")
if _w("report_workspace_dir"):
    os.environ["DQS_REPORT_STORE"] = "workspace"
    os.environ["DQS_REPORT_WORKSPACE_DIR"] = _w("report_workspace_dir")
else:
    os.environ["DQS_REPORT_STORE"] = "off"
if _w("airtable_base_id"):
    os.environ["AIRTABLE_BASE_ID"] = _w("airtable_base_id")
    try:
        os.environ["AIRTABLE_TOKEN"] = dbutils.secrets.get(  # noqa: F821
            _w("airtable_secret_scope"), _w("airtable_secret_key"))
    except Exception as exc:  # no scope / key: push is skipped, run goes on
        print(f"Airtable token not available ({exc}); scores will not be pushed")

# Headless Chromium for the PDF edition. `init_chromium.sh` (cluster init
# script) pre-installs it; this is the fallback for clusters without it.
if _w("want_pdf") == "true":
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                       check=True, capture_output=True, timeout=600)
    except Exception as exc:
        print(f"Chromium not installed ({exc}); the print-ready HTML is stored instead")

# COMMAND ----------

from scripts.run_scheduled_report import main  # noqa: E402

argv = ["--domain", _w("domain")]
if _w("systems"):
    argv += ["--systems", _w("systems")]
if _w("project_filter"):
    argv += ["--project-filter", _w("project_filter")]
if _w("want_pdf") != "true":
    argv.append("--no-pdf")

exit_code = main(argv)
if exit_code != 0:
    raise RuntimeError("Scheduled report run is not usable - see the JSON summary above")
