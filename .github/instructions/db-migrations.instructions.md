---
applyTo: "**"
description: "Safe Alembic migration patterns"
---

# Alembic

- Never edit an existing revision; create a new one per schema change.
- Use autogenerate but inspect diffs; add `op.create_index`, `unique=True`, and FKs with `ondelete`.
- Provide upgrade & downgrade.
- Data migrations: write idempotent SQL/ORM code guarded by existence checks.
- Test: `uv run alembic upgrade head` on a fresh DB; ensure app boots.
