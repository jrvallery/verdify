# Verdify

**A public AI-assisted greenhouse control loop.**

367 sq ft. Longmont, Colorado. 5,090 feet. 15% humidity. 95°F solar peaks. Mixed crops. One deterministic controller.

About 172 ESPHome entities feed an 8-state firmware controller that evaluates conditions every 5 seconds. Crop profiles define what each zone needs at each hour. Iris uses Claude through OpenClaw to write bounded tactical plans at solar milestones and event triggers. The system measures outcomes, scores plans, and feeds validated lessons into future planning.

**[verdify.ai](https://verdify.ai)**

## Architecture

```
ESP32 Controller (8-state, greenhouse_logic.h, 5s loop)
  ├── aioesphomeapi ──→ Ingestor ──→ TimescaleDB (2.5M+ rows)
  ├── MQTT ──→ Mosquitto (state publishing + occupancy)
  └── HTTPS ──→ API (band-driven setpoints every 5 min)

TimescaleDB (telemetry, views, scorecards, lessons)
  ├── Grafana (public and private dashboards)
  ├── FastAPI (crop catalog + ESP32 setpoints)
  ├── MCP Server (typed tools for Iris)
  └── Quartz (static site with embedded panels)

Iris Planner (Claude via OpenClaw)
  └── Event-driven: sunrise, transitions, sunset, forecast, deviation
      → MCP tools → set_tunable() → Slack #greenhouse
```

The greenhouse control core runs on a single VM. External APIs provide planning, weather, and public delivery support; real-time relay control stays local.

## Components

| Directory | What |
|-----------|------|
| `ingestor/` | Python async service — ESP32 data capture, 15 periodic tasks, entity routing |
| `api/` | FastAPI crop catalog + ESP32 setpoint endpoint |
| `firmware/` | ESPHome YAML + C++ headers — 8-state climate controller (greenhouse_logic.h) |
| `mcp/` | FastMCP server — typed tools for Iris agent (climate, scorecard, set_tunable, etc.) |
| `scripts/` | Operational scripts — planner, vision analysis, forecast sync, monitoring |
| `provisioning/` | Grafana dashboard JSON + datasource config |
| `db/` | Schema, analytical views, functions, and migrations |
| `templates/` | Jinja2 planner prompt + reference docs |
| `config/` | AI model config, zone definitions |
| `tests/` | Smoke, drift, and integration tests |
| `site/` | Quartz static site source |

## Development

```bash
# Prerequisites: Docker, Python 3.13+, shared venv at /srv/greenhouse/.venv

# Run all checks (lint + test + firmware compile)
make check

# Individual commands
make lint              # Ruff linter (0 errors)
make format            # Auto-format Python
make test              # 83 smoke tests (~65s)
make firmware-check    # Compile ESP32 firmware
make planner-dry       # Render planner prompt (no API call)
make help              # List all targets
```

**Tooling:** ruff (lint + format), pytest, pre-commit hooks, GitHub Actions CI.
**Config:** `pyproject.toml` is the single source of truth for deps, lint rules, and test config.

## The Greenhouse

The control system has three layers:

1. **Crop target band** — diurnal VPD/temperature profiles for active crops, computed from `fn_band_setpoints()` every 5 minutes
2. **AI planner** — Iris reads live context (scorecard, forecast, lessons, sensors) and writes 72h tactical setpoint plans with performance targets
3. **ESP32 state machine** — 8 priority-ordered states evaluated every 5 seconds, enforcing the band with fans, heaters, misters, and fog

The crops set the targets. The AI tunes the tactics. The controller enforces them. The telemetry proves what happened.

## KPIs

**Planner Score (0–100):** 80% band compliance + 20% cost efficiency.
4 independent stress states tracked: heat, cold, VPD-high, VPD-low.
Dew point margin monitored for condensation risk.
Planner self-scores at every cycle and sets falsifiable performance targets.

## License

MIT
