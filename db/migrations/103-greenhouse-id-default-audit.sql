-- Ensure every tenant-scoped base table with a greenhouse_id column can accept
-- legacy single-site writes without every caller spelling the tenant id.

BEGIN;

ALTER TABLE equipment ALTER COLUMN greenhouse_id SET DEFAULT 'vallery';
ALTER TABLE greenhouse_sensor_config ALTER COLUMN greenhouse_id SET DEFAULT 'vallery';
ALTER TABLE positions ALTER COLUMN greenhouse_id SET DEFAULT 'vallery';
ALTER TABLE pressure_groups ALTER COLUMN greenhouse_id SET DEFAULT 'vallery';
ALTER TABLE sensors ALTER COLUMN greenhouse_id SET DEFAULT 'vallery';
ALTER TABLE shelves ALTER COLUMN greenhouse_id SET DEFAULT 'vallery';
ALTER TABLE switches ALTER COLUMN greenhouse_id SET DEFAULT 'vallery';
ALTER TABLE water_systems ALTER COLUMN greenhouse_id SET DEFAULT 'vallery';
ALTER TABLE zones ALTER COLUMN greenhouse_id SET DEFAULT 'vallery';

CREATE OR REPLACE VIEW v_greenhouse_id_default_audit AS
SELECT
    c.table_name,
    c.column_default,
    c.is_nullable,
    (c.column_default IS NOT NULL) AS has_default,
    (c.column_default = '''vallery''::text') AS uses_single_site_default
FROM information_schema.columns c
JOIN information_schema.tables t
  ON t.table_schema = c.table_schema
 AND t.table_name = c.table_name
WHERE c.table_schema = 'public'
  AND t.table_type = 'BASE TABLE'
  AND c.column_name = 'greenhouse_id'
ORDER BY c.table_name;

COMMIT;
