-- Monthly declarative partitioning for `audit_log` (Phase 8, item 11).
--
-- WHY THIS IS NOT AN ALEMBIC MIGRATION
--
-- Converting a populated table to a partitioned one means creating a new table, copying every
-- row, and swapping the names. On a table with tens of millions of audit rows that is minutes
-- to hours under an ACCESS EXCLUSIVE lock — the whole application stops for the duration.
-- A migration that runs automatically on deploy and takes the system down for an hour is
-- worse than no migration, so this is a script an operator runs during a maintenance window,
-- with the row count in front of them.
--
-- Below roughly 10 million rows the existing indexes already handle it and this is churn.
-- The size check at step 1 refuses to proceed on a small table for exactly that reason.
--
-- WHAT SURVIVES
--
-- The tamper-evidence chain is **per row** — each row stores its own `prev_hash` and
-- `row_hash`, and verification walks `seq` in order. Nothing about the chain depends on the
-- rows living in one physical table, so partitioning does not weaken it. That was a design
-- choice made in 0023 precisely so this step would stay available.
--
-- Verify afterwards with `audit.verify_chain(db, tenant_id)` for a sample of tenants. If the
-- chain does not verify after the copy, the copy is wrong — stop and roll back.

\set ON_ERROR_STOP on

BEGIN;

-- ---------------------------------------------------------------------------------------
-- 1. Size check. Refuse to proceed on a table small enough not to need this.
-- ---------------------------------------------------------------------------------------
DO $$
DECLARE
    row_count bigint;
BEGIN
    SELECT count(*) INTO row_count FROM audit_log;
    RAISE NOTICE 'audit_log currently holds % rows', row_count;
    IF row_count < 1000000 THEN
        RAISE EXCEPTION
            'audit_log has only % rows. Partitioning below ~10M rows adds operational '
            'complexity for no measurable gain. Re-run when it is warranted.', row_count;
    END IF;
END $$;

-- ---------------------------------------------------------------------------------------
-- 2. The partitioned table.
--
-- Partitioned by `at` (month). Not by tenant: tenant counts vary wildly and a per-tenant
-- scheme produces thousands of tiny partitions plus a planning cost on every query. Time is
-- the axis that grows without bound, and retention is expressed in time — which makes
-- dropping an expired month a DETACH rather than a DELETE of millions of rows.
-- ---------------------------------------------------------------------------------------
CREATE TABLE audit_log_partitioned (
    LIKE audit_log INCLUDING DEFAULTS INCLUDING CONSTRAINTS
) PARTITION BY RANGE (at);

-- The primary key must include the partition key. `id` alone cannot be unique across
-- partitions, so it becomes (id, at). Nothing looks a row up by `id` without also having the
-- row, so this costs nothing in practice.
ALTER TABLE audit_log_partitioned ADD PRIMARY KEY (id, at);

CREATE INDEX ON audit_log_partitioned (tenant_id, seq);
CREATE INDEX ON audit_log_partitioned (tenant_id, at);
CREATE INDEX ON audit_log_partitioned (object_type, object_id);
CREATE INDEX ON audit_log_partitioned (action);

-- ---------------------------------------------------------------------------------------
-- 3. Partitions covering the existing data plus twelve months ahead.
--
-- Created ahead of time on purpose: a write with no matching partition fails, and an audit
-- write that fails takes the state-changing action with it. Running out of partitions would
-- stop the application, so the maintenance function below keeps a year in front.
-- ---------------------------------------------------------------------------------------
DO $$
DECLARE
    start_month date;
    end_month date;
    current_month date;
    partition_name text;
BEGIN
    SELECT date_trunc('month', COALESCE(min(at), now()))::date INTO start_month FROM audit_log;
    end_month := (date_trunc('month', now()) + interval '12 months')::date;
    current_month := start_month;

    WHILE current_month < end_month LOOP
        partition_name := 'audit_log_' || to_char(current_month, 'YYYY_MM');
        EXECUTE format(
            'CREATE TABLE %I PARTITION OF audit_log_partitioned FOR VALUES FROM (%L) TO (%L)',
            partition_name, current_month, current_month + interval '1 month');
        current_month := (current_month + interval '1 month')::date;
    END LOOP;

    -- A catch-all for anything with a timestamp outside the expected range. Without it a
    -- clock-skewed row fails to insert, which would fail the audit write and therefore the
    -- action being audited.
    EXECUTE 'CREATE TABLE audit_log_overflow PARTITION OF audit_log_partitioned DEFAULT';
END $$;

-- ---------------------------------------------------------------------------------------
-- 4. Copy. This is the slow part.
-- ---------------------------------------------------------------------------------------
INSERT INTO audit_log_partitioned SELECT * FROM audit_log;

DO $$
DECLARE
    original bigint;
    copied bigint;
BEGIN
    SELECT count(*) INTO original FROM audit_log;
    SELECT count(*) INTO copied FROM audit_log_partitioned;
    IF original <> copied THEN
        RAISE EXCEPTION 'Copy is short: % rows original, % copied. Rolling back.',
            original, copied;
    END IF;
    RAISE NOTICE 'Copied % rows', copied;
END $$;

-- ---------------------------------------------------------------------------------------
-- 5. Swap. The old table is renamed, not dropped — it is the rollback.
-- ---------------------------------------------------------------------------------------
ALTER TABLE audit_log RENAME TO audit_log_pre_partition;
ALTER TABLE audit_log_partitioned RENAME TO audit_log;

-- Row-level security has to be re-applied: it does not follow the rename, and an audit table
-- without it is a cross-tenant read.
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE ROW LEVEL SECURITY;
CREATE POLICY cm_tenant_isolation ON audit_log
    USING (coalesce(current_setting('app.cm_tenant', true), '') IN ('', tenant_id));

COMMIT;

-- ---------------------------------------------------------------------------------------
-- 6. The maintenance function, so partitions never run out.
-- ---------------------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION create_audit_partition(month_start date)
RETURNS void AS $$
DECLARE
    partition_name text := 'audit_log_' || to_char(month_start, 'YYYY_MM');
BEGIN
    IF to_regclass(partition_name) IS NOT NULL THEN
        RETURN;   -- idempotent: safe to run on a schedule
    END IF;
    EXECUTE format(
        'CREATE TABLE %I PARTITION OF audit_log FOR VALUES FROM (%L) TO (%L)',
        partition_name, month_start, month_start + interval '1 month');
END $$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------------------
-- 7. AFTERWARDS — do these, in this order.
-- ---------------------------------------------------------------------------------------
--
--   a. Verify the chain for the busiest tenants:
--        SELECT tenant_id, count(*) FROM audit_log GROUP BY tenant_id ORDER BY 2 DESC LIMIT 5;
--      then, from the application:  audit.verify_chain(db, tenant_id)
--
--   b. Only once (a) passes for every sampled tenant:
--        DROP TABLE audit_log_pre_partition;
--      Keep it until then. It is the only way back.
--
--   c. Schedule the maintenance job:
--        SELECT cron.schedule('audit-partitions', '0 3 1 * *', $$
--          SELECT create_audit_partition(date_trunc('month', now() + interval '12 months')::date)
--        $$);
--
--   d. Retention becomes a DETACH rather than a DELETE:
--        ALTER TABLE audit_log DETACH PARTITION audit_log_2019_01;
--        -- archive the detached table, then drop it
--      Check the retention period in `docs/29-backup-and-dr.md` first, and confirm no legal
--      hold covers the period — a hold overrides retention unconditionally.
