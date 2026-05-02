-- Refresh measured daily energy after the recurring daily_summary writers were
-- taught to maintain kwh_total from v_energy_daily.

BEGIN;

UPDATE daily_summary ds
SET kwh_total = ed.measured_kwh::double precision,
    peak_kw = (ed.peak_watts / 1000.0)::double precision,
    cost_electric = round((ed.measured_kwh * 0.111), 2)::double precision,
    cost_total = round((
        COALESCE(round((ed.measured_kwh * 0.111), 2), ds.cost_electric::numeric, 0)
        + COALESCE(ds.cost_gas::numeric, 0)
        + COALESCE(ds.cost_water::numeric, 0)
    ), 2)::double precision,
    captured_at = now()
FROM v_energy_daily ed
WHERE ds.date = ed.date
  AND ed.measured_kwh IS NOT NULL;

COMMIT;
