"""
Tests for H4 Observation fields & filters functionality.

Tests the new observation_type enum field, created_at server default,
and enhanced filtering capabilities.
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.security import create_access_token
from app.crud.observation import observation as observation_crud
from app.models.crops import ZoneCrop, ZoneCropObservation
from app.models.enums import ObservationType
from app.tests.conftest import create_greenhouse_zone_crop_chain
from app.tests.utils.user import create_random_user


def create_test_token(user_id) -> str:
    """Helper to create access token for testing."""
    return create_access_token(subject=user_id, expires_delta=timedelta(minutes=30))


def test_observation_type_enum_values():
    """Test that ObservationType enum has correct values."""
    assert ObservationType.GROWTH == "growth"
    assert ObservationType.PEST == "pest"
    assert ObservationType.DISEASE == "disease"
    assert ObservationType.HARVEST == "harvest"
    assert ObservationType.GENERAL == "general"


def test_create_observation_with_type(client: TestClient, db: Session) -> None:
    """Test creating observations with observation_type field."""
    # Create test data using helper
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

    # Test creating observation with each observation type
    for obs_type in ["growth", "pest", "disease", "harvest", "general"]:
        data = {
            "zone_crop_id": str(zone_crop.id),
            "observation_type": obs_type,
            "notes": f"Test {obs_type} observation",
            "observed_at": "2024-01-15T10:00:00Z",
        }

        response = client.post(
            "/api/v1/observations",
            headers={"Authorization": f"Bearer {access_token}"},
            json=data,
        )

        assert response.status_code == 201
        observation = response.json()
        assert observation["observation_type"] == obs_type
        assert observation["notes"] == f"Test {obs_type} observation"
        # Should have created_at populated by server
        assert "created_at" in observation
        assert observation["created_at"] is not None


def test_create_observation_without_type(client: TestClient, db: Session) -> None:
    """Test creating observation without observation_type (should be None)."""
    user = create_random_user(db)
    access_token = create_access_token(subject=user.id)
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

    data = {
        "zone_crop_id": str(zone_crop.id),
        "notes": "Observation without type",
        "observed_at": "2024-01-15T10:00:00Z",
    }

    response = client.post(
        "/api/v1/observations",
        headers={"Authorization": f"Bearer {access_token}"},
        json=data,
    )

    assert response.status_code == 201
    observation = response.json()
    assert observation["observation_type"] is None
    assert observation["notes"] == "Observation without type"


def test_filter_observations_by_type(client: TestClient, db: Session) -> None:
    """Test filtering observations by observation_type."""
    user = create_random_user(db)
    access_token = create_access_token(subject=user.id)
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

    # Create observations with different types
    observation_types = ["growth", "pest", "disease"]
    created_observations = []

    for i, obs_type in enumerate(observation_types):
        data = {
            "zone_crop_id": str(zone_crop.id),
            "observation_type": obs_type,
            "notes": f"Test {obs_type} observation {i}",
            "observed_at": f"2024-01-{15+i:02d}T10:00:00Z",
        }

        response = client.post(
            "/api/v1/observations",
            headers={"Authorization": f"Bearer {access_token}"},
            json=data,
        )
        assert response.status_code == 201
        created_observations.append(response.json())

    # Test filtering by each type
    for obs_type in observation_types:
        response = client.get(
            f"/api/v1/observations?observation_type={obs_type}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["observation_type"] == obs_type
        assert data["total"] == 1


def test_filter_observations_by_greenhouse(client: TestClient, db: Session) -> None:
    """Test filtering observations by greenhouse_id."""
    user = create_random_user(db)
    access_token = create_access_token(subject=user.id)

    # Create two greenhouses
    greenhouse1, zone1, crop1 = create_greenhouse_zone_crop_chain(db, owner=user)
    greenhouse2, zone2, crop2 = create_greenhouse_zone_crop_chain(db, owner=user)

    # Create zone_crops for each greenhouse
    zone_crop1 = ZoneCrop(
        zone_id=zone1.id,
        crop_id=crop1.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    zone_crop2 = ZoneCrop(
        zone_id=zone2.id,
        crop_id=crop2.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add_all([zone_crop1, zone_crop2])
    db.commit()
    db.refresh(zone_crop1)
    db.refresh(zone_crop2)

    # Create observations in each greenhouse
    for i, zone_crop in enumerate([zone_crop1, zone_crop2], 1):
        data = {
            "zone_crop_id": str(zone_crop.id),
            "observation_type": "growth",
            "notes": f"Observation in greenhouse {i}",
            "observed_at": f"2024-01-{14+i:02d}T10:00:00Z",
        }

        response = client.post(
            "/api/v1/observations",
            headers={"Authorization": f"Bearer {access_token}"},
            json=data,
        )
        assert response.status_code == 201

    # Test filtering by greenhouse1
    response = client.get(
        f"/api/v1/observations?greenhouse_id={greenhouse1.id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert "greenhouse 1" in data["data"][0]["notes"]

    # Test filtering by greenhouse2
    response = client.get(
        f"/api/v1/observations?greenhouse_id={greenhouse2.id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert "greenhouse 2" in data["data"][0]["notes"]


def test_combined_filters(client: TestClient, db: Session) -> None:
    """Test combining observation_type and greenhouse_id filters."""
    user = create_random_user(db)
    access_token = create_access_token(subject=user.id)
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

    # Create different types of observations
    observations_data = [
        {"type": "growth", "notes": "Growth observation"},
        {"type": "pest", "notes": "Pest observation"},
        {"type": "growth", "notes": "Another growth observation"},
    ]

    for i, obs_data in enumerate(observations_data):
        data = {
            "zone_crop_id": str(zone_crop.id),
            "observation_type": obs_data["type"],
            "notes": obs_data["notes"],
            "observed_at": f"2024-01-{15+i:02d}T10:00:00Z",
        }

        response = client.post(
            "/api/v1/observations",
            headers={"Authorization": f"Bearer {access_token}"},
            json=data,
        )
        assert response.status_code == 201

    # Test filtering by type=growth AND greenhouse_id
    response = client.get(
        f"/api/v1/observations?observation_type=growth&greenhouse_id={greenhouse.id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["total"] == 2
    for obs in data["data"]:
        assert obs["observation_type"] == "growth"


def test_sort_by_observation_date_desc(client: TestClient, db: Session) -> None:
    """Test sorting by observation_date in descending order (default)."""
    user = create_random_user(db)
    access_token = create_access_token(subject=user.id)
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

    # Create observations with different observed_at dates
    dates = ["2024-01-10T10:00:00Z", "2024-01-15T10:00:00Z", "2024-01-12T10:00:00Z"]

    for i, date in enumerate(dates):
        data = {
            "zone_crop_id": str(zone_crop.id),
            "observation_type": "growth",
            "notes": f"Observation {i+1}",
            "observed_at": date,
        }

        response = client.post(
            "/api/v1/observations",
            headers={"Authorization": f"Bearer {access_token}"},
            json=data,
        )
        assert response.status_code == 201

    # Test default sort (should be -observation_date)
    response = client.get(
        "/api/v1/observations",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 3

    # Should be sorted by observed_at descending (newest first)
    observed_dates = [obs["observed_at"] for obs in data["data"]]
    assert observed_dates[0] == "2024-01-15T10:00:00+00:00"  # newest
    assert observed_dates[1] == "2024-01-12T10:00:00+00:00"  # middle
    assert observed_dates[2] == "2024-01-10T10:00:00+00:00"  # oldest


def test_sort_by_observation_date_asc(client: TestClient, db: Session) -> None:
    """Test sorting by observation_date in ascending order."""
    user = create_random_user(db)
    access_token = create_access_token(subject=user.id)
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

    # Create observations with different observed_at dates
    dates = ["2024-01-10T10:00:00Z", "2024-01-15T10:00:00Z", "2024-01-12T10:00:00Z"]

    for i, date in enumerate(dates):
        data = {
            "zone_crop_id": str(zone_crop.id),
            "observation_type": "general",
            "notes": f"Observation {i+1}",
            "observed_at": date,
        }

        response = client.post(
            "/api/v1/observations",
            headers={"Authorization": f"Bearer {access_token}"},
            json=data,
        )
        assert response.status_code == 201

    # Test explicit ascending sort
    response = client.get(
        "/api/v1/observations?sort=observation_date",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 3

    # Should be sorted by observed_at ascending (oldest first)
    observed_dates = [obs["observed_at"] for obs in data["data"]]
    assert observed_dates[0] == "2024-01-10T10:00:00+00:00"  # oldest
    assert observed_dates[1] == "2024-01-12T10:00:00+00:00"  # middle
    assert observed_dates[2] == "2024-01-15T10:00:00+00:00"  # newest


def test_created_at_server_default(client: TestClient, db: Session) -> None:
    """Test that created_at gets a server default value."""
    user = create_random_user(db)
    access_token = create_access_token(subject=user.id)
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

    # Create observation
    data = {
        "zone_crop_id": str(zone_crop.id),
        "observation_type": "harvest",
        "notes": "Test harvest observation",
        "observed_at": "2024-01-15T10:00:00Z",
    }

    before_creation = datetime.now(timezone.utc)

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


def test_invalid_observation_type(client: TestClient, db: Session) -> None:
    """Test that invalid observation_type values are rejected."""
    user = create_random_user(db)
    access_token = create_access_token(subject=user.id)
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


def test_crud_observation_type_filtering(db: Session) -> None:
    """Test CRUD layer observation_type filtering directly."""
    # This tests the CRUD layer without going through the API
    user = create_random_user(db)
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

    # Create observations with different types directly in DB
    observation_data = [
        (ObservationType.GROWTH, "Growth observation"),
        (ObservationType.PEST, "Pest observation"),
        (ObservationType.DISEASE, "Disease observation"),
        (None, "Untyped observation"),
    ]

    created_observations = []
    for obs_type, notes in observation_data:
        observation = ZoneCropObservation(
            zone_crop_id=zone_crop.id,
            observation_type=obs_type,
            notes=notes,
            observed_at=datetime.now(timezone.utc),
        )
        db.add(observation)
        db.flush()
        created_observations.append(observation)

    db.commit()

    # Test filtering by observation_type using CRUD
    growth_obs = observation_crud.get_multi(
        db, user_id=user.id, observation_type=ObservationType.GROWTH
    )
    assert len(growth_obs) == 1
    assert growth_obs[0].observation_type == ObservationType.GROWTH

    pest_obs = observation_crud.get_multi(
        db, user_id=user.id, observation_type=ObservationType.PEST
    )
    assert len(pest_obs) == 1
    assert pest_obs[0].observation_type == ObservationType.PEST

    # Test getting all observations (no filter)
    all_obs = observation_crud.get_multi(db, user_id=user.id)
    assert len(all_obs) == 4

    # Test count with filtering
    growth_count = observation_crud.count(
        db, user_id=user.id, observation_type=ObservationType.GROWTH
    )
    assert growth_count == 1

    total_count = observation_crud.count(db, user_id=user.id)
    assert total_count == 4
