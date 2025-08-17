"""
Tests for plan management endpoints.

Tests plan CRUD, device plan fetch with ETag support, and plan activation logic.
"""
import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Controller, Greenhouse, Plan


class TestPlanCRUD:
    """Test plan CRUD endpoints."""

    def test_list_plans_success(
        self,
        client: TestClient,
        test_greenhouse: Greenhouse,
        test_plan: Plan,
        superuser_token_headers: dict[str, str],
    ):
        """Test successful plan listing with pagination."""
        response = client.get(
            f"/plans?greenhouse_id={test_greenhouse.id}&page=1&page_size=10",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data
        assert len(data["data"]) >= 1

        # Check plan structure
        plan_data = data["data"][0]
        assert "id" in plan_data
        assert "version" in plan_data
        assert "is_active" in plan_data
        assert "payload" in plan_data

    def test_list_plans_filter_active(
        self,
        client: TestClient,
        test_greenhouse: Greenhouse,
        test_plan: Plan,
        superuser_token_headers: dict[str, str],
    ):
        """Test plan listing filtered to active plans only."""
        response = client.get(
            f"/plans?greenhouse_id={test_greenhouse.id}&active=true&page=1&page_size=10",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["data"]) >= 1

        # All returned plans should be active
        for plan in data["data"]:
            assert plan["is_active"] is True

    def test_list_plans_missing_greenhouse_id(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test plan listing without greenhouse_id returns 400."""
        response = client.get(
            "/plans?page=1&page_size=10", headers=superuser_token_headers
        )
        assert response.status_code == 400
        assert "greenhouse_id" in response.json()["detail"]

    def test_list_plans_invalid_greenhouse(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test plan listing for non-existent greenhouse returns 404."""
        fake_id = "123e4567-e89b-12d3-a456-426614174000"
        response = client.get(
            f"/plans?greenhouse_id={fake_id}&page=1&page_size=10",
            headers=superuser_token_headers,
        )
        assert response.status_code == 404

    def test_list_plans_unauthorized(
        self, client: TestClient, test_greenhouse: Greenhouse
    ):
        """Test plan listing without auth returns 401."""
        response = client.get(f"/plans?greenhouse_id={test_greenhouse.id}")
        assert response.status_code == 401

    def test_create_plan_success(
        self,
        client: TestClient,
        db: Session,
        test_greenhouse: Greenhouse,
        superuser_token_headers: dict[str, str],
    ):
        """Test successful plan creation."""
        payload = {
            "version": 2,
            "greenhouse_id": str(test_greenhouse.id),
            "setpoints": {"temperature": 23.0, "humidity": 65.0},
            "irrigation": {"frequency": "twice_daily", "duration": 20},
            "phases": [{"name": "vegetative", "duration_days": 30, "light_hours": 18}],
        }

        request_data = {
            "greenhouse_id": str(test_greenhouse.id),
            "payload": payload,
            "is_active": True,
        }

        response = client.post(
            "/plans", json=request_data, headers=superuser_token_headers
        )
        assert response.status_code == 201

        data = response.json()
        assert data["greenhouse_id"] == str(test_greenhouse.id)
        assert data["is_active"] is True
        assert data["payload"] == payload
        assert "etag" in data
        assert "version" in data

        # Verify plan was created in database
        plan = db.get(Plan, data["id"])
        assert plan is not None
        assert plan.is_active is True

    def test_create_plan_deactivates_existing(
        self,
        client: TestClient,
        db: Session,
        test_greenhouse: Greenhouse,
        test_plan: Plan,
        superuser_token_headers: dict[str, str],
    ):
        """Test creating active plan deactivates existing active plans."""
        # Verify test_plan is initially active
        assert test_plan.is_active is True

        payload = {
            "version": 2,
            "greenhouse_id": str(test_greenhouse.id),
            "setpoints": {"temperature": 25.0, "humidity": 70.0},
        }

        request_data = {
            "greenhouse_id": str(test_greenhouse.id),
            "payload": payload,
            "is_active": True,
        }

        response = client.post(
            "/plans", json=request_data, headers=superuser_token_headers
        )
        assert response.status_code == 201

        # Verify old plan was deactivated
        db.refresh(test_plan)
        assert test_plan.is_active is False

    def test_create_plan_invalid_greenhouse(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test plan creation for non-existent greenhouse returns 404."""
        fake_id = "123e4567-e89b-12d3-a456-426614174000"

        request_data = {
            "greenhouse_id": fake_id,
            "payload": {"version": 1},
            "is_active": False,
        }

        response = client.post(
            "/plans", json=request_data, headers=superuser_token_headers
        )
        assert response.status_code == 404


class TestPlanDeviceEndpoints:
    """Test device plan fetch endpoints."""

    def test_get_plan_by_controller_id_success(
        self,
        client: TestClient,
        test_controller: Controller,
        test_plan: Plan,
        device_token_headers: dict[str, str],
    ):
        """Test successful plan fetch by controller ID."""
        response = client.get(
            f"/controllers/{test_controller.id}/plan", headers=device_token_headers
        )
        assert response.status_code == 200

        # Check ETag header
        assert "ETag" in response.headers
        assert response.headers["ETag"] == f'"{test_plan.etag}"'

        # Check Last-Modified header
        assert "Last-Modified" in response.headers

        # Check payload
        data = response.json()
        assert data["version"] == test_plan.version
        assert data["greenhouse_id"] == str(test_plan.greenhouse_id)

    def test_get_plan_by_controller_id_etag_match(
        self,
        client: TestClient,
        test_controller: Controller,
        test_plan: Plan,
        device_token_headers: dict[str, str],
    ):
        """Test plan fetch with matching ETag returns 304."""
        headers = {**device_token_headers, "If-None-Match": f'"{test_plan.etag}"'}

        response = client.get(
            f"/controllers/{test_controller.id}/plan", headers=headers
        )
        assert response.status_code == 304

    def test_get_plan_by_controller_id_wrong_controller(
        self, client: TestClient, device_token_headers: dict[str, str]
    ):
        """Test plan fetch with mismatched controller ID returns 403."""
        fake_controller_id = "123e4567-e89b-12d3-a456-426614174000"

        response = client.get(
            f"/controllers/{fake_controller_id}/plan", headers=device_token_headers
        )
        assert response.status_code == 403

    def test_get_plan_by_controller_id_no_active_plan(
        self, client: TestClient, db: Session, device_token_headers: dict[str, str]
    ):
        """Test plan fetch when no active plan exists returns 404."""
        # Create new greenhouse and controller without active plan
        from datetime import datetime, timezone

        from app.core.security import create_device_token_hash, generate_device_token
        from app.models import Controller, Greenhouse

        greenhouse = Greenhouse(
            id=uuid.uuid4(),
            name="Test Greenhouse No Plan",
            location="Test Location",
            user_id=uuid.uuid4(),
        )
        db.add(greenhouse)

        device_token = generate_device_token()
        device_token_hash = create_device_token_hash(device_token)

        controller = Controller(
            device_name="verdify-noplan",
            label="Test Controller No Plan",
            hardware_profile="v1.0",
            firmware="1.0.0",
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            greenhouse_id=greenhouse.id,
            claim_code="123456",
            device_token_hash=device_token_hash,
        )
        db.add(controller)
        db.commit()

        headers = {"X-Device-Token": device_token}

        response = client.get(f"/controllers/{controller.id}/plan", headers=headers)
        assert response.status_code == 404

    def test_get_plan_by_controller_id_unauthorized(
        self, client: TestClient, test_controller: Controller
    ):
        """Test plan fetch without device token returns 401."""
        response = client.get(f"/controllers/{test_controller.id}/plan")
        assert response.status_code == 401

    def test_get_plan_me_success(
        self,
        client: TestClient,
        test_controller: Controller,
        test_plan: Plan,
        device_token_headers: dict[str, str],
    ):
        """Test successful plan fetch using 'me' endpoint."""
        response = client.get("/controllers/me/plan", headers=device_token_headers)
        assert response.status_code == 200

        # Check ETag header
        assert "ETag" in response.headers
        assert response.headers["ETag"] == f'"{test_plan.etag}"'

        # Check payload
        data = response.json()
        assert data["version"] == test_plan.version

    def test_get_plan_me_etag_match(
        self, client: TestClient, test_plan: Plan, device_token_headers: dict[str, str]
    ):
        """Test plan fetch 'me' endpoint with matching ETag returns 304."""
        headers = {**device_token_headers, "If-None-Match": f'"{test_plan.etag}"'}

        response = client.get("/controllers/me/plan", headers=headers)
        assert response.status_code == 304

    def test_get_plan_me_no_greenhouse(
        self, client: TestClient, db: Session, device_token_headers: dict[str, str]
    ):
        """Test plan fetch for controller without greenhouse returns 404."""
        # Create controller without greenhouse
        from datetime import datetime, timezone

        from app.core.security import create_device_token_hash, generate_device_token
        from app.models import Controller

        device_token = generate_device_token()
        device_token_hash = create_device_token_hash(device_token)

        controller = Controller(
            device_name="verdify-noghouse2",
            label="Test Controller No Greenhouse 2",
            hardware_profile="v1.0",
            firmware="1.0.0",
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            greenhouse_id=None,  # type: ignore
            claim_code="123456",
            device_token_hash=device_token_hash,
        )
        db.add(controller)
        db.commit()

        headers = {"X-Device-Token": device_token}

        response = client.get("/controllers/me/plan", headers=headers)
        assert response.status_code == 404


class TestPlanVersioning:
    """Test plan versioning logic."""

    def test_plan_version_increment(
        self,
        client: TestClient,
        db: Session,
        test_greenhouse: Greenhouse,
        test_plan: Plan,
        superuser_token_headers: dict[str, str],
    ):
        """Test that plan versions increment automatically."""
        # Create first plan (test_plan has version 1)
        assert test_plan.version == 1

        # Create second plan
        request_data = {
            "greenhouse_id": str(test_greenhouse.id),
            "payload": {"version": 2, "setpoints": {"temperature": 24.0}},
            "is_active": False,
        }

        response = client.post(
            "/plans", json=request_data, headers=superuser_token_headers
        )
        assert response.status_code == 201

        data = response.json()
        assert data["version"] == 2  # Should auto-increment

    def test_plan_etag_generation(
        self,
        client: TestClient,
        test_greenhouse: Greenhouse,
        superuser_token_headers: dict[str, str],
    ):
        """Test that plan ETags are generated properly."""
        request_data = {
            "greenhouse_id": str(test_greenhouse.id),
            "payload": {"version": 1, "test": "etag"},
            "is_active": False,
        }

        response = client.post(
            "/plans", json=request_data, headers=superuser_token_headers
        )
        assert response.status_code == 201

        data = response.json()
        etag = data["etag"]

        # ETag should follow pattern: plan:v{version}:{sha8}
        assert etag.startswith("plan:v")
        assert ":1:" in etag  # version 1
        assert len(etag.split(":")[-1]) == 8  # 8-character hash
