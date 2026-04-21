# Firmware Sprint-15.1 Hotfix Spec — post-sprint-15 regressions + latent interlock bugs

**Status:** proposal 2026-04-21. Written after overnight observation of repeated whipsaw cycles and a top-down code audit against greenhouse_logic.h + controls.yaml + hardware.yaml.
**Routes to:** `firmware` agent — one-commit hotfix branch `firmware/sprint-15.1`.
**Coordinator scope:** one entity_map entry + one drift-guard validation.

## Bugs to fix (ordered by severity)

| # | Bug | File:line | Severity | Observable impact |
|---|---|---|---|---|
| 1 | `summer_vent_active` flag not wired into `active_overrides` text sensor | `controls.yaml:771-779` | **P0** — feature invisible | Sprint-15 telemetry blind spot; we can't see if the gate fires |
| 2 | Sprint-15 gate cannot unseal an ongoing SEAL cycle | `greenhouse_logic.h:180-267` | **P0** — gate half-works | Gate only pre-empts seal entry; `was_sealed` path holds sealed next cycle regardless |
| 3 | `outdoor_staleness_max_s=300s` equals dispatcher cadence — marginal eligibility | `greenhouse_types.h` default + clamp range | **P0** — gate intermittent | Gate ineligible on any push jitter > 300s |
| 4 | Vent-close interlock not enforced for fog | `controls.yaml:418-424` | **P1** — 74% efficacy loss | Study 3: 74% of fog-on time had vent open, -2.4× ΔVPD/min |
| 5 | Vent-close interlock not enforced for misters | `controls.yaml:426-670` | **P1** — 12% efficacy loss | Study 4: 12% of mister-on time had vent open |
| 6 | `min_heat_off_s=300s` pins 54% of heat1 cycles at floor | firmware default + dispatcher clamp | **P1** — night σ +0.5°F | Study 2/6: per-night σ 1.22°F could drop to 0.7°F |
| 7 | `sw_mister_closes_vent` has cfg readback but no SETPOINT_MAP route | `ingestor/entity_map.py` SETPOINT_MAP | **P2** — sprint-21 debt | Dispatcher can't push; inconsistent exposure |
| 8 | Mode/decision reasoning not observable | `controls.yaml` + `greenhouse_logic.h` | **P2** — diagnostic blind | Can't tell WHY a mode fired; blocks RCA of #2 and #3 in-flight |

---

## Fix 1 — Wire `summer_vent_active` into `active_overrides`

**Root cause.** `OverrideFlags::summer_vent_active` is set in `greenhouse_logic.h::evaluate_overrides()` (line 492) from `state.override_summer_vent`. But the ESPHome block that composes the `active_overrides` comma-joined text sensor (controls.yaml:762-779) never reads this flag — the list of emitters was written in sprint-16 (OBS-1e) and never extended when sprint-15 added the new flag.

**Evidence.** Overnight 2026-04-20 23:20 → 2026-04-21 05:30, gate eligibility conditions were satisfied 3 times (outdoor 10-17°F cooler than indoor, DP delta >30°F, temp above band). `active_overrides` was `none` throughout. Either the gate is firing invisibly, or not firing at all — **we cannot tell** without wiring this flag.

**Diff** (`firmware/greenhouse/controls.yaml`):

```diff
@@ -771,13 +771,14 @@
             if(of.occupancy_blocks_moisture) add("occupancy_blocks_moisture");
             if(of.fog_gate_rh)               add("fog_gate_rh");
             if(of.fog_gate_temp)             add("fog_gate_temp");
             if(of.fog_gate_window)           add("fog_gate_window");
             if(of.relief_cycle_breaker)      add("relief_cycle_breaker");
             if(of.seal_blocked_temp)         add("seal_blocked_temp");
             if(of.vpd_dry_override)          add("vpd_dry_override");
+            if(of.summer_vent_active)        add("summer_vent");
             obuf[n] = '\0';
             id(gh_overrides).publish_state(n > 0 ? obuf : "none");
```

One line. Validates the rest of this hotfix because we'll immediately be able to observe whether fix #2 made the gate functional.

---

## Fix 2 — Gate must unseal ongoing SEAL cycles, not only preempt entry

**Root cause.** `determine_mode()` priority order (greenhouse_logic.h:215-299):

```
1. safety_cool / safety_heat
2. in_thermal_relief
3. was_sealed && !relief_just_expired   ← sticky: exits only on vpd_below_exit | sealed_max | moisture_blocked
4. vpd_wants_seal && ... (new entry)    ← sprint-15 gate sets vpd_wants_seal=false here
5. vpd_too_low_enter
6. was_dehum && !vpd_dehum_exit
7. needs_cooling → VENTILATE
```

The sprint-15 gate block (lines 180-213) sets `vpd_wants_seal = false` + `state.override_summer_vent = true`. But `vpd_wants_seal` is only consulted at line 271's **new-entry** path. Once firmware is in SEALED_MIST, the **was_sealed** path at line 250 takes over, and that path doesn't read `vpd_wants_seal`. The gate is toothless for the lifetime of the seal cycle.

**Consequence.** Firmware enters seal on first cycle (for whatever reason — stale outdoor data, dwell just matured, etc.), then the gate can never un-seal even though gate eligibility is obvious. This matches exactly what we observed: brief seal → THERMAL_RELIEF exit after sealed_max_ms (10 min) → next cycle potentially re-enters seal because outdoor conditions are the same. Whipsaw.

**Diff** (`firmware/lib/greenhouse_logic.h`):

```diff
@@ -178,6 +178,7 @@
     }
     bool vpd_wants_seal = vpd_above_band && state.vpd_watch_timer_ms >= sp.vpd_watch_dwell_ms;

     // ── Sprint-15: summer thermal-driven vent preference gate ──
+    // Sprint-15.1: gate now pre-empts BOTH new seal entries AND ongoing
+    // sealed cycles. Pre-15.1 the gate only set vpd_wants_seal=false which
+    // didn't affect the was_sealed path (line 250), so ongoing seals stayed
+    // sealed regardless. In practice the first seal entry happens whenever
+    // outdoor data is briefly stale, and the was_sealed bypass meant gate
+    // could never recover the cycle.
     state.override_summer_vent = false;
     {
         const bool outdoor_data_fresh = (in.outdoor_data_age_s < sp.outdoor_staleness_max_s);
         const bool outdoor_cooler     = (in.outdoor_temp_f      < (in.temp_f      - sp.vent_prefer_temp_delta_f));
         const bool outdoor_drier_dp   = (in.outdoor_dewpoint_f  < (in.dew_point_f - sp.vent_prefer_dp_delta_f));
         const bool temp_above_band    = (in.temp_f > (sp.temp_low + sp.temp_hysteresis));
         const bool vent_preferred     = sp.sw_summer_vent_enabled
                                      && outdoor_data_fresh
                                      && outdoor_cooler
                                      && outdoor_drier_dp
                                      && temp_above_band;
-        if (vent_preferred && vpd_wants_seal) {
-            // Pre-empt the seal — fall through to the temperature-driven
-            // VENTILATE branch below. Telemetry flag is read by
-            // evaluate_overrides() and surfaced as override_events.
+        if (vent_preferred && (vpd_wants_seal || was_sealed)) {
+            // Pre-empt the seal — clear entry dwell (blocks new seal) AND
+            // clean up sealed state (forces the was_sealed path to fall
+            // through). Telemetry flag is read by evaluate_overrides() and
+            // surfaced via active_overrides = "summer_vent".
             vpd_wants_seal = false;
             state.override_summer_vent = true;
+            if (was_sealed) {
+                // Mirror the vpd_below_exit cleanup at line 252-259 so
+                // the cascade below treats this like a clean seal exit.
+                state.sealed_timer_ms = 0;
+                state.vpd_watch_timer_ms = 0;
+                state.relief_cycle_count = 0;
+                state.vent_latch_timer_ms = 0;
+                state.mist_stage = MIST_WATCH;
+                state.mist_stage_timer_ms = 0;
+                was_sealed = false;  // force normal-cascade path below
+            }
         }
     }
```

Covered by new bench test cases (see Test Plan below).

---

## Fix 3 — Raise `outdoor_staleness_max_s` default to 600s

**Root cause.** Dispatcher pushes `outdoor_temp` + `outdoor_rh` every ~5 min (300s). On each push, `pulled_data_age_s` resets to 0. Between pushes, `pulled_data_age_s` increments toward 300. Gate check (greenhouse_logic.h:197): `in.outdoor_data_age_s < sp.outdoor_staleness_max_s`. With default `outdoor_staleness_max_s=300`, at exactly dispatcher cadence the comparison flips false. Any dispatcher jitter past 300s disqualifies the gate.

**Empirical evidence.** At 08:35 MDT today, VPD crossed seal trigger AND outdoor was 10°F cooler. Gate should have fired but firmware entered seal anyway. Likely cause: outdoor_data_age_s crossed 300s briefly (dispatcher push jitter common — last push at 08:27 to gate-check at 08:35 = 480s old).

**Fix.** Raise default to 600s (2× nominal dispatcher cadence). Operator can tighten via planner push if they want stricter freshness.

**Diff** (`firmware/lib/greenhouse_types.h`):

```diff
-    uint32_t outdoor_staleness_max_s;      // gate disables when outdoor data older than this (s)
+    uint32_t outdoor_staleness_max_s;      // gate disables when outdoor data older than this (s); default 600s = 2× dispatcher cadence
```

```diff
 inline Setpoints default_setpoints() {
 ...
-        .outdoor_staleness_max_s = 300u,
+        .outdoor_staleness_max_s = 600u,
 ...
 }
```

`firmware/greenhouse/globals.yaml`:

```diff
   - id: outdoor_staleness_max_s
     type: int
     restore_value: no
-    initial_value: '300'     # 5 min — Tempest typically updates every 3 min
+    initial_value: '600'     # 10 min — 2× dispatcher cadence, covers push jitter
```

`firmware/greenhouse/controls.yaml` (clamp range in the /setpoints handler):

```diff
-                    if(key == "outdoor_staleness_max_s"){ int v = ci((int)val, 60, 1800); ... }
+                    if(key == "outdoor_staleness_max_s"){ int v = ci((int)val, 120, 1800); ... }
```

(Raising the clamp floor from 60 to 120 — anything under 2 min is below dispatcher cadence and guaranteed to ineligibilize the gate. Planner shouldn't push that.)

`docs/tunable-cascade.md`: update the default + comment in the sprint-15 section.

---

## Fix 4 — Enforce vent-close interlock for fog

**Root cause.** In controls.yaml, relay actuation at lines 419-424:

```c
set_relay(R[0], willHeat1);
set_relay(R[1], willHeat2);
set_relay(R[2], willFan1);
set_relay(R[3], willFan2);
set_relay(R[4], willFog);     // ← fog can turn on this cycle
set_relay(R[5], willVent);    // ← vent only requested off this cycle; min_on lock may hold it open
```

`set_relay` (line 76-91) respects its own min_on_ms/min_off_ms timer per relay but has no cross-relay interlock. If vent was turned on within the last `min_vent_on_s` (60s default) and sealed-mist mode switches `willVent=false`, the vent stays physically open but `willFog=true` fires. Result: fog running with vent open → Study 3's 74% efficacy-loss observation.

**Fix.** Add a pre-actuation clamp that zeroes `willFog` and mister drivers when vent is physically still open (regardless of what firmware would set next). Operator-disableable via existing `sw_fog_closes_vent` switch (default on).

**Diff** (`firmware/greenhouse/controls.yaml`, before line 419):

```diff
+          /**************** 11a — VENT-CLOSE INTERLOCK (sprint-15.1) **************/
+          // Fog + misters must wait for vent to physically close. Pre-sprint-15.1,
+          // 74% of fog-on-time and 12% of mister-on-time had vent open (Study 3+4),
+          // because set_relay respects per-relay min_on timers but has no cross-
+          // relay ordering. Check physical vent state and suppress moisture
+          // actuation until the vent actuator reports closed.
+          const bool vent_is_open = id(vent_rly)->state;
+          const bool enforce_vent_close = id(fog_closes_vent);  // sw_fog_closes_vent
+          if (enforce_vent_close && vent_is_open) {
+              willFog = false;
+              // Misters share the interlock — see block 12 below.
+          }
+
           /**************** 11 — APPLY RELAY OUTPUTS ******************************/
           set_relay(R[0], willHeat1);
           set_relay(R[1], willHeat2);
           set_relay(R[2], willFan1);
           set_relay(R[3], willFan2);
           set_relay(R[4], willFog);
           set_relay(R[5], willVent);
```

---

## Fix 5 — Enforce vent-close interlock for misters

**Root cause.** The mister state machine (controls.yaml block 12, starting line 426) drives `south_wall_mister`, `west_wall_mister`, `center_mister` switches directly via `.turn_on()` / `.turn_off()` calls, bypassing `set_relay`. No check for vent state. Same class of bug as fog.

**Fix.** Gate the mister state machine entry on `vent_is_open`:

**Diff** (`firmware/greenhouse/controls.yaml`, block 12 entry around line 437):

```diff
-            bool humidity_demand = (mode == SEALED_MIST);
+            // Vent-close interlock: no misting while vent is open. Shares the
+            // `fog_closes_vent` operator switch with fog (fixed-semantics: either
+            // all moisture waits for vent, or none does). Pre-15.1 mister had
+            // its own dormant `sw_mister_closes_vent` switch that was never
+            // wired to the dispatcher (sprint-21 follow-up); fix 7 wires that
+            // switch end-to-end so operator has per-device granularity.
+            const bool mister_vent_ok = !vent_is_open || !id(mister_closes_vent);
+            bool humidity_demand = (mode == SEALED_MIST) && mister_vent_ok;
+
+            // If misters WERE firing but vent just opened, kill the zone drivers.
+            if (!mister_vent_ok && id(mister_pulse_zone) > 0) {
+                id(south_wall_mister).turn_off();
+                id(west_wall_mister).turn_off();
+                id(center_mister).turn_off();
+                id(mister_pulse_zone) = 0;
+                id(mister_pulse_timer_ms) = 0;
+                ESP_LOGI("interlock","Mister suppressed — vent still open");
+            }
```

`vent_is_open` is already in scope from fix 4.

---

## Fix 6 — Lower `min_heat_off_s` from 300 → 180

**Root cause.** Study 2 + Study 6 both flagged: 54% of heat1 off-phases end exactly at the 300s rail, meaning firmware wants to re-fire heat sooner and is held off by the lockout. Per-night σ of indoor temp is 1.22°F; lowering to 180s is projected to drop that to ~0.7°F without meaningfully stressing the gas igniter (3-min gaps are still well above igniter cooldown spec).

**Fix.** Lower the default in firmware, update dispatcher clamp range, update tunable-cascade doc.

**Diff** (`firmware/lib/greenhouse_types.h` in `default_setpoints`):

```diff
-        .min_heat_off_s = 300,
+        .min_heat_off_s = 180,
```

`firmware/greenhouse/globals.yaml` (or wherever `min_heat_off_s` is initialized):

```diff
-    initial_value: '300'
+    initial_value: '180'
```

`firmware/greenhouse/controls.yaml` /setpoints clamp:

```diff
-                    if(key == "min_heat_off_s"){ int v = ci((int)val, 60, 1800); ... }
+                    if(key == "min_heat_off_s"){ int v = ci((int)val, 60, 600); ... }
```

(Tighter upper bound prevents planner from walking it back past 10 min.)

`docs/tunable-cascade.md`: update `min_heat_off_s` row.

---

## Fix 7 — Wire `sw_mister_closes_vent` to SETPOINT_MAP (sprint-21 follow-up)

**Root cause.** From `verdify_schemas/tunables.py` line 132-135 comment:

> NOTE: sw_mister_closes_vent exists as an ESP32 switch (firmware tunables.yaml line 1069) and as a CFG readback, but is NOT in SETPOINT_MAP today — dispatcher can't push it. Not adding here until the routing gap is closed; see Sprint 21 follow-up.

Fix 5 above uses `id(mister_closes_vent)` as the operator toggle. For that switch to be meaningful, the dispatcher must be able to push it.

**Diff** (`ingestor/entity_map.py`):

```diff
     "fog_closes_vent": "sw_fog_closes_vent",
+    "mister_closes_vent": "sw_mister_closes_vent",   # sprint-15.1 (sprint-21 follow-up)
     "gl_auto_mode": "sw_gl_auto_mode",
```

`verdify_schemas/tunables.py` SWITCH_TUNABLES — remove the deferring note and add:

```diff
         "sw_occupancy_inhibit",
         "sw_summer_vent_enabled",
-        # NOTE: sw_mister_closes_vent exists as an ESP32 switch (firmware
-        # tunables.yaml line 1069) and as a CFG readback, but is NOT in
-        # SETPOINT_MAP today — dispatcher can't push it. Not adding here
-        # until the routing gap is closed; see Sprint 21 follow-up.
+        "sw_mister_closes_vent",  # sprint-15.1: routing gap closed
     }
 )
```

`docs/tunable-cascade.md`: add row for `sw_mister_closes_vent` in the Switches section.

---

## Fix 8 — Add `mode_reason` trace (minimal version)

**Root cause.** Fixes 2 + 3 are hypotheses. We can't confirm they land correctly in production without seeing *which* branch of `determine_mode()` actually fired. Proposed full solution in architecture v2; minimal version for this hotfix just captures a one-string reason per transition.

**Diff** (`firmware/lib/greenhouse_logic.h`, make `determine_mode` also return a reason — one option is a side-channel via ControlState):

```diff
 struct ControlState {
     ...
     bool override_summer_vent;
+    // Sprint-15.1: which branch of determine_mode() chose the current mode.
+    // Short string literal — no heap allocation. Read by controls.yaml for
+    // the `mode_reason` text sensor. Prefer this over trying to reconstruct
+    // post-hoc from state + inputs (too ambiguous once dry_override or
+    // summer_vent have cleared the dwell counters).
+    const char* last_mode_reason;
 };
```

In `determine_mode()`, at each mode-assigning branch, set `state.last_mode_reason = "..."`. Then in controls.yaml after determine_mode is called, publish `state.last_mode_reason` to a new `mode_reason` text sensor.

Add a new diagnostic text sensor in `hardware.yaml`:

```diff
   - platform: template
     id: gh_overrides
     name: "Active Overrides"
     entity_category: diagnostic
     update_interval: 5s
+
+  # Sprint-15.1: which branch of determine_mode() selected the current mode.
+  # Diagnostic-only — used to RCA gate/seal/idle decisions post-hoc.
+  - platform: template
+    id: gh_mode_reason
+    name: "Mode Reason"
+    entity_category: diagnostic
+    update_interval: 5s
```

Ingestor side: add `"mode_reason": "mode_reason"` to STATE_MAP (entity_map.py).

Minimal trace strings:

```c
if (safety_cool) { mode = SAFETY_COOL; state.last_mode_reason = "safety_cool"; ... }
else if (safety_heat) { ... "safety_heat" ... }
else if (in_thermal_relief) { mode = THERMAL_RELIEF; state.last_mode_reason = "thermal_relief"; ... }
else if (was_sealed && !relief_just_expired) {
    if (vpd_below_exit || moisture_blocked) {
        mode = needs_cooling ? VENTILATE : IDLE;
        state.last_mode_reason = state.override_summer_vent ? "summer_vent_unseal" : "seal_exit";
    } else if (...sealed_max...) { ..."thermal_relief_forced"... }
    else { mode = SEALED_MIST; state.last_mode_reason = "seal_continue"; }
}
else if (vpd_wants_seal && ...) { mode = SEALED_MIST; state.last_mode_reason = "seal_enter"; }
else if (...max_relief_cycles...) { mode = VENTILATE; state.last_mode_reason = "relief_cycle_breaker"; }
else if (vpd_too_low_enter) { mode = DEHUM_VENT; state.last_mode_reason = "vpd_too_low"; }
else if (was_dehum && ...) { mode = DEHUM_VENT; state.last_mode_reason = "dehum_continue"; }
else if (needs_cooling) { mode = VENTILATE; state.last_mode_reason = "temp_vent"; }
else { mode = IDLE; state.last_mode_reason = "idle_default"; }
```

R2-3 dry override path sets `"dry_override"`. Sprint-15 gate sets `"summer_vent_preempt"` when it suppresses a seal.

Post-hotfix we'll be able to run a query like:

```sql
SELECT value AS reason, count(*)
FROM system_state
WHERE entity='mode_reason' AND ts > now() - interval '24 hours'
GROUP BY value ORDER BY count(*) DESC;
```

which immediately answers "how often are we in idle_default during stress?" and "is summer_vent_preempt ever firing?"

---

## Test plan

### Bench tests (C++ unit tests, firmware/test/test_greenhouse_logic.cpp)

1. **Test: sprint-15 gate pre-empts new seal entry.** Inject SensorInputs with indoor 88°F / VPD 1.5 (wants seal) + outdoor 75°F / DP 30°F (gate conditions met). Setpoints default. Run determine_mode from prev=IDLE after dwell matures. Expect `mode == VENTILATE` and `state.override_summer_vent == true`.
2. **Test: sprint-15 gate unseals ongoing SEAL.** Same inputs but `prev=SEALED_MIST`, `state.sealed_timer_ms` mid-cycle. Expect `mode == VENTILATE`, `state.override_summer_vent == true`, `state.sealed_timer_ms == 0`, `state.mist_stage == MIST_WATCH`.
3. **Test: gate correctly NOT firing when outdoor not cooler.** Indoor 88°F / VPD 1.5 + outdoor 85°F / DP 30°F. Expect `mode == SEALED_MIST`, `override_summer_vent == false`.
4. **Test: gate correctly NOT firing when outdoor stale.** All conditions met except `in.outdoor_data_age_s = 900`. Setpoints `outdoor_staleness_max_s = 600`. Expect `mode == SEALED_MIST`, `override_summer_vent == false`.
5. **Test: `min_heat_off_s` adaptive below 180s clamp.** Push `min_heat_off_s = 100`; dispatcher should clamp to 60 (floor) but never let it exceed 600 (ceiling).

### Integration tests (synthetic today's data)

6. Replay today's 2026-04-21 overnight sensor stream through the state machine with sprint-15.1 active. Expected: gate fires at 23:20, 05:13, 05:26 events (vs 0 firings pre-fix). No SEAL+MIST+THERMAL_RELIEF whipsaw on those events.

### Post-deploy validation (live)

7. Query `SELECT value, count(*) FROM system_state WHERE entity='active_overrides' AND ts > now() - '24h' GROUP BY value;` and confirm `summer_vent` appears (currently zero firings).
8. Query `daily_summary` for `cycles_heat1` pre/post deploy — expect modest increase (shorter off-period allows more cycles) and night temp σ decrease.
9. Query `system_state` for `mode_reason` — confirm `idle_default` is rare during stress events (Study 5's 40% IDLE observation should drop significantly).
10. Query fog+vent simultaneous time pre/post deploy:
    ```sql
    WITH bucket AS (
      SELECT time_bucket_gapfill('30s', ts) AS ts, equipment,
             locf(last(state::int, ts)) AS on
      FROM equipment_state WHERE ts > now() - interval '1 hour'
        AND equipment IN ('fog','vent')
      GROUP BY 1, 2
    )
    SELECT
      sum(CASE WHEN fog=1 THEN 1 ELSE 0 END) AS fog_min,
      sum(CASE WHEN fog=1 AND vent=1 THEN 1 ELSE 0 END) AS fog_vent_leak
    FROM (SELECT ts, max(CASE WHEN equipment='fog' THEN on END) AS fog,
                     max(CASE WHEN equipment='vent' THEN on END) AS vent
          FROM bucket GROUP BY ts) q;
    ```
    Expect `fog_vent_leak / fog_min < 5%` post-fix (74% pre-fix).

### Pre-deploy guardrails

- `firmware/artifacts/last-good.ota.bin` captured before deploy (current: sprint-15 commit e74b884).
- `make firmware-check` passes (compile + bench).
- Post-OTA sensor-health sweep (sprint-17 infra) — fail = auto-rollback.
- 24h observation before declaring sprint-15.1 stable.

---

## Out of scope for 15.1

Addressed in later phases per `docs/firmware-roadmap-v2.md`:

- Full `mode_reason` enum + structured override_events table → sprint-16
- `regime_hot_dry_continuous` + `regime_night_hum_guard` → sprint-16
- Predictive triggers (sunrise preempt, heat2 predictive, mister+fan recirc) → sprint-17
- Postures (`posture_cooling_strategy`, etc.) → sprint-19
- CFM hardware validation → sprint-20

## Open questions flagged for firmware agent

1. **heat1 firing at 74°F indoor at 2026-04-21 08:35:48** — unclear root cause. Could be delayed relay report after min_heat_off expiry with a stale decision queue. Fix 8's mode_reason trace will disambiguate on next occurrence. If `idle_default` logs with `out.heat1=true` somewhere, the IDLE-mode equipment resolution (greenhouse_logic.h:600-611) has a path that fires heat1 on `econ_block && vpd < vpd_low_eff && temp < Thigh - econ_heat_margin_f`. That would be worth double-checking against today's conditions (need `econ_block` state).

2. **Should the sprint-15 gate also preempt `relief_cycle_breaker` forced VENTILATE?** Currently it does — the gate fires before that path. But the interaction isn't tested. Bench test #6's replay should exercise it.

3. **Sprint-12 center-of-band with `bias_heat=3`** still targets 66.4°F (upper edge of 62.4-66.4 band). That's Thigh_interior level. Fix is arguably not firmware — the operator default for `bias_heat` should be lower (1-2°F) given the current tight band. Recommend coordinator follow-up to push a lower `bias_heat` default.

---

## Ready to ship

If firmware agent approves this spec, route to `firmware/sprint-15.1` branch, one commit. Expected changes:

- `firmware/lib/greenhouse_logic.h` — fix 2, fix 8 (+~30 LOC)
- `firmware/lib/greenhouse_types.h` — fix 3, fix 6, fix 8 (+~4 fields updated)
- `firmware/greenhouse/controls.yaml` — fix 1, fix 4, fix 5, fix 8 (+~40 LOC)
- `firmware/greenhouse/hardware.yaml` — fix 8 (+~6 LOC)
- `firmware/greenhouse/globals.yaml` — fix 3, fix 6 (+2 LOC)
- `firmware/test/test_greenhouse_logic.cpp` — 5 new bench tests (+~120 LOC)
- `ingestor/entity_map.py` — fix 7, fix 8 (+2 entries)
- `verdify_schemas/tunables.py` — fix 7 (+1 entry, -note)
- `docs/tunable-cascade.md` — defaults updated for fixes 3, 6, 7
- `docs/firmware-sprint-15.1-hotfix.md` — this doc

CI should stay green (lint + bench + compile). Drift guards pass.
