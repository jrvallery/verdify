"""
Tests for controller CRUD endpoints.
"""
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings


def test_create_controller(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test creating a controller."""
    # First create a greenhouse
    greenhouse_data = {
        "title": "Test Greenhouse for Controller",
        "description": "Test description",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    assert greenhouse_response.status_code == 201
    greenhouse_id = greenhouse_response.json()["id"]

    # Then create a controller
    data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-123abc",
        "label": "Test Controller",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    response = client.post(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
        json=data,
    )
    assert response.status_code == 201
    content = response.json()
    assert content["device_name"] == data["device_name"]
    assert content["label"] == data["label"]
    assert content["model"] == data["model"]
    assert content["is_climate_controller"] == data["is_climate_controller"]
    assert content["greenhouse_id"] == greenhouse_id
    assert "id" in content


def test_create_climate_controller_unique(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test that only one climate controller is allowed per greenhouse."""
    # Create greenhouse
    greenhouse_data = {
        "title": "Test Greenhouse for Climate Controller",
        "description": "Test description",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    # Create first climate controller
    data1 = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-111aaa",
        "label": "Climate Controller 1",
        "model": "ESP32",
        "is_climate_controller": True,
    }
    response1 = client.post(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
        json=data1,
    )
    assert response1.status_code == 201

    # Try to create second climate controller - should fail
    data2 = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-222bbb",
        "label": "Climate Controller 2",
        "model": "ESP32",
        "is_climate_controller": True,
    }
    response2 = client.post(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
        json=data2,
    )
    assert (
        response2.status_code == 409
    )  # Should fail due to climate controller constraint


def test_list_controllers(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test listing controllers."""
    # Create greenhouse and controller
    greenhouse_data = {
        "title": "Test Greenhouse for Controller List",
        "description": "Test description",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-11aa01",
        "label": "Test Controller for List",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    client.post(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )

    # List controllers
    response = client.get(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert "data" in content
    assert "page" in content
    assert "page_size" in content
    assert "total" in content


def test_list_controllers_with_filters(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test listing controllers with greenhouse_id and is_climate_controller filters."""
    # Create greenhouse
    greenhouse_data = {
        "title": "Test Greenhouse for Controller Filter",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    # Create controllers
    controller1_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-aaa111",
        "label": "Climate Controller",
        "model": "ESP32",
        "is_climate_controller": True,
    }
    client.post(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
        json=controller1_data,
    )

    controller2_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-bbb222",
        "label": "Regular Controller",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    client.post(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
        json=controller2_data,
    )

    # Test greenhouse_id filter
    response = client.get(
        f"{settings.API_V1_STR}/controllers/?greenhouse_id={greenhouse_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    for controller in content["data"]:
        assert controller["greenhouse_id"] == greenhouse_id

    # Test is_climate_controller filter
    response = client.get(
        f"{settings.API_V1_STR}/controllers/?is_climate_controller=true",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    for controller in content["data"]:
        assert controller["is_climate_controller"] is True


def test_get_controller(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test getting a specific controller."""
    # Create greenhouse and controller
    greenhouse_data = {
        "title": "Test Greenhouse for Controller Get",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-ccc333",
        "label": "Test Controller for Get",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = create_response.json()["id"]

    # Get the controller
    response = client.get(
        f"{settings.API_V1_STR}/controllers/{controller_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == controller_id
    assert content["device_name"] == controller_data["device_name"]


def test_update_controller(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test updating a controller."""
    # Create greenhouse and controller
    greenhouse_data = {
        "title": "Test Greenhouse for Controller Update",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-ddd444",
        "label": "Test Controller for Update",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = create_response.json()["id"]

    # Update the controller
    update_data = {
        "label": "Updated Controller Label",
        "fw_version": "1.2.3",
        "hw_version": "2.1",
    }
    response = client.patch(
        f"{settings.API_V1_STR}/controllers/{controller_id}",
        headers=superuser_token_headers,
        json=update_data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["label"] == update_data["label"]
    assert content["fw_version"] == update_data["fw_version"]
    assert content["hw_version"] == update_data["hw_version"]


def test_delete_controller(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test deleting a controller."""
    # Create greenhouse and controller
    greenhouse_data = {
        "title": "Test Greenhouse for Controller Delete",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-eee555",
        "label": "Test Controller for Delete",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = create_response.json()["id"]

    # Delete the controller
    response = client.delete(
        f"{settings.API_V1_STR}/controllers/{controller_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 204

    # Verify it's deleted
    get_response = client.get(
        f"{settings.API_V1_STR}/controllers/{controller_id}",
        headers=superuser_token_headers,
    )
    assert get_response.status_code == 404


def test_create_controller_requires_greenhouse_id(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """Test that creating a controller without greenhouse_id returns 422."""
    # Attempt to create controller without greenhouse_id
    data_without_greenhouse_id = {
        "device_name": "verdify-123def",
        "label": "Test Controller",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    response = client.post(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
        json=data_without_greenhouse_id,
    )
    assert response.status_code == 422
    error_content = response.json()
    assert "greenhouse_id" in str(error_content).lower()

    # Now test with valid greenhouse_id returns 201
    # First create a greenhouse
    greenhouse_data = {
        "title": "Test Greenhouse for Required ID Test",
        "description": "Test description",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    assert greenhouse_response.status_code == 201
    greenhouse_id = greenhouse_response.json()["id"]

    # Then create controller with valid greenhouse_id
    data_with_greenhouse_id = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-123def",
        "label": "Test Controller",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    response = client.post(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
        json=data_with_greenhouse_id,
    )
    assert response.status_code == 201
    content = response.json()
    assert content["greenhouse_id"] == greenhouse_id
    assert content["device_name"] == data_with_greenhouse_id["device_name"]


def test_controller_unauthorized(client: TestClient) -> None:
    """Test that controller endpoints require authentication."""
    response = client.get(f"{settings.API_V1_STR}/controllers/")
    assert response.status_code == 401

    data = {
        "greenhouse_id": str(uuid.uuid4()),
        "device_name": "verdify-test",
        "label": "Test",
        "model": "ESP32",
    }
    response = client.post(f"{settings.API_V1_STR}/controllers/", json=data)
    assert response.status_code == 401
