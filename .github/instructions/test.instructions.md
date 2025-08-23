---
applyTo: "app/tests/**"
---

# Tests — Copilot Instructions

- Prefer Pytest. Organize by domain.
- Cover success, error, and boundary cases.
- Keep E2E `end_to_end.py` green. PRs must not introduce critical failures.
- Use `uv run pytest -q`; target minimum coverage not to regress.
- Add negative tests for invalid enums, duplicate resources, auth failures.
