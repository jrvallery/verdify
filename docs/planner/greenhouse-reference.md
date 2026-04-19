# Greenhouse Operational Reference

## Physical

- 367 sq ft, elongated hexagon, 3,614 cu ft volume, peak 143" ceiling
- Elevation: 5,090 ft (Longmont, CO, 40.17°N). 17% less air density than sea level.
- Glazing: 6mm opal polycarbonate, SHGC 0.66, diffuses all direct light
- Glazed surface area: ~1,050 ft² (walls + roof, surface-to-floor ratio ~3.0)
- Solar gain: ~87,000 BTU/hr peak (validated — conservative, roof alone ~81K)
- Fan cooling (actual): ~34,000-39,000 BTU/hr (altitude-derated + intake-restricted)
- Fan cooling (nameplate): 52,900 BTU/hr — overstated ~40% due to altitude + vent restriction
- Cooling deficit: ~49,000-53,000 BTU/hr on peak days → 107-112°F indoor on 90°F outdoor
- Intake vent: single 24"x24" (4 sq ft) — critically undersized for 4,900 CFM (2x industry max velocity)

## Zones

| Zone | Character | Crops | Mister | Notes |
|------|-----------|-------|--------|-------|
| South | Hottest, exhaust fans, hex taper | Canna lilies (floor) | 6 heads, 30 nozzles, 0.23 kPa drop/pulse | Primary misting zone |
| West | Longest wall (22'5"), afternoon sun | Shelves (herbs, starts) | 3 heads, 15 nozzles, 0.15 kPa drop/pulse | Secondary misting |
| East | Coolest, tree shade until 10:18 AM | Hydro NFT (lettuce, pepper, strawberry) | NONE | Stress boosts south/center via 0.3x adjacency |
| Center | Mixing zone, fog machine location | Vanda orchids (hanging) | 5 heads, 0.04 kPa drop/pulse (weak) | Deprioritized (penalty 0.8) |
| North | Equipment buffer, thermally stable | None | None | Manifold, sink, controller, heater |

## Equipment

| Device | Capacity | Control |
|--------|----------|---------|
| Fan 1 (SW) | 2,450 CFM, 52W | COOL_S1 (lead rotation every 600s) |
| Fan 2 (SE) | 2,450 CFM, 52W | COOL_S1 (lag) or COOL_S2 (both) |
| Heater 1 (electric) | 1,500W | HEAT_S1 (pre-heat inside band) |
| Heater 2 (gas/Lennox) | 75,000 BTU/hr nameplate, ~48,000-54,000 actual (altitude derated 20%) | HEAT_S2 (below band floor). Overshoot: ~1-2°F typical |
| AquaFog XE 2000 | ~750-850W, centrifugal atomizer (4-25µm droplets, ~90% evap efficiency) | HUMID_S3 (fog escalation, vent forced closed). Max 15.8 GPH (0.26 GPM). |
| Intake vent (north) | 24"x24" (4 sq ft) — critically undersized, needs 2-3x more area | Economiser logic (enthalpy gate) |
| Grow lights (main) | 630W, 15x4FT LED | DLI-based automation |
| Grow lights (shelf) | 816W, 15x2FT LED | DLI-based automation |

## Mode Controller (7 priority-ordered modes)

SENSOR_FAULT → SAFETY_COOL → SAFETY_HEAT → SEALED_MIST → THERMAL_RELIEF → VENTILATE → DEHUM_VENT → IDLE

Key thresholds:
- SAFETY_HEAT at 35°F, SAFETY_COOL at 100°F
- SEALED_MIST when VPD > vpd_high (after vpd_watch_dwell_s observation)
- VENTILATE when temp > temp_high + bias_cool
- THERMAL_RELIEF after mist_max_closed_vent_s sealed
- Mist stages within SEALED_MIST: WATCH → S1 → S2 → FOG

## Utility Rates

- Electric: $0.111/kWh
- Gas: $0.83/therm (100,000 BTU)
- Water: $0.00484/gal
- Gas heat is 3.9x more cost-effective per BTU than electric

## Water System

- 1 GPM per zone (water pressure limits to one zone at a time)
- Warm water (86°F from Rinnai tankless) aids evaporation
- At 15% outdoor RH, evaporation is near-instant (gap can be very short)

## Key Physics

- VPD rises with solar load and ventilation (dry outside air at 5,090 ft)
- Closing vent during HUMID retains humidity but traps heat
- Fog + fans = evaporative cooling (phase change absorbs heat)
- At 85°F/15% RH outdoor: open-vent misting achieves only 52-61% RH (VPD 1.6-2.0 kPa) — still above target
- Sealed-vent misting can reach 70-85% RH in 2-5 min, but heat builds without ventilation
- Above ~85°F, heat stress is engineering-limited (addressable with shade cloth + fan-and-pad), not physics-limited
- Wet-bulb depression at 5,090ft/15% RH reaches ~31°F — evaporative cooling is exceptionally powerful here
- Slab thermal mass: ~7,300 BTU/°F effective (slab + sub-slab soil), time constant ~11.5h, provides 7-10°F overnight retention
- Air exchange at 4,900 CFM: full volume replaced every 44 seconds
