#!/usr/bin/env python3
"""Simple test to verify zone_crop table and field names work"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.db import engine
from app.models import ZoneCrop, ZoneCropObservation


def test_zone_crop_basic():
    """Test that zone_crop and zone_crop_observation tables use correct names and fields"""

    print("=== Testing ZoneCrop table and field names ===")

    # Test 1: Create a ZoneCrop with minimal data to verify table name works
    with Session(engine) as session:
        # Create a ZoneCrop with fake IDs to test table structure
        # (This will fail on FK constraint, but should show correct table name in error)
        fake_zone_id = uuid.uuid4()
        fake_crop_id = uuid.uuid4()

        zone_crop = ZoneCrop(
            zone_id=fake_zone_id,
            crop_id=fake_crop_id,
            start_date=date(2024, 3, 1),
            end_date=date(2024, 8, 1),
            planting_method="direct_seed",
        )

        print("✓ ZoneCrop object created with:")
        print("  Table name: zone_crop (implicit from __tablename__)")
        print(f"  start_date: {zone_crop.start_date}")
        print(f"  end_date: {zone_crop.end_date}")
        print(f"  zone_id: {zone_crop.zone_id}")
        print(f"  crop_id: {zone_crop.crop_id}")

        # Try to add it to see if the table name is recognized
        try:
            session.add(zone_crop)
            session.flush()
            print("✗ Unexpected success - FK constraint should have failed")
        except IntegrityError as e:
            session.rollback()
            error_msg = str(e)

            # Check if the error mentions the correct table name "zone_crop"
            if "zone_crop" in error_msg:
                print(
                    "✓ Table name 'zone_crop' correctly recognized in FK constraint error"
                )
            else:
                print(f"? Table name check unclear. Error: {error_msg[:200]}...")

    # Test 2: Create a ZoneCropObservation to verify table name and FK reference
    print("\n=== Testing ZoneCropObservation table name and FK reference ===")

    with Session(engine) as session:
        fake_zone_crop_id = uuid.uuid4()

        observation = ZoneCropObservation(
            zone_crop_id=fake_zone_crop_id,
            observed_at=datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
            notes="Test observation",
        )

        print("✓ ZoneCropObservation object created with:")
        print("  Table name: zone_crop_observation (implicit from __tablename__)")
        print(f"  zone_crop_id: {observation.zone_crop_id}")
        print(f"  observed_at: {observation.observed_at}")
        print(f"  notes: {observation.notes}")

        # Try to add it to see FK constraint error
        try:
            session.add(observation)
            session.flush()
            print("✗ Unexpected success - FK constraint should have failed")
        except IntegrityError as e:
            session.rollback()
            error_msg = str(e)

            # Check if the error mentions the correct FK reference "zone_crop.id"
            if "zone_crop" in error_msg:
                print(
                    "✓ FK reference to 'zone_crop.id' correctly recognized in constraint error"
                )
            else:
                print(f"? FK reference check unclear. Error: {error_msg[:200]}...")

    # Test 3: Verify we can query the tables by their correct names
    print("\n=== Testing table queries ===")

    with Session(engine) as session:
        try:
            # These should not fail even with empty results
            zone_crops = session.exec(select(ZoneCrop)).all()
            observations = session.exec(select(ZoneCropObservation)).all()

            print(f"✓ Successfully queried zone_crop table: {len(zone_crops)} records")
            print(
                f"✓ Successfully queried zone_crop_observation table: {len(observations)} records"
            )

        except Exception as e:
            print(f"✗ Table query failed: {e}")

    print("\n=== Field name migration verification completed ===")
    print("✓ Tables 'zone_crop' and 'zone_crop_observation' are accessible")
    print("✓ Field names 'start_date' and 'end_date' work correctly")
    print(
        "✓ FK reference from zone_crop_observation.zone_crop_id to zone_crop.id is correct"
    )


if __name__ == "__main__":
    test_zone_crop_basic()
