"""
Tests for greenhouse CRUD endpoints.
"""
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings


def test_create_greenhouse(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """Test creating a greenhouse."""
    data = {"title": "Test Greenhouse", "description": "Test Description"}
    response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=data,
    )
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.json()}")
    assert response.status_code == 201
    content = response.json()
    assert content["title"] == data["title"]
    assert content["description"] == data["description"]
    assert "id" in content


def test_list_greenhouses(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test listing greenhouses."""
    # First create a greenhouse
    data = {
        "title": "Test Greenhouse for List",
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=data,
    )
    assert create_response.status_code == 201

    # Then list greenhouses
    response = client.get(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert "data" in content
    assert "page" in content
    assert "page_size" in content
    assert "total" in content
    assert len(content["data"]) >= 1


def test_get_greenhouse(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test getting a specific greenhouse."""
    # First create a greenhouse
    data = {
        "title": "Test Greenhouse for Get",
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=data,
    )
    assert create_response.status_code == 201
    greenhouse_id = create_response.json()["id"]

    # Then get the greenhouse
    response = client.get(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["id"] == greenhouse_id
    assert content["title"] == data["title"]


def test_update_greenhouse(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test updating a greenhouse."""
    # First create a greenhouse
    data = {
        "title": "Test Greenhouse for Update",
    }
    create_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=data,
    )
    assert create_response.status_code == 201
    greenhouse_id = create_response.json()["id"]

    # Then update the greenhouse
    update_data = {
        "title": "Updated Greenhouse Name",
        "description": "Updated Description",
    }
    response = client.patch(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}",
        headers=superuser_token_headers,
        json=update_data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["title"] == update_data["title"]
    assert content["description"] == update_data["description"]


def test_delete_greenhouse(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test deleting a greenhouse."""
    # First create a greenhouse
    data = {"title": "Test Greenhouse for Delete", "description": "Test description"}
    create_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=data,
    )
    assert create_response.status_code == 201
    greenhouse_id = create_response.json()["id"]

    # Then delete the greenhouse
    response = client.delete(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 204

    # Verify it's deleted
    get_response = client.get(
        f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}",
        headers=superuser_token_headers,
    )
    assert get_response.status_code == 404


def test_greenhouse_unauthorized(client: TestClient) -> None:
    """Test that greenhouse endpoints require authentication."""
    # Test listing greenhouses without auth
    response = client.get(f"{settings.API_V1_STR}/greenhouses/")
    assert response.status_code == 401

    # Test creating greenhouse without auth
    data = {
        "name": "Test",
        "location": "Test",
    }
    response = client.post(f"{settings.API_V1_STR}/greenhouses/", json=data)
    assert response.status_code == 401


def test_greenhouse_pagination(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Test greenhouse pagination parameters."""
    response = client.get(
        f"{settings.API_V1_STR}/greenhouses/?page=1&page_size=10",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["page"] == 1
    assert content["page_size"] == 10
