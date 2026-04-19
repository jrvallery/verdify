"""Telemetry row schemas — 1:1 onto ESP32-backed DB tables.

Each model mirrors the shape of a hypertable the ingestor writes to:
- ClimateRow           → climate          (30 s cadence; 80 cols)
- Diagnostics          → diagnostics      (60 s cadence)
- EquipmentStateEvent  → equipment_state  (on-change)
- EnergySample         → energy           (5 min cadence)
- SystemStateRow       → system_state     (key/value state)
- OverrideEvent        → override_events  (firmware-emitted silent overrides)

Principles:
- `extra="ignore"` — tolerate DB column additions without breaking old readers.
- Most numeric fields are `float | None` because the schema is permissive; the
  ingestor's per-path validators enforce physical ranges (ClimateRow.rh_avg
  stays in [0,100], etc.) where it matters.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class ClimateRow(BaseModel):
    """climate hypertable row — the 30 s telemetry sweep from the ESP32.

    ~80 columns today (zone temps + RH + VPD for N/S/E/W/case/control/intake,
    dew point, enthalpy, lux/DLI/PPFD, flow + water totals, outdoor (Tempest),
    hydroponics (YINMIK), soil moisture, leaf wetness, wind). Adding a new
    column in the DB is additive; the schema ignores what it doesn't know.
    """

    model_config = ConfigDict(extra="ignore")

    ts: AwareDatetime
    greenhouse_id: str = "vallery"

    # Zone temps
    temp_avg: float | None = None
    temp_north: float | None = None
    temp_south: float | None = None
    temp_east: float | None = None
    temp_west: float | None = None
    temp_case: float | None = None
    temp_control: float | None = None
    temp_intake: float | None = None

    # Zone RH
    rh_avg: float | None = Field(default=None, ge=0, le=100)
    rh_north: float | None = Field(default=None, ge=0, le=100)
    rh_south: float | None = Field(default=None, ge=0, le=100)
    rh_east: float | None = Field(default=None, ge=0, le=100)
    rh_west: float | None = Field(default=None, ge=0, le=100)
    rh_case: float | None = Field(default=None, ge=0, le=100)

    # Zone VPD
    vpd_avg: float | None = Field(default=None, ge=0, le=20)
    vpd_north: float | None = Field(default=None, ge=0, le=20)
    vpd_south: float | None = Field(default=None, ge=0, le=20)
    vpd_east: float | None = Field(default=None, ge=0, le=20)
    vpd_west: float | None = Field(default=None, ge=0, le=20)
    vpd_control: float | None = Field(default=None, ge=0, le=20)

    # Psychrometrics
    dew_point: float | None = None
    abs_humidity: float | None = None
    enthalpy_delta: float | None = None

    # Light
    lux: float | None = None
    dli_today: float | None = None
    ppfd: float | None = None
    dli_par_today: float | None = None

    # Water
    flow_gpm: float | None = None
    water_total_gal: float | None = None
    mister_water_today: float | None = None

    # Outdoor (Tempest + HA)
    outdoor_temp_f: float | None = None
    outdoor_rh_pct: float | None = Field(default=None, ge=0, le=100)
    outdoor_lux: float | None = None
    outdoor_illuminance: float | None = None
    pressure_hpa: float | None = None
    precip_in: float | None = Field(default=None, ge=0)
    precip_intensity_in_h: float | None = Field(default=None, ge=0)
    uv_index: float | None = Field(default=None, ge=0, le=20)
    wind_speed_mph: float | None = Field(default=None, ge=0)
    wind_direction_deg: float | None = Field(default=None, ge=0, le=360)
    wind_gust_mph: float | None = Field(default=None, ge=0)
    wind_lull_mph: float | None = Field(default=None, ge=0)
    wind_speed_avg_mph: float | None = Field(default=None, ge=0)
    wind_direction_avg_deg: float | None = Field(default=None, ge=0, le=360)
    feels_like_f: float | None = None
    wet_bulb_temp_f: float | None = None
    vapor_pressure_inhg: float | None = Field(default=None, ge=0)
    lightning_count: int | None = None
    lightning_avg_dist_mi: float | None = Field(default=None, ge=0)
    solar_altitude_deg: float | None = None
    solar_azimuth_deg: float | None = None

    # Hydroponics (YINMIK)
    hydro_ph: float | None = Field(default=None, ge=0, le=14)
    hydro_ec_us_cm: float | None = Field(default=None, ge=0)
    hydro_tds_ppm: float | None = Field(default=None, ge=0)
    hydro_water_temp_f: float | None = None
    hydro_orp_mv: float | None = None
    hydro_battery_pct: float | None = Field(default=None, ge=0, le=100)

    # Nutrient runoff (fertigation)
    ph_input: float | None = Field(default=None, ge=0, le=14)
    ec_input: float | None = Field(default=None, ge=0)
    ph_runoff_wall: float | None = Field(default=None, ge=0, le=14)
    ec_runoff_wall: float | None = Field(default=None, ge=0)
    ph_runoff_center: float | None = Field(default=None, ge=0, le=14)
    ec_runoff_center: float | None = Field(default=None, ge=0)

    # Soil moisture
    moisture_north: float | None = None
    moisture_south: float | None = None
    moisture_center: float | None = None
    soil_moisture_west: float | None = None
    soil_temp_west: float | None = None

    # Leaf telemetry
    leaf_temp_north: float | None = None
    leaf_temp_south: float | None = None
    leaf_wetness_north: float | None = None
    leaf_wetness_south: float | None = None

    # Intake sensor
    intake_rh: float | None = Field(default=None, ge=0, le=100)
    intake_vpd: float | None = Field(default=None, ge=0, le=20)


class Diagnostics(BaseModel):
    """diagnostics hypertable row — ESP32 health heartbeat every 60 s."""

    model_config = ConfigDict(extra="ignore")

    ts: AwareDatetime
    greenhouse_id: str = "vallery"
    wifi_rssi: float | None = Field(default=None, ge=-120, le=0)
    heap_bytes: float | None = Field(default=None, ge=0)
    uptime_s: float | None = Field(default=None, ge=0)
    probe_health: str | None = None
    reset_reason: str | None = None
    firmware_version: str | None = None
    # FW-10 + OBS-3 additions
    active_probe_count: int | None = Field(default=None, ge=0, le=4)
    relief_cycle_count: int | None = Field(default=None, ge=0)
    vent_latch_timer_s: int | None = Field(default=None, ge=0, le=1800)


# Every equipment_state row asserts one of these. Keep the literal in sync
# with the dispatcher's emission set; the drift guard test confirms it against
# the enum that firmware controls.yaml publishes.
EquipmentId = Literal[
    "fan1",
    "fan2",
    "vent",
    "fog",
    "heat1",
    "heat2",
    "mister_south",
    "mister_west",
    "mister_center",
    "mister_any",
    "drip_wall",
    "drip_center",
    "mister_south_fert",
    "mister_west_fert",
    "drip_wall_fert",
    "drip_center_fert",
    "fert_master_valve",
    "water_flowing",
    "leak_detected",
    "gl1",
    "gl2",
    "grow_light",
    "dehum",
    "safety_dehum",
    "occupancy",
    "door_open",
]


class EquipmentStateEvent(BaseModel):
    """equipment_state hypertable row — on-change relay events."""

    model_config = ConfigDict(extra="ignore")

    ts: AwareDatetime
    equipment: str
    state: bool
    greenhouse_id: str = "vallery"


class EnergySample(BaseModel):
    """energy hypertable row — 5 min from Shelly EM50 + derived breakdown."""

    model_config = ConfigDict(extra="ignore")

    ts: AwareDatetime
    greenhouse_id: str = "vallery"
    watts_total: float | None = None  # Signed (may be negative during export)
    watts_heat: float | None = None
    watts_fans: float | None = None
    watts_other: float | None = None
    kwh_today: float | None = Field(default=None, ge=0)


class SystemStateRow(BaseModel):
    """system_state hypertable row — key/value persistent state
    (e.g., greenhouse_state, occupancy_active, door_open)."""

    model_config = ConfigDict(extra="ignore")

    ts: AwareDatetime
    entity: str
    value: str  # Free-form — mode names, booleans-as-strings, floats-as-strings all land here
    greenhouse_id: str = "vallery"


class OverrideEvent(BaseModel):
    """override_events hypertable row — OBS-1e silent firmware overrides.

    `override_type` is a comma-separated set of flag names (see
    firmware/lib/greenhouse_types.h OverrideFlags). `details` is a JSONB blob
    with the per-flag state at emission time.
    """

    model_config = ConfigDict(extra="ignore")

    ts: AwareDatetime
    override_type: str
    mode: str | None = None  # controller mode at emission (SEALED_MIST, VENTILATE, ...)
    details: dict | None = None
    greenhouse_id: str = "vallery"
