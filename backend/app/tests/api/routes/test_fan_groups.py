"""
Tests for fan group CRUD endpoints.
"""
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings


def test_create_fan_group(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test creating a fan group."""
    # Create greenhouse
    greenhouse_data = {
        "title": "Test Greenhouse for Fan Group",
        "description": "Test description for fan group testing",
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
        "device_name": "verdify-fangroup1",
        "label": "Test Controller for Fan Group",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    # Create fan group
    fan_group_data = {"controller_id": controller_id, "name": "Test Fan Group"}
    response = client.post(
        f"{settings.API_V1_STR}/fan-groups/",
        headers=superuser_token_headers,
        json=fan_group_data,
    )
    assert response.status_code == 201
    content = response.json()
    assert content["name"] == "Test Fan Group"
    assert content["controller_id"] == controller_id
    assert "id" in content


def test_list_fan_groups(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test listing fan groups."""
    response = client.get(
        f"{settings.API_V1_STR}/fan-groups/",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert "data" in content
    assert "page" in content
    assert "page_size" in content
    assert "total" in content


def test_add_fan_group_member(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test adding an actuator to a fan group."""
    # Create greenhouse
    greenhouse_data = {
        "title": "Test Greenhouse for Fan Group Member",
        "description": "Test description for fan group member testing",
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
        "device_name": "verdify-fgmember1",
        "label": "Test Controller for Fan Group Member",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    # Create fan group
    fan_group_data = {
        "controller_id": controller_id,
        "name": "Test Fan Group for Members",
    }
    fan_group_response = client.post(
        f"{settings.API_V1_STR}/fan-groups/",
        headers=superuser_token_headers,
        json=fan_group_data,
    )
    fan_group_id = fan_group_response.json()["id"]

    # Create actuator
    actuator_data = {
        "controller_id": controller_id,
        "name": "Test Fan for Group",
        "kind": "fan",
        "relay_channel": 1,
    }
    actuator_response = client.post(
        f"{settings.API_V1_STR}/actuators/",
        headers=superuser_token_headers,
        json=actuator_data,
    )
    actuator_id = actuator_response.json()["id"]

    # Add actuator to fan group
    member_data = {"actuator_id": actuator_id}
    response = client.post(
        f"{settings.API_V1_STR}/fan-groups/{fan_group_id}/members",
        headers=superuser_token_headers,
        json=member_data,
    )
    assert response.status_code == 201
    content = response.json()
    assert content["fan_group_id"] == fan_group_id
    assert content["actuator_id"] == actuator_id


def test_remove_fan_group_member(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test removing an actuator from a fan group."""
    # Create greenhouse, controller, fan group, and actuator
    greenhouse_data = {
        "title": "Test Greenhouse for Remove Fan Group Member",
        "description": "Test description for remove fan group member",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-rmfgmem1",
        "label": "Test Controller for Remove Fan Group Member",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    fan_group_data = {
        "controller_id": controller_id,
        "name": "Test Fan Group for Remove",
    }
    fan_group_response = client.post(
        f"{settings.API_V1_STR}/fan-groups/",
        headers=superuser_token_headers,
        json=fan_group_data,
    )
    fan_group_id = fan_group_response.json()["id"]

    actuator_data = {
        "controller_id": controller_id,
        "name": "Test Fan for Remove",
        "kind": "fan",
        "relay_channel": 2,
    }
    actuator_response = client.post(
        f"{settings.API_V1_STR}/actuators/",
        headers=superuser_token_headers,
        json=actuator_data,
    )
    actuator_id = actuator_response.json()["id"]

    # Add actuator to fan group first
    member_data = {"actuator_id": actuator_id}
    client.post(
        f"{settings.API_V1_STR}/fan-groups/{fan_group_id}/members",
        headers=superuser_token_headers,
        json=member_data,
    )

    # Remove actuator from fan group
    response = client.delete(
        f"{settings.API_V1_STR}/fan-groups/{fan_group_id}/members",
        headers=superuser_token_headers,
        params={"actuator_id": actuator_id},
    )
    assert response.status_code == 204


def test_delete_fan_group(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test deleting a fan group."""
    # Create greenhouse, controller, and fan group
    greenhouse_data = {
        "title": "Test Greenhouse for Delete Fan Group",
        "description": "Test description for delete fan group",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-delfg1",
        "label": "Test Controller for Delete Fan Group",
        "model": "ESP32",
        "is_climate_controller": False,
    }
    controller_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    controller_id = controller_response.json()["id"]

    fan_group_data = {
        "controller_id": controller_id,
        "name": "Test Fan Group for Delete",
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/fan-groups/",
        headers=superuser_token_headers,
        json=fan_group_data,
    )
    fan_group_id = create_response.json()["id"]

    # Delete the fan group
    response = client.delete(
        f"{settings.API_V1_STR}/fan-groups/{fan_group_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 204


def test_fan_group_unauthorized(client: TestClient) -> None:
    """Test that fan group endpoints require authentication."""
    response = client.get(f"{settings.API_V1_STR}/fan-groups/")
    assert response.status_code == 401

    data = {"controller_id": str(uuid.uuid4()), "name": "Test Fan Group"}
    response = client.post(f"{settings.API_V1_STR}/fan-groups/", json=data)
    assert response.status_code == 401
