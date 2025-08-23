---
applyTo: "app/models/**"
---

# Models — Copilot Instructions

- **Do not** create or modify `app/models.py`. Use separate files per domain in `app/models/*.py`.
- SQLModel table classes: `table=True`. Primary keys as `uuid.UUID`.
- Create matching DTOs (`*Create`, `*Update`, `*Public`).
- Add `__tablename__` explicitly and indexes/uniques mirroring business rules:
  - `(greenhouse_id, zone_number)` unique
  - `(controller_id, modbus_slave_id, modbus_reg)` unique
  - `(controller_id, relay_channel)` unique
  - Single active plan per greenhouse; single active zone‑crop per zone enforced via partial index or code + transaction.
- Timestamps are UTC aware `datetime`.
