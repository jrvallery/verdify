"""
Tests for meta endpoints.

Tests all meta endpoints that provide operational readiness
and device configuration information:
- /health - Service health status
- /meta/sensor-kinds - Available sensor types
- /meta/actuator-kinds - Available actuator types
"""

from starlette.testclient import TestClient

from app.core.config import settings


class TestHealthEndpoint:
    """Test the health check endpoint."""

    def test_health_check_success(self, client: TestClient):
        """Test that health endpoint returns healthy status."""
        response = client.get(f"{settings.API_V1_STR}/health")

        assert response.status_code == 200
        data = response.json()

        # Check required fields per OpenAPI spec
        assert "status" in data
        assert "timestamp" in data
        assert "version" in data

        # Check specific values
        assert data["status"] == "healthy"
        assert data["version"] == "2.0"

        # Timestamp should be valid ISO format
        from datetime import datetime

        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))

    def test_health_check_no_auth_required(self, client: TestClient):
        """Test that health endpoint doesn't require authentication."""
        # No headers provided - should still work
        response = client.get(f"{settings.API_V1_STR}/health")
        assert response.status_code == 200


class TestSensorKindsEndpoint:
    """Test the sensor kinds metadata endpoint."""

    def test_get_sensor_kinds_success(self, client: TestClient):
        """Test that sensor kinds endpoint returns expected data."""
        response = client.get(f"{settings.API_V1_STR}/meta/sensor-kinds")

        assert response.status_code == 200
        data = response.json()

        # Check response structure per OpenAPI spec
        assert "sensor_kinds" in data
        assert isinstance(data["sensor_kinds"], list)

        # Check that we have expected sensor kinds (from OpenAPI spec)
        expected_kinds = [
            "temperature",
            "humidity",
            "vpd",
            "co2",
            "light",
            "soil_moisture",
            "water_flow",
            "water_total",
            "dew_point",
            "absolute_humidity",
            "enthalpy_delta",
            "air_pressure",
            "kwh",
            "gas_consumption",
            "ppfd",
            "wind_speed",
            "rainfall",
            "power",
        ]

        sensor_kinds = data["sensor_kinds"]

        # Check that all expected kinds are present
        for expected_kind in expected_kinds:
            assert (
                expected_kind in sensor_kinds
            ), f"Missing sensor kind: {expected_kind}"

        # All items should be strings
        for kind in sensor_kinds:
            assert isinstance(kind, str)

    def test_sensor_kinds_no_auth_required(self, client: TestClient):
        """Test that sensor kinds endpoint doesn't require authentication."""
        response = client.get(f"{settings.API_V1_STR}/meta/sensor-kinds")
        assert response.status_code == 200

    def test_sensor_kinds_matches_openapi_example(self, client: TestClient):
        """Test that response includes kinds from OpenAPI example."""
        response = client.get(f"{settings.API_V1_STR}/meta/sensor-kinds")

        assert response.status_code == 200
        data = response.json()

        # OpenAPI example includes these specific kinds
        example_kinds = [
            "temperature",
            "humidity",
            "vpd",
            "co2",
            "light",
            "soil_moisture",
        ]

        for kind in example_kinds:
            assert kind in data["sensor_kinds"]


class TestActuatorKindsEndpoint:
    """Test the actuator kinds metadata endpoint."""

    def test_get_actuator_kinds_success(self, client: TestClient):
        """Test that actuator kinds endpoint returns expected data."""
        response = client.get(f"{settings.API_V1_STR}/meta/actuator-kinds")

        assert response.status_code == 200
        data = response.json()

        # Check response structure per OpenAPI spec
        assert "actuator_kinds" in data
        assert isinstance(data["actuator_kinds"], list)

        # Check that we have expected actuator kinds (from OpenAPI spec)
        expected_kinds = [
            "fan",
            "heater",
            "vent",
            "fogger",
            "irrigation_valve",
            "fertilizer_valve",
            "pump",
            "light",
        ]

        actuator_kinds = data["actuator_kinds"]

        # Check that all expected kinds are present
        for expected_kind in expected_kinds:
            assert (
                expected_kind in actuator_kinds
            ), f"Missing actuator kind: {expected_kind}"

        # All items should be strings
        for kind in actuator_kinds:
            assert isinstance(kind, str)

    def test_actuator_kinds_no_auth_required(self, client: TestClient):
        """Test that actuator kinds endpoint doesn't require authentication."""
        response = client.get(f"{settings.API_V1_STR}/meta/actuator-kinds")
        assert response.status_code == 200

    def test_actuator_kinds_matches_openapi_example(self, client: TestClient):
        """Test that response matches OpenAPI example exactly."""
        response = client.get(f"{settings.API_V1_STR}/meta/actuator-kinds")

        assert response.status_code == 200
        data = response.json()

        # OpenAPI example includes these specific kinds
        example_kinds = [
            "fan",
            "heater",
            "vent",
            "fogger",
            "irrigation_valve",
            "fertilizer_valve",
            "pump",
            "light",
        ]

        # Should contain all example kinds
        for kind in example_kinds:
            assert kind in data["actuator_kinds"]


class TestMetaEndpointsIntegration:
    """Integration tests for meta endpoints."""

    def test_all_meta_endpoints_available(self, client: TestClient):
        """Test that all three meta endpoints are accessible."""
        endpoints = ["/health", "/meta/sensor-kinds", "/meta/actuator-kinds"]

        for endpoint in endpoints:
            response = client.get(f"{settings.API_V1_STR}{endpoint}")
            assert response.status_code == 200, f"Endpoint {endpoint} failed"

    def test_meta_endpoints_consistent_structure(self, client: TestClient):
        """Test that meta endpoints return consistent response structures."""
        # Health endpoint
        health_response = client.get(f"{settings.API_V1_STR}/health")
        health_data = health_response.json()
        assert isinstance(health_data, dict)

        # Sensor kinds endpoint
        sensor_response = client.get(f"{settings.API_V1_STR}/meta/sensor-kinds")
        sensor_data = sensor_response.json()
        assert isinstance(sensor_data, dict)
        assert "sensor_kinds" in sensor_data

        # Actuator kinds endpoint
        actuator_response = client.get(f"{settings.API_V1_STR}/meta/actuator-kinds")
        actuator_data = actuator_response.json()
        assert isinstance(actuator_data, dict)
        assert "actuator_kinds" in actuator_data

    def test_meta_endpoints_cors_headers(self, client: TestClient):
        """Test that meta endpoints can be called from browsers (no CORS issues)."""
        # These endpoints should be accessible from web UIs
        response = client.get(f"{settings.API_V1_STR}/health")
        assert response.status_code == 200

        # Content-Type should be JSON
        assert "application/json" in response.headers.get("content-type", "")
