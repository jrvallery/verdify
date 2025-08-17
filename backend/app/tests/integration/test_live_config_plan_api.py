"""
Live integration tests for configuration and plan API endpoints.
Tests against running FastAPI server on localhost:8000.
"""

import uuid
from datetime import datetime, timezone

import pytest
import requests


class TestLiveConfigPlanAPI:
    """Test configuration and plan endpoints against live server"""

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

    def create_full_ecosystem(self) -> dict[str, str]:
        """Create a complete ecosystem for config/plan testing"""
        # Create greenhouse
        greenhouse_data = {
            "title": f"Config Test Greenhouse {uuid.uuid4().hex[:8]}",
            "description": "For config/plan testing",
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

        # Create and claim controller
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
        claim_data = claim_response.json()
        controller_id = claim_data["controller"]["id"]
        new_claim_code = claim_data["controller"]["claim_code"]

        # Exchange for token
        exchange_payload = {"device_name": device_name, "claim_code": new_claim_code}

        exchange_response = requests.post(
            f"{self.API_BASE}/controllers/{controller_id}/token-exchange",
            json=exchange_payload,
            headers={"Content-Type": "application/json"},
        )
        assert exchange_response.status_code == 201
        exchange_data = exchange_response.json()
        device_token = exchange_data["device_token"]

        return {
            "greenhouse_id": greenhouse_id,
            "controller_id": controller_id,
            "device_name": device_name,
            "device_token": device_token,
        }


class TestLiveDeviceConfig(TestLiveConfigPlanAPI):
    """Test device configuration endpoints"""

    def test_get_config_with_device_token(self):
        """Test getting config using device token"""
        ecosystem = self.create_full_ecosystem()
        device_token = ecosystem["device_token"]

        response = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": device_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "controller" in data
        assert "greenhouse" in data
        assert "zones" in data
        assert "sensors" in data
        assert "actuators" in data
        assert "version" in data

        # Check ETag header
        assert "ETag" in response.headers
        etag = response.headers["ETag"]
        assert etag.startswith('"config:v')

    def test_get_config_by_device_name(self):
        """Test getting config by device name (admin access)"""
        ecosystem = self.create_full_ecosystem()
        device_name = ecosystem["device_name"]

        response = requests.get(
            f"{self.API_BASE}/controllers/by-name/{device_name}/config",
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert "controller" in data
        assert "greenhouse" in data
        assert "zones" in data
        assert "sensors" in data
        assert "actuators" in data

    def test_get_config_with_if_none_match(self):
        """Test config retrieval with If-None-Match header"""
        ecosystem = self.create_full_ecosystem()
        device_token = ecosystem["device_token"]

        # First request to get ETag
        first_response = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": device_token},
        )
        assert first_response.status_code == 200
        etag = first_response.headers["ETag"]

        # Second request with If-None-Match
        second_response = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": device_token, "If-None-Match": etag},
        )

        assert second_response.status_code == 304  # Not Modified

    def test_get_config_unauthorized(self):
        """Test config access without proper authentication"""
        response = requests.get(f"{self.API_BASE}/controllers/me/config")

        assert response.status_code == 401

    def test_get_config_invalid_device_token(self):
        """Test config access with invalid device token"""
        response = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": "invalid_token"},
        )

        assert response.status_code == 401


class TestLiveDevicePlan(TestLiveConfigPlanAPI):
    """Test device plan endpoints"""

    def test_get_plan_with_device_token(self):
        """Test getting plan using device token"""
        ecosystem = self.create_full_ecosystem()
        device_token = ecosystem["device_token"]

        response = requests.get(
            f"{self.API_BASE}/controllers/me/plan",
            headers={"X-Device-Token": device_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "schedules" in data
        assert "rules" in data
        assert "version" in data

        # Check ETag header
        assert "ETag" in response.headers
        etag = response.headers["ETag"]
        assert etag.startswith('"plan:v')

    def test_get_plan_by_controller_id(self):
        """Test getting plan by controller ID (admin access)"""
        ecosystem = self.create_full_ecosystem()
        controller_id = ecosystem["controller_id"]

        response = requests.get(
            f"{self.API_BASE}/controllers/{controller_id}/plan",
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert "schedules" in data
        assert "rules" in data
        assert "version" in data

    def test_get_plan_with_if_none_match(self):
        """Test plan retrieval with If-None-Match header"""
        ecosystem = self.create_full_ecosystem()
        device_token = ecosystem["device_token"]

        # First request to get ETag
        first_response = requests.get(
            f"{self.API_BASE}/controllers/me/plan",
            headers={"X-Device-Token": device_token},
        )
        assert first_response.status_code == 200
        etag = first_response.headers["ETag"]

        # Second request with If-None-Match
        second_response = requests.get(
            f"{self.API_BASE}/controllers/me/plan",
            headers={"X-Device-Token": device_token, "If-None-Match": etag},
        )

        assert second_response.status_code == 304  # Not Modified

    def test_get_plan_unauthorized(self):
        """Test plan access without proper authentication"""
        response = requests.get(f"{self.API_BASE}/controllers/me/plan")

        assert response.status_code == 401


class TestLiveAdminConfig(TestLiveConfigPlanAPI):
    """Test admin configuration endpoints"""

    def test_create_plan_admin(self):
        """Test creating a plan as admin"""
        plan_data = {
            "name": f"Test Plan {uuid.uuid4().hex[:8]}",
            "description": "Integration test plan",
            "schedules": [
                {
                    "name": "Daily watering",
                    "cron": "0 8 * * *",
                    "action": "water",
                    "duration_minutes": 10,
                }
            ],
            "rules": [
                {
                    "name": "Temperature control",
                    "condition": "temperature > 30",
                    "action": "turn_on_fan",
                    "priority": 1,
                }
            ],
        }

        response = requests.post(
            f"{self.API_BASE}/plans", json=plan_data, headers=self.get_auth_headers()
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == plan_data["name"]
        assert "id" in data
        assert "version" in data

        return data["id"]

    def test_list_plans_admin(self):
        """Test listing plans as admin"""
        response = requests.get(
            f"{self.API_BASE}/plans", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data

    def test_greenhouse_config_diff(self):
        """Test getting greenhouse config diff"""
        ecosystem = self.create_full_ecosystem()
        greenhouse_id = ecosystem["greenhouse_id"]

        response = requests.get(
            f"{self.API_BASE}/greenhouses/{greenhouse_id}/config/diff",
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert "changes" in data
        assert "current_version" in data
        assert "target_version" in data

    def test_publish_greenhouse_config(self):
        """Test publishing greenhouse config"""
        ecosystem = self.create_full_ecosystem()
        greenhouse_id = ecosystem["greenhouse_id"]

        publish_data = {"message": "Test config publish", "force": False}

        response = requests.post(
            f"{self.API_BASE}/greenhouses/{greenhouse_id}/config/publish",
            json=publish_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code in [200, 202]  # Success or Accepted
        data = response.json()
        assert "message" in data


class TestLiveControllerTokenManagement(TestLiveConfigPlanAPI):
    """Test controller token management"""

    def test_rotate_controller_token(self):
        """Test rotating controller token"""
        ecosystem = self.create_full_ecosystem()
        controller_id = ecosystem["controller_id"]
        old_token = ecosystem["device_token"]

        response = requests.post(
            f"{self.API_BASE}/controllers/{controller_id}/rotate-token",
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert "device_token" in data
        assert "expires_at" in data
        new_token = data["device_token"]
        assert new_token != old_token

        # Test that old token no longer works
        old_token_response = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": old_token},
        )
        assert old_token_response.status_code == 401

        # Test that new token works
        new_token_response = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": new_token},
        )
        assert new_token_response.status_code == 200

    def test_revoke_controller_token(self):
        """Test revoking controller token"""
        ecosystem = self.create_full_ecosystem()
        controller_id = ecosystem["controller_id"]
        device_token = ecosystem["device_token"]

        # First verify token works
        config_response = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": device_token},
        )
        assert config_response.status_code == 200

        # Revoke token
        revoke_response = requests.post(
            f"{self.API_BASE}/controllers/{controller_id}/revoke-token",
            headers=self.get_auth_headers(),
        )
        assert revoke_response.status_code == 204

        # Verify token no longer works
        invalid_response = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": device_token},
        )
        assert invalid_response.status_code == 401


class TestLiveMetaEndpoints(TestLiveConfigPlanAPI):
    """Test meta endpoints"""

    def test_get_sensor_kinds(self):
        """Test getting sensor kinds metadata"""
        response = requests.get(f"{self.API_BASE}/meta/sensor-kinds")

        assert response.status_code == 200
        data = response.json()

        # Handle both formats: list or dict with sensor_kinds key
        if isinstance(data, list):
            sensor_kinds = data
        else:
            assert "sensor_kinds" in data
            sensor_kinds = data["sensor_kinds"]

        assert len(sensor_kinds) > 0

        # Check structure - may be strings or objects
        for sensor_kind in sensor_kinds:
            if isinstance(sensor_kind, dict):
                assert "type" in sensor_kind
                assert "description" in sensor_kind
                assert "unit" in sensor_kind
            else:
                # Simple string format
                assert isinstance(sensor_kind, str)

    def test_get_actuator_kinds(self):
        """Test getting actuator kinds metadata"""
        response = requests.get(f"{self.API_BASE}/meta/actuator-kinds")

        assert response.status_code == 200
        data = response.json()

        # Handle both formats: list or dict with actuator_kinds key
        if isinstance(data, list):
            actuator_kinds = data
        else:
            assert "actuator_kinds" in data
            actuator_kinds = data["actuator_kinds"]

        assert len(actuator_kinds) > 0

        # Check structure - may be strings or objects
        for actuator_kind in actuator_kinds:
            if isinstance(actuator_kind, dict):
                assert "type" in actuator_kind
                assert "description" in actuator_kind
            else:
                # Simple string format
                assert isinstance(actuator_kind, str)


class TestLiveEndToEndConfigPlan(TestLiveConfigPlanAPI):
    """Test complete config and plan workflows"""

    def test_complete_config_plan_flow(self):
        """Test complete configuration and plan flow"""
        print("\n=== Testing Complete Config/Plan Flow ===")

        # Step 1: Create ecosystem
        ecosystem = self.create_full_ecosystem()
        print(f"✓ Ecosystem created: {ecosystem['controller_id']}")

        # Step 2: Get initial config
        config_response = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": ecosystem["device_token"]},
        )
        assert config_response.status_code == 200
        config_etag = config_response.headers["ETag"]
        print(f"✓ Initial config retrieved: {config_etag}")

        # Step 3: Get initial plan
        plan_response = requests.get(
            f"{self.API_BASE}/controllers/me/plan",
            headers={"X-Device-Token": ecosystem["device_token"]},
        )
        assert plan_response.status_code == 200
        plan_etag = plan_response.headers["ETag"]
        print(f"✓ Initial plan retrieved: {plan_etag}")

        # Step 4: Test conditional requests (304 responses)
        config_304 = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={
                "X-Device-Token": ecosystem["device_token"],
                "If-None-Match": config_etag,
            },
        )
        assert config_304.status_code == 304
        print("✓ Config 304 response verified")

        plan_304 = requests.get(
            f"{self.API_BASE}/controllers/me/plan",
            headers={
                "X-Device-Token": ecosystem["device_token"],
                "If-None-Match": plan_etag,
            },
        )
        assert plan_304.status_code == 304
        print("✓ Plan 304 response verified")

        # Step 5: Test admin access to same resources
        admin_config = requests.get(
            f"{self.API_BASE}/controllers/by-name/{ecosystem['device_name']}/config",
            headers=self.get_auth_headers(),
        )
        assert admin_config.status_code == 200
        print("✓ Admin config access verified")

        admin_plan = requests.get(
            f"{self.API_BASE}/controllers/{ecosystem['controller_id']}/plan",
            headers=self.get_auth_headers(),
        )
        assert admin_plan.status_code == 200
        print("✓ Admin plan access verified")

        # Step 6: Test token rotation
        rotate_response = requests.post(
            f"{self.API_BASE}/controllers/{ecosystem['controller_id']}/rotate-token",
            headers=self.get_auth_headers(),
        )
        assert rotate_response.status_code == 200
        new_token = rotate_response.json()["device_token"]
        print("✓ Token rotation successful")

        # Step 7: Verify new token works
        new_config = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": new_token},
        )
        assert new_config.status_code == 200
        print("✓ New token verification successful")

        # Step 8: Verify old token doesn't work
        old_config = requests.get(
            f"{self.API_BASE}/controllers/me/config",
            headers={"X-Device-Token": ecosystem["device_token"]},
        )
        assert old_config.status_code == 401
        print("✓ Old token invalidation verified")

        print("=== Complete Config/Plan Flow Test PASSED ===\n")
