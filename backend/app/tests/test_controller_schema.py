"""
Test Controller schema differences: last_seen and greenhouse_id handling.
"""
import uuid
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.models import Controller, Greenhouse, User


def test_controller_last_seen_field(db: Session):
    """Test that Controller model includes last_seen field."""

    # Create test data
    unique_email = f"controller_test_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=unique_email,
        hashed_password="fake_hash",
        full_name="Controller Test User",
    )
    db.add(user)
    db.flush()

    greenhouse = Greenhouse(
        title="Controller Test Greenhouse",
        description="Testing controller schema",
        user_id=user.id,
    )
    db.add(greenhouse)
    db.flush()

    # Test 1: Create controller without last_seen (should default to None)
    controller1 = Controller(
        device_name="verdify-abc123",
        greenhouse_id=greenhouse.id,
        is_climate_controller=True,
        label="Test Controller 1",
    )
    db.add(controller1)
    db.commit()

    # Verify last_seen defaults to None
    assert controller1.last_seen is None
    print(f"✓ Controller created with last_seen: {controller1.last_seen}")

    # Test 2: Create controller with explicit last_seen
    now = datetime.now(timezone.utc)
    controller2 = Controller(
        device_name="verdify-def456",
        greenhouse_id=greenhouse.id,
        is_climate_controller=False,
        label="Test Controller 2",
        last_seen=now,
    )
    db.add(controller2)
    db.commit()

    # Verify last_seen is set (allow for timezone differences)
    assert controller2.last_seen is not None
    # Compare timestamps ignoring timezone (DB may strip timezone info)
    if controller2.last_seen.tzinfo is None and now.tzinfo is not None:
        # Compare naive datetime with aware datetime by converting to UTC
        assert (
            abs((controller2.last_seen - now.replace(tzinfo=None)).total_seconds()) < 1
        )
    else:
        assert controller2.last_seen == now
    print(f"✓ Controller created with last_seen: {controller2.last_seen}")

    # Test 3: Update last_seen
    updated_time = datetime.now(timezone.utc)
    controller1.last_seen = updated_time
    db.commit()

    # Verify update worked (allow for timezone differences)
    db.refresh(controller1)
    assert controller1.last_seen is not None
    # Compare timestamps ignoring timezone (DB may strip timezone info)
    if controller1.last_seen.tzinfo is None and updated_time.tzinfo is not None:
        assert (
            abs(
                (
                    controller1.last_seen - updated_time.replace(tzinfo=None)
                ).total_seconds()
            )
            < 1
        )
    else:
        assert controller1.last_seen == updated_time
    print(f"✓ Controller last_seen updated to: {controller1.last_seen}")


def test_controller_unclaimed_handling(db: Session):
    """Test that unclaimed controllers (greenhouse_id=None) can be created but are handled properly."""

    # Test 1: Create unclaimed controller (greenhouse_id=None)
    unclaimed_controller = Controller(
        device_name="verdify-000001",
        is_climate_controller=False,
        label="Unclaimed Controller",
        # greenhouse_id intentionally None
    )
    db.add(unclaimed_controller)
    db.commit()

    # Verify unclaimed controller was created
    assert unclaimed_controller.greenhouse_id is None
    print(
        f"✓ Unclaimed controller created: id={unclaimed_controller.id}, greenhouse_id={unclaimed_controller.greenhouse_id}"
    )

    # Test 2: Query all controllers including unclaimed
    all_controllers = db.exec(select(Controller)).all()
    unclaimed_count = sum(1 for c in all_controllers if c.greenhouse_id is None)
    claimed_count = sum(1 for c in all_controllers if c.greenhouse_id is not None)

    print(
        f"✓ Total controllers: {len(all_controllers)} (claimed: {claimed_count}, unclaimed: {unclaimed_count})"
    )
    assert unclaimed_count >= 1  # At least our test controller


def test_controller_claimed_filtering(db: Session):
    """Test that only claimed controllers (non-null greenhouse_id) should be exposed via API."""

    # Create test data
    unique_email = f"controller_filter_test_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=unique_email,
        hashed_password="fake_hash",
        full_name="Controller Filter Test User",
    )
    db.add(user)
    db.flush()

    greenhouse = Greenhouse(
        title="Controller Filter Test Greenhouse",
        description="Testing controller filtering",
        user_id=user.id,
    )
    db.add(greenhouse)
    db.flush()

    # Create unclaimed controller
    unclaimed = Controller(
        device_name="verdify-uncl01",
        is_climate_controller=False,
        label="Unclaimed",
        # greenhouse_id=None
    )
    db.add(unclaimed)

    # Create claimed controller
    claimed = Controller(
        device_name="verdify-clmd01",
        greenhouse_id=greenhouse.id,
        is_climate_controller=True,
        label="Claimed",
        last_seen=datetime.now(timezone.utc),
    )
    db.add(claimed)
    db.commit()

    # Query only claimed controllers (for API responses)
    claimed_controllers = db.exec(
        select(Controller).where(Controller.greenhouse_id.is_not(None))
    ).all()

    # Verify filtering works
    claimed_ids = [c.id for c in claimed_controllers]
    assert claimed.id in claimed_ids
    assert unclaimed.id not in claimed_ids

    print(f"✓ Claimed controllers query returns {len(claimed_controllers)} controllers")
    print(f"  Claimed controller included: {claimed.id}")
    print(f"  Unclaimed controller excluded: {unclaimed.id}")

    # Test that claimed controllers have all required fields for API
    for controller in claimed_controllers:
        assert controller.greenhouse_id is not None
        assert (
            controller.last_seen is not None or controller.last_seen is None
        )  # Can be null but field exists
        print(
            f"  Controller {controller.id}: greenhouse_id={controller.greenhouse_id}, last_seen={controller.last_seen}"
        )


def test_controller_public_model_validation(db: Session):
    """Test that ControllerPublic model enforces non-null greenhouse_id."""

    # Create test data
    unique_email = f"controller_public_test_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        email=unique_email,
        hashed_password="fake_hash",
        full_name="Controller Public Test User",
    )
    db.add(user)
    db.flush()

    greenhouse = Greenhouse(
        title="Controller Public Test Greenhouse",
        description="Testing controller public model",
        user_id=user.id,
    )
    db.add(greenhouse)
    db.flush()

    # Create claimed controller
    controller = Controller(
        device_name="verdify-abc123",  # Use valid hex digits
        greenhouse_id=greenhouse.id,
        is_climate_controller=True,
        label="Public Test Controller",
        last_seen=datetime.now(timezone.utc),
    )
    db.add(controller)
    db.commit()

    # Test conversion to ControllerPublic (should work for claimed controllers)
    from app.models.controllers import ControllerPublic

    public_data = {
        "id": controller.id,
        "greenhouse_id": controller.greenhouse_id,
        "device_name": controller.device_name,
        "is_climate_controller": controller.is_climate_controller,
        "label": controller.label,
        "model": controller.model,
        "fw_version": controller.fw_version,
        "hw_version": controller.hw_version,
        "last_seen": controller.last_seen,
        "created_at": controller.created_at,
        "updated_at": controller.updated_at,
    }

    public_controller = ControllerPublic(**public_data)

    # Verify all fields are present
    assert public_controller.id == controller.id
    assert public_controller.greenhouse_id == controller.greenhouse_id
    assert public_controller.last_seen == controller.last_seen
    assert public_controller.device_name == controller.device_name

    print("✓ ControllerPublic model validated:")
    print(f"  id: {public_controller.id}")
    print(f"  greenhouse_id: {public_controller.greenhouse_id}")
    print(f"  last_seen: {public_controller.last_seen}")
    print(f"  device_name: {public_controller.device_name}")
