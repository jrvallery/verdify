# Mode: CRUD Endpoint

## Goal
Add or update a REST endpoint under `app/api/routes/` with full contract, tests, and docs.

## Steps
1) Confirm request/response DTOs and path from `requirements/openapi.yml`.
2) Add DTOs (`*Create`, `*Update`, `*Public`) and table model if needed.
3) Add CRUD functions; enforce uniqueness & boundaries.
4) Add router handlers; return DTOs; ensure pagination envelope for lists.
5) Add route tests in `app/tests/api/`.
6) Update OpenAPI if needed and docs in `requirements/API.md`.
7) Run: `uv run pytest -q` and ensure E2E is still green.

## Output
- Diff of added/changed files.
- Pytest summary.
- Next steps or issues (if any).
