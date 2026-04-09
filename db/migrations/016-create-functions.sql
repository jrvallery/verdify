-- Migration 016: Create derived functions
-- These replace HA composite templates with DB-native logic.

-- fn_equipment_health(): Composite 0-100 score
-- Deductions: WiFi <-85 = -25, <-75 = -10; heap <15K = -25, <30K = -10;
--             each stuck relay = -20
CREATE OR REPLACE FUNCTION fn_equipment_health()
RETURNS INT AS $$
DECLARE
    score INT := 100;
    rssi FLOAT;
    heap FLOAT;
    stuck_count INT;
    probe TEXT;
BEGIN
    -- Get latest diagnostics
    SELECT wifi_rssi, heap_bytes, probe_health
    INTO rssi, heap, probe
    FROM diagnostics
    ORDER BY ts DESC LIMIT 1;

    -- WiFi deductions
    IF rssi IS NOT NULL THEN
        IF rssi < -85 THEN score := score - 25;
        ELSIF rssi < -75 THEN score := score - 10;
        END IF;
    END IF;

    -- Heap deductions
    IF heap IS NOT NULL THEN
        IF heap < 15000 THEN score := score - 25;
        ELSIF heap < 30000 THEN score := score - 10;
        END IF;
    END IF;

    -- Stuck relay deductions (requires v_relay_stuck materialized view)
    BEGIN
        SELECT COUNT(*) INTO stuck_count
        FROM v_relay_stuck
        WHERE is_stuck = TRUE;
        score := score - (stuck_count * 20);
    EXCEPTION WHEN undefined_table THEN
        -- v_relay_stuck not yet refreshed
        NULL;
    END;

    -- Probe health deductions
    IF probe IS NOT NULL AND probe != 'OK' THEN
        score := score - 15;
    END IF;

    RETURN GREATEST(0, score);
END;
$$ LANGUAGE plpgsql;

-- fn_stress_summary(): Human-readable stress text
-- Returns: '2.1h cold | 0h heat | 13.9h VPD high | 0h VPD low'
CREATE OR REPLACE FUNCTION fn_stress_summary(target_date DATE DEFAULT CURRENT_DATE)
RETURNS TEXT AS $$
DECLARE
    cold NUMERIC;
    heat NUMERIC;
    vpd_hi NUMERIC;
    vpd_lo NUMERIC;
BEGIN
    SELECT cold_stress_hours, heat_stress_hours, vpd_stress_hours, vpd_low_hours
    INTO cold, heat, vpd_hi, vpd_lo
    FROM v_stress_hours_today
    WHERE date = target_date::timestamptz;

    IF cold IS NULL THEN
        RETURN 'No data for ' || target_date::text;
    END IF;

    RETURN cold || 'h cold | ' || heat || 'h heat | ' || vpd_hi || 'h VPD high | ' || vpd_lo || 'h VPD low';
END;
$$ LANGUAGE plpgsql;
