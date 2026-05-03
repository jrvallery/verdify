-- Migration 097: persist firmware per-zone mister/drip cycle counters.
--
-- Firmware sprint-7 publishes five daily diagnostic counters. This migration
-- gives the ingestor a DB home for them and adds an audit view that compares
-- firmware-reported daily counters with equipment_state rising-edge counts.

ALTER TABLE daily_summary
    ADD COLUMN IF NOT EXISTS cycles_mister_south integer,
    ADD COLUMN IF NOT EXISTS cycles_mister_west integer,
    ADD COLUMN IF NOT EXISTS cycles_mister_center integer,
    ADD COLUMN IF NOT EXISTS cycles_drip_wall integer,
    ADD COLUMN IF NOT EXISTS cycles_drip_center integer;

COMMENT ON COLUMN daily_summary.cycles_mister_south IS
    'Firmware daily_mister_south_cycles counter, reset at local midnight.';
COMMENT ON COLUMN daily_summary.cycles_mister_west IS
    'Firmware daily_mister_west_cycles counter, reset at local midnight.';
COMMENT ON COLUMN daily_summary.cycles_mister_center IS
    'Firmware daily_mister_center_cycles counter, reset at local midnight.';
COMMENT ON COLUMN daily_summary.cycles_drip_wall IS
    'Firmware daily_drip_wall_cycles counter, reset at local midnight.';
COMMENT ON COLUMN daily_summary.cycles_drip_center IS
    'Firmware daily_drip_center_cycles counter, reset at local midnight.';

CREATE OR REPLACE VIEW v_cycle_count_audit AS
WITH equipment_edges AS (
    SELECT
        date_trunc('day', ts AT TIME ZONE 'America/Denver')::date AS date,
        equipment,
        count(*) FILTER (
            WHERE state IS TRUE
              AND COALESCE(lag_state, FALSE) IS FALSE
        ) AS equipment_cycles
    FROM (
        SELECT
            ts,
            equipment,
            state,
            lag(state) OVER (
                PARTITION BY equipment, date_trunc('day', ts AT TIME ZONE 'America/Denver')
                ORDER BY ts
            ) AS lag_state
        FROM equipment_state
        WHERE equipment IN ('mister_south', 'mister_west', 'mister_center', 'drip_wall', 'drip_center')
    ) e
    GROUP BY date, equipment
),
firmware_cycles AS (
    SELECT date, 'mister_south'::text AS equipment, cycles_mister_south AS firmware_cycles FROM daily_summary
    UNION ALL SELECT date, 'mister_west', cycles_mister_west FROM daily_summary
    UNION ALL SELECT date, 'mister_center', cycles_mister_center FROM daily_summary
    UNION ALL SELECT date, 'drip_wall', cycles_drip_wall FROM daily_summary
    UNION ALL SELECT date, 'drip_center', cycles_drip_center FROM daily_summary
)
SELECT
    f.date,
    f.equipment,
    f.firmware_cycles,
    COALESCE(e.equipment_cycles, 0) AS equipment_cycles,
    f.firmware_cycles - COALESCE(e.equipment_cycles, 0) AS cycle_delta,
    CASE
        WHEN f.firmware_cycles IS NULL THEN 'missing_firmware_counter'
        WHEN GREATEST(f.firmware_cycles, COALESCE(e.equipment_cycles, 0)) = 0 THEN 'ok'
        WHEN abs(f.firmware_cycles - COALESCE(e.equipment_cycles, 0))::numeric
            / GREATEST(f.firmware_cycles, COALESCE(e.equipment_cycles, 0)) > 0.05 THEN 'warn'
        ELSE 'ok'
    END AS audit_status
FROM firmware_cycles f
LEFT JOIN equipment_edges e ON e.date = f.date AND e.equipment = f.equipment;

COMMENT ON VIEW v_cycle_count_audit IS
    'Compares firmware per-zone mister/drip cycle counters against equipment_state rising-edge counts; >5% divergence is warn.';
