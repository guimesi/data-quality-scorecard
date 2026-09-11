-- =============================================================================
-- Report store: Unity Catalog Volume for the Data Quality Report artefacts
-- =============================================================================
-- Run once per environment as a principal with CREATE VOLUME on the schema.
-- The app (src/report_store.py, backend "volume") writes every run's report
-- artefacts here through the Databricks Files API and serves the interactive
-- edition at /reports/<run_id> (server.py) - the link pasted in SharePoint,
-- which sanitises .html files. Objects per run:
--   <run_id>.html         interactive edition        <run_id>.pdf   PDF edition
--   <run_id>.print.html   print-ready HTML           <run_id>.json  metadata
--
-- app.yaml points DQS_REPORT_VOLUME at this path; keep them in sync.

CREATE VOLUME IF NOT EXISTS entai_sandbox_catalog.data_quality_scorecards.dq_reports
    COMMENT 'DQ Scorecard: Data Quality Report artefacts per run (served at /reports/<run_id>)';

-- The app's service principal needs to read and write the Volume (replace
-- <APP_SERVICE_PRINCIPAL> as in 01_grants.sql; USE CATALOG / USE SCHEMA are
-- already granted there).
GRANT READ VOLUME, WRITE VOLUME
    ON VOLUME entai_sandbox_catalog.data_quality_scorecards.dq_reports
    TO `<APP_SERVICE_PRINCIPAL>`;
