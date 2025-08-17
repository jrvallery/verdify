#!/usr/bin/env python3
"""
Comprehensive API Testing Against Live FastAPI Server

This script tests the ACTUAL running FastAPI server (not TestClient) against
the complete OpenAPI specification to ensure 100% API coverage and compliance.

Requirements:
- FastAPI server running (via uvicorn or docker-compose)
- Database with proper migrations applied
- Test data seeded as needed

Usage:
    # Start the server first:
    cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

    # Run the comprehensive tests:
    python test_full_api_live.py
"""

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import yaml
from pydantic import BaseModel

# Add the app to Python path for imports
sys.path.insert(0, str(Path(__file__).parent / "app"))

# Configuration
BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
OPENAPI_SPEC_PATH = Path(__file__).parent.parent / "requirements" / "openapi.yml"


class TestConfig:
    """Test configuration and constants"""

    BASE_URL = BASE_URL
    TIMEOUT = 30.0
    MAX_RETRIES = 3

    # Test data patterns
    DEVICE_NAME_PATTERN = "verdify-{:06x}"  # hex format
    CLAIM_CODE_PATTERN = "{:06d}"  # 6-digit numeric

    # Test user credentials
    TEST_USER_EMAIL = "test@example.com"
    TEST_USER_PASSWORD = "TestPassword123!"
    TEST_USER_FULL_NAME = "Test User"


class APITestResult(BaseModel):
    """Result of a single API test"""

    endpoint: str
    method: str
    status_code: int
    expected_status: int
    success: bool
    response_time_ms: float
    error_message: str | None = None
    response_body: dict[str, Any] | None = None


class APITestSuite:
    """Comprehensive API test suite against live FastAPI server"""

    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=TestConfig.BASE_URL, timeout=TestConfig.TIMEOUT
        )
        self.openapi_spec = self._load_openapi_spec()
        self.test_results: list[APITestResult] = []
        self.user_token: str | None = None
        self.device_token: str | None = None
        self.test_data: dict[str, Any] = {}

    def _load_openapi_spec(self) -> dict[str, Any]:
        """Load and parse the OpenAPI specification"""
        with open(OPENAPI_SPEC_PATH) as f:
            return yaml.safe_load(f)

    async def setup(self):
        """Setup test environment and authentication"""
        print("🔧 Setting up test environment...")

        # Test basic connectivity
        try:
            response = await self.client.get("/health")
            if response.status_code != 200:
                raise Exception(f"Health check failed: {response.status_code}")
            print("✅ Server connectivity confirmed")
        except Exception as e:
            raise Exception(
                f"Cannot connect to API server at {TestConfig.BASE_URL}: {e}"
            )

        # Setup test user and authentication
        await self._setup_authentication()
        print("✅ Authentication setup complete")

        # Create test data
        await self._setup_test_data()
        print("✅ Test data setup complete")

    async def _setup_authentication(self):
        """Setup user authentication and get JWT token"""
        # Try to register test user (may already exist)
        register_data = {
            "email": TestConfig.TEST_USER_EMAIL,
            "password": TestConfig.TEST_USER_PASSWORD,
            "full_name": TestConfig.TEST_USER_FULL_NAME,
        }

        try:
            await self.client.post("/auth/register", json=register_data)
        except Exception:
            pass  # User may already exist

        # Login to get JWT token
        login_data = {
            "email": TestConfig.TEST_USER_EMAIL,
            "password": TestConfig.TEST_USER_PASSWORD,
        }

        response = await self.client.post("/auth/login", json=login_data)
        if response.status_code == 200:
            self.user_token = response.json()["access_token"]
        else:
            raise Exception(f"Login failed: {response.status_code} - {response.text}")

    async def _setup_test_data(self):
        """Create test data needed for comprehensive testing"""
        headers = {"Authorization": f"Bearer {self.user_token}"}

        # Create test greenhouse
        greenhouse_data = {
            "title": "Test Greenhouse",
            "description": "Automated test greenhouse",
            "latitude": 37.7749,
            "longitude": -122.4194,
            "min_temp_c": 15.0,
            "max_temp_c": 30.0,
            "min_vpd_kpa": 0.5,
            "max_vpd_kpa": 1.5,
        }

        response = await self.client.post(
            "/greenhouses", json=greenhouse_data, headers=headers
        )
        if response.status_code == 201:
            self.test_data["greenhouse"] = response.json()
            print(f"📍 Created test greenhouse: {self.test_data['greenhouse']['id']}")
        else:
            raise Exception(f"Failed to create test greenhouse: {response.status_code}")

        # Create test controller (for device token testing)
        controller_data = {
            "greenhouse_id": self.test_data["greenhouse"]["id"],
            "device_name": TestConfig.DEVICE_NAME_PATTERN.format(0xAABBCC),
            "label": "Test Controller",
            "is_climate_controller": True,
        }

        response = await self.client.post(
            "/controllers", json=controller_data, headers=headers
        )
        if response.status_code == 201:
            self.test_data["controller"] = response.json()
            print(f"🎛️  Created test controller: {self.test_data['controller']['id']}")

    async def run_comprehensive_tests(self) -> list[APITestResult]:
        """Run tests against all endpoints defined in OpenAPI spec"""
        print("🚀 Starting comprehensive API tests...")

        # Extract all paths from OpenAPI spec
        paths = self.openapi_spec.get("paths", {})

        # Test each endpoint
        for path, methods in paths.items():
            for method, spec in methods.items():
                if method.upper() in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                    await self._test_endpoint(path, method.upper(), spec)

        return self.test_data

    async def _test_endpoint(self, path: str, method: str, spec: dict[str, Any]):
        """Test a single endpoint"""
        operation_id = spec.get("operationId", f"{method}_{path}")
        print(f"🧪 Testing {method} {path} ({operation_id})")

        try:
            # Prepare request based on endpoint requirements
            headers, body, params = await self._prepare_request(path, method, spec)

            # Replace path parameters
            actual_path = self._replace_path_params(path)

            start_time = datetime.now()

            # Make the actual HTTP request
            response = await self.client.request(
                method=method,
                url=actual_path,
                headers=headers,
                json=body,
                params=params,
            )

            end_time = datetime.now()
            response_time = (end_time - start_time).total_seconds() * 1000

            # Determine expected status codes
            expected_statuses = list(spec.get("responses", {}).keys())
            expected_status = int(expected_statuses[0]) if expected_statuses else 200

            # Check if response is successful
            success = str(response.status_code) in expected_statuses

            result = APITestResult(
                endpoint=path,
                method=method,
                status_code=response.status_code,
                expected_status=expected_status,
                success=success,
                response_time_ms=response_time,
                response_body=response.json()
                if response.headers.get("content-type", "").startswith(
                    "application/json"
                )
                else None,
            )

            if not success:
                result.error_message = f"Unexpected status {response.status_code}, expected one of {expected_statuses}"

            self.test_results.append(result)

            # Log result
            status_emoji = "✅" if success else "❌"
            print(f"  {status_emoji} {response.status_code} ({response_time:.1f}ms)")

            if not success:
                print(f"    Error: {result.error_message}")
                print(f"    Response: {response.text[:200]}...")

        except Exception as e:
            print(f"  ❌ Exception: {str(e)}")
            self.test_results.append(
                APITestResult(
                    endpoint=path,
                    method=method,
                    status_code=0,
                    expected_status=200,
                    success=False,
                    response_time_ms=0,
                    error_message=str(e),
                )
            )

    async def _prepare_request(
        self, path: str, method: str, spec: dict[str, Any]
    ) -> tuple[dict[str, str], dict | None, dict | None]:
        """Prepare headers, body, and parameters for a request"""
        headers = {}
        body = None
        params = {}

        # Authentication
        security = spec.get("security", [])
        if security:
            for sec_req in security:
                if "UserJWT" in sec_req and self.user_token:
                    headers["Authorization"] = f"Bearer {self.user_token}"
                elif "DeviceToken" in sec_req and self.device_token:
                    headers["X-Device-Token"] = self.device_token

        # Request body
        request_body = spec.get("requestBody")
        if request_body and method in ["POST", "PUT", "PATCH"]:
            body = self._generate_request_body(path, method, request_body)

        # Query parameters
        parameters = spec.get("parameters", [])
        for param in parameters:
            if param.get("in") == "query":
                params[param["name"]] = self._generate_param_value(param)

        return headers, body, params

    def _replace_path_params(self, path: str) -> str:
        """Replace path parameters with actual values"""
        # Simple parameter replacement - use test data where available
        replacements = {
            "{id}": str(
                self.test_data.get("greenhouse", {}).get("id", str(uuid.uuid4()))
            ),
            "{controller_id}": str(
                self.test_data.get("controller", {}).get("id", str(uuid.uuid4()))
            ),
            "{device_name}": TestConfig.DEVICE_NAME_PATTERN.format(0xAABBCC),
        }

        actual_path = path
        for param, value in replacements.items():
            actual_path = actual_path.replace(param, value)

        return actual_path

    def _generate_request_body(
        self, path: str, method: str, request_body_spec: dict
    ) -> dict[str, Any]:
        """Generate request body based on schema"""
        # This is simplified - in a full implementation, you'd generate data based on the schema
        content = request_body_spec.get("content", {})
        if "application/json" in content:
            schema_ref = content["application/json"].get("schema", {}).get("$ref", "")

            # Generate sample data based on endpoint
            if "greenhouse" in path.lower():
                return {
                    "title": "Test Greenhouse",
                    "description": "Generated test data",
                }
            elif "controller" in path.lower():
                return {
                    "greenhouse_id": str(
                        self.test_data.get("greenhouse", {}).get(
                            "id", str(uuid.uuid4())
                        )
                    ),
                    "device_name": TestConfig.DEVICE_NAME_PATTERN.format(0xDDEEFF),
                    "label": "Test Controller",
                }

        return {}

    def _generate_param_value(self, param: dict) -> Any:
        """Generate parameter value based on schema"""
        param_type = param.get("schema", {}).get("type", "string")

        if param_type == "string":
            if param["name"] == "page":
                return "1"
            elif param["name"] == "page_size":
                return "10"
            else:
                return "test_value"
        elif param_type == "integer":
            return 1
        elif param_type == "boolean":
            return True

        return None

    def generate_report(self) -> dict[str, Any]:
        """Generate comprehensive test report"""
        total_tests = len(self.test_results)
        successful_tests = sum(1 for result in self.test_results if result.success)
        failed_tests = total_tests - successful_tests

        avg_response_time = (
            sum(result.response_time_ms for result in self.test_results) / total_tests
            if total_tests > 0
            else 0
        )

        # Group results by endpoint
        endpoints_summary = {}
        for result in self.test_results:
            endpoint_key = f"{result.method} {result.endpoint}"
            endpoints_summary[endpoint_key] = {
                "success": result.success,
                "status_code": result.status_code,
                "response_time_ms": result.response_time_ms,
                "error_message": result.error_message,
            }

        return {
            "summary": {
                "total_tests": total_tests,
                "successful_tests": successful_tests,
                "failed_tests": failed_tests,
                "success_rate": (successful_tests / total_tests * 100)
                if total_tests > 0
                else 0,
                "average_response_time_ms": avg_response_time,
            },
            "endpoints": endpoints_summary,
            "failed_tests": [
                {
                    "endpoint": f"{result.method} {result.endpoint}",
                    "status_code": result.status_code,
                    "error": result.error_message,
                }
                for result in self.test_results
                if not result.success
            ],
        }

    async def cleanup(self):
        """Cleanup test data and close connections"""
        print("🧹 Cleaning up...")
        await self.client.aclose()


async def main():
    """Main test execution"""
    print("🎯 Verdify API Comprehensive Testing Suite")
    print(f"📡 Testing against: {TestConfig.BASE_URL}")
    print(f"📋 OpenAPI spec: {OPENAPI_SPEC_PATH}")
    print()

    suite = APITestSuite()

    try:
        # Setup
        await suite.setup()

        # Run tests
        await suite.run_comprehensive_tests()

        # Generate report
        report = suite.generate_report()

        # Print summary
        print()
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 50)
        print(f"Total Tests: {report['summary']['total_tests']}")
        print(f"Successful: {report['summary']['successful_tests']}")
        print(f"Failed: {report['summary']['failed_tests']}")
        print(f"Success Rate: {report['summary']['success_rate']:.1f}%")
        print(
            f"Avg Response Time: {report['summary']['average_response_time_ms']:.1f}ms"
        )

        if report["failed_tests"]:
            print()
            print("❌ FAILED TESTS:")
            for failure in report["failed_tests"]:
                print(f"  - {failure['endpoint']}: {failure['error']}")

        # Save detailed report
        report_path = Path(__file__).parent / "api_test_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n📄 Detailed report saved to: {report_path}")

        # Exit with error code if tests failed
        if report["summary"]["failed_tests"] > 0:
            print(
                f"\n🚨 {report['summary']['failed_tests']} tests failed. Check the report for details."
            )
            sys.exit(1)
        else:
            print(f"\n🎉 All {report['summary']['total_tests']} tests passed!")
            sys.exit(0)

    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        sys.exit(1)

    finally:
        await suite.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
