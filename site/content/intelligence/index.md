---
title: Intelligence
tags: [intelligence, planning, ai, overview]
date: 2026-04-07
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">
<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# How the AI Works

![Security camera at the roof apex and exhaust fan on the south gable, part of the integrated monitoring and ventilation system](/static/photos/roof-camera-exhaust-fan.jpg)

At every solar milestone — sunrise, peak stress, tree shade, decline, sunset — an AI agent named Iris (Claude Opus 4.6) reviews greenhouse conditions and adjusts 24 tunables that shape the controller's response. She does not choose what the greenhouse should target. The crop target band does that, computed from the diurnal profiles of five active crops. Iris chooses how aggressively the controller chases those targets given the forecast. The ESP32 enforces it. The system scores itself. Lessons accumulate.

<div class="grafana-controls" data-ranges="7d,30d,60d"></div>

<div class="pg s3">
<div class="grafana-lazy" data-src="https://graphs.verdify.ai/d-solo/site-intelligence/?orgId=1&panelId=2&theme=dark" data-width="100%" data-height="120" style="width:100%;height:120;background:#111;border-radius:4px;"></div>
<div class="grafana-lazy" data-src="https://graphs.verdify.ai/d-solo/site-intelligence/?orgId=1&panelId=3&theme=dark" data-width="100%" data-height="120" style="width:100%;height:120;background:#111;border-radius:4px;"></div>
<div class="grafana-lazy" data-src="https://graphs.verdify.ai/d-solo/site-intelligence/?orgId=1&panelId=4&theme=dark" data-width="100%" data-height="120" style="width:100%;height:120;background:#111;border-radius:4px;"></div>
</div>

## The Loop

Every planning event follows the same cycle: gather 30 sections of context (current conditions, equipment state, 24-hour history, stress data, 72-hour forecast, the crop target band, active crops, validated lessons, previous plan, disease risk, DIF, scorecard). Reason across all of it. Adjust tactical tunables for hysteresis, mister timing, fan staging, and water budgets via MCP tools. Score the previous plan. Extract a lesson if something unexpected happened.

The crop target band tells Iris what the ESP32 will be targeting at every hour. The forecast tells her what conditions the greenhouse will face. Her job is to bridge the gap between the two.

Between milestones, a forecast deviation monitor watches for conditions that diverge from predictions (temperature off by 5°F+, humidity off by 15%+, solar off by 200 W/m²+). If something shifts hard enough, Iris responds immediately.

## What the AI Optimizes

<div class="pg s1">
<div class="grafana-lazy" data-src="https://graphs.verdify.ai/d-solo/site-intelligence/?orgId=1&panelId=30&theme=dark&from=now-72h&to=now%2B72h" data-width="100%" data-height="350" style="width:100%;height:350;background:#111;border-radius:4px;"></div>
</div>

The green band is what the crops need, computed from horticultural profiles for all five active crops. It follows the diurnal cycle: narrow at night, wide at solar peak. The solid green line is observed indoor temperature. The gray dashed line is the 72-hour outdoor forecast. The planner's job is to choose tactical parameters (hysteresis, mister timing, fan bursts) that keep the green line inside the band while spending as little energy as possible.

<div class="pg s1">
<div class="grafana-lazy" data-src="https://graphs.verdify.ai/d-solo/site-intelligence/?orgId=1&panelId=31&theme=dark&from=now-72h&to=now%2B72h" data-width="100%" data-height="350" style="width:100%;height:350;background:#111;border-radius:4px;"></div>
</div>

VPD is the harder problem. Temperature responds to fans and vents. VPD responds to humidity, which the greenhouse can only partially control. On dry days (outdoor RH below 20%), the planner knows the band must widen because misters alone cannot hold VPD down. The AI's tactical setpoints may intentionally differ from the target band: pre-misting before a VPD spike, or tolerating a brief excursion to save water. The KPI is simple: maximize time in-band, minimize cost.

## The Split

AI reasons about what should happen. The controller enforces how to do it safely. If the AI goes offline, the ESP32 keeps the last setpoints and runs autonomously. The greenhouse never depends on cloud availability.

## The Learning

Every plan is a hypothesis. The planner asks: what did I expect? What actually happened? Lessons start at low confidence and graduate to high as patterns get re-confirmed. High-confidence lessons are mandatory. The system has 75 lessons so far, from "60-second mister pulses outperform 120-second" to "thermal relief venting at 18% outdoor RH destroys all misting gains in under 2 minutes."

## Infrastructure

The entire stack runs locally on a single VM: TimescaleDB (2.5M+ rows), Grafana (54 dashboards), a FastAPI crop catalog, an MCP server (9 greenhouse tools), and a Mosquitto MQTT broker. The ESP32 connects via encrypted native API for real-time data and MQTT for state publishing. Iris (Claude Opus 4.6) handles event-driven planning via OpenClaw. No cloud infrastructure, just an API key.

## Go Deeper

- **[System Architecture](/intelligence/architecture/)** : the complete loop — ESP32, ingestor, database, MCP, Iris, dispatch
- **[The Planning Loop](/intelligence/planning/)** : context gathering, reasoning, tunable adjustment, dispatch, learning
- **[Lessons Learned](/intelligence/lessons/)** : validated findings from the planning loop
- **[What's Broken](/intelligence/broken/)** : known issues, workarounds, and things we haven't fixed yet
- **[Data Pipeline](/intelligence/data/)** : 47 tables, 56 views, 100+ functions in TimescaleDB
