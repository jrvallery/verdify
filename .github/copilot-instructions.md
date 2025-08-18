# Verdify Backend — Copilot Global Instructions

These instructions describe how to contribute code, tests, and docs for Verdify's FastAPI backend. Apply to **all** backend work.

DO NOT USE models.py.  All models are located in the `app/models/` directory and are organized into separate files.

## Tech & Repository Reality

- Python 3.12, FastAPI, SQLModel (with Pydantic), Alembic, PostgreSQL.
- Package/runtime via `uv` (use `uv run ...`), not bare `python`/`pip`.
- Tree of interest:
  - API routers: `app/api/routes/*.py`
  - Core infra: `app/core/{config,db,security}.py`
  - Domain models: `app/models/*.py` (SQLModel + DTOs)
  - CRUD layer: `app/crud/*.py`
  - Tests: `app/tests/**`
  - Alembic: `app/alembic/**`

## API Contract & Spec

- The “to‑be” API and database schema are defined by the API requirements doc `requirements/API.md`, the OpenAPI v3.1 spec `requirements/openapi.yml`,  and `requirements/DATABASE.md` which are all provided in this repo’s context. Treat these as **source of truth** for:
  - Paths, methods, params, request/response bodies, headers
  - Security schemes: **UserJWT** (bearer), **DeviceToken** (`X-Device-Token`)
  - Error envelope (`ErrorResponse`) and error codes
  - Pagination contract (`Paginated` or `*List` shapes)
  - ETag & `If-None-Match` semantics for Config/Plan
  - Idempotency-Key & telemetry rate‑limiting semantics
  - Field names
  - Database table schemas, columns, and relationships
- When adding/altering endpoints, keep wire shapes **exact** (field names, casing, types). Prefer server 4xx/5xx code paths that return `ErrorResponse`.

## Conventions

- **Typing** everywhere; no `Any` unless unavoidable. Use `uuid.UUID` for IDs, `datetime` (UTC) for timestamps.
- **Pydantic/SQLModel models**:
  - DB tables: `table=True` classes (e.g., `Greenhouse`, `Zone`, …)
  - Wire DTOs: `*Create`, `*Update`, `*Public`/`*List`
- **DB migrations**: every schema change must ship with an Alembic revision. Never mutate an existing revision.
- **Security**:
  - Distinguish **user** auth (JWT) vs **device** auth (`X-Device-Token` dep). Don’t couple them.
  - Return `401` for unauthenticated, `403` for unauthorized.
- **Pagination**:
  - Query params: `page`, `page_size`
  - Return `{data, page, page_size, total}` for paginated lists.
- **Errors**:
  - Always return the standard `ErrorResponse` envelope with `error_code`, `message`, `timestamp`, `request_id`.
- **ETag**:
  - Strong ETag format per spec: `config:v<version>:<sha8>` or `plan:v<version>:<sha8>`.
  - Honor `If-None-Match` with `304 Not Modified` when appropriate.
- **Rate limiting & idempotency** (telemetry):
  - Respect `Idempotency-Key`: dedupe exact repeat bodies (store key hash + result).
  - Enforce request token-bucket with safe defaults; fail with `429` and informative headers.

## Work Style

- Small, atomic PRs, each with:
  - Tests (unit + route tests) and migrations (if schema changes)
  - Update of OpenAPI (if generated) and docs, if applicable
- Keep `app/models.py` coherent until we explicitly split into modules. If split is needed, keep import paths stable and provide a migration.
- Use scripts in `/scripts` when present: `format.sh`, `lint.sh`, `test.sh`.
- Prefer `sqlmodel.Session` and the project’s DB session helpers from `app/core/db.py`.
- Use `app/api/deps.py` for dependencies (auth, DB, pagination).
