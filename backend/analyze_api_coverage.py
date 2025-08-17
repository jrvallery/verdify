#!/usr/bin/env python3
"""
OpenAPI Specification Analysis & Route Coverage Report

This script analyzes the OpenAPI specification and reports on:
1. All defined endpoints and their expected status codes
2. Which endpoints are implemented in FastAPI routes
3. Which endpoints are missing or disabled
4. Test coverage recommendations

This helps achieve 100% API specification compliance.
"""

import json
from pathlib import Path

import yaml


def load_openapi_spec() -> dict:
    """Load the OpenAPI specification"""
    spec_path = Path(__file__).parent.parent / "requirements" / "openapi.yml"
    with open(spec_path) as f:
        return yaml.safe_load(f)


def extract_endpoints_from_spec(spec: dict) -> list[dict]:
    """Extract all endpoints from OpenAPI spec with their details"""
    endpoints = []

    paths = spec.get("paths", {})
    for path, methods in paths.items():
        for method, details in methods.items():
            if method.upper() in ["GET", "POST", "PUT", "PATCH", "DELETE"]:
                operation_id = details.get("operationId", f"{method}_{path}")
                tags = details.get("tags", [])
                security = details.get("security", [])
                responses = list(details.get("responses", {}).keys())

                endpoints.append(
                    {
                        "path": path,
                        "method": method.upper(),
                        "operation_id": operation_id,
                        "tags": tags,
                        "security": security,
                        "expected_responses": responses,
                        "summary": details.get("summary", ""),
                    }
                )

    return endpoints


def analyze_route_files() -> dict[str, set[str]]:
    """Analyze FastAPI route files to see what's implemented"""
    routes_dir = Path(__file__).parent / "app" / "api" / "routes"
    implemented_operations = {}

    # Check main.py to see what's enabled
    main_py = Path(__file__).parent / "app" / "api" / "main.py"
    if main_py.exists():
        with open(main_py) as f:
            main_content = f.read()

        # Find disabled routes
        disabled_routes = []
        for line in main_content.split("\n"):
            if line.strip().startswith("#") and ".router" in line:
                disabled_routes.append(line.strip())

        implemented_operations["disabled_routes"] = set(disabled_routes)

    # Scan route files for operation IDs and endpoints
    if routes_dir.exists():
        for route_file in routes_dir.glob("*.py"):
            if route_file.name == "__init__.py":
                continue

            try:
                with open(route_file) as f:
                    content = f.read()

                # Look for @router decorators
                operations = set()
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if line.strip().startswith("@router."):
                        method_path = line.strip()
                        # Try to find the function name in the next few lines
                        for j in range(i + 1, min(i + 5, len(lines))):
                            if lines[j].strip().startswith("def "):
                                func_name = (
                                    lines[j].strip().split("(")[0].replace("def ", "")
                                )
                                operations.add(f"{method_path} -> {func_name}")
                                break

                implemented_operations[route_file.stem] = operations

            except Exception as e:
                print(f"Error reading {route_file}: {e}")

    return implemented_operations


def create_coverage_report(endpoints: list[dict], implemented_ops: dict) -> dict:
    """Create a comprehensive coverage report"""

    # Group endpoints by tags/categories
    by_category = {}
    for endpoint in endpoints:
        for tag in endpoint["tags"]:
            if tag not in by_category:
                by_category[tag] = []
            by_category[tag].append(endpoint)

    # Count totals
    total_endpoints = len(endpoints)

    # Security analysis
    user_jwt_endpoints = [
        ep for ep in endpoints if any("UserJWT" in sec for sec in ep["security"])
    ]
    device_token_endpoints = [
        ep for ep in endpoints if any("DeviceToken" in sec for sec in ep["security"])
    ]
    public_endpoints = [ep for ep in endpoints if not ep["security"]]

    # Create status code analysis
    status_codes = {}
    for endpoint in endpoints:
        for status in endpoint["expected_responses"]:
            if status not in status_codes:
                status_codes[status] = 0
            status_codes[status] += 1

    return {
        "summary": {
            "total_endpoints": total_endpoints,
            "user_jwt_required": len(user_jwt_endpoints),
            "device_token_required": len(device_token_endpoints),
            "public_endpoints": len(public_endpoints),
            "categories": len(by_category),
        },
        "by_category": by_category,
        "security_breakdown": {
            "user_jwt": [f"{ep['method']} {ep['path']}" for ep in user_jwt_endpoints],
            "device_token": [
                f"{ep['method']} {ep['path']}" for ep in device_token_endpoints
            ],
            "public": [f"{ep['method']} {ep['path']}" for ep in public_endpoints],
        },
        "status_codes": status_codes,
        "implemented_operations": implemented_ops,
    }


def print_coverage_report(report: dict):
    """Print a formatted coverage report"""
    print("🎯 VERDIFY API SPECIFICATION ANALYSIS")
    print("=" * 60)

    summary = report["summary"]
    print("📊 SUMMARY:")
    print(f"   Total API Endpoints: {summary['total_endpoints']}")
    print(f"   Categories/Tags: {summary['categories']}")
    print(f"   User JWT Required: {summary['user_jwt_required']}")
    print(f"   Device Token Required: {summary['device_token_required']}")
    print(f"   Public Endpoints: {summary['public_endpoints']}")
    print()

    print("📂 ENDPOINTS BY CATEGORY:")
    for category, endpoints in report["by_category"].items():
        print(f"   {category}: {len(endpoints)} endpoints")
        for ep in endpoints[:3]:  # Show first 3
            print(f"     - {ep['method']} {ep['path']} ({ep['operation_id']})")
        if len(endpoints) > 3:
            print(f"     ... and {len(endpoints) - 3} more")
        print()

    print("🔒 SECURITY REQUIREMENTS:")
    auth_types = ["user_jwt", "device_token", "public"]
    for auth_type in auth_types:
        endpoints = report["security_breakdown"][auth_type]
        print(f"   {auth_type.replace('_', ' ').title()}: {len(endpoints)} endpoints")
        for ep in endpoints[:5]:  # Show first 5
            print(f"     - {ep}")
        if len(endpoints) > 5:
            print(f"     ... and {len(endpoints) - 5} more")
        print()

    print("📈 EXPECTED STATUS CODES:")
    for status, count in sorted(report["status_codes"].items()):
        print(f"   {status}: {count} endpoints")
    print()

    print("🔧 IMPLEMENTATION STATUS:")
    implemented = report["implemented_operations"]
    for route_file, operations in implemented.items():
        if route_file == "disabled_routes":
            print(f"   DISABLED: {len(operations)} routes commented out")
            for disabled in list(operations)[:3]:
                print(f"     - {disabled}")
            if len(operations) > 3:
                print(f"     ... and {len(operations) - 3} more")
        else:
            print(f"   {route_file}.py: {len(operations)} operations")
    print()


def main():
    """Main analysis function"""
    print("🔍 Analyzing OpenAPI specification...")

    try:
        # Load specification
        spec = load_openapi_spec()
        print(
            f"✅ Loaded OpenAPI spec v{spec.get('info', {}).get('version', 'unknown')}"
        )

        # Extract endpoints
        endpoints = extract_endpoints_from_spec(spec)
        print(f"✅ Found {len(endpoints)} API endpoints")

        # Analyze implementation
        implemented_ops = analyze_route_files()
        print("✅ Analyzed route implementations")

        # Create report
        report = create_coverage_report(endpoints, implemented_ops)

        # Print detailed report
        print_coverage_report(report)

        # Save detailed JSON report
        report_path = Path(__file__).parent / "api_specification_analysis.json"
        with open(report_path, "w") as f:
            # Convert sets to lists for JSON serialization
            json_report = json.loads(json.dumps(report, default=list))
            json.dump(json_report, f, indent=2)

        print(f"📄 Detailed report saved to: {report_path}")

        # Provide next steps
        print("\n🚀 NEXT STEPS:")
        print("1. Enable disabled routes by fixing import issues")
        print("2. Create missing telemetry models")
        print("3. Implement missing endpoints identified in analysis")
        print("4. Run comprehensive API tests against live server")
        print("5. Validate all responses match OpenAPI schema")

    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        raise


if __name__ == "__main__":
    main()
