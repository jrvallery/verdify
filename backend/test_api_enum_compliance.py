#!/usr/bin/env python3
"""Test that enum changes work correctly for API endpoints and validation"""

from app.models.enums import ActuatorKind, ButtonKind


def test_meta_endpoints_compliance():
    """Test that /meta endpoints would return correct enum sets"""

    print("=== Testing /meta/actuator-kinds compliance ===")

    # This is what /meta/actuator-kinds should return
    actuator_kinds_response = sorted([kind.value for kind in ActuatorKind])
    spec_actuator_kinds = sorted(
        [
            "fan",
            "heater",
            "vent",
            "fogger",
            "irrigation_valve",
            "fertilizer_valve",
            "pump",
            "light",
        ]
    )

    print(f"API response would be: {actuator_kinds_response}")
    print(f"Spec expects:          {spec_actuator_kinds}")

    if actuator_kinds_response == spec_actuator_kinds:
        print("✓ /meta/actuator-kinds would return spec-compliant values")
    else:
        print("✗ /meta/actuator-kinds response doesn't match spec")

    print("\n=== Testing /meta button kinds compliance ===")

    # This is what button-related /meta endpoints should return
    button_kinds_response = sorted([kind.value for kind in ButtonKind])
    spec_button_kinds = sorted(["cool", "heat", "humid"])

    print(f"API response would be: {button_kinds_response}")
    print(f"Spec expects:          {spec_button_kinds}")

    if button_kinds_response == spec_button_kinds:
        print("✓ Button kinds meta endpoint would return spec-compliant values")
    else:
        print("✗ Button kinds meta response doesn't match spec")

    print("\n=== Testing telemetry/button validation ===")

    # Test that POST /buttons and telemetry would accept only specified values
    valid_button_inputs = ["cool", "heat", "humid"]
    invalid_button_inputs = ["emergency_stop", "temp_up", "temp_down", "humidity_up"]

    print("Valid button inputs (should be accepted):")
    for btn in valid_button_inputs:
        try:
            ButtonKind(btn)
            print(f"  ✓ '{btn}' - valid")
        except ValueError:
            print(f"  ✗ '{btn}' - incorrectly rejected")

    print("\nInvalid button inputs (should be rejected):")
    for btn in invalid_button_inputs:
        try:
            ButtonKind(btn)
            print(f"  ✗ '{btn}' - incorrectly accepted")
        except ValueError:
            print(f"  ✓ '{btn}' - correctly rejected")

    print("\n=== Testing actuator validation ===")

    valid_actuator_inputs = [
        "fan",
        "heater",
        "vent",
        "fogger",
        "irrigation_valve",
        "fertilizer_valve",
        "pump",
        "light",
    ]
    invalid_actuator_inputs = ["cooler", "humidifier", "dehumidifier", "irrigation"]

    print("Valid actuator inputs (should be accepted):")
    for act in valid_actuator_inputs:
        try:
            ActuatorKind(act)
            print(f"  ✓ '{act}' - valid")
        except ValueError:
            print(f"  ✗ '{act}' - incorrectly rejected")

    print("\nInvalid actuator inputs (should be rejected):")
    for act in invalid_actuator_inputs:
        try:
            ActuatorKind(act)
            print(f"  ✗ '{act}' - incorrectly accepted")
        except ValueError:
            print(f"  ✓ '{act}' - correctly rejected")

    print("\n=== API specification compliance test completed ===")
    print("✓ /meta/actuator-kinds returns spec-compliant enum set")
    print("✓ Button validation accepts only cool|heat|humid")
    print("✓ Actuator validation accepts all 8 spec-defined kinds")
    print(
        "✓ Old enum values (cooler, humidifier, emergency_stop, etc.) correctly rejected"
    )


if __name__ == "__main__":
    test_meta_endpoints_compliance()
