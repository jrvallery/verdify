Executive Summary
Project Verdify is an end to end IoT system for greenhouse automation that combines local control (ESPHome controllers), a cloud API, and an AI assisted Planning Engine. The MVP delivers reliable telemetry, deterministic climate control via a declarative state machine, irrigation/fertilization/lighting scheduling, and a clean configuration model suitable for later scale out.
Goals
•	Operational control & safety: Maintain crop appropriate climate while enforcing immutable greenhouse guard rails (min/max temp, min/max VPD).
•	Deterministic behavior: Use a declarative state machine (MUST_ON/MUST_OFF at each temp_stage × humi_stage intersection) with explicit fan group staging and rotation.
•	LLM assisted planning: Generate plans (setpoints, deltas, hysteresis, irrigation/fertilization/lighting) informed by crop recipes, observations, telemetry history, and weather; clamp outputs to guard rails.
•	Simple, observable data: Store all telemetry, actuator events, and controller status in a query friendly schema (TimescaleDB) for reports (e.g., “how long was Fan 1 ON today?”).
•	Clear onboarding: Claim controllers using a user facing device_name (verdify-aabbcc) and a short claim code; keep boot behavior simple and resilient.
•	Extensibility without refactors: Normalize sensor/actuator kinds and units; keep schemas stable so new hardware is additive, not disruptive.

Scope (MVP)
•	Components
o	App (Web): Onboarding/claim, CRUD for greenhouses, zones, sensors, actuators, state machine; plan preview; dashboards/reports.
o	API (FastAPI): Auth (JWT), device tokens, full CRUD, config/plan serving with ETags, HTTP telemetry ingest, reporting endpoints.
o	Planning Engine (Celery + LLM): Periodic plan generation for climate (min/max temp & VPD, stage offsets, hysteresis) and schedules (irrigation/fertilization/lighting).
o	Controller (ESPHome on ESP32/Kincony A16S): Pulls config/plan; runs climate loop locally; computes VPD/enthalpy; executes schedules; posts telemetry/events; supports physical override buttons.
•	Control model
o	Climate loop is greenhouse wide and runs on one designated “climate controller.” Only temp/humidity sensors flagged include_in_climate_loop=true are averaged (interior). Exterior sensors (temp/humidity/pressure) are separate and never averaged with interior; both are used for enthalpy based dehumidification decisions.
o	Fan lead/lag via fan groups: controller rotates the “lead”; on_count per stage drives how many group members run.
o	Manual overrides: Physical buttons can force cool / humid / heat stages with per button target stage and timeout.
•	Irrigation & locking
o	Per controller valve lockout: only one irrigation valve may be ON at a time; overlapping jobs are queued FIFO by the controller.
•	Data model highlights
o	Zone ↔ Planting 1:1 (one active planting per zone).
o	Sensor ↔ Zone mapping: A zone can map at most one sensor per kind (“temperature”, “humidity”, “soil_moisture”), but a sensor may be reused by multiple zones (e.g., shared probe).
o	Context fields (context_text) on greenhouse and zone capture operator narrative for the planner.
•	Ingest path
o	HTTP batch ingest to API for telemetry (sensors, actuator events, controller status, input events). MQTT/EMQX/Telegraf is out of scope for MVP and may be reconsidered later.
•	Database migration posture
o	No Alembic migrations are required until the first controller is collecting real data; schemas are included and will be stabilized before enabling migrations.

Assumptions
•	Single owner per greenhouse for MVP (no roles/permissions beyond basic user auth).
•	One climate controller per greenhouse; other controllers may host additional sensors/actuators (e.g., irrigation, pumps, lights).
•	Plans can expire; controllers must continue executing the last valid plan; if no applicable plan segment exists, fallback to greenhouse failsafe values (from initial config).
•	Device token lifecycle: token remains valid until the controller is deleted/removed in the API.
•	LLM influence: planner may shift stage thresholds (deltas/offsets/hysteresis) but firmware clamps to greenhouse guard rails.
•	External sensing: at least one exterior temp/humidity/pressure sensor is available to the climate controller for enthalpy comparison.

Key Risks & Mitigations
•	Misconfiguration of state machine or mappings → Mitigation: strict API validation (unique zone × kind mapping; on/off conflict checks; on_count ≤ group size; only temp/humidity in climate loop).
•	Plan unavailability/expiry → Mitigation: controller caches last plan; if a time slot is unspecified, use failsafe rails and baseline config thresholds.
•	Multi controller coordination (irrigation lockout local, climate global) → Mitigation: climate actuators must live on the climate controller; irrigation lockout enforced per controller; schedules are partitioned by actuator/controller in the plan.
•	Sensor quality/time sync → Mitigation: controller publishes loop timings and status; enforce UTC; reject ingest with excessive clock skew; allow per sensor calibration (scale/offset).
•	Enthalpy decisions without pressure → Mitigation: require pressure inputs for exterior and compute with defaults only if explicitly allowed (flag).

Standards & Conventions
•	Identifiers:
o	device_name = verdify-aabbcc (last 3 MAC bytes, lowercase hex, no separators) for claiming and display.
o	All persistent entities: UUIDv4 (e.g., controller_uuid, greenhouse_id, sensor_id, actuator_id).
•	Naming: snake_case for all JSON fields, DB columns, and API paths.
•	Time: UTC ISO 8601 timestamps on wire and in DB in UTC
•	Units: Metric (SI) only in DB and over the wire; UI may convert to imperial per user preference.
•	Schemas: JSON Schemas provided for config, plan, and telemetry; ETag/If None Match used for config/plan retrieval.
•	Security (baseline only): TLS for all endpoints; user JWT; per device tokens; rate limiting on unauthenticated bootstrap/hello.


Architecture Overview
This section defines the end to end architecture for Project Verdify: components, responsibilities, interaction patterns, data flows, and rationale. It includes an HTTP first design for configuration, planning, and telemetry ingest, with an optional MQTT ingress path that can be enabled later without redesign.

1. Components (Logical View)
1. App (Web Portal)
•	Purpose: User onboarding/claim, CRUD for greenhouses/zones/sensors/actuators/state machine, plan review, dashboards.
•	Interfaces: REST to API.
•	Notes: Converts units for display (metric → imperial) per user preference.
2. API (FastAPI)
•	Purpose: Auth (JWT), device tokens, config & plan serving (ETag), CRUD, telemetry ingest, reporting queries.
•	Data: Postgres + TimescaleDB hypertables for time series; object storage for images (via image_url).
•	Responsibilities:
o	Device onboarding: /hello, /controllers/claim.
o	Configuration materialization for controllers (one “climate controller” per greenhouse).
o	Ingest: HTTP batch telemetry (sensors, actuator events, controller status, input events).
o	Planning Engine orchestration (task enqueue), weather & DB access.
o	Validation & constraints (e.g., unique zone × kind mapping; climate loop rules).
3. Planning Engine (Celery worker + LLM)
•	Purpose: Periodically compute greenhouse plan segments (climate min/max + deltas/offsets/hysteresis; irrigation/fertilization/lighting schedules).
•	Inputs: Crop recipes, active plantings, observations, recent telemetry, weather forecast, greenhouse/zone context_text.
•	Outputs: Plan rows (versioned, time bounded); values clamped to greenhouse guard rails.
•	Interfaces: DB reads/writes via API service account; external weather; LLM provider.
4. Controller (ESPHome on ESP32/Kincony A16S)
•	Purpose: Local control loop execution, telemetry publication, schedule execution, manual override buttons.
•	Boot: Captive portal shows device_name = verdify-aabbcc + claim_code; POST /hello until claimed.
•	Runtime:
o	Pulls config & plan (HTTP with ETag).
o	Computes averages (interior sensors with include_in_climate_loop=true), external vs interior separation, VPD & enthalpy.
o	Evaluates state machine (greenhouse wide climate loop) and actuates relays.
o	Enforces irrigation single valve lockout per controller; queues overlaps FIFO.
o	Supports manual overrides: cool / humid / heat buttons → force target stage with timeout.
o	Posts batched telemetry via HTTP (/telemetry/ingest).
•	Optional: Can publish telemetry to MQTT if ingress is enabled.
5. Optional Ingress (MQTT Bridge)
•	Purpose: Alternate telemetry path when needed (scale, low latency streaming). Broker receives device topics, bridge/consumer batches to API ingest.
•	Status: Disabled for MVP; architecture accommodates later enablement without changing controller/API contracts.
 
2. High Level Diagram (Mermaid)
 
3. Key Data Flows
3.1 Device Onboarding & Claim
1.	Controller boot: Captive portal displays device_name (verdify-aabbcc) and claim_code.
2.	Hello: Controller periodically POST /v1/controllers/hello with { device_name, claim_code, hardware_profile, firmware, ts_utc }.
3.	Claim: User opens App → enters device_name, claim_code, selects greenhouse → POST /v1/controllers/claim.
4.	Provision: API creates controller_uuid, associates greenhouse, issues device token.
5.	Bootstrap: Controller retries GET /v1/controllers/by-name/{device_name}/bootstrap to learn controller_uuid and fetch device token (or gets initial config inline).
6.	Config pull: Controller GETs /v1/controllers/{controller_uuid}/config (ETag). On 200, caches; on 304, continues with cached.
3.2 Telemetry Ingest (HTTP first; MQTT optional)
•	HTTP MVP: Controller batches readings/events every N seconds: POST /v1/telemetry/ingest with arrays:
o	sensor_readings[] (time, sensor_id/kind/scope, value)
o	actuator_events[] (time, actuator_id, state, reason)
o	controller_status[] (time, state, averages, vpd_kpa, enthalpy_kjkg, plan_version)
o	input_events[] (manual override button presses)
•	API writes to TimescaleDB hypertables; derives run segments for reports.
•	Optional MQTT: If enabled, controller publishes to topics; broker consumer batches to same HTTP ingest endpoint.
3.3 Config Pull
1.	ETag retrieval: Controller GET /config with If-None-Match.
2.	Payload includes: zones, mappings (sensor⇄zone; zone allows one per kind; sensors may map to multiple zones), climate controller designation, fan groups, state machine (MUST_ON/MUST_OFF per temp_stage × humi_stage, on_count for fan groups), baselines & hysteresis, failsafe guard rails, manual button bindings, irrigation lockout = true.
3.	Validation server side: unique constraints, kind whitelist, climate loop inclusion limits (temp/humidity only), actuator references exist on this greenhouse/controller.
3.4 Plan Generation & Pull
1.	Celery job (e.g., every 5–10 min): Planning Engine gathers: active plantings, crop recipes, observations (incl. images & health scores), last N days of telemetry & actuator use, weather forecast, greenhouse/zone context_text.
2.	LLM output: Structured JSON for:
o	Climate: min/max temp °C, min/max VPD kPa, stage_deltas, offsets, hysteresis, valid time windows.
o	Schedules: irrigation/fertilization per zone/actuator; lighting on/off by actuator.
3.	Clamp: Engine clamps values to greenhouse guard rails (min/max temp/VPD).
4.	Persist: New plan_version rows in DB with time bounds and per controller slices (climate controller gets climate segment; each controller gets only actuators it owns).
5.	Pull: Controller GET /plan with ETag; cache & execute. If plan segment missing for current time → fallback to failsafe baselines.
3.5 Runtime Control (on the Climate Controller)
1.	Acquire sensors: Poll interior sensors flagged include_in_climate_loop=true (temp/humidity) and exterior (temp/humidity/pressure).
2.	Compute: Greenhouse interior averages (temp, RH, VPD) + exterior enthalpy (requires pressure).
3.	Determine stages: Apply LLM plan deltas/offsets/hysteresis over config baselines; clamp to guard rails; pick temp_stage and humi_stage.
4.	Lookup state: Find state machine row for (temp_stage, humi_stage):
o	Turn MUST_ON actuators ON.
o	Turn MUST_OFF actuators OFF.
o	For fan groups, apply on_count and rotate lead evenly across members.
5.	Irrigation: Execute scheduled jobs; enforce single valve lockout per controller; queue overlaps FIFO.
6.	Manual overrides: On button press, force target stage for configured timeout; return to automatic control afterward.
7.	Telemetry: Batch and POST to API. In case of network loss: continue with cached plan; if no plan slot applies, use failsafe baselines and guard rails.

4. Integration Points
•	Weather API: Forecasts (temperature, humidity, pressure) for planning; cached via API.
•	LLM Provider: Structured prompt-to-plan generation; responses validated against JSON Schema; values clamped to rails.
•	Object Storage (images): Observation photos stored externally; DB holds image_url.
•	(Optional) MQTT Broker: Telemetry pub/sub; consumer bridges to API ingest.
 
5. Why This Architecture
•	Resilience by design: Controllers operate safely offline with cached config/plan and immutable guard rails; deterministic state machine avoids ambiguous behaviors.
•	Separation of concerns:
o	Controller: real time control, safety, and simple HTTP batching.
o	API: source of truth, validation, and storage.
o	Planning Engine: heavy, asynchronous computation and external integrations (LLM, weather).
•	HTTP first simplicity: Minimizes moving parts for MVP and simplifies ops; optional MQTT ingress allows future low latency streaming without changing controller firmware or API contracts.
•	Evolvability: Sensor/actuator kind metadata, strict schemas, and versioned plans/configs allow additive growth (new sensors, more controllers) with minimal refactors.
•	Observability: TimescaleDB hypertables + actuator event model enable precise reports (on/off times, daily runtimes, cycle counts) and future analytics.
 
6. Architectural Conventions (enforced across components)
•	IDs: device_name for claim (verdify-aabbcc); all persistent entities are UUIDv4.
•	Naming: snake_case for JSON/DB; enums are lowercase strings (e.g., "temperature").
•	Time & Units: UTC ISO 8601; metric (SI) in DB and on the wire; UI handles imperial conversions.
•	Config/Plan Transport: ETag/If None Match for efficient pulls; monotonically incrementing version.
•	Climate Controller Ownership: Exactly one controller per greenhouse runs the climate loop and owns climate actuators; others handle irrigation/pumps/lights.
 
Open Questions
1.	MVP ingest path: Keep MQTT fully disabled in v1, or enable broker early for future proofing dashboards? If enabled, which broker and auth model (per device token reuse vs separate credentials)?
2.	Time sync at the edge: Will controllers rely solely on NTP via ESPHome, and what is the tolerated clock skew for accepting telemetry at ingest (e.g., ±120s)?
3.	Plan distribution: Should we add optional retained MQTT for plan/config push in the future, or keep pull only and rely on short ETag polling intervals?
