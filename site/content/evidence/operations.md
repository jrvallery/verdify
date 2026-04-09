---
title: "Operations"
tags: [evidence, operations, live-status]
date: 2026-04-07
type: canonical
aliases:

  - dashboards/operations
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Operations
This is the live-status hub for Verdify.
If you want to know what the greenhouse is doing **right now**, whether the controller is behaving, whether the plan is being enforced, and whether anything needs intervention, start here.
This page is the operational bridge between:

- the **physical greenhouse**
- the **AI planning layer**
- the **deterministic controller**
- the **evidence trail** in telemetry, plans, and alerts

<div class="grafana-controls"></div>

## What this page should answer
1. **Is the system healthy right now?**
2. **What climate conditions are the plants actually experiencing?**
3. **What state is the controller in, and what equipment is running?**
4. **What plan is active, and is the greenhouse following it?**
5. **Do we need to intervene?**

## System health
Top-line indicators: health score, active alerts, controller uptime, connectivity, memory, and today's cost.

<div class="pg s6">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=2&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=3&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=4&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=5&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=6&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=7&theme=dark" width="100%" height="130" frameborder="0"></iframe>

</div>

## Climate now
The current sensor state across the greenhouse. This is the fastest way to see whether the plants are comfortable or drifting into stress.

<div class="pg s6">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=9&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=3&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=10&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=11&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=12&theme=dark" width="100%" height="130" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=14&theme=dark" width="100%" height="130" frameborder="0"></iframe>

</div>

## Equipment and controller state
This is where Verdify stops being a dashboard story and becomes a control-system story.
The panels below show which devices are running, how long the state machine has spent in each mode, and how the controller has transitioned through the day.

<div class="pg s1">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=9&theme=dark" width="100%" height="320" frameborder="0"></iframe>

</div>

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=16&theme=dark" width="100%" height="320" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=17&theme=dark" width="100%" height="320" frameborder="0"></iframe>

</div>

## Active plan
The greenhouse is not just reacting. It is following an explicit plan.
This panel shows the current climate plan that the controller is supposed to be enforcing, which makes it the key link between the reasoning layer and the physical environment.

<div class="pg s1">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=14&theme=dark" width="100%" height="320" frameborder="0"></iframe>

</div>

## Zone behavior
Average conditions are not enough in this greenhouse. The zones behave differently, and the operational view has to respect that.

<div class="pg s1">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=9&theme=dark" width="100%" height="350" frameborder="0"></iframe>

</div>

## Alerts and diagnostics
When something goes wrong, this is where you verify whether the issue is climate, hardware, controller state, or telemetry.

<div class="pg s2">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=17&theme=dark" width="100%" height="320" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-operations/?orgId=1&panelId=18&theme=dark" width="100%" height="320" frameborder="0"></iframe>

</div>

## How this fits the site
This page is the canonical operational entry point.
If you want:

- broader cost and executive framing, go to [[evidence/dashboards|Dashboards]]
- historical plan decisions, go to [[evidence/plans/|Daily Plans]]
- lessons extracted from incidents and experiments, go to [[intelligence/lessons|Lessons Learned]]
---

**Operational target:** high system health, fast alert response, safe controller behavior, and a greenhouse that follows the plan closely enough for the lessons to mean something.
[Open full dashboard ↗](https://graphs.verdify.ai/d/greenhouse-ops-command-center/)
