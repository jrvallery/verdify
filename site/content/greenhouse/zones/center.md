---
title: "Center Zone"
tags: [zones, center, offline]
date: 2026-03-28
type: zone
zone: center
sensor: "None (avg of N/S/E/W)"
orientation: "Open floor area"
water_systems: [center_mister, "center_drip (DISCONNECTED)"]
position_scheme: "CENTER-HANG-{1|2}, CENTER-FLOOR-{N}"
status: OFFLINE
---

# Center Zone

![Vanda orchids hanging in the greenhouse — planned occupants for the center zone](/static/photos/vanda-orchids-hanging.jpg)
**STATUS: OFFLINE** — No active planting. Equipment transit zone.
The center is the greenhouse's airflow mixing zone. The AquaFog XE 2000 fog machine hangs overhead, blowing fog north-to-south aligned with the primary airflow path. Center drip infrastructure exists but is **physically disconnected** — plumbing needs to be reconnected before software control is possible.

## Physical Layout

| Feature | Details |
|---------|---------|
| Fog machine | AquaFog XE 2000 HumidiFan, 1,644W, <10µm droplets, overhead center | 
| Hanging holes | 2 positions (CENTER-HANG-1, CENTER-HANG-2). Planned for orchids. |
| Floor space | Open area between perimeter zones. Work table. |
| Center misters | 7 heads (5 active, 2 off over work area), 25 nozzles, overhead |

### Center Mister Underperformance
The center mister zone has the worst VPD effectiveness of all three zones:

| Zone | Avg VPD Drop per Pulse |
|------|----------------------|
| South | 0.15 kPa (best) |
| West | 0.13 kPa |
| **Center** | **0.04 kPa (worst)** |
This needs physical investigation. Likely causes:

- Nozzle geometry or positioning (overhead in a mixing zone vs wall-mounted for south)
- Open airflow pulls mist away before it evaporates
- Fewer active nozzles relative to open volume

### Drip Infrastructure

| Relay | Pin | Status |
|-------|-----|--------|
| Center drip (clean) | pcf_out_1 pin 7 | ❌ Physically disconnected |
| Center drip (fert) | pcf_out_1 pin 6 | ❌ Physically disconnected |
Reconnection requires physical plumbing work. The relays and firmware are ready — just need pipes.

## Sensor Coverage
No dedicated sensor. The center zone uses the average of north, south, east, and west probe readings. In practice, center conditions are close to the greenhouse average since the fog machine blows air through this zone.

## Airflow Role
The center is the critical mixing zone in the greenhouse's north-to-south airflow:
```
North (intake vent)
  ↓
CENTER — Fog machine blows N→S
         Center misters add humidity
         Air mixing zone
  ↓
South (exhaust fans, 4,900 CFM)
```
Even though no plants live here, the center's fog machine and misters serve the entire greenhouse's humidity control.

## Future Plans

| Plan | Status | Dependency |
|------|--------|------------|
| Orchid hanging baskets | Planned | Hanging holes ready. Need species selection. |
| Center drip reconnection | Pending | Physical plumbing work |
| Dedicated probe | Considered | Would improve mixing zone monitoring |
→ See [[climate/|Climate at 5,000 Feet]] for fog and mister context.
→ See [[greenhouse/zones/|All Zones]]
