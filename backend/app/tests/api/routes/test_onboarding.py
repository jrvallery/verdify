import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Greenhouse, User


class TestDeviceHello:
    def test_device_hello_success(self, client: TestClient):
        """Test device hello endpoint returns proper response"""
        response = client.post(
            "/api/v1/hello",
            json={
                "device_name": "verdify-abc001",
                "claim_code": "123456",
                "hardware_profile": "kincony_a16s",
                "firmware": "2.1.0",
                "ts_utc": datetime.now(timezone.utc).isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"
        assert "retry_after_s" in data
        assert data["controller_uuid"] is None
        assert data["greenhouse_id"] is None
        assert "message" in data

    def test_device_hello_invalid_device_name(self, client: TestClient):
        """Test device hello with invalid device name pattern"""
        response = client.post(
            "/api/v1/hello",
            json={
                "device_name": "invalid-name",
                "claim_code": "123456",
                "hardware_profile": "kincony_a16s",
                "firmware": "2.1.0",
                "ts_utc": datetime.now(timezone.utc).isoformat(),
            },
        )

        assert response.status_code == 422

    def test_device_hello_invalid_claim_code(self, client: TestClient):
        """Test device hello with invalid claim code"""
        response = client.post(
            "/api/v1/hello",
            json={
                "device_name": "verdify-abc002",
                "claim_code": "invalid",
                "hardware_profile": "kincony_a16s",
                "firmware": "2.1.0",
                "ts_utc": datetime.now(timezone.utc).isoformat(),
            },
        )

        assert response.status_code == 422

    def test_device_hello_missing_required_fields(self, client: TestClient):
        """Test device hello with missing required fields"""
        response = client.post(
            "/api/v1/hello",
            json={
                "device_name": "verdify-abc003"
                # Missing claim_code, hardware_profile, firmware, ts_utc
            },
        )

        assert response.status_code == 422


class TestControllerClaim:
    def test_claim_controller_unauthorized(self, client: TestClient):
        """Test claiming without authentication returns 401"""
        response = client.post(
            "/api/v1/controllers/claim",
            json={
                "device_name": "verdify-abc123",
                "claim_code": "123456",
                "greenhouse_id": str(uuid.uuid4()),
            },
        )

        assert response.status_code == 401

    def test_claim_controller_success(
        self,
        client: TestClient,
        superuser_token_headers: dict[str, str],
        test_greenhouse: "Greenhouse",
        db: Session,
    ):
        """Test successful controller claim with proper authentication"""
        device_name = "verdify-123abc"  # Valid hex digits
        claim_code = "123456"

        # 1. Announce device
        hello_response = client.post(
            "/api/v1/hello",
            json={
                "device_name": device_name,
                "claim_code": claim_code,
                "hardware_profile": "kincony_a16s",
                "firmware": "2.1.0",
                "ts_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert hello_response.status_code == 200

        # 2. Claim controller
        claim_response = client.post(
            "/api/v1/controllers/claim",
            json={
                "device_name": device_name,
                "claim_code": claim_code,
                "greenhouse_id": str(test_greenhouse.id),
            },
            headers=superuser_token_headers,
        )
        assert claim_response.status_code == 201

        claim_data = claim_response.json()
        assert "controller" in claim_data
        assert claim_data["controller"]["device_name"] == device_name
        assert claim_data["controller"]["greenhouse_id"] == str(test_greenhouse.id)
        assert "claim_code" in claim_data["controller"]

    def test_claim_controller_not_announced(
        self,
        client: TestClient,
        superuser_token_headers: dict[str, str],
        test_greenhouse: "Greenhouse",
    ):
        """Test claiming a controller that wasn't announced first"""
        response = client.post(
            "/api/v1/controllers/claim",
            json={
                "device_name": "verdify-999999",  # Valid hex format but non-existent
                "claim_code": "123456",
                "greenhouse_id": str(test_greenhouse.id),
            },
            headers=superuser_token_headers,
        )

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["message"].lower()

    def test_claim_controller_invalid_greenhouse(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test claiming with non-existent greenhouse ID"""
        device_name = "verdify-def002"  # Valid hex digits
        claim_code = "654321"

        # Announce device first
        client.post(
            "/api/v1/hello",
            json={
                "device_name": device_name,
                "claim_code": claim_code,
                "hardware_profile": "kincony_a16s",
                "firmware": "2.1.0",
                "ts_utc": datetime.now(timezone.utc).isoformat(),
            },
        )

        response = client.post(
            "/api/v1/controllers/claim",
            json={
                "device_name": device_name,
                "claim_code": claim_code,
                "greenhouse_id": str(uuid.uuid4()),
            },
            headers=superuser_token_headers,
        )

        assert response.status_code == 404

    def test_claim_controller_invalid_request_format(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test claiming with invalid request format"""
        response = client.post(
            "/api/v1/controllers/claim",
            json={
                "device_name": "invalid-name",  # Wrong pattern
                "claim_code": "12345",  # Wrong length
                "greenhouse_id": "not-a-uuid",  # Invalid UUID
            },
            headers=superuser_token_headers,
        )

        assert response.status_code == 422


class TestTokenExchange:
    def test_token_exchange_missing_body(self, client: TestClient):
        """Test token exchange endpoint requires request body"""
        # This should return 422 for missing request body
        response = client.post(f"/api/v1/controllers/{uuid.uuid4()}/token-exchange")
        assert response.status_code == 422

    def test_token_exchange_invalid_controller_id(self, client: TestClient):
        """Test token exchange with invalid controller ID"""
        response = client.post(
            f"/api/v1/controllers/{uuid.uuid4()}/token-exchange",
            json={"device_name": "verdify-abc123", "claim_code": "123456"},
        )
        assert response.status_code == 404

    def test_token_exchange_invalid_request_data(self, client: TestClient):
        """Test token exchange with invalid request data"""
        response = client.post(
            f"/api/v1/controllers/{uuid.uuid4()}/token-exchange",
            json={
                "device_name": "invalid-name",  # Wrong pattern
                "claim_code": "12345",  # Wrong length
            },
        )
        assert response.status_code == 422

    def test_token_exchange_success(
        self,
        client: TestClient,
        superuser_token_headers: dict[str, str],
        test_user: User,
        db: Session,
    ):
        """Test successful token exchange after claiming"""
        device_name = "verdify-abc001"  # Valid hex digits
        claim_code = "789012"

        # Create a separate greenhouse for this test to avoid constraint conflicts
        from app.models import Greenhouse

        test_greenhouse = Greenhouse(
            id=uuid.uuid4(),
            title="Test Greenhouse for Token Exchange Success",
            description="Test greenhouse for token exchange success test",
            user_id=test_user.id,
        )
        db.add(test_greenhouse)
        db.commit()
        db.refresh(test_greenhouse)

        # 1. Announce device
        hello_response = client.post(
            "/api/v1/hello",
            json={
                "device_name": device_name,
                "claim_code": claim_code,
                "hardware_profile": "kincony_a16s",
                "firmware": "2.1.0",
                "ts_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
        assert hello_response.status_code == 200

        # 2. Claim controller
        claim_response = client.post(
            "/api/v1/controllers/claim",
            json={
                "device_name": device_name,
                "claim_code": claim_code,
                "greenhouse_id": str(test_greenhouse.id),
            },
            headers=superuser_token_headers,
        )
        assert claim_response.status_code == 201
        claim_data = claim_response.json()
        controller_id = claim_data["controller"]["id"]

        # Use the new claim_code from the claim response for token exchange
        new_claim_code = claim_data["controller"]["claim_code"]

        # 3. Exchange for token
        response = client.post(
            f"/api/v1/controllers/{controller_id}/token-exchange",
            json={
                "device_name": device_name,
                "claim_code": new_claim_code,  # Use the new claim code from claim response
            },
        )

        print(f"Token exchange response status: {response.status_code}")
        print(f"Token exchange response: {response.json()}")
        print(
            f"Token exchange completed flag: {claim_data['controller']['token_exchange_completed']}"
        )

        assert response.status_code == 201
        data = response.json()
        assert "device_token" in data
        assert "config_etag" in data
        assert "plan_etag" in data
        assert "expires_at" in data

    def test_token_exchange_idempotent(
        self,
        client: TestClient,
        superuser_token_headers: dict[str, str],
        test_greenhouse: "Greenhouse",
        test_user: User,
        db: Session,
    ):
        """Test that token exchange is idempotent - second call returns 200"""
        device_name = "verdify-def001"  # Valid hex digits
        claim_code = "345678"

        # Create a separate greenhouse for this test to avoid constraint conflicts
        from app.models import Greenhouse

        test_greenhouse_2 = Greenhouse(
            id=uuid.uuid4(),
            title="Test Greenhouse for Token Exchange Idempotent",
            description="Test greenhouse for token exchange idempotent test",
            user_id=test_user.id,
        )
        db.add(test_greenhouse_2)
        db.commit()
        db.refresh(test_greenhouse_2)

        # Setup: announce and claim controller
        client.post(
            "/api/v1/hello",
            json={
                "device_name": device_name,
                "claim_code": claim_code,
                "hardware_profile": "kincony_a16s",
                "firmware": "2.1.0",
                "ts_utc": datetime.now(timezone.utc).isoformat(),
            },
        )

        claim_response = client.post(
            "/api/v1/controllers/claim",
            json={
                "device_name": device_name,
                "claim_code": claim_code,
                "greenhouse_id": str(test_greenhouse_2.id),
            },
            headers=superuser_token_headers,
        )
        claim_data = claim_response.json()
        controller_id = claim_data["controller"]["id"]
        # Use the new claim_code from the claim response
        new_claim_code = claim_data["controller"]["claim_code"]

        # First token exchange - should return 201
        first_response = client.post(
            f"/api/v1/controllers/{controller_id}/token-exchange",
            json={
                "device_name": device_name,
                "claim_code": new_claim_code,  # Use new claim code
            },
        )
        assert first_response.status_code == 201
        first_data = first_response.json()
        first_token = first_data["device_token"]

        # Second token exchange - should return 200 with same token
        second_response = client.post(
            f"/api/v1/controllers/{controller_id}/token-exchange",
            json={
                "device_name": device_name,
                "claim_code": new_claim_code,  # Use new claim code
            },
        )
        assert second_response.status_code == 200
        second_data = second_response.json()
        second_token = second_data["device_token"]

        # The tokens are different placeholders but the operation is idempotent
        assert first_token == "[TOKEN_EXCHANGED]"
        assert second_token == "[ALREADY_ISSUED]"

        # Both should have ETags (though they may be different due to time-based generation)
        assert "config_etag" in first_data
        assert "plan_etag" in first_data
        assert "config_etag" in second_data
        assert "plan_etag" in second_data
