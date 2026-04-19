-- 088-crop-history.sql — Sprint 23 Phase 4a
--
-- Makes crop history first-class:
--   1. cleared_at column — "when did this crop end"
--   2. unique partial index — only one active crop per position_id
--   3. Auto-event triggers — INSERT/UPDATE on crops auto-logs crop_events
--   4. Data cleanup — resolve Sprint 22 physical discrepancies
--   5. Backfill — populate cleared_at on existing inactive crops
--
-- Safety: additive column + triggers that only fire going forward.
-- No existing data is deleted; historical crop_events are preserved as-is.
--
-- The unique index only enforces on rows where BOTH is_active=TRUE AND
-- position_id IS NOT NULL, so historical rows and orphans don't conflict.

BEGIN;

-- ── Column: cleared_at ──────────────────────────────────────────────────

ALTER TABLE crops ADD COLUMN IF NOT EXISTS cleared_at TIMESTAMPTZ;
COMMENT ON COLUMN crops.cleared_at IS
    'Sprint 23: when this crop ended (harvest, removal, or clear). NULL = active. Set automatically by crops_log_clear() trigger when is_active transitions true→false.';


-- ── Unique active crop per position ─────────────────────────────────────

CREATE UNIQUE INDEX IF NOT EXISTS idx_crops_active_position
    ON crops (greenhouse_id, position_id)
    WHERE is_active AND position_id IS NOT NULL;

COMMENT ON INDEX idx_crops_active_position IS
    'Sprint 23: prevents double-booking a position. Only one active crop (is_active=true) can exist at a given position_id per greenhouse. Historical rows (is_active=false) and orphans (position_id NULL) are not constrained.';


-- ── Trigger: auto-log "planted" on INSERT ──────────────────────────────

CREATE OR REPLACE FUNCTION crops_log_planted() RETURNS TRIGGER AS $$
BEGIN
    -- Only log on INSERT where the crop is born active. Backfilled
    -- historical rows (is_active=false on insert) don't get an auto-event.
    IF NEW.is_active THEN
        INSERT INTO crop_events (
            ts, crop_id, event_type, new_stage, source, notes,
            greenhouse_id, position_id
        )
        VALUES (
            COALESCE(NEW.created_at, now()),
            NEW.id,
            'planted',
            NEW.stage,
            'trigger',
            'Auto-logged by crops_log_planted trigger',
            NEW.greenhouse_id,
            NEW.position_id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_crops_log_planted ON crops;
CREATE TRIGGER trg_crops_log_planted
    AFTER INSERT ON crops
    FOR EACH ROW
    EXECUTE FUNCTION crops_log_planted();


-- ── Trigger: auto-log "stage_change" on UPDATE of stage ────────────────

CREATE OR REPLACE FUNCTION crops_log_stage_change() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.stage IS DISTINCT FROM OLD.stage THEN
        INSERT INTO crop_events (
            ts, crop_id, event_type, old_stage, new_stage,
            source, notes, greenhouse_id, position_id
        )
        VALUES (
            now(),
            NEW.id,
            'stage_change',
            OLD.stage,
            NEW.stage,
            'trigger',
            'Auto-logged by crops_log_stage_change trigger',
            NEW.greenhouse_id,
            NEW.position_id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_crops_log_stage_change ON crops;
CREATE TRIGGER trg_crops_log_stage_change
    AFTER UPDATE OF stage ON crops
    FOR EACH ROW
    EXECUTE FUNCTION crops_log_stage_change();


-- ── Trigger: auto-log "removed" + set cleared_at on deactivation ───────

CREATE OR REPLACE FUNCTION crops_log_clear() RETURNS TRIGGER AS $$
BEGIN
    -- Fires on any is_active transition (for completeness).
    -- Only act when true→false (the "clear" direction).
    IF OLD.is_active = TRUE AND NEW.is_active = FALSE THEN
        -- Stamp cleared_at if not already set (caller may set it explicitly).
        IF NEW.cleared_at IS NULL THEN
            NEW.cleared_at := now();
        END IF;
        INSERT INTO crop_events (
            ts, crop_id, event_type, old_stage, new_stage,
            source, notes, greenhouse_id, position_id
        )
        VALUES (
            NEW.cleared_at,
            NEW.id,
            'removed',
            OLD.stage,
            NEW.stage,
            'trigger',
            'Auto-logged by crops_log_clear trigger (is_active: true → false)',
            NEW.greenhouse_id,
            NEW.position_id
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_crops_log_clear ON crops;
CREATE TRIGGER trg_crops_log_clear
    BEFORE UPDATE OF is_active ON crops
    FOR EACH ROW
    EXECUTE FUNCTION crops_log_clear();


-- ── Data cleanup (Sprint 22 discrepancies resolved in session 2026-04-19) ──

-- Canna Lilies (id=2) → SOUTH-FLOOR-1
UPDATE crops
SET position_id = (
    SELECT p.id FROM positions p
    WHERE p.greenhouse_id = 'vallery' AND p.label = 'SOUTH-FLOOR-1'
)
WHERE id = 2 AND greenhouse_id = 'vallery' AND position_id IS NULL;

-- Vanda Orchids (id=5) → CENTER-HANG-1
UPDATE crops
SET position_id = (
    SELECT p.id FROM positions p
    WHERE p.greenhouse_id = 'vallery' AND p.label = 'CENTER-HANG-1'
)
WHERE id = 5 AND greenhouse_id = 'vallery' AND position_id IS NULL;

-- House Plants (id=4) → migrate stage from 'unknown' to 'cleared'
-- (Will fire trg_crops_log_stage_change which logs the migration.)
UPDATE crops
SET stage = 'cleared'
WHERE id = 4 AND greenhouse_id = 'vallery' AND stage = 'unknown';


-- ── Backfill cleared_at for inactive crops (using updated_at as proxy) ──

UPDATE crops
SET cleared_at = updated_at
WHERE NOT is_active AND cleared_at IS NULL AND greenhouse_id = 'vallery';


-- ── Backfill 'planted' events for active crops missing them ─────────────

INSERT INTO crop_events (ts, crop_id, event_type, new_stage, source, notes, greenhouse_id, position_id)
SELECT
    c.created_at,
    c.id,
    'planted',
    c.stage,
    'backfill',
    'Backfilled planted event for active crop (Sprint 23 migration 088)',
    c.greenhouse_id,
    c.position_id
FROM crops c
WHERE c.is_active
  AND c.greenhouse_id = 'vallery'
  AND NOT EXISTS (
      SELECT 1 FROM crop_events e
      WHERE e.crop_id = c.id AND e.event_type = 'planted'
  );


COMMIT;
