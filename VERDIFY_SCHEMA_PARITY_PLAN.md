# Verdify Schema Parity & API Freeze Plan
*Generated: August 18, 2025*

## Executive Summary

**Status:** Schema/model drift identified that will cause runtime failures in production
**Impact:** Blocks frontend development until resolved
**Timeline:** 6 milestones, with Milestones 1-3 being critical blockers
**Strategy:** Systematic alignment of DB schema, SQLModel classes, and OpenAPI V2 DTOs

## Critical Issues Identified

### 🚨 Milestone 1 Blockers (Schema/Model Parity)

1. **Greenhouse `title`/`name` Mismatch**
   - API uses `title` (OpenAPI spec), DB uses `name` column
   - Will cause missing column errors on CRUD operations

2. **ENUM Case & Value Drift**
   - Models: lowercase enums (`zone`, `greenhouse`, `external`)
   - DB: UPPERCASE enums (`ZONE`, `GREENHOUSE`, `EXTERNAL`)
   - Different value sets between code and migrations

3. **Missing Plan Schema Fields**
   - Models expect: `is_active`, `effective_from`, `effective_to`, `updated_at`
   - DB migration: doesn't include these fields
   - Missing partial unique index for active plans

4. **Table Naming Inconsistency**
   - Models: `zone_crop`, `zone_crop_observation`
   - DB: `zonecrop`, `zonecropobservation`

5. **Missing Constraints**
   - Config snapshot uniqueness: `(greenhouse_id, version)`
   - Idempotency key uniqueness: `(key, controller_id)`
   - Controller climate controller partial unique index

### 🚨 Milestone 2 Blockers (CRUD Corrections)

1. **Controllers CRUD Legacy References**
   - Uses non-existent `Controller.greenhouse` relationship
   - References `owner_id` instead of `user_id`

2. **Sensors CRUD Outdated Logic**
   - Still uses `Sensor.type` (renamed to `kind`)
   - Zone slot mapping logic for removed columns

3. **State Machine Security Gap**
   - Ownership validation doesn't throw on failure

4. **Climate CRUD Dead References**
   - References non-existent `ZoneClimateHistory`/`GreenhouseClimateHistory`

### 🚨 Milestone 3 Blockers (API Conformance)

1. **DTO Compliance**
   - Ensure all routes return correct `*Public` DTOs
   - Hide internal fields per OpenAPI spec

2. **Controller Exposure Rules**
   - `ControllerPublic` requires non-null `greenhouse_id`
   - Filter unclaimed controllers from public APIs

## Execution Strategy

### Testing Philosophy
**CRITICAL:** Run tests against Postgres created via Alembic migrations only, not `create_all()`. This is the only way to catch schema/model drift.

### Migration Strategy
**Recommended:** Convert PostgreSQL ENUMs to TEXT with app-level validation for easier iteration.

## Milestone Breakdown

### Milestone 1: Schema/Model Parity ⚠️ BLOCKER
**Goal:** Make DB schema and SQLModel classes 1:1 with OpenAPI V2 DTOs

**Tasks:**
1. Map Greenhouse `title` → DB column `name` (SQLModel change only)
2. Convert ENUMs to TEXT strategy (new Alembic migration)
3. Add missing Plan/Config/Idempotency constraints (new Alembic migration)
4. State machine cleanup (new Alembic migration)
5. Crops table naming parity (new Alembic migration)
6. Controller climate uniqueness fix (new Alembic migration)

**Exit Criteria:** pytest passes with Alembic-created database only

### Milestone 2: CRUD Corrections ⚠️ BLOCKER
**Goal:** Remove/repair code paths that break against finalized schema

**Tasks:**
1. Fix Controllers CRUD joins & owner filtering
2. Update Sensors CRUD to use `kind` and `SensorZoneMap`
3. Fix State machine ownership validation
4. Remove or implement Climate History models

**Exit Criteria:** No dead imports or attribute errors in CRUD layer

### Milestone 3: API Route Conformance ⚠️ BLOCKER
**Goal:** Ensure every route returns correct `*Public` DTOs

**Tasks:**
1. Audit all routes for correct return models
2. Implement Controller exposure rules
3. Validate device onboarding flows

**Exit Criteria:** OpenAPI docs match actual responses; contract tests pass

### Milestone 4: Telemetry + Idempotency (Important)
**Goal:** Make telemetry ingestion safe and exactly-once

**Tasks:**
1. Wire idempotency flow on telemetry endpoints
2. Add periodic cleanup for expired keys

### Milestone 5: Plan & Config Publishing (Important)
**Goal:** Plans/configs behave as specified

**Tasks:**
1. Implement activate plan workflow
2. Complete config snapshot publishing

### Milestone 6: CI & Documentation (Recommended)
**Goal:** Prevent regressions and smooth FE integration

**Tasks:**
1. Update CI to test against Postgres + Alembic
2. Add OpenAPI validation
3. Document DB/ENUM strategy

## Quick Reference: Pinned Issues

- ❌ Greenhouse `title` vs DB `name` mapping
- ❌ ENUM case mismatch (lower vs UPPER) + different value sets
- ❌ Crops table naming (`zone_crop*` vs `zonecrop*`)
- ❌ Plan fields missing in DB (`is_active`, timestamps)
- ❌ Missing uniqueness constraints (config, idempotency)
- ❌ State machine JSON fields vs old join tables
- ❌ Controllers CRUD relationship dependencies
- ❌ Sensors CRUD `type` → `kind` + zone mapping
- ❌ Climate CRUD dead model references

## Frontend Green-Light Criteria

**Milestones 1-3 MUST be complete** before frontend integration:
- ✅ All schema/model alignment issues resolved
- ✅ CRUD layer cleaned of legacy references
- ✅ API routes return consistent `*Public` DTOs
- ✅ 100% test pass rate against Alembic-created database
- ✅ OpenAPI contract validated against actual responses

**Result:** Stable API contract that frontend can build against without surprises.

## Next Steps

1. **Generate Alembic migration skeletons** for Milestone 1
2. **Execute Milestones 1-3 in sequence** (blockers)
3. **Validate with full test suite** against real Postgres
4. **Green-light frontend development** once blockers resolved
5. **Complete Milestones 4-6** for operational readiness

---

*This plan addresses the schema/model drift identified in the bundle review and provides a clear path to API stability for frontend development.*
