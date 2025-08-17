#!/usr/bin/env python3

import os
import sys
import uuid

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient

from app.main import app


def test_create_observation():
    client = TestClient(app)

    # Create a user first
    user_data = {
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User",
    }

    user_response = client.post("/api/v1/users/signup", json=user_data)
    print(f"User creation: {user_response.status_code}")
    if user_response.status_code != 201:
        print(f"User response: {user_response.text}")
        return

    # Login to get token
    login_data = {
        "username": user_data["email"],
        "password": user_data["password"],
    }
    login_response = client.post("/api/v1/login/access-token", data=login_data)
    print(f"Login: {login_response.status_code}")
    if login_response.status_code != 200:
        print(f"Login response: {login_response.text}")
        return

    tokens = login_response.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # Create greenhouse
    greenhouse_data = {"name": "Test Greenhouse", "location": "Test Location"}
    greenhouse_response = client.post(
        "/api/v1/greenhouses/", json=greenhouse_data, headers=headers
    )
    print(f"Greenhouse creation: {greenhouse_response.status_code}")
    if greenhouse_response.status_code != 201:
        print(f"Greenhouse response: {greenhouse_response.text}")
        return

    greenhouse = greenhouse_response.json()
    print(f"Created greenhouse: {greenhouse['id']}")

    # Create crop
    crop_data = {
        "name": "Test Tomato",
        "variety": "Cherry",
        "species": "Solanum lycopersicum",
    }
    crop_response = client.post("/api/v1/crops/", json=crop_data, headers=headers)
    print(f"Crop creation: {crop_response.status_code}")
    # This might not exist, let's check what crops endpoints are available

    # Let's just try to create an observation with a fake zone_crop_id to see validation
    observation_data = {
        "zone_crop_id": str(uuid.uuid4()),
        "observation_text": "Test observation",
        "observed_at": "2024-01-15T10:00:00Z",
        "observation_type": "growth",
    }

    print("Sending observation request with data:", observation_data)

    observation_response = client.post(
        "/api/v1/observations/observations", json=observation_data, headers=headers
    )

    print(f"Observation Status: {observation_response.status_code}")
    print(f"Observation Response: {observation_response.text}")

    if observation_response.status_code == 422:
        print("Validation errors:")
        try:
            errors = observation_response.json()
            import json

            print(json.dumps(errors, indent=2))
        except:
            print("Could not parse response as JSON")


if __name__ == "__main__":
    test_create_observation()
