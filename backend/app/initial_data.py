import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine, init_db
from app.crud.actuator import create_actuator
from app.crud.controller import create_controller
from app.crud.greenhouses import create_greenhouse
from app.crud.sensors import create_sensor
from app.crud.zone import create_zone
from app.models import (
    ActuatorCreate,
    ActuatorKind,
    ConfigSnapshot,
    ConfigSnapshotCreate,
    ControllerCreate,
    Greenhouse,
    GreenhouseCreate,
    LocationEnum,
    Plan,
    PlanCreate,
    SensorCreate,
    SensorKind,
    SensorScope,
    User,
    ZoneCreate,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_seed_data(session: Session) -> dict[str, Any]:
    """
    Create comprehensive seed data for all entities.
    Returns dictionary with important IDs and tokens for testing.
    """
    result = {}

    # Get the superuser to use as owner
    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        raise ValueError("Superuser not found - run init_db first")

    # 1. Create greenhouse
    greenhouse_data = GreenhouseCreate(
        title="Seed Data Greenhouse",
        description="A comprehensive seed greenhouse with all entity types",
        location="Test Location",
        timezone="UTC",
    )
    greenhouse = create_greenhouse(
        session=session, greenhouse_create=greenhouse_data, owner_id=user.id
    )
    result["greenhouse_id"] = str(greenhouse.id)
    logger.info(f"✅ Created greenhouse: {greenhouse.id}")
    logger.info(f"   Title: {greenhouse.title}")

    # 2. Create zone
    zone_data = ZoneCreate(
        greenhouse_id=greenhouse.id,
        zone_number=1,
        location=LocationEnum.N,
        context_text="Primary growing zone",
    )
    zone = create_zone(session=session, z_in=zone_data)
    result["zone_id"] = str(zone.id)
    logger.info(f"✅ Created zone: {zone.id}")
    logger.info(f"   Zone Number: {zone.zone_number}, Location: {zone.location}")

    # 3. Create controller with device token
    device_token = secrets.token_urlsafe(32)
    device_token_hash = f"hashed_{device_token}"  # In real implementation, this would be properly hashed
    controller_data = ControllerCreate(
        greenhouse_id=greenhouse.id,
        label="Seed Climate Controller",
        device_name="verdify-abc123",
        is_climate_controller=True,
        hw_version="2.1",
        fw_version="1.5.2",
        hardware_profile="kincony_a16s",
        device_token_hash=device_token_hash,
        token_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        claimed_at=datetime.now(timezone.utc),
        first_seen=datetime.now(timezone.utc),
        token_exchange_completed=True,
    )
    controller = create_controller(session=session, c_in=controller_data)
    result["controller_id"] = str(controller.id)
    result["device_token"] = device_token
    result["device_name"] = controller.device_name
    logger.info(f"✅ Created controller: {controller.id}")
    logger.info(f"   Device Name: {controller.device_name}")
    logger.info(f"   Label: {controller.label}")

    # 4. Create sensors
    sensors = []
    sensor_configs = [
        {
            "name": "Temperature Sensor",
            "kind": SensorKind.TEMPERATURE,
            "modbus_slave_id": 1,
            "modbus_reg": 30001,
        },
        {
            "name": "Humidity Sensor",
            "kind": SensorKind.HUMIDITY,
            "modbus_slave_id": 1,
            "modbus_reg": 30002,
        },
        {
            "name": "CO2 Sensor",
            "kind": SensorKind.CO2,
            "modbus_slave_id": 1,
            "modbus_reg": 30003,
        },
        {
            "name": "Light Sensor",
            "kind": SensorKind.LIGHT,
            "modbus_slave_id": 1,
            "modbus_reg": 30004,
        },
    ]

    for config in sensor_configs:
        sensor_data = SensorCreate(
            controller_id=controller.id,
            name=config["name"],
            kind=config["kind"],
            scope=SensorScope.ZONE,
            modbus_slave_id=config["modbus_slave_id"],
            modbus_reg=config["modbus_reg"],
            value_type="float",
            include_in_climate_loop=True,
        )
        sensor = create_sensor(session=session, s_in=sensor_data)
        sensors.append(sensor)
        logger.info(f"✅ Created sensor: {sensor.id}")
        logger.info(
            f"   Name: {sensor.name}, Kind: {sensor.kind}, Modbus: {sensor.modbus_slave_id}:{sensor.modbus_reg}"
        )

    result["sensor_ids"] = [str(s.id) for s in sensors]

    # 5. Create actuators
    actuators = []
    actuator_configs = [
        {"name": "Exhaust Fan", "kind": ActuatorKind.FAN, "relay_channel": 1},
        {"name": "Intake Fan", "kind": ActuatorKind.FAN, "relay_channel": 2},
        {"name": "Heater", "kind": ActuatorKind.HEATER, "relay_channel": 3},
        {"name": "Humidifier", "kind": ActuatorKind.HUMIDIFIER, "relay_channel": 4},
    ]

    for config in actuator_configs:
        actuator_data = ActuatorCreate(
            controller_id=controller.id,
            name=config["name"],
            kind=config["kind"],
            relay_channel=config["relay_channel"],
        )
        actuator = create_actuator(session=session, actuator_in=actuator_data)
        actuators.append(actuator)
        logger.info(f"✅ Created actuator: {actuator.id}")
        logger.info(
            f"   Name: {actuator.name}, Kind: {actuator.kind}, Relay: {actuator.relay_channel}"
        )

    result["actuator_ids"] = [str(a.id) for a in actuators]

    # 6. Create a plan
    plan_payload = {
        "version": 1,
        "greenhouse_id": str(greenhouse.id),
        "zones": [
            {
                "zone_id": str(zone.id),
                "zone_number": zone.zone_number,
                "target_temperature": 22.0,
                "target_humidity": 65.0,
                "light_hours": 16,
            }
        ],
        "schedule": {
            "day_start": "06:00",
            "day_end": "22:00",
            "temperature_day": 22.0,
            "temperature_night": 18.0,
        },
    }

    plan_etag = f"plan:v1:{secrets.token_hex(4)}"
    plan_data = PlanCreate(
        greenhouse_id=greenhouse.id,
        version=1,
        payload=plan_payload,
        etag=plan_etag,
        is_active=True,
        effective_from=datetime.now(timezone.utc),
        effective_to=datetime.now(timezone.utc) + timedelta(days=30),
        created_by=user.id,
    )

    plan = Plan.model_validate(plan_data.model_dump())
    session.add(plan)
    session.commit()
    session.refresh(plan)
    result["plan_id"] = str(plan.id)
    result["plan_etag"] = plan.etag
    logger.info(f"✅ Created plan: {plan.id}")
    logger.info(f"   Version: {plan.version}, ETag: {plan.etag}")

    # 7. Create a config snapshot
    config_payload = {
        "version": 1,
        "greenhouse_id": str(greenhouse.id),
        "materialized_at": datetime.now(timezone.utc).isoformat(),
        "controllers": [
            {
                "id": str(controller.id),
                "device_name": controller.device_name,
                "label": controller.label,
                "is_climate_controller": controller.is_climate_controller,
                "sensors": [
                    {
                        "id": str(s.id),
                        "name": s.name,
                        "kind": s.kind,
                        "modbus_slave_id": s.modbus_slave_id,
                        "modbus_reg": s.modbus_reg,
                        "scope": s.scope,
                    }
                    for s in sensors
                ],
                "actuators": [
                    {
                        "id": str(a.id),
                        "name": a.name,
                        "kind": a.kind,
                        "relay_channel": a.relay_channel,
                    }
                    for a in actuators
                ],
            }
        ],
        "zones": [
            {
                "id": str(zone.id),
                "zone_number": zone.zone_number,
                "location": zone.location,
                "context_text": zone.context_text,
            }
        ],
    }

    config_etag = f"config:v1:{secrets.token_hex(4)}"
    config_data = ConfigSnapshotCreate(
        greenhouse_id=greenhouse.id,
        version=1,
        etag=config_etag,
        payload=config_payload,
        created_by=user.id,
    )

    config_snapshot = ConfigSnapshot.model_validate(config_data.model_dump())
    session.add(config_snapshot)
    session.commit()
    session.refresh(config_snapshot)
    result["config_id"] = str(config_snapshot.id)
    result["config_etag"] = config_snapshot.etag
    logger.info(f"✅ Created config snapshot: {config_snapshot.id}")
    logger.info(f"   Version: {config_snapshot.version}, ETag: {config_snapshot.etag}")

    return result


def init() -> None:
    with Session(engine) as session:
        init_db(session)


def main() -> None:
    logger.info("🌱 Creating comprehensive seed data...")
    logger.info("=" * 60)

    # Initialize DB (creates superuser)
    init()

    # Create seed data
    with Session(engine) as session:
        # Check if seed data already exists (idempotent)
        existing_greenhouse = session.exec(
            select(Greenhouse).where(Greenhouse.title == "Seed Data Greenhouse")
        ).first()

        if existing_greenhouse:
            logger.info("✅ Seed data already exists - skipping creation")
            logger.info(f"   Existing greenhouse: {existing_greenhouse.id}")
            return

        try:
            result = create_seed_data(session)

            logger.info("=" * 60)
            logger.info("🎉 Seed data creation completed successfully!")
            logger.info("")
            logger.info("📋 Important IDs and Tokens for Testing:")
            logger.info("=" * 60)
            logger.info(f"🏡 Greenhouse ID:    {result['greenhouse_id']}")
            logger.info(f"🌱 Zone ID:          {result['zone_id']}")
            logger.info(f"🎮 Controller ID:    {result['controller_id']}")
            logger.info(f"📟 Device Name:      {result['device_name']}")
            logger.info(f"🔑 Device Token:     {result['device_token']}")
            logger.info(f"📊 Plan ID:          {result['plan_id']}")
            logger.info(f"🏷️  Plan ETag:        {result['plan_etag']}")
            logger.info(f"⚙️  Config ID:        {result['config_id']}")
            logger.info(f"🏷️  Config ETag:      {result['config_etag']}")
            logger.info("")
            logger.info("🧪 Test Commands:")
            logger.info("=" * 60)
            logger.info("# Get superuser token:")
            logger.info(
                'JWT_TOKEN=$(curl -s -X POST "http://localhost:8000/auth/login" \\'
            )
            logger.info('  -H "Content-Type: application/x-www-form-urlencoded" \\')
            logger.info(
                f'  -d "username={settings.FIRST_SUPERUSER}&password={settings.FIRST_SUPERUSER_PASSWORD}" \\'
            )
            logger.info(
                "  | python3 -c \"import sys, json; print(json.load(sys.stdin)['access_token'])\")"
            )
            logger.info("")
            logger.info("# Fetch config via device route:")
            logger.info(
                f'curl -X GET "http://localhost:8000/controllers/by-name/{result["device_name"]}/config" \\'
            )
            logger.info(f'  -H "X-Device-Token: {result["device_token"]}"')
            logger.info("")
            logger.info("# Create telemetry:")
            logger.info('curl -X POST "http://localhost:8000/telemetry" \\')
            logger.info(f'  -H "X-Device-Token: {result["device_token"]}" \\')
            logger.info('  -H "Content-Type: application/json" \\')
            logger.info(
                f'  -d \'{{"sensor_readings": [{{"sensor_id": "{result["sensor_ids"][0]}", "value": 23.5, "timestamp": "2024-01-01T12:00:00Z"}}]}}\''
            )
            logger.info("")
            logger.info("# List resources:")
            logger.info(
                'curl -X GET "http://localhost:8000/greenhouses/" -H "Authorization: Bearer $JWT_TOKEN"'
            )
            logger.info(
                'curl -X GET "http://localhost:8000/zones/" -H "Authorization: Bearer $JWT_TOKEN"'
            )
            logger.info(
                'curl -X GET "http://localhost:8000/controllers/" -H "Authorization: Bearer $JWT_TOKEN"'
            )

        except Exception as e:
            logger.error(f"❌ Failed to create seed data: {e}")
            session.rollback()
            raise


if __name__ == "__main__":
    main()
