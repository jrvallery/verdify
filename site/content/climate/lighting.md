---
title: Lighting
tags: [greenhouse, lighting, dli, equipment]
date: 2026-04-07
type: reference
total_fixtures: 49
total_wattage: 1446
cost_per_hour: 0.161
grow_circuit_fixtures: 34
grow_circuit_wattage: 816
main_circuit_fixtures: 15
main_circuit_wattage: 630
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Lighting

![Interior grow lights visible from outside, the greenhouse runs supplemental lighting into the evening](/static/photos/exterior-night-patio-lights.jpg)
The greenhouse has plenty of light available. The problem is when and where it arrives. Morning tree shade, afternoon transmission losses, and a sensor that saturates at 28,000 lux create gaps that 49 LED fixtures fill.
It is not the place to explain all of Verdify's planning logic. The question here is simpler: **what light do the plants actually get, where does it fall short, and what hardware makes up the difference?**

## What this page should answer
1. How much supplemental lighting does the greenhouse have?
2. Why does this greenhouse need lights even with so much glazing?
3. What does the DLI picture look like, and where are the sensor limitations?
4. How are the two lighting circuits physically different?
5. What should readers understand before over-interpreting the light charts?

<div class="grafana-controls" data-ranges="7d,30d,60d,90d,1y"></div>

## The lighting system at a glance
49 Barrina fixtures, **1,446W total**, about **$0.161/hour** at the current electric rate.
The lights are not there because the greenhouse is dark. They are there because the greenhouse has two repeatable shadow windows:

- the east-side tree blocks useful morning light until roughly 10:30 AM
- late-day sun drops below an effective transmission angle
That means the lighting system is less about brute-force indoor farming and more about smoothing a highly uneven natural light profile.

## Cost and solar context

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-lighting/?orgId=1&panelId=2&theme=dark" width="100%" height="120px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-lighting/?orgId=1&panelId=5&theme=dark" width="100%" height="120px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-lighting/?orgId=1&panelId=1&theme=dark" width="100%" height="120px" frameborder="0"></iframe></div>
Lighting is one of the major electrical loads in the greenhouse, but it is also one of the easiest to align with solar production. That matters. Supplemental light is much easier to justify when it lands during strong daytime generation than when it leans on nighttime storage.

## When the lights run

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-lighting/?orgId=1&panelId=4&theme=dark" width="100%" height="250px" frameborder="0"></iframe></div>
The runtime pattern tells the real story. Lights come on in the morning shadow window, ease off during the best natural-light hours, and often return as afternoon transmission falls away. Cloudy days stretch runtime longer. Clear days compress it.

## Daily runtime and DLI

<div class="pg s2"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-lighting/?orgId=1&panelId=5&theme=dark" width="100%" height="300px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-lighting/?orgId=1&panelId=9&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
Runtime matters, but the more important plant-facing metric is DLI.
The key caveat is that the current indoor lux sensor is unreliable. It saturates, misses morning light because of placement, and cannot see the grow lights properly. So the raw sensor DLI is not the real crop-light story.

| Metric | Value |
|--------|-------|
| Sensor-reported DLI | ~5–7 mol/m²/d |
| Estimated actual plant DLI | ~17–27 mol/m²/d |
| Estimated grow-light contribution | ~8–12 mol/m²/d |
That is why this page should be read carefully. The greenhouse is not actually as light-starved as the raw sensor trace suggests.

## Indoor versus outdoor light

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-lighting/?orgId=1&panelId=11&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
This chart is useful mostly as a relationship view, not a precision measurement tool. Outdoor light gives the cleaner baseline. Indoor light needs to be interpreted through glazing transmission, tree shade, fixture timing, and sensor failure modes.

## Crop-facing DLI context

| Crop | Minimum DLI | More comfortable range | Notes |
|------|--------------|------------------------|-------|
| Lettuce | 12 | 14–17 | Usually heat-limited before light-limited here |
| Herbs | 12 | 15–20 | Light is usually adequate; heat and placement matter more |
| Strawberries | 12 | 17–22 | Good fit for the east hydro zone |
| Peppers | 15 | 20–30 | South zone can support them if heat is managed |
| Tomatoes | 15 | 20–30 | Strong light, but also strong heat demand |
| Cucumbers | 15 | 20–25 | Good candidate for west-zone production |
The practical takeaway is that light is usually not the main limiting factor in this greenhouse. Heat and VPD are more often the real constraint.

## Two circuits, two jobs

### Grow circuit, 34× 2FT fixtures, 816W
This is the close-range crop-support circuit.

| Location | Count | Watts |
|----------|-------|-------|
| Hydro top row | 7 | 168W |
| Hydro bottom row | 7 | 168W |
| East wall shelves | 5 | 120W |
| West wall shelves | 15 | 360W |
These fixtures are doing the direct plant work over hydro lanes and shelf crops.

### Main circuit, 15× 4FT fixtures, 630W
This is the broader ambient overhead circuit.
Mounted on the west-wall rafters, these fixtures help flatten the room's uneven natural-light profile and support the wider production aisle.

## What this page is not
This page is not the full intelligence story.
If you want to understand how Verdify decides when to run lights, go to [[intelligence/planning|The Planning Loop]].
If you want the broader greenhouse light-and-structure context, go to [[greenhouse/structure|Physical Structure]] and [[greenhouse/growing|Growing in This Greenhouse]].
If you want the crop-facing interpretation, go to [[greenhouse/crops/|Crops]].
The main thing to keep in view is simple: the greenhouse has plenty of light potential, but it arrives unevenly. The lighting system exists to turn that uneven light environment into something more agriculturally usable.
