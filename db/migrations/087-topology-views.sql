-- 087-topology-views.sql — Sprint 22 Phase 2
--
-- Render-ready views that join the new topology tables. These are the
-- primary consumers for:
--   - /api/v1/topology (website zone nav, debugging)
--   - /api/v1/zones/{slug} detail page (replaces hand-typed zone.md)
--   - Relay map page (replaces hand-typed equipment.md tables)
--   - Planner's topology() MCP tool (future Phase 4)
--
-- All views are read-only and non-materialized; refresh cost is zero, and
-- they stay in sync with the underlying tables automatically.

BEGIN;

-- ── v_zone_full — one row per zone with nested JSON arrays ─────────────

CREATE OR REPLACE VIEW v_zone_full AS
SELECT
    z.id                    AS zone_id,
    z.greenhouse_id,
    z.slug                  AS zone_slug,
    z.name                  AS zone_name,
    z.orientation,
    z.sensor_modbus_addr,
    z.peak_temp_f,
    z.status                AS zone_status,
    z.notes                 AS zone_notes,
    -- Shelves array
    COALESCE(
        (SELECT jsonb_agg(
                    jsonb_build_object(
                        'id', sh.id,
                        'slug', sh.slug,
                        'name', sh.name,
                        'kind', sh.kind,
                        'tier', sh.tier,
                        'position_scheme', sh.position_scheme
                    ) ORDER BY sh.tier NULLS LAST, sh.slug)
         FROM shelves sh
         WHERE sh.zone_id = z.id),
        '[]'::jsonb
    ) AS shelves,
    -- Sensors array
    COALESCE(
        (SELECT jsonb_agg(
                    jsonb_build_object(
                        'id', s.id,
                        'slug', s.slug,
                        'kind', s.kind,
                        'protocol', s.protocol,
                        'model', s.model,
                        'modbus_addr', s.modbus_addr,
                        'source_table', s.source_table,
                        'source_column', s.source_column,
                        'unit', s.unit,
                        'is_active', s.is_active
                    ) ORDER BY s.slug)
         FROM sensors s
         WHERE s.zone_id = z.id),
        '[]'::jsonb
    ) AS sensors,
    -- Equipment array
    COALESCE(
        (SELECT jsonb_agg(
                    jsonb_build_object(
                        'id', e.id,
                        'slug', e.slug,
                        'kind', e.kind,
                        'name', e.name,
                        'model', e.model,
                        'watts', e.watts,
                        'cost_per_hour_usd', e.cost_per_hour_usd,
                        'is_active', e.is_active
                    ) ORDER BY e.kind, e.slug)
         FROM equipment e
         WHERE e.zone_id = z.id),
        '[]'::jsonb
    ) AS equipment,
    -- Water systems array
    COALESCE(
        (SELECT jsonb_agg(
                    jsonb_build_object(
                        'id', w.id,
                        'slug', w.slug,
                        'kind', w.kind,
                        'name', w.name,
                        'nozzle_count', w.nozzle_count,
                        'head_count', w.head_count,
                        'mount', w.mount,
                        'pressure_group_id', w.pressure_group_id,
                        'is_fert_path', w.is_fert_path
                    ) ORDER BY w.kind, w.slug)
         FROM water_systems w
         WHERE w.zone_id = z.id),
        '[]'::jsonb
    ) AS water_systems,
    -- Active crop count via FK
    (SELECT COUNT(*)::int FROM crops c
     WHERE c.zone_id = z.id AND c.is_active) AS active_crops_fk_count
FROM zones z;

COMMENT ON VIEW v_zone_full IS
    'Sprint 22: per-zone rollup of shelves, sensors, equipment, water_systems as JSONB arrays. Drives the website zone pages + /api/v1/zones/{slug}.';


-- ── v_topology_tree — full greenhouse → zones tree ─────────────────────

CREATE OR REPLACE VIEW v_topology_tree AS
SELECT
    g.id AS greenhouse_id,
    g.name AS greenhouse_name,
    COALESCE(
        (SELECT jsonb_agg(
                    jsonb_build_object(
                        'zone_id', z.id,
                        'slug', z.slug,
                        'name', z.name,
                        'status', z.status,
                        'shelves', COALESCE(
                            (SELECT jsonb_agg(
                                        jsonb_build_object(
                                            'shelf_id', sh.id,
                                            'slug', sh.slug,
                                            'name', sh.name,
                                            'kind', sh.kind,
                                            'positions', COALESCE(
                                                (SELECT jsonb_agg(
                                                            jsonb_build_object(
                                                                'position_id', p.id,
                                                                'label', p.label,
                                                                'mount_type', p.mount_type,
                                                                'is_active', p.is_active
                                                            ) ORDER BY p.label)
                                                 FROM positions p
                                                 WHERE p.shelf_id = sh.id),
                                                '[]'::jsonb
                                            )
                                        ) ORDER BY sh.slug)
                             FROM shelves sh
                             WHERE sh.zone_id = z.id),
                            '[]'::jsonb
                        )
                    ) ORDER BY z.slug)
         FROM zones z
         WHERE z.greenhouse_id = g.id),
        '[]'::jsonb
    ) AS zones
FROM greenhouses g;

COMMENT ON VIEW v_topology_tree IS
    'Sprint 22: greenhouse → zone → shelf → position recursive tree as a single JSONB blob. Drives website nav + /api/v1/topology.';


-- ── v_equipment_relay_map — replaces hand-typed relay table ───────────

CREATE OR REPLACE VIEW v_equipment_relay_map AS
SELECT
    sw.greenhouse_id,
    sw.board,
    sw.pin,
    sw.slug AS switch_slug,
    e.slug AS equipment_slug,
    e.name AS equipment_name,
    e.kind AS equipment_kind,
    e.model,
    z.slug AS zone_slug,
    z.name AS zone_name,
    sw.purpose,
    sw.state_source_column,
    sw.is_active
FROM switches sw
LEFT JOIN equipment e ON e.id = sw.equipment_id
LEFT JOIN zones z     ON z.id = e.zone_id
ORDER BY sw.board, sw.pin;

COMMENT ON VIEW v_equipment_relay_map IS
    'Sprint 22: replaces the hand-typed Relay Map in website/greenhouse/equipment.md. One row per PCF pin with equipment + zone joined in.';


-- ── v_pressure_group_status — current mister/drip activity by group ────

CREATE OR REPLACE VIEW v_pressure_group_status AS
SELECT
    pg.id AS pressure_group_id,
    pg.greenhouse_id,
    pg.slug AS group_slug,
    pg.name AS group_name,
    pg.constraint_kind,
    pg.max_concurrent,
    -- Snapshot: water systems in the group + equipment, derived currently-on
    -- via a latest-equipment-state DISTINCT ON join (matches v_equipment_now pattern).
    COALESCE(
        (SELECT jsonb_agg(
                    jsonb_build_object(
                        'water_system_slug', w.slug,
                        'water_system_kind', w.kind,
                        'equipment_slug', e.slug,
                        'zone_slug', z.slug,
                        'is_on', COALESCE(
                            (SELECT es.state
                             FROM equipment_state es
                             WHERE es.equipment = e.slug
                               AND es.greenhouse_id = pg.greenhouse_id
                             ORDER BY es.ts DESC
                             LIMIT 1),
                            FALSE
                        )
                    ) ORDER BY w.slug)
         FROM water_systems w
         LEFT JOIN equipment e ON e.id = w.equipment_id
         LEFT JOIN zones z     ON z.id = w.zone_id
         WHERE w.pressure_group_id = pg.id AND w.is_active),
        '[]'::jsonb
    ) AS systems
FROM pressure_groups pg;

COMMENT ON VIEW v_pressure_group_status IS
    'Sprint 22: snapshot of pressure-manifold activity. Shows which mister/drip systems are currently on per pressure group. Used to verify firmware "one-at-a-time" rule is being honored.';


-- ── v_crop_catalog_with_profiles — for website crop-profile pages ──────

CREATE OR REPLACE VIEW v_crop_catalog_with_profiles AS
SELECT
    cc.id AS crop_catalog_id,
    cc.slug,
    cc.common_name,
    cc.scientific_name,
    cc.category,
    cc.season,
    cc.cycle_days_min,
    cc.cycle_days_max,
    cc.base_temp_f,
    cc.default_target_dli,
    cc.default_target_vpd_low,
    cc.default_target_vpd_high,
    cc.default_ph_low,
    cc.default_ph_high,
    cc.default_ec_low,
    cc.default_ec_high,
    -- Grouped profiles per stage × season (24 hour rows → one aggregate)
    COALESCE(
        (SELECT jsonb_agg(
                    jsonb_build_object(
                        'growth_stage', p.growth_stage,
                        'season', p.season,
                        'hours_covered', p.hours_covered,
                        'temp_ideal_min_24h', p.temp_ideal_min_24h,
                        'temp_ideal_max_24h', p.temp_ideal_max_24h,
                        'vpd_ideal_min_24h', p.vpd_ideal_min_24h,
                        'vpd_ideal_max_24h', p.vpd_ideal_max_24h,
                        'dli_target_mol', p.dli_target_mol
                    ) ORDER BY p.growth_stage, p.season)
         FROM (
            SELECT
                ctp.growth_stage,
                ctp.season,
                COUNT(*)::int AS hours_covered,
                AVG(ctp.temp_ideal_min) AS temp_ideal_min_24h,
                AVG(ctp.temp_ideal_max) AS temp_ideal_max_24h,
                AVG(ctp.vpd_ideal_min)  AS vpd_ideal_min_24h,
                AVG(ctp.vpd_ideal_max)  AS vpd_ideal_max_24h,
                AVG(ctp.dli_target_mol) AS dli_target_mol
            FROM crop_target_profiles ctp
            WHERE ctp.crop_catalog_id = cc.id
            GROUP BY ctp.growth_stage, ctp.season
         ) p),
        '[]'::jsonb
    ) AS stage_season_profiles
FROM crop_catalog cc
ORDER BY cc.slug;

COMMENT ON VIEW v_crop_catalog_with_profiles IS
    'Sprint 22: per-crop reference data + stage/season band aggregates. Drives the website crop-profile pages (currently hand-typed per variety).';


COMMIT;
