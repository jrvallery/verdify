---
description: "Verdify backend - SQLModel conventions and guardrails (foreign-key-only mapping, modular models, safe imports)."
applyTo: "app/models/**/*.py,app/crud/**/*.py"
---
# Verdify SQLModel Instructions (Foreign‑Key‑Only Mapping)

> **Scope:** These instructions apply to `app/models/**/*.py` and `app/crud/**/*.py` in this repository.
> **Goal:** Keep tests and runtime stable by **not using `Relationship()`** in SQLModel; rely on **explicit foreign keys** and **manual queries** instead.

---

## 🔒 Non‑Negotiables (Copilot must follow these)

1. **Do NOT add `Relationship()` anywhere.**
   Use only foreign keys defined with `sa_column=Column(ForeignKey(...))`.
2. **Avoid runtime cross‑module imports in model code.**
   For type hints, use `from __future__ import annotations` and guard imports with `if TYPE_CHECKING:`.
3. **Association/link tables are plain SQLModel tables.**
   Composite primary keys + FKs. No relationships or back_populates.
4. **Keep `app/models/__init__.py` import order stable (see below).**
5. **Alembic owns schema.**
   Do **not** call `SQLModel.metadata.create_all()` in application code. It is allowed only in test fixtures.

---

## Why this policy

String-based `Relationship()` forward references across modules are brittle with SQLModel and can cause mapper errors like:

```
sqlalchemy.exc.InvalidRequestError: Mapper 'Mapper[Sensor(sensor)]' has no property 'controller'
```

Removing relationships and navigating via explicit queries avoids registry timing problems, circular imports, and inconsistent back‑populate definitions—while preserving referential integrity via proper foreign keys.

---

## Model Patterns

### 1) Entities use explicit foreign keys (no relationships)

```python
from __future__ import annotations
import uuid
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, ForeignKey

class SensorBase(SQLModel):
    sensor_index: int = Field(description="0-based index within the controller")
    location: str = Field(max_length=200)
    sensor_type: str = Field(max_length=100)
    kind: "SensorKind"
    scope: "SensorScope"

class Sensor(SensorBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    controller_id: uuid.UUID = Field(
        sa_column=Column(
            "controller_id",
            ForeignKey("controller.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    # 🚫 No Relationship() here
```

**Rules**
- Always include `ondelete="CASCADE"` (or the intended policy) and `nullable` on FKs.
- Primary keys are `uuid.UUID` via `default_factory=uuid.uuid4` (unless composite PK tables).

### 2) Association (link) tables

- Place in `app/models/links.py` (or the most relevant domain module if unavoidable).
- Use composite PKs, explicit FKs, and **no** relationships.

```python
# app/models/links.py
from __future__ import annotations
import uuid
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, ForeignKey
from app.models.enums import SensorKind

class SensorZoneMap(SQLModel, table=True):
    __tablename__ = "sensor_zone_map"

    sensor_id: uuid.UUID = Field(
        sa_column=Column(
            "sensor_id",
            ForeignKey("sensor.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    zone_id: uuid.UUID = Field(
        sa_column=Column(
            "zone_id",
            ForeignKey("zone.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    kind: SensorKind = Field(primary_key=True)
    # 🚫 No Relationship() here
```

### 3) Forward typing & imports

- Start every model file with:
  ```python
  from __future__ import annotations
  from typing import TYPE_CHECKING
  ```
- For type hints only:
  ```python
  if TYPE_CHECKING:
      from .controllers import Controller
  ```
- Never rely on runtime cross‑module imports inside model modules—there are no relationship targets to resolve.

---

## Aggregator Import Order (keep deterministic)

Maintain this import ordering in `app/models/__init__.py` so all table classes register predictably:

```
enums  -> users -> greenhouses -> controllers -> sensors
-> actuators -> crops -> telemetry -> config -> auth -> links
```

> Do **not** import from `app.api`, `app.crud`, or other layers in model modules to avoid cycles.

---

## Querying Without Relationships

Replace implicit navigation with explicit queries in CRUD/service code.

```python
from sqlmodel import select, Session
from app.models.controllers import Controller
from app.models.sensors import Sensor

def get_sensor_controller(session: Session, sensor: Sensor) -> Controller | None:
    return session.get(Controller, sensor.controller_id)

def list_controller_sensors(session: Session, controller_id: str) -> list[Sensor]:
    return session.exec(
        select(Sensor).where(Sensor.controller_id == controller_id)
    ).all()
```

M:N via link tables:

```python
from sqlmodel import select
from app.models.links import SensorZoneMap
from app.models.greenhouses import Zone

def zones_for_sensor(session: Session, sensor_id: str) -> list[Zone]:
    zone_ids = session.exec(
        select(SensorZoneMap.zone_id).where(SensorZoneMap.sensor_id == sensor_id)
    ).all()
    if not zone_ids:
        return []
    return session.exec(select(Zone).where(Zone.id.in_(zone_ids))).all()
```

---

## Testing & Migrations

- **Tests**: In pytest fixtures for ephemeral DBs, after `import app.models`:
  ```python
  from sqlmodel import SQLModel
  SQLModel.metadata.create_all(engine)
  ```
  Runtime code must **not** call `create_all()`; Alembic owns schema in all non‑test environments.

- **Alembic**: Add/modify columns and FKs via migrations. Keep table/column names stable.

---

## File Layout

```
app/models/
  enums.py
  users.py
  greenhouses.py
  controllers.py
  sensors.py
  actuators.py
  crops.py
  telemetry.py
  config.py
  auth.py
  links.py      # association tables only
  __init__.py   # ordered aggregator
```

Table names default to the class name in snake_case. For link tables, set `__tablename__` explicitly (e.g., `sensor_zone_map`).

---

## Pydantic / SQLModel Notes

- Prefer Pydantic v2 conventions for new models. If forward references are needed for **pure Pydantic** models, you may call `model_rebuild()` in the aggregator **after** imports (rare with this pattern).
- Keep `Field(...)` arguments consistent across the repo (`max_length`, `description`, `example` where used).

---

## Pagination Aliases (`Paginated[T]`)

- Import once per model module when you need typed paginated responses:

```python
from app.utils_paging import Paginated

SensorsPaginated = Paginated["SensorPublic"]
ControllersPaginated = Paginated["ControllerPublic"]
```

Use these aliases to keep OpenAPI and tests aligned with prior monolith behavior.

---

## DO / DON’T Cheat‑Sheet

**DO**
- Use `sa_column=Column(ForeignKey("table.id", ondelete="CASCADE"), nullable=...)` for all FKs.
- Use composite PKs for link tables and explicit `__tablename__`.
- Write explicit `select(...)` queries in CRUD to traverse via FK(s).
- Preserve the aggregator import order and don’t import from higher layers.

**DON’T**
- ❌ Add `Relationship()` or `back_populates` anywhere.
- ❌ Add runtime cross‑module imports in model code (type‑hints must be behind `TYPE_CHECKING`).
- ❌ Call `SQLModel.metadata.create_all()` outside tests.
- ❌ Introduce dynamic/late relationship wiring files (e.g., `_relationships.py`).

---

## Templates (Copilot should prefer these)

**Entity with FK**
```python
class Equipment(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(
        sa_column=Column(
            "controller_id",
            ForeignKey("controller.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    name: str = Field(max_length=100)
```

**Link Table**
```python
class FanGroupMember(SQLModel, table=True):
    __tablename__ = "fan_group_member"

    fan_group_id: uuid.UUID = Field(
        sa_column=Column(
            "fan_group_id",
            ForeignKey("fan_group.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    actuator_id: uuid.UUID = Field(
        sa_column=Column(
            "actuator_id",
            ForeignKey("actuator.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
```

---

## Sanity Checks (Copilot should keep these green)

- Import smoke test:
  ```python
  import app.models
  from sqlalchemy.orm import configure_mappers
  configure_mappers()  # should not raise
  ```
- FastAPI health endpoint returns 200 with TestClient.
- `pytest` runs without mapper configuration errors.

---

## Escalation Path (if someone requests relationships)

If a change appears to require `Relationship()`:
1) Add/verify the necessary FKs.
2) Provide/extend CRUD helpers to traverse explicitly via queries.
3) If design pressure persists, propose a design note in `docs/`—but **do not** add relationships in this codebase.

---
