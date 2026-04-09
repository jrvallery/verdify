---
title: Cooling & Ventilation
tags: [greenhouse, cooling, ventilation, equipment]
date: 2026-03-28
type: reference
fan_cfm_each: 2450
fan_cfm_total: 4900
air_exchange_seconds: 44
cooling_deficit_pct: 60-70
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Cooling & Ventilation

![Motorized louver vent for automated ventilation control](/static/photos/motorized-louver-vent.jpg)
*Part of [Climate at 5,000 Feet](/climate/) — the daytime solar gain side of the control problem.*
65,000–87,000 BTU/hr of solar heat enters through ~785 sq ft of glazing at peak. The fans can reject heat proportional to the indoor-outdoor temperature difference — 53,000 BTU/hr at a 10°F delta, but only 16,000 at 3°F. At 5,090 ft altitude, air is 17% less dense, further reducing ventilation effectiveness. On a 95°F day, equilibrium interior temperature will be 10–20°F above outdoor. This is physics, not a tuning problem.

![South end of the greenhouse — high-mounted KEN BROWN exhaust fans on the angled faces with overhead red mister nozzles](/static/photos/south-wall-fans-misters.jpg)

<div class="grafana-controls" data-ranges="7d,30d,60d,90d,1y"></div>

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-cooling/?orgId=1&panelId=2&theme=dark" width="100%" height="120" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-cooling/?orgId=1&panelId=5&theme=dark" width="100%" height="120" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-cooling/?orgId=1&panelId=8&theme=dark" width="100%" height="120" frameborder="0"></iframe></div>
Electricity spent, kilowatt-hours consumed, and average daily cost for the selected range.

## The Heat Source

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-cooling/?orgId=1&panelId=11&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
Solar radiation is the input side of the equation. The total glazed surface — walls above the 25.5" pony wall plus the entire peaked roof — is approximately 785 sq ft. At peak irradiance (886 W/m²), the glazing's SHGC of 0.66 admits 65,000–87,000 BTU/hr depending on effective sun-exposed area (which varies with sun angle throughout the day). The opal polycarbonate's SHGC exceeds its light transmission (0.66 vs 0.57) — the greenhouse admits proportionally more solar heat than visible photosynthetic light. This is why shade cloth on the roof and WSW wall blocks more heat than useful PAR — almost pure upside for summer.

## Where Cooling Fails

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-cooling/?orgId=1&panelId=11&theme=dark" width="100%" height="300" frameborder="0"></iframe></div>
Zone temperatures through the day. When all four lines climb together past 82°F, the cooling system is saturated. The south zone leads (narrowest wall, most direct sun), the east zone lags (tree shade + patio door). March 25 at 88°F outdoor produced a 96.5°F indoor peak. The all-time record is 100°F+.

## Indoor vs Outdoor Delta

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-cooling/?orgId=1&panelId=9&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
Watch the delta narrow on hot days. When outdoor temp is 90°F, indoor peaks at 97°F — only 7°F above ambient. The cooling system is working hard, but it's fighting thermodynamics. The fans move 4,900 CFM through 3,614 cu ft of space — a full air exchange every 44 seconds. At 5,090 ft altitude, each cubic foot of air carries 17% less thermal mass than at sea level, compounding the deficit.

## Cooling Cascade

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-cooling/?orgId=1&panelId=937&theme=dark" width="100%" height="450" frameborder="0"></iframe></div>
Temperature plotted against equipment activation. When temp rises past 82°F, Fan 1 kicks on. At 85°F, Fan 2 joins. If VPD spikes, misters start pulsing. At 87°F, fog engages as the last resort. This graph tells the full cascade story.

## Equipment Activity

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-cooling/?orgId=1&panelId=20&theme=dark" width="100%" height="400" frameborder="0"></iframe></div>
Fan and vent cycling in real time. The lead fan rotates every 6 hours for wear balance. Stage 1 (one fan + vent) kicks at 82°F. Stage 2 (both fans) at 85°F. Stage 3 (everything including evaporative fog) at 87°F. On a sunny March afternoon, the system lives in Stage 2–3 for hours.

## Runtime Trends

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-cooling/?orgId=1&panelId=17&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
Fan runtime hours correlate directly with solar radiation. Cloudy days: 2–3 hours of fan time. Clear days: 8–10 hours. The correlation is so tight you can predict tomorrow's fan runtime from the weather forecast.

## Cooling Stages

| State | Trigger | Equipment | Estimated Rejection |
|-------|---------|-----------|-------------------|
| COOL_S1 | temp > 82°F | Lead fan + vent | Variable: ~2,600 × ΔT BTU/hr |
| COOL_S2 | temp > 85°F | Both fans + vent | Variable: ~5,300 × ΔT BTU/hr |
| COOL_S3 | temp > 87°F | All cooling + evaporative fog | Variable: ~5,300 × ΔT + ~5,600 BTU/hr evaporative |
Fan cooling is not a fixed number — it depends on the temperature difference between indoor and outdoor air. At a 5°F delta, both fans reject ~26,500 BTU/hr. At a 10°F delta, ~52,900 BTU/hr. The fog machine adds a roughly constant ~5,600 BTU/hr of evaporative cooling.

## Equipment

| Unit | Spec | Power | Location |
|------|------|-------|----------|
| Fan1 / Fan2 | KEN BROWN 18" Shutter Exhaust, 2,450 CFM each | 52W each | High on the southwest and southeast angled walls |
| Vent | 24" × 24" mechanical actuator, screened | ~10W | North wall |
The 4 sq ft vent opening is the intake bottleneck — fans pull more air than it supplies. In summer, the patio door (east wall) becomes the **dominant** intake, creating an asymmetric east/NE-to-south airflow path rather than a clean north-to-south wash. West-side plants experience worse conditions as a result. HAF (horizontal air flow) circulation fans would significantly improve mixing.
→ See [Humidity](/climate/humidity/) for how the cooling/humidity tradeoff works — opening vents improves temperature but kills humidity.
→ See [Heating](/climate/heating/) for what happens when the sun goes down and the equation reverses.
