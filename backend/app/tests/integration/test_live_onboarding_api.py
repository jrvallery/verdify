"""
Integration tests for onboarding API endpoints against live server.

These tests hit the actual running FastAPI server on localhost:8000
and use the real database, testing the complete HTTP stack.
"""

import json
import uuid
from datetime import datetime, timezone

import pytest
import requests


class TestLiveOnboardingAPI:
    """Test onboarding flow against live server at localhost:8000"""

    BASE_URL = "http://localhost:8000"
    API_BASE = f"{BASE_URL}/api/v1"

    def setup_method(self):
        """Setup before each test method"""
        # Check if server is running
        try:
            response = requests.get(f"{self.API_BASE}/health", timeout=5)
            assert response.status_code == 200, "Server not running on localhost:8000"
        except requests.exceptions.ConnectionError:
            pytest.skip("FastAPI server not running on localhost:8000")

    def get_superuser_token(self) -> str:
        """Get authentication token for superuser"""
        # Use actual superuser credentials from .env
        login_data = {
            "username": "jason@verdify.ai",  # From FIRST_SUPERUSER
            "password": "v@ll3ry4761",  # From FIRST_SUPERUSER_PASSWORD
        }

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

    def create_test_greenhouse(self) -> str:
        """Create a test greenhouse and return its ID"""
        greenhouse_data = {
            "title": f"Live Test Greenhouse {uuid.uuid4().hex[:8]}",
            "description": "Integration test greenhouse",
            "min_temp_c": 10.0,
            "max_temp_c": 35.0,
            "site_pressure_hpa": 1013.25,
            "enthalpy_open_kjkg": 50.0,
            "enthalpy_close_kjkg": 100.0,
        }

        response = requests.post(
            f"{self.API_BASE}/greenhouses/",
            json=greenhouse_data,
            headers=self.get_auth_headers(),
        )

        if response.status_code not in [200, 201]:
            pytest.skip(
                f"Cannot create test greenhouse: {response.status_code} - {response.text}"
            )

        greenhouse = response.json()
        return greenhouse["id"]


class TestLiveDeviceHello(TestLiveOnboardingAPI):
    """Test device hello endpoint against live server"""

    def test_device_hello_success(self):
        """Test successful device hello announcement"""
        device_name = f"verdify-{uuid.uuid4().hex[:6]}"
        claim_code = "123456"

        payload = {
            "device_name": device_name,
            "claim_code": claim_code,
            "hardware_profile": "kincony_a16s",
            "firmware": "2.1.0",
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        response = requests.post(
            f"{self.API_BASE}/hello",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert data["controller_uuid"] is None
        assert data["greenhouse_id"] is None
        assert "retry_after_s" in data
        assert "message" in data

    def test_device_hello_invalid_device_name(self):
        """Test device hello with invalid device name pattern"""
        payload = {
            "device_name": "invalid-name",
            "claim_code": "123456",
            "hardware_profile": "kincony_a16s",
            "firmware": "2.1.0",
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        response = requests.post(
            f"{self.API_BASE}/hello",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        # Check validation error mentions device_name pattern
        error_msg = json.dumps(data).lower()
        assert "device_name" in error_msg
        assert "pattern" in error_msg or "verdify" in error_msg

    def test_device_hello_invalid_claim_code(self):
        """Test device hello with invalid claim code format"""
        device_name = f"verdify-{uuid.uuid4().hex[:6]}"

        payload = {
            "device_name": device_name,
            "claim_code": "12345",  # Too short
            "hardware_profile": "kincony_a16s",
            "firmware": "2.1.0",
            "ts_utc": datetime.now(timezone.utc).isoformat(),
        }

        response = requests.post(
            f"{self.API_BASE}/hello",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_device_hello_missing_fields(self):
        """Test device hello with missing required fields"""
        payload = {
            "device_name": f"verdify-{uuid.uuid4().hex[:6]}",
            # Missing claim_code and other required fields
        }

        response = requests.post(
            f"{self.API_BASE}/hello",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


class TestLiveControllerClaim(TestLiveOnboardingAPI):
    """Test controller claim endpoint against live server"""

    def test_claim_controller_unauthorized(self):
        """Test claiming controller without authentication fails"""
        device_name = f"verdify-{uuid.uuid4().hex[:6]}"

        payload = {
            "device_name": device_name,
            "claim_code": "123456",
            "greenhouse_id": str(uuid.uuid4()),
        }

        response = requests.post(
            f"{self.API_BASE}/controllers/claim",
            json=payload,
            headers={"Content-Type": "application/json"},
            # No auth headers
        )

        assert response.status_code == 401

    def test_claim_controller_success(self):
        """Test successful controller claim with proper authentication"""
        device_name = f"verdify-{uuid.uuid4().hex[:6]}"
        claim_code = "123456"

        # 1. First announce the device
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

        # 2. Create a test greenhouse
        greenhouse_id = self.create_test_greenhouse()

        # 3. Claim the controller
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
        data = claim_response.json()
        assert "controller" in data
        assert data["controller"]["device_name"] == device_name
        assert data["controller"]["greenhouse_id"] == greenhouse_id
        assert "claim_code" in data["controller"]
        assert "id" in data["controller"]

    def test_claim_controller_not_announced(self):
        """Test claiming controller that was not announced first"""
        device_name = f"verdify-{uuid.uuid4().hex[:6]}"
        greenhouse_id = self.create_test_greenhouse()

        claim_payload = {
            "device_name": device_name,
            "claim_code": "123456",
            "greenhouse_id": greenhouse_id,
        }

        response = requests.post(
            f"{self.API_BASE}/controllers/claim",
            json=claim_payload,
            headers={**{"Content-Type": "application/json"}, **self.get_auth_headers()},
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data or "error_code" in data

    def test_claim_controller_invalid_greenhouse(self):
        """Test claiming controller with invalid greenhouse ID"""
        device_name = f"verdify-{uuid.uuid4().hex[:6]}"
        claim_code = "123456"

        # Announce the device first
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

        # Try to claim with non-existent greenhouse
        claim_payload = {
            "device_name": device_name,
            "claim_code": claim_code,
            "greenhouse_id": str(uuid.uuid4()),  # Random UUID
        }

        response = requests.post(
            f"{self.API_BASE}/controllers/claim",
            json=claim_payload,
            headers={**{"Content-Type": "application/json"}, **self.get_auth_headers()},
        )

        assert response.status_code in [404, 422]


class TestLiveTokenExchange(TestLiveOnboardingAPI):
    """Test token exchange endpoint against live server"""

    def setup_full_onboarding_flow(self):
        """Setup a complete onboarding flow and return controller_id and claim_code"""
        device_name = f"verdify-{uuid.uuid4().hex[:6]}"
        claim_code = "123456"

        # 1. Announce device
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

        # 2. Create greenhouse
        greenhouse_id = self.create_test_greenhouse()

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

        return device_name, controller_id, new_claim_code

    def test_token_exchange_success(self):
        """Test successful token exchange after claiming"""
        device_name, controller_id, new_claim_code = self.setup_full_onboarding_flow()

        # Exchange for token
        exchange_payload = {"device_name": device_name, "claim_code": new_claim_code}

        response = requests.post(
            f"{self.API_BASE}/controllers/{controller_id}/token-exchange",
            json=exchange_payload,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "device_token" in data
        assert "config_etag" in data
        assert "plan_etag" in data
        assert "expires_at" in data

    def test_token_exchange_idempotent(self):
        """Test that token exchange is idempotent"""
        device_name, controller_id, new_claim_code = self.setup_full_onboarding_flow()

        exchange_payload = {"device_name": device_name, "claim_code": new_claim_code}

        # First exchange - should return 201
        first_response = requests.post(
            f"{self.API_BASE}/controllers/{controller_id}/token-exchange",
            json=exchange_payload,
            headers={"Content-Type": "application/json"},
        )
        assert first_response.status_code == 201
        first_data = first_response.json()

        # Second exchange - should return 200 (idempotent)
        second_response = requests.post(
            f"{self.API_BASE}/controllers/{controller_id}/token-exchange",
            json=exchange_payload,
            headers={"Content-Type": "application/json"},
        )
        assert second_response.status_code == 200
        second_data = second_response.json()

        # Both should have all required fields
        for data in [first_data, second_data]:
            assert "device_token" in data
            assert "config_etag" in data
            assert "plan_etag" in data
            assert "expires_at" in data

    def test_token_exchange_invalid_controller_id(self):
        """Test token exchange with invalid controller ID"""
        exchange_payload = {
            "device_name": f"verdify-{uuid.uuid4().hex[:6]}",
            "claim_code": "123456",
        }

        # Use random UUID as controller ID
        fake_controller_id = str(uuid.uuid4())

        response = requests.post(
            f"{self.API_BASE}/controllers/{fake_controller_id}/token-exchange",
            json=exchange_payload,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 404

    def test_token_exchange_missing_body(self):
        """Test token exchange with missing request body"""
        device_name, controller_id, new_claim_code = self.setup_full_onboarding_flow()

        response = requests.post(
            f"{self.API_BASE}/controllers/{controller_id}/token-exchange",
            headers={"Content-Type": "application/json"},
            # No body
        )

        assert response.status_code == 422

    def test_token_exchange_invalid_request_data(self):
        """Test token exchange with invalid request data"""
        device_name, controller_id, new_claim_code = self.setup_full_onboarding_flow()

        exchange_payload = {
            "device_name": "invalid-name",  # Wrong pattern
            "claim_code": "12345",  # Wrong length
        }

        response = requests.post(
            f"{self.API_BASE}/controllers/{controller_id}/token-exchange",
            json=exchange_payload,
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422


class TestLiveEndToEndOnboarding(TestLiveOnboardingAPI):
    """Test complete end-to-end onboarding flow against live server"""

    def test_complete_onboarding_flow(self):
        """Test the complete onboarding flow from hello to token exchange"""
        device_name = f"verdify-{uuid.uuid4().hex[:6]}"
        original_claim_code = "123456"

        print(f"\n=== Testing Complete Onboarding Flow for {device_name} ===")

        # Step 1: Device Hello
        print("Step 1: Device Hello...")
        hello_payload = {
            "device_name": device_name,
            "claim_code": original_claim_code,
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
        hello_data = hello_response.json()
        print(f"✓ Hello successful: {hello_data}")

        # Step 2: Create Greenhouse
        print("Step 2: Creating greenhouse...")
        greenhouse_id = self.create_test_greenhouse()
        print(f"✓ Greenhouse created: {greenhouse_id}")

        # Step 3: Claim Controller
        print("Step 3: Claiming controller...")
        claim_payload = {
            "device_name": device_name,
            "claim_code": original_claim_code,
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
        print(f"✓ Controller claimed: {controller_id}")
        print(f"  New claim code: {new_claim_code}")

        # Step 4: Token Exchange
        print("Step 4: Token exchange...")
        exchange_payload = {"device_name": device_name, "claim_code": new_claim_code}

        exchange_response = requests.post(
            f"{self.API_BASE}/controllers/{controller_id}/token-exchange",
            json=exchange_payload,
            headers={"Content-Type": "application/json"},
        )
        assert exchange_response.status_code == 201
        exchange_data = exchange_response.json()
        print("✓ Token exchange successful")
        print(f"  Device token: {exchange_data.get('device_token', 'N/A')}")
        print(f"  Config ETag: {exchange_data.get('config_etag', 'N/A')}")
        print(f"  Plan ETag: {exchange_data.get('plan_etag', 'N/A')}")

        # Step 5: Test Idempotency
        print("Step 5: Testing idempotency...")
        second_exchange_response = requests.post(
            f"{self.API_BASE}/controllers/{controller_id}/token-exchange",
            json=exchange_payload,
            headers={"Content-Type": "application/json"},
        )
        assert second_exchange_response.status_code == 200
        second_exchange_data = second_exchange_response.json()
        print("✓ Idempotent exchange successful (200 status)")

        print("=== Complete Onboarding Flow Test PASSED ===\n")

        # Verify all steps worked correctly
        assert hello_data["status"] == "pending"
        assert claim_data["controller"]["device_name"] == device_name
        assert claim_data["controller"]["greenhouse_id"] == greenhouse_id
        assert "device_token" in exchange_data
        assert "config_etag" in exchange_data
        assert "plan_etag" in exchange_data
        assert "expires_at" in exchange_data
        assert "device_token" in second_exchange_data
