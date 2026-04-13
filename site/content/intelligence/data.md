---
title: "Data Model"
tags: [intelligence, database, timescaledb]
date: 2026-04-07
type: reference
tables: 47
views: 56
functions: 100
aliases:

  - data-model
rows_climate: 221000
rows_energy: 516000
---

<link rel="stylesheet" href="/static/grafana-controls.f0ea8065.css">

<script src="/static/grafana-controls.f0ea8065.js" defer></script>

# Data Model

![Tzone RS485 climate probe mounted in the south zone — one of six sensors feeding the data pipeline](/static/photos/tzone-sensor-south.jpg)

The data pipeline: ESP32 sensors publish state changes over aioesphomeapi (encrypted, port 6053). The ingestor maps 172 entities to 128 database columns and writes them to TimescaleDB in near real-time. Twelve periodic tasks enrich the data: outdoor weather from Open-Meteo, energy from a Shelly EM50, forecasts, alert monitoring, and band-driven setpoint dispatch. Everything runs locally on a single VM.

TimescaleDB (PostgreSQL 16 + hypertables) stores every measurement, event, plan, and observation.

## Core Tables

| Table | Type | Rows | Write Pattern |
|-------|------|------|---------------|
| `climate` | Hypertable | 221K+ | ~2 min batch (ESP32 sensors + outdoor merge) |
| `equipment_state` | Hypertable | 39K+ | Event-driven (relay changes) |
| `energy` | Hypertable | 516K+ | Every 5 min (Shelly EM50) |
| `setpoint_changes` | Hypertable | — | Event-driven (ESP32 reports + plan pushes) |
| `setpoint_plan` | Hypertable | 144+ | 3× daily (AI planner waypoints) |
| `weather_forecast` | Hypertable | 28K+ | Hourly (Open-Meteo, 16-day, 27 columns) |
| `daily_summary` | Regular | 236 | Nightly snapshot |
| `diagnostics` | Hypertable | — | ~60s (ESP32 health) |

## Crop & Operations Tables

| Table | Purpose | Status |
|-------|---------|--------|
| `crops` | Active plantings with position, zone, stage | 3 records |
| `crop_events` | Stage changes, transplants, harvests | Empty (awaiting operator input) |
| `observations` | Pest scouting, visual notes, camera assessments | Empty |
| `treatments` | Spray/biological applications with PHI/REI | Empty |
| `harvests` | Yield records | Empty |
| `plan_journal` | Per-plan hypothesis, outcome, score | 12 entries |
| `planner_lessons` | Validated patterns from planning cycles | 75 lessons |

## Key Views (56 total)

| View | Purpose |
|------|---------|
| `v_greenhouse_now` | Single-row snapshot: all zones, hydro, costs, health |
| `v_equipment_now` | Current state of all 33 equipment items |
| `v_cost_today` | Real-time electric + gas + water cost |
| `v_active_plan` | Resolves plan supersession (latest waypoint per parameter) |
| `v_stress_hours_today` | Hours above/below target bands per day |
| `v_disease_risk` | Botrytis + condensation risk from RH/temp/VPD |
| `v_mister_effectiveness` | VPD drop per pulse by zone, with outdoor context |
| `v_forecast_vs_actual` | Hourly forecast accountability (bias detection) |
| `v_indoor_outdoor_correlation` | Thermal gain coefficient |
| `v_state_durations` | Time-in-state per day |
| `v_estimated_plant_dli` | Corrected DLI estimate (sensor × correction factor) |

## Key Functions

| Function | Returns |
|----------|---------|
| `fn_equipment_health()` | 0–100 composite health score |
| `fn_stress_summary(date)` | Human-readable stress text |
| `fn_system_health()` | 4-component health: sensors, alerts, equipment, controller |
| `fn_compliance_pct()` | % time within target bands |
| `fn_forecast_dli()` | Predicted natural DLI from forecast radiation |
| `fn_forecast_correction()` | Rolling 7-day bias per forecast parameter |

<div class="grafana-controls"></div>

<div class="pg s2"><div class="grafana-lazy" data-src="https://graphs.verdify.ai/d-solo/site-intelligence-data/?orgId=1&panelId=13&theme=dark" data-width="100%" data-height="320px" style="width:100%;height:320px;background:#111;border-radius:4px;"></div>

<div class="grafana-lazy" data-src="https://graphs.verdify.ai/d-solo/site-intelligence-data/?orgId=1&panelId=17&theme=dark" data-width="100%" data-height="320px" style="width:100%;height:320px;background:#111;border-radius:4px;"></div></div>

<div class="pg s4"><div class="grafana-lazy" data-src="https://graphs.verdify.ai/d-solo/site-intelligence-data/?orgId=1&panelId=1&theme=dark" data-width="100%" data-height="130px" style="width:100%;height:130px;background:#111;border-radius:4px;"></div>

<div class="grafana-lazy" data-src="https://graphs.verdify.ai/d-solo/site-intelligence-data/?orgId=1&panelId=2&theme=dark" data-width="100%" data-height="130px" style="width:100%;height:130px;background:#111;border-radius:4px;"></div>

<div class="grafana-lazy" data-src="https://graphs.verdify.ai/d-solo/site-intelligence-data/?orgId=1&panelId=3&theme=dark" data-width="100%" data-height="130px" style="width:100%;height:130px;background:#111;border-radius:4px;"></div>

<div class="grafana-lazy" data-src="https://graphs.verdify.ai/d-solo/site-intelligence-data/?orgId=1&panelId=4&theme=dark" data-width="100%" data-height="130px" style="width:100%;height:130px;background:#111;border-radius:4px;"></div></div>

## Compression & Retention

| Table | Compression | Retention |
|-------|------------|-----------|
| climate | 7 days | 365 days |
| energy | 7 days | 365 days |
| diagnostics | 7 days | 180 days |
| esp32_logs | — | 30 days |

---

## Where to Go Next

- [Planning Loop](/intelligence/planning/) — how the AI planner reads this data and writes setpoints
- [Operations](/evidence/operations/) — live health checks and data freshness monitoring
- [Lessons Learned](/intelligence/lessons/) — what the data has taught us about greenhouse control
