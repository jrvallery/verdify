-- Migration 095a: restore daily_summary compliance fields for fresh DBs.
--
-- Production already has these columns and ingestor.daily_summary_live writes
-- them. Migration 096, db/schema.sql, and later trust/outcome views depend on
-- them, but the migration chain never created them on a fresh CI database.

ALTER TABLE daily_summary
    ADD COLUMN IF NOT EXISTS compliance_pct DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS temp_compliance_pct DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS vpd_compliance_pct DOUBLE PRECISION;

COMMENT ON COLUMN daily_summary.compliance_pct IS
    'Percent of daily readings where both temperature and VPD were inside the active band.';
COMMENT ON COLUMN daily_summary.temp_compliance_pct IS
    'Percent of daily readings where temperature was inside the active band.';
COMMENT ON COLUMN daily_summary.vpd_compliance_pct IS
    'Percent of daily readings where VPD was inside the active band.';
