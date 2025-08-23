# Verdify MVP – Worklog

Time-stamped notes per task. Timestamps are UTC (ISO-8601 with Z).

## 2025-08-21T00:00:00Z — T00 Repo Sanity & Scaffolding
- Created docs scaffolding: `docs/runbook/worklog.md`, `docs/runbook/manifest.json`, `docs/test-reports/`, `docs/log-samples/`.
- Added `backend/.env.example` with required environment variables (no secrets).
- Verified FastAPI app factory mounts routers under `/api/v1` and health endpoint available at `/api/v1/health`.
- Ensured pytest/dev tools present in `backend/pyproject.toml` (pytest, pytest-asyncio, testcontainers, coverage).
- Added `backend/tests/conftest.py` to set safe local env for tests.

Notes:
- Settings load env using `app/core/config.py` model_config; tests set minimal env via conftest.

## 2025-08-21T00:20:00Z — T02 Database DDL & Alembic Migrations
- Confirmed presence of Timescale core migration `app/alembic/versions/ab12cd34ef56_t02_timescale_core_ddl.py` creating extensions, meta tables, and hypertables.
- Added migration test `backend/tests/test_db_migration.py` using `timescale/timescaledb:latest-pg15` to run `alembic upgrade head` and assert key tables/hypertables exist.

## 2025-08-21T00:40:00Z — T03 Core App, Errors, and Logging
- Added tests for meta sensor kinds and standardized error envelope: `backend/tests/test_meta_and_errors.py`.
- Registered RequestValidationError handler in `app/main.py` to return standardized ErrorResponse for 422s.
