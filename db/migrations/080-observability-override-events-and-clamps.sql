-- Migration 080: Tier 1 observability — firmware overrides + dispatcher clamps
-- Context: 96h review (2026-04-13 → 2026-04-17) showed compliance collapse
-- from 59% → 14% with no visibility into WHY. Firmware silently blocks
-- misting/fog/seals under 7+ conditions; dispatcher silently clamps planner
-- setpoints to band edges. This migration adds the audit trail so the loop
-- from planner intent → physical behavior becomes queryable.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────
-- 1. override_events: firmware silent-override audit trail
-- ─────────────────────────────────────────────────────────────────────
-- Rows are written by the ingestor when the firmware emits an override
-- signal (via ESPHome text_sensor on override_log topic). Each row
-- records a single override fire so Iris can correlate compliance misses
-- with firmware decisions she didn't make.
CREATE TABLE IF NOT EXISTS override_events (
    ts             TIMESTAMPTZ NOT NULL DEFAULT now(),
    override_type  TEXT NOT NULL,
    mode           TEXT,
    details        JSONB,
    greenhouse_id  TEXT NOT NULL DEFAULT 'vallery'
);

SELECT create_hypertable('override_events', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_override_events_type
    ON override_events (override_type, ts DESC);
CREATE INDEX IF NOT EXISTS idx_override_events_ts
    ON override_events (ts DESC);

COMMENT ON TABLE override_events IS
    'Firmware silent-override audit trail. Written when ESP32 ignores planner intent (occupancy inhibit, fog gate, relief breaker, temp-near-safety, VPD dry override, etc.). Lets planner correlate compliance misses with overrides she cannot see otherwise.';
COMMENT ON COLUMN override_events.override_type IS
    'occupancy_blocks_moisture | fog_gate_rh | fog_gate_temp | fog_gate_window | relief_cycle_breaker | seal_blocked_temp | vpd_dry_override | enthalpy_stale';
COMMENT ON COLUMN override_events.mode IS
    'Firmware control mode when override fired (IDLE, VENTILATE, SEALED_MIST, DEHUM_VENT, THERMAL_RELIEF, SAFETY_COOL, SAFETY_HEAT, SENSOR_FAULT)';
COMMENT ON COLUMN override_events.details IS
    'Override-specific context: {"rh_pct": 92.1, "ceiling": 90} or {"count": 5, "max": 4}';

-- ─────────────────────────────────────────────────────────────────────
-- 2. setpoint_clamps: dispatcher clamp audit
-- ─────────────────────────────────────────────────────────────────────
-- Written by setpoint_dispatcher (ingestor/tasks.py) each time the
-- planner's requested value is clamped to the crop band edge. Lets
-- Iris see exactly what she asked for vs. what was applied.
CREATE TABLE IF NOT EXISTS setpoint_clamps (
    ts             TIMESTAMPTZ NOT NULL DEFAULT now(),
    parameter      TEXT NOT NULL,
    requested      DOUBLE PRECISION NOT NULL,
    applied        DOUBLE PRECISION NOT NULL,
    band_lo        DOUBLE PRECISION,
    band_hi        DOUBLE PRECISION,
    reason         TEXT NOT NULL,
    greenhouse_id  TEXT NOT NULL DEFAULT 'vallery'
);

SELECT create_hypertable('setpoint_clamps', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_setpoint_clamps_param
    ON setpoint_clamps (parameter, ts DESC);
CREATE INDEX IF NOT EXISTS idx_setpoint_clamps_ts
    ON setpoint_clamps (ts DESC);

COMMENT ON TABLE setpoint_clamps IS
    'Dispatcher clamp audit. Written when planner_val was clamped to band edge in setpoint_dispatcher. Without this, Iris has no way to know her requested setpoint was modified before reaching the device.';
COMMENT ON COLUMN setpoint_clamps.reason IS
    'band_lo | band_hi — which edge triggered the clamp';

-- ─────────────────────────────────────────────────────────────────────
-- 3. Convenience view: recent override activity
-- ─────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_override_activity_24h AS
SELECT
    override_type,
    COUNT(*) AS events,
    MIN(ts) AS first_seen,
    MAX(ts) AS last_seen,
    COUNT(DISTINCT mode) AS distinct_modes
FROM override_events
WHERE ts > now() - interval '24 hours'
GROUP BY override_type
ORDER BY events DESC;

COMMENT ON VIEW v_override_activity_24h IS
    'Firmware override frequency over last 24h. First gate on any compliance investigation.';

-- ─────────────────────────────────────────────────────────────────────
-- 4. Convenience view: recent clamp activity
-- ─────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_clamp_activity_24h AS
SELECT
    parameter,
    COUNT(*) AS clamp_events,
    ROUND(AVG(ABS(requested - applied))::numeric, 3) AS avg_clamp_delta,
    ROUND(MAX(ABS(requested - applied))::numeric, 3) AS max_clamp_delta,
    MIN(ts) AS first_seen,
    MAX(ts) AS last_seen
FROM setpoint_clamps
WHERE ts > now() - interval '24 hours'
GROUP BY parameter
ORDER BY clamp_events DESC;

COMMENT ON VIEW v_clamp_activity_24h IS
    'Dispatcher clamp frequency over last 24h. High counts = planner is asking for values outside the crop band.';

COMMIT;
