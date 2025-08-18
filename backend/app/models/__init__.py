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

from .actuators import *  # noqa: F403, F401
from .auth import *  # noqa: F403, F401
from .config import *  # noqa: F403, F401
from .controllers import *  # noqa: F403, F401
from .crops import *  # noqa: F403, F401

# Import enums first (no dependencies)
from .enums import *  # noqa: F403, F401

# Step 2: Primary domains with potential cross-references
from .greenhouses import *  # noqa: F403, F401

# Step 4: Association/link models imported LAST (after all target classes exist)
from .links import *  # noqa: F403, F401
from .sensors import *  # noqa: F403, F401
from .state_machine import *  # noqa: F403, F401

# Step 3: Secondary domains that reference primary domains
from .telemetry import *  # noqa: F403, F401

# Import domain models in dependency order
# Step 1: Independent domains (no cross-references)
from .users import *  # noqa: F403, F401


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
        User,  # noqa: F405
        Greenhouse,  # noqa: F405
        GreenhouseMember,  # noqa: F405
        GreenhouseInvite,  # noqa: F405
        Zone,  # noqa: F405
        Controller,  # noqa: F405
        Sensor,  # noqa: F405
        Actuator,  # noqa: F405
        ControllerButton,  # noqa: F405
        FanGroup,  # noqa: F405
        Equipment,  # noqa: F405
        SensorZoneMap,  # noqa: F405
        FanGroupMember,  # noqa: F405  # from links.py
        Crop,  # noqa: F405
        ZoneCrop,  # noqa: F405
        ConfigSnapshot,  # noqa: F405
        Plan,  # noqa: F405
        IdempotencyKey,  # noqa: F405
        StateMachineRow,  # noqa: F405
        StateMachineFallback,  # noqa: F405  # from state_machine.py
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
    UsersPaginated = Paginated[UserPublic]  # noqa: F405
    GreenhousesPaginated = Paginated[GreenhousePublicAPI]  # noqa: F405
    GreenhouseMembersPaginated = Paginated[GreenhouseMemberPublic]  # noqa: F405
    GreenhouseInvitesPaginated = Paginated[GreenhouseInvitePublic]  # noqa: F405
    ZonesPaginated = Paginated[ZonePublic]  # noqa: F405
    ControllersPaginated = Paginated[ControllerPublic]  # noqa: F405
    # Sensors & Actuators
    SensorsPaginated = Paginated[SensorPublic]  # noqa: F405
    ActuatorsPaginated = Paginated[ActuatorPublic]  # noqa: F405
    ControllerButtonsPaginated = Paginated[ControllerButtonPublic]  # noqa: F405
    FanGroupsPaginated = Paginated[FanGroupPublic]  # noqa: F405
    # Crops
    CropsPaginated = Paginated[CropPublic]  # noqa: F405
    ZoneCropsPaginated = Paginated[ZoneCropPublic]  # noqa: F405
    ZoneCropObservationsPaginated = Paginated[ZoneCropObservationPublic]  # noqa: F405
    # Config & Plans
    ConfigSnapshotsPaginated = Paginated[ConfigSnapshotPublic]  # noqa: F405
    PlansPaginated = Paginated[PlanPublic]  # noqa: F405
    # State Machine
    StateMachineRowsPaginated = Paginated[StateMachineRowPublic]  # noqa: F405
except NameError:
    # Some types might not be available in certain contexts
    pass
