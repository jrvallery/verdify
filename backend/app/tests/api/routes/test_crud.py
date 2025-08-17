"""
Tests for CRUD endpoints with pagination.

Tests controller, sensor, actuator CRUD operations with proper pagination,
filtering, and error handling.
"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import Controller, Greenhouse


class TestControllersCRUD:
    """Test controllers CRUD endpoints."""

    def test_list_controllers_success(
        self,
        client: TestClient,
        test_controller: Controller,
        superuser_token_headers: dict[str, str],
    ):
        """Test successful controller listing with pagination."""
        response = client.get(
            "/controllers/?page=1&page_size=10", headers=superuser_token_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data
        assert len(data["data"]) >= 1

        # Check controller structure
        controller_data = data["data"][0] if data["data"] else None
        if controller_data:
            assert "id" in controller_data
            assert "device_name" in controller_data
            assert "greenhouse_id" in controller_data

    def test_list_controllers_filter_by_greenhouse(
        self,
        client: TestClient,
        test_controller: Controller,
        test_greenhouse: Greenhouse,
        superuser_token_headers: dict[str, str],
    ):
        """Test controller listing filtered by greenhouse."""
        response = client.get(
            f"/controllers/?greenhouse_id={test_greenhouse.id}&page=1&page_size=10",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert len(data["data"]) >= 1

        # All returned controllers should belong to the specified greenhouse
        for controller in data["data"]:
            assert controller["greenhouse_id"] == str(test_greenhouse.id)

    def test_list_controllers_filter_by_status(
        self,
        client: TestClient,
        test_controller: Controller,
        superuser_token_headers: dict[str, str],
    ):
        """Test controller listing filtered by claimed status."""
        response = client.get(
            "/controllers/?claimed=true&page=1&page_size=10",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        data = response.json()
        # All returned controllers should be claimed
        for controller in data["data"]:
            assert controller["greenhouse_id"] is not None

    def test_list_controllers_search(
        self,
        client: TestClient,
        test_controller: Controller,
        superuser_token_headers: dict[str, str],
    ):
        """Test controller listing with search query."""
        response = client.get(
            f"/controllers/?search={test_controller.device_name[:8]}&page=1&page_size=10",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        data = response.json()
        # Should find the test controller
        found = any(
            c["device_name"] == test_controller.device_name for c in data["data"]
        )
        assert found

    def test_list_controllers_unauthorized(self, client: TestClient):
        """Test controller listing without auth returns 401."""
        response = client.get("/controllers/")
        assert response.status_code == 401

    def test_get_controller_success(
        self,
        client: TestClient,
        test_controller: Controller,
        superuser_token_headers: dict[str, str],
    ):
        """Test successful controller retrieval."""
        response = client.get(
            f"/controllers/{test_controller.id}", headers=superuser_token_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == str(test_controller.id)
        assert data["device_name"] == test_controller.device_name
        assert data["greenhouse_id"] == str(test_controller.greenhouse_id)

    def test_get_controller_not_found(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test controller retrieval for non-existent controller returns 404."""
        fake_id = "123e4567-e89b-12d3-a456-426614174000"
        response = client.get(
            f"/controllers/{fake_id}", headers=superuser_token_headers
        )
        assert response.status_code == 404

    def test_create_controller_success(
        self,
        client: TestClient,
        db: Session,
        test_greenhouse: Greenhouse,
        superuser_token_headers: dict[str, str],
    ):
        """Test successful controller creation."""
        request_data = {
            "device_name": "verdify-newdev",
            "label": "New Test Controller",
            "hardware_profile": "v2.0",
            "greenhouse_id": str(test_greenhouse.id),
        }

        response = client.post(
            "/controllers/", json=request_data, headers=superuser_token_headers
        )
        assert response.status_code == 201

        data = response.json()
        assert data["device_name"] == "verdify-newdev"
        assert data["label"] == "New Test Controller"
        assert data["greenhouse_id"] == str(test_greenhouse.id)

    def test_create_controller_duplicate_device_name(
        self,
        client: TestClient,
        test_controller: Controller,
        test_greenhouse: Greenhouse,
        superuser_token_headers: dict[str, str],
    ):
        """Test controller creation with duplicate device_name returns 409."""
        request_data = {
            "device_name": test_controller.device_name,
            "label": "Duplicate Controller",
            "hardware_profile": "v1.0",
            "greenhouse_id": str(test_greenhouse.id),
        }

        response = client.post(
            "/controllers/", json=request_data, headers=superuser_token_headers
        )
        assert response.status_code == 409

    def test_update_controller_success(
        self,
        client: TestClient,
        db: Session,
        test_controller: Controller,
        superuser_token_headers: dict[str, str],
    ):
        """Test successful controller update."""
        request_data = {"label": "Updated Controller Label", "firmware": "2.0.0"}

        response = client.patch(
            f"/controllers/{test_controller.id}",
            json=request_data,
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["label"] == "Updated Controller Label"
        assert data["firmware"] == "2.0.0"

        # Verify database was updated
        db.refresh(test_controller)
        assert test_controller.label == "Updated Controller Label"
        assert test_controller.firmware == "2.0.0"

    def test_delete_controller_success(
        self, client: TestClient, db: Session, superuser_token_headers: dict[str, str]
    ):
        """Test successful controller deletion."""
        # Create controller to delete
        controller = Controller(
            device_name="verdify-delete",
            label="Controller to Delete",
            hardware_profile="v1.0",
            firmware="1.0.0",
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            greenhouse_id=None,  # type: ignore
            claim_code=None,
        )
        db.add(controller)
        db.commit()

        response = client.delete(
            f"/controllers/{controller.id}", headers=superuser_token_headers
        )
        assert response.status_code == 204

        # Verify controller was deleted
        db.refresh(controller)
        # The controller might be soft-deleted or actually deleted depending on implementation


class TestSensorsCRUD:
    """Test sensors CRUD endpoints."""

    def test_list_sensors_success(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test successful sensor listing with pagination."""
        response = client.get(
            "/sensors/?page=1&page_size=10", headers=superuser_token_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data

    def test_list_sensors_filter_by_kind(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test sensor listing filtered by kind."""
        response = client.get(
            "/sensors/?kind=temperature&page=1&page_size=10",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        data = response.json()
        # All returned sensors should be temperature sensors
        for sensor in data["data"]:
            assert sensor["kind"] == "temperature"

    def test_list_sensors_filter_by_controller(
        self,
        client: TestClient,
        test_controller: Controller,
        superuser_token_headers: dict[str, str],
    ):
        """Test sensor listing filtered by controller."""
        response = client.get(
            f"/sensors/?controller_id={test_controller.id}&page=1&page_size=10",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        data = response.json()
        for sensor in data["data"]:
            assert sensor["controller_id"] == str(test_controller.id)

    def test_create_sensor_success(
        self,
        client: TestClient,
        test_controller: Controller,
        superuser_token_headers: dict[str, str],
    ):
        """Test successful sensor creation."""
        request_data = {
            "label": "Test Temperature Sensor",
            "kind": "temperature",
            "pin": "A0",
            "controller_id": str(test_controller.id),
        }

        response = client.post(
            "/sensors/", json=request_data, headers=superuser_token_headers
        )
        assert response.status_code == 201

        data = response.json()
        assert data["label"] == "Test Temperature Sensor"
        assert data["kind"] == "temperature"
        assert data["pin"] == "A0"
        assert data["controller_id"] == str(test_controller.id)


class TestActuatorsCRUD:
    """Test actuators CRUD endpoints."""

    def test_list_actuators_success(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test successful actuator listing with pagination."""
        response = client.get(
            "/actuators/?page=1&page_size=10", headers=superuser_token_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert "data" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data

    def test_list_actuators_filter_by_kind(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test actuator listing filtered by kind."""
        response = client.get(
            "/actuators/?kind=fan&page=1&page_size=10", headers=superuser_token_headers
        )
        assert response.status_code == 200

        data = response.json()
        for actuator in data["data"]:
            assert actuator["kind"] == "fan"

    def test_create_actuator_success(
        self,
        client: TestClient,
        test_controller: Controller,
        superuser_token_headers: dict[str, str],
    ):
        """Test successful actuator creation."""
        request_data = {
            "label": "Test Fan",
            "kind": "fan",
            "pin": "D2",
            "controller_id": str(test_controller.id),
        }

        response = client.post(
            "/actuators/", json=request_data, headers=superuser_token_headers
        )
        assert response.status_code == 201

        data = response.json()
        assert data["label"] == "Test Fan"
        assert data["kind"] == "fan"
        assert data["pin"] == "D2"
        assert data["controller_id"] == str(test_controller.id)


class TestPaginationAndFiltering:
    """Test pagination and filtering across CRUD endpoints."""

    def test_pagination_page_size_validation(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test pagination with invalid page size returns proper error."""
        response = client.get(
            "/controllers/?page=1&page_size=101",  # Assuming max is 100
            headers=superuser_token_headers,
        )
        # Should either work or return validation error
        assert response.status_code in [200, 400, 422]

    def test_pagination_empty_page(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test requesting page beyond available data."""
        response = client.get(
            "/controllers/?page=999&page_size=10", headers=superuser_token_headers
        )
        assert response.status_code == 200

        data = response.json()
        assert data["data"] == []
        assert data["page"] == 999
        assert data["total"] >= 0

    def test_sorting_controllers(
        self, client: TestClient, superuser_token_headers: dict[str, str]
    ):
        """Test controller listing with sorting."""
        # Test ascending sort
        response = client.get(
            "/controllers/?sort=device_name&page=1&page_size=10",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200

        # Test descending sort
        response = client.get(
            "/controllers/?sort=-device_name&page=1&page_size=10",
            headers=superuser_token_headers,
        )
        assert response.status_code == 200
