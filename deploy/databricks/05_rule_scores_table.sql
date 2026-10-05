-- =============================================================================
-- DQS_RULE_SCORES: per-rule score history (persistence backend "databricks")
-- =============================================================================
-- Run once per environment on any SQL Warehouse, as a principal with CREATE
-- TABLE on the schema, then the GRANT as an admin. The app
-- (src/persistence.py, save_rule_scores) only INSERTs; it never creates or
-- alters the table.
--
-- One row per recorded run (a DQS_RUNS row) and rule, written automatically
-- whenever the run history records a run - the same pass rates the DQS_RUNS
-- JSON payload carries, flattened so the trend of one rule is a plain
-- WHERE RULE_ID = ... . Append-only.
--
--   * RUN_ID is the DQS_RUNS payload id ("snap_<ts>_<DP>"): join with
--       get_json_object(r.PAYLOAD, '$.payload.id') = s.RUN_ID
--   * RULE_TYPE is 'Standard' (RULE_ID = '<CDE>::<Dimension>', CDE and
--     DIMENSION filled) or 'Custom' (RULE_ID = catalog code, RULE_NAME and
--     DIMENSION = the rule's type from the catalog).
--   * SCORE is the rule's pass rate, 0-100.

CREATE TABLE IF NOT EXISTS entai_sandbox_catalog.data_quality_scorecards.DQS_RULE_SCORES (
    RUN_ID      STRING COMMENT 'DQS_RUNS payload id of the run',
    TS          STRING COMMENT 'UTC ISO-8601, stamped by the app',
    USERNAME    STRING COMMENT 'Forwarded app viewer identity (or OS user locally)',
    DOMAIN_CODE STRING,
    DP_CODE     STRING,
    CONFIG_HASH STRING,
    RULE_ID     STRING COMMENT 'Standard: <CDE>::<Dimension>; Custom: catalog code',
    RULE_TYPE   STRING COMMENT 'Standard | Custom',
    RULE_NAME   STRING,
    CDE         STRING COMMENT 'Standard rules only',
    DIMENSION   STRING,
    SCORE       DOUBLE COMMENT 'Pass rate of the rule in this run, 0-100'
) COMMENT 'DQ Scorecard: per-rule score history, one row per recorded run and rule (append-only)';

GRANT MODIFY ON TABLE entai_sandbox_catalog.data_quality_scorecards.DQS_RULE_SCORES TO `<APP_SERVICE_PRINCIPAL>`;
