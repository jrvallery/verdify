-- 063-forecast-action-engine.sql
-- Forecast-driven preemptive adjustment rule engine

CREATE TABLE IF NOT EXISTS forecast_action_rules (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    condition TEXT NOT NULL,          -- human-readable description
    metric TEXT NOT NULL,             -- forecast column: temp_f, rh_pct, wind_speed_mph, precip_in
    operator TEXT NOT NULL CHECK (operator IN ('<', '>', '<=', '>=')),
    threshold NUMERIC NOT NULL,
    time_window TEXT NOT NULL DEFAULT '24h',  -- how far ahead to look: 24h, 48h
    param TEXT,                       -- setpoint parameter to adjust (NULL = log only)
    adjustment_value NUMERIC,         -- absolute value to set (not relative)
    action_type TEXT NOT NULL DEFAULT 'setpoint' CHECK (action_type IN ('setpoint', 'alert', 'log')),
    priority INT DEFAULT 50,          -- lower = higher priority
    cooldown_hours INT DEFAULT 6,     -- don't re-trigger within this window
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS forecast_action_log (
    id SERIAL PRIMARY KEY,
    rule_id INT REFERENCES forecast_action_rules(id),
    rule_name TEXT NOT NULL,
    triggered_at TIMESTAMPTZ DEFAULT now(),
    forecast_condition JSONB,         -- snapshot of the triggering forecast data
    action_taken TEXT NOT NULL,       -- 'setpoint_written', 'alert_posted', 'skipped_cooldown', 'evaluated_ok'
    plan_id TEXT,                     -- if setpoint written, the plan_id used
    param TEXT,
    old_value NUMERIC,
    new_value NUMERIC,
    outcome TEXT                       -- filled later by planner or manually
);

CREATE INDEX IF NOT EXISTS idx_forecast_log_triggered ON forecast_action_log (triggered_at DESC);
CREATE INDEX IF NOT EXISTS idx_forecast_rules_enabled ON forecast_action_rules (enabled, priority);

-- View: recent forecast actions
CREATE OR REPLACE VIEW v_forecast_actions_recent AS
SELECT
    fl.triggered_at AT TIME ZONE 'America/Denver' AS triggered,
    fl.rule_name,
    fl.action_taken,
    fl.param,
    fl.old_value,
    fl.new_value,
    fl.plan_id,
    fl.forecast_condition->>'trigger_value' AS trigger_value,
    fl.forecast_condition->>'trigger_hour' AS trigger_hour,
    fl.outcome
FROM forecast_action_log fl
WHERE fl.triggered_at > now() - interval '7 days'
ORDER BY fl.triggered_at DESC;

-- Seed default rules
INSERT INTO forecast_action_rules (name, condition, metric, operator, threshold, time_window, param, adjustment_value, action_type, priority, cooldown_hours) VALUES
('hard_freeze', 'Overnight low < 28°F — hard freeze protection', 'temp_f', '<', 28, '24h', 'temp_low', 55, 'setpoint', 10, 6),
('extreme_freeze', 'Overnight low < 20°F — extreme freeze, alert + lower floor', 'temp_f', '<', 20, '24h', 'temp_low', 50, 'setpoint', 5, 6),
('heat_wave', 'Daytime high > 90°F — preemptive cooling', 'temp_f', '>', 90, '24h', 'temp_high', 80, 'setpoint', 20, 6),
('extreme_heat', 'Daytime high > 100°F — aggressive cooling + misting', 'temp_f', '>', 100, '24h', 'temp_high', 78, 'setpoint', 10, 6),
('high_wind', 'Wind > 30mph — close vent for protection', 'wind_speed_mph', '>', 30, '24h', 'sw_economiser_enabled', 0, 'setpoint', 30, 4),
('disease_risk', 'RH > 80% + temp > 75°F — Botrytis/condensation risk', 'rh_pct', '>', 80, '24h', NULL, NULL, 'alert', 40, 12),
('storm_precip', 'Heavy precip > 0.5in — pre-ventilate if humid', 'precip_in', '>', 0.5, '48h', NULL, NULL, 'log', 50, 12),
('heat_misting', 'Daytime high > 90°F — extend mister pulse', 'temp_f', '>', 90, '24h', 'mister_pulse_on_s', 90, 'setpoint', 25, 6);
