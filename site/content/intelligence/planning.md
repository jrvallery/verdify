---
title: The Planning Loop
tags: [intelligence, planning, ai, gemini]
date: 2026-04-07
type: reference
planning_frequency: "3x daily (6AM, 12PM, 6PM MDT)"
core_parameters: 10
aliases:

  - platform/planning
  - platform/intelligence
  - platform/openclaw
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# The Planning Loop

![Verdify control center: KinCony relay board above a development laptop, where plans become physical relay states](/static/photos/control-center-laptop.jpg)
Three times a day, Gemini 3.1 Pro reads 14 sections of context and writes a 72-hour tactical plan. It does not choose what the greenhouse should target. The crop target band handles that, computed from the diurnal profiles of five active crops with smooth hour-by-hour interpolation. The planner chooses how aggressively the controller should chase those targets given the weather forecast.
Each plan is a hypothesis. The system measures what happened, scores the result, and extracts lessons when predictions diverge from reality.

## The Closed Loop
```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   GATHER          VALIDATE         REASON          PLAN          LEARN  │
│                                                                         │
│   14 sections     Score previous   Check lessons   Tactical      Score  │
│   of context      plan 1-10        against today   waypoints     this   │
│   from sensors,   Extract lesson   Reason across   for response  plan   │
│   forecast,       if unexpected    temp, VPD,      tuning +      next   │
│   crop band       happened         misting, cost   band tighten  cycle  │
│                                                                         │
│   ────────────────────────────────────────────────────────────────────>  │
│                                                                         │
│   Every 5 min:    ESP32 executes   42 states ×     Equipment     Data   │
│   Dispatcher      plan via         5-second        transitions   flows  │
│   pushes to       relay patterns   eval loop       logged to DB  back   │
│   ESP32                                                                 │
│                                                                         │
└──────────────────────────── repeats every 6 hours ──────────────────────┘
```

<div class="grafana-controls" data-ranges="7d,30d,60d"></div>

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-intelligence-planning/?orgId=1&panelId=10&theme=dark&from=now-30d&to=now" width="100%" height="280" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-intelligence-planning/?orgId=1&panelId=5&theme=dark" width="100%" height="280" frameborder="0"></iframe>

</div>
Left: plan outcome scores over 30 days — each dot is a cycle's self-assessment. Right: recent plan history with hypotheses and outcomes.

## Step 0: Validate the Previous Plan
Before writing anything new, the planner reviews what happened since its last plan. It reads the `plan_journal` entry — hypothesis, experiment, expected outcome — then checks actual data: stress hours, zone temperatures, VPD compliance, equipment runtimes, water usage. It scores the plan 1–10.
If something unexpected happened, the planner extracts a **lesson**. Lessons accumulate in the `planner_lessons` table with confidence that increases each time the pattern is re-confirmed. This is how the system gets smarter — it learns from being wrong.

## Step 1: Gather Context
The planner assembles 14 sections of structured context from the database:

| # | Section | Data |
|---|---------|------|
| 1 | Current conditions | All zone temps, VPDs, humidity, CO2, lux, outdoor weather |
| 2 | Greenhouse state | Current state machine state (IDLE, COOL_S1, etc.) |
| 3 | Equipment | All relays on/off |
| 4 | Active setpoints | Every tunable's current value on the ESP32 |
| 5 | 24h hourly pattern | Yesterday's temp/vpd/rh/outdoor by hour |
| 6 | Stress today | Hours of heat, cold, and VPD stress |
| 7 | 72h weather forecast | Outdoor temp, RH, VPD, solar radiation, cloud cover, wind |
| 8 | Crop target band | The band setpoints for every hour of the next 72 hours |
| 9 | Active crops | Name, zone, growth stage, VPD targets, 7-day health score |
| 10 | Validated lessons | Every pattern the system has learned, with confidence levels |
| 11 | Previous plan | The current active waypoints |
| 12 | Disease risk | Latest Botrytis/powdery mildew assessment |
| 13 | DIF | Day-night temperature differential |
The crop target band (section 8) is the key addition. The planner sees exactly what the ESP32 will be targeting at each hour. It can then plan tactics around those targets: pre-cool before a solar peak, increase misting before a dry afternoon, widen hysteresis when the band is narrow and physics makes it hard to hold.

## Step 2: Reason Across All Systems
The planner doesn't optimize one variable. It reasons across seven interconnected systems simultaneously:

- **Temperature** — The south zone runs 9°F hotter than east at peak. temp_high applies to the average, so south is already in COOL_S2 when the average hits threshold.
- **VPD** — On a 14% RH day, the system fights VPD stress for 8+ hours. Lowering vpd_high means misters engage earlier — more water, more humidity, less plant stress.
- **Misting** — 60-second pulses with 45-second gaps is the tuned sweet spot. Higher VPD weight concentrates water on the driest zone.
- **Economiser** — When outdoor enthalpy is lower than indoor, the vent opens for free cooling. The planner understands enthalpy dynamics when planning ventilation strategy.
- **Grow lights** — Two circuits (816W + 630W) supplement natural DLI. The planner adjusts the lux threshold based on the DLI forecast.
- **Irrigation** — Misting serves dual purpose: humidity control AND irrigation via foliar absorption.
- **Cost** — Electric heat costs 3.9× more per BTU than gas. Running fog during solar production is free; at midnight it costs $0.18/hour.

## Step 3: Write the Plan
The planner controls two categories of parameters:
**Target tightening** (optional, clamped to crop band):
The crop band sets the outer envelope (e.g., temp 72-78F at midday). The planner can tighten within the band on mild days. If it sets temp_high=75, the ESP32 targets 75 instead of 78. On extreme days, it leaves these alone and the band edges are used. Values are always clamped to the band. The planner cannot exceed crop science limits.
**Tactical parameters** (the planner's main output):

| Parameter | What it controls |
|-----------|-----------------|
| `vpd_hysteresis` | Dead band around VPD target (0.1-0.4 kPa) |
| `temp_hysteresis` | Dead band around temp target (1-3F) |
| `d_cool_stage_2` | Delta for second cooling stage (2-5F) |
| `mister_engage_kpa` | VPD threshold for first mister zone |
| `mister_pulse_on_s` | Mister burst duration (30-90s) |
| `mister_pulse_gap_s` | Pause between bursts (30-120s) |
| `mister_water_budget_gal` | Daily water budget (10-500 gal) |
| `fog_burst_min` | Fog cycle duration (1-10 min) |
| `min_fan_on_s` / `min_fan_off_s` | Fan cycling limits |
| `min_heat_on_s` / `min_heat_off_s` | Heater cycling limits |
| `sw_economiser_enabled` | Enthalpy-based ventilation on/off |
A typical plan has 8-16 waypoints at natural breakpoints: pre-dawn, dawn, morning ramp, solar noon, afternoon peak, decline, evening, night. Each new plan atomically replaces all future waypoints from previous plans.

## Step 4: Journal the Hypothesis
Every plan writes a structured journal entry: what the world looks like, what the planner thinks will happen, one specific experiment being tested, and a measurable expected outcome. The next cycle validates the hypothesis and scores the result.
This isn't logging for debugging. It's the experimental protocol that turns each cycle into a learning opportunity.

## Step 5: Dispatch to the ESP32
The dispatcher runs every 5 minutes inside the ingestor service. It reads the active plan, compares each value to what the ESP32 currently reports, and pushes only changed values via aioesphomeapi (encrypted, immediate). The ESP32 also pulls `/setpoints` via HTTP every 5 minutes as a fallback.
Between dispatches, the ESP32 runs completely autonomously. If the AI layer goes offline, the controller keeps the last setpoints.

## The Learning System

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-intelligence-planning/?orgId=1&panelId=12&theme=dark&from=now-30d&to=now" width="100%" height="280" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-intelligence-planning/?orgId=1&panelId=14&theme=dark" width="100%" height="280" frameborder="0"></iframe>

</div>
Left: forecast temperature bias over 30 days. Right: setpoint write rate and oscillation count.
Confidence levels:

- **Low:** First observation. Might be coincidence.
- **Medium:** Confirmed 2+ times under similar conditions.
- **High:** Validated 5+ times. Mandatory unless conditions clearly differ.
The planner must check every active lesson before finalizing a plan. See [Lessons Learned](/intelligence/lessons/) for the full list.

## Planning Goals (Priority Order)
1. **Minimize VPD stress hours** — plant transpiration balance
2. **Minimize heat stress hours** — physics-limited by cooling capacity
3. **Maximize DLI** — daily light integral for growth
4. **Minimize water usage** — misting water isn't free
5. **Minimize energy cost** — $0.111/kWh, $0.83/therm, $0.00484/gal
6. **Maintain positive DIF** — 8–15°F day warmer than night
7. **Maximize compliance %** — time within setpoint bands
These are ordered. The planner will spend water and energy to reduce VPD stress. It won't sacrifice plant health for a lower utility bill.

## Control Loop Performance

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-intelligence-planning/?orgId=1&panelId=7&theme=dark" width="100%" height="320" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-intelligence-planning/?orgId=1&panelId=8&theme=dark" width="100%" height="320" frameborder="0"></iframe>

</div>
Temperature (left) and VPD (right) vs setpoint bands. Where the line tracks the plan, the system is in control. Where it diverges — typically on hot, dry spring afternoons — the greenhouse has hit a physics limit. The planner knows this. It optimizes for minimal stress, not zero stress.
---

**Full dashboards:** [ESP32 Controller Health ↗](https://graphs.verdify.ai/d/greenhouse-esp32-controller/) · [Control Loop Performance ↗](https://graphs.verdify.ai/d/greenhouse-control-loop/)
