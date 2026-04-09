-- 065-succession-planning.sql
-- Succession planning: crop rotation scheduling + gap detection

CREATE TABLE IF NOT EXISTS succession_plan (
    id SERIAL PRIMARY KEY,
    zone TEXT NOT NULL,
    position TEXT,
    crop TEXT NOT NULL,
    variety TEXT,
    planned_sow DATE NOT NULL,
    planned_harvest DATE,
    rotation_group TEXT,
    season TEXT,
    notes TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_succession_active ON succession_plan(is_active, zone);
CREATE INDEX idx_succession_rotation ON succession_plan(rotation_group);

-- v_succession_gaps: days between current crop harvest and next planned sow
CREATE OR REPLACE VIEW v_succession_gaps AS
WITH current_crops AS (
    SELECT id, name, zone, position, expected_harvest, is_active
    FROM crops WHERE is_active = true
),
next_planned AS (
    SELECT DISTINCT ON (zone, position)
        zone, position, crop AS next_crop, planned_sow
    FROM succession_plan
    WHERE is_active = true AND planned_sow >= CURRENT_DATE
    ORDER BY zone, position, planned_sow
)
SELECT
    COALESCE(c.zone, n.zone) AS zone,
    COALESCE(c.position, n.position) AS position,
    c.name AS current_crop,
    c.expected_harvest AS current_harvest_date,
    n.next_crop AS next_planned_crop,
    n.planned_sow AS next_sow_date,
    CASE
        WHEN c.expected_harvest IS NOT NULL AND n.planned_sow IS NOT NULL
        THEN n.planned_sow - c.expected_harvest
        ELSE NULL
    END AS gap_days,
    CASE
        WHEN c.expected_harvest IS NULL THEN true
        WHEN n.planned_sow IS NULL THEN true
        WHEN n.planned_sow - c.expected_harvest > 7 THEN true
        ELSE false
    END AS gap_flag
FROM current_crops c
FULL OUTER JOIN next_planned n ON c.zone = n.zone AND c.position = n.position;

-- v_succession_timeline: all plans + current crops ordered by zone/position/date
CREATE OR REPLACE VIEW v_succession_timeline AS
SELECT
    'current' AS entry_type,
    c.zone, c.position, c.name AS crop, c.variety,
    c.planted_date AS start_date, c.expected_harvest AS end_date,
    c.stage, NULL::text AS rotation_group, NULL::text AS season
FROM crops c WHERE c.is_active = true
UNION ALL
SELECT
    'planned', s.zone, s.position, s.crop, s.variety,
    s.planned_sow, s.planned_harvest,
    'planned'::text, s.rotation_group, s.season
FROM succession_plan s WHERE s.is_active = true
ORDER BY zone, position, start_date;

-- fn_succession_gaps_by_zone: optional zone filter
CREATE OR REPLACE FUNCTION fn_succession_gaps_by_zone(target_zone TEXT DEFAULT NULL)
RETURNS TABLE (
    zone TEXT, position TEXT, current_crop TEXT,
    current_harvest_date DATE, next_planned_crop TEXT,
    next_sow_date DATE, gap_days INT, gap_flag BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT g.zone, g.position, g.current_crop,
        g.current_harvest_date, g.next_planned_crop,
        g.next_sow_date, g.gap_days, g.gap_flag
    FROM v_succession_gaps g
    WHERE target_zone IS NULL OR g.zone = target_zone
    ORDER BY g.zone, g.position;
END;
$$ LANGUAGE plpgsql;
