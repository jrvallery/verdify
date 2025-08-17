---
mode: 'agent'
model: GPT-4o
tools: ['codebase', 'terminal']
description: 'Implement a REST endpoint from Verdify OpenAPI'
---

Use the OpenAPI spec in this workspace to implement one endpoint end-to-end (router, CRUD, DTOs, tests), adhering to:

- [../instructions/api-contract.instructions.md](../instructions/api-contract.instructions.md)
- [../instructions/backend.instructions.md](../instructions/backend.instructions.md)
- [../instructions/tests.instructions.md](../instructions/tests.instructions.md)

## Inputs
- Endpoint path: ${input:path}
- Method: ${input:method}
- Success model name: ${input:response_model_name}
- Error cases to cover: ${input:error_cases}

## Task
1) Locate or create router under `app/api/routes/<resource>.py`. Add FastAPI route:
   - Security deps (UserJWT or DeviceToken as per spec).
   - `response_model` set to DTO matching spec.
   - Validate query/path/body per spec (including enums and formats).

2) CRUD:
   - Implement or extend `app/crud/<resource>.py` functions.
   - Use `sqlmodel.Session` from the project DB helpers. Keep router thin.

3) DTOs:
   - If needed, add/update DTOs in `app/models.py` to match the wire schema naming & shapes in the spec.

4) Tests:
   - Add API tests to `app/tests/api/routes/test_<resource>.py`.
   - Cover success + all declared error variants and pagination when relevant.

5) Run:
   - `uv run pytest -q`
   - `scripts/format.sh && scripts/lint.sh` (if present)

## Constraints
- Do not change unrelated public endpoints.
- Keep models backwards compatible unless migration is required (then use the migration prompt).
- Use precise field names/types per spec.

## Acceptance
- Tests added and passing; endpoint returns exact shapes and status codes.
- OpenAPI served by the app shows the new endpoint and correct schemas (if the app auto-generates).
