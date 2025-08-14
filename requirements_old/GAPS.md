# Project Verdify - Open Questions and Implementation Gaps

## Overview

This document consolidates all open questions, implementation gaps, and design decisions that need resolution across the Project Verdify specification suite. Questions are organized by category and priority to facilitate systematic resolution during implementation.

## Related Documentation

- [System Overview](./OVERVIEW.md) - Project goals and architecture
- [API Specification](./API.md) - REST endpoints and schemas
- [Database Schema](./DATABASE.md) - Data model and constraints
- [Controller Specification](./CONTROLLER.md) - ESPHome firmware requirements
- [Planning Engine](./PLANNER.md) - AI-assisted plan generation
- [Authentication](./AUTHENTICATION.md) - Security and authorization
- [Configuration Management](./CONFIGURATION.md) - Config publishing workflows

---

## 1. API Design Questions

### 1.1 Rate Limiting & Performance
**Source**: [API.md - Open Questions](./API.md#open-questions)

- **Rate limits**: Do we enforce per device and per user limits (e.g., POST /telemetry/* ≤ 10 req/min; config/plan pulls ≤ 6 req/min with backoff)? Required values?
- **Unified Batch Adoption**: Should controllers prefer /telemetry/batch always to reduce connections, or keep per type endpoints for simplicity?

### 1.2 Security & Access Control
**Source**: [API.md](./API.md), [AUTHENTICATION.md](./AUTHENTICATION.md)

- **Planner auth**: Should the Planning Engine use a service JWT with scoped permissions (plans only), or a separate API key?
- **Roles & permissions (post MVP)**: Do we need user roles (e.g., owner, viewer) and resource scoping (per greenhouse) for the App? If yes, define JWT roles claim and authorization matrix
- **Multi-owner access model**: When should we introduce multi-owner or role-based permissions (viewer/operator/admin), and how should existing greenhouses migrate?
- **Token rotation policy**: Beyond deletion/revocation, should device tokens expire periodically (e.g., 180 days) with a grace window and App-initiated rotation workflow?

### 1.3 Audit & Compliance
**Source**: [API.md - Open Questions](./API.md#open-questions)

- **Audit depth**: Which fields must be captured in immutable audit logs (esp. guard rails, state machine, plan changes)? Retention period?

---

## 2. State Machine & Control Logic

### 2.1 State Grid Completeness
**Source**: [API.md](./API.md), [DATABASE.md](./DATABASE.md)

- **Partial state machine**: If the 7×7 grid is incomplete but a fallback exists, do we allow publish (warn only) or block until full coverage?
- **State machine fan rules**: Is one default_fan_on_count per state sufficient, or do we require per-group on_count always? (Current schema supports both via state_machine_fan_rule)

### 2.2 Plan Expiry & Fallback
**Source**: [API.md](./API.md), [AUTHENTICATION.md](./AUTHENTICATION.md)

- **Plan expiry default**: If a plan expires without a new one, is a 24 h fallback window acceptable before alerting?
- **Plan expiry window**: What is the maximum allowed gap before a plan is considered stale (e.g., 24 hours) and the controller should rely exclusively on failsafe rails?

---

## 3. Controller Firmware Questions

### 3.1 Storage & Performance
**Source**: [CONTROLLER.md - Open Questions](./CONTROLLER.md#open-questions)

- **Plan storage size**: Is 10 day/30 min horizon final? If increased (e.g., 15 days), confirm LittleFS size allocation (proposal: reserve 512 KB)
- **OTA cadence**: After initial provisioning, should the controller attempt OTA updates automatically when a new firmware is published (nightly window)? If yes, add OTA section (signed binaries)

### 3.2 Hardware Control Logic
**Source**: [CONTROLLER.md - Open Questions](./CONTROLLER.md#open-questions)

- **Lighting power budgets**: Can multiple lighting actuators run concurrently? If the site has limited power, we may need a lighting lockout similar to irrigation
- **Button behavior**: On press and hold, should we extend the override timeout or restart it?
- **Enthalpy gate tuning**: Should the enthalpy decision include a threshold band (e.g., only switch path if |delta| > 1.0 kJ/kg) to prevent flapping?

### 3.3 Resource Contention
**Source**: [AUTHENTICATION.md - Open Questions](./AUTHENTICATION.md#open-questions)

- **Resource contention**: May lighting and irrigation overlap if they share power constraints/circuits? If not, specify a global controller-level lock or schedule conflict rules

---

## 4. Planning Engine & LLM Integration

### 4.1 Model Configuration
**Source**: [PLANNER.md - Open Questions](./PLANNER.md#open-questions)

- **Model & Budget**: Which LLM (OpenAI/Grok/other) and max tokens per plan? Are we okay with ~3–5K tokens total (prompt + output) per greenhouse per compute cycle?
- **Horizon & Granularity**: Confirm default horizon (10 days) and step (30 minutes). Should night hours be coarser (e.g., 60 min) to reduce output size?

### 4.2 Control Algorithm Tuning
**Source**: [PLANNER.md - Open Questions](./PLANNER.md#open-questions)

- **Dehumid Thresholding**: Should the enthalpy delta split point be fixed in config (e.g., 0.0 kJ/kg) or tunable by the plan (e.g., enthalpy_switch_kjkg per setpoint row)?

---

## 5. Database & Data Management

### 5.1 Schema Design
**Source**: [DATABASE.md - Open Questions](./DATABASE.md#open-questions)

- **Plan entities**: Keep both plan_irrigation.fertilizer and separate plan_fertilization, or single table with kind ENUM ('water','fert')? (Both currently present)

### 5.2 Data Retention & Performance
**Source**: [DATABASE.md](./DATABASE.md), [PLANNER.md](./PLANNER.md)

- **Retention/compression**: Confirm default retention windows for telemetry (e.g., 180 days) and whether to enable compression in MVP
- **Retention/Compression**: Confirm raw retention (proposal: 90 days) and compression start (proposal: 7 days). Different policies for status vs sensors?

---

## 6. Telemetry & Monitoring

### 6.1 Alert Thresholds
**Source**: [PLANNER.md - Open Questions](./PLANNER.md#open-questions)

- **Missing Telemetry Alerts**: What thresholds (e.g., no status for >120 s) should trigger an alert? Per greenhouse configurable?
- **Skew Policy**: Acceptable maximum device clock skew before clamping (proposal: 5 minutes)? Should server reject beyond a hard limit?

---

## 7. Future Protocol Support

### 7.1 MQTT Migration
**Source**: [AUTHENTICATION.md - Open Questions](./AUTHENTICATION.md#open-questions)

- **MQTT enablement timing**: If MQTT is enabled later, should we require a separate device credential pair for MQTT (username/password) or reuse the same device_token?

---

## Priority Classification

### High Priority (MVP Blocking)
- Plan expiry default and window (affects fallback behavior)
- State machine fan rules (affects configuration schema)
- Plan storage size (affects firmware requirements)
- Lighting power budgets (affects hardware control logic)

### Medium Priority (MVP Nice-to-Have)
- Rate limiting policies (affects API stability)
- Audit depth requirements (affects compliance)
- Enthalpy gate tuning (affects control precision)
- Missing telemetry alert thresholds (affects monitoring)

### Low Priority (Post-MVP)
- Multi-owner access model (affects user management)
- OTA cadence policies (affects maintenance)
- MQTT protocol migration (affects scalability)
- Token rotation policies (affects security)

---

## Resolution Process

1. **Technical Review**: Each question should be reviewed by relevant domain experts
2. **Decision Documentation**: Decisions should be recorded with rationale and alternatives considered
3. **Specification Updates**: Resolved questions should result in updates to relevant specification documents
4. **Implementation Tracking**: Changes should be tracked through implementation phases

---

*This document is part of the Project Verdify requirements suite. All questions should be resolved systematically to ensure consistent implementation across components.*
