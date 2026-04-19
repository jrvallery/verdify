-- 089-crop-history-views.sql — Sprint 23 Phase 4a
--
-- History-aware views that consume the position_id FK + cleared_at column
-- from migration 088. Drives the website "what was planted here" pages,
-- the API /positions/{id} detail, and the MCP crop_history() tool.

BEGIN;

-- ── v_position_current ─────────────────────────────────────────────────
-- One row per (position, active_crop) pair. NULL crop columns = empty slot.
-- Days-in-place is calculated from planted_date for quick scan.

CREATE OR REPLACE VIEW v_position_current AS
SELECT
    p.id                                     AS position_id,
    p.greenhouse_id,
    p.label                                  AS position_label,
    sh.slug                                  AS shelf_slug,
    sh.kind                                  AS shelf_kind,
    z.id                                     AS zone_id,
    z.slug                                   AS zone_slug,
    z.name                                   AS zone_name,
    c.id                                     AS crop_id,
    c.name                                   AS crop_name,
    c.variety                                AS crop_variety,
    c.stage                                  AS crop_stage,
    c.planted_date                           AS crop_planted_date,
    c.expected_harvest                       AS crop_expected_harvest,
    cc.slug                                  AS crop_catalog_slug,
    (CURRENT_DATE - c.planted_date)          AS crop_days_in_place,
    (c.id IS NOT NULL)                       AS is_occupied
FROM positions p
JOIN shelves sh ON sh.id = p.shelf_id
JOIN zones z    ON z.id = sh.zone_id
LEFT JOIN crops c ON c.position_id = p.id AND c.is_active
LEFT JOIN crop_catalog cc ON cc.id = c.crop_catalog_id
WHERE p.is_active
ORDER BY z.slug, sh.slug, p.label;

COMMENT ON VIEW v_position_current IS
    'Sprint 23: current state of every active position — which crop (if any) is there, how long it has been, which zone/shelf it belongs to. Left-join on crops, so empty slots show up with NULL crop columns.';


-- ── v_crop_history ─────────────────────────────────────────────────────
-- Chronological per-position crop list including inactive rows. Enables
-- "what has been planted at SOUTH-FLOOR-1 over time" queries.

CREATE OR REPLACE VIEW v_crop_history AS
SELECT
    p.id                                     AS position_id,
    p.greenhouse_id,
    p.label                                  AS position_label,
    z.slug                                   AS zone_slug,
    c.id                                     AS crop_id,
    c.name                                   AS crop_name,
    c.variety                                AS crop_variety,
    c.stage                                  AS final_stage,
    c.planted_date                           AS planted_date,
    c.cleared_at                             AS cleared_at,
    c.is_active                              AS is_active,
    (c.cleared_at::date - c.planted_date)    AS days_in_place,
    cc.slug                                  AS crop_catalog_slug,
    cc.common_name                           AS crop_common_name,
    (SELECT COUNT(*) FROM crop_events e WHERE e.crop_id = c.id)    AS event_count,
    (SELECT COUNT(*) FROM observations o WHERE o.crop_id = c.id)   AS observation_count,
    (SELECT COUNT(*) FROM harvests h WHERE h.crop_id = c.id)       AS harvest_count
FROM crops c
LEFT JOIN positions p ON p.id = c.position_id
LEFT JOIN shelves sh  ON sh.id = p.shelf_id
LEFT JOIN zones z     ON z.id = sh.zone_id
LEFT JOIN crop_catalog cc ON cc.id = c.crop_catalog_id
ORDER BY p.label NULLS LAST, c.planted_date DESC;

COMMENT ON VIEW v_crop_history IS
    'Sprint 23: every crop ever recorded at a position, in reverse-chronological order. Drives website position history + /api/v1/positions/{id}/crops.';


-- ── v_crop_lifecycle ───────────────────────────────────────────────────
-- Per-crop timeline: planted, stage transitions, observations, harvests,
-- cleared. Aggregates crop_events into a compact JSONB timeline array.

CREATE OR REPLACE VIEW v_crop_lifecycle AS
SELECT
    c.id                                     AS crop_id,
    c.greenhouse_id,
    c.name                                   AS crop_name,
    c.variety,
    c.stage                                  AS current_stage,
    c.is_active,
    c.planted_date,
    c.cleared_at,
    (COALESCE(c.cleared_at::date, CURRENT_DATE) - c.planted_date) AS days_alive,
    z.slug                                   AS current_zone_slug,
    p.label                                  AS current_position_label,
    cc.slug                                  AS crop_catalog_slug,
    cc.common_name                           AS catalog_name,
    cc.category                              AS catalog_category,
    -- Event timeline
    COALESCE(
        (SELECT jsonb_agg(
                    jsonb_build_object(
                        'ts', e.ts,
                        'event_type', e.event_type,
                        'old_stage', e.old_stage,
                        'new_stage', e.new_stage,
                        'position_id', e.position_id,
                        'notes', e.notes,
                        'source', e.source
                    ) ORDER BY e.ts)
         FROM crop_events e
         WHERE e.crop_id = c.id),
        '[]'::jsonb
    )                                        AS events,
    -- Harvest totals
    COALESCE((SELECT SUM(h.weight_kg) FROM harvests h WHERE h.crop_id = c.id), 0) AS total_weight_kg,
    COALESCE((SELECT SUM(h.unit_count) FROM harvests h WHERE h.crop_id = c.id), 0) AS total_units,
    COALESCE((SELECT SUM(h.revenue) FROM harvests h WHERE h.crop_id = c.id), 0)   AS total_revenue_usd,
    -- Observation summary
    (SELECT COUNT(*) FROM observations o WHERE o.crop_id = c.id) AS observation_count,
    (SELECT AVG(o.health_score)::numeric(4,3) FROM observations o WHERE o.crop_id = c.id
        AND o.health_score IS NOT NULL) AS avg_health_score,
    (SELECT MAX(o.ts) FROM observations o WHERE o.crop_id = c.id) AS latest_observation_ts
FROM crops c
LEFT JOIN positions p ON p.id = c.position_id
LEFT JOIN shelves sh  ON sh.id = p.shelf_id
LEFT JOIN zones z     ON z.id = sh.zone_id
LEFT JOIN crop_catalog cc ON cc.id = c.crop_catalog_id
ORDER BY c.is_active DESC, c.planted_date DESC;

COMMENT ON VIEW v_crop_lifecycle IS
    'Sprint 23: per-crop timeline with events JSONB array + harvest totals + observation summary. Drives /api/v1/crops/{id}/lifecycle and the MCP crop_lifecycle tool.';


COMMIT;
