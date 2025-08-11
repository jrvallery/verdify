import uuid
from datetime import datetime, timezone

from pydantic import EmailStr
from sqlmodel import Field, Relationship, SQLModel, JSON
from typing import Optional, Dict, Any, List
from enum import Enum
from fastapi import UploadFile, File
from sqlalchemy import Column, ForeignKey

class LocationEnum(str, Enum):
    N  = "N"
    NE = "NE"
    E  = "E"
    SE = "SE"
    S  = "S"
    SW = "SW"
    W  = "W"
    NW = "NW"

class SensorType(str, Enum):
    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    CO2 = "co2"
    LIGHT = "light"
    SOIL_MOISTURE = "soil_moisture"

#-------------------------------------------------------
#USER MODELS
#-------------------------------------------------------
# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=40)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=40)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=40)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=40)
    new_password: str = Field(min_length=8, max_length=40)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    greenhouses: list["Greenhouse"] = Relationship(back_populates="owner", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


#-------------------------------------------------------
#GREENHOUSE MODELS
#-------------------------------------------------------
class GreenhouseBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = Field(default=True, description="Whether this greenhouse is active")

    outside_temperature: float = Field(default=0.0, description="Current external temperature")
    outside_humidity: float = Field(default=0.0, description="Current external humidity")

    latitude: Optional[float] = Field(default=None, description="Latitude of greenhouse location")
    longitude: Optional[float] = Field(default=None, description="Longitude of greenhouse location")


class Greenhouse(GreenhouseBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    owner: "User" = Relationship(back_populates="greenhouses")
    zones: List["Zone"] = Relationship(
        back_populates="greenhouse",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )
    controllers: List["Controller"] = Relationship(
        back_populates="greenhouse",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )


class GreenhouseCreate(GreenhouseBase):
    pass


class GreenhouseUpdate(SQLModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    outside_temperature: Optional[float] = None
    outside_humidity: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class GreenhousePublic(GreenhouseBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    is_active: bool


class GreenhousesPublic(SQLModel):
    data: list[GreenhousePublic]
    count: int
#-------------------------------------------------------
#ZONE MODELS
#-------------------------------------------------------
class ZoneBase(SQLModel):
    zone_number: int = Field(..., description="Numeric identifier within greenhouse")
    location: LocationEnum = Field(..., description="N, E, S, W, NE, SE, SW, NW")
    temperature: Optional[float] = None
    humidity: Optional[float] = None

class Zone(ZoneBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(
        sa_column=Column("greenhouse_id", ForeignKey("greenhouse.id", ondelete="CASCADE"), nullable=False)
    )
    greenhouse: Optional["Greenhouse"] = Relationship(
        back_populates="zones",
        sa_relationship_kwargs={"passive_deletes": True},
    )

    temperature_sensor_id: Optional[uuid.UUID] = Field(foreign_key="sensor.id", nullable=True)
    humidity_sensor_id: Optional[uuid.UUID] = Field(foreign_key="sensor.id", nullable=True)
    co2_sensor_id: Optional[uuid.UUID] = Field(foreign_key="sensor.id", nullable=True)
    light_sensor_id: Optional[uuid.UUID] = Field(foreign_key="sensor.id", nullable=True)
    soil_moisture_sensor_id: Optional[uuid.UUID] = Field(foreign_key="sensor.id", nullable=True)

    # Historical zone crops (all instances)
    zone_crops: List["ZoneCrop"] = Relationship(
        back_populates="zone",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )

    # Helper property to get current active crop
    @property
    def current_crop(self) -> Optional["ZoneCrop"]:
        """Get the currently active crop for this zone"""
        for zone_crop in self.zone_crops:
            if zone_crop.is_active:
                return zone_crop
        return None

class ZoneCreate(ZoneBase):
    greenhouse_id: uuid.UUID

class ZonePublic(ZoneBase):
    id: uuid.UUID
    greenhouse_id: uuid.UUID

class ZoneUpdate(SQLModel):
    zone_number: Optional[int] = None
    location: Optional[LocationEnum] = None

class ZoneRead(ZoneBase):
    id: uuid.UUID
    sensors: list["Sensor"] = []

class ZoneReading(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    zone_id: uuid.UUID = Field(foreign_key="zone.id")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    temperature: float
    humidity: float

# New model for sensor mapping
class ZoneSensorMap(SQLModel):
    sensor_id: uuid.UUID
    type: SensorType


#-------------------------------------------------------
#CROP MODELS (Global crop templates)
#-------------------------------------------------------
class CropBase(SQLModel):
    name: str = Field(..., max_length=255, description="Name of the crop (e.g., 'Tomato')")
    description: Optional[str] = Field(default=None, max_length=500)
    expected_yield_per_sqm: Optional[float] = Field(default=None, description="Expected yield per square meter")
    growing_days: Optional[int] = Field(default=None, description="Expected days from seed to harvest")

class Crop(CropBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    recipe: Optional[dict[str, Any]] = Field(default=None, sa_type=JSON, description="JSON recipe for the crop")
    
    # No direct relationship to zones - crops are global templates

class CropCreate(CropBase):
    recipe: Optional[dict[str, Any]] = None

class CropPublic(CropBase):
    id: uuid.UUID
    recipe: Optional[dict[str, Any]] = None

class CropUpdate(SQLModel):
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None, max_length=500)
    recipe: Optional[dict[str, Any]] = None
    expected_yield_per_sqm: Optional[float] = None
    growing_days: Optional[int] = None

#-------------------------------------------------------
#ZONE CROP MODELS (Zone-specific crop instance)
#-------------------------------------------------------
class ZoneCropBase(SQLModel):
    start_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_date: Optional[datetime] = Field(default=None)
    is_active: bool = Field(default=True)
    final_yield: Optional[float] = Field(default=None, description="Total yield produced")
    area_sqm: Optional[float] = Field(default=None, description="Area used in square meters")

class ZoneCrop(ZoneCropBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    crop_id: uuid.UUID = Field(foreign_key="crop.id", nullable=False, ondelete="CASCADE")
    zone_id: uuid.UUID = Field(
        sa_column=Column("zone_id", ForeignKey("zone.id", ondelete="CASCADE"), nullable=False)
    )
    zone: "Zone" = Relationship(back_populates="zone_crops", sa_relationship_kwargs={"passive_deletes": True})
    
    crop: "Crop" = Relationship()  # Reference to global crop template
    observations: List["ZoneCropObservation"] = Relationship(
        back_populates="zone_crop",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True},
    )

class ZoneCropCreate(ZoneCropBase):
    crop_id: uuid.UUID
    zone_id: uuid.UUID

class ZoneCropPublic(ZoneCropBase):
    id: uuid.UUID
    crop_id: uuid.UUID
    zone_id: uuid.UUID

class ZoneCropUpdate(SQLModel):
    crop_id: Optional[uuid.UUID] = None  # Allow changing the crop template
    end_date: Optional[datetime] = None
    is_active: Optional[bool] = None
    final_yield: Optional[float] = None
    area_sqm: Optional[float] = None

#-------------------------------------------------------
#ZONE CROP OBSERVATION MODELS
#-------------------------------------------------------
class ZoneCropObservationBase(SQLModel):
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When observation was made")
    notes: Optional[str] = Field(default=None, max_length=2000)
    image_url: Optional[str] = Field(default=None, max_length=500, description="URL to uploaded image")
    height_cm: Optional[float] = Field(default=None, description="Plant height in cm")
    health_score: Optional[int] = Field(default=None, ge=1, le=10, description="Health score 1-10")

class ZoneCropObservation(ZoneCropObservationBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    zone_crop_id: uuid.UUID = Field(
        sa_column=Column("zone_crop_id", ForeignKey("zonecrop.id", ondelete="CASCADE"), nullable=False)
    )
    zone_crop: "ZoneCrop" = Relationship(back_populates="observations", sa_relationship_kwargs={"passive_deletes": True})

class ZoneCropObservationCreate(ZoneCropObservationBase):
    zone_crop_id: uuid.UUID

class ZoneCropObservationPublic(ZoneCropObservationBase):
    id: uuid.UUID
    zone_crop_id: uuid.UUID

class ZoneCropObservationUpdate(SQLModel):
    notes: Optional[str] = Field(default=None, max_length=2000)
    image_url: Optional[str] = Field(default=None, max_length=500)
    height_cm: Optional[float] = None
    health_score: Optional[int] = Field(default=None, ge=1, le=10)

#-------------------------------------------------------
#Controller MODELS
#-------------------------------------------------------
class ControllerBase(SQLModel):
    name: str = Field(..., description="Controller name, e.g. 'fan', 'heater'")
    model: Optional[str] = None
    # you can add other fields later (serial number, specs, etc.)

class Controller(ControllerBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(
        sa_column=Column(
            "greenhouse_id",
            ForeignKey("greenhouse.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    greenhouse: Optional[Greenhouse] = Relationship(
        back_populates="controllers",
        sa_relationship_kwargs={"passive_deletes": True},
    )

    sensors: List["Sensor"] = Relationship(
        back_populates="controller",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True}
    )
    # relays: List["Relay"] = Relationship(
    #     back_populates="controller",
    #     sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True}
    # )

    # Add missing equipment relationship to match Equipment.controller back_populates="equipment"
    equipment: List["Equipment"] = Relationship(
        back_populates="controller",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "passive_deletes": True}
    )

class ControllerCreate(ControllerBase):
    greenhouse_id: uuid.UUID

class ControllerPublic(ControllerBase):
    id: uuid.UUID
    greenhouse_id: uuid.UUID

class ControllerUpdate(SQLModel):
    name: Optional[str] = None
    model: Optional[str] = None

#-------------------------------------------------------
#SENSOR MODELS
#-------------------------------------------------------
class SensorBase(SQLModel):
    name: str = Field(..., description="Sensor name/identifier")
    type: SensorType = Field(..., description="Type of sensor")
    model: Optional[str] = Field(default=None, description="Model/manufacturer information")
    value: Optional[float] = Field(default=None, description="Current sensor value")
    unit: Optional[str] = Field(default=None, description="Unit of measurement")


class Sensor(SensorBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(
        sa_column=Column(
            "controller_id",
            ForeignKey("controller.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    controller: "Controller" = Relationship(back_populates="sensors", sa_relationship_kwargs={"passive_deletes": True})

class SensorCreate(SensorBase):
    controller_id: uuid.UUID

class SensorPublic(SensorBase):
    id: uuid.UUID
    controller_id: uuid.UUID

class SensorUpdate(SQLModel):
    name: Optional[str] = None
    type: Optional[str] = None
    model: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    controller_id: Optional[uuid.UUID] = None

#-------------------------------------------------------
#Equipment MODELS
#-------------------------------------------------------
class EquipmentBase(SQLModel):
    name: str = Field(..., description="Equipment name, e.g. 'fan', 'heater'")
    model: Optional[str] = None
    status: bool = Field(..., description="Current status of the equipment (e.g. 'on', 'off')")

class Equipment(EquipmentBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    controller_id: uuid.UUID = Field(foreign_key="controller.id", nullable=False, ondelete="CASCADE")
    controller: "Controller" = Relationship(back_populates="equipment")

class EquipmentCreate(EquipmentBase):
    controller_id: uuid.UUID

class EquipmentPublic(EquipmentBase):
    id: uuid.UUID
    controller_id: uuid.UUID

class EquipmentUpdate(SQLModel):
    name: Optional[str] = None
    model: Optional[str] = None
    status: bool = None

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

