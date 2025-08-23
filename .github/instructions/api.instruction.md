---
applyTo: "app/api/**"
---

# API Routes — Copilot Instructions

- **Routers** live under `app/api/routes/*.py`. Group endpoints by domain (e.g., greenhouses.py, zones.py).
- Always add route‑level tests in `app/tests/api/`:
  - Success paths
  - Ownership boundaries (403/404)
  - Uniqueness & validation errors (409/422)
- Use dependencies from `app/api/deps.py`:
  - DB session, auth (userJWT / device token), pagination.
- Response models must be DTOs; hide internal columns.
- Lists return `{data, page, page_size, total}`.
- For ETag routes, set `ETag` header, and 304 on `If-None-Match`.
