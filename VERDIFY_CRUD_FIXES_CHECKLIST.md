# Verdify CRUD Fixes Checklist & Code Examples
*Critical fixes for Milestone 2 - CRUD Corrections*

## 🔧 Controllers CRUD Fixes

### Issue: Legacy relationship and owner_id references
**File:** `backend/app/crud/controller.py`

**Problem:**
```python
# BROKEN - uses non-existent relationship and owner_id
def list_controllers(session: Session, owner_id: str):
    return session.exec(
        select(Controller)
        .join(Controller.greenhouse)  # ❌ No relationship defined
        .where(Greenhouse.owner_id == owner_id)  # ❌ Field is user_id
    ).all()
```

**Fix:**
```python
# CORRECT - explicit join with proper field names
def list_controllers(session: Session, user_id: str):
    return session.exec(
        select(Controller)
        .join(Greenhouse, Controller.greenhouse_id == Greenhouse.id)  # ✅ Explicit join
        .where(Greenhouse.user_id == user_id)  # ✅ Correct field name
    ).all()
```

## 🔧 Sensors CRUD Fixes

### Issue: References to renamed fields and removed zone slot mapping
**File:** `backend/app/crud/sensors.py`

**Problem:**
```python
# BROKEN - uses old field name
def list_sensors_by_type(session: Session, sensor_type: str):
    return session.exec(
        select(Sensor).where(Sensor.type == sensor_type)  # ❌ Field renamed to 'kind'
    ).all()

# BROKEN - uses removed zone slot columns
def assign_sensor_to_zone_slot(session: Session, zone_id: str, sensor_id: str, slot: str):
    zone = session.get(Zone, zone_id)
    if slot == "temperature":
        zone.temperature_sensor_id = sensor_id  # ❌ Column removed
    # ... other slot assignments
```

**Fix:**
```python
# CORRECT - uses new field name
def list_sensors_by_kind(session: Session, sensor_kind: SensorKind):
    return session.exec(
        select(Sensor).where(Sensor.kind == sensor_kind)  # ✅ Correct field name
    ).all()

# CORRECT - uses SensorZoneMap association
def assign_sensor_to_zone(session: Session, zone_id: str, sensor_id: str, kind: SensorKind):
    from app.crud.sensor_zone_map import create_sensor_zone_mapping
    return create_sensor_zone_mapping(
        session=session,
        sensor_id=sensor_id,
        zone_id=zone_id,
        kind=kind
    )
```

## 🔧 State Machine CRUD Fixes

### Issue: Ownership validation doesn't throw on failure
**File:** `backend/app/crud/state_machine.py`

**Problem:**
```python
# BROKEN - validation result ignored
def create_state_machine_row(session: Session, user_id: str, greenhouse_id: str, data: dict):
    validate_user_owns_greenhouse(session, user_id, greenhouse_id)  # ❌ Result ignored
    # ... proceed with creation regardless
```

**Fix:**
```python
# CORRECT - raise on validation failure
def create_state_machine_row(session: Session, user_id: str, greenhouse_id: str, data: dict):
    if not validate_user_owns_greenhouse(session, user_id, greenhouse_id):  # ✅ Check result
        raise ValueError(f"User {user_id} does not own greenhouse {greenhouse_id}")
    # ... proceed with creation only if authorized
```

## 🔧 Climate CRUD Resolution

### Issue: References to non-existent models
**File:** `backend/app/crud/climate.py`

**Option A - Remove if not needed:**
```python
# If climate history isn't part of V2, remove the entire file
# and any imports/routes that reference it
```

**Option B - Implement missing models:**
```python
# Add to app/models/climate.py or appropriate file
class ZoneClimateHistory(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    zone_id: uuid.UUID = Field(sa_column=Column("zone_id", ForeignKey("zone.id", ondelete="CASCADE")))
    temperature: float | None = None
    humidity: float | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GreenhouseClimateHistory(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(sa_column=Column("greenhouse_id", ForeignKey("greenhouse.id", ondelete="CASCADE")))
    avg_temperature: float | None = None
    avg_humidity: float | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

## 🔧 Greenhouse Title/Name Mapping

### Issue: API uses 'title', DB uses 'name' column
**File:** `backend/app/models/greenhouses.py`

**Fix:**
```python
class Greenhouse(GreenhouseBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Map API field 'title' to DB column 'name'
    title: str = Field(
        max_length=200,
        sa_column=Column("name", String(200), nullable=False)  # ✅ Explicit column mapping
    )

    user_id: uuid.UUID = Field(
        sa_column=Column("user_id", ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    )
    # ... rest of fields
```

## 🧪 Testing Strategy

### Test Against Alembic-Created Database
```python
# In conftest.py or test setup
def test_database_engine():
    """Create test database using Alembic migrations, not create_all()"""
    from alembic.config import Config
    from alembic import command

    # Run migrations to create schema
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

    # Now run tests against properly migrated schema
```

### CRUD Integration Tests
```python
def test_controller_list_by_user(session, test_user, test_greenhouse):
    """Test controller listing uses correct joins and field names"""
    # Create controller in user's greenhouse
    controller = Controller(greenhouse_id=test_greenhouse.id, ...)
    session.add(controller)
    session.commit()

    # Test the fixed CRUD function
    controllers = list_controllers(session, user_id=test_user.id)
    assert len(controllers) == 1
    assert controllers[0].greenhouse_id == test_greenhouse.id

def test_sensor_kind_filtering(session):
    """Test sensor filtering uses 'kind' not 'type'"""
    sensor = Sensor(kind=SensorKind.TEMPERATURE, ...)
    session.add(sensor)
    session.commit()

    sensors = list_sensors_by_kind(session, SensorKind.TEMPERATURE)
    assert len(sensors) == 1
    assert sensors[0].kind == SensorKind.TEMPERATURE
```

## ✅ Validation Checklist

### Milestone 2 Exit Criteria:
- [ ] Controllers CRUD uses explicit joins, no relationship dependencies
- [ ] Controllers CRUD filters by `user_id` not `owner_id`
- [ ] Sensors CRUD uses `kind` field, not `type`
- [ ] Sensor zone mapping uses `SensorZoneMap`, not zone slot columns
- [ ] State machine ownership validation throws on unauthorized access
- [ ] Climate CRUD either removed or models implemented
- [ ] All CRUD imports resolve without missing model errors
- [ ] Unit tests pass against Alembic-created database schema

### Testing Commands:
```bash
# Test with proper database setup
cd backend
uv run alembic upgrade head
uv run pytest app/tests/crud/ -v

# Validate no import errors
uv run python -c "import app.crud; print('All CRUD imports successful')"
```

## 📋 Implementation Order

1. **Fix Greenhouse title mapping** (quick win)
2. **Update Controllers CRUD** (explicit joins)
3. **Update Sensors CRUD** (kind field, SensorZoneMap)
4. **Fix State machine ownership** (validation enforcement)
5. **Resolve Climate CRUD** (remove or implement)
6. **Run full test suite** against Alembic database
7. **Validate imports** across entire CRUD layer

---

*These fixes address the legacy CRUD paths that would break against the finalized schema, ensuring clean separation and proper field/table references.*
