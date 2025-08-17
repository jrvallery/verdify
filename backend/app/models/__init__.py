"""
Aggregate imports of ALL mapped models so SQLAlchemy's class registry
sees them before any metadata/DB operations.
Import this module early in app startup, Alembic env.py, and tests.

Dependency order (order matters):
1. enums (no dependencies)
2. users (no dependencies)
3. greenhouses (-> users)
4. controllers (-> greenhouses)
5. sensors (-> controllers)
6. actuators (-> controllers)
7. crops (-> zones)
8. config, telemetry (-> prior domains)
9. auth (standalone)
10. links (-> all target classes) # association models imported LAST

Rationale: ensure all class names are importable/registered before links resolve.
"""
from __future__ import annotations

# Re-export SQLModel for Alembic
# Import pagination utilities
from app.utils_paging import Paginated

from .actuators import *  # Actuators domain - references controllers
from .auth import *  # Auth models - standalone token/messaging
from .config import *  # Config and Plan models
from .controllers import *  # Controllers domain - may reference greenhouses
from .crops import *  # Crops domain

# Import enums first (no dependencies)
# Step 2: Primary domains with potential cross-references
from .greenhouses import *  # Greenhouses domain

# Step 4: Association/link models imported LAST (after all target classes exist)
from .links import *  # Cross-domain associations imported after all targets available
from .sensors import *  # Sensors domain - references controllers
from .state_machine import *  # State machine models - references greenhouses

# Step 3: Secondary domains that reference primary domains
from .telemetry import *  # Telemetry domain - references sensors and controllers

# Import domain models in dependency order
# Step 1: Independent domains (no cross-references)
from .users import *  # Users domain - referenced by many others


def bootstrap_mappers() -> None:
    """
    Idempotently force SQLAlchemy to resolve all string relationships
    *after* all model classes have been imported into the registry.
    """
    from sqlalchemy.orm import configure_mappers

    configure_mappers()


# T24.4 - Rebuild Pydantic models after imports (forward annotation safety net)
try:
    for cls in [
        User,
        Greenhouse,
        Zone,
        Controller,
        Sensor,
        Actuator,
        ControllerButton,
        FanGroup,
        Equipment,
        SensorZoneMap,
        FanGroupMember,  # from links.py
        Crop,
        ZoneCrop,
        ConfigSnapshot,
        Plan,
        IdempotencyKey,
        StateMachineRow,
        StateMachineFallback,  # from state_machine.py
    ]:
        cls.model_rebuild()
except Exception:
    # Non-fatal; helps in tests where namespaces differ
    pass


# ===============================================
# PAGINATED TYPES
# ===============================================
# Define here as fallback since module-level assignments in sub-modules
# sometimes don't work with star imports
try:
    # Core entities
    UsersPaginated = Paginated[UserPublic]
    GreenhousesPaginated = Paginated[GreenhousePublicAPI]
    ZonesPaginated = Paginated[ZonePublic]
    ControllersPaginated = Paginated[ControllerPublic]
    # Sensors & Actuators
    SensorsPaginated = Paginated[SensorPublic]
    ActuatorsPaginated = Paginated[ActuatorPublic]
    ControllerButtonsPaginated = Paginated[ControllerButtonPublic]
    FanGroupsPaginated = Paginated[FanGroupPublic]
    # Crops
    CropsPaginated = Paginated[CropPublic]
    ZoneCropsPaginated = Paginated[ZoneCropPublic]
    ZoneCropObservationsPaginated = Paginated[ZoneCropObservationPublic]
    # Config & Plans
    ConfigSnapshotsPaginated = Paginated[ConfigSnapshotPublic]
    PlansPaginated = Paginated[PlanPublic]
    # State Machine
    StateMachineRowsPaginated = Paginated[StateMachineRowPublic]
except NameError:
    # Some types might not be available in certain contexts
    pass
