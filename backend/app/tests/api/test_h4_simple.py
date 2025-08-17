"""
Simple working test for H4 observation functionality using API endpoints.
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import create_access_token
from app.models.crops import ZoneCrop
from app.tests.conftest import create_greenhouse_zone_crop_chain
from app.tests.utils.user import create_random_user


def create_test_token(user_id) -> str:
    """Helper to create access token for testing."""
    return create_access_token(subject=user_id, expires_delta=timedelta(minutes=30))


def test_h4_create_and_filter_observations(client: TestClient, db: Session) -> None:
    """Test H4 functionality: create observations with types and filter them."""
    # Setup test data
    user = create_random_user(db)
    access_token = create_test_token(user.id)
    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db, owner=user)

    # Create zone crop
    zone_crop = ZoneCrop(
        zone_id=zone.id,
        crop_id=crop.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(zone_crop)
    db.commit()
    db.refresh(zone_crop)

    # Test 1: Create observations with different types
    observation_data = [
        {"type": "growth", "notes": "Plants growing well"},
        {"type": "pest", "notes": "Found aphids on leaves"},
        {"type": "harvest", "notes": "First tomatoes ready"},
        {"type": None, "notes": "General observation"},
    ]

    created_observations = []
    for i, data in enumerate(observation_data):
        payload = {
            "zone_crop_id": str(zone_crop.id),
            "notes": data["notes"],
            "observed_at": f"2024-01-{10+i:02d}T10:00:00Z",
        }

        # Add observation_type if provided
        if data["type"]:
            payload["observation_type"] = data["type"]

        response = client.post(
            "/api/v1/observations",
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
        )

        if response.status_code != 201:
            print(f"Request failed with {response.status_code}: {response.text}")
            print(f"Payload was: {payload}")

        assert response.status_code == 201
        observation = response.json()
        assert observation["observation_type"] == data["type"]
        assert observation["notes"] == data["notes"]
        assert "created_at" in observation  # H4 requirement: server default
        created_observations.append(observation)

    # Test 2: Filter by observation_type
    response = client.get(
        "/api/v1/observations?observation_type=growth",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["observation_type"] == "growth"
    assert data["total"] == 1

    # Test 3: Filter by greenhouse_id
    response = client.get(
        f"/api/v1/observations?greenhouse_id={greenhouse.id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 4  # All observations in this greenhouse
    assert data["total"] == 4

    # Test 4: Test sorting (H4 requirement: sort by observation_date maps to observed_at)
    response = client.get(
        "/api/v1/observations?sort=-observation_date",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 4

    # Should be sorted by observed_at descending (newest first)
    observed_dates = [obs["observed_at"] for obs in data["data"]]
    assert observed_dates[0] > observed_dates[1] > observed_dates[2] > observed_dates[3]

    # Test 5: Combined filters - type + greenhouse
    response = client.get(
        f"/api/v1/observations?observation_type=pest&greenhouse_id={greenhouse.id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["observation_type"] == "pest"
    assert data["total"] == 1


def test_h4_invalid_observation_type(client: TestClient, db: Session) -> None:
    """Test that invalid observation_type values are rejected."""
    user = create_random_user(db)
    access_token = create_test_token(user.id)
    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db, owner=user)

    zone_crop = ZoneCrop(
        zone_id=zone.id,
        crop_id=crop.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(zone_crop)
    db.commit()
    db.refresh(zone_crop)

    # Try to create observation with invalid type
    data = {
        "zone_crop_id": str(zone_crop.id),
        "observation_type": "invalid_type",
        "notes": "This should fail",
        "observed_at": "2024-01-15T10:00:00Z",
    }

    response = client.post(
        "/api/v1/observations",
        headers={"Authorization": f"Bearer {access_token}"},
        json=data,
    )

    assert response.status_code == 422  # Validation error


def test_h4_created_at_server_default(client: TestClient, db: Session) -> None:
    """Test that created_at gets populated by server (H4 requirement)."""
    user = create_random_user(db)
    access_token = create_test_token(user.id)
    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db, owner=user)

    zone_crop = ZoneCrop(
        zone_id=zone.id,
        crop_id=crop.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(zone_crop)
    db.commit()
    db.refresh(zone_crop)

    before_creation = datetime.now(timezone.utc)

    data = {
        "zone_crop_id": str(zone_crop.id),
        "observation_type": "disease",
        "notes": "Test disease observation",
        "observed_at": "2024-01-15T10:00:00Z",
    }

    response = client.post(
        "/api/v1/observations",
        headers={"Authorization": f"Bearer {access_token}"},
        json=data,
    )

    after_creation = datetime.now(timezone.utc)

    assert response.status_code == 201
    observation = response.json()

    # Should have created_at populated by server
    assert "created_at" in observation
    assert observation["created_at"] is not None

    # created_at should be recent (within our test window)
    created_at = datetime.fromisoformat(
        observation["created_at"].replace("Z", "+00:00")
    )
    assert before_creation <= created_at <= after_creation
