-- =============================================================================
-- Unity Catalog grants for the Data Quality Scorecard app (Databricks Apps)
-- =============================================================================
-- Run once per environment, as a metastore/catalog admin, AFTER the app has
-- been created (creating the app provisions its service principal).
--
-- Replace <APP_SERVICE_PRINCIPAL> with the app's service principal
-- application-id (shown on the app page under "App resources" / identity;
-- backticks required around it).
--
-- Least privilege:
--   * read-only on the data tables in the app namespace;
--   * MODIFY only on the three DQS_* app-state tables
--     (created by 02_persistence_tables.sql).
-- The SQL Warehouse the app uses is attached as an app *resource* with
-- CAN_USE permission - that grant lives in the app configuration, not here.

-- Make the namespace reachable.
GRANT USE CATALOG ON CATALOG entai_sandbox_catalog TO `<APP_SERVICE_PRINCIPAL>`;
GRANT USE SCHEMA  ON SCHEMA  entai_sandbox_catalog.data_quality_scorecards TO `<APP_SERVICE_PRINCIPAL>`;

-- Read every application table (system tables + reference datasets).
GRANT SELECT ON SCHEMA entai_sandbox_catalog.data_quality_scorecards TO `<APP_SERVICE_PRINCIPAL>`;

-- Write access restricted to the app-state tables (persistence layer).
GRANT MODIFY ON TABLE entai_sandbox_catalog.data_quality_scorecards.DQS_RUNS     TO `<APP_SERVICE_PRINCIPAL>`;
GRANT MODIFY ON TABLE entai_sandbox_catalog.data_quality_scorecards.DQS_EVENTS   TO `<APP_SERVICE_PRINCIPAL>`;
GRANT MODIFY ON TABLE entai_sandbox_catalog.data_quality_scorecards.DQS_PROJECTS TO `<APP_SERVICE_PRINCIPAL>`;
