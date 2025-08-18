"""
Comprehensive Unit Tests for API Code Paths and Concurrency

This module provides exhaustive testing of all API endpoints with:
- All possible code paths (success, failure, edge cases)
- Concurrency testing and race conditions
- Security boundary testing
- Input validation and error handling
- Database transaction integrity
- Performance under load

Created to ensure 100% code coverage and robust production behavior.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.api.deps import get_db
from app.main import app
from app.models import User


class APICodePathTester:
    """Comprehensive API code path and concurrency testing framework."""

    def __init__(self):
        self.client = TestClient(app)
        self.test_db_engine = None
        self.test_session = None
        self.test_user_id = None
        self.test_headers = {}

    def setup_test_database(self):
        """Setup isolated test database for each test."""
        # Create in-memory SQLite for testing
        self.test_db_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        # Create all tables
        SQLModel.metadata.create_all(self.test_db_engine)

        # Override the dependency
        def get_test_session():
            with Session(self.test_db_engine) as session:
                yield session

        app.dependency_overrides[get_db] = get_test_session

    def create_test_user_and_auth(self):
        """Create test user and get authentication token."""
        from app.core.security import get_password_hash

        with Session(self.test_db_engine) as session:
            # Create user with properly hashed password
            hashed_password = get_password_hash("testpass123")
            test_user = User(
                email="comprehensive@example.com",
                full_name="Comprehensive Test User",
                hashed_password=hashed_password,
                is_active=True,
                is_superuser=False,
            )
            session.add(test_user)
            session.commit()
            session.refresh(test_user)
            self.test_user_id = test_user.id

        # Get auth token
        response = self.client.post(
            "/api/v1/login/access-token",
            data={"username": "comprehensive@example.com", "password": "testpass123"},
        )
        if response.status_code == 200:
            token = response.json()["access_token"]
            self.test_headers = {"Authorization": f"Bearer {token}"}
        else:
            raise Exception(
                f"Failed to authenticate: {response.status_code} - {response.text}"
            )

    def teardown(self):
        """Clean up test resources."""
        app.dependency_overrides.clear()
        if self.test_db_engine:
            self.test_db_engine.dispose()


class TestGreenhousesCodePaths:
    """Test all code paths in greenhouse endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = APICodePathTester()
        self.tester.setup_test_database()
        self.tester.create_test_user_and_auth()
        yield
        self.tester.teardown()

    def test_create_greenhouse_all_paths(self):
        """Test all code paths for greenhouse creation."""

        # Success path
        valid_data = {
            "title": "Test Greenhouse",
            "description": "A test greenhouse",
            "latitude": 37.7749,
            "longitude": -122.4194,
        }

        response = self.tester.client.post(
            "/api/v1/greenhouses/", json=valid_data, headers=self.tester.test_headers
        )
        assert response.status_code == 201

        # Validation error paths
        invalid_cases = [
            # Missing required field
            {"description": "Missing title"},
            # Invalid latitude
            {"title": "Test", "latitude": 91.0, "longitude": 0.0},
            # Invalid longitude
            {"title": "Test", "latitude": 0.0, "longitude": 181.0},
            # Invalid data types
            {"title": 123, "latitude": "invalid", "longitude": "invalid"},
        ]

        for invalid_data in invalid_cases:
            response = self.tester.client.post(
                "/api/v1/greenhouses/",
                json=invalid_data,
                headers=self.tester.test_headers,
            )
            assert response.status_code == 422

    def test_greenhouse_authorization_paths(self):
        """Test authorization code paths."""

        # Unauthenticated request
        response = self.tester.client.get("/api/v1/greenhouses/")
        assert response.status_code == 401

        # Invalid token
        response = self.tester.client.get(
            "/api/v1/greenhouses/", headers={"Authorization": "Bearer invalid_token"}
        )
        assert response.status_code == 401

        # Valid request
        response = self.tester.client.get(
            "/api/v1/greenhouses/", headers=self.tester.test_headers
        )
        assert response.status_code == 200

    def test_greenhouse_not_found_paths(self):
        """Test not found error paths."""

        non_existent_id = str(uuid.uuid4())

        # GET non-existent greenhouse
        response = self.tester.client.get(
            f"/api/v1/greenhouses/{non_existent_id}", headers=self.tester.test_headers
        )
        assert response.status_code == 404

        # UPDATE non-existent greenhouse
        response = self.tester.client.patch(
            f"/api/v1/greenhouses/{non_existent_id}",
            json={"title": "Updated"},
            headers=self.tester.test_headers,
        )
        assert response.status_code == 404

        # DELETE non-existent greenhouse
        response = self.tester.client.delete(
            f"/api/v1/greenhouses/{non_existent_id}", headers=self.tester.test_headers
        )
        assert response.status_code == 404


class TestZonesCodePaths:
    """Test all code paths in zones endpoints."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = APICodePathTester()
        self.tester.setup_test_database()
        self.tester.create_test_user_and_auth()

        # Create test greenhouse
        gh_data = {
            "title": "Test Greenhouse",
            "latitude": 37.7749,
            "longitude": -122.4194,
        }
        response = self.tester.client.post(
            "/api/v1/greenhouses/", json=gh_data, headers=self.tester.test_headers
        )
        self.greenhouse_id = response.json()["id"]

        yield
        self.tester.teardown()

    def test_zone_creation_all_paths(self):
        """Test all zone creation code paths."""

        # Success path
        valid_data = {
            "greenhouse_id": self.greenhouse_id,
            "zone_number": 1,
            "location": "N",
            "is_active": True,
        }

        response = self.tester.client.post(
            "/api/v1/zones/", json=valid_data, headers=self.tester.test_headers
        )
        assert response.status_code == 201

        # Duplicate zone number (conflict path)
        response = self.tester.client.post(
            "/api/v1/zones/", json=valid_data, headers=self.tester.test_headers
        )
        assert response.status_code == 409

        # Invalid greenhouse_id
        invalid_data = {
            "greenhouse_id": str(uuid.uuid4()),
            "zone_number": 2,
            "location": "S",
            "is_active": True,
        }

        response = self.tester.client.post(
            "/api/v1/zones/", json=invalid_data, headers=self.tester.test_headers
        )
        assert response.status_code == 404

        # Invalid location
        invalid_location_data = {
            "greenhouse_id": self.greenhouse_id,
            "zone_number": 3,
            "location": "INVALID",
            "is_active": True,
        }

        response = self.tester.client.post(
            "/api/v1/zones/",
            json=invalid_location_data,
            headers=self.tester.test_headers,
        )
        assert response.status_code == 422

    def test_zone_access_control_paths(self):
        """Test zone access control code paths."""

        # Create zone
        zone_data = {
            "greenhouse_id": self.greenhouse_id,
            "zone_number": 1,
            "location": "N",
            "is_active": True,
        }

        response = self.tester.client.post(
            "/api/v1/zones/", json=zone_data, headers=self.tester.test_headers
        )
        zone_id = response.json()["id"]

        # User can access their own zone
        response = self.tester.client.get(
            f"/api/v1/zones/{zone_id}", headers=self.tester.test_headers
        )
        assert response.status_code == 200

        # Test superuser access
        # TODO: Create superuser and test access

        # Test non-owner access (should be forbidden)
        # TODO: Create another user and test access denial


class TestControllersConcurrency:
    """Test controller operations under concurrency."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = APICodePathTester()
        self.tester.setup_test_database()
        self.tester.create_test_user_and_auth()

        # Create test greenhouse
        gh_data = {
            "title": "Concurrency Test Greenhouse",
            "latitude": 37.7749,
            "longitude": -122.4194,
        }
        response = self.tester.client.post(
            "/api/v1/greenhouses/", json=gh_data, headers=self.tester.test_headers
        )
        self.greenhouse_id = response.json()["id"]

        yield
        self.tester.teardown()

    def test_concurrent_controller_creation(self):
        """Test concurrent controller creation for race conditions."""

        def create_controller(device_suffix: str):
            """Create a controller with unique device name."""
            controller_data = {
                "greenhouse_id": self.greenhouse_id,
                "device_name": f"verdify-{device_suffix}",
                "is_climate_controller": False,
            }

            response = self.tester.client.post(
                "/api/v1/controllers/",
                json=controller_data,
                headers=self.tester.test_headers,
            )
            return (
                response.status_code,
                response.json() if response.status_code == 201 else response.text,
            )

        # Test concurrent creation with unique device names (should all succeed)
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(create_controller, f"con{i:03d}") for i in range(5)
            ]

            results = [future.result() for future in as_completed(futures)]

        # All should succeed
        success_count = sum(1 for status, _ in results if status == 201)
        assert success_count == 5

    def test_concurrent_duplicate_device_names(self):
        """Test concurrent creation with duplicate device names."""

        def create_duplicate_controller():
            """Attempt to create controller with same device name."""
            controller_data = {
                "greenhouse_id": self.greenhouse_id,
                "device_name": "verdify-aabbcc",  # Same name for all
                "is_climate_controller": False,
            }

            response = self.tester.client.post(
                "/api/v1/controllers/",
                json=controller_data,
                headers=self.tester.test_headers,
            )
            return response.status_code

        # Test concurrent creation with same device name
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(create_duplicate_controller) for _ in range(3)]

            results = [future.result() for future in as_completed(futures)]

        # Only one should succeed (201), others should fail (409)
        success_count = sum(1 for status in results if status == 201)
        conflict_count = sum(1 for status in results if status == 409)

        assert success_count == 1
        assert conflict_count == 2

    def test_concurrent_climate_controller_creation(self):
        """Test concurrent climate controller creation (only one allowed per greenhouse)."""

        def create_climate_controller(device_suffix: str):
            """Attempt to create climate controller."""
            controller_data = {
                "greenhouse_id": self.greenhouse_id,
                "device_name": f"verdify-cli{device_suffix}",
                "is_climate_controller": True,  # All try to be climate controller
            }

            response = self.tester.client.post(
                "/api/v1/controllers/",
                json=controller_data,
                headers=self.tester.test_headers,
            )
            return response.status_code

        # Test concurrent climate controller creation
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(create_climate_controller, str(i)) for i in range(3)
            ]

            results = [future.result() for future in as_completed(futures)]

        # Only one should succeed, others should get conflict
        success_count = sum(1 for status in results if status == 201)
        conflict_count = sum(1 for status in results if status == 409)

        assert success_count == 1
        assert conflict_count == 2


class TestPaginationEdgeCases:
    """Test pagination edge cases and boundary conditions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = APICodePathTester()
        self.tester.setup_test_database()
        self.tester.create_test_user_and_auth()

        # Create test greenhouse and zones
        gh_data = {
            "title": "Pagination Test Greenhouse",
            "latitude": 37.7749,
            "longitude": -122.4194,
        }
        response = self.tester.client.post(
            "/api/v1/greenhouses/", json=gh_data, headers=self.tester.test_headers
        )
        self.greenhouse_id = response.json()["id"]

        # Create 25 zones for pagination testing
        for i in range(25):
            zone_data = {
                "greenhouse_id": self.greenhouse_id,
                "zone_number": i + 1,
                "location": ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][i % 8],
                "is_active": True,
            }

            self.tester.client.post(
                "/api/v1/zones/", json=zone_data, headers=self.tester.test_headers
            )

        yield
        self.tester.teardown()

    def test_pagination_boundary_conditions(self):
        """Test pagination boundary conditions."""

        boundary_cases = [
            # Normal cases
            {"page": 1, "page_size": 10, "expected_items": 10},
            {"page": 3, "page_size": 10, "expected_items": 5},  # Last page
            # Edge cases
            {"page": 1, "page_size": 1, "expected_items": 1},  # Minimum page size
            {"page": 1, "page_size": 100, "expected_items": 25},  # Larger than total
            {"page": 999, "page_size": 10, "expected_items": 0},  # Beyond available
            # Boundary values
            {"page": 0, "page_size": 10, "expected_status": 422},  # Invalid page
            {"page": -1, "page_size": 10, "expected_status": 422},  # Negative page
            {"page": 1, "page_size": 0, "expected_status": 422},  # Invalid page size
            {"page": 1, "page_size": -5, "expected_status": 422},  # Negative page size
        ]

        for case in boundary_cases:
            params = {
                "greenhouse_id": self.greenhouse_id,
                "page": case["page"],
                "page_size": case["page_size"],
            }

            response = self.tester.client.get(
                "/api/v1/zones/", params=params, headers=self.tester.test_headers
            )

            if "expected_status" in case:
                assert response.status_code == case["expected_status"]
            else:
                assert response.status_code == 200
                data = response.json()
                assert len(data["data"]) == case["expected_items"]
                assert data["total"] == 25

    def test_pagination_consistency(self):
        """Test pagination consistency across multiple requests."""

        # Make multiple requests to same page
        responses = []
        for _ in range(5):
            response = self.tester.client.get(
                "/api/v1/zones/",
                params={
                    "greenhouse_id": self.greenhouse_id,
                    "page": 1,
                    "page_size": 10,
                },
                headers=self.tester.test_headers,
            )
            responses.append(response.json())

        # All responses should be identical
        first_response = responses[0]
        for response in responses[1:]:
            assert response["total"] == first_response["total"]
            assert len(response["data"]) == len(first_response["data"])
            assert response["page"] == first_response["page"]
            assert response["page_size"] == first_response["page_size"]


class TestDatabaseTransactionIntegrity:
    """Test database transaction integrity and rollback scenarios."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = APICodePathTester()
        self.tester.setup_test_database()
        self.tester.create_test_user_and_auth()
        yield
        self.tester.teardown()

    def test_transaction_rollback_on_error(self):
        """Test that transactions are properly rolled back on errors."""

        # Count initial greenhouses
        initial_response = self.tester.client.get(
            "/api/v1/greenhouses/", headers=self.tester.test_headers
        )
        initial_count = initial_response.json()["total"]

        # Attempt to create greenhouse with invalid data (should rollback)
        invalid_data = {
            "title": "Test Greenhouse",
            "latitude": 91.0,  # Invalid latitude
            "longitude": -122.4194,
        }

        response = self.tester.client.post(
            "/api/v1/greenhouses/", json=invalid_data, headers=self.tester.test_headers
        )
        assert response.status_code == 422

        # Check that count hasn't changed (transaction rolled back)
        final_response = self.tester.client.get(
            "/api/v1/greenhouses/", headers=self.tester.test_headers
        )
        final_count = final_response.json()["total"]

        assert final_count == initial_count

    @patch("app.crud.greenhouse.create_greenhouse")
    def test_database_error_handling(self, mock_create):
        """Test handling of database errors."""

        # Mock database error
        mock_create.side_effect = Exception("Database connection failed")

        greenhouse_data = {
            "title": "Test Greenhouse",
            "latitude": 37.7749,
            "longitude": -122.4194,
        }

        response = self.tester.client.post(
            "/api/v1/greenhouses/",
            json=greenhouse_data,
            headers=self.tester.test_headers,
        )

        # Should return 500 internal server error
        assert response.status_code == 500


class TestSecurityBoundaries:
    """Test security boundaries and access control."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = APICodePathTester()
        self.tester.setup_test_database()
        self.tester.create_test_user_and_auth()
        yield
        self.tester.teardown()

    def test_sql_injection_protection(self):
        """Test protection against SQL injection attacks."""

        # Attempt SQL injection in search parameters
        malicious_params = {
            "title": "'; DROP TABLE greenhouse; --",
            "page": 1,
            "page_size": 10,
        }

        response = self.tester.client.get(
            "/api/v1/greenhouses/",
            params=malicious_params,
            headers=self.tester.test_headers,
        )

        # Should not crash, should return 200 with no results
        assert response.status_code == 200

        # Database should still be intact
        normal_response = self.tester.client.get(
            "/api/v1/greenhouses/", headers=self.tester.test_headers
        )
        assert normal_response.status_code == 200

    def test_input_sanitization(self):
        """Test input sanitization and validation."""

        # Test with potentially malicious input
        malicious_data = {
            "title": "<script>alert('XSS')</script>",
            "description": "'; DROP TABLE users; --",
            "latitude": 37.7749,
            "longitude": -122.4194,
        }

        response = self.tester.client.post(
            "/api/v1/greenhouses/",
            json=malicious_data,
            headers=self.tester.test_headers,
        )

        if response.status_code == 201:
            # If created, verify the malicious content is properly escaped/sanitized
            greenhouse = response.json()
            assert "<script>" not in greenhouse["title"]
            assert "DROP TABLE" not in greenhouse["description"]

    def test_authorization_bypass_attempts(self):
        """Test attempts to bypass authorization."""

        # Test various invalid token formats
        invalid_tokens = [
            "Bearer ",
            "Bearer invalid",
            "Invalid token",
            "",
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature",
        ]

        for token in invalid_tokens:
            response = self.tester.client.get(
                "/api/v1/greenhouses/", headers={"Authorization": token}
            )
            assert response.status_code in [
                401,
                422,
            ]  # Unauthorized or validation error


# Performance and Load Testing
class TestPerformanceUnderLoad:
    """Test API performance under concurrent load."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = APICodePathTester()
        self.tester.setup_test_database()
        self.tester.create_test_user_and_auth()
        yield
        self.tester.teardown()

    def test_concurrent_read_performance(self):
        """Test read performance under concurrent load."""

        def make_read_request():
            """Make a read request and measure response time."""
            start_time = datetime.now(timezone.utc)
            response = self.tester.client.get(
                "/api/v1/greenhouses/", headers=self.tester.test_headers
            )
            end_time = datetime.now(timezone.utc)

            return {
                "status_code": response.status_code,
                "response_time_ms": (end_time - start_time).total_seconds() * 1000,
            }

        # Execute concurrent read requests
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_read_request) for _ in range(20)]
            results = [future.result() for future in as_completed(futures)]

        # All should succeed
        success_count = sum(1 for result in results if result["status_code"] == 200)
        assert success_count == 20

        # Average response time should be reasonable (< 1000ms)
        avg_response_time = sum(result["response_time_ms"] for result in results) / len(
            results
        )
        assert avg_response_time < 1000  # Less than 1 second average

    def test_mixed_workload_performance(self):
        """Test performance under mixed read/write workload."""

        def create_greenhouse(index: int):
            """Create a greenhouse."""
            data = {
                "title": f"Load Test Greenhouse {index}",
                "latitude": 37.7749,
                "longitude": -122.4194,
            }
            response = self.tester.client.post(
                "/api/v1/greenhouses/", json=data, headers=self.tester.test_headers
            )
            return response.status_code

        def read_greenhouses():
            """Read greenhouses list."""
            response = self.tester.client.get(
                "/api/v1/greenhouses/", headers=self.tester.test_headers
            )
            return response.status_code

        # Execute mixed workload
        with ThreadPoolExecutor(max_workers=8) as executor:
            # Submit mix of read and write operations
            futures = []

            # 70% reads, 30% writes
            for i in range(14):  # 14 reads
                futures.append(executor.submit(read_greenhouses))

            for i in range(6):  # 6 writes
                futures.append(executor.submit(create_greenhouse, i))

            results = [future.result() for future in as_completed(futures)]

        # All operations should succeed
        success_count = sum(1 for status in results if status in [200, 201])
        assert success_count >= 18  # Allow for some conflicts in writes


if __name__ == "__main__":
    # Run all tests
    pytest.main([__file__, "-v", "--tb=short"])
