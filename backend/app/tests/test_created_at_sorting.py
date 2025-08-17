"""
Test created_at sorting for sensors and zones.
"""
import time
import uuid

from sqlmodel import Session, select

from app.models import Controller, Greenhouse, Sensor, User, Zone
from app.models.enums import LocationEnum, SensorKind, SensorScope


def test_sensor_created_at_sorting(db: Session):
    """Test that sensors can be sorted by created_at field."""

    # Create test data
    unique_email = f"sensor_sort_test_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=unique_email,
        hashed_password="fake_hash",
        full_name="Sensor Sort Test User",
    )
    db.add(user)
    db.flush()

    greenhouse = Greenhouse(
        title="Sensor Sort Test Greenhouse",
        description="Testing sensor sorting",
        user_id=user.id,
    )
    db.add(greenhouse)
    db.flush()

    controller = Controller(
        greenhouse_id=greenhouse.id,
        device_name="verdify-test-sort-001",
        name="Test Controller for Sensor Sort",
        location="Test Location",
    )
    db.add(controller)
    db.flush()

    # Create first sensor
    sensor1 = Sensor(
        controller_id=controller.id,
        name="First Sensor",
        kind=SensorKind.TEMPERATURE,
        scope=SensorScope.ZONE,
        include_in_climate_loop=True,
    )
    db.add(sensor1)
    db.commit()

    # Small delay to ensure different created_at times
    time.sleep(0.01)

    # Create second sensor
    sensor2 = Sensor(
        controller_id=controller.id,
        name="Second Sensor",
        kind=SensorKind.HUMIDITY,
        scope=SensorScope.ZONE,
        include_in_climate_loop=True,
    )
    db.add(sensor2)
    db.commit()

    # Test ascending order (created_at)
    sensors_asc = db.exec(
        select(Sensor)
        .where(Sensor.controller_id == controller.id)
        .order_by(Sensor.created_at.asc())
    ).all()

    assert len(sensors_asc) == 2
    assert sensors_asc[0].id == sensor1.id  # First created should be first
    assert sensors_asc[1].id == sensor2.id  # Second created should be second
    assert sensors_asc[0].created_at <= sensors_asc[1].created_at

    print(
        f"✓ Sensors ascending sort: {sensors_asc[0].name} ({sensors_asc[0].created_at}) → {sensors_asc[1].name} ({sensors_asc[1].created_at})"
    )

    # Test descending order (-created_at)
    sensors_desc = db.exec(
        select(Sensor)
        .where(Sensor.controller_id == controller.id)
        .order_by(Sensor.created_at.desc())
    ).all()

    assert len(sensors_desc) == 2
    assert sensors_desc[0].id == sensor2.id  # Most recent should be first
    assert sensors_desc[1].id == sensor1.id  # Oldest should be second
    assert sensors_desc[0].created_at >= sensors_desc[1].created_at

    print(
        f"✓ Sensors descending sort: {sensors_desc[0].name} ({sensors_desc[0].created_at}) → {sensors_desc[1].name} ({sensors_desc[1].created_at})"
    )


def test_zone_created_at_sorting(db: Session):
    """Test that zones can be sorted by created_at field."""

    # Create test data
    unique_email = f"zone_sort_test_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=unique_email, hashed_password="fake_hash", full_name="Zone Sort Test User"
    )
    db.add(user)
    db.flush()

    greenhouse = Greenhouse(
        title="Zone Sort Test Greenhouse",
        description="Testing zone sorting",
        user_id=user.id,
    )
    db.add(greenhouse)
    db.flush()

    # Create first zone
    zone1 = Zone(
        greenhouse_id=greenhouse.id,
        zone_number=1,
        location=LocationEnum.N,
        context_text="First zone created",
    )
    db.add(zone1)
    db.commit()

    # Small delay to ensure different created_at times
    time.sleep(0.01)

    # Create second zone
    zone2 = Zone(
        greenhouse_id=greenhouse.id,
        zone_number=2,
        location=LocationEnum.S,
        context_text="Second zone created",
    )
    db.add(zone2)
    db.commit()

    # Test ascending order (created_at)
    zones_asc = db.exec(
        select(Zone)
        .where(Zone.greenhouse_id == greenhouse.id)
        .order_by(Zone.created_at.asc())
    ).all()

    assert len(zones_asc) == 2
    assert zones_asc[0].id == zone1.id  # First created should be first
    assert zones_asc[1].id == zone2.id  # Second created should be second
    assert zones_asc[0].created_at <= zones_asc[1].created_at

    print(
        f"✓ Zones ascending sort: Zone {zones_asc[0].zone_number} ({zones_asc[0].created_at}) → Zone {zones_asc[1].zone_number} ({zones_asc[1].created_at})"
    )

    # Test descending order (-created_at)
    zones_desc = db.exec(
        select(Zone)
        .where(Zone.greenhouse_id == greenhouse.id)
        .order_by(Zone.created_at.desc())
    ).all()

    assert len(zones_desc) == 2
    assert zones_desc[0].id == zone2.id  # Most recent should be first
    assert zones_desc[1].id == zone1.id  # Oldest should be second
    assert zones_desc[0].created_at >= zones_desc[1].created_at

    print(
        f"✓ Zones descending sort: Zone {zones_desc[0].zone_number} ({zones_desc[0].created_at}) → Zone {zones_desc[1].zone_number} ({zones_desc[1].created_at})"
    )


def test_server_default_created_at(db: Session):
    """Test that created_at gets server default values."""

    # Create test data
    unique_email = f"server_default_test_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=unique_email,
        hashed_password="fake_hash",
        full_name="Server Default Test User",
    )
    db.add(user)
    db.flush()

    greenhouse = Greenhouse(
        title="Server Default Test Greenhouse",
        description="Testing server defaults",
        user_id=user.id,
    )
    db.add(greenhouse)
    db.flush()

    controller = Controller(
        greenhouse_id=greenhouse.id,
        device_name="verdify-test-default-001",
        name="Test Controller for Server Default",
        location="Test Location",
    )
    db.add(controller)
    db.flush()

    # Create sensor without explicitly setting created_at
    sensor = Sensor(
        controller_id=controller.id,
        name="Server Default Sensor",
        kind=SensorKind.TEMPERATURE,
        scope=SensorScope.ZONE,
        include_in_climate_loop=True,
    )
    db.add(sensor)
    db.commit()

    # Create zone without explicitly setting created_at
    zone = Zone(
        greenhouse_id=greenhouse.id,
        zone_number=1,
        location=LocationEnum.N,
        context_text="Server default zone",
    )
    db.add(zone)
    db.commit()

    # Refresh to get the server-set values
    db.refresh(sensor)
    db.refresh(zone)

    # Verify created_at fields are populated by server
    assert sensor.created_at is not None
    assert zone.created_at is not None

    print(f"✓ Sensor created_at server default: {sensor.created_at}")
    print(f"✓ Zone created_at server default: {zone.created_at}")

    # Verify they are timezone-aware datetime objects
    assert sensor.created_at.tzinfo is not None
    assert zone.created_at.tzinfo is not None

    print("✓ Server default created_at fields are timezone-aware")
