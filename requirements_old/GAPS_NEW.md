# Known Gaps & Future Enhancements

## Overview

This document identifies internal inconsistencies, gaps in coverage, and opportunities for improvement in the Project Verdify MVP specification. It provides a comprehensive review focused on contract consistency, implementation readiness, and future-proofing considerations.

## Related Documentation

- [API Specification](./API.md) - REST API endpoints and schemas
- [Authentication Specification](./AUTHENTICATION.md) - Security and authorization
- [Controller Specification](./CONTROLLER.md) - ESPHome firmware requirements
- [Configuration Management](./CONFIGURATION.md) - Device configuration workflows
- [Database Schema](./DATABASE.md) - Data model and constraints
- [Project Overview](./OVERVIEW.md) - System architecture and goals

## Executive Summary

The specification is well-structured, comprehensive, and aligned with the project's MVP goals for an AI-powered greenhouse system. It provides a solid foundation for implementation with clear schemas, OpenAPI YAML, endpoint tables, validation rules, examples, and contract tests. The focus on normalization (3NF), metric units, UTC timestamps, and business invariants ensures consistency and safety.

**Overall Assessment**: 85-90% ready for development; fixes identified below would bring it to 100%.

### Strengths

- ✅ **Strong Consistency**: Snake_case uniformly applied; UUIDv4 for IDs; well-defined enums
- ✅ **Comprehensive Validation**: Covers uniqueness, ranges, business logic with precise pseudocode
- ✅ **OpenAPI YAML Completeness**: All required endpoints with security schemes and reusable parameters
- ✅ **Practical Examples**: cURL/Postman snippets and contract tests validate against schemas
- ✅ **Inter-Component Clarity**: Unambiguous pseudocode for data flows and HTTP-only MVP notes

## 🔴 High-Severity Issues (Fix Before Implementation)

### 1. Telemetry Wire Format Diverges Across Documents

**Issue**: OpenAPI and implementation sections use different schemas and field names.

#### Where Found
- **OpenAPI Section**: Uses `controller_id`, `device_name`, string enum `state: "on"|"off"`
- **Telemetry & Analytics Section**: Uses `time` + `sensors[]` with `unit` per item, boolean `state`, nested objects

#### Impact
Client/firmware and server can't both pass contract tests; analytics schemas won't match ingest.

#### Recommended Fix
**Adopt OpenAPI as authoritative** and align all sections:

```yaml
# Keep OpenAPI payloads as-is
TelemetryActuators:
  properties:
    state:
      type: string
      enum: ["on", "off"]  # Keep string enum

# Make controller_id optional for security
TelemetrySensors:
  properties:
    controller_id:
      type: string
      format: uuid
      nullable: true  # Optional - derived from token
```

### 2. Hello vs Controllers/Claim Flow Conflicts

**Issue**: Bootstrap flow has conflicting token issuance patterns.

#### Where Found
- **OpenAPI `/hello`**: Returns only status `pending|claimed`
- **Controller spec**: Shows `/hello` returning `device_token` and controller IDs
- **OpenAPI `/controllers/claim`**: Issues device_token (UserJWT required)

#### Impact
Security ambiguity; devices could self-provision without user claim.

#### Recommended Fix
- **Keep `/hello`** unauth and never return tokens
- **Keep `/controllers/claim`** as only token issuer
- Update Controller boot flow:
  1. `POST /hello` → `{status: "pending"}`
  2. Human calls `/controllers/claim` → issues token
  3. Device retries until token available

### 3. Config Payload Structure & Naming Diverge

**Issue**: Multiple config schemas with different field names and structures.

#### Where Found
- **OpenAPI**: Uses `version`, `baselines`, `rails`, array of objects for fan groups
- **Config Pipeline**: Uses `config_version`, nested `guard_rails`, map for fan counts

#### Impact
Controllers fail schema validation; ETag calculation unstable.

#### Recommended Fix
**Standardize on OpenAPI schema**:

```yaml
ConfigPayload:
  properties:
    version: number  # Not config_version
    baselines: object  # Not nested under greenhouse
    rails: object  # Not guard_rails
    state_rules:
      properties:
        grid:
          items:
            properties:
              must_on_fan_groups:
                type: array  # Not map
                items:
                  properties:
                    fan_group_id: string
                    on_count: number
```

### 4. ETag Semantics Inconsistent

**Issue**: Weak vs strong ETag usage conflicts.

#### Where Found
- **OpenAPI**: Shows weak ETags `W/"config-version:<n>"`
- **Config Pipeline**: Mandates strong ETag with SHA-256

#### Impact
Caching bugs, unnecessary downloads, version mismatch debugging issues.

#### Recommended Fix
**Use strong ETags consistently**:

```http
ETag: "config:v<version>:<sha256-8>"
Last-Modified: <RFC1123>
```

### 5. Humidity/VPD Unit System Conflicts

**Issue**: Mixed RH percentage and VPD kPa usage.

#### Where Found
- **OpenAPI baselines**: Defines `rh_pct` hysteresis
- **Controller & Planning**: Computes from VPD (kPa) with `humi_hysteresis_kpa`

#### Impact
Controller ignores RH hysteresis or computes on wrong units.

#### Recommended Fix
**Standardize on VPD end-to-end**:

```yaml
ConfigPayload:
  properties:
    baselines:
      properties:
        vpd_thresholds:  # Replace humi_thresholds
          type: object
          properties:
            minus3: { type: number }  # kPa
            # ... other stages
        hysteresis:
          properties:
            temp_c: { type: number, default: 0.5 }
            vpd_kpa: { type: number, default: 0.1 }  # Replace rh_pct
```

## 🟠 Medium-Severity Issues (Close Before Codegen)

### 6. Actuator & Sensor Naming Drift

**Issue**: Inconsistent kind names between schemas and examples.

#### Examples
- `ActuatorKind` has `fogger`, examples use `"humidifier"`
- `SensorKind` has `air_pressure`, examples show `"pressure"`
- Energy kinds are `"kwh"` and `"power"` (units not explicit)

#### Recommended Fix
- Use **`fogger`** consistently
- Use **`air_pressure`** consistently  
- Consider unit-explicit names: `energy_kwh`, `power_w`

### 7. Plan Job Addressing Inconsistent

**Issue**: Mixed addressing schemes for different job types.

#### Where Found
- `irrigation` & `fertilization`: Use `zone_id` + `controller_id`
- `lighting`: Uses `actuator_id`

#### Recommended Fix
**Make all job targets actuator-centric**:

```yaml
PlanPayload:
  properties:
    irrigation:
      items:
        required: [ts_utc, actuator_id, duration_s]
        properties:
          actuator_id: { type: string, format: uuid }
          zone_id: { type: string, format: uuid, nullable: true }  # For analytics
```

### 8. Status Code Inconsistencies

**Issue**: Endpoint documentation shows conflicting HTTP codes.

#### Examples
- `/greenhouses/{id}/config/publish`: Table shows 201, prose shows 200

#### Recommended Fix
- **201 Created**: When new published snapshot created
- **200 OK**: For dry_run operations

### 9. State Machine Fallback Incomplete

**Issue**: Fallback configuration lacks fan group control.

#### Current State
`ConfigPayload.state_rules.fallback` only includes actuator lists.

#### Recommended Fix
Add fan group staging to fallback:

```yaml
fallback:
  properties:
    must_on_fan_groups:
      type: array
      items:
        properties:
          fan_group_id: string
          on_count: number
```

### 10. Unit Profile Contradicts Metric-Only Invariant

**Issue**: `Greenhouse.unit_profile` enum suggests imperial support.

#### Current State
```yaml
unit_profile:
  type: string
  enum: [metric, imperial]
  default: metric
```

#### Recommended Fix
**For MVP**: Restrict to metric only or mark as UI-only field.

## 🟡 Nice-to-Have Improvements

### 11. Missing API Features

#### Rate Limiting & Throttling
- **Gap**: Mentioned in conventions but not in OpenAPI
- **Add**: 429 response examples, `Retry-After` headers, per-device limits

#### Pagination & Filtering
- **Gap**: Basic page/size only, no filters or sorting
- **Add**: `?kind=temperature` for sensors, `?sort=created_at desc` for plans

#### Observation Image Uploads
- **Gap**: Schema has `image_url` but no upload endpoint
- **Add**: `POST /observations/{id}/upload-url` for presigned URLs

### 12. Error Handling Improvements

#### Structured Error Details
**Current**: Freeform `details` object
**Improvement**: Define ErrorDetails schema:

```yaml
ErrorDetails:
  type: object
  properties:
    field: string
    value: any
    constraint: string
```

### 13. Security Enhancements

#### Token Rotation
**Add**: `POST /controllers/{id}/rotate-token` for compromise recovery

#### Device Path Simplification  
**Add**: `GET /controllers/me/plan` using token identity instead of path parameter

### 14. Data Quality Improvements

#### Geolocation Validation
**Add**: Range constraints for latitude (-90..90) and longitude (-180..180)

#### Sensor Value Types
**Expand**: `{enum: [float, int, bool, uint32, uint64]}` for specialized sensors

#### Claim Code Format
**Standardize**: Choose 6-digit numeric or base-32 format with clear regex

## Implementation Recommendations

### Phase 1: Critical Fixes (Before Development)
1. ✅ Align telemetry schemas across all documents
2. ✅ Fix hello/claim bootstrap flow
3. ✅ Standardize config payload structure  
4. ✅ Implement strong ETag policy
5. ✅ Convert to VPD-only humidity control

### Phase 2: Medium Priority (Before Codegen)
1. ⚠️ Standardize actuator/sensor naming
2. ⚠️ Unify plan job addressing
3. ⚠️ Fix status code inconsistencies
4. ⚠️ Complete fallback configuration
5. ⚠️ Resolve unit profile handling

### Phase 3: Quality of Life (Post-MVP)
1. ℹ️ Add comprehensive rate limiting
2. ℹ️ Implement advanced filtering/pagination
3. ℹ️ Add image upload workflows
4. ℹ️ Enhance error detail structure
5. ℹ️ Add security token rotation

## Contract Test Additions

### Telemetry Alignment Tests
```javascript
// Enforce string enum for actuator state
POST /telemetry/actuators with state=true → E400_BAD_REQUEST

// Reject old nested JSON format
POST /telemetry/status with nested structure → E400_SCHEMA
```

### Config Payload Tests
```javascript
// Reject RH percentage if migrated to VPD
POST /config with hysteresis.rh_pct → E422_UNITS

// Require fan groups in fallback
POST /config with incomplete fallback → E422_STATE_GRID
```

### Bootstrap Flow Tests
```javascript
// Hello should never include tokens
GET /hello → response excludes device_token

// Claim idempotency
POST /controllers/claim (duplicate) → same token
```

### ETag Behavior Tests
```javascript
// Consistent hash for identical content
POST /config (identical) → same <sha8> in ETag

// Version increments appropriately
POST /config (different) → incremented version
```

## Future Considerations

### Post-MVP Features
1. **Multi-tenant Permissions**: User roles (owner/viewer/operator) and resource scoping
2. **Advanced Scheduling**: Conflict resolution for shared power circuits
3. **MQTT Integration**: Separate credentials or token reuse decision
4. **Plan Expiry Windows**: Maximum staleness before failsafe activation
5. **Audit Logging**: Enhanced tracking with minimal PII

### Scalability Concerns
1. **Config/Plan Size**: ESP32 storage limits for large configurations
2. **Telemetry Volume**: High-frequency data compression strategies
3. **Database Performance**: Indexing strategy for time-series data
4. **API Rate Limits**: Per-controller and per-user quotas

### Integration Points
1. **Weather Services**: External climate data integration
2. **Analytics Platform**: Business intelligence data pipelines
3. **Mobile Notifications**: Push notification infrastructure
4. **Third-party Sensors**: Non-ESPHome device integration

---

*This analysis is part of the Project Verdify requirements suite. Address high-severity issues before implementation begins to ensure contract consistency and reduce development risks.*
