---
title: "East Zone"
tags: [zones, east, hydroponic, climate]
date: 2026-03-28
type: zone
zone: east
sensor: "Modbus addr 5 (temp, RH, VPD)"
orientation: "Most shaded, coolest"
water_systems: [hydroponic_recirculating, wall_drip, south_mister]
position_scheme: "EAST-HYDRO-{1..60} + EAST-SHELF-{T|B}{1..3}"
peak_temp: "~91°F (on an 88°F outdoor day)"
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# East Zone
The cool corridor. Coolest zone by 5-9°F during peak heat. Home to the hydroponic system (60 positions), seedling shelves, and the patio door — the single most important climate variable in the building.

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 1.5rem 0;">

![Hydroponic NFT channels with lettuce and herb starts in net cups](/static/photos/hydro-nft-channels.jpg)

![Seedling flats on wire shelving near the hydro system](/static/photos/seedling-flats-propagation.jpg)

</div>

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=11&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>

<div class="pg s4"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=1&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=2&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=3&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=4&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>

<div class="grafana-controls"></div>

## Climate Profile

| Metric | Value | Context |
|--------|-------|---------|
| Peak temperature (hot day) | ~91°F | When south hits 100°F, east is at 91°F |
| Temperature delta vs avg | -5 to -9°F | Consistently the coolest active zone |
| Humidity | Higher than other zones | Hydro evaporation adds local RH |
| VPD | Lowest in greenhouse | Cool + humid = most plant-comfortable |

### Why It's Coolest
Three factors stack to create the east zone's microclimate:
1. **Tree shade** — A large tree on the east side blocks morning solar until ~10:18 AM. The shadow shifts west through the day, but the east wall gets the least total solar radiation. Light transmission at the east wall sensor position: 6.9% (vs 57% spec).
2. **Patio door** — The glass/screen combo at the NE corner provides cross-ventilation in summer. When open or screened, outdoor air enters here directly.
3. **Blocked morning solar** — The combination of tree shade and the house to the northwest means the east zone misses the strongest morning heating period.

### Seasonal Door Management

| Season | Patio Door Config | Effect |
|--------|------------------|--------|
| Winter | Glass insert in | Insulation. Minimal heat loss. |
| Spring/Fall | Glass insert, sometimes screen | Partial ventilation on warm days |
| Summer | Glass removed → screen or fully open | Major vent opening — cross-ventilation drops east zone temps significantly |
The patio door is the **#1 manual climate lever**. Open it for cooling but lose humidity. Close it for fog retention but temps climb. On a 90°F/16% RH day, there is no configuration that achieves both comfortable temperature AND comfortable VPD simultaneously.

## Physical Layout

### Hydroponic System (~half of east wall)

| Component | Spec |
|-----------|------|
| Rails | 4" PVC, 3 rails (A, B, C) |
| Rows | 2 per rail (top + bottom) |
| Positions | 60 total (1-30 top row, 31-60 bottom row) |
| Media | Grodan rockwool → net cups → clay pellets |
| Nutrients | General Hydroponics Flora/Bloom/Grow |
| Type | Recirculating pump system |
| Grow lights | 14× Barrina 2FT LED (7 per row, 12" OC, 336W total) |

### Hydro Water Quality Monitoring (YINMIK)

| Parameter | Current Reading | Target | Status |
|-----------|----------------|--------|--------|
| pH | ~1922 (raw) | 5.5-6.5 | **⚠️ NEEDS CALIBRATION** |
| EC | ~1,400 µS/cm | 800-2,500 | ✅ In range |
| TDS | ~690 ppm | 400-1,250 | ✅ In range |
| ORP | -1 mV | 200-400 mV | **⚠️ NEEDS CALIBRATION** |
| Water temp | ~70°F | 65-75°F | ✅ Good |
| Battery | 1% | > 20% | **⚠️ NEEDS ATTENTION** |

### Wall Shelving (~half of east wall, south of patio door)

| Position | Contents | Notes |
|----------|----------|-------|
| EAST-SHELF-T1 | Seedlings (unknown) on heat mat | Heat mat for germination |
| EAST-SHELF-T2, T3 | Available | Grow lights: 5× Barrina 2FT |
| EAST-SHELF-B1, B2, B3 | Available | Partially blocked by hydro tank below |

## Water Systems

| System | Type | Control | Notes |
|--------|------|---------|-------|
| Hydro recirculating | Continuous pump | Independent | Not on ESP32 control |
| Wall drip (shared) | pcf_out_1 pin 4 | Scheduled 6 AM | Shared with south + west |
| South mister access | pcf_out_1 pin 3 | VPD-triggered | South misters reach into east zone |

## Sensor Coverage

| Sensor | Address/Source | Interval | Notes |
|--------|---------------|----------|-------|
| Temperature | Modbus addr 5 (SHT3X) | 10s | ±0.3°C accuracy |
| RH | Same probe | 10s | ±2% RH |
| VPD | Derived on ESP32 | 10s | Magnus formula |
| pH | YINMIK (LocalTuya → HA) | 5 min | Uncalibrated |
| EC | YINMIK | 5 min | Flowing |
| TDS | YINMIK | 5 min | Flowing |
| ORP | YINMIK | 5 min | Uncalibrated |
| Water temp | YINMIK | 5 min | Flowing |
| Soil moisture | Modbus addr 8 (DFRobot SEN0600) | 30s | %VWC |
| Soil temp | Same probe | 30s | °F |
The east zone has the most comprehensive instrumentation of any zone — climate probe + 5 hydro parameters + soil probe.

## Current Planting

| Crop | System | Stage | VPD Target | Notes |
|------|--------|-------|-----------|-------|
| [[greenhouse/crops/lettuce|Lettuce]] | Hydro | Seedling | 0.60-1.50 kPa | Bolt-sensitive above 80F |
| [[greenhouse/crops/strawberries|Strawberry starts]] | Hydro | Seedling | 0.75-1.40 kPa | Constrains zone VPD target |
| [[greenhouse/crops/peppers|Pepper starts]] | Hydro | Seedling | 0.70-1.50 kPa | Most heat-tolerant of the three |
The east zone VPD target (0.81-0.98 kPa) is the tightest in the greenhouse because strawberry starts have the narrowest VPD tolerance. East has a VPD sensor but no mister. When east VPD exceeds its target, the firmware boosts the stress score of adjacent zones (south and center) to increase their misting, which raises humidity across the greenhouse.
With the patio door open, east also gets direct outdoor air exchange, which helps cooling but hurts humidity on dry days.
**Also suitable:** basil, herbs, seedlings on shelving.

## Hydro Position Planning
60 positions is significant real estate. Recommended allocation:

| Positions | Count | Crop | Duration |
|-----------|-------|------|----------|
| 1-20 | 20 | Lettuce (rotating, 2-week succession) | 45-60 days per batch |
| 21-26 | 6 | Peppers (shishito, semi-permanent) | 90-120 days |
| 27-34 | 8 | Strawberries (Albion, semi-permanent) | Perennial |
| 35-42 | 8 | Basil (rotating) | 30-45 days per batch |
| 43-50 | 8 | Mixed herbs (cilantro, parsley) | 30-50 days |
| 51-60 | 10 | Experimental / overflow | Variable |

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=14&theme=dark" width="100%" height="320px" frameborder="0"></iframe></div>
→ See [[greenhouse/crops/|Crop Profiles]] for detailed growing conditions.
→ See [[greenhouse/zones/|All Zones]]
