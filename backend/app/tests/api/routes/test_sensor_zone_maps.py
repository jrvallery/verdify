"""
Tests for sensor-zone mapping endpoints.
"""
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings


def test_create_sensor_zone_map(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test creating a sensor-zone mapping."""
    # Create greenhouse
    greenhouse_data = {
        "title": "Test Greenhouse for Sensor-Zone Map",
        "description": "Test description for sensor zone mapping",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    # Create zone
    zone_data = {
        "greenhouse_id": greenhouse_id,
        "zone_number": 1,
        "location": "N",
        "context_text": "Test Zone for Mapping",
    }
    zone_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/zones/",
        headers=superuser_token_headers,
        json=zone_data,
    )
    zone_id = zone_response.json()["id"]

    # Create controller
    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-szmap1",
        "label": "Test Controller for Mapping",
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
    sensor_data = {
        "controller_id": controller_id,
        "name": "Test Sensor for Mapping",
        "kind": "temperature",
        "scope": "zone",
    }
    sensor_response = client.post(
        f"{settings.API_V1_STR}/sensors/",
        headers=superuser_token_headers,
        json=sensor_data,
    )
    sensor_id = sensor_response.json()["id"]

    # Create sensor-zone mapping
    map_data = {"sensor_id": sensor_id, "zone_id": zone_id, "kind": "temperature"}
    response = client.post(
        f"{settings.API_V1_STR}/sensor-zone-maps/",
        headers=superuser_token_headers,
        json=map_data,
    )
    assert response.status_code == 201
    content = response.json()
    assert content["sensor_id"] == sensor_id
    assert content["zone_id"] == zone_id
    assert content["kind"] == "temperature"


def test_create_duplicate_sensor_zone_map(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test that creating duplicate sensor-zone mappings returns 409."""
    # Create greenhouse, zone, controller, and sensor
    greenhouse_data = {
        "title": "Test Greenhouse for Duplicate Map",
        "description": "Test description for duplicate mapping",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    zone_data = {
        "greenhouse_id": greenhouse_id,
        "zone_number": 1,
        "location": "N",
        "context_text": "Test Zone for Duplicate",
    }
    zone_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/zones/",
        headers=superuser_token_headers,
        json=zone_data,
    )
    zone_id = zone_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-szdup1",
        "label": "Test Controller for Duplicate",
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
        "name": "Test Sensor for Duplicate",
        "kind": "humidity",
        "scope": "zone",
    }
    sensor_response = client.post(
        f"{settings.API_V1_STR}/sensors/",
        headers=superuser_token_headers,
        json=sensor_data,
    )
    sensor_id = sensor_response.json()["id"]

    # Create first mapping
    map_data = {"sensor_id": sensor_id, "zone_id": zone_id, "kind": "humidity"}
    response1 = client.post(
        f"{settings.API_V1_STR}/sensor-zone-maps/",
        headers=superuser_token_headers,
        json=map_data,
    )
    assert response1.status_code == 201

    # Try to create duplicate mapping - should fail with 409
    response2 = client.post(
        f"{settings.API_V1_STR}/sensor-zone-maps/",
        headers=superuser_token_headers,
        json=map_data,
    )
    assert response2.status_code == 409


def test_delete_sensor_zone_map(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test deleting a sensor-zone mapping."""
    # Create greenhouse, zone, controller, and sensor
    greenhouse_data = {
        "title": "Test Greenhouse for Map Delete",
        "description": "Test description for map deletion",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    zone_data = {
        "greenhouse_id": greenhouse_id,
        "zone_number": 1,
        "location": "N",
        "context_text": "Test Zone for Map Delete",
    }
    zone_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/zones/",
        headers=superuser_token_headers,
        json=zone_data,
    )
    zone_id = zone_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-szdel1",
        "label": "Test Controller for Map Delete",
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
        "name": "Test Sensor for Map Delete",
        "kind": "co2",
        "scope": "zone",
    }
    sensor_response = client.post(
        f"{settings.API_V1_STR}/sensors/",
        headers=superuser_token_headers,
        json=sensor_data,
    )
    sensor_id = sensor_response.json()["id"]

    # Create mapping first
    map_data = {"sensor_id": sensor_id, "zone_id": zone_id, "kind": "co2"}
    create_response = client.post(
        f"{settings.API_V1_STR}/sensor-zone-maps/",
        headers=superuser_token_headers,
        json=map_data,
    )
    assert create_response.status_code == 201

    # Delete the mapping
    response = client.delete(
        f"{settings.API_V1_STR}/sensor-zone-maps/",
        headers=superuser_token_headers,
        params={"sensor_id": sensor_id, "zone_id": zone_id, "kind": "co2"},
    )
    assert response.status_code == 204


def test_delete_nonexistent_sensor_zone_map(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test deleting a nonexistent sensor-zone mapping returns 403."""
    fake_sensor_id = str(uuid.uuid4())
    fake_zone_id = str(uuid.uuid4())

    response = client.delete(
        f"{settings.API_V1_STR}/sensor-zone-maps/",
        headers=superuser_token_headers,
        params={
            "sensor_id": fake_sensor_id,
            "zone_id": fake_zone_id,
            "kind": "temperature",
        },
    )
    assert response.status_code == 403


def test_sensor_zone_map_permission_validation(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    normal_user_token_headers: dict[str, str],
    db: Session,
) -> None:
    """Test that users can only create mappings for sensors/zones they own."""
    # Create greenhouse, zone, controller, and sensor as superuser
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

    zone_data = {
        "greenhouse_id": greenhouse_id,
        "zone_number": 1,
        "location": "N",
        "context_text": "Test Zone for Permission",
    }
    zone_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/zones/",
        headers=superuser_token_headers,
        json=zone_data,
    )
    zone_id = zone_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-szperm1",
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

    sensor_data = {
        "controller_id": controller_id,
        "name": "Test Sensor for Permission",
        "kind": "light",
        "scope": "zone",
    }
    sensor_response = client.post(
        f"{settings.API_V1_STR}/sensors/",
        headers=superuser_token_headers,
        json=sensor_data,
    )
    sensor_id = sensor_response.json()["id"]

    # Try to create mapping as normal user (should fail with 403)
    map_data = {"sensor_id": sensor_id, "zone_id": zone_id, "kind": "light"}
    response = client.post(
        f"{settings.API_V1_STR}/sensor-zone-maps/",
        headers=normal_user_token_headers,
        json=map_data,
    )
    assert response.status_code == 403


def test_sensor_zone_map_unauthorized(client: TestClient) -> None:
    """Test that sensor zone map endpoints require authentication."""
    data = {
        "sensor_id": str(uuid.uuid4()),
        "zone_id": str(uuid.uuid4()),
        "kind": "temperature",
    }
    response = client.post(f"{settings.API_V1_STR}/sensor-zone-maps/", json=data)
    assert response.status_code == 401

    response = client.delete(
        f"{settings.API_V1_STR}/sensor-zone-maps/",
        params={
            "sensor_id": str(uuid.uuid4()),
            "zone_id": str(uuid.uuid4()),
            "kind": "temperature",
        },
    )
    assert response.status_code == 401
