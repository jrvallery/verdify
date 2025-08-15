import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlmodel import SQLModel, Field, Relationship, JSON
from sqlalchemy import Column, ForeignKey, UniqueConstraint, CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID, ARRAY
from pydantic import EmailStr  # ADD
from enum import Enum

class ButtonType(str):
    COOL = "cool"
    HUMID = "humid"
    HEAT = "heat"

class FailSafeState(str):
    ON = "on"
    OFF = "off"

class SensorType(str, Enum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    CO2 = "co2"
    LIGHT = "light"
    SOIL_MOISTURE = "soil_moisture"

class LocationEnum(str, Enum):
    N  = "N"
    NE = "NE"
    E  = "E"
    SE = "SE"
    S  = "S"
    SW = "SW"
    W  = "W"
    NW = "NW"

# -------------------------------------------------------
# 3.1 Users (app_user)
# -------------------------------------------------------
class User(SQLModel, table=True):
    __tablename__ = "user"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(sa_column=Column("email", nullable=False, unique=True))  # citext in DB
    is_active: bool = Field(default=True, nullable=False)
    is_superuser: bool = Field(default=False, nullable=False)
    full_name: Optional[str] = None
    hashed_password: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)

# ---------------------------
# User DTOs (FastAPI schemas)
# ---------------------------
class UserBase(SQLModel):
    email: EmailStr
    is_active: bool = True
    is_superuser: bool = False
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=40)
    full_name: str | None = Field(default=None, max_length=255)

class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=40)

class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)

class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=40)
    new_password: str = Field(min_length=8, max_length=40)

class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime

class UsersPublic(SQLModel):
    data: List[UserPublic]
    count: int

# -------------------------------------------------------
# 3.2 Greenhouse
# -------------------------------------------------------
class Greenhouse(SQLModel, table=True):
    __tablename__ = "greenhouse"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(sa_column=Column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False))
    title: str
    description: Optional[str] = None
    is_active: bool = Field(default=True, nullable=False)
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Guard rails
    min_temp_c: float = Field(default=7.0, nullable=False)
    max_temp_c: float = Field(default=35.0, nullable=False)
    min_vpd_kpa: float = Field(default=0.30, nullable=False)
    max_vpd_kpa: float = Field(default=2.50, nullable=False)

    # Baseline/context
    climate_baseline: dict = Field(default_factory=dict, sa_type=JSON)
    site_pressure_hpa: Optional[float] = None
    context_text: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
   

    zones: List["Zone"] = Relationship(
        back_populates="greenhouse", 
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )
    controllers: List["Controller"] = Relationship(
        back_populates="greenhouse",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )

# -------------------------------
# Greenhouse DTOs (FastAPI schemas)
# -------------------------------
class GreenhouseBase(SQLModel):
    title: str
    description: Optional[str] = None
    is_active: bool = True
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # guard rails/baseline/context
    min_temp_c: float = 7.0
    max_temp_c: float = 35.0
    min_vpd_kpa: float = 0.30
    max_vpd_kpa: float = 2.50
    climate_baseline: dict = Field(default_factory=dict)
    site_pressure_hpa: Optional[float] = None
    context_text: Optional[str] = None

class GreenhouseCreate(GreenhouseBase):
    owner_id: uuid.UUID

class GreenhouseUpdate(SQLModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    min_temp_c: Optional[float] = None
    max_temp_c: Optional[float] = None
    min_vpd_kpa: Optional[float] = None
    climate_baseline: Optional[dict] = None
    site_pressure_hpa: Optional[float] = None
    context_text: Optional[str] = None

class GreenhousePublic(GreenhouseBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime

class GreenhousesPublic(SQLModel):
    data: List[GreenhousePublic]
    count: int

# -------------------------------------------------------
# 3.2 Zone (keep direct sensor mapping)
# -------------------------------------------------------
class Zone(SQLModel, table=True):
    __tablename__ = "zone"
    __table_args__ = (
        UniqueConstraint("greenhouse_id", "zone_number", name="uq_zone_greenhouse_zone_number"),
        CheckConstraint("location IN ('N','NE','E','SE','S','SW','W','NW')", name="ck_zone_location"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(sa_column=Column(ForeignKey("greenhouse.id", ondelete="CASCADE"), nullable=False))
    zone_number: int
    location: str
    context_text: Optional[str] = None

    # Keep the current 1:many mapping via foreign keys on Zone
    temperature_sensor_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column(ForeignKey("sensor.id"), nullable=True))
    humidity_sensor_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column(ForeignKey("sensor.id"), nullable=True))
    co2_sensor_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column(ForeignKey("sensor.id"), nullable=True))
    light_sensor_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column(ForeignKey("sensor.id"), nullable=True))
    soil_moisture_sensor_id: Optional[uuid.UUID] = Field(default=None, sa_column=Column(ForeignKey("sensor.id"), nullable=True))
    
    greenhouse: "Greenhouse" = Relationship(
        back_populates="zones",
        sa_relationship_kwargs={"passive_deletes": True}
    )
    crops: List["Crop"] = Relationship(
        back_populates="zone",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )

    @property
    def current_crop(self) -> Optional["Crop"]:
        # Returns the active crop for this zone, if any
        for c in self.crops:
            if c.is_active:
                return c
        return None

# -----------------------
# Zone DTOs
# -----------------------
class ZoneBase(SQLModel):
    zone_number: int
    location: LocationEnum  # was: str
    context_text: Optional[str] = None

class ZoneCreate(ZoneBase):
    greenhouse_id: uuid.UUID

class ZoneUpdate(SQLModel):
    zone_number: Optional[int] = None
    location: Optional[LocationEnum] = None  # was: Optional[str]
    context_text: Optional[str] = None
    temperature_sensor_id: Optional[uuid.UUID] = None
    humidity_sensor_id: Optional[uuid.UUID] = None
    co2_sensor_id: Optional[uuid.UUID] = None
    light_sensor_id: Optional[uuid.UUID] = None
    soil_moisture_sensor_id: Optional[uuid.UUID] = None

class ZoneSensorMap(SQLModel):
    sensor_id: uuid.UUID
    type: SensorType

class ZonePublic(ZoneBase):
    id: uuid.UUID
    greenhouse_id: uuid.UUID

# -------------------------------------------------------
# 3.3 Controller (with DDL fields and partial unique idx)
# -------------------------------------------------------
class Controller(SQLModel, table=True):
    __tablename__ = "controller"
    __table_args__ = (
        Index("ux_one_climate_controller", "greenhouse_id", unique=True, postgresql_where=text("is_climate_controller")),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(sa_column=Column(ForeignKey("greenhouse.id", ondelete="CASCADE"), nullable=False))
    name: str
    model: Optional[str] = None
    device_name: Optional[str] = Field(default=None, sa_column=Column("device_name", unique=True, nullable=True))
    firmware: Optional[str] = None
    hardware_profile: Optional[str] = None
    is_climate_controller: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)


    greenhouse: Optional[Greenhouse] = Relationship(
        back_populates="controllers",
        sa_relationship_kwargs={"passive_deletes": True},
    )

    sensors: List["Sensor"] = Relationship(
        back_populates="controller",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True}
    )

    actuators: List["Actuator"] = Relationship(
        back_populates="controller",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )

# -----------------------
# Controller DTOs
# -----------------------
class ControllerBase(SQLModel):
    name: str
    model: Optional[str] = None

class ControllerCreate(ControllerBase):
    greenhouse_id: uuid.UUID
    device_name: Optional[str] = None
    firmware: Optional[str] = None
    hardware_profile: Optional[str] = None
    is_climate_controller: bool = False

class ControllerUpdate(SQLModel):
    name: Optional[str] = None
    model: Optional[str] = None
    device_name: Optional[str] = None
    firmware: Optional[str] = None
    hardware_profile: Optional[str] = None
    is_climate_controller: Optional[bool] = None

class ControllerPublic(ControllerBase):
    id: uuid.UUID
    greenhouse_id: uuid.UUID
    device_name: Optional[str] = None
    firmware: Optional[str] = None
    hardware_profile: Optional[str] = None
    is_climate_controller: bool
    created_at: datetime

# -------------------------------------------------------
# 3.4 Sensor (DDL fields; no M2M mapping)
# -------------------------------------------------------
class Sensor(SQLModel, table=True):
    __tablename__ = "sensor"
    __table_args__ = (
        CheckConstraint("scope IN ('zone','greenhouse','external')", name="ck_sensor_scope"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(sa_column=Column(ForeignKey("controller.id", ondelete="CASCADE"), nullable=False))
    name: str
    type: str  # temperature | humidity | soil_moisture | co2 | light (via sensor_kind_meta)
    scope: str = Field(default="zone")
    include_in_climate_loop: bool = Field(default=False, nullable=False)

    # hardware/config
    model: Optional[str] = None
    poll_interval_s: Optional[int] = Field(default=10)
    modbus_slave_id: Optional[int] = None
    modbus_reg: Optional[int] = None
    scale_factor: Optional[float] = Field(default=1.0)
    offset: Optional[float] = Field(default=0.0)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)

    controller: "Controller" = Relationship(
        back_populates="sensors",
        sa_relationship_kwargs={"passive_deletes": True}
    )
# -----------------------
# Sensor DTOs
# -----------------------
class SensorBase(SQLModel):
    name: str
    type: str  # was: kind
    scope: str = "zone"
    include_in_climate_loop: bool = False
    model: Optional[str] = None
    poll_interval_s: Optional[int] = 10
    modbus_slave_id: Optional[int] = None
    modbus_reg: Optional[int] = None
    scale_factor: Optional[float] = 1.0
    offset: Optional[float] = 0.0

class SensorCreate(SensorBase):
    controller_id: uuid.UUID

class SensorUpdate(SQLModel):
    name: Optional[str] = None
    type: Optional[str] = None  # was: kind
    scope: Optional[str] = None
    include_in_climate_loop: Optional[bool] = None
    model: Optional[str] = None
    poll_interval_s: Optional[int] = None
    modbus_slave_id: Optional[int] = None
    modbus_reg: Optional[int] = None
    scale_factor: Optional[float] = None
    offset: Optional[float] = None
    controller_id: Optional[uuid.UUID] = None

class SensorPublic(SensorBase):
    id: uuid.UUID
    controller_id: uuid.UUID
    created_at: datetime

# -------------------------------------------------------
# 3.2 Crop Template, Crop Instance, Crop Observation (renamed)
# -------------------------------------------------------
class CropTemplate(SQLModel, table=True):
    __tablename__ = "crop_template"  # renamed from 'crop'
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    description: Optional[str] = None
    expected_yield_per_sqm: Optional[float] = None
    growing_days: Optional[int] = None
    recipe: Optional[dict] = Field(default=None, sa_type=JSON)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)


class Crop(SQLModel, table=True):
    __tablename__ = "crop"  # renamed from 'zone_crop'
    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_crop_dates"),
        Index("ux_zone_crop_one_active", "zone_id", unique=True, postgresql_where=text("is_active")),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    zone_id: uuid.UUID = Field(sa_column=Column(ForeignKey("zone.id", ondelete="CASCADE"), nullable=False))
    crop_template_id: uuid.UUID = Field(sa_column=Column(ForeignKey("crop_template.id", ondelete="CASCADE"), nullable=False))
    start_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
    end_date: Optional[datetime] = None
    is_active: bool = Field(default=True, nullable=False)
    final_yield: Optional[float] = None
    area_sqm: Optional[float] = None

    crop_template: "CropTemplate" = Relationship()

    zone: "Zone" = Relationship(
        back_populates="crops",
        sa_relationship_kwargs={"passive_deletes": True}
    )

    observations: List["CropObservation"] = Relationship(
        back_populates="crop",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )
    

class CropObservation(SQLModel, table=True):
    __tablename__ = "crop_observation"  # renamed from 'zone_crop_observation'
    __table_args__ = (
        CheckConstraint("health_score IS NULL OR (health_score BETWEEN 1 AND 10)", name="ck_crop_obs_health"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    crop_id: uuid.UUID = Field(sa_column=Column(ForeignKey("crop.id", ondelete="CASCADE"), nullable=False))
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)
    notes: Optional[str] = None
    image_url: Optional[str] = None
    height_cm: Optional[float] = None
    health_score: Optional[int] = None

    crop: "Crop" = Relationship(
        back_populates="observations", 
        sa_relationship_kwargs={"passive_deletes": True}
    )
# --------------------------------------
# Crop Template, Crop, Observation DTOs
# --------------------------------------
class CropTemplateBase(SQLModel):
    name: str
    description: Optional[str] = None
    expected_yield_per_sqm: Optional[float] = None
    growing_days: Optional[int] = None
    recipe: Optional[dict] = None


class CropTemplateCreate(CropTemplateBase):
    pass


class CropTemplateUpdate(SQLModel):
    name: Optional[str] = None
    description: Optional[str] = None
    expected_yield_per_sqm: Optional[float] = None
    growing_days: Optional[int] = None
    recipe: Optional[dict] = None


class CropTemplatePublic(CropTemplateBase):
    id: uuid.UUID
    created_at: datetime


class CropBase(SQLModel):
    start_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_date: Optional[datetime] = None
    is_active: bool = True
    final_yield: Optional[float] = None
    area_sqm: Optional[float] = None

class CropCreate(CropBase):
    zone_id: uuid.UUID
    crop_template_id: uuid.UUID

class CropUpdate(SQLModel):
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None
    final_yield: Optional[float] = None
    area_sqm: Optional[float] = None

class CropPublic(CropBase):
    id: uuid.UUID
    zone_id: uuid.UUID
    crop_template_id: uuid.UUID

class CropObservationBase(SQLModel):
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None
    image_url: Optional[str] = None
    height_cm: Optional[float] = None
    health_score: Optional[int] = None

class CropObservationCreate(CropObservationBase):
    crop_id: uuid.UUID

class CropObservationUpdate(SQLModel):
    notes: Optional[str] = None
    image_url: Optional[str] = None
    height_cm: Optional[float] = None
    health_score: Optional[int] = None

class CropObservationPublic(CropObservationBase):
    id: uuid.UUID
    crop_id: uuid.UUID

# -------------------------------------------------------
# 3.3 Device tokens, Claim tickets, Controller buttons
# -------------------------------------------------------
class DeviceToken(SQLModel, table=True):
    __tablename__ = "device_token"
    __table_args__ = (
        # One active token per controller (unique on controller_id + revoked_at)
        UniqueConstraint("controller_id", "revoked_at", name="ux_one_active_token", deferrable=True, initially="IMMEDIATE"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("controller.id", ondelete="CASCADE"), nullable=False)
    )
    token_hash: str
    last4: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    revoked_at: Optional[datetime] = None

# -----------------------
# Device Token DTOs
# -----------------------
class DeviceTokenCreate(SQLModel):
    controller_id: uuid.UUID
    token_hash: str
    last4: Optional[str] = None

class DeviceTokenPublic(SQLModel):
    id: uuid.UUID
    controller_id: uuid.UUID
    last4: Optional[str] = None
    created_at: datetime
    revoked_at: Optional[datetime] = None

class ClaimTicket(SQLModel, table=True):
    __tablename__ = "claim_ticket"
    device_name: str = Field(primary_key=True)
    claim_code_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

# -----------------------
# Claim Ticket DTOs
# -----------------------
class ClaimTicketCreate(SQLModel):
    device_name: str
    claim_code_hash: str
    expires_at: Optional[datetime] = None


class ClaimTicketPublic(SQLModel):
    device_name: str
    created_at: datetime
    expires_at: Optional[datetime] = None


class ControllerButton(SQLModel, table=True):
    __tablename__ = "controller_button"
    __table_args__ = (
        UniqueConstraint("controller_id", "analog_channel", name="uq_controller_button_channel"),
        CheckConstraint("button_type IN ('cool','humid','heat')", name="ck_button_type"),
        CheckConstraint("temp_stage IS NULL OR temp_stage BETWEEN -3 AND 3", name="ck_temp_stage"),
        CheckConstraint("humi_stage IS NULL OR humi_stage BETWEEN -3 AND 3", name="ck_humi_stage"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("controller.id", ondelete="CASCADE"), nullable=False)
    )
    button_type: str  # 'cool' | 'humid' | 'heat'
    analog_channel: int
    temp_stage: Optional[int] = None
    humi_stage: Optional[int] = None
    timeout_s: int = Field(default=600)

# -----------------------
# Controller Button DTOs
# -----------------------
class ControllerButtonBase(SQLModel):
    button_type: str
    analog_channel: int
    temp_stage: Optional[int] = None
    humi_stage: Optional[int] = None
    timeout_s: int = 600

class ControllerButtonCreate(ControllerButtonBase):
    controller_id: uuid.UUID

class ControllerButtonUpdate(SQLModel):
    button_type: Optional[str] = None
    analog_channel: Optional[int] = None
    temp_stage: Optional[int] = None
    humi_stage: Optional[int] = None
    timeout_s: Optional[int] = None

class ControllerButtonPublic(ControllerButtonBase):
    id: uuid.UUID
    controller_id: uuid.UUID

# -------------------------------------------------------
# 3.5 Actuators, Fan groups
# -------------------------------------------------------
class Actuator(SQLModel, table=True):
    __tablename__ = "actuator"
    __table_args__ = (
        CheckConstraint("fail_safe_state IN ('on','off')", name="ck_actuator_fail_safe_state"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("controller.id", ondelete="CASCADE"), nullable=False)
    )
    name: str
    kind: str  # references actuator_kind_meta(kind)
    relay_channel: Optional[int] = None
    min_on_ms: int = Field(default=60000)
    min_off_ms: int = Field(default=60000)
    fail_safe_state: str = Field(default=FailSafeState.OFF)  # 'on' | 'off'
    zone_id: Optional[uuid.UUID] = Field(
        sa_column=Column(ForeignKey("zone.id", ondelete="SET NULL"), nullable=True)
    )
    status: Optional[bool] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    controller: "Controller" = Relationship(
        back_populates="actuators",
        sa_relationship_kwargs={"passive_deletes": True}
    )
# -----------------------
# Actuator DTOs
# -----------------------
class ActuatorBase(SQLModel):
    name: str
    kind: str
    relay_channel: Optional[int] = None
    min_on_ms: int = 60000
    min_off_ms: int = 60000
    fail_safe_state: str = "off"
    zone_id: Optional[uuid.UUID] = None
    status: Optional[bool] = None

class ActuatorCreate(ActuatorBase):
    controller_id: uuid.UUID

class ActuatorUpdate(SQLModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    relay_channel: Optional[int] = None
    min_on_ms: Optional[int] = None
    min_off_ms: Optional[int] = None
    fail_safe_state: Optional[str] = None
    zone_id: Optional[uuid.UUID] = None
    status: Optional[bool] = None
    controller_id: Optional[uuid.UUID] = None

class ActuatorPublic(ActuatorBase):
    id: uuid.UUID
    controller_id: uuid.UUID
    created_at: datetime

class FanGroup(SQLModel, table=True):
    __tablename__ = "fan_group"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("controller.id", ondelete="CASCADE"), nullable=False)
    )
    name: str

class FanGroupMember(SQLModel, table=True):
    __tablename__ = "fan_group_member"
    fan_group_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("fan_group.id", ondelete="CASCADE"), primary_key=True)
    )
    actuator_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("actuator.id", ondelete="CASCADE"), primary_key=True)
    )

# -----------------------
# Fan Group DTOs
# -----------------------
class FanGroupBase(SQLModel):
    name: str

class FanGroupCreate(FanGroupBase):
    controller_id: uuid.UUID

class FanGroupPublic(FanGroupBase):
    id: uuid.UUID
    controller_id: uuid.UUID

class FanGroupMemberCreate(SQLModel):
    fan_group_id: uuid.UUID
    actuator_id: uuid.UUID

class FanGroupMemberPublic(SQLModel):
    fan_group_id: uuid.UUID
    actuator_id: uuid.UUID

# -------------------------------------------------------
# 3.6 State Machine
# -------------------------------------------------------
class StateMachineRow(SQLModel, table=True):
    __tablename__ = "state_machine_row"
    __table_args__ = (
        CheckConstraint("temp_stage BETWEEN -3 AND 3", name="ck_state_temp_stage"),
        CheckConstraint("humi_stage BETWEEN -3 AND 3", name="ck_state_humi_stage"),
        UniqueConstraint("greenhouse_id", "temp_stage", "humi_stage", name="uq_state_machine_row"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("greenhouse.id", ondelete="CASCADE"), nullable=False)
    )
    temp_stage: int
    humi_stage: int
    must_on_actuators: List[uuid.UUID] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(PGUUID(as_uuid=True)), nullable=False, server_default=text("ARRAY[]::uuid[]")),
    )
    must_off_actuators: List[uuid.UUID] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(PGUUID(as_uuid=True)), nullable=False, server_default=text("ARRAY[]::uuid[]")),
    )
    default_fan_on_count: Optional[int] = None

class StateMachineFanRule(SQLModel, table=True):
    __tablename__ = "state_machine_fan_rule"
    __table_args__ = (
        CheckConstraint("on_count >= 0", name="ck_fan_rule_on_count_nonneg"),
    )
    state_row_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("state_machine_row.id", ondelete="CASCADE"), primary_key=True)
    )
    fan_group_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("fan_group.id", ondelete="CASCADE"), primary_key=True)
    )
    on_count: int

# -----------------------
# State Machine DTOs
# -----------------------
class StateMachineRowBase(SQLModel):
    temp_stage: int
    humi_stage: int
    must_on_actuators: List[uuid.UUID] = Field(default_factory=list)
    must_off_actuators: List[uuid.UUID] = Field(default_factory=list)
    default_fan_on_count: Optional[int] = None

class StateMachineRowCreate(StateMachineRowBase):
    greenhouse_id: uuid.UUID

class StateMachineRowUpdate(SQLModel):
    temp_stage: Optional[int] = None
    humi_stage: Optional[int] = None
    must_on_actuators: Optional[List[uuid.UUID]] = None
    must_off_actuators: Optional[List[uuid.UUID]] = None
    default_fan_on_count: Optional[int] = None

class StateMachineRowPublic(StateMachineRowBase):
    id: uuid.UUID
    greenhouse_id: uuid.UUID

class StateMachineFanRuleCreate(SQLModel):
    state_row_id: uuid.UUID
    fan_group_id: uuid.UUID
    on_count: int

class StateMachineFanRulePublic(SQLModel):
    state_row_id: uuid.UUID
    fan_group_id: uuid.UUID
    on_count: int

# -------------------------------------------------------
# 3.7 Plans (setpoints & schedules)
# -------------------------------------------------------
class Plan(SQLModel, table=True):
    __tablename__ = "plan"
    __table_args__ = (
        UniqueConstraint("greenhouse_id", "version", name="uq_plan_version"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("greenhouse.id", ondelete="CASCADE"), nullable=False)
    )
    version: int
    effective_from: datetime
    effective_to: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships within this module only
    setpoints: List["PlanSetpoint"] = Relationship(
        back_populates="plan",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )

    irrigations: List["PlanIrrigation"] = Relationship(
        back_populates="plan",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )

    fertilizations: List["PlanFertilization"] = Relationship(
        back_populates="plan",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )

    lightings: List["PlanLighting"] = Relationship(
        back_populates="plan",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )

# -----------------------
# Plan DTOs
# -----------------------
class PlanBase(SQLModel):
    version: int
    effective_from: datetime
    effective_to: datetime

class PlanCreate(PlanBase):
    greenhouse_id: uuid.UUID

class PlanUpdate(SQLModel):
    version: Optional[int] = None
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    greenhouse_id: Optional[uuid.UUID] = None

class PlanPublic(PlanBase):
    id: uuid.UUID
    greenhouse_id: uuid.UUID
    created_at: datetime

class PlanSetpoint(SQLModel, table=True):
    __tablename__ = "plan_setpoint"
    __table_args__ = (
        UniqueConstraint("plan_id", "ts", name="uq_plan_setpoint_ts"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    plan_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("plan.id", ondelete="CASCADE"), nullable=False)
    )
    ts: datetime
    min_temp_c: Optional[float] = None
    max_temp_c: Optional[float] = None
    min_vpd_kpa: Optional[float] = None
    max_vpd_kpa: Optional[float] = None
    temp_delta_c: Optional[float] = None
    humi_delta_pct: Optional[float] = None
    vpd_delta_kpa: Optional[float] = None
    temp_hysteresis_c: Optional[float] = None
    humi_hysteresis_pct: Optional[float] = None
    vpd_hysteresis_kpa: Optional[float] = None
    stage_offset_temp: Optional[int] = None
    stage_offset_humi: Optional[int] = None
    plan: "Plan" = Relationship(back_populates="setpoints")

class PlanSetpointBase(SQLModel):
    ts: datetime
    min_temp_c: Optional[float] = None
    max_temp_c: Optional[float] = None
    min_vpd_kpa: Optional[float] = None
    max_vpd_kpa: Optional[float] = None
    temp_delta_c: Optional[float] = None
    humi_delta_pct: Optional[float] = None
    vpd_delta_kpa: Optional[float] = None
    temp_hysteresis_c: Optional[float] = None
    humi_hysteresis_pct: Optional[float] = None
    vpd_hysteresis_kpa: Optional[float] = None
    stage_offset_temp: Optional[int] = None
    stage_offset_humi: Optional[int] = None

class PlanSetpointCreate(PlanSetpointBase):
    plan_id: uuid.UUID

class PlanSetpointUpdate(SQLModel):
    ts: Optional[datetime] = None
    min_temp_c: Optional[float] = None
    max_temp_c: Optional[float] = None
    min_vpd_kpa: Optional[float] = None
    max_vpd_kpa: Optional[float] = None
    temp_delta_c: Optional[float] = None
    humi_delta_pct: Optional[float] = None
    vpd_delta_kpa: Optional[float] = None
    temp_hysteresis_c: Optional[float] = None
    humi_hysteresis_pct: Optional[float] = None
    vpd_hysteresis_kpa: Optional[float] = None
    stage_offset_temp: Optional[int] = None
    stage_offset_humi: Optional[int] = None
    plan_id: Optional[uuid.UUID] = None

class PlanSetpointPublic(PlanSetpointBase):
    id: uuid.UUID
    plan_id: uuid.UUID

class PlanIrrigation(SQLModel, table=True):
    __tablename__ = "plan_irrigation"
    __table_args__ = (
        UniqueConstraint("plan_id", "zone_id", "ts", name="uq_plan_irrigation_ts"),
        CheckConstraint("duration_s > 0", name="ck_irrigation_duration_positive"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    plan_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("plan.id", ondelete="CASCADE"), nullable=False)
    )
    zone_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("zone.id", ondelete="CASCADE"), nullable=False)
    )
    ts: datetime
    duration_s: int
    fertilizer: bool = Field(default=False)
    min_soil_vwc: Optional[float] = None
    plan: "Plan" = Relationship(back_populates="irrigations")

class PlanIrrigationBase(SQLModel):
    ts: datetime
    duration_s: int
    fertilizer: bool = False
    min_soil_vwc: Optional[float] = None

class PlanIrrigationCreate(PlanIrrigationBase):
    plan_id: uuid.UUID
    zone_id: uuid.UUID

class PlanIrrigationUpdate(SQLModel):
    ts: Optional[datetime] = None
    duration_s: Optional[int] = None
    fertilizer: Optional[bool] = None
    min_soil_vwc: Optional[float] = None
    plan_id: Optional[uuid.UUID] = None
    zone_id: Optional[uuid.UUID] = None

class PlanIrrigationPublic(PlanIrrigationBase):
    id: uuid.UUID
    plan_id: uuid.UUID
    zone_id: uuid.UUID

class PlanFertilization(SQLModel, table=True):
    __tablename__ = "plan_fertilization"
    __table_args__ = (
        UniqueConstraint("plan_id", "zone_id", "ts", name="uq_plan_fertilization_ts"),
        CheckConstraint("duration_s > 0", name="ck_fertilization_duration_positive"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    plan_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("plan.id", ondelete="CASCADE"), nullable=False)
    )
    zone_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("zone.id", ondelete="CASCADE"), nullable=False)
    )
    ts: datetime
    duration_s: int
    plan: "Plan" = Relationship(back_populates="fertilizations")

class PlanFertilizationBase(SQLModel):
    ts: datetime
    duration_s: int

class PlanFertilizationCreate(PlanFertilizationBase):
    plan_id: uuid.UUID
    zone_id: uuid.UUID

class PlanFertilizationUpdate(SQLModel):
    ts: Optional[datetime] = None
    duration_s: Optional[int] = None
    plan_id: Optional[uuid.UUID] = None
    zone_id: Optional[uuid.UUID] = None

class PlanFertilizationPublic(PlanFertilizationBase):
    id: uuid.UUID
    plan_id: uuid.UUID
    zone_id: uuid.UUID

class PlanLighting(SQLModel, table=True):
    __tablename__ = "plan_lighting"
    __table_args__ = (
        UniqueConstraint("plan_id", "actuator_id", "ts", name="uq_plan_lighting_ts"),
        CheckConstraint("duration_s > 0", name="ck_lighting_duration_positive"),
    )
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    plan_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("plan.id", ondelete="CASCADE"), nullable=False)
    )
    actuator_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("actuator.id", ondelete="CASCADE"), nullable=False)
    )
    ts: datetime
    duration_s: int
    plan: "Plan" = Relationship(back_populates="lightings")

class PlanLightingBase(SQLModel):
    ts: datetime
    duration_s: int

class PlanLightingCreate(PlanLightingBase):
    plan_id: uuid.UUID
    actuator_id: uuid.UUID

class PlanLightingUpdate(SQLModel):
    ts: Optional[datetime] = None
    duration_s: Optional[int] = None
    plan_id: Optional[uuid.UUID] = None
    actuator_id: Optional[uuid.UUID] = None

class PlanLightingPublic(PlanLightingBase):
    id: uuid.UUID
    plan_id: uuid.UUID
    actuator_id: uuid.UUID

#-------------------------------------------------------
#MISC MODELS
#-------------------------------------------------------
# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=40)