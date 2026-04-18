---
title: Water Systems
tags: [climate, irrigation, water, soil]
date: 2026-04-07
type: canonical
aliases:

  - climate/irrigation
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Water Systems

![Night rain on the patio, water management extends from irrigation inside to drainage outside](/static/photos/exterior-night-rain-reflections.jpg)
Water is doing two jobs in this greenhouse.
It feeds crops through wall drips and the [hydroponic NFT system](/greenhouse/hydroponics/), and it protects plant health indirectly by pushing back against Colorado's dry air through misting and fog. That makes irrigation a climate-control story, an operations story, and eventually a crop-performance story.
This page is the canonical water-systems page for the site.

<div class="grafana-controls" data-ranges="7d,30d,60d,90d,1y"></div>

## What this page should answer
1. How much water is the greenhouse using?
2. How much of that water is feeding plants versus conditioning the air?
3. Which zones are getting the most mister runtime, and why?
4. Is the irrigation system behaving efficiently and predictably?
5. Where are the current instrumentation gaps?

## Water now
Top-line indicators for gallons, cost, and current flow. Water is operationally important, but economically it is still the cheapest resource the greenhouse consumes.

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=4&theme=dark" width="100%" height="120px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=7&theme=dark" width="100%" height="120px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=8&theme=dark" width="100%" height="120px" frameborder="0"></iframe></div>
On a cool cloudy day, water use is mostly the scheduled wall-drip cycle. On a hot dry day, the misting system dominates. The budget impact is still modest, but the operational meaning is very different. Heavy water use usually means the greenhouse is fighting VPD, not overwatering crops.

## Daily water consumption

<div class="pg s2"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=7&theme=dark" width="100%" height="300px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=8&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
The left chart is the one that matters most. It shows the daily water story clearly, from low-use winter days to spring and summer spikes driven by humidity control. The cumulative chart is still useful for pattern reading, but the daily totals are the more honest view of operational load.

## Misting as climate control

<div class="pg s2"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=9&theme=dark" width="100%" height="300px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=10&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
The question is whether the water actually changed the climate. South and west pulses produce measurable VPD drops (0.15 and 0.13 kPa per pulse). Center still underperforms at 0.04 kPa, which makes it a hardware or geometry problem, not a planning problem.

![Pulse-output water flow meter on copper piping for automated consumption tracking](/static/photos/water-flow-meter.jpg)

![Drip irrigation emitters on potted herbs showing individual zone control](/static/photos/drip-irrigation-emitters.jpg)

## Flow, usage, and zone distribution

<div class="pg s2"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=7&theme=dark" width="100%" height="300px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=10&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=7&theme=dark" width="100%" height="260px" frameborder="0"></iframe></div>
The greenhouse can only run one mister zone at a time. That is a hard pressure constraint, not a software preference. South usually leads because it is the hottest and driest zone. The controller is routing limited water capacity toward the highest-stress part of the room first.

## Irrigation infrastructure

### Wall drip system
This is the crop-feeding side of the water system.

| Property | Value |
|----------|-------|
| Coverage | South + west wall shelves |
| Schedule | Daily at 6:00 AM, 10 minutes |
| Plumbing | Dual lines, clean water + parallel fertilizer |
| Control | ESP32 relay (clean: pcf_out_1 pin 4, fert: pcf_out_2 pin 0) |
One zone covers all south and west wall shelves, so software cannot allocate water plant by plant. Fine control happens physically at the drip heads.

### Fertigation
Every water zone has dual plumbing, a clean-water path and a fertilizer path through the fert tank. The relay selection determines which path is active, and a fert master valve gates all fertilizer delivery.

| Zone | Clean Relay | Fert Relay |
|------|------------|------------|
| Wall drip | pcf_out_1, pin 4 | pcf_out_2, pin 0 |
| South misters | pcf_out_1, pin 3 | pcf_out_1, pin 2 |
| West misters | pcf_out_1, pin 0 | pcf_out_1, pin 1 |
That means the same physical heads can either water, humidify, or deliver fertilizer depending on the active path. It is a practical system, but it also means the site should explain clearly when water is being used for plants versus air management.

## Water economics

| Resource | Rate | Hot Day (200 gal) | Cool Day (5 gal) |
|----------|------|-------------------|-------------------|
| Water | $0.00484/gal | $0.97 | $0.02 |
| Gas (Rinnai heater) | marginal | ~$0.10 | ~$0.01 |
| **Total** | | **~$1.07** | **~$0.03** |
Water is cheap enough ($0.00484/gal) that the bill doesn't matter. The cost of water mistakes is plant stress, disease risk, or wasted humidity effort.

## Root Zone Monitoring
Three DFRobot soil probes buried in pots — for the first time, we can see what's happening below the surface and correlate it with atmospheric conditions above.

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=15&theme=dark" width="100%" height="200px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=16&theme=dark" width="100%" height="200px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=17&theme=dark" width="100%" height="200px" frameborder="0"></iframe></div>
Current soil moisture from all three probes — south 1 and south 2 in the canna lily pots (60–70%), west at ~50%. Watch for the sawtooth pattern: the 6 AM wall drip spikes moisture, then it declines through the day as plants transpire and soil evaporates. Steep drops on hot, high-VPD days; flat holds on cool, humid days.

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-water/?orgId=1&panelId=12&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
Soil moisture vs air VPD — when VPD spikes, plants draw more water from the soil. Diverging lines mean dual stress (atmospheric AND root zone) before visible symptoms appear.

| Probe | Model | Zone | Measures |
|-------|-------|------|----------|
| South 1 | DFRobot SEN0601 | South | Moisture, Temp, EC |
| South 2 | DFRobot SEN0600 | South | Moisture, Temp |
| West | DFRobot SEN0600 | West | Moisture, Temp |
These probes enable future demand-based irrigation: skip when wet, extend when dry, predict demand from VPD and ET₀ correlation, and schedule fertigation using EC trends.
→ See [Humidity & VPD](/climate/humidity/) for the atmospheric demand driving root zone drawdown.
→ See [Operations](/evidence/operations/) for live controller state and alerts.
