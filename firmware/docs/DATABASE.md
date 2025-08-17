
# Database and Data Structures Specification for AI‑Powered Greenhouse (Project Verdify)

**Version:** 2.0
**Author:** Postgres/Timescale Database Architect
**Status:** Authoritative DDL and data model for MVP (HTTP ingest only)

---

## 0. Scope & Conventions

* **Goal:** Provide a complete, copy‑paste‑ready schema for Project Verdify MVP, optimized for correctness and time‑series analytics.
* **Applies to:** API, Planning Engine, Controller, and App. All IDs and field names **must** match the API spec.
* **Canonical invariants:**

  * **snake\_case** fields; **UUIDv4** primary keys (`uuid` type).
  * Device identity: **`device_name`** (user‑facing) = `verdify-aabbcc` where `aabbcc` are last 3 MAC bytes (lowercase hex). Regex: `^verdify-[0-9a-f]{6}$`.
  * **Metric** units on wire and in DB; timestamps as **UTC** `timestamptz`.
  * **Zones & plantings:** 1 active planting per zone (1:1).
  * **Sensor ↔ Zone mapping:** Many‑to‑many via `sensor_zone_map`, unique `(sensor_id, zone_id, kind)`.
  * **Climate loop:** Exactly one `is_climate_controller = true` per greenhouse.
  * **State machine grid:** temp\_stage ∈ `[-3..+3]` × humi\_stage ∈ `[-3..+3]` plus **one fallback** row.
  * **Irrigation lockout:** Enforced in controller; DB supports scheduling and audit.
* **Timescale:** Hypertables for `sensor_reading`, `actuator_event`, `controller_status`, `input_event` with chunking, compression, and (optional) retention policies.

---

## 1. Sub‑Projects & Tasks

1. **Core Tables** — users, greenhouses, zones, crops, controllers, sensors, actuators, mappings.
2. **Relationships & Indexes** — all FKs, unique constraints, partial uniques (climate singleton), and common query indexes.
3. **Planning & State Machine** — plan tables, state machine tables (normalized), config snapshots.
4. **Timeseries** — hypertables + policies.
5. **Views & Procedures** — analytics views (daily runtimes/cycles), validation functions.
6. **Queries** — ready‑to‑use analytics and correlation examples.
7. **Data Migration/Backup** — initial setup notes.

Each section includes DDL, normalization notes, and usage.

---

## 2. Security Framework & Row-Level Security (RLS)

### 2.1 Multi-Tenant Isolation via RLS

**Critical Security Requirement**: All tables must enforce tenant isolation using PostgreSQL Row-Level Security (RLS) policies. Users can only access greenhouses they own and dependent resources via foreign key relationships.

```sql
-- 2.1.1 Session context function for current user
-- Backend middleware sets: SET LOCAL app.current_user_id = '<user_uuid>';
CREATE OR REPLACE FUNCTION app.current_user_id() RETURNS UUID AS $$
BEGIN
  RETURN COALESCE(current_setting('app.current_user_id', TRUE)::UUID, '00000000-0000-0000-0000-000000000000'::UUID);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 2.1.2 Device context function for controller token authentication
-- Backend sets: SET LOCAL app.current_controller_id = '<controller_uuid>';
CREATE OR REPLACE FUNCTION app.current_controller_id() RETURNS UUID AS $$
BEGIN
  RETURN COALESCE(current_setting('app.current_controller_id', TRUE)::UUID, '00000000-0000-0000-0000-000000000000'::UUID);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;
```

**Implementation Notes**:
- RLS policies are applied to **all core tables** after table creation (see sections 3.x)
- User endpoints: Set `app.current_user_id` from JWT claims
- Device endpoints: Set `app.current_controller_id` from device token validation
- Superuser/admin queries: Use `SET LOCAL` override or disable RLS temporarily

### 2.2 Device Token Security

Device tokens must be stored **hashed** with expiry and revocation tracking to prevent token theft and enable proper lifecycle management.

```sql
-- Enhanced controller_token table (replaces basic version in section 3.4)
CREATE TABLE IF NOT EXISTS controller_token (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  controller_id   UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  token_hash      TEXT NOT NULL,  -- base64(sha256(token)) - never store plaintext
  issued_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at      TIMESTAMPTZ NOT NULL,
  revoked_at      TIMESTAMPTZ NULL,
  rotation_reason TEXT NULL,      -- 'user_revoke', 'admin_revoke', 'rotation', 'security_incident'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (controller_id, token_hash)
);

-- Indexes for fast authentication and cleanup
CREATE INDEX IF NOT EXISTS idx_controller_token_active
  ON controller_token(controller_id, token_hash)
  WHERE revoked_at IS NULL AND expires_at > now();

CREATE INDEX IF NOT EXISTS idx_controller_token_expiry
  ON controller_token(expires_at);
```

### 2.3 Audit Logging

Complete audit trail for all mutations with actor tracking and before/after state capture for compliance and incident response.

```sql
CREATE TABLE IF NOT EXISTS audit_log (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id       UUID NULL REFERENCES app_user(id) ON DELETE SET NULL,
  actor_controller_id UUID NULL REFERENCES controller(id) ON DELETE SET NULL,
  action              TEXT NOT NULL, -- INSERT, UPDATE, DELETE, PUBLISH, ROTATE_TOKEN, REVOKE_TOKEN
  table_name          TEXT NOT NULL,
  row_id              UUID NULL,
  before_data         JSONB NULL,
  after_data          JSONB NULL,
  occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  request_id          TEXT NULL,      -- X-Request-Id for correlation
  CONSTRAINT audit_log_actor_check CHECK (
    (actor_user_id IS NOT NULL AND actor_controller_id IS NULL) OR
    (actor_user_id IS NULL AND actor_controller_id IS NOT NULL)
  )
);

-- Indexes for audit queries and performance
CREATE INDEX IF NOT EXISTS idx_audit_log_occurred_at ON audit_log(occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_table_row ON audit_log(table_name, row_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor_user ON audit_log(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_actor_controller ON audit_log(actor_controller_id);
```

### 2.4 Idempotency Protection

Prevent duplicate telemetry processing during network retries and ensure reliable device communication.

```sql
CREATE TABLE IF NOT EXISTS idempotency_key (
  controller_id UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  key          TEXT NOT NULL,
  seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  response_data JSONB NULL,  -- cached response for replay
  PRIMARY KEY (controller_id, key)
);

-- TTL cleanup index (cleanup keys older than 24h)
CREATE INDEX IF NOT EXISTS idx_idempotency_key_ttl ON idempotency_key(seen_at)
WHERE seen_at < now() - INTERVAL '24 hours';
```

---

## 3. DDL — Extensions, Types, Meta (Dependency Order)

> Run top‑to‑bottom. No Alembic required yet.

```sql
-- 3.1 Extensions (install once per database)
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pgcrypto;     -- gen_random_uuid()
-- optional:
-- CREATE EXTENSION IF NOT EXISTS citext;   -- for case-insensitive emails

-- 3.2 Enums
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'location_enum') THEN
    CREATE TYPE location_enum AS ENUM ('N','NE','E','SE','S','SW','W','NW');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'button_kind_enum') THEN
    CREATE TYPE button_kind_enum AS ENUM ('cool','heat','humid');
  END IF;
END$$;

-- 3.3 Meta (kinds)
CREATE TABLE IF NOT EXISTS sensor_kind_meta (
  kind        TEXT PRIMARY KEY,
  value_type  TEXT NOT NULL CHECK (value_type IN ('float','int')),
  unit        TEXT NOT NULL,   -- metric only (e.g., '°C','%','kPa','hPa','m³/m³','L/min','L','ppm','lx','µmol/m²/s','kWh','kW','m/s','mm','g/m³','kJ/kg')
  notes       TEXT
);

CREATE TABLE IF NOT EXISTS actuator_kind_meta (
  kind        TEXT PRIMARY KEY,
  notes       TEXT
);

-- 3.4 Seed meta values (idempotent)
INSERT INTO sensor_kind_meta(kind, value_type, unit, notes) VALUES
  ('temperature','float','°C','ambient/surface/soil'),
  ('humidity','float','%','relative humidity'),
  ('vpd','float','kPa','vapor pressure deficit'),
  ('co2','float','ppm','CO₂ concentration'),
  ('light','float','lx','photometric lux'),
  ('ppfd','float','µmol/m²/s','photosynthetic photon flux density'),
  ('soil_moisture','float','m³/m³','volumetric water content'),
  ('water_flow','float','L/min','instantaneous flow'),
  ('water_total','float','L','cumulative volume'),
  ('air_pressure','float','hPa','barometric pressure'),
  ('dew_point','float','°C','derived'),
  ('absolute_humidity','float','g/m³','derived'),
  ('enthalpy_delta','float','kJ/kg','derived in-out'),
  ('kwh','float','kWh','energy consumption'),
  ('power','float','kW','instantaneous power'),
  ('gas_consumption','float','m³','fuel usage'),
  ('wind_speed','float','m/s','external'),
  ('rainfall','float','mm','external')
ON CONFLICT (kind) DO NOTHING;

INSERT INTO actuator_kind_meta(kind, notes) VALUES
  ('fan','ventilation'),
  ('heater','heating'),
  ('vent','vent opening'),
  ('fogger','humidifier'),
  ('irrigation_valve','water valve'),
  ('fertilizer_valve','fert valve'),
  ('pump','general pump'),
  ('light','grow light')
ON CONFLICT (kind) DO NOTHING;
```

**Normalization:** Kinds are **data‑driven** (meta tables) instead of hard enums → extensible without DDL changes. All other controlled vocabularies are enums or checks with narrow scope (e.g., button\_kind).

---

## 4. Core Entity Tables

### 4.1 Users

```sql
CREATE TABLE IF NOT EXISTS app_user (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email           TEXT NOT NULL UNIQUE, -- consider CITEXT
  hashed_password TEXT NOT NULL,
  full_name       TEXT,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  is_superuser    BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.2 Greenhouses & Zones

```sql
CREATE TABLE IF NOT EXISTS greenhouse (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id             UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  title                TEXT NOT NULL,
  description          TEXT,
  is_active            BOOLEAN NOT NULL DEFAULT TRUE,
  latitude             DOUBLE PRECISION,
  longitude            DOUBLE PRECISION,
  -- Guard rails (immutable by plan)
  min_temp_c           DOUBLE PRECISION NOT NULL DEFAULT 7.0,
  max_temp_c           DOUBLE PRECISION NOT NULL DEFAULT 35.0,
  min_vpd_kpa          DOUBLE PRECISION NOT NULL DEFAULT 0.30,
  max_vpd_kpa          DOUBLE PRECISION NOT NULL DEFAULT 2.50,
  -- Dehumid enthalpy thresholds and site pressure
  enthalpy_open_kjkg   DOUBLE PRECISION NOT NULL DEFAULT -2.0,
  enthalpy_close_kjkg  DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  site_pressure_hpa    DOUBLE PRECISION NOT NULL DEFAULT 840.0,
  -- Unit profile: enforce metric-only (remove imperial support)
  unit_profile         TEXT NOT NULL DEFAULT 'metric' CHECK (unit_profile = 'metric'),
  context_text         TEXT,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS zone (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  greenhouse_id  UUID NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  zone_number    INTEGER NOT NULL CHECK (zone_number > 0),
  location       location_enum NOT NULL,
  context_text   TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (greenhouse_id, zone_number)
);
CREATE INDEX IF NOT EXISTS idx_zone_greenhouse ON zone(greenhouse_id);
```

**Normalization:** `zone` references `greenhouse`. Unique `(greenhouse_id, zone_number)` enforces identity.

### 4.3 Crops, Plantings, Observations

```sql
CREATE TABLE IF NOT EXISTS crop (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name                     TEXT NOT NULL,
  description              TEXT,
  expected_yield_per_sqm   DOUBLE PRECISION,
  growing_days             INTEGER,
  recipe                   JSONB,     -- crop template
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS zone_crop (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  zone_id       UUID NOT NULL REFERENCES zone(id) ON DELETE CASCADE,
  crop_id       UUID NOT NULL REFERENCES crop(id) ON DELETE CASCADE,
  start_date    TIMESTAMPTZ NOT NULL DEFAULT now(),
  end_date      TIMESTAMPTZ,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  final_yield   DOUBLE PRECISION,
  area_sqm      DOUBLE PRECISION,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 1 active planting per zone
CREATE UNIQUE INDEX IF NOT EXISTS uq_zone_crop_active ON zone_crop(zone_id)
  WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS zone_crop_observation (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  zone_crop_id  UUID NOT NULL REFERENCES zone_crop(id) ON DELETE CASCADE,
  observed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  notes         TEXT,
  image_url     TEXT,
  height_cm     DOUBLE PRECISION,
  health_score  INTEGER CHECK (health_score BETWEEN 1 AND 10),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_obs_zonecrop_time ON zone_crop_observation(zone_crop_id, observed_at DESC);
```

### 4.4 Controllers & Device Tokens

```sql
CREATE TABLE IF NOT EXISTS controller (
  id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  greenhouse_id          UUID NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  label                  TEXT,                    -- renamed from 'name' to align with API.md/openapi.yml
  model                  TEXT,
  device_name            TEXT NOT NULL UNIQUE CHECK (device_name ~ '^verdify-[0-9a-f]{6}$'),
  is_climate_controller  BOOLEAN NOT NULL DEFAULT FALSE,
  fw_version             TEXT,
  hw_version             TEXT,
  last_seen              TIMESTAMPTZ,            -- track device connectivity
  created_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Constraints for data integrity and business rules
CREATE UNIQUE INDEX IF NOT EXISTS uq_greenhouse_climate_controller
  ON controller(greenhouse_id)
  WHERE is_climate_controller = TRUE;

CREATE INDEX IF NOT EXISTS idx_controller_last_seen ON controller(last_seen DESC);

-- Note: controller_token table is defined in section 2.2 Device Token Security
-- with enhanced security features (expiry, revocation tracking, etc.)
```

### 4.5 Sensors & Mappings

```sql
CREATE TABLE IF NOT EXISTS sensor (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  controller_id            UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  name                     TEXT NOT NULL,
  kind                     TEXT NOT NULL REFERENCES sensor_kind_meta(kind),
  scope                    TEXT NOT NULL CHECK (scope IN ('zone','greenhouse','external')),
  include_in_climate_loop  BOOLEAN NOT NULL DEFAULT FALSE,
  modbus_slave_id          INTEGER,
  modbus_reg               INTEGER,
  value_type               TEXT CHECK (value_type IN ('float','int')),
  scale_factor             DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  offset                   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  poll_interval_s          INTEGER NOT NULL DEFAULT 10,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sensor_controller ON sensor(controller_id);
CREATE INDEX IF NOT EXISTS idx_sensor_kind_scope ON sensor(kind, scope);

-- M:N sensor ↔ zone mapping, multi-zone allowed; unique per (sensor, zone, kind)
-- CRITICAL: Business rule enforces max 1 sensor per (zone_id, kind) for control logic
CREATE TABLE IF NOT EXISTS sensor_zone_map (
  sensor_id   UUID NOT NULL REFERENCES sensor(id) ON DELETE CASCADE,
  zone_id     UUID NOT NULL REFERENCES zone(id) ON DELETE CASCADE,
  kind        TEXT NOT NULL REFERENCES sensor_kind_meta(kind),
  PRIMARY KEY (sensor_id, zone_id, kind)
);

-- Enforce business rule: only one sensor per zone/kind combination
CREATE UNIQUE INDEX IF NOT EXISTS uq_sensor_zone_map_zone_kind
  ON sensor_zone_map(zone_id, kind);

CREATE INDEX IF NOT EXISTS idx_szm_zone ON sensor_zone_map(zone_id);
```

### 4.6 Actuators, Fan Groups, Buttons

```sql
CREATE TABLE IF NOT EXISTS actuator (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  controller_id    UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  name             TEXT NOT NULL,
  kind             TEXT NOT NULL REFERENCES actuator_kind_meta(kind),
  relay_channel    INTEGER CHECK (relay_channel IS NULL OR relay_channel > 0), -- range validation
  min_on_ms        INTEGER NOT NULL DEFAULT 60000,
  min_off_ms       INTEGER NOT NULL DEFAULT 60000,
  fail_safe_state  TEXT NOT NULL DEFAULT 'off' CHECK (fail_safe_state IN ('on','off')),
  zone_id          UUID REFERENCES zone(id) ON DELETE SET NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Ensure unique relay channels per controller (when not null)
CREATE UNIQUE INDEX IF NOT EXISTS uq_actuator_controller_channel
  ON actuator(controller_id, relay_channel)
  WHERE relay_channel IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_actuator_controller ON actuator(controller_id);
CREATE INDEX IF NOT EXISTS idx_actuator_zone ON actuator(zone_id);

CREATE TABLE IF NOT EXISTS fan_group (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  controller_id  UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  name           TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fan_group_name_per_controller
  ON fan_group(controller_id, name);

CREATE TABLE IF NOT EXISTS fan_group_member (
  fan_group_id  UUID NOT NULL REFERENCES fan_group(id) ON DELETE CASCADE,
  actuator_id   UUID NOT NULL REFERENCES actuator(id) ON DELETE CASCADE,
  PRIMARY KEY(fan_group_id, actuator_id)
);

CREATE TABLE IF NOT EXISTS controller_button (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  controller_id    UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  button_kind      button_kind_enum NOT NULL,
  target_temp_stage  INTEGER CHECK (target_temp_stage BETWEEN -3 AND 3),
  target_humi_stage  INTEGER CHECK (target_humi_stage BETWEEN -3 AND 3),
  timeout_s        INTEGER NOT NULL CHECK (timeout_s > 0),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_button_per_kind
  ON controller_button(controller_id, button_kind);
```

---

## 5. State Machine (Normalized)

```sql
CREATE TABLE IF NOT EXISTS state_machine_row (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  greenhouse_id   UUID NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  temp_stage      INTEGER,
  humi_stage      INTEGER,
  is_fallback     BOOLEAN NOT NULL DEFAULT FALSE,
  CHECK (
    (is_fallback = TRUE AND temp_stage IS NULL AND humi_stage IS NULL)
    OR
    (is_fallback = FALSE AND temp_stage BETWEEN -3 AND 3 AND humi_stage BETWEEN -3 AND 3)
  ),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_state_cell
  ON state_machine_row(greenhouse_id, temp_stage, humi_stage)
  WHERE is_fallback = FALSE;
CREATE UNIQUE INDEX IF NOT EXISTS uq_state_fallback
  ON state_machine_row(greenhouse_id)
  WHERE is_fallback = TRUE;

-- MUST ON/OFF actuator sets
CREATE TABLE IF NOT EXISTS state_machine_row_must_on (
  row_id       UUID NOT NULL REFERENCES state_machine_row(id) ON DELETE CASCADE,
  actuator_id  UUID NOT NULL REFERENCES actuator(id) ON DELETE CASCADE,
  PRIMARY KEY (row_id, actuator_id)
);
CREATE TABLE IF NOT EXISTS state_machine_row_must_off (
  row_id       UUID NOT NULL REFERENCES state_machine_row(id) ON DELETE CASCADE,
  actuator_id  UUID NOT NULL REFERENCES actuator(id) ON DELETE CASCADE,
  PRIMARY KEY (row_id, actuator_id)
);

-- Fan group staging per row
CREATE TABLE IF NOT EXISTS state_machine_row_fan_group (
  row_id        UUID NOT NULL REFERENCES state_machine_row(id) ON DELETE CASCADE,
  fan_group_id  UUID NOT NULL REFERENCES fan_group(id) ON DELETE CASCADE,
  on_count      INTEGER NOT NULL CHECK (on_count >= 0),
  PRIMARY KEY (row_id, fan_group_id)
);
```

**Coverage validation:** Use a server‑side function to assert 49 grid rows + 1 fallback (see §8.1).

---

## 6. Config Snapshots (for ETag & rollback)

```sql
CREATE TABLE IF NOT EXISTS config_snapshot (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  greenhouse_id UUID NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  version       INTEGER NOT NULL,
  payload       JSONB NOT NULL,
  etag          TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_by    UUID NULL REFERENCES app_user(id) ON DELETE SET NULL,
  UNIQUE (greenhouse_id, version)
);

-- Indexes for ETag-based config fetches and latest version queries
CREATE INDEX IF NOT EXISTS idx_config_snapshot_etag ON config_snapshot(greenhouse_id, etag);
CREATE INDEX IF NOT EXISTS idx_config_snapshot_latest ON config_snapshot(greenhouse_id, version DESC);

-- Optionally track latest version per greenhouse to accelerate ETag generation:
ALTER TABLE greenhouse
  ADD COLUMN IF NOT EXISTS latest_config_version INTEGER;

ALTER TABLE greenhouse
  ADD COLUMN IF NOT EXISTS latest_plan_version INTEGER;
```

---

## 7. Planning Tables

```sql
CREATE TABLE IF NOT EXISTS plan (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  greenhouse_id   UUID NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  version         INTEGER NOT NULL,
  effective_from  TIMESTAMPTZ NOT NULL,
  effective_to    TIMESTAMPTZ NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (greenhouse_id, version)
);
CREATE INDEX IF NOT EXISTS idx_plan_gh_time ON plan(greenhouse_id, effective_from DESC);

CREATE TABLE IF NOT EXISTS plan_setpoint (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id         UUID NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
  ts_utc          TIMESTAMPTZ NOT NULL,
  min_temp_c      DOUBLE PRECISION NOT NULL,
  max_temp_c      DOUBLE PRECISION NOT NULL,
  min_vpd_kpa     DOUBLE PRECISION NOT NULL,
  max_vpd_kpa     DOUBLE PRECISION NOT NULL,
  temp_stage_delta  INTEGER NOT NULL DEFAULT 0 CHECK (temp_stage_delta BETWEEN -1 AND 1),
  humi_stage_delta  INTEGER NOT NULL DEFAULT 0 CHECK (humi_stage_delta BETWEEN -1 AND 1),
  hyst_temp_c     DOUBLE PRECISION,
  hyst_rh_pct     DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_setpoint_plan_time ON plan_setpoint(plan_id, ts_utc);

CREATE TABLE IF NOT EXISTS plan_irrigation (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id         UUID NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
  controller_id   UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  zone_id         UUID NOT NULL REFERENCES zone(id) ON DELETE CASCADE,
  ts_utc          TIMESTAMPTZ NOT NULL,
  duration_s      INTEGER NOT NULL CHECK (duration_s > 0),
  min_soil_vwc    DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_plan_irrigation_sched ON plan_irrigation(controller_id, ts_utc);

CREATE TABLE IF NOT EXISTS plan_fertilization (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id         UUID NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
  controller_id   UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  zone_id         UUID NOT NULL REFERENCES zone(id) ON DELETE CASCADE,
  ts_utc          TIMESTAMPTZ NOT NULL,
  duration_s      INTEGER NOT NULL CHECK (duration_s > 0)
);
CREATE INDEX IF NOT EXISTS idx_plan_fert_sched ON plan_fertilization(controller_id, ts_utc);

CREATE TABLE IF NOT EXISTS plan_lighting (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id         UUID NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
  controller_id   UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  actuator_id     UUID NOT NULL REFERENCES actuator(id) ON DELETE CASCADE,
  ts_utc          TIMESTAMPTZ NOT NULL,
  duration_s      INTEGER NOT NULL CHECK (duration_s > 0)
);
CREATE INDEX IF NOT EXISTS idx_plan_lighting_sched ON plan_lighting(controller_id, ts_utc);
```

**Normalization:** Schedules are independent child tables keyed by `plan_id`; this enables per‑type analytics and lockout logic in the controller.

---

## 8. Timescale Hypertables

> **All times are UTC**; chunk interval suggestions can be tuned later.

```sql
-- 7.1 Sensor readings
CREATE TABLE IF NOT EXISTS sensor_reading (
  time           TIMESTAMPTZ NOT NULL,
  greenhouse_id  UUID NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  controller_id  UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  sensor_id      UUID NOT NULL REFERENCES sensor(id) ON DELETE CASCADE,
  kind           TEXT NOT NULL REFERENCES sensor_kind_meta(kind),
  value          DOUBLE PRECISION NOT NULL
);
SELECT create_hypertable('sensor_reading', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');

-- TimescaleDB policies for sensor_reading
SELECT add_compression_policy('sensor_reading', INTERVAL '7 days');
SELECT add_retention_policy('sensor_reading', INTERVAL '180 days');

CREATE INDEX IF NOT EXISTS idx_sr_sensor_time ON sensor_reading(sensor_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_sr_gh_time ON sensor_reading(greenhouse_id, time DESC);

-- 7.2 Actuator edge events
CREATE TABLE IF NOT EXISTS actuator_event (
  time           TIMESTAMPTZ NOT NULL,
  greenhouse_id  UUID NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  controller_id  UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  actuator_id    UUID NOT NULL REFERENCES actuator(id) ON DELETE CASCADE,
  state          BOOLEAN NOT NULL,     -- TRUE=on, FALSE=off
  reason         TEXT NOT NULL
);
SELECT create_hypertable('actuator_event', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');

-- TimescaleDB policies for actuator_event
SELECT add_compression_policy('actuator_event', INTERVAL '7 days');
SELECT add_retention_policy('actuator_event', INTERVAL '180 days');

CREATE INDEX IF NOT EXISTS idx_ae_actuator_time ON actuator_event(actuator_id, time DESC);
CREATE INDEX IF NOT EXISTS idx_ae_gh_time ON actuator_event(greenhouse_id, time DESC);

-- 7.3 Controller status frames
CREATE TABLE IF NOT EXISTS controller_status (
  time                         TIMESTAMPTZ NOT NULL,
  greenhouse_id                UUID NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  controller_id                UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  temp_stage                   INTEGER,
  humi_stage                   INTEGER,
  avg_interior_temp_c          DOUBLE PRECISION,
  avg_interior_rh_pct          DOUBLE PRECISION,
  avg_interior_pressure_hpa    DOUBLE PRECISION,
  avg_exterior_temp_c          DOUBLE PRECISION,
  avg_exterior_rh_pct          DOUBLE PRECISION,
  avg_exterior_pressure_hpa    DOUBLE PRECISION,
  avg_vpd_kpa                  DOUBLE PRECISION,
  enthalpy_in_kj_per_kg        DOUBLE PRECISION,
  enthalpy_out_kj_per_kg       DOUBLE PRECISION,
  override_active              BOOLEAN,
  plan_version                 INTEGER
);
SELECT create_hypertable('controller_status', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');

-- TimescaleDB policies for controller_status
SELECT add_compression_policy('controller_status', INTERVAL '7 days');
SELECT add_retention_policy('controller_status', INTERVAL '180 days');

CREATE INDEX IF NOT EXISTS idx_cs_controller_time ON controller_status(controller_id, time DESC);

-- 7.4 Input/button events
CREATE TABLE IF NOT EXISTS input_event (
  time           TIMESTAMPTZ NOT NULL,
  greenhouse_id  UUID NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  controller_id  UUID NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  button_kind    button_kind_enum NOT NULL,
  latched        BOOLEAN NOT NULL DEFAULT FALSE
);
SELECT create_hypertable('input_event', 'time', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');

-- TimescaleDB policies for input_event
SELECT add_compression_policy('input_event', INTERVAL '7 days');
SELECT add_retention_policy('input_event', INTERVAL '180 days');
CREATE INDEX IF NOT EXISTS idx_ie_controller_time ON input_event(controller_id, time DESC);

-- 7.5 Policies (tune as needed)
-- Enable compression after 7 days, keep 180 days (examples)
ALTER TABLE sensor_reading SET (timescaledb.compress, timescaledb.compress_segmentby = 'sensor_id');
SELECT add_compression_policy('sensor_reading', INTERVAL '7 days');
SELECT add_retention_policy('sensor_reading', INTERVAL '180 days', if_not_exists => TRUE);

ALTER TABLE actuator_event SET (timescaledb.compress, timescaledb.compress_segmentby = 'actuator_id');
SELECT add_compression_policy('actuator_event', INTERVAL '7 days');
SELECT add_retention_policy('actuator_event', INTERVAL '365 days', if_not_exists => TRUE);

ALTER TABLE controller_status SET (timescaledb.compress, timescaledb.compress_segmentby = 'controller_id');
SELECT add_compression_policy('controller_status', INTERVAL '7 days');

ALTER TABLE input_event SET (timescaledb.compress, timescaledb.compress_segmentby = 'controller_id');
SELECT add_compression_policy('input_event', INTERVAL '7 days');
```

**Indexing rationale:** Support recent‑first queries by device/greenhouse; hypertable chunking minimizes IO.

---

## 9. Validation Functions & Views

### 8.1 Validate State Machine Coverage

```sql
CREATE OR REPLACE FUNCTION fn_validate_state_machine(gh UUID)
RETURNS VOID
LANGUAGE plpgsql AS $$
DECLARE
  grid_count INT;
  fallback_count INT;
BEGIN
  SELECT COUNT(*) INTO grid_count
  FROM state_machine_row
  WHERE greenhouse_id = gh AND is_fallback = FALSE;

  SELECT COUNT(*) INTO fallback_count
  FROM state_machine_row
  WHERE greenhouse_id = gh AND is_fallback = TRUE;

  IF grid_count <> 49 THEN
    RAISE EXCEPTION 'STATE_GRID_INCOMPLETE: expected 49, found % for greenhouse %', grid_count, gh
      USING ERRCODE = '23514'; -- check_violation
  END IF;

  IF fallback_count <> 1 THEN
    RAISE EXCEPTION 'FALLBACK_INVALID: expected 1, found % for greenhouse %', fallback_count, gh
      USING ERRCODE = '23514';
  END IF;
END$$;
-- Usage (API publish step): SELECT fn_validate_state_machine('<greenhouse_id>'::uuid);
```

### 8.2 Actuator Run Segments (pair ON→OFF)

```sql
CREATE OR REPLACE VIEW actuator_run_segments AS
WITH ordered AS (
  SELECT
    actuator_id,
    greenhouse_id,
    controller_id,
    time AS start_time,
    LEAD(time) OVER (PARTITION BY actuator_id ORDER BY time) AS end_time,
    state,
    reason
  FROM actuator_event
),
on_rows AS (
  SELECT actuator_id, greenhouse_id, controller_id, start_time, end_time,
         EXTRACT(EPOCH FROM COALESCE(end_time, now()) - start_time) AS duration_s
  FROM ordered
  WHERE state = TRUE
)
SELECT * FROM on_rows;
```

### 8.3 Daily Runtime & Cycles (Continuous Aggregates)

```sql
-- Daily runtime per actuator (sum of ON durations)
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_actuator_runtime
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 day', start_time) AS bucket,
       greenhouse_id, controller_id, actuator_id,
       SUM(duration_s)::bigint AS total_on_s
FROM actuator_run_segments
GROUP BY bucket, greenhouse_id, controller_id, actuator_id;

-- Daily cycles per actuator (count ON edges)
CREATE MATERIALIZED VIEW IF NOT EXISTS daily_actuator_cycles
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 day', time) AS bucket,
       greenhouse_id, controller_id, actuator_id,
       COUNT(*) FILTER (WHERE state = TRUE) AS cycles
FROM actuator_event
GROUP BY bucket, greenhouse_id, controller_id, actuator_id;

-- Policies for refresh
SELECT add_continuous_aggregate_policy('daily_actuator_runtime',
  start_offset => INTERVAL '30 days',
  end_offset   => INTERVAL '1 hour',
  schedule_interval => INTERVAL '15 minutes');

SELECT add_continuous_aggregate_policy('daily_actuator_cycles',
  start_offset => INTERVAL '30 days',
  end_offset   => INTERVAL '1 hour',
  schedule_interval => INTERVAL '15 minutes');
```

### 8.4 Interior/Exterior Averages (for diagnostics)

```sql
CREATE OR REPLACE VIEW greenhouse_interior_exterior_avg AS
SELECT
  sr.greenhouse_id,
  time_bucket('5 minutes', sr.time) AS bucket,
  AVG(sr.value) FILTER (WHERE s.scope = 'greenhouse' AND s.kind='temperature' AND s.include_in_climate_loop) AS avg_interior_temp_c,
  AVG(sr.value) FILTER (WHERE s.scope = 'external'   AND s.kind='temperature') AS avg_exterior_temp_c,
  AVG(sr.value) FILTER (WHERE s.scope = 'greenhouse' AND s.kind='humidity' AND s.include_in_climate_loop) AS avg_interior_rh_pct,
  AVG(sr.value) FILTER (WHERE s.scope = 'external'   AND s.kind='humidity') AS avg_exterior_rh_pct
FROM sensor_reading sr
JOIN sensor s ON s.id = sr.sensor_id
GROUP BY sr.greenhouse_id, time_bucket('5 minutes', sr.time);
```

---

## 10. Sample Queries

### 9.1 Relay ON/OFF durations last 24h (one actuator)

```sql
SELECT *
FROM actuator_run_segments
WHERE actuator_id = $1::uuid
  AND start_time >= now() - INTERVAL '24 hours'
ORDER BY start_time DESC;
```

### 9.2 Daily totals & cycles (one greenhouse, week)

```sql
SELECT r.bucket, a.name AS actuator, r.total_on_s, c.cycles
FROM daily_actuator_runtime r
JOIN daily_actuator_cycles c
  ON r.bucket = c.bucket AND r.actuator_id = c.actuator_id
JOIN actuator a ON a.id = r.actuator_id
WHERE r.greenhouse_id = $1::uuid
  AND r.bucket >= date_trunc('day', now()) - INTERVAL '7 days'
ORDER BY r.bucket, actuator;
```

### 9.3 Correlate fan runtime with kWh delta (same controller/day)

```sql
WITH energy AS (
  SELECT time_bucket('1 day', sr.time) AS bucket,
         sr.controller_id,
         MAX(sr.value) - MIN(sr.value) AS kwh_delta
  FROM sensor_reading sr
  JOIN sensor s ON s.id = sr.sensor_id
  WHERE s.kind = 'kwh'
  GROUP BY bucket, sr.controller_id
)
SELECT r.bucket, r.controller_id, SUM(r.total_on_s) AS fan_on_s, e.kwh_delta
FROM daily_actuator_runtime r
JOIN actuator a ON a.id = r.actuator_id
JOIN energy e ON e.bucket = r.bucket AND e.controller_id = r.controller_id
WHERE a.kind = 'fan'
GROUP BY r.bucket, r.controller_id, e.kwh_delta
ORDER BY r.bucket DESC;
```

---

## 11. Relationships & Indexes (Summary)

* **FKs:** All child tables reference parents with `ON DELETE CASCADE` where appropriate (telemetry, mappings, planning).
* **Uniques:**

  * `zone (greenhouse_id, zone_number)`
  * `controller (device_name)` and partial unique `is_climate_controller` per greenhouse
  * `sensor_zone_map (sensor_id, zone_id, kind)`
  * `state_machine_row` unique per cell and unique fallback per greenhouse
  * `zone_crop` one active per zone (partial unique)
  * `controller_token` one active token per controller (partial unique)
* **Common indexes:**

  * By foreign key (`*_id`) and time for hypertables.
  * Name uniqueness in fan\_group per controller.

**Normalization:** All reference data (kinds) separated; state machine decomposed into row + relationship tables (3NF). JSONB limited to config snapshots and crop recipes.

---

## 12. Data Migration & Backup Strategy

### 11.1 Database Migration Management

**Initial Setup:**
* Execute DDL in clean database with `timescaledb` and `pgcrypto` extensions enabled
* Run all schema creation scripts in dependency order
* Apply initial seed data (sensor kinds, actuator types, location enums)

**Schema Evolution:**
* Use Alembic migrations for schema changes (aligned with FastAPI template)
* Version all DDL changes with descriptive migration names
* Test migrations on copy of production data before deployment
* Support both upgrade and downgrade operations for rollback capability

**Migration Commands:**
```bash
# Generate new migration
alembic revision --autogenerate -m "add_device_token_expiry"

# Apply migrations
alembic upgrade head

# Rollback to previous version
alembic downgrade -1

# Show migration history
alembic history --verbose
```

### 11.2 Backup Strategy and Procedures

**Backup Types and Schedule:**

| **Backup Type** | **Frequency** | **Retention** | **Purpose** | **Storage Location** |
|-----------------|---------------|---------------|-------------|----------------------|
| Full Logical Dump | Daily 2:00 AM | 30 days | Complete recovery, migrations | S3 + local disk |
| Incremental WAL | Continuous | 7 days | Point-in-time recovery | S3 |
| TimescaleDB Chunk | Weekly | 90 days | Efficient telemetry recovery | S3 |
| Configuration Export | On publish | 365 days | Config version tracking | Git + S3 |

**1. Full Database Backup (pg_dump)**

```bash
#!/bin/bash
# /scripts/backup_full.sh

DB_NAME="verdify"
DB_USER="postgres"
BACKUP_DIR="/var/backups/postgresql"
S3_BUCKET="verdify-backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create logical dump with all data
pg_dump \
  --host=localhost \
  --username=$DB_USER \
  --dbname=$DB_NAME \
  --format=custom \
  --compress=9 \
  --verbose \
  --file="$BACKUP_DIR/verdify_full_$TIMESTAMP.dump"

# Verify backup integrity
pg_restore --list "$BACKUP_DIR/verdify_full_$TIMESTAMP.dump" > /dev/null
if [ $? -eq 0 ]; then
  echo "Backup verification successful"

  # Upload to S3
  aws s3 cp "$BACKUP_DIR/verdify_full_$TIMESTAMP.dump" \
    "s3://$S3_BUCKET/daily/verdify_full_$TIMESTAMP.dump"

  # Cleanup local files older than 7 days
  find $BACKUP_DIR -name "verdify_full_*.dump" -mtime +7 -delete
else
  echo "Backup verification failed!" >&2
  exit 1
fi
```

**2. TimescaleDB Chunk Backup**

```bash
#!/bin/bash
# /scripts/backup_chunks.sh

# Backup compressed chunks efficiently
psql -d verdify -c "
SELECT chunk_schema, chunk_name, range_start, range_end
FROM timescaledb_information.chunks
WHERE hypertable_name IN ('telemetry_sensors', 'telemetry_actuators', 'telemetry_status')
  AND compression_status = 'Compressed'
  AND range_end < NOW() - INTERVAL '7 days'
" --csv > /tmp/chunks_to_backup.csv

# For each compressed chunk, create targeted backup
while IFS=, read -r schema chunk start_time end_time; do
  if [ "$schema" != "chunk_schema" ]; then  # Skip header
    pg_dump \
      --table="$schema.$chunk" \
      --data-only \
      --format=custom \
      --file="$BACKUP_DIR/chunk_${chunk}_$TIMESTAMP.dump" \
      verdify

    # Upload chunk backup
    aws s3 cp "$BACKUP_DIR/chunk_${chunk}_$TIMESTAMP.dump" \
      "s3://$S3_BUCKET/chunks/"
  fi
done < /tmp/chunks_to_backup.csv
```

**3. Continuous WAL Archiving**

```bash
# postgresql.conf settings
wal_level = replica
archive_mode = on
archive_command = 'aws s3 cp %p s3://verdify-backups/wal/%f'
archive_timeout = 300  # 5 minutes

# Enable point-in-time recovery
max_wal_senders = 3
wal_keep_segments = 64
```

**4. Configuration Backup**

```bash
#!/bin/bash
# /scripts/backup_configs.sh

# Export all published configurations
psql -d verdify -c "
COPY (
  SELECT
    gh.title as greenhouse_title,
    cv.version,
    cv.config_yaml,
    cv.published_at,
    cv.published_by_user_id
  FROM config_version cv
  JOIN greenhouse gh ON cv.greenhouse_id = gh.id
  WHERE cv.is_published = true
  ORDER BY gh.title, cv.version
) TO '/tmp/published_configs_$TIMESTAMP.csv'
WITH CSV HEADER;
"

# Commit to git for version control
cd /var/backups/configs
git add .
git commit -m "Config backup $TIMESTAMP"
git push origin main

# Also upload to S3
aws s3 cp "/tmp/published_configs_$TIMESTAMP.csv" \
  "s3://$S3_BUCKET/configs/"
```

### 11.3 Recovery Procedures

**1. Full Database Recovery**

```bash
#!/bin/bash
# /scripts/restore_full.sh

BACKUP_FILE="$1"
TARGET_DB="verdify_restored"

# Create new database
createdb $TARGET_DB

# Restore extensions
psql -d $TARGET_DB -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
psql -d $TARGET_DB -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"

# Restore full backup
pg_restore \
  --dbname=$TARGET_DB \
  --verbose \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  $BACKUP_FILE

echo "Database restored to $TARGET_DB"
echo "Verify data integrity before switching over"
```

**2. Point-in-Time Recovery (PITR)**

```bash
#!/bin/bash
# /scripts/restore_pitr.sh

TARGET_TIME="$1"  # e.g., "2025-08-13 17:30:00"
BASE_BACKUP_DIR="/var/backups/postgresql/base"
WAL_ARCHIVE_DIR="/var/backups/postgresql/wal"

# Stop PostgreSQL
systemctl stop postgresql

# Restore base backup
rm -rf /var/lib/postgresql/data/*
tar -xzf $BASE_BACKUP_DIR/base_backup.tar.gz -C /var/lib/postgresql/data/

# Create recovery configuration
cat > /var/lib/postgresql/data/recovery.conf << EOF
restore_command = 'cp $WAL_ARCHIVE_DIR/%f %p'
recovery_target_time = '$TARGET_TIME'
recovery_target_action = 'promote'
EOF

# Start PostgreSQL for recovery
systemctl start postgresql

echo "Point-in-time recovery initiated to $TARGET_TIME"
echo "Monitor PostgreSQL logs for completion"
```

**3. Selective Data Recovery**

```bash
#!/bin/bash
# /scripts/restore_selective.sh

# Restore specific tables from backup
BACKUP_FILE="$1"
TABLES=("greenhouse" "zone" "sensor" "actuator")

for table in "${TABLES[@]}"; do
  echo "Restoring table: $table"
  pg_restore \
    --dbname=verdify \
    --table=$table \
    --data-only \
    --verbose \
    $BACKUP_FILE
done
```

### 11.4 Disaster Recovery Planning

**Recovery Time Objectives (RTO):**
- **Critical Data Loss**: < 15 minutes (WAL recovery)
- **Full System Recovery**: < 2 hours (from daily backup)
- **Partial Data Recovery**: < 30 minutes (selective restore)

**Recovery Point Objectives (RPO):**
- **Telemetry Data**: < 5 minutes (continuous WAL)
- **Configuration Data**: < 24 hours (daily backup)
- **User Data**: < 1 hour (frequent snapshots)

**Disaster Scenarios and Responses:**

| **Scenario** | **Detection** | **Recovery Method** | **Estimated RTO** |
|--------------|---------------|--------------------|--------------------|
| Database Corruption | Health checks fail | Point-in-time recovery from WAL | 15 minutes |
| Accidental Data Deletion | User reports, monitoring alerts | Selective table restore | 30 minutes |
| Hardware Failure | Infrastructure monitoring | Full restore to new hardware | 2 hours |
| Ransomware/Security Breach | Security alerts, anomaly detection | Clean restore + security audit | 4 hours |
| Data Center Outage | Network monitoring | Failover to backup region | 1 hour |

**Testing and Validation:**
- **Weekly**: Automated backup verification and test restores
- **Monthly**: Full disaster recovery drill with RTO measurement
- **Quarterly**: Cross-region recovery testing and documentation updates

**Backup Monitoring:**
```sql
-- Monitor backup job success
CREATE VIEW backup_status AS
SELECT
  date_trunc('day', backup_time) as backup_date,
  backup_type,
  status,
  duration_minutes,
  backup_size_gb,
  verification_status
FROM backup_log
WHERE backup_time > NOW() - INTERVAL '30 days'
ORDER BY backup_time DESC;

-- Alert on backup failures
SELECT * FROM backup_status
WHERE status != 'SUCCESS'
  AND backup_date = CURRENT_DATE;
```

---

## 13. Examples (Insert/Select)

### 12.1 Seed a greenhouse, controller, sensor, actuator

```sql
-- Create user
INSERT INTO app_user(email, hashed_password) VALUES
('grower@example.com', '$2b$12$abcdef...') RETURNING id;

-- Greenhouse
INSERT INTO greenhouse(owner_id, title) VALUES
($USER_ID, 'North House') RETURNING id;

-- Controller (climate)
INSERT INTO controller(greenhouse_id, name, device_name, is_climate_controller)
VALUES ($GH_ID, 'Main Controller', 'verdify-a1b2c3', TRUE) RETURNING id;

-- Sensor (interior temp)
INSERT INTO sensor(controller_id, name, kind, scope, include_in_climate_loop)
VALUES ($CTRL_ID, 'SHT31 #1', 'temperature', 'greenhouse', TRUE) RETURNING id;

-- Actuator (fan)
INSERT INTO actuator(controller_id, name, kind, relay_channel, fail_safe_state)
VALUES ($CTRL_ID, 'Fan 1', 'fan', 1, 'off') RETURNING id;
```

### 12.2 Record telemetry

```sql
INSERT INTO sensor_reading(time, greenhouse_id, controller_id, sensor_id, kind, value)
VALUES (now(), $GH_ID, $CTRL_ID, $SENSOR_ID, 'temperature', 22.7);

INSERT INTO actuator_event(time, greenhouse_id, controller_id, actuator_id, state, reason)
VALUES (now(), $GH_ID, $CTRL_ID, $FAN_ID, TRUE, 'STATE_MACHINE:S1');
```

---

## 14. Risks & Edge Cases

* **State machine coverage** cannot be fully enforced via static constraints; use `fn_validate_state_machine` in publish pipeline.
* **Plan rows vs guard rails:** Clamping occurs in controller; optionally add application‑level validation to reject out‑of‑rail setpoints.
* **Clock skew:** Controller timestamps should be UTC; API may receive out‑of‑order rows—hypertables handle this but analytics windows must consider it.
* **Open run segments:** If `OFF` edge missing, `actuator_run_segments` truncates to `now()`. Dashboards should indicate “open” segments.

---

## 15. Implementation Guidance for Agentic Coder

**Task 1 — Create schema**

* Run the DDL in this file, in order. Verify extensions, types, meta seeds.
* Confirm all FKs and indexes exist.

**Task 2 — Timescale setup**

* Verify hypertables created with 7‑day chunks.
* Enable compression and policies (can be postponed in dev).

**Task 3 — Validation functions & views**

* Create `fn_validate_state_machine` and materialized continuous aggregates.
* Schedule policies with Timescale background jobs.

**Task 4 — Populate minimal data**

* Insert test user, greenhouse, controller (`is_climate_controller=true`), one temp/humidity sensor (interior), one fan actuator.
* Insert a minimal state machine (49 rows + fallback) and call `fn_validate_state_machine`.

**Task 5 — Contract tests**

* Write SQL tests (pgTAP or Python/pytest) to assert:

  * unique `(greenhouse_id, zone_number)`
  * climate controller singleton (second set to true fails)
  * sensor\_zone\_map uniqueness
  * state machine coverage function raises on incomplete grid
  * views produce expected aggregates for synthetic data

**Task 6 — Performance sanity**

* Load synthetic telemetry (e.g., 1M sensor readings) and run sample queries.
* Confirm index usage with `EXPLAIN (ANALYZE, BUFFERS)`.

**Task 7 — API integration**

* Map API schemas 1:1:

  * IDs as UUIDs; kinds validated via meta tables; device\_name regex enforced in `controller`.
  * Telemetry writes to hypertables; config snapshots stored in `config_snapshot`.

**Task 8 — Backup & reset scripts**

* Provide `pg_dump` scripts and a truncation/reset script for dev environments.

---

## End‑of‑Output Checklist

* [x] DDL runs top‑to‑bottom on a fresh database.
* [x] All required entities exist (users, greenhouse/zone, crops/plantings/obs, controller/token, sensor/sensor\_zone\_map, actuator/fan group/button, state machine, planning, config\_snapshot).
* [x] Timescale hypertables created with indexes and policies.
* [x] Invariants enforced via UNIQUE, CHECK, partial UNIQUE, and validation function.
* [x] Views for run segments and daily aggregates compile.
* [x] Sample queries work against seeded/sample data.
* [x] Consistent with API spec: fields, units, timestamps, device\_name regex.
# Database Schema Specification

## Overview

This document defines the complete database schema for Project Verdify, aligned with the **Full-Stack FastAPI Template** architecture. The schema uses **PostgreSQL with TimescaleDB extension**, **SQLModel for ORM**, and supports multi-tenant greenhouse automation with time-series telemetry data.

**Template Alignment**:
- **PostgreSQL** as primary database (template default)
- **TimescaleDB extension** for time-series telemetry data
- **SQLModel classes** with `table=True` for each table
- **FastAPI dependency injection** for database sessions
- **Docker Compose** configuration with `db` service name

## 1. Database Setup & Extensions

### Docker Compose Configuration
```yaml
# docker-compose.yml - PostgreSQL with TimescaleDB
services:
  db:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: verdify
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
```

### Extensions and Setup
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

### SQLModel Integration
All tables defined below have corresponding **SQLModel classes** in `backend/app/models/`:

```python
# backend/app/models/greenhouse.py
from sqlmodel import SQLModel, Field
from uuid import UUID
from datetime import datetime

class Greenhouse(SQLModel, table=True):
    id: UUID = Field(primary_key=True, default_factory=uuid4)
    title: str = Field(max_length=255)
    min_temp_c: float = Field(ge=-50, le=100)
    max_temp_c: float = Field(ge=-50, le=100)
    # ... other fields matching SQL schema below
```

**Benefits**:
- **Type safety** between API and database
- **Automatic OpenAPI schema generation**
- **Pydantic validation** on all database operations
- **IDE autocompletion** and error detection

## 2. Meta & Enums (Flexible Kinds)

### Sensor Kind Metadata

**SQL Schema:**
```sql
-- Sensor kinds + units/types (extensible; referenced by sensor.kind)
CREATE TABLE IF NOT EXISTS sensor_kind_meta (
  kind              text PRIMARY KEY,
  value_type        text NOT NULL CHECK (value_type IN ('float','int','bool','string')),
  unit              text NOT NULL,  -- SI unit symbol (e.g., '°C','%','kPa','ppm','hPa','lx','µmol/m²/s','m³/m³','L/min','L','kWh','m³','kW')
  notes             text
);
```

**SQLModel Class:**
```python
from sqlmodel import SQLModel, Field
from enum import Enum

class ValueType(str, Enum):
    FLOAT = "float"
    INT = "int"
    BOOL = "bool"
    STRING = "string"

class SensorKindMeta(SQLModel, table=True):
    __tablename__ = "sensor_kind_meta"

    kind: str = Field(primary_key=True, max_length=50)
    value_type: ValueType
    unit: str = Field(max_length=20)  # SI unit symbol
    notes: str | None = Field(default=None)
```

### Seed Data

```sql
-- Seed common kinds (add as needed)
INSERT INTO sensor_kind_meta(kind, value_type, unit, notes) VALUES
  ('temperature','float','°C','air/leaf/soil'),
  ('humidity','float','%','relative humidity'),
  ('pressure','float','hPa','barometric'),
  ('vpd','float','kPa','derived'),
  ('co2','float','ppm','ambient'),
  ('light_lux','float','lx','photometric'),
  ('ppfd','float','µmol/m²/s','PAR'),
  ('soil_moisture','float','m³/m³','volumetric water content'),
  ('water_flow','float','L/min','instantaneous'),
  ('water_total','float','L','cumulative'),
  ('power','float','kW','instantaneous'),
  ('energy_kwh','float','kWh','cumulative'),
  ('gas_volume','float','m³','cumulative'),
  ('dew_point','float','°C','derived'),
  ('absolute_humidity','float','g/m³','derived'),
  ('enthalpy','float','kJ/kg','moist air enthalpy')
ON CONFLICT (kind) DO NOTHING;

-- Actuator kinds (vent/fan/etc.)
CREATE TABLE IF NOT EXISTS actuator_kind_meta (
  kind  text PRIMARY KEY,
  notes text
);

INSERT INTO actuator_kind_meta(kind, notes) VALUES
  ('fan','ventilation'),
  ('heater','space heating'),
  ('vent','mechanical/roof vent'),
  ('humidifier','fogger/ultrasonic'),
  ('dehumidifier','desiccant/refrigerant'),
  ('irrigation_valve','zone valve'),
  ('fertilizer_valve','fertigation'),
  ('pump','circulation/transfer'),
  ('light','grow light')
ON CONFLICT (kind) DO NOTHING;

3) Core Entities
3.1 Users
CREATE TABLE IF NOT EXISTS app_user (
  id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  email           citext UNIQUE NOT NULL,
  is_active       boolean NOT NULL DEFAULT true,
  is_superuser    boolean NOT NULL DEFAULT false,
  full_name       text,
  hashed_password text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now()
);
3.2 Greenhouse, Zones, Crops
-- Greenhouse with guard rails, baselines, and planner context
CREATE TABLE IF NOT EXISTS greenhouse (
  id                   uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  owner_id             uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
  title                text NOT NULL,
  description          text,
  is_active            boolean NOT NULL DEFAULT true,
  latitude             double precision,
  longitude            double precision,

  -- Guard rails (immutable to planner)
  min_temp_c           double precision NOT NULL DEFAULT 7.0,
  max_temp_c           double precision NOT NULL DEFAULT 35.0,
  min_vpd_kpa          double precision NOT NULL DEFAULT 0.30,
  max_vpd_kpa          double precision NOT NULL DEFAULT 2.50,

  -- Baseline climate thresholds/hysteresis used if plan missing
  climate_baseline     jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- Example shape (documented elsewhere):
  -- {
  --   "temp_c": {"stage_thresholds":{"-3":..., "-2":...,"0":...,"+3":...}, "hysteresis_c": 0.5},
  --   "humi_pct": {"stage_thresholds":{...}, "hysteresis_pct": 3.0},
  --   "vpd_kpa": {"stage_thresholds":{...}, "hysteresis_kpa": 0.1}
  -- }

  -- Defaults for dehumid decisions
  site_pressure_hpa    double precision, -- optional baseline
  context_text         text,             -- narrative for planner

  created_at           timestamptz NOT NULL DEFAULT now()
);

-- Zone (1:1 with active planting; additional context for planner)
CREATE TABLE IF NOT EXISTS zone (
  id             uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  greenhouse_id  uuid NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  zone_number    integer NOT NULL,
  location       text NOT NULL CHECK (location IN ('N','NE','E','SE','S','SW','W','NW')),
  context_text   text,

  UNIQUE (greenhouse_id, zone_number)
);

-- Crop template
CREATE TABLE IF NOT EXISTS crop (
  id                        uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  name                      text NOT NULL,
  description               text,
  expected_yield_per_sqm    double precision,
  growing_days              integer,
  recipe                    jsonb, -- crop recipe/playbook
  created_at                timestamptz NOT NULL DEFAULT now()
);

-- Zone crop (instance); enforce one active per zone
CREATE TABLE IF NOT EXISTS zone_crop (
  id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  zone_id       uuid NOT NULL REFERENCES zone(id) ON DELETE CASCADE,
  crop_id       uuid NOT NULL REFERENCES crop(id) ON DELETE CASCADE,
  start_date    timestamptz NOT NULL DEFAULT now(),
  end_date      timestamptz,
  is_active     boolean NOT NULL DEFAULT true,
  final_yield   double precision,
  area_sqm      double precision,

  CONSTRAINT ck_zone_crop_dates CHECK (end_date IS NULL OR end_date >= start_date)
);

-- One active crop per zone (partial unique)
CREATE UNIQUE INDEX IF NOT EXISTS ux_zone_crop_one_active
  ON zone_crop(zone_id) WHERE is_active;

-- Observations (photos/notes/measurements)
CREATE TABLE IF NOT EXISTS zone_crop_observation (
  id             uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  zone_crop_id   uuid NOT NULL REFERENCES zone_crop(id) ON DELETE CASCADE,
  observed_at    timestamptz NOT NULL DEFAULT now(),
  notes          text,
  image_url      text,
  height_cm      double precision,
  health_score   integer CHECK (health_score BETWEEN 1 AND 10)
);
3.3 Controllers, Tokens, Buttons
-- Controller identity; exactly one climate controller per greenhouse (MVP)
CREATE TABLE IF NOT EXISTS controller (
  id                     uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  greenhouse_id          uuid NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  name                   text NOT NULL,          -- friendly name
  model                  text,                   -- Kincony A16S etc.
  device_name            text UNIQUE,            -- verdify-aabbcc (claim)
  firmware               text,
  hardware_profile       text,                   -- e.g., kincony_a16s
  is_climate_controller  boolean NOT NULL DEFAULT false,
  created_at             timestamptz NOT NULL DEFAULT now()
);

-- Only one climate controller per greenhouse
CREATE UNIQUE INDEX IF NOT EXISTS ux_one_climate_controller
  ON controller(greenhouse_id)
  WHERE is_climate_controller;

-- Device tokens (hashed)
CREATE TABLE IF NOT EXISTS device_token (
  id               uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  controller_id    uuid NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  token_hash       text NOT NULL,
  last4            text,
  created_at       timestamptz NOT NULL DEFAULT now(),
  revoked_at       timestamptz,
  CONSTRAINT ux_one_active_token UNIQUE (controller_id, revoked_at)
    DEFERRABLE INITIALLY IMMEDIATE
);

-- Optional claim ticket for onboarding (device_name + code)
CREATE TABLE IF NOT EXISTS claim_ticket (
  device_name      text PRIMARY KEY,
  claim_code_hash  text NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  expires_at       timestamptz
);

-- Physical override buttons
CREATE TABLE IF NOT EXISTS controller_button (
  id                uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  controller_id     uuid NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  button_type       text NOT NULL CHECK (button_type IN ('cool','humid','heat')),
  analog_channel    integer NOT NULL,  -- hardware input index
  temp_stage        smallint,          -- -3..+3 when button_type='cool' or 'heat'
  humi_stage        smallint,          -- -3..+3 when button_type='humid'
  timeout_s         integer NOT NULL DEFAULT 600,
  UNIQUE (controller_id, analog_channel),
  CHECK (temp_stage IS NULL OR temp_stage BETWEEN -3 AND 3),
  CHECK (humi_stage IS NULL OR humi_stage BETWEEN -3 AND 3)
);
3.4 Sensors and Zone Mapping (multi zone)
-- Sensors exist at different scopes; a sensor MAY be used by multiple zones
CREATE TABLE IF NOT EXISTS sensor (
  id                      uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  controller_id           uuid NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  name                    text NOT NULL,
  kind                    text NOT NULL REFERENCES sensor_kind_meta(kind),
  scope                   text NOT NULL CHECK (scope IN ('zone','greenhouse','external')),
  include_in_climate_loop boolean NOT NULL DEFAULT false, -- only valid for scope in ('zone','greenhouse')

  -- hardware/config
  model                   text,
  poll_interval_s         integer DEFAULT 10,
  modbus_slave_id         integer,
  modbus_reg              integer,
  scale_factor            double precision DEFAULT 1.0,
  offset                  double precision DEFAULT 0.0,

  created_at              timestamptz NOT NULL DEFAULT now()
);

-- Map sensors to zones (many-to-many). Enforce one temperature/humidity/soil_moisture per zone.
CREATE TABLE IF NOT EXISTS sensor_zone_map (
  sensor_id   uuid NOT NULL REFERENCES sensor(id) ON DELETE CASCADE,
  zone_id     uuid NOT NULL REFERENCES zone(id) ON DELETE CASCADE,
  kind        text NOT NULL,  -- duplicated for enforcement
  PRIMARY KEY (sensor_id, zone_id),

  -- Kind must match sensor.kind (enforced via trigger)
  CHECK (kind <> '')
);

-- Enforce at most ONE {temperature, humidity, soil_moisture} per zone
CREATE UNIQUE INDEX IF NOT EXISTS ux_zone_one_sensor_per_kind
  ON sensor_zone_map(zone_id, kind)
  WHERE kind IN ('temperature','humidity','soil_moisture');
Trigger to validate sensor_zone_map.kind and scope
CREATE OR REPLACE FUNCTION trg_sensor_zone_map_validate() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE s RECORD;
BEGIN
  SELECT kind, scope INTO s FROM sensor WHERE id = NEW.sensor_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'sensor not found';
  END IF;
  IF s.kind <> NEW.kind THEN
    RAISE EXCEPTION 'mapping.kind % must equal sensor.kind %', NEW.kind, s.kind;
  END IF;
  IF s.scope <> 'zone' THEN
    RAISE EXCEPTION 'only sensors with scope=zone can be mapped to zones (scope was %)', s.scope;
  END IF;
  RETURN NEW;
END$$;

DROP TRIGGER IF EXISTS sensor_zone_map_validate ON sensor_zone_map;
CREATE TRIGGER sensor_zone_map_validate
  BEFORE INSERT OR UPDATE ON sensor_zone_map
  FOR EACH ROW EXECUTE FUNCTION trg_sensor_zone_map_validate();
3.5 Actuators, Fan Groups
-- Equipment -> Actuator
CREATE TABLE IF NOT EXISTS actuator (
  id              uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  controller_id   uuid NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  name            text NOT NULL,
  kind            text NOT NULL REFERENCES actuator_kind_meta(kind),
  relay_channel   integer,           -- board channel
  min_on_ms       integer NOT NULL DEFAULT 60000,
  min_off_ms      integer NOT NULL DEFAULT 60000,
  fail_safe_state text NOT NULL DEFAULT 'off' CHECK (fail_safe_state IN ('on','off')),
  zone_id         uuid REFERENCES zone(id) ON DELETE SET NULL,  -- nullable (e.g., climate actuators)

  status          boolean, -- transient cache if needed
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- Fan grouping for rotation/staging
CREATE TABLE IF NOT EXISTS fan_group (
  id             uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  controller_id  uuid NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  name           text NOT NULL
);

CREATE TABLE IF NOT EXISTS fan_group_member (
  fan_group_id   uuid NOT NULL REFERENCES fan_group(id) ON DELETE CASCADE,
  actuator_id    uuid NOT NULL REFERENCES actuator(id) ON DELETE CASCADE,
  PRIMARY KEY (fan_group_id, actuator_id)
);
3.6 State Machine (declarative rules)
-- One row per (temp_stage, humi_stage) intersection (both -3..+3)
CREATE TABLE IF NOT EXISTS state_machine_row (
  id                 uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  greenhouse_id      uuid NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  temp_stage         smallint NOT NULL CHECK (temp_stage BETWEEN -3 AND 3),
  humi_stage         smallint NOT NULL CHECK (humi_stage BETWEEN -3 AND 3),
  is_fallback        boolean NOT NULL DEFAULT false,

  must_on_actuators  uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],
  must_off_actuators uuid[] NOT NULL DEFAULT ARRAY[]::uuid[],

  -- Optional default fan staging if no explicit group rule present
  default_fan_on_count integer,  -- e.g., 1 for S1, 2 for S2

  UNIQUE (greenhouse_id, temp_stage, humi_stage),
  -- Enforce exactly one fallback row per greenhouse
  UNIQUE (greenhouse_id) WHERE is_fallback = true
);

-- Optional per-row fan group rule (to support multiple groups)
CREATE TABLE IF NOT EXISTS state_machine_fan_rule (
  state_row_id   uuid NOT NULL REFERENCES state_machine_row(id) ON DELETE CASCADE,
  fan_group_id   uuid NOT NULL REFERENCES fan_group(id) ON DELETE CASCADE,
  on_count       integer NOT NULL CHECK (on_count >= 0),
  PRIMARY KEY (state_row_id, fan_group_id)
);
3.7 Plans (setpoints & schedules)
-- Plan header
CREATE TABLE IF NOT EXISTS plan (
  id               uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  greenhouse_id    uuid NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  version          integer NOT NULL,
  effective_from   timestamptz NOT NULL,
  effective_to     timestamptz NOT NULL,
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (greenhouse_id, version)
);

-- Time-stepped climate setpoints + biases/offsets/hysteresis
CREATE TABLE IF NOT EXISTS plan_setpoint (
  id                 uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  plan_id            uuid NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
  ts                 timestamptz NOT NULL,
  min_temp_c         double precision,
  max_temp_c         double precision,
  min_vpd_kpa        double precision,
  max_vpd_kpa        double precision,
  temp_delta_c       double precision,  -- bias vs baseline
  humi_delta_pct     double precision,
  vpd_delta_kpa      double precision,
  temp_hysteresis_c  double precision,
  humi_hysteresis_pct double precision,
  vpd_hysteresis_kpa double precision,
  stage_offset_temp  smallint,  -- -3..+3 offset
  stage_offset_humi  smallint,
  UNIQUE (plan_id, ts)
);

-- Irrigation schedule (per zone)
CREATE TABLE IF NOT EXISTS plan_irrigation (
  id               uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  plan_id          uuid NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
  zone_id          uuid NOT NULL REFERENCES zone(id) ON DELETE CASCADE,
  ts               timestamptz NOT NULL,
  duration_s       integer NOT NULL CHECK (duration_s > 0),
  fertilizer       boolean NOT NULL DEFAULT false,
  min_soil_vwc     double precision, -- optional threshold
  UNIQUE (plan_id, zone_id, ts)
);

-- (Optional) Dedicated fertilization entries
CREATE TABLE IF NOT EXISTS plan_fertilization (
  id               uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  plan_id          uuid NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
  zone_id          uuid NOT NULL REFERENCES zone(id) ON DELETE CASCADE,
  ts               timestamptz NOT NULL,
  duration_s       integer NOT NULL CHECK (duration_s > 0),
  UNIQUE (plan_id, zone_id, ts)
);

-- Lighting schedule (per actuator, e.g., grow light relay)
CREATE TABLE IF NOT EXISTS plan_lighting (
  id               uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  plan_id          uuid NOT NULL REFERENCES plan(id) ON DELETE CASCADE,
  actuator_id      uuid NOT NULL REFERENCES actuator(id) ON DELETE CASCADE,
  ts               timestamptz NOT NULL,
  duration_s       integer NOT NULL CHECK (duration_s > 0),
  UNIQUE (plan_id, actuator_id, ts)
);

4) Telemetry (Timescale Hypertables)
Hypertables use time as the partitioning column. Add compression/retention policies as needed.
-- Sensor readings
CREATE TABLE IF NOT EXISTS sensor_reading (
  time            timestamptz NOT NULL,
  greenhouse_id   uuid NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  controller_id   uuid NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  sensor_id       uuid NOT NULL REFERENCES sensor(id) ON DELETE CASCADE,
  kind            text NOT NULL REFERENCES sensor_kind_meta(kind),
  scope           text NOT NULL CHECK (scope IN ('zone','greenhouse','external')),
  zone_id         uuid REFERENCES zone(id) ON DELETE SET NULL,
  value           double precision NOT NULL,
  unit            text NOT NULL,   -- copy from meta at ingest time
  PRIMARY KEY (time, sensor_id)
);
SELECT create_hypertable('sensor_reading','time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS ix_sr_by_greenhouse_time ON sensor_reading(greenhouse_id, time DESC);
CREATE INDEX IF NOT EXISTS ix_sr_by_zone_time ON sensor_reading(zone_id, time DESC);

-- Actuator on/off events
CREATE TABLE IF NOT EXISTS actuator_event (
  time            timestamptz NOT NULL,
  greenhouse_id   uuid NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  controller_id   uuid NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  actuator_id     uuid NOT NULL REFERENCES actuator(id) ON DELETE CASCADE,
  state           boolean NOT NULL,       -- true=ON, false=OFF
  reason          text NOT NULL,          -- state machine, manual, failsafe
  PRIMARY KEY (time, actuator_id)
);
SELECT create_hypertable('actuator_event','time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS ix_ae_by_actuator_time ON actuator_event(actuator_id, time DESC);
CREATE INDEX IF NOT EXISTS ix_ae_by_greenhouse_time ON actuator_event(greenhouse_id, time DESC);

-- Controller status snapshots (loop runtime + computed aggregates)
CREATE TABLE IF NOT EXISTS controller_status (
  time                 timestamptz NOT NULL,
  greenhouse_id        uuid NOT NULL REFERENCES greenhouse(id) ON DELETE CASCADE,
  controller_id        uuid NOT NULL REFERENCES controller(id) ON DELETE CASCADE,

  avg_in_temp_c        double precision,
  avg_in_rh_pct        double precision,
  avg_in_pressure_hpa  double precision,
  avg_vpd_kpa          double precision,
  enth_kj_per_kg       double precision,

  ext_temp_c           double precision,
  ext_rh_pct           double precision,
  ext_pressure_hpa     double precision,

  temp_stage           smallint,
  humi_stage           smallint,
  plan_version         integer,
  config_version       integer,
  loop_ms              integer,

  PRIMARY KEY (time, controller_id)
);
SELECT create_hypertable('controller_status','time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS ix_cs_by_controller_time ON controller_status(controller_id, time DESC);

-- Manual input events (button presses/overrides)
CREATE TABLE IF NOT EXISTS input_event (
  time            timestamptz NOT NULL,
  controller_id   uuid NOT NULL REFERENCES controller(id) ON DELETE CASCADE,
  button_id       uuid REFERENCES controller_button(id) ON DELETE SET NULL,
  button_type     text NOT NULL CHECK (button_type IN ('cool','humid','heat')),
  temp_stage      smallint,
  humi_stage      smallint,
  timeout_s       integer,
  PRIMARY KEY (time, controller_id, button_type)
);
SELECT create_hypertable('input_event','time', if_not_exists => TRUE);

## 4. Audit Logging

```sql
-- Audit trail for configuration changes
CREATE TABLE IF NOT EXISTS audit_log (
  id            uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
  table_name    text NOT NULL,
  operation     text NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
  old_row       jsonb,
  new_row       jsonb,
  user_id       uuid REFERENCES users(id) ON DELETE SET NULL,
  ts_utc        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_audit_log_table_time ON audit_log(table_name, ts_utc DESC);
CREATE INDEX IF NOT EXISTS ix_audit_log_user_time ON audit_log(user_id, ts_utc DESC);

-- Example trigger for greenhouse changes
CREATE OR REPLACE FUNCTION trg_audit_greenhouse()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO audit_log(table_name, operation, old_row, new_row, user_id)
  VALUES (
    'greenhouse',
    TG_OP,
    CASE WHEN TG_OP = 'DELETE' THEN to_jsonb(OLD) ELSE NULL END,
    CASE WHEN TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN to_jsonb(NEW) ELSE NULL END,
    current_setting('app.current_user_id', true)::uuid
  );
  RETURN COALESCE(NEW, OLD);
END$$;

CREATE TRIGGER tg_audit_greenhouse
  AFTER INSERT OR UPDATE OR DELETE ON greenhouse
  FOR EACH ROW EXECUTE FUNCTION trg_audit_greenhouse();
```

Optional compression & retention policies (example):
-- Compress older than 7 days; keep 180 days
SELECT add_compression_policy('sensor_reading', INTERVAL '7 days');
SELECT add_compression_policy('actuator_event', INTERVAL '7 days');
SELECT add_compression_policy('controller_status', INTERVAL '7 days');

SELECT add_retention_policy('sensor_reading', INTERVAL '180 days');
SELECT add_retention_policy('actuator_event', INTERVAL '180 days');
SELECT add_retention_policy('controller_status', INTERVAL '180 days');

5) Derived Views & Continuous Aggregates
5.1 Run segments from on/off events (per actuator)
-- Segments end on OFF events; duration from previous ON
CREATE OR REPLACE VIEW vw_actuator_run_segments AS
WITH ordered AS (
  SELECT
    greenhouse_id,
    controller_id,
    actuator_id,
    time,
    state,
    reason,
    LAG(state) OVER (PARTITION BY actuator_id ORDER BY time) AS prev_state,
    LAG(time)  OVER (PARTITION BY actuator_id ORDER BY time) AS prev_time
  FROM actuator_event
),
segments AS (
  SELECT
    greenhouse_id,
    controller_id,
    actuator_id,
    prev_time AS started_at,
    time      AS ended_at,
    EXTRACT(EPOCH FROM (time - prev_time))::bigint AS duration_s
  FROM ordered
  WHERE state = false AND prev_state = true AND prev_time IS NOT NULL
)
SELECT * FROM segments;
5.2 Daily totals (continuous aggregate)
CREATE MATERIALIZED VIEW IF NOT EXISTS cagg_daily_actuator_on_seconds
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('1 day', ended_at) AS day,
  actuator_id,
  SUM(duration_s)::bigint AS on_seconds
FROM vw_actuator_run_segments
GROUP BY 1, 2
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
  'cagg_daily_actuator_on_seconds',
  start_offset => INTERVAL '7 days',
  end_offset   => INTERVAL '1 hour',
  schedule_interval => INTERVAL '15 minutes'
);

## 6) Validation Functions & Triggers {#algorithms-functions}

### 6.1 Climate Calculation Functions

**VPD Calculation (Vapor Pressure Deficit)**
```python
def calc_vpd_kpa(temp_c, rh_pct):
    """Calculate VPD in kPa from temperature (°C) and relative humidity (%)"""
    es = 0.6108 * exp((17.27 * temp_c) / (temp_c + 237.3))  # Saturation vapor pressure (kPa)
    ea = es * (rh_pct / 100.0)  # Actual vapor pressure
    return max(0.0, es - ea)
```

**Enthalpy Calculation (Moist Air)**
```python
def calc_enthalpy_kjkg(temp_c, rh_pct, pressure_hpa):
    """Calculate moist air specific enthalpy (kJ/kg) using psychrometric approximation"""
    p_kpa = pressure_hpa / 10.0
    es = 0.6108 * exp((17.27 * temp_c) / (temp_c + 237.3))
    phi = rh_pct / 100.0
    pv = phi * es
    w = 0.62198 * pv / max(0.001, (p_kpa - pv))  # Humidity ratio (kg water/kg dry air)
    return 1.006*temp_c + w*(2501 + 1.86*temp_c)
```

**Stage Determination Algorithms**
```python
def stage_for_temp(temp_c, eff_min, eff_max, hyst):
    """Determine temperature stage [-3..+3] with hysteresis"""
    if temp_c < eff_min - 3*hyst: return -3
    if temp_c < eff_min - 2*hyst: return -2
    if temp_c < eff_min - 1*hyst: return -1
    if temp_c > eff_max + 3*hyst: return 3
    if temp_c > eff_max + 2*hyst: return 2
    if temp_c > eff_max + 1*hyst: return 1
    return 0

def stage_for_humi(vpd_kpa, eff_min_vpd, eff_max_vpd, hyst_vpd):
    """Determine humidity stage [-3..+3] based on VPD with hysteresis"""
    # Negative = dehumidification demand (air too humid / VPD below band)
    # Positive = humidification demand (air too dry / VPD above band)
    if vpd_kpa < eff_min_vpd - 3*hyst_vpd: return -3
    if vpd_kpa < eff_min_vpd - 2*hyst_vpd: return -2
    if vpd_kpa < eff_min_vpd - 1*hyst_vpd: return -1
    if vpd_kpa > eff_max_vpd + 3*hyst_vpd: return 3
    if vpd_kpa > eff_max_vpd + 2*hyst_vpd: return 2
    if vpd_kpa > eff_max_vpd + 1*hyst_vpd: return 1
    return 0
```

**Plan Staleness Check**
```python
def is_plan_stale(plan_end_time, current_time, grace_period_hours=24):
    """Check if plan has expired beyond grace period"""
    grace_period = timedelta(hours=grace_period_hours)
    return current_time > (plan_end_time + grace_period)
```

**Planning Guard Rail Clamping**
```python
def clamp(x, lo, hi):
    """Clamp value to range [lo, hi]"""
    return max(lo, min(hi, x))

def parse_and_clamp(llm_json, rails):
    """Parse LLM output and clamp setpoints to guard rails"""
    obj = validate_against_schema(llm_json)

    # Clamp setpoints to guard rails
    for sp in obj["setpoints"]:
        sp["temp_min_c"]  = clamp(sp["temp_min_c"],  rails.min_temp_c,  rails.max_temp_c)
        sp["temp_max_c"]  = clamp(sp["temp_max_c"],  rails.min_temp_c,  rails.max_temp_c)
        sp["vpd_min_kpa"] = clamp(sp["vpd_min_kpa"], rails.min_vpd_kpa, rails.max_vpd_kpa)
        sp["vpd_max_kpa"] = clamp(sp["vpd_max_kpa"], rails.min_vpd_kpa, rails.max_vpd_kpa)
        assert sp["temp_min_c"] <= sp["temp_max_c"]
        assert sp["vpd_min_kpa"] <= sp["vpd_max_kpa"]

    return obj
```

**Configuration Build Pipeline**
```python
def build_greenhouse_config(greenhouse_id: UUID) -> dict:
    """Build canonical configuration JSON from database with deterministic ETag"""
    gh = load_greenhouse(greenhouse_id)
    controllers = load_controllers(gh.id)
    sensors = load_sensors_for(controllers)
    actuators = load_actuators_for(controllers)
    fan_groups = load_fan_groups_for(controllers)
    buttons = load_buttons_for(controllers)
    state_rows = load_state_rows(gh.id)

    # Sort for deterministic output
    controllers.sort(key=lambda c: c["device_name"])
    sensors.sort(key=lambda s: s["id"])
    actuators.sort(key=lambda a: a["id"])
    fan_groups.sort(key=lambda g: g["id"])
    buttons.sort(key=lambda b: b["id"])
    state_rows.sort(key=lambda r: (r["temp_stage"], r["humi_stage"]))

    cfg = {
        "version": next_version(greenhouse_id),
        "generated_at": now_iso_utc(),
        "greenhouse": serialize_greenhouse(gh),
        "baselines": build_baselines(gh),
        "rails": extract_guard_rails(gh),
        "controllers": [serialize_controller(c) for c in controllers],
        "sensors": [serialize_sensor(s) for s in sensors],
        "actuators": [serialize_actuator(a) for a in actuators],
        "fan_groups": [serialize_fan_group(fg) for fg in fan_groups],
        "buttons": [serialize_button(b) for b in buttons],
        "state_rules": {
            "grid": [serialize_state_row(r) for r in state_rows if not r.is_fallback],
            "fallback": serialize_state_row(next(r for r in state_rows if r.is_fallback))
        }
    }

    # Canonical JSON + ETag (excluding volatile fields)
    canonical_bytes = json.dumps(cfg, sort_keys=True, separators=(',', ':')).encode('utf-8')
    etag = sha256_hex(canonical_bytes)
    store_snapshot(greenhouse_id, cfg["version"], etag, cfg)
    return cfg, etag
```

### 6.2 Database Validation Functions

**Plan Setpoint Clamping (Server-side Safety)**
CREATE OR REPLACE FUNCTION fn_clamp_setpoints_to_rails(p_plan_id uuid)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  gh_id uuid;
  rails RECORD;
BEGIN
  SELECT greenhouse_id INTO gh_id FROM plan WHERE id = p_plan_id;
  IF gh_id IS NULL THEN RAISE EXCEPTION 'plan % not found', p_plan_id; END IF;

  SELECT min_temp_c, max_temp_c, min_vpd_kpa, max_vpd_kpa
    INTO rails
  FROM greenhouse WHERE id = gh_id;

  UPDATE plan_setpoint
    SET min_temp_c = GREATEST(min_temp_c, rails.min_temp_c),
        max_temp_c = LEAST(max_temp_c, rails.max_temp_c),
        min_vpd_kpa = GREATEST(min_vpd_kpa, rails.min_vpd_kpa),
        max_vpd_kpa = LEAST(max_vpd_kpa, rails.max_vpd_kpa)
  WHERE plan_id = p_plan_id;
END$$;
**State Coverage Validation (49 Grid Rows + 1 Fallback)**
-- Lists missing (temp_stage, humi_stage) pairs for each greenhouse
CREATE OR REPLACE VIEW vw_missing_state_rows AS
WITH stages AS (
  SELECT gs.greenhouse_id, t.s AS temp_stage, h.s AS humi_stage
  FROM (SELECT DISTINCT greenhouse_id FROM state_machine_row) gs,
       generate_series(-3,3) t(s),
       generate_series(-3,3) h(s)
),
present AS (
  SELECT greenhouse_id, temp_stage, humi_stage FROM state_machine_row
)
SELECT s.greenhouse_id, s.temp_stage, s.humi_stage
FROM stages s
LEFT JOIN present p
  ON p.greenhouse_id = s.greenhouse_id
 AND p.temp_stage = s.temp_stage
 AND p.humi_stage = s.humi_stage
WHERE p.greenhouse_id IS NULL;

-- Agentic enforcement: CI should fail if SELECT COUNT(*) FROM vw_missing_state_rows > 0

### 6.3 Telemetry Analytics Queries

**Daily Runtime Reports**
```sql
-- Daily actuator runtime (minutes) per device
SELECT
  DATE(time) as date,
  actuator_id,
  SUM(CASE WHEN state = 'ON' THEN 1 ELSE 0 END) as on_minutes
FROM actuator_event
WHERE time >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(time), actuator_id
ORDER BY date DESC, actuator_id;

-- Daily cycle counts per fan group
SELECT
  DATE(ae.time) as date,
  fg.name as fan_group,
  COUNT(*) as cycle_count
FROM actuator_event ae
JOIN actuator a ON ae.actuator_id = a.id
JOIN fan_group_member fgm ON a.id = fgm.actuator_id
JOIN fan_group fg ON fgm.fan_group_id = fg.id
WHERE ae.new_state = 'ON'
  AND ae.time >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(ae.time), fg.id, fg.name
ORDER BY date DESC, fan_group;

-- Temperature/VPD compliance analysis
SELECT
  DATE(sr.time) as date,
  AVG(sr.value) as avg_temp_c,
  COUNT(CASE WHEN sr.value < gh.min_temp_c OR sr.value > gh.max_temp_c THEN 1 END) as out_of_range_readings,
  COUNT(*) as total_readings
FROM sensor_reading sr
JOIN sensor s ON sr.entity_id = s.id
JOIN controller c ON s.controller_id = c.id
JOIN greenhouse gh ON c.greenhouse_id = gh.id
WHERE s.kind = 'temperature'
  AND s.include_in_climate_loop = true
  AND sr.time >= CURRENT_DATE - INTERVAL '7 days'
GROUP BY DATE(sr.time), gh.id, gh.min_temp_c, gh.max_temp_c
ORDER BY date DESC;
```

7) Indices & Performance Notes
-	Foreign key access paths: indexes on all FK columns (*_id) created implicitly via queries above; add more as needed.
-	Telemetry queries: sensor_reading and actuator_event indexed by (entity_id, time DESC).
-	Planning joins: indexes on plan(version, greenhouse_id) and plan_setpoint(plan_id, ts) already ensured via UNIQUE.

8) Mapping to models.py (Non breaking Extensions)
-	Greenhouse: added guard rails (min_*, max_*), climate_baseline (JSONB), context_text, optional site_pressure_hpa.
-	Zone: added context_text.
-	Controller: added device_name, firmware, hardware_profile, is_climate_controller (+ unique partial index).
-	Sensor: replaces narrow enum with kind FK → sensor_kind_meta; adds scope, include_in_climate_loop, poll/scale/offset; moved zone association to sensor_zone_map (many to many).
-	Actuator: replaces equipment; adds kind, timing constraints, fail_safe_state, optional zone_id.
-	Fan groups: new fan_group and fan_group_member.
-	Buttons: new controller_button.
-	State machine: state_machine_row + optional state_machine_fan_rule.
-	Plans: plan, plan_setpoint, plan_irrigation, plan_fertilization, plan_lighting.
-	Telemetry: Timescale hypertables (sensor_reading, actuator_event, controller_status, input_event).
-	Auth: device_token, claim_ticket.
Note: Existing SensorType enum in code should be replaced with a string constrained by sensor_kind_meta(kind). API validation MUST reject unknown kinds.

## 9) Additional Integrity Constraints (Business Rules) {#validation-functions-triggers}

> **Validation Reference**: For complete validation rules and business invariants, see [Business Invariants in OVERVIEW.md](./OVERVIEW.md#business-invariants).

**Database-enforced constraints:**

- **Climate singleton**: `ux_one_climate_controller` partial unique index ensures exactly one per greenhouse
- **Active plantings**: `ux_zone_crop_one_active` partial unique index ensures one active crop per zone
- **Zone sensor mapping**: `ux_zone_one_sensor_per_kind` partial unique index on `sensor_zone_map`
- **Zone scope validation**: `trg_sensor_zone_map_validate` trigger ensures only zone-scoped sensors have mappings
- **Plan clamping**: `fn_clamp_setpoints_to_rails(plan_id)` enforces guard rail compliance
- **State coverage**: `vw_missing_state_rows` validates 49 grid rows + 1 fallback requirement

## 10. SQLModel Integration (FastAPI Template Alignment)

### 10.1 Overview

SQLModel provides a unified approach to define database models and API schemas, ensuring type safety and consistency between the database layer and API endpoints. Each table is represented by a SQLModel class with `table=True`, and corresponding Pydantic schemas are generated automatically for API serialization.

### 10.2 Core Model Patterns

**Base Configuration:**
```python
from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum

class ValueType(str, Enum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    PRESSURE = "pressure"
    VPD = "vpd"
    CO2 = "co2"
    LIGHT_LUX = "light_lux"
    PPFD = "ppfd"
    SOIL_MOISTURE = "soil_moisture"
    WATER_FLOW = "water_flow"
    WATER_TOTAL = "water_total"
    POWER = "power"
    ENERGY_KWH = "energy_kwh"
    GAS_VOLUME = "gas_volume"
    DEW_POINT = "dew_point"
    ABSOLUTE_HUMIDITY = "absolute_humidity"
    ENTHALPY = "enthalpy"
```

### 10.3 Table Models

**Greenhouse Model:**
```python
class Greenhouse(SQLModel, table=True):
    __tablename__ = "greenhouse"

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    title: str = Field(max_length=100)
    min_temp_c: float = Field(ge=-50, le=100)
    max_temp_c: float = Field(ge=-50, le=100)
    min_vpd_kpa: float = Field(ge=0, le=10)
    max_vpd_kpa: float = Field(ge=0, le=10)
    enthalpy_open_kjkg: float
    enthalpy_close_kjkg: float
    site_pressure_hpa: float = Field(ge=500, le=1200)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    controllers: List["Controller"] = Relationship(back_populates="greenhouse")
    zones: List["Zone"] = Relationship(back_populates="greenhouse")
    crops: List["Crop"] = Relationship(back_populates="greenhouse")
```

**Controller Model:**
```python
class Controller(SQLModel, table=True):
    __tablename__ = "controller"

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    greenhouse_id: UUID = Field(foreign_key="greenhouse.id")
    device_name: str = Field(max_length=50, regex=r"^verdify-[0-9a-f]{6}$")
    label: Optional[str] = Field(default=None, max_length=100)
    is_climate_controller: bool = Field(default=False)
    device_token_hash: Optional[str] = Field(default=None, max_length=255)
    fw_version: Optional[str] = Field(default=None, max_length=50)
    hw_version: Optional[str] = Field(default=None, max_length=50)
    claim_code: Optional[str] = Field(default=None, max_length=6, regex=r"^\d{6}$")
    claimed_at: Optional[datetime] = Field(default=None)
    last_seen: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    greenhouse: Greenhouse = Relationship(back_populates="controllers")
    sensors: List["Sensor"] = Relationship(back_populates="controller")
    actuators: List["Actuator"] = Relationship(back_populates="controller")
```

**Sensor Model:**
```python
class Sensor(SQLModel, table=True):
    __tablename__ = "sensor"

    id: UUID = Field(primary_key=True, default_factory=uuid4)
    controller_id: UUID = Field(foreign_key="controller.id")
    greenhouse_id: UUID = Field(foreign_key="greenhouse.id")
    kind: str = Field(foreign_key="sensor_kind_meta.kind", max_length=50)
    scope: str = Field(max_length=20)  # zone, greenhouse, external
    zone_id: Optional[UUID] = Field(default=None, foreign_key="zone.id")
    modbus_addr: Optional[int] = Field(default=None, ge=1, le=247)
    modbus_register: Optional[int] = Field(default=None, ge=0, le=65535)
    scale_factor: float = Field(default=1.0)
    offset: float = Field(default=0.0)
    poll_interval_s: int = Field(default=10, ge=1, le=3600)
    include_in_climate_loop: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    controller: Controller = Relationship(back_populates="sensors")
    greenhouse: Greenhouse = Relationship()
    zone: Optional["Zone"] = Relationship(back_populates="sensors")
    kind_meta: "SensorKindMeta" = Relationship()
```

### 10.4 API Schema Generation

SQLModel automatically generates Pydantic schemas for API endpoints:

```python
# Read schemas (for responses)
class GreenhouseRead(GreenhouseBase):
    id: UUID
    created_at: datetime

# Create schemas (for requests)
class GreenhouseCreate(GreenhouseBase):
    pass

# Update schemas (for PATCH requests)
class GreenhouseUpdate(GreenhouseBase):
    title: Optional[str] = None
    min_temp_c: Optional[float] = None
    max_temp_c: Optional[float] = None
    # ... other optional fields
```

### 10.5 Database Operations with Type Safety

```python
from sqlmodel import Session, select
from app.core.db import engine

def get_greenhouse(greenhouse_id: UUID) -> Optional[Greenhouse]:
    with Session(engine) as session:
        statement = select(Greenhouse).where(Greenhouse.id == greenhouse_id)
        return session.exec(statement).first()

def create_greenhouse(greenhouse_data: GreenhouseCreate) -> Greenhouse:
    with Session(engine) as session:
        greenhouse = Greenhouse.model_validate(greenhouse_data)
        session.add(greenhouse)
        session.commit()
        session.refresh(greenhouse)
        return greenhouse
```

### 10.6 FastAPI Integration

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from app.core.db import get_db

router = APIRouter(prefix="/api/v1/greenhouses", tags=["greenhouses"])

@router.get("/{greenhouse_id}", response_model=GreenhouseRead)
def get_greenhouse(
    greenhouse_id: UUID,
    db: Session = Depends(get_db)
) -> Greenhouse:
    greenhouse = get_greenhouse(greenhouse_id)
    if not greenhouse:
        raise HTTPException(status_code=404, detail="Greenhouse not found")
    return greenhouse

@router.post("/", response_model=GreenhouseRead, status_code=201)
def create_greenhouse(
    greenhouse_data: GreenhouseCreate,
    db: Session = Depends(get_db)
) -> Greenhouse:
    return create_greenhouse(greenhouse_data)
```

### 10.7 Migration from Raw SQL

For existing SQL tables, SQLModel classes should be created to match the existing schema. Use Alembic for any schema changes:

```python
# alembic/versions/001_initial_schema.py
def upgrade():
    # Create tables using SQLModel metadata
    SQLModel.metadata.create_all(bind=op.get_bind())
```

### 10.8 Benefits

1. **Type Safety**: Compile-time validation of database operations
2. **API Consistency**: Single source of truth for data models
3. **Automatic Validation**: Pydantic validation on all API boundaries
4. **IDE Support**: Full autocomplete and type checking
5. **OpenAPI Generation**: Automatic schema generation for API documentation
6. **Testing**: Easy mocking and test data creation


11) Example Policies (optional; comment out if not desired now)
-- Example: permit read-only app role
-- CREATE ROLE verdify_app NOINHERIT;
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO verdify_app;
-- GRANT USAGE ON SCHEMA public TO verdify_app;

## Open Questions

> **Open Questions Reference**: All open questions have been consolidated in [GAPS.md](./GAPS.md) for systematic resolution. See sections on Database & Data Management.
