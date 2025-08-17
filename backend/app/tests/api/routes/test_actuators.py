"""
Tests for actuator CRUD endpoints.
"""
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings


def test_create_actuator(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test creating an actuator."""
    # Create greenhouse
    greenhouse_data = {
        "title": "Test Greenhouse for Actuator",
        "description": "Test description for actuator testing",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    # Create controller
    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-b00001",
        "label": "Test Controller for Actuator",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    # Create actuator
    actuator_data = {
        "controller_id": controller_id,
        "name": "Test Fan",
        "kind": "fan",
        "relay_channel": 1,
        "min_on_ms": 60000,
        "min_off_ms": 60000,
        "fail_safe_state": "off",
    }
    response = client.post(
        f"{settings.API_V1_STR}/actuators/",
        headers=superuser_token_headers,
        json=actuator_data,
    )
    assert response.status_code == 201
    content = response.json()
    assert content["name"] == "Test Fan"
    assert content["kind"] == "fan"
    assert content["controller_id"] == controller_id
    assert "id" in content


def test_list_actuators(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test listing actuators."""
    response = client.get(
        f"{settings.API_V1_STR}/actuators/",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert "data" in content
    assert "page" in content
    assert "page_size" in content
    assert "total" in content


def test_get_actuator(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test getting an actuator by ID."""
    # Create greenhouse, controller, and actuator first
    greenhouse_data = {
        "title": "Test Greenhouse for Get Actuator",
        "description": "Test description for get actuator",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-b00002",
        "label": "Test Controller for Get Actuator",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    actuator_data = {
        "controller_id": controller_id,
        "name": "Test Heater",
        "kind": "heater",
        "relay_channel": 2,
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/actuators/",
        headers=superuser_token_headers,
        json=actuator_data,
    )
    actuator_id = create_response.json()["id"]

    # Get the actuator
    response = client.get(
        f"{settings.API_V1_STR}/actuators/{actuator_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == actuator_id
    assert content["name"] == "Test Heater"
    assert content["kind"] == "heater"


def test_update_actuator(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test updating an actuator."""
    # Create greenhouse, controller, and actuator first
    greenhouse_data = {
        "title": "Test Greenhouse for Update Actuator",
        "description": "Test description for update actuator",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-b00003",
        "label": "Test Controller for Update Actuator",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    actuator_data = {
        "controller_id": controller_id,
        "name": "Test Irrigation",
        "kind": "irrigation",
        "relay_channel": 3,
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/actuators/",
        headers=superuser_token_headers,
        json=actuator_data,
    )
    assert create_response.status_code == 201
    actuator_id = create_response.json()["id"]

    # Update the actuator
    update_data = {"name": "Updated Test Pump", "min_on_ms": 30000}
    response = client.patch(
        f"{settings.API_V1_STR}/actuators/{actuator_id}",
        headers=superuser_token_headers,
        json=update_data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["name"] == "Updated Test Pump"
    assert content["min_on_ms"] == 30000


def test_delete_actuator(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test deleting an actuator."""
    # Create greenhouse, controller, and actuator first
    greenhouse_data = {
        "title": "Test Greenhouse for Delete Actuator",
        "description": "Test description for delete actuator",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-b00004",
        "label": "Test Controller for Delete Actuator",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    actuator_data = {
        "controller_id": controller_id,
        "name": "Test Light",
        "kind": "light",
        "relay_channel": 4,
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/actuators/",
        headers=superuser_token_headers,
        json=actuator_data,
    )
    actuator_id = create_response.json()["id"]

    # Delete the actuator
    response = client.delete(
        f"{settings.API_V1_STR}/actuators/{actuator_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 204


def test_actuator_permission_validation(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """Test that users can only access actuators they own."""
    # Create greenhouse, controller, and actuator as superuser
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

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-b00005",
        "label": "Test Controller for Permission",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    actuator_data = {
        "controller_id": controller_id,
        "name": "Test Vent",
        "kind": "vent",
        "relay_channel": 5,
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/actuators/",
        headers=superuser_token_headers,
        json=actuator_data,
    )
    actuator_id = create_response.json()["id"]

    # Try to access as normal user (should fail with 403)
    response = client.get(
        f"{settings.API_V1_STR}/actuators/{actuator_id}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 403


def test_actuator_unauthorized(client: TestClient) -> None:
    """Test that actuator endpoints require authentication."""
    response = client.get(f"{settings.API_V1_STR}/actuators/")
    assert response.status_code == 401

    data = {"controller_id": str(uuid.uuid4()), "name": "Test", "kind": "fan"}
    response = client.post(f"{settings.API_V1_STR}/actuators/", json=data)
    assert response.status_code == 401
