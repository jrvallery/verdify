# Project Verdify Planning Engine & Telemetry

## Overview

This document specifies Project Verdify's Planning Engine (LLM-assisted) and telemetry ingestion system. The Planning Engine generates actionable greenhouse plans from data, validates and stores outputs, and coordinates controller execution. The telemetry system defines how controllers report sensor data, actuator events, and status information back to the API.

This specification is written for agentic coders to implement end-to-end with deterministic constraints and validation rules.

## Related Documentation

This Planning Engine specification integrates with other Project Verdify components:

- **[API.md](./API.md)** - REST endpoints for plan retrieval and telemetry ingestion
- **[CONTROLLER.md](./CONTROLLER.md)** - Controller execution of plans and telemetry reporting
- **[CONFIGURATION.md](./CONFIGURATION.md)** - Configuration management and guard rails
- **[DATABASE.md](./DATABASE.md)** - Database schema for plans and telemetry storage
- **[OVERVIEW.md](./OVERVIEW.md)** - System architecture and business invariants
- **[GAPS.md](./GAPS.md)** - Known limitations and open questions

## Planning Engine

### Objectives and Scope

**Objective**: Produce a rolling, time-segmented plan that sets climate targets (min/max temp/VPD, stage deltas & hysteresis), plus irrigation, fertilization, and lighting schedules—per greenhouse and routed to the right controllers/actuators—while respecting immutable guard rails.

**Scope (MVP)**:
- One climate controller per greenhouse executes the climate loop
- Irrigation lockout is enforced per controller (one valve ON at a time; overlaps queued FIFO)
- Plans are valid for a horizon (e.g., 10 days) with step size (e.g., 30 min)
- If no valid plan row for "now", controllers fall back to configuration baseline (guard rails always enforced)

### Inputs

The Planning Engine runs as an async worker (e.g., Celery Beat + tasks) on a schedule (e.g., every 5–10 minutes per greenhouse). For each greenhouse `gh_id`, it assembles the following inputs:

#### Static/Config (from DB)

- **greenhouse**: guard rails (min_temp_c, max_temp_c, min_vpd_kpa, max_vpd_kpa), baselines (stage thresholds + hysteresis), site_pressure_hpa, context_text
- **zones**: id, location, context_text
- **controllers**: list with is_climate_controller (exactly one true), and controller → actuator ownership
- **sensors**: by kind, scope (zone/greenhouse/external), include_in_climate_loop
  - Note: Ensure climate loop sensors belong to the climate controller (local access)
- **actuators**: climate (heater/fan/vent/humidifier/dehumidifier), irrigation valves (often zone scoped), lights
- **fan_groups**: with member fan actuators

#### Crop Context

- Active zone_crop rows (1:1 with zones) for all zones in greenhouse
- crop templates with recipe JSON (environmental targets by growth stage)
- zone_crop_observation: last N (e.g., 7–10) observations per active crop (notes, health score, height, photo URLs)

#### Telemetry History (Timescale)

- **Window**: last 7 days (configurable)
- **Aggregations** (example SQL patterns):
  - **Interior averages**: temp, humidity, derived VPD; daily min/max, 95th/5th percentiles
  - **Exterior**: temp, humidity, pressure (or greenhouse baseline pressure if absent)
  - **Actuator runtimes**: total ON duration/day; cycle counts
  - **Soil moisture per zone**: recent mean/min; last irrigation timestamp; drying rate estimate
  - **Light exposure**: daily photoperiod, min/max lux or PPFD if available
- Provide a compact summary to the LLM (see §3): numeric ranges and short bullet lists; no raw time series

#### Weather Forecast (External API)

- Daily/hourly forecast for horizon: outside temp, humidity, pressure (or elevation adjusted), cloud cover, precipitation, wind speed
- **Derived enthalpy inputs**: use outside T/RH/pressure versus interior T/RH/pressure to estimate enthalpy delta for dehumidification decisions (heat vs ventilate)

### Prompting the LLM

#### Prompt Structure (Deterministic JSON)

The prompt must instruct the LLM to return strict JSON conforming to our schema (see §4.1). Use guard rails as hard constraints and require explanations in a separate field that we will discard at parse time (for observability only).

**Template (abridged)**:

```
SYSTEM: You are Verdify's planning engine. Output ONLY JSON that validates against the provided JSON Schema. Do not include code fences or commentary.

USER:
Context:
- Greenhouse: {title}, guard_rails={min_temp_c..max_vpd_kpa}, baseline={thresholds + hysteresis}, site_pressure_hpa={value}
- Greenhouse notes: """{greenhouse.context_text}"""

Controllers:
- Climate controller: {controller_id}
- Other controllers: [{...}] (with irrigation lockout = {true/false})

Zones (active plantings):
{[
  { "zone_id": "...", "crop": { "name": "...", "recipe": {...} }, 
    "observations_summary": {
      "last_7d": {"health_avg": X, "height_cm_avg": Y, "notes": ["...","..."] },
      "issues": ["pests?","leaf curl?"]
    },
    "soil": {"vwc_recent_min": x, "vwc_recent_avg": y, "last_irrigation_utc": "..."}
  }, ...
]}

History (last 7d summary):
- Interior: temp {avg/min/max}, rh {avg/min/max}, vpd {avg/min/max}
- Exterior: temp {avg/min/max}, rh {avg/min/max}, pressure {avg/min/max}
- Enthalpy delta recent: {avg/min/max}
- Actuator usage: {fan_runtime_h:..., heater_runtime_h:..., humidifier_h:..., dehumidifier_h:...}
- Light: {avg_day_length_h, avg_ppfd_or_lux}
- Water: {daily_total_L}

Forecast (next {H}h @ {step}min):
- By time: [{ts_utc, temp_out_c, rh_out_pct, pressure_hpa, cloud_cover_pct, precip_mm, wind_mps}, ...]

Task:
1) Propose climate setpoints timeline (every {step} minutes for {H} hours) with:
   - temp_min_c, temp_max_c, vpd_min_kpa, vpd_max_kpa
   - temp_delta_c, vpd_delta_kpa (deltas applied to baseline thresholds; VPD-only model)
   - temp_hysteresis_c, vpd_hysteresis_kpa
   Respect guard_rails strictly. Prefer energy efficiency. Use enthalpy delta to choose dehumid strategy (heat vs ventilate).

2) Propose irrigation jobs per ZONE with {ts_utc, duration_s}. Optionally include fertilizer flag or fertilizer_duration_s.
   Follow irrigation lockout per controller (we will queue if overlaps exist but avoid overlaps when possible).
   Avoid overwatering; consider soil drying rate and forecast humidity/temperature.

3) Propose lighting jobs per LIGHT actuator with {ts_utc, duration_s} to achieve photoperiod and intensity needs from crop recipes and forecast daylight.

Output JSON per the following schema (do not include fields not in the schema). Provide brief 'rationale' strings we may log, but they will be ignored by devices.
Note: We embed the JSON Schema (next section) in the prompt to improve compliance.
```

### Plan Output & Persistence

#### Plan JSON Schema (LLM Output → Parser Input)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://api.verdify.ai/schemas/plan-output.json",
  "title": "Verdify Plan Output",
  "type": "object",
  "required": ["effective_from", "effective_to", "setpoints", "irrigation", "lighting"],
  "properties": {
    "effective_from": { "type": "string", "format": "date-time" },
    "effective_to":   { "type": "string", "format": "date-time" },

    "setpoints": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": [
          "ts_utc",
          "temp_min_c", "temp_max_c",
          "vpd_min_kpa", "vpd_max_kpa",
          "temp_delta_c", "vpd_delta_kpa",
          "temp_hysteresis_c", "vpd_hysteresis_kpa"
        ],
        "properties": {
          "ts_utc": { "type": "string", "format": "date-time" },
          "temp_min_c": { "type": "number" },
          "temp_max_c": { "type": "number" },
          "vpd_min_kpa": { "type": "number" },
          "vpd_max_kpa": { "type": "number" },
          "temp_delta_c": { "type": "number" },
          "vpd_delta_kpa": { "type": "number" },
          "temp_hysteresis_c": { "type": "number" },
          "vpd_hysteresis_kpa": { "type": "number" },
          "rationale": { "type": "string" }
        },
        "additionalProperties": false
      }
    },

    "irrigation": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["zone_id", "ts_utc", "duration_s"],
        "properties": {
          "zone_id": { "type": "string", "format": "uuid" },
          "ts_utc":  { "type": "string", "format": "date-time" },
          "duration_s": { "type": "integer", "minimum": 1 },
          "fertilizer": { "type": "boolean", "default": false },
          "fertilizer_duration_s": { "type": "integer", "minimum": 1 },
          "min_soil_vwc": { "type": "number", "description": "Optional guard; skip if soil VWC already above." },
          "rationale": { "type": "string" }
        },
        "additionalProperties": false
      }
    },

    "lighting": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["actuator_id", "ts_utc", "duration_s"],
        "properties": {
          "actuator_id": { "type": "string", "format": "uuid" },
          "ts_utc": { "type": "string", "format": "date-time" },
          "duration_s": { "type": "integer", "minimum": 1 },
          "rationale": { "type": "string" }
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
```

#### Parser & Validation (Agentic enforcement)

> **Algorithm Reference**: For complete parsing and validation algorithms, see [DATABASE.md - Planning Guard Rail Clamping](./DATABASE.md#algorithms-functions).

**Validation Pipeline:**
1. **JSON Schema validation**: Validate against OpenAPI PlanPayload schema
2. **Guard rail clamping**: Clamp all setpoints to greenhouse min/max boundaries  
3. **Business logic validation**: Check irrigation durations, lighting actuator references, schedule conflicts
4. **Staleness detection**: Use 24-hour grace period for plan expiry checks

**Plan Staleness:**
- Plans remain valid for 24 hours past `effective_to` timestamp
- `is_plan_stale()` function determines when fallback behavior should activate
- Grace period prevents abrupt transitions during planning engine delays

**Agentic enforcement requirements:**
- Reject unknown zone_id / actuator_id references
- Warn but allow irrigation job overlaps (controller will queue with lockout)
- Planner should avoid overlaps by design but accept them for robustness

#### Persistence (DB Writes)

- Insert one row into plan:
  - (greenhouse_id, version=n+1, effective_from, effective_to, generated_at=now_utc())
- Bulk insert:
  - plan_setpoint (one per ts_utc item)
  - plan_irrigation (one per zone job)
  - plan_lighting (one per actuator job)
  - Optional plan_fertilization if separated (MVP: included via flags in irrigation)
- **Versioning**: bump monotonically; keep historical plans (no migrations required yet)
- **ETag for Plan**: hash of canonical JSON payload (optional; useful if controllers pull /plan)

### Execution on Controllers

Controllers periodically fetch the current plan segment (HTTP GET with ETag). Climate controller applies setpoint deltas to config baselines to compute effective thresholds.

#### Climate Setpoints → Effective Thresholds

At time t_now, select latest plan_setpoint.ts_utc ≤ t_now. If none exists or plan expired, use baseline.

```python
# baseline from config
base_temp   = baseline.temp_c   # thresholds dict {-3..3} + hysteresis
base_humi   = baseline.humi_pct
base_vpd    = baseline.vpd_kpa

# plan deltas at t_now (if available)
delta_temp_c   = sp.temp_delta_c
delta_vpd_kpa  = sp.vpd_delta_kpa

# effective thresholds = baseline thresholds + deltas
eff_temp_stages = {k: base_temp.stages[k] + delta_temp_c for k in -3..3}
eff_humi_stages = {k: base_humi.stages[k] + delta_humi_pct for k in -3..3}
eff_vpd_stages  = {k: base_vpd.stages[k]  + delta_vpd_kpa  for k in -3..3}

# hysteresis override (plan may tighten/loosen)
temp_hyst = sp.temp_hysteresis_c or base_temp.hysteresis_c
vpd_hyst  = sp.vpd_hysteresis_kpa or base_vpd.hysteresis_kpa

# guard rails are always enforced when evaluating stages/targets
```

#### Dehumidification Strategy (Enthalpy aware)

- Controller computes enthalpy delta = h_interior - h_exterior
- If enthalpy_delta > threshold, prefer ventilation; else prefer heating for dehumid (configurable threshold or from plan; MVP: simple fixed split point)
- This influences actuator choices via the state machine (e.g., prefer vent+fans vs heater+dehumidifier in relevant stage intersections)

#### Irrigation & Fertilization

For each due job (zone_id, ts_utc, duration_s, fertilizer?):
- Ensure this controller owns the valve actuator for the zone; if not, ignore (plan routing error)
- Enforce irrigation lockout: if another valve is ON, queue job FIFO
- If min_soil_vwc provided and current soil VWC ≥ min, skip
- Start valve, respect min_on_ms, stop after duration_s (or longer if min_on_ms dominates)
- Log to actuator_event

#### Lighting

- Start/stop light actuators per schedule. No lockout unless explicitly configured by user

#### Fallbacks

- No plan row for now or plan expired → use baseline thresholds/hysteresis only
- Manual override buttons temporarily force temp_stage/humi_stage for timeout_s; actuator decisions continue to respect min_on/off and lockout

### Orchestration & Scheduling

- **Cadence**: every 5–10 min per greenhouse (configurable)
- **Triggers**: new observations, unusual telemetry deviations (e.g., high VPD), forecast shift events, or user request ("Recompute Plan")
- **Horizon & Granularity** (recommendation): 10 days at 30 min steps → 480 setpoint rows/day; can be tuned
- **Idempotency**: If inputs unchanged and last plan still valid, skip new version

### Integration Contracts (API)

- **Planner Reads**: `/api/v1/greenhouses/{id}/facts` (server side join for everything needed) or discrete endpoints:
  - `/api/v1/greenhouses/{id}`
  - `/api/v1/zones?greenhouse_id=`
  - `/api/v1/controllers?greenhouse_id=`
  - `/api/v1/sensors?greenhouse_id=`
  - `/api/v1/actuators?greenhouse_id=`
  - `/api/v1/fan-groups?greenhouse_id=`
  - `/api/v1/observations?zone_id=`
  - telemetry summaries via Timescale views
- **Planner Writes**:
  - `POST /api/v1/greenhouses/{id}/plans` with full LLM output; API parser clamps & persists
  - `GET /api/v1/greenhouses/{id}/plans/latest` for verification
- **Controller Plan Pull**:
  - `GET /api/v1/controllers/self/plan` (with ETag); returns merged/filtered plan subset for that controller (its actuators + global setpoints)

### Celery Task Integration (FastAPI Template Alignment)

#### Background Task Architecture

The planning engine integrates with the FastAPI template's Celery infrastructure for reliable background processing:

```python
# app/tasks/planner.py
from celery import shared_task
from celery.exceptions import Retry
from app.core.celery_app import celery_app
from app.services.planning import PlanningService
from app.models import Greenhouse
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def generate_plan(self, greenhouse_id: str) -> Dict[str, Any]:
    """
    Generate AI plan for greenhouse with retry logic and error handling.
    
    Args:
        greenhouse_id: UUID of the greenhouse to plan for
        
    Returns:
        Dictionary with plan generation results
        
    Raises:
        Retry: If temporary failures occur (API limits, network issues)
    """
    try:
        logger.info(f"Starting plan generation for greenhouse {greenhouse_id}")
        
        service = PlanningService()
        result = service.generate_plan_with_llm(greenhouse_id)
        
        logger.info(f"Plan generated successfully: {result.plan_id}")
        return {
            "status": "success",
            "plan_id": result.plan_id,
            "version": result.version,
            "generated_at": result.generated_at.isoformat(),
            "setpoints_count": len(result.setpoints)
        }
        
    except Exception as exc:
        logger.error(f"Plan generation failed for greenhouse {greenhouse_id}: {exc}")
        
        # Retry on temporary failures
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying plan generation (attempt {self.request.retries + 1})")
            raise self.retry(countdown=60 * (2 ** self.request.retries), exc=exc)
        
        # Final failure - log and return error
        logger.error(f"Plan generation permanently failed after {self.max_retries} retries")
        return {
            "status": "error",
            "error_message": str(exc),
            "greenhouse_id": greenhouse_id
        }

@shared_task
def schedule_periodic_planning():
    """Schedule plan generation for all active greenhouses"""
    from app.crud.greenhouse import get_active_greenhouses
    
    greenhouses = get_active_greenhouses()
    
    for greenhouse in greenhouses:
        logger.info(f"Scheduling plan generation for {greenhouse.title}")
        generate_plan.delay(str(greenhouse.id))
    
    return {"scheduled_count": len(greenhouses)}

@shared_task  
def cleanup_old_plans():
    """Remove plan data older than retention period"""
    from app.services.planning import PlanningService
    
    service = PlanningService()
    deleted_count = service.cleanup_expired_plans()
    
    logger.info(f"Cleaned up {deleted_count} expired plan records")
    return {"deleted_count": deleted_count}
```

#### API Integration

**Trigger Planning via API:**
```python
# app/api/routes/planning.py
from fastapi import APIRouter, Depends, HTTPException
from app.tasks.planner import generate_plan
from app.models import User

router = APIRouter()

@router.post("/greenhouses/{greenhouse_id}/plans/generate")
async def trigger_plan_generation(
    greenhouse_id: str,
    current_user: User = Depends(get_current_user)
):
    """Trigger immediate plan generation for greenhouse"""
    
    # Validate greenhouse ownership
    if not await validate_greenhouse_access(greenhouse_id, current_user):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Enqueue background task
    task = generate_plan.delay(greenhouse_id)
    
    return {
        "task_id": task.id,
        "status": "queued",
        "greenhouse_id": greenhouse_id
    }

@router.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """Check status of background planning task"""
    
    task = celery_app.AsyncResult(task_id)
    
    return {
        "task_id": task_id,
        "status": task.status,
        "result": task.result if task.ready() else None
    }
```

#### Celery Configuration

**Setup Celery with Redis broker:**
```python
# app/core/celery_app.py
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "verdify",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.planner", "app.tasks.analytics"]
)

# Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minute timeout for planning tasks
    worker_disable_rate_limits=True,
)

# Periodic tasks
celery_app.conf.beat_schedule = {
    'generate-plans': {
        'task': 'app.tasks.planner.schedule_periodic_planning',
        'schedule': 3600.0,  # Every hour
    },
    'cleanup-old-plans': {
        'task': 'app.tasks.planner.cleanup_old_plans', 
        'schedule': 86400.0,  # Daily
    },
}
```

#### Error Handling and Monitoring

**Task Monitoring:**
```python
# app/api/routes/monitoring.py
@router.get("/admin/tasks/status")
async def get_task_statistics():
    """Get Celery task statistics for monitoring"""
    
    inspector = celery_app.control.inspect()
    
    return {
        "active_tasks": inspector.active(),
        "scheduled_tasks": inspector.scheduled(),
        "worker_stats": inspector.stats(),
        "queue_length": get_queue_length()
    }
```

**Integration Benefits:**
- **Reliability**: Automatic retries with exponential backoff
- **Scalability**: Multiple Celery workers can process plans in parallel
- **Monitoring**: Built-in task tracking and status reporting
- **Scheduling**: Periodic plan generation via Celery Beat
- **Error Recovery**: Graceful handling of LLM API failures

### Acceptance Criteria (Agentic Tests)

- **Schema compliance**: Generated JSON validates against plan-output.json
- **Guard rails**: All setpoints stored are within greenhouse rails (unit tests clamp extremes)
- **Irrigation routing**: Every irrigation job references a zone_id with an owned valve actuator; otherwise API rejects with 422
- **Lighting kind**: Every lighting job actuator_id must be kind=light; otherwise 422
- **Versioning**: New plan increments version; effective window continuous or explicitly gapped (documented)
- **Fallback**: Simulate missing plan → controller uses baseline; tests assert state machine still operates

### Example (Abbreviated LLM Output)

```json
{
  "effective_from": "2025-08-12T00:00:00Z",
  "effective_to":   "2025-08-22T00:00:00Z",
  "setpoints": [
    {
      "ts_utc": "2025-08-12T06:00:00Z",
      "temp_min_c": 18.0, "temp_max_c": 24.0,
      "vpd_min_kpa": 0.8, "vpd_max_kpa": 1.4,
      "temp_delta_c": +1.0, "vpd_delta_kpa": +0.1,
      "temp_hysteresis_c": 0.5, "vpd_hysteresis_kpa": 0.1
    }
    // ... every 30 min ...
  ],
  "irrigation": [
    { "zone_id": "d3c6...", "ts_utc": "2025-08-12T09:30:00Z", "duration_s": 300, "fertilizer": false, "min_soil_vwc": 0.22 }
  ],
  "lighting": [
    { "actuator_id": "a-light-...", "ts_utc": "2025-08-12T11:00:00Z", "duration_s": 21600 }
  ]
}
```

### Implementation Hints

- **Tokenizer limits**: Summarize telemetry/history into ≤1–2 KB JSON to avoid prompt bloat; move large logic (clamping, overlaps) to the parser
- **Few shot JSON examples** improve adherence; include at least one day of hourly setpoints and 2–3 example jobs
- **Guard rail prompts**: Repeat constraints near the end ("You MUST keep outputs within …")
- **Deterministic decoding**: Use "JSON only" responses; strip any prefixes/suffixes before parsing
- **Back pressure**: If LLM fails validation → retry with stricter instructions; after N failures, fall back to heuristic planner (optional MVP deferral)

### Validation & Business Rules

> **Validation Reference**: For complete validation rules and business invariants, see [Business Invariants in OVERVIEW.md](./OVERVIEW.md#business-invariants).

**Planning-specific validation:**
- **Guard rail compliance**: All generated setpoints clamped to greenhouse min/max boundaries
- **Schedule conflicts**: Irrigation overlaps accepted but marked for sequential execution  
- **JSON schema validation**: Plan outputs validated against OpenAPI schemas before storage
- **Retry logic**: Failed validation triggers LLM retry with stricter constraints

## Telemetry System

### Goals & Scope

- **Goals**: Reliably ingest greenhouse data (sensors, actuator edges, controller status, input/button events) for control, planning, and reporting
- **Transport**: HTTPS (no MQTT in MVP). Controllers POST JSON (optionally gzip compressed) to API endpoints under `/api/v1/telemetry/*`
- **Auth**: Authorization: Bearer <device_token>; token binds request to a single controller. Device tokens are valid until controller deletion
- **Time**: All timestamps are UTC ISO 8601. Server may adjust/override if skew is excessive
- **Units**: All values are metric in DB/wire

### Payload Types & Frequency

| Type | Endpoint | Frequency / Trigger | Purpose |
|------|----------|-------------------|---------|
| Sensors Batch | `POST /api/v1/telemetry/sensors` | Every 10–15 s (configurable) | Raw sensor readings (zone/greenhouse/external) |
| Actuator Edges | `POST /api/v1/telemetry/actuators` | Immediately on ON/OFF change | Edge events for relays/actuators with reason codes |
| Status | `POST /api/v1/telemetry/status` | Every 30 s | Controller heartbeat: averages, stages, enthalpy, overrides, versions |
| Input Events | `POST /api/v1/telemetry/inputs` | Immediately on button press/release | Manual override button events (cool/heat/humid) |
| Batch (optional) | `POST /api/v1/telemetry/batch` | When convenient to coalesce within 1–2 s | Single POST containing any/all of the above arrays |

**Compression**: Content-Encoding: gzip accepted on all telemetry endpoints.

### REST Endpoints (contract)

All endpoints require Authorization: Bearer <device_token>.

- `POST /api/v1/telemetry/sensors` → 204 No Content on success
- `POST /api/v1/telemetry/actuators` → 204 No Content
- `POST /api/v1/telemetry/status` → 204 No Content
- `POST /api/v1/telemetry/inputs` → 204 No Content
- `POST /api/v1/telemetry/batch` → 207 Multi-Status with per section results (or 204 if all ok)

**Error codes:**
- 400 schema invalid
- 401 bad/expired token
- 403 controller mismatch (IDs don't belong to token)
- 404 unknown sensor/actuator
- 409 duplicate event (event_id already ingested)
- 422 semantic error (e.g., wrong actuator kind)

### JSON Schemas

**Conventions**: snake_case keys; no extra properties; UUIDs are canonical 36 char hyphenated; timestamps are ISO 8601 with Z.

#### Sensors Batch

```json
{
  "$schema":"https://json-schema.org/draft/2020-12/schema",
  "title":"Sensors Batch",
  "type":"object",
  "required":["readings"],
  "properties":{
    "device_ts_utc": {"type":"string","format":"date-time"},
    "readings":{
      "type":"array",
      "minItems":1,
      "items":{
        "type":"object",
        "required":["sensor_id","value"],
        "properties":{
          "sensor_id":{"type":"string","format":"uuid"},
          "ts_utc":{"type":"string","format":"date-time"},
          "value":{"type":"number"},
          "status":{"type":"string","enum":["ok","fault","offline"],"default":"ok"}
        },
        "additionalProperties":false
      }
    }
  },
  "additionalProperties":false
}
```

**Rules:**
- sensor_id must belong to the authenticated controller
- If ts_utc missing, server uses now() (and logs drift if abs(device_ts_utc - now()) > skew_limit_s)
- Values must be metric and already scaled (controller applies scale_factor/offset from config)

**Example:**
```json
{
  "device_ts_utc": "2025-08-12T18:00:05Z",
  "readings": [
    {"sensor_id":"8b2a...c7a4","ts_utc":"2025-08-12T18:00:04Z","value":23.6},
    {"sensor_id":"e3f1...9112","value":56.2}
  ]
}
```

#### Actuator Edge Events

```json
{
  "$schema":"https://json-schema.org/draft/2020-12/schema",
  "title":"Actuator Events",
  "type":"object",
  "required":["events"],
  "properties":{
    "events":{
      "type":"array",
      "minItems":1,
      "items":{
        "type":"object",
        "required":["event_id","actuator_id","ts_utc","state","reason"],
        "properties":{
          "event_id":{"type":"string","maxLength":64,"description":"Unique per controller for idempotency"},
          "actuator_id":{"type":"string","format":"uuid"},
          "ts_utc":{"type":"string","format":"date-time"},
          "state":{"type":"boolean"},
          "reason":{
            "type":"string",
            "enum":[
              "state_machine","manual_override","plan_job_start","plan_job_end",
              "lockout_queue_start","lockout_queue_end","guard_rail","config_applied",
              "boot_default","failsafe_timeout","test"
            ]
          },
          "meta":{"type":"object","additionalProperties":true}
        },
        "additionalProperties":false
      }
    }
  },
  "additionalProperties":false
}
```

**Rules:**
- Deduplicate by (event_id, controller); identical duplicates are ignored (204)
- actuator_id must belong to the authenticated controller
- Ingestion pairs ON (state=true) with the next OFF to create a run segment

**Example:**
```json
{
  "events":[
    {
      "event_id":"a1-000123",
      "actuator_id":"c2de...b09a",
      "ts_utc":"2025-08-12T18:00:10Z",
      "state":true,
      "reason":"state_machine"
    },
    {
      "event_id":"a1-000124",
      "actuator_id":"c2de...b09a",
      "ts_utc":"2025-08-12T18:07:42Z",
      "state":false,
      "reason":"state_machine"
    }
  ]
}
```

#### Controller Status (heartbeat)

```json
{
  "$schema":"https://json-schema.org/draft/2020-12/schema",
  "title":"Controller Status",
  "type":"object",
  "required":["ts_utc","config_version","plan_version","interior","exterior","stages","override","metrics"],
  "properties":{
    "ts_utc":{"type":"string","format":"date-time"},
    "config_version":{"type":"integer","minimum":1},
    "plan_version":{"type":"integer","minimum":0},
    "interior":{
      "type":"object",
      "required":["avg_temp_c","avg_rh_pct","avg_pressure_hpa","avg_vpd_kpa"],
      "properties":{
        "avg_temp_c":{"type":"number"},
        "avg_rh_pct":{"type":"number"},
        "avg_pressure_hpa":{"type":"number"},
        "avg_vpd_kpa":{"type":"number"}
      },
      "additionalProperties":false
    },
    "exterior":{
      "type":"object",
      "required":["temp_c","rh_pct","pressure_hpa"],
      "properties":{
        "temp_c":{"type":"number"},
        "rh_pct":{"type":"number"},
        "pressure_hpa":{"type":"number"}
      },
      "additionalProperties":false
    },
    "enthalpy":{
      "type":"object",
      "required":["in_kjkg","out_kjkg","delta_kjkg"],
      "properties":{
        "in_kjkg":{"type":"number"},
        "out_kjkg":{"type":"number"},
        "delta_kjkg":{"type":"number"}
      },
      "additionalProperties":false
    },
    "stages":{
      "type":"object",
      "required":["temp_stage","humi_stage"],
      "properties":{
        "temp_stage":{"type":"integer","minimum":-3,"maximum":3},
        "humi_stage":{"type":"integer","minimum":-3,"maximum":3}
      },
      "additionalProperties":false
    },
    "override":{
      "type":"object",
      "required":["active"],
      "properties":{
        "active":{"type":"boolean"},
        "source":{"type":"string","enum":["button_cool","button_heat","button_humid","api","none"],"default":"none"},
        "seconds_remaining":{"type":"integer","minimum":0}
      },
      "additionalProperties":false
    },
    "metrics":{
      "type":"object",
      "required":["uptime_s","loop_ms"],
      "properties":{
        "uptime_s":{"type":"integer","minimum":0},
        "loop_ms":{"type":"integer","minimum":0},
        "wifi_rssi_dbm":{"type":"integer"},
        "heap_free_b":{"type":"integer"},
        "irrigation_queue_depth":{"type":"integer","minimum":0}
      },
      "additionalProperties":false
    }
  },
  "additionalProperties":false
}
```

**Example:**
```json
{
  "ts_utc":"2025-08-12T18:00:30Z",
  "config_version":4,
  "plan_version":12,
  "interior":{"avg_temp_c":23.8,"avg_rh_pct":57.1,"avg_pressure_hpa":845.0,"avg_vpd_kpa":1.10},
  "exterior":{"temp_c":29.1,"rh_pct":35.0,"pressure_hpa":845.0},
  "enthalpy":{"in_kjkg":48.2,"out_kjkg":52.0,"delta_kjkg":-3.8},
  "stages":{"temp_stage":1,"humi_stage":-1},
  "override":{"active":false,"source":"none","seconds_remaining":0},
  "metrics":{"uptime_s":86400,"loop_ms":37,"wifi_rssi_dbm":-55,"heap_free_b":172032,"irrigation_queue_depth":0}
}
```

#### Input Events (manual override buttons)

```json
{
  "$schema":"https://json-schema.org/draft/2020-12/schema",
  "title":"Input Events",
  "type":"object",
  "required":["events"],
  "properties":{
    "events":{
      "type":"array",
      "items":{
        "type":"object",
        "required":["event_id","button_id","ts_utc","action"],
        "properties":{
          "event_id":{"type":"string","maxLength":64},
          "button_id":{"type":"string","format":"uuid"},
          "ts_utc":{"type":"string","format":"date-time"},
          "action":{"type":"string","enum":["press","release"]},
          "mapped_stage":{"type":"string","enum":["COOL_S1","COOL_S2","HEAT_S1","HUMID_S1"],"description":"From config button mapping"},
          "timeout_s":{"type":"integer","minimum":0}
        },
        "additionalProperties":false
      }
    }
  },
  "additionalProperties":false
}
```

**Example:**
```json
{
  "events":[
    {"event_id":"btn-771","button_id":"2f1e...8a22","ts_utc":"2025-08-12T18:05:00Z","action":"press","mapped_stage":"COOL_S1","timeout_s":600}
  ]
}
```

#### Plan Expiry and Grace Period

**Grace Period**: Plans are considered stale if they expire beyond a 24-hour grace period.

- **Active Plan**: Current time falls within plan's valid interval
- **Grace Period**: Plan expired but within 24 hours - controller continues executing
- **Stale Plan**: Plan expired > 24 hours ago - controller reports `plan_stale: true` in telemetry and may fall back to failsafe

> **Algorithm Reference**: For plan staleness detection, see [DATABASE.md - Plan Staleness Check](./DATABASE.md#algorithms-functions).

Controllers should:
1. Continue executing plans within grace period (24 hours past `effective_to`)
2. Report `plan_stale: true` in status telemetry when beyond grace
3. Alert via App when plan expired > grace period

### Ingestion Pipeline (Server)

Steps per request:
1. **Auth & Bind**: Resolve device_token → controller_uuid, greenhouse_id. Reject if controller is_active=false
2. **Schema Validation**: Validate JSON against the respective schema
3. **Semantic Validation**:
   - Ensure all sensor_id / actuator_id / button_id belong to the controller
   - Reject unknown IDs; return 404
   - Dedup by event_id (actuators, inputs)
4. **Time Normalization**:
   - If ts_utc missing, set to now(); if skew > configured limit (e.g., 5 min), clamp to now() and tag meta.skewed=true
5. **Enrichment**: Add greenhouse_id, controller_id to each row
6. **Write**:
   - sensors → sensor_reading(time, greenhouse_id, controller_id, sensor_id, value)
   - actuators → actuator_event(time, greenhouse_id, controller_id, actuator_id, state, reason)
   - status → controller_status(time, greenhouse_id, controller_id, state, avg_interior/exterior, enthalpy, stages, override, loop_ms, uptime_s)
   - inputs → input_event(time, greenhouse_id, controller_id, button_id, action, mapped_stage, timeout_s)
7. **Run Segment Pairing** (actuators): On OFF event insert, find latest unmatched ON for same actuator and insert into actuator_run_segment. (Trigger/procedure defined in Database section.)
8. **Respond**: 204 or per section results for batch

**Idempotency**: Duplicate event_id → 204 (ignored). Replays with identical body are safe.

### Aggregates, Views & Policies

Hypertables exist per Database section. Below are recommended continuous aggregates/materialized views and helper views.

#### Actuator Run Segments (helper view)

If not materialized by trigger:

```sql
-- View pairing ON with next event (requires dedup at ingest)
create or replace view actuator_run_segments as
select
  e_on.greenhouse_id,
  e_on.controller_id,
  e_on.actuator_id,
  e_on.time       as started_at,
  e_off.time      as ended_at,
  extract(epoch from (e_off.time - e_on.time))::int as duration_s
from actuator_event e_on
join lateral (
  select time from actuator_event e2
  where e2.actuator_id = e_on.actuator_id and e2.time > e_on.time
  order by e2.time asc limit 1
) e_off on true
where e_on.state = true;
```

**Preferred (MVP)**: Use a trigger to populate a hypertable actuator_run_segment on OFF events for durability and easy aggregation.

#### Daily Runtimes & Cycles (continuous aggregate)

```sql
create materialized view actuator_daily_runtime
with (timescaledb.continuous) as
select
  time_bucket('1 day', start_time)      as day,
  greenhouse_id, controller_id, actuator_id,
  sum(duration_s)                        as run_seconds,
  count(*)                               as cycles
from actuator_run_segment
group by day, greenhouse_id, controller_id, actuator_id;

select add_continuous_aggregate_policy('actuator_daily_runtime',
  start_offset => interval '7 days',
  end_offset   => interval '1 hour',
  schedule_interval => interval '15 minutes');
```

#### Sensor Hourly Averages (continuous aggregate)

```sql
create materialized view sensor_hourly_avg
with (timescaledb.continuous) as
select
  time_bucket('1 hour', time) as hour,
  greenhouse_id, controller_id, sensor_id,
  avg(value) as avg_value, min(value) as min_value, max(value) as max_value
from sensor_reading
group by hour, greenhouse_id, controller_id, sensor_id;

select add_continuous_aggregate_policy('sensor_hourly_avg',
  start_offset => interval '14 days',
  end_offset   => interval '1 hour',
  schedule_interval => interval '15 minutes');
```

#### Example Retention/Compression (to be confirmed)

```sql
-- Raw telemetry
select add_retention_policy('sensor_reading',      interval '90 days');
select add_retention_policy('actuator_event',      interval '180 days');
select add_retention_policy('controller_status',   interval '90 days');
select add_retention_policy('input_event',         interval '180 days');

-- Compress after 7 days (if compression enabled)
select add_compression_policy('sensor_reading',    interval '7 days');
select add_compression_policy('actuator_event',    interval '7 days');
```

### Query Patterns (Examples)

#### "When did actuator X turn on/off last week?"

```sql
select time as ts_utc, state, reason
from actuator_event
where actuator_id = $1
  and time >= now() - interval '7 days'
order by time asc;
```

#### "How long was actuator X ON between A and B?"

```sql
select sum(duration_s) as total_on_s
from actuator_run_segment
where actuator_id = $1
  and start_time <  $end
  and end_time   >= $start;
```

#### "How many cycles today for all fans?"

```sql
select adr.controller_id, a.name, adr.cycles
from actuator_daily_runtime adr
join actuator a on a.id = adr.actuator_id
where adr.day = date_trunc('day', now())
  and a.kind = 'fan'
order by adr.cycles desc;
```

#### "Correlate fan runtime with energy (kWh)"

Assuming a greenhouse level kwh sensor:

```sql
with fan_run as (
  select time_bucket('1 hour', start_time) as hour, sum(duration_s)/3600.0 as fan_hours
  from actuator_run_segment ars
  join actuator a on a.id = ars.actuator_id
  where a.kind = 'fan' and start_time >= now() - interval '7 days'
  group by hour
), energy as (
  select hour, avg_value as kwh
  from sensor_hourly_avg
  join sensor s on s.id = sensor_hourly_avg.sensor_id
  where s.kind = 'kwh' and hour >= now() - interval '7 days'
)
select f.hour, f.fan_hours, e.kwh, (e.kwh / nullif(f.fan_hours,0)) as kwh_per_fan_hour
from fan_run f
left join energy e using (hour)
order by hour;
```

#### "Daily irrigation valve cycles/duration per zone"

```sql
select adr.day, z.zone_number, sum(adr.run_seconds) as run_s, sum(adr.cycles) as cycles
from actuator_daily_runtime adr
join actuator a on a.id = adr.actuator_id and a.kind = 'irrigation_valve'
left join zone z on z.id = a.zone_id
where adr.day >= current_date - interval '7 days'
group by adr.day, z.zone_number
order by adr.day, z.zone_number;
```

### Controller Implementation Notes

- Batch sensors every 10–15 s; status every ~30 s; edges/inputs immediately
- Include stages (ints −3..+3), enthalpy in/out/delta, and override_active in status
- Use monotonic event_ids for actuators and inputs to enable idempotency
- Clock sync via SNTP; still tolerate server clamping on skew
- Always send metric units; apply sensor scaling/offset from config before send

### Server Validation & Enforcement (Agentic checklist)

- **MUST** verify (sensor_id|actuator_id|button_id) ∈ controller or reject 404
- **MUST** deduplicate event_id (store last N event_ids per controller in Redis/DB) and ignore duplicates (204)
- **SHOULD** clamp outrageous timestamps (>5 min skew) to now(); tag as skewed
- **MUST** create run segments on OFF edges (trigger or worker)
- **SHOULD** rate limit per controller (e.g., 5 req/s burst 10)
- **MUST** write to hypertables with UTC time
- **SHOULD** backpressure if DB unavailable: respond 503; controller retries with jitter

## Open Questions

> **Open Questions Reference**: All open questions have been consolidated in [GAPS.md](./GAPS.md) for systematic resolution. See sections on Planning Engine & LLM Integration and Telemetry & Monitoring.
