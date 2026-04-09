-- v_setpoint_forward: projects current setpoint values forward in time
-- Provides two anchor points per param: now() and now()+7d
-- Future plan waypoints appear between them, creating step transitions
-- Used by homepage charts to draw continuous setpoint lines into the future
CREATE OR REPLACE VIEW v_setpoint_forward AS
-- Current value at now()
SELECT parameter, now() as ts, value, 'current' as source
FROM v_active_plan
WHERE parameter IN ('temp_high','temp_low','vpd_high','vpd_low','vpd_hysteresis','d_cool_stage_2',
  'mister_engage_kpa','mister_all_kpa','mister_pulse_on_s','mister_pulse_gap_s')
UNION ALL
-- Same value projected 7 days forward (gives Grafana a line endpoint)
SELECT parameter, now() + interval '7 days' as ts, value, 'projection' as source
FROM v_active_plan
WHERE parameter IN ('temp_high','temp_low','vpd_high','vpd_low','vpd_hysteresis','d_cool_stage_2',
  'mister_engage_kpa','mister_all_kpa','mister_pulse_on_s','mister_pulse_gap_s')
UNION ALL
-- Future plan waypoints override the flat projection
SELECT parameter, ts, value, 'plan' as source
FROM setpoint_plan
WHERE parameter IN ('temp_high','temp_low','vpd_high','vpd_low','vpd_hysteresis','d_cool_stage_2',
  'mister_engage_kpa','mister_all_kpa','mister_pulse_on_s','mister_pulse_gap_s')
AND is_active = true AND ts > now()
ORDER BY parameter, ts;
