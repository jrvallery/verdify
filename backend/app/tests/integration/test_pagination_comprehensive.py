"""
Pagination Testing Suite

Comprehensive testing of pagination across all endpoints with real data volumes.
Replaces ad-hoc pagination testing with systematic validation.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


class PaginationTestFramework:
    """Framework for testing pagination across all API endpoints."""

    def __init__(self, client: TestClient):
        self.client = client
        self.headers = {}
        self.test_greenhouse_id = None

    def authenticate(self):
        """Authenticate user for testing."""
        response = self.client.post(
            "/api/v1/login/access-token",
            data={"username": "debug_user@example.com", "password": "testpass123"},
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {token}"}

    def setup_test_data(self):
        """Create test data for pagination testing."""
        # Create test greenhouse
        greenhouse_data = {
            "title": "Pagination Test Greenhouse",
            "description": "Test facility for pagination validation",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "location": "New York, NY - Pagination Test",
        }

        response = self.client.post(
            "/api/v1/greenhouses/", json=greenhouse_data, headers=self.headers
        )
        assert response.status_code == 201
        self.test_greenhouse_id = response.json()["id"]

        # Create 35 test zones for pagination testing
        locations = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        for i in range(35):
            zone_data = {
                "greenhouse_id": self.test_greenhouse_id,
                "zone_number": i + 1,
                "location": locations[i % len(locations)],
                "is_active": True,
            }

            response = self.client.post(
                "/api/v1/zones/", json=zone_data, headers=self.headers
            )
            assert response.status_code == 201

    def test_pagination_scenarios(self, endpoint: str, params: dict = None):
        """Test various pagination scenarios for an endpoint."""
        if params is None:
            params = {}

        scenarios = [
            {"page": 1, "page_size": 10, "desc": "First page, standard size"},
            {"page": 2, "page_size": 10, "desc": "Second page, standard size"},
            {"page": 4, "page_size": 10, "desc": "Last page with partial results"},
            {"page": 1, "page_size": 5, "desc": "Small page size"},
            {"page": 1, "page_size": 50, "desc": "Large page size"},
            {"page": 999, "page_size": 10, "desc": "Page beyond available data"},
            {"page": 0, "page_size": 10, "desc": "Invalid page number (0)"},
            {"page": -1, "page_size": 10, "desc": "Negative page number"},
            {"page": 1, "page_size": 0, "desc": "Invalid page size (0)"},
            {"page": 1, "page_size": -5, "desc": "Negative page size"},
        ]

        results = []
        for scenario in scenarios:
            test_params = {
                **params,
                "page": scenario["page"],
                "page_size": scenario["page_size"],
            }

            response = self.client.get(
                endpoint, params=test_params, headers=self.headers
            )

            result = {
                "scenario": scenario["desc"],
                "page": scenario["page"],
                "page_size": scenario["page_size"],
                "status_code": response.status_code,
                "valid": False,
                "items_count": 0,
                "total": 0,
            }

            if response.status_code == 200:
                data = response.json()
                result["valid"] = True
                result["items_count"] = len(data.get("data", []))
                result["total"] = data.get("total", 0)
                result["page_returned"] = data.get("page", 0)
                result["page_size_returned"] = data.get("page_size", 0)

            results.append(result)

        return results


@pytest.fixture
def pagination_framework():
    """Fixture providing pagination testing framework."""
    client = TestClient(app)
    framework = PaginationTestFramework(client)
    framework.authenticate()
    framework.setup_test_data()
    return framework


class TestPaginationComprehensive:
    """Comprehensive pagination testing across all endpoints."""

    def test_zones_pagination(self, pagination_framework):
        """Test zones pagination with real data volume."""
        results = pagination_framework.test_pagination_scenarios(
            "/api/v1/zones/", {"greenhouse_id": pagination_framework.test_greenhouse_id}
        )

        # Verify standard pagination works
        first_page = next(r for r in results if r["page"] == 1 and r["page_size"] == 10)
        assert first_page["valid"]
        assert first_page["items_count"] == 10
        assert first_page["total"] >= 35

        # Verify second page works
        second_page = next(
            r for r in results if r["page"] == 2 and r["page_size"] == 10
        )
        assert second_page["valid"]
        assert second_page["items_count"] == 10

        # Verify last page with partial results
        last_page = next(r for r in results if r["page"] == 4 and r["page_size"] == 10)
        assert last_page["valid"]
        assert last_page["items_count"] == 5  # 35 total, so page 4 should have 5 items

    def test_greenhouses_pagination(self, pagination_framework):
        """Test greenhouses pagination."""
        results = pagination_framework.test_pagination_scenarios("/api/v1/greenhouses/")

        # Should have at least our test greenhouse
        first_page = next(r for r in results if r["page"] == 1 and r["page_size"] == 10)
        assert first_page["valid"]
        assert first_page["total"] >= 1

    def test_pagination_edge_cases(self, pagination_framework):
        """Test pagination edge cases and error handling."""
        results = pagination_framework.test_pagination_scenarios(
            "/api/v1/zones/", {"greenhouse_id": pagination_framework.test_greenhouse_id}
        )

        # Page beyond available data should return empty results
        beyond_page = next(r for r in results if r["page"] == 999)
        assert beyond_page["valid"]  # Should still be 200 OK
        assert beyond_page["items_count"] == 0

        # Large page size should return all available items
        large_page = next(r for r in results if r["page_size"] == 50)
        assert large_page["valid"]
        assert large_page["items_count"] == large_page["total"]

        # Invalid parameters should be handled gracefully
        # (Framework should normalize negative/zero values)
        invalid_cases = [r for r in results if r["page"] <= 0 or r["page_size"] <= 0]
        for case in invalid_cases:
            # Either returns 400 for validation error, or normalizes to valid values
            assert case["status_code"] in [200, 400, 422]

    def test_pagination_consistency(self, pagination_framework):
        """Test pagination consistency across multiple requests."""
        endpoint = "/api/v1/zones/"
        params = {"greenhouse_id": pagination_framework.test_greenhouse_id}

        # Make multiple requests to same page
        responses = []
        for _ in range(3):
            response = pagination_framework.client.get(
                endpoint,
                params={**params, "page": 1, "page_size": 10},
                headers=pagination_framework.headers,
            )
            assert response.status_code == 200
            responses.append(response.json())

        # Results should be consistent
        first_response = responses[0]
        for response in responses[1:]:
            assert response["total"] == first_response["total"]
            assert len(response["data"]) == len(first_response["data"])
            assert response["page"] == first_response["page"]
            assert response["page_size"] == first_response["page_size"]

    def test_pagination_metadata(self, pagination_framework):
        """Test pagination metadata accuracy."""
        response = pagination_framework.client.get(
            "/api/v1/zones/",
            params={
                "greenhouse_id": pagination_framework.test_greenhouse_id,
                "page": 2,
                "page_size": 10,
            },
            headers=pagination_framework.headers,
        )

        assert response.status_code == 200
        data = response.json()

        # Verify metadata structure
        assert "data" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data

        # Verify metadata accuracy
        assert data["page"] == 2
        assert data["page_size"] == 10
        assert len(data["data"]) <= data["page_size"]
        assert data["total"] >= len(data["data"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
