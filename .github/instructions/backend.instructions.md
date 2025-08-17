---
applyTo: "**"
description: "Backend style: FastAPI + SQLModel + Alembic + Postgres"
---

# Backend Conventions

- **Routers** live in `app/api/routes/*.py`. Add `APIRouter`, include tags, `responses` stubs, security deps, and explicit `response_model`.
- **CRUD layer** is in `app/crud/*.py`. Keep routers thin: parameter handling + orchestration only.
- **SQLModel**:
  - Foreign keys define `ondelete="CASCADE"` where parent removal should cascade.
  - Use `Relationship(..., sa_relationship_kwargs={"passive_deletes": True})`.
  - Avoid N+1: use `selectinload` when list endpoints include children.
- **Transactions**: Keep each request scoped to a short transaction; commit once; rollback on exceptions.
- **Validation**: prefer DTO classes (`*Create`/`*Update`) with Pydantic `Field()` constraints matching the spec (min/max/enum).
- **Timestamps**: always UTC (`datetime.now(timezone.utc)`).
