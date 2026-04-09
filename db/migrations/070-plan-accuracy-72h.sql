-- Migration 070: v_plan_accuracy_72h — per-day accuracy within 72h plans
-- Computes day_offset (1/2/3) relative to each plan's first waypoint

CREATE OR REPLACE VIEW v_plan_accuracy_72h AS
WITH plan_starts AS (
    SELECT plan_id, min(planned_ts) AS plan_start
    FROM v_plan_compliance
    GROUP BY plan_id
)
SELECT
    c.plan_id,
    (EXTRACT(EPOCH FROM (c.planned_ts - ps.plan_start)) / 86400)::int + 1 AS day_offset,
    count(*)                                       AS waypoints_count,
    count(*) FILTER (WHERE c.plan_achieved)        AS achieved_count,
    round(
        100.0 * count(*) FILTER (WHERE c.plan_achieved)::numeric
        / NULLIF(count(*), 0)::numeric,
        1
    )                                              AS accuracy_pct,
    round(avg(abs(c.overshoot)), 2)                AS mean_abs_error
FROM v_plan_compliance c
JOIN plan_starts ps USING (plan_id)
WHERE (EXTRACT(EPOCH FROM (c.planned_ts - ps.plan_start)) / 86400)::int < 3
GROUP BY c.plan_id, (EXTRACT(EPOCH FROM (c.planned_ts - ps.plan_start)) / 86400)::int + 1
ORDER BY c.plan_id, day_offset;

COMMENT ON VIEW v_plan_accuracy_72h IS 'Per-day accuracy within 72h plans. day_offset: 1=first 24h, 2=24-48h, 3=48-72h.';
