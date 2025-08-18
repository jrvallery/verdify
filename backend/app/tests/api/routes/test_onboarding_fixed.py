import uuid

from fastapi.testclient import TestClient
from sqlmodel import select

from app.api.deps import get_db
from app.main import app
from app.models import Controller

client = TestClient(app)


class TestDeviceHello:
    def test_device_hello_success(self, test_session):
        """Test device hello endpoint returns proper response"""
        app.dependency_overrides[get_db] = lambda: test_session
        try:
            response = client.post(
                "/api/v1/hello",
                json={
                    "device_name": "test-controller-hello-001",
                    "device_type": "controller",
                    "hw_version": "1.0.0",
                    "sw_version": "2.1.0",
                },
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Hello from Verdify"
        assert data["device_name"] == "test-controller-hello-001"
        assert data["api_version"] == "1.0"
        assert "server_time" in data

    def test_device_hello_invalid_device_type(self, test_session):
        """Test device hello with invalid device type"""
        app.dependency_overrides[get_db] = lambda: test_session
        try:
            response = client.post(
                "/api/v1/hello",
                json={
                    "device_name": "test-controller-hello-002",
                    "device_type": "invalid",
                    "hw_version": "1.0.0",
                    "sw_version": "2.1.0",
                },
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 422


class TestControllerClaim:
    def test_claim_controller_success(self, test_session, test_greenhouse):
        """Test claiming a controller successfully"""
        app.dependency_overrides[get_db] = lambda: test_session
        try:
            device_name = "test-controller-claim-001"
            # First announce the device
            client.post(
                "/api/v1/hello",
                json={
                    "device_name": device_name,
                    "device_type": "controller",
                    "hw_version": "1.0.0",
                    "sw_version": "2.1.0",
                },
            )

            # Then claim it
            response = client.post(
                "/api/v1/controllers/claim",
                json={
                    "device_name": device_name,
                    "greenhouse_id": str(test_greenhouse.id),
                },
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        data = response.json()
        assert data["device_name"] == device_name
        assert data["greenhouse_id"] == str(test_greenhouse.id)
        assert data["is_active"] is True

        # Verify controller was created in DB
        controller = test_session.exec(
            select(Controller).where(Controller.device_name == device_name)
        ).first()
        assert controller is not None
        assert controller.greenhouse_id == test_greenhouse.id

    def test_claim_controller_not_found(self, test_session, test_greenhouse):
        """Test claiming a controller that doesn't exist"""
        app.dependency_overrides[get_db] = lambda: test_session
        try:
            response = client.post(
                "/api/v1/controllers/claim",
                json={
                    "device_name": "nonexistent-controller",
                    "greenhouse_id": str(test_greenhouse.id),
                },
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404

    def test_claim_controller_already_claimed(self, test_session, test_controller):
        """Test claiming a controller that's already claimed"""
        app.dependency_overrides[get_db] = lambda: test_session
        try:
            response = client.post(
                "/api/v1/controllers/claim",
                json={
                    "device_name": test_controller.device_name,
                    "greenhouse_id": str(test_controller.greenhouse_id),
                },
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 409

    def test_claim_invalid_greenhouse(self, test_session):
        """Test claiming with invalid greenhouse ID"""
        app.dependency_overrides[get_db] = lambda: test_session
        try:
            device_name = "test-controller-claim-invalid"
            # Announce device first
            client.post(
                "/api/v1/hello",
                json={
                    "device_name": device_name,
                    "device_type": "controller",
                    "hw_version": "1.0.0",
                    "sw_version": "2.1.0",
                },
            )

            response = client.post(
                "/api/v1/controllers/claim",
                json={"device_name": device_name, "greenhouse_id": str(uuid.uuid4())},
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404


class TestTokenExchange:
    def test_token_exchange_success(self, test_session, test_controller):
        """Test successful token exchange"""
        app.dependency_overrides[get_db] = lambda: test_session
        try:
            response = client.post(
                f"/api/v1/controllers/{test_controller.id}/token-exchange"
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    def test_token_exchange_controller_not_found(self, test_session):
        """Test token exchange with non-existent controller"""
        app.dependency_overrides[get_db] = lambda: test_session
        try:
            response = client.post(f"/api/v1/controllers/{uuid.uuid4()}/token-exchange")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 404

    def test_token_exchange_inactive_controller(self, test_session, test_controller):
        """Test token exchange with inactive controller"""
        app.dependency_overrides[get_db] = lambda: test_session
        try:
            # Deactivate the controller
            test_controller.is_active = False
            test_session.add(test_controller)
            test_session.commit()

            response = client.post(
                f"/api/v1/controllers/{test_controller.id}/token-exchange"
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 403


class TestTokenRotation:
    def test_token_rotation_success(
        self, test_session, test_controller, device_token_headers
    ):
        """Test successful token rotation"""
        app.dependency_overrides[get_db] = lambda: test_session
        try:
            response = client.post(
                f"/api/v1/controllers/{test_controller.id}/rotate-token",
                headers=device_token_headers,
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    def test_token_revocation_success(
        self, test_session, test_controller, device_token_headers
    ):
        """Test successful token revocation"""
        app.dependency_overrides[get_db] = lambda: test_session
        try:
            response = client.post(
                f"/api/v1/controllers/{test_controller.id}/revoke-token",
                headers=device_token_headers,
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 204

    def test_unauthorized_token_rotation(self, test_session, test_controller):
        """Test token rotation without proper authorization"""
        app.dependency_overrides[get_db] = lambda: test_session
        try:
            response = client.post(
                f"/api/v1/controllers/{test_controller.id}/rotate-token"
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 401
