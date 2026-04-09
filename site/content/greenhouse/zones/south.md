---
title: "South Zone"
tags: [zones, south, climate]
date: 2026-03-28
type: zone
zone: south
sensor: "Modbus addr 4 (temp, RH, VPD)"
orientation: "Front-facing, highest direct light"
water_systems: [wall_drip, south_mister]
position_scheme: "SOUTH-SHELF-{T|B}{1..4}, SOUTH-FLOOR-{N}"
peak_temp: "100°F+"
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# South Zone
The furnace. Hottest at solar noon, highest natural light, driest VPD. The south end sits between the two angled exhaust faces as the hex tapers to its narrowest point. Home to canna lilies and tropical ornamentals that thrive in conditions that would stress production crops.

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 1.5rem 0;">

![South end — twin KEN BROWN exhaust fans on the angled faces with overhead mister nozzles and climate sensor](/static/photos/south-wall-fans-misters.jpg)

![Exhaust fan closeup with red mister nozzles on the irrigation header](/static/photos/exhaust-fan-mister-nozzles.jpg)

![The south zone — exhaust fans, mister nozzles, and the hottest microclimate at solar noon](/static/photos/interior-south-zone.jpg)

</div>

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=11&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=15&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=15&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=15&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>

<div class="grafana-controls"></div>

## Climate Profile

| Metric | Value | Context |
|--------|-------|---------|
| Peak temperature (hot day) | 100.4°F | March 25, 88°F outdoor |
| Avg peak vs greenhouse avg | +5-9°F | Consistently the hottest zone at noon |
| Overnight retention | 2-4°F above north | Concrete slab stores solar heat |
| VPD at peak | Highest in greenhouse | Exhaust fans pull humid air out here |
| CO₂ | Elevated midday (+150 ppm) | Soil microbial activity from floor pots |

### Why It's Hottest
Three factors stack:
1. **Hex taper** — the south wall is the narrowest (~8-10 ft), concentrating solar gain per square foot of floor
2. **Exhaust path** — both Ken Brown 18" fans are mounted high on the southwest and southeast angled faces. They still pull hot air *toward* and out of the south end
3. **Peak solar angle** — at solar noon, the south-facing surfaces receive maximum radiation

### The Heat Spot Rotation
South isn't always hottest. The heat rotates through the day:

- **Solar noon (12 PM):** South is hottest (100°F+)
- **2 PM:** North catches up (93.6°F — house thermal mass releasing stored heat)
- **Late afternoon:** West takes the lead (setting sun on the longest wall)
- **Overnight:** South retains heat from concrete slab (2-4°F above north)

## Physical Layout

| Position | Contents | Water Access |
|----------|----------|-------------|
| SOUTH-SHELF-T1 through T4 | 4 shelf bays, top tier | Wall drip (shared zone) |
| SOUTH-SHELF-B1 through B4 | 4 shelf bays, bottom tier | Wall drip (shared zone) |
| SOUTH-FLOOR | Canna lilies in large pots | Individual drip heads from wall drip line |

### Wall Structure
The south end is a three-face taper. Two shelf bays on the southeast angled wall and two on the southwest angled wall flank the narrower south center face. The two exhaust fans are mounted high on those angled faces, not on the center face.

### Equipment

- **Exhaust Fan 1:** Ken Brown 18" shutter exhaust, 2,450 CFM, 52W (pcf_out_2 pin 3)
- **Exhaust Fan 2:** Ken Brown 18" shutter exhaust, 2,450 CFM, 52W (pcf_out_2 pin 4)
- **South Misters:** 6 heads, 30 nozzles, wall-mounted in 2 rows. Most effective zone (0.15 kPa avg VPD drop per pulse)

## Water Systems

| System | Type | Control | Notes |
|--------|------|---------|-------|
| Wall drip (clean) | Scheduled, daily 6 AM × 10 min | pcf_out_1 pin 4 | Shared with west zone — ONE zone |
| Wall drip (fert) | On-demand | pcf_out_2 pin 0 + master | Same heads, fert supply path |
| South misters (clean) | VPD-triggered pulse | pcf_out_1 pin 3 | 60s on / 45s gap |
| South misters (fert) | Manual | pcf_out_1 pin 2 | Available for fertigation |

## Sensor Coverage

| Sensor | Address | Interval | Accuracy |
|--------|---------|----------|----------|
| Temperature | Modbus addr 4 (Tzone SHT3X) | 10s | ±0.3°C |
| Relative Humidity | Same probe | 10s | ±2% RH |
| VPD | Derived on ESP32 (Magnus formula) | 10s | Calculated |
| Soil moisture | Modbus addr 7 (DFRobot SEN0601) | 30s | %VWC |
| Soil temp | Same probe | 30s | °F |
| Soil EC | Same probe | 30s | µS/cm |

## Current Planting

| Crop | VPD Target | Notes |
|------|-----------|-------|
| [[greenhouse/crops/canna-lilies|Canna Lilies]] | 1.37-1.57 kPa (tolerant) | Established tropical perennials, floor pots |
The south zone's VPD target is the highest in the greenhouse because cannas tolerate dry air up to 1.8+ kPa. This means the mister stress-score algorithm deprioritizes south in favor of zones with more sensitive crops (east hydro, center orchids). South misters fire only when VPD exceeds the canna's wide comfort zone.
**Also suitable:** peppers, tomatoes, heat-tolerant herbs. Anything that tolerates 90-100F and high VPD.

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=11&theme=dark" width="100%" height="320px" frameborder="0"></iframe></div>
**Avoid:** Lettuce, cilantro, spinach — anything that bolts above 80°F. The south zone exceeds 80°F routinely from March through October.
→ See [[climate/|Climate at 5,000 Feet]] for the full thermal analysis.
→ See [[climate/cooling|Cooling & Ventilation]] for exhaust fan details.
→ See [[greenhouse/zones/|All Zones]]
