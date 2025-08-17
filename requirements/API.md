# Project Verdify API Specification

## Related Documentation

This API specification is part of a comprehensive requirements suite. For complete implementation guidance, refer to:

- **[CONFIGURATION.md](./CONFIGURATION.md)** - Configuration management, schema validation, and publishing workflows
- **[CONTROLLER.md](./CONTROLLER.md)** - ESPHome firmware specification and device behavior
- **[PLANNER.md](./PLANNER.md)** - Cultivation planning algorithms and scheduling logic
- **[DATABASE.md](./DATABASE.md)** - Database schema, migrations, and data modeling
- **[AUTHENTICATION.md](./AUTHENTICATION.md)** - Authentication flows, JWT handling, and security policies
- **[OVERVIEW.md](./OVERVIEW.md)** - High-level architecture and system overview
- **[GAPS.md](./GAPS.md)** - Known limitations and future enhancement areas

## Overview

This section defines all REST endpoints for Project Verdify, aligned with the **Full-Stack FastAPI Template** architecture. It specifies paths, verbs, auth, request/response schemas, validation, and error semantics. The API follows FastAPI best practices with **SQLModel** backend, **automatic OpenAPI generation**, and **type-safe client generation** for the React/Next.js frontend.

**Template Alignment**: All endpoints use `/api/v1` prefix, JWT authentication for users, device tokens for controllers, SQLModel for ORM, and PostgreSQL with TimescaleDB extension.

**ETag Support**: Config and Plan GET responses include ETag. Controllers/Apps SHOULD send If-None-Match to receive 304 Not Modified.

## Conventions

### Base URL & API Versioning
```
https://api.verdify.ai/api/v1
```
**Local Development** (via Traefik reverse proxy):
```
http://localhost/api/v1
```

# FastAPI Template Alignment Summary

This document summarizes the comprehensive alignment of Project Verdify requirements with the Full-Stack FastAPI Template architecture to enable frictionless development by agentic coders.

## Template Architecture Overview

The FastAPI template provides an opinionated full-stack architecture:
- **Backend**: FastAPI + SQLModel + Pydantic + PostgreSQL
- **Frontend**: React/Next.js + TypeScript + Chakra UI
- **Database**: PostgreSQL with automatic migrations
- **Infrastructure**: Docker Compose + Traefik reverse proxy
- **Authentication**: JWT tokens with secure cookie handling
- **API**: Automatic OpenAPI generation + TypeScript client generation

## Alignment Work Completed

### 1. API Endpoints (/api/v1 Prefix)

**Files Updated**: `API.md`, `CONTROLLER.md`, `PLANNER.md`

**Changes Made**:
- Updated 200+ endpoint URLs from `/path` to `/api/v1/path` format
- Aligned with FastAPI template's standard URL structure
- Ensures compatibility with automatic client generation

**Examples**:
```
Before: POST /auth/login
After:  POST /api/v1/auth/login

Before: GET /greenhouses/{id}
After:  GET /api/v1/greenhouses/{id}

Before: POST /telemetry/sensors
After:  POST /api/v1/telemetry/sensors
```

### 2. Router Organization

**File**: `API.md`

**Added Router Structure**:
- `auth` - Authentication endpoints (login, signup, password reset)
- `onboarding` - Device claiming and initial setup
- `config` - Controller configuration management
- `planning` - AI planning and setpoint generation
- `telemetry` - Sensor data and controller status
- `greenhouses` - Greenhouse CRUD operations
- `zones` - Zone management within greenhouses
- `sensors` - Sensor configuration and management
- `actuators` - Actuator configuration and control
- `crops` - Crop management and lifecycle

This organization aligns with FastAPI's router-based architecture and enables clean code generation.

### 3. Error Response Standardization

**File**: `API.md`

**Standardized ErrorResponse Schema**:
```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "Invalid greenhouse configuration",
  "details": {
    "field": "min_temp_c",
    "constraint": "must be >= -10"
  }
}
```

This format is fully compatible with FastAPI's HTTPException and enables consistent error handling across all endpoints.

### 4. Authentication Schemes

**File**: `API.md`

**Defined Authentication**:
- **JWT Bearer Token**: For user endpoints (web app)
- **DeviceToken**: For controller endpoints (ESPHome devices)

Both schemes integrate seamlessly with FastAPI's security dependency injection system.

### 5. Database Integration (SQLModel)

**File**: `DATABASE.md`

**Added SQLModel Integration**:
- Docker Compose configuration for TimescaleDB
- SQLModel class examples with type safety
- FastAPI dependency injection patterns
- Automatic Pydantic model generation

**Example SQLModel Class**:
```python
from sqlmodel import SQLModel, Field
from enum import Enum

class ValueType(str, Enum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    PRESSURE = "pressure"

class SensorKindMeta(SQLModel, table=True):
    __tablename__ = "sensor_kind_meta"

    id: str = Field(primary_key=True)
    name: str = Field(max_length=100)
    value_type: ValueType
    unit: str = Field(max_length=20)
    precision: int = Field(ge=0, le=10)
```

### 6. Testing Framework Alignment

**File**: `API.md`

**Added FastAPI Testing Patterns**:
- pytest + FastAPI TestClient configuration
- Test database setup with TimescaleDB containers
- Contract testing with OpenAPI validation
- SQLModel integration testing
- Parametrized endpoint validation

**Test Configuration Example**:
```python
@pytest.fixture(scope="session")
def test_db():
    with PostgresContainer("timescale/timescaledb:latest-pg15") as postgres:
        engine = create_engine(postgres.get_connection_url())
        SQLModel.metadata.create_all(engine)
        yield engine
```

### 7. Client Generation

**File**: `API.md`

**Automatic Client Generation**:
- TypeScript client for Next.js frontend
- Python client for testing and scripts
- ETag caching support in generated clients
- Type-safe error handling with ErrorResponse schema

### 8. Controller Communication

**File**: `CONTROLLER.md`

**HTTP-Only Integration**:
- Updated all ESPHome controller endpoints to use `/api/v1` prefix
- DeviceToken authentication for all controller requests
- ETag-based conditional requests for config/plan updates
- Structured telemetry payloads compatible with Pydantic validation

## Benefits of Alignment

### For Agentic Coders
1. **Predictable Structure**: All endpoints follow `/api/v1/{router}/{resource}` pattern
2. **Type Safety**: SQLModel ensures database operations are type-safe
3. **Auto-Generation**: OpenAPI schema enables automatic client generation
4. **Testing**: FastAPI TestClient provides reliable testing patterns
5. **Error Handling**: Standardized ErrorResponse format across all endpoints

### For Development
1. **Rapid Prototyping**: Template provides instant development environment
2. **Production Ready**: Docker Compose + Traefik for deployment
3. **Type Safety**: End-to-end type safety from database to frontend
4. **Documentation**: Automatic API documentation via OpenAPI
5. **Testing**: Built-in testing patterns with pytest integration

### For Deployment
1. **Container Ready**: Docker Compose configuration included
2. **Reverse Proxy**: Traefik configuration for production
3. **Database**: PostgreSQL + TimescaleDB with automatic migrations
4. **Monitoring**: Built-in health checks and logging
5. **Security**: JWT authentication with secure patterns

## Implementation Roadmap

With this alignment completed, agentic coders can now:

1. **Clone the FastAPI template** as the foundation
2. **Generate SQLModel classes** from the DATABASE.md specifications
3. **Implement API endpoints** following the router organization in API.md
4. **Add controller integration** using the HTTP patterns in CONTROLLER.md
5. **Build frontend components** using the generated TypeScript client
6. **Deploy with confidence** using the included Docker Compose configuration

The requirements are now fully aligned with the template's opinionated architecture, eliminating friction and enabling rapid, reliable implementation.


### Authentication Schemes
- **User endpoints**: `Authorization: Bearer <user_jwt>` (FastAPI template JWT dependency)
- **Device endpoints**: `X-Device-Token: <device_token>` (custom dependency for controllers)

**Security Definitions**:
```yaml
components:
  securitySchemes:
    JWT:
      type: http
      scheme: bearer
      bearerFormat: JWT
    DeviceToken:
      type: apiKey
      in: header
      name: X-Device-Token
```

### OpenAPI Client Generation
- Frontend TypeScript client auto-generated from `/api/v1/openapi.json`
- **Strongly typed** requests/responses using generated models
- **ETag support** built into client for caching
- **Error handling** standardized via ErrorResponse schema

### Backend Technology Stack
- **FastAPI** with automatic OpenAPI documentation
- **SQLModel** for type-safe database operations (inherits from Pydantic)
- **PostgreSQL** with TimescaleDB extension for telemetry data
- **Docker Compose** for development and production deployment
- **Traefik** as reverse proxy handling routing and TLS

### Error Response Schema
All error responses follow a standardized format compatible with FastAPI's HTTPException:

```json
{
  "error_code": "E400_BAD_REQUEST",
  "message": "Human-readable error description",
  "details": "Optional detailed information or field-specific errors"
}
```

**Standard Error Codes**:
- `E400_BAD_REQUEST` - Invalid JSON, missing required fields, malformed UUIDs
- `E401_UNAUTHORIZED` - Missing or invalid JWT/device token
- `E403_FORBIDDEN` - Valid token but insufficient permissions
- `E404_NOT_FOUND` - Resource does not exist or access denied
- `E409_CONFLICT` - Uniqueness violations, business logic conflicts
- `E422_UNPROCESSABLE_ENTITY` - Valid JSON but business validation failed
- `E429_TOO_MANY_REQUESTS` - Rate limit exceeded
- `E500_INTERNAL_SERVER_ERROR` - Unexpected server error

**Example Error Response**:
```json
{
  "error_code": "E409_CONFLICT",
  "message": "Cannot set second climate controller for greenhouse",
  "details": "Greenhouse already has climate controller with device_name 'verdify-abc123'"
}
```

### Error Handling

All 4xx/5xx responses follow this structure:

```json
{
  "error": {
    "code": "E409_CONFLICT",
    "message": "Climate controller already exists for greenhouse",
    "details": { "greenhouse_id": "..." }
  }
}
```

**Common Error Codes**: E400_BAD_REQUEST, E401_UNAUTHORIZED, E403_FORBIDDEN, E404_NOT_FOUND, E409_CONFLICT, E412_PRECONDITION_FAILED, E422_UNPROCESSABLE, E429_TOO_MANY_REQUESTS, E500_INTERNAL, E503_SERVICE_UNAVAILABLE.

### Common Schema Definitions

JSON Schema snippets used throughout the API:

```json
{
  "$defs": {
    "uuid": { "type": "string", "format": "uuid" },
    "ts": { "type": "string", "format": "date-time" },
    "device_name": { "type": "string", "pattern": "^verdify-[0-9a-f]{6}$" },
    "scope": { "type": "string", "enum": ["zone","greenhouse","external"] },
    "stage": { "type": "integer", "minimum": -3, "maximum": 3 },
    "sensor_kind": {
      "type": "string",
      "enum": [
        "temperature","humidity","vpd","co2","light","soil_moisture",
        "water_flow","water_total","dew_point","absolute_humidity",
        "enthalpy_delta","kwh","gas_consumption","air_pressure","ppfd",
        "wind_speed","rainfall","power"
      ]
    },
    "actuator_kind": {
      "type": "string",
      "enum": ["fan","heater","vent","fogger","irrigation_valve","fertilizer_valve","pump","light"]
    }
  }
}
```

### FastAPI Router Organization
Endpoints are organized into logical router groups following FastAPI best practices:

**Router Tags & Organization**:
- `auth` - User authentication, registration, JWT management
- `onboarding` - Device claiming, hello flow, token exchange
- `config` - Configuration management, publishing, ETags
- `planning` - Plan generation, management, and delivery
- `telemetry` - Sensor data, actuator events, status reporting
- `greenhouses` - Greenhouse CRUD operations
- `zones` - Zone management and crop plantings
- `sensors` - Sensor configuration and zone mapping
- `actuators` - Actuator configuration and fan groups
- `crops` - Crop catalog and recipe management

**Backend Implementation**: Each router group maps to a dedicated FastAPI router module in `backend/app/api/routes/`.

## Endpoints

### 1. Authentication (`auth` router)

#### 1.0 CSRF Token Generation
**GET /api/v1/auth/csrf** (Unauthenticated)

Generate CSRF token for browser-based authentication requests.

**Response 200:**
```json
{
  "csrf_token": "abc123def456...",
  "expires_at": "2025-08-12T19:00:00Z"
}
```

**Security Notes:**
- CSRF tokens are valid for 1 hour
- Required for POST /auth/register and POST /auth/login from browsers
- Include in X-CSRF-Token header for protected endpoints

#### 1.1 User Registration
**POST /api/v1/auth/register** (Unauthenticated, CSRF Protected)

Create new user account.

**Headers:**
```
X-CSRF-Token: abc123def456...  (required for browser requests)
```

**Request:**
```json
{
  "email": "user@example.com",
  "password": "secure_password",
  "full_name": "John Doe"
}
```

**Response 201:**
```json
{
  "user": {
    "id": "uuid",
    "email": "user@example.com",
    "full_name": "John Doe",
    "created_at": "2025-08-12T18:00:00Z"
  },
  "access_token": "eyJhbGciOi..."
}
```

**Errors:**
- E409_CONFLICT email already exists
- E422_UNPROCESSABLE invalid email or password too weak

#### 1.2 User Login
**POST /api/v1/auth/login** (Unauthenticated, CSRF Protected)

Authenticate user and issue JWT.

**Headers:**
```
X-CSRF-Token: abc123def456...  (required for browser requests)
```

**Request:**
```json
{
  "email": "user@example.com",
  "password": "secure_password"
}
```

**Response 200:**
```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**Errors:**
- E401_UNAUTHORIZED invalid credentials

1.0.3 POST /api/v1/auth/revoke-token (User JWT)
Revoke current user JWT (logout).
Response 204 (no content)
Errors
- E401_UNAUTHORIZED invalid or expired token

1.0.4 POST /api/v1/controllers/{id}/revoke-token (User JWT, admin)
Revoke device token for a specific controller.
Response 204 (no content)
Errors
- E401_UNAUTHORIZED, E403_FORBIDDEN, E404_NOT_FOUND

1.1 POST /api/v1/hello (Device, unauthenticated)
Initial handshake; polled until the user claims the device. This endpoint is **status-only** (no secret issuance) to reduce token exposure surface.
Request (JSON)
{
  "device_name": "verdify-a1b2c3",
  "claim_code": "932611",
  "firmware": "verdify-esphome-0.3.1",
  "hardware_profile": "kincony_a16s",
  "ts_utc": "2025-08-12T18:00:00Z"
}
Responses
- 200 OK (pending)
{ "status": "pending", "retry_after_s": 15 }
- 200 OK (claimed)
{ "status": "claimed", "controller_uuid": "6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad", "greenhouse_id": "a6f7a28f-271a-4e8b-94d6-5a8a8b8d0a12" }
Errors
- E422_UNPROCESSABLE invalid device_name/claim_code
- E409_CONFLICT device already associated with a different controller record in conflicting state

1.1.1 POST /api/v1/controllers/{controller_uuid}/token-exchange (Device, unauthenticated, single-use)
After /hello returns status=claimed the controller performs a one-time token exchange using its device_name + claim_code + controller_uuid. Server returns long-lived device_token and initial strong ETags so the controller can immediately conditional GET config/plan.
Request
{
  "device_name": "verdify-a1b2c3",
  "claim_code": "932611"
}
Response 201
{
  "device_token": "eyJhbGciOi...",
  "config_etag": "W/\"v42:1a2b3c4d5e6f7890abcdef1234567890abcdef1234567890abcdef1234567890\"",
  "plan_etag": "W/\"v17:0f9e8d7c6b5a49382716504938271650493827165049382716504938271650\"",
  "expires_at": "2024-06-15T10:30:00Z"
}
Validation
- controller_uuid in path must match claimed controller for device_name.
- claim_code must match stored value (then invalidated / rotated server-side to prevent replay).
Errors
- E404_NOT_FOUND unknown controller
- E409_CONFLICT token already issued (idempotent replay returns 200 with same etags)
- E422_UNPROCESSABLE invalid claim code

1.2 POST /api/v1/controllers/claim (User JWT)
Associate a device to a greenhouse and issue a device token.
Request
{
  "device_name": "verdify-a1b2c3",
  "claim_code": "932611",
  "greenhouse_id": "a6f7a28f-271a-4e8b-94d6-5a8a8b8d0a12",
  "label": "North Wall IO Panel"
}
Response 201
{
  "controller_uuid": "6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad",
  "greenhouse_id": "a6f7a28f-271a-4e8b-94d6-5a8a8b8d0a12",
  "device_name": "verdify-a1b2c3",
  "label": "North Wall IO Panel",
  "is_climate_controller": false,
  "provisioning": { "token_exchange_endpoint": "/api/v1/controllers/6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad/token-exchange" }
}
Validation
-	device_name must match an unclaimed hello record (recent, e.g., last 24h)
-	user must own greenhouse_id
Errors
-	E404_NOT_FOUND device_name or greenhouse missing
-	E409_CONFLICT device already claimed

1.3 POST /api/v1/controllers/{controller_uuid}/rotate-token (User JWT)
Rotate device token (old token immediately revoked).
Response 200
{
  "device_token": "eyJhbGciOi...",
  "expires_at": "2024-12-15T10:30:00Z"
}
Errors
-	E404_NOT_FOUND
-	E403_FORBIDDEN not owner

1.4 DELETE /api/v1/controllers/{controller_uuid} (User JWT)
Delete controller; revokes device token.
Response 204 (no body)
Errors
-	E404_NOT_FOUND, E403_FORBIDDEN

2) Controllers (`onboarding` router - Config & Plan access)
2.1 GET /api/v1/controllers/{controller_uuid} (User JWT)
Fetch controller metadata.
Response 200
{
  "controller_uuid": "6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad",
  "greenhouse_id": "a6f7a28f-271a-4e8b-94d6-5a8a8b8d0a12",
  "device_name": "verdify-a1b2c3",
  "label": "North Wall IO Panel",
  "is_climate_controller": false,
  "fw_version": "verdify-esphome-0.3.1",
  "last_seen": "2025-08-12T18:03:12Z"
}

2.2 PATCH /api/v1/controllers/{controller_uuid} (User JWT)
Update label, is_climate_controller (must be unique per greenhouse).
Request
{ "label": "Panel A", "is_climate_controller": true }
Response 200 updated controller JSON
Validation
-	If setting is_climate_controller=true, ensure no other controller in the same greenhouse has it.
-	If violation: E409_CONFLICT.

2.3 GET /api/v1/controllers/{controller_uuid}/config (Device token or User JWT)
Materialized configuration for this controller. ETag supported.
Headers
-	Request: If-None-Match: "config:v42:1a2b3c4d" (optional)
-	Response: ETag: "config:v42:1a2b3c4d"
Response 200: Full config.json (see Configuration section for authoritative schema)
Response 304: Not Modified
Errors
-	E403_FORBIDDEN controller does not belong to token’s greenhouse
-	E404_NOT_FOUND

2.4 GET /api/v1/greenhouses/{greenhouse_id}/plan/current (Device token or User JWT)
Current plan slice for the greenhouse (controller uses to execute). ETag supported.
Headers
-	Request: If-None-Match: "plan:v17:0f9e8d7c"
-	Response: ETag: "plan:v17:0f9e8d7c"
Response 200: Plan JSON (full schema defined in Planning section)
Response 304: Not Modified
Errors
-	E404_NOT_FOUND, E403_FORBIDDEN

3) Telemetry Ingest (`telemetry` router - Device token)
All payloads may be gzip compressed. The API validates IDs (must exist & belong to controller/greenhouse), units (metric), kinds, and writes to Timescale hypertables.
3.1 POST /api/v1/telemetry/sensors
Request
{
  "controller_uuid": "6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad",
  "ts_utc": "2025-08-12T18:04:10Z",
  "readings": [
    { "sensor_id": "3b4...", "value": 24.7 },
    { "sensor_id": "5c6...", "value": 62.1 }
  ]
}
Response 202
{ "ingested": 2, "skipped": 0 }
Errors
-	E422_UNPROCESSABLE unknown sensor_id or mismatched ownership

3.2 POST /api/v1/telemetry/actuators
Request
{
  "controller_uuid": "6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad",
  "edges": [
    {
      "actuator_id": "af2...",
      "state": true,
      "reason": "rule_apply",
      "ts_utc": "2025-08-12T18:05:00Z"
    }
  ]
}
Response 202 { "ingested": 1 }

3.3 POST /api/v1/telemetry/status
Request
{
  "controller_uuid": "6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad",
  "ts_utc": "2025-08-12T18:05:30Z",
  "interior": {
    "temp_c": 24.6, "rh_pct": 61.5, "pressure_hpa": 985.2, "vpd_kpa": 0.85
  },
  "exterior": {
    "temp_c": 22.1, "rh_pct": 70.2, "pressure_hpa": 986.0
  },
  "enthalpy": { "in_kjkg": 47.1, "out_kjkg": 45.3, "delta_kjkg": -1.8 },
  "stages": { "temp_stage": 1, "humi_stage": -1 },
  "override": { "active": false, "seconds_remaining": 0 },
  "uptime_s": 123456, "loop_ms": 18,
  "config_version": 42, "plan_version": 17
}
Response 202 { "accepted": true }

3.4 POST /api/v1/telemetry/inputs
Request
{
  "controller_uuid": "6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad",
  "events": [
    { "button_id": "b1...", "action": "press", "ts_utc": "2025-08-12T18:06:00Z" }
  ]
}
Response 202 { "ingested": 1 }

3.5 POST /api/v1/telemetry/batch
Bundle of sensors, actuators, status, inputs.
Request
{
  "controller_uuid": "6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad",
  "payloads": [
    { "type": "sensors", "ts_utc": "2025-08-12T18:04:10Z", "readings": [ ... ] },
    { "type": "actuators", "edges": [ ... ] },
    { "type": "status", "ts_utc": "2025-08-12T18:05:30Z", "interior": { ... } }
  ]
}
Response 202 { "accepted": true }

4) Greenhouses (`greenhouses` router)
4.1 POST /api/v1/greenhouses (User JWT)
Create a greenhouse.
Request (abridged; full fields in Database/Configuration sections)
{
  "title": "Main GH",
  "description": "Poly tunnel",
  "latitude": 40.123, "longitude": -105.123,
  "context_text": "Two ridge vents; heaters struggle below -10C",
  "guard_rails": { "min_temp_c": 7, "max_temp_c": 35, "min_vpd_kpa": 0.3, "max_vpd_kpa": 2.5 },
  "baselines": { "temp": { "min_c": 18, "max_c": 26, "hysteresis_c": 0.5 },
                 "vpd":  { "min_kpa": 0.8, "max_kpa": 1.2, "hysteresis_kpa": 0.05 } }
}
Response 201 greenhouse JSON (with id)
Validation
-	clamp baselines within guard rails

4.2 GET /api/v1/greenhouses / 4.3 GET /api/v1/greenhouses/{id} / 4.4 PATCH /api/v1/greenhouses/{id} / 4.5 DELETE /api/v1/greenhouses/{id}
Standard CRUD (single owner). PATCH accepts any mutable fields; DELETE cascades to zones/controllers (soft delete optional). Errors: E403_FORBIDDEN, E404_NOT_FOUND.

5) Zones (`zones` router)
5.1 POST /api/v1/zones
{ "greenhouse_id": "a6f7...", "zone_number": 1, "location": "NW", "context_text": "Shaded afternoon" }
201 zone JSON with id.
5.2 GET /api/v1/zones?greenhouse_id=... / 5.3 GET /api/v1/zones/{id} / 5.4 PATCH /api/v1/zones/{id} / 5.5 DELETE /api/v1/zones/{id}
Standard CRUD. unique(greenhouse_id, zone_number) enforced; E409_CONFLICT on dup.

6) Crops & Plantings (`crops` router)
6.1 POST /api/v1/crops
{
  "name": "Tomato",
  "description": "Indeterminate",
  "expected_yield_per_sqm": 12.5,
  "growing_days": 90,
  "recipe": { "stages": [ /* crop recipe data */ ] }
}
201 crop JSON.
6.2 GET /api/v1/crops / 6.3 GET /api/v1/crops/{id} / 6.4 PATCH /api/v1/crops/{id} / 6.5 DELETE /api/v1/crops/{id}

6.6 POST /api/v1/zone-crops
Start a planting in a zone (enforce 1 active per zone).
{ "zone_id": "z1...", "crop_id": "c1...", "start_date": "2025-08-01T00:00:00Z", "area_sqm": 10.0 }
201 zone_crop JSON.
Validation
-	If existing active planting for zone_id: E409_CONFLICT.
6.7 PATCH /api/v1/zone-crops/{id}
End planting or update metrics.
{ "end_date": "2025-10-15T00:00:00Z", "is_active": false, "final_yield": 95.2 }
6.8 POST /api/v1/zone-crop-observations
{
  "zone_crop_id": "zc1...",
  "observed_at": "2025-08-12T08:00:00Z",
  "notes": "Mild tip burn",
  "height_cm": 62.0,
  "health_score": 7,
  "image_url": "https://..."
}
Plus GET/PATCH/DELETE endpoints for observations.

7) Sensors & Mappings (`sensors` router)
Sensors are created/configured in API; controllers map them via config.json. A sensor may be mapped to multiple zones. Per zone/kind there MUST be ≤1 mapping (enforced).
7.1 POST /api/v1/sensors
{
  "controller_id": "6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad",
  "name": "RS485 T/RH #1",
  "kind": "temperature",
  "scope": "zone",
  "include_in_climate_loop": true,
  "modbus": { "slave_id": 1, "register": 30001 },
  "scale_factor": 0.1,
  "offset": 0.0,
  "poll_interval_s": 10
}
201 sensor JSON with id.
Validation
-	include_in_climate_loop==true ONLY allowed for kind ∈ {"temperature","humidity"}.
-	If include_in_climate_loop==true, sensor’s controller_id MUST equal the greenhouse climate controller; else E409_CONFLICT.
7.2 GET /api/v1/sensors (supports ?kind=, ?controller_id=, ?greenhouse_id=, ?sort=, pagination) / 7.3 GET /api/v1/sensors/{id} / 7.4 PATCH /api/v1/sensors/{id} / 7.5 DELETE /api/v1/sensors/{id}

7.6 POST /api/v1/sensor-zone-maps
Map a sensor to a zone as a given kind (used to enforce per zone singleton per kind).
{
  "sensor_id": "s1...",
  "zone_id": "z1...",
  "kind": "temperature"
}
201 map JSON (composite key).
Validation
-	Enforce unique (zone_id, kind); else E409_CONFLICT.
7.7 GET /api/v1/sensor-zone-maps?zone_id=... / 7.8 DELETE /api/v1/sensor-zone-maps/{sensor_id}:{zone_id}:{kind}

8) Actuators, Fan Groups, Buttons (`actuators` router)
8.1 POST /api/v1/actuators
{
  "controller_id": "6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad",
  "name": "Fan #1",
  "kind": "fan",
  "relay_channel": 1,
  "min_on_ms": 60000,
  "min_off_ms": 60000,
  "fail_safe_state": "off",
  "zone_id": null
}
201 actuator JSON.
Validation
-	Relay channel must be within controller’s range and unique per controller; E409_CONFLICT on duplicate.
8.2 GET/PATCH/DELETE /api/v1/actuators/{id} and list /actuators?controller_id=...

8.3 POST /api/v1/fan-groups
{ "controller_id": "6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad", "name": "North Fans" }
201 fan_group JSON with id.
8.4 POST /api/v1/fan-groups/{fan_group_id}/members
{ "actuator_id": "a1..." }
201 member JSON. Duplicate adds → E409_CONFLICT.
GET/DELETE members provided.

8.5 POST /api/v1/controller-buttons
{
  "controller_id": "6f9a8b0e-09e0-4e59-9b2d-2a0189f1f7ad",
  "name": "button_cool",
  "gpio": 32,
  "action": "cool",
  "mapped_stage": { "temp_stage": 1, "humi_stage": 0 },
  "timeout_s": 600
}
GET/PATCH/DELETE supported.

9) State Machine
Declarative grid: for each (temp_stage, humi_stage) intersection, define MUST_ON/MUST_OFF plus fan group counts and fallback.
9.1 POST /api/v1/state-machine-rows
{
  "greenhouse_id": "a6f7...",
  "temp_stage": -1,
  "humi_stage": 2,
  "must_on_actuators": ["a1...","a2..."],
  "must_off_actuators": ["a3..."],
  "must_on_fan_groups": [ { "fan_group_id": "fg1...", "on_count": 2 } ]
}
Validation
-	Unique (greenhouse_id, temp_stage, humi_stage); duplicate → E409_CONFLICT.
9.2 GET /api/v1/state-machine-rows?greenhouse_id=...
9.3 PATCH /api/v1/state-machine-rows/{id}
9.4 DELETE /api/v1/state-machine-rows/{id}
9.5 PUT /api/v1/state-machine-fallback/{greenhouse_id}
{
  "must_on_actuators": [],
  "must_off_actuators": [],
  "must_on_fan_groups": [ { "fan_group_id": "fg1...", "on_count": 1 } ]
}
Sets the fallback row (used when no explicit row matches).

10) Plans (`planning` router - for Planning Engine + App/Controller)
10.1 POST /api/v1/plans (Planning Engine JWT or Admin)
Create a new plan version for a greenhouse. The API validates and clamps to guard rails.
Request (abridged)
{
  "greenhouse_id": "a6f7...",
  "version": 18,
  "effective_from": "2025-08-12T00:00:00Z",
  "effective_to": "2025-08-22T00:00:00Z",
  "setpoints": [
    {
      "ts_utc": "2025-08-12T00:00:00Z",
      "min_temp_c": 18.0, "max_temp_c": 26.0,
      "min_vpd_kpa": 0.8,  "max_vpd_kpa": 1.2,
      "temp_hysteresis_c": 0.5, "vpd_hysteresis_kpa": 0.05,
      "temp_delta_c": 0.0, "vpd_delta_kpa": 0.0
    }
  ],
  "irrigation": [
    { "zone_id": "z1...", "ts_utc": "2025-08-12T06:00:00Z", "duration_s": 300 }
  ],
  "fertilization": [],
  "lighting": [
    { "actuator_id": "a9...", "ts_utc": "2025-08-12T05:00:00Z", "duration_s": 14400 }
  ]
}
Response 201
{ "plan_id": "p1...", "version": 18 }
Validation & Errors
-	Overlapping setpoints timestamps → E422_UNPROCESSABLE
-	Entries outside [effective_from, effective_to] → E422_UNPROCESSABLE
-	Values exceeding greenhouse guard rails → clamped (returned in warnings)
-	Overlapping irrigation jobs per controller are allowed (controller enforces lockout), but API MAY warn.
10.2 GET /api/v1/plans?greenhouse_id=... (supports ?active=true, ?sort=version desc, pagination)
10.3 GET /api/v1/plans/{plan_id}
10.4 DELETE /api/v1/plans/{plan_id}

11) Config Publish & Diff (`config` router)
11.1 POST /api/v1/greenhouses/{id}/config/publish (User JWT)
Materialize a new config version (rebuilt from DB tables) and invalidate controller caches.
Response 200
{ "config_version": 43, "controllers_notified": 2 }
11.2 GET /api/v1/greenhouses/{id}/config/diff?from=42&to=43
Human readable JSON diff for App.

12) Health & Metadata
12.1 GET /api/v1/health
200 OK with { "status": "ok", "time": "..." }
12.2 GET /api/v1/meta/sensor-kinds / /meta/actuator-kinds
Return allowed kinds from meta tables.

13) Validation Rules (Server Side)
-	Ownership: JWT user MUST own the greenhouse for any mutate/read ops (except public meta).
-	Climate uniqueness: Exactly 0 or 1 is_climate_controller=true per greenhouse. Setting a second → E409_CONFLICT.
-	Loop inclusion: include_in_climate_loop=true only for temperature/humidity and only on sensors on the climate controller.
-	Sensor ↔ Zone mapping: Enforce unique(zone_id, kind) in sensor_zone_map. Multiple zones MAY reference the same sensor_id.
-	Actuator channels: (controller_id, relay_channel) unique; ranges validated per controller profile.
-	State machine coverage: Server SHOULD warn if the 7×7 grid is not fully specified; fallback MUST exist or E422_UNPROCESSABLE on publish.
-	Plan clamping: API clamps setpoints against greenhouse guard rails; clamped values returned with warnings field.
-	ETag: Config/Plan GET returns ETag. If If-None-Match matches, return 304.

14) Endpoint Index (Quick Reference)
Group	Method	Path	Auth	Notes
Authentication	POST	/auth/register	none	Create user account
Authentication	POST	/auth/login	none	Issue JWT token
Onboarding	POST	/hello	none	Device polls until claimed
Onboarding	POST	/controllers/claim	JWT	Issues device_token
Onboarding	POST	/controllers/{controller_id}/token-exchange	none	One-time token issuance
Controllers	GET	/controllers/{controller_uuid}	JWT	Metadata
Controllers	PATCH	/controllers/{controller_uuid}	JWT	Update label/role
Controllers	POST	/controllers/{controller_uuid}/rotate-token	JWT	Reissue token
Controllers	DELETE	/controllers/{controller_uuid}	JWT	Revoke & delete
Config	GET	/controllers/{controller_uuid}/config	Device/JWT	ETag
Plan	GET	/greenhouses/{id}/plan/current	Device/JWT	ETag
Telemetry	POST	/telemetry/sensors	Device	Batch 10–15s
Telemetry	POST	/telemetry/actuators	Device	Edge on change
Telemetry	POST	/telemetry/status	Device	30s
Telemetry	POST	/telemetry/inputs	Device	Buttons
Telemetry	POST	/telemetry/batch	Device	Mixed
Greenhouse	CRUD	/greenhouses	JWT	Guard rails/baselines
Zone	CRUD	/zones	JWT	unique (gh, number)
Crop	CRUD	/crops	JWT
Planting	CRUD	/zone-crops	JWT	1 active/zone
Observation	CRUD	/zone-crop-observations	JWT
Sensor	CRUD	/sensors	JWT	Kind/scope validation
Mapping	CRUD	/sensor-zone-maps	JWT	unique (zone, kind)
Actuator	CRUD	/actuators	JWT	Relay channel unique
Fan group	CRUD	/fan-groups	JWT
Fan member	CRUD	/fan-groups/{id}/members	JWT
Button	CRUD	/controller-buttons	JWT
State machine	CRUD	/state-machine-rows	JWT	7×7 grid
Fallback	PUT	/state-machine-fallback/{gh_id}	JWT	Required
Plans	CRUD	/plans	Planner/JWT	Create/Read/Delete
Publish	POST	/greenhouses/{id}/config/publish	JWT	Bumps version
Diff	GET	/greenhouses/{id}/config/diff	JWT	Compare versions
Meta	GET	/meta/*	none	Enums, health

15) Examples (Selected Schemas)
15.1 Sensor (response)
{
  "id": "3b4d7c8a-...", "controller_id": "6f9a8b0e-...",
  "name": "RS485 T/RH #1",
  "kind": "temperature", "scope": "zone",
  "include_in_climate_loop": true,
  "modbus": { "slave_id": 1, "register": 30001 },
  "scale_factor": 0.1, "offset": 0.0, "poll_interval_s": 10
}
15.2 Actuator (response)
{
  "id": "af2a...", "controller_id": "6f9a8b0e-...",
  "name": "Fan #1", "kind": "fan", "relay_channel": 1,
  "min_on_ms": 60000, "min_off_ms": 60000, "fail_safe_state": "off",
  "zone_id": null
}
15.3 State machine row (response)
{
  "id": "smr1...", "greenhouse_id": "a6f7...",
  "temp_stage": 1, "humi_stage": -1,
  "must_on_actuators": ["af2a..."], "must_off_actuators": ["a777..."],
  "must_on_fan_groups": [ { "fan_group_id": "fg1...", "on_count": 1 } ]
}
Config & Plan response schemas: Full authoritative definitions are provided in the Configuration and Planning sections and are not duplicated here.

16) Logging & Auditing
-	Request IDs: Every request returns X-Request-Id.
-	Audit: Mutations on greenhouse/zones/sensors/actuators/state machine/plans SHOULD be logged with actor, before/after diff.
-	PII: Minimal; email in user account records only.

17) Open Questions
> **Open Questions Reference**: All open questions have been consolidated in [GAPS.md](./GAPS.md) for systematic resolution. See sections on API Design Questions, Security & Access Control, and Audit & Compliance.

**Version:** 2.0
**Audience:** Backend/API engineers, firmware developers, planning/LLM engineers, app developers, agentic coders
**Status:** Authoritative API & schema reference for MVP (HTTP ingest only)

---

## 1. Scope & Conventions

**Purpose.** Define complete, unambiguous REST API contracts, JSON/ID conventions, and inter‑component interfaces for MVP. This is the canonical source for schema generation (Pydantic/OpenAPI), validation, and contract tests.

**Canonical invariants (apply to *all* endpoints and payloads):**

* **Naming & IDs:** `snake_case` for fields; all entity IDs are **UUIDv4** (`format: uuid`), except **device\_name** which is the user‑facing controller identity:
  `device_name = "verdify-aabbcc"` where `aabbcc` = last 3 MAC bytes in **lowercase hex**, no separators. Regex: `^verdify-[0-9a-f]{6}$`.
* **Units & Time:** **Metric** only in DB and on wire (°C, kPa, L/min, hPa, m³/m³, etc.). Timestamps are **UTC ISO‑8601** with `Z` (e.g., `2025-08-12T18:00:00Z`).
* **Zones & Plantings:** Exactly **one active** planting per zone (1:1).
* **Sensors & Zones:** A sensor may be mapped to **zero, one, or multiple** zones; enforce with `sensor_zone_map` **unique (sensor\_id, zone\_id, kind)**.
* **Climate Loop:** Exactly **one** `is_climate_controller = true` per greenhouse; it must own climate actuators and have access to loop sensors (interior/exterior temp/humidity/pressure).
* **State Machine Grid:** `temp_stage ∈ [-3..+3] × humi_stage ∈ [-3..+3]` (49 cells). Each cell specifies **MUST\_ON**/**MUST\_OFF** actuator lists and optional **fan\_group on\_count**. A **fallback** row is required.
* **Fan Staging:** Fans grouped; **rotation** among group members; `on_count` = number of fans to engage for that group at current stage.
* **Guard Rails:** Greenhouse immutable min/max temp (°C) and min/max VPD (kPa). Plans cannot override; controller clamps.
* **LLM Plan:** Sets min/max temp/VPD, stage deltas/hysteresis/offsets, **irrigation/fertilization/lighting** schedules.
* **Irrigation Lockout:** Per controller, **only one** valve ON at a time; overlapping jobs are **FIFO queued**.
* **Manual Overrides:** Physical **cool/heat/humid** buttons can force a stage for a configured timeout.
* **Fallback:** If no valid plan entry for “now,” controller executes **baselines + guard rails** from config.
* **Auth:** Users via **JWT**; devices via long‑lived **device\_token** issued at claim and valid until controller deletion. TLS everywhere.
* **MVP Transport:** **HTTP ingest only** (no MQTT in MVP).
* **Versioning:** Config and plan endpoints use **ETag** for conditional GET (304 if unchanged).

---

## 2. Core JSON Schemas (conceptual overview)

> Authoritative, copy‑pasteable definitions are embedded in the OpenAPI 3.1 section below under `components/schemas`. This overview highlights key entities and invariants:

* **Greenhouse:** guard rails, baselines, location, `context_text`.
* **Zone:** unique `(greenhouse_id, zone_number)`, `location`, `context_text`.
* **Crop / ZoneCrop / Observation:** lifecycle recipe, 1 active planting/zone.
* **Controller:** `device_name` (claim ID), `is_climate_controller`.
* **Sensor:** `kind` (temperature, humidity, etc.), `scope` (zone/greenhouse/external), include\_in\_climate\_loop, polling/scale/offset, Modbus hints.
* **SensorZoneMap:** `(sensor_id, zone_id, kind)` mapping (multi‑zone supported).
* **Actuator:** `kind` (fan/heater/vent/fogger/irrigation\_valve/fertilizer\_valve/pump/light), min\_on/off, fail\_safe, optional `zone_id`.
* **FanGroup / Member:** fan staging/rotation grouping.
* **ControllerButton:** manual override (cool/heat/humid) → target stages + timeout.
* **StateMachineRow:** per greenhouse (49 rows + fallback) with MUST\_ON/MUST\_OFF and fan group `on_count`.
* **Config (config.json):** materialized snapshot per greenhouse, referenced by controllers (via device token), includes baselines, rails, stage thresholds/hysteresis, mapping tables, state machine rules, and controller‑scoped actuators.
* **Plan (plan.json):** setpoints (time‑series), irrigation/fertilization/lighting jobs.
* **Telemetry payloads:** `sensors`, `actuators` (edge events), `status`, `inputs` (button events), and `batch`.

---

## 3. OpenAPI Specification

The complete OpenAPI 3.1 specification is available in a separate file:

**📄 [openapi.yml](./openapi.yml)**

This specification includes:
- All endpoints with complete request/response schemas
- Authentication schemes (UserJWT, DeviceToken)
- Rate limiting headers and error responses
- ETag support for caching
- Comprehensive schema definitions
- Production-ready security configurations

The OpenAPI specification can be used for:
- Client code generation (TypeScript, Python, etc.)
- API documentation with Swagger UI
- Contract testing and validation
- Development tooling integration

---

## 4. Endpoint Tables (summary)

| Verb | Path                                        | Auth        | Idempotency                | Request                                      | Response                  | Status              | Notes                                                                                        |
| ---- | ------------------------------------------- | ----------- | -------------------------- | -------------------------------------------- | ------------------------- | ------------------- | -------------------------------------------------------------------------------------------- |
| POST | `/hello`                                    | None        | N/A                        | `HelloRequest`                               | `HelloResponse`           | 200/400             | Validates `device_name` regex; status-only provisioning poll.                                |
| POST | `/controllers/{controller_id}/token-exchange` | None      | Idempotent (201/200)       | `TokenExchangeRequest`                      | `TokenExchangeResponse`   | 201/200/400/404/409/422 | One-time token issuance + initial strong ETags.                                             |
| POST | `/controllers/claim`                        | UserJWT     | Optional `Idempotency-Key` | `ControllerClaimRequest`                     | `ControllerClaimResponse` | 201/400/401/404/409 | Issues `device_token` (valid until deletion). Enforces one climate controller per GH if set. |
| GET  | `/controllers/by-name/{device_name}/config` | DeviceToken | ETag (`If-None-Match`)     | —                                            | `ConfigPayload`           | 200/304/401/404     | Strong ETag `config:v<version>:<sha8>`.                                                       |
| GET  | `/controllers/{controller_id}/plan`         | DeviceToken | ETag                       | —                                            | `PlanPayload`             | 200/304/401/404     | Strong ETag `plan:v<version>:<sha8>`.                                                         |
| POST | `/greenhouses/{id}/config/publish`          | UserJWT     | Optional                   | `{dry_run?}`                                 | `ConfigPublishResult`     | 201/400/401/404/409 | Performs validations before publish.                                                         |
| GET  | `/greenhouses/{id}/config/diff`             | UserJWT     | N/A                        | —                                            | `ConfigDiff`              | 200/401/404         | –                                                                                            |
| POST | `/telemetry/sensors`                        | DeviceToken | Optional `Idempotency-Key` | `TelemetrySensors`                           | `IngestResult`            | 202/400/401         | Validates metric + UTC.                                                                      |
| POST | `/telemetry/actuators`                      | DeviceToken | Optional                   | `TelemetryActuators`                         | `IngestResult`            | 202/400/401         | Edge events only.                                                                            |
| POST | `/telemetry/status`                         | DeviceToken | Optional                   | `TelemetryStatus`                            | `IngestResult`            | 202/400/401         | 30s cadence recommended.                                                                     |
| POST | `/telemetry/inputs`                         | DeviceToken | Optional                   | `TelemetryInputs`                            | `IngestResult`            | 202/400/401         | –                                                                                            |
| POST | `/telemetry/batch`                          | DeviceToken | Optional                   | `TelemetryBatch`                             | `IngestResult`            | 202/400/401         | Gzipped body allowed.                                                                        |
| CRUD | `/greenhouses`, `/greenhouses/{id}`         | UserJWT     | Optional                   | `GreenhouseCreate/Update`                    | `Greenhouse`/List         | 200/201/204/...     | Unique `(owner_id, title)` optional; rails present.                                          |
| CRUD | `/zones`, `/zones/{id}`                     | UserJWT     | Optional                   | `ZoneCreate/Update`                          | `Zone`                    | 200/201/204         | Enforce unique `(greenhouse_id, zone_number)`.                                               |
| CRUD | Crops, ZoneCrops, Observations              | UserJWT     | Optional                   | As schemas                                   | Entities                  | …                   | Enforce 1 active ZoneCrop per zone.                                                          |
| CRUD | Controllers                                 | UserJWT     | Optional                   | `ControllerCreate/Update`                    | `Controller`              | …                   | Enforce climate singleton per GH.                                                            |
| CRUD | Sensors / SensorZoneMap                     | UserJWT     | Optional                   | `SensorCreate/Update`, `SensorZoneMapCreate` | Entities                  | …                   | Enforce unique `(sensor_id, zone_id, kind)`.                                                 |
| CRUD | Actuators                                   | UserJWT     | Optional                   | `ActuatorCreate`                             | `Actuator`                | …                   | –                                                                                            |
| CRUD | FanGroups/Members                           | UserJWT     | Optional                   | …                                            | …                         | …                   | –                                                                                            |
| CRUD | Buttons                                     | UserJWT     | Optional                   | `ControllerButtonCreate`                     | `ControllerButton`        | …                   | –                                                                                            |
| GET  | `/plans`                                    | UserJWT     | N/A                        | `greenhouse_id` query                        | `PlanList`                | 200                 | Read-only list of versions.                                                                  |

**Pagination & filters:** Lists accept `page` & `page_size`. Entity-specific filters can be added later (MVP keeps basic pagination).

---

## 5. Validation Rules (enforced at API boundary) {#validation-rules}

> **Validation Reference**: For complete validation rules and business invariants, see [Business Invariants in OVERVIEW.md](./OVERVIEW.md#business-invariants).

**Key API-specific enforcement points:**

* **Request validation**: All endpoints validate JSON schema, required fields, and data types before processing
* **Business logic validation**: Uniqueness constraints, cardinality rules, and state machine coverage checked during operations
* **Response codes**: Standard HTTP status codes for validation failures:
  - `400 Bad Request`: Malformed JSON, invalid UUIDs, wrong timestamp format, imperial units
  - `409 Conflict`: Uniqueness violations, cardinality conflicts, state machine coverage issues
  - `422 Unprocessable Entity`: Business logic violations, invalid references, constraint failures
* **ETag validation**: Strong ETags for configuration and plans with conditional requests (`If-None-Match`)
* **Authentication separation**: Strict separation between user JWT endpoints and device token endpoints

**Auth**

* User endpoints require **JWT**; controller endpoints require **DeviceToken** (long‑lived until deletion).
* On controller deletion, its token is **revoked** immediately.

---

## 6. Examples

### 6.1 cURL

**Hello**

```bash
curl -sS https://api.verdify.ai/v1/hello \
  -H 'Content-Type: application/json' \
  -d '{
    "device_name":"verdify-a1b2c3",
    "claim_code":"932611",
    "hardware_profile":"kincony_a16s",
    "firmware":"esphome-2025.8",
    "ts_utc":"2025-08-12T18:00:00Z"
  }'
```

**Claim (UserJWT)**

```bash
curl -sS -X POST https://api.verdify.ai/v1/controllers/claim \
  -H "Authorization: Bearer $USER_JWT" \
  -H 'Content-Type: application/json' \
  -d '{
    "device_name":"verdify-a1b2c3",
    "claim_code":"932611",
    "greenhouse_id":"9a94a0a7-d039-4d9b-86f2-46b1c7f7942c"
  }'
```

**Config GET with ETag (DeviceToken)**

```bash
curl -i https://api.verdify.ai/v1/controllers/by-name/verdify-a1b2c3/config \
  -H "X-Device-Token: $DEVICE_TOKEN" \
  -H 'If-None-Match: "config:v12:1a2b3c4d"'
```

**Telemetry sensors**

```bash
curl -sS -X POST https://api.verdify.ai/v1/telemetry/sensors \
  -H "X-Device-Token: $DEVICE_TOKEN" -H 'Content-Type: application/json' \
  -d '{
    "readings":[
      {"sensor_id":"3a...","kind":"temperature","value":23.4,"ts_utc":"2025-08-12T18:00:10Z"},
      {"sensor_id":"4b...","kind":"humidity","value":58.2,"ts_utc":"2025-08-12T18:00:10Z"}
    ]
  }'
```

**Publish config**

```bash
curl -sS -X POST https://api.verdify.ai/v1/greenhouses/9a94a0a7-d039-4d9b-86f2-46b1c7f7942c/config/publish \
  -H "Authorization: Bearer $USER_JWT" -d '{"dry_run":false}'
```

### 6.2 Minimal Postman collection (snippet)

```json
{
  "info": { "name": "Verdify MVP", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json" },
  "item": [
    {
      "name": "Hello",
      "request": { "method": "POST", "url": "{{base}}/v1/hello",
        "header": [{"key":"Content-Type","value":"application/json"}],
        "body": {"mode":"raw","raw":"{\"device_name\":\"verdify-a1b2c3\",\"claim_code\":\"932611\",\"hardware_profile\":\"kincony_a16s\",\"firmware\":\"esphome-2025.8\",\"ts_utc\":\"2025-08-12T18:00:00Z\"}"}
      }
    },
    {
      "name": "Config GET",
      "request": { "method": "GET", "url": "{{base}}/v1/controllers/by-name/verdify-a1b2c3/config",
        "header": [{"key":"X-Device-Token","value":"{{device_token}}"}]
      }
    }
  ],
  "variable": [
    {"key":"base","value":"https://api.verdify.ai"},
    {"key":"device_token","value":""}
  ]
}
```

---

## 7. Contract Tests (examples)

> Agentic coders: implement these as pytest + schemathesis or Dredd tests against the OpenAPI.

1. **Identity & format**

* POST `/hello` with `device_name="Verdify-A1B2C3"` → `E400_BAD_REQUEST` (regex is lowercase).
* POST `/telemetry/sensors` with `ts_utc="2025-08-12T18:00:00+02:00"` → `E400_BAD_REQUEST` (not Zulu).

2. **Uniqueness & singleton**

* Create two zones with same `(greenhouse_id, zone_number)` → second returns `E409_CONFLICT`.
* Set `is_climate_controller=true` on two controllers in same greenhouse → second returns `E409_CONFLICT`.

3. **State machine coverage**

* Publish config with only 45 grid rows or missing fallback → `published=false` and `errors` array includes `"STATE_GRID_INCOMPLETE"`; if `dry_run=false` then `E409_CONFLICT`.

4. **Sensor mappings**

* POST `/sensor-zone-map` duplicate `(sensor_id, zone_id, kind)` → `E409_CONFLICT`.

5. **ETag**

* GET `/controllers/{id}/plan` with matching `If-None-Match` → `304`.

6. **Telemetry acceptance**

* POST `/telemetry/actuators` with `state="ON"` (wrong case) → `E400_BAD_REQUEST`.
* POST `/telemetry/status` missing required `temp_stage` → `E400_BAD_REQUEST`.

7. **Plan invariants**

* Insert plan with irrigation jobs overlapping per controller; API responds `200` (accepted) but `warnings` field in plan validation endpoint (future) lists conflicts. (MVP: accept + warn.)

---

## 8. Inter‑Component Contracts (MVP)

* **Controller ⇄ API (DeviceToken):**

  * `GET /api/v1/controllers/by-name/{device_name}/config` (ETag).
  * `GET /api/v1/controllers/{controller_id}/plan` (ETag).
  * `POST /api/v1/telemetry/*` (HTTP only; gzip allowed).
* **App ⇄ API (UserJWT):**

  * CRUD for all configuration entities, publish/diff, plan list.

**Database anchoring:** API responses map 1:1 to tables from the DB spec (IDs always UUIDv4). `device_name` is not a DB PK; it’s a claim/display identity tied to the controller row.

**Realtime (future):** WebSockets/SSE for dashboards can be added later; not in MVP.

---

## 9. Algorithms / Pseudocode (validation highlights)

**State grid coverage check (publish):**

```pseudo
function validate_state_grid(rows):
  map = set()
  fallback_count = 0
  for r in rows:
    if r.is_fallback:
      fallback_count += 1
      continue
    assert -3 <= r.temp_stage <= 3
    assert -3 <= r.humi_stage <= 3
    key = (r.temp_stage, r.humi_stage)
    if key in map: error("DUPLICATE_STAGE_CELL")
    map.add(key)
  if len(map) != 49: error("STATE_GRID_INCOMPLETE")
  if fallback_count != 1: error("FALLBACK_MISSING_OR_DUPLICATE")
```

**Climate controller singleton (update/create):**

```pseudo
if payload.is_climate_controller == true:
  count = select count(*) from controller where greenhouse_id = GH and is_climate_controller = true and id != current_id
  if count > 0: reject E409_CONFLICT("CLIMATE_CONTROLLER_ALREADY_EXISTS")
```

**Sensor mapping uniqueness:**

```pseudo
unique_key = (sensor_id, zone_id, kind)
reject if key exists -> E409_CONFLICT("SENSOR_ZONE_MAP_DUP")
```

---

## 10. Implementation Guidance for Agentic Coder

**Step‑by‑step:**

1. **Generate code from OpenAPI 3.1**

   * Use FastAPI + Pydantic models auto‑generated from `components/schemas`.
   * Implement `UserJWT` and `DeviceToken` security dependencies.
   * Add ETag middleware/helper for config/plan endpoints.

2. **Validation middleware**

   * Enforce regex for `device_name`, UTC Zulu timestamps, unit sanity (numbers only, metric).
   * Centralize error responses with `error_code` enums (E400/E401/E404/E409…).

3. **CRUD scaffolding**

   * Implement all CRUD endpoints with DB constraints:

     * Unique `(greenhouse_id, zone_number)`.
     * Unique `(sensor_id, zone_id, kind)`.
     * Climate controller singleton.
   * Include pagination helpers (`page`, `page_size`).

4. **Publish pipeline**

   * Implement `/greenhouses/{id}/config/publish`:

     * Build `ConfigPayload` from DB joins.
     * Run **state grid** + **mapping** validations.
     * If `dry_run=true`, return `published=false` with errors/warnings + preview payload.
     * Else write snapshot, bump `version`, return payload + `version`.

5. **ETag endpoints**

   * Store latest `config_version` and `plan_version` per greenhouse.
   * Compute weak ETag `W/"config-version:<n>"`, `W/"plan-version:<n>"`.
   * Return `304` on match.

6. **Telemetry ingest**

   * Implement handlers for `/telemetry/*`:

     * Validate schemas and timestamp unit rules.
     * Write to TimescaleDB hypertables (per DB spec).
     * Return `IngestResult`.

7. **Auth lifecycle**

   * `POST /api/v1/controllers/claim` issues device\_token; store hashed token; revoke on controller deletion.

8. **Testing** (FastAPI Template Alignment)

**8.1 Testing Framework Setup**
* Use pytest with FastAPI TestClient for API testing (aligned with template)
* Configure test database with SQLModel and TimescaleDB
* Use httpx.AsyncClient for async endpoint testing
* Set up conftest.py with database fixtures and auth tokens

**8.2 Test Database Configuration**
```python
# conftest.py aligned with FastAPI template
import pytest
from sqlmodel import create_engine, Session, SQLModel
from testcontainers.postgres import PostgresContainer
from app.core.db import get_db

@pytest.fixture(scope="session")
def test_db():
    with PostgresContainer("timescale/timescaledb:latest-pg15") as postgres:
        engine = create_engine(postgres.get_connection_url())
        SQLModel.metadata.create_all(engine)
        yield engine

@pytest.fixture
def db_session(test_db):
    with Session(test_db) as session:
        yield session
```

**8.3 FastAPI TestClient Patterns**
* Override dependency injection for database and auth
* Use parametrized tests for endpoint validation
* Test OpenAPI schema generation and client compatibility
* Validate ETag caching behavior with conditional requests

**8.4 Contract Testing Suite**
* **OpenAPI Schema Validation**: Ensure all endpoints generate valid OpenAPI
* **Pydantic Model Tests**: Validate SQLModel <-> Pydantic serialization
* **Authentication Flow Tests**: JWT + DeviceToken schemes
* **Error Response Format**: StandardError schema compliance
* **Router Organization**: Verify all endpoints follow /api/v1/{router} pattern

**8.5 SQLModel Integration Tests**
* Test database model constraints and relationships
* Validate TimescaleDB time-series operations
* Test CRUD operations with type safety
* Verify foreign key constraints and cascading

**Implementation Guidelines**:
   * Use schemathesis/Dredd against this OpenAPI.
   * Implement contract tests listed above.
   * Add unit tests for validators (state grid coverage, singleton, mapping uniqueness).
   * Use pytest + FastAPI TestClient for all API testing.
   * Add integration tests with test containers for TimescaleDB.

9. **Examples & SDKs** (FastAPI Template Integration)

**9.1 Automatic Client Generation**
* Generate TypeScript client using `openapi-ts` (aligned with template frontend)
* Generate Python client using `openapi-python-client` for testing and scripts
* Configure automatic regeneration on OpenAPI schema changes
* Validate generated clients against FastAPI's OpenAPI output

**9.2 Frontend Integration (Next.js + TypeScript)**
```typescript
// client/index.ts - Generated from FastAPI OpenAPI
import { DefaultApi } from './sdk.gen';
import { Configuration } from './core';

const api = new DefaultApi(new Configuration({
  basePath: '/api/v1',
  headers: {
    'Authorization': `Bearer ${token}`
  }
}));

// Type-safe API calls with ETag support
const greenhouses = await api.getGreenhouses({
  headers: { 'If-None-Match': lastETag }
});
```

**9.3 ETag Caching Integration**
* Implement conditional requests with If-None-Match headers
* Cache responses based on ETag values in frontend state
* Support 304 Not Modified responses in generated clients
* Validate ETag behavior across all cacheable endpoints

**9.4 Error Handling Standardization**
```typescript
// Standardized error handling aligned with FastAPI HTTPException
interface ErrorResponse {
  error_code: string;
  message: string;
  details?: any;
}

// Type-safe error handling in generated client
try {
  await api.createGreenhouse(data);
} catch (error) {
  if (error.status === 422) {
    const errorResponse: ErrorResponse = error.body;
    // Handle validation errors with typed details
  }
}
```

**Implementation Guidelines**:
   * Use openapi-generator for TypeScript client with ETag support.
   * Configure automatic client regeneration in CI/CD pipeline.
   * Validate generated clients work with FastAPI development server.
   * Provide Python/TypeScript client generation using this OpenAPI.
   * Test all generated clients against contract test suite.

---

## End‑of‑Output Checklist

* [x] **OpenAPI compiles** (3.1, schemas referenced consistently).
* [x] All **required endpoints** present: onboarding, config publish/diff, config/plan GET with ETag, telemetry ingest, full CRUD, plan versions list.
* [x] **Security schemes** defined (JWT, DeviceToken) and applied.
* [x] **Validation rules** captured: uniqueness, regex, singleton, state grid, metric/UTC.
* [x] **Examples** provided (cURL, Postman snippet).
* [x] **Contract tests** enumerated with error codes.
* [x] HTTP ingest only (no MQTT); device tokens long‑lived until deletion.
* [x] Consistency with v2.0 invariants: snake\_case, UUIDs, device\_name format, metric units, UTC timestamps.
