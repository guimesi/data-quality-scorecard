-- =============================================================================
-- DQS_* app-state tables (persistence backend "databricks")
-- =============================================================================
-- Run once per environment on any SQL Warehouse, as a principal with CREATE
-- TABLE on the schema. The app (src/persistence.py) INSERTs and SELECTs
-- these tables; it never creates or alters them.
--
-- Design notes (mirrors the original Snowflake DQS_* tables):
--   * Append-only: the app only ever INSERTs; history is the audit trail.
--   * A few record keys are promoted to real columns for ad-hoc querying;
--     the FULL record always travels in PAYLOAD as a JSON string, and reads
--     reconstruct records exclusively from PAYLOAD (no column drift).
--   * TS is the app-stamped UTC ISO-8601 timestamp (string). The fixed
--     format makes lexicographic ORDER BY TS chronological.

CREATE TABLE IF NOT EXISTS entai_sandbox_catalog.data_quality_scorecards.DQS_RUNS (
    TS          STRING COMMENT 'UTC ISO-8601, stamped by the app',
    USERNAME    STRING COMMENT 'Forwarded app viewer identity (or OS user locally)',
    DOMAIN_CODE STRING,
    DP_CODE     STRING,
    CONFIG_HASH STRING,
    PAYLOAD     STRING COMMENT 'Full record as JSON - single source of truth'
) COMMENT 'DQ Scorecard: one row per scorecard run snapshot (append-only)';

CREATE TABLE IF NOT EXISTS entai_sandbox_catalog.data_quality_scorecards.DQS_EVENTS (
    TS          STRING COMMENT 'UTC ISO-8601, stamped by the app',
    USERNAME    STRING COMMENT 'Forwarded app viewer identity (or OS user locally)',
    EVENT_TYPE  STRING,
    DOMAIN_CODE STRING,
    PAYLOAD     STRING COMMENT 'Full record as JSON - single source of truth'
) COMMENT 'DQ Scorecard: adoption / audit telemetry events (append-only)';

CREATE TABLE IF NOT EXISTS entai_sandbox_catalog.data_quality_scorecards.DQS_PROJECTS (
    TS             STRING COMMENT 'UTC ISO-8601, stamped by the app',
    USERNAME       STRING COMMENT 'Forwarded app viewer identity (or OS user locally)',
    PROJECT_NAME   STRING,
    VERSION        INT,
    CHANGE_SUMMARY STRING,
    PAYLOAD        STRING COMMENT 'Full record as JSON - single source of truth'
) COMMENT 'DQ Scorecard: saved-project versions = audit changelog (append-only)';
