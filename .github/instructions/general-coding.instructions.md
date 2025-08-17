---
applyTo: "**/*.py"
---
# General Coding Standards for Project Verdify Backend Refactoring

Follow these guidelines for all code changes:
- Align all models, routes, and features with the provided OpenAPI specification (see docs/openapi.yaml). Do not deviate from schemas like Greenhouse (add fields like min_temp_c), Sensor (use SensorKind enum), etc.
- Use SQLModel for database models with table=True, UUID primary keys (default_factory=uuid.uuid4), and cascading deletes (ondelete="CASCADE", passive_deletes=True).
- For FastAPI routes: Use Pydantic for request/response models, dependencies like get_current_user for auth, and tags from the spec (e.g., [CRUD]).
- Implement security: UserJWT (Bearer) for user endpoints, DeviceToken (X-Device-Token) for device ones.
- Handle errors with standardized ErrorResponse schema (error_code like E400_BAD_REQUEST).
- Project goals: Refactor existing files (e.g., app/models.py, api/routes/greenhouses.py) to match spec; add new features like telemetry ingestion with rate limiting and ETags for config/plan.
- Constraints: No new external deps without updating pyproject.toml; use existing libs (FastAPI, SQLModel, Alembic); ensure code is Python 3.12 compatible.
- Best practices: Short functions, type hints, docstrings referencing spec sections.
