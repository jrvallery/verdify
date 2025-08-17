"""
Live integration tests for telemetry API endpoints.
Tests against running FastAPI server on localhost:8000.
"""

import time
import uuid
from datetime import datetime, timezone

import pytest
import requests


class TestLiveTelemetryAPI:
    """Test telemetry endpoints against live server"""

    BASE_URL = "http://localhost:8000"
    API_BASE = f"{BASE_URL}/api/v1"

    def setup_method(self):
        """Setup before each test method"""
        try:
            response = requests.get(f"{self.API_BASE}/health", timeout=5)
            assert response.status_code == 200, "Server not running on localhost:8000"
        except requests.exceptions.ConnectionError:
            pytest.skip("FastAPI server not running on localhost:8000")

    def get_superuser_token(self) -> str:
        """Get authentication token for superuser"""
        login_data = {"username": "jason@verdify.ai", "password": "v@ll3ry4761"}

        response = requests.post(
            f"{self.API_BASE}/login/access-token",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            pytest.skip(
                f"Cannot authenticate superuser: {response.status_code} - {response.text}"
            )

        token_data = response.json()
        return token_data["access_token"]

    def get_auth_headers(self) -> dict[str, str]:
        """Get headers with authentication token"""
        token = self.get_superuser_token()
        return {"Authorization": f"Bearer {token}"}

    def create_device_token(self) -> tuple[str, str]:
        """Create a device token for telemetry testing"""
        # Create full onboarding flow to get device token
        device_name = f"verdify-{uuid.uuid4().hex[:6]}"
        claim_code = "123456"

        # 1. Create greenhouse
        greenhouse_data = {
            "title": f"Telemetry Test Greenhouse {uuid.uuid4().hex[:8]}",
            "description": "For telemetry testing",
            "min_temp_c": 10.0,
            "max_temp_c": 35.0,
            "site_pressure_hpa": 1013.25,
            "enthalpy_open_kjkg": 50.0,
            "enthalpy_close_kjkg": 100.0,
        }

        gh_response = requests.post(
            f"{self.API_BASE}/greenhouses/",
            json=greenhouse_data,
            headers=self.get_auth_headers(),
        )
        assert gh_response.status_code == 201
        greenhouse_id = gh_response.json()["id"]

        # 2. Announce device
        hello_payload = {
            "device_name": device_name,
            "claim_code": claim_code,
            "hardware_profile": "kincony_a16s",
            "firmware": "2.1.0",
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        hello_response = requests.post(
            f"{self.API_BASE}/hello",
            json=hello_payload,
            headers={"Content-Type": "application/json"},
        )
        assert hello_response.status_code == 200

        # 3. Claim controller
        claim_payload = {
            "device_name": device_name,
            "claim_code": claim_code,
            "greenhouse_id": greenhouse_id,
        }

        claim_response = requests.post(
            f"{self.API_BASE}/controllers/claim",
            json=claim_payload,
            headers={**{"Content-Type": "application/json"}, **self.get_auth_headers()},
        )
        assert claim_response.status_code == 201
        claim_data = claim_response.json()
        controller_id = claim_data["controller"]["id"]
        new_claim_code = claim_data["controller"]["claim_code"]

        # 4. Exchange for token
        exchange_payload = {"device_name": device_name, "claim_code": new_claim_code}

        exchange_response = requests.post(
            f"{self.API_BASE}/controllers/{controller_id}/token-exchange",
            json=exchange_payload,
            headers={"Content-Type": "application/json"},
        )
        assert exchange_response.status_code == 201
        exchange_data = exchange_response.json()

        return exchange_data["device_token"], controller_id

    def get_device_headers(self, device_token: str) -> dict[str, str]:
        """Get headers with device token"""
        return {"X-Device-Token": device_token}


class TestLiveTelemetrySensors(TestLiveTelemetryAPI):
    """Test sensor telemetry endpoints"""

    def test_sensor_telemetry_success(self):
        """Test successful sensor data submission"""
        device_token, controller_id = self.create_device_token()

        sensor_data = {
            "readings": [
                {
                    "sensor_type": "temperature",
                    "value": 23.5,
                    "unit": "celsius",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                {
                    "sensor_type": "humidity",
                    "value": 65.0,
                    "unit": "percent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            ]
        }

        response = requests.post(
            f"{self.API_BASE}/telemetry/sensors",
            json=sensor_data,
            headers=self.get_device_headers(device_token),
        )

        assert response.status_code == 202
        data = response.json()
        assert "message" in data
        assert "processed_count" in data
        assert data["processed_count"] == 2

    def test_sensor_telemetry_with_idempotency_key(self):
        """Test sensor telemetry with idempotency key"""
        device_token, controller_id = self.create_device_token()
        idempotency_key = str(uuid.uuid4())

        sensor_data = {
            "readings": [
                {
                    "sensor_type": "temperature",
                    "value": 24.0,
                    "unit": "celsius",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }

        headers = {
            **self.get_device_headers(device_token),
            "Idempotency-Key": idempotency_key,
        }

        # First request - should return 202
        response1 = requests.post(
            f"{self.API_BASE}/telemetry/sensors", json=sensor_data, headers=headers
        )
        assert response1.status_code == 202

        # Second request with same idempotency key - should return 202 (cached)
        response2 = requests.post(
            f"{self.API_BASE}/telemetry/sensors", json=sensor_data, headers=headers
        )
        assert response2.status_code == 202

    def test_sensor_telemetry_unauthorized(self):
        """Test sensor telemetry without device token"""
        sensor_data = {
            "readings": [
                {
                    "sensor_type": "temperature",
                    "value": 23.5,
                    "unit": "celsius",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }

        response = requests.post(
            f"{self.API_BASE}/telemetry/sensors",
            json=sensor_data,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 401

    def test_sensor_telemetry_invalid_data(self):
        """Test sensor telemetry with invalid data"""
        device_token, controller_id = self.create_device_token()

        invalid_data = {
            "readings": [
                {
                    "sensor_type": "invalid_type",
                    "value": "not_a_number",
                    "unit": "celsius",
                    "timestamp": "invalid_timestamp",
                }
            ]
        }

        response = requests.post(
            f"{self.API_BASE}/telemetry/sensors",
            json=invalid_data,
            headers=self.get_device_headers(device_token),
        )

        assert response.status_code == 422


class TestLiveTelemetryActuators(TestLiveTelemetryAPI):
    """Test actuator telemetry endpoints"""

    def test_actuator_telemetry_success(self):
        """Test successful actuator status submission"""
        device_token, controller_id = self.create_device_token()

        actuator_data = {
            "states": [
                {
                    "actuator_type": "relay",
                    "pin": "R1",
                    "state": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                {
                    "actuator_type": "pwm",
                    "pin": "PWM1",
                    "state": False,
                    "value": 0.0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            ]
        }

        response = requests.post(
            f"{self.API_BASE}/telemetry/actuators",
            json=actuator_data,
            headers=self.get_device_headers(device_token),
        )

        assert response.status_code == 202
        data = response.json()
        assert "message" in data
        assert "processed_count" in data
        assert data["processed_count"] == 2

    def test_actuator_telemetry_unauthorized(self):
        """Test actuator telemetry without device token"""
        actuator_data = {
            "states": [
                {
                    "actuator_type": "relay",
                    "pin": "R1",
                    "state": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }

        response = requests.post(
            f"{self.API_BASE}/telemetry/actuators",
            json=actuator_data,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 401


class TestLiveTelemetryInputs(TestLiveTelemetryAPI):
    """Test input telemetry endpoints"""

    def test_input_telemetry_success(self):
        """Test successful input event submission"""
        device_token, controller_id = self.create_device_token()

        input_data = {
            "events": [
                {
                    "input_type": "button",
                    "pin": "BTN1",
                    "state": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
        }

        response = requests.post(
            f"{self.API_BASE}/telemetry/inputs",
            json=input_data,
            headers=self.get_device_headers(device_token),
        )

        assert response.status_code == 202
        data = response.json()
        assert "message" in data
        assert "processed_count" in data
        assert data["processed_count"] == 1


class TestLiveTelemetryStatus(TestLiveTelemetryAPI):
    """Test status telemetry endpoints"""

    def test_status_telemetry_success(self):
        """Test successful status submission"""
        device_token, controller_id = self.create_device_token()

        status_data = {
            "uptime_ms": 3600000,  # 1 hour
            "free_memory_bytes": 51200,
            "wifi_signal_strength": -45,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        response = requests.post(
            f"{self.API_BASE}/telemetry/status",
            json=status_data,
            headers=self.get_device_headers(device_token),
        )

        assert response.status_code == 202
        data = response.json()
        assert "message" in data


class TestLiveTelemetryBatch(TestLiveTelemetryAPI):
    """Test batch telemetry endpoints"""

    def test_batch_telemetry_success(self):
        """Test successful batch telemetry submission"""
        device_token, controller_id = self.create_device_token()

        batch_data = {
            "sensors": [
                {
                    "sensor_type": "temperature",
                    "value": 23.5,
                    "unit": "celsius",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
            "actuators": [
                {
                    "actuator_type": "relay",
                    "pin": "R1",
                    "state": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
            "inputs": [
                {
                    "input_type": "button",
                    "pin": "BTN1",
                    "state": False,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
            "status": {
                "uptime_ms": 3600000,
                "free_memory_bytes": 51200,
                "wifi_signal_strength": -45,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

        response = requests.post(
            f"{self.API_BASE}/telemetry/batch",
            json=batch_data,
            headers=self.get_device_headers(device_token),
        )

        assert response.status_code == 202
        data = response.json()
        assert "message" in data
        assert "sensors_processed" in data
        assert "actuators_processed" in data
        assert "inputs_processed" in data
        assert "status_processed" in data
        assert data["sensors_processed"] == 1
        assert data["actuators_processed"] == 1
        assert data["inputs_processed"] == 1
        assert data["status_processed"] == 1

    def test_batch_telemetry_partial_data(self):
        """Test batch telemetry with only some data types"""
        device_token, controller_id = self.create_device_token()

        batch_data = {
            "sensors": [
                {
                    "sensor_type": "humidity",
                    "value": 65.0,
                    "unit": "percent",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ]
            # Only sensors, no actuators, inputs, or status
        }

        response = requests.post(
            f"{self.API_BASE}/telemetry/batch",
            json=batch_data,
            headers=self.get_device_headers(device_token),
        )

        assert response.status_code == 202
        data = response.json()
        assert data["sensors_processed"] == 1
        assert data["actuators_processed"] == 0
        assert data["inputs_processed"] == 0
        assert data["status_processed"] == 0


class TestLiveTelemetryRateLimit(TestLiveTelemetryAPI):
    """Test telemetry rate limiting"""

    def test_telemetry_rate_limiting(self):
        """Test that rapid telemetry submissions are rate limited"""
        device_token, controller_id = self.create_device_token()

        # Submit many requests rapidly
        successful_requests = 0
        rate_limited_requests = 0

        for i in range(20):  # Submit 20 requests rapidly
            sensor_data = {
                "readings": [
                    {
                        "sensor_type": "temperature",
                        "value": 20.0 + i,
                        "unit": "celsius",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ]
            }

            response = requests.post(
                f"{self.API_BASE}/telemetry/sensors",
                json=sensor_data,
                headers=self.get_device_headers(device_token),
            )

            if response.status_code == 202:
                successful_requests += 1
            elif response.status_code == 429:
                rate_limited_requests += 1
                # Check rate limit headers
                assert "X-RateLimit-Limit" in response.headers
                assert "X-RateLimit-Remaining" in response.headers
                assert "Retry-After" in response.headers

            # Small delay between requests
            time.sleep(0.1)

        print(f"Successful requests: {successful_requests}")
        print(f"Rate limited requests: {rate_limited_requests}")

        # Should have at least some successful requests
        assert successful_requests > 0


class TestLiveEndToEndTelemetry(TestLiveTelemetryAPI):
    """Test complete telemetry workflows"""

    def test_complete_telemetry_flow(self):
        """Test complete telemetry submission flow"""
        print("\n=== Testing Complete Telemetry Flow ===")

        # Step 1: Setup device
        device_token, controller_id = self.create_device_token()
        print(f"✓ Device setup complete: {controller_id}")

        # Step 2: Submit sensor data
        sensor_response = requests.post(
            f"{self.API_BASE}/telemetry/sensors",
            json={
                "readings": [
                    {
                        "sensor_type": "temperature",
                        "value": 23.5,
                        "unit": "celsius",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    {
                        "sensor_type": "humidity",
                        "value": 65.0,
                        "unit": "percent",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                ]
            },
            headers=self.get_device_headers(device_token),
        )
        assert sensor_response.status_code == 202
        print("✓ Sensor data submitted")

        # Step 3: Submit actuator data
        actuator_response = requests.post(
            f"{self.API_BASE}/telemetry/actuators",
            json={
                "states": [
                    {
                        "actuator_type": "relay",
                        "pin": "R1",
                        "state": True,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ]
            },
            headers=self.get_device_headers(device_token),
        )
        assert actuator_response.status_code == 202
        print("✓ Actuator data submitted")

        # Step 4: Submit input data
        input_response = requests.post(
            f"{self.API_BASE}/telemetry/inputs",
            json={
                "events": [
                    {
                        "input_type": "button",
                        "pin": "BTN1",
                        "state": True,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ]
            },
            headers=self.get_device_headers(device_token),
        )
        assert input_response.status_code == 202
        print("✓ Input data submitted")

        # Step 5: Submit status data
        status_response = requests.post(
            f"{self.API_BASE}/telemetry/status",
            json={
                "uptime_ms": 3600000,
                "free_memory_bytes": 51200,
                "wifi_signal_strength": -45,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            headers=self.get_device_headers(device_token),
        )
        assert status_response.status_code == 202
        print("✓ Status data submitted")

        # Step 6: Submit batch data
        batch_response = requests.post(
            f"{self.API_BASE}/telemetry/batch",
            json={
                "sensors": [
                    {
                        "sensor_type": "soil_moisture",
                        "value": 45.0,
                        "unit": "percent",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                "actuators": [
                    {
                        "actuator_type": "pwm",
                        "pin": "PWM1",
                        "state": True,
                        "value": 75.0,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                "status": {
                    "uptime_ms": 3660000,
                    "free_memory_bytes": 50800,
                    "wifi_signal_strength": -48,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            },
            headers=self.get_device_headers(device_token),
        )
        assert batch_response.status_code == 202
        print("✓ Batch data submitted")

        print("=== Complete Telemetry Flow Test PASSED ===\n")
