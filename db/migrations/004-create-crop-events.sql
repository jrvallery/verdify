-- Migration 004: Create crop_events table (P0)
-- Audit trail for all crop lifecycle transitions.

CREATE TABLE IF NOT EXISTS crop_events (
    id          SERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ DEFAULT now(),
    crop_id     INT REFERENCES crops(id),
    event_type  TEXT NOT NULL,
    old_stage   TEXT,
    new_stage   TEXT,
    count       INT,
    operator    TEXT,
    source      TEXT DEFAULT 'manual',  -- manual, agent, slack, camera
    notes       TEXT
);

CREATE INDEX IF NOT EXISTS idx_crop_events_crop ON crop_events(crop_id, ts);

-- Valid event_types: stage_change, transplant, thin, prune, remove,
--                    water_adjust, note, photo_assessment, health_check
