# Firmware Roadmap — v2 Architecture Phased Rollout

**Status:** proposal 2026-04-20. Companion to `docs/firmware-architecture-v2.md`.
**Supersedes:** ad-hoc sprint planning for firmware/sprint-16 onward.
**Owner:** firmware agent (primary) + coordinator (schema/entity_map/prompt).

## Phase 1 — Bug fixes + observability foundation (sprint-15.1 + sprint-16)

Target: ship within 1-2 weeks. Unblocks all later phases by surfacing the data needed to validate them.

### Sprint-15.1 hotfix (P0, days-scale)

Pure bug fixes. No new features. Ship independent of sprint-16.

- [ ] **Fix `sw_fog_closes_vent` enforcement.** Gate at `determine_mode` entry: if fog_wants, require vent_closed first. Add `fog_vent_interlock_blocked_today` counter to observe blocked fires. Study 3: 74% leak rate measured.
- [ ] **Fix mister vent-close interlock.** Same pattern. Either wire `sw_mister_closes_vent` end-to-end (currently in cfg_readback but NOT in SETPOINT_MAP — sprint-21 follow-up still open) or enforce unconditionally in firmware. Study 4: 12% leak rate.
- [ ] **Lower `min_heat_off_s`** from 300s to 180s. Study 2: pins 54% of off-phases. Night σ expected to drop 1.22°F → 0.7°F.
- [ ] **Audit heat1 firing during hot-dry afternoons.** Study 5 saw 4-5% duty on 2 of 4 events with outdoor > 75°F — probable stale-setpoint or hysteresis bug. Trace with mode_reason logging (below) once added.

### Sprint-16 — observability foundation + first new regimes

- [ ] **Add `mode_reason` enum + logging.** Write to `system_state(entity='mode_reason', ...)` on each mode change. Enum lists enumerated in architecture doc §Observability.
- [ ] **Add `override_events` structured table** (migration required). Replace comma-joined `overrides_active` consumers gradually. Keep writing comma-joined for backward compat until all consumers migrate.
- [ ] **Add effect counters for existing overrides** (`override_summer_vent_fires_today`, `_runtime_today_s`, same for `relief_cycle_breaker`, `dry_override`, etc.). Surface in setpoint_snapshot, aggregate nightly into daily_summary.
- [ ] **Ship `regime_hot_dry_continuous`** (see Study 5 scope). Entry: outdoor>70°F + outdoor_rh<35 + solar>500. Body: fans 100%, vent open, fog pulse to RH ceiling, misters S1 continuous pulse. Exit: sunset OR outdoor≥indoor OR hysteresis slack period. 4 new tunables: `regime_hot_dry_continuous_enabled`, `hot_dry_outdoor_temp_f`, `hot_dry_outdoor_rh_pct_max`, `hot_dry_solar_w_m2_min`.
- [ ] **Ship `regime_night_hum_guard`** (Study 6). Entry: solar<10 AND VPD>`night_hum_guard_vpd_trigger` (default 0.7) AND indoor temp > safety_fog_min_temp_f. Body: short fog pulses. 2 new tunables: `regime_night_hum_guard_enabled`, `night_hum_guard_vpd_trigger`.

**Coordinator scope for sprint-16:**
- Schema: add regime tunables to `NUMERIC_TUNABLES` + `SWITCH_TUNABLES`
- entity_map: add 6 SETPOINT_MAP entries + cfg_* readbacks
- CORE prompt: document both new regimes with entry/exit conditions
- docs/tunable-cascade.md: add rows
- Migration: `override_events` table
- Update `scorecard()` MCP tool to surface new effect counters

**Success criteria:**
- `fog_vent_interlock_blocked_today` is emitted and shows the leak shrinking post-deploy
- `mode_reason` populated on every transition, queryable
- `regime_hot_dry_continuous` fires on the next qualifying afternoon; `override_summer_vent_fires_today` shows it engaged
- Night σ decreases measurably week-over-week

## Phase 2 — Missing regimes (sprint-17 + sprint-18)

### Sprint-17 — predictive + recirc regimes

- [ ] **`regime_sunrise_preempt`** (Study 6). Trigger: `d(solar)/dt > 100 W/m²/5min` during 06:00-10:00 local. Body: preemptively engage S1 mister + open vent. Closes observed 206-min VENTILATE lag on cool-humid mornings. 2 tunables: `regime_sunrise_preempt_enabled`, `solar_derivative_preempt_threshold_w_m2_per_5min`.
- [ ] **`regime_mister_fan_recirc`** (Study 4). Trigger: S1+ active AND outdoor > `mister_fan1_recirc_above_f` (default 70°F) AND vent closed. Body: fan1 on (recirculation only, no vent). Study 4 showed 2× ΔVPD efficiency. 2 tunables: `regime_mister_fan_recirc_enabled`, `mister_fan1_recirc_above_f`.
- [ ] **`regime_predictive_heat2`** (Study 2). Trigger: outdoor < 35°F AND h1 duty last-10min > 70%. Body: pre-latch h2 before temperature starts declining. Avoids 3-min dip observed in current reactive behavior. 3 tunables: `regime_predictive_heat2_enabled`, `heat2_predictive_outdoor_f`, `heat2_predictive_h1_duty_pct`.

### Sprint-18 — transition-aware behavior

- [ ] **`regime_transition_slack`** (Study 6). Trigger: `d(solar)/dt > 150 W/m²/5min` (either direction). Body: multiply `temp_hysteresis` × 1.5 and `min_vent_on_s` × 1.5 for `transition_duration_s` (default 1800). Reduces sunset thrash from observed 8.3 mode changes/transition. 2 tunables: `regime_transition_slack_enabled`, `transition_hysteresis_multiplier`, `transition_duration_s`.
- [ ] **Retune existing defaults.** `fog_time_window_end` 17→18 or 19 (Study 3: 1163 stressed buckets post-17:00 uncovered). `fog_escalation_kpa` 0.5→0.35 (Study 3: fog is most effective in cool-dry, currently under-engaged). `mister_water_budget_gal` 200→300 (Study 4: empirically exceeded 5/15 days without cutoff). `mister_all_kpa` 1.9→1.8 (Study 4: S2 recovery speed is strong).
- [ ] **Force mister pulse above 75°F.** Study 4: continuous mode overshoots VPD in hot conditions. New tunable `mister_pulse_force_above_f` (default 75) — firmware enforces regardless of planner.
- [ ] **`fan2_outdoor_temp_ceiling_f`** (Study 1). Default 78°F. Disables fan2 escalation above this outdoor temp where Study 1 measured it adds only marginal benefit (-0.33°F/min vs -0.54°F/min below).

**Coordinator scope for sprint-17-18:**
- Add all new tunables to schema + entity_map + cascade doc
- CORE prompt: add a "regime quick-reference" section listing each regime, its entry condition, and the scorecard metric that shows if it's firing
- Surface all new effect counters in `scorecard()`

**Success criteria:**
- Sunrise VENTILATE lag drops from median 206 min to <60 min
- Sunset thrash drops from 8.3 → <5 mode changes per transition
- Mister duty above 75°F shows 100% pulse mode

## Phase 3 — Postures (sprint-19 + sprint-20)

This is the architectural inflection. Introduces Layer 2. Requires coordinated schema + firmware + planner-prompt work.

### Sprint-19 — posture infrastructure

- [ ] **Add 5 posture enum tunables** to schema (NUMERIC_TUNABLES — use 0..N int encoding since pydantic). Entity_map entries. cfg_* readbacks. Cascade doc rows.
- [ ] **Firmware posture router.** New struct `PostureWeights` computed each cycle from posture tunables. Consumed by `determine_mode()` and by regime trigger code. Posture values encoded as enums in firmware `greenhouse_types.h`.
- [ ] **`posture_sensor_trust` auto-degrade.** Firmware watches `probe_health` + NaN-count on recent readings; auto-downgrades `posture_sensor_trust` to `degraded` or `critical` and reports via cfg_* readback so planner sees the degrade (can't push back to `full` until firmware clears it).
- [ ] **Planner prompt redesign.** CORE prompt leads with posture decision-tree: "Start with posture. If forecast is X, set posture_cooling_strategy to Y." Individual tunables demoted to "escape hatch" subsection. Update `scorecard()` to show current posture + its derived internal weights.

### Sprint-20 — hardware validation (runs in parallel)

Non-firmware but blocks meaningful evaluation of cooling regimes:

- [ ] **Actual CFM measurement.** Anemometer at fan exhaust under fan1-only, fan1+fan2, fan+vent configurations. Confirms whether Study 1's 150-200 CFM back-calculation is real hardware constraint or model artifact.
- [ ] **If confirmed CFM-limited**: intake upgrade scoping (larger vent, dedicated louvre, secondary exhaust). Hardware work, not firmware.
- [ ] **If model artifact**: revise Study 1 findings; sprint-15's cooling-via-exchange premise is more valid than it currently looks.

**Success criteria:**
- Planner pushes `posture_cooling_strategy` and observes behavior change
- `posture_sensor_trust=degraded` fires when a probe goes offline, auto-clears when it returns
- CFM ground truth documented

## Phase 4 — Experiment primitive + forecast-reactive (sprint-21 + sprint-22)

### Sprint-21 — experiment primitive + enthalpy-first

- [ ] **Experiment tunable set**: `experiment_tag`, `experiment_overrides` (JSONB), `experiment_started_at`, `experiment_duration_s`, `experiment_success_criteria`, `experiment_abort_on_safety`. Firmware applies overrides for duration; auto-reverts on expiry/safety/criteria-met. All events logged to `override_events`.
- [ ] **Gate experiment mode** behind `posture_experiment_mode=active`. Prevents accidental experiment activation.
- [ ] **Enthalpy-delta first-class**. Add `regime_enthalpy_vent_enabled` that uses computed indoor/outdoor enthalpy comparison rather than discrete temp+dewpoint deltas. Validate against sprint-15 summer_vent for ≥2 weeks. If enthalpy version outperforms, mark sprint-15 summer_vent as deprecated-shim (keep enabled for backwards compat).
- [ ] **Multi-input `DecisionInputs`** struct. Firmware computes rolling averages (5-min indoor temp, 15-min VPD, 1-hr heat duty) and derivatives (d(temp)/dt, d(solar)/dt) internally. Forecast inputs pushed by dispatcher (next-hour outdoor temp/RH/solar).

### Sprint-22 — posture waypoints

- [ ] **Extend `setpoint_plan`** to carry posture + regime waypoints, not just band waypoints. Dispatcher pushes posture at scheduled times.
- [ ] **Planner prompt update.** Examples of forecast-reactive posture plans. SUNRISE plan hypothesis block to include posture rationale.
- [ ] **Scorecard**: "posture adherence" metric (planned vs actual time spent in each posture).

**Success criteria:**
- Iris runs an experiment on fog_escalation_kpa with auto-revert; `override_events` shows clean start/end
- Enthalpy regime produces ≥ equal results to discrete summer_vent; deprecation plan published
- Next hot-dry forecast pre-conditions greenhouse via posture waypoint at 11:00 MDT before stress starts

## Phase 5 — Aggressive curation (sprint-23+)

- [ ] **Retire Layer 4 tunables subsumed by postures.** Candidate list:
  - `fog_escalation_kpa` → folded into `posture_cooling_strategy` weights
  - `mister_engage_kpa`, `mister_all_kpa` → folded
  - `vpd_watch_dwell_s` → folded or moved to mechanics
  - `mister_pulse_on_s`, `mister_pulse_gap_s` → operator-only once defaults validated
  - 8 irrigation-schedule knobs → confirmed static HA-controlled, move to separate irrigation config (not firmware tunables)
  - Mister plumbing `mister_on_s`, `mister_off_s`, `mister_all_on_s`, `mister_all_off_s`, `mister_max_runtime_min` → superseded by pulse model, delete
- [ ] **Target**: 88 tunables → ~35 total. Breakdown: 6 band + 6 safety + 5 posture + 20 regime + 10 mechanics + experiment set.
- [ ] **Every remaining knob has a paired effect observable** (enforced via CI drift guard on `tunable-cascade.md`).

## Ongoing (not phased)

- **Data re-audit quarterly.** Re-run the 6-study suite as more data accumulates (summer 2026 will provide genuine hot-dry corpus). Findings feed back into default tunings + new regime proposals.
- **Deprecation tracking.** Every sprint records which Layer 4 tunables are now "soft-deprecated" (still functional but planner prompt no longer lists them). After 2 quarters soft-deprecated, remove.

## Dependencies + blockers

- **Migration timing.** Each schema change lands as a coordinator PR first (schema-first rule per `CLAUDE.md`), then firmware branch consumes. Same pattern as sprint-15 flow.
- **Planner prompt token budget.** CORE prompt is growing. Sprint-19 restructuring should net-reduce size by moving per-tunable lookup to EXTENDED (opus-only) while keeping posture/regime quick-reference in CORE for both Opus and local gemma.
- **Sprint-15 gate tunables still dormant.** Phase 1 must include updating planner prompt to actually cause Iris to push those 5 tunables. Otherwise gate stays unused and Phase 2-5 regimes inherit the same issue.

## Not in scope

- Variable fan speed (binary on/off remains hardware constraint)
- Additional hardware (new relays, sensors) — separate hardware sprint track
- Crop-profile management (separate crop-planning track)
- SaaS cloud migration (separate track)
