"""
Input Validation and Edge Case Testing

This module provides comprehensive testing of input validation,
boundary conditions, and edge cases across all API endpoints.

Focuses on:
- Field validation boundaries (min/max values, lengths)
- Invalid input types and formats
- SQL injection protection
- XSS prevention
- Unicode and special character handling
- Null/empty value handling
- Malformed request payloads
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.api.deps import get_db
from app.main import app
from app.models import User


class InputValidationTester:
    """Framework for testing input validation and edge cases."""

    def __init__(self):
        self.client = TestClient(app)
        self.test_db_engine = None
        self.test_user_id = None
        self.test_headers = {}

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
                email="validation@example.com",
                full_name="Validation Test User",
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
            data={"username": "validation@example.com", "password": "testpass123"},
        )
        if response.status_code == 200:
            token = response.json()["access_token"]
            self.test_headers = {"Authorization": f"Bearer {token}"}

    def teardown(self):
        """Clean up test resources."""
        app.dependency_overrides.clear()
        if self.test_db_engine:
            self.test_db_engine.dispose()


class TestFieldValidationBoundaries:
    """Test field validation boundaries and constraints."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = InputValidationTester()
        self.tester.setup_test_database()
        self.tester.create_test_user()
        yield
        self.tester.teardown()

    def test_greenhouse_title_length_boundaries(self):
        """Test greenhouse title length validation."""

        test_cases = [
            {"title": "", "expected_status": 422, "case": "empty_string"},
            {"title": "a", "expected_status": 201, "case": "minimum_length"},
            {"title": "a" * 200, "expected_status": 201, "case": "maximum_length"},
            {"title": "a" * 201, "expected_status": 422, "case": "exceeds_maximum"},
            {"title": "  ", "expected_status": 422, "case": "whitespace_only"},
            {"title": None, "expected_status": 422, "case": "null_value"},
        ]

        for case in test_cases:
            data = {"title": case["title"], "latitude": 37.7749, "longitude": -122.4194}

            # Handle None case
            if case["title"] is None:
                del data["title"]

            response = self.tester.client.post(
                "/api/v1/greenhouses/", json=data, headers=self.tester.test_headers
            )

            assert (
                response.status_code == case["expected_status"]
            ), f"Failed for case {case['case']}: expected {case['expected_status']}, got {response.status_code}"

    def test_coordinate_validation_boundaries(self):
        """Test latitude/longitude validation boundaries."""

        coordinate_test_cases = [
            # Latitude tests
            {"lat": -90.0, "lng": 0, "expected": 201, "case": "min_latitude"},
            {"lat": 90.0, "lng": 0, "expected": 201, "case": "max_latitude"},
            {"lat": -90.1, "lng": 0, "expected": 422, "case": "below_min_latitude"},
            {"lat": 90.1, "lng": 0, "expected": 422, "case": "above_max_latitude"},
            # Longitude tests
            {"lat": 0, "lng": -180.0, "expected": 201, "case": "min_longitude"},
            {"lat": 0, "lng": 180.0, "expected": 201, "case": "max_longitude"},
            {"lat": 0, "lng": -180.1, "expected": 422, "case": "below_min_longitude"},
            {"lat": 0, "lng": 180.1, "expected": 422, "case": "above_max_longitude"},
            # Edge cases
            {
                "lat": "invalid",
                "lng": 0,
                "expected": 422,
                "case": "non_numeric_latitude",
            },
            {
                "lat": 0,
                "lng": "invalid",
                "expected": 422,
                "case": "non_numeric_longitude",
            },
            {"lat": None, "lng": 0, "expected": 422, "case": "null_latitude"},
            {"lat": 0, "lng": None, "expected": 422, "case": "null_longitude"},
        ]

        for case in coordinate_test_cases:
            data = {
                "title": f"Test Greenhouse {case['case']}",
                "latitude": case["lat"],
                "longitude": case["lng"],
            }

            response = self.tester.client.post(
                "/api/v1/greenhouses/", json=data, headers=self.tester.test_headers
            )

            assert (
                response.status_code == case["expected"]
            ), f"Failed for {case['case']}: expected {case['expected']}, got {response.status_code}"

    def test_zone_number_validation(self):
        """Test zone number validation boundaries."""

        # Create test greenhouse first
        gh_data = {
            "title": "Zone Validation Test",
            "latitude": 37.7749,
            "longitude": -122.4194,
        }

        gh_response = self.tester.client.post(
            "/api/v1/greenhouses/", json=gh_data, headers=self.tester.test_headers
        )
        greenhouse_id = gh_response.json()["id"]

        zone_test_cases = [
            {"zone_number": 1, "expected": 201, "case": "minimum_valid"},
            {"zone_number": 999, "expected": 201, "case": "large_valid"},
            {"zone_number": 0, "expected": 422, "case": "zero_invalid"},
            {"zone_number": -1, "expected": 422, "case": "negative_invalid"},
            {"zone_number": "invalid", "expected": 422, "case": "non_numeric"},
            {"zone_number": None, "expected": 422, "case": "null_value"},
            {"zone_number": 1.5, "expected": 422, "case": "decimal_invalid"},
        ]

        for case in zone_test_cases:
            data = {
                "greenhouse_id": greenhouse_id,
                "zone_number": case["zone_number"],
                "location": "N",
                "is_active": True,
            }

            response = self.tester.client.post(
                "/api/v1/zones/", json=data, headers=self.tester.test_headers
            )

            assert (
                response.status_code == case["expected"]
            ), f"Failed for {case['case']}: expected {case['expected']}, got {response.status_code}"


class TestSecurityInputValidation:
    """Test security-related input validation."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = InputValidationTester()
        self.tester.setup_test_database()
        self.tester.create_test_user()
        yield
        self.tester.teardown()

    def test_sql_injection_protection(self):
        """Test protection against SQL injection attempts."""

        sql_injection_payloads = [
            "'; DROP TABLE greenhouse; --",
            "' OR '1'='1",
            "'; DELETE FROM greenhouse WHERE 1=1; --",
            "' UNION SELECT * FROM user; --",
            '"; DROP TABLE greenhouse; --',
            "1' OR 1=1#",
            "1'; TRUNCATE TABLE greenhouse; --",
        ]

        for payload in sql_injection_payloads:
            # Test in greenhouse title
            data = {"title": payload, "latitude": 37.7749, "longitude": -122.4194}

            response = self.tester.client.post(
                "/api/v1/greenhouses/", json=data, headers=self.tester.test_headers
            )

            # Should either reject (422) or accept but escape properly (201)
            assert response.status_code in [201, 422]

            # If accepted, verify the payload was escaped/handled safely
            if response.status_code == 201:
                created_id = response.json()["id"]
                get_response = self.tester.client.get(
                    f"/api/v1/greenhouses/{created_id}",
                    headers=self.tester.test_headers,
                )

                # Title should be stored safely (not executed)
                assert get_response.status_code == 200
                stored_title = get_response.json()["title"]
                assert payload in stored_title  # Should be stored as-is, not executed

    def test_xss_protection(self):
        """Test protection against XSS attempts."""

        xss_payloads = [
            "<script>alert('xss')</script>",
            "<img src=x onerror=alert('xss')>",
            "javascript:alert('xss')",
            "<svg onload=alert('xss')>",
            "<iframe src='javascript:alert(`xss`)'></iframe>",
            "';alert(String.fromCharCode(88,83,83))//';alert(String.fromCharCode(88,83,83))//",
            "\"><script>alert('xss')</script>",
            "<body onload=alert('xss')>",
        ]

        for payload in xss_payloads:
            data = {
                "title": payload,
                "description": f"Description with {payload}",
                "latitude": 37.7749,
                "longitude": -122.4194,
            }

            response = self.tester.client.post(
                "/api/v1/greenhouses/", json=data, headers=self.tester.test_headers
            )

            # Should handle gracefully
            assert response.status_code in [201, 422]

            if response.status_code == 201:
                created_id = response.json()["id"]
                get_response = self.tester.client.get(
                    f"/api/v1/greenhouses/{created_id}",
                    headers=self.tester.test_headers,
                )

                # Should not execute scripts - content should be escaped
                assert get_response.status_code == 200
                response_data = get_response.json()

                # Raw payload should be stored/returned safely
                assert (
                    payload in response_data["title"]
                    or payload in response_data["description"]
                )

    def test_unicode_and_special_characters(self):
        """Test handling of Unicode and special characters."""

        unicode_test_cases = [
            {"title": "Тест", "case": "cyrillic"},
            {"title": "测试", "case": "chinese"},
            {"title": "テスト", "case": "japanese"},
            {"title": "🌱🏡", "case": "emojis"},
            {"title": "Café & Résumé", "case": "accented_chars"},
            {"title": "Special: !@#$%^&*()", "case": "special_symbols"},
            {"title": "Newline\nTest", "case": "newline"},
            {"title": "Tab\tTest", "case": "tab"},
            {"title": 'Quote"Test', "case": "double_quote"},
            {"title": "Quote'Test", "case": "single_quote"},
            {"title": "Backslash\\Test", "case": "backslash"},
        ]

        for case in unicode_test_cases:
            data = {"title": case["title"], "latitude": 37.7749, "longitude": -122.4194}

            response = self.tester.client.post(
                "/api/v1/greenhouses/", json=data, headers=self.tester.test_headers
            )

            # Should handle all Unicode properly
            assert (
                response.status_code == 201
            ), f"Failed to handle {case['case']}: {case['title']}"

            # Verify storage integrity
            created_id = response.json()["id"]
            get_response = self.tester.client.get(
                f"/api/v1/greenhouses/{created_id}", headers=self.tester.test_headers
            )

            assert get_response.status_code == 200
            assert get_response.json()["title"] == case["title"]


class TestMalformedRequestHandling:
    """Test handling of malformed requests and payloads."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = InputValidationTester()
        self.tester.setup_test_database()
        self.tester.create_test_user()
        yield
        self.tester.teardown()

    def test_invalid_json_payloads(self):
        """Test handling of invalid JSON payloads."""

        invalid_json_cases = [
            '{"title": "Test"',  # Missing closing brace
            '{"title": "Test",}',  # Trailing comma
            '{title: "Test"}',  # Unquoted key
            '{"title": "Test", "latitude": }',  # Missing value
            '{"title": undefined}',  # Invalid value
            "",  # Empty payload
            "not json at all",  # Not JSON
            '{"title": "Test", "latitude": NaN}',  # Invalid number
        ]

        for invalid_json in invalid_json_cases:
            response = self.tester.client.post(
                "/api/v1/greenhouses/",
                content=invalid_json,
                headers={
                    **self.tester.test_headers,
                    "Content-Type": "application/json",
                },
            )

            # Should return 422 for malformed JSON
            assert response.status_code == 422

    def test_missing_required_fields(self):
        """Test handling of requests with missing required fields."""

        # Test missing title
        response = self.tester.client.post(
            "/api/v1/greenhouses/",
            json={"latitude": 37.7749, "longitude": -122.4194},
            headers=self.tester.test_headers,
        )
        assert response.status_code == 422

        # Test missing coordinates
        response = self.tester.client.post(
            "/api/v1/greenhouses/",
            json={"title": "Test Greenhouse"},
            headers=self.tester.test_headers,
        )
        assert response.status_code == 422

        # Test completely empty payload
        response = self.tester.client.post(
            "/api/v1/greenhouses/", json={}, headers=self.tester.test_headers
        )
        assert response.status_code == 422

    def test_extra_unexpected_fields(self):
        """Test handling of requests with extra unexpected fields."""

        data_with_extra_fields = {
            "title": "Test Greenhouse",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "unexpected_field": "should_be_ignored",
            "another_extra": 12345,
            "nested_extra": {"key": "value"},
        }

        response = self.tester.client.post(
            "/api/v1/greenhouses/",
            json=data_with_extra_fields,
            headers=self.tester.test_headers,
        )

        # Should either accept (ignoring extra fields) or reject
        assert response.status_code in [201, 422]

        if response.status_code == 201:
            # Verify extra fields were ignored
            created_id = response.json()["id"]
            get_response = self.tester.client.get(
                f"/api/v1/greenhouses/{created_id}", headers=self.tester.test_headers
            )

            greenhouse_data = get_response.json()
            assert "unexpected_field" not in greenhouse_data
            assert "another_extra" not in greenhouse_data
            assert "nested_extra" not in greenhouse_data

    def test_invalid_content_types(self):
        """Test handling of requests with invalid content types."""

        valid_data = {
            "title": "Test Greenhouse",
            "latitude": 37.7749,
            "longitude": -122.4194,
        }

        # Test with wrong content type
        response = self.tester.client.post(
            "/api/v1/greenhouses/",
            content=json.dumps(valid_data),
            headers={**self.tester.test_headers, "Content-Type": "text/plain"},
        )

        # Should reject non-JSON content type
        assert response.status_code == 422

        # Test with no content type
        response = self.tester.client.post(
            "/api/v1/greenhouses/",
            content=json.dumps(valid_data),
            headers=self.tester.test_headers,  # No Content-Type header
        )

        # Behavior may vary - should handle gracefully
        assert response.status_code in [201, 422]


class TestPaginationEdgeCases:
    """Test pagination edge cases and boundary conditions."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.tester = InputValidationTester()
        self.tester.setup_test_database()
        self.tester.create_test_user()
        yield
        self.tester.teardown()

    def test_pagination_boundary_values(self):
        """Test pagination with boundary values."""

        # Create some test data
        for i in range(5):
            data = {
                "title": f"Pagination Test {i}",
                "latitude": 37.7749 + (i * 0.001),
                "longitude": -122.4194 + (i * 0.001),
            }
            self.tester.client.post(
                "/api/v1/greenhouses/", json=data, headers=self.tester.test_headers
            )

        pagination_test_cases = [
            {"page": 0, "page_size": 10, "expected_status": 422, "case": "zero_page"},
            {
                "page": -1,
                "page_size": 10,
                "expected_status": 422,
                "case": "negative_page",
            },
            {
                "page": 1,
                "page_size": 0,
                "expected_status": 422,
                "case": "zero_page_size",
            },
            {
                "page": 1,
                "page_size": -1,
                "expected_status": 422,
                "case": "negative_page_size",
            },
            {
                "page": 1,
                "page_size": 1000,
                "expected_status": 200,
                "case": "large_page_size",
            },
            {
                "page": 100,
                "page_size": 10,
                "expected_status": 200,
                "case": "page_beyond_data",
            },
            {
                "page": "invalid",
                "page_size": 10,
                "expected_status": 422,
                "case": "non_numeric_page",
            },
            {
                "page": 1,
                "page_size": "invalid",
                "expected_status": 422,
                "case": "non_numeric_page_size",
            },
        ]

        for case in pagination_test_cases:
            response = self.tester.client.get(
                "/api/v1/greenhouses/",
                params={"page": case["page"], "page_size": case["page_size"]},
                headers=self.tester.test_headers,
            )

            assert (
                response.status_code == case["expected_status"]
            ), f"Failed for {case['case']}: expected {case['expected_status']}, got {response.status_code}"

            if response.status_code == 200:
                data = response.json()

                # Verify pagination structure
                assert "data" in data
                assert "page" in data
                assert "page_size" in data
                assert "total" in data

                # For page beyond data, should return empty results
                if case["case"] == "page_beyond_data":
                    assert len(data["data"]) == 0
                    assert data["total"] == 5  # Still shows total count


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
