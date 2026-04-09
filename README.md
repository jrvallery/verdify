# Verdify

**What if a greenhouse could learn?**

367 sq ft. Longmont, Colorado. 5,090 feet. 15% humidity. 95F solar peaks. Six crops. One AI.

172 sensors feed a 42-state climate machine that evaluates conditions every 5 seconds. Crop profiles define what each zone needs at each hour. Gemini plans 72 hours ahead, three times a day. The system measures every outcome, scores every plan, and gets better.

**[verdify.ai](https://verdify.ai)**

## Architecture

```
ESP32 Controller (42-state machine, 5s loop)
  ├── aioesphomeapi ──→ Ingestor ──→ TimescaleDB (2.5M+ rows)
  ├── MQTT ──→ Mosquitto (state publishing)
  └── HTTPS ──→ API (band-driven setpoints)

TimescaleDB (44 tables, 54 views, 23 functions)
  ├── Grafana (54 dashboards)
  ├── FastAPI (crop catalog + setpoints)
  └── Quartz (static site with embedded panels)

Gemini 2.5 Pro (Google AI Studio)
  └── 72h tactical planning, 3x daily
```

Everything runs on a single VM. No cloud infrastructure — just an API key.

## Components

| Directory | What |
|-----------|------|
| `ingestor/` | Python async service — ESP32 data capture, 12 periodic tasks, entity routing |
| `api/` | FastAPI crop catalog + ESP32 setpoint endpoint |
| `firmware/` | ESPHome YAML — 42-state climate controller, VPD/temp bands, mister cascade |
| `grafana/` | 17 standardized dashboards + provisioning config |
| `scripts/` | 26 operational scripts — planner, vision analysis, vault export, monitoring |
| `db/` | Schema (44 tables), migrations, init scripts |
| `site/` | Quartz static site content (56 pages) |
| `mqtt/` | Mosquitto broker config |
| `traefik/` | Reverse proxy config |
| `docs/` | System architecture, runbook, roadmap |

## Quick Start

```bash
# Prerequisites: Docker, Python 3.13+, Node 20+

# 1. Clone and configure
git clone https://github.com/jvallery/verdify.git
cd verdify
cp .env.example .env  # Edit with your passwords

# 2. Start the stack
docker compose up -d

# 3. Start the ingestor (requires ESP32 on the network)
pip install -r ingestor/requirements.txt
python ingestor/ingestor.py

# 4. Build the site
cd site && npm install && npx quartz build
```

## The Greenhouse

The control system has three layers:

1. **Crop target band** — smooth diurnal VPD/temperature profiles for six active crops, computed from `crop_target_profiles` and interpolated by hour
2. **AI planner** — Gemini 2.5 Pro reads 14 sections of context (sensor data, 72h forecast, crop band, validated lessons, previous plan scores) and writes tactical setpoint plans
3. **ESP32 state machine** — 42 climate states evaluated every 5 seconds, enforcing the band with fans, heaters, misters, and fog

The crops set the targets. The AI tunes the tactics. The controller enforces it. The telemetry proves what happened.

## Data Flow

The ESP32 publishes 172 entities via encrypted native API. The ingestor routes them through 9 entity maps into 6 database tables at 60-second cadence. Twelve periodic tasks enrich the data: outdoor weather from Open-Meteo, energy from a Shelly EM50, forecast sync, alert monitoring, and band-driven setpoint dispatch.

The setpoint dispatcher computes crop-science target bands every 5 minutes using `fn_band_setpoints()` and `fn_zone_vpd_targets()`, derives mister engagement thresholds from the band ceiling, and pushes directly to the ESP32 via aioesphomeapi.

## License

MIT
