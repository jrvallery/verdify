---
title: "West Zone"
tags: [zones, west, climate]
date: 2026-03-28
type: zone
zone: west
sensor: "Modbus addr 3 (temp, RH, VPD)"
orientation: "Longest wall, afternoon sun"
water_systems: [wall_drip, west_mister]
position_scheme: "WEST-SHELF-{T|B}{1..6}"
wall_length: "~16-17 ft"
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# West Zone

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=11&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=15&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>

<div class="grafana-controls"></div>

The longest wall. Six shelf bays, 15 overhead 4FT grow lights on the rafters, and 15 shelf-level 2FT grow lights. The most versatile zone: not as hot as south, not as cool as east. Currently holds propagation trays, house plants, and rotating experimental plantings. No active production crop is assigned to this zone, so its VPD target defaults to 1.20 kPa.

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 1.5rem 0;">

![Labeled blue planters |�|�|� Serrano, Tomatillo, Columbine, Zinnia starts along the west wall](/static/photos/planters-labeled-starts.jpg)

![Seedlings and mint growing in blue troughs with drip irrigation](/static/photos/planters-seedlings-mint.jpg)

</div>

## Climate Profile

| Metric | Value | Context |
|--------|-------|---------|
| Temperature | Mid-range, hot late afternoon | Setting sun hits this wall directly |
| VPD | Mid-range | Between south (driest) and east (most humid) |
| Light | Strong natural + 30 grow lights | Best artificial light coverage |
| Afternoon peak | Takes over as hottest zone late PM | West-facing surfaces absorb afternoon sun |

### The Southwest Corner

The small angled southwest wall (~5-6 ft) has the best light transmission angle at 23.5% |�|�|� the most perpendicular incidence of any surface. Two shelf bays here get the most efficient natural light delivery.

## Physical Layout

| Position | Contents | Grow Lights |
|----------|----------|------------|
| WEST-SHELF-T1 through T6 | 6 shelf bays, top tier | 15|�|� Barrina 2FT (grow circuit, 12" OC) |
| WEST-SHELF-B1 through B6 | 6 shelf bays, bottom tier | 15|�|� Barrina 2FT (same) |
| Rafters above | |�|�|� | 15|�|� Barrina 4FT (main circuit, 36" OC, CRI 98) |

**Current contents:** Unknown pots from previous growing season. The grower needs to do an inventory.

### Wall Structure
At ~16-17 feet, the west wall is the longest continuous growing surface. Six shelf bays provide 12 total planting positions (6 top + 6 bottom). The overhead 4FT lights on the rafters are the highest-CRI fixtures in the greenhouse (CRI 98) and provide ambient supplemental light across the entire zone.

## Water Systems

| System | Type | Control | Notes |
|--------|------|---------|-------|
| Wall drip (clean) | Scheduled, daily 6 AM |�|� 10 min | pcf_out_1 pin 4 | **Shared with south zone** |
| Wall drip (fert) | On-demand | pcf_out_2 pin 0 + master | Same heads, fert path |
| West misters (clean) | VPD-triggered pulse | pcf_out_1 pin 0 | 0.13 kPa avg VPD drop |
| West misters (fert) | Manual | pcf_out_1 pin 1 | Available |

### |�|�|�|�|�|� Shared Drip Zone

Wall drip for south AND west is on one relay. Watering west waters south (and vice versa). Per-plant adjustment is via physical drip head volume restrictors only.

### Mister Configuration

3 active heads (3 off |�|�|� over storage below). 15 active nozzles. Overhead-mounted. VPD drop effectiveness: 0.13 kPa per pulse (second best after south's 0.15).

## Sensor Coverage

| Sensor | Address | Interval | Accuracy |
|--------|---------|----------|----------|
| Temperature | Modbus addr 3 (Tzone SHT3X) | 10s | |�|�0.3|�|�C |
| Relative Humidity | Same probe | 10s | |�|�2% RH |
| VPD | Derived on ESP32 | 10s | Calculated |
| Soil moisture | Modbus addr 9 (DFRobot SEN0600) | 30s | %VWC |
| Soil temp | Same probe | 30s | |�|�F |

## Recommended Crops

| Crop | Why West Zone | Notes |
|------|-------------|-------|
| [[greenhouse/crops/basil|Basil]] | Warm enough, excellent grow light coverage | Good year-round |
| [[greenhouse/crops/cucumbers|Cucumbers]] | Moderate heat, strong light, wall for vining | Trellis against wall |
| [[greenhouse/crops/herbs|Mixed herbs]] (parsley, oregano, thyme) | Versatile conditions | Group by water needs |
| Garden starts | Moderate conditions, good light | For spring outdoor transplant |
| [[greenhouse/crops/peppers|Peppers]] | Viable |�|�|� less heat than south but sufficient | Most varieties do fine here |

The west zone's versatility makes it ideal for:

- **Mixed herb production** (parsley, oregano, thyme, chives) on upper shelves
- **Garden starts** for outdoor transplant (spring plan)
- **Overflow** from the east zone when hydro positions are full

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=11&theme=dark" width="100%" height="320px" frameborder="0"></iframe></div>

�|�|� See [[climate/lighting|Grow Lighting]] for the fixture inventory.
�|�|� See [[greenhouse/zones/|All Zones]]
