"""
Test state machine models against API specification requirements.
"""
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models import Greenhouse, StateMachineFallback, StateMachineRow, User


def test_state_machine_spec_compliance(db: Session):
    """Test that state machine models match the API specification"""

    print("=== Testing StateMachineRow spec compliance ===")

    # Create test greenhouse with unique email
    unique_email = f"state_machine_test_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=unique_email,
        hashed_password="fake_hash",
        full_name="State Machine Test User",
    )
    db.add(user)
    db.flush()

    greenhouse = Greenhouse(
        title="Test Greenhouse",
        description="State machine test greenhouse",
        user_id=user.id,
    )
    db.add(greenhouse)
    db.flush()

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
            {"fan_group_id": str(uuid.uuid4()), "on_count": 1},
        ],
    )
    db.add(row1)
    db.commit()

    print(f"✓ Created StateMachineRow: greenhouse_id={row1.greenhouse_id}")
    print(f"  temp_stage: {row1.temp_stage}, humi_stage: {row1.humi_stage}")
    print(f"  must_on_actuators: {len(row1.must_on_actuators)} items")
    print(f"  must_off_actuators: {len(row1.must_off_actuators)} items")
    print(f"  must_on_fan_groups: {len(row1.must_on_fan_groups)} items")

    row1_id = row1.id
    greenhouse_id = greenhouse.id

    # Test 2: Verify unique constraint on (greenhouse_id, temp_stage, humi_stage)
    print("\n=== Testing unique constraint (greenhouse_id, temp_stage, humi_stage) ===")

    with pytest.raises(IntegrityError):
        # Try to create duplicate row with same greenhouse_id, temp_stage, humi_stage
        duplicate_row = StateMachineRow(
            greenhouse_id=greenhouse_id,
            temp_stage=1,  # Same as row1
            humi_stage=2,  # Same as row1
            is_fallback=False,
            must_on_actuators=[str(uuid.uuid4())],
            must_off_actuators=[],
            must_on_fan_groups=[],
        )
        db.add(duplicate_row)
        db.commit()

    # Rollback after the integrity error
    db.rollback()
    print("✓ Unique constraint enforced correctly")

    # Test 3: Create row with different temp_stage/humi_stage (should succeed)
    print("\n=== Testing different temp_stage/humi_stage (should succeed) ===")

    row2 = StateMachineRow(
        greenhouse_id=greenhouse_id,
        temp_stage=2,  # Different from row1
        humi_stage=1,  # Different from row1
        is_fallback=False,
        must_on_actuators=[str(uuid.uuid4())],
        must_off_actuators=[],
        must_on_fan_groups=[],
    )
    db.add(row2)
    db.commit()
    print(
        f"✓ Created second row with temp_stage={row2.temp_stage}, humi_stage={row2.humi_stage}"
    )

    # Test 4: Test StateMachineFallback unique constraint
    print("\n=== Testing StateMachineFallback spec compliance ===")

    fallback1 = StateMachineFallback(
        greenhouse_id=greenhouse_id,
        must_on_actuators=[str(uuid.uuid4()), str(uuid.uuid4())],
        must_off_actuators=[str(uuid.uuid4())],
        must_on_fan_groups=[{"fan_group_id": str(uuid.uuid4()), "on_count": 3}],
    )
    db.add(fallback1)
    db.commit()
    print(f"✓ Created StateMachineFallback: greenhouse_id={fallback1.greenhouse_id}")

    # Test 5: Try to create second fallback for same greenhouse (should fail)
    print("\n=== Testing StateMachineFallback unique greenhouse constraint ===")

    with pytest.raises(IntegrityError):
        fallback2 = StateMachineFallback(
            greenhouse_id=greenhouse_id,  # Same greenhouse
            must_on_actuators=[],
            must_off_actuators=[],
            must_on_fan_groups=[],
        )
        db.add(fallback2)
        db.commit()

    # Rollback after the integrity error
    db.rollback()
    print("✓ Unique greenhouse constraint enforced correctly")

    # Test 6: Verify JSON field structure and query
    print("\n=== Testing JSON field queries and structure ===")

    # Query the row back and verify JSON structure
    stored_row = db.get(StateMachineRow, row1_id)
    assert stored_row is not None

    print(f"  must_on_actuators type: {type(stored_row.must_on_actuators)}")
    print(f"  must_on_actuators content: {stored_row.must_on_actuators}")
    print(f"  must_on_fan_groups type: {type(stored_row.must_on_fan_groups)}")
    print(f"  must_on_fan_groups content: {stored_row.must_on_fan_groups}")

    # Verify structure
    assert isinstance(stored_row.must_on_actuators, list)
    assert all(isinstance(aid, str) for aid in stored_row.must_on_actuators)
    assert isinstance(stored_row.must_on_fan_groups, list)
    for fg in stored_row.must_on_fan_groups:
        assert "fan_group_id" in fg
        assert "on_count" in fg
        assert isinstance(fg["fan_group_id"], str)
        assert isinstance(fg["on_count"], int)

    print("✓ JSON field structure verified")

    print("\n=== All state machine spec compliance tests passed! ===")
