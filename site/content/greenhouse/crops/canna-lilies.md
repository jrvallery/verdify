---
title: "Canna Lilies"
tags: [crops, canna, tropical, ornamental, reference]
date: 2026-04-08
type: crop-profile
crop: canna
system: soil
zone: south
season: warm
cycle_days: "perennial"
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">
<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Canna Lilies

![Canna lilies blooming beside hydroponic channels under grow lights](/static/photos/interior-cannas-hydro-growlights.jpg)

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=2&theme=dark" width="100%" height="130px" frameborder="0"></iframe>
<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=3&theme=dark" width="100%" height="130px" frameborder="0"></iframe>
<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=4&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>

Tropical perennials from the Americas. Cannas occupy the south zone floor in large pots, thriving in the hottest, brightest conditions the greenhouse produces. They are the opposite of lettuce: they love heat, tolerate drought, and bloom prolifically when conditions that would stress most crops barely register.

## Optimal Conditions

| Parameter | Range | Notes |
|-----------|-------|-------|
| Day temperature | 75-95F | Thrives in heat that kills lettuce |
| Night temperature | 55-65F | Tolerates cool nights, dormant below 50F |
| VPD | 0.8-1.8 kPa | Very tolerant of dry air |
| DLI | 12-20+ mol/m2/d | Full sun preferred |
| Water | Regular but well-drained | Heavy drinkers during growth, rot-prone if waterlogged |

## Diurnal Target Profile (Spring)

This table drives the greenhouse control band for the south zone. Because cannas tolerate high VPD, the south zone's mister target is set much higher than the east zone (hydro crops) or center (orchids).

| Hour | Temp Min (F) | Temp Max (F) | VPD Min (kPa) | VPD Max (kPa) |
|------|-------------|-------------|---------------|---------------|
| 0 (midnight) | 55 | 75 | 0.25 | 1.00 |
| 3 | 55 | 75 | 0.25 | 1.00 |
| 6 (dawn) | 55 | 75 | 0.25 | 1.00 |
| 8 | 60 | 78 | 0.30 | 1.20 |
| 10 | 62 | 80 | 0.40 | 1.36 |
| 12 (noon) | 64 | 82 | 0.50 | 1.52 |
| 14 | 66 | 85 | 0.60 | 1.68 |
| 16 | 68 | 88 | 0.70 | 1.84 |
| 18 (dusk) | 62 | 79 | 0.25 | 1.30 |
| 20 | 55 | 75 | 0.25 | 1.00 |
| 23 | 55 | 75 | 0.25 | 1.00 |

The wide VPD range (up to 1.84 kPa at peak) means the south zone mister fires last in the stress-score priority system. When lettuce in the east zone is stressed at 1.0 kPa, cannas in the south are still comfortable. This is by design: water goes where it does the most good.

## Zone Recommendation

**Primary: [[greenhouse/zones/south|South Zone]] floor pots**

The south zone is the hottest spot in the greenhouse, regularly hitting 100F on sunny spring days. Cannas not only tolerate this, they prefer it. Their large leaves provide natural shading for the south zone floor, and their heavy transpiration contributes moisture to the local microclimate.

## Why Cannas Matter for the Greenhouse

Cannas are not a production crop. They are here because:

1. **They survive the south zone.** Almost nothing else thrives at 95-100F sustained. Cannas fill a zone that would otherwise be empty or require shade cloth to make usable.

2. **They transpire heavily.** A large canna can transpire several liters per day, adding moisture to the south zone air. This provides a baseline humidity contribution that benefits nearby zones.

3. **They are visually dramatic.** The 4-foot foliage and tropical flowers make the greenhouse feel alive, especially in winter when the outdoor landscape is dormant.

4. **They tolerate neglect.** Wall drip irrigation keeps them alive. They do not need the precision monitoring that lettuce or orchids demand.

## Care Notes

- **Water:** Heavy drinkers during active growth. The wall drip system provides daily irrigation.
- **Fertilizer:** Monthly balanced fertilizer during growing season. Heavy feeders.
- **Winter dormancy:** Below 50F, cannas go dormant. In this greenhouse they rarely hit true dormancy thanks to heating, but growth slows dramatically in December-January.
- **Pruning:** Remove spent flower stalks to encourage reblooming. Cut back dead foliage in late winter.

---

## Where to Go Next

- [South Zone](/greenhouse/zones/south/) — the hottest zone, where cannas thrive
- [Humidity & VPD](/climate/humidity/) — why cannas' high VPD tolerance deprioritizes south misters
- [Growing at 5,000 Feet](/climate/) — how altitude shapes the greenhouse microclimate
