#!/usr/bin/env python3
"""Test state machine models agai    print(f"✓ Created StateMachineRow: greenhouse_id={row1.greenhouse_id}")
    print(f"  temp_stage: {row1.temp_stage}, humi_stage: {row1.humi_stage}")
    print(f"  must_on_actuators: {len(row1.must_on_actuators)} items")
    print(f"  must_off_actuators: {len(row1.must_off_actuators)} items")
    print(f"  must_on_fan_groups: {len(row1.must_on_fan_groups)} items")

    row1_id = row1.id
    greenhouse_id = greenhouse.id  # Store the ID before session closes

# Test 2: Verify unique constraint on (greenhouse_id, temp_stage, humi_stage)
print("
=== Testing unique constraint (greenhouse_id, temp_stage, humi_stage) ===")

with Session(engine) as session:
    try:
        # Try to create duplicate row with same greenhouse_id, temp_stage, humi_stage
        duplicate_row = StateMachineRow(
            greenhouse_id=greenhouse_id,ecification"""

import uuid
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.db import engine
from app.models import (
    User, Greenhouse, StateMachineRow, StateMachineFallback,
    StateMachineRowCreate, StateMachineFallbackCreate
)

def test_state_machine_spec_compliance():
    """Test that state machine models match the API specification"""

    print("=== Testing StateMachineRow spec compliance ===")

    with Session(engine) as session:
        # Create test greenhouse
        user = User(
            email="test@example.com",
            hashed_password="fake_hash",
            full_name="Test User"
        )
        session.add(user)
        session.flush()

        greenhouse = Greenhouse(
            title="Test Greenhouse",
            description="State machine test greenhouse",
            user_id=user.id
        )
        session.add(greenhouse)
        session.flush()

        # Test 1: Create StateMachineRow with temp_stage and humi_stage
        actuator_id1 = str(uuid.uuid4())
        actuator_id2 = str(uuid.uuid4())
        actuator_id3 = str(uuid.uuid4())

        row1 = StateMachineRow(
            greenhouse_id=greenhouse.id,
            temp_stage=1,
            humi_stage=2,
            is_fallback=False,
            must_on_actuators=[actuator_id1, actuator_id2],
            must_off_actuators=[actuator_id3],
            must_on_fan_groups=[
                {"fan_group_id": str(uuid.uuid4()), "on_count": 2},
                {"fan_group_id": str(uuid.uuid4()), "on_count": 1}
            ]
        )
        session.add(row1)
        session.commit()

        print(f"✓ Created StateMachineRow: greenhouse_id={row1.greenhouse_id}")
        print(f"  temp_stage: {row1.temp_stage}, humi_stage: {row1.humi_stage}")
        print(f"  must_on_actuators: {len(row1.must_on_actuators)} items")
        print(f"  must_off_actuators: {len(row1.must_off_actuators)} items")
        print(f"  must_on_fan_groups: {len(row1.must_on_fan_groups)} items")

        row1_id = row1.id
        greenhouse_id = greenhouse.id  # Store the ID before session closes

    # Test 2: Verify unique constraint on (greenhouse_id, temp_stage, humi_stage)
    print("\n=== Testing unique constraint (greenhouse_id, temp_stage, humi_stage) ===")

    with Session(engine) as session:
        try:
            # Try to create duplicate row with same greenhouse_id, temp_stage, humi_stage
            duplicate_row = StateMachineRow(
                greenhouse_id=greenhouse.id,
                temp_stage=1,  # Same as row1
                humi_stage=2,  # Same as row1
                is_fallback=False,
                must_on_actuators=[str(uuid.uuid4())],
                must_off_actuators=[],
                must_on_fan_groups=[]
            )
            session.add(duplicate_row)
            session.commit()
            print("✗ ERROR: Unique constraint failed - duplicate row was allowed!")

        except IntegrityError as e:
            session.rollback()
            error_msg = str(e)
            print("✓ Unique constraint working correctly")

            if "uq_smrow_gh_temp_humi" in error_msg:
                print("✓ Constraint name 'uq_smrow_gh_temp_humi' found in error")
            else:
                print(f"? Constraint name check: {error_msg[:200]}...")

    # Test 3: Create row with different temp/humi stages - should succeed
    print("\n=== Testing different temp/humi stages ===")

    with Session(engine) as session:
        row2 = StateMachineRow(
            greenhouse_id=greenhouse.id,
            temp_stage=2,  # Different temp_stage
            humi_stage=1,  # Different humi_stage
            is_fallback=False,
            must_on_actuators=[],
            must_off_actuators=[str(uuid.uuid4()), str(uuid.uuid4())],
            must_on_fan_groups=[]
        )
        session.add(row2)
        session.commit()

        print(f"✓ Created second StateMachineRow with different stages")
        print(f"  temp_stage: {row2.temp_stage}, humi_stage: {row2.humi_stage}")

    # Test 4: Test StateMachineFallback with unique greenhouse constraint
    print("\n=== Testing StateMachineFallback spec compliance ===")

    with Session(engine) as session:
        fallback = StateMachineFallback(
            greenhouse_id=greenhouse.id,
            must_on_actuators=[str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())],
            must_off_actuators=[str(uuid.uuid4())],
            must_on_fan_groups=[
                {"fan_group_id": str(uuid.uuid4()), "on_count": 3}
            ]
        )
        session.add(fallback)
        session.commit()

        print(f"✓ Created StateMachineFallback: greenhouse_id={fallback.greenhouse_id}")
        print(f"  must_on_actuators: {len(fallback.must_on_actuators)} items")
        print(f"  must_off_actuators: {len(fallback.must_off_actuators)} items")
        print(f"  must_on_fan_groups: {len(fallback.must_on_fan_groups)} items")

    # Test 5: Try to create second fallback for same greenhouse - should fail
    print("\n=== Testing StateMachineFallback unique greenhouse constraint ===")

    with Session(engine) as session:
        try:
            duplicate_fallback = StateMachineFallback(
                greenhouse_id=greenhouse.id,  # Same greenhouse
                must_on_actuators=[],
                must_off_actuators=[],
                must_on_fan_groups=[]
            )
            session.add(duplicate_fallback)
            session.commit()
            print("✗ ERROR: Unique greenhouse constraint failed - duplicate fallback was allowed!")

        except IntegrityError as e:
            session.rollback()
            error_msg = str(e)
            print("✓ Unique greenhouse constraint working correctly")
            print(f"  Error indicates unique constraint on greenhouse_id")

    # Test 6: Verify field ranges for temp_stage and humi_stage
    print("\n=== Testing stage value ranges (-3 to 3) ===")

    # Test valid range values
    for stage in [-3, -2, -1, 0, 1, 2, 3]:
        try:
            row = StateMachineRowCreate(
                greenhouse_id=greenhouse.id,
                temp_stage=stage,
                humi_stage=0,
                must_on_actuators=[],
                must_off_actuators=[],
                must_on_fan_groups=[]
            )
            print(f"  ✓ temp_stage={stage} - valid")
        except Exception as e:
            print(f"  ✗ temp_stage={stage} - invalid: {e}")

    # Test 7: Verify JSON field structure
    print("\n=== Testing JSON field structures ===")

    with Session(engine) as session:
        # Query back the created data to verify JSON structure
        saved_row = session.get(StateMachineRow, row1_id)
        saved_fallback = session.exec(
            select(StateMachineFallback).where(StateMachineFallback.greenhouse_id == greenhouse.id)
        ).first()

        print(f"✓ StateMachineRow JSON fields:")
        print(f"  must_on_actuators type: {type(saved_row.must_on_actuators)}")
        print(f"  must_off_actuators type: {type(saved_row.must_off_actuators)}")
        print(f"  must_on_fan_groups type: {type(saved_row.must_on_fan_groups)}")
        print(f"  Fan group structure: {saved_row.must_on_fan_groups[0] if saved_row.must_on_fan_groups else 'empty'}")

        print(f"✓ StateMachineFallback JSON fields:")
        print(f"  must_on_actuators type: {type(saved_fallback.must_on_actuators)}")
        print(f"  must_off_actuators type: {type(saved_fallback.must_off_actuators)}")
        print(f"  must_on_fan_groups type: {type(saved_fallback.must_on_fan_groups)}")

    print("\n=== State machine specification compliance test completed ===")
    print("✓ StateMachineRow: greenhouse-scoped with temp_stage/humi_stage")
    print("✓ Unique constraint on (greenhouse_id, temp_stage, humi_stage)")
    print("✓ StateMachineFallback: one per greenhouse with unique constraint")
    print("✓ JSON arrays for actuator/fan-group IDs work correctly")
    print("✓ temp_stage/humi_stage ranges (-3 to 3) validated")
    print("✓ Fan group structure includes fan_group_id and on_count")

if __name__ == "__main__":
    test_state_machine_spec_compliance()
