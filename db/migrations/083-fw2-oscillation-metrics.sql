-- Migration 083: FW-2 oscillation regression metrics (Sprint 18)
--
-- Context: the 96 h review flagged Apr-15 22:00 with 278 equipment state
-- changes in a single hour (vs baseline ~170) as the signature of the
-- oscillation root cause. DI-1 (proportional dead-bands) should reduce
-- this; we need a metric to prove it.
--
-- `v_daily_oscillation` is a per-day, per-equipment rollup of the worst
-- hour's transition count — i.e. "on day X, equipment Y's peak hourly
-- cycle count was Z". `v_daily_oscillation_summary` collapses further to
-- the single worst hour across all equipment for that day.

BEGIN;

CREATE OR REPLACE VIEW v_daily_oscillation AS
WITH hourly AS (
    SELECT
        date_trunc('day', ts) AS date,
        date_trunc('hour', ts) AS hour,
        equipment,
        count(*) AS transitions
    FROM equipment_state
    GROUP BY 1, 2, 3
)
SELECT
    date::date AS date,
    equipment,
    max(transitions) AS peak_transitions_per_hour,
    (array_agg(hour ORDER BY transitions DESC))[1] AS peak_hour,
    round(avg(transitions), 1) AS avg_transitions_per_hour,
    count(*) AS active_hours
FROM hourly
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

COMMENT ON VIEW v_daily_oscillation IS
    'FW-2: per-day, per-equipment peak hourly transition count. Use to detect oscillation regressions after dispatcher/firmware changes.';

CREATE OR REPLACE VIEW v_daily_oscillation_summary AS
SELECT
    date,
    sum(peak_transitions_per_hour) AS total_peak_per_hour,
    max(peak_transitions_per_hour) AS worst_equipment_peak,
    (array_agg(equipment ORDER BY peak_transitions_per_hour DESC))[1] AS worst_equipment,
    (array_agg(peak_hour ORDER BY peak_transitions_per_hour DESC))[1] AS worst_hour,
    round(avg(avg_transitions_per_hour), 1) AS avg_across_equipment
FROM v_daily_oscillation
GROUP BY 1
ORDER BY 1 DESC;

COMMENT ON VIEW v_daily_oscillation_summary IS
    'FW-2: single-row-per-day oscillation scorecard. worst_equipment + worst_hour identify the peak oscillation event of the day.';

COMMIT;
