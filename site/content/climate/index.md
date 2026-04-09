---
title: Climate
tags: [greenhouse, climate, vpd, light, microclimates]
date: 2026-04-07
type: canonical
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Climate at 5,000 Feet

![The greenhouse at dusk, warm light through polycarbonate panels on the patio](/static/photos/exterior-dusk-patio.jpg)

![Winter snow on the patio, the greenhouse maintains growing conditions year-round at 4,979 feet elevation](/static/photos/exterior-winter-snow-lamppost.jpg)
What 5,000 feet of Colorado altitude and 785 sq ft of glazing teach you about the limits of climate automation.
This is the proof layer for the physical problem Verdify manages. Not the firmware, not the planner. The environment itself.
The greenhouse fights two battles almost every day:

- too much solar heat
- not enough humidity
That tension is the reason Verdify exists.

## Crop target bands vs reality

<div class="pg s1">

<iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=30&theme=dark&from=now-72h&to=now%2B72h" width="100%" height="350" frameborder="0"></iframe>

</div>
The green band is what the crops need, computed from the diurnal profiles of all five active crops. It follows a smooth daily cycle: narrow at night (62-65F), wide at peak sun (72-78F). The solid green line is observed indoor temperature. The solid gray line is outdoor temperature. Where the gray goes dashed, that is the 72-hour weather forecast. The gap between outdoor forecast and the crop band is the control problem the greenhouse has to solve every day.

<div class="pg s1">

<iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=31&theme=dark&from=now-72h&to=now%2B72h" width="100%" height="350" frameborder="0"></iframe>

</div>
VPD tells a different story. The target band is driven by outdoor humidity. When Longmont drops to 15% RH on a spring afternoon, no amount of misting can hold VPD in a tight range. The band widens to reflect that physical limit. When monsoon moisture arrives in late summer, the band tightens because humidity management gets easier. The right axis shows outdoor relative humidity so you can see exactly why the band changes shape.

## What this page should answer
1. What kind of climate problem is this greenhouse actually dealing with?
2. How do indoor conditions diverge from outdoor weather?
3. Which zones are hardest to hold, and when?
4. Why are spring and summer stressful in different ways?
5. What evidence shows the greenhouse is physically constrained, not just poorly controlled?

<div class="grafana-controls" data-ranges="7d,30d,60d,90d,1y"></div>

## The operating pressure

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=2&theme=dark" width="100%" height="120px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=108&theme=dark" width="100%" height="120px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=113&theme=dark" width="100%" height="120px" frameborder="0"></iframe></div>

<div class="pg s3"><iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=105&theme=dark" width="100%" height="120px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=106&theme=dark" width="100%" height="120px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=107&theme=dark" width="100%" height="120px" frameborder="0"></iframe></div>
These panels show the combined pressure the greenhouse lives under: heat, humidity demand, electricity, gas, water, and solar timing. They are not just utility numbers. They are the environmental load the system has to absorb.

## What has been running

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=19&theme=dark" width="100%" height="400px" frameborder="0"></iframe></div>
The equipment timeline is one of the clearest forms of evidence on the site. In winter, the heaters dominate overnight. In dry spring weather, fans, misters, and fog start stacking into the afternoon. The pattern tells you what kind of day the greenhouse had before you even read the narrative.

## Indoor versus outdoor

<div class="pg s2"><iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=9&theme=dark" width="100%" height="300px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=10&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
This is the core climate story.
On sunny days, indoor temperature can run 15 to 25°F above outdoor. That is the glazing and solar gain story, not a software bug. At the same time, Longmont can drop into the mid-teens for outdoor relative humidity on spring afternoons. Cooling wants outside air. Humidity hates outside air. That is the tension the planner and controller are working inside.

## VPD heatmap

<div class="pg s1"><iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=120&theme=dark" width="100%" height="350px" frameborder="0"></iframe></div>
This is one of the strongest proof panels on the site.
The counterintuitive result is that **March can be worse than August** for VPD stress. August gets monsoon moisture. March gets dry air plus strong solar. If you want to understand why this greenhouse is such a good proving ground, this chart is one of the best answers.

## Zone behavior

<div class="pg s2"><iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=11&theme=dark" width="100%" height="300px" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-climate/?orgId=1&panelId=12&theme=dark" width="100%" height="300px" frameborder="0"></iframe></div>
The greenhouse is not one climate.
South is the hardest hot-zone problem. East stays cooler because of tree shade and patio-door ventilation. West is flexible but swings harder in late afternoon. The heat spot rotates through the day, which means averages hide the real plant experience.

## The seasonal arc
Each season stresses a different part of the system.

- **Winter:** heating and overnight retention
- **Spring:** the hardest VPD season, because dry air and solar show up together
- **Summer:** peak solar gain and structural cooling limits
- **Fall:** the easiest balance point, with better cooling deltas and more forgiving humidity
That seasonal shift is part of what makes Verdify more than a thermostat project. The greenhouse is not solving one static control problem. It is living inside a moving climate regime.

## The cooling-humidity tradeoff
This is the central physical tradeoff.
Opening the greenhouse to cool it brings in dry outdoor air. Closing it to preserve humidity traps heat. Misters and fog help, but they do not erase the underlying physics. Some days are not “fixable” by better logic alone. They are only manageable.
That distinction matters. Verdify should be honest about when it is optimizing inside hard physical limits rather than pretending software can always win.

## Colorado at altitude
At roughly 5,000 feet, the greenhouse gets:

- strong solar load
- very dry afternoon air
- cold nights
- large daily swings
- thinner air, which weakens ventilation effectiveness
That combination is why this greenhouse is such a credible proof system. It is not a gentle environment.

## Where to go next
If you want the physical explanation for why the greenhouse behaves this way, go to [[greenhouse/structure|Physical Structure]] and [[greenhouse/growing|Growing in This Greenhouse]].
If you want the control-system explanation for how Verdify responds, go to:

- [[climate/controller|ESP32 Controller]]
- [[intelligence/planning|The Planning Loop]]
- [[intelligence/|How the AI Works]]
If you want subsystem-specific climate stories, go to:

- [[climate/heating|Heating]]
- [[climate/cooling|Cooling]]
- [[climate/humidity|Humidity & VPD]]
- [[climate/water|Water Systems]]
- [[climate/lighting|Lighting & DLI]]

The planning system reads this reality and writes tactical responses. See [How the AI Works](/intelligence/).
