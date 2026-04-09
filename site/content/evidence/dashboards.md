---
title: Dashboards
tags: [evidence, dashboards, observability]
date: 2026-04-07
aliases:

  - dashboards/owner
  - dashboards/grower
  - dashboards/hvac
  - dashboards/climatologist
  - dashboards/compliance
  - dashboards/sustainability
  - dashboards/irrigation
  - dashboards/ipm
  - dashboards/agronomist
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Dashboards
Verdify's dashboards are the public proof layer. They are evidence surfaces, not the product by themselves.
For real-time system status, start with [Operations](/evidence/operations/).
For cost and resource proof, go to [Economics](/evidence/economics/).

<div class="grafana-controls" data-ranges="7d,30d,60d,90d,1y"></div>

## Primary views

### Owner view
The executive view: is the greenhouse healthy, what is it costing, are the zones behaving, and is anything drifting?

<div class="pg s3">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=2&theme=dark" width="100%" height="120" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=3&theme=dark" width="100%" height="120" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=5&theme=dark" width="100%" height="120" frameborder="0"></iframe>

</div>

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=9&theme=dark" width="100%" height="300" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=11&theme=dark" width="100%" height="300" frameborder="0"></iframe>

</div>
[Open full Owner dashboard ↗](https://graphs.verdify.ai/d/greenhouse-owner-overview/)

### Grower view
The operator's view: today's tasks, zone conditions, weather context, irrigation status, and active alerts.

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=2&theme=dark" width="100%" height="300" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=9&theme=dark" width="100%" height="300" frameborder="0"></iframe>

</div>

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=11&theme=dark" width="100%" height="300" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=12&theme=dark" width="100%" height="300" frameborder="0"></iframe>

</div>
[Open full Grower dashboard ↗](https://graphs.verdify.ai/d/greenhouse-grower-daily/)

## Specialist overlays
These are supporting analytical lenses, not first-class site narratives.

### HVAC
Setpoint compliance and equipment performance.

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=7&theme=dark" width="100%" height="300" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=8&theme=dark" width="100%" height="300" frameborder="0"></iframe>

</div>
[Open full HVAC dashboard ↗](https://graphs.verdify.ai/d/greenhouse-hvac-climate/)

### Climatologist
Indoor versus outdoor relationships and forecast behavior.

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=9&theme=dark" width="100%" height="300" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=14&theme=dark" width="100%" height="300" frameborder="0"></iframe>

</div>
[Open full Climatologist dashboard ↗](https://graphs.verdify.ai/d/greenhouse-climatologist-weather/)

### Compliance
Controller state tracking and timing validation.

<div class="pg s1">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=10&theme=dark" width="100%" height="230" frameborder="0"></iframe>

</div>
[Open full Control Loop dashboard ↗](https://graphs.verdify.ai/d/greenhouse-control-loop/)

### Plant health
Growth metrics, VPD stress, and disease-risk context.

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=8&theme=dark" width="100%" height="300" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=13&theme=dark" width="100%" height="300" frameborder="0"></iframe>

</div>
[Open full Plant Health dashboard ↗](https://graphs.verdify.ai/d/greenhouse-plant-health/)

## What changed in the reorg
This page no longer treats sustainability as a standalone top-level dashboard story. Cost and resource proof now belong primarily on [[evidence/economics|Economics]].
The dashboard directory remains useful, but mostly as a way to browse supporting views after the stronger canonical pages have already framed the story.
