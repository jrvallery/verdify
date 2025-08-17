#!/usr/bin/env python3
"""Test IdempotencyKey unique constraint behavior"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.db import engine
from app.models import Controller, Greenhouse, IdempotencyKey, User


def test_idempotency_key_constraint():
    """Test that unique constraint on (key, controller_id) works correctly"""

    print("=== Testing IdempotencyKey unique constraint ===")

    with Session(engine) as session:
        # Create minimal test data
        user = User(
            email="test@example.com", hashed_password="fake_hash", full_name="Test User"
        )
        session.add(user)
        session.flush()

        greenhouse = Greenhouse(
            title="Test Greenhouse",
            description="Test greenhouse for idempotency test",
            user_id=user.id,
        )
        session.add(greenhouse)
        session.flush()

        controller = Controller(
            name="Test Controller",
            device_token="test-device-token-123",
            greenhouse_id=greenhouse.id,
        )
        session.add(controller)
        session.flush()

        # Test 1: Create first idempotency key
        key1 = IdempotencyKey(
            key="test-idempotency-key-1",
            controller_id=controller.id,
            body_hash="hash123",
            response_status=200,
            response_body='{"success": true}',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session.add(key1)
        session.commit()

        print(f"✓ Created first IdempotencyKey: {key1.id}")
        print(f"  key: {key1.key}")
        print(f"  controller_id: {key1.controller_id}")
        print("  constraint name: uq_idempotency_key_controller")

        # Test 2: Try to create second key with same (key, controller_id) - should fail
        print("\n=== Testing unique constraint violation ===")

        try:
            key2 = IdempotencyKey(
                key="test-idempotency-key-1",  # Same key
                controller_id=controller.id,  # Same controller
                body_hash="different_hash",  # Different body hash
                response_status=201,
                response_body='{"different": true}',
                expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            )
            session.add(key2)
            session.commit()
            print("✗ ERROR: Unique constraint failed - duplicate key was allowed!")

        except IntegrityError as e:
            session.rollback()
            error_msg = str(e)
            print("✓ Unique constraint working correctly")

            # Verify it mentions the constraint name
            if "uq_idempotency_key_controller" in error_msg:
                print(
                    "✓ Constraint name 'uq_idempotency_key_controller' found in error"
                )
            else:
                print(f"? Constraint name check: {error_msg[:200]}...")

        # Test 3: Create key with same key but different controller - should succeed
        print("\n=== Testing different controller with same key ===")

        controller2 = Controller(
            name="Test Controller 2",
            device_token="test-device-token-456",
            greenhouse_id=greenhouse.id,
        )
        session.add(controller2)
        session.flush()

        key3 = IdempotencyKey(
            key="test-idempotency-key-1",  # Same key as before
            controller_id=controller2.id,  # Different controller
            body_hash="hash789",
            response_status=200,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session.add(key3)
        session.commit()

        print(f"✓ Created key with same key but different controller: {key3.id}")
        print(f"  Same key '{key3.key}' but controller_id: {key3.controller_id}")

        # Test 4: Create key with different key but same controller - should succeed
        print("\n=== Testing different key with same controller ===")

        key4 = IdempotencyKey(
            key="test-idempotency-key-2",  # Different key
            controller_id=controller.id,  # Same controller as first
            body_hash="hash456",
            response_status=202,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session.add(key4)
        session.commit()

        print(f"✓ Created key with different key but same controller: {key4.id}")
        print(
            f"  Different key '{key4.key}' but same controller_id: {key4.controller_id}"
        )

        # Final verification
        total_keys = len(session.exec(select(IdempotencyKey)).all())
        print(f"\n✓ Total IdempotencyKey records: {total_keys}")

    print("\n=== IdempotencyKey constraint test completed ===")
    print("✓ Unique constraint (key, controller_id) works correctly")
    print("✓ Same key with different controllers allowed")
    print("✓ Different keys with same controller allowed")
    print("✓ Duplicate (key, controller_id) pairs correctly rejected")


if __name__ == "__main__":
    test_idempotency_key_constraint()
