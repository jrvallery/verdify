-- 061-equipment-runtime-view.sql
-- Compute daily equipment runtime from equipment_state transitions
-- Replaces broken ESP32 accumulator approach (resets at midnight before 00:05 snapshot)

CREATE OR REPLACE VIEW v_equipment_runtime_daily AS
WITH transitions AS (
    SELECT
        (ts AT TIME ZONE 'America/Denver')::date AS day,
        equipment, ts, state,
        LEAD(ts) OVER (PARTITION BY equipment, (ts AT TIME ZONE 'America/Denver')::date ORDER BY ts) AS next_ts
    FROM equipment_state
    WHERE equipment IN (
        'fan1','fan2','heat1','heat2','fog','vent',
        'mister_south','mister_west','mister_center',
        'grow_light_main','grow_light_grow',
        'drip_wall','drip_center'
    )
)
SELECT day, equipment,
    ROUND((SUM(EXTRACT(EPOCH FROM
        COALESCE(next_ts, (day + 1)::timestamp AT TIME ZONE 'America/Denver') - ts
    ) / 60.0) FILTER (WHERE state = true))::numeric, 1) AS on_minutes,
    COUNT(*) FILTER (WHERE state = true) AS cycles
FROM transitions
GROUP BY day, equipment;
