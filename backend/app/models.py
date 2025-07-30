import uuid
from datetime import datetime

from pydantic import EmailStr
from sqlmodel import Field, Relationship, SQLModel
from typing import Optional
from enum import Enum

class LocationEnum(str, Enum):
    N  = "N"
    NE = "NE"
    E  = "E"
    SE = "SE"
    S  = "S"
    SW = "SW"
    W  = "W"
    NW = "NW"
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
    temperature: float = Field(default=0.0, description="Current internal temperature")
    humidity: float = Field(default=0.0, description="Current internal humidity")
    outside_temperature: float = Field(default=0.0, description="Current external temperature")
    outside_humidity: float = Field(default=0.0, description="Current external humidity")
    type: Optional[str] = Field(default="standard", description="Greenhouse style/type")
    latitude: Optional[float] = Field(default=None, description="Latitude of greenhouse location")
    longitude: Optional[float] = Field(default=None, description="Longitude of greenhouse location")


class Greenhouse(GreenhouseBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    owner: "User" = Relationship(back_populates="greenhouses")
    zones: list["Zone"] = Relationship(back_populates="greenhouse", cascade_delete=True)
    controllers: list["Controller"] = Relationship(back_populates="greenhouse", cascade_delete=True)
    #climate_history: list["GreenhouseClimateHistory"] = Relationship(back_populates="greenhouse", cascade_delete=True)


class GreenhouseCreate(GreenhouseBase):
    pass


class GreenhouseUpdate(SQLModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    outside_temperature: Optional[float] = None
    outside_humidity: Optional[float] = None
    type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class GreenhousePublic(GreenhouseBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    is_active: bool


class GreenhousesPublic(SQLModel):
    data: list[GreenhousePublic]
    count: int


class GreenhouseClimateUpdate(SQLModel):
    temperature: float
    humidity: float
    outside_temperature: Optional[float] = None
    outside_humidity: Optional[float] = None


class GreenhouseClimateRead(SQLModel):
    temperature: float
    humidity: float
    outside_temperature: float
    outside_humidity: float
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
    greenhouse_id: uuid.UUID = Field(foreign_key="greenhouse.id", nullable=False, ondelete="CASCADE")
    greenhouse: "Greenhouse" = Relationship(back_populates="zones")
    sensors: list["Sensor"] = Relationship(back_populates="zone", cascade_delete=True)
    #climate_history: list["ZoneClimateHistory"] = Relationship(back_populates="zone", cascade_delete=True)


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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(datetime.timezone.utc))
    temperature: float
    humidity: float
#-------------------------------------------------------
#Controller MODELS
#-------------------------------------------------------
class ControllerBase(SQLModel):
    name: str = Field(..., description="Controller name, e.g. 'fan', 'heater'")
    model: Optional[str] = None
    # you can add other fields later (serial number, specs, etc.)

class Controller(ControllerBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    greenhouse_id: uuid.UUID = Field(foreign_key="greenhouse.id", nullable=False, ondelete="CASCADE")
    greenhouse: "Greenhouse" = Relationship(back_populates="controllers")
    sensors: list["Sensor"] = Relationship(back_populates="controller")
    equipment: list["Equipment"] = Relationship(back_populates="controller", cascade_delete=True)

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
    type: str = Field(..., description="Type of sensor (temperature, humidity, etc.)")
    model: Optional[str] = Field(default=None, description="Model/manufacturer information")
    value: Optional[float] = Field(default=None, description="Current sensor value")
    unit: Optional[str] = Field(default=None, description="Unit of measurement")

class Sensor(SensorBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    zone_id: uuid.UUID = Field(foreign_key="zone.id", nullable=False, ondelete="CASCADE")
    zone: "Zone" = Relationship(back_populates="sensors")
    controller_id: uuid.UUID = Field(foreign_key="controller.id", nullable=True, ondelete="SET NULL")
    controller: Optional["Controller"] = Relationship(back_populates="sensors")

class SensorCreate(SensorBase):
    zone_id: uuid.UUID
    controller_id: Optional[uuid.UUID] = None

class SensorPublic(SensorBase):
    id: uuid.UUID
    zone_id: uuid.UUID

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
#CLIMATE HISTORY MODELS
#-------------------------------------------------------
# class ClimateReadingBase(SQLModel):
#     temperature: float = Field(..., description="Temperature reading")
#     humidity: float = Field(..., description="Humidity reading")
#     timestamp: datetime = Field(default_factory=datetime.utcnow)

# class ZoneClimateHistory(ClimateReadingBase, table=True):
#     id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
#     zone_id: uuid.UUID = Field(foreign_key="zone.id", nullable=False, ondelete="CASCADE")
#     zone: "Zone" = Relationship(back_populates="climate_history")

# class GreenhouseClimateHistory(ClimateReadingBase, table=True):
#     id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
#     greenhouse_id: uuid.UUID = Field(foreign_key="greenhouse.id", nullable=False, ondelete="CASCADE")
#     greenhouse: "Greenhouse" = Relationship(back_populates="climate_history")
#     outside_temperature: float = Field(..., description="External temperature")
#     outside_humidity: float = Field(..., description="External humidity")

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