---
title: System Architecture
tags: [intelligence, architecture, esp32, iris, mcp]
date: 2026-04-11
type: reference
aliases:
  - architecture
---

# System Architecture

Everything runs on a single VM. No cloud infrastructure. The only external dependencies are API keys for the AI models. The greenhouse operates autonomously — if the AI goes offline, the ESP32 keeps the last setpoints and runs on its own.

## The Complete Loop

```mermaid
graph TB
    subgraph ESP["ESP32 Controller"]
        direction TB
        MODE["7-Mode Controller<br/><i>greenhouse_logic.h</i><br/>5-second eval loop"]
        RELAY["Relay Outputs<br/>fans, heaters, vent,<br/>misters, fog"]
        MODE --> RELAY
    end

    subgraph INGEST["Ingestor Service"]
        direction TB
        API_SUB["aioesphomeapi<br/>172 entity subscription"]
        TASKS["13 periodic tasks<br/>(60s-86400s intervals)"]
        DISPATCH["Setpoint Dispatcher<br/>(every 5 min)"]
    end

    subgraph DB["TimescaleDB"]
        direction TB
        CLIMATE["climate<br/>2.5M+ rows"]
        SETPOINTS["setpoint_changes"]
        VIEWS["56 analytical views"]
        SCORECARD["fn_planner_scorecard()"]
    end

    subgraph MCP["MCP Server"]
        direction TB
        TOOLS["18 tools:<br/>climate, scorecard, equipment,<br/>forecast, get_setpoints, set_tunable,<br/>set_plan, plan_evaluate, plan_status,<br/>history, crops, observations,<br/>alerts, lessons_manage, query,<br/>plan_run, record_observation"]
    end

    subgraph IRIS["Iris Planner (Opus 4.6)"]
        direction TB
        EVENTS["Event-driven triggers:<br/>sunrise, peak stress,<br/>tree shade, decline,<br/>sunset, forecast, deviation"]
        REASON["Reasoning + decisions<br/>24 Tier 1 tunables"]
        SLACK["Slack #greenhouse<br/>briefs + reasoning"]
    end

    subgraph GW["OpenClaw Gateway"]
        direction TB
        HOOK["Hook endpoint<br/>/hooks/agent"]
        SESSION["Persistent session<br/>conversation memory"]
    end

    ESP -->|"sensor data<br/>(encrypted)"| API_SUB
    API_SUB --> CLIMATE
    TASKS -->|"context assembly"| HOOK
    HOOK --> SESSION --> IRIS
    IRIS -->|"set_tunable()"| MCP
    MCP --> SETPOINTS
    DISPATCH -->|"push changed values"| ESP
    SETPOINTS --> DISPATCH
    CLIMATE --> VIEWS
    VIEWS --> SCORECARD
    MCP --> CLIMATE
    MCP --> VIEWS
    IRIS --> SLACK
    EVENTS --> REASON --> SLACK

    classDef hardware fill:#2d5016,stroke:#4a8c2a,color:#fff
    classDef service fill:#1a3a5c,stroke:#2980b9,color:#fff
    classDef data fill:#5c3a1a,stroke:#b97029,color:#fff
    classDef ai fill:#4a1a5c,stroke:#9b29b9,color:#fff

    class ESP hardware
    class INGEST,MCP,GW service
    class DB data
    class IRIS ai
```

## Three Layers

The system has three distinct control layers, each with a different time scale and responsibility:

### Layer 1: Crop Target Band (minutes)
Computed from the diurnal profiles of all active crops. Sets temp_low, temp_high, vpd_low, vpd_high every 5 minutes. Night: 62-65°F. Peak day: 72-78°F. The ESP32's mode thresholds follow the band automatically. Plant science defines what conditions the greenhouse should target.

### Layer 2: Iris Planner (hours)
An AI agent (Claude Opus 4.6) responds to solar milestones and environmental changes. Iris adjusts 24 Tier 1 tunables that shape how aggressively the controller responds: hysteresis widths, mister timing, fog thresholds, thermal biases. The planner decides how hard the system tries given the weather forecast. Every decision is posted to #greenhouse in Slack with reasoning.

### Layer 3: ESP32 Mode Controller (seconds)
7 priority-ordered modes evaluated every 5 seconds. Pure C++ (`greenhouse_logic.h`) compiles identically on ESP32 and x86. The mode controller enforces the band + tunables with physical equipment. If the AI goes offline, the ESP32 keeps its last setpoints.

```mermaid
graph LR
    CROP["🌱 Crop Science<br/><i>what to target</i><br/>band setpoints"] --> ESP["⚡ ESP32<br/><i>how to enforce</i><br/>7 modes, 5s loop"]
    AI["🧠 Iris<br/><i>how hard to try</i><br/>24 tunables"] --> ESP
    ESP --> EQUIP["🔧 Equipment<br/>fans, heaters, vent,<br/>misters, fog"]

    classDef science fill:#2d5016,stroke:#4a8c2a,color:#fff
    classDef ai fill:#4a1a5c,stroke:#9b29b9,color:#fff
    classDef hw fill:#1a3a5c,stroke:#2980b9,color:#fff
    classDef equip fill:#5c3a1a,stroke:#b97029,color:#fff

    class CROP science
    class AI ai
    class ESP hw
    class EQUIP equip
```

## Event-Driven Planning

Instead of running on a fixed schedule, Iris responds to natural transition points in the greenhouse day. The ingestor computes solar milestones from ephemeris data each morning.

```mermaid
gantt
    title Iris Planning Events (typical spring day)
    dateFormat HH:mm
    axisFormat %H:%M

    section Events
    Sunrise (morning brief)         :milestone, 06:28, 0m
    Peak Stress (max aggression)    :milestone, 15:01, 0m
    Tree Shade (reduce misting)     :milestone, 17:01, 0m
    Decline (evening transition)    :milestone, 18:34, 0m
    Sunset (evening brief)          :milestone, 19:34, 0m

    section Reactive
    Forecast changes                :active, 06:00, 20:00
    Deviation alerts                :crit, 06:00, 20:00
```

**Sunrise and sunset** produce full planning briefs — yesterday's scorecard, today's forecast, tunable adjustments with reasoning. **Transitions** are brief — Iris checks conditions and adjusts only if needed. **Deviations** trigger immediate response when observed conditions diverge from forecast.

## Data Pipeline

172 sensor entities flow from the ESP32 through encrypted native API into TimescaleDB at sub-minute freshness:

| Source | Transport | Destination | Rate |
|--------|-----------|-------------|------|
| ESP32 sensors | aioesphomeapi (encrypted) | climate table | ~2s |
| ESP32 relays | aioesphomeapi | equipment_state table | on change |
| ESP32 mode | aioesphomeapi | system_state table | on change |
| Tempest weather | HA REST (transitional) | climate outdoor columns | 5 min |
| Open-Meteo forecast | HTTP API | weather_forecast table | 1 hour |
| Sentinel cameras | MQTT | occupancy → ESP32 | on change |
| Iris planner | MCP set_tunable() | setpoint_changes table | on event |
| Dispatcher | aioesphomeapi push | ESP32 tunables | 5 min |

## Planner Score (KPI)

Performance is measured by an automated composite score:

```mermaid
pie title Planner Score (0-100)
    "Compliance (80%)" : 80
    "Cost Efficiency (20%)" : 20
```

- **Compliance** = % of day with temp AND VPD inside crop band. Target: >90%.
- **Cost efficiency** = daily utility spend. <$5/day = full marks, $15+ = zero.
- **Stress hours** tracked as 4 independent states: heat, cold, VPD-high, VPD-low.
- Iris reviews the scorecard at every sunrise and sunset event.

## Physical Constraints

| Parameter | Value | Impact |
|-----------|-------|--------|
| Floor area | 367 sq ft | Elongated hexagon, 6 distinct microclimates |
| Elevation | 5,090 ft | 17% less air density, extreme VPD in spring |
| Solar gain | ~87,000 BTU/hr peak | Drives all thermal behavior |
| Cooling capacity | ~34,000-39,000 BTU/hr | 40% overstated due to altitude + undersized vent |
| Cooling deficit | ~49,000 BTU/hr | Physics-limited above 85°F without shade cloth |
| Intake vent | 24"x24" (4 sq ft) | Critically undersized for 4,900 CFM |
| AquaFog | 800W, 7× mister effectiveness | Centrifugal atomizer, 4-25μm droplets |
| Gas heater | 54,000 BTU/hr actual | Altitude-derated 20%, 3.9× cheaper than electric |
| Slab thermal mass | ~7,300 BTU/°F | 11.5h time constant, 7-10°F overnight retention |

The system doesn't pretend these limits don't exist. The AI knows the cooling deficit. It knows fog is 7× more effective than misters. It plans around physics, not through it.

---

**Deeper dives:** [The Planning Loop](/intelligence/planning/) · [ESP32 Controller](/climate/controller/) · [Lessons Learned](/intelligence/lessons/)
