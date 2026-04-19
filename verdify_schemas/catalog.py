"""Crop catalog — reference data for crop types and their hourly target bands.

Two layers:

    CropCatalogEntry     — one row per crop type (tomatoes, basil, ...).
                           Promotes the string `crop` column in
                           `crop_target_profiles` to a typed reference.

    CropProfileHour      — one row per (crop_type, growth_stage, hour, season).
                           Mirrors the existing `crop_target_profiles` table,
                           but now FK-linked to CropCatalogEntry.

Before Sprint 22, `crop_target_profiles.crop_type` was free text; a typo
in one seed row silently produced a separate pseudo-crop with no
integrity tie to `crops.name`. This module ties them together.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .topology import GreenhouseId

_SLUG_PATTERN = r"^[a-z][a-z0-9_]*$"

CropCatalogId = Annotated[str, Field(pattern=_SLUG_PATTERN, min_length=1, max_length=64)]
"""Crop-catalog slug: lowercase snake_case (e.g., "tomatoes", "canna_lilies")."""

CropCategory = Literal[
    "fruit",
    "leafy_green",
    "herb",
    "flower",
    "root",
    "legume",
    "brassica",
    "ornamental",
    "tropical",
    "vine",
]

CropSeason = Literal["cool", "warm", "hot", "year_round", "short_day", "long_day"]

CropGrowthStage = Literal[
    "seed",
    "germination",
    "seedling",
    "vegetative",
    "flowering",
    "fruiting",
    "harvest",
]


class CropCatalogEntry(BaseModel):
    """crop_catalog table row — reference data for a crop type."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: int | None = None
    slug: CropCatalogId
    common_name: str = Field(..., min_length=1, max_length=200)
    scientific_name: str | None = Field(default=None, max_length=200)
    category: CropCategory
    season: CropSeason
    cycle_days_min: int | None = Field(default=None, ge=0)
    cycle_days_max: int | None = Field(default=None, ge=0)
    base_temp_f: float | None = Field(default=50.0, description="GDD base temperature")
    default_target_dli: float | None = Field(default=None, ge=0)
    default_target_vpd_low: float | None = Field(default=None, ge=0, le=20)
    default_target_vpd_high: float | None = Field(default=None, ge=0, le=20)
    default_ph_low: float | None = Field(default=None, ge=0, le=14)
    default_ph_high: float | None = Field(default=None, ge=0, le=14)
    default_ec_low: float | None = Field(default=None, ge=0)
    default_ec_high: float | None = Field(default=None, ge=0)
    notes: str | None = None
    created_at: AwareDatetime | None = None


class CropCatalogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slug: CropCatalogId
    common_name: str = Field(..., min_length=1, max_length=200)
    scientific_name: str | None = Field(default=None, max_length=200)
    category: CropCategory
    season: CropSeason
    cycle_days_min: int | None = Field(default=None, ge=0)
    cycle_days_max: int | None = Field(default=None, ge=0)
    base_temp_f: float | None = 50.0
    default_target_dli: float | None = Field(default=None, ge=0)
    default_target_vpd_low: float | None = Field(default=None, ge=0, le=20)
    default_target_vpd_high: float | None = Field(default=None, ge=0, le=20)
    default_ph_low: float | None = Field(default=None, ge=0, le=14)
    default_ph_high: float | None = Field(default=None, ge=0, le=14)
    default_ec_low: float | None = Field(default=None, ge=0)
    default_ec_high: float | None = Field(default=None, ge=0)
    notes: str | None = None


class CropProfileHour(BaseModel):
    """crop_target_profiles row — one hourly target band.

    Before Sprint 22: `crop_type: text` (no FK).
    After Sprint 22: `crop_catalog_id: int` FK → `crop_catalog.id`;
    the legacy `crop_type` string remains populated until Phase 6.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    id: int | None = None
    greenhouse_id: GreenhouseId
    crop_catalog_id: int | None = None  # Nullable during Phase 3 backfill window
    crop_type: str = Field(..., min_length=1, max_length=64)  # Legacy string (deprecated Phase 6)
    growth_stage: CropGrowthStage = "vegetative"
    hour_of_day: int = Field(..., ge=0, le=23)
    season: CropSeason = "cool"
    temp_ideal_min: float
    temp_ideal_max: float
    temp_stress_low: float
    temp_stress_high: float
    vpd_ideal_min: float = Field(..., ge=0, le=20)
    vpd_ideal_max: float = Field(..., ge=0, le=20)
    vpd_stress_low: float = Field(..., ge=0, le=20)
    vpd_stress_high: float = Field(..., ge=0, le=20)
    dli_target_mol: float | None = Field(default=None, ge=0)
    source: str = "horticultural_reference"


class CropStageTarget(BaseModel):
    """Aggregated target for a (crop, stage) pair across 24 hours.

    Computed view-level projection used by the website's crop-profile page
    and by the planner when it needs "what does tomatoes-flowering want on
    average". Not a table — derived from CropProfileHour.
    """

    model_config = ConfigDict(extra="ignore")

    crop_catalog_id: int
    crop_slug: CropCatalogId
    growth_stage: CropGrowthStage
    season: CropSeason
    temp_ideal_min_24h: float
    temp_ideal_max_24h: float
    vpd_ideal_min_24h: float
    vpd_ideal_max_24h: float
    dli_target_mol: float | None = None
    hours_covered: int = Field(..., ge=0, le=24)
