-- Migration: P0 Security & Schema Alignment Fixes
-- Author: GitHub Copilot (via comprehensive audit)
-- Date: 2025-08-13
--
-- This migration addresses the highest-priority security vulnerabilities,
-- schema misalignments, and architectural gaps identified in the cross-audit
-- of API.md, openapi.yml, and DATABASE.md.

-- =============================================================================
-- TASK 1: Row-Level Security (RLS) - Multi-tenant isolation
-- =============================================================================

-- Enable RLS on core tables and create ownership-based policies
-- Users can only access greenhouses they own, and dependent resources via FK joins

-- Set up session variable for current user context
-- Backend will call: SET LOCAL app.current_user_id = '<user_uuid>';
CREATE OR REPLACE FUNCTION app.current_user_id() RETURNS UUID AS $$
BEGIN
  RETURN COALESCE(current_setting('app.current_user_id', TRUE)::UUID, '00000000-0000-0000-0000-000000000000'::UUID);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Enable RLS on greenhouse (root ownership)
ALTER TABLE greenhouse ENABLE ROW LEVEL SECURITY;

CREATE POLICY greenhouse_owner_access ON greenhouse
  FOR ALL
  USING (owner_id = app.current_user_id())
  WITH CHECK (owner_id = app.current_user_id());

-- Enable RLS on zone (via greenhouse ownership)
ALTER TABLE zone ENABLE ROW LEVEL SECURITY;

CREATE POLICY zone_owner_access ON zone
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM greenhouse g
      WHERE g.id = zone.greenhouse_id
      AND g.owner_id = app.current_user_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM greenhouse g
      WHERE g.id = zone.greenhouse_id
      AND g.owner_id = app.current_user_id()
    )
  );

-- Enable RLS on controller (via greenhouse ownership)
ALTER TABLE controller ENABLE ROW LEVEL SECURITY;

CREATE POLICY controller_owner_access ON controller
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM greenhouse g
      WHERE g.id = controller.greenhouse_id
      AND g.owner_id = app.current_user_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM greenhouse g
      WHERE g.id = controller.greenhouse_id
      AND g.owner_id = app.current_user_id()
    )
  );

-- Enable RLS on sensor (via controller->greenhouse ownership)
ALTER TABLE sensor ENABLE ROW LEVEL SECURITY;

CREATE POLICY sensor_owner_access ON sensor
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM controller c
      JOIN greenhouse g ON g.id = c.greenhouse_id
      WHERE c.id = sensor.controller_id
      AND g.owner_id = app.current_user_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM controller c
      JOIN greenhouse g ON g.id = c.greenhouse_id
      WHERE c.id = sensor.controller_id
      AND g.owner_id = app.current_user_id()
    )
  );

-- Enable RLS on actuator (via controller->greenhouse ownership)
ALTER TABLE actuator ENABLE ROW LEVEL SECURITY;

CREATE POLICY actuator_owner_access ON actuator
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM controller c
      JOIN greenhouse g ON g.id = c.greenhouse_id
      WHERE c.id = actuator.controller_id
      AND g.owner_id = app.current_user_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM controller c
      JOIN greenhouse g ON g.id = c.greenhouse_id
      WHERE c.id = actuator.controller_id
      AND g.owner_id = app.current_user_id()
    )
  );

-- Enable RLS on sensor_zone_map (via sensor->controller->greenhouse ownership)
ALTER TABLE sensor_zone_map ENABLE ROW LEVEL SECURITY;

CREATE POLICY sensor_zone_map_owner_access ON sensor_zone_map
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM sensor s
      JOIN controller c ON c.id = s.controller_id
      JOIN greenhouse g ON g.id = c.greenhouse_id
      WHERE s.id = sensor_zone_map.sensor_id
      AND g.owner_id = app.current_user_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM sensor s
      JOIN controller c ON c.id = s.controller_id
      JOIN greenhouse g ON g.id = c.greenhouse_id
      WHERE s.id = sensor_zone_map.sensor_id
      AND g.owner_id = app.current_user_id()
    )
  );

-- =============================================================================
-- TASK 2: Device Token Security - Hashed storage with expiry/revocation
-- =============================================================================

CREATE TABLE IF NOT EXISTS controller_token (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  controller_id UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  token_hash    TEXT NOT NULL, -- base64(sha256(token)) - never store plaintext
  issued_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at    TIMESTAMPTZ NOT NULL,
  revoked_at    TIMESTAMPTZ NULL,
  rotation_reason TEXT NULL, -- 'user_revoke', 'admin_revoke', 'rotation', 'security_incident'
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (controller_id, token_hash)
);

-- Index for fast auth lookups (active tokens only)
CREATE INDEX IF NOT EXISTS idx_controller_token_active
  ON controller_token(controller_id, token_hash)
  WHERE revoked_at IS NULL AND expires_at > now();

-- Index for cleanup/monitoring
CREATE INDEX IF NOT EXISTS idx_controller_token_expiry
  ON controller_token(expires_at);

-- RLS for controller tokens (via controller->greenhouse ownership)
ALTER TABLE controller_token ENABLE ROW LEVEL SECURITY;

CREATE POLICY controller_token_owner_access ON controller_token
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM controller c
      JOIN greenhouse g ON g.id = c.greenhouse_id
      WHERE c.id = controller_token.controller_id
      AND g.owner_id = app.current_user_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM controller c
      JOIN greenhouse g ON g.id = c.greenhouse_id
      WHERE c.id = controller_token.controller_id
      AND g.owner_id = app.current_user_id()
    )
  );

-- =============================================================================
-- TASK 4: Audit Logging - Track mutations with actor/before/after
-- =============================================================================

CREATE TABLE IF NOT EXISTS audit_log (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id       UUID NULL REFERENCES "user"(id) ON DELETE SET NULL,
  actor_controller_id UUID NULL REFERENCES controller(id) ON DELETE SET NULL,
  action              TEXT NOT NULL, -- INSERT, UPDATE, DELETE, PUBLISH, ROTATE_TOKEN, REVOKE_TOKEN
  table_name          TEXT NOT NULL,
  row_id              UUID NULL,
  before_data         JSONB NULL,
  after_data          JSONB NULL,
  occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  request_id          TEXT NULL, -- X-Request-Id for correlation
  CONSTRAINT audit_log_actor_check CHECK (
    (actor_user_id IS NOT NULL AND actor_controller_id IS NULL) OR
    (actor_user_id IS NULL AND actor_controller_id IS NOT NULL)
  )
);

-- Indexes for audit queries
CREATE INDEX IF NOT EXISTS idx_audit_log_occurred_at ON audit_log(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_table_row ON audit_log(table_name, row_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor_user ON audit_log(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor_controller ON audit_log(actor_controller_id);

-- RLS for audit log (users see audits for their resources only)
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_log_user_access ON audit_log
  FOR SELECT
  USING (
    -- User can see audits they performed
    actor_user_id = app.current_user_id()
    OR
    -- User can see audits on their resources (via controller->greenhouse)
    (actor_controller_id IS NOT NULL AND EXISTS (
      SELECT 1 FROM controller c
      JOIN greenhouse g ON g.id = c.greenhouse_id
      WHERE c.id = audit_log.actor_controller_id
      AND g.owner_id = app.current_user_id()
    ))
  );

-- =============================================================================
-- TASK 17: Idempotency Key Storage - Dedupe telemetry retries
-- =============================================================================

CREATE TABLE IF NOT EXISTS idempotency_key (
  controller_id UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  key          TEXT NOT NULL,
  seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  response_data JSONB NULL, -- cached response for replay
  PRIMARY KEY (controller_id, key)
);

-- TTL cleanup (retain for 24h)
CREATE INDEX IF NOT EXISTS idx_idempotency_key_ttl ON idempotency_key(seen_at)
WHERE seen_at < now() - INTERVAL '24 hours';

-- RLS for idempotency keys (device-scoped)
ALTER TABLE idempotency_key ENABLE ROW LEVEL SECURITY;

CREATE POLICY idempotency_key_controller_access ON idempotency_key
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM controller c
      JOIN greenhouse g ON g.id = c.greenhouse_id
      WHERE c.id = idempotency_key.controller_id
      AND g.owner_id = app.current_user_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM controller c
      JOIN greenhouse g ON g.id = c.greenhouse_id
      WHERE c.id = idempotency_key.controller_id
      AND g.owner_id = app.current_user_id()
    )
  );

-- =============================================================================
-- TASK 7: Sensor-Zone Mapping - Enforce unique (zone_id, kind)
-- =============================================================================

-- Keep existing unique constraint for exact duplicate prevention
-- Add new constraint for business rule: only one sensor per zone/kind
CREATE UNIQUE INDEX IF NOT EXISTS uq_sensor_zone_map_zone_kind
  ON sensor_zone_map(zone_id, kind);

-- Note: This may require data cleanup if violations exist
-- Check before applying: SELECT zone_id, kind, COUNT(*) FROM sensor_zone_map GROUP BY zone_id, kind HAVING COUNT(*) > 1;

-- =============================================================================
-- TASK 19: Actuator Constraints - Unique relay channels per controller
-- =============================================================================

-- Ensure (controller_id, relay_channel) is unique when relay_channel is not null
CREATE UNIQUE INDEX IF NOT EXISTS uq_actuator_controller_channel
  ON actuator(controller_id, relay_channel)
  WHERE relay_channel IS NOT NULL;

-- Range check for relay channels
ALTER TABLE actuator
  ADD CONSTRAINT relay_channel_positive
  CHECK (relay_channel IS NULL OR relay_channel > 0);

-- =============================================================================
-- TASK 20: Climate Controller Singleton - One per greenhouse
-- =============================================================================

-- Ensure only one climate controller per greenhouse
CREATE UNIQUE INDEX IF NOT EXISTS uq_climate_controller_per_greenhouse
  ON controller(greenhouse_id)
  WHERE is_climate_controller = true;

-- =============================================================================
-- TASK 21: Device Name Constraints - Unique with format validation
-- =============================================================================

-- Enforce device_name format and uniqueness
ALTER TABLE controller
  ADD CONSTRAINT device_name_format
  CHECK (device_name ~ '^verdify-[0-9a-f]{6}$');

CREATE UNIQUE INDEX IF NOT EXISTS uq_controller_device_name
  ON controller(device_name);

-- =============================================================================
-- TASK 22: Plan Integrity - Versioning and activeness constraints
-- =============================================================================

-- Note: Assuming plan table exists (not fully shown in DATABASE.md)
-- Ensure only one active plan per greenhouse
-- CREATE UNIQUE INDEX IF NOT EXISTS uq_active_plan_per_greenhouse
--   ON plan(greenhouse_id) WHERE is_active = true;

-- Ensure effective date windows are valid
-- ALTER TABLE plan
--   ADD CONSTRAINT effective_window_valid
--   CHECK (effective_from < effective_to);

-- =============================================================================
-- TASK 9: Controller Schema Updates - Add label and last_seen fields
-- =============================================================================

-- Add missing fields to controller table (align with openapi.yml changes)
ALTER TABLE controller
  ADD COLUMN IF NOT EXISTS label TEXT NULL,
  ADD COLUMN IF NOT EXISTS last_seen TIMESTAMPTZ NULL;

-- Create index for last_seen queries (monitoring/health)
CREATE INDEX IF NOT EXISTS idx_controller_last_seen ON controller(last_seen DESC);

-- =============================================================================
-- TASK 28: Config Snapshots - Version/ETag persistence
-- =============================================================================

CREATE TABLE IF NOT EXISTS config_snapshot (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  greenhouse_id UUID NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  version       INTEGER NOT NULL,
  payload       JSONB NOT NULL,
  etag          TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by    UUID NULL REFERENCES "user"(id) ON DELETE SET NULL,
  UNIQUE (greenhouse_id, version)
);

-- Index for ETag-based config fetches
CREATE INDEX IF NOT EXISTS idx_config_snapshot_etag ON config_snapshot(greenhouse_id, etag);
CREATE INDEX IF NOT EXISTS idx_config_snapshot_latest ON config_snapshot(greenhouse_id, version DESC);

-- RLS for config snapshots (via greenhouse ownership)
ALTER TABLE config_snapshot ENABLE ROW LEVEL SECURITY;

CREATE POLICY config_snapshot_owner_access ON config_snapshot
  FOR ALL
  USING (
    EXISTS (
      SELECT 1 FROM greenhouse g
      WHERE g.id = config_snapshot.greenhouse_id
      AND g.owner_id = app.current_user_id()
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM greenhouse g
      WHERE g.id = config_snapshot.greenhouse_id
      AND g.owner_id = app.current_user_id()
    )
  );

-- =============================================================================
-- TASK 18: TimescaleDB Hypertables - Time-series optimization
-- =============================================================================

-- Note: These tables may already exist. Add IF NOT EXISTS checking.
-- Ensure sensor_reading is a hypertable with proper indexes

-- Example for sensor_reading (adapt based on actual schema):
-- SELECT create_hypertable('sensor_reading', 'ts_utc', if_not_exists => TRUE);
-- CREATE INDEX IF NOT EXISTS idx_sensor_reading_sensor_time ON sensor_reading(sensor_id, ts_utc DESC);
-- SELECT add_compression_policy('sensor_reading', INTERVAL '7 days', if_not_exists => TRUE);
-- SELECT add_retention_policy('sensor_reading', INTERVAL '365 days', if_not_exists => TRUE);

-- Enable RLS on time-series tables (via sensor->controller->greenhouse)
-- ALTER TABLE sensor_reading ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY sensor_reading_owner_access ON sensor_reading
--   FOR ALL
--   USING (
--     EXISTS (
--       SELECT 1 FROM sensor s
--       JOIN controller c ON c.id = s.controller_id
--       JOIN greenhouse g ON g.id = c.greenhouse_id
--       WHERE s.id = sensor_reading.sensor_id
--       AND g.owner_id = app.current_user_id()
--     )
--   );

-- =============================================================================
-- Cleanup and Maintenance Functions
-- =============================================================================

-- Function to cleanup expired idempotency keys
CREATE OR REPLACE FUNCTION cleanup_expired_idempotency_keys()
RETURNS INTEGER AS $$
DECLARE
  deleted_count INTEGER;
BEGIN
  DELETE FROM idempotency_key
  WHERE seen_at < now() - INTERVAL '24 hours';

  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to cleanup old audit logs (optional retention)
CREATE OR REPLACE FUNCTION cleanup_old_audit_logs(retention_days INTEGER DEFAULT 365)
RETURNS INTEGER AS $$
DECLARE
  deleted_count INTEGER;
BEGIN
  DELETE FROM audit_log
  WHERE occurred_at < now() - (retention_days || ' days')::INTERVAL;

  GET DIAGNOSTICS deleted_count = ROW_COUNT;
  RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Migration Verification Queries
-- =============================================================================

-- Verify RLS is enabled
-- SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname = 'public' AND tablename IN
--   ('greenhouse', 'zone', 'controller', 'sensor', 'actuator', 'sensor_zone_map', 'controller_token', 'audit_log', 'idempotency_key', 'config_snapshot');

-- Verify unique constraints exist
-- SELECT conname, contype FROM pg_constraint WHERE conname LIKE 'uq_%';

-- Test RLS policies (as non-superuser)
-- SET app.current_user_id = 'your-test-user-uuid';
-- SELECT COUNT(*) FROM greenhouse; -- Should only show user's greenhouses

COMMIT;
