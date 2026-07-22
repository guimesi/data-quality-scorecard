-- =============================================================================
-- F0 — App-state schema + append-only tables for the Data Quality Scorecard
-- =============================================================================
-- Run as SYSADMIN (DDL) after 01_least_privilege_role.sql. Replace every
-- <PLACEHOLDER>. NOT required until the app switches to
-- DQS_PERSISTENCE=snowflake — until then the app persists to local files
-- and never touches these tables.
--
-- Why: run history, adoption/audit telemetry and saved projects
-- (src/persistence.py) need durable storage. This is a DELIBERATE, SCOPED
-- exception to the read-only posture documented in 01_least_privilege_role.sql:
-- the app role gains INSERT+SELECT on THESE THREE TABLES ONLY — never UPDATE,
-- DELETE, TRUNCATE or any DDL — so persisted history is append-only and
-- tamper-evident by construction. Data schemas stay strictly read-only.
--
-- Layout: indexed columns for the fields features filter on, plus the full
-- record in PAYLOAD (VARIANT) — the payload is the source of truth,
-- reconstructed verbatim by SnowflakeStore.load().
-- =============================================================================

USE ROLE SYSADMIN;

-- 1) Dedicated state schema (keep app state away from the data schemas) -------
CREATE SCHEMA IF NOT EXISTS <APP_DB>.DQS_APP_STATE
  COMMENT = 'Append-only app state for the Data Quality Scorecard (run history, telemetry, saved projects)';

-- 2) Tables -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS <APP_DB>.DQS_APP_STATE.DQS_RUNS (
  TS            TIMESTAMP_TZ  NOT NULL,   -- UTC ISO stamp from the app
  USERNAME      VARCHAR       NOT NULL,   -- CURRENT_USER() inside SiS
  DOMAIN_CODE   VARCHAR,
  DP_CODE       VARCHAR,                  -- data product / system code
  CONFIG_HASH   VARCHAR,                  -- distinguishes data vs config changes
  PAYLOAD       VARIANT       NOT NULL    -- full run snapshot (source of truth)
);

CREATE TABLE IF NOT EXISTS <APP_DB>.DQS_APP_STATE.DQS_EVENTS (
  TS            TIMESTAMP_TZ  NOT NULL,
  USERNAME      VARCHAR       NOT NULL,
  EVENT_TYPE    VARCHAR       NOT NULL,   -- app_open / run / export / save ...
  DOMAIN_CODE   VARCHAR,
  PAYLOAD       VARIANT       NOT NULL
);

CREATE TABLE IF NOT EXISTS <APP_DB>.DQS_APP_STATE.DQS_PROJECTS (
  TS              TIMESTAMP_TZ  NOT NULL,
  USERNAME        VARCHAR       NOT NULL,
  PROJECT_NAME    VARCHAR       NOT NULL,
  VERSION         NUMBER        NOT NULL, -- append-only: each save = new row
  CHANGE_SUMMARY  VARCHAR,                -- human-readable "what changed"
  PAYLOAD         VARIANT       NOT NULL  -- full serialized project config
);

-- 3) Append-only grants to the app role (the scoped write exception) ----------
USE ROLE SECURITYADMIN;
GRANT USAGE  ON SCHEMA <APP_DB>.DQS_APP_STATE                    TO ROLE DQS_APP_ROLE;
GRANT INSERT, SELECT ON TABLE <APP_DB>.DQS_APP_STATE.DQS_RUNS     TO ROLE DQS_APP_ROLE;
GRANT INSERT, SELECT ON TABLE <APP_DB>.DQS_APP_STATE.DQS_EVENTS   TO ROLE DQS_APP_ROLE;
GRANT INSERT, SELECT ON TABLE <APP_DB>.DQS_APP_STATE.DQS_PROJECTS TO ROLE DQS_APP_ROLE;

-- =============================================================================
-- NOTES / VERIFY
-- - Do NOT grant UPDATE / DELETE / TRUNCATE / OWNERSHIP on these tables to
--   DQS_APP_ROLE: append-only is the audit guarantee. Corrections are an
--   admin operation under a separate role, leaving a trail.
-- - The app reaches this schema via DQS_STATE_SCHEMA (default DQS_APP_STATE)
--   and SNOWFLAKE_DATABASE; flip DQS_PERSISTENCE=snowflake to activate.
-- - Retention/PII: USERNAME is the Snowflake login; align retention of
--   DQS_EVENTS with your telemetry policy (e.g. a scheduled admin cleanup).
-- =============================================================================
