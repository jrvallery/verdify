-- Repair TimescaleDB metadata after restoring the checked-in schema snapshot.
--
-- db/schema.sql is a pg_dump snapshot from production. It includes inherited
-- _timescaledb_internal chunk tables, but replaying it in CI with
-- ON_ERROR_STOP=0 does not reconstruct TimescaleDB's hypertable catalog rows.
-- The result is a table that is "already partitioned" but absent from
-- timescaledb_information.hypertables. On real production databases these
-- tables are already registered hypertables, so this migration is a no-op.

DO $$
DECLARE
    target record;
    child record;
    registered boolean;
BEGIN
    FOR target IN
        SELECT * FROM (VALUES
            ('climate'::text, 'ts'::text),
            ('equipment_state', 'ts'),
            ('system_state', 'ts'),
            ('weather_forecast', 'ts')
        ) AS t(table_name, time_column)
    LOOP
        IF to_regclass(format('public.%I', target.table_name)) IS NULL THEN
            CONTINUE;
        END IF;

        SELECT EXISTS (
            SELECT 1
            FROM timescaledb_information.hypertables
            WHERE hypertable_schema = 'public'
              AND hypertable_name = target.table_name
        ) INTO registered;

        IF registered THEN
            CONTINUE;
        END IF;

        FOR child IN
            SELECT inhrelid::regclass AS child_table
            FROM pg_inherits
            WHERE inhparent = format('public.%I', target.table_name)::regclass
        LOOP
            EXECUTE format('DROP TABLE IF EXISTS %s CASCADE', child.child_table);
        END LOOP;

        EXECUTE format(
            'SELECT create_hypertable(%L, %L, if_not_exists => TRUE, migrate_data => TRUE)',
            target.table_name,
            target.time_column
        );
    END LOOP;
END $$;
