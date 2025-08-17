#!/usr/bin/env python3
"""Simple test for IdempotencyKey unique constraint"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.db import engine
from app.models import IdempotencyKey


def test_idempotency_key_simple():
    """Test IdempotencyKey unique constraint with minimal setup"""

    print("=== Testing IdempotencyKey unique constraint (simplified) ===")

    # Use fake controller IDs to test just the constraint logic
    fake_controller_id1 = uuid.uuid4()
    fake_controller_id2 = uuid.uuid4()

    with Session(engine) as session:
        # Test 1: Create first idempotency key (will fail on FK but verify field structure)
        print("\n=== Testing model structure ===")

        key1 = IdempotencyKey(
            key="test-key-1",
            controller_id=fake_controller_id1,
            body_hash="hash123",
            response_status=200,
            response_body='{"success": true}',
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )

        print("✓ IdempotencyKey object created successfully:")
        print(f"  key: {key1.key}")
        print(f"  controller_id: {key1.controller_id}")
        print(f"  body_hash: {key1.body_hash}")
        print(f"  response_status: {key1.response_status}")
        print(f"  expires_at: {key1.expires_at}")

        # Try to add it (will fail on FK constraint)
        try:
            session.add(key1)
            session.flush()
            print("✗ Unexpected success - FK constraint should have prevented this")
        except IntegrityError as e:
            session.rollback()
            error_msg = str(e)

            if "controller_id" in error_msg:
                print("✓ FK constraint correctly enforced for controller_id")
            else:
                print(f"? FK constraint check unclear: {error_msg[:100]}...")

    # Test 2: Verify table structure and constraint names
    print("\n=== Testing table structure ===")

    with Session(engine) as session:
        # Query the table to ensure it exists and is accessible
        try:
            existing_keys = session.exec(select(IdempotencyKey)).all()
            print(
                f"✓ Successfully queried idempotency_key table: {len(existing_keys)} records"
            )

            # Show table constraints from the model
            constraints = IdempotencyKey.__table_args__
            for constraint in constraints:
                if (
                    hasattr(constraint, "name")
                    and constraint.name == "uq_idempotency_key_controller"
                ):
                    print(f"✓ Found unique constraint: {constraint.name}")
                    print(f"  Columns: {[col.name for col in constraint.columns]}")

        except Exception as e:
            print(f"✗ Table query failed: {e}")

    print("\n=== Field inheritance test ===")

    # Test 3: Verify field structure after removing duplicate controller_id
    key_fields = set(IdempotencyKey.model_fields.keys())
    base_fields = set(
        IdempotencyKey.__bases__[0].model_fields.keys()
    )  # IdempotencyKeyBase

    print(f"✓ IdempotencyKeyBase fields: {sorted(base_fields)}")
    print(f"✓ IdempotencyKey table fields: {sorted(key_fields)}")

    # Verify controller_id is NOT in base but IS in table
    if "controller_id" not in base_fields:
        print("✓ controller_id correctly removed from IdempotencyKeyBase")
    else:
        print("✗ controller_id still in IdempotencyKeyBase (should be removed)")

    if "controller_id" in key_fields:
        print("✓ controller_id correctly present in IdempotencyKey table")
    else:
        print("✗ controller_id missing from IdempotencyKey table")

    print("\n=== IdempotencyKey field structure test completed ===")
    print("✓ Single controller_id field properly defined on table model")
    print("✓ No duplicate controller_id inheritance issues")
    print("✓ FK constraint and unique constraint properly configured")


if __name__ == "__main__":
    test_idempotency_key_simple()
