-- Use published device wattages and observed on-time as the canonical electric
-- cost source. Shelly metered kWh remains a diagnostic feed because current
-- circuit coverage does not explain heater/light/fog/fan runtime.

BEGIN;

WITH electric_runtime AS (
    SELECT
        r.day::date AS date,
        round(
            SUM((COALESCE(r.on_minutes, 0) / 60.0) * COALESCE(ea.wattage, 0) / 1000.0)::numeric,
            2
        ) AS runtime_kwh
    FROM v_equipment_runtime_daily r
    JOIN equipment_assets ea USING (equipment)
    WHERE ea.wattage IS NOT NULL
    GROUP BY r.day::date
)
UPDATE daily_summary ds
   SET kwh_estimated = er.runtime_kwh::double precision,
       cost_electric = round((er.runtime_kwh * 0.111)::numeric, 2)::double precision,
       cost_total = round((
           round((er.runtime_kwh * 0.111)::numeric, 2)
           + COALESCE(ds.cost_gas, 0)::numeric
           + COALESCE(ds.cost_water, 0)::numeric
       ), 2)::double precision,
       captured_at = now()
  FROM electric_runtime er
 WHERE ds.date = er.date
   AND er.runtime_kwh IS NOT NULL;

WITH monthly AS (
    SELECT
        date_trunc('month', date)::date AS month_start,
        round(SUM(COALESCE(cost_electric, 0))::numeric, 2) AS amount_usd,
        round(SUM(COALESCE(kwh_estimated, 0))::numeric, 2) AS kwh
    FROM daily_summary
    WHERE kwh_estimated IS NOT NULL
    GROUP BY 1
)
INSERT INTO utility_cost (month, category, amount_usd, kwh, notes)
SELECT month_start, 'electric', amount_usd, kwh, 'Auto from runtime-modeled device watts and on-time'
FROM monthly
ON CONFLICT (month, category) DO UPDATE SET
    amount_usd = EXCLUDED.amount_usd,
    kwh = EXCLUDED.kwh,
    notes = EXCLUDED.notes,
    updated_at = now();

CREATE OR REPLACE VIEW v_energy_estimate_reconciliation AS
SELECT
    ds.date,
    ds.kwh_estimated,
    ed.measured_kwh,
    round((ds.kwh_estimated - ed.measured_kwh::double precision)::numeric, 3) AS estimate_delta_kwh,
    CASE
        WHEN ed.measured_kwh IS NULL THEN 'missing_measured'
        WHEN ds.kwh_estimated IS NULL THEN 'missing_runtime_estimate'
        WHEN ed.measured_kwh = 0 AND ds.kwh_estimated > 1 THEN 'meter_runtime_divergence'
        WHEN ds.kwh_estimated = 0 AND ed.measured_kwh > 1 THEN 'meter_runtime_divergence'
        WHEN ds.kwh_estimated / NULLIF(ed.measured_kwh::double precision, 0) > 3 THEN 'meter_runtime_divergence'
        WHEN ed.measured_kwh::double precision / NULLIF(ds.kwh_estimated, 0) > 3 THEN 'meter_runtime_divergence'
        WHEN abs(ds.kwh_estimated - ed.measured_kwh::double precision) > 5 THEN 'meter_runtime_delta'
        ELSE 'ok'
    END AS quality_flag
FROM daily_summary ds
LEFT JOIN v_energy_daily ed USING (date)
WHERE ds.date IS NOT NULL;

COMMENT ON VIEW v_energy_estimate_reconciliation IS
'Compares runtime-modeled electric kWh from published equipment wattage and observed on-time against Shelly watt-time integration. Divergence is expected while Shelly circuit coverage is partial; the public electric cost uses runtime-modeled kWh.';

COMMIT;
