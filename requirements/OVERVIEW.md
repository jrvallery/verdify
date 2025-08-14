Below is (1) a concise, actionable **OpenAPI review** with exact fixes and gaps, and (2) an **updated OVERVIEW\.md** that bakes in the forward/backward traceability you requested and aligns scope with the API. I made sure the new OVERVIEW removes claims that aren’t in the API yet, and adds a “Deferred / Proposed” section for anything we’d still like but haven’t exposed.

# Project Verdify — System Overview (MVP-aligned)

## Executive Summary

Project Verdify is an end‑to‑end IoT system for greenhouse automation that combines local control (ESPHome controllers), a cloud API, and an AI‑assisted Planning Engine. The MVP delivers reliable telemetry, **deterministic climate control** via a declarative state machine (grid of MUST\_ON/MUST\_OFF), irrigation/fertilization/lighting scheduling, and a configuration/plan delivery model using strong **ETags**.

This document reflects what is **implemented/exposed in the API now** and clearly separates deferred features.

---

## Goals

* **Operational control & safety:** Maintain crop‑appropriate climate while enforcing immutable greenhouse guard rails (min/max temp, min/max VPD).
* **Deterministic behavior:** Declarative state machine with explicit fan group staging and rotation; always computable locally on the controller.
* **LLM‑assisted planning:** Generate or accept plans (setpoints, stage deltas, hysteresis, irrigation/fertilization/lighting) informed by crop recipes, observations, history, and weather; clamp to guard rails.
* **Simple, observable data:** Persist telemetry, actuator events, and controller status in a query‑friendly schema (TimescaleDB) to answer оператор questions (e.g., “how long was Fan 1 ON today?”).
* **Clear onboarding:** Claim controllers with `device_name` (`verdify-aabbcc`) and a 6‑digit claim code; keep boot behavior minimal and resilient.
* **Extensibility without refactors:** Normalize sensor/actuator kinds and units; keep schema stable so new hardware is additive.

> **MVP note:** Real‑time dashboards use **HTTP polling with ETags**, not WebSockets. Deep health endpoints and reporting queries are **deferred**.

---

## Scope (MVP)

### Components

* **Frontend (Web)** — Next.js/TypeScript admin UI with generated API client, CRUD flows, dashboards with polling.
* **API (FastAPI)** — Auth (JWT), device tokens, CRUD, config/plan serving with ETags, HTTP telemetry ingest, basic meta endpoints.
* **Planning Engine (Celery + LLM)** — Periodic plan generation; manual plan creation via API; clamps to rails.
* **Controller (ESPHome on ESP32/Kincony A16S)** — Pulls config/plan; runs climate loop locally; computes VPD/enthalpy; executes schedules; posts telemetry/events; physical override buttons.

---

## Frontend Architecture (Next.js + TypeScript)

* **Framework:** Next.js (App Router)
* **Language:** TypeScript end‑to‑end with auto‑generated client
* **UI:** Chakra UI
* **Server State:** React Query (ETag‑aware)
* **API Client Generation:**

  ```bash
  npx openapi-typescript-codegen --input https://api.verdify.ai/api/v1/openapi.json --output src/api/client
  ```

**Key UI flows (MVP):**

* Onboard & claim controllers (device name + claim code)
* Configure greenhouse/zone/sensor/actuator/fan groups/buttons
* Define state machine rows + fallback
* Review plan versions; create a new plan version
* View telemetry summaries (via simple queries/polling)

> **Real‑time:** The UI performs **polling** on config/plan/health and uses `If-None-Match` with ETags. WebSockets are deferred.

---

## Backend Architecture (FastAPI + Celery + Redis + TimescaleDB)

* **FastAPI** for REST and OpenAPI
* **Celery + Redis** for planning runs and future analytics
* **PostgreSQL + TimescaleDB** for relational + time‑series telemetry
* **Redis** for ETag caches and future rate‑limit state

**Background Tasks (MVP):**

* Periodic plan generation (Celery)
* Notifications & analytics (skeletons present; heavy analytics deferred)
* Health & metrics exposure (Prometheus endpoint via instrumentation)

---

## Control Model

* **Climate loop:** Runs on the *designated climate controller*. Only interior temp/humidity with `include_in_climate_loop=true` are averaged; exterior readings are separate, but used (with pressure) for enthalpy‑guided dehumidification.
* **Fan lead/lag:** Fan groups rotate the lead; `on_count` per stage drives how many members run.
* **Manual overrides:** Physical buttons can force cool/heat/humid stages with per‑button target stage and timeout.
* **Irrigation lockout:** Per‑controller lockout ensures only one irrigation valve ON at a time; overlaps queue FIFO.

---

## API Surface (MVP)

> Canonical reference: **OpenAPI 3.1** (`Project Verdify MVP API v2.0`).

### Authentication & Onboarding

* `POST /auth/register`, `POST /auth/login`, `GET /auth/csrf`, `POST /auth/revoke-token`
* `POST /hello` (public) — first boot announcement
* `POST /controllers/claim` — claim device, returns token
* `POST /controllers/{controller_id}/token-exchange` (public) — one-time token exchange
* `POST /controllers/{controller_id}/rotate-token`, `POST /controllers/{controller_id}/revoke-token`

### Config & Plan (ETag)

* `GET /controllers/by-name/{device_name}/config` (DeviceToken; `If-None-Match`)
* `GET /controllers/me/config` (DeviceToken; `If-None-Match`)
* `GET /controllers/{controller_id}/plan`, `GET /controllers/me/plan` (DeviceToken; `If-None-Match`)
* `POST /greenhouses/{greenhouse_id}/config/publish` (supports `dry_run`)
* `GET /greenhouses/{greenhouse_id}/config/diff`
* `GET /plans` (list versions), `POST /plans` (create version)

### Telemetry Ingest (HTTP only; optional gzip; Idempotency-Key)

* `POST /telemetry/sensors` — batch readings
* `POST /telemetry/actuators` — edge events
* `POST /telemetry/status` — controller status frames
* `POST /telemetry/inputs` — button/input events
* `POST /telemetry/batch` — mixed payload; supports `Content-Encoding: gzip`

### CRUD (admin/app)

* Greenhouses: `GET/POST /greenhouses`, `GET/PATCH/DELETE /greenhouses/{greenhouse_id}`
* Zones: `GET/POST /zones`, `GET/PATCH/DELETE /zones/{zone_id}`
* Crops: `GET/POST /crops`, `GET/PATCH/DELETE /crops/{crop_id}`
* Plantings: `GET/POST /zone-crops`, `GET/PATCH /zone-crops/{id}`
* Observations: `GET/POST /observations`, `PATCH/DELETE /observations/{id}`, `POST /observations/{id}/upload-url`
* Controllers: `GET/POST /controllers`, `GET/PATCH/DELETE /controllers/{controller_id}`
* Sensors: `GET/POST /sensors`, `GET/PATCH /sensors/{id}`
* Sensor–Zone Map: `POST /sensor-zone-maps`, `DELETE /sensor-zone-maps`
* Actuators: `POST /actuators`, `GET /actuators/{id}` *(see “Deferred” for list/update/delete)*
* Fan Groups: `POST /fan-groups`, `POST/DELETE /fan-groups/{id}/members` *(list/get/delete group deferred)*
* Buttons: `POST /buttons` *(list/get/update/delete deferred)*
* State Machine: `POST /state-machine-rows`, `PUT /state-machine-fallback/{greenhouse_id}` *(list/update rows deferred)*

### Meta & Health

* `GET /meta/sensor-kinds`, `GET /meta/actuator-kinds`
* `GET /health` (liveness + version)

---

## Business Invariants & Validation Rules

> **Error codes in API:** `E400_BAD_REQUEST`, `E401_UNAUTHORIZED`, `E403_FORBIDDEN`, `E404_NOT_FOUND`, `E409_CONFLICT`, `E412_PRECONDITION_FAILED`, `E422_UNPROCESSABLE`, `E429_TOO_MANY_REQUESTS`, `E500_INTERNAL`, `E503_SERVICE_UNAVAILABLE`.

**Identity & formatting**

* `device_name` must match `^verdify-[0-9a-f]{6}$`
* Claim codes must match `^\d{6}$`
* UUIDv4 IDs; ISO‑8601 UTC timestamps; **metric units only**

**Uniqueness & cardinality**

* `(greenhouse_id, zone_number)` unique
* Exactly one `is_climate_controller=true` per greenhouse
* At most one active planting per zone
* `(sensor_id, zone_id, kind)` unique (and one sensor per kind per zone)

**State machine coverage**

* Grid covers all `temp_stage, humi_stage ∈ [-3..+3]`
* Exactly one fallback row
* All referenced actuator/fan group IDs must exist

**Climate & safety**

* Planner outputs clamped within greenhouse rails
* Only temp/humidity sensors can set `include_in_climate_loop=true`
* Zone-scoped sensors require `zone_id`; others must not have it

**Irrigation & scheduling**

* Single‑valve lockout per controller; overlapping jobs queued FIFO (controller‑side)

**Auth separation**

* Device tokens can’t access user endpoints; user JWTs can’t access device endpoints

**ETags & caching**

* Config ETag: `config:v<version>:<sha8>`
* Plan ETag: `plan:v<version>:<sha8>`

---

## Traceability (two‑way)

> Abbreviations: **US** (User Story), **FR** (Functional Requirement), **TR** (Technical Requirement), **API** (endpoint).

### A. Capabilities → API (forward mapping)

| Capability                     | US                                                                                            | FR                                                                  | TR                                                | API (primary)                                                                                                                           |
| ------------------------------ | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Controller onboarding & claim  | As an operator, I claim a new controller by code.                                             | Accept `device_name` + 6‑digit `claim_code`; issue DeviceToken.     | Public `/hello`; token exchange; JWT‑gated claim. | `POST /hello`, `POST /controllers/claim`, `POST /controllers/{id}/token-exchange`                                                       |
| Rotate/revoke device token     | As an admin, I can rotate or revoke a device token.                                           | Non‑disruptive rotation; immediate revoke.                          | JWT‑protected admin calls.                        | `POST /controllers/{id}/rotate-token`, `POST /controllers/{id}/revoke-token`                                                            |
| Fetch config/plan with ETags   | As firmware, I fetch config/plan efficiently.                                                 | Support `If-None-Match`; strong ETags.                              | Strong ETags, canonical JSON hashing.             | `GET /controllers/me/config`, `GET /controllers/me/plan`, `GET /controllers/by-name/{device_name}/config`, `GET /controllers/{id}/plan` |
| Publish config snapshot & diff | As an admin, I review & publish deterministic config.                                         | Dry‑run preview; diff vs last published.                            | Materializer with validation.                     | `POST /greenhouses/{id}/config/publish`, `GET /greenhouses/{id}/config/diff`                                                            |
| Deterministic climate control  | As an admin, I configure state grid & fallback.                                               | 49 grid rows + single fallback; fan groups with on\_count.          | Validation of grid coverage and refs.             | `POST /state-machine-rows`, `PUT /state-machine-fallback/{greenhouse_id}`, `POST /fan-groups`, `POST/DELETE /fan-groups/{id}/members`   |
| CRUD core domain               | As an admin, I manage greenhouses, zones, sensors, actuators, crops, plantings, observations. | Create/read/update/delete per entity (MVP has some read/list gaps). | JWT auth; pagination; sorts.                      | See CRUD table above (noting deferred list/update/delete for some entities)                                                             |
| Telemetry ingest               | As firmware, I batch-send telemetry & events reliably.                                        | Idempotency key; rate-limit headers; gzip for batch.                | HTTP ingest only (MQTT deferred).                 | `POST /telemetry/*`, `POST /telemetry/batch`                                                                                            |
| Planning                       | As an admin/system, I can create plan versions and list history.                              | Only one active at a time; effective window.                        | Stored payload with setpoints and schedules.      | `POST /plans`, `GET /plans`                                                                                                             |
| Health/meta                    | As operator, I can check liveness and lookup kinds.                                           | Health OK; meta enumerations.                                       | Public `GET /health`; meta endpoints.             | `GET /health`, `GET /meta/sensor-kinds`, `GET /meta/actuator-kinds`                                                                     |

### B. API → Requirements (backward mapping)

For each **API family**, here are the user intent(s) and requirements it satisfies:

* **/hello, /controllers/claim, /controllers/{id}/token-exchange** → US: claim device → FR: secure onboarding → TR: CSRF not required; short claim code; token issuance.
* **/controllers/*/config & /controllers/*/plan** → US: pull config & plan → FR: ETag & gzip → TR: canonical hashing, Last‑Modified.
* **/telemetry/* & /telemetry/batch*\* → US: reliable ingest → FR: idempotency & rate-limit feedback → TR: 202 Accepted, counters, epoch reset.
* **/plans** → US: manage plan versions → FR: version monotonicity; single active → TR: DB checks & uniqueness.
* **/state-machine-rows & fallback; /fan-groups** → US: express deterministic logic → FR: full grid + fallback → TR: validation of references and counts.
* **/greenhouses, /zones, /sensors, /controllers, /crops, /zone-crops, /observations** → US: model greenhouse and plantings → FR: pagination + sorting where listed → TR: standard CRUD with UUIDs.
* **/health, /meta/** → US: liveness and enumerations → FR: stable public health; kinds for UX → TR: no auth on health/meta.

---

## Data Model Highlights

* **Zone ↔ Planting 1:1 active** (at most one active planting per zone).
* **Sensor–Zone mapping:** At most one sensor per kind per zone; sensors can be shared by multiple zones.
* **Context fields:** `context_text` on greenhouse/zone to guide planning.

---

## Ingest Path

* **HTTP batch ingest** only (MVP). MQTT/EMQX/Telegraf **deferred**.
* **Idempotency-Key** recommended for exactly‑once semantics.
* **Rate-limiting:** Telemetry category limits returned via headers (limit/remaining/reset).

---

## Health & Monitoring

* **MVP endpoint:** `GET /health` (always on; liveness + version).
* **Metrics:** Prometheus endpoint via service instrumentation (outside OpenAPI).
* **Deferred deep endpoints:** `/health/detailed`, `/health/cache`, `/health/workers`, etc. (see “Deferred & Proposed”).

---

## Assumptions

* Single owner per greenhouse (roles later).
* One climate controller per greenhouse.
* Controllers cache last valid plan; fallback rails if expired.
* Device token lifetime: long‑lived until controller removal.
* Planner may shift stage thresholds but firmware clamps to greenhouse rails.
* Exterior temp/humidity/pressure available for enthalpy decisions.

---

## Risks & Mitigations

* **Misconfiguration:** Strict API validation (grid coverage, uniqueness, on\_count ≤ group size).
* **Plan expiry:** Controller caches last plan; fallback rails baseline enforced.
* **Multi‑controller:** Climate actuators must be on the climate controller; irrigation lockout per controller.
* **Clock/timestamps:** Enforce UTC; reject excessive skew; sensor calibration (scale/offset).

---

## Standards & Conventions

* **Identifiers:** `device_name` = `verdify-aabbcc`; entity IDs = UUIDv4.
* **snake\_case** fields; **metric units**; timestamps = ISO‑8601 UTC (`Z`).
* **ETags:** `config:v<version>:<sha8>`, `plan:v<version>:<sha8>`.

---

## Validation Constraints (selected)

* `min_temp_c < max_temp_c`, `min_vpd_kpa < max_vpd_kpa`
* Physical ranges: temp −50..+100 °C; RH 0..100 %; VPD 0..10 kPa; pressure 500–1200 hPa
* `temp_stage`/`humi_stage` ∈ \[−3..+3]
* Version numbers ≥ 1 (monotonic per greenhouse for plans)

---

## Deferred & Proposed (tracked in `GAPS.md`)

**Deferred (documented, not in API yet):**

* Deep health endpoints (`/health/detailed`, `/health/cache`, `/health/workers`, `/health/controllers`, `/metrics` swagger exposure)
* Reporting/analytics query endpoints (e.g., “fan runtime today”)
* WebSocket endpoints for live dashboards
* MQTT ingest

**Proposed near‑term endpoints (to improve CRUD ergonomics & ops):**

* `GET /actuators`, `PATCH /actuators/{id}`, `DELETE /actuators/{id}`
* `GET /fan-groups`, `GET /fan-groups/{id}`, `DELETE /fan-groups/{id}`
* `GET /buttons`, `GET /buttons/{id}`, `PATCH /buttons/{id}`, `DELETE /buttons/{id}`
* `GET /state-machine-rows?greenhouse_id=...`, `PATCH /state-machine-rows/{id}`, `DELETE /state-machine-rows/{id}`
* `POST /greenhouses/{id}/plans/generate` (enqueue planner run)

---

## Error Response Standards (API‑aligned)

All validation failures return:

```json
{
  "error_code": "E422_UNPROCESSABLE",
  "message": "Validation failed",
  "timestamp": "2025-08-13T18:05:00Z",
  "details": [
    { "field": "min_temp_c", "value": 25.0, "expected": "must be less than max_temp_c" }
  ],
  "request_id": "req_123..."
}
```

---

## Related Documentation

* **API** — auto‑generated client from OpenAPI (`/openapi.json`)
* **CONFIGURATION.md** — Config materialization & validation
* **CONTROLLER.md** — ESPHome firmware spec
* **PLANNER.md** — Planning engine logic & clamps
* **DATABASE.md** — Schema & constraints (TimescaleDB)
* **AUTHENTICATION.md** — JWT & device token flows
* **GAPS.md** — Deferred features & proposed endpoints

---

### Notes baked into this revision

* Replaced prior references to `E422_UNPROCESSABLE_ENTITY` with `E422_UNPROCESSABLE` to match the API.
* Clarified that dashboards use **polling with ETags** (WS deferred).
* Trimmed earlier “deep health endpoints” from MVP scope to match current API.
* Added a two‑way **traceability matrix** so each capability maps to specific endpoints and vice versa.
* Captured **deferred & proposed** endpoints to keep API and overview in lockstep.

---

If you’d like, I can produce a **patch-ready diff** for the OpenAPI file reflecting items A(1–8) and B(13), and a second diff adding the optional ergonomics endpoints in B(9–11,14).
