---
title: What's Broken
tags: [intelligence, issues, honesty]
date: 2026-04-07
---

# What's Broken

Every system has problems. Here are ours.

## The Lux Sensor Lies

The LDR on GPIO35 saturates at ~28,000 lux. A sunny day in Colorado pushes well past 100,000 lux outdoors, so the sensor clips all day. Worse, the sensor is positioned where a tree shadows it until 10:18 AM, so it misses the first four hours of useful morning light. And it can't see the grow lights at all (below its noise floor).

The reported DLI is 5-7 mol/m2/day. The actual plant DLI is 17-27 mol. The sensor is wrong by 3-4x. A BH1750 digital lux sensor costs $3-5 and would fix this. We haven't installed one yet.

The planner knows the sensor lies and applies a correction factor. But it's a workaround, not a fix.

## The Center Mister Zone Underperforms (Partially Fixed)

South misters: 0.15 kPa VPD drop per pulse. West: 0.13 kPa. Center: 0.04 kPa. The center zone is nearly useless for humidity management, which is probably a nozzle alignment or water pressure geometry problem.

**Root cause found (April 8):** The firmware's zone selection logic had a hardcoded fallback to center. Center (with no VPD sensor) was getting 75% of all mister pulses despite being the least effective zone. South and west (which have sensors and work 3-4x better) were starved.

**Fix deployed:** The firmware now uses per-zone VPD targets from the planted crops, with a stress-score algorithm that picks the most stressed zone. Center gets a 0.5x penalty because it has no dedicated sensor. Zone targets: east=0.98 (lettuce/strawberry), center=0.85 (orchids), south=1.37 (cannas), west=1.20 (default). The nozzle geometry problem remains, but center now gets pulses proportional to its crop's needs, not as a default fallback.

## The Dispatcher Drops Parameters

When the setpoint dispatcher pushes a batch of parameter changes to the ESP32 via aioesphomeapi, it sometimes silently fails to deliver some of them. On April 5, after a reboot, `temp_low`, `vpd_high`, and `vpd_hysteresis` all read 0 on the controller while the dispatcher thought they were set. `temp_low=0` means the heaters never fire. `vpd_high=0` means misting never stops.

The workaround is verification after every dispatch (read back and retry). The root cause is in the aioesphomeapi batch write path. It's been observed 5+ times.

## No Shade Cloth

The single most impactful physical improvement. 65,000-87,000 BTU/hr of solar gain through ~785 sq ft of glazing. The fans max out at ~45,000 BTU/hr on a 10F delta. On a 95F day, equilibrium interior temperature will be 105-115F regardless of what the software does.

External shade cloth on the roof and WSW wall (30-50% shade factor) would cut solar gain by 30-50% while blocking proportionally more heat than useful light (SHGC 0.66 > LT 0.57). Estimated cost: $50-200. We don't have it yet.

## The Intake Probe is Offline

Modbus address 6, the exterior intake probe, has been disconnected or failed since February 23, 2026. This means no direct measurement of intake air temperature and humidity. The firmware works around it by pulling Tempest weather station data via the /setpoints HTTP endpoint, but it's a fallback, not a primary measurement.

## The Grow Light Sensor Can't See Grow Lights

The lux sensor (LDR on GPIO35) operates below the threshold where it can detect the Barrina LED fixtures. So the DLI automation (`gl_auto_mode`) effectively runs open-loop. It triggers based on outdoor light falling below a 3,000 lux threshold (which happens to correlate with the tree shadow clearing). The system works by accident, not by design.

## ESP32 Reboots Spike in March

March 2026 saw 111 controller reboots vs 5 in February. The cause hasn't been identified. Each reboot resets all setpoint parameters to firmware defaults, which means the dispatcher has to re-push everything. Combined with the batch delivery bug, reboots can leave the greenhouse running on wrong setpoints for up to 5 minutes.

## Firmware Safety Constraints

These are not lessons |â|€|” they are bugs that require defensive coding:

**Zero-value parameter protection.** If temp_low, vpd_high, or mister_water_budget_gal are set to 0 (via dispatcher failure or ESP32 reboot), the results are catastrophic: heating disabled, misting disabled, or VPD stress accounting corrupted. The dispatcher now verifies non-zero values after every push.

**Dispatcher batch delivery.** The aioesphomeapi batch write path sometimes silently drops parameters. Observed 5+ times. The workaround is read-back verification after each dispatch cycle.

**ESP32 reboot recovery.** March 2026 saw 111 reboots. Each resets setpoints to firmware defaults. The firmware defaults for temp_low/temp_high should be crop-safe values (62/78), not the old planner defaults (55/82). This firmware change is pending.

## Known and Accepted

The planner knows about each of these and compensates where it can. The lux sensor, shade cloth, and dispatcher reliability remain the three highest-priority improvements.

â|†|’ See [Lessons Learned](/intelligence/lessons/) for validated operational findings
â|†|’ See [The Planning Loop](/intelligence/planning/) for how the planner works around these issues
