-- 131-water-meter-quality-filter.sql
--
-- Water meter events already classify many impossible counter jumps as
-- high_delta, but the daily views were still summing every positive delta.
-- The original high-delta threshold was also too loose for the observed sample
-- cadence: interleaved counter lanes produced repeated 60-70 gallon jumps that
-- were still marked ok. That made Resource Use monthly cost charts report
-- physically impossible water spend.

UPDATE water_meter_events
   SET quality_flag = 'high_delta',
       raw = raw || jsonb_build_object('quality_reclass', 'migration_131_delta_gt_25')
 WHERE event_type = 'delta'
   AND quality_flag = 'ok'
   AND delta_gal > 25;

CREATE OR REPLACE VIEW v_water_meter_daily AS
SELECT
    ((ts AT TIME ZONE 'America/Denver')::date::timestamp AT TIME ZONE 'America/Denver') AS day,
    greenhouse_id,
    meter_id,
    round(
        COALESCE(
            sum(delta_gal) FILTER (
                WHERE event_type = 'delta'
                  AND quality_flag = 'ok'
            ),
            0
        )::numeric,
        3
    )::double precision AS used_gal,
    count(*) FILTER (
        WHERE event_type = 'delta'
          AND quality_flag = 'ok'
    ) AS delta_events,
    count(*) FILTER (WHERE event_type = 'reset') AS reset_events,
    count(*) FILTER (WHERE event_type = 'phantom_zero') AS phantom_zero_events,
    count(*) FILTER (WHERE quality_flag <> 'ok') AS quality_events
FROM water_meter_events
WHERE event_type IN ('delta', 'reset', 'phantom_zero')
GROUP BY 1, greenhouse_id, meter_id
ORDER BY day DESC;

COMMENT ON VIEW v_water_meter_daily IS
'Daily local-day water totals from water_meter_events. used_gal includes only quality_flag=ok deltas; quality_events counts rejected counter resets, phantom zeros, and high deltas for auditability.';

CREATE OR REPLACE VIEW v_water_daily AS
SELECT
    day,
    round(sum(used_gal)::numeric, 3)::double precision AS used_gal
FROM v_water_meter_daily
GROUP BY day
ORDER BY day DESC;

COMMENT ON VIEW v_water_daily IS
'Canonical America/Denver daily water usage from quality-filtered water_meter_events positive deltas.';

WITH meter_daily AS (
    SELECT
        day::date AS date,
        round(sum(used_gal)::numeric, 3)::double precision AS meter_gal
    FROM v_water_meter_daily
    GROUP BY 1
),
normalized AS (
    SELECT
        ds.date,
        greatest(COALESCE(md.meter_gal, 0), COALESCE(ds.mister_water_gal, 0)) AS water_gal
    FROM daily_summary ds
    JOIN meter_daily md ON md.date = ds.date
),
recomputed AS (
    SELECT
        date,
        water_gal,
        round((water_gal * 0.00484)::numeric, 2)::double precision AS cost_water
    FROM normalized
),
updated AS (
    UPDATE daily_summary ds
       SET water_used_gal = r.water_gal,
           cost_water = r.cost_water,
           cost_total = round((
               COALESCE(ds.cost_electric, 0)::numeric
               + COALESCE(ds.cost_gas, 0)::numeric
               + COALESCE(r.cost_water, 0)::numeric
           ), 2)::double precision,
           captured_at = now()
      FROM recomputed r
     WHERE ds.date = r.date
       AND (
           ds.water_used_gal IS DISTINCT FROM r.water_gal
           OR ds.cost_water IS DISTINCT FROM r.cost_water
       )
     RETURNING ds.date
)
SELECT count(*) AS daily_summary_water_rows_recomputed FROM updated;

WITH monthly AS (
    SELECT
        date_trunc('month', date)::date AS month,
        round(sum(COALESCE(cost_water, 0))::numeric, 2) AS amount_usd,
        round(sum(COALESCE(water_used_gal, 0))::numeric, 2) AS gallons
    FROM daily_summary
    GROUP BY 1
)
INSERT INTO utility_cost (month, category, amount_usd, gallons, notes)
SELECT month, 'water', amount_usd, gallons, 'Auto from daily_summary quality-filtered water meter events'
FROM monthly
ON CONFLICT (month, category) DO UPDATE SET
    amount_usd = EXCLUDED.amount_usd,
    gallons = EXCLUDED.gallons,
    notes = EXCLUDED.notes,
    updated_at = now();
