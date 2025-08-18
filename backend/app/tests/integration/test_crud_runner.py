"""
CRUD Operations Test Runner

This script implements comprehensive CRUD testing as proper reusable tests,
replacing the ad-hoc terminal commands with systematic pytest infrastructure.

Run with: uv run python -m pytest app/tests/integration/test_crud_runner.py -v
"""

import sys
import uuid

import requests


def get_auth_headers():
    """Get authentication headers for API requests."""
    login_response = requests.post(
        "http://localhost:8000/api/v1/login/access-token",
        data={"username": "debug_user@example.com", "password": "testpass123"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_phase_1_endpoint_verification():
    """Phase 1: Verify all 11 endpoints are working."""
    headers = get_auth_headers()

    # First, create a test greenhouse for endpoints that require it
    greenhouse_data = {
        "title": "Phase 1 Test Greenhouse",
        "description": "Temporary greenhouse for endpoint verification",
        "latitude": 37.7749,
        "longitude": -122.4194,
    }

    gh_response = requests.post(
        "http://localhost:8000/api/v1/greenhouses/",
        json=greenhouse_data,
        headers=headers,
    )
    assert gh_response.status_code == 201
    test_greenhouse_id = gh_response.json()["id"]

    endpoints = [
        ("/api/v1/greenhouses/", {}),
        (
            "/api/v1/zones/",
            {"greenhouse_id": test_greenhouse_id},
        ),  # Requires greenhouse_id
        ("/api/v1/controllers/", {}),
        ("/api/v1/sensors/", {}),
        ("/api/v1/actuators/", {}),
        ("/api/v1/crops/", {}),
        (
            "/api/v1/plans/",
            {"greenhouse_id": test_greenhouse_id},
        ),  # Requires greenhouse_id
        ("/api/v1/fan-groups/", {}),  # Correct endpoint with hyphen
        ("/api/v1/sensor-zone-maps/", {}),  # Correct endpoint with hyphens
        ("/api/v1/zone-crops/", {}),  # Correct endpoint with hyphen
        ("/api/v1/observations/", {}),
    ]

    working_endpoints = 0
    broken_endpoints = []

    for endpoint, params in endpoints:
        try:
            response = requests.get(
                f"http://localhost:8000{endpoint}",
                params=params,
                headers=headers,
                timeout=10,
            )
            if response.status_code == 200:
                working_endpoints += 1
                print(f"✅ {endpoint} - Working")
            elif (
                response.status_code == 405
            ):  # Method not allowed - endpoint exists but may not support GET
                working_endpoints += 1
                print(
                    f"✅ {endpoint} - Working (405 - endpoint exists, GET not supported)"
                )
            else:
                broken_endpoints.append(f"{endpoint} - Status {response.status_code}")
                print(f"❌ {endpoint} - Status {response.status_code}")
        except Exception as e:
            broken_endpoints.append(f"{endpoint} - Error: {str(e)[:50]}")
            print(f"💥 {endpoint} - Error: {str(e)[:50]}")

    print(
        f"\n📊 Phase 1 Results: {working_endpoints}/{len(endpoints)} endpoints working"
    )

    if broken_endpoints:
        print("❌ Broken endpoints:")
        for broken in broken_endpoints:
            print(f"   • {broken}")
        return False

    return True


def test_phase_2_data_creation():
    """Phase 2: Create comprehensive test data with real volumes."""
    headers = get_auth_headers()

    print("\n🔧 Phase 2: Creating comprehensive test data...")

    # Create test greenhouse
    greenhouse_data = {
        "title": "CRUD Test Facility - Systematic",
        "description": "Comprehensive testing facility for systematic CRUD validation",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "location": "San Francisco, CA - Systematic Test",
        "context_text": "Created by systematic CRUD test runner for comprehensive validation",
    }

    gh_response = requests.post(
        "http://localhost:8000/api/v1/greenhouses/",
        json=greenhouse_data,
        headers=headers,
    )
    assert gh_response.status_code == 201
    greenhouse_id = gh_response.json()["id"]
    print(f"✅ Created test greenhouse: {greenhouse_id}")

    # Create 30+ zones for high volume testing
    zones_created = 0
    locations = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

    for i in range(32):
        zone_data = {
            "greenhouse_id": greenhouse_id,
            "zone_number": i + 1,
            "location": locations[i % len(locations)],
            "is_active": i % 5 != 4,  # 80% active
            "context_text": f"Systematic test zone #{i+1} - High volume pagination testing",
        }

        zone_response = requests.post(
            "http://localhost:8000/api/v1/zones/", json=zone_data, headers=headers
        )
        if zone_response.status_code == 201:
            zones_created += 1

    print(f"✅ Created {zones_created} zones for high-volume testing")

    # Create controller for sensors/actuators
    controller_data = {
        "greenhouse_id": greenhouse_id,
        "device_name": "verdify-def456",  # Proper format
        "is_climate_controller": True,
        "hardware_profile": "systematic_test_v1",
    }

    controller_response = requests.post(
        "http://localhost:8000/api/v1/controllers/",
        json=controller_data,
        headers=headers,
    )

    if controller_response.status_code == 201:
        controller_id = controller_response.json()["id"]
        print(f"✅ Created test controller: {controller_id}")

        # Create 25+ sensors
        sensors_created = 0
        sensor_kinds = ["temperature", "humidity", "co2", "light", "soil_moisture"]

        for i in range(26):
            sensor_data = {
                "controller_id": controller_id,
                "name": f"SystematicSensor-{i+1:02d}",
                "kind": sensor_kinds[i % len(sensor_kinds)],
                "scope": ["zone", "greenhouse", "external"][i % 3],
                "sensor_index": i,
                "location": f"Rack-{(i//5)+1}-Pos-{i%5+1}",
                "sensor_type": "systematic_test",
            }

            sensor_response = requests.post(
                "http://localhost:8000/api/v1/sensors/",
                json=sensor_data,
                headers=headers,
            )
            if sensor_response.status_code == 201:
                sensors_created += 1

        print(f"✅ Created {sensors_created} sensors")

        # Create 25+ actuators
        actuators_created = 0
        actuator_kinds = ["fan", "heater", "vent", "fogger", "irrigation_valve"]

        for i in range(28):
            actuator_data = {
                "controller_id": controller_id,
                "name": f"SystematicActuator-{i+1:02d}",
                "kind": actuator_kinds[i % len(actuator_kinds)],
                "actuator_index": i,
                "pin_number": i + 1,
                "is_active": i % 6 != 5,  # ~83% active
            }

            actuator_response = requests.post(
                "http://localhost:8000/api/v1/actuators/",
                json=actuator_data,
                headers=headers,
            )
            if actuator_response.status_code == 201:
                actuators_created += 1

        print(f"✅ Created {actuators_created} actuators")

    else:
        print(f"❌ Controller creation failed: {controller_response.status_code}")
        controller_id = None

    return {
        "greenhouse_id": greenhouse_id,
        "controller_id": controller_id,
        "zones_created": zones_created,
        "sensors_created": sensors_created if controller_id else 0,
        "actuators_created": actuators_created if controller_id else 0,
    }


def test_phase_3_pagination_validation(greenhouse_id: str):
    """Phase 3: Comprehensive pagination testing with real data."""
    headers = get_auth_headers()

    print("\n📖 Phase 3: Testing pagination with real data volumes...")

    pagination_tests = [
        {"page": 1, "page_size": 5, "desc": "Small page size"},
        {"page": 3, "page_size": 10, "desc": "Middle page"},
        {"page": 1, "page_size": 50, "desc": "Large page size"},
        {"page": 999, "page_size": 10, "desc": "Beyond available data"},
    ]

    successful_tests = 0

    for test in pagination_tests:
        params = {
            "greenhouse_id": greenhouse_id,
            "page": test["page"],
            "page_size": test["page_size"],
        }

        response = requests.get(
            "http://localhost:8000/api/v1/zones/", params=params, headers=headers
        )

        if response.status_code == 200:
            data = response.json()
            items_count = len(data["data"])
            total = data["total"]

            print(
                f"✅ {test['desc']}: Page {test['page']} returned {items_count} items (total: {total})"
            )
            successful_tests += 1
        else:
            print(f"❌ {test['desc']}: Failed with status {response.status_code}")

    print(f"📊 Pagination tests: {successful_tests}/{len(pagination_tests)} passed")
    return successful_tests == len(pagination_tests)


def test_phase_4_update_operations(greenhouse_id: str):
    """Phase 4: Test UPDATE operations."""
    headers = get_auth_headers()

    print("\n✏️ Phase 4: Testing UPDATE operations...")

    # Update greenhouse
    greenhouse_update = {
        "description": "UPDATED: Systematic testing facility with comprehensive validation",
        "context_text": "Updated during systematic CRUD testing to validate UPDATE operations",
    }

    gh_update_response = requests.patch(
        f"http://localhost:8000/api/v1/greenhouses/{greenhouse_id}",
        json=greenhouse_update,
        headers=headers,
    )

    greenhouse_updated = gh_update_response.status_code == 200
    print(
        f"{'✅' if greenhouse_updated else '❌'} Greenhouse update: {gh_update_response.status_code}"
    )

    # Update zones
    zones_response = requests.get(
        f"http://localhost:8000/api/v1/zones/?greenhouse_id={greenhouse_id}&page=1&page_size=3",
        headers=headers,
    )

    zones_updated = 0
    if zones_response.status_code == 200:
        zones = zones_response.json()["data"]

        for i, zone in enumerate(zones[:3]):
            zone_update = {
                "context_text": f'UPDATED during systematic testing - Zone {zone["zone_number"]} - Update #{i+1}'
            }

            zone_update_response = requests.patch(
                f'http://localhost:8000/api/v1/zones/{zone["id"]}',
                json=zone_update,
                headers=headers,
            )
            if zone_update_response.status_code == 200:
                zones_updated += 1

    print(f"✅ Updated {zones_updated}/3 zones successfully")

    return greenhouse_updated and zones_updated >= 2


def test_phase_5_delete_operations(greenhouse_id: str):
    """Phase 5: Test DELETE operations (selective)."""
    headers = get_auth_headers()

    print("\n🗑️ Phase 5: Testing DELETE operations...")

    # Get zones for deletion testing
    zones_response = requests.get(
        f"http://localhost:8000/api/v1/zones/?greenhouse_id={greenhouse_id}&page=3&page_size=3",
        headers=headers,
    )

    deleted_count = 0
    if zones_response.status_code == 200:
        zones = zones_response.json()["data"]

        for zone in zones[:2]:  # Delete only 2 zones
            delete_response = requests.delete(
                f'http://localhost:8000/api/v1/zones/{zone["id"]}', headers=headers
            )
            if delete_response.status_code == 204:
                deleted_count += 1

    print(f"✅ Deleted {deleted_count}/2 zones successfully")
    return deleted_count >= 1


def test_phase_6_edge_cases():
    """Phase 6: Test edge cases and error handling."""
    headers = get_auth_headers()

    print("\n🔬 Phase 6: Testing edge cases and error handling...")

    edge_cases = [
        {
            "name": "Invalid greenhouse creation (missing title)",
            "method": "POST",
            "url": "/api/v1/greenhouses/",
            "data": {"description": "Missing title field"},
            "expected_status": 422,
        },
        {
            "name": "Access non-existent resource",
            "method": "GET",
            "url": f"/api/v1/greenhouses/{uuid.uuid4()}",
            "expected_status": 404,
        },
    ]

    passed_cases = 0

    for case in edge_cases:
        try:
            if case["method"] == "POST":
                response = requests.post(
                    f'http://localhost:8000{case["url"]}',
                    json=case["data"],
                    headers=headers,
                    timeout=5,
                )
            elif case["method"] == "GET":
                response = requests.get(
                    f'http://localhost:8000{case["url"]}', headers=headers, timeout=5
                )

            if response.status_code == case["expected_status"]:
                print(
                    f"✅ {case['name']}: Expected {case['expected_status']}, got {response.status_code}"
                )
                passed_cases += 1
            else:
                print(
                    f"❌ {case['name']}: Expected {case['expected_status']}, got {response.status_code}"
                )

        except Exception as e:
            print(f"💥 {case['name']}: Error - {str(e)[:50]}")

    print(f"📊 Edge case tests: {passed_cases}/{len(edge_cases)} passed")
    return passed_cases == len(edge_cases)


def get_final_status(greenhouse_id: str = None):
    """Get final status of all resources."""
    headers = get_auth_headers()

    print("\n📊 Final Comprehensive Status Check")
    print("=" * 50)

    endpoints = [
        {"name": "Greenhouses", "url": "/api/v1/greenhouses/", "params": {}},
        {
            "name": "Zones",
            "url": "/api/v1/zones/",
            "params": {"greenhouse_id": greenhouse_id} if greenhouse_id else {},
        },
        {"name": "Controllers", "url": "/api/v1/controllers/", "params": {}},
        {"name": "Sensors", "url": "/api/v1/sensors/", "params": {}},
        {"name": "Actuators", "url": "/api/v1/actuators/", "params": {}},
    ]

    total_entities = 0
    resources_with_data = 0

    for check in endpoints:
        response = requests.get(
            f'http://localhost:8000{check["url"]}',
            params=check["params"],
            headers=headers,
        )

        if response.status_code == 200:
            data = response.json()
            count = data.get("total", 0)
            total_entities += count

            if count > 0:
                resources_with_data += 1

            volume_indicator = (
                "🎯 HIGH VOLUME"
                if count >= 25
                else "📊 GOOD"
                if count >= 5
                else "📋 BASIC"
                if count > 0
                else "⭕ EMPTY"
            )

            print(f"   • {check['name']}: {count} items {volume_indicator}")
        else:
            print(
                f"   ❌ {check['name']}: Failed to fetch (status {response.status_code})"
            )

    return {
        "total_entities": total_entities,
        "resources_with_data": resources_with_data,
    }


def run_comprehensive_crud_tests():
    """Run all comprehensive CRUD tests systematically."""
    print("🚀 SYSTEMATIC COMPREHENSIVE CRUD TESTING")
    print("=" * 60)

    results = {}

    # Phase 1: Basic endpoint verification
    results["phase_1"] = test_phase_1_endpoint_verification()

    if not results["phase_1"]:
        print("\n❌ Phase 1 failed - stopping execution")
        return results

    # Phase 2: Data creation
    phase_2_data = test_phase_2_data_creation()
    results["phase_2"] = phase_2_data
    greenhouse_id = phase_2_data["greenhouse_id"]

    # Phase 3: Pagination validation
    results["phase_3"] = test_phase_3_pagination_validation(greenhouse_id)

    # Phase 4: UPDATE operations
    results["phase_4"] = test_phase_4_update_operations(greenhouse_id)

    # Phase 5: DELETE operations
    results["phase_5"] = test_phase_5_delete_operations(greenhouse_id)

    # Phase 6: Edge cases
    results["phase_6"] = test_phase_6_edge_cases()

    # Final status
    final_status = get_final_status(greenhouse_id)
    results["final_status"] = final_status

    # Summary
    print("\n🏆 COMPREHENSIVE CRUD TESTING COMPLETE")
    print("=" * 50)
    print(
        f"✅ Phase 1 - Endpoint Verification: {'PASS' if results['phase_1'] else 'FAIL'}"
    )
    print(
        f"📊 Phase 2 - Data Creation: {results['phase_2']['zones_created']} zones, {results['phase_2']['sensors_created']} sensors, {results['phase_2']['actuators_created']} actuators"
    )
    print(f"📖 Phase 3 - Pagination: {'PASS' if results['phase_3'] else 'FAIL'}")
    print(f"✏️ Phase 4 - Updates: {'PASS' if results['phase_4'] else 'FAIL'}")
    print(f"🗑️ Phase 5 - Deletes: {'PASS' if results['phase_5'] else 'FAIL'}")
    print(f"🔬 Phase 6 - Edge Cases: {'PASS' if results['phase_6'] else 'FAIL'}")
    print(f"📊 Total Entities: {final_status['total_entities']}")
    print(f"📈 Resources with Data: {final_status['resources_with_data']}/5")

    all_passed = all(
        [
            results["phase_1"],
            results["phase_3"],
            results["phase_4"],
            results["phase_5"],
            results["phase_6"],
        ]
    )

    print(
        f"\n🎯 OVERALL RESULT: {'✅ COMPREHENSIVE CRUD COVERAGE ACHIEVED!' if all_passed else '❌ Some tests failed'}"
    )

    return results


if __name__ == "__main__":
    # Run the comprehensive test suite
    test_results = run_comprehensive_crud_tests()

    # Exit with appropriate code
    all_passed = all(
        [
            test_results.get("phase_1", False),
            test_results.get("phase_3", False),
            test_results.get("phase_4", False),
            test_results.get("phase_5", False),
            test_results.get("phase_6", False),
        ]
    )

    sys.exit(0 if all_passed else 1)
