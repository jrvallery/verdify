#!/usr/bin/env python3
"""Test zone crop and observation cascade behavior with renamed fields"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.db import engine
from app.models import Crop, Greenhouse, User, Zone, ZoneCrop, ZoneCropObservation


def test_zone_crop_cascade():
    """Test that zone_crop deletion properly cascades to zone_crop_observation"""

    # Test 1: Verify table names and field names after migration
    print("=== Testing table names and field access ===")

    with Session(engine) as session:
        # Create a simple user first
        user = User(
            email="test@example.com", hashed_password="fake_hash", full_name="Test User"
        )
        session.add(user)
        session.flush()

        # Create test data using new field names
        greenhouse = Greenhouse(
            title="Test Greenhouse", description="Migration test", user_id=user.id
        )
        session.add(greenhouse)
        session.flush()

        zone = Zone(
            name="Test Zone",
            description="Migration test zone",
            greenhouse_id=greenhouse.id,
        )
        session.add(zone)
        session.flush()

        crop_template = Crop(
            name="Test Tomato",
            description="Test crop template",
            category="vegetable",
            planting_method="direct_seed",
        )
        session.add(crop_template)
        session.flush()

        # Test ZoneCrop with new field names (start_date/end_date)
        zone_crop = ZoneCrop(
            zone_id=zone.id,
            crop_id=crop_template.id,
            start_date=date(2024, 3, 1),
            end_date=date(2024, 8, 1),
            planting_method="direct_seed",
        )
        session.add(zone_crop)
        session.flush()

        print(f"✓ Created ZoneCrop with ID: {zone_crop.id}")
        print(f"  start_date: {zone_crop.start_date}")
        print(f"  end_date: {zone_crop.end_date}")

        # Create observations linked to zone_crop
        observation1 = ZoneCropObservation(
            zone_crop_id=zone_crop.id,
            observation_date=datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
            growth_stage="seedling",
            health="good",
            notes="Looking healthy",
        )
        observation2 = ZoneCropObservation(
            zone_crop_id=zone_crop.id,
            observation_date=datetime(2024, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
            growth_stage="vegetative",
            health="excellent",
            notes="Growing well",
        )
        session.add_all([observation1, observation2])
        session.flush()

        print(f"✓ Created 2 observations for zone_crop {zone_crop.id}")

        # Verify data exists
        crop_count = session.exec(select(ZoneCrop)).first()
        obs_count = len(session.exec(select(ZoneCropObservation)).all())
        print(f"✓ Database state: 1 zone_crop, {obs_count} observations")

        session.commit()
        zone_crop_id = zone_crop.id

    # Test 2: Verify cascade delete works with new table names
    print("\n=== Testing CASCADE delete ===")

    with Session(engine) as session:
        # Delete the zone_crop and verify observations are automatically deleted
        zone_crop = session.get(ZoneCrop, zone_crop_id)
        if zone_crop:
            print(f"Deleting zone_crop {zone_crop_id}")
            session.delete(zone_crop)
            session.commit()

            # Check that observations were cascade deleted
            remaining_observations = session.exec(
                select(ZoneCropObservation).where(
                    ZoneCropObservation.zone_crop_id == zone_crop_id
                )
            ).all()

            if not remaining_observations:
                print(
                    "✓ CASCADE delete working: observations were automatically deleted"
                )
            else:
                print(
                    f"✗ CASCADE delete failed: {len(remaining_observations)} observations still exist"
                )
        else:
            print("✗ Zone crop not found")

    # Test 3: Verify FK constraint prevents orphaned observations
    print("\n=== Testing FK constraint enforcement ===")

    with Session(engine) as session:
        try:
            # Try to create observation with invalid zone_crop_id
            orphan_observation = ZoneCropObservation(
                zone_crop_id=uuid.uuid4(),  # Random UUID that doesn't exist
                observation_date=datetime.now(timezone.utc),
                growth_stage="unknown",
                health="unknown",
                notes="This should fail",
            )
            session.add(orphan_observation)
            session.commit()
            print("✗ FK constraint failed: orphaned observation was created")
        except IntegrityError as e:
            session.rollback()
            print("✓ FK constraint working: cannot create orphaned observation")
            print(f"  Error: {str(e).split('DETAIL:')[0].strip()}")

    print("\n=== Test completed ===")


if __name__ == "__main__":
    test_zone_crop_cascade()
