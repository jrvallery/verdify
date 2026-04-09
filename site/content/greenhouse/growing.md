---
title: Growing
tags: [greenhouse, crops, hydroponic, growing]
date: 2026-04-07
aliases:
  - crops
  - greenhouse/hydroponics
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">
<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Growing

The south zone hits 100F. The east stays 91F. Lettuce bolts above 80F. Peppers love 90F. So where you put what matters more than how much space you have.

![Seedling propagation trays showing multiple growth stages from germination under humidity domes to transplant-ready starts](/static/photos/seedling-trays-humidity-dome.jpg)

![Seedling starter trays with young herb and vegetable starts under grow lights](/static/photos/seedling-flats-propagation.jpg)

<div class="grafana-controls" data-ranges="7d,30d,60d,90d"></div>

<div class="pg s3">
<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=2&theme=dark" width="100%" height="130px" frameborder="0"></iframe>
<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=3&theme=dark" width="100%" height="130px" frameborder="0"></iframe>
<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=4&theme=dark" width="100%" height="130px" frameborder="0"></iframe>
</div>

## Current Planting

- **South zone:** Canna lilies in floor pots (wall drip + south misters)
- **East zone:** Hydroponic system ready (60 positions, strawberries and lettuce planned)
- **West zone:** Shelf starts, contents mixed
- **Center zone:** Offline |â|€|” planned for orchids

Crop records are still sparse. Emily's actual greenhouse updates are not yet flowing into the structured crop system consistently. That's okay |â|€|” the right move is to make this honest and useful now, then deepen it as the system matures.

## Zone-Crop Fit

Each zone's microclimate determines what grows well there:

| Zone | Temp Range | Best Crops | Avoid |
|------|-----------|------------|-------|
| [South](/greenhouse/zones/south/) | Hottest (100|Â|°F+ peak) | Peppers, tomatoes, heat-loving herbs | Lettuce, cilantro |
| [East](/greenhouse/zones/east/) | Coolest (91|Â|°F peak) | Lettuce, strawberries, herbs, seedlings | Nothing |â|€|” most versatile |
| [West](/greenhouse/zones/west/) | Mid-range, hot PM | Cucumbers, versatile herbs, starts | Bolt-prone crops in summer |

## The Hydroponic System

60-position recirculating NFT system on the east wall |â|€|” the coolest zone with the best temperature range for leafy greens.

- **Rails:** 3 PVC rails |Ã|— 2 rows (top: positions 1|â|€|“30, bottom: 31|â|€|“60)
- **Media:** Grodan rockwool in net cups with clay pellets
- **Nutrients:** General Hydroponics Flora/Bloom/Grow series
- **Lighting:** 14|Ã|— Barrina 2FT grow lights at 12" spacing overhead

<div class="pg s2">
<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=15&theme=dark" width="100%" height="300" frameborder="0"></iframe>
<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=16&theme=dark" width="100%" height="300" frameborder="0"></iframe>
</div>

Water quality is monitored by a YINMIK sensor (pH, EC, TDS, ORP, water temp). EC and TDS are in range; pH and ORP need calibration. Water heated to 86|Â|°F by Rinnai RE140iN tankless heater.

## Plant Stress Context

<div class="pg s2">
<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=8&theme=dark" width="100%" height="300" frameborder="0"></iframe>
<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=13&theme=dark" width="100%" height="300" frameborder="0"></iframe>
</div>

VPD stress hours (left) and zone-level VPD (right). When VPD exceeds 2.0 kPa, plants close stomata and stop growing. See the [VPD scale](/climate/humidity/#the-vpd-scale) and [DLI requirements](/climate/lighting/#crop-dli-requirements) for crop-specific thresholds.

## Crop Profiles

Detailed growing parameters, zone recommendations, and economics for each crop:

- [Lettuce](/greenhouse/crops/lettuce/) |â|€|” The anchor crop. Fast rotation, loves east zone.
- [Peppers](/greenhouse/crops/peppers/) |â|€|” Heat-loving, semi-permanent. South or east zone.
- [Tomatoes](/greenhouse/crops/tomatoes/) |â|€|” Light-demanding. South zone primary.
- [Strawberries](/greenhouse/crops/strawberries/) |â|€|” Perennial everbearing. East zone hydro.
- [Basil](/greenhouse/crops/basil/) |â|€|” Fast cycle, high value. East zone.
- [Herbs](/greenhouse/crops/herbs/) |â|€|” Cilantro, parsley, dill, mint, and more. Mixed zones.
- [Cucumbers](/greenhouse/crops/cucumbers/) |â|€|” Vigorous growers. West zone.

â|†|’ See [Zones](/greenhouse/zones/) for the full microclimate data behind these recommendations.
â|†|’ See [Water Systems](/climate/water/) for irrigation, fertigation, and root zone monitoring.
