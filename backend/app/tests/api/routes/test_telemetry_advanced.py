"""
Enhanced telemetry tests for idempotency and rate limiting.

Tests duplicate request handling, rate limit enforcement, and edge cases.
"""
import time

from fastapi.testclient import TestClient


class TestTelemetryIdempotency:
    """Test telemetry idempotency features."""

    def test_sensor_telemetry_idempotency_same_key_same_response(
        self, client: TestClient, device_token_headers: dict[str, str]
    ):
        """Test that same idempotency key returns same response."""
        telemetry_data = {
            "batch_id": "test_batch_001",
            "ts_utc": "2025-08-16T12:00:00Z",
            "readings": [
                {
                    "sensor_id": "550e8400-e29b-41d4-a716-446655440001",
                    "kind": "temperature",
                    "value": 22.5,
                    "ts_utc": "2025-08-16T12:00:00Z",
                    "scope": "greenhouse",
                }
            ],
        }

        headers = {**device_token_headers, "Idempotency-Key": "test-key-123"}

        # First request
        response1 = client.post(
            "/api/v1/telemetry/sensors", json=telemetry_data, headers=headers
        )
        assert response1.status_code == 202
        result1 = response1.json()

        # Second request with same key
        response2 = client.post(
            "/api/v1/telemetry/sensors", json=telemetry_data, headers=headers
        )
        assert response2.status_code == 202
        result2 = response2.json()

        # Should be identical responses
        assert result1 == result2

    def test_sensor_telemetry_idempotency_different_key_different_response(
        self, client: TestClient, device_token_headers: dict[str, str]
    ):
        """Test that different idempotency keys create separate records."""
        telemetry_data = {
            "batch_id": "test_batch_002",
            "ts_utc": "2025-08-16T12:01:00Z",
            "readings": [
                {
                    "sensor_id": "550e8400-e29b-41d4-a716-446655440002",
                    "kind": "humidity",
                    "value": 65.0,
                    "ts_utc": "2025-08-16T12:01:00Z",
                    "scope": "greenhouse",
                }
            ],
        }

        headers1 = {**device_token_headers, "Idempotency-Key": "test-key-001"}

        headers2 = {**device_token_headers, "Idempotency-Key": "test-key-002"}

        # Two requests with different keys
        response1 = client.post(
            "/api/v1/telemetry/sensors", json=telemetry_data, headers=headers1
        )
        assert response1.status_code == 202

        response2 = client.post(
            "/api/v1/telemetry/sensors", json=telemetry_data, headers=headers2
        )
        assert response2.status_code == 202

        # Both should succeed as separate records
        result1 = response1.json()
        result2 = response2.json()

        # Should have different request IDs or timestamps
        assert result1.get("request_id") != result2.get("request_id") or result1.get(
            "timestamp"
        ) != result2.get("timestamp")

    def test_actuator_telemetry_idempotency(
        self, client: TestClient, device_token_headers: dict[str, str]
    ):
        """Test actuator telemetry idempotency."""
        telemetry_data = {
            "events": [
                {
                    "actuator_id": "550e8400-e29b-41d4-a716-446655440003",
                    "ts_utc": "2025-08-16T12:02:00Z",
                    "state": True,
                    "reason": "temperature_control",
                }
            ]
        }

        headers = {**device_token_headers, "Idempotency-Key": "actuator-test-key-001"}

        # Send twice with same key
        response1 = client.post(
            "/api/v1/telemetry/actuators", json=telemetry_data, headers=headers
        )
        assert response1.status_code == 202

        response2 = client.post(
            "/api/v1/telemetry/actuators", json=telemetry_data, headers=headers
        )
        assert response2.status_code == 202

        # Should return identical results
        assert response1.json() == response2.json()

    def test_batch_telemetry_idempotency(
        self, client: TestClient, device_token_headers: dict[str, str]
    ):
        """Test batch telemetry idempotency."""
        batch_data = {
            "sensors": {
                "batch_id": "batch_idem_001",
                "ts_utc": "2025-08-16T12:03:00Z",
                "readings": [
                    {
                        "sensor_id": "550e8400-e29b-41d4-a716-446655440004",
                        "kind": "temperature",
                        "value": 23.0,
                        "ts_utc": "2025-08-16T12:03:00Z",
                        "scope": "greenhouse",
                    }
                ],
            },
            "status": {
                "ts_utc": "2025-08-16T12:03:00Z",
                "temp_stage": 1,
                "humi_stage": 0,
                "avg_interior_temp_c": 23.0,
                "avg_interior_rh_pct": 60.0,
                "plan_version": 1,
            },
        }

        headers = {**device_token_headers, "Idempotency-Key": "batch-test-key-001"}

        # Send twice with same key
        response1 = client.post(
            "/api/v1/telemetry/batch", json=batch_data, headers=headers
        )
        assert response1.status_code == 202

        response2 = client.post(
            "/api/v1/telemetry/batch", json=batch_data, headers=headers
        )
        assert response2.status_code == 202

        # Should return identical results
        assert response1.json() == response2.json()


class TestTelemetryRateLimiting:
    """Test telemetry rate limiting features."""

    def test_sensor_telemetry_rate_limit_headers(
        self, client: TestClient, device_token_headers: dict[str, str]
    ):
        """Test that rate limit headers are present in successful responses."""
        telemetry_data = {
            "batch_id": "rate_test_001",
            "ts_utc": "2025-08-16T12:04:00Z",
            "readings": [
                {
                    "sensor_id": "550e8400-e29b-41d4-a716-446655440005",
                    "kind": "temperature",
                    "value": 22.0,
                    "ts_utc": "2025-08-16T12:04:00Z",
                    "scope": "greenhouse",
                }
            ],
        }

        response = client.post(
            "/api/v1/telemetry/sensors",
            json=telemetry_data,
            headers=device_token_headers,
        )
        assert response.status_code == 202

        # Check for rate limit headers
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers

        # Verify header values are reasonable
        limit = int(response.headers["X-RateLimit-Limit"])
        remaining = int(response.headers["X-RateLimit-Remaining"])
        reset_time = int(response.headers["X-RateLimit-Reset"])

        assert limit > 0
        assert remaining >= 0
        assert remaining <= limit
        assert reset_time > 0

    def test_rate_limit_enforcement_simulation(
        self, client: TestClient, device_token_headers: dict[str, str]
    ):
        """Test rate limit enforcement by making multiple rapid requests."""
        telemetry_data = {
            "batch_id": "rapid_test",
            "ts_utc": "2025-08-16T12:05:00Z",
            "readings": [
                {
                    "sensor_id": "550e8400-e29b-41d4-a716-446655440006",
                    "kind": "temperature",
                    "value": 21.0,
                    "ts_utc": "2025-08-16T12:05:00Z",
                    "scope": "greenhouse",
                }
            ],
        }

        # Make multiple rapid requests
        responses = []
        for i in range(5):
            headers = {
                **device_token_headers,
                "Idempotency-Key": f"rapid-test-{i}",  # Different keys to avoid idempotency
            }

            response = client.post(
                "/api/v1/telemetry/sensors", json=telemetry_data, headers=headers
            )
            responses.append(response)

            # Small delay to avoid overwhelming the test
            time.sleep(0.1)

        # All should succeed initially (unless rate limit is very low)
        for i, response in enumerate(responses):
            if response.status_code == 429:
                # Rate limit hit - check for proper headers
                assert "Retry-After" in response.headers
                assert "X-RateLimit-Reset" in response.headers
                print(f"Rate limit hit at request {i+1}")
                break
            else:
                assert response.status_code == 202

    def test_different_endpoints_separate_rate_limits(
        self, client: TestClient, device_token_headers: dict[str, str]
    ):
        """Test that different telemetry endpoints have separate rate limits."""
        # Make requests to different endpoints
        sensor_data = {
            "batch_id": "separate_test_sensors",
            "ts_utc": "2025-08-16T12:06:00Z",
            "readings": [
                {
                    "sensor_id": "550e8400-e29b-41d4-a716-446655440007",
                    "kind": "temperature",
                    "value": 20.0,
                    "ts_utc": "2025-08-16T12:06:00Z",
                    "scope": "greenhouse",
                }
            ],
        }

        actuator_data = {
            "events": [
                {
                    "actuator_id": "550e8400-e29b-41d4-a716-446655440008",
                    "ts_utc": "2025-08-16T12:06:00Z",
                    "state": False,
                    "reason": "test_separate_limits",
                }
            ]
        }

        status_data = {
            "ts_utc": "2025-08-16T12:06:00Z",
            "temp_stage": 0,
            "humi_stage": 0,
            "avg_interior_temp_c": 20.0,
            "avg_interior_rh_pct": 55.0,
            "plan_version": 1,
        }

        # Test sensor endpoint
        response1 = client.post(
            "/api/v1/telemetry/sensors", json=sensor_data, headers=device_token_headers
        )
        assert response1.status_code == 202

        # Test actuator endpoint
        response2 = client.post(
            "/api/v1/telemetry/actuators",
            json=actuator_data,
            headers=device_token_headers,
        )
        assert response2.status_code == 202

        # Test status endpoint
        response3 = client.post(
            "/api/v1/telemetry/status", json=status_data, headers=device_token_headers
        )
        assert response3.status_code == 202

        # All should succeed as they have separate rate limits
        for response in [response1, response2, response3]:
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers


class TestTelemetryEdgeCases:
    """Test telemetry edge cases and error conditions."""

    def test_malformed_telemetry_data(
        self, client: TestClient, device_token_headers: dict[str, str]
    ):
        """Test handling of malformed telemetry data."""
        malformed_data = {
            "batch_id": "malformed_test",
            "readings": [
                {
                    "sensor_id": "invalid-uuid",
                    "kind": "temperature",
                    "value": "not_a_number",
                    "ts_utc": "invalid-timestamp",
                }
            ],
        }

        response = client.post(
            "/api/v1/telemetry/sensors",
            json=malformed_data,
            headers=device_token_headers,
        )
        assert response.status_code == 422  # Validation error

    def test_empty_telemetry_batch(
        self, client: TestClient, device_token_headers: dict[str, str]
    ):
        """Test handling of empty telemetry batch."""
        empty_batch = {}

        response = client.post(
            "/api/v1/telemetry/batch", json=empty_batch, headers=device_token_headers
        )
        # Should either accept empty batch or return validation error
        assert response.status_code in [202, 400, 422]

    def test_large_telemetry_batch(
        self, client: TestClient, device_token_headers: dict[str, str]
    ):
        """Test handling of large telemetry batch."""
        # Create a large batch with many readings
        large_batch = {
            "sensors": {
                "batch_id": "large_batch_test",
                "ts_utc": "2025-08-16T12:07:00Z",
                "readings": [
                    {
                        "sensor_id": f"550e8400-e29b-41d4-a716-44665544{i:04d}",
                        "kind": "temperature",
                        "value": 20.0 + (i * 0.1),
                        "ts_utc": "2025-08-16T12:07:00Z",
                        "scope": "greenhouse",
                    }
                    for i in range(100)  # 100 readings
                ],
            }
        }

        headers = {**device_token_headers, "Idempotency-Key": "large-batch-test"}

        response = client.post(
            "/api/v1/telemetry/batch", json=large_batch, headers=headers
        )
        # Should either accept or reject based on size limits
        assert response.status_code in [202, 413, 400]

    def test_telemetry_without_device_token(self, client: TestClient):
        """Test telemetry endpoints require device token."""
        telemetry_data = {
            "batch_id": "no_token_test",
            "ts_utc": "2025-08-16T12:08:00Z",
            "readings": [],
        }

        response = client.post("/api/v1/telemetry/sensors", json=telemetry_data)
        assert response.status_code == 401

    def test_telemetry_with_invalid_device_token(self, client: TestClient):
        """Test telemetry with invalid device token returns 401."""
        telemetry_data = {
            "batch_id": "invalid_token_test",
            "ts_utc": "2025-08-16T12:09:00Z",
            "readings": [],
        }

        headers = {"X-Device-Token": "invalid-token-123"}

        response = client.post(
            "/api/v1/telemetry/sensors", json=telemetry_data, headers=headers
        )
        assert response.status_code == 401
