"""
Comprehensive live integration test runner for ALL Verdify API endpoints.
Tests against running FastAPI server on localhost:8000.
"""

import uuid
from datetime import datetime, timezone

import pytest
import requests


class TestLiveComprehensiveAPI:
    """Comprehensive test suite for all API endpoints"""

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


class TestLiveUtilsAndHealth(TestLiveComprehensiveAPI):
    """Test utility and health endpoints"""

    def test_health_endpoint(self):
        """Test health check endpoint"""
        response = requests.get(f"{self.API_BASE}/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["ok", "healthy"]  # Accept both formats

    def test_utils_health_check(self):
        """Test utils health check endpoint"""
        response = requests.get(
            f"{self.API_BASE}/utils/health-check/", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data

    def test_openapi_json(self):
        """Test OpenAPI specification endpoint"""
        response = requests.get(f"{self.API_BASE}/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data

    def test_docs_endpoints(self):
        """Test documentation endpoints"""
        endpoints = ["/docs", "/redoc"]

        for endpoint in endpoints:
            response = requests.get(f"{self.BASE_URL}{endpoint}")
            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")


class TestLiveAdvancedCRUD(TestLiveComprehensiveAPI):
    """Test advanced CRUD operations"""

    def create_test_ecosystem(self) -> dict[str, str]:
        """Create a complete test ecosystem"""
        # Create greenhouse
        greenhouse_data = {
            "title": f"Advanced Test Greenhouse {uuid.uuid4().hex[:8]}",
            "description": "For advanced CRUD testing",
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

        # Create zone
        zone_data = {
            "name": f"Advanced Test Zone {uuid.uuid4().hex[:8]}",
            "description": "For advanced testing",
            "greenhouse_id": greenhouse_id,
        }

        zone_response = requests.post(
            f"{self.API_BASE}/zones/", json=zone_data, headers=self.get_auth_headers()
        )
        assert zone_response.status_code == 201
        zone_id = zone_response.json()["id"]

        # Create controller
        controller_data = {
            "device_name": f"verdify-{uuid.uuid4().hex[:6]}",
            "claim_code": "123456",
            "hardware_profile": "kincony_a16s",
            "firmware": "2.1.0",
            "greenhouse_id": greenhouse_id,
        }

        controller_response = requests.post(
            f"{self.API_BASE}/controllers/",
            json=controller_data,
            headers=self.get_auth_headers(),
        )
        assert controller_response.status_code == 201
        controller_id = controller_response.json()["id"]

        return {
            "greenhouse_id": greenhouse_id,
            "zone_id": zone_id,
            "controller_id": controller_id,
        }

    def test_crops_operations(self):
        """Test crop-related operations"""
        ecosystem = self.create_test_ecosystem()

        # Create crop
        crop_data = {
            "name": f"Test Crop {uuid.uuid4().hex[:8]}",
            "description": "Integration test crop",
            "growth_days": 60,
        }

        crop_response = requests.post(
            f"{self.API_BASE}/crops/", json=crop_data, headers=self.get_auth_headers()
        )
        assert crop_response.status_code == 201
        crop_id = crop_response.json()["id"]

        # List crops
        list_response = requests.get(
            f"{self.API_BASE}/crops/", headers=self.get_auth_headers()
        )
        assert list_response.status_code == 200
        assert "data" in list_response.json()

        # Get crop by ID
        get_response = requests.get(
            f"{self.API_BASE}/crops/{crop_id}", headers=self.get_auth_headers()
        )
        assert get_response.status_code == 200

        # Update crop
        update_data = {"description": "Updated test crop"}
        update_response = requests.patch(
            f"{self.API_BASE}/crops/{crop_id}",
            json=update_data,
            headers=self.get_auth_headers(),
        )
        assert update_response.status_code == 200

        # Create zone-crop relationship
        zone_crop_data = {
            "crop_id": crop_id,
            "zone_id": ecosystem["zone_id"],
            "planted_date": datetime.now(timezone.utc).isoformat(),
            "expected_harvest_date": datetime.now(timezone.utc).isoformat(),
        }

        zone_crop_response = requests.post(
            f"{self.API_BASE}/crops/zones/{ecosystem['zone_id']}/zone-crop/",
            json=zone_crop_data,
            headers=self.get_auth_headers(),
        )
        assert zone_crop_response.status_code == 201

        # Get zone crop
        get_zone_crop = requests.get(
            f"{self.API_BASE}/crops/zones/{ecosystem['zone_id']}/zone-crop/",
            headers=self.get_auth_headers(),
        )
        assert get_zone_crop.status_code == 200

        print("✓ Crops operations test passed")

    def test_fan_groups_operations(self):
        """Test fan group operations"""
        ecosystem = self.create_test_ecosystem()

        # Create fan group
        fan_group_data = {
            "name": f"Test Fan Group {uuid.uuid4().hex[:8]}",
            "description": "Integration test fan group",
            "controller_id": ecosystem["controller_id"],
        }

        fan_group_response = requests.post(
            f"{self.API_BASE}/fan-groups/",
            json=fan_group_data,
            headers=self.get_auth_headers(),
        )
        assert fan_group_response.status_code == 201
        fan_group_id = fan_group_response.json()["id"]

        # List fan groups
        list_response = requests.get(
            f"{self.API_BASE}/fan-groups/", headers=self.get_auth_headers()
        )
        assert list_response.status_code == 200

        # Get fan group by ID
        get_response = requests.get(
            f"{self.API_BASE}/fan-groups/{fan_group_id}",
            headers=self.get_auth_headers(),
        )
        assert get_response.status_code == 200

        # Update fan group
        update_data = {"description": "Updated fan group"}
        update_response = requests.patch(
            f"{self.API_BASE}/fan-groups/{fan_group_id}",
            json=update_data,
            headers=self.get_auth_headers(),
        )
        assert update_response.status_code == 200

        # Delete fan group
        delete_response = requests.delete(
            f"{self.API_BASE}/fan-groups/{fan_group_id}",
            headers=self.get_auth_headers(),
        )
        assert delete_response.status_code == 204

        print("✓ Fan groups operations test passed")

    def test_buttons_operations(self):
        """Test button operations"""
        ecosystem = self.create_test_ecosystem()

        # Create button
        button_data = {
            "name": f"Test Button {uuid.uuid4().hex[:8]}",
            "pin": "BTN1",
            "controller_id": ecosystem["controller_id"],
        }

        button_response = requests.post(
            f"{self.API_BASE}/buttons/",
            json=button_data,
            headers=self.get_auth_headers(),
        )
        assert button_response.status_code == 201
        button_id = button_response.json()["id"]

        # List buttons
        list_response = requests.get(
            f"{self.API_BASE}/buttons/", headers=self.get_auth_headers()
        )
        assert list_response.status_code == 200

        # Get button by ID
        get_response = requests.get(
            f"{self.API_BASE}/buttons/{button_id}", headers=self.get_auth_headers()
        )
        assert get_response.status_code == 200

        # Update button
        update_data = {"name": "Updated test button"}
        update_response = requests.patch(
            f"{self.API_BASE}/buttons/{button_id}",
            json=update_data,
            headers=self.get_auth_headers(),
        )
        assert update_response.status_code == 200

        # Delete button
        delete_response = requests.delete(
            f"{self.API_BASE}/buttons/{button_id}", headers=self.get_auth_headers()
        )
        assert delete_response.status_code == 204

        print("✓ Buttons operations test passed")

    def test_state_machine_operations(self):
        """Test state machine operations"""
        ecosystem = self.create_test_ecosystem()

        # Create state machine row
        state_data = {
            "greenhouse_id": ecosystem["greenhouse_id"],
            "condition": "temperature > 25",
            "action": "turn_on_fan",
            "priority": 1,
        }

        state_response = requests.post(
            f"{self.API_BASE}/state-machine-rows/",
            json=state_data,
            headers=self.get_auth_headers(),
        )
        assert state_response.status_code == 201
        state_id = state_response.json()["id"]

        # List state machine rows
        list_response = requests.get(
            f"{self.API_BASE}/state-machine-rows/", headers=self.get_auth_headers()
        )
        assert list_response.status_code == 200

        # Get state machine row by ID
        get_response = requests.get(
            f"{self.API_BASE}/state-machine-rows/{state_id}",
            headers=self.get_auth_headers(),
        )
        assert get_response.status_code == 200

        # Update state machine row
        update_data = {"priority": 2}
        update_response = requests.put(
            f"{self.API_BASE}/state-machine-rows/{state_id}",
            json={**state_data, **update_data},
            headers=self.get_auth_headers(),
        )
        assert update_response.status_code == 200

        # Test state machine fallback
        fallback_data = {
            "temperature_action": "maintain",
            "humidity_action": "monitor",
            "default_fan_speed": 50,
        }

        fallback_response = requests.put(
            f"{self.API_BASE}/state-machine-fallback/{ecosystem['greenhouse_id']}",
            json=fallback_data,
            headers=self.get_auth_headers(),
        )
        assert fallback_response.status_code == 200

        # Get state machine fallback
        get_fallback = requests.get(
            f"{self.API_BASE}/state-machine-fallback/{ecosystem['greenhouse_id']}",
            headers=self.get_auth_headers(),
        )
        assert get_fallback.status_code == 200

        print("✓ State machine operations test passed")


class TestLiveObservations(TestLiveComprehensiveAPI):
    """Test observation endpoints"""

    def test_observations_operations(self):
        """Test observation CRUD operations"""
        # Create observation
        observation_data = {
            "title": f"Test Observation {uuid.uuid4().hex[:8]}",
            "description": "Integration test observation",
            "observation_type": "growth",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        create_response = requests.post(
            f"{self.API_BASE}/observations/observations",
            json=observation_data,
            headers=self.get_auth_headers(),
        )
        assert create_response.status_code == 201
        observation_id = create_response.json()["id"]

        # List observations
        list_response = requests.get(
            f"{self.API_BASE}/observations/observations",
            headers=self.get_auth_headers(),
        )
        assert list_response.status_code == 200
        assert "data" in list_response.json()

        # Get observation by ID
        get_response = requests.get(
            f"{self.API_BASE}/observations/observations/{observation_id}",
            headers=self.get_auth_headers(),
        )
        assert get_response.status_code == 200

        # Update observation
        update_data = {
            **observation_data,
            "description": "Updated observation description",
        }
        update_response = requests.put(
            f"{self.API_BASE}/observations/observations/{observation_id}",
            json=update_data,
            headers=self.get_auth_headers(),
        )
        assert update_response.status_code == 200

        # Test upload URL generation
        upload_response = requests.post(
            f"{self.API_BASE}/observations/observations/{observation_id}/upload-url",
            json={"filename": "test_image.jpg", "content_type": "image/jpeg"},
            headers=self.get_auth_headers(),
        )
        assert upload_response.status_code == 200
        assert "upload_url" in upload_response.json()

        # Delete observation
        delete_response = requests.delete(
            f"{self.API_BASE}/observations/observations/{observation_id}",
            headers=self.get_auth_headers(),
        )
        assert delete_response.status_code == 204

        print("✓ Observations operations test passed")


class TestLiveErrorHandling(TestLiveComprehensiveAPI):
    """Test error handling and edge cases"""

    def test_404_endpoints(self):
        """Test 404 responses for non-existent resources"""
        fake_id = str(uuid.uuid4())

        endpoints_404 = [
            f"/greenhouses/{fake_id}",
            f"/zones/{fake_id}",
            f"/controllers/{fake_id}",
            f"/sensors/{fake_id}",
            f"/actuators/{fake_id}",
            f"/crops/{fake_id}",
            f"/users/{fake_id}",
        ]

        for endpoint in endpoints_404:
            response = requests.get(
                f"{self.API_BASE}{endpoint}", headers=self.get_auth_headers()
            )
            assert response.status_code == 404, f"Endpoint {endpoint} should return 404"

        print("✓ 404 error handling test passed")

    def test_422_validation_errors(self):
        """Test 422 validation errors"""
        # Test invalid greenhouse data
        invalid_greenhouse = {
            "title": "",  # Empty title should fail
            "min_temp_c": 50.0,
            "max_temp_c": 10.0,  # max < min should fail
        }

        response = requests.post(
            f"{self.API_BASE}/greenhouses/",
            json=invalid_greenhouse,
            headers=self.get_auth_headers(),
        )
        assert response.status_code == 422

        # Test invalid device name in onboarding
        invalid_hello = {
            "device_name": "invalid-name",  # Wrong pattern
            "claim_code": "123456",
            "hardware_profile": "kincony_a16s",
            "firmware": "2.1.0",
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        response = requests.post(
            f"{self.API_BASE}/hello",
            json=invalid_hello,
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

        print("✓ 422 validation error handling test passed")

    def test_401_unauthorized_endpoints(self):
        """Test 401 responses for unauthorized access"""
        protected_endpoints = [
            "/greenhouses/",
            "/zones/",
            "/controllers/",
            "/sensors/",
            "/actuators/",
            "/users/",
            "/crops/",
        ]

        for endpoint in protected_endpoints:
            response = requests.get(f"{self.API_BASE}{endpoint}")
            assert (
                response.status_code == 401
            ), f"Endpoint {endpoint} should require auth"

        print("✓ 401 unauthorized handling test passed")

    def test_pagination_parameters(self):
        """Test pagination parameters"""
        # Test valid pagination
        response = requests.get(
            f"{self.API_BASE}/greenhouses/?page=1&page_size=5",
            headers=self.get_auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 5

        # Test invalid pagination
        response = requests.get(
            f"{self.API_BASE}/greenhouses/?page=0&page_size=-1",
            headers=self.get_auth_headers(),
        )
        # Should either return 422 or correct the values
        assert response.status_code in [200, 422]

        print("✓ Pagination parameter handling test passed")


class TestLiveEndToEndScenarios(TestLiveComprehensiveAPI):
    """Test complete end-to-end scenarios"""

    def test_complete_greenhouse_operation_lifecycle(self):
        """Test complete greenhouse operation from setup to data collection"""
        print("\n=== Testing Complete Greenhouse Operation Lifecycle ===")

        # Step 1: Create greenhouse
        greenhouse_data = {
            "title": f"Lifecycle Test Greenhouse {uuid.uuid4().hex[:8]}",
            "description": "Complete operation lifecycle test",
            "min_temp_c": 15.0,
            "max_temp_c": 30.0,
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
        print(f"✓ Greenhouse created: {greenhouse_id}")

        # Step 2: Create zones
        zones = []
        for i in range(2):
            zone_data = {
                "name": f"Zone {i+1}",
                "description": f"Test zone {i+1}",
                "greenhouse_id": greenhouse_id,
            }

            zone_response = requests.post(
                f"{self.API_BASE}/zones/",
                json=zone_data,
                headers=self.get_auth_headers(),
            )
            assert zone_response.status_code == 201
            zones.append(zone_response.json()["id"])

        print(f"✓ Created {len(zones)} zones")

        # Step 3: Device onboarding and controller setup
        device_name = f"verdify-{uuid.uuid4().hex[:6]}"
        claim_code = "123456"

        # Announce device
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
        print("✓ Device announced")

        # Claim controller
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
        controller_id = claim_response.json()["controller"]["id"]
        new_claim_code = claim_response.json()["controller"]["claim_code"]
        print(f"✓ Controller claimed: {controller_id}")

        # Exchange for token
        exchange_payload = {"device_name": device_name, "claim_code": new_claim_code}

        exchange_response = requests.post(
            f"{self.API_BASE}/controllers/{controller_id}/token-exchange",
            json=exchange_payload,
            headers={"Content-Type": "application/json"},
        )
        assert exchange_response.status_code == 201
        device_token = exchange_response.json()["device_token"]
        print("✓ Device token obtained")

        # Step 4: Create sensors and actuators
        sensors = []
        sensor_types = ["temperature", "humidity", "soil_moisture"]

        for i, sensor_type in enumerate(sensor_types):
            sensor_data = {
                "controller_id": controller_id,
                "sensor_type": sensor_type,
                "pin": f"A{i}",
                "name": f"Test {sensor_type.title()} Sensor",
            }

            sensor_response = requests.post(
                f"{self.API_BASE}/sensors/",
                json=sensor_data,
                headers=self.get_auth_headers(),
            )
            assert sensor_response.status_code == 201
            sensors.append(sensor_response.json()["id"])

        actuators = []
        actuator_types = ["relay", "pwm"]

        for i, actuator_type in enumerate(actuator_types):
            actuator_data = {
                "controller_id": controller_id,
                "actuator_type": actuator_type,
                "pin": f"R{i+1}",
                "name": f"Test {actuator_type.upper()} Actuator",
            }

            actuator_response = requests.post(
                f"{self.API_BASE}/actuators/",
                json=actuator_data,
                headers=self.get_auth_headers(),
            )
            assert actuator_response.status_code == 201
            actuators.append(actuator_response.json()["id"])

        print(f"✓ Created {len(sensors)} sensors and {len(actuators)} actuators")

        # Step 5: Get configuration
        config_response = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": device_token},
        )
        assert config_response.status_code == 200
        config_data = config_response.json()
        assert len(config_data["sensors"]) == len(sensors)
        assert len(config_data["actuators"]) == len(actuators)
        print("✓ Configuration retrieved and validated")

        # Step 6: Submit telemetry data
        telemetry_data = {
            "sensors": [
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
            ],
            "actuators": [
                {
                    "actuator_type": "relay",
                    "pin": "R1",
                    "state": True,
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

        telemetry_response = requests.post(
            f"{self.API_BASE}/telemetry/batch",
            json=telemetry_data,
            headers={"X-Device-Token": device_token},
        )
        assert telemetry_response.status_code == 202
        print("✓ Telemetry data submitted")

        # Step 7: Create and manage crops
        crop_data = {
            "name": "Test Tomatoes",
            "description": "Lifecycle test crop",
            "growth_days": 90,
        }

        crop_response = requests.post(
            f"{self.API_BASE}/crops/", json=crop_data, headers=self.get_auth_headers()
        )
        assert crop_response.status_code == 201
        crop_id = crop_response.json()["id"]

        # Plant crop in zone
        zone_crop_data = {
            "crop_id": crop_id,
            "zone_id": zones[0],
            "planted_date": datetime.now(timezone.utc).isoformat(),
            "expected_harvest_date": datetime.now(timezone.utc).isoformat(),
        }

        zone_crop_response = requests.post(
            f"{self.API_BASE}/crops/zones/{zones[0]}/zone-crop/",
            json=zone_crop_data,
            headers=self.get_auth_headers(),
        )
        assert zone_crop_response.status_code == 201
        print("✓ Crop planted in zone")

        # Step 8: Create observations
        observation_data = {
            "title": "First growth observation",
            "description": "Seedlings are sprouting well",
            "observation_type": "growth",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        observation_response = requests.post(
            f"{self.API_BASE}/observations/observations",
            json=observation_data,
            headers=self.get_auth_headers(),
        )
        assert observation_response.status_code == 201
        print("✓ Growth observation recorded")

        # Step 9: Verify everything is connected and working
        # Check greenhouse has all components
        final_greenhouse_check = requests.get(
            f"{self.API_BASE}/greenhouses/{greenhouse_id}",
            headers=self.get_auth_headers(),
        )
        assert final_greenhouse_check.status_code == 200

        # Check controller has latest configuration
        final_config_check = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": device_token},
        )
        assert final_config_check.status_code == 200

        # Check plan is available
        plan_check = requests.get(
            f"{self.API_BASE}/controllers/me/plan",
            headers={"X-Device-Token": device_token},
        )
        assert plan_check.status_code == 200

        print("✓ Final system verification passed")
        print("=== Complete Greenhouse Operation Lifecycle Test PASSED ===\n")

        return {
            "greenhouse_id": greenhouse_id,
            "zones": zones,
            "controller_id": controller_id,
            "device_token": device_token,
            "sensors": sensors,
            "actuators": actuators,
            "crop_id": crop_id,
        }
