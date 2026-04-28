# Firmware Architecture v2 — Layered Tunable Model for AI Flexibility

**Status:** proposal, 2026-04-20. Written by iris-dev (coordinator) after a 6-study data-driven audit of the current controller behavior.
**Supersedes:** implicit flat-tunable interface documented piecemeal across `tunables.yaml`, `controls.yaml`, `docs/tunable-cascade.md`.
**Routes to:** `firmware` agent + `coordinator` for end-to-end rollout. See companion phased roadmap in `docs/backlog/firmware-roadmap-v2.md`.

## Why this exists

The current firmware exposes **88 flat tunables** to the AI planner (Iris). A 60-day audit shows **37 of those 88 have never been pushed**. The planner is forced to mentally simulate the state machine to compose behavior out of low-level relay timers and threshold deltas — and most of the time she can't, so those knobs sit dormant. Meanwhile, during the stress events the controller is designed to handle, firmware chose `IDLE` 40% of the time while indoor was 10-25°F above band (Study 5).

The mismatch is architectural. The AI needs to express **what** the greenhouse should prefer (intent), and firmware should handle **how** (mechanism). Today the interface is mechanism-only.

This document defines the target architecture: a layered tunable model where each layer has a different owner, change rate, and blast radius, and where the AI's primary control surface is *posture + regime opt-ins*, not individual relay timers.

## Data audit summary (context)

Six parallel studies of 45-90 days of operational data (commit `e74b884` firmware state) surfaced the following signals that motivate this redesign:

- **Logic-limited, not physics-limited**: during hot-dry afternoon failures, 83% of minutes had indoor above band AND at least one major cooling actuator off. Only 8-17% of failed minutes were true equipment saturation.
- **Vent-close interlocks leak**: fog runs with vent open 74% of the time; mister 12%. Efficacy loss: 2.4× for fog, ~30% for mister.
- **Sprint-15 gate is dormant**: 5 new tunables live in firmware, planner has pushed zero of them in 60 days.
- **Dead interface surface**: 37 of 88 tunables never touched. Some are superseded (mister plumbing vs pulse model), some are feature-dormant (sprint-15), some are intentionally static (irrigation schedules).
- **Mechanical defaults wrong**: `min_heat_off_s=300` pins 54% of heat-off phases at the floor; plant cools during lockout.
- **Regime-dependence unacknowledged**: fog is -0.228 kPa/min in cool-dry but only -0.022 in hot-dry; mister is 2× more efficient with fan1 recirc in warm conditions but firmware rarely enables it.
- **Zone targeting mostly theater**: greenhouse is well-mixed except the S-wall; west/east/center bleed effects to neighbors in 2 min.

Full study reports are preserved in session artifacts; summarized findings inform the design below.

## The layered model

| Layer | Owner | Purpose | Change rate | Approx knob count |
|---|---|---|---|---|
| **0 — Safety rails** | Operator | Absolute clamps firmware refuses to cross regardless of AI input | rare (crop change, hardware change) | 4-6 |
| **1 — Crop band** | Crop profile (DB-driven) | Target temp + VPD bands, hysteresis | per crop change / season | 6 |
| **2 — Posture** | AI (Iris) | High-level behavioral mode enums | daily | 4-6 enums |
| **3 — Regime triggers** | AI (Iris) | Enable/tune named scenario recipes | weekly | 15-25 |
| **4 — Device mechanics** | Operator (rarely AI) | Relay timers, hardware-physics constants | quarterly | ~20 |
| **5 — Experimental scratch** | AI (Iris), short-lived | A/B testing with auto-revert | hourly (rare) | dynamic |

**The AI's primary control surface is Layer 2 + Layer 3.** Everything else she touches only for experiments or responding to specific diagnostics. Today's 88 tunables live almost entirely in Layer 4, which is why so many are dormant.

## Layer-by-layer definition

### Layer 0 — Safety rails (operator-only, AI cannot weaken)

Firmware refuses to leave these regardless of any AI input. Clamp is applied by dispatcher at ingest AND re-asserted in firmware `validate_setpoints()`.

- `safety_min` — absolute low temp cutoff (SAFETY_HEAT trigger)
- `safety_max` — absolute high temp cutoff (SAFETY_COOL trigger)
- `safety_vpd_min` — DEHUM_VENT force trigger
- `safety_vpd_max` — R2-3 dry override seal trigger
- `safety_fog_min_temp_f` — fog absolutely blocked below this (anti-frost)
- `safety_leak_max_gpm` — leak-detection rail (future; links to existing `leak_detected` sensor)

Keep current behavior: dispatcher clamps per `_PHYSICS_INVARIANTS`, firmware asserts on ingest. No AI override path.

### Layer 1 — Crop band (crop profile default, AI-can-widen-or-tighten within safety)

- `temp_low`, `temp_high` — target temperature band
- `temp_hysteresis` — band dead-zone (prevents mode churn near boundary)
- `vpd_low`, `vpd_high` — target VPD band
- `vpd_hysteresis` — VPD band dead-zone
- `bias_heat`, `bias_cool` — band-internal offset (sprint-12 center-of-band targeting)

Source of truth: `crop_target_profiles` table, pushed by dispatcher. Iris can override within safety clamp. Current behavior is correct; keep.

### Layer 2 — Posture (brand new; primary AI control surface)

Small number of enum tunables that map to bundles of firmware behavior. The AI picks one value; firmware expands it into a weight profile applied to the Layer 3 regimes and Layer 4 decisions.

```
posture_cooling_strategy:   { economiser_first | evaporative_first | balanced }
posture_dryness_tolerance:  { strict | moderate | tolerant }
posture_energy_priority:    { cost_minimize | comfort_maximize | balanced }
posture_sensor_trust:       { full | degraded | critical }   # auto-degrades on probe_health issues
posture_experiment_mode:    { off | active }                 # enables Layer 5
```

**Example**: if Iris sets `posture_cooling_strategy = evaporative_first`, firmware internally:
- Lowers the effective `fog_escalation_kpa` threshold
- Raises priority of SEALED_MIST_S1 entry over VENTILATE
- Enables `regime_mister_fan_recirc` automatically above 70°F
- Does NOT change any Layer 4 mechanics

Each posture is a firmware-coded bundle of ~5-10 internal weight changes. Adding a new posture value = firmware change. The AI interface stays stable.

**Why this matters**: today, Iris approximates postures by pushing combinations of `fog_escalation_kpa` + `mister_engage_kpa` + `vpd_watch_dwell_s` + etc. That's error-prone and 37 of those individual knobs end up dormant. Postures compress the common intents into a handful of safe, meaningful choices.

### Layer 3 — Regime triggers (existing pattern, formalized)

Each regime is a named firmware behavior that pre-empts or augments the base cascade. Sprint-15's `sw_summer_vent_enabled` gate is the first example; it should not be the last or the only one.

Pattern: each regime has
- One `regime_*_enabled` switch (default 1)
- 1-3 threshold tunables (e.g. temp deltas, dwell times)
- 1-3 effect counters (fires today, runtime today)
- A documented entry + exit condition pair
- A telemetry override flag (exposed in `overrides_active`)

Regimes to ship (see phased roadmap for sequencing):

| Regime | Purpose | Source |
|---|---|---|
| `regime_summer_vent` | Outdoor-cooler+drier → pre-empt VPD-seal | already live (sprint-15) |
| `regime_hot_dry_continuous` | Hot+dry+high-solar → collapse cascade into max-cooling | Study 5 |
| `regime_night_hum_guard` | Night VPD>0.7 → fog pulse | Study 6 |
| `regime_sunrise_preempt` | Solar derivative → preempt VENTILATE | Study 6 |
| `regime_transition_slack` | Rapid solar change → hysteresis × 1.5 for 30 min | Study 6 |
| `regime_mister_fan_recirc` | Warm + S1 active → auto fan1 recirc | Study 4 |
| `regime_predictive_heat2` | Outdoor <35°F + h1 duty >70% → pre-latch h2 | Study 2 |
| `regime_enthalpy_vent` | General enthalpy-delta driven ventilation | future, replaces discrete summer_vent |

All default enabled. AI can disable individual regimes for experiments. Adding a regime is a scoped firmware change that doesn't touch other regimes.

### Layer 4 — Device mechanics (operator-level, escape hatch for AI)

The knobs the current firmware exposes. Keep them as an override path but expect the AI to almost never touch them once Layers 2-3 are complete.

Examples:
- `min_fan_on_s`, `min_fan_off_s`, `min_heat_on_s`, `min_heat_off_s`, `min_vent_on_s`, `min_vent_off_s`, `min_fog_on_s`, `min_fog_off_s`
- `d_heat_stage_2`, `d_cool_stage_2`
- `fan_burst_min`, `vent_bypass_min`, `fog_burst_min`, `lead_rotate_s`
- Mister pulse model: `mister_pulse_on_s`, `mister_pulse_gap_s`
- Mister stage thresholds: `mister_engage_kpa`, `mister_all_kpa` (if not collapsed into `posture_cooling_strategy`)

**Deprecation plan**: once postures are live and stable, a large subset of Layer 4 tunables become redundant. Target migration: sprint-22 onward, aggressively retire knobs that posture bundles now control.

### Layer 5 — Experimental scratch (AI-writable, short-lived, auto-reverting)

Required for Iris to run clean A/B experiments without permanent drift.

```
experiment_tag              # name, surfaced in override_events
experiment_overrides        # JSONB of {tunable: value}
experiment_started_at       # firmware timestamp
experiment_duration_s       # auto-revert deadline
experiment_success_criteria # optional expression, e.g. "compliance_pct_5min > 0.9"
experiment_abort_on_safety  # default true — any safety trip aborts experiment
```

Firmware applies overrides for the duration; reverts on expiry, safety trip, or criteria-met. All start/end events logged to `override_events` table. `posture_experiment_mode=active` gates this to prevent accidental use.

Enables: "try `fog_escalation_kpa=0.25` for 2 hours tomorrow afternoon, auto-revert" without Iris tracking revert herself.

## Observability — what's missing from the current interface

Today we have **value readbacks** (`cfg_*`) — firmware tells us what config values it thinks it has. That is necessary but not sufficient. What's missing is **effect observables** — what did the config actually cause to happen.

### Effect counters (add one per regime + per existing override)

Pattern: `<regime>_fires_today`, `<regime>_runtime_today_s`, `<regime>_last_entry_ts`, `<regime>_last_exit_reason`.

Concrete entries to add:
- `override_summer_vent_fires_today` + `_runtime_today_s`
- `override_relief_cycle_breaker_fires_today`
- `override_dry_fires_today`
- `regime_hot_dry_continuous_runtime_today_s`
- `regime_night_hum_guard_fires_today`
- `mister_fan_recirc_engagements_today`
- `heat2_predictive_latches_today`
- `fog_vent_interlock_blocked_today` (count of times firmware blocked fog from firing because vent was still open — debugging observability)

Surfaced alongside cfg_* readbacks in `setpoint_snapshot`. Aggregated in `daily_summary`. Exposed in `scorecard()` MCP tool.

### Structured override events (replace comma-joined text)

Today `system_state(entity='overrides_active', value='summer_vent,relief_cycle_breaker,...')` is a comma-joined text. It can't answer "when does summer_vent fire? How long? What triggered it?"

Replace with structured table:

```sql
CREATE TABLE override_events (
  id          BIGSERIAL PRIMARY KEY,
  ts          TIMESTAMPTZ NOT NULL,
  override    TEXT NOT NULL,            -- 'summer_vent', 'dry_override', 'relief_cycle_breaker', ...
  event       TEXT NOT NULL,            -- 'start' | 'end'
  mode_at_event TEXT,                   -- greenhouse_state at time of event
  reason      TEXT,                     -- firmware-authored brief explanation
  trigger_values JSONB                  -- snapshot: {outdoor_temp_f, outdoor_dewpoint_f, indoor_temp_f, ...}
);
```

Populated by firmware via a new field in the /status push. Mirrors Ingestor sprint-18's `override_events` pattern but adds structured trigger_values.

### Mode-entry reason (why did we pick this mode?)

Every call to `determine_mode()` should log a reason enum when the mode changes:

```c
enum ModeReason {
    MR_SAFETY_COOL,
    MR_SAFETY_HEAT,
    MR_THERMAL_RELIEF,
    MR_VPD_SEAL_S1,
    MR_VPD_SEAL_S2,
    MR_VPD_SEAL_FOG,
    MR_SUMMER_VENT_PREEMPT,
    MR_HOT_DRY_CONTINUOUS,
    MR_SUNRISE_PREEMPT,
    MR_RELIEF_CYCLE_BREAKER,
    MR_DEHUM_VENT,
    MR_TEMP_VENTILATE,
    MR_TEMP_HEAT_S1,
    MR_TEMP_HEAT_S2,
    MR_TRANSITION_SLACK,
    MR_DEFAULT_IDLE       // !!! this should be rare
};
```

Written to `system_state(entity='mode_reason', value=ModeReason)` on each transition. Enables queries like "How often is MR_DEFAULT_IDLE the reason when we're failing compliance?" (answer today: 40% of hot-dry afternoons — invisible without this field).

### Enthalpy-delta as a first-class decision input

`SensorInputs.enthalpy_delta` exists in the struct but `determine_mode()` never reads it. Sprint-15's summer-vent gate uses two discrete deltas (temp + dewpoint) as a proxy. That proxy is partially wrong (it's why the gate's firmware-modeled impact exceeded the measured 10× CFM constraint).

Move to using computed enthalpy as the core cooling-direction decision variable:
- Indoor enthalpy from indoor temp + RH
- Outdoor enthalpy from Tempest (needs the `outdoor_enthalpy_kj_kg` computation that Tempest data supports)
- `enthalpy_delta_kj_kg = outdoor - indoor`
- Gate: if `enthalpy_delta < -3` → cooling opportunity, prefer ventilation

New regime: `regime_enthalpy_vent_enabled` supersedes the discrete `regime_summer_vent` once validated.

### Multi-input decision variables

Current `determine_mode()` consumes ~5 instantaneous state variables. Predictive behavior needs:
- Rolling averages: 5-min indoor temp, 15-min VPD, 1-hr heat duty
- Derivatives: `d(temp)/dt`, `d(solar)/dt`, `d(vpd)/dt`
- Forecast lookahead: next-hour outdoor temp / RH / solar (pushed by dispatcher alongside setpoints)
- Duty cycle today: `h1_duty_today_pct`, `fan_duty_today_pct`, `fog_runtime_today_s`

Add a `DecisionInputs` struct alongside `SensorInputs` that carries these aggregates. Firmware computes the rolling/derivative fields internally; forecast + duty are pushed by dispatcher.

## Forecast-reactive posture waypoints

Dispatcher already has weather forecast. Extend `setpoint_plan` to carry posture waypoints, same shape as band waypoints today:

```python
set_plan([
  {ts: "tomorrow 11:00", tunable: "posture_cooling_strategy", value: "evaporative_first"},
  {ts: "tomorrow 11:00", tunable: "regime_hot_dry_continuous_enabled", value: 1},
  {ts: "tomorrow 18:00", tunable: "posture_cooling_strategy", value: "balanced"},
  {ts: "tomorrow 18:00", tunable: "regime_hot_dry_continuous_enabled", value: 0},
])
```

Iris plans postures for the day; firmware is pre-conditioned before stress arrives rather than reacting 206 minutes late (Study 6's sunrise lag). Closes the reactive-morning-spike gap.

## Migration path

See `docs/backlog/firmware-roadmap-v2.md` for the phased plan. Short version:

- **Phase 1 (sprint-15.1 + sprint-16)**: P0 bug fixes (vent interlocks, min_heat_off_s), add mode_reason logging, add effect counters for existing overrides, ship `regime_hot_dry_continuous` + `regime_night_hum_guard`.
- **Phase 2 (sprint-17-18)**: add missing regimes (sunrise_preempt, transition_slack, mister_fan_recirc, predictive_heat2).
- **Phase 3 (sprint-19-20)**: introduce postures, update planner prompt, start deprecating redundant Layer 4 tunables.
- **Phase 4 (sprint-21-22)**: experiment primitive + forecast-reactive posture waypoints + structured override_events + enthalpy-delta first-class.
- **Phase 5 (sprint-23+)**: aggressive curation. Target: 88 → ~35 tunables total.

## Design principles (the rules this architecture enforces)

1. **Intent above mechanism.** The AI expresses *what to prefer*, not *how to move the relays*.
2. **Layers have owners.** Safety is operator. Band is crop. Posture + regime are AI. Mechanics are operator. Experiment is AI-scratch. Blast radius respects the owner.
3. **Every knob has a paired observable.** If there's no way to see whether the knob mattered, the knob shouldn't exist.
4. **Decisions are explainable.** Every mode entry carries a reason. Every override has a structured event. No silent behavior.
5. **Experimentation is first-class.** Iris can A/B without permanent drift. Auto-revert + audit.
6. **New capabilities land as new regimes.** Adding behavior doesn't reshape the interface or require Iris to relearn the knob space.
7. **Deprecation is planned.** Layer 4 tunables that postures subsume get removed, not left as ghost knobs. The interface stays curated.

## What this doesn't solve

- **CFM limit.** Study 1 back-calculated observed airflow at 150-200 ft³/min vs 4,900 spec — a hardware constraint. Software can't fix a 10× intake shortfall. Sprint-20 (hardware validation + possible intake upgrade) runs in parallel to this firmware work.
- **Crop band vs physics.** Current `temp_high=66.4°F` is unachievable at outdoor 84°F + full solar. Band widening or summer crop switch is a crop-planning conversation; this architecture doesn't address it but enables forecast-reactive band waypoints.
- **Sensor truth.** All of this assumes the sensors are honest. Sprint-21+ work on probe_health + sensor_trust posture auto-degrade starts addressing it.

## Review + approval

This document is a proposal. Firmware agent reviews for implementability; coordinator approves phased rollout. Land as doc-only now; Phase 1 implementation follows.
