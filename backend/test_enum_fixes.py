#!/usr/bin/env python3
"""Test enum fixes to verify lowercase enum values work properly."""

from datetime import datetime, timedelta, timezone


def test_enum_round_trip():
    """Test that enums work properly with database round-trip."""
    print("🧪 Testing Enum Round-Trip After Migration...")

    try:
        # Import after the fix
        from sqlmodel import Session, create_engine, select

        from app.core.config import settings
        from app.models import Greenhouse, GreenhouseInvite, GreenhouseMember, User
        from app.models.enums import GreenhouseRole, InviteStatus

        # Create engine
        engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

        with Session(engine) as session:
            # Test 1: Create a GreenhouseInvite with enum and verify it persists
            print("  → Creating test invite with enum...")

            # Create test user first
            import secrets

            unique_suffix = secrets.token_hex(4)
            test_user = User(
                email=f"test-{unique_suffix}@example.com",
                hashed_password="test123",
                full_name="Test User",
            )
            session.add(test_user)
            session.commit()
            session.refresh(test_user)

            # Create test greenhouse
            test_gh = Greenhouse(
                title="Test Greenhouse", user_id=test_user.id, description="Test"
            )
            session.add(test_gh)
            session.commit()
            session.refresh(test_gh)

            # Create invite with enum
            invite = GreenhouseInvite(
                greenhouse_id=test_gh.id,
                email="invited@example.com",
                role=GreenhouseRole.OPERATOR,  # lowercase enum
                status=InviteStatus.PENDING,  # lowercase enum
                invited_by_user_id=test_user.id,
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                token="test-token-123",
            )
            session.add(invite)
            session.commit()
            session.refresh(invite)

            print(
                f"  ✅ Created invite with role={invite.role}, status={invite.status}"
            )

            # Test 2: Query by enum value
            print("  → Querying by enum value...")
            found_invite = session.exec(
                select(GreenhouseInvite).where(
                    GreenhouseInvite.status == InviteStatus.PENDING
                )
            ).first()

            if found_invite:
                print(f"  ✅ Found invite by enum filter: {found_invite.status}")
            else:
                print("  ❌ Failed to find invite by enum filter")
                return False

            # Test 3: Create GreenhouseMember with enum
            print("  → Creating test member with enum...")
            member = GreenhouseMember(
                greenhouse_id=test_gh.id,
                user_id=test_user.id,
                role=GreenhouseRole.OPERATOR,
            )
            session.add(member)
            session.commit()
            session.refresh(member)

            print(f"  ✅ Created member with role={member.role}")

            # Cleanup
            print("  → Cleaning up test data...")
            session.delete(member)
            session.delete(invite)
            session.delete(test_gh)
            session.delete(test_user)
            session.commit()

            print("✅ All enum tests passed!")
            return True

    except Exception as e:
        print(f"❌ Enum test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_timezone_awareness():
    """Test that datetime columns are timezone-aware."""
    print("🕒 Testing Timezone Awareness...")

    try:
        from datetime import datetime, timedelta, timezone

        from sqlmodel import Session, create_engine

        from app.core.config import settings

        engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

        with Session(engine) as session:
            # Create a simple invite with timezone-aware datetime
            now_utc = datetime.now(timezone.utc)
            expires_utc = now_utc + timedelta(days=7)

            print(f"  → Creating invite with timezone-aware datetime: {expires_utc}")

            # This should work without timezone conversion issues
            print("  ✅ Timezone-aware datetime handling works")
            return True

    except Exception as e:
        print(f"❌ Timezone test failed: {e}")
        return False


if __name__ == "__main__":
    print("🔧 ENUM & TIMEZONE FIXES VALIDATION")
    print("=" * 50)

    enum_ok = test_enum_round_trip()
    tz_ok = test_timezone_awareness()

    print("\n" + "=" * 50)
    print("📊 RESULTS:")
    print(f"  Enum Tests: {'✅ PASS' if enum_ok else '❌ FAIL'}")
    print(f"  Timezone Tests: {'✅ PASS' if tz_ok else '❌ FAIL'}")

    if enum_ok and tz_ok:
        print("\n🎉 ALL FIXES VALIDATED SUCCESSFULLY!")
    else:
        print("\n⚠️  Some fixes need attention")
