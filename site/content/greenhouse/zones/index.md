---
title: Growing Zones
tags: [zones, overview]
date: 2026-03-28
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Growing Zones

<div class="pg s4"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=11&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=11&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=11&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=12&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>

<div class="grafana-controls"></div>
Five zones, three microclimates, 367 square feet. Each zone has distinct temperature, humidity, and light characteristics driven by wall orientation, proximity to the house, tree shade, and equipment placement.

## Zone Map

| Zone | Status | Character | Peak Temp | Best Crops |
|------|--------|-----------|-----------|------------|
| [[greenhouse/zones/south|South]] | ✅ Active | The furnace — hottest at noon | 100°F+ | Peppers, tomatoes, heat-lovers |
| [[greenhouse/zones/east|East]] | ✅ Active | The cool corridor — hydro system | ~91°F | Lettuce, herbs, strawberries |
| [[greenhouse/zones/west|West]] | ✅ Active | The longest wall — versatile | Mid-range | Basil, cucumbers, mixed herbs, starts |
| [[greenhouse/zones/north|North]] | ✅ Equipment | Shared with house — thermal buffer | 93°F (2 PM) | No planting — equipment only |
| [[greenhouse/zones/center|Center]] | ❌ **OFFLINE** | Fog machine location, mixing zone | — | Drip disconnected |

## The Three Microclimates
At any given moment, there can be a 9°F difference between the hottest and coolest zones in 367 square feet. This stratification is an asset — it lets us match crops to their preferred conditions.
**South (Hot + Dry):** Peak solar gain at the tapered south end. The exhaust path terminates here, with fans mounted high on the southwest and southeast angled faces. Concrete slab retains heat overnight. VPD runs highest. Reserved for heat-lovers.
**East (Cool + Humid):** Tree shade blocks morning solar. Patio door provides cross-ventilation. Hydroponic evaporation adds local humidity. The most comfortable zone for plants.
**West (Moderate + Versatile):** Longest wall, best grow light coverage, afternoon sun exposure. Neither the hottest nor coolest — handles the widest range of crops.

## Airflow Path
```
NORTH — Intake vent (24"×24") + house door (passive)
  ↓
EAST — Patio door (summer: secondary intake)
  ↓
CENTER — Fog machine blows N→S + center misters
  ↓
SOUTH END — 2× exhaust fans on SW/SE angled faces (4,900 CFM combined)
```
Full air exchange every 44 seconds when both fans are running. In summer, the patio door is the dominant intake (not the north vent), creating an asymmetric east/NE-to-south airflow path.

## Zone Sensor Coverage

| Zone | Probe | Address | Additional Sensors |
|------|-------|---------|-------------------|
| South | Tzone RS485 SHT3X | Modbus 4 | Soil (SEN0601: moisture, temp, EC) |
| East | Tzone RS485 SHT3X | Modbus 5 | YINMIK hydro (pH, EC, TDS, ORP, water temp), Soil (SEN0600: moisture, temp) |
| West | Tzone RS485 SHT3X | Modbus 3 | Soil (SEN0600: moisture, temp) |
| North | Tzone RS485 SHT3X | Modbus 2 | CO₂ (analog), Lux (LDR) |
| Center | None (calculated avg) | — | — |
| Outdoor | Tempest + intake (OFFLINE) | — | 20 weather metrics |

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-zones/?orgId=1&panelId=11&theme=dark" width="100%" height="320px" frameborder="0"></iframe></div>
→ See [[climate/|Climate at 5,000 Feet]] for the full thermal analysis.
→ See [[greenhouse/structure|Physical Structure]] for dimensions and wall specs.
