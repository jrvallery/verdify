#!/usr/bin/env python3
"""
Minimal E2E test runner with detailed debugging
"""
import os
import sys
import requests
import json
from datetime import datetime, timezone
import secrets

# Set base URL
BASE_URL = os.getenv("VERDIFY_BASE_URL", "http://127.0.0.1:8000")
API_V1 = f"{BASE_URL}/api/v1"

def log(msg):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}")

def test_auth_flow():
    """Test the full auth flow and return token"""
    log("=== Testing Auth Flow ===")
    
    session = requests.Session()
    
    # Register user
    email = f"e2e-debug-{secrets.token_hex(4)}@example.com"
    user_data = {
        "email": email,
        "password": "StrongPass!234",
        "full_name": "E2E Debug User"
    }
    
    log(f"Registering user: {email}")
    r = session.post(f"{API_V1}/auth/register", json=user_data, timeout=10)
    log(f"Register response: {r.status_code} - {r.text[:200]}")
    
    if r.status_code != 201:
        return None, None
    
    # Login
    login_data = {
        "username": email,
        "password": "StrongPass!234"
    }
    log(f"Logging in user: {email}")
    r = session.post(
        f"{API_V1}/auth/login", 
        data=login_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=10
    )
    log(f"Login response: {r.status_code} - {r.text[:200]}")
    
    if r.status_code != 200:
        return None, None
    
    token = r.json()["access_token"]
    session.headers.update({"Authorization": f"Bearer {token}"})
    
    # Test token
    r = session.post(f"{API_V1}/auth/test-token", timeout=10)
    log(f"Test token response: {r.status_code}")
    
    return session, token

def test_greenhouse_flow(session):
    """Test greenhouse creation"""
    log("=== Testing Greenhouse Flow ===")
    
    gh_data = {
        "title": f"Debug GH {secrets.token_hex(3)}",
        "description": "Debug greenhouse",
        "latitude": 37.77,
        "longitude": -122.42,
        "min_temp_c": 9.0,
        "max_temp_c": 31.0,
        "min_vpd_kpa": 0.4,
        "max_vpd_kpa": 2.2,
        "context_text": "debug-test",
    }
    
    log(f"Creating greenhouse with auth headers: {session.headers}")
    r = session.post(f"{API_V1}/greenhouses/", json=gh_data, timeout=10)
    log(f"Greenhouse create response: {r.status_code} - {r.text[:200]}")
    
    if r.status_code == 201:
        gh = r.json()
        log(f"Created greenhouse ID: {gh['id']}")
        return gh
    
    return None

def test_zones_flow(session, greenhouse):
    """Test zone creation"""
    log("=== Testing Zones Flow ===")
    
    if not greenhouse:
        log("No greenhouse available for zone test")
        return None
    
    zone_data = {
        "greenhouse_id": greenhouse["id"],
        "zone_number": 1,
        "location": "N",
        "title": "Debug Zone",
        "context_text": "debug-zone",
    }
    
    log(f"Creating zone for greenhouse {greenhouse['id']}")
    log(f"Zone data: {json.dumps(zone_data, indent=2)}")
    log(f"Session headers: {dict(session.headers)}")
    
    r = session.post(f"{API_V1}/zones/", json=zone_data, timeout=10)
    log(f"Zone create response: {r.status_code}")
    log(f"Zone response body: {r.text}")
    log(f"Zone response headers: {dict(r.headers)}")
    
    if r.status_code == 201:
        zone = r.json()
        log(f"Created zone ID: {zone['id']}")
        return zone
    else:
        log(f"Zone creation failed with status {r.status_code}")
        return None

def main():
    log(f"Starting debug E2E tests against {BASE_URL}")
    
    # Test auth
    session, token = test_auth_flow()
    if not session:
        log("❌ Auth flow failed")
        return False
    
    log("✅ Auth flow successful")
    
    # Test greenhouse
    greenhouse = test_greenhouse_flow(session)
    if not greenhouse:
        log("❌ Greenhouse flow failed")
        return False
    
    log("✅ Greenhouse flow successful")
    
    # Test zones
    zone = test_zones_flow(session, greenhouse)
    if not zone:
        log("❌ Zone flow failed")
        return False
    
    log("✅ Zone flow successful")
    log("✅ All basic flows working!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
