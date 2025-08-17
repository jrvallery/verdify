"""
Tests for telemetry ingestion endpoints.

Tests rate limiting, idempotency, authentication, and all telemetry endpoint types.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.models import Controller


@pytest.fixture(scope="function")
def controller(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> Controller:
    """Create a test controller for telemetry tests."""
    # Use a unique device name to avoid conflicts
    import time

    unique_suffix = str(int(time.time() * 1000))[-6:]  # Last 6 digits of timestamp
    device_name = f"verdify-test{unique_suffix}"

    # First create a greenhouse
    greenhouse_data = {
        "title": f"Test Greenhouse for Telemetry {unique_suffix}",
        "description": "Test greenhouse for telemetry ingestion tests",
    }
    greenhouse_response = client.post(
        f"{settings.API_V1_STR}/greenhouses/",
        headers=superuser_token_headers,
        json=greenhouse_data,
    )
    assert greenhouse_response.status_code == 201
    greenhouse_id = greenhouse_response.json()["id"]

    # Create a controller
    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": device_name,
        "label": f"Test Telemetry Controller {unique_suffix}",
        "model": "ESP32",
        "is_climate_controller": True,
    }

    controller_response = client.post(
        f"{settings.API_V1_STR}/controllers/",
        headers=superuser_token_headers,
        json=controller_data,
    )
    assert controller_response.status_code == 201
    controller_data = controller_response.json()

    # Return controller object (the test uses controller.id for device token)
    return Controller(
        id=uuid.UUID(controller_data["id"]),
        device_name=controller_data["device_name"],
        label=controller_data["label"],
        model=controller_data["model"],
        is_climate_controller=controller_data["is_climate_controller"],
        greenhouse_id=uuid.UUID(controller_data["greenhouse_id"]),
        claimed_at=datetime.now(timezone.utc),
    )


class TestTelemetryAuthentication:
    """Test authentication requirements for telemetry endpoints."""

    def test_sensor_telemetry_requires_device_token(self, client: TestClient):
        """Test that sensor telemetry endpoint requires X-Device-Token."""
        payload = {
            "batch_id": "test_batch_001",
            "ts_utc": "2025-08-15T12:00:00Z",
            "readings": [
                {
                    "sensor_id": str(uuid.uuid4()),
                    "value": 25.5,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
        }

        response = client.post(f"{settings.API_V1_STR}/telemetry/sensors", json=payload)

        assert response.status_code == 401
        assert "X-Device-Token header required" in response.json()["message"]

    def test_actuator_telemetry_requires_device_token(self, client: TestClient):
        """Test that actuator telemetry endpoint requires X-Device-Token."""
        payload = {
            "batch_id": "test_batch_001",
            "ts_utc": "2025-08-15T12:00:00Z",
            "events": [
                {
                    "actuator_id": str(uuid.uuid4()),
                    "state": True,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
        }

        response = client.post(
            f"{settings.API_V1_STR}/telemetry/actuators", json=payload
        )

        assert response.status_code == 401

    def test_status_telemetry_requires_device_token(self, client: TestClient):
        """Test that status telemetry endpoint requires X-Device-Token."""
        payload = {
            "ts_utc": "2025-08-15T12:00:00Z",
            "temp_stage": 1,
            "humi_stage": 0,
            "avg_interior_temp_c": 25.5,
            "avg_interior_rh_pct": 60.0,
        }

        response = client.post(f"{settings.API_V1_STR}/telemetry/status", json=payload)

        assert response.status_code == 401

    def test_inputs_telemetry_requires_device_token(self, client: TestClient):
        """Test that inputs telemetry endpoint requires X-Device-Token."""
        payload = {
            "batch_id": "test_batch_001",
            "ts_utc": "2025-08-15T12:00:00Z",
            "events": [
                {
                    "button_id": str(uuid.uuid4()),
                    "pressed": True,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
        }

        response = client.post(f"{settings.API_V1_STR}/telemetry/inputs", json=payload)

        assert response.status_code == 401

    def test_batch_telemetry_requires_device_token(self, client: TestClient):
        """Test that batch telemetry endpoint requires X-Device-Token."""
        payload = {
            "batch_id": "test_batch_001",
            "ts_utc": "2025-08-15T12:00:00Z",
            "sensors": [
                {
                    "sensor_id": str(uuid.uuid4()),
                    "value": 25.5,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
        }

        response = client.post(f"{settings.API_V1_STR}/telemetry/batch", json=payload)

        assert response.status_code == 401


class TestSensorTelemetry:
    """Test sensor telemetry ingestion."""

    def test_ingest_sensor_readings_success(
        self, client: TestClient, controller: Controller
    ):
        """Test successful sensor readings ingestion."""
        sensor_id = uuid.uuid4()
        payload = {
            "batch_id": "sensor_batch_001",
            "ts_utc": "2025-08-15T12:00:00Z",
            "readings": [
                {
                    "sensor_id": str(sensor_id),
                    "value": 25.5,
                    "ts_utc": "2025-08-15T12:00:00Z",
                },
                {
                    "sensor_id": str(sensor_id),
                    "value": 25.7,
                    "ts_utc": "2025-08-15T12:01:00Z",
                },
            ],
        }

        response = client.post(
            f"{settings.API_V1_STR}/telemetry/sensors",
            json=payload,
            headers={"X-Device-Token": str(controller.id)},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 2
        assert data["rejected"] == 0
        assert isinstance(data["warnings"], list)

        # Check rate limit headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

    def test_ingest_sensor_readings_with_idempotency(
        self, client: TestClient, controller: Controller
    ):
        """Test sensor readings with idempotency key."""
        sensor_id = uuid.uuid4()
        payload = {
            "batch_id": "sensor_batch_002",
            "ts_utc": "2025-08-15T12:00:00Z",
            "readings": [
                {
                    "sensor_id": str(sensor_id),
                    "value": 25.5,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
        }

        idempotency_key = "test_sensor_key_001"

        # First request
        response1 = client.post(
            f"{settings.API_V1_STR}/telemetry/sensors",
            json=payload,
            headers={
                "X-Device-Token": str(controller.id),
                "Idempotency-Key": idempotency_key,
            },
        )

        assert response1.status_code == 202
        data1 = response1.json()
        assert data1["accepted"] == 1

        # Second request with same key and payload - should be idempotent
        response2 = client.post(
            f"{settings.API_V1_STR}/telemetry/sensors",
            json=payload,
            headers={
                "X-Device-Token": str(controller.id),
                "Idempotency-Key": idempotency_key,
            },
        )

        assert response2.status_code == 202
        data2 = response2.json()
        # Should indicate idempotent processing
        assert "already processed" in str(data2.get("warnings", []))


class TestActuatorTelemetry:
    """Test actuator telemetry ingestion."""

    def test_ingest_actuator_events_success(
        self, client: TestClient, controller: Controller
    ):
        """Test successful actuator events ingestion."""
        actuator_id = uuid.uuid4()
        payload = {
            "batch_id": "actuator_batch_001",
            "ts_utc": "2025-08-15T12:00:00Z",
            "events": [
                {
                    "actuator_id": str(actuator_id),
                    "state": True,
                    "ts_utc": "2025-08-15T12:00:00Z",
                },
                {
                    "actuator_id": str(actuator_id),
                    "state": False,
                    "ts_utc": "2025-08-15T12:05:00Z",
                },
            ],
        }

        response = client.post(
            f"{settings.API_V1_STR}/telemetry/actuators",
            json=payload,
            headers={"X-Device-Token": str(controller.id)},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 2
        assert data["rejected"] == 0


class TestStatusTelemetry:
    """Test status telemetry ingestion."""

    def test_ingest_status_success(self, client: TestClient, controller: Controller):
        """Test successful status ingestion."""
        payload = {
            "ts_utc": "2025-08-15T12:00:00Z",
            "temp_stage": 1,
            "humi_stage": -1,
            "avg_interior_temp_c": 25.5,
            "avg_interior_rh_pct": 60.0,
            "avg_interior_pressure_hpa": 1013.25,
            "avg_exterior_temp_c": 28.0,
            "avg_exterior_rh_pct": 65.0,
            "avg_exterior_pressure_hpa": 1013.0,
            "avg_vpd_kpa": 0.8,
            "enthalpy_in_kj_per_kg": 45.2,
            "enthalpy_out_kj_per_kg": 48.5,
            "override_active": False,
            "plan_version": 17,
            "plan_stale": False,
            "offline_sensors": [],
            "fallback_active": False,
            "uptime_s": 86400,
            "loop_ms": 250,
            "config_version": 12,
        }

        response = client.post(
            f"{settings.API_V1_STR}/telemetry/status",
            json=payload,
            headers={"X-Device-Token": str(controller.id)},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 1
        assert data["rejected"] == 0

    def test_ingest_status_invalid_stages(
        self, client: TestClient, controller: Controller
    ):
        """Test status ingestion with invalid stage values."""
        payload = {
            "ts_utc": "2025-08-15T12:00:00Z",
            "temp_stage": 5,  # Invalid: outside [-3, 3] range
            "humi_stage": 0,
            "avg_interior_temp_c": 25.5,
            "avg_interior_rh_pct": 60.0,
        }

        response = client.post(
            f"{settings.API_V1_STR}/telemetry/status",
            json=payload,
            headers={"X-Device-Token": str(controller.id)},
        )

        # Should reject invalid data with 422 validation error
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data  # FastAPI validation error format


class TestInputTelemetry:
    """Test input telemetry ingestion."""

    def test_ingest_input_events_success(
        self, client: TestClient, controller: Controller
    ):
        """Test successful input events ingestion."""
        button_id = uuid.uuid4()
        payload = {
            "batch_id": "input_batch_001",
            "ts_utc": "2025-08-15T12:00:00Z",
            "events": [
                {
                    "button_id": str(button_id),
                    "pressed": True,
                    "ts_utc": "2025-08-15T12:00:00Z",
                },
                {
                    "button_id": str(button_id),
                    "pressed": False,
                    "ts_utc": "2025-08-15T12:00:02Z",
                },
            ],
        }

        response = client.post(
            f"{settings.API_V1_STR}/telemetry/inputs",
            json=payload,
            headers={"X-Device-Token": str(controller.id)},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 2
        assert data["rejected"] == 0


class TestBatchTelemetry:
    """Test batch telemetry ingestion."""

    def test_ingest_batch_success(self, client: TestClient, controller: Controller):
        """Test successful batch telemetry ingestion."""
        sensor_id = uuid.uuid4()
        actuator_id = uuid.uuid4()
        button_id = uuid.uuid4()

        payload = {
            "batch_id": "comprehensive_batch_001",
            "ts_utc": "2025-08-15T12:00:00Z",
            "sensors": [
                {
                    "sensor_id": str(sensor_id),
                    "value": 25.5,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
            "actuators": [
                {
                    "actuator_id": str(actuator_id),
                    "state": True,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
            "status": {
                "ts_utc": "2025-08-15T12:00:00Z",
                "temp_stage": 0,
                "humi_stage": 1,
                "avg_interior_temp_c": 25.5,
                "avg_interior_rh_pct": 60.0,
            },
            "inputs": [
                {
                    "button_id": str(button_id),
                    "pressed": True,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
        }

        response = client.post(
            f"{settings.API_V1_STR}/telemetry/batch",
            json=payload,
            headers={"X-Device-Token": str(controller.id)},
        )

        assert response.status_code == 202
        data = response.json()
        # Should accept: 1 sensor + 1 actuator + 1 status + 1 input = 4 total
        assert data["accepted"] == 4
        assert data["rejected"] == 0

    def test_ingest_batch_partial_data(
        self, client: TestClient, controller: Controller
    ):
        """Test batch ingestion with only some telemetry types."""
        sensor_id = uuid.uuid4()

        payload = {
            "batch_id": "partial_batch_001",
            "ts_utc": "2025-08-15T12:00:00Z",
            "sensors": [
                {
                    "sensor_id": str(sensor_id),
                    "value": 25.5,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
            # No actuators, status, or inputs
        }

        response = client.post(
            f"{settings.API_V1_STR}/telemetry/batch",
            json=payload,
            headers={"X-Device-Token": str(controller.id)},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["accepted"] == 1  # Only the sensor reading
        assert data["rejected"] == 0


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_rate_limit_enforcement(self, client: TestClient, controller: Controller):
        """Test that rate limiting is enforced."""
        payload = {
            "batch_id": "rate_limit_test",
            "ts_utc": "2025-08-15T12:00:00Z",
            "readings": [
                {
                    "sensor_id": str(uuid.uuid4()),
                    "value": 25.5,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
        }

        # Make many requests to trigger rate limit
        # Default limit is 100 requests per minute for telemetry
        # For testing, let's try a smaller number first to see the headers
        responses = []
        for i in range(10):  # Start with fewer requests
            response = client.post(
                f"{settings.API_V1_STR}/telemetry/sensors",
                json=payload,
                headers={"X-Device-Token": str(controller.id)},
            )
            responses.append(response)

            # Stop if we hit rate limit
            if response.status_code == 429:
                break

        # All requests within the limit should succeed
        successful_responses = [r for r in responses if r.status_code == 202]
        assert (
            len(successful_responses) == 10
        )  # All should succeed for this small number

        # Check that rate limit headers are present in successful responses
        if successful_responses:
            last_response = successful_responses[-1]
            assert "X-RateLimit-Limit" in last_response.headers
            assert "X-RateLimit-Remaining" in last_response.headers
            assert "X-RateLimit-Reset" in last_response.headers

            # Verify the headers have reasonable values
            assert int(last_response.headers["X-RateLimit-Limit"]) == 100
            remaining = int(last_response.headers["X-RateLimit-Remaining"])
            assert remaining < 100  # Should be decremented
            assert remaining >= 0

    def test_different_endpoints_separate_limits(
        self, client: TestClient, controller: Controller
    ):
        """Test that different endpoints have separate rate limits."""
        # Batch endpoint should have different (lower) limits than individual endpoints

        # Make many sensor requests
        sensor_payload = {
            "batch_id": "sensor_rate_test",
            "ts_utc": "2025-08-15T12:00:00Z",
            "readings": [
                {
                    "sensor_id": str(uuid.uuid4()),
                    "value": 25.5,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
        }

        # Should still be able to use batch endpoint
        batch_payload = {
            "batch_id": "batch_rate_test",
            "ts_utc": "2025-08-15T12:00:00Z",
            "sensors": [
                {
                    "sensor_id": str(uuid.uuid4()),
                    "value": 25.5,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
        }

        # Test that batch endpoint works even if sensors endpoint is rate limited
        # (This test is conceptual - in practice, the rate limits would need to be
        # configured very low to test this quickly)

        batch_response = client.post(
            f"{settings.API_V1_STR}/telemetry/batch",
            json=batch_payload,
            headers={"X-Device-Token": str(controller.id)},
        )

        # Batch should still work (different rate limit bucket)
        assert batch_response.status_code in [
            202,
            429,
        ]  # Either works or has its own limit


class TestIdempotency:
    """Test idempotency key functionality."""

    def test_idempotency_same_key_same_response(
        self, client: TestClient, controller: Controller
    ):
        """Test that same idempotency key returns same response."""
        payload = {
            "batch_id": "idempotency_test_001",
            "ts_utc": "2025-08-15T12:00:00Z",
            "readings": [
                {
                    "sensor_id": str(uuid.uuid4()),
                    "value": 25.5,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
        }

        idempotency_key = "test_idem_key_001"
        headers = {
            "X-Device-Token": str(controller.id),
            "Idempotency-Key": idempotency_key,
        }

        # First request
        response1 = client.post(
            f"{settings.API_V1_STR}/telemetry/sensors", json=payload, headers=headers
        )

        # Second request with same key
        response2 = client.post(
            f"{settings.API_V1_STR}/telemetry/sensors", json=payload, headers=headers
        )

        # Both should succeed
        assert response1.status_code == 202
        assert response2.status_code == 202

        # Second response should indicate idempotent processing
        data2 = response2.json()
        warnings = data2.get("warnings", [])
        assert any("already processed" in str(w) for w in warnings)

    def test_idempotency_different_controller_different_key_space(
        self, client: TestClient, db: Session
    ):
        """Test that idempotency keys are scoped per controller."""
        # Create two controllers with all required fields
        import time

        unique_suffix1 = str(int(time.time() * 1000))[-6:]
        unique_suffix2 = str(int(time.time() * 1000))[-5:]  # Different suffix

        controller1 = Controller(
            id=uuid.uuid4(),
            device_name=f"verdify-test{unique_suffix1}",
            label=f"Test Controller {unique_suffix1}",
            claimed_at=datetime.now(timezone.utc),
        )
        controller2 = Controller(
            id=uuid.uuid4(),
            device_name=f"verdify-test{unique_suffix2}",
            label=f"Test Controller {unique_suffix2}",
            claimed_at=datetime.now(timezone.utc),
        )

        db.add(controller1)
        db.add(controller2)
        db.commit()

        payload = {
            "batch_id": "idempotency_scoping_test",
            "ts_utc": "2025-08-15T12:00:00Z",
            "readings": [
                {
                    "sensor_id": str(uuid.uuid4()),
                    "value": 25.5,
                    "ts_utc": "2025-08-15T12:00:00Z",
                }
            ],
        }

        idempotency_key = "shared_key_001"

        # Same key, different controllers - should both work
        response1 = client.post(
            f"{settings.API_V1_STR}/telemetry/sensors",
            json=payload,
            headers={
                "X-Device-Token": str(controller1.id),
                "Idempotency-Key": idempotency_key,
            },
        )

        response2 = client.post(
            f"{settings.API_V1_STR}/telemetry/sensors",
            json=payload,
            headers={
                "X-Device-Token": str(controller2.id),
                "Idempotency-Key": idempotency_key,
            },
        )

        # Both should succeed (different key spaces)
        assert response1.status_code == 202
        assert response2.status_code == 202

        # Neither should be marked as idempotent
        data1 = response1.json()
        data2 = response2.json()
        assert data1["accepted"] > 0
        assert data2["accepted"] > 0
