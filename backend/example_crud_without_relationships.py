#!/usr/bin/env python3
"""
Example showing how to perform CRUD operations without SQLModel relationships.

This demonstrates the foreign-key-only approach as specified in sqlmodel.instructions.md.
Instead of using Relationship() with automatic navigation, we use explicit queries
via foreign keys.
"""

from sqlmodel import Session, select

from app.models import *


def example_crud_queries(session: Session):
    """
    Examples of how to navigate between models using explicit foreign keys
    instead of relationships.
    """

    # Example 1: Get greenhouse from controller
    # Old way (with relationships): controller.greenhouse
    # New way (explicit FK query):
    def get_controller_greenhouse(controller_id: str) -> Greenhouse | None:
        controller = session.get(Controller, controller_id)
        if not controller:
            return None
        return session.get(Greenhouse, controller.greenhouse_id)

    # Example 2: Get all sensors for a controller
    # Old way (with relationships): controller.sensors
    # New way (explicit FK query):
    def get_controller_sensors(controller_id: str) -> list[Sensor]:
        return session.exec(
            select(Sensor).where(Sensor.controller_id == controller_id)
        ).all()

    # Example 3: Get zones for a sensor (via SensorZoneMap association)
    # Old way (with relationships): sensor.sensor_zone_maps[0].zone
    # New way (explicit join query):
    def get_sensor_zones(sensor_id: str) -> list[Zone]:
        zone_ids = session.exec(
            select(SensorZoneMap.zone_id).where(SensorZoneMap.sensor_id == sensor_id)
        ).all()
        if not zone_ids:
            return []
        return session.exec(select(Zone).where(Zone.id.in_(zone_ids))).all()

    # Example 4: Get user that owns a greenhouse
    # Old way (with relationships): greenhouse.owner
    # New way (explicit FK query):
    def get_greenhouse_owner(greenhouse_id: str) -> User | None:
        greenhouse = session.get(Greenhouse, greenhouse_id)
        if not greenhouse:
            return None
        return session.get(User, greenhouse.user_id)

    # Example 5: Get all greenhouses for a user
    # Old way (with relationships): user.greenhouses
    # New way (explicit FK query):
    def get_user_greenhouses(user_id: str) -> list[Greenhouse]:
        return session.exec(
            select(Greenhouse).where(Greenhouse.user_id == user_id)
        ).all()

    print("✅ All CRUD examples demonstrate foreign-key-only navigation patterns")


if __name__ == "__main__":
    print("This example shows how to query related models using explicit foreign keys")
    print("instead of SQLModel relationships, as per sqlmodel.instructions.md")
    print("\nKey principles:")
    print("1. 🚫 No Relationship() anywhere")
    print("2. ✅ Use explicit foreign keys with sa_column=Column(ForeignKey(...))")
    print("3. ✅ Navigate via explicit select() queries")
    print("4. ✅ Handle many-to-many via association tables and join queries")
    print(
        "5. ✅ Maintain referential integrity via proper CASCADE/SET NULL constraints"
    )
