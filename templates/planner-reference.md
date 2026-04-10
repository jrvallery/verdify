# Greenhouse Operational Reference

## Physical

- 367 sq ft, elongated hexagon, 3,614 cu ft volume, peak 143" ceiling
- Elevation: 5,090 ft (Longmont, CO, 40.17°N). 17% less air density than sea level.
- Glazing: 6mm opal polycarbonate, SHGC 0.66, diffuses all direct light
- Solar gain: ~87,000 BTU/hr peak vs ~52,900 BTU/hr max fan cooling capacity

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
| Heater 2 (gas/Lennox) | 75,000 BTU/hr | HEAT_S2 (below band floor) |
| AquaFog XE 2000 | 1,644W, ultrasonic | HUMID_S1+ or fog escalation |
| Intake vent (north) | 24"x24", motorized | Economiser logic (enthalpy gate) |
| Grow lights (main) | 630W, 15x4FT LED | DLI-based automation |
| Grow lights (shelf) | 816W, 15x2FT LED | DLI-based automation |

## State Machine (48 states (6 thermal × 8 VPD))

Temperature axis: HEAT_S2 → HEAT_S1 → TEMP_IDLE → COOL_S1 → COOL_S2 → COOL_S3
Humidity axis: DEHUM_HEAT → DEHUM_V2 → DEHUM_V1 → HUM_IDLE → HUMID_S1 → HUMID_S2 → HUMID_S3

Key thresholds:
- HEAT_S2 at temp_low, HEAT_S1 at temp_low + d_heat_stage_2
- COOL_S1 at temp_high, COOL_S2 at temp_high + d_cool_stage_2
- HUMID_S1 at vpd_high + vpd_hysteresis
- Safety: force HEAT_S2 below 45°F, force COOL_S3 above 95°F

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
- Above ~85°F, system is physics-limited — accept stress
