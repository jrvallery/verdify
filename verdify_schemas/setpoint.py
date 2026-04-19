"""SetpointChange — 1:1 onto the setpoint_changes DB row.

Adds the `confirmed_at` field from migration 084. Downstream consumers
(dispatcher audit, FB-1 confirmation monitor, website renderer) all see
the same shape.
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from .tunables import TunableParameter

SetpointSource = Literal["plan", "band", "manual", "esp32"]


class SetpointChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: AwareDatetime
    parameter: TunableParameter
    value: float
    source: SetpointSource = "plan"
    confirmed_at: AwareDatetime | None = None
    greenhouse_id: str = "vallery"
