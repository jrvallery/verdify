#!/usr/bin/env python3

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient

from app.main import app
from app.tests.utils.utils import get_superuser_token_headers


def test_create_observation():
    client = TestClient(app)

    # Get auth headers
    headers = get_superuser_token_headers(client)

    # Try to create an observation
    observation_data = {
        "observation_text": "Test observation",
        "observed_at": "2024-01-15T10:00:00Z",
        "observation_type": "growth",
    }

    print("Sending request with data:", observation_data)

    response = client.post(
        "/api/v1/observations/observations", json=observation_data, headers=headers
    )

    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

    if response.status_code == 422:
        print("Validation errors:")
        try:
            errors = response.json()
            print(errors)
        except:
            print("Could not parse response as JSON")


if __name__ == "__main__":
    test_create_observation()
