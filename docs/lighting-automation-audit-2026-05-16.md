# Lighting Automation Audit — 2026-05-16

## Contract

Verdify lighting now follows the same traceable shape as the climate bands,
but with one independent state machine per Lutron circuit:

1. Active crop targets seed the default DLI goal for each light circuit.
2. `fn_lighting_circuit_policy(now(), 'vallery')` emits one policy row for
   `main` / `grow_light_main` and one for `grow` / `grow_light_grow`.
3. Iris may override each circuit independently with planner-managed tunables:
   `gl_main_*`, `gl_grow_*`, `sw_gl_main_auto_mode`, and
   `sw_gl_grow_auto_mode`.
4. `setpoint_dispatcher`, `/setpoints`, and `verdify-setpoint-server` expose
   the same per-circuit policy. The dispatcher only pushes the new per-circuit
   tunables after firmware readbacks prove the deployed ESP32 supports them.
5. Firmware evaluates each light separately using a local `LightingState`:
   auto enable, photoperiod window, DLI goal, Tempest natural lux, lux
   hysteresis, minimum on/off dwell, and occupancy force-on.
6. `equipment_state`, `v_lighting_circuit_status_now`, and
   `fn_lighting_timeline()` trace expected state, actual Lutron state, natural
   light, and ON/OFF lux bands back to the same policy source used by Grafana.

Legacy `fn_lighting_policy()` and `v_lighting_status_now` remain compatibility
surfaces, but the current implementation target is the per-circuit contract.

## Current Live Policy

On 2026-05-16 at implementation time:

- Limiting crop: `pepper`
- Target DLI: `22 mol/m2/day`
- Target photoperiod: `16 hours`
- Start hour: `6`
- Natural sunset hour: `21`
- Cutoff hour: `22`
- Main light lux ON/OFF band: `40000` / `48000 lux`
- Grow light lux ON/OFF band: `40000` / `48000 lux`
- Main and grow dwell guards: `min_on=120s`, `min_off=60s`

This keeps the lighting window open after natural sunset and closes it at local hour 22.

## Live Verification

The earlier shared lighting policy was inserted into `setpoint_changes` with
`source='band'`:

- `gl_dli_target=22`
- `gl_sunrise_hour=6`
- `gl_sunset_hour=22`
- `sw_gl_auto_mode=1`

The current per-circuit database policy returns two rows:

- `main` -> `grow_light_main`, DLI `22`, window `6-22`, lux band
  `40000-48000`, dwell `120/60`, auto enabled.
- `grow` -> `grow_light_grow`, DLI `22`, window `6-22`, lux band
  `40000-48000`, dwell `120/60`, auto enabled.

The public API container was rebuilt and `verdify-setpoint-server.service` was
restarted after the source changes. Both `/setpoints` surfaces now include the
new `gl_main_*` and `gl_grow_*` values.

After the 2026-05-16 OTA, `v_lighting_circuit_status_now` reports both lights
off because outdoor lux is above the OFF threshold; that is expected in full
sun. The view also exposes expected state, actual state, DLI, natural lux,
per-circuit lux bands, and live firmware state/reason fields. The post-OTA
steady-state reason for both circuits was `lux_sufficient`.

## Lutron Control Verification

Follow-up live validation found that the stale `light.greenhouse_*` wrapper entities accepted service calls but did not report state. The actual Lutron-backed entities are:

- `switch.greenhouse_main`
- `switch.greenhouse_grow`

`verdify-setpoint-server` now commands those switches, confirms HA state before returning success, and records the confirmed state transition in `equipment_state`.

Live test at 2026-05-16 14:53 MDT ran three on/off cycles for both circuits:

- Every `POST /lights/{main,grow}/on` returned `success=true`, `confirmed_state=on`, `db_recorded=true`.
- Every `POST /lights/{main,grow}/off` returned `success=true`, `confirmed_state=off`, `db_recorded=true`.
- HA `last_changed` advanced for both switches on each cycle.
- `equipment_state` recorded ON/OFF rows for both `grow_light_main` and `grow_light_grow`.

Final verified state after the test: both Lutron switches off.

Post-OTA validation repeated the proof after firmware
`2026.5.16.1723.c9b842b.dirty` first reported diagnostics:

- `POST /lights/main/on` and `/off` returned HTTP 200, confirmed
  `switch.greenhouse_main`, and recorded `grow_light_main` state rows.
- `POST /lights/grow/on` and `/off` returned HTTP 200, confirmed
  `switch.greenhouse_grow`, and recorded `grow_light_grow` state rows.
- Both circuits had ON and OFF `equipment_state` evidence after the latest
  firmware start.
- Final verified state after the post-OTA test: both Lutron switches off.

## Tempest Lux Threshold

Firmware uses Tempest outdoor illuminance as the primary lux trigger, with indoor lux only as fallback. The old `gl_lux_threshold=3000` was too low for actual overcast detection.

`fn_lighting_lux_threshold_recommendation()` now derives planner guidance from recent Tempest `outdoor_lux` and `solar_irradiance_w_m2` history. On 2026-05-16 it used 21,106 daylight samples:

- Heavy-overcast p80: `22879 lux`
- Clear-sun p20: `58904 lux`
- Recommended threshold: `40000 lux`
- Recommended hysteresis: `8000 lux`

The shared legacy controller threshold was updated live to
`gl_lux_threshold=40000` and `gl_lux_hysteresis=8000` as a pre-OTA fallback.
Those shared `gl_lux_*` values are now read-only dispatcher/default context;
the planner-owned knobs are the per-circuit values. After the OTA, Iris can
tune `gl_main_lux_threshold`, `gl_main_lux_hysteresis`,
`gl_grow_lux_threshold`, and `gl_grow_lux_hysteresis` independently, with
`cfg_*` readbacks proving the ESP32 received the values.

## Dashboard

`site-climate-lighting` now includes:

- Crop-driven target DLI from `v_lighting_daily`
- Daily DLI vs target
- Per-circuit lighting policy table from `v_lighting_circuit_status_now`
- State timeline for both grow-light circuits
- Policy window, occupancy, and sun state
- Per-circuit lighting forecast bands from `fn_lighting_timeline()`

`site-home` now includes a lighting forecast-band graph. It overlays
observed/forecast natural lux with the main and grow circuit ON/OFF lux bands,
plus expected-on markers. This mirrors the temperature/VPD band graphs without
pretending every internal setpoint should be drawn as a separate line.

## OTA Status

The lighting firmware OTA was completed on 2026-05-16 under Jason's explicit
operator request to bypass the deployment gate. The final accepted firmware is:

- `2026.5.16.1723.c9b842b.dirty`

The bypass covered the 48-hour bake and weekly OTA deployment gates. The final
preflight had no unresolved critical/legacy-high alerts, but still had the expected
hot-weather warning and the policy bake/week gates that were intentionally
overridden. The OTA uploaded successfully, diagnostics reported the expected
firmware version, and the post-deploy sensor health sweep reported `27` pass,
`0` fail, `0` warn.

Two deployment issues were found and fixed during the OTA sequence:

- Firmware initially published blank lighting state/reason fields when SNTP was
  invalid. The deployed fix uses Home Assistant controller time under the
  existing firmware time id and fails lights closed if time is unavailable.
- Reconnect/direct-push bursts contributed to ESP32 heap pressure during early
  OTA attempts. `ingestor/esp32_push.py` now paces direct pushes more slowly.
  The open `heap_pressure_critical` alert auto-resolved through the alert
  monitor after the final firmware showed healthy heap samples and no new heap
  pressure logs.

Post-OTA direct ESPHome API proof:

- `last_boot='2026-05-16 17:24:23'`
- `gl_main_state='OFF'`, `gl_main_reason='lux_sufficient'`
- `gl_grow_state='OFF'`, `gl_grow_reason='lux_sufficient'`

Latest lighting status proof showed both circuits `expected_on=false`,
`actual_on=false`, natural lux around `60k`, and ON/OFF thresholds of
`40000/48000 lux`.

## Completion Audit

Objective restated as concrete criteria:

1. Lighting automation has no remaining obvious traceability gaps across
   planner tunables, dispatcher/API delivery, firmware enforcement, Lutron
   switching, telemetry, dashboards, and public page copy.
2. Tempest light evidence drives the natural-light trigger bands.
3. Main and grow light circuits are represented separately where the
   implementation treats them separately.
4. Public graphs tell the same story as the implementation without rendering
   every internal setpoint line.
5. Any deployment bypass or residual risk is identified explicitly instead of
   being hidden behind passing tests.

Prompt-to-artifact checklist:

| Requirement | Evidence | Status |
|---|---|---|
| Same state-machine approach as climate, implemented in firmware source | `LightingInputs`, `LightingSetpoints`, `LightingState`, and `evaluate_lighting()` in `firmware/lib/greenhouse_types.h` and `firmware/lib/greenhouse_logic.h`; ESPHome uses separate `gl_main_state` and `gl_grow_state` in `firmware/greenhouse/controls.yaml` | Live on firmware `2026.5.16.1723.c9b842b.dirty` |
| Each light has identical but separate tunables | `gl_main_*`, `gl_grow_*`, `sw_gl_main_auto_mode`, and `sw_gl_grow_auto_mode` in firmware globals/tunables/readbacks, `verdify_schemas/tunable_registry.py`, `verdify_schemas/tunables.py`, and `ingestor/entity_map.py` | Live with post-OTA `cfg_*` readbacks |
| Per-circuit tunables have the right planner ownership | The audit imports `verdify_schemas.tunable_registry.REGISTRY` and verifies all per-circuit lighting params are planner-owned, MCP-pushable Tier 2 tunables with cfg readbacks | Static registry contract |
| Legacy shared lighting knobs cannot drift back into planner writes | The audit verifies shared `gl_lux_threshold` / `gl_lux_hysteresis` are dispatcher/default context, not in `PLANNER_PUSHABLE_REG`; Iris writes per-circuit `gl_main_*` and `gl_grow_*` knobs instead | Static registry contract |
| Planner can manage each light independently | `make lighting-audit-current` runs `scripts/gather-plan-context.sh` and verifies the live prompt context contains `grow|grow_light_grow`, `main|grow_light_main`, Tempest threshold evidence, and per-circuit `gl_main_*` / `gl_grow_*` guidance; `verdify-mcp.service` restarted after schema changes | Live planner context |
| MCP write gate accepts only the right lighting knobs | `make lighting-audit-current` dry-runs `set_tunable` with a fake `trigger_id`: per-circuit `gl_main_lux_threshold` and `sw_gl_main_auto_mode` pass the allowlist and stop at the trigger-ledger gate, while legacy `gl_lux_threshold` is rejected as not planner-pushable | Live no-write MCP proof |
| Dispatcher/API/setpoint surfaces align | `ingestor/tasks.py`, `api/main.py`, and `scripts/setpoint-server.py` all call `fn_lighting_circuit_policy()`; API container rebuilt; `verdify-setpoint-server.service` restarted | Live |
| Unsupported-push guard handles firmware transition safely | Before OTA, dispatcher withheld per-circuit pushes until readbacks existed; after OTA, per-circuit `cfg_*` readbacks are live and setpoint confirmations are proven | Live guard verified |
| Tempest is the trigger evidence | `fn_lighting_lux_threshold_recommendation()` used 21,106 daylight samples; recommended `40000 lux` ON threshold and `8000 lux` hysteresis; per-circuit policy uses `40000/48000 lux` ON/OFF bands | Live |
| On/off state tracked separately | Lutron entities are `switch.greenhouse_main` and `switch.greenhouse_grow`; pre-OTA and post-OTA live tests recorded ON/OFF `equipment_state` rows for `grow_light_main` and `grow_light_grow` | Live for Lutron/API path |
| Enforcement uses the real Lutron switch path | The audit verifies `scripts/setpoint-server.py`, `scripts/ha-sensor-sync.py`, and `ingestor/tasks.py` use `switch.greenhouse_main` / `switch.greenhouse_grow` and do not use stale `light.greenhouse_*` wrappers | Static enforcement contract |
| Policy/status tracked separately | `v_lighting_circuit_status_now` returns one row per circuit with expected/actual state, natural lux, ON/OFF lux thresholds, and firmware state/reason columns | Live; firmware columns populated post-OTA |
| Forecast graph mirrors temp/VPD band approach | `site-home` panel `36` and `site-climate-lighting` panel `17` query `fn_lighting_timeline()` for observed/forecast natural lux, ON/OFF bands, and expected-on markers | Live Grafana |
| Forecast graph labels match enforcement semantics | The audit verifies user-facing graph series for `Tempest/Forecast Lux`, main/grow `ON` and `OFF` thresholds, main/grow expected-on markers, and `custom.fillBelowTo` shaded hysteresis bands | Static dashboard contract |
| Public graph renderer returns real images | `make lighting-audit-current` requests PNG renders for `site-home` panel `36` and `site-climate-lighting` panels `16` and `17` from `graphs.verdify.ai/render/d-solo/...` and verifies HTTP 200 PNG payloads | Live Grafana renderer |
| Public website serves the updated story | `make lighting-audit-current` fetches `https://verdify.ai/`, `/greenhouse/lighting/`, and `/reference/ai-tunables/`, then verifies the home lighting forecast embed, lighting page per-circuit policy copy plus panels `16`/`17`, and AI Tunables writeability labels for per-circuit vs legacy shared lighting knobs | Live public website |
| Forecast graph is fast enough for homepage use | Migration `124-lighting-timeline-performance.sql` resolves per-circuit policy once per graph query instead of once per bucket; 36-hour/30-minute aggregate measured about `3.3s` after optimization instead of about `77s` before | Live |
| Lighting page tells the implementation story | `/greenhouse/lighting` now includes "Circuit Policy And Forecast Bands" and embeds `site-climate-lighting` panels `16` and `17`; rebuilt HTML contains both embeds | Live site output |
| Legacy lighting dashboards do not contradict per-circuit implementation | `greenhouse-lighting` now labels "Main Light Circuit", "Lutron Circuit State", "Lighting Decision Context", and "Daily Lutron Circuit Runtime"; runtime uses `v_lighting_daily` main/grow circuit columns | Live Grafana after restart |
| Repeatable proof gate exists | `make lighting-audit-static` reports `23` pass; post-OTA `make lighting-audit-current` reports `47` pass and only the expected 48-hour bake policy blocker; `make lighting-audit-complete` reports `48` pass when run under the same explicit operator bypass used for deployment | Verified post-OTA |
| Validation gates cover code and dashboards | `make test-firmware`: 137 passed; `make firmware-check`: compiled; `make firmware-invariants`: 16 invariants passed over 193,525 rows; `make firmware-replay-worktree`: 0 divergent rows over 193,525 rows; `scripts/audit-tunable-traceability.py`: OK with 37 required Tier 1 planner params and 53 MCP-writable planner-policy params; `make lint`: passed; `make test`: 390 passed, 2 skipped, 1 xfailed; `make site-doctor`: 0 errors, 2 stale snapshot warnings unrelated to lighting | Verified |
| OTA safety gate outcome | Normal preflight still reports the expected 48-hour bake blocker, but Jason explicitly requested a deployment-gate bypass; the accepted OTA kept rollback artifacts intact, passed sensor health, and now has zero open critical/legacy-high alerts | Operator-bypassed; post-OTA proof complete |

Current conclusion: the lighting automation path is live end to end. The normal
48-hour bake policy is still in effect for future OTAs, but this deployment was
completed under explicit operator override and then validated with the final
post-OTA proof gate. The final proof requires per-circuit cfg readbacks,
confirmed per-circuit `setpoint_changes`, firmware state/reason telemetry, and
ON/OFF `equipment_state` evidence for both Lutron circuits after the latest
firmware start; all of those checks passed on firmware
`2026.5.16.1723.c9b842b.dirty`.
