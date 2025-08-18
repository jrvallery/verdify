"""
Database Concurrency and Transaction Integrity Tests

This module provides comprehensive testing of database operations under
concurrent access, race conditions, and transaction integrity scenarios.

Focuses on:
- Concurrent database writes and reads
- Transaction isolation and ACID properties
- Deadlock detection and resolution
- Data consistency under high concurrency
- Resource locking and unlocking
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.api.deps import get_db
from app.main import app
from app.models import User


class DatabaseConcurrencyTester:
    """Framework for testing database concurrency and integrity."""

    def __init__(self):
        self.client = TestClient(app)
        self.test_db_engine = None
        self.test_user_id = None
        self.test_headers = {}
        self.concurrent_results = []

    def setup_test_database(self):
        """Setup test database with proper isolation."""
        self.test_db_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

        SQLModel.metadata.create_all(self.test_db_engine)

        def get_test_session():
            with Session(self.test_db_engine) as session:
                yield session

        app.dependency_overrides[get_db] = get_test_session

    def create_test_user(self):
        """Create test user for authentication."""
        with Session(self.test_db_engine) as session:
            test_user = User(
                email="concurrency@example.com",
                full_name="Concurrency Test User",
                hashed_password="test_hash",
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
            data={"username": "concurrency@example.com", "password": "testpass123"},
        )
        if response.status_code == 200:
            token = response.json()["access_token"]
            self.test_headers = {"Authorization": f"Bearer {token}"}

    def teardown(self):
        """Clean up test resources."""
        app.dependency_overrides.clear()
        if self.test_db_engine:
            self.test_db_engine.dispose()


class TestConcurrentDatabaseWrites:
    """Test concurrent database write operations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = DatabaseConcurrencyTester()
        self.tester.setup_test_database()
        self.tester.create_test_user()
        yield
        self.tester.teardown()

    def test_concurrent_greenhouse_creation(self):
        """Test concurrent greenhouse creation for race conditions."""

        def create_greenhouse(index: int) -> dict[str, Any]:
            """Create a greenhouse and return result."""
            start_time = time.time()

            data = {
                "title": f"Concurrent Greenhouse {index}",
                "description": f"Created by thread {index}",
                "latitude": 37.7749 + (index * 0.001),  # Unique coordinates
                "longitude": -122.4194 + (index * 0.001),
            }

            response = self.tester.client.post(
                "/api/v1/greenhouses/", json=data, headers=self.tester.test_headers
            )

            end_time = time.time()

            return {
                "thread_id": index,
                "status_code": response.status_code,
                "response_time": end_time - start_time,
                "data": response.json() if response.status_code == 201 else None,
                "error": response.text if response.status_code != 201 else None,
            }

        # Execute concurrent greenhouse creation
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(create_greenhouse, i) for i in range(20)]

            results = [future.result() for future in as_completed(futures)]

        # All should succeed
        success_count = sum(1 for r in results if r["status_code"] == 201)
        assert success_count == 20

        # Verify all have unique IDs
        created_ids = {r["data"]["id"] for r in results if r["data"]}
        assert len(created_ids) == 20  # All unique

        # Verify database consistency
        final_response = self.tester.client.get(
            "/api/v1/greenhouses/", headers=self.tester.test_headers
        )
        assert final_response.json()["total"] == 20

    def test_concurrent_zone_creation_same_greenhouse(self):
        """Test concurrent zone creation in the same greenhouse."""

        # Create test greenhouse
        gh_data = {
            "title": "Concurrency Test Greenhouse",
            "latitude": 37.7749,
            "longitude": -122.4194,
        }

        gh_response = self.tester.client.post(
            "/api/v1/greenhouses/", json=gh_data, headers=self.tester.test_headers
        )
        greenhouse_id = gh_response.json()["id"]

        def create_zone(zone_number: int) -> dict[str, Any]:
            """Create a zone in the test greenhouse."""
            start_time = time.time()

            data = {
                "greenhouse_id": greenhouse_id,
                "zone_number": zone_number,
                "location": ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][
                    zone_number % 8
                ],
                "is_active": True,
            }

            response = self.tester.client.post(
                "/api/v1/zones/", json=data, headers=self.tester.test_headers
            )

            end_time = time.time()

            return {
                "zone_number": zone_number,
                "status_code": response.status_code,
                "response_time": end_time - start_time,
                "error": response.text if response.status_code != 201 else None,
            }

        # Execute concurrent zone creation
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(create_zone, i + 1) for i in range(15)]

            results = [future.result() for future in as_completed(futures)]

        # All should succeed (unique zone numbers)
        success_count = sum(1 for r in results if r["status_code"] == 201)
        assert success_count == 15

        # Verify database consistency
        zones_response = self.tester.client.get(
            "/api/v1/zones/",
            params={"greenhouse_id": greenhouse_id},
            headers=self.tester.test_headers,
        )
        assert zones_response.json()["total"] == 15

    def test_concurrent_duplicate_zone_numbers(self):
        """Test concurrent creation of zones with duplicate numbers (should conflict)."""

        # Create test greenhouse
        gh_data = {
            "title": "Conflict Test Greenhouse",
            "latitude": 37.7749,
            "longitude": -122.4194,
        }

        gh_response = self.tester.client.post(
            "/api/v1/greenhouses/", json=gh_data, headers=self.tester.test_headers
        )
        greenhouse_id = gh_response.json()["id"]

        def create_duplicate_zone() -> int:
            """Attempt to create zone with same number."""
            data = {
                "greenhouse_id": greenhouse_id,
                "zone_number": 1,  # Same number for all
                "location": "N",
                "is_active": True,
            }

            response = self.tester.client.post(
                "/api/v1/zones/", json=data, headers=self.tester.test_headers
            )

            return response.status_code

        # Execute concurrent duplicate zone creation
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_duplicate_zone) for _ in range(5)]
            results = [future.result() for future in as_completed(futures)]

        # Only one should succeed, others should conflict
        success_count = sum(1 for status in results if status == 201)
        conflict_count = sum(1 for status in results if status == 409)

        assert success_count == 1
        assert conflict_count == 4

        # Verify only one zone was created
        zones_response = self.tester.client.get(
            "/api/v1/zones/",
            params={"greenhouse_id": greenhouse_id},
            headers=self.tester.test_headers,
        )
        assert zones_response.json()["total"] == 1


class TestTransactionIntegrity:
    """Test transaction integrity and ACID properties."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = DatabaseConcurrencyTester()
        self.tester.setup_test_database()
        self.tester.create_test_user()
        yield
        self.tester.teardown()

    def test_atomic_operations(self):
        """Test atomicity of database operations."""

        # Get initial count
        initial_response = self.tester.client.get(
            "/api/v1/greenhouses/", headers=self.tester.test_headers
        )
        initial_count = initial_response.json()["total"]

        # Attempt operation that should fail and rollback
        invalid_data = {
            "title": "Test Greenhouse",
            "latitude": 100.0,  # Invalid latitude
            "longitude": -122.4194,
        }

        response = self.tester.client.post(
            "/api/v1/greenhouses/", json=invalid_data, headers=self.tester.test_headers
        )

        assert response.status_code == 422

        # Verify no partial state was saved
        final_response = self.tester.client.get(
            "/api/v1/greenhouses/", headers=self.tester.test_headers
        )
        final_count = final_response.json()["total"]

        assert final_count == initial_count

    def test_isolation_concurrent_reads_writes(self):
        """Test isolation between concurrent reads and writes."""

        # Create initial greenhouse
        initial_data = {
            "title": "Initial Greenhouse",
            "latitude": 37.7749,
            "longitude": -122.4194,
        }

        create_response = self.tester.client.post(
            "/api/v1/greenhouses/", json=initial_data, headers=self.tester.test_headers
        )
        greenhouse_id = create_response.json()["id"]

        def read_greenhouse() -> dict[str, Any]:
            """Read greenhouse data."""
            response = self.tester.client.get(
                f"/api/v1/greenhouses/{greenhouse_id}", headers=self.tester.test_headers
            )
            return {
                "status": response.status_code,
                "title": response.json()["title"]
                if response.status_code == 200
                else None,
                "timestamp": time.time(),
            }

        def update_greenhouse() -> int:
            """Update greenhouse data."""
            update_data = {
                "title": "Updated Greenhouse",
                "description": "Updated during concurrency test",
            }

            response = self.tester.client.patch(
                f"/api/v1/greenhouses/{greenhouse_id}",
                json=update_data,
                headers=self.tester.test_headers,
            )
            return response.status_code

        # Execute concurrent reads and writes
        with ThreadPoolExecutor(max_workers=6) as executor:
            # Submit multiple reads and one write
            read_futures = [executor.submit(read_greenhouse) for _ in range(5)]
            write_future = executor.submit(update_greenhouse)

            # Collect results
            read_results = [future.result() for future in read_futures]
            write_result = write_future.result()

        # All reads should succeed
        successful_reads = sum(1 for r in read_results if r["status"] == 200)
        assert successful_reads == 5

        # Write should succeed
        assert write_result == 200

        # Final state should be consistent
        final_response = self.tester.client.get(
            f"/api/v1/greenhouses/{greenhouse_id}", headers=self.tester.test_headers
        )
        assert final_response.json()["title"] == "Updated Greenhouse"

    def test_consistency_after_concurrent_updates(self):
        """Test data consistency after concurrent updates."""

        # Create greenhouse
        gh_data = {
            "title": "Consistency Test",
            "latitude": 37.7749,
            "longitude": -122.4194,
        }

        create_response = self.tester.client.post(
            "/api/v1/greenhouses/", json=gh_data, headers=self.tester.test_headers
        )
        greenhouse_id = create_response.json()["id"]

        def update_description(suffix: str) -> int:
            """Update greenhouse description."""
            update_data = {
                "description": f"Updated by thread {suffix} at {time.time()}"
            }

            response = self.tester.client.patch(
                f"/api/v1/greenhouses/{greenhouse_id}",
                json=update_data,
                headers=self.tester.test_headers,
            )
            return response.status_code

        # Execute concurrent updates
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(update_description, str(i)) for i in range(5)]

            results = [future.result() for future in as_completed(futures)]

        # All updates should succeed
        success_count = sum(1 for status in results if status == 200)
        assert success_count == 5

        # Final state should be consistent (one of the updates should be final)
        final_response = self.tester.client.get(
            f"/api/v1/greenhouses/{greenhouse_id}", headers=self.tester.test_headers
        )

        assert final_response.status_code == 200
        assert "Updated by thread" in final_response.json()["description"]


class TestDatabasePerformanceUnderLoad:
    """Test database performance under concurrent load."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = DatabaseConcurrencyTester()
        self.tester.setup_test_database()
        self.tester.create_test_user()
        yield
        self.tester.teardown()

    def test_high_concurrent_read_load(self):
        """Test database performance under high concurrent read load."""

        # Create some test data
        for i in range(10):
            gh_data = {
                "title": f"Load Test Greenhouse {i}",
                "latitude": 37.7749 + (i * 0.001),
                "longitude": -122.4194 + (i * 0.001),
            }

            self.tester.client.post(
                "/api/v1/greenhouses/", json=gh_data, headers=self.tester.test_headers
            )

        def perform_read() -> dict[str, Any]:
            """Perform a read operation and measure performance."""
            start_time = time.time()

            response = self.tester.client.get(
                "/api/v1/greenhouses/", headers=self.tester.test_headers
            )

            end_time = time.time()

            return {
                "status_code": response.status_code,
                "response_time": end_time - start_time,
                "item_count": len(response.json()["data"])
                if response.status_code == 200
                else 0,
            }

        # Execute high concurrent read load
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(perform_read) for _ in range(50)]
            results = [future.result() for future in as_completed(futures)]

        # All should succeed
        success_count = sum(1 for r in results if r["status_code"] == 200)
        assert success_count == 50

        # Performance should be reasonable
        avg_response_time = sum(r["response_time"] for r in results) / len(results)
        assert avg_response_time < 1.0  # Less than 1 second average

        # Data consistency
        unique_counts = {r["item_count"] for r in results}
        assert len(unique_counts) == 1  # All should return same count

    def test_mixed_read_write_load(self):
        """Test database under mixed read/write load."""

        read_results = []
        write_results = []

        def perform_read() -> dict[str, Any]:
            """Perform read operation."""
            start_time = time.time()
            response = self.tester.client.get(
                "/api/v1/greenhouses/", headers=self.tester.test_headers
            )
            end_time = time.time()

            result = {
                "operation": "read",
                "status_code": response.status_code,
                "response_time": end_time - start_time,
            }
            read_results.append(result)
            return result

        def perform_write(index: int) -> dict[str, Any]:
            """Perform write operation."""
            start_time = time.time()

            data = {
                "title": f"Mixed Load Greenhouse {index}",
                "latitude": 37.7749 + (index * 0.0001),
                "longitude": -122.4194 + (index * 0.0001),
            }

            response = self.tester.client.post(
                "/api/v1/greenhouses/", json=data, headers=self.tester.test_headers
            )

            end_time = time.time()

            result = {
                "operation": "write",
                "status_code": response.status_code,
                "response_time": end_time - start_time,
            }
            write_results.append(result)
            return result

        # Execute mixed workload
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = []

            # 70% reads, 30% writes
            for i in range(35):  # 35 reads
                futures.append(executor.submit(perform_read))

            for i in range(15):  # 15 writes
                futures.append(executor.submit(perform_write, i))

            # Wait for completion
            [future.result() for future in as_completed(futures)]

        # Analyze results
        total_operations = len(read_results) + len(write_results)
        successful_reads = sum(1 for r in read_results if r["status_code"] == 200)
        successful_writes = sum(1 for r in write_results if r["status_code"] == 201)

        assert successful_reads == 35
        assert successful_writes == 15

        # Performance metrics
        avg_read_time = sum(r["response_time"] for r in read_results) / len(
            read_results
        )
        avg_write_time = sum(r["response_time"] for r in write_results) / len(
            write_results
        )

        assert avg_read_time < 0.5  # Reads should be faster
        assert avg_write_time < 1.0  # Writes can be slower but reasonable


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
