"""
Tests for controller button CRUD endpoints.
"""
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings


def test_create_controller_button(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test creating a controller button."""
    # Create greenhouse
    greenhouse_data = {
        "title": "Test Greenhouse for Button",
        "description": "Test description for button testing",
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
        "device_name": "verdify-c00001",
        "label": "Test Controller for Button",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    # Create controller button
    button_data = {
        "controller_id": controller_id,
        "button_kind": "temp_up",
        "target_temp_stage": 1,
        "timeout_s": 300,
    }
    response = client.post(
        f"{settings.API_V1_STR}/buttons/",
        headers=superuser_token_headers,
        json=button_data,
    )
    assert response.status_code == 201
    content = response.json()
    assert content["button_kind"] == "temp_up"
    assert content["target_temp_stage"] == 1
    assert content["timeout_s"] == 300
    assert content["controller_id"] == controller_id
    assert "id" in content


def test_list_controller_buttons(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test listing controller buttons."""
    response = client.get(
        f"{settings.API_V1_STR}/buttons/",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert "data" in content
    assert "page" in content
    assert "page_size" in content
    assert "total" in content


def test_get_controller_button(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test getting a controller button by ID."""
    # Create greenhouse, controller, and button first
    greenhouse_data = {
        "title": "Test Greenhouse for Get Button",
        "description": "Test description for get button",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-c00002",
        "label": "Test Controller for Get Button",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    button_data = {
        "controller_id": controller_id,
        "button_kind": "humidity_up",
        "target_humi_stage": 2,
        "timeout_s": 600,
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/buttons/",
        headers=superuser_token_headers,
        json=button_data,
    )
    button_id = create_response.json()["id"]

    # Get the button
    response = client.get(
        f"{settings.API_V1_STR}/buttons/{button_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == button_id
    assert content["button_kind"] == "humidity_up"
    assert content["target_humi_stage"] == 2


def test_update_controller_button(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test updating a controller button."""
    # Create greenhouse, controller, and button first
    greenhouse_data = {
        "title": "Test Greenhouse for Update Button",
        "description": "Test description for update button",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-c00003",
        "label": "Test Controller for Update Button",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    button_data = {
        "controller_id": controller_id,
        "button_kind": "humidity_down",
        "timeout_s": 120,
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/buttons/",
        headers=superuser_token_headers,
        json=button_data,
    )
    button_id = create_response.json()["id"]

    # Update the button
    update_data = {"timeout_s": 900, "target_temp_stage": 3}
    response = client.patch(
        f"{settings.API_V1_STR}/buttons/{button_id}",
        headers=superuser_token_headers,
        json=update_data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["timeout_s"] == 900
    assert content["target_temp_stage"] == 3


def test_delete_controller_button(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test deleting a controller button."""
    # Create greenhouse, controller, and button first
    greenhouse_data = {
        "title": "Test Greenhouse for Delete Button",
        "description": "Test description for delete button",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-c00004",
        "label": "Test Controller for Delete Button",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    button_data = {
        "controller_id": controller_id,
        "button_kind": "temp_down",
        "timeout_s": 180,
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/buttons/",
        headers=superuser_token_headers,
        json=button_data,
    )
    button_id = create_response.json()["id"]

    # Delete the button
    response = client.delete(
        f"{settings.API_V1_STR}/buttons/{button_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 204


def test_controller_button_permission_validation(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """Test that users can only access controller buttons they own."""
    # Create greenhouse, controller, and button as superuser
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
        "device_name": "verdify-c00005",
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

    button_data = {
        "controller_id": controller_id,
        "button_kind": "emergency_stop",
        "timeout_s": 60,
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/buttons/",
        headers=superuser_token_headers,
        json=button_data,
    )
    button_id = create_response.json()["id"]

    # Try to access as normal user (should fail with 403)
    response = client.get(
        f"{settings.API_V1_STR}/buttons/{button_id}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 403


def test_controller_button_unauthorized(client: TestClient) -> None:
    """Test that controller button endpoints require authentication."""
    response = client.get(f"{settings.API_V1_STR}/buttons/")
    assert response.status_code == 401

    data = {"controller_id": str(uuid.uuid4()), "button_kind": "cool", "timeout_s": 300}
    response = client.post(f"{settings.API_V1_STR}/buttons/", json=data)
    assert response.status_code == 401
