"""Forecast-driven action pipeline schemas.

- ForecastActionRule: declarative rule — "if metric operator threshold within
  time_window, adjust param by adjustment_value"
- ForecastActionLog: audit trail of every triggered rule + before/after values
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

ForecastActionType = Literal["setpoint", "alert", "noop", "override"]


class ForecastActionLog(BaseModel):
    """forecast_action_log table row — one row per triggered rule firing."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    rule_id: int | None = None
    rule_name: str = Field(..., min_length=1)
    triggered_at: AwareDatetime | None = None
    forecast_condition: dict | None = None
    action_taken: str = Field(..., min_length=1)
    plan_id: str | None = None
    param: str | None = None
    old_value: Decimal | None = None
    new_value: Decimal | None = None
    outcome: str | None = None
    greenhouse_id: str = "vallery"


class ForecastActionRule(BaseModel):
    """forecast_action_rules table row — rules engine definition."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str = Field(..., min_length=1)
    condition: str = Field(..., min_length=1)
    metric: str = Field(..., min_length=1)
    operator: str = Field(..., min_length=1)  # '>', '<', '>=', etc.
    threshold: Decimal
    time_window: str = "24h"
    param: str | None = None
    adjustment_value: Decimal | None = None
    action_type: ForecastActionType = "setpoint"
    priority: int = Field(default=50, ge=0, le=1000)
    cooldown_hours: int = Field(default=6, ge=0)
    enabled: bool = True
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
