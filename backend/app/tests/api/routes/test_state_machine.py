"""
Tests for state machine CRUD operations.
"""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings


def test_create_state_machine_row(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test creating a state machine row."""
    # Create greenhouse first
    greenhouse_data = {
        "title": "Test Greenhouse for State Machine",
        "description": "Test description for state machine testing",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    # Create actuator for testing
    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-statemach1",
        "label": "Test Controller for State Machine",
        "model": "ESP32",
        "is_climate_controller": True,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    actuator_data = {
        "controller_id": controller_id,
        "name": "Test Fan",
        "kind": "fan",
        "relay_channel": 1,
    }
    actuator_response = client.post(
        f"{settings.API_V1_STR}/actuators/",
        headers=superuser_token_headers,
        json=actuator_data,
    )
    actuator_id = actuator_response.json()["id"]

    # Create state machine row
    row_data = {
        "greenhouse_id": greenhouse_id,
        "temp_stage": 1,
        "humi_stage": 2,
        "is_fallback": False,
        "must_on_actuators": [actuator_id],
        "must_off_actuators": [],
        "must_on_fan_groups": [],
    }
    response = client.post(
        f"{settings.API_V1_STR}/state-machine-rows/",
        headers=superuser_token_headers,
        json=row_data,
    )
    assert response.status_code == 201
    content = response.json()
    assert content["temp_stage"] == 1
    assert content["humi_stage"] == 2
    assert content["is_fallback"] is False
    assert content["must_on_actuators"] == [actuator_id]
    assert content["must_off_actuators"] == []
    assert content["must_on_fan_groups"] == []


def test_create_duplicate_state_machine_row_returns_409(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test that creating duplicate grid position returns 409."""
    # Create greenhouse first
    greenhouse_data = {
        "title": "Test Greenhouse for Duplicate",
        "description": "Test description for duplicate testing",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    # Create first state machine row
    row_data = {
        "greenhouse_id": greenhouse_id,
        "temp_stage": 1,
        "humi_stage": 1,
        "is_fallback": False,
        "must_on_actuators": [],
        "must_off_actuators": [],
        "must_on_fan_groups": [],
    }
    response1 = client.post(
        f"{settings.API_V1_STR}/state-machine-rows/",
        headers=superuser_token_headers,
        json=row_data,
    )
    assert response1.status_code == 201

    # Try to create duplicate - should return 409
    response2 = client.post(
        f"{settings.API_V1_STR}/state-machine-rows/",
        headers=superuser_token_headers,
        json=row_data,
    )
    assert response2.status_code == 409
    # Check the error message in the custom ErrorResponse format
    response_json = response2.json()
    assert "already exists" in response_json["message"]


def test_list_state_machine_rows(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test listing state machine rows."""
    response = client.get(
        f"{settings.API_V1_STR}/state-machine-rows/",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert "data" in content
    assert "page" in content
    assert "page_size" in content
    assert "total" in content


def test_get_state_machine_row(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test getting a state machine row by ID."""
    # Create greenhouse and row first
    greenhouse_data = {
        "title": "Test Greenhouse for Get Row",
        "description": "Test description for get row",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    row_data = {
        "greenhouse_id": greenhouse_id,
        "temp_stage": -2,
        "humi_stage": 3,
        "is_fallback": False,
        "must_on_actuators": [],
        "must_off_actuators": [],
        "must_on_fan_groups": [],
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/state-machine-rows/",
        headers=superuser_token_headers,
        json=row_data,
    )
    row_id = create_response.json()["id"]

    # Get the row
    response = client.get(
        f"{settings.API_V1_STR}/state-machine-rows/{row_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == row_id
    assert content["temp_stage"] == -2
    assert content["humi_stage"] == 3


def test_update_state_machine_row(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test updating a state machine row."""
    # Create greenhouse and row first
    greenhouse_data = {
        "title": "Test Greenhouse for Update Row",
        "description": "Test description for update row",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    row_data = {
        "greenhouse_id": greenhouse_id,
        "temp_stage": 0,
        "humi_stage": 0,
        "is_fallback": False,
        "must_on_actuators": [],
        "must_off_actuators": [],
        "must_on_fan_groups": [],
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/state-machine-rows/",
        headers=superuser_token_headers,
        json=row_data,
    )
    row_id = create_response.json()["id"]

    # Update the row
    update_data = {"temp_stage": 2, "humi_stage": -1}
    response = client.put(
        f"{settings.API_V1_STR}/state-machine-rows/{row_id}",
        headers=superuser_token_headers,
        json=update_data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["temp_stage"] == 2
    assert content["humi_stage"] == -1


def test_delete_state_machine_row(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test deleting a state machine row."""
    # Create greenhouse and row first
    greenhouse_data = {
        "title": "Test Greenhouse for Delete Row",
        "description": "Test description for delete row",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    row_data = {
        "greenhouse_id": greenhouse_id,
        "temp_stage": -3,
        "humi_stage": 3,
        "is_fallback": False,
        "must_on_actuators": [],
        "must_off_actuators": [],
        "must_on_fan_groups": [],
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/state-machine-rows/",
        headers=superuser_token_headers,
        json=row_data,
    )
    row_id = create_response.json()["id"]

    # Delete the row
    response = client.delete(
        f"{settings.API_V1_STR}/state-machine-rows/{row_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 204

    # Verify it's deleted
    get_response = client.get(
        f"{settings.API_V1_STR}/state-machine-rows/{row_id}",
        headers=superuser_token_headers,
    )
    assert get_response.status_code == 404


def test_state_machine_row_permission_validation(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """Test that users can only access state machine rows they own."""
    # Create greenhouse and row as superuser
    greenhouse_data = {
        "title": "Test Greenhouse for Permission",
        "description": "Test description for permission validation",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    row_data = {
        "greenhouse_id": greenhouse_id,
        "temp_stage": 1,
        "humi_stage": 1,
        "is_fallback": False,
        "must_on_actuators": [],
        "must_off_actuators": [],
        "must_on_fan_groups": [],
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/state-machine-rows/",
        headers=superuser_token_headers,
        json=row_data,
    )
    row_id = create_response.json()["id"]

    # Try to access with normal user - should fail
    response = client.get(
        f"{settings.API_V1_STR}/state-machine-rows/{row_id}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 404


def test_set_state_machine_fallback(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test setting state machine fallback configuration."""
    # Create greenhouse first
    greenhouse_data = {
        "title": "Test Greenhouse for Fallback",
        "description": "Test description for fallback testing",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    # Set fallback configuration
    fallback_data = {
        "must_on_actuators": [],
        "must_off_actuators": [],
        "must_on_fan_groups": [],
    }
    response = client.put(
        f"{settings.API_V1_STR}/state-machine-fallback/{greenhouse_id}",
        headers=superuser_token_headers,
        json=fallback_data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["greenhouse_id"] == greenhouse_id
    assert content["must_on_actuators"] == []
    assert content["must_off_actuators"] == []
    assert content["must_on_fan_groups"] == []


def test_get_state_machine_fallback(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test getting state machine fallback configuration."""
    # Create greenhouse and set fallback first
    greenhouse_data = {
        "title": "Test Greenhouse for Get Fallback",
        "description": "Test description for get fallback",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    fallback_data = {
        "must_on_actuators": [],
        "must_off_actuators": [],
        "must_on_fan_groups": [],
    }
    client.put(
        f"{settings.API_V1_STR}/state-machine-fallback/{greenhouse_id}",
        headers=superuser_token_headers,
        json=fallback_data,
    )

    # Get the fallback
    response = client.get(
        f"{settings.API_V1_STR}/state-machine-fallback/{greenhouse_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["greenhouse_id"] == greenhouse_id


def test_validate_temp_and_humi_stage_constraints(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test that temp_stage and humi_stage are validated to be within -3 to +3."""
    # Create greenhouse first
    greenhouse_data = {
        "title": "Test Greenhouse for Validation",
        "description": "Test description for validation testing",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    # Test invalid temp_stage (too high)
    row_data = {
        "greenhouse_id": greenhouse_id,
        "temp_stage": 4,  # Invalid: > 3
        "humi_stage": 1,
        "is_fallback": False,
        "must_on_actuators": [],
        "must_off_actuators": [],
        "must_on_fan_groups": [],
    }
    response = client.post(
        f"{settings.API_V1_STR}/state-machine-rows/",
        headers=superuser_token_headers,
        json=row_data,
    )
    assert response.status_code == 422

    # Test invalid humi_stage (too low)
    row_data["temp_stage"] = 1
    row_data["humi_stage"] = -4  # Invalid: < -3
    response = client.post(
        f"{settings.API_V1_STR}/state-machine-rows/",
        headers=superuser_token_headers,
        json=row_data,
    )
    assert response.status_code == 422

    # Test valid values
    row_data["temp_stage"] = -3  # Valid minimum
    row_data["humi_stage"] = 3  # Valid maximum
    response = client.post(
        f"{settings.API_V1_STR}/state-machine-rows/",
        headers=superuser_token_headers,
        json=row_data,
    )
    assert response.status_code == 201
