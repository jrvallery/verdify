---
title: Heating
tags: [greenhouse, heating, equipment]
date: 2026-03-28
type: reference
heat1_watts: 1500
heat1_btu: 5120
heat1_cost_hr: 0.167
heat2_model: Lennox LF24-75A-5
heat2_btu: 75000
heat2_fuel: natural_gas
heat2_cost_hr: 0.623
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Heating

![Lennox gas-fired unit heater and green circulation fan suspended from the greenhouse roof structure](/static/photos/lennox-heater-circulation-fan.jpg)
*Part of [Climate at 5,000 Feet](/climate/) — the winter and overnight side of the control problem.*
The Lennox furnace could heat a 2,000 sq ft house. For 367 sq ft, it's a sledgehammer — but at 0°F outdoor, you need the sledgehammer.

![Lennox LF24-75A-5 ceiling-mounted furnace with gas supply piping and louvered vent](/static/photos/lennox-heater-overhead.jpg)

![Snow falling on the greenhouse at night — the heating system maintains 58°F+ inside while it's freezing outside](/static/photos/exterior-snow-falling-night.jpg)

<div class="grafana-controls" data-ranges="7d,30d,60d,90d,1y"></div>

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-heating/?orgId=1&panelId=3&theme=dark" width="100%" height="120px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-heating/?orgId=1&panelId=6&theme=dark" width="100%" height="120px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-heating/?orgId=1&panelId=8&theme=dark" width="100%" height="120px" frameborder="0"></iframe></div>
Gas dollars, therms burned, and average daily cost over the selected period. In January, 90% of the daily budget is gas. By April, heating nearly disappears from the bill.

## Runtime Distribution

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-heating/?orgId=1&panelId=19&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
The runtime bar chart tells the heating story at a glance. In winter, the gas furnace dominates the equipment list — 9+ hours per day in January. The electric heater runs longer (17+ hours) but at a fraction of the BTU output. Together: 80,120 BTU/hr of combined capacity. Absurd for 367 sq ft, but the polycarbonate's R-value of 1.639 leaks heat fast when it's 0°F outside.

## Gas Consumption vs Outdoor Temperature

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-heating/?orgId=1&panelId=21&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
The scaling curve. Gas consumption climbs linearly as outdoor temp drops — roughly 480 BTU/hr lost per degree of indoor-outdoor delta through ~785 sq ft of total glazing at U-value 0.61. Below 20°F outdoor, the furnace runs continuously overnight. Above 50°F, it doesn't fire at all.

## Heating Cascade

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-heating/?orgId=1&panelId=920&theme=dark" width="100%" height="400px" frameborder="0"></iframe></div>
Indoor temperature plotted against heater activation. When temp drops below 58°F, Heat1 (electric, orange dots) kicks on. If it keeps falling below 55°F, Heat2 (gas furnace, red dots) joins. The dashed blue line is the setpoint floor. Watch the overnight cycle: both heaters work in tandem against radiant loss through the polycarbonate. The outdoor temperature (gray) shows what the system is fighting against.

## The Thermal Envelope

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-heating/?orgId=1&panelId=9&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
Indoor vs outdoor temperature shows the envelope at work. The greenhouse retains 5–8°F above outdoor without heaters, thanks to:
1. **Polycarbonate insulation** — R-1.639, better than single glass (R-0.9)
2. **House connection** — the shared north wall leaks ~68°F house heat all night
3. **Concrete slab** — 367 sq ft of thermal mass storing and releasing solar heat
4. **Air volume** — 3,600+ cu ft of warm air takes time to cool
On moderate nights (50°F+ outdoor), the greenhouse holds above 67°F with zero heater assistance. The electric heater handles mild dips below 58°F. The gas furnace is the heavy artillery — and at 3.9× more cost-effective per BTU than electric, it's the economical choice when temperatures really drop.

## Staging Strategy

| Outdoor Temp | Indoor Response | Heater(s) | Cost |
|-------------|----------------|-----------|------|
| > 50°F | House heat + slab retention handle it | None | $0 |
| 40–50°F | Mild dips below 58°F | Heat1 (electric) | $0.167/hr |
| 20–40°F | Sustained cold | Heat1 + Heat2 (gas) | $0.79/hr |
| < 20°F | Both heaters run most of the night | Heat1 + Heat2 | $0.79/hr |

## Day/Night Temperature Differential

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-heating/?orgId=1&panelId=41&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
DIF — the difference between day and night temperatures — matters for plant growth. Heating creates the night temperature floor. A positive DIF (warm days, cool nights) promotes stem elongation. A negative DIF (cool days, warm nights) produces compact growth. The heating system's job is maintaining that floor at 55–58°F regardless of what's happening outside.

## Monthly Cost

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-heating/?orgId=1&panelId=10&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
The seasonal arc is stark. January peak: ~$270/month, almost entirely gas. By March, heating cost drops 60%+. By May, heating is essentially zero and the budget shifts entirely to cooling and lighting.

## Equipment

| Unit | Type | Output | Cost/hr | Stage Trigger |
|------|------|--------|---------|---------------|
| Heat1 (electric) | Space heater, 1,500W | 5,120 BTU/hr | $0.167 | temp < 58°F |
| Heat2 (Lennox LF24-75A-5) | Gas forced-air furnace | 75,000 BTU/hr | $0.623 | temp < 55°F |
Both controlled via ESP32 → PCF8574 → SSR-25DA relay chain.
> ⚠️ Heat1 has a **physical override switch** on the unit. Was accidentally left ON for 24+ hours on 2026-03-25 — ran continuously fighting the cooling system while the ESP32 thought it was off. The override bypasses the relay entirely.
→ See [Cooling](/climate/cooling/) for what happens when heating season ends and solar gain takes over.
→ See [Climate Overview](/climate/) for the full picture.
