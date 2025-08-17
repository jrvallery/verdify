"""
Tests for zone crop API endpoints
"""
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.models import ZoneCrop


def test_create_zone_crop_with_start_date(
    client: TestClient, db: Session, normal_user_token_headers: dict[str, str]
):
    """Test creating a zone crop with explicit start_date"""
    from app.tests.conftest import create_greenhouse_zone_crop_chain

    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db)

    start_date = datetime.now(timezone.utc)
    zone_crop_data = {
        "zone_id": str(zone.id),
        "crop_id": str(crop.id),
        "start_date": start_date.isoformat(),
        "area_sqm": 50.0,
    }

    response = client.post(
        "/api/v1/zone-crops",
        headers=normal_user_token_headers,
        json=zone_crop_data,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["zone_id"] == str(zone.id)
    assert data["crop_id"] == str(crop.id)
    assert data["start_date"] == start_date.isoformat()
    assert data["area_sqm"] == 50.0
    assert data["is_active"] is True
    assert data["end_date"] is None


def test_create_zone_crop_requires_start_date(
    client: TestClient, db: Session, normal_user_token_headers: dict[str, str]
):
    """Test that creating zone crop requires start_date"""
    from app.tests.conftest import create_greenhouse_zone_crop_chain

    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db)

    zone_crop_data = {
        "zone_id": str(zone.id),
        "crop_id": str(crop.id),
        # Missing start_date
        "area_sqm": 50.0,
    }

    response = client.post(
        "/api/v1/zone-crops",
        headers=normal_user_token_headers,
        json=zone_crop_data,
    )

    assert response.status_code == 422


def test_update_zone_crop_with_end_date(
    client: TestClient, db: Session, normal_user_token_headers: dict[str, str]
):
    """Test updating zone crop with end_date (harvest)"""
    from app.tests.conftest import create_greenhouse_zone_crop_chain

    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db)

    # Create zone crop first
    zone_crop = ZoneCrop(
        zone_id=zone.id,
        crop_id=crop.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
        area_sqm=25.0,
    )
    db.add(zone_crop)
    db.commit()
    db.refresh(zone_crop)

    # Update with end_date and yield
    end_date = datetime.now(timezone.utc)
    update_data = {
        "end_date": end_date.isoformat(),
        "is_active": False,
        "final_yield": 150.5,
    }

    response = client.put(
        f"/api/v1/zone-crops/{zone_crop.id}",
        headers=normal_user_token_headers,
        json=update_data,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["end_date"] == end_date.isoformat()
    assert data["is_active"] is False
    assert data["final_yield"] == 150.5
    assert data["area_sqm"] == 25.0  # Should remain unchanged


def test_list_zone_crops_sort_by_start_date(
    client: TestClient, db: Session, normal_user_token_headers: dict[str, str]
):
    """Test listing zone crops sorted by start_date"""
    from app.tests.conftest import create_greenhouse_zone_crop_chain

    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db)

    # Create multiple zone crops with different start dates
    base_time = datetime.now(timezone.utc)
    zone_crop1 = ZoneCrop(
        zone_id=zone.id,
        crop_id=crop.id,
        start_date=base_time,
        is_active=True,
    )
    zone_crop2 = ZoneCrop(
        zone_id=zone.id,
        crop_id=crop.id,
        start_date=base_time.replace(day=base_time.day - 1),  # Earlier
        is_active=False,
    )
    db.add_all([zone_crop1, zone_crop2])
    db.commit()

    # Test descending sort (newest first)
    response = client.get(
        "/api/v1/zone-crops?sort=-start_date",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) >= 2

    # Should be sorted by start_date descending (newest first)
    dates = [item["start_date"] for item in data["data"]]
    assert dates == sorted(dates, reverse=True)


def test_list_zone_crops_sort_backwards_compatibility(
    client: TestClient, db: Session, normal_user_token_headers: dict[str, str]
):
    """Test that old sort parameter names still work (planted_at -> start_date)"""
    from app.tests.conftest import create_greenhouse_zone_crop_chain

    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db)

    # Create a zone crop
    zone_crop = ZoneCrop(
        zone_id=zone.id,
        crop_id=crop.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(zone_crop)
    db.commit()

    # Test with old parameter name (should still work)
    response = client.get(
        "/api/v1/zone-crops?sort=-planted_at",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) >= 1


def test_list_zone_crops_filter_by_zone(
    client: TestClient, db: Session, normal_user_token_headers: dict[str, str]
):
    """Test filtering zone crops by zone_id"""
    from app.tests.conftest import create_greenhouse_zone_crop_chain

    greenhouse, zone1, crop = create_greenhouse_zone_crop_chain(db)

    # Create second zone in same greenhouse
    from app.models import Zone

    zone2 = Zone(
        name="Zone 2",
        greenhouse_id=greenhouse.id,
        zone_type="growing",
    )
    db.add(zone2)
    db.commit()
    db.refresh(zone2)

    # Create zone crops in different zones
    zone_crop1 = ZoneCrop(
        zone_id=zone1.id,
        crop_id=crop.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    zone_crop2 = ZoneCrop(
        zone_id=zone2.id,
        crop_id=crop.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add_all([zone_crop1, zone_crop2])
    db.commit()

    # Filter by zone1
    response = client.get(
        f"/api/v1/zone-crops?zone_id={zone1.id}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["zone_id"] == str(zone1.id)


def test_list_zone_crops_filter_by_greenhouse(
    client: TestClient, db: Session, normal_user_token_headers: dict[str, str]
):
    """Test filtering zone crops by greenhouse_id"""
    from app.tests.conftest import create_greenhouse_zone_crop_chain

    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db)

    # Create zone crop
    zone_crop = ZoneCrop(
        zone_id=zone.id,
        crop_id=crop.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(zone_crop)
    db.commit()

    # Filter by greenhouse
    response = client.get(
        f"/api/v1/zone-crops?greenhouse_id={greenhouse.id}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["zone_id"] == str(zone.id)


def test_list_zone_crops_filter_by_active_status(
    client: TestClient, db: Session, normal_user_token_headers: dict[str, str]
):
    """Test filtering zone crops by is_active status"""
    from app.tests.conftest import create_greenhouse_zone_crop_chain

    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db)

    # Create active and inactive zone crops
    active_crop = ZoneCrop(
        zone_id=zone.id,
        crop_id=crop.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    inactive_crop = ZoneCrop(
        zone_id=zone.id,
        crop_id=crop.id,
        start_date=datetime.now(timezone.utc),
        is_active=False,
        end_date=datetime.now(timezone.utc),
    )
    db.add_all([active_crop, inactive_crop])
    db.commit()

    # Filter for active only
    response = client.get(
        "/api/v1/zone-crops?is_active=true",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["is_active"] is True

    # Filter for inactive only
    response = client.get(
        "/api/v1/zone-crops?is_active=false",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["is_active"] is False


def test_zone_crop_ownership_validation(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
):
    """Test that users can only access zone crops in their own greenhouses"""
    from app.tests.conftest import create_greenhouse_zone_crop_chain, create_random_user

    # Create another user's greenhouse
    other_user = create_random_user(db)
    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db, owner=other_user)

    zone_crop = ZoneCrop(
        zone_id=zone.id,
        crop_id=crop.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(zone_crop)
    db.commit()
    db.refresh(zone_crop)

    # Try to access with different user's token
    response = client.get(
        f"/api/v1/zone-crops/{zone_crop.id}",
        headers=superuser_token_headers,  # Different user
    )

    assert response.status_code == 403


def test_delete_zone_crop(
    client: TestClient, db: Session, normal_user_token_headers: dict[str, str]
):
    """Test deleting a zone crop"""
    from app.tests.conftest import create_greenhouse_zone_crop_chain

    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db)

    zone_crop = ZoneCrop(
        zone_id=zone.id,
        crop_id=crop.id,
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(zone_crop)
    db.commit()
    db.refresh(zone_crop)

    response = client.delete(
        f"/api/v1/zone-crops/{zone_crop.id}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 204

    # Verify it's deleted
    response = client.get(
        f"/api/v1/zone-crops/{zone_crop.id}",
        headers=normal_user_token_headers,
    )

    assert response.status_code == 404


def test_one_active_crop_per_zone_constraint(
    client: TestClient, db: Session, normal_user_token_headers: dict[str, str]
):
    """Test that only one active crop is allowed per zone"""
    from app.tests.conftest import create_greenhouse_zone_crop_chain

    greenhouse, zone, crop = create_greenhouse_zone_crop_chain(db)

    # Create first active zone crop
    zone_crop_data = {
        "zone_id": str(zone.id),
        "crop_id": str(crop.id),
        "start_date": datetime.now(timezone.utc).isoformat(),
        "is_active": True,
    }

    response = client.post(
        "/api/v1/zone-crops",
        headers=normal_user_token_headers,
        json=zone_crop_data,
    )

    assert response.status_code == 201

    # Try to create second active zone crop in same zone
    response = client.post(
        "/api/v1/zone-crops",
        headers=normal_user_token_headers,
        json=zone_crop_data,
    )

    assert response.status_code == 409  # Conflict
