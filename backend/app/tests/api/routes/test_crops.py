"""
Tests for crops CRUD endpoints.

Covers all standalone crop management endpoints (/crops) with comprehensive
edge cases, validation scenarios, and error handling.
"""

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings


class TestCropsCreate:
    """Test crop creation endpoint POST /crops"""

    def test_create_crop_success(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test successful crop creation."""
        crop_data = {
            "name": "Test Tomato",
            "scientific_name": "Solanum lycopersicum",
            "variety": "Cherry Red",
            "description": "Small cherry tomatoes perfect for snacking",
            "optimal_temp_min": 18.0,
            "optimal_temp_max": 26.0,
            "optimal_humidity_min": 60.0,
            "optimal_humidity_max": 80.0,
            "growth_duration_days": 75,
        }

        response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )

        assert response.status_code == 201
        data = response.json()

        # Verify all fields are returned correctly
        assert data["name"] == crop_data["name"]
        assert data["scientific_name"] == crop_data["scientific_name"]
        assert data["variety"] == crop_data["variety"]
        assert data["description"] == crop_data["description"]
        assert data["optimal_temp_min"] == crop_data["optimal_temp_min"]
        assert data["optimal_temp_max"] == crop_data["optimal_temp_max"]
        assert data["optimal_humidity_min"] == crop_data["optimal_humidity_min"]
        assert data["optimal_humidity_max"] == crop_data["optimal_humidity_max"]
        assert data["growth_duration_days"] == crop_data["growth_duration_days"]

        # Verify auto-generated fields
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_crop_minimal_data(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop creation with only required fields."""
        crop_data = {"name": "Minimal Crop"}

        response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == crop_data["name"]

        # Optional fields should be null or have defaults
        assert data.get("scientific_name") is None
        assert data.get("variety") is None
        assert data.get("description") is None

    def test_create_crop_duplicate_name(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test creating crop with duplicate name."""
        crop_name = f"Duplicate Crop {uuid.uuid4().hex[:8]}"
        crop_data = {"name": crop_name}

        # First creation should succeed
        response1 = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )
        assert response1.status_code == 201

        # Second creation with same name should either succeed or fail based on business rules
        response2 = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )
        # Could be 201 (allowed duplicates) or 409 (conflict) - depends on implementation
        assert response2.status_code in [201, 409]

    def test_create_crop_invalid_temperature_range(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop creation with invalid temperature range (min > max)."""
        crop_data = {
            "name": "Invalid Temp Crop",
            "optimal_temp_min": 30.0,
            "optimal_temp_max": 20.0,  # Max less than min
        }

        response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )

        assert response.status_code == 422

    def test_create_crop_invalid_humidity_range(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop creation with invalid humidity range."""
        crop_data = {
            "name": "Invalid Humidity Crop",
            "optimal_humidity_min": 90.0,
            "optimal_humidity_max": 70.0,  # Max less than min
        }

        response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )

        assert response.status_code == 422

    def test_create_crop_extreme_values(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop creation with extreme but valid values."""
        crop_data = {
            "name": "Extreme Crop",
            "optimal_temp_min": -10.0,
            "optimal_temp_max": 50.0,
            "optimal_humidity_min": 0.0,
            "optimal_humidity_max": 100.0,
            "growth_duration_days": 365,
        }

        response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )

        assert response.status_code == 201

    def test_create_crop_negative_growth_duration(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop creation with negative growth duration."""
        crop_data = {"name": "Negative Growth Crop", "growth_duration_days": -5}

        response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )

        assert response.status_code == 422

    def test_create_crop_unauthorized(self, client: TestClient):
        """Test crop creation without authentication."""
        crop_data = {"name": "Unauthorized Crop"}

        response = client.post(f"{settings.API_V1_STR}/crops/", json=crop_data)

        assert response.status_code == 401

    def test_create_crop_empty_name(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop creation with empty name."""
        crop_data = {"name": ""}

        response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )

        assert response.status_code == 422

    def test_create_crop_very_long_name(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop creation with very long name."""
        crop_data = {"name": "a" * 1000}  # Very long name

        response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )

        assert response.status_code == 422

    def test_create_crop_unicode_characters(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop creation with Unicode characters."""
        crop_data = {
            "name": "トマト (Japanese Tomato) 🍅",
            "scientific_name": "Solanum lycopersicum",
            "variety": "Variété française",
            "description": "描述包含中文字符",
        }

        response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == crop_data["name"]
        assert data["scientific_name"] == crop_data["scientific_name"]


class TestCropsList:
    """Test crop listing endpoint GET /crops"""

    def test_list_crops_success(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test successful crop listing."""
        # Create a test crop first
        crop_data = {"name": f"List Test Crop {uuid.uuid4().hex[:8]}"}
        client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )

        response = client.get(
            f"{settings.API_V1_STR}/crops/", headers=superuser_token_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Check pagination structure
        assert "data" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data

        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

    def test_list_crops_pagination(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop listing with pagination."""
        # Create multiple crops for pagination testing
        for i in range(5):
            crop_data = {"name": f"Pagination Crop {i} {uuid.uuid4().hex[:8]}"}
            client.post(
                f"{settings.API_V1_STR}/crops/",
                headers=superuser_token_headers,
                json=crop_data,
            )

        # Test first page
        response = client.get(
            f"{settings.API_V1_STR}/crops/?page=1&page_size=3",
            headers=superuser_token_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 3
        assert len(data["data"]) <= 3

    def test_list_crops_unauthorized(self, client: TestClient):
        """Test crop listing without authentication."""
        response = client.get(f"{settings.API_V1_STR}/crops/")

        assert response.status_code == 401

    def test_list_crops_invalid_pagination(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop listing with invalid pagination parameters."""
        test_cases = [
            {"page": 0, "page_size": 10},  # Page starts from 1
            {"page": 1, "page_size": 0},  # Page size must be positive
            {"page": -1, "page_size": 10},  # Negative page
            {"page": 1, "page_size": -5},  # Negative page size
        ]

        for params in test_cases:
            response = client.get(
                f"{settings.API_V1_STR}/crops/",
                headers=superuser_token_headers,
                params=params,
            )

            assert response.status_code == 422

    def test_list_crops_empty_database(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test crop listing when no crops exist."""
        # Clear any existing crops for this test
        from app.crud.crop import crop as crop_crud

        crops = crop_crud.get_multi(db=db)
        for crop in crops:
            crop_crud.remove(db=db, id=crop.id)

        response = client.get(
            f"{settings.API_V1_STR}/crops/", headers=superuser_token_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["data"] == []
        assert data["total"] == 0


class TestCropsGet:
    """Test crop retrieval endpoint GET /crops/{id}"""

    def test_get_crop_success(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test successful crop retrieval by ID."""
        # Create a crop first
        crop_data = {
            "name": f"Get Test Crop {uuid.uuid4().hex[:8]}",
            "scientific_name": "Test species",
            "description": "Test description",
        }
        create_response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )
        assert create_response.status_code == 201
        crop_id = create_response.json()["id"]

        # Get the crop
        response = client.get(
            f"{settings.API_V1_STR}/crops/{crop_id}", headers=superuser_token_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == crop_id
        assert data["name"] == crop_data["name"]
        assert data["scientific_name"] == crop_data["scientific_name"]

    def test_get_crop_not_found(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop retrieval with non-existent ID."""
        fake_id = str(uuid.uuid4())

        response = client.get(
            f"{settings.API_V1_STR}/crops/{fake_id}", headers=superuser_token_headers
        )

        assert response.status_code == 404

    def test_get_crop_invalid_uuid(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop retrieval with invalid UUID format."""
        invalid_ids = ["not-a-uuid", "123", "abc-def-ghi", ""]

        for invalid_id in invalid_ids:
            response = client.get(
                f"{settings.API_V1_STR}/crops/{invalid_id}",
                headers=superuser_token_headers,
            )

            assert response.status_code == 422

    def test_get_crop_unauthorized(self, client: TestClient):
        """Test crop retrieval without authentication."""
        fake_id = str(uuid.uuid4())

        response = client.get(f"{settings.API_V1_STR}/crops/{fake_id}")

        assert response.status_code == 401


class TestCropsUpdate:
    """Test crop update endpoint PATCH /crops/{id}"""

    def test_update_crop_success(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test successful crop update."""
        # Create a crop first
        crop_data = {"name": f"Update Test Crop {uuid.uuid4().hex[:8]}"}
        create_response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )
        assert create_response.status_code == 201
        crop_id = create_response.json()["id"]

        # Update the crop
        update_data = {
            "name": "Updated Crop Name",
            "scientific_name": "Updated species",
            "optimal_temp_min": 20.0,
            "optimal_temp_max": 25.0,
        }

        response = client.patch(
            f"{settings.API_V1_STR}/crops/{crop_id}",
            headers=superuser_token_headers,
            json=update_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        assert data["scientific_name"] == update_data["scientific_name"]
        assert data["optimal_temp_min"] == update_data["optimal_temp_min"]

    def test_update_crop_partial(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test partial crop update (only some fields)."""
        # Create a crop first
        crop_data = {
            "name": f"Partial Update Crop {uuid.uuid4().hex[:8]}",
            "scientific_name": "Original species",
        }
        create_response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )
        assert create_response.status_code == 201
        crop_id = create_response.json()["id"]

        # Update only the name
        update_data = {"name": "Partially Updated Name"}

        response = client.patch(
            f"{settings.API_V1_STR}/crops/{crop_id}",
            headers=superuser_token_headers,
            json=update_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == update_data["name"]
        assert (
            data["scientific_name"] == crop_data["scientific_name"]
        )  # Should remain unchanged

    def test_update_crop_not_found(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop update with non-existent ID."""
        fake_id = str(uuid.uuid4())
        update_data = {"name": "Non-existent Crop"}

        response = client.patch(
            f"{settings.API_V1_STR}/crops/{fake_id}",
            headers=superuser_token_headers,
            json=update_data,
        )

        assert response.status_code == 404

    def test_update_crop_invalid_data(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop update with invalid data."""
        # Create a crop first
        crop_data = {"name": f"Invalid Update Crop {uuid.uuid4().hex[:8]}"}
        create_response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )
        assert create_response.status_code == 201
        crop_id = create_response.json()["id"]

        # Try to update with invalid temperature range
        update_data = {
            "optimal_temp_min": 30.0,
            "optimal_temp_max": 20.0,  # Max less than min
        }

        response = client.patch(
            f"{settings.API_V1_STR}/crops/{crop_id}",
            headers=superuser_token_headers,
            json=update_data,
        )

        assert response.status_code == 422

    def test_update_crop_unauthorized(self, client: TestClient):
        """Test crop update without authentication."""
        fake_id = str(uuid.uuid4())
        update_data = {"name": "Unauthorized Update"}

        response = client.patch(
            f"{settings.API_V1_STR}/crops/{fake_id}", json=update_data
        )

        assert response.status_code == 401

    def test_update_crop_empty_data(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop update with empty data."""
        # Create a crop first
        crop_data = {"name": f"Empty Update Crop {uuid.uuid4().hex[:8]}"}
        create_response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )
        assert create_response.status_code == 201
        crop_id = create_response.json()["id"]

        # Update with empty data
        response = client.patch(
            f"{settings.API_V1_STR}/crops/{crop_id}",
            headers=superuser_token_headers,
            json={},
        )

        # Should succeed but not change anything
        assert response.status_code == 200


class TestCropsDelete:
    """Test crop deletion endpoint DELETE /crops/{id}"""

    def test_delete_crop_success(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test successful crop deletion."""
        # Create a crop first
        crop_data = {"name": f"Delete Test Crop {uuid.uuid4().hex[:8]}"}
        create_response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )
        assert create_response.status_code == 201
        crop_id = create_response.json()["id"]

        # Delete the crop
        response = client.delete(
            f"{settings.API_V1_STR}/crops/{crop_id}", headers=superuser_token_headers
        )

        assert response.status_code == 204

        # Verify crop is deleted
        get_response = client.get(
            f"{settings.API_V1_STR}/crops/{crop_id}", headers=superuser_token_headers
        )
        assert get_response.status_code == 404

    def test_delete_crop_not_found(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop deletion with non-existent ID."""
        fake_id = str(uuid.uuid4())

        response = client.delete(
            f"{settings.API_V1_STR}/crops/{fake_id}", headers=superuser_token_headers
        )

        assert response.status_code == 404

    def test_delete_crop_invalid_uuid(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop deletion with invalid UUID format."""
        invalid_ids = ["not-a-uuid", "123", "abc-def-ghi"]

        for invalid_id in invalid_ids:
            response = client.delete(
                f"{settings.API_V1_STR}/crops/{invalid_id}",
                headers=superuser_token_headers,
            )

            assert response.status_code == 422

    def test_delete_crop_unauthorized(self, client: TestClient):
        """Test crop deletion without authentication."""
        fake_id = str(uuid.uuid4())

        response = client.delete(f"{settings.API_V1_STR}/crops/{fake_id}")

        assert response.status_code == 401

    def test_delete_crop_twice(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test deleting the same crop twice."""
        # Create a crop first
        crop_data = {"name": f"Double Delete Crop {uuid.uuid4().hex[:8]}"}
        create_response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )
        assert create_response.status_code == 201
        crop_id = create_response.json()["id"]

        # First deletion should succeed
        response1 = client.delete(
            f"{settings.API_V1_STR}/crops/{crop_id}", headers=superuser_token_headers
        )
        assert response1.status_code == 204

        # Second deletion should return 404
        response2 = client.delete(
            f"{settings.API_V1_STR}/crops/{crop_id}", headers=superuser_token_headers
        )
        assert response2.status_code == 404


class TestCropsEdgeCases:
    """Test edge cases and complex scenarios for crops"""

    def test_concurrent_crop_operations(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test concurrent operations on the same crop."""
        # Create a crop first
        crop_data = {"name": f"Concurrent Test Crop {uuid.uuid4().hex[:8]}"}
        create_response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )
        assert create_response.status_code == 201
        crop_id = create_response.json()["id"]

        # Simulate concurrent updates
        import threading

        results = []

        def update_crop(name_suffix: str):
            update_data = {"name": f"Updated Crop {name_suffix}"}
            response = client.patch(
                f"{settings.API_V1_STR}/crops/{crop_id}",
                headers=superuser_token_headers,
                json=update_data,
            )
            results.append(response.status_code)

        threads = [
            threading.Thread(target=update_crop, args=[f"Thread{i}"]) for i in range(3)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All updates should succeed (optimistic locking might cause some to fail)
        assert all(status in [200, 409] for status in results)

    def test_crop_with_special_characters(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop operations with special characters and edge cases."""
        special_crops = [
            {"name": 'Crop with "quotes"'},
            {"name": "Crop with 'apostrophes'"},
            {"name": "Crop with <tags>"},
            {"name": "Crop with & ampersand"},
            {"name": "Crop with newline\ncharacter"},
            {"name": "Crop with tab\tcharacter"},
            {"name": "   Crop with leading/trailing spaces   "},
        ]

        for crop_data in special_crops:
            # Create
            response = client.post(
                f"{settings.API_V1_STR}/crops/",
                headers=superuser_token_headers,
                json=crop_data,
            )
            assert response.status_code == 201

            crop_id = response.json()["id"]

            # Get
            get_response = client.get(
                f"{settings.API_V1_STR}/crops/{crop_id}",
                headers=superuser_token_headers,
            )
            assert get_response.status_code == 200
            assert get_response.json()["name"] == crop_data["name"]

            # Update
            update_data = {"description": "Updated description with special chars"}
            update_response = client.patch(
                f"{settings.API_V1_STR}/crops/{crop_id}",
                headers=superuser_token_headers,
                json=update_data,
            )
            assert update_response.status_code == 200

            # Delete
            delete_response = client.delete(
                f"{settings.API_V1_STR}/crops/{crop_id}",
                headers=superuser_token_headers,
            )
            assert delete_response.status_code == 204

    def test_crop_field_boundary_values(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crops with boundary values for numeric fields."""
        boundary_test_cases = [
            {
                "name": "Zero Temperature Crop",
                "optimal_temp_min": 0.0,
                "optimal_temp_max": 0.0,
            },
            {
                "name": "Extreme Cold Crop",
                "optimal_temp_min": -273.15,  # Absolute zero
                "optimal_temp_max": -200.0,
            },
            {
                "name": "Extreme Hot Crop",
                "optimal_temp_min": 100.0,
                "optimal_temp_max": 200.0,
            },
            {
                "name": "Humidity Boundary Crop",
                "optimal_humidity_min": 0.0,
                "optimal_humidity_max": 100.0,
            },
            {"name": "Long Growth Crop", "growth_duration_days": 1000},
            {"name": "Short Growth Crop", "growth_duration_days": 1},
        ]

        for crop_data in boundary_test_cases:
            response = client.post(
                f"{settings.API_V1_STR}/crops/",
                headers=superuser_token_headers,
                json=crop_data,
            )

            # Should either succeed or fail validation consistently
            assert response.status_code in [201, 422]

            if response.status_code == 201:
                # If created, verify values are stored correctly
                data = response.json()
                for key, value in crop_data.items():
                    assert data[key] == value

    def test_crop_cascade_operations(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop operations and their effect on related entities."""
        # Create a crop
        crop_data = {"name": f"Cascade Test Crop {uuid.uuid4().hex[:8]}"}
        create_response = client.post(
            f"{settings.API_V1_STR}/crops/",
            headers=superuser_token_headers,
            json=crop_data,
        )
        assert create_response.status_code == 201
        crop_id = create_response.json()["id"]

        # TODO: When zone-crops are implemented, test cascade behavior
        # For now, just test that crop can be deleted cleanly

        delete_response = client.delete(
            f"{settings.API_V1_STR}/crops/{crop_id}", headers=superuser_token_headers
        )
        assert delete_response.status_code == 204

    def test_crop_search_and_filtering(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test crop search and filtering capabilities (if implemented)."""
        # Create multiple crops with different characteristics
        test_crops = [
            {"name": "Tomato Crop", "scientific_name": "Solanum lycopersicum"},
            {"name": "Lettuce Crop", "scientific_name": "Lactuca sativa"},
            {"name": "Basil Crop", "scientific_name": "Ocimum basilicum"},
        ]

        created_crops = []
        for crop_data in test_crops:
            response = client.post(
                f"{settings.API_V1_STR}/crops/",
                headers=superuser_token_headers,
                json=crop_data,
            )
            assert response.status_code == 201
            created_crops.append(response.json())

        # Test basic listing (should include our crops)
        list_response = client.get(
            f"{settings.API_V1_STR}/crops/", headers=superuser_token_headers
        )
        assert list_response.status_code == 200
        data = list_response.json()
        assert len(data["data"]) >= len(test_crops)

        # Test filtering by name (if supported)
        search_response = client.get(
            f"{settings.API_V1_STR}/crops/?search=Tomato",
            headers=superuser_token_headers,
        )
        # Should either work or return 422 if search not implemented
        assert search_response.status_code in [200, 422]

        # Clean up
        for crop in created_crops:
            client.delete(
                f"{settings.API_V1_STR}/crops/{crop['id']}",
                headers=superuser_token_headers,
            )
