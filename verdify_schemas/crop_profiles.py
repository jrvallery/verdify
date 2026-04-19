"""Crop target profile — reference band curves (hour-of-day × growth stage × season).

Used by fn_band_setpoints() to derive temp/VPD bands for a crop mix; seeded
from horticultural references. One row per (crop_type, growth_stage, season,
hour_of_day) combination — so a crop's full curve is 24 rows.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CropTargetProfile(BaseModel):
    """crop_target_profiles table row."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    crop_type: str = Field(..., min_length=1)
    growth_stage: str = "vegetative"
    hour_of_day: int = Field(..., ge=0, le=23)
    season: str = "spring"
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
    greenhouse_id: str = "vallery"
