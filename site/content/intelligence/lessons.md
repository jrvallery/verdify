---
title: Lessons Learned
tags:
  - greenhouse
  - planning
  - lessons
  - operations
date: 2026-04-08
aliases:
  - operations/lessons-learned
  - greenhouse/lessons
---

# Lessons Learned

Operational findings validated through hypothesis-driven planning cycles. Each was tested, measured, and confirmed before graduating here. The planner reads these as context before every tactical decision.

## Active Operational Lessons

### #1 |�|�|� Dry days need proactive misting before the VPD ramp

**Category:** Misting | **Confidence:** Medium | **Validated:** 4x

**When:** outdoor_rh < 20% AND forecast_high > 80F

On dry days, lower mister_engage_kpa to 1.3 (from 1.6) before the morning VPD ramp. Use pulse_gap 30s not 45s. Shorter gaps keep humidity from collapsing between pulses. Data: 60s pulse + 30s gap got 0.42 kPa VPD drop vs 0.12 for 55s/45s.

### #2 |�|�|� Gas heat is 3.9x more cost-effective than electric

**Category:** Heating | **Confidence:** High | **Validated:** 5x

**When:** overnight forecast < 45F

Gas heater (75K BTU, $0.623/hr) is 3.9x more cost-effective per BTU than electric (5K BTU, $0.167/hr). Electric-first staging handles mild dips. Gas handles sustained cold. The concrete slab retains 7-8F above outdoor overnight.

### #3 |�|�|� The lux sensor reads 25-40% of actual plant-available light

**Category:** Lighting | **Confidence:** High | **Validated:** 7x

LDR saturates at 28K lux. Morning tree shadow blocks until 10:18 AM. Estimated actual DLI = sensor_dli x 3.5 + grow_light_hours x 0.8. Sensor DLI of 5-7 mol corresponds to actual 17-27 mol. Do not over-schedule grow lights based on low sensor readings.

### #4 |�|�|� The greenhouse cannot cool below ambient

**Category:** Cooling | **Confidence:** High | **Validated:** 3x

**When:** forecast_high > 85F

65,000-87,000 BTU/hr peak solar gain through glazing. Cooling capacity is variable by delta-T. At 10F delta: 45,000 BTU/hr. At 3F delta: 13,500 BTU/hr. Fans cannot cool below ambient. Software cannot prevent overheating on 90F+ days. Only shade cloth fixes this. Focus on pre-cooling, aggressive misting, and accepting 5-8h of structural heat stress.

### #5 |�|�|� Overcast cold days need grow lights, not misters

**Category:** Weather response | **Confidence:** Medium | **Validated:** 1x

**When:** cloud_cover > 90% AND outdoor_temp < 60F

Full overcast below 60F produces zero VPD stress. Relax VPD settings. Focus shifts to grow light compensation for DLI. Heating cost is minimal above 44F outdoor due to slab retention.

### #6 |�|�|� Cold-dry is not the same as warm-dry

**Category:** Misting | **Confidence:** Medium | **Validated:** 2x

**When:** outdoor_temp < 55F AND outdoor_rh < 25%

Temperature is the dominant VPD driver, not humidity alone. Low RH at 45F outdoor translates to only 1.0-1.3 indoor VPD. Low RH at 70F produces 2.0+ VPD. Save aggressive misting for warm-dry days (outdoor > 60F + RH < 20%).

### #7 |�|�|� Per-zone VPD targets must match planted crops

**Category:** Control architecture | **Confidence:** New (April 8)

Each mister zone has its own VPD ceiling from its planted crops. East (lettuce/strawberry starts) has the tightest target. Center (orchids) triggers early. South (cannas) tolerates the most stress. The firmware selects the most stressed zone using `(actual - target) / target` scoring. This replaced a hardcoded center-default selection that was wasting 75% of mister pulses on the zone with no sensor and the worst effectiveness.

## Lesson Lifecycle

1. **Hypothesis** |�|�|� Planner proposes a theory during a planning cycle
2. **Test** |�|�|� Specific setpoint changes are made with measurable expected outcomes
3. **Validate** |�|�|� Next cycle scores the result and extracts findings
4. **Graduate** |�|�|� If significant, added here at confidence "low"
5. **Confirm** |�|�|� Each re-validation bumps confidence (low at 1x, medium at 3x, high at 5x)
6. **Supersede** |�|�|� If a better approach is found, old lesson is marked superseded

Several firmware safety constraints (zero-value parameter protection, dispatcher batch reliability, ESP32 reboot recovery) are documented on the [Known Issues](/intelligence/broken/) page rather than here. Those are bugs, not operational findings.

These findings feed directly into the [planning loop](/intelligence/planning/) as mandatory context. The planner reads every graduated lesson before writing its next plan.
