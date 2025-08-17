---
applyTo: "**"
description: "Testing patterns & expectations"
---

# Tests

- Tests live in `app/tests/**`. For each new route:
  - Unit tests for CRUD logic.
  - API tests for all HTTP statuses defined in the spec (success + failure paths).
- Use factory helpers/fixtures when available; otherwise create minimal seed data in setup.
- Ensure JWT/device token auth paths are covered.
- CI acceptance: `uv run pytest -q` must pass.
