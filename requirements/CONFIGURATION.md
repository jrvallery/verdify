# Configuration Management Specification

## Overview

This section defines how configuration is created, stored, versioned, delivered, and applied. It is both a product UX guide and a technical contract for the API and controller firmware. All names use snake_case. IDs are UUIDv4 except the user facing device identifier device_name = verdify-aabbcc (MAC suffix with last 3 bytes, lowercase hex).

## Related Documentation

- [API Specification](./API.md) - REST API endpoints and schemas
- [Database Schema](./DATABASE.md) - Data model and constraints
- [Controller Specification](./CONTROLLER.md) - ESPHome firmware requirements
- [Authentication Specification](./AUTHENTICATION.md) - Security and authorization
- [Project Overview](./OVERVIEW.md) - System architecture and goals

## 1. UX Flow (Onboarding → Configure → Publish)

### 1.1 Configuration Schema Structure

> **Schema Reference**: For the complete and authoritative configuration schema, see [ConfigPayload in API.md](./API.md#configpayload).
>
> The configuration structure includes:
> - **Greenhouse**: Guard rails, baselines, and thresholds
> - **Controllers**: Device mapping and climate control flags
> - **Sensors**: Physical and virtual sensor definitions
> - **Actuators**: Relay and device control mappings
> - **State Machine**: Climate control rules grid with fallback
> - **Fan Groups**: Staging and rotation configuration

### 1.2 User Flow

1. **Create Greenhouse** → Define guard rails (min/max temp, VPD)
2. **Add Controllers** → Claim devices, designate climate controller
3. **Configure Sensors** → Map physical sensors to zones
4. **Configure Actuators** → Assign relays to heating/cooling/ventilation
5. **Define State Machine** → Create 49-cell grid (7×7 stages) + fallback
6. **Publish Configuration** → Generate versioned config with ETag

---

## 2. Configuration Pipeline Specification

**Scope:** Defines how Verdify builds a canonical `config.json` from database tables, validates it, publishes versions with strong ETags, serves them to controllers, and computes diffs.

### 2.1 Source of Truth (SoT)

**Canonical invariants:** snake_case, UUIDv4 IDs, device_name = `verdify-aabbcc`, metric units, UTC timestamps, one climate controller per greenhouse.

**Tables involved (read-only for build):**

| Table | Purpose | Key columns used |
|-------|---------|------------------|
| `greenhouse` | Guard rails & climate baselines | `id`, `title`, `min_temp_c`, `max_temp_c`, `min_vpd_kpa`, `max_vpd_kpa`, `baseline_temp_stages`, `baseline_humi_stages`, `context_text` |
| `controller` | Device inventory | `id`, `greenhouse_id`, `device_name`, `is_climate_controller`, `model`, `fw_version`, `hw_version` |
| `sensor_kind_meta` | Units & value types | `kind`, `value_type`, `unit` |
| `sensor` | Physical/virtual sensors | `id`, `controller_id`, `kind`, `scope`, `include_in_climate_loop`, `modbus_slave_id`, `modbus_reg`, `scale_factor`, `offset`, `poll_interval_s` |
| `sensor_zone_map` | Sensor ↔ zone linkage (M:N) | `sensor_id`, `zone_id`, `kind` |
| `zone` | Physical zones | `id`, `greenhouse_id`, `zone_number`, `location`, `context_text` |
| `actuator_kind_meta` | Lookup | `kind` |
| `actuator` | Relays/actuators | `id`, `controller_id`, `kind`, `relay_channel`, `min_on_ms`, `min_off_ms`, `fail_safe_state`, `zone_id` |
| `fan_group` | Fan group headers | `id`, `controller_id`, `name` |
| `fan_group_member` | Fan group membership | `fan_group_id`, `actuator_id` |
| `controller_button` | Manual overrides | `id`, `controller_id`, `button_kind`, `stage_override`, `timeout_s` |
| `state_machine_row` | Climate rules grid | `id`, `greenhouse_id`, `temp_stage`, `humi_stage`, `must_on_actuators[]`, `must_off_actuators[]`, `fan_on_counts` (map `fan_group_id`→int), `is_fallback` |
| `config_snapshot` *(new)* | Published snapshots | `id`, `greenhouse_id`, `version`, `etag`, `snapshot_json`, `created_at` |

### 2.2 Materialization Process (Deterministic Build)

**Goal:** Produce a byte‑for‑byte stable JSON (`config.json`) for a greenhouse and each controller's filtered view, with a monotonically increasing `version` and a strong `etag` (SHA‑256 of canonical JSON bytes).

**Algorithm (pseudo-code):**

> **Algorithm Reference**: For the complete configuration build algorithm, see [DATABASE.md - Configuration Build Pipeline](./DATABASE.md#algorithms-functions).

**Process Overview:**
1. Load all related entities (greenhouse, controllers, sensors, actuators, fan groups, buttons, state rules)
2. Sort collections deterministically by device_name, ID, or stage coordinates
3. Serialize to canonical JSON structure matching OpenAPI ConfigPayload schema
4. Generate strong ETag from canonical bytes (excluding `generated_at`)
5. Store snapshot with version, ETag, and full JSON payload

**Strong ETag:** `config:v<version>:<sha8>` where `<sha8>` = first 8 hex chars of SHA-256 over canonical JSON excluding `generated_at`.

### 2.3 Publishing Workflow

**Call sequence:** `POST /greenhouses/{id}/config/publish` → server performs checks; on success, materializes & stores snapshot; returns `{version, etag}`.

**Validation rules:**
- Climate singleton check (exactly one `is_climate_controller=true` per greenhouse)
- State grid completeness (49 rows + 1 fallback)
- Actuator/sensor references valid
- Guard rail compliance

**Response codes:**
- `201 Created` on success: `{"greenhouse_id": "...", "version": 12, "etag": "config:v12:1a2b3c4d", "generated_at": "..." }`
- `422 Unprocessable Entity` on validation failure

### 2.4 Controller Delivery

**Endpoints:**
- User view: `GET /greenhouses/{id}/config` → full snapshot, `ETag: "config:v<version>:<sha8>"`.
- Controller view: `GET /controllers/by-name/{device_name}/config` → filtered view (own sensors/actuators only).

**Controller Fetch Flow:**
1. Headers: supports If-None-Match: "<etag>".
2. 200 OK: returns config.json; headers: ETag: "config:v<version>:<sha8>", Cache-Control: no-store.
3. 304 Not Modified: if ETag matches current server config.

**Controller Processing:**
1. Compare ETag with stored version.
2. Persist config.json to flash with config_version and ETag.
3. Reload climate loop with new configuration.

## 3. Validation Rules

> **Validation Reference**: For complete validation rules, see [Business Invariants in DATABASE.md](./DATABASE.md#validation-functions-triggers).

Key validation points:
- **Climate singleton**: Exactly one controller per greenhouse with `is_climate_controller=true`
- **State grid coverage**: 49 cells (7×7) + 1 fallback row
- **Actuator references**: All state machine actuator IDs must exist
- **Sensor zone mapping**: Zone-scoped sensors must have valid zone links
- **Guard rail compliance**: Baselines must fall within greenhouse guard rails

## 4. Caching and ETags

**ETag Policy:**
- Strong ETags for content integrity: `"config:v<version>:<sha8>"`
- Computed from canonical JSON (sorted keys, no whitespace)
- Excludes volatile fields like `generated_at`

**Caching Strategy:**
- Controllers use If-None-Match for conditional fetches
- Server responds 304 Not Modified when content unchanged
- No aggressive caching (Cache-Control: no-store)

---

*This specification is part of the Project Verdify requirements suite. For implementation details, see the related documentation linked above.*
