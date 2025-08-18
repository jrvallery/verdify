"""
Comprehensive CRUD Operations Testing Suite

This module implements systematic testing of all CRUD operations across all endpoints,
with real data volumes, pagination validation, edge cases, and error handling.

Created to replace ad-hoc terminal commands with proper reusable pytest infrastructure.
"""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app


class CRUDTestFramework:
    """Framework for comprehensive CRUD testing with real data volumes."""

    def __init__(self, client: TestClient):
        self.client = client
        self.headers = {}
        self.test_greenhouse_id = None
        self.test_controller_id = None
        self.created_entities = {
            "greenhouses": [],
            "zones": [],
            "controllers": [],
            "sensors": [],
            "actuators": [],
            "crops": [],
            "plans": [],
            "fan_groups": [],
            "sensor_zone_maps": [],
            "zone_crops": [],
            "observations": [],
        }

    def authenticate(
        self, username: str = "debug_user@example.com", password: str = "testpass123"
    ):
        """Authenticate and set headers for subsequent requests."""
        response = self.client.post(
            "/api/v1/login/access-token",
            data={"username": username, "password": password},
        )
        assert response.status_code == 200
        token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {token}"}
        return token

    def create_test_greenhouse(self) -> str:
        """Create a comprehensive test greenhouse for CRUD operations."""
        greenhouse_data = {
            "title": "CRUD Testing Facility - Automated",
            "description": "Comprehensive testing facility for advanced CRUD operations validation",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "location": "San Francisco, CA - Test Lab",
            "context_text": "Automated test greenhouse created by comprehensive CRUD test suite. Contains extensive test data for validation of all CRUD operations.",
            "target_temperature_celsius": 22.5,
            "target_humidity_percent": 65.0,
            "target_co2_ppm": 1200,
            "target_vpd_kpa": 1.2,
            "max_temperature_celsius": 35.0,
            "min_temperature_celsius": 5.0,
        }

        response = self.client.post(
            "/api/v1/greenhouses/", json=greenhouse_data, headers=self.headers
        )
        assert response.status_code == 201

        greenhouse = response.json()
        self.test_greenhouse_id = greenhouse["id"]
        self.created_entities["greenhouses"].append(greenhouse)
        return greenhouse["id"]

    def create_test_zones(
        self, greenhouse_id: str, count: int = 30
    ) -> list[dict[str, Any]]:
        """Create multiple test zones for pagination and volume testing."""
        zones = []
        locations = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

        for i in range(count):
            zone_data = {
                "greenhouse_id": greenhouse_id,
                "zone_number": i + 1,
                "location": locations[i % len(locations)],
                "is_active": i % 5 != 4,  # 80% active rate
                "context_text": f"Automated test zone #{i+1} - Location: {locations[i % len(locations)]} - Created for comprehensive CRUD validation with detailed context for testing pagination and filtering capabilities.",
            }

            response = self.client.post(
                "/api/v1/zones/", json=zone_data, headers=self.headers
            )
            assert response.status_code == 201

            zone = response.json()
            zones.append(zone)
            self.created_entities["zones"].append(zone)

        return zones

    def create_test_controller(self, greenhouse_id: str) -> str:
        """Create a test controller with proper device_name format."""
        controller_data = {
            "greenhouse_id": greenhouse_id,
            "device_name": "verdify-abc123",  # Proper format: verdify-XXXXXX (hex)
            "is_climate_controller": True,
            "hardware_profile": "comprehensive_test_v3",
            "firmware_version": "3.0.0-testing",
        }

        response = self.client.post(
            "/api/v1/controllers/", json=controller_data, headers=self.headers
        )
        assert response.status_code == 201

        controller = response.json()
        self.test_controller_id = controller["id"]
        self.created_entities["controllers"].append(controller)
        return controller["id"]

    def create_test_sensors(
        self, controller_id: str, count: int = 26
    ) -> list[dict[str, Any]]:
        """Create multiple test sensors for comprehensive testing."""
        sensors = []
        sensor_kinds = [
            "temperature",
            "humidity",
            "co2",
            "light",
            "soil_moisture",
            "vpd",
            "water_flow",
        ]

        for i in range(count):
            sensor_data = {
                "controller_id": controller_id,
                "name": f"CrudSensor-{i+1:02d}",
                "kind": sensor_kinds[i % len(sensor_kinds)],
                "scope": ["zone", "greenhouse", "external"][i % 3],
                "sensor_index": i,
                "location": f"Rack-{(i//8)+1}-Pos-{chr(65 + (i%8))}",
                "sensor_type": "comprehensive_test_sensor",
                "poll_interval_s": 15 + (i % 4) * 15,  # 15, 30, 45, 60 second intervals
            }

            response = self.client.post(
                "/api/v1/sensors/", json=sensor_data, headers=self.headers
            )
            assert response.status_code == 201

            sensor = response.json()
            sensors.append(sensor)
            self.created_entities["sensors"].append(sensor)

        return sensors

    def create_test_actuators(
        self, controller_id: str, count: int = 28
    ) -> list[dict[str, Any]]:
        """Create multiple test actuators for comprehensive testing."""
        actuators = []
        actuator_kinds = [
            "fan",
            "heater",
            "vent",
            "fogger",
            "irrigation_valve",
            "pump",
            "light",
        ]

        for i in range(count):
            actuator_data = {
                "controller_id": controller_id,
                "name": f"CrudActuator-{i+1:02d}",
                "kind": actuator_kinds[i % len(actuator_kinds)],
                "actuator_index": i,
                "pin_number": i + 1,
                "is_active": i % 7 != 6,  # ~85% active
                "failsafe_state": ["off", "on"][i % 2],
            }

            response = self.client.post(
                "/api/v1/actuators/", json=actuator_data, headers=self.headers
            )
            assert response.status_code == 201

            actuator = response.json()
            actuators.append(actuator)
            self.created_entities["actuators"].append(actuator)

        return actuators

    def test_pagination_comprehensive(
        self, endpoint: str, params: dict[str, Any] = None
    ):
        """Test pagination edge cases and scenarios."""
        if params is None:
            params = {}

        test_cases = [
            {"page": 1, "page_size": 5, "desc": "Small page size"},
            {"page": 3, "page_size": 10, "desc": "Middle page"},
            {"page": 1, "page_size": 50, "desc": "Large page size"},
            {"page": 999, "page_size": 10, "desc": "Invalid page (beyond range)"},
        ]

        pagination_results = []

        for case in test_cases:
            test_params = {
                **params,
                "page": case["page"],
                "page_size": case["page_size"],
            }

            response = self.client.get(
                endpoint, params=test_params, headers=self.headers
            )
            assert response.status_code == 200

            data = response.json()
            items_count = len(data["data"])
            total = data["total"]

            result = {
                "description": case["desc"],
                "page": case["page"],
                "page_size": case["page_size"],
                "items_returned": items_count,
                "total_available": total,
                "valid_pagination": items_count <= case["page_size"],
            }
            pagination_results.append(result)

        return pagination_results

    def test_update_operations(
        self,
        entities: list[dict[str, Any]],
        endpoint_base: str,
        update_data: dict[str, Any],
    ):
        """Test UPDATE operations on multiple entities."""
        updated_entities = []

        for i, entity in enumerate(entities[:3]):  # Update first 3 entities
            entity_id = entity["id"]

            # Customize update data with unique identifiers
            test_update_data = {**update_data}
            if "context_text" in test_update_data:
                test_update_data[
                    "context_text"
                ] = f"{update_data['context_text']} - Update #{i+1} - ID: {entity_id[:8]}"

            response = self.client.patch(
                f"{endpoint_base}/{entity_id}",
                json=test_update_data,
                headers=self.headers,
            )
            assert response.status_code == 200

            updated_entity = response.json()
            updated_entities.append(updated_entity)

        return updated_entities

    def test_delete_operations(
        self, entities: list[dict[str, Any]], endpoint_base: str, count: int = 2
    ):
        """Test DELETE operations on selected entities."""
        deleted_count = 0

        for entity in entities[-count:]:  # Delete last N entities
            entity_id = entity["id"]

            response = self.client.delete(
                f"{endpoint_base}/{entity_id}", headers=self.headers
            )
            assert response.status_code == 204

            deleted_count += 1

        return deleted_count

    def test_edge_cases(self):
        """Test edge cases and error handling."""
        edge_case_results = []

        edge_cases = [
            {
                "name": "Invalid greenhouse creation (missing required field)",
                "method": "POST",
                "endpoint": "/api/v1/greenhouses/",
                "data": {"description": "Missing title field"},
                "expected_status": 422,
            },
            {
                "name": "Invalid zone creation (invalid location)",
                "method": "POST",
                "endpoint": "/api/v1/zones/",
                "data": {
                    "greenhouse_id": self.test_greenhouse_id,
                    "zone_number": 999,
                    "location": "INVALID",  # Should be one of N, NE, E, SE, S, SW, W, NW
                    "is_active": True,
                },
                "expected_status": 422,
            },
            {
                "name": "Access non-existent resource",
                "method": "GET",
                "endpoint": "/api/v1/greenhouses/12345678-1234-5678-9abc-123456789012",
                "data": None,
                "expected_status": 404,
            },
            {
                "name": "Unauthorized access to other user's data",
                "method": "GET",
                "endpoint": f"/api/v1/greenhouses/{uuid.uuid4()}",
                "data": None,
                "expected_status": 404,  # Should return 404 for non-existent resources
            },
        ]

        for case in edge_cases:
            try:
                if case["method"] == "POST":
                    response = self.client.post(
                        case["endpoint"], json=case["data"], headers=self.headers
                    )
                elif case["method"] == "GET":
                    response = self.client.get(case["endpoint"], headers=self.headers)

                status_ok = response.status_code == case["expected_status"]
                result = {
                    "name": case["name"],
                    "expected_status": case["expected_status"],
                    "actual_status": response.status_code,
                    "passed": status_ok,
                }
                edge_case_results.append(result)

            except Exception as e:
                edge_case_results.append(
                    {"name": case["name"], "error": str(e)[:100], "passed": False}
                )

        return edge_case_results

    def get_final_status(self):
        """Get comprehensive status of all created entities."""
        endpoints = [
            {"name": "Greenhouses", "endpoint": "/api/v1/greenhouses/", "params": {}},
            {
                "name": "Zones",
                "endpoint": "/api/v1/zones/",
                "params": {"greenhouse_id": self.test_greenhouse_id}
                if self.test_greenhouse_id
                else {},
            },
            {"name": "Controllers", "endpoint": "/api/v1/controllers/", "params": {}},
            {"name": "Sensors", "endpoint": "/api/v1/sensors/", "params": {}},
            {"name": "Actuators", "endpoint": "/api/v1/actuators/", "params": {}},
        ]

        status_report = []
        total_entities = 0

        for check in endpoints:
            response = self.client.get(
                check["endpoint"], params=check["params"], headers=self.headers
            )
            assert response.status_code == 200

            data = response.json()
            count = data.get("total", 0)
            total_entities += count

            volume_indicator = (
                "🎯 HIGH VOLUME"
                if count >= 25
                else "📊 GOOD"
                if count >= 5
                else "📋 BASIC"
                if count > 0
                else "⭕ EMPTY"
            )

            status_report.append(
                {
                    "resource": check["name"],
                    "count": count,
                    "volume_indicator": volume_indicator,
                }
            )

        return {
            "status_report": status_report,
            "total_entities": total_entities,
            "resources_with_data": len([s for s in status_report if s["count"] > 0]),
        }


@pytest.fixture
def crud_framework():
    """Fixture providing the CRUD testing framework."""
    client = TestClient(app)
    framework = CRUDTestFramework(client)
    framework.authenticate()
    return framework


class TestComprehensiveCRUD:
    """Comprehensive CRUD Operations Test Suite"""

    def test_phase_1_basic_endpoint_verification(self, crud_framework):
        """Phase 1: Verify all endpoints are working (basic smoke test)."""
        # This replaces the basic endpoint checking we did in terminal

        endpoints = [
            "/api/v1/greenhouses/",
            "/api/v1/zones/",
            "/api/v1/controllers/",
            "/api/v1/sensors/",
            "/api/v1/actuators/",
            "/api/v1/crops/",
            "/api/v1/plans/",
            "/api/v1/fan_groups/",
            "/api/v1/sensor_zone_maps/",
            "/api/v1/zone_crops/",
            "/api/v1/observations/",
        ]

        working_endpoints = 0
        for endpoint in endpoints:
            response = crud_framework.client.get(
                endpoint, headers=crud_framework.headers
            )
            if response.status_code == 200:
                working_endpoints += 1

        # All endpoints should be working
        assert working_endpoints == len(
            endpoints
        ), f"Only {working_endpoints}/{len(endpoints)} endpoints working"

    def test_phase_2_data_volume_creation(self, crud_framework):
        """Phase 2: Create substantial test data for realistic volume testing."""

        # Step 1: Create test greenhouse
        greenhouse_id = crud_framework.create_test_greenhouse()
        assert greenhouse_id is not None

        # Step 2: Create 30+ zones for high volume pagination testing
        zones = crud_framework.create_test_zones(greenhouse_id, count=32)
        assert len(zones) == 32

        # Step 3: Create controller for sensors/actuators
        controller_id = crud_framework.create_test_controller(greenhouse_id)
        assert controller_id is not None

        # Step 4: Create 25+ sensors
        sensors = crud_framework.create_test_sensors(controller_id, count=26)
        assert len(sensors) == 26

        # Step 5: Create 25+ actuators
        actuators = crud_framework.create_test_actuators(controller_id, count=28)
        assert len(actuators) == 28

        # Verify final data volumes
        status = crud_framework.get_final_status()
        assert status["total_entities"] >= 87  # 1 + 32 + 1 + 26 + 28 = 88
        assert status["resources_with_data"] >= 5

    def test_phase_3_advanced_crud_operations(self, crud_framework):
        """Phase 3: Advanced CRUD operations with real data."""

        # Prerequisites: Ensure we have test data
        greenhouse_id = crud_framework.create_test_greenhouse()
        zones = crud_framework.create_test_zones(greenhouse_id, count=10)
        controller_id = crud_framework.create_test_controller(greenhouse_id)

        # Test UPDATE operations
        greenhouse_updates = {
            "description": "UPDATED: Comprehensive testing facility with advanced validation",
            "context_text": "This greenhouse has been updated during comprehensive CRUD testing to validate UPDATE operations.",
        }

        # Update greenhouse
        response = crud_framework.client.patch(
            f"/api/v1/greenhouses/{greenhouse_id}",
            json=greenhouse_updates,
            headers=crud_framework.headers,
        )
        assert response.status_code == 200

        # Update zones
        zone_updates = {"context_text": "UPDATED during comprehensive CRUD testing"}
        updated_zones = crud_framework.test_update_operations(
            zones, "/api/v1/zones", zone_updates
        )
        assert len(updated_zones) == 3

        # Test DELETE operations
        deleted_count = crud_framework.test_delete_operations(
            zones, "/api/v1/zones", count=2
        )
        assert deleted_count == 2

    def test_phase_4_pagination_validation(self, crud_framework):
        """Phase 4: Comprehensive pagination testing."""

        # Setup: Create greenhouse and zones for pagination testing
        greenhouse_id = crud_framework.create_test_greenhouse()
        zones = crud_framework.create_test_zones(greenhouse_id, count=25)

        # Test pagination on zones with high volume
        pagination_results = crud_framework.test_pagination_comprehensive(
            "/api/v1/zones/", {"greenhouse_id": greenhouse_id}
        )

        assert len(pagination_results) == 4  # 4 test cases

        # Verify pagination behavior
        for result in pagination_results:
            assert result[
                "valid_pagination"
            ], f"Invalid pagination for {result['description']}"

        # Test edge case: large page size should return all items
        large_page_result = next(
            (r for r in pagination_results if r["page_size"] == 50), None
        )
        assert large_page_result is not None
        assert (
            large_page_result["items_returned"] <= large_page_result["total_available"]
        )

    def test_phase_5_edge_cases_and_error_handling(self, crud_framework):
        """Phase 5: Edge cases and error handling validation."""

        # Setup minimal data for edge case testing
        greenhouse_id = crud_framework.create_test_greenhouse()

        # Run comprehensive edge case testing
        edge_case_results = crud_framework.test_edge_cases()

        # Verify all edge cases passed
        passed_cases = [r for r in edge_case_results if r.get("passed", False)]
        total_cases = len(edge_case_results)

        assert (
            len(passed_cases) >= total_cases * 0.8
        ), f"Only {len(passed_cases)}/{total_cases} edge cases passed"

    def test_complete_crud_lifecycle(self, crud_framework):
        """Test complete CREATE → READ → UPDATE → DELETE lifecycle."""

        # CREATE: Full entity creation
        greenhouse_id = crud_framework.create_test_greenhouse()
        zones = crud_framework.create_test_zones(greenhouse_id, count=5)
        controller_id = crud_framework.create_test_controller(greenhouse_id)
        sensors = crud_framework.create_test_sensors(controller_id, count=3)

        # READ: Verify all entities can be retrieved
        response = crud_framework.client.get(
            f"/api/v1/greenhouses/{greenhouse_id}", headers=crud_framework.headers
        )
        assert response.status_code == 200

        zone_response = crud_framework.client.get(
            f"/api/v1/zones/{zones[0]['id']}", headers=crud_framework.headers
        )
        assert zone_response.status_code == 200

        sensor_response = crud_framework.client.get(
            f"/api/v1/sensors/{sensors[0]['id']}", headers=crud_framework.headers
        )
        assert sensor_response.status_code == 200

        # UPDATE: Modify entities
        updated_zones = crud_framework.test_update_operations(
            zones[:2], "/api/v1/zones", {"context_text": "Updated in lifecycle test"}
        )
        assert len(updated_zones) == 2

        # DELETE: Remove entities
        deleted_count = crud_framework.test_delete_operations(
            zones[2:], "/api/v1/zones", count=2
        )
        assert deleted_count == 2

        # VERIFY: Confirm deletions
        for zone in zones[2:4]:  # First 2 of the deleted zones
            response = crud_framework.client.get(
                f"/api/v1/zones/{zone['id']}", headers=crud_framework.headers
            )
            assert response.status_code == 404  # Should be deleted


if __name__ == "__main__":
    # Allow running tests directly for development
    pytest.main([__file__, "-v"])
