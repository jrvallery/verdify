"""
Live integration tests for CRUD operations (Greenhouses, Zones, Controllers, Sensors, etc.).
Tests against running FastAPI server on localhost:8000.
"""

import uuid

import pytest
import requests


class TestLiveCRUDAPI:
    """Base class for CRUD API tests against live server"""

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


class TestLiveGreenhouseCRUD(TestLiveCRUDAPI):
    """Test greenhouse CRUD operations"""

    def test_create_greenhouse(self):
        """Test creating a new greenhouse"""
        greenhouse_data = {
            "title": f"Test Greenhouse {uuid.uuid4().hex[:8]}",
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

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == greenhouse_data["title"]
        assert data["description"] == greenhouse_data["description"]
        assert "id" in data
        assert "created_at" in data

        return data["id"]

    def test_list_greenhouses(self):
        """Test listing greenhouses with pagination"""
        response = requests.get(
            f"{self.API_BASE}/greenhouses/", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data
        assert isinstance(data["data"], list)

    def test_get_greenhouse_by_id(self):
        """Test getting specific greenhouse by ID"""
        greenhouse_id = self.test_create_greenhouse()

        response = requests.get(
            f"{self.API_BASE}/greenhouses/{greenhouse_id}",
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == greenhouse_id

    def test_update_greenhouse(self):
        """Test updating greenhouse"""
        greenhouse_id = self.test_create_greenhouse()

        update_data = {
            "title": "Updated Test Greenhouse",
            "description": "Updated description",
        }

        response = requests.patch(
            f"{self.API_BASE}/greenhouses/{greenhouse_id}",
            json=update_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Test Greenhouse"
        assert data["description"] == "Updated description"

    def test_delete_greenhouse(self):
        """Test deleting greenhouse"""
        greenhouse_id = self.test_create_greenhouse()

        response = requests.delete(
            f"{self.API_BASE}/greenhouses/{greenhouse_id}",
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 204

        # Verify deletion
        get_response = requests.get(
            f"{self.API_BASE}/greenhouses/{greenhouse_id}",
            headers=self.get_auth_headers(),
        )
        assert get_response.status_code == 404

    def test_greenhouse_not_found(self):
        """Test accessing non-existent greenhouse"""
        fake_id = str(uuid.uuid4())

        response = requests.get(
            f"{self.API_BASE}/greenhouses/{fake_id}", headers=self.get_auth_headers()
        )

        assert response.status_code == 404

    def test_create_greenhouse_validation_errors(self):
        """Test greenhouse creation with invalid data"""
        invalid_data = {
            "title": "",  # Empty title
            "min_temp_c": 50.0,
            "max_temp_c": 10.0,  # max_temp < min_temp
        }

        response = requests.post(
            f"{self.API_BASE}/greenhouses/",
            json=invalid_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


class TestLiveZoneCRUD(TestLiveCRUDAPI):
    """Test zone CRUD operations"""

    def create_test_greenhouse(self) -> str:
        """Create a test greenhouse for zone tests"""
        greenhouse_data = {
            "title": f"Zone Test Greenhouse {uuid.uuid4().hex[:8]}",
            "description": "For zone testing",
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
        assert response.status_code == 201
        return response.json()["id"]

    def test_create_zone(self):
        """Test creating a new zone"""
        greenhouse_id = self.create_test_greenhouse()

        zone_data = {
            "zone_number": 1,
            "location": "N",
            "context_text": "Integration test zone",
            "greenhouse_id": greenhouse_id,
        }

        response = requests.post(
            f"{self.API_BASE}/zones/", json=zone_data, headers=self.get_auth_headers()
        )

        assert response.status_code == 201
        data = response.json()
        assert data["zone_number"] == zone_data["zone_number"]
        assert data["location"] == zone_data["location"]
        assert data["greenhouse_id"] == greenhouse_id
        assert "id" in data

        return data["id"]

    def test_list_zones(self):
        """Test listing zones"""
        response = requests.get(
            f"{self.API_BASE}/zones/", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data

    def test_get_zone_by_id(self):
        """Test getting specific zone by ID"""
        zone_id = self.test_create_zone()

        response = requests.get(
            f"{self.API_BASE}/zones/{zone_id}", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == zone_id

    def test_update_zone(self):
        """Test updating zone"""
        zone_id = self.test_create_zone()

        update_data = {
            "name": "Updated Test Zone",
            "description": "Updated description",
        }

        response = requests.patch(
            f"{self.API_BASE}/zones/{zone_id}",
            json=update_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Test Zone"
        assert data["description"] == "Updated description"

    def test_delete_zone(self):
        """Test deleting zone"""
        zone_id = self.test_create_zone()

        response = requests.delete(
            f"{self.API_BASE}/zones/{zone_id}", headers=self.get_auth_headers()
        )

        assert response.status_code == 204

        # Verify deletion
        get_response = requests.get(
            f"{self.API_BASE}/zones/{zone_id}", headers=self.get_auth_headers()
        )
        assert get_response.status_code == 404


class TestLiveControllerCRUD(TestLiveCRUDAPI):
    """Test controller CRUD operations"""

    def test_list_controllers(self):
        """Test listing controllers"""
        response = requests.get(
            f"{self.API_BASE}/controllers/", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data

    def test_create_controller_directly(self):
        """Test creating controller directly (not through onboarding)"""
        greenhouse_id = self.create_test_greenhouse()

        controller_data = {
            "device_name": f"verdify-{uuid.uuid4().hex[:6]}",
            "greenhouse_id": greenhouse_id,
            "label": "Test Controller",
            "model": "kincony_a16s",
            "fw_version": "2.1.0",
            "is_climate_controller": False,
        }

        response = requests.post(
            f"{self.API_BASE}/controllers/",
            json=controller_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["device_name"] == controller_data["device_name"]
        assert data["greenhouse_id"] == greenhouse_id
        assert "id" in data

        return data["id"]

    def create_test_greenhouse(self) -> str:
        """Create a test greenhouse for controller tests"""
        greenhouse_data = {
            "title": f"Controller Test Greenhouse {uuid.uuid4().hex[:8]}",
            "description": "For controller testing",
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
        assert response.status_code == 201
        return response.json()["id"]

    def test_get_controller_by_id(self):
        """Test getting specific controller by ID"""
        controller_id = self.test_create_controller_directly()

        response = requests.get(
            f"{self.API_BASE}/controllers/{controller_id}",
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == controller_id

    def test_update_controller(self):
        """Test updating controller"""
        controller_id = self.test_create_controller_directly()

        update_data = {"firmware": "2.2.0"}

        response = requests.patch(
            f"{self.API_BASE}/controllers/{controller_id}",
            json=update_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["firmware"] == "2.2.0"

    def test_delete_controller(self):
        """Test deleting controller"""
        controller_id = self.test_create_controller_directly()

        response = requests.delete(
            f"{self.API_BASE}/controllers/{controller_id}",
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 204

        # Verify deletion
        get_response = requests.get(
            f"{self.API_BASE}/controllers/{controller_id}",
            headers=self.get_auth_headers(),
        )
        assert get_response.status_code == 404


class TestLiveSensorCRUD(TestLiveCRUDAPI):
    """Test sensor CRUD operations"""

    def create_test_controller(self) -> str:
        """Create a test controller for sensor tests"""
        greenhouse_id = self.create_test_greenhouse()

        controller_data = {
            "device_name": f"verdify-{uuid.uuid4().hex[:6]}",
            "greenhouse_id": greenhouse_id,
            "label": "Test Controller for Sensors",
            "model": "kincony_a16s",
            "fw_version": "2.1.0",
            "is_climate_controller": False,
        }

        response = requests.post(
            f"{self.API_BASE}/controllers/",
            json=controller_data,
            headers=self.get_auth_headers(),
        )
        assert response.status_code == 201
        return response.json()["id"]

    def create_test_greenhouse(self) -> str:
        """Create a test greenhouse"""
        greenhouse_data = {
            "title": f"Sensor Test Greenhouse {uuid.uuid4().hex[:8]}",
            "description": "For sensor testing",
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
        assert response.status_code == 201
        return response.json()["id"]

    def test_create_sensor(self):
        """Test creating a new sensor"""
        controller_id = self.create_test_controller()

        sensor_data = {
            "controller_id": controller_id,
            "name": f"Test Sensor {uuid.uuid4().hex[:8]}",
            "kind": "temperature",
            "scope": "zone",
            "include_in_climate_loop": False,
            "poll_interval_s": 10,
        }

        response = requests.post(
            f"{self.API_BASE}/sensors/",
            json=sensor_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["controller_id"] == controller_id
        assert data["kind"] == "temperature"
        assert data["scope"] == "zone"
        assert "id" in data

        return data["id"]

    def test_list_sensors(self):
        """Test listing sensors"""
        response = requests.get(
            f"{self.API_BASE}/sensors/", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data

    def test_get_sensor_by_id(self):
        """Test getting specific sensor by ID"""
        sensor_id = self.test_create_sensor()

        response = requests.get(
            f"{self.API_BASE}/sensors/{sensor_id}", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sensor_id

    def test_update_sensor(self):
        """Test updating sensor"""
        sensor_id = self.test_create_sensor()

        update_data = {"name": "Updated Test Sensor"}

        response = requests.patch(
            f"{self.API_BASE}/sensors/{sensor_id}",
            json=update_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Test Sensor"

    def test_delete_sensor(self):
        """Test deleting sensor"""
        sensor_id = self.test_create_sensor()

        response = requests.delete(
            f"{self.API_BASE}/sensors/{sensor_id}", headers=self.get_auth_headers()
        )

        assert response.status_code == 204

        # Verify deletion
        get_response = requests.get(
            f"{self.API_BASE}/sensors/{sensor_id}", headers=self.get_auth_headers()
        )
        assert get_response.status_code == 404


class TestLiveActuatorCRUD(TestLiveCRUDAPI):
    """Test actuator CRUD operations"""

    def create_test_controller(self) -> str:
        """Create a test controller for actuator tests"""
        greenhouse_id = self.create_test_greenhouse()

        controller_data = {
            "device_name": f"verdify-{uuid.uuid4().hex[:6]}",
            "greenhouse_id": greenhouse_id,
            "label": "Test Controller for Actuators",
            "model": "kincony_a16s",
            "fw_version": "2.1.0",
            "is_climate_controller": False,
        }

        response = requests.post(
            f"{self.API_BASE}/controllers/",
            json=controller_data,
            headers=self.get_auth_headers(),
        )
        assert response.status_code == 201
        return response.json()["id"]

    def create_test_greenhouse(self) -> str:
        """Create a test greenhouse"""
        greenhouse_data = {
            "title": f"Actuator Test Greenhouse {uuid.uuid4().hex[:8]}",
            "description": "For actuator testing",
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
        assert response.status_code == 201
        return response.json()["id"]

    def test_create_actuator(self):
        """Test creating a new actuator"""
        controller_id = self.create_test_controller()

        actuator_data = {
            "controller_id": controller_id,
            "name": f"Test Actuator {uuid.uuid4().hex[:8]}",
            "kind": "fan",
            "relay_channel": 1,
            "min_on_ms": 60000,
            "min_off_ms": 60000,
            "fail_safe_state": "off",
        }

        response = requests.post(
            f"{self.API_BASE}/actuators/",
            json=actuator_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["controller_id"] == controller_id
        assert data["kind"] == "fan"
        assert data["relay_channel"] == 1
        assert "id" in data

        return data["id"]

    def test_list_actuators(self):
        """Test listing actuators"""
        response = requests.get(
            f"{self.API_BASE}/actuators/", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "page" in data
        assert "page_size" in data
        assert "total" in data

    def test_get_actuator_by_id(self):
        """Test getting specific actuator by ID"""
        actuator_id = self.test_create_actuator()

        response = requests.get(
            f"{self.API_BASE}/actuators/{actuator_id}", headers=self.get_auth_headers()
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == actuator_id

    def test_update_actuator(self):
        """Test updating actuator"""
        actuator_id = self.test_create_actuator()

        update_data = {"name": "Updated Test Actuator"}

        response = requests.patch(
            f"{self.API_BASE}/actuators/{actuator_id}",
            json=update_data,
            headers=self.get_auth_headers(),
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Test Actuator"

    def test_delete_actuator(self):
        """Test deleting actuator"""
        actuator_id = self.test_create_actuator()

        response = requests.delete(
            f"{self.API_BASE}/actuators/{actuator_id}", headers=self.get_auth_headers()
        )

        assert response.status_code == 204

        # Verify deletion
        get_response = requests.get(
            f"{self.API_BASE}/actuators/{actuator_id}", headers=self.get_auth_headers()
        )
        assert get_response.status_code == 404


class TestLiveEndToEndCRUD(TestLiveCRUDAPI):
    """Test complete CRUD workflows"""

    def test_complete_greenhouse_ecosystem(self):
        """Test creating a complete greenhouse ecosystem"""
        print("\n=== Testing Complete Greenhouse Ecosystem ===")

        # Step 1: Create greenhouse
        greenhouse_data = {
            "title": f"Ecosystem Test {uuid.uuid4().hex[:8]}",
            "description": "Complete ecosystem test",
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
        print(f"✓ Created greenhouse: {greenhouse_id}")

        # Step 2: Create zone
        zone_data = {
            "zone_number": 1,
            "location": "N",
            "context_text": "Primary zone for testing",
            "greenhouse_id": greenhouse_id,
        }

        zone_response = requests.post(
            f"{self.API_BASE}/zones/", json=zone_data, headers=self.get_auth_headers()
        )
        assert zone_response.status_code == 201
        zone_id = zone_response.json()["id"]
        print(f"✓ Created zone: {zone_id}")

        # Step 3: Create controller
        controller_data = {
            "device_name": f"verdify-{uuid.uuid4().hex[:6]}",
            "greenhouse_id": greenhouse_id,
            "label": "Test Controller for Comprehensive",
            "model": "kincony_a16s",
            "fw_version": "2.1.0",
            "is_climate_controller": False,
        }

        controller_response = requests.post(
            f"{self.API_BASE}/controllers/",
            json=controller_data,
            headers=self.get_auth_headers(),
        )
        assert controller_response.status_code == 201
        controller_id = controller_response.json()["id"]
        print(f"✓ Created controller: {controller_id}")

        # Step 4: Create sensors
        sensor_types = ["temperature", "humidity", "soil_moisture"]
        sensor_ids = []

        for i, sensor_type in enumerate(sensor_types):
            sensor_data = {
                "controller_id": controller_id,
                "name": f"Test {sensor_type.title()} Sensor",
                "kind": sensor_type,
                "scope": "zone",
                "include_in_climate_loop": False,
                "poll_interval_s": 10,
            }

            sensor_response = requests.post(
                f"{self.API_BASE}/sensors/",
                json=sensor_data,
                headers=self.get_auth_headers(),
            )
            assert sensor_response.status_code == 201
            sensor_ids.append(sensor_response.json()["id"])

        print(f"✓ Created {len(sensor_ids)} sensors")

        # Step 5: Create actuators
        actuator_types = ["fan", "heater"]
        actuator_ids = []

        for i, actuator_type in enumerate(actuator_types):
            actuator_data = {
                "controller_id": controller_id,
                "name": f"Test {actuator_type.title()} Actuator",
                "kind": actuator_type,
                "relay_channel": i + 1,
                "min_on_ms": 60000,
                "min_off_ms": 60000,
                "fail_safe_state": "off",
            }

            actuator_response = requests.post(
                f"{self.API_BASE}/actuators/",
                json=actuator_data,
                headers=self.get_auth_headers(),
            )
            assert actuator_response.status_code == 201
            actuator_ids.append(actuator_response.json()["id"])

        print(f"✓ Created {len(actuator_ids)} actuators")

        # Step 6: Verify everything is connected
        # Check greenhouse has everything
        gh_check = requests.get(
            f"{self.API_BASE}/greenhouses/{greenhouse_id}",
            headers=self.get_auth_headers(),
        )
        assert gh_check.status_code == 200
        print("✓ Greenhouse verification passed")

        # Check zone exists
        zone_check = requests.get(
            f"{self.API_BASE}/zones/{zone_id}", headers=self.get_auth_headers()
        )
        assert zone_check.status_code == 200
        print("✓ Zone verification passed")

        # Check controller exists
        controller_check = requests.get(
            f"{self.API_BASE}/controllers/{controller_id}",
            headers=self.get_auth_headers(),
        )
        assert controller_check.status_code == 200
        print("✓ Controller verification passed")

        # Check all sensors exist
        for sensor_id in sensor_ids:
            sensor_check = requests.get(
                f"{self.API_BASE}/sensors/{sensor_id}", headers=self.get_auth_headers()
            )
            assert sensor_check.status_code == 200
        print("✓ All sensors verification passed")

        # Check all actuators exist
        for actuator_id in actuator_ids:
            actuator_check = requests.get(
                f"{self.API_BASE}/actuators/{actuator_id}",
                headers=self.get_auth_headers(),
            )
            assert actuator_check.status_code == 200
        print("✓ All actuators verification passed")

        print("=== Complete Greenhouse Ecosystem Test PASSED ===\n")

        return {
            "greenhouse_id": greenhouse_id,
            "zone_id": zone_id,
            "controller_id": controller_id,
            "sensor_ids": sensor_ids,
            "actuator_ids": actuator_ids,
        }
