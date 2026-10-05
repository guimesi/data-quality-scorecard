-- =============================================================================
-- DQS_FAILS_<DOMAIN>_<DP> failed-row tables (persistence backend "databricks")
-- =============================================================================
-- Run once per environment on any SQL Warehouse, as a principal with CREATE
-- TABLE on the schema, then run the GRANTs at the bottom as an admin. The
-- app (src/persistence.py, save_failed_rows) only DELETEs from and INSERTs
-- into these tables; it never creates or alters them.
--
-- One table per (domain, data product), all with the same shape, holding
-- the failed rows of the LATEST SAVED RUN only: every save (the Step 6
-- "Save failed rows" button, or the scheduled job) empties the table and
-- writes the rows failing at least one evaluated rule - optionally capped
-- by DQS_FAILS_MAX_ROWS (lowest row score first; 0 = every failing row).
-- The per-run history lives in DQS_RUNS / DQS_RULE_SCORES, not here.
--
-- Design notes:
--   * RUN_ID is the DQS_RUNS payload id ("snap_<ts>_<DP>"): join with
--       get_json_object(r.PAYLOAD, '$.payload.id') = f.RUN_ID
--     ("unrecorded_..." when the run was never recorded in the history).
--   * TOTAL_FAILED_ROWS is the run's full failing-row count, repeated on
--     every row: COUNT(*) < TOTAL_FAILED_ROWS means the save was capped.
--   * FAILED_RULES is a JSON array of rule ids (Standard: "<CDE>::<Dimension>",
--     Custom: catalog codes); ROW_DATA is a JSON object with the row's CDE
--     values and the reference-dataset columns the rules compared against
--     (only the columns the rules use - not the whole data-product row).
--     Query them with the : operator, e.g. ROW_DATA:ITEM_TYPE, or from_json.
--   * A new data product needs its own table: copy one block and rename it
--     DQS_FAILS_<DOMAIN_CODE>_<DP_CODE> (upper case).

CREATE TABLE IF NOT EXISTS entai_sandbox_catalog.data_quality_scorecards.DQS_FAILS_COST_ESTIMATE_ADR (
    RUN_ID            STRING COMMENT 'DQS_RUNS payload id of the run',
    TS                STRING COMMENT 'UTC ISO-8601, stamped by the app',
    USERNAME          STRING COMMENT 'Forwarded app viewer identity (or OS user locally)',
    DOMAIN_CODE       STRING,
    DP_CODE           STRING,
    CONFIG_HASH       STRING,
    TOTAL_FAILED_ROWS BIGINT COMMENT 'Failing rows in the run (before the DQS_FAILS_MAX_ROWS cap)',
    PLANVIEW_ID       STRING COMMENT 'Project key of the row, when the DP carries it',
    ROW_KEY           STRING COMMENT 'ROW_ID when the DP has one, else the row position',
    ROW_SCORE         DOUBLE COMMENT 'Combined 0-100 score of the row',
    FAILED_RULES      STRING COMMENT 'JSON array of the rule ids the row fails',
    ROW_DATA          STRING COMMENT 'JSON object: CDE + reference-dataset values of the row'
) COMMENT 'DQ Scorecard: failed rows of the latest saved run - Cost Estimate / ADR';

CREATE TABLE IF NOT EXISTS entai_sandbox_catalog.data_quality_scorecards.DQS_FAILS_COST_ESTIMATE_ACCE (
    RUN_ID            STRING COMMENT 'DQS_RUNS payload id of the run',
    TS                STRING COMMENT 'UTC ISO-8601, stamped by the app',
    USERNAME          STRING COMMENT 'Forwarded app viewer identity (or OS user locally)',
    DOMAIN_CODE       STRING,
    DP_CODE           STRING,
    CONFIG_HASH       STRING,
    TOTAL_FAILED_ROWS BIGINT COMMENT 'Failing rows in the run (before the per-run cap)',
    PLANVIEW_ID       STRING COMMENT 'Project key of the row, when the DP carries it',
    ROW_KEY           STRING COMMENT 'ROW_ID when the DP has one, else the row position',
    ROW_SCORE         DOUBLE COMMENT 'Combined 0-100 score of the row',
    FAILED_RULES      STRING COMMENT 'JSON array of the rule ids the row fails',
    ROW_DATA          STRING COMMENT 'JSON object: CDE + reference-dataset values of the row'
) COMMENT 'DQ Scorecard: failed rows of the latest saved run - Cost Estimate / ACCE';

CREATE TABLE IF NOT EXISTS entai_sandbox_catalog.data_quality_scorecards.DQS_FAILS_COST_ESTIMATE_EPT (
    RUN_ID            STRING COMMENT 'DQS_RUNS payload id of the run',
    TS                STRING COMMENT 'UTC ISO-8601, stamped by the app',
    USERNAME          STRING COMMENT 'Forwarded app viewer identity (or OS user locally)',
    DOMAIN_CODE       STRING,
    DP_CODE           STRING,
    CONFIG_HASH       STRING,
    TOTAL_FAILED_ROWS BIGINT COMMENT 'Failing rows in the run (before the per-run cap)',
    PLANVIEW_ID       STRING COMMENT 'Project key of the row, when the DP carries it',
    ROW_KEY           STRING COMMENT 'ROW_ID when the DP has one, else the row position',
    ROW_SCORE         DOUBLE COMMENT 'Combined 0-100 score of the row',
    FAILED_RULES      STRING COMMENT 'JSON array of the rule ids the row fails',
    ROW_DATA          STRING COMMENT 'JSON object: CDE + reference-dataset values of the row'
) COMMENT 'DQ Scorecard: failed rows of the latest saved run - Cost Estimate / EPT';

CREATE TABLE IF NOT EXISTS entai_sandbox_catalog.data_quality_scorecards.DQS_FAILS_QUALITY_SQS (
    RUN_ID            STRING COMMENT 'DQS_RUNS payload id of the run',
    TS                STRING COMMENT 'UTC ISO-8601, stamped by the app',
    USERNAME          STRING COMMENT 'Forwarded app viewer identity (or OS user locally)',
    DOMAIN_CODE       STRING,
    DP_CODE           STRING,
    CONFIG_HASH       STRING,
    TOTAL_FAILED_ROWS BIGINT COMMENT 'Failing rows in the run (before the per-run cap)',
    PLANVIEW_ID       STRING COMMENT 'Project key of the row, when the DP carries it',
    ROW_KEY           STRING COMMENT 'ROW_ID when the DP has one, else the row position',
    ROW_SCORE         DOUBLE COMMENT 'Combined 0-100 score of the row',
    FAILED_RULES      STRING COMMENT 'JSON array of the rule ids the row fails',
    ROW_DATA          STRING COMMENT 'JSON object: CDE + reference-dataset values of the row'
) COMMENT 'DQ Scorecard: failed rows of the latest saved run - Quality / SQS';

-- Write access for the app's service principal (same placeholder as
-- 01_grants.sql; backticks required).
GRANT MODIFY ON TABLE entai_sandbox_catalog.data_quality_scorecards.DQS_FAILS_COST_ESTIMATE_ADR  TO `<APP_SERVICE_PRINCIPAL>`;
GRANT MODIFY ON TABLE entai_sandbox_catalog.data_quality_scorecards.DQS_FAILS_COST_ESTIMATE_ACCE TO `<APP_SERVICE_PRINCIPAL>`;
GRANT MODIFY ON TABLE entai_sandbox_catalog.data_quality_scorecards.DQS_FAILS_COST_ESTIMATE_EPT  TO `<APP_SERVICE_PRINCIPAL>`;
GRANT MODIFY ON TABLE entai_sandbox_catalog.data_quality_scorecards.DQS_FAILS_QUALITY_SQS        TO `<APP_SERVICE_PRINCIPAL>`;
