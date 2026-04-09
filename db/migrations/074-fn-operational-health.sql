-- Migration 074: Create fn_operational_health() scoring function
-- Returns JSONB with {score, max_score, checks: [{name, score, max, status, detail}]}
-- 12 checks, max 105 points

CREATE OR REPLACE FUNCTION fn_operational_health()
RETURNS jsonb
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    checks jsonb := '[]'::jsonb;
    total_score int := 0;
    max_score int := 105;
    v_ts timestamptz;
    v_age interval;
    v_count int;
    v_detail text;
    v_score int;
    v_date date;
BEGIN
    -- 1. Data freshness: climate row < 2min old = 10pts
    SELECT ts INTO v_ts FROM climate ORDER BY ts DESC LIMIT 1;
    v_age := now() - v_ts;
    IF v_ts IS NOT NULL AND v_age < interval '2 minutes' THEN
        v_score := 10;
        v_detail := format('Latest row %s ago', to_char(v_age, 'MI:SS'));
    ELSIF v_ts IS NOT NULL THEN
        v_score := 0;
        v_detail := format('Stale: last row %s ago', to_char(v_age, 'HH24:MI:SS'));
    ELSE
        v_score := 0;
        v_detail := 'No climate data';
    END IF;
    total_score := total_score + v_score;
    checks := checks || jsonb_build_object(
        'name', 'data_freshness', 'score', v_score, 'max', 10,
        'status', CASE WHEN v_score = 10 THEN 'ok' ELSE 'fail' END, 'detail', v_detail);

    -- 2. All 6 probes reporting = 10pts
    -- Probes: temp_north, temp_south, temp_east, temp_west, temp_intake, temp_case
    SELECT COUNT(*) INTO v_count
    FROM (
        SELECT 1 WHERE (SELECT temp_north FROM climate ORDER BY ts DESC LIMIT 1) IS NOT NULL
        UNION ALL
        SELECT 1 WHERE (SELECT temp_south FROM climate ORDER BY ts DESC LIMIT 1) IS NOT NULL
        UNION ALL
        SELECT 1 WHERE (SELECT temp_east FROM climate ORDER BY ts DESC LIMIT 1) IS NOT NULL
        UNION ALL
        SELECT 1 WHERE (SELECT temp_west FROM climate ORDER BY ts DESC LIMIT 1) IS NOT NULL
        UNION ALL
        SELECT 1 WHERE (SELECT temp_intake FROM climate ORDER BY ts DESC LIMIT 1) IS NOT NULL
        UNION ALL
        SELECT 1 WHERE (SELECT temp_case FROM climate ORDER BY ts DESC LIMIT 1) IS NOT NULL
    ) probes;
    IF v_count = 6 THEN
        v_score := 10;
        v_detail := '6/6 probes reporting';
    ELSE
        v_score := 0;
        v_detail := format('%s/6 probes reporting', v_count);
    END IF;
    total_score := total_score + v_score;
    checks := checks || jsonb_build_object(
        'name', 'probe_coverage', 'score', v_score, 'max', 10,
        'status', CASE WHEN v_score = 10 THEN 'ok' ELSE 'fail' END, 'detail', v_detail);

    -- 3. Ingestor liveness: most recent climate row < 5min (proxy for systemd active) = 10pts
    -- DB cannot check systemd directly; use data freshness as proxy
    IF v_ts IS NOT NULL AND (now() - v_ts) < interval '5 minutes' THEN
        v_score := 10;
        v_detail := 'Ingestor alive (data flowing)';
    ELSE
        v_score := 0;
        v_detail := 'Ingestor may be down (no recent data)';
    END IF;
    total_score := total_score + v_score;
    checks := checks || jsonb_build_object(
        'name', 'ingestor_liveness', 'score', v_score, 'max', 10,
        'status', CASE WHEN v_score = 10 THEN 'ok' ELSE 'fail' END, 'detail', v_detail);

    -- 4. Active plan: future waypoints > 0 = 10pts
    SELECT COUNT(*) INTO v_count
    FROM setpoint_plan
    WHERE is_active = true AND ts > now();
    IF v_count > 0 THEN
        v_score := 10;
        v_detail := format('%s future waypoints', v_count);
    ELSE
        v_score := 0;
        v_detail := 'No active future waypoints';
    END IF;
    total_score := total_score + v_score;
    checks := checks || jsonb_build_object(
        'name', 'active_plan', 'score', v_score, 'max', 10,
        'status', CASE WHEN v_score = 10 THEN 'ok' ELSE 'fail' END, 'detail', v_detail);

    -- 5. Dispatcher: last setpoint push < 10min = 10pts
    SELECT ts INTO v_ts FROM setpoint_changes ORDER BY ts DESC LIMIT 1;
    IF v_ts IS NOT NULL AND (now() - v_ts) < interval '10 minutes' THEN
        v_score := 10;
        v_detail := format('Last push %s ago', to_char(now() - v_ts, 'MI:SS'));
    ELSIF v_ts IS NOT NULL THEN
        v_score := 0;
        v_detail := format('Last push %s ago', to_char(now() - v_ts, 'HH24:MI:SS'));
    ELSE
        v_score := 0;
        v_detail := 'No setpoint changes recorded';
    END IF;
    total_score := total_score + v_score;
    checks := checks || jsonb_build_object(
        'name', 'dispatcher_active', 'score', v_score, 'max', 10,
        'status', CASE WHEN v_score = 10 THEN 'ok' ELSE 'fail' END, 'detail', v_detail);

    -- 6. Equipment assets populated = 5pts
    SELECT COUNT(*) INTO v_count FROM equipment_assets;
    IF v_count > 0 THEN
        v_score := 5;
        v_detail := format('%s assets registered', v_count);
    ELSE
        v_score := 0;
        v_detail := 'No equipment assets';
    END IF;
    total_score := total_score + v_score;
    checks := checks || jsonb_build_object(
        'name', 'equipment_assets', 'score', v_score, 'max', 5,
        'status', CASE WHEN v_score = 5 THEN 'ok' ELSE 'fail' END, 'detail', v_detail);

    -- 7. Nutrient recipes populated = 5pts
    SELECT COUNT(*) INTO v_count FROM nutrient_recipes;
    IF v_count > 0 THEN
        v_score := 5;
        v_detail := format('%s recipes defined', v_count);
    ELSE
        v_score := 0;
        v_detail := 'No nutrient recipes';
    END IF;
    total_score := total_score + v_score;
    checks := checks || jsonb_build_object(
        'name', 'nutrient_recipes', 'score', v_score, 'max', 5,
        'status', CASE WHEN v_score = 5 THEN 'ok' ELSE 'fail' END, 'detail', v_detail);

    -- 8. Active crops > 0 = 5pts
    SELECT COUNT(*) INTO v_count FROM crops WHERE is_active = true;
    IF v_count > 0 THEN
        v_score := 5;
        v_detail := format('%s active crops', v_count);
    ELSE
        v_score := 0;
        v_detail := 'No active crops';
    END IF;
    total_score := total_score + v_score;
    checks := checks || jsonb_build_object(
        'name', 'active_crops', 'score', v_score, 'max', 5,
        'status', CASE WHEN v_score = 5 THEN 'ok' ELSE 'fail' END, 'detail', v_detail);

    -- 9. No relay stuck alerts = 10pts
    BEGIN
        SELECT COUNT(*) INTO v_count FROM v_relay_stuck WHERE is_stuck = true;
        IF v_count = 0 THEN
            v_score := 10;
            v_detail := 'No stuck relays';
        ELSE
            v_score := 0;
            v_detail := format('%s stuck relay(s)', v_count);
        END IF;
    EXCEPTION WHEN undefined_table THEN
        v_score := 10;
        v_detail := 'Relay stuck view not available (assumed ok)';
    END;
    total_score := total_score + v_score;
    checks := checks || jsonb_build_object(
        'name', 'relay_health', 'score', v_score, 'max', 10,
        'status', CASE WHEN v_score = 10 THEN 'ok' ELSE 'fail' END, 'detail', v_detail);

    -- 10. Forecast data < 6h old = 10pts
    SELECT MAX(fetched_at) INTO v_ts FROM weather_forecast;
    IF v_ts IS NOT NULL AND (now() - v_ts) < interval '6 hours' THEN
        v_score := 10;
        v_detail := format('Forecast fetched %s ago', to_char(now() - v_ts, 'HH24:MI'));
    ELSIF v_ts IS NOT NULL THEN
        v_score := 0;
        v_detail := format('Forecast stale: fetched %s ago', to_char(now() - v_ts, 'HH24:MI'));
    ELSE
        v_score := 0;
        v_detail := 'No forecast data';
    END IF;
    total_score := total_score + v_score;
    checks := checks || jsonb_build_object(
        'name', 'forecast_freshness', 'score', v_score, 'max', 10,
        'status', CASE WHEN v_score = 10 THEN 'ok' ELSE 'fail' END, 'detail', v_detail);

    -- 11. Daily summary current = 5pts
    SELECT MAX(date) INTO v_date FROM daily_summary;
    IF v_date IS NOT NULL AND v_date >= (CURRENT_DATE - 1) THEN
        v_score := 5;
        v_detail := format('Latest summary: %s', v_date);
    ELSIF v_date IS NOT NULL THEN
        v_score := 0;
        v_detail := format('Summary stale: last %s', v_date);
    ELSE
        v_score := 0;
        v_detail := 'No daily summaries';
    END IF;
    total_score := total_score + v_score;
    checks := checks || jsonb_build_object(
        'name', 'daily_summary', 'score', v_score, 'max', 5,
        'status', CASE WHEN v_score = 5 THEN 'ok' ELSE 'fail' END, 'detail', v_detail);

    -- 12. Soil sensors reporting = 10pts
    -- Check soil_moisture_south_1, soil_moisture_south_2, soil_moisture_west from latest climate row
    SELECT COUNT(*) INTO v_count
    FROM (
        SELECT 1 WHERE (SELECT soil_moisture_south_1 FROM climate ORDER BY ts DESC LIMIT 1) IS NOT NULL
        UNION ALL
        SELECT 1 WHERE (SELECT soil_moisture_south_2 FROM climate ORDER BY ts DESC LIMIT 1) IS NOT NULL
        UNION ALL
        SELECT 1 WHERE (SELECT soil_moisture_west FROM climate ORDER BY ts DESC LIMIT 1) IS NOT NULL
    ) soil;
    IF v_count = 3 THEN
        v_score := 10;
        v_detail := '3/3 soil sensors reporting';
    ELSIF v_count > 0 THEN
        v_score := 5;
        v_detail := format('%s/3 soil sensors reporting', v_count);
    ELSE
        v_score := 0;
        v_detail := 'No soil sensors reporting';
    END IF;
    total_score := total_score + v_score;
    checks := checks || jsonb_build_object(
        'name', 'soil_sensors', 'score', v_score, 'max', 10,
        'status', CASE WHEN v_score >= 10 THEN 'ok' WHEN v_score > 0 THEN 'degraded' ELSE 'fail' END, 'detail', v_detail);

    RETURN jsonb_build_object(
        'score', total_score,
        'max_score', max_score,
        'checks', checks
    );
END;
$$;

COMMENT ON FUNCTION fn_operational_health() IS 'Composite operational health score (0-105) with per-check breakdown as JSONB';
