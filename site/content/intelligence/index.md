---
title: Intelligence
tags: [intelligence, planning, ai, overview]
date: 2026-04-07
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">
<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# How the AI Works

![Security camera at the roof apex and exhaust fan on the south gable, part of the integrated monitoring and ventilation system](/static/photos/roof-camera-exhaust-fan.jpg)

Three times a day (6 AM, 12 PM, 6 PM Mountain), Gemini 3.1 Pro reads 14 sections of context about the greenhouse and writes a 72-hour tactical plan. It does not choose what the greenhouse should target. The crop target band does that, computed from the diurnal profiles of five active crops. The AI chooses how aggressively the controller chases those targets given the forecast. The ESP32 enforces it. The system scores itself. Lessons accumulate.

<div class="grafana-controls" data-ranges="7d,30d,60d"></div>

<div class="pg s3">
<iframe src="https://graphs.verdify.ai/d-solo/site-intelligence/?orgId=1&panelId=2&theme=dark" width="100%" height="120" frameborder="0"></iframe>
<iframe src="https://graphs.verdify.ai/d-solo/site-intelligence/?orgId=1&panelId=3&theme=dark" width="100%" height="120" frameborder="0"></iframe>
<iframe src="https://graphs.verdify.ai/d-solo/site-intelligence/?orgId=1&panelId=4&theme=dark" width="100%" height="120" frameborder="0"></iframe>
</div>

## The Loop

Every plan follows the same cycle: gather 14 sections of context (current conditions, equipment state, 24-hour history, stress data, 72-hour forecast, the crop target band, active crops, validated lessons, previous plan, disease risk, DIF). Reason across all of it. Write tactical waypoints for hysteresis, mister timing, fan staging, and water budgets across 72 hours. Score the previous plan. Extract a lesson if something unexpected happened.

The crop target band tells the planner what the ESP32 will be targeting at every hour of the planning horizon. The forecast tells it what conditions the greenhouse will face. The planner's job is to bridge the gap between the two.

Between cycles, a forecast deviation monitor watches for conditions that diverge from predictions (temperature off by 5F+, humidity off by 15%+, solar off by 200 W/m2+). If something shifts hard enough, it triggers an unscheduled replan.

## What the AI Optimizes

<div class="pg s1">
<iframe src="https://graphs.verdify.ai/d-solo/site-intelligence/?orgId=1&panelId=30&theme=dark&from=now-72h&to=now%2B72h" width="100%" height="350" frameborder="0"></iframe>
</div>

The green band is what the crops need, computed from horticultural profiles for all five active crops. It follows the diurnal cycle: narrow at night, wide at solar peak. The solid green line is observed indoor temperature. The gray dashed line is the 72-hour outdoor forecast. The planner's job is to choose tactical parameters (hysteresis, mister timing, fan bursts) that keep the green line inside the band while spending as little energy as possible.

<div class="pg s1">
<iframe src="https://graphs.verdify.ai/d-solo/site-intelligence/?orgId=1&panelId=31&theme=dark&from=now-72h&to=now%2B72h" width="100%" height="350" frameborder="0"></iframe>
</div>

VPD is the harder problem. Temperature responds to fans and vents. VPD responds to humidity, which the greenhouse can only partially control. On dry days (outdoor RH below 20%), the planner knows the band must widen because misters alone cannot hold VPD down. The AI's tactical setpoints may intentionally differ from the target band: pre-misting before a VPD spike, or tolerating a brief excursion to save water. The KPI is simple: maximize time in-band, minimize cost.

## The Split

AI reasons about what should happen. The controller enforces how to do it safely. If the AI goes offline, the ESP32 keeps the last setpoints and runs autonomously. The greenhouse never depends on cloud availability.

## The Learning

Every plan is a hypothesis. The planner asks: what did I expect? What actually happened? Lessons start at low confidence and graduate to high as patterns get re-confirmed. High-confidence lessons are mandatory. The system has 13 validated lessons so far, from "60-second mister pulses outperform 120-second" to "the dispatcher sometimes silently drops parameters in batch pushes."

## Infrastructure

The entire stack runs locally on a single VM: TimescaleDB (2.5M+ rows), Grafana (54 dashboards), a FastAPI crop catalog, and a Mosquitto MQTT broker. The ESP32 connects via encrypted native API for real-time data and MQTT for state publishing. Gemini 2.5 Pro handles 72-hour planning via Google AI Studio. No cloud infrastructure — just an API key.

## Go Deeper

- **[The Planning Loop](/intelligence/planning/)** : context gathering, reasoning, waypoint generation, dispatch, learning
- **[Lessons Learned](/intelligence/lessons/)** : 13 validated findings from the planning loop
- **[What's Broken](/intelligence/broken/)** : known issues, workarounds, and things we haven't fixed yet
- **[Data Pipeline](/intelligence/data/)** : 44 tables, 54 views, 23 functions in TimescaleDB
