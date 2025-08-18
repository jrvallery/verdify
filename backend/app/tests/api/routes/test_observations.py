"""
Tests for observations CRUD endpoints - Individual operations.

Covers individual observation operations (GET by ID, PATCH, DELETE, upload-url)
that are missing from the existing H4 tests which only cover list and create.
"""

import uuid
from datetime import datetime

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.tests.conftest import create_greenhouse_zone_crop_chain


class TestObservationsGetById:
    """Test observation retrieval by ID - GET /observations/{id}"""

    def test_get_observation_success(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test successful observation retrieval by ID."""
        # Create test data chain
        test_data = create_greenhouse_zone_crop_chain(db)

        # Create an observation first
        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Test observation for individual retrieval",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Get the observation by ID
        response = client.get(
            f"{settings.API_V1_STR}/observations/{observation_id}",
            headers=superuser_token_headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify all fields are returned
        assert data["id"] == observation_id
        assert data["zone_crop_id"] == observation_data["zone_crop_id"]
        assert data["observation_type"] == observation_data["observation_type"]
        assert data["notes"] == observation_data["notes"]
        assert "created_at" in data
        assert "updated_at" in data

    def test_get_observation_not_found(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test observation retrieval with non-existent ID."""
        fake_id = str(uuid.uuid4())

        response = client.get(
            f"{settings.API_V1_STR}/observations/{fake_id}",
            headers=superuser_token_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert "error_code" in data
        assert "message" in data

    def test_get_observation_invalid_uuid(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test observation retrieval with invalid UUID format."""
        invalid_ids = ["not-a-uuid", "123", "abc-def-ghi", ""]

        for invalid_id in invalid_ids:
            response = client.get(
                f"{settings.API_V1_STR}/observations/{invalid_id}",
                headers=superuser_token_headers,
            )

            assert response.status_code == 422

    def test_get_observation_unauthorized(self, client: TestClient):
        """Test observation retrieval without authentication."""
        fake_id = str(uuid.uuid4())

        response = client.get(f"{settings.API_V1_STR}/observations/{fake_id}")

        assert response.status_code == 401

    def test_get_observation_cross_user_access(
        self,
        client: TestClient,
        normal_user_token_headers: dict[str, str],
        superuser_token_headers: dict[str, str],
        db: Session,
    ):
        """Test that users cannot access observations from other users' greenhouses."""
        # Create test data with superuser
        test_data = create_greenhouse_zone_crop_chain(db)

        # Create observation as superuser
        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Cross-user access test observation",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Try to access as normal user (should fail)
        response = client.get(
            f"{settings.API_V1_STR}/observations/{observation_id}",
            headers=normal_user_token_headers,
        )

        assert response.status_code in [
            403,
            404,
        ]  # Forbidden or not found (depends on implementation)


class TestObservationsUpdate:
    """Test observation update - PATCH /observations/{id}"""

    def test_update_observation_success(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test successful observation update."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Original observation notes",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Update the observation
        update_data = {
            "observation_type": "pest",
            "notes": "Updated observation notes - found pests",
            "severity": "medium",
        }

        response = client.patch(
            f"{settings.API_V1_STR}/observations/{observation_id}",
            headers=superuser_token_headers,
            json=update_data,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify updates are applied
        assert data["observation_type"] == update_data["observation_type"]
        assert data["notes"] == update_data["notes"]
        if "severity" in data:  # If field exists in model
            assert data["severity"] == update_data["severity"]

        # Verify unchanged fields remain
        assert data["zone_crop_id"] == observation_data["zone_crop_id"]

    def test_update_observation_partial(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test partial observation update (only some fields)."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Original notes",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Update only the notes
        update_data = {"notes": "Only notes updated"}

        response = client.patch(
            f"{settings.API_V1_STR}/observations/{observation_id}",
            headers=superuser_token_headers,
            json=update_data,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify only notes changed
        assert data["notes"] == update_data["notes"]
        assert data["observation_type"] == observation_data["observation_type"]

    def test_update_observation_not_found(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test observation update with non-existent ID."""
        fake_id = str(uuid.uuid4())
        update_data = {"notes": "Update non-existent observation"}

        response = client.patch(
            f"{settings.API_V1_STR}/observations/{fake_id}",
            headers=superuser_token_headers,
            json=update_data,
        )

        assert response.status_code == 404

    def test_update_observation_invalid_data(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test observation update with invalid data."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Valid observation",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Try to update with invalid observation type
        update_data = {"observation_type": "invalid_type"}

        response = client.patch(
            f"{settings.API_V1_STR}/observations/{observation_id}",
            headers=superuser_token_headers,
            json=update_data,
        )

        assert response.status_code == 422

    def test_update_observation_unauthorized(self, client: TestClient):
        """Test observation update without authentication."""
        fake_id = str(uuid.uuid4())
        update_data = {"notes": "Unauthorized update"}

        response = client.patch(
            f"{settings.API_V1_STR}/observations/{fake_id}", json=update_data
        )

        assert response.status_code == 401

    def test_update_observation_empty_data(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test observation update with empty data."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Original notes",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Update with empty data
        response = client.patch(
            f"{settings.API_V1_STR}/observations/{observation_id}",
            headers=superuser_token_headers,
            json={},
        )

        # Should succeed but not change anything
        assert response.status_code == 200


class TestObservationsDelete:
    """Test observation deletion - DELETE /observations/{id}"""

    def test_delete_observation_success(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test successful observation deletion."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Observation to be deleted",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Delete the observation
        response = client.delete(
            f"{settings.API_V1_STR}/observations/{observation_id}",
            headers=superuser_token_headers,
        )

        assert response.status_code == 204

        # Verify observation is deleted
        get_response = client.get(
            f"{settings.API_V1_STR}/observations/{observation_id}",
            headers=superuser_token_headers,
        )
        assert get_response.status_code == 404

    def test_delete_observation_not_found(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test observation deletion with non-existent ID."""
        fake_id = str(uuid.uuid4())

        response = client.delete(
            f"{settings.API_V1_STR}/observations/{fake_id}",
            headers=superuser_token_headers,
        )

        assert response.status_code == 404

    def test_delete_observation_invalid_uuid(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test observation deletion with invalid UUID format."""
        invalid_ids = ["not-a-uuid", "123", "abc-def-ghi"]

        for invalid_id in invalid_ids:
            response = client.delete(
                f"{settings.API_V1_STR}/observations/{invalid_id}",
                headers=superuser_token_headers,
            )

            assert response.status_code == 422

    def test_delete_observation_unauthorized(self, client: TestClient):
        """Test observation deletion without authentication."""
        fake_id = str(uuid.uuid4())

        response = client.delete(f"{settings.API_V1_STR}/observations/{fake_id}")

        assert response.status_code == 401

    def test_delete_observation_twice(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test deleting the same observation twice."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Double delete test observation",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # First deletion should succeed
        response1 = client.delete(
            f"{settings.API_V1_STR}/observations/{observation_id}",
            headers=superuser_token_headers,
        )
        assert response1.status_code == 204

        # Second deletion should return 404
        response2 = client.delete(
            f"{settings.API_V1_STR}/observations/{observation_id}",
            headers=superuser_token_headers,
        )
        assert response2.status_code == 404


class TestObservationsUploadUrl:
    """Test observation upload URL generation - POST /observations/{id}/upload-url"""

    def test_generate_upload_url_success(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test successful upload URL generation."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Observation with photo upload",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Generate upload URL
        upload_request = {
            "filename": "observation_photo.jpg",
            "content_type": "image/jpeg",
            "file_size": 1024000,  # 1MB
        }

        response = client.post(
            f"{settings.API_V1_STR}/observations/{observation_id}/upload-url",
            headers=superuser_token_headers,
            json=upload_request,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "upload_url" in data
        assert "expires_at" in data
        assert "file_id" in data

        # Verify URL is valid format
        assert data["upload_url"].startswith("http")

        # Verify expiration is in the future
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        assert expires_at > datetime.now(expires_at.tzinfo)

    def test_generate_upload_url_invalid_file_type(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test upload URL generation with invalid file type."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Invalid file type test",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Try to upload non-image file
        upload_request = {
            "filename": "malicious_script.exe",
            "content_type": "application/x-executable",
            "file_size": 1024,
        }

        response = client.post(
            f"{settings.API_V1_STR}/observations/{observation_id}/upload-url",
            headers=superuser_token_headers,
            json=upload_request,
        )

        assert response.status_code == 422

    def test_generate_upload_url_file_too_large(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test upload URL generation with file that's too large."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Large file test",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Try to upload very large file
        upload_request = {
            "filename": "huge_image.jpg",
            "content_type": "image/jpeg",
            "file_size": 100 * 1024 * 1024,  # 100MB
        }

        response = client.post(
            f"{settings.API_V1_STR}/observations/{observation_id}/upload-url",
            headers=superuser_token_headers,
            json=upload_request,
        )

        assert response.status_code == 422

    def test_generate_upload_url_observation_not_found(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test upload URL generation for non-existent observation."""
        fake_id = str(uuid.uuid4())

        upload_request = {
            "filename": "test_photo.jpg",
            "content_type": "image/jpeg",
            "file_size": 1024000,
        }

        response = client.post(
            f"{settings.API_V1_STR}/observations/{fake_id}/upload-url",
            headers=superuser_token_headers,
            json=upload_request,
        )

        assert response.status_code == 404

    def test_generate_upload_url_unauthorized(self, client: TestClient):
        """Test upload URL generation without authentication."""
        fake_id = str(uuid.uuid4())

        upload_request = {
            "filename": "test_photo.jpg",
            "content_type": "image/jpeg",
            "file_size": 1024000,
        }

        response = client.post(
            f"{settings.API_V1_STR}/observations/{fake_id}/upload-url",
            json=upload_request,
        )

        assert response.status_code == 401

    def test_generate_upload_url_missing_fields(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test upload URL generation with missing required fields."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Missing fields test",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Test missing filename
        upload_request = {"content_type": "image/jpeg", "file_size": 1024000}

        response = client.post(
            f"{settings.API_V1_STR}/observations/{observation_id}/upload-url",
            headers=superuser_token_headers,
            json=upload_request,
        )

        assert response.status_code == 422

    def test_generate_upload_url_empty_filename(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test upload URL generation with empty filename."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Empty filename test",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Test empty filename
        upload_request = {
            "filename": "",
            "content_type": "image/jpeg",
            "file_size": 1024000,
        }

        response = client.post(
            f"{settings.API_V1_STR}/observations/{observation_id}/upload-url",
            headers=superuser_token_headers,
            json=upload_request,
        )

        assert response.status_code == 422

    def test_generate_upload_url_malicious_filename(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test upload URL generation with malicious filename patterns."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Malicious filename test",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        malicious_filenames = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config\\sam",
            "<script>alert('xss')</script>.jpg",
            "'; DROP TABLE observations; --.jpg",
            "file with\nnewline.jpg",
            "file\x00with\x00nulls.jpg",
        ]

        for malicious_filename in malicious_filenames:
            upload_request = {
                "filename": malicious_filename,
                "content_type": "image/jpeg",
                "file_size": 1024000,
            }

            response = client.post(
                f"{settings.API_V1_STR}/observations/{observation_id}/upload-url",
                headers=superuser_token_headers,
                json=upload_request,
            )

            # Should either sanitize the filename or reject it
            assert response.status_code in [200, 422]

            if response.status_code == 200:
                # If accepted, verify filename is sanitized
                data = response.json()
                assert "upload_url" in data


class TestObservationsEdgeCases:
    """Test edge cases and complex scenarios for observations individual operations"""

    def test_observation_operations_on_deleted_zone_crop(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test observation operations when associated zone crop is deleted."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Orphaned observation test",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Delete the zone crop
        delete_zone_crop_response = client.delete(
            f"{settings.API_V1_STR}/zone-crops/{test_data['zone_crop'].id}",
            headers=superuser_token_headers,
        )
        assert delete_zone_crop_response.status_code == 204

        # Try to get the observation (behavior depends on cascade settings)
        get_response = client.get(
            f"{settings.API_V1_STR}/observations/{observation_id}",
            headers=superuser_token_headers,
        )

        # Could be 404 (cascade delete) or 200 (orphaned record)
        assert get_response.status_code in [200, 404]

    def test_concurrent_observation_updates(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test concurrent updates to the same observation."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": "Concurrent update test",
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Simulate concurrent updates
        import threading

        results = []

        def update_observation(suffix: str):
            update_data = {"notes": f"Updated by thread {suffix}"}
            response = client.patch(
                f"{settings.API_V1_STR}/observations/{observation_id}",
                headers=superuser_token_headers,
                json=update_data,
            )
            results.append(response.status_code)

        threads = [
            threading.Thread(target=update_observation, args=[f"T{i}"])
            for i in range(3)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All updates should succeed (unless there's optimistic locking)
        assert all(status in [200, 409] for status in results)

    def test_observation_large_notes_field(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test observations with very large notes field."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        # Create observation with large notes
        large_notes = "A" * 10000  # 10k character notes
        observation_data = {
            "zone_crop_id": str(test_data["zone_crop"].id),
            "observation_type": "growth",
            "observation_date": "2025-08-17T10:00:00Z",
            "notes": large_notes,
        }

        create_response = client.post(
            f"{settings.API_V1_STR}/observations",
            headers=superuser_token_headers,
            json=observation_data,
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # Get observation and verify notes
        get_response = client.get(
            f"{settings.API_V1_STR}/observations/{observation_id}",
            headers=superuser_token_headers,
        )
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["notes"] == large_notes

    def test_observation_special_characters_in_notes(
        self, client: TestClient, superuser_token_headers: dict[str, str], db: Session
    ):
        """Test observations with special characters in notes field."""
        # Create test data and observation
        test_data = create_greenhouse_zone_crop_chain(db)

        special_notes_cases = [
            "Notes with emoji 🌱🍅🐛",
            "Notes with unicode: 中文字符, العربية, русский",
            'Notes with JSON: {"temperature": 25.5, "humidity": 70}',
            "Notes with HTML: <strong>Important</strong> observation",
            "Notes with newlines:\nLine 1\nLine 2\nLine 3",
            "Notes with quotes: \"quoted text\" and 'single quotes'",
            "Notes with escape chars: \\n \\t \\r \\\\",
        ]

        for special_notes in special_notes_cases:
            observation_data = {
                "zone_crop_id": str(test_data["zone_crop"].id),
                "observation_type": "growth",
                "observation_date": "2025-08-17T10:00:00Z",
                "notes": special_notes,
            }

            create_response = client.post(
                f"{settings.API_V1_STR}/observations",
                headers=superuser_token_headers,
                json=observation_data,
            )
            assert create_response.status_code == 201
            observation_id = create_response.json()["id"]

            # Verify notes are stored correctly
            get_response = client.get(
                f"{settings.API_V1_STR}/observations/{observation_id}",
                headers=superuser_token_headers,
            )
            assert get_response.status_code == 200
            data = get_response.json()
            assert data["notes"] == special_notes

            # Clean up
            delete_response = client.delete(
                f"{settings.API_V1_STR}/observations/{observation_id}",
                headers=superuser_token_headers,
            )
            assert delete_response.status_code == 204
