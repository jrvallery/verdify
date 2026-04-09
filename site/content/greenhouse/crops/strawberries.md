---
title: "Strawberries"
tags: [crops, strawberries, hydroponic, reference]
date: 2026-03-28
type: crop-profile
crop: strawberries
system: hydroponic
zone: east
season: perennial
cycle_days: "60+ (perennial, everbearing)"
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Strawberries

![Strawberry plants flowering in the hydroponic system — white blossoms among trifoliate leaves](/static/photos/hydro-strawberry-flowers.jpg)

![Strawberry harvest from the hydroponic system](/static/photos/hydro-strawberry-harvest.jpg)

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=2&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=3&theme=dark" width="100%" height="130px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=4&theme=dark" width="100%" height="130px" frameborder="0"></iframe></div>
Perennial everbearing — plant once, harvest for months. Strawberries occupy hydroponic positions semi-permanently (6-12 months) and produce continuously once established. High-value crop: greenhouse strawberries in winter are luxury produce.

## Optimal Conditions

| Parameter | Range | Notes |
|-----------|-------|-------|
| Day temperature | 65-75°F | Fruit quality drops above 85°F |
| Night temperature | 55-60°F | Cool nights improve sweetness |
| VPD | 0.8-1.0 kPa | Prefers moderate humidity |
| DLI | 17-22 mol/m²/d | Needs more light than lettuce. Grow lights critical in winter. |
| pH (hydro) | 5.5-6.2 | Iron availability is pH-sensitive |
| EC | 1.0-1.5 mS/cm | Moderate feeder, sensitive to salt buildup |
| Photoperiod | 14-16 hours | Day-neutral everbearing types produce regardless |

## Diurnal Target Profile (Spring)

| Hour | Temp Min (F) | Temp Max (F) | VPD Min (kPa) | VPD Max (kPa) |
|------|-------------|-------------|---------------|---------------|
| 0 (midnight) | 55 | 65 | 0.30 | 0.75 |
| 1 | 55 | 65 | 0.30 | 0.75 |
| 2 | 55 | 65 | 0.30 | 0.75 |
| 3 | 55 | 65 | 0.30 | 0.75 |
| 4 | 55 | 65 | 0.28 | 0.70 |
| 5 | 56 | 66 | 0.30 | 0.75 |
| 6 (dawn) | 58 | 68 | 0.35 | 0.85 |
| 7 | 60 | 72 | 0.42 | 0.95 |
| 8 | 62 | 75 | 0.55 | 1.10 |
| 9 | 64 | 78 | 0.65 | 1.25 |
| 10 | 65 | 78 | 0.70 | 1.35 |
| 11 | 65 | 78 | 0.72 | 1.40 |
| 12 (noon) | 65 | 78 | 0.72 | 1.40 |
| 13 | 65 | 78 | 0.72 | 1.40 |
| 14 | 65 | 78 | 0.70 | 1.35 |
| 15 | 65 | 78 | 0.65 | 1.25 |
| 16 | 63 | 76 | 0.58 | 1.15 |
| 17 | 61 | 74 | 0.48 | 1.00 |
| 18 (dusk) | 59 | 72 | 0.40 | 0.88 |
| 19 | 57 | 69 | 0.35 | 0.78 |
| 20 | 56 | 67 | 0.32 | 0.75 |
| 21 | 55 | 66 | 0.30 | 0.75 |
| 22 | 55 | 65 | 0.30 | 0.75 |
| 23 | 55 | 65 | 0.30 | 0.75 |
Strawberries sit between lettuce and peppers in the thermal spectrum. They cap at 78F (same as the composite band daytime high) and are particularly sensitive to VPD extremes, which is why their VPD max is moderate.

## Varieties for This Greenhouse

| Variety | Type | Season | Flavor | Runner Production | Notes |
|---------|------|--------|--------|-------------------|-------|
| **Albion** | Everbearing | Year-round | Excellent | Low | Best flavor of everbearing types. |
| Seascape | Everbearing | Year-round | Good | Moderate | High yield, reliable |
| San Andreas | Everbearing | Year-round | Very good | Low | Good disease resistance |
| Monterey | Everbearing | Year-round | Good | Moderate | Highest yield of everbearing |
**Recommendation:** Albion. Best flavor, low runner production (important in hydro — runners are wasted energy), and consistently rated as the top everbearing strawberry for controlled environments.

## Zone Recommendation
**Primary: [[greenhouse/zones/east|East Zone]] hydroponic system**
Strawberries need the east zone's cooler temperatures. On hot days:

- East peaks at ~91°F (tolerable for short periods)
- South peaks at 100°F+ (fruit quality suffers significantly)

| Factor | East Zone | Strawberry Need |
|--------|-----------|----------------|
| Peak temp | ~91°F | < 85°F preferred, < 95°F tolerable |
| Night temp | ~62-67°F | 55-60°F ideal (slightly warmer than ideal) |
| Humidity | Higher (hydro evaporation) | Prefers moderate humidity |
| Light | 14× grow lights directly overhead | 17-22 mol DLI target achievable |
**Summer challenge:** June-July peak heat will stress strawberry fruit quality even in the east zone. [[climate/cooling|Shade cloth]] on the south and west faces helps the entire greenhouse.

## Hydroponic Growing Notes

- **Bare-root starts:** Soak roots 1 hour, trim to 4-5 inches, place in rockwool/clay pellets with crown above media line.
- **Position allocation:** Reserve 6-10 positions. Semi-permanent — plan around them.
- **Runner management:** Trim runners to direct energy to fruit production.
- **Pollination:** Strawberries need pollination. **Hand pollination** is necessary — brush each flower with a small paintbrush. Takes 30 seconds per plant every other day.
- **Iron supplementation:** Strawberries are iron-hungry. Watch for interveinal chlorosis.

## Harvest & Economics

| Metric | Value |
|--------|-------|
| Days to first fruit | 60-90 from bare-root |
| Production period | 6-12 months continuous |
| Yield per plant | 0.5-1.0 lb per month (established) |
| Grocery price | $4-6/lb (conventional), $6-8/lb (organic) |
| **Value per position** | **$2-6/month** |
At 8 positions producing 0.75 lb/month each at $5/lb average, that's $30/month in grocery-equivalent strawberries. Year-round greenhouse strawberries in Colorado winter are a genuine luxury.

## Longmont-Specific Notes

- **Altitude advantage:** Cooler night temperatures at 4,979 feet improve fruit sweetness.
- **Pest watch:** Spider mites love strawberries AND dry air. Regular scouting of leaf undersides is essential. See [[evidence/dashboards|Plant Health dashboard]].
- **Water quality:** Longmont's low-mineral water is ideal for strawberry hydro.
→ See [[greenhouse/growing|All Crops]]

## Current Light Availability

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=9&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-greenhouse-crops/?orgId=1&panelId=5&theme=dark" width="100%" height="130" frameborder="0"></iframe>

</div>
