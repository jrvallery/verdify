"""
Tests for sensor CRUD endpoints.
"""
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings


def test_create_sensor(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test creating a sensor."""
    # Create greenhouse and controller first
    greenhouse_data = {
        "title": "Test Greenhouse for Sensor",
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
        "device_name": "verdify-a00001",
        "label": "Test Controller for Sensor",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    # Create sensor
    data = {
        "controller_id": controller_id,
        "name": "Test Temperature Sensor",
        "kind": "temperature",
        "scope": "zone",
        "include_in_climate_loop": True,
        "modbus_slave_id": 1,
        "modbus_reg": 100,
        "value_type": "float",
        "scale_factor": 1.0,
        "offset": 0.0,
        "poll_interval_s": 30,
    }
    response = client.post(
        f"{settings.API_V1_STR}/sensors/",
        headers=superuser_token_headers,
        json=data,
    )
    assert response.status_code == 201
    content = response.json()
    assert content["name"] == data["name"]
    assert content["kind"] == data["kind"]
    assert content["scope"] == data["scope"]
    assert content["include_in_climate_loop"] == data["include_in_climate_loop"]
    assert content["controller_id"] == controller_id
    assert "id" in content


def test_list_sensors(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test listing sensors."""
    # Create greenhouse, controller, and sensor
    greenhouse_data = {
        "title": "Test Greenhouse for Sensor List",
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
        "device_name": "verdify-a00002",
        "label": "Test Controller for Sensor List",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    sensor_data = {
        "controller_id": controller_id,
        "name": "Test Sensor for List",
        "kind": "humidity",
        "scope": "zone",
    }
    client.post(
        f"{settings.API_V1_STR}/sensors/",
        headers=superuser_token_headers,
        json=sensor_data,
    )

    # List sensors
    response = client.get(
        f"{settings.API_V1_STR}/sensors/",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert "data" in content
    assert "page" in content
    assert "page_size" in content
    assert "total" in content


def test_list_sensors_with_filters(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test listing sensors with kind, controller_id, and greenhouse_id filters."""
    # Create greenhouse and controller
    greenhouse_data = {
        "title": "Test Greenhouse for Sensor Filter",
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
        "device_name": "verdify-a00003",
        "label": "Test Controller for Sensor Filter",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    # Create different types of sensors
    sensor1_data = {
        "controller_id": controller_id,
        "name": "Temperature Sensor",
        "kind": "temperature",
        "scope": "zone",
    }
    client.post(
        f"{settings.API_V1_STR}/sensors/",
        headers=superuser_token_headers,
        json=sensor1_data,
    )

    sensor2_data = {
        "controller_id": controller_id,
        "name": "Humidity Sensor",
        "kind": "humidity",
        "scope": "zone",
    }
    client.post(
        f"{settings.API_V1_STR}/sensors/",
        headers=superuser_token_headers,
        json=sensor2_data,
    )

    # Test kind filter
    response = client.get(
        f"{settings.API_V1_STR}/sensors/?kind=temperature",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    for sensor in content["data"]:
        assert sensor["kind"] == "temperature"

    # Test controller_id filter
    response = client.get(
        f"{settings.API_V1_STR}/sensors/?controller_id={controller_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    for sensor in content["data"]:
        assert sensor["controller_id"] == controller_id

    # Test greenhouse_id filter
    response = client.get(
        f"{settings.API_V1_STR}/sensors/?greenhouse_id={greenhouse_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    # Should return sensors since they belong to controllers in this greenhouse


def test_get_sensor(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test getting a specific sensor."""
    # Create greenhouse, controller, and sensor
    greenhouse_data = {
        "title": "Test Greenhouse for Sensor Get",
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
        "device_name": "verdify-a00004",
        "label": "Test Controller for Sensor Get",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    sensor_data = {
        "controller_id": controller_id,
        "name": "Test Sensor for Get",
        "kind": "co2",
        "scope": "zone",
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/sensors/",
        headers=superuser_token_headers,
        json=sensor_data,
    )
    sensor_id = create_response.json()["id"]

    # Get the sensor
    response = client.get(
        f"{settings.API_V1_STR}/sensors/{sensor_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == sensor_id
    assert content["name"] == sensor_data["name"]


def test_update_sensor(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test updating a sensor."""
    # Create greenhouse, controller, and sensor
    greenhouse_data = {
        "title": "Test Greenhouse for Sensor Update",
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
        "device_name": "verdify-a00005",
        "label": "Test Controller for Sensor Update",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    sensor_data = {
        "controller_id": controller_id,
        "name": "Test Sensor for Update",
        "kind": "light",
        "scope": "zone",
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/sensors/",
        headers=superuser_token_headers,
        json=sensor_data,
    )
    sensor_id = create_response.json()["id"]

    # Update the sensor
    update_data = {
        "name": "Updated Sensor Name",
        "include_in_climate_loop": True,
        "poll_interval_s": 60,
    }
    response = client.patch(
        f"{settings.API_V1_STR}/sensors/{sensor_id}",
        headers=superuser_token_headers,
        json=update_data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["name"] == update_data["name"]
    assert content["include_in_climate_loop"] == update_data["include_in_climate_loop"]
    assert content["poll_interval_s"] == update_data["poll_interval_s"]


def test_delete_sensor(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test deleting a sensor."""
    # Create greenhouse, controller, and sensor
    greenhouse_data = {
        "title": "Test Greenhouse for Sensor Delete",
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
        "device_name": "verdify-a00006",
        "label": "Test Controller for Sensor Delete",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    sensor_data = {
        "controller_id": controller_id,
        "name": "Test Sensor for Delete",
        "kind": "soil_moisture",
        "scope": "zone",
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/sensors/",
        headers=superuser_token_headers,
        json=sensor_data,
    )
    sensor_id = create_response.json()["id"]

    # Delete the sensor
    response = client.delete(
        f"{settings.API_V1_STR}/sensors/{sensor_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200  # Assuming it returns {"ok": True}

    # Verify it's deleted
    get_response = client.get(
        f"{settings.API_V1_STR}/sensors/{sensor_id}",
        headers=superuser_token_headers,
    )
    assert get_response.status_code == 404


def test_sensor_unauthorized(client: TestClient) -> None:
    """Test that sensor endpoints require authentication."""
    response = client.get(f"{settings.API_V1_STR}/sensors/")
    assert response.status_code == 401

    data = {
        "controller_id": str(uuid.uuid4()),
        "name": "Test",
        "kind": "temperature",
        "scope": "zone",
    }
    response = client.post(f"{settings.API_V1_STR}/sensors/", json=data)
    assert response.status_code == 401
