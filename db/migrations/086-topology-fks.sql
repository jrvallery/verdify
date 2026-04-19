-- 086-topology-fks.sql — Sprint 22 Phase 2
--
-- Add nullable FK columns to existing tables that reference the new topology
-- entities. Every column is nullable during the Sprint 22 migration window —
-- Phase 3 (import-vault-topology.py) backfills them from the legacy string
-- fields (crops.zone, crops.position, observations.zone, etc.).
--
-- Phase 6 drops the legacy string columns after callers are updated.
--
-- Safety: all columns are nullable ADDs, so existing INSERT paths keep working.

BEGIN;

-- ── crops ──────────────────────────────────────────────────────────────
ALTER TABLE crops
    ADD COLUMN IF NOT EXISTS position_id      INT REFERENCES positions(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS zone_id          INT REFERENCES zones(id)     ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS crop_catalog_id  INT REFERENCES crop_catalog(id) ON DELETE SET NULL;

COMMENT ON COLUMN crops.position_id      IS 'Sprint 22: FK to positions.id. Nullable during backfill; legacy `position` text column remains authoritative until Phase 6.';
COMMENT ON COLUMN crops.zone_id          IS 'Sprint 22: FK to zones.id. Nullable during backfill.';
COMMENT ON COLUMN crops.crop_catalog_id  IS 'Sprint 22: FK to crop_catalog.id. Nullable during backfill.';

CREATE INDEX IF NOT EXISTS idx_crops_position_id ON crops (position_id) WHERE position_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_crops_zone_id     ON crops (zone_id)     WHERE zone_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_crops_catalog_id  ON crops (crop_catalog_id) WHERE crop_catalog_id IS NOT NULL;


-- ── observations ───────────────────────────────────────────────────────
ALTER TABLE observations
    ADD COLUMN IF NOT EXISTS position_id  INT REFERENCES positions(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS zone_id      INT REFERENCES zones(id)     ON DELETE SET NULL;

COMMENT ON COLUMN observations.position_id IS 'Sprint 22: FK to positions.id. Nullable during backfill; legacy `position` text column remains authoritative.';
COMMENT ON COLUMN observations.zone_id     IS 'Sprint 22: FK to zones.id. Nullable during backfill.';


-- ── crop_events ────────────────────────────────────────────────────────
ALTER TABLE crop_events
    ADD COLUMN IF NOT EXISTS position_id INT REFERENCES positions(id) ON DELETE SET NULL;

COMMENT ON COLUMN crop_events.position_id IS 'Sprint 22: FK to positions.id. Derived from crops.position_id at write time once Phase 4 lands.';


-- ── harvests ───────────────────────────────────────────────────────────
ALTER TABLE harvests
    ADD COLUMN IF NOT EXISTS position_id INT REFERENCES positions(id) ON DELETE SET NULL;

COMMENT ON COLUMN harvests.position_id IS 'Sprint 22: FK to positions.id (nullable).';


-- ── treatments ─────────────────────────────────────────────────────────
ALTER TABLE treatments
    ADD COLUMN IF NOT EXISTS position_id INT REFERENCES positions(id) ON DELETE SET NULL;

COMMENT ON COLUMN treatments.position_id IS 'Sprint 22: FK to positions.id (nullable).';


-- ── alert_log ──────────────────────────────────────────────────────────
ALTER TABLE alert_log
    ADD COLUMN IF NOT EXISTS zone_id INT REFERENCES zones(id) ON DELETE SET NULL;

COMMENT ON COLUMN alert_log.zone_id IS 'Sprint 22: FK to zones.id. Nullable; backfilled by resolving alert_log.zone text against zones.slug.';


-- ── crop_target_profiles ───────────────────────────────────────────────
ALTER TABLE crop_target_profiles
    ADD COLUMN IF NOT EXISTS crop_catalog_id INT REFERENCES crop_catalog(id) ON DELETE SET NULL;

COMMENT ON COLUMN crop_target_profiles.crop_catalog_id IS 'Sprint 22: FK to crop_catalog.id. Replaces the free-text crop_type column as the integrity-bearing reference.';

CREATE INDEX IF NOT EXISTS idx_ctp_catalog_id ON crop_target_profiles (crop_catalog_id) WHERE crop_catalog_id IS NOT NULL;


-- ── image_observations ─────────────────────────────────────────────────
-- Camera snapshots often capture a zone; expose the FK so vision observations
-- can be joined to zone state without re-resolving text columns.
ALTER TABLE image_observations
    ADD COLUMN IF NOT EXISTS zone_id INT REFERENCES zones(id) ON DELETE SET NULL;

COMMENT ON COLUMN image_observations.zone_id IS 'Sprint 22: FK to zones.id. Backfilled from camera_zone_map.';


COMMIT;
