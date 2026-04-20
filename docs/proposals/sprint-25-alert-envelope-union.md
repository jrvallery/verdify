# Sprint 25 — Discriminated `AlertEnvelope` (schema PR spec)

**Author:** ingestor agent
**Destination:** coordinator (schema PR on `verdify_schemas/alerts.py`)
**Depends on:** none (clean-room split — no DB schema change, `alert_log.details` is already JSONB)
**Unblocks:** ingestor Sprint 25 code work (3 story branches)

## Problem

Today `verdify_schemas/alerts.py::AlertEnvelope` has `details: dict | None = None`. The outer envelope has `extra="forbid"` but the dict payload is unconstrained. Fifteen alert types populate `details` today, each with a distinct shape. A typo or rename in any of them lands in DB silently until a downstream consumer fails.

Sprint 23's `AlertEnvelope.model_validate(a)` in `tasks.py::alert_monitor` catches envelope drift (e.g. F1's bad `category: "safety"`), but not details drift. This sprint closes the gap.

## Design

Split `AlertEnvelope` into a discriminated union keyed by `alert_type`. Each subtype carries a typed `*Details` model with `extra="forbid"`. The discriminator is `alert_type` (already a required field). The `alert_log.details` JSONB column is unchanged — Pydantic dumps to dict on INSERT, validates on model construction.

### Fifteen alert types in scope

Observed from `ingestor/tasks.py` (paths cited against `ingestor/main` @ `9e3bca3`).

| # | alert_type | fires from | sensor_id shape | details fields |
|---|---|---|---|---|
| 1 | `sensor_offline` | alert_monitor #1 (`tasks.py:509`) | `v_sensor_staleness.sensor_id` (free-form) | `type: str`, `staleness_ratio: float \| None` |
| 2 | `relay_stuck` | alert_monitor #2 (`tasks.py:529`) | `equipment.{name}` | `hours_on: float ≥ 0` |
| 3 | `vpd_stress` | alert_monitor #3 (`tasks.py:549`) | `climate.vpd_avg` | `vpd_stress_hours: float ≥ 0` |
| 4 | `temp_safety` | alert_monitor #4 (`tasks.py:570/584`) | `climate.temp_avg` | `temp_f: float` (below 40 or above 100) |
| 5 | `vpd_extreme` | alert_monitor #4b (`tasks.py:605`) | `climate.vpd_avg` | `vpd_kpa: float ≥ 0` |
| 6 | `leak_detected` | alert_monitor #5 (`tasks.py:624`) | `equipment.leak_detected` | `since: AwareDatetime` (ISO string today) |
| 7 | `esp32_reboot` | alert_monitor #6 (`tasks.py:650`) | `diag.uptime_s` | `uptime_s: float ≥ 0`, `reset_reason: str` |
| 8 | `planner_stale` | alert_monitor #7 (`tasks.py:677`) | `system.planner` | `age_s: int ≥ 0`, `age_h: float ≥ 0` |
| 9 | `safety_invalid` | alert_monitor #8 (`tasks.py:710`) | `setpoint.{parameter}` | `parameter: TunableParameter`, `value: float \| None` |
| 10 | `heat_manual_override` | alert_monitor #9 (`tasks.py:736`) | `equipment.heat1` | `watts: int ≥ 0` |
| 11 | `soil_sensor_offline` | alert_monitor #9 (`tasks.py:767`) | `{sensor_id}.{column}` | `column: str`, `sensor: str` |
| 12 | `heat_staging_inversion` | alert_monitor #10 (`tasks.py:785`) | `equipment.heat2` | `heat2_on_since: AwareDatetime`, `duration_s: float ≥ 0`, `temp_avg: float \| None`, `temp_low: float \| None`, `d_heat_stage_2: float \| None` |
| 13 | `setpoint_unconfirmed` | setpoint_confirmation_monitor (`tasks.py:2371`) | `setpoint.{parameter}` | `parameter: TunableParameter`, `requested_value: float`, `last_cfg_readback: float \| None`, `age_s: int ≥ 0`, `pushed_at: AwareDatetime` |
| 14 | `esp32_push_failed` | setpoint_dispatcher (`tasks.py:1232`) | `(none, null)` | `error: str`, `change_count: int ≥ 0` |
| 15 | `plan_context_failed` | iris_planner `_record_plan_context_failure` (`iris_planner.py:440`) | `(none, null)` | `reason: str`, `stderr: str`, `exit_code: int \| None` |

### Proposed types

```python
# verdify_schemas/alerts.py — after the existing AlertSeverity / AlertCategory

# ── Per-type detail payloads ──────────────────────────────────────
# Each *Details model is extra="forbid" — a typo in alert_monitor fails
# at model_validate time, not at downstream consumption.

class SensorOfflineDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    staleness_ratio: float | None = None

class RelayStuckDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hours_on: float = Field(..., ge=0)

class VpdStressDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vpd_stress_hours: float = Field(..., ge=0)

class TempSafetyDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temp_f: float

class VpdExtremeDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vpd_kpa: float = Field(..., ge=0)

class LeakDetectedDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    since: AwareDatetime

class ESP32RebootDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uptime_s: float = Field(..., ge=0)
    reset_reason: str = ""

class PlannerStaleDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    age_s: int = Field(..., ge=0)
    age_h: float = Field(..., ge=0)

class SafetyInvalidDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parameter: TunableParameter
    value: float | None = None

class HeatManualOverrideDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    watts: int = Field(..., ge=0)

class SoilSensorOfflineDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str
    sensor: str

class HeatStagingInversionDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heat2_on_since: AwareDatetime
    duration_s: float = Field(..., ge=0)
    temp_avg: float | None = None
    temp_low: float | None = None
    d_heat_stage_2: float | None = None

class SetpointUnconfirmedDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parameter: TunableParameter
    requested_value: float
    last_cfg_readback: float | None = None
    age_s: int = Field(..., ge=0)
    pushed_at: AwareDatetime

class ESP32PushFailedDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: str
    change_count: int = Field(..., ge=0)

class PlanContextFailedDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str
    stderr: str = ""
    exit_code: int | None = None


# ── Per-type envelopes (union members) ────────────────────────────

class _AlertBase(BaseModel):
    """Fields shared by every discriminated envelope."""
    model_config = ConfigDict(extra="forbid")
    severity: AlertSeverity
    category: AlertCategory
    sensor_id: str | None = None
    zone: str | None = None
    zone_id: int | None = None          # kept for topology routing (F9)
    message: str = Field(..., min_length=1)
    metric_value: float | None = None
    threshold_value: float | None = None


class SensorOfflineAlert(_AlertBase):
    alert_type: Literal["sensor_offline"]
    details: SensorOfflineDetails

class RelayStuckAlert(_AlertBase):
    alert_type: Literal["relay_stuck"]
    details: RelayStuckDetails

# ... one class per alert_type (15 total) ...

class PlanContextFailedAlert(_AlertBase):
    alert_type: Literal["plan_context_failed"]
    details: PlanContextFailedDetails


# ── Discriminated union + type alias ──────────────────────────────

AlertEnvelope = Annotated[
    SensorOfflineAlert | RelayStuckAlert | VpdStressAlert | TempSafetyAlert
    | VpdExtremeAlert | LeakDetectedAlert | ESP32RebootAlert | PlannerStaleAlert
    | SafetyInvalidAlert | HeatManualOverrideAlert | SoilSensorOfflineAlert
    | HeatStagingInversionAlert | SetpointUnconfirmedAlert
    | ESP32PushFailedAlert | PlanContextFailedAlert,
    Field(discriminator="alert_type"),
]
```

### `AlertLogRow` adjustment

The existing `AlertLogRow` (read-only, full persisted shape) should keep `details: dict | None` for backward compat with historical rows that may not match a current subtype. Its `alert_type: str` stays permissive. It's the WRITE path (`AlertEnvelope`) that tightens.

### MCP `AlertAction` contract

Unchanged. The MCP `alerts` tool only consumes `alert_id` + action kind — not details.

## Why discriminator: str vs Enum

Using `Literal["..."]` per-envelope + `Field(discriminator="alert_type")` gives Pydantic v2's tagged-union semantics — `model_validate({...})` routes to the right subtype in O(1) and produces a clear error if `alert_type` doesn't match any known tag. Alternative (a plain `Union` without discriminator) tries each subtype in order and surfaces a tangled error message — worse UX when a typo happens.

## Drift guards

New tests in `verdify_schemas/tests/test_alert_envelope.py`:

1. `test_envelope_dispatches_per_type` — parametrized over all 15; `AlertEnvelope.model_validate({"alert_type": ..., "details": <valid payload>, ...})` returns the correct subtype.
2. `test_envelope_rejects_cross_type_details` — parametrized; validates that supplying the payload of `alert_type=X` to an envelope with `alert_type=Y` fails.
3. `test_envelope_rejects_extra_detail_fields` — parametrized over all 15; every `*Details` rejects an extra key (drift guard).
4. `test_every_alert_type_has_a_subtype` — cross-check: enumerate `alert_type` values from the discriminator against a hard-coded list of the 15; new alert types must be added here or test fails. Makes new-type additions a deliberate step.

## Ingestor rollout (Sprint 25 code work, after this PR merges)

Three stories on `ingestor/sprint-25-alert-union`:

- **S25.1** — `alert_monitor` build sites (13 `alerts.append({...})` calls) switch to instantiating the right subtype class directly. The subsequent `AlertEnvelope.model_validate(a)` at the insert loop becomes unnecessary (already typed) but kept as a sanity check.
- **S25.2** — `setpoint_confirmation_monitor` INSERT replaced with `SetpointUnconfirmedAlert` construction + the shared insert helper (extracted from alert_monitor in the same sprint).
- **S25.3** — `forecast_deviation_check` replaces its `replan-needed.json` trigger-file write with a `ForecastDeviationAlert` subtype (or equivalent). This also supersedes the "deviation → AlertEnvelope" cross-cutting item, so that bullet can close.

## Deploy sequence

1. Coordinator opens schema-only PR with this content + tests. Drift guards green.
2. PR lands on main.
3. Ingestor pulls latest, opens `ingestor/sprint-25-alert-union`, migrates alert sites. Drift guards stay green.
4. Live-restart gate. At least one cycle of every alert type in staging (or wait for natural triggers over a few days).
5. Once the 15 code paths are all on typed builders, the fallback `model_validate` at the insert loop can be dropped — schema itself is the only validator needed.

## Risk / reversal

- Risk: a future alert_type added to `tasks.py` but not to the schema would fail `AlertEnvelope.model_validate` at build time. **Good** — that's the drift guard doing its job; don't paper over it with a generic fallback envelope.
- Reversal: revert the schema-only PR. Ingestor's alert_monitor code is unchanged at Sprint 25 PR-merge time; the flat-dict path still works if we roll back.
- Not addressed here: any consumers of `alert_log.details` JSONB that expect legacy keys. `AlertLogRow` is unchanged, so readers of persisted rows see what they saw before. The tightening is WRITE-side only.

## Sanity check questions for coordinator review

1. Should `AlertCategory` grow `"safety"`? F1 currently uses `"system"` (Sprint 24 shipped that). The discriminated union gives `safety_invalid` its own subtype already — `category` is just a coarse group. Leave `AlertCategory` as-is, or add `"safety"` for semantic accuracy? My vote: leave as-is; the subtype is the real distinction.
2. `zone_id: int | None` on `_AlertBase`: F9 says alert_monitor doesn't populate it today. Is it worth holding this PR until F9's `zone_of(sensor_id)` helper exists, or ship both tracks in parallel? My vote: ship in parallel — this PR makes zone_id availability a non-breaking default; F9 can populate later.
