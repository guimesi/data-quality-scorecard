-- =============================================================================
-- A4 — Deploy the Data Quality Scorecard as a Streamlit in Snowflake (SiS) app
--      from this GitHub repository.
-- =============================================================================
-- Prerequisite: run 01_least_privilege_role.sql first (creates DQS_APP_ROLE).
-- Replace every <PLACEHOLDER>. Steps are marked with the role they require.
--
-- Objects created:
--   1. SECRET           – stores the GitHub Personal Access Token (PAT)
--   2. API INTEGRATION  – allows Snowflake to reach github.com (ACCOUNTADMIN)
--   3. GIT REPOSITORY   – points at this repo; acts as a stage Snowflake reads
--   4. STREAMLIT        – the app object (built from environment.yml + app.py)
--   5. GRANT USAGE      – which viewer role(s) may open the app
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1) GitHub PAT stored as a Snowflake SECRET (never put the PAT in the repo)
--    Run as DQS_APP_ROLE (it has CREATE SECRET on the app schema).
--    The PAT needs READ (contents) access to the repository.
-- -----------------------------------------------------------------------------
USE ROLE DQS_APP_ROLE;
USE SCHEMA <APP_DB>.<APP_SCHEMA>;

CREATE OR REPLACE SECRET github_dqs_secret
  TYPE = password
  USERNAME = '<GH_USER>'
  PASSWORD = '<GH_PAT>'     -- GitHub Personal Access Token (read access)
  COMMENT = 'GitHub PAT for the data-quality-scorecard Git integration';

-- -----------------------------------------------------------------------------
-- 2) API integration for GitHub (account-level object → ACCOUNTADMIN)
--    Restrict the allowed prefix to your org so the integration can only reach
--    your repositories.
-- -----------------------------------------------------------------------------
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE API INTEGRATION github_dqs_api_integration
  API_PROVIDER = git_https_api
  API_ALLOWED_PREFIXES = ('https://github.com/<GH_ORG>')
  ALLOWED_AUTHENTICATION_SECRETS = (<APP_DB>.<APP_SCHEMA>.github_dqs_secret)
  ENABLED = TRUE
  COMMENT = 'GitHub access for data-quality-scorecard SiS deployment';

-- Let the app role use the integration:
GRANT USAGE ON INTEGRATION github_dqs_api_integration TO ROLE DQS_APP_ROLE;

-- -----------------------------------------------------------------------------
-- 3) Git repository object (acts as a read-only stage of the repo)
--    Run as DQS_APP_ROLE.
-- -----------------------------------------------------------------------------
USE ROLE DQS_APP_ROLE;
USE SCHEMA <APP_DB>.<APP_SCHEMA>;

CREATE OR REPLACE GIT REPOSITORY dqs_repo
  API_INTEGRATION = github_dqs_api_integration
  GIT_CREDENTIALS = <APP_DB>.<APP_SCHEMA>.github_dqs_secret
  ORIGIN = 'https://github.com/<GH_ORG>/data-quality-scorecard.git'
  COMMENT = 'Source repo for the Data Quality Scorecard SiS app';

-- Pull the latest commits (re-run this to sync new commits before re-deploy):
ALTER GIT REPOSITORY dqs_repo FETCH;

-- Sanity check: list files on the deploy branch (expect app.py + environment.yml)
LS @dqs_repo/branches/<DEPLOY_BRANCH>/;

-- -----------------------------------------------------------------------------
-- 4) Create the Streamlit app from the repo branch.
--    ROOT_LOCATION points at the repo root on the deploy branch; environment.yml
--    and app.py both live there. The app runs with DQS_APP_ROLE's rights
--    (owner's rights), on <WAREHOUSE>.
--    Run as DQS_APP_ROLE.
--
--    VERIFY: exact CREATE STREAMLIT clause names can vary by account/version.
--    Some accounts use `FROM '@...stage/path' MAIN_FILE='app.py'` instead of
--    ROOT_LOCATION/MAIN_FILE. Cross-check in Snowsight if this errors.
-- -----------------------------------------------------------------------------
CREATE OR REPLACE STREAMLIT data_quality_scorecard
  ROOT_LOCATION = '@<APP_DB>.<APP_SCHEMA>.dqs_repo/branches/<DEPLOY_BRANCH>'
  MAIN_FILE = 'app.py'
  QUERY_WAREHOUSE = <WAREHOUSE>
  TITLE = 'Data Quality Scorecard'
  COMMENT = 'Data Quality Scorecard — deployed from GitHub (branch <DEPLOY_BRANCH>)';

-- -----------------------------------------------------------------------------
-- 5) Grant who may OPEN the app (decide the audience deliberately).
--    Viewers need only USAGE on the Streamlit object — owner's rights means they
--    do NOT need SELECT on the underlying data (the app role provides it).
--    Run as DQS_APP_ROLE (owner) or SECURITYADMIN.
-- -----------------------------------------------------------------------------
GRANT USAGE ON STREAMLIT <APP_DB>.<APP_SCHEMA>.data_quality_scorecard
  TO ROLE <VIEWER_ROLE>;

-- =============================================================================
-- VERIFY / OPERATE
--   SHOW STREAMLITS IN SCHEMA <APP_DB>.<APP_SCHEMA>;
--   -- Open the app from Snowsight: Projects → Streamlit → Data Quality Scorecard
--
-- Re-deploy after pushing new commits to <DEPLOY_BRANCH>:
--   USE ROLE DQS_APP_ROLE;
--   ALTER GIT REPOSITORY <APP_DB>.<APP_SCHEMA>.dqs_repo FETCH;
--   -- the Streamlit picks up the refreshed branch contents
--
-- When promoting from test (dev) to prod: re-point or recreate the STREAMLIT
-- with ROOT_LOCATION '.../branches/main' (and add branch protection on main).
-- =============================================================================
