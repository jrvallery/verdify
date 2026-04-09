---
title: "Lettuce"
tags: [crops, lettuce, hydroponic, reference]
date: 2026-03-28
type: crop-profile
crop: lettuce
system: hydroponic
zone: east
season: cool
cycle_days: 45-60
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Lettuce

![Lettuce varieties and dill growing in PVC NFT hydroponic channels — romaine, red leaf, and young transplants](/static/photos/hydro-nft-channels.jpg)

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=2&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=3&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=4&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>
The anchor crop. Fast rotation, high demand, loves the [[greenhouse/zones/east|East Zone]]'s cooler temperatures. The narrow planting window at this greenhouse is *now* — by late May, the south zone will be too hot and even the east zone will push lettuce's comfort zone.

## Optimal Conditions

| Parameter | Range | Notes |
|-----------|-------|-------|
| Day temperature | 65-75°F | Above 80°F triggers bolting |
| Night temperature | 55-65°F | Cool nights improve crispness |
| VPD | 0.8-1.0 kPa | Moderate — lettuce transpires freely |
| DLI | 14-17 mol/m²/d | Below 12 = leggy. Above 20 = can trigger bolting with heat |
| pH (hydro) | 5.5-6.0 | Slightly acidic |
| EC | 0.8-1.2 mS/cm | Light feeder |
| Photoperiod | 14-16 hours | Day-neutral but benefits from long days |

## Diurnal Target Profile (Spring)
This table drives the greenhouse control band. The tightest envelope across all active crops becomes the setpoint the ESP32 chases. Values transition gradually to follow stomatal opening and closing patterns.

| Hour | Temp Min (F) | Temp Max (F) | VPD Min (kPa) | VPD Max (kPa) |
|------|-------------|-------------|---------------|---------------|
| 0 (midnight) | 55 | 65 | 0.30 | 0.60 |
| 1 | 55 | 65 | 0.30 | 0.60 |
| 2 | 55 | 65 | 0.30 | 0.60 |
| 3 | 55 | 65 | 0.30 | 0.60 |
| 4 | 55 | 65 | 0.28 | 0.55 |
| 5 | 56 | 66 | 0.30 | 0.60 |
| 6 (dawn) | 58 | 68 | 0.35 | 0.70 |
| 7 | 60 | 72 | 0.45 | 0.85 |
| 8 | 63 | 75 | 0.55 | 1.00 |
| 9 | 65 | 78 | 0.65 | 1.20 |
| 10 | 65 | 80 | 0.75 | 1.35 |
| 11 | 65 | 80 | 0.80 | 1.45 |
| 12 (noon) | 65 | 80 | 0.80 | 1.50 |
| 13 | 65 | 80 | 0.80 | 1.50 |
| 14 | 65 | 80 | 0.80 | 1.45 |
| 15 | 65 | 78 | 0.75 | 1.35 |
| 16 | 63 | 76 | 0.65 | 1.20 |
| 17 | 61 | 74 | 0.55 | 1.05 |
| 18 (dusk) | 59 | 72 | 0.45 | 0.90 |
| 19 | 57 | 70 | 0.38 | 0.75 |
| 20 | 55 | 68 | 0.32 | 0.65 |
| 21 | 55 | 66 | 0.30 | 0.60 |
| 22 | 55 | 65 | 0.30 | 0.60 |
| 23 | 55 | 65 | 0.30 | 0.60 |
Lettuce is the most cold-tolerant active crop (temp min 55F) but the most heat-sensitive (bolts above 80F sustained). It constrains the high end of the composite band more than any other crop.

## Varieties for This Greenhouse

| Variety | Type | Days to Harvest | Heat Tolerance | Notes |
|---------|------|----------------|---------------|-------|
| Butterhead (Bibb) | Head | 50-60 | Moderate | Classic, tender leaves |
| Romaine | Head | 55-70 | Good | More heat-tolerant than butterhead |
| Red leaf | Loose-leaf | 45-55 | Good | Fast, cut-and-come-again possible |
| Green leaf | Loose-leaf | 45-55 | Good | Workhorse variety |
| Oakleaf | Loose-leaf | 45-50 | Best | Most bolt-resistant |
**Recommendation:** Start with a mix of romaine and red/green leaf. Leaf types are fastest and most forgiving. Oakleaf for summer planting — best bolt resistance.

## Zone Recommendation
**Primary: [[greenhouse/zones/east|East Zone]] hydroponic system**
The east zone runs 5-9°F below the greenhouse average during peak heat. On a day when the south zone hits 100°F, the east zone is at 91°F. For lettuce, this difference is the line between a head of lettuce and a flower stalk.

| Factor | East Zone Value | Lettuce Tolerance |
|--------|----------------|-------------------|
| Peak temp (hot day) | ~91°F | Bolts > 80°F sustained |
| Tree shade | Blocks morning direct solar | Reduces heat stress |
| Patio door ventilation | Additional cooling in summer | Helps but introduces dry air |
| Hydro humidity | Evaporation adds local RH | Improves VPD for lettuce |
**Seasonal viability:**

| Season | Viability | Notes |
|--------|-----------|-------|
| March-May | ✅ Excellent | Plant NOW. Prime lettuce window. |
| June-July | ⚠️ Marginal | Even east zone will be hot. Bolt-resistant varieties only. |
| August | ⚠️ Marginal | Monsoon moisture helps but still hot |
| September-October | ✅ Good | Fall crop window |
| November-February | ✅ Good | Grow lights essential; heat cost offset by value |

## Hydroponic Growing Notes

- **Media:** Grodan rockwool cubes → net cups → clay pellets
- **Spacing:** Every other position (positions 1, 3, 5...) gives 6" spacing for heads
- **Nutrient formula:** General Hydroponics Flora series, light concentration (EC 0.8-1.2)
- **Days to harvest:** 45-60 from transplant to hydro (add 10-14 for seedling stage)
- **Harvest method:** Cut at base for head types. Cut outer leaves for leaf types (extends to 2-3 harvests)

## Succession Planting
For continuous harvest, stagger plantings by 2 weeks:

| Week | Action | Positions |
|------|--------|-----------|
| 0 | Seed starts (Jiffy mix, east shelf heat mat) | Tray |
| 2 | Transplant batch 1 to hydro | HYDRO-1 through HYDRO-10 |
| 4 | Transplant batch 2 to hydro, seed batch 3 | HYDRO-11 through HYDRO-20 |
| 6 | Harvest batch 1, transplant batch 3 | Rotate positions |
At 10 positions per batch with 2-week stagger, this yields continuous lettuce with 30 hydro positions dedicated.

## Longmont-Specific Notes

- **Altitude effect:** Higher UV at 4,979 feet can stress lettuce. The opal polycarbonate blocks 99% of UV — this is actually an advantage.
- **Dry air:** Outdoor RH of 14-18% in spring means the greenhouse VPD will push high. [[climate/|Misters]] are essential during peak afternoon hours.
- **Water quality:** Longmont municipal water is soft, low in dissolved minerals. Good for hydro — nutrient solution won't need pH adjustment from high alkalinity.
→ See [[greenhouse/growing|All Crops]]

## Current Light Availability

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=9&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=5&theme=dark" width="100%" height="130" frameborder="0"></iframe>

</div>
