---
title: Evidence
tags: [evidence, proof, dashboards, plans]
date: 2026-04-07
aliases:

  - dashboards
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Evidence
The system publishes what it does.

Verdify makes claims: the AI improved overnight compliance, mister stress-scoring cut water waste, the crop band drives better setpoints than static rules. This section is the proof layer. Four surfaces, each doing different work:

- **Operations** is the live feed. System health, controller state, data freshness, active alerts. If something is broken right now, it shows here.
- **Daily Plans** is the lab notebook. Every planning cycle archived with conditions, decisions, experiments, and self-scored outcomes. This is where the AI's reasoning becomes auditable.
- **Economics** is the cost truth. Actual utility consumption by type, daily and monthly, with the raw data behind every cost claim on the site.
- **Dashboards** is the analytical layer. Role-based views for the owner (economics, compliance), the grower (zone conditions, crop health), and the engineer (state machine, pipeline metrics).

If Verdify claims something, this section should make it possible to check.

<div class="grafana-controls"></div>

<div class="pg s3">

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=2&theme=dark" width="100%" height="120" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=5&theme=dark" width="100%" height="120" frameborder="0"></iframe>

<iframe src="https://graphs.verdify.ai/d-solo/site-evidence-dashboards/?orgId=1&panelId=6&theme=dark" width="100%" height="120" frameborder="0"></iframe>

</div>

## What you can verify
**[Operations](/evidence/operations/)** shows what the greenhouse is doing right now: system health, controller state, active plan, and zone conditions.
**[Daily Plans](/evidence/plans/)** archives planning cycles with conditions, decisions, experiments, and scores. This is the lab notebook layer.
**[Economics](/evidence/economics/)** shows actual resource and utility behavior. It is the canonical cost-and-efficiency proof page, not a side dashboard category.
**[Dashboards](/evidence/dashboards/)** provides the supporting browse layer: owner, grower, and specialist analytical overlays.

## Why this section matters
The greenhouse is the proof system for Verdify. That only works if the evidence layer stays stronger than the marketing layer.
This section is where the site earns trust.
