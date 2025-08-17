"""
Tests for config endpoints.

Tests config publishing, diff generation, and device config fetch with ETag support.
"""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import ConfigSnapshot, Controller, Greenhouse


class TestConfigAdmin:
    """Test admin config management endpoints."""

    def test_publish_config_dry_run(
        self,
        client: TestClient,
        test_greenhouse: Greenhouse,
        superuser_token_headers: dict[str, str],
    ):
        """Test dry run config publish (preview mode)."""
        request_data = {"dry_run": True}

        response = client.post(
            f"/greenhouses/{test_greenhouse.id}/config/publish",
            json=request_data,
            headers=superuser_token_headers,
        )
        assert response.status_code == 200  # 200 for dry run

        data = response.json()
        assert data["published"] is False
        assert "version" in data
        assert "etag" in data
        assert "payload" in data
        assert data["payload"]["greenhouse"]["id"] == str(test_greenhouse.id)

    def test_publish_config_success(
        self,
        client: TestClient,
        test_greenhouse: Greenhouse,
        superuser_token_headers: dict[str, str],
    ):
        """Test successful config publish creates snapshot."""
        request_data = {"dry_run": False}

        response = client.post(
            f"/greenhouses/{test_greenhouse.id}/config/publish",
            json=request_data,
            headers=superuser_token_headers,
        )
        assert response.status_code == 201  # 201 for actual publish

        data = response.json()
        assert data["published"] is True
        assert "version" in data
        assert "etag" in data
        assert "payload" in data
        assert len(data["errors"]) == 0

    def test_publish_config_greenhouse_not_found(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test publish config for non-existent greenhouse returns 404."""
        fake_id = "123e4567-e89b-12d3-a456-426614174000"
        request_data = {"dry_run": True}

        response = client.post(
            f"/greenhouses/{fake_id}/config/publish",
            json=request_data,
            headers=superuser_token_headers,
        )
        assert response.status_code == 404

    def test_publish_config_unauthorized(
        self, client: TestClient, test_greenhouse: Greenhouse
    ):
        """Test config publish without auth returns 401."""
        request_data = {"dry_run": True}

        response = client.post(
            f"/greenhouses/{test_greenhouse.id}/config/publish", json=request_data
        )
        assert response.status_code == 401

    def test_get_config_diff_no_snapshot(
        self,
        client: TestClient,
        test_greenhouse: Greenhouse,
        superuser_token_headers: dict[str, str],
    ):
        """Test config diff when no published snapshots exist."""
        response = client.get(
            f"/greenhouses/{test_greenhouse.id}/config/diff",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["added"] == ["*"]  # Everything is "added" when no baseline
        assert data["removed"] == []
        assert data["changed"] == []

    def test_get_config_diff_with_snapshot(
        self,
        client: TestClient,
        test_greenhouse: Greenhouse,
        test_config_snapshot: ConfigSnapshot,
        superuser_token_headers: dict[str, str],
    ):
        """Test config diff with existing snapshot."""
        response = client.get(
            f"/greenhouses/{test_greenhouse.id}/config/diff",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert "added" in data
        assert "removed" in data
        assert "changed" in data


class TestConfigDevice:
    """Test device config fetch endpoints."""

    def test_get_config_by_device_name_success(
        self,
        client: TestClient,
        test_controller: Controller,
        test_config_snapshot: ConfigSnapshot,
        device_token_headers: dict[str, str],
    ):
        """Test successful config fetch by device name."""
        response = client.get(
            f"/controllers/by-name/{test_controller.device_name}/config",
            headers=device_token_headers,
        )
        assert response.status_code == 200

        # Check ETag header
        assert "ETag" in response.headers
        assert response.headers["ETag"] == f'"{test_config_snapshot.etag}"'

        # Check Last-Modified header
        assert "Last-Modified" in response.headers

        # Check payload
        data = response.json()
        assert data["version"] == test_config_snapshot.version
        assert data["greenhouse"]["id"] == str(test_config_snapshot.greenhouse_id)

    def test_get_config_by_device_name_etag_match(
        self,
        client: TestClient,
        test_controller: Controller,
        test_config_snapshot: ConfigSnapshot,
        device_token_headers: dict[str, str],
    ):
        """Test config fetch with matching ETag returns 304."""
        headers = {
            **device_token_headers,
            "If-None-Match": f'"{test_config_snapshot.etag}"',
        }

        response = client.get(
            f"/controllers/by-name/{test_controller.device_name}/config",
            headers=headers,
        )
        assert response.status_code == 304

    def test_get_config_by_device_name_wrong_device(
        self, client: TestClient, device_token_headers: dict[str, str]
    ):
        """Test config fetch with mismatched device name returns 403."""
        response = client.get(
            "/controllers/by-name/verdify-wrongdev/config", headers=device_token_headers
        )
        assert response.status_code == 403

    def test_get_config_by_device_name_no_greenhouse(
        self, client: TestClient, db: Session, device_token_headers: dict[str, str]
    ):
        """Test config fetch for controller without greenhouse returns 404."""
        # Create controller without greenhouse
        from datetime import datetime, timezone

        from app.core.security import create_device_token_hash, generate_device_token
        from app.models import Controller

        device_token = generate_device_token()
        device_token_hash = create_device_token_hash(device_token)

        controller = Controller(
            device_name="verdify-noghouse",
            label="Test Controller No Greenhouse",
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

        response = client.get(
            "/controllers/by-name/verdify-noghouse/config", headers=headers
        )
        assert response.status_code == 404

    def test_get_config_by_device_name_unauthorized(
        self, client: TestClient, test_controller: Controller
    ):
        """Test config fetch without device token returns 401."""
        response = client.get(
            f"/controllers/by-name/{test_controller.device_name}/config"
        )
        assert response.status_code == 401

    def test_get_config_me_success(
        self,
        client: TestClient,
        test_controller: Controller,
        test_config_snapshot: ConfigSnapshot,
        device_token_headers: dict[str, str],
    ):
        """Test successful config fetch using 'me' endpoint."""
        response = client.get("/controllers/me/config", headers=device_token_headers)
        assert response.status_code == 200

        # Check ETag header
        assert "ETag" in response.headers
        assert response.headers["ETag"] == f'"{test_config_snapshot.etag}"'

        # Check payload
        data = response.json()
        assert data["version"] == test_config_snapshot.version

    def test_get_config_me_etag_match(
        self,
        client: TestClient,
        test_config_snapshot: ConfigSnapshot,
        device_token_headers: dict[str, str],
    ):
        """Test config fetch 'me' endpoint with matching ETag returns 304."""
        headers = {
            **device_token_headers,
            "If-None-Match": f'"{test_config_snapshot.etag}"',
        }

        response = client.get("/controllers/me/config", headers=headers)
        assert response.status_code == 304

    def test_get_config_me_no_config_snapshot(
        self, client: TestClient, db: Session, device_token_headers: dict[str, str]
    ):
        """Test config fetch when no snapshot exists returns 404."""
        # Create new greenhouse without config snapshot
        import uuid
        from datetime import datetime, timezone

        from app.core.security import create_device_token_hash, generate_device_token
        from app.models import Controller, Greenhouse

        # Create test user and greenhouse without snapshot
        greenhouse = Greenhouse(
            id=uuid.uuid4(),
            name="Test Greenhouse No Config",
            location="Test Location",
            user_id=uuid.uuid4(),  # Use a random user ID
        )
        db.add(greenhouse)

        device_token = generate_device_token()
        device_token_hash = create_device_token_hash(device_token)

        controller = Controller(
            device_name="verdify-noconf",
            label="Test Controller No Config",
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

        response = client.get("/controllers/me/config", headers=headers)
        assert response.status_code == 404
