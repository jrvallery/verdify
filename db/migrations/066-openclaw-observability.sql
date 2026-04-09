-- 066-openclaw-observability.sql
-- OpenClaw interaction logging + usage views

CREATE TABLE IF NOT EXISTS openclaw_interaction_log (
    id SERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_type TEXT NOT NULL,
    action TEXT,
    duration_ms INTEGER,
    tokens_in INTEGER,
    tokens_out INTEGER,
    model TEXT,
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX idx_openclaw_ts ON openclaw_interaction_log (ts DESC);
CREATE INDEX idx_openclaw_type ON openclaw_interaction_log (session_type, ts DESC);

CREATE OR REPLACE VIEW v_openclaw_usage_daily AS
SELECT
    (ts AT TIME ZONE 'America/Denver')::date AS day,
    session_type,
    COUNT(*) AS calls,
    SUM(COALESCE(tokens_in, 0) + COALESCE(tokens_out, 0)) AS total_tokens,
    SUM(COALESCE(duration_ms, 0)) AS total_duration_ms,
    ROUND(AVG(duration_ms)::numeric, 0) AS avg_duration_ms,
    COUNT(*) FILTER (WHERE NOT success) AS error_count
FROM openclaw_interaction_log
GROUP BY 1, 2;

CREATE OR REPLACE VIEW v_openclaw_usage_hourly AS
SELECT
    date_trunc('hour', ts) AS hour,
    session_type,
    COUNT(*) AS calls,
    SUM(COALESCE(tokens_in, 0) + COALESCE(tokens_out, 0)) AS total_tokens,
    SUM(COALESCE(duration_ms, 0)) AS total_duration_ms,
    COUNT(*) FILTER (WHERE NOT success) AS error_count
FROM openclaw_interaction_log
WHERE ts > now() - interval '7 days'
GROUP BY 1, 2;
