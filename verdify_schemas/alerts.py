"""alert_log row + alert envelope schemas.

- AlertLogRow: 1:1 onto the alert_log table (full persisted shape).
- AlertEnvelope: the dict shape that tasks.py builds up across 8 alert types
  before batch INSERT. Today it's dict-of-anything; typing it surfaces
  inconsistencies the moment they're introduced.
- AlertAction: MCP `alerts` tool envelope — replaces free-form (action, data: str).
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

AlertSeverity = Literal["info", "warning", "critical"]
AlertCategory = Literal["sensor", "equipment", "climate", "water", "system"]
AlertDisposition = Literal["open", "acknowledged", "resolved"]


class AlertEnvelope(BaseModel):
    """In-memory alert struct tasks.py builds before INSERT.

    Mirrored 1:1 on `alert_log` writable columns. Enforced here so that a new
    alert_type in `alert_monitor` can't silently drift its payload shape.

    Note: the Sprint 22 zone_id FK lands in migration 086 and gets added
    here in Phase 4.
    """

    model_config = ConfigDict(extra="forbid")

    alert_type: str = Field(..., min_length=1)
    severity: AlertSeverity
    category: AlertCategory
    sensor_id: str | None = None
    zone: str | None = None
    message: str = Field(..., min_length=1)
    details: dict | None = None
    metric_value: float | None = None
    threshold_value: float | None = None


class AlertLogRow(AlertEnvelope):
    """Full row as persisted. AlertEnvelope + audit columns."""

    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    ts: AwareDatetime | None = None
    source: str = "system"
    disposition: AlertDisposition = "open"
    acknowledged_at: AwareDatetime | None = None
    acknowledged_by: str | None = None
    resolved_at: AwareDatetime | None = None
    resolved_by: str | None = None
    resolution: str | None = None
    slack_ts: str | None = None
    notes: str | None = None
    greenhouse_id: str = "vallery"


# ── MCP action envelope ────────────────────────────────────────────
#
# Replaces the current `action: str, data: str` contract in server.py
# `alerts` tool, where `data` is ad hoc JSON parsed after the fact.
# The tool migration in Phase 7 builds an AlertAction from the raw args,
# which forces every downstream branch to see a typed payload.

AlertActionKind = Literal["list", "acknowledge", "resolve"]


class AlertAckPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledged_by: str = Field(..., min_length=1, max_length=100)


class AlertResolvePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_by: str = Field(..., min_length=1, max_length=100)
    resolution: str | None = Field(default=None, max_length=2000)


class AlertAction(BaseModel):
    """MCP `alerts` tool input envelope."""

    model_config = ConfigDict(extra="forbid")

    action: AlertActionKind
    alert_id: int | None = None  # ignored for list
    data: AlertAckPayload | AlertResolvePayload | None = None
