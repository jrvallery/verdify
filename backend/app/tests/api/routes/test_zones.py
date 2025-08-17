"""
Tests for zone CRUD endpoints.
"""
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings


def test_create_zone(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test creating a zone."""
    # First create a greenhouse
    greenhouse_data = {
        "title": "Test Greenhouse for Zone",
        "description": "Test description",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    assert greenhouse_response.status_code == 201
    greenhouse_id = greenhouse_response.json()["id"]

    # Then create a zone
    data = {
        "greenhouse_id": greenhouse_id,
        "zone_number": 1,
        "location": "N",
        "context_text": "North zone for testing",
    }
    response = client.post(
        f"{settings.API_V1_STR}/zones/",
        headers=superuser_token_headers,
        json=data,
    )
    assert response.status_code == 201
    content = response.json()
    assert content["zone_number"] == data["zone_number"]
    assert content["location"] == data["location"]
    assert content["context_text"] == data["context_text"]
    assert content["greenhouse_id"] == greenhouse_id
    assert "id" in content


def test_list_zones(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test listing zones."""
    # First create a greenhouse and zone
    greenhouse_data = {
        "title": "Test Greenhouse for Zone List",
        "description": "Test description",
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
        "context_text": "Test Zone for List",
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/zones/",
        headers=superuser_token_headers,
        json=zone_data,
    )
    assert create_response.status_code == 201

    # Then list zones
    response = client.get(
        f"{settings.API_V1_STR}/zones/",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert "data" in content
    assert "page" in content
    assert "page_size" in content
    assert "total" in content
    assert isinstance(content["data"], list)
    assert len(content["data"]) > 0


def test_list_zones_with_greenhouse_filter(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test listing zones filtered by greenhouse."""
    # Create a greenhouse
    greenhouse_data = {
        "title": "Test Greenhouse for Zone Filter",
        "description": "Test description",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    greenhouse_id = greenhouse_response.json()["id"]

    # Create a zone in that greenhouse
    zone_data = {
        "greenhouse_id": greenhouse_id,
        "zone_number": 1,
        "location": "N",
        "context_text": "Test Zone for Filter",
    }
    client.post(
        f"{settings.API_V1_STR}/zones/",
        headers=superuser_token_headers,
        json=zone_data,
    )

    # List zones filtered by greenhouse
    response = client.get(
        f"{settings.API_V1_STR}/zones/?greenhouse_id={greenhouse_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert "data" in content
    assert "page" in content
    assert "page_size" in content
    assert "total" in content
    assert isinstance(content["data"], list)
    # All zones should belong to the specified greenhouse
    for zone in content["data"]:
        assert zone["greenhouse_id"] == greenhouse_id


def test_get_zone(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test getting a specific zone."""
    # Create greenhouse and zone
    greenhouse_data = {
        "title": "Test Greenhouse for Zone Get",
        "description": "Test description for zone get test",
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
        "context_text": "Test Zone for Get",
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/zones/",
        headers=superuser_token_headers,
        json=zone_data,
    )
    zone_id = create_response.json()["id"]

    # Get the zone
    response = client.get(
        f"{settings.API_V1_STR}/zones/{zone_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == zone_id
    assert content["context_text"] == zone_data["context_text"]


def test_update_zone(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test updating a zone."""
    # Create greenhouse and zone
    greenhouse_data = {
        "title": "Test Greenhouse for Zone Update",
        "description": "Test description for zone update test",
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
        "context_text": "Test Zone for Update",
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/zones/",
        headers=superuser_token_headers,
        json=zone_data,
    )
    zone_id = create_response.json()["id"]

    # Update the zone
    update_data = {"context_text": "Updated Zone Name", "location": "S"}
    response = client.patch(
        f"{settings.API_V1_STR}/zones/{zone_id}",
        headers=superuser_token_headers,
        json=update_data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["context_text"] == update_data["context_text"]
    assert content["location"] == update_data["location"]


def test_delete_zone(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test deleting a zone."""
    # Create greenhouse and zone
    greenhouse_data = {
        "title": "Test Greenhouse for Zone Delete",
        "description": "Test description for zone delete test",
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
        "context_text": "Test Zone for Delete",
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/zones/",
        headers=superuser_token_headers,
        json=zone_data,
    )
    zone_id = create_response.json()["id"]

    # Delete the zone
    response = client.delete(
        f"{settings.API_V1_STR}/zones/{zone_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 204

    # Verify it's deleted
    get_response = client.get(
        f"{settings.API_V1_STR}/zones/{zone_id}",
        headers=superuser_token_headers,
    )
    assert get_response.status_code == 404


def test_zone_unauthorized(client: TestClient) -> None:
    """Test that zone endpoints require authentication."""
    greenhouse_id = str(uuid.uuid4())
    response = client.get(f"{settings.API_V1_STR}/zones/")
    assert response.status_code == 401

    data = {
        "greenhouse_id": greenhouse_id,
        "zone_number": 1,
        "location": "N",
        "context_text": "Test",
    }
    response = client.post(f"{settings.API_V1_STR}/zones/", json=data)
    assert response.status_code == 401
