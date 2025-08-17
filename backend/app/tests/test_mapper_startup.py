"""
Mapper smoke test to validate SQLModel relationship configuration.
This test ensures all forward references and back_populates pairs are correctly resolved.
"""


def test_mapper_startup():
    """Test that all SQLModel relationships can be configured without errors."""
    from sqlalchemy.orm import configure_mappers

    # If relationships / forward refs are broken, this will raise.
    configure_mappers()


def test_relationship_pairs_exist():
    """Test that expected relationship properties exist on both sides."""
    import app.models as m

    # Define expected relationship pairs: (Class, property, Target, target_property)
    pairs = [
        (m.Controller, "sensors", m.Sensor, "controller"),
        (m.Controller, "actuators", m.Actuator, "controller"),
        (m.Controller, "buttons", m.ControllerButton, "controller"),
        (m.Controller, "equipment", m.Equipment, "controller"),
        (m.Controller, "fan_groups", m.FanGroup, "controller"),
        (m.Zone, "sensor_zone_maps", m.SensorZoneMap, "zone"),
        (m.Sensor, "zone_mappings", m.SensorZoneMap, "sensor"),
        (m.FanGroup, "members", m.FanGroupMember, "group"),
        (m.Actuator, "fan_group_memberships", m.FanGroupMember, "actuator"),
        (m.Greenhouse, "controllers", m.Controller, "greenhouse"),
        (m.Greenhouse, "zones", m.Zone, "greenhouse"),
    ]

    for a, a_prop, b, b_prop in pairs:
        assert hasattr(a, a_prop), f"{a.__name__}.{a_prop} missing"
        assert hasattr(b, b_prop), f"{b.__name__}.{b_prop} missing"
