---
title: ESP32 Controller
tags: [climate, firmware, esp32, state-machine]
date: 2026-04-07
type: reference
states_total: 42
temp_states: 6
humidity_states: 7
eval_interval_seconds: 5
esphome_version: 2026.3.0
aliases:

  - platform/controller
board: esp32dev
framework: esp-idf
entities: 198
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# ESP32 Controller

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 1.5rem 0;">

![Verdify control center: KinCony relay board in its enclosure with development laptop below for live commissioning](/static/photos/control-center-laptop.jpg)

![Interior of the KinCony relay board showing 16-channel relay terminals, DIN-rail breaker, transformer, and color-coded wiring](/static/photos/kincony-relay-closeup.jpg)

</div>
ESPHome 2026.3.0 on a Kincony KC868-E16P board. 198 entities across sensors, relays, switches, tunables, and diagnostics. The ESP32 evaluates two independent axes — **temperature** (6 states) and **humidity** (7 states) — every 5 seconds, producing **42 possible state combinations**. Each maps to a specific relay pattern.

## Hardware Health

<div class="pg s5" style="grid-template-columns: repeat(6, 1fr) !important;">

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=10&theme=dark" width="100%" height="120" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=11&theme=dark" width="100%" height="120" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=12&theme=dark" width="100%" height="120" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=13&theme=dark" width="100%" height="120" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=14&theme=dark" width="100%" height="120" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=15&theme=dark" width="100%" height="120" frameborder="0"></iframe>

</div>
WiFi signal strength, free heap memory, uptime since last reboot, enclosure case temperature, 30-day reboot count, and last reset reason. Case temperature correlates with solar irradiance — the enclosure is in the north zone near the house wall, buffered from direct sun, but ambient air temperature inside the greenhouse still drives it above 100°F on peak days.

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=16&theme=dark&from=now-30d&to=now" width="100%" height="280" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=17&theme=dark&from=now-30d&to=now" width="100%" height="280" frameborder="0"></iframe>

</div>
30-day hardware trends. Left: heap memory and WiFi RSSI over time — heap drops indicate memory fragmentation, drops to zero mark reboots. Right: case temperature and uptime — uptime resets at each reboot. Annotations mark reboot events. A healthy ESP32 shows stable heap above 40KB and WiFi above -70 dBm.

## State Machine

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=19&theme=dark" width="100%" height="250" frameborder="0"></iframe></div>

<div class="grafana-controls" data-mode="none"></div>
The state timeline above shows the controller's combined temperature × humidity state over the last 24 hours. Each color represents a different state combination — green bands are TEMP_IDLE (comfortable), blue/purple are cooling stages with mister activity, red would indicate heating. The pattern reveals the daily cycle: heating at night, idle through morning, escalating cooling stages as solar gain builds through the afternoon, then back to idle at sunset.

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=24&theme=dark" width="100%" height="280" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=25&theme=dark" width="100%" height="280" frameborder="0"></iframe>

</div>
Left: hourly state transition rate — high transition rates indicate the controller is hunting between states (oscillating). A well-tuned system shows smooth transitions, not rapid toggling. Right: state distribution pie — how the controller spends its time across states. A healthy greenhouse in spring should show mostly TEMP_IDLE + COOL stages, with humidity states active during peak VPD hours.

## Firmware Structure

| File | Lines | Content |
|------|-------|---------|
| `greenhouse.yaml` | 380 | Top-level: WiFi, SNTP, MQTT, buttons |
| `hardware.yaml` | 292 | I²C, UART, Modbus, relay definitions |
| `sensors.yaml` | 1,202 | All sensors, derived metrics, DLI accumulator |
| `globals.yaml` | 584 | State variables, setpoints, counters |
| `controls.yaml` | 1,050 | Climate + irrigation + mister state machines |
| `tunables.yaml` | 851 | HA number/switch/button entities (57 numbers, 8 switches) |

## Three-Layer Control Architecture
The greenhouse uses three layers of control, each with a distinct role:
1. **Crop Target Band** (plant science, automatic). Computed from diurnal profiles of all five active crops (lettuce, pepper, strawberry, basil, vanda orchid) with smooth hour-by-hour interpolation. The band sets temp_low, temp_high, vpd_low, vpd_high every 5 minutes. Night: 62-65F. Peak day: 72-78F. These are the ESP32's triggers.
2. **AI Planner** (tactical, Gemini 3.1 Pro). Runs 3x/day. Reads the 72-hour weather forecast and the crop band, then chooses how aggressively the controller should chase the band: hysteresis widths, mister timing, fan staging thresholds, water budgets. The planner can also tighten the targets within the band on mild days.
3. **ESP32 State Machine** (enforcement, every 5 seconds). Evaluates the band setpoints + tactical parameters and drives relay patterns. If the AI goes offline, the ESP32 holds its last setpoints and runs autonomously.

## Temperature States
The trigger values are not static. They follow the crop band, which shifts with the sun.

| State | Condition | Equipment |
|-------|-----------|-----------|
| HEAT_S2 | temp < temp_low - d_heat_stage_2 | Heat1 + Heat2 (gas) |
| HEAT_S1 | temp < temp_low | Heat1 (electric) |
| TEMP_IDLE | temp_low ≤ temp ≤ temp_high | Nothing |
| COOL_S1 | temp > temp_high | Fan1 (lead) + vent |
| COOL_S2 | temp > temp_high + d_cool_s2 | Both fans + vent |
| COOL_S3 | temp > safety_max | Emergency + evaporative fog |
At night, temp_low is 62F and temp_high is 65F. By midday, temp_low rises to 72F and temp_high to 78F. The state machine follows the band automatically.

## Humidity States (Per-Zone VPD Targeting)
Each mister zone has its own VPD target from the crops planted there. The state machine uses a stress score to decide which zone to mist: `(actual VPD - zone target) / zone target`. The zone with the highest stress gets the next pulse. East has a VPD sensor but no mister, so its stress boosts the misting urgency of adjacent zones (south and center).

| Zone | Crops | VPD Target | Mister |
|------|-------|-----------|--------|
| East | lettuce, strawberry, pepper starts | 0.98 (tightest) | No mister, boosts neighbors |
| Center | Vanda Orchids | 0.85 | Yes, with 0.5x sensor penalty |
| South | Canna Lilies | 1.57 | Yes |
| West | House plants | 1.20 (default) | Yes |
Misters first, fog as escalation. When the vent is open, dry outdoor air negates mist pulses. The `sw_mister_closes_vent` flag can close the vent during active pulses to trap humidity.

| State | Condition | Equipment |
|-------|-----------|-----------|
| HUM_IDLE | All zones in-band | Nothing |
| DEHUM | VPD < vpd_low | Vent opens |
| HUMID_S1 | avg VPD > engage threshold | Mister pulse on most-stressed zone |
| HUMID_S2 | S1 sustained, VPD still high | Stress-proportional all-zone rotation |
| HUMID_S3 | Misters can't control VPD | FOG (1,644W, vent closes) |

## Control Loop Performance

<div class="pg s2"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=14&theme=dark" width="100%" height="320" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=15&theme=dark" width="100%" height="320" frameborder="0"></iframe></div>
Temperature (left) and VPD (right) vs their setpoint bands. The green observed line should track within the dashed setpoint boundaries. Excursions outside the band indicate either physics limitations (solar overshoot that the cooling system can't reject) or setpoint tracking issues. The controller can reject ~40% of peak solar heat gain — the remaining 60% requires shade cloth.

<div class="pg s2"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=10&theme=dark" width="100%" height="320" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=11&theme=dark" width="100%" height="250" frameborder="0"></iframe></div>
Left: enthalpy delta (indoor vs outdoor) — drives the economiser decision. When outdoor enthalpy is lower (delta positive), the vent opens for free cooling. Right: economiser activity timeline — ON/OFF periods for the enthalpy gate.

## Mister Pulse Model
```
S1: Pick most-stressed zone (stress score = (VPD - target) / target)
    → mister_pulse_on_s (60s) burst
    → mister_pulse_gap_s (45s) gap
    → re-read VPDs
    → repeat
S2: Rotate all 3 zones
    → driest zone gets mister_vpd_weight (1.5×) burst
    → 30s gaps between zones
    → re-rank each rotation
```
**Hard rule:** Never more than one mister zone simultaneously (water pressure constraint).

## AI Planning System

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=10&theme=dark&from=now-30d&to=now" width="100%" height="280" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=12&theme=dark&from=now-30d&to=now" width="100%" height="280" frameborder="0"></iframe>

</div>
Three times a day, the planner reads 14 sections of context: current conditions, equipment state, 24-hour history, stress hours, 72-hour weather forecast, the crop target band for the next 72 hours, active crops, validated lessons, the previous plan, disease risk, and DIF. It generates a tactical plan: misting strategy, fan staging thresholds, hysteresis widths, and grow light schedules. The crop band sets what the ESP32 targets. The planner decides how hard it tries.
Left: plan outcome scores over 30 days (0–10 scale, self-assessed by the planner on the next cycle). The trend shows whether the AI is learning. Right: forecast temperature bias — systematic error between what the weather forecast predicted and what actually happened. A persistent bias means the planner should compensate.

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=5&theme=dark" width="100%" height="280" frameborder="0"></iframe></div>
Recent plan history table — each plan's timestamp, parameters changed, outcome score, and what the planner was thinking. This is the audit trail for every AI decision that affects the greenhouse.

## Setpoint Pipeline Health

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=14&theme=dark" width="100%" height="280" frameborder="0"></iframe></div>
Setpoint write rate and oscillation count per hour. In a healthy system, writes happen at the dispatcher interval (every 5 minutes) and oscillations are near zero. Spikes in the oscillation line indicate parameters fighting between the push and pull paths — the signature of the dual-name bug that was discovered 2026-03-29 and is being fixed.

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-controller/?orgId=1&panelId=45&theme=dark" width="100%" height="280" frameborder="0"></iframe></div>
The oscillation heatmap — parameter names on the Y axis, hours on the X axis, color intensity shows how many value-flips occurred. Red cells mean a parameter is bouncing between values. This is the single most important panel for diagnosing control loop issues. A clean heatmap is all cool colors; any hot cell deserves investigation.

## Key Design Decisions
1. **ESP32 owns real-time control.** The AI adjusts setpoints (boundaries), never relay states directly. The firmware makes real-time tradeoffs at 5-second resolution.
2. **Dual-path setpoint delivery.** Push via aioesphomeapi (immediate) + pull via HTTP `/setpoints` (300s fallback). If both fail, hardcoded defaults keep the greenhouse safe.
3. **Inverted humidity hierarchy.** Misters first (cheap, targeted, work with vent open), fog as S3 escalation (expensive, vent must close). This was a significant change from the original firmware which used fog first.
4. **Pulse-rotation model.** Never more than one mister zone simultaneously. VPD-weighted burst allocation. 60s on / 45s gap is the tuned sweet spot.
5. **Autonomous safety.** Safety rails (45–95°F, 0.3–3.0 kPa VPD) override all setpoints. The controller operates independently of the AI layer.

## Safety Rails

| Parameter | Value | Purpose |
|-----------|-------|---------|
| safety_min | 45°F | Emergency heat below this |
| safety_max | 95°F | Emergency cooling above this |
| safety_vpd_min | 0.3 kPa | Emergency dehumidification |
| safety_vpd_max | 3.0 kPa | Emergency humidification |

## Autonomy
The ESP32 operates independently. If the AI planning layer (Iris) goes offline and both push and pull paths fail, the controller falls back to hardcoded default setpoints and continues managing the greenhouse. Iris makes it smarter, but it doesn't depend on Iris to survive.

<div style="margin-top: 2rem; padding: 1rem; border-left: 3px solid var(--secondary); font-size: 0.9rem;">
**Full dashboard:** <a href="https://graphs.verdify.ai/d/greenhouse-esp32-controller/" class="external">ESP32 Controller Health →</a> — hardware diagnostics, state machine analysis, planning system integrity, setpoint pipeline monitoring, data pipeline metrics, and alert history.

</div>

---

## Where to Go Next

- [Planning Loop](/intelligence/planning/) — how the AI reads sensor data and writes tactical setpoints
- [Operations](/evidence/operations/) — live system health and data pipeline status
- [What's Broken](/evidence/operations/#alerts) — current alerts and anomalies

The state machine enforces what the [planner](/intelligence/planning/) decides. The planner reads the forecast and crop band, writes tactical setpoints, and the ESP32 turns them into relay states every 5 seconds.
