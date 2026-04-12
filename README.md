# Verdify

**What if a greenhouse could learn?**

367 sq ft. Longmont, Colorado. 5,090 feet. 15% humidity. 95°F solar peaks. Six crops. One AI.

172 sensors feed a 7-mode climate controller that evaluates conditions every 5 seconds. Crop profiles define what each zone needs at each hour. An AI agent named Iris (Claude Opus 4.6) plans event-driven — adjusting 24 tunables at sunrise, sunset, and every transition in between. The system measures every outcome, scores every plan, and gets better.

**[verdify.ai](https://verdify.ai)**

## Architecture

```
ESP32 Controller (7-mode, greenhouse_logic.h, 5s loop)
  ├── aioesphomeapi ──→ Ingestor ──→ TimescaleDB (2.5M+ rows)
  ├── MQTT ──→ Mosquitto (state publishing + occupancy)
  └── HTTPS ──→ API (band-driven setpoints every 5 min)

TimescaleDB (47 tables, 56 views, 100+ functions)
  ├── Grafana (54 dashboards, anonymous read)
  ├─��� FastAPI (crop catalog + ESP32 setpoints)
  ├── MCP Server (9 tools for Iris agent)
  └── Quartz (static site with embedded panels)

Iris Planner (Claude Opus 4.6, OpenClaw agent)
  └── Event-driven: sunrise, transitions, sunset, forecast, deviation
      → MCP tools → set_tunable() → Slack #greenhouse
```

Everything runs on a single VM. No cloud infrastructure — just API keys.

## Components

| Directory | What |
|-----------|------|
| `ingestor/` | Python async service — ESP32 data capture, 15 periodic tasks, entity routing |
| `api/` | FastAPI crop catalog + ESP32 setpoint endpoint |
| `firmware/` | ESPHome YAML + C++ headers — 7-mode climate controller (greenhouse_logic.h) |
| `mcp/` | FastMCP server — 9 tools for Iris agent (climate, scorecard, set_tunable, etc.) |
| `scripts/` | Operational scripts — planner, vision analysis, forecast sync, monitoring |
| `provisioning/` | Grafana dashboard JSON (54 dashboards) + datasource config |
| `db/` | Schema (44 tables, 55 views), migrations (002–077) |
| `templates/` | Jinja2 planner prompt + reference docs |
| `config/` | AI model config, zone definitions |
| `tests/` | 83 smoke tests — full-stack validation against live production |
| `site/` | Quartz static site content (56 pages) |

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
2. **AI planner** — Claude Opus 4.6 reads live context (scorecard, forecast, lessons, sensors) and writes 72h tactical setpoint plans with performance targets
3. **ESP32 state machine** — 48 climate states evaluated every 5 seconds, enforcing the band with fans, heaters, misters, and fog

The crops set the targets. The AI tunes the tactics. The controller enforces it. The telemetry proves what happened.

## KPIs

**Planner Score (0–100):** 80% band compliance + 20% cost efficiency.
4 independent stress states tracked: heat, cold, VPD-high, VPD-low.
Dew point margin monitored for condensation risk.
Planner self-scores at every cycle and sets falsifiable performance targets.

## License

MIT
