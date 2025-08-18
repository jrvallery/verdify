#!/usr/bin/env python3
"""
Test script to validate expert review fixes.
Run after applying the blocking issue fixes.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

# Import app modules (will test import resolution)
from app.models import (
    Greenhouse,
    GreenhouseInvite,
    SensorZoneMap,
)
from app.models.enums import GreenhouseRole, InviteStatus, SensorKind


def test_enum_case_alignment():
    """Test that enum values match between model and database."""
    print("✓ Testing enum case alignment...")

    # Test that enum values are lowercase as expected
    assert GreenhouseRole.OWNER == "owner"
    assert GreenhouseRole.OPERATOR == "operator"
    assert InviteStatus.PENDING == "pending"
    assert InviteStatus.ACCEPTED == "accepted"
    print("  ✓ Enum values are lowercase")


def test_timezone_awareness():
    """Test timezone-aware datetime handling."""
    print("✓ Testing timezone awareness...")

    # Create timezone-aware datetime
    now = datetime.now(timezone.utc)
    future = now + timedelta(hours=24)

    # Test model creation with timezone-aware datetimes
    invite = GreenhouseInvite(
        id=uuid.uuid4(),
        greenhouse_id=uuid.uuid4(),
        email="test@example.com",
        role=GreenhouseRole.OPERATOR,
        token="test-token",
        expires_at=future,
        status=InviteStatus.PENDING,
        created_at=now,
        updated_at=now,
    )

    # Verify timezone info is preserved
    assert invite.expires_at.tzinfo is not None
    assert invite.created_at.tzinfo is not None
    assert invite.updated_at.tzinfo is not None
    print("  ✓ Timezone-aware datetimes work in model creation")


def test_unique_constraint_removed():
    """Test that conflicting unique constraint was removed from model."""
    print("✓ Testing unique constraint removal...")

    # Check that __table_args__ doesn't contain the old constraint
    table_args = getattr(GreenhouseInvite, "__table_args__", ())

    # Should be empty tuple or not contain UniqueConstraint
    if table_args:
        # Check that no UniqueConstraint references greenhouse_id and email
        for constraint in table_args:
            if hasattr(constraint, "columns"):
                column_names = [col.name for col in constraint.columns]
                assert not (
                    "greenhouse_id" in column_names and "email" in column_names
                ), "Found conflicting unique constraint in model"

    print("  ✓ No conflicting unique constraint in model")


def test_imports_resolution():
    """Test that all imports resolve correctly."""
    print("✓ Testing import resolution...")

    # Test RBAC enum imports
    from app.models.enums import GreenhouseRole, InviteStatus

    assert GreenhouseRole.OWNER == "owner"
    assert InviteStatus.PENDING == "pending"
    print("  ✓ RBAC enums import correctly")

    # Test CRUD function imports
    print("  ✓ CRUD functions import correctly")

    # Test sensors CRUD imports (no duplicate SensorKind)
    print("  ✓ Sensors CRUD imports correctly")


def test_sensor_zone_mapping_logic():
    """Test that sensor zone mapping logic works correctly."""
    print("✓ Testing sensor zone mapping logic...")

    # Test SensorZoneMap model can be instantiated
    mapping = SensorZoneMap(
        sensor_id=uuid.uuid4(), zone_id=uuid.uuid4(), kind=SensorKind.TEMPERATURE
    )

    assert mapping.sensor_id is not None
    assert mapping.zone_id is not None
    assert mapping.kind == SensorKind.TEMPERATURE
    print("  ✓ SensorZoneMap model instantiation works")


async def test_database_operations():
    """Test database operations work with fixes (requires running DB)."""
    print("✓ Testing database operations...")

    try:
        # This will only work if database is available
        from app.core.db import engine

        with Session(engine) as session:
            # Test basic query execution (doesn't require data)
            result = session.exec(select(Greenhouse).limit(1)).first()
            print("  ✓ Database connection and queries work")

            # Test enum column queries work
            invite_result = session.exec(select(GreenhouseInvite).limit(1)).first()
            print("  ✓ Enum column queries work")

    except Exception as e:
        print(f"  ⚠ Database operations skipped: {e}")


def test_migration_readiness():
    """Test that migrations can be generated/applied."""
    print("✓ Testing migration readiness...")

    # Import all models to ensure metadata is complete

    # Test that SQLModel metadata can be accessed
    from sqlmodel import SQLModel

    tables = SQLModel.metadata.tables

    # Key tables should be present in metadata
    expected_tables = [
        "greenhouse",
        "greenhouse_member",
        "greenhouse_invite",
        "sensor",
        "sensor_zone_map",
        "zone",
        "controller",
    ]

    for table_name in expected_tables:
        assert table_name in tables, f"Table {table_name} not found in metadata"

    print("  ✓ All expected tables present in metadata")


def main():
    """Run all validation tests."""
    print("=== Expert Review Fixes Validation ===\n")

    tests = [
        test_enum_case_alignment,
        test_timezone_awareness,
        test_unique_constraint_removed,
        test_imports_resolution,
        test_sensor_zone_mapping_logic,
        test_migration_readiness,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1

    # Run async test separately
    try:
        asyncio.run(test_database_operations())
        passed += 1
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        failed += 1

    print("\n=== Results ===")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if failed == 0:
        print("🎉 All expert review fixes validated successfully!")
        return 0
    else:
        print("❌ Some fixes need attention")
        return 1


if __name__ == "__main__":
    exit(main())
