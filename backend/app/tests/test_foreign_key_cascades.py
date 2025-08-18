#!/usr/bin/env python3
"""
Test script to verify that foreign key constraints with CASCADE and SET NULL work correctly.

This test verifies that our sa_column=Column(ForeignKey(..., ondelete=...)) pattern
properly enforces database-level cascade behaviors.
"""

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.models import *


def test_foreign_key_cascades():
    """Test CASCADE and SET NULL foreign key behaviors."""

    # Create in-memory SQLite database for testing
    engine = create_engine("sqlite:///:memory:", echo=False)

    # Enable foreign key constraints in SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        print("🧪 Testing foreign key cascade behaviors...")

        # Test 1: CASCADE behavior (Greenhouse -> Zone)
        print("\n1️⃣ Testing CASCADE: Greenhouse -> Zone")

        # Create user and greenhouse
        user = User(
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_superuser=False,
        )
        session.add(user)
        session.commit()

        greenhouse = Greenhouse(
            title="Test Greenhouse", user_id=user.id, description="Test description"
        )
        session.add(greenhouse)
        session.commit()

        # Create zone belonging to greenhouse
        zone = Zone(zone_number=1, location="N", greenhouse_id=greenhouse.id)
        session.add(zone)
        session.commit()

        zone_id = zone.id

        # Verify zone exists
        assert session.get(Zone, zone_id) is not None
        print(f"   ✅ Zone {zone_id} created")

        # Delete greenhouse (should CASCADE delete zone)
        session.delete(greenhouse)
        session.commit()

        # Verify zone was cascade deleted
        deleted_zone = session.get(Zone, zone_id)
        assert deleted_zone is None
        print(f"   ✅ Zone {zone_id} was CASCADE deleted when greenhouse was deleted")

        # Test 2: SET NULL behavior (ZoneCrop -> Crop)
        print("\n2️⃣ Testing SET NULL: ZoneCrop -> Crop")

        # Create new greenhouse and zone for this test
        greenhouse2 = Greenhouse(
            title="Test Greenhouse 2", user_id=user.id, description="Test description 2"
        )
        session.add(greenhouse2)
        session.commit()

        zone2 = Zone(zone_number=1, location="S", greenhouse_id=greenhouse2.id)
        session.add(zone2)
        session.commit()

        # Create crop template
        crop = Crop(name="Test Crop", description="Test crop description")
        session.add(crop)
        session.commit()

        # Create zone crop referencing the crop template
        zone_crop = ZoneCrop(
            zone_id=zone2.id,
            crop_id=crop.id,  # This should be SET NULL when crop is deleted
            planted_date="2024-01-01",
        )
        session.add(zone_crop)
        session.commit()

        zone_crop_id = zone_crop.id

        # Verify zone crop exists and references crop
        existing_zone_crop = session.get(ZoneCrop, zone_crop_id)
        assert existing_zone_crop is not None
        assert existing_zone_crop.crop_id == crop.id
        print(f"   ✅ ZoneCrop {zone_crop_id} created with crop_id={crop.id}")

        # Delete crop template (should SET NULL on zone_crop.crop_id)
        session.delete(crop)
        session.commit()

        # Verify zone crop still exists but crop_id is NULL
        remaining_zone_crop = session.get(ZoneCrop, zone_crop_id)
        assert remaining_zone_crop is not None
        assert remaining_zone_crop.crop_id is None
        print(
            f"   ✅ ZoneCrop {zone_crop_id} still exists with crop_id=NULL after crop deletion"
        )

        print("\n✅ All foreign key cascade tests passed!")


if __name__ == "__main__":
    test_foreign_key_cascades()
    print("\n🎉 Foreign key constraint verification completed successfully!")
