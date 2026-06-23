-- =============================================================================
-- B1 — Least-privilege, READ-ONLY role for the Data Quality Scorecard SiS app
-- =============================================================================
-- Run as SECURITYADMIN (or ACCOUNTADMIN). Replace every <PLACEHOLDER>.
--
-- Why: under Streamlit in Snowflake the app runs with the OWNER role's rights.
-- This role is intended to OWN the Streamlit object (02_sis_deploy.sql), so it
-- must hold ONLY the read access the app needs — never a broad personal/admin
-- role. The app is read-only (SELECT only; no INSERT/UPDATE/DELETE/DDL), so this
-- role is granted SELECT and nothing that can mutate data.
--
-- Data the app reads (adjust to your actual schemas):
--   * Cost Estimate domain : INSIGHTS_DB.UC_GP_CSC
--   * Quality domain       : INGESTION_DB.GP_QUALITY
--   (plus any reference-dataset tables those rules look up, in the same schemas)
-- =============================================================================

USE ROLE SECURITYADMIN;

-- 1) The app role -------------------------------------------------------------
CREATE ROLE IF NOT EXISTS DQS_APP_ROLE
  COMMENT = 'Least-privilege read-only owner role for the Data Quality Scorecard SiS app';

-- 2) Warehouse usage (compute for the app's queries) --------------------------
GRANT USAGE ON WAREHOUSE <WAREHOUSE> TO ROLE DQS_APP_ROLE;
-- Optional: let the app start the warehouse if suspended (no resize/admin):
-- GRANT OPERATE ON WAREHOUSE <WAREHOUSE> TO ROLE DQS_APP_ROLE;

-- 3) Read access to the data schemas -----------------------------------------
-- Cost Estimate domain
GRANT USAGE   ON DATABASE INSIGHTS_DB                       TO ROLE DQS_APP_ROLE;
GRANT USAGE   ON SCHEMA   INSIGHTS_DB.UC_GP_CSC             TO ROLE DQS_APP_ROLE;
GRANT SELECT  ON ALL    TABLES IN SCHEMA INSIGHTS_DB.UC_GP_CSC TO ROLE DQS_APP_ROLE;
GRANT SELECT  ON FUTURE TABLES IN SCHEMA INSIGHTS_DB.UC_GP_CSC TO ROLE DQS_APP_ROLE;
-- If the app reads views as well as tables, also grant SELECT on views:
GRANT SELECT  ON ALL    VIEWS  IN SCHEMA INSIGHTS_DB.UC_GP_CSC TO ROLE DQS_APP_ROLE;
GRANT SELECT  ON FUTURE VIEWS  IN SCHEMA INSIGHTS_DB.UC_GP_CSC TO ROLE DQS_APP_ROLE;

-- Quality domain
GRANT USAGE   ON DATABASE INGESTION_DB                      TO ROLE DQS_APP_ROLE;
GRANT USAGE   ON SCHEMA   INGESTION_DB.GP_QUALITY           TO ROLE DQS_APP_ROLE;
GRANT SELECT  ON ALL    TABLES IN SCHEMA INGESTION_DB.GP_QUALITY TO ROLE DQS_APP_ROLE;
GRANT SELECT  ON FUTURE TABLES IN SCHEMA INGESTION_DB.GP_QUALITY TO ROLE DQS_APP_ROLE;
GRANT SELECT  ON ALL    VIEWS  IN SCHEMA INGESTION_DB.GP_QUALITY TO ROLE DQS_APP_ROLE;
GRANT SELECT  ON FUTURE VIEWS  IN SCHEMA INGESTION_DB.GP_QUALITY TO ROLE DQS_APP_ROLE;

-- 4) Usage on the app DB/schema where the Streamlit object will live ----------
-- (so the role can own/operate the app objects created in 02_sis_deploy.sql)
GRANT USAGE ON DATABASE <APP_DB>             TO ROLE DQS_APP_ROLE;
GRANT USAGE ON SCHEMA   <APP_DB>.<APP_SCHEMA> TO ROLE DQS_APP_ROLE;
GRANT CREATE STREAMLIT ON SCHEMA <APP_DB>.<APP_SCHEMA> TO ROLE DQS_APP_ROLE;
GRANT CREATE SECRET    ON SCHEMA <APP_DB>.<APP_SCHEMA> TO ROLE DQS_APP_ROLE;
GRANT CREATE GIT REPOSITORY ON SCHEMA <APP_DB>.<APP_SCHEMA> TO ROLE DQS_APP_ROLE;

-- 5) Assign the role so a human/automation can deploy & operate it ------------
GRANT ROLE DQS_APP_ROLE TO ROLE SYSADMIN;          -- role hierarchy hygiene
GRANT ROLE DQS_APP_ROLE TO USER <DEPLOY_USER>;     -- the person running 02_*

-- =============================================================================
-- NOTES / VERIFY
-- - This grants read-only access. Confirm the app's rules don't need any other
--   schema (e.g. a separate reference-data schema); add USAGE+SELECT for it.
-- - "FUTURE TABLES" grants require MANAGE GRANTS or ownership of the schema;
--   run as a role that can grant future privileges (SECURITYADMIN/ACCOUNTADMIN).
-- - Do NOT grant any write/DDL privilege — the app never writes.
-- =============================================================================
