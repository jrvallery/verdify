---
title: "Peppers"
tags: [crops, peppers, hydroponic, reference]
date: 2026-03-28
type: crop-profile
crop: peppers
system: hydroponic
zone: east-south
season: warm
cycle_days: 90-120
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Peppers

![Pepper plants growing in the PVC hydroponic channels alongside lettuce](/static/photos/hydro-peppers-lettuce-channels.jpg)

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=2&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=3&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=4&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>
Heat-loving, semi-permanent residents. Peppers occupy hydroponic positions for months — they're not rotation crops. They thrive in exactly the conditions that kill lettuce.

## Optimal Conditions

| Parameter | Range | Notes |
|-----------|-------|-------|
| Day temperature | 75-85°F | Can tolerate 90°F+, but fruit set drops above 90°F |
| Night temperature | 65-70°F | Fruit set requires warm nights |
| VPD | 0.8-1.2 kPa | Moderate transpiration needs |
| DLI | 15-25 mol/m²/d | More light = more fruit. Above 30 mol is diminishing returns |
| pH (hydro) | 5.8-6.3 | Slightly less acidic than lettuce |
| EC | 2.0-3.5 mS/cm | Heavy feeder during fruiting |
| Photoperiod | 14-18 hours | Day-neutral but benefits from long days |

## Diurnal Target Profile (Spring)
This table drives the greenhouse control band. The tightest envelope across all active crops becomes the setpoint the ESP32 chases.

| Hour | Temp Min (F) | Temp Max (F) | VPD Min (kPa) | VPD Max (kPa) |
|------|-------------|-------------|---------------|---------------|
| 0 (midnight) | 60 | 68 | 0.30 | 0.70 |
| 1 | 60 | 68 | 0.30 | 0.70 |
| 2 | 60 | 68 | 0.30 | 0.70 |
| 3 | 60 | 68 | 0.30 | 0.70 |
| 4 | 60 | 68 | 0.30 | 0.65 |
| 5 | 61 | 69 | 0.32 | 0.70 |
| 6 (dawn) | 63 | 72 | 0.40 | 0.80 |
| 7 | 65 | 75 | 0.50 | 0.95 |
| 8 | 68 | 78 | 0.60 | 1.10 |
| 9 | 70 | 82 | 0.70 | 1.25 |
| 10 | 72 | 85 | 0.75 | 1.40 |
| 11 | 72 | 85 | 0.80 | 1.50 |
| 12 (noon) | 72 | 85 | 0.80 | 1.50 |
| 13 | 72 | 85 | 0.80 | 1.50 |
| 14 | 72 | 85 | 0.80 | 1.45 |
| 15 | 72 | 83 | 0.75 | 1.35 |
| 16 | 70 | 80 | 0.65 | 1.20 |
| 17 | 68 | 78 | 0.58 | 1.10 |
| 18 (dusk) | 65 | 76 | 0.48 | 0.95 |
| 19 | 63 | 73 | 0.40 | 0.80 |
| 20 | 61 | 70 | 0.35 | 0.72 |
| 21 | 60 | 68 | 0.30 | 0.70 |
| 22 | 60 | 68 | 0.30 | 0.70 |
| 23 | 60 | 68 | 0.30 | 0.70 |
Peppers are the heat lovers. They push the temp_min up during the day (72F minimum at peak) and tolerate the widest temp range (up to 85F). In the composite band, peppers constrain the low end during daytime hours.

## Varieties for This Greenhouse

| Variety | Type | Days to Fruit | Heat | Scoville | Notes |
|---------|------|--------------|------|---------|-------|
| **Shishito** | Sweet/mild | 60-80 | Excellent | 50-200 | Primary pick. 1/10 pods are spicy. |
| Jalapeño | Hot | 70-80 | Excellent | 2,500-8,000 | Classic, reliable |
| Mini Sweet | Sweet | 55-65 | Good | 0 | Snacking peppers, compact plants |
| Habanero | Hot | 90-120 | Excellent | 100,000+ | Needs the south zone heat |
| Banana | Sweet/mild | 65-75 | Good | 0-500 | Good for pickling |
**Recommendation:** Shishito as the primary pepper. Compact, prolific, and the east zone's temperature profile (91°F peak) is within their sweet spot. Reserve 4-6 hydro positions as semi-permanent.

## Zone Recommendation
**Primary: [[greenhouse/zones/east|East Zone]] hydroponic (for most varieties)**
**Alternative: [[greenhouse/zones/south|South Zone]] shelving (for heat-lovers like habanero)**

| Zone | Peak Temp | Fit |
|------|----------|-----|
| East (hydro) | ~91°F | ✅ Ideal for shishito, jalapeño, mini sweet |
| South (shelving) | ~100°F+ | ✅ For habanero, superhots that want maximum heat |
| West | ~mid-range | ✅ Viable for all varieties |
Peppers tolerate the greenhouse's hottest days. Even the south zone's 100°F+ peaks don't damage established pepper plants — fruit set just slows above 90°F. The east zone's more moderate temperatures (75-91°F range) optimize for both plant health AND fruit production.

## Hydroponic Growing Notes

- **Semi-permanent:** Pepper plants occupy positions for 3-6 months. Plan positions accordingly.
- **Support:** Plants get 18-24" tall. Net cups may need stakes or ties.
- **Nutrient transition:** Start at EC 1.5-2.0 during vegetative growth. Increase to 2.5-3.5 during flowering/fruiting.
- **Pruning:** Remove first flowers to encourage branching. Top at 12" for bushier growth.
- **Harvest:** Pick when color turns. Frequent picking encourages more production.

## Longmont-Specific Notes

- **Growing season advantage:** The greenhouse extends peppers from Longmont's outdoor 90-day frost-free window to year-round production.
- **Light is adequate:** At 17-27 mol/m²/d estimated actual DLI, the greenhouse exceeds pepper minimum (15 mol) and hits optimal range (20-25 mol) on clear days.
- **Pollination:** Peppers are self-pollinating but benefit from vibration. The exhaust fans provide air movement; occasional gentle shaking helps.
→ See [[greenhouse/growing|All Crops]]
→ See [[greenhouse/zones/south|South Zone]] for the heat-loving zone profile

## Current Light Availability

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=9&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=5&theme=dark" width="100%" height="130" frameborder="0"></iframe>

</div>
