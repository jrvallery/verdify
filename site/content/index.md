---
title: Verdify
tags: [home]
date: 2026-04-08
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">
<script src="/static/grafana-controls.f0ea8065.js" defer></script>

<div style="text-align: center; margin: 2rem 0;">

# Verdify

## What if a greenhouse could learn?

**367 sq ft. Longmont, Colorado. 5,090 feet. 15% humidity. 95F solar peaks. Six crops. One AI.**

172 sensors feed a 42-state climate machine that evaluates conditions every 5 seconds. Crop profiles define what each zone needs at each hour. Gemini plans 72 hours ahead, three times a day. The system measures every outcome, scores every plan, and gets better.

</div>

<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 1.5rem 0;">

![The greenhouse glowing through snowfall on a winter night](/static/photos/exterior-night-snow.jpg)

![Greenhouse interior with grow lights, hydroponic channels, and production shelving](/static/photos/interior-full-view.jpg)

</div>

<div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin: 1.5rem 0; text-align: center; font-size: 0.85rem;">
<div>

**2.4M+**
sensor readings

</div>
<div>

**247**
days operational

</div>
<div>

**3,116**
plans written

</div>
<div>

**15**
lessons validated

</div>
</div>

Crop profiles define what each zone needs at each hour. An ESP32 state machine enforces those targets across fans, heaters, misters, and fog. Three times a day, Gemini reads the forecast, the crop band, per-zone VPD stress, and what went wrong yesterday, then writes a tactical plan. The system measures every outcome and learns from every cycle.

<div class="grafana-controls" data-mode="none"></div>

<div class="pg s3" style="grid-template-columns: repeat(3, 1fr) !important;">
<iframe src="https://graphs.verdify.ai/d-solo/site-home/?orgId=1&panelId=2&theme=dark" width="100%" height="140" frameborder="0"></iframe>
<iframe src="https://graphs.verdify.ai/d-solo/site-home/?orgId=1&panelId=4&theme=dark" width="100%" height="140" frameborder="0"></iframe>
<iframe src="https://graphs.verdify.ai/d-solo/site-home/?orgId=1&panelId=108&theme=dark" width="100%" height="140" frameborder="0"></iframe>
</div>

## Temperature

<div class="grafana-controls" data-ranges="24h,Forecast,7d,30d"></div>

<div class="pg s1">
<iframe src="https://graphs.verdify.ai/d-solo/site-home/?orgId=1&panelId=30&theme=dark&from=now-72h&to=now%2B72h" width="100%" height="350" frameborder="0"></iframe>
</div>

The golden glow behind the data is solar irradiance through the glazing. It is the primary driver of indoor temperature, more predictive than outdoor air temperature. On a 65F day with 800 W/m2 of solar, the greenhouse will hit 85F. On the same 65F day under clouds, it stays at 70F. The AI plans around the solar forecast, not just the temperature forecast.

The green band is what the crops need, computed from diurnal profiles of six active crops. The solid green line is the 15-minute smoothed indoor temperature. Equipment dots at the bottom show the control response: fans (blue) engage when temperature exceeds the band, heaters (red) fire when it drops below, fog (purple) provides evaporative cooling at extremes.

## Humidity (VPD)

<div class="grafana-controls" data-ranges="24h,Forecast,7d,30d"></div>

<div class="pg s1">
<iframe src="https://graphs.verdify.ai/d-solo/site-home/?orgId=1&panelId=31&theme=dark&from=now-72h&to=now%2B72h" width="100%" height="350" frameborder="0"></iframe>
</div>

VPD is the metric that drives plant transpiration. Each mister zone has its own crop-driven target. When east zone lettuce is stressed at 1.0 kPa, the system mists adjacent zones to raise greenhouse humidity. When south zone cannas are comfortable at 1.5 kPa, those misters stay off. Equipment bars at the bottom show mister activity by zone (south, west, center) and fog. The AI adjusts pulse timing, water budgets, and vent coordination based on the forecast.

## Light & DLI

<div class="grafana-controls" data-ranges="24h,Forecast,7d,30d"></div>

<div class="pg s1">
<iframe src="https://graphs.verdify.ai/d-solo/site-home/?orgId=1&panelId=35&theme=dark&from=now-24h&to=now%2B24h" width="100%" height="350" frameborder="0"></iframe>
</div>

The golden background is solar irradiance through the glazing. The green line is daily light integral (DLI) accumulation, which resets at midnight and climbs with the sun. The dashed line is the crop DLI target (the minimum the plants need). When natural light falls short, grow lights supplement. Yellow bars at the bottom show when the two grow light circuits are active. The dashed solar forecast shows what tomorrow's light budget looks like.

## Economics

<div class="pg s1">
<iframe src="https://graphs.verdify.ai/d-solo/site-home/?orgId=1&panelId=109&theme=dark&from=now-180d&to=now" width="100%" height="400" frameborder="0"></iframe>
</div>

Three utilities stacked: electricity (11.1 cents/kWh), natural gas (83 cents/therm), and water (0.48 cents/gal). Winter is gas-dominated. Spring shifts to electric cooling and water for misting. The AI optimizes across all three: gas heating overnight costs less per BTU than electric, fog during solar production hours is nearly free, and mister water is the cheapest resource but the most critical for VPD management.

<div class="pg s1">
<iframe src="https://graphs.verdify.ai/d-solo/site-home/?orgId=1&panelId=110&theme=dark&from=now-7d&to=now" width="100%" height="300" frameborder="0"></iframe>
</div>

Greenhouse power draw (watts) overlaid with solar irradiance. When the curves overlap, the greenhouse runs on solar. The Tesla Powerwall covers overnight demand. The entire software stack runs locally on a single VM.

<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 2rem; margin: 2rem 0;">
<div>

### [The Greenhouse](greenhouse/)
Structure, zones, equipment, what we grow

</div>
<div>

### [Climate & Control](climate/)
Heating, cooling, humidity, water, light, the ESP32

</div>
<div>

### [Intelligence](intelligence/)
Planning, lessons, data pipeline, known issues

</div>
<div>

### [Evidence](evidence/)
Operations, dashboards, economics, daily plans

</div>
<div>

### [About](about/)
The story behind the system

</div>
</div>
