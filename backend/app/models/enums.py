"""
Enum definitions for Verdify API models.
"""
from enum import Enum


class LocationEnum(str, Enum):
    N = "N"
    NE = "NE"
    E = "E"
    SE = "SE"
    S = "S"
    SW = "SW"
    W = "W"
    NW = "NW"


class SensorType(str, Enum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    CO2 = "co2"
    LIGHT = "light"
    SOIL_MOISTURE = "soil_moisture"


# -------------------------------------------------------
# NEW OPENAPI V2 ENUMS
# -------------------------------------------------------
class SensorKind(str, Enum):
    """Sensor kind matching OpenAPI spec."""

    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    VPD = "vpd"
    CO2 = "co2"
    LIGHT = "light"
    SOIL_MOISTURE = "soil_moisture"
    WATER_FLOW = "water_flow"
    WATER_TOTAL = "water_total"
    DEW_POINT = "dew_point"
    ABSOLUTE_HUMIDITY = "absolute_humidity"
    ENTHALPY_DELTA = "enthalpy_delta"
    AIR_PRESSURE = "air_pressure"
    KWH = "kwh"
    GAS_CONSUMPTION = "gas_consumption"
    PPFD = "ppfd"
    WIND_SPEED = "wind_speed"
    RAINFALL = "rainfall"
    POWER = "power"


class SensorScope(str, Enum):
    ZONE = "zone"
    GREENHOUSE = "greenhouse"
    EXTERNAL = "external"


class ActuatorKind(str, Enum):
    FAN = "fan"
    HEATER = "heater"
    VENT = "vent"
    FOGGER = "fogger"
    IRRIGATION_VALVE = "irrigation_valve"
    FERTILIZER_VALVE = "fertilizer_valve"
    PUMP = "pump"
    LIGHT = "light"


class ButtonKind(str, Enum):
    COOL = "cool"
    HEAT = "heat"


class FailSafeState(str, Enum):
    ON = "on"
    OFF = "off"


class SensorValueType(str, Enum):
    FLOAT = "float"
    INT = "int"


class ObservationType(str, Enum):
    """Types of crop observations that can be recorded"""

    GROWTH = "growth"
    PEST = "pest"
    DISEASE = "disease"
    HARVEST = "harvest"
    GENERAL = "general"
