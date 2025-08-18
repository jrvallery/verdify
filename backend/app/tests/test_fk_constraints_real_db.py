#!/usr/bin/env python3
"""
Test foreign key constraints against the real PostgreSQL database.

This test verifies that our sa_column=Column(ForeignKey(..., ondelete=...)) pattern
properly enforces database-level cascade behaviors in the actual production database.
"""

import uuid

from sqlmodel import Session

from app.core.db import engine
from app.models import *


def test_foreign_key_cascades_real_db():
    """Test CASCADE and SET NULL foreign key behaviors against real PostgreSQL."""

    print(
        "🧪 Testing foreign key cascade behaviors against real PostgreSQL database..."
    )

    with Session(engine) as session:
        # Test 1: CASCADE behavior (Greenhouse -> Zone)
        print("\n1️⃣ Testing CASCADE: Greenhouse -> Zone")

        # Create or get a test user
        from app.crud.auth import create_user_crud
        from app.models import UserCreate

        test_email = f"test-fk-{uuid.uuid4().hex[:8]}@example.com"
        user_create = UserCreate(
            email=test_email,
            password="test_password_123",
            is_active=True,
            is_superuser=False,
        )
        user = create_user_crud(session=session, user_create=user_create)
        session.commit()
        print(f"   ✅ Test user {user.id} created")

        # Create greenhouse
        greenhouse = Greenhouse(
            title="FK Test Greenhouse",
            user_id=user.id,
            description="Testing foreign key constraints",
        )
        session.add(greenhouse)
        session.commit()
        print(f"   ✅ Greenhouse {greenhouse.id} created")

        # Create zone belonging to greenhouse
        zone = Zone(
            zone_number=999,  # Use a unique number to avoid conflicts
            location="N",
            greenhouse_id=greenhouse.id,
        )
        session.add(zone)
        session.commit()

        zone_id = zone.id
        print(f"   ✅ Zone {zone_id} created")

        # Verify zone exists
        existing_zone = session.get(Zone, zone_id)
        assert existing_zone is not None, "Zone should exist before deletion"

        # Delete greenhouse (should CASCADE delete zone due to ondelete="CASCADE")
        session.delete(greenhouse)
        session.commit()
        print("   ✅ Greenhouse deleted")

        # Verify zone was cascade deleted
        deleted_zone = session.get(Zone, zone_id)
        assert deleted_zone is None, f"Zone {zone_id} should have been CASCADE deleted"
        print(f"   ✅ Zone {zone_id} was CASCADE deleted when greenhouse was deleted")

        # Test 2: SET NULL behavior (ZoneCrop -> Crop)
        print("\n2️⃣ Testing SET NULL: ZoneCrop -> Crop")

        # Create new greenhouse and zone for this test
        greenhouse2 = Greenhouse(
            title="FK Test Greenhouse 2",
            user_id=user.id,
            description="Testing SET NULL constraint",
        )
        session.add(greenhouse2)
        session.commit()

        zone2 = Zone(
            zone_number=998,  # Another unique number
            location="S",
            greenhouse_id=greenhouse2.id,
        )
        session.add(zone2)
        session.commit()
        print(f"   ✅ New greenhouse {greenhouse2.id} and zone {zone2.id} created")

        # Create crop template
        crop = Crop(
            name=f"FK Test Crop {uuid.uuid4().hex[:8]}",
            description="Test crop for foreign key testing",
        )
        session.add(crop)
        session.commit()
        print(f"   ✅ Crop template {crop.id} created")

        # Create zone crop referencing the crop template
        zone_crop = ZoneCrop(
            zone_id=zone2.id,
            crop_id=crop.id,  # This should be SET NULL when crop is deleted
            planted_date="2024-01-01",
        )
        session.add(zone_crop)
        session.commit()

        zone_crop_id = zone_crop.id
        print(f"   ✅ ZoneCrop {zone_crop_id} created with crop_id={crop.id}")

        # Verify zone crop exists and references crop
        existing_zone_crop = session.get(ZoneCrop, zone_crop_id)
        assert existing_zone_crop is not None, "ZoneCrop should exist"
        assert existing_zone_crop.crop_id == crop.id, "ZoneCrop should reference crop"

        # Delete crop template (should SET NULL on zone_crop.crop_id due to ondelete="SET NULL")
        session.delete(crop)
        session.commit()
        print("   ✅ Crop template deleted")

        # Verify zone crop still exists but crop_id is NULL
        remaining_zone_crop = session.get(ZoneCrop, zone_crop_id)
        assert (
            remaining_zone_crop is not None
        ), "ZoneCrop should still exist after crop deletion"
        assert (
            remaining_zone_crop.crop_id is None
        ), f"ZoneCrop.crop_id should be NULL, got {remaining_zone_crop.crop_id}"
        print(
            f"   ✅ ZoneCrop {zone_crop_id} still exists with crop_id=NULL after crop deletion"
        )

        # Clean up - delete the remaining test data (handle cascade deletions gracefully)
        try:
            session.delete(remaining_zone_crop)
            session.delete(zone2)
            session.delete(greenhouse2)
            session.delete(user)
            session.commit()
            print("   ✅ Test data cleaned up")
        except Exception:
            # Some objects may have been cascade deleted already
            session.rollback()
            print("   ⚠️  Cleanup completed (some objects were already cascade deleted)")

        print(
            "\n✅ All foreign key cascade tests passed against real PostgreSQL database!"
        )


if __name__ == "__main__":
    test_foreign_key_cascades_real_db()
    print(
        "\n🎉 Real database foreign key constraint verification completed successfully!"
    )
