-- =============================================================================
-- ADMIN SETUP — Snowflake objects required by the EM CI/CD pipeline
-- (Snow CLI + key-pair auth). Replaces deploy/02_sis_deploy.sql entirely
-- (no PAT / SECRET / API INTEGRATION / GIT REPOSITORY in this model) and
-- supersedes the app-object part of deploy/01_least_privilege_role.sql
-- (its DATA-read grants are reproduced below and remain the core idea:
-- a least-privilege, READ-ONLY owner role).
--
-- Run once per environment as SECURITYADMIN/ACCOUNTADMIN, replacing every
-- <PLACEHOLDER>. Repeat the per-environment blocks for DEV / ACC / PRD.
-- =============================================================================

USE ROLE SECURITYADMIN;

-- 1) Streamlit owner role (single role across envs, per the platform template's
--    STREAMLIT_OWNER_ROLE variable). It owns the app objects and provides the
--    data access every viewer inherits (owner's rights) — keep it READ-ONLY.
CREATE ROLE IF NOT EXISTS DQS_STREAMLIT_OWNER
  COMMENT = 'Least-privilege read-only owner role for the Data Quality Scorecard SiS app (CI/CD deployed)';

-- 2) CI/CD service users — one per environment, key-pair auth only.
--    Generate the key pair per the template README:
--      openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8
--      openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
--    Store rsa_key.p8 + passphrase in Azure Key Vault (KEY_NAME_*/PASSPHRASE_NAME_*).
CREATE USER IF NOT EXISTS <CICD_USER_DEV>
  TYPE = SERVICE                          -- no password/MFA; key-pair only (VERIFY: TYPE=SERVICE available in the account edition)
  RSA_PUBLIC_KEY = '<RSA_PUBLIC_KEY_DEV>' -- contents of rsa_key.pub (no header/footer lines)
  DEFAULT_ROLE = DQS_STREAMLIT_OWNER
  DEFAULT_WAREHOUSE = <WAREHOUSE>
  COMMENT = 'CI/CD service user (DEV) for data-quality-scorecard';
GRANT ROLE DQS_STREAMLIT_OWNER TO USER <CICD_USER_DEV>;
-- Repeat CREATE USER + GRANT for <CICD_USER_ACC> and <CICD_USER_PRD>
-- (these map to the SNOWSQL_USER_DEV/ACC/PRD GitHub variables).

-- 3) Warehouse usage (compute for the app's queries and the deploys).
GRANT USAGE ON WAREHOUSE <WAREHOUSE> TO ROLE DQS_STREAMLIT_OWNER;
-- Optional: GRANT OPERATE ON WAREHOUSE <WAREHOUSE> TO ROLE DQS_STREAMLIT_OWNER;

-- 4) App database/schema per environment — where the Streamlit object and its
--    stage (DQS_APP_STAGE, auto-created by `snow streamlit deploy`) live.
--    These map to the APP_DATABASE_DEV/ACC/PRD + APP_SCHEMA GitHub variables.
USE ROLE SYSADMIN;
CREATE DATABASE IF NOT EXISTS <APP_DATABASE_DEV>;
CREATE SCHEMA   IF NOT EXISTS <APP_DATABASE_DEV>.<APP_SCHEMA>;

USE ROLE SECURITYADMIN;
GRANT USAGE  ON DATABASE <APP_DATABASE_DEV>                TO ROLE DQS_STREAMLIT_OWNER;
GRANT USAGE  ON SCHEMA   <APP_DATABASE_DEV>.<APP_SCHEMA>   TO ROLE DQS_STREAMLIT_OWNER;
GRANT CREATE STREAMLIT ON SCHEMA <APP_DATABASE_DEV>.<APP_SCHEMA> TO ROLE DQS_STREAMLIT_OWNER;
GRANT CREATE STAGE     ON SCHEMA <APP_DATABASE_DEV>.<APP_SCHEMA> TO ROLE DQS_STREAMLIT_OWNER;
-- Repeat block 4 for <APP_DATABASE_ACC> and <APP_DATABASE_PRD>.

-- 5) READ-ONLY access to the data the app reads (unchanged from
--    deploy/01_least_privilege_role.sql — SELECT only, never write/DDL).
-- Cost Estimate domain
GRANT USAGE   ON DATABASE INSIGHTS_DB                       TO ROLE DQS_STREAMLIT_OWNER;
GRANT USAGE   ON SCHEMA   INSIGHTS_DB.UC_GP_CSC             TO ROLE DQS_STREAMLIT_OWNER;
GRANT SELECT  ON ALL    TABLES IN SCHEMA INSIGHTS_DB.UC_GP_CSC TO ROLE DQS_STREAMLIT_OWNER;
GRANT SELECT  ON FUTURE TABLES IN SCHEMA INSIGHTS_DB.UC_GP_CSC TO ROLE DQS_STREAMLIT_OWNER;
GRANT SELECT  ON ALL    VIEWS  IN SCHEMA INSIGHTS_DB.UC_GP_CSC TO ROLE DQS_STREAMLIT_OWNER;
GRANT SELECT  ON FUTURE VIEWS  IN SCHEMA INSIGHTS_DB.UC_GP_CSC TO ROLE DQS_STREAMLIT_OWNER;
-- Quality domain
GRANT USAGE   ON DATABASE INGESTION_DB                      TO ROLE DQS_STREAMLIT_OWNER;
GRANT USAGE   ON SCHEMA   INGESTION_DB.GP_QUALITY           TO ROLE DQS_STREAMLIT_OWNER;
GRANT SELECT  ON ALL    TABLES IN SCHEMA INGESTION_DB.GP_QUALITY TO ROLE DQS_STREAMLIT_OWNER;
GRANT SELECT  ON FUTURE TABLES IN SCHEMA INGESTION_DB.GP_QUALITY TO ROLE DQS_STREAMLIT_OWNER;
GRANT SELECT  ON ALL    VIEWS  IN SCHEMA INGESTION_DB.GP_QUALITY TO ROLE DQS_STREAMLIT_OWNER;
GRANT SELECT  ON FUTURE VIEWS  IN SCHEMA INGESTION_DB.GP_QUALITY TO ROLE DQS_STREAMLIT_OWNER;

-- 6) Role hierarchy hygiene
GRANT ROLE DQS_STREAMLIT_OWNER TO ROLE SYSADMIN;

-- 7) Viewers: who may OPEN the app (per environment). Owner's rights means
--    viewers need only USAGE on the Streamlit object — no data grants.
--    Run AFTER the first pipeline deploy has created the object.
-- GRANT USAGE ON STREAMLIT <APP_DATABASE_PRD>.<APP_SCHEMA>.DATA_QUALITY_SCORECARD
--   TO ROLE <VIEWER_ROLE>;

-- =============================================================================
-- NOTES / VERIFY
-- - Single owner role across DEV/ACC/PRD follows the template's single
--   STREAMLIT_OWNER_ROLE variable. If the org requires stronger environment
--   separation, split into per-env roles and set STREAMLIT_OWNER_ROLE
--   accordingly per environment (would need a workflow tweak).
-- - "FUTURE" grants require SECURITYADMIN/ACCOUNTADMIN (or MANAGE GRANTS).
-- - Do NOT grant any write/DDL privilege on the DATA schemas — the app never
--   writes (read-only by design; verified in the Odin assessment).
-- =============================================================================
