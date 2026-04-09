---
title: "Humidity & VPD"
tags: [climate, humidity, vpd, fog, misters]
date: 2026-04-07
type: reference
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Humidity & VPD

![South wall exhaust fans with misting nozzle line for evaporative cooling](/static/photos/south-wall-fans-misters.jpg)
Humidity is the hardest day-to-day control problem in this greenhouse.
Not because the greenhouse is wet, but because Colorado spring and summer air can be brutally dry at exactly the same time solar gain is pushing temperatures up. That combination drives VPD high fast, especially in the south zone.
This page is about that problem as an environmental reality first, and only secondarily about the hardware used to fight it.

## What this page should answer
1. Why is humidity such a hard problem here?
2. Why does VPD matter more than relative humidity by itself?
3. What does the greenhouse humidity pattern actually look like?
4. How effective are misters and fog in practice?
5. Where does the humidity story overlap, but not duplicate, water systems and control logic?

<div class="grafana-controls" data-ranges="7d,30d,60d,90d,1y"></div>

## The core problem
The greenhouse is usually not fighting one variable at a time.
On hard spring days it is fighting:

- rising solar heat
- falling relative humidity
- strong plant transpiration demand
- dry intake air from outside
That is why VPD is the better lens. Relative humidity alone can look moderate while the actual evaporative demand on the plants is already punishing.

## VPD as the real signal

<div class="pg s2"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-humidity/?orgId=1&panelId=15&theme=dark" width="100%" height="300px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-humidity/?orgId=1&panelId=20&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
The left panel shows the greenhouse control view. The right panel shows the broader pattern over time.
This is the main thing to notice: the stress is not random. It ramps predictably with light and temperature, and it often peaks in the south zone before the room average looks catastrophic.

## How the humidity battle unfolds

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-humidity/?orgId=1&panelId=12&theme=dark" width="100%" height="320px" frameborder="0"></iframe></div>
The greenhouse tends to start mornings in a safe range, then lose ground as solar gain climbs and outdoor air gets drier. By early afternoon, the system is often trying to cool and humidify at the same time, which is exactly where the control tradeoff gets ugly.
That is why this page belongs next to Climate, not buried only under irrigation or equipment. Humidity here is not a side metric. It is one of the defining constraints of the whole greenhouse.

## Mister effectiveness

<div class="pg s2"><iframe src="https://graphs.verdify.ai/d-solo/site-climate-humidity/?orgId=1&panelId=9&theme=dark" width="100%" height="300px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate-humidity/?orgId=1&panelId=10&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
This is where the site earns credibility.
The question is not whether a mister fired. The question is whether it changed VPD enough to matter.
South and west produce real drops. Center still underperforms badly, which points to a physical geometry or nozzle issue, not just a planning issue. That distinction matters because it shows Verdify is measuring outcomes, not just issuing commands.

## The cooling-humidity conflict
Humidity control and cooling are often in conflict.

- ventilation helps temperature
- ventilation hurts humidity retention
- fog works best when the greenhouse is more closed
- misters work better than fog when the space is actively ventilating
That means the greenhouse is often choosing between two imperfect options rather than one correct one. Some afternoons are simply physics-limited. The right question becomes how to manage the damage, not how to eliminate it completely.

## The two humidity tools

### Fog machine
The AquaFog is the fast room-saturation tool.
It produces very fine droplets, fills the room quickly, and is most useful when vents are closed enough for that moisture to stay in the space. It is powerful, but not universally useful. If the greenhouse is ventilating hard, much of that fog is effectively lost.

### Micro mister system
The misters are the practical daytime humidity tool.
They produce heavier droplets that can still help while fans are running. That is why they matter so much on hard spring afternoons. They are not elegant, but they are the more operationally useful humidity system during active cooling.

## Why spring is worse than people expect
One of the most important Verdify findings is that spring can be more punishing than summer for humidity stress.
Summer brings higher heat, but it can also bring more atmospheric moisture. Spring in Colorado often combines strong sun with extremely dry air. That produces long VPD stress windows, even on days that do not look especially hot at first glance.

## Where this page fits
This page should explain the environmental humidity problem and show the evidence for it.
If you want the broader room-level behavior, go to [[climate/|Climate]].
If you want the water-use and fertigation side, go to [[climate/water|Water Systems]].
If you want the control logic that decides when misting and fogging happen, go to [[climate/controller|ESP32 Controller]] and [[intelligence/planning|The Planning Loop]].
The key point is simple: in this greenhouse, humidity is not just comfort. It is one of the main limiting factors on plant performance, and one of the clearest places where Verdify has to operate inside hard physical tradeoffs.
