#!/usr/bin/env python3
"""
Test script to verify that all relationships are working correctly.
"""

from sqlmodel import Session, create_engine

# Import all models to ensure they're registered
from app.models import *
from app.models import bootstrap_mappers

# Create in-memory SQLite database for testing
engine = create_engine("sqlite:///:memory:", echo=True)


def test_relationships():
    """Test that all relationships are working without mapper errors."""

    # Bootstrap mappers to resolve string relationships
    bootstrap_mappers()

    # Create all tables
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # Create a user
        user = User(
            email="test@example.com", hashed_password="fake_hash", full_name="Test User"
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        # Create a greenhouse
        greenhouse = Greenhouse(title="Test Greenhouse", user_id=user.id)
        session.add(greenhouse)
        session.commit()
        session.refresh(greenhouse)

        # Test greenhouse -> user relationship
        print(f"✅ Greenhouse owner: {greenhouse.owner.email}")

        # Test user -> greenhouses relationship
        print(f"✅ User greenhouses: {len(user.greenhouses)}")

        # Create a zone
        zone = Zone(zone_number=1, location="N", greenhouse_id=greenhouse.id)
        session.add(zone)
        session.commit()
        session.refresh(zone)

        # Test zone -> greenhouse relationship
        print(f"✅ Zone greenhouse: {zone.greenhouse.title}")

        # Test greenhouse -> zones relationship
        print(f"✅ Greenhouse zones: {len(greenhouse.zones)}")

        # Create a controller
        controller = Controller(
            device_name="verdify-123456", greenhouse_id=greenhouse.id
        )
        session.add(controller)
        session.commit()
        session.refresh(controller)

        # Test controller -> greenhouse relationship
        print(f"✅ Controller greenhouse: {controller.greenhouse.title}")

        # Test greenhouse -> controllers relationship
        print(f"✅ Greenhouse controllers: {len(greenhouse.controllers)}")

        # Create a sensor
        sensor = Sensor(
            name="Test Sensor",
            kind="temperature",
            scope="zone",
            controller_id=controller.id,
        )
        session.add(sensor)
        session.commit()
        session.refresh(sensor)

        # Test sensor -> controller relationship
        print(f"✅ Sensor controller: {sensor.controller.device_name}")

        # Test controller -> sensors relationship
        print(f"✅ Controller sensors: {len(controller.sensors)}")

        # Create an actuator
        actuator = Actuator(
            name="Test Actuator",
            kind="fan",
            controller_id=controller.id,
            zone_id=zone.id,
        )
        session.add(actuator)
        session.commit()
        session.refresh(actuator)

        # Test actuator -> controller relationship
        print(f"✅ Actuator controller: {actuator.controller.device_name}")

        # Test actuator -> zone relationship
        print(f"✅ Actuator zone: {actuator.zone.zone_number}")

        # Test controller -> actuators relationship
        print(f"✅ Controller actuators: {len(controller.actuators)}")

        # Test zone -> actuators relationship
        print(f"✅ Zone actuators: {len(zone.actuators)}")

        # Create a crop
        crop = Crop(name="Test Crop", description="A test crop")
        session.add(crop)
        session.commit()
        session.refresh(crop)

        # Create a zone crop
        zone_crop = ZoneCrop(crop_id=crop.id, zone_id=zone.id)
        session.add(zone_crop)
        session.commit()
        session.refresh(zone_crop)

        # Test zone_crop -> crop relationship
        print(f"✅ ZoneCrop crop: {zone_crop.crop.name}")

        # Test zone_crop -> zone relationship
        print(f"✅ ZoneCrop zone: {zone_crop.zone.zone_number}")

        # Test crop -> zone_crops relationship
        print(f"✅ Crop zone_crops: {len(crop.zone_crops)}")

        # Test zone -> zone_crops relationship
        print(f"✅ Zone zone_crops: {len(zone.zone_crops)}")

        print("\n🎉 All relationship tests passed!")


if __name__ == "__main__":
    test_relationships()
