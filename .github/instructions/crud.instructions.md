---
applyTo: "app/crud/**"
---

# CRUD — Copilot Instructions

- Keep functions small and explicit: `get|list|create|update|delete`.
- Enforce ownership boundaries at query (filter by `user_id`/ownership).
- Raise `HTTPException(status_code=409/422)` for uniqueness/validation errors.
- Return DTOs (convert from SQLModel entities), never raw DB models.
- Use transactions for multi‑write invariants (plans, zone‑crop active flags).
