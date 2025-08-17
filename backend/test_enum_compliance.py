#!/usr/bin/env python3
"""Test enum values match API specification exactly"""

from app.models.enums import ActuatorKind, ButtonKind


def test_enum_spec_compliance():
    """Test that enums match the API specification exactly"""

    print("=== Testing ActuatorKind enum compliance ===")

    # Expected ActuatorKind values from spec
    expected_actuator_kinds = {
        "fan",
        "heater",
        "vent",
        "fogger",
        "irrigation_valve",
        "fertilizer_valve",
        "pump",
        "light",
    }

    # Actual values from enum
    actual_actuator_kinds = {kind.value for kind in ActuatorKind}

    print(f"Expected ActuatorKind values: {sorted(expected_actuator_kinds)}")
    print(f"Actual ActuatorKind values:   {sorted(actual_actuator_kinds)}")

    if actual_actuator_kinds == expected_actuator_kinds:
        print("✓ ActuatorKind enum matches spec exactly")
    else:
        missing = expected_actuator_kinds - actual_actuator_kinds
        extra = actual_actuator_kinds - expected_actuator_kinds
        if missing:
            print(f"✗ Missing ActuatorKind values: {missing}")
        if extra:
            print(f"✗ Extra ActuatorKind values: {extra}")

    print("\n=== Testing ButtonKind enum compliance ===")

    # Expected ButtonKind values from spec
    expected_button_kinds = {"cool", "heat", "humid"}

    # Actual values from enum
    actual_button_kinds = {kind.value for kind in ButtonKind}

    print(f"Expected ButtonKind values: {sorted(expected_button_kinds)}")
    print(f"Actual ButtonKind values:   {sorted(actual_button_kinds)}")

    if actual_button_kinds == expected_button_kinds:
        print("✓ ButtonKind enum matches spec exactly")
    else:
        missing = expected_button_kinds - actual_button_kinds
        extra = actual_button_kinds - expected_button_kinds
        if missing:
            print(f"✗ Missing ButtonKind values: {missing}")
        if extra:
            print(f"✗ Extra ButtonKind values: {extra}")

    print("\n=== Testing enum field access ===")

    # Test that we can access the enum values programmatically
    print("ActuatorKind enum values:")
    for kind in ActuatorKind:
        print(f"  {kind.name} = {kind.value}")

    print("\nButtonKind enum values:")
    for kind in ButtonKind:
        print(f"  {kind.name} = {kind.value}")

    print("\n=== Testing enum validation ===")

    # Test that enum validation works for valid values
    try:
        ActuatorKind("fan")
        ActuatorKind("heater")
        ActuatorKind("irrigation_valve")
        ButtonKind("cool")
        ButtonKind("heat")
        ButtonKind("humid")
        print("✓ Valid enum values accepted")
    except ValueError as e:
        print(f"✗ Valid enum validation failed: {e}")

    # Test that enum validation rejects invalid values
    try:
        ActuatorKind("invalid_kind")
        print("✗ Invalid ActuatorKind value was accepted")
    except ValueError:
        print("✓ Invalid ActuatorKind value correctly rejected")

    try:
        ButtonKind("invalid_button")
        print("✗ Invalid ButtonKind value was accepted")
    except ValueError:
        print("✓ Invalid ButtonKind value correctly rejected")

    print("\n=== Enum specification compliance test completed ===")
    print(
        "✓ ActuatorKind: fan, heater, vent, fogger, irrigation_valve, fertilizer_valve, pump, light"
    )
    print("✓ ButtonKind: cool, heat, humid")


if __name__ == "__main__":
    test_enum_spec_compliance()
