# Verdify Backend — Copilot Global Instructions

These instructions apply to **all** backend work.

## Project Reality

- Python 3.12, FastAPI, SQLModel (with Pydantic), Alembic, PostgreSQL.
- Use **uv** for env & commands (`uv run ...`), not bare `python`/`pip`.
- Key paths:
  - API routers: `app/api/routes/*.py`
  - Core infra: `app/core/{config,db,security}.py`
  - Domain models: `app/models/*.py`  (**Do not** use `app/models.py`)
  - CRUD layer: `app/crud/*.py`
  - Tests: `app/tests/**`
  - Alembic migrations: `app/alembic/**`
- Running: backend dev server is `uv run fastapi dev app/main.py`; tests are `uv run pytest -q`.

## API Contract & DB

Treat the repo docs (in `requirements/`) as **source of truth**:
- `requirements/API.md`, `requirements/openapi.yml`, `requirements/DATABASE.md`
- Respect exactly:
  - Paths, methods, params, request/response bodies, headers
  - Security schemes: **UserJWT** (Authorization: Bearer), **DeviceToken** (`X-Device-Token`)
  - Error envelope `ErrorResponse` { `error_code`, `message`, `timestamp`, `request_id` }
  - Pagination envelope `{data, page, page_size, total}`
  - ETag + `If-None-Match` semantics (Config/Plan)
  - Idempotency-Key + telemetry rate‑limiting semantics
  - Field names & types
  - Normalized timestamps in UTC (RFC 3339/ISO 8601 with timezone)

## Conventions

- Full typing; avoid `Any`. Use `uuid.UUID` for IDs; use timezone‑aware `datetime` (UTC).
- **SQLModel/Pydantic** separation:
  - DB: `table=True` classes (`Greenhouse`, `Zone`, `Controller`, `Sensor`, `Actuator`, `FanGroup`, `Plan`, `ConfigSnapshot`, `ZoneCrop`, `Observation`, State machine rows/fallback, etc.)
  - Wire DTOs: `*Create`, `*Update`, `*Public` or `*List`
- Pagination query: `?page=&page_size=`; normalize invalid input to safe defaults.
- Errors: always return the standard `ErrorResponse` envelope; never leak internals.
- **Auth**:
  - 401 if unauthenticated; 403 if authenticated but unauthorized (ownership boundary).
  - Device flows must accept `X-Device-Token`. Never mix device tokens with user JWT.
- **Uniqueness** constraints enforced in DB + business logic (zone_number per greenhouse; sensor `(slave, reg)` per controller; actuator relay channel per controller; single active plan per greenhouse; single active zone-crop per zone).
- **ETag**:
  - Strong ETag format: `config:v<version>:<sha8>` or `plan:v<version>:<sha8>`
  - Honor `If-None-Match` with `304`.
- **Idempotency / Telemetry**:
  - Respect `Idempotency-Key` (store hash of body + key; re‑serve response).
  - Token bucket or equivalent; reply 429 with informative headers when throttled.
- **Security**: never echo secrets; scrub device tokens in logs; no `eval()` or shelling out in request handlers.

## Tests & Definition of Done

- Add/extend **Pytest** coverage (unit + route tests) under `app/tests`.
- Keep/extend the E2E suite `end_to_end_v3.py`. A PR is **ready** only if:
  1) Unit & route tests pass, 2) E2E passes (no critical failures), 3) Coverage not lower.
- Every schema change ships with an Alembic migration (no mutation of past revisions).
- Update OpenAPI schema + docs if wire shapes change (avoid unless necessary).

## Implementation Guardrails for Copilot

- Prefer **minimal diffs**; preserve interfaces.
- For new endpoints: Add DTOs → CRUD → Router → Tests → Docs → (optional) E2E touchpoint.
- For telemetry and config/plan endpoints: re‑check idempotency, ETag, pagination invariants.
- **Never** create or use `app/models.py`. All models live in `app/models/*.py`.
- Use `app/api/deps.py` for dependencies (DB, auth, pagination).
- Use `sqlmodel.Session` from `app/core/db.py`. No ad‑hoc engines.
- Return DTOs that **hide** DB‑internal fields (e.g., `user_id`, `params`, `updated_at`, `is_active` when required).

## Common Tasks (expectations)

- CRUD endpoint:
  - Request/response models with Pydantic (`*Create`, `*Update`, `*Public`).
  - DB layer via SQLModel, unique constraints mirrored in DB & validated in code (raise 409/422).
  - Route tests under `app/tests/api/test_<resource>.py`.
- Alembic migration:
  - Autogenerate, review, add **unique constraints**, **indexes**, **FKs** as needed.
  - Upgrade & downgrade paths must be correct.
- Telemetry:
  - Validate enums strictly; reject unknown actions w/ 422.
  - Enforce device token requirement; 401/403 for failures.
- Plans & Config:
  - Single active plan per greenhouse; payload.version must match entity version on PATCH.
  - Config device fetch supports `ETag` and `If-None-Match`.

