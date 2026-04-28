-- 098-greenhouse-state-refresh.sql
-- Keep v_greenhouse_state current and make latest equipment state tie-breaking
-- deterministic when ESPHome emits same-timestamp true/false pulses.

CREATE OR REPLACE FUNCTION refresh_greenhouse_state(job_id integer DEFAULT 0, config jsonb DEFAULT '{}'::jsonb)
RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW v_greenhouse_state;
END;
$$;

COMMENT ON FUNCTION refresh_greenhouse_state(integer, jsonb) IS
    'Refresh v_greenhouse_state; invoked by ingestor matview_refresh every 5 minutes.';

CREATE OR REPLACE VIEW v_equipment_now AS
SELECT DISTINCT ON (equipment)
  equipment,
  state,
  ts AS since,
  ROUND(EXTRACT(EPOCH FROM now() - ts)::numeric) AS seconds_ago
FROM equipment_state
ORDER BY equipment, ts DESC, state ASC;

COMMENT ON VIEW v_equipment_now IS
    'Current state of every equipment relay. Same-timestamp false/true pulses resolve false first.';
