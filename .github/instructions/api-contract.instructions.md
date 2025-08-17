---
applyTo: "**"
description: "Enforce strict OpenAPI contract across endpoints"
---

# Contract Fidelity

- **Request**: exact body shape and header names (`X-Device-Token`, `If-None-Match`, `Idempotency-Key`).
- **Response**: exact shapes; use `response_model` to enforce DTOs.
- **Status codes**: follow spec per path. Prefer `201` for creates, `204` for deletes, `304` for ETag match, correct 4xx codes for errors.
- **Pagination**: accept `page`, `page_size`; respond with `{data, page, page_size, total}`.
- **Errors**: return `ErrorResponse` with `error_code` enum.
- **Security**:
  - User endpoints → Bearer JWT.
  - Device endpoints → `X-Device-Token` (API key style). Validate and map to controller identity.
