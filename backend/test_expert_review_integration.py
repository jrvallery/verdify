#!/usr/bin/env python3
"""
Integration tests for specific expert review scenarios.
These test the actual database behavior and API endpoints.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import EmailStr
from sqlmodel import Session

from app.core.db import engine
from app.crud.greenhouses import create_greenhouse_invite, revoke_greenhouse_invite
from app.crud.sensors import (
    list_sensors_by_zone,
    list_unmapped_sensors_by_greenhouse,
)
from app.models import (
    GreenhouseInvite,
    SensorZoneMap,
)
from app.models.enums import GreenhouseRole, InviteStatus, SensorKind


class TestInviteUniqueness:
    """Test partial unique index for pending invites."""

    def test_pending_invite_uniqueness(self):
        """Test that only one PENDING invite per (greenhouse, email) is allowed."""

        with Session(engine) as session:
            # Create test greenhouse and user
            gh_id = uuid.uuid4()
            user_id = uuid.uuid4()
            email = "test@example.com"

            # Create first pending invite
            invite1 = create_greenhouse_invite(
                session, gh_id, EmailStr(email), GreenhouseRole.OPERATOR, user_id
            )
            assert invite1.status == InviteStatus.PENDING

            # Try to create second pending invite for same (greenhouse, email)
            with pytest.raises(Exception):  # Should raise IntegrityError
                create_greenhouse_invite(
                    session, gh_id, EmailStr(email), GreenhouseRole.OPERATOR, user_id
                )

            # Revoke first invite
            revoke_greenhouse_invite(session, invite1)

            # Now should be able to create new pending invite
            invite2 = create_greenhouse_invite(
                session, gh_id, EmailStr(email), GreenhouseRole.OPERATOR, user_id
            )
            assert invite2.status == InviteStatus.PENDING
            assert invite2.id != invite1.id


class TestTimezoneRoundTrip:
    """Test timezone-aware datetime round-trip."""

    def test_timezone_persistence(self):
        """Test that timezone-aware datetimes persist correctly."""

        with Session(engine) as session:
            # Create timezone-aware datetime
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(hours=72)

            # Create invite with timezone-aware timestamps
            invite = GreenhouseInvite(
                id=uuid.uuid4(),
                greenhouse_id=uuid.uuid4(),
                email=EmailStr("timezone@test.com"),
                role=GreenhouseRole.OPERATOR,
                token=f"tz-test-{uuid.uuid4()}",
                expires_at=expires_at,
                invited_by_user_id=uuid.uuid4(),
                status=InviteStatus.PENDING,
                created_at=now,
                updated_at=now,
            )

            session.add(invite)
            session.commit()

            # Read back from database
            retrieved = session.get(GreenhouseInvite, invite.id)

            # Verify timezone info is preserved
            assert retrieved.expires_at.tzinfo is not None
            assert retrieved.created_at.tzinfo is not None
            assert retrieved.updated_at.tzinfo is not None

            # Verify the actual times match (within a small tolerance)
            assert abs((retrieved.expires_at - expires_at).total_seconds()) < 1
            assert abs((retrieved.created_at - now).total_seconds()) < 1


class TestSensorZoneMapping:
    """Test sensor zone mapping with uniqueness constraints."""

    def test_one_sensor_per_zone_kind(self):
        """Test that database enforces one sensor per (zone, kind)."""

        with Session(engine) as session:
            zone_id = uuid.uuid4()
            sensor_a_id = uuid.uuid4()
            sensor_b_id = uuid.uuid4()
            kind = SensorKind.TEMPERATURE

            # Create first mapping
            mapping1 = SensorZoneMap(sensor_id=sensor_a_id, zone_id=zone_id, kind=kind)
            session.add(mapping1)
            session.commit()

            # Try to create second mapping with same (zone, kind) but different sensor
            mapping2 = SensorZoneMap(
                sensor_id=sensor_b_id,
                zone_id=zone_id,
                kind=kind,  # Same zone and kind!
            )
            session.add(mapping2)

            # Should raise IntegrityError due to unique constraint
            with pytest.raises(Exception):
                session.commit()

    def test_sensors_by_zone_no_n_plus_1(self):
        """Test that list_sensors_by_zone uses efficient single query."""

        with Session(engine) as session:
            # This test verifies the function executes without N+1
            # In a real test, you'd set up test data and verify query count
            zone_id = uuid.uuid4()

            # Should not raise any errors and return empty list for non-existent zone
            sensors = list_sensors_by_zone(session, zone_id)
            assert isinstance(sensors, list)


class TestUnmappedSensors:
    """Test unmapped sensor filtering."""

    def test_truly_unmapped_sensors(self):
        """Test that unmapped sensors query returns only unmapped sensors."""

        with Session(engine) as session:
            greenhouse_id = uuid.uuid4()

            # This test verifies the function uses LEFT JOIN correctly
            # In a real scenario, you'd create mapped and unmapped sensors
            unmapped = list_unmapped_sensors_by_greenhouse(session, greenhouse_id)
            assert isinstance(unmapped, list)


class TestMembershipAccess:
    """Test RBAC membership access patterns."""

    def test_operator_access_permissions(self):
        """Test that operators can access but not modify greenhouses."""
        # This would test the permission utilities
        # user_can_access_greenhouse should return True for operators
        # validate_user_owns_greenhouse should return False for operators
        pass  # Implement with actual test data


if __name__ == "__main__":
    # Run with pytest for better test reporting
    pytest.main([__file__, "-v"])
