import uuid
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, delete

# Import ALL models early to ensure proper registration
import app.models as models  # noqa: F401

# Force mapper resolution early and deterministically
# models.bootstrap_mappers()  # DISABLED: causing relationship errors
from app.core.config import settings
from app.core.db import engine, init_db
from app.main import app
from app.models import (
    ConfigSnapshot,
    Controller,
    Greenhouse,
    Plan,
    User,
)
from app.tests.utils.user import authentication_token_from_email, create_random_user
from app.tests.utils.utils import get_superuser_token_headers


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[Session, None, None]:
    # Ensure models are imported and schema is created deterministically for tests
    from sqlmodel import SQLModel

    import app.models  # noqa: F401

    # Create schema deterministically for tests
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        init_db(session)
        yield session
        statement = delete(User)
        session.execute(statement)
        session.commit()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )


@pytest.fixture(scope="module")
def test_user(db: Session) -> User:
    """Create a test user."""
    return create_random_user(db)


@pytest.fixture(scope="module")
def test_greenhouse(db: Session, test_user: User) -> Greenhouse:
    """Create a test greenhouse."""
    greenhouse = Greenhouse(
        id=uuid.uuid4(),
        title="Test Greenhouse",
        description="Test greenhouse for testing",
        user_id=test_user.id,
    )
    db.add(greenhouse)
    db.commit()
    db.refresh(greenhouse)
    return greenhouse


@pytest.fixture(scope="function")
def test_controller(test_session, test_greenhouse):
    """Create a test controller with unique device name"""
    from uuid import uuid4

    from app.models import Controller

    controller = Controller(
        device_name=f"test-controller-{uuid4().hex[:8]}",  # Unique name
        greenhouse_id=test_greenhouse.id,
        is_active=True,
        hw_version="1.0.0",
        sw_version="2.1.0",
    )
    test_session.add(controller)
    test_session.commit()
    test_session.refresh(controller)
    return controller


@pytest.fixture(scope="module")
def device_token_headers(test_controller: Controller) -> dict[str, str]:
    """Get device token auth headers."""
    return {"X-Device-Token": test_controller._test_device_token}  # type: ignore


@pytest.fixture(scope="module")
def test_config_snapshot(
    db: Session, test_greenhouse: Greenhouse, test_user: User
) -> ConfigSnapshot:
    """Create a test config snapshot."""
    payload = {
        "version": 1,
        "greenhouse": {"id": str(test_greenhouse.id), "name": test_greenhouse.name},
        "controllers": [],
        "sensors": [],
        "actuators": [],
        "fan_groups": [],
        "buttons": [],
        "state_rules": [],
        "baselines": [],
        "rails": [],
    }

    snapshot = ConfigSnapshot(
        id=uuid.uuid4(),
        greenhouse_id=test_greenhouse.id,
        version=1,
        etag="config:v1:12345678",
        payload=payload,
        created_by=test_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


@pytest.fixture(scope="module")
def test_plan(db: Session, test_greenhouse: Greenhouse, test_user: User) -> Plan:
    """Create a test plan."""
    payload = {
        "version": 1,
        "greenhouse_id": str(test_greenhouse.id),
        "setpoints": {"temperature": 22.0, "humidity": 60.0},
        "irrigation": {"frequency": "daily", "duration": 30},
        "phases": [],
    }

    plan = Plan(
        id=uuid.uuid4(),
        greenhouse_id=test_greenhouse.id,
        version=1,
        payload=payload,
        etag="plan:v1:87654321",
        is_active=True,
        created_by=test_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def create_greenhouse_zone_crop_chain(session: Session, owner: User | None = None):
    """Helper to create a complete greenhouse -> zone -> crop chain for testing"""
    from app.models import Crop, Greenhouse, Zone
    from app.models.enums import LocationEnum

    if owner is None:
        owner = create_random_user(session)

    # Create greenhouse
    greenhouse = Greenhouse(
        name="Test Greenhouse",
        title="Test Greenhouse",  # Add required title field
        user_id=owner.id,
        location="Test Location",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(greenhouse)
    session.commit()
    session.refresh(greenhouse)

    # Create zone
    zone = Zone(
        zone_number=1,  # Add required zone_number
        location=LocationEnum.N,  # Add required location enum
        greenhouse_id=greenhouse.id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(zone)
    session.commit()
    session.refresh(zone)

    # Create crop
    crop = Crop(
        name="Test Tomato",
        description="Test tomato variety",
        expected_yield_per_sqm=5.0,
        growing_days=90,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(crop)
    session.commit()
    session.refresh(crop)

    return greenhouse, zone, crop
