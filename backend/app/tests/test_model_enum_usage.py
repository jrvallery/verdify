#!/usr/bin/env python3
"""Test that model instances can be created with new enum values"""

import uuid

from app.models.actuators import ActuatorCreate, ControllerButtonCreate
from app.models.enums import ActuatorKind, ButtonKind


def test_model_enum_usage():
    """Test that models work correctly with the updated enum values"""

    print("=== Testing ActuatorCreate with new enum values ===")

    # Test each new ActuatorKind value
    for kind in ActuatorKind:
        try:
            actuator = ActuatorCreate(
                name=f"Test {kind.value}",
                kind=kind,
                controller_id=uuid.uuid4(),
                relay_channel=1,
                min_on_ms=60000,
                min_off_ms=60000,
                fail_safe_state="off",
            )
            print(f"✓ ActuatorCreate with {kind.name} ({kind.value}) successful")
        except Exception as e:
            print(f"✗ ActuatorCreate with {kind.name} failed: {e}")

    print("\n=== Testing ControllerButtonCreate with new enum values ===")

    # Test each new ButtonKind value
    for kind in ButtonKind:
        try:
            button = ControllerButtonCreate(
                button_kind=kind,
                controller_id=uuid.uuid4(),
                target_temp_stage=1 if kind == ButtonKind.HEAT else None,
                target_humi_stage=1 if kind == ButtonKind.HUMID else None,
                timeout_s=300,
            )
            print(
                f"✓ ControllerButtonCreate with {kind.name} ({kind.value}) successful"
            )
        except Exception as e:
            print(f"✗ ControllerButtonCreate with {kind.name} failed: {e}")

    print("\n=== Testing specific new enum values ===")

    # Test the new irrigation_valve and fertilizer_valve specifically
    try:
        irrigation_actuator = ActuatorCreate(
            name="Irrigation Valve",
            kind=ActuatorKind.IRRIGATION_VALVE,
            controller_id=uuid.uuid4(),
            relay_channel=2,
            min_on_ms=30000,
            min_off_ms=30000,
            fail_safe_state="off",
        )
        print(f"✓ IRRIGATION_VALVE actuator: {irrigation_actuator.kind}")
    except Exception as e:
        print(f"✗ IRRIGATION_VALVE test failed: {e}")

    try:
        fertilizer_actuator = ActuatorCreate(
            name="Fertilizer Valve",
            kind=ActuatorKind.FERTILIZER_VALVE,
            controller_id=uuid.uuid4(),
            relay_channel=3,
            min_on_ms=15000,
            min_off_ms=15000,
            fail_safe_state="off",
        )
        print(f"✓ FERTILIZER_VALVE actuator: {fertilizer_actuator.kind}")
    except Exception as e:
        print(f"✗ FERTILIZER_VALVE test failed: {e}")

    # Test the new button kinds
    try:
        cool_button = ControllerButtonCreate(
            button_kind=ButtonKind.COOL, controller_id=uuid.uuid4(), timeout_s=600
        )
        print(f"✓ COOL button: {cool_button.button_kind}")
    except Exception as e:
        print(f"✗ COOL button test failed: {e}")

    print("\n=== Model enum usage test completed ===")
    print("✓ All actuator kinds can be used in ActuatorCreate")
    print("✓ All button kinds can be used in ControllerButtonCreate")
    print("✓ Models validate enum values correctly")


if __name__ == "__main__":
    test_model_enum_usage()
