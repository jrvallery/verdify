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


# ===============================================
# EDGE CASES AND COMPREHENSIVE ERROR TESTING
# ===============================================


class TestGreenhousesEdgeCases:
    """Test edge cases and comprehensive error scenarios for greenhouses"""

    def test_create_greenhouse_invalid_data_types(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse creation with invalid data types."""
        invalid_data_cases = [
            {"title": 123},  # Title should be string
            {"title": None},  # Title should not be null
            {"title": []},  # Title should not be array
            {"title": {"name": "test"}},  # Title should not be object
            {"description": 123},  # Description should be string if provided
        ]

        for invalid_data in invalid_data_cases:
            response = client.post(
                f"{settings.API_V1_STR}/greenhouses/",
                headers=superuser_token_headers,
                json=invalid_data,
            )
            assert response.status_code == 422

    def test_create_greenhouse_extremely_long_fields(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse creation with extremely long field values."""
        data = {
            "title": "A" * 1000,  # Very long title
            "description": "B" * 10000,  # Very long description
        }
        response = client.post(
            f"{settings.API_V1_STR}/greenhouses/",
            headers=superuser_token_headers,
            json=data,
        )
        # Should either succeed or fail with 422 (validation error)
        assert response.status_code in [201, 422]

    def test_create_greenhouse_unicode_characters(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse creation with Unicode characters."""
        unicode_data = {
            "title": "温室 🌱 (Greenhouse in Chinese)",
            "description": "Español, Français, Deutsch, 中文, العربية, русский",
        }
        response = client.post(
            f"{settings.API_V1_STR}/greenhouses/",
            headers=superuser_token_headers,
            json=unicode_data,
        )
        assert response.status_code == 201
        content = response.json()
        assert content["title"] == unicode_data["title"]
        assert content["description"] == unicode_data["description"]

    def test_create_greenhouse_special_characters(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse creation with special characters."""
        special_chars_data = {
            "title": "Greenhouse with \"quotes\" and 'apostrophes'",
            "description": "Special chars: <>&\"'\\n\\t\\r",
        }
        response = client.post(
            f"{settings.API_V1_STR}/greenhouses/",
            headers=superuser_token_headers,
            json=special_chars_data,
        )
        assert response.status_code == 201
        content = response.json()
        assert content["title"] == special_chars_data["title"]

    def test_get_greenhouse_invalid_uuid_formats(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse GET with various invalid UUID formats."""
        invalid_uuids = [
            "not-a-uuid",
            "123",
            "abc-def-ghi",
            "",
            "00000000-0000-0000-0000-00000000000G",  # Invalid character
            "00000000-0000-0000-0000-000000000000-extra",  # Too long
        ]

        for invalid_uuid in invalid_uuids:
            response = client.get(
                f"{settings.API_V1_STR}/greenhouses/{invalid_uuid}",
                headers=superuser_token_headers,
            )
            assert response.status_code == 422

    def test_update_greenhouse_partial_fields(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse update with only some fields."""
        # Create greenhouse
        data = {"title": "Original Title", "description": "Original Description"}
        create_response = client.post(
            f"{settings.API_V1_STR}/greenhouses/",
            headers=superuser_token_headers,
            json=data,
        )
        assert create_response.status_code == 201
        greenhouse_id = create_response.json()["id"]

        # Update only title
        update_data = {"title": "Updated Title Only"}
        response = client.patch(
            f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}",
            headers=superuser_token_headers,
            json=update_data,
        )
        assert response.status_code == 200
        content = response.json()
        assert content["title"] == "Updated Title Only"
        assert (
            content["description"] == "Original Description"
        )  # Should remain unchanged

    def test_update_greenhouse_empty_data(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse update with empty data."""
        # Create greenhouse
        data = {"title": "Test Greenhouse"}
        create_response = client.post(
            f"{settings.API_V1_STR}/greenhouses/",
            headers=superuser_token_headers,
            json=data,
        )
        assert create_response.status_code == 201
        greenhouse_id = create_response.json()["id"]

        # Update with empty data
        response = client.patch(
            f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}",
            headers=superuser_token_headers,
            json={},
        )
        # Should succeed but not change anything
        assert response.status_code == 200

    def test_delete_greenhouse_cascade_effects(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse deletion and its cascade effects on related entities."""
        # Create greenhouse with zones
        greenhouse_data = {"title": "Cascade Test Greenhouse"}
        greenhouse_response = client.post(
            f"{settings.API_V1_STR}/greenhouses/",
            headers=superuser_token_headers,
            json=greenhouse_data,
        )
        assert greenhouse_response.status_code == 201
        greenhouse_id = greenhouse_response.json()["id"]

        # Create zone in the greenhouse
        zone_data = {"name": "Test Zone", "greenhouse_id": greenhouse_id}
        zone_response = client.post(
            f"{settings.API_V1_STR}/zones/",
            headers=superuser_token_headers,
            json=zone_data,
        )
        assert zone_response.status_code == 201
        zone_id = zone_response.json()["id"]

        # Delete greenhouse
        delete_response = client.delete(
            f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}",
            headers=superuser_token_headers,
        )
        assert delete_response.status_code == 204

        # Verify zones are also deleted (cascade behavior)
        zone_get_response = client.get(
            f"{settings.API_V1_STR}/zones/{zone_id}",
            headers=superuser_token_headers,
        )
        assert zone_get_response.status_code == 404

    def test_list_greenhouses_invalid_pagination(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse listing with invalid pagination parameters."""
        invalid_pagination_cases = [
            {"page": 0, "page_size": 10},  # Page starts from 1
            {"page": -1, "page_size": 10},  # Negative page
            {"page": 1, "page_size": 0},  # Page size must be positive
            {"page": 1, "page_size": -5},  # Negative page size
            {"page": "invalid", "page_size": 10},  # Non-numeric page
            {"page": 1, "page_size": "invalid"},  # Non-numeric page_size
        ]

        for invalid_params in invalid_pagination_cases:
            response = client.get(
                f"{settings.API_V1_STR}/greenhouses/",
                headers=superuser_token_headers,
                params=invalid_params,
            )
            assert response.status_code == 422

    def test_greenhouse_operations_with_malformed_json(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse operations with malformed JSON."""
        malformed_json = '{"title": "Test", "description": "incomplete'  # Missing closing quote and brace

        response = client.post(
            f"{settings.API_V1_STR}/greenhouses/",
            content=malformed_json,
            headers={**superuser_token_headers, "Content-Type": "application/json"},
        )
        assert response.status_code == 422

    def test_greenhouse_sql_injection_attempts(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse endpoints against SQL injection attempts."""
        sql_injection_payloads = [
            "'; DROP TABLE greenhouses; --",
            "' OR '1'='1",
            "'; UPDATE greenhouses SET title='hacked'; --",
            "' UNION SELECT * FROM users; --",
        ]

        for payload in sql_injection_payloads:
            # Test in title field
            data = {"title": payload, "description": "Test description"}
            response = client.post(
                f"{settings.API_V1_STR}/greenhouses/",
                headers=superuser_token_headers,
                json=data,
            )

            # Should either succeed (treating as literal string) or fail validation
            assert response.status_code in [201, 422]

            if response.status_code == 201:
                # If successful, verify the payload is stored as literal string
                content = response.json()
                assert content["title"] == payload

    def test_greenhouse_xss_prevention(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse endpoints against XSS attempts."""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "'; alert('xss'); //",
            "<svg onload=alert('xss')>",
        ]

        for payload in xss_payloads:
            data = {
                "title": f"Greenhouse {payload}",
                "description": f"Description {payload}",
            }
            response = client.post(
                f"{settings.API_V1_STR}/greenhouses/",
                headers=superuser_token_headers,
                json=data,
            )

            assert response.status_code == 201
            content = response.json()
            # XSS payload should be stored as-is, not executed
            assert payload in content["title"]
            assert payload in content["description"]

    def test_concurrent_greenhouse_operations(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test concurrent operations on greenhouses."""
        import threading
        import uuid

        # Create a greenhouse for concurrent operations
        data = {"title": f"Concurrent Test {uuid.uuid4().hex[:8]}"}
        create_response = client.post(
            f"{settings.API_V1_STR}/greenhouses/",
            headers=superuser_token_headers,
            json=data,
        )
        assert create_response.status_code == 201
        greenhouse_id = create_response.json()["id"]

        results = []

        def update_greenhouse(suffix: str):
            update_data = {"title": f"Updated Title {suffix}"}
            response = client.patch(
                f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}",
                headers=superuser_token_headers,
                json=update_data,
            )
            results.append(response.status_code)

        # Start multiple concurrent updates
        threads = [
            threading.Thread(target=update_greenhouse, args=[f"Thread{i}"])
            for i in range(3)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All updates should succeed (unless there's optimistic locking)
        assert all(status in [200, 409] for status in results)

    def test_greenhouse_response_headers(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse endpoints return proper response headers."""
        # Test CREATE response headers
        data = {"title": "Header Test Greenhouse"}
        response = client.post(
            f"{settings.API_V1_STR}/greenhouses/",
            headers=superuser_token_headers,
            json=data,
        )
        assert response.status_code == 201
        assert "application/json" in response.headers.get("content-type", "")

        greenhouse_id = response.json()["id"]

        # Test GET response headers
        get_response = client.get(
            f"{settings.API_V1_STR}/greenhouses/{greenhouse_id}",
            headers=superuser_token_headers,
        )
        assert get_response.status_code == 200
        assert "application/json" in get_response.headers.get("content-type", "")

        # Test LIST response headers
        list_response = client.get(
            f"{settings.API_V1_STR}/greenhouses/",
            headers=superuser_token_headers,
        )
        assert list_response.status_code == 200
        assert "application/json" in list_response.headers.get("content-type", "")

    def test_greenhouse_field_validation_boundaries(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ) -> None:
        """Test greenhouse field validation at boundary values."""
        # Test minimum valid title length
        min_title_data = {"title": "A"}  # Single character
        response = client.post(
            f"{settings.API_V1_STR}/greenhouses/",
            headers=superuser_token_headers,
            json=min_title_data,
        )
        assert response.status_code == 201

        # Test empty title (should fail)
        empty_title_data = {"title": ""}
        response = client.post(
            f"{settings.API_V1_STR}/greenhouses/",
            headers=superuser_token_headers,
            json=empty_title_data,
        )
        assert response.status_code == 422

        # Test whitespace-only title (should fail)
        whitespace_title_data = {"title": "   "}
        response = client.post(
            f"{settings.API_V1_STR}/greenhouses/",
            headers=superuser_token_headers,
            json=whitespace_title_data,
        )
        assert response.status_code == 422
