# Project Verdify - System Overview

## Executive Summary

Project Verdify is an end-to-end IoT system for greenhouse automation that combines local control (ESPHome controllers), a cloud API, and an AI-assisted Planning Engine. The MVP delivers reliable telemetry, deterministic climate control via a declarative state machine, irrigation/fertilization/lighting scheduling, and a clean configuration model suitable for later scale out.

## Goals

- **Operational control & safety**: Maintain crop appropriate climate while enforcing immutable greenhouse guard rails (min/max temp, min/max VPD).
- **Deterministic behavior**: Use a declarative state machine (MUST_ON/MUST_OFF at each temp_stage × humi_stage intersection) with explicit fan group staging and rotation.
- **LLM assisted planning**: Generate plans (setpoints, deltas, hysteresis, irrigation/fertilization/lighting) informed by crop recipes, observations, telemetry history, and weather; clamp outputs to guard rails.
- **Simple, observable data**: Store all telemetry, actuator events, and controller status in a query friendly schema (TimescaleDB) for reports (e.g., "how long was Fan 1 ON today?").
- **Clear onboarding**: Claim controllers using a user facing device_name (verdify-aabbcc) and a short claim code; keep boot behavior simple and resilient.
- **Extensibility without refactors**: Normalize sensor/actuator kinds and units; keep schemas stable so new hardware is additive, not disruptive.

## Scope (MVP)

### Components

- **App (Web)**: Onboarding/claim, CRUD for greenhouses, zones, sensors, actuators, state machine; plan preview; dashboards/reports.
- **API (FastAPI)**: Auth (JWT), device tokens, full CRUD, config/plan serving with ETags, HTTP telemetry ingest, reporting endpoints.
- **Planning Engine (Celery + LLM)**: Periodic plan generation for climate (min/max temp & VPD, stage offsets, hysteresis) and schedules (irrigation/fertilization/lighting).
- **Controller (ESPHome on ESP32/Kincony A16S)**: Pulls config/plan; runs climate loop locally; computes VPD/enthalpy; executes schedules; posts telemetry/events; supports physical override buttons.

### Control Model

- **Climate loop**: Greenhouse wide and runs on one designated "climate controller." Only temp/humidity sensors flagged include_in_climate_loop=true are averaged (interior). Exterior sensors (temp/humidity/pressure) are separate and never averaged with interior; both are used for enthalpy based dehumidification decisions.
- **Fan lead/lag via fan groups**: Controller rotates the "lead"; on_count per stage drives how many group members run.
- **Manual overrides**: Physical buttons can force cool / humid / heat stages with per button target stage and timeout.

### Irrigation & Locking

- **Per controller valve lockout**: Only one irrigation valve may be ON at a time; overlapping jobs are queued FIFO by the controller.

### Data Model Highlights

- **Zone ↔ Planting 1:1**: One active planting per zone.
- **Sensor ↔ Zone mapping**: A zone can map at most one sensor per kind ("temperature", "humidity", "soil_moisture"), but a sensor may be reused by multiple zones (e.g., shared probe).
- **Context fields**: `context_text` on greenhouse and zone capture operator narrative for the planner.

### Ingest Path

- **HTTP batch ingest**: To API for telemetry (sensors, actuator events, controller status, input events). MQTT/EMQX/Telegraf is out of scope for MVP and may be reconsidered later.

### Database Migration Posture

- **No Alembic migrations**: Required until the first controller is collecting real data; schemas are included and will be stabilized before enabling migrations.

## Assumptions

- **Single owner per greenhouse**: For MVP (no roles/permissions beyond basic user auth).
- **One climate controller per greenhouse**: Other controllers may host additional sensors/actuators (e.g., irrigation, pumps, lights).
- **Plan expiry handling**: Controllers must continue executing the last valid plan; if no applicable plan segment exists, fallback to greenhouse failsafe values (from initial config).
- **Device token lifecycle**: Token remains valid until the controller is deleted/removed in the API.
- **LLM influence**: Planner may shift stage thresholds (deltas/offsets/hysteresis) but firmware clamps to greenhouse guard rails.
- **External sensing**: At least one exterior temp/humidity/pressure sensor is available to the climate controller for enthalpy comparison.

## Key Risks & Mitigations

### Misconfiguration of State Machine or Mappings
**Mitigation**: Strict API validation (unique zone × kind mapping; on/off conflict checks; on_count ≤ group size; only temp/humidity in climate loop).

### Plan Unavailability/Expiry
**Mitigation**: Controller caches last plan; if a time slot is unspecified, use failsafe rails and baseline config thresholds.

### Multi-Controller Coordination
**Mitigation**: Climate actuators must live on the climate controller; irrigation lockout enforced per controller; schedules are partitioned by actuator/controller in the plan.

### Sensor Quality/Time Sync
**Mitigation**: Controller publishes loop timings and status; enforce UTC; reject ingest with excessive clock skew; allow per sensor calibration (scale/offset).

### Enthalpy Decisions Without Pressure
**Mitigation**: Require pressure inputs for exterior and compute with defaults only if explicitly allowed (flag).

## Standards & Conventions

### Identifiers

- **device_name**: `verdify-aabbcc` (last 3 MAC bytes, lowercase hex, no separators) for claiming and display.
- **All persistent entities**: UUIDv4 (e.g., controller_uuid, greenhouse_id, sensor_id, actuator_id).

### Naming

- **snake_case**: For all JSON fields, DB columns, and API paths.
- **Units**: Metric units throughout (Celsius, kPa, meters, liters).
- **Timestamps**: ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ).

### Telemetry

- **Batching**: Preferred for network efficiency.
- **Frequency**: Configurable per sensor/actuator type.
- **Retention**: Long-term storage in TimescaleDB for analytics.

## Related Documentation

For detailed implementation specifications, see:

- **[API.md](./API.md)** - Complete REST API specification
- **[CONFIGURATION.md](./CONFIGURATION.md)** - Configuration management and publishing
- **[CONTROLLER.md](./CONTROLLER.md)** - ESPHome firmware specification
- **[PLANNER.md](./PLANNER.md)** - AI planning engine algorithms
- **[DATABASE.md](./DATABASE.md)** - Database schema and migrations
- **[AUTHENTICATION.md](./AUTHENTICATION.md)** - Security and auth flows
- **[GAPS.md](./GAPS.md)** - Known limitations and future work
