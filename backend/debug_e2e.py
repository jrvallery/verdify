#!/usr/bin/env python3
"""
Debug E2E test runner - avoids app.main import conflicts
"""
import os
import sys
import requests
import json
from datetime import datetime, timezone

# Set base URL
BASE_URL = os.getenv("VERDIFY_BASE_URL", "http://127.0.0.1:8000")
API_V1 = f"{BASE_URL}/api/v1"

def log(msg):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")

def test_health():
    """Test basic health endpoint"""
    log("Testing health endpoint...")
    try:
        r = requests.get(f"{API_V1}/health", timeout=10)
        log(f"Health: {r.status_code} - {r.text}")
        return r.status_code == 200
    except Exception as e:
        log(f"Health check failed: {e}")
        return False

def test_auth_register():
    """Test user registration"""
    log("Testing user registration...")
    try:
        user_data = {
            "username": f"testuser_{datetime.now().microsecond}",
            "email": f"test_{datetime.now().microsecond}@example.com", 
            "password": "testpass123"
        }
        r = requests.post(f"{API_V1}/auth/register", json=user_data, timeout=10)
        log(f"Register: {r.status_code} - {r.text[:200]}")
        return r.status_code in [200, 201]
    except Exception as e:
        log(f"Registration failed: {e}")
        return False

def test_openapi():
    """Test OpenAPI spec endpoint"""
    log("Testing OpenAPI endpoint...")
    try:
        r = requests.get(f"{BASE_URL}/openapi.json", timeout=10)
        log(f"OpenAPI: {r.status_code} - Content length: {len(r.text)}")
        if r.status_code == 200:
            spec = r.json()
            log(f"OpenAPI version: {spec.get('openapi', 'unknown')}")
            log(f"API title: {spec.get('info', {}).get('title', 'unknown')}")
        return r.status_code == 200
    except Exception as e:
        log(f"OpenAPI test failed: {e}")
        return False

def main():
    log(f"Starting E2E debug tests against {BASE_URL}")
    
    tests = [
        ("Health Check", test_health),
        ("OpenAPI Spec", test_openapi), 
        ("Auth Registration", test_auth_register),
    ]
    
    results = []
    for name, test_func in tests:
        log(f"\n--- Running: {name} ---")
        try:
            result = test_func()
            results.append((name, result))
            log(f"✅ PASS: {name}" if result else f"❌ FAIL: {name}")
        except Exception as e:
            log(f"❌ ERROR in {name}: {e}")
            results.append((name, False))
    
    log(f"\n=== SUMMARY ===")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    log(f"Passed: {passed}/{total}")
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        log(f"{status}: {name}")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
