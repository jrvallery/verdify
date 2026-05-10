"""
Verdify configuration — single source of truth for all connection settings.

All values come from environment variables (loaded from .env files) with
sensible defaults where appropriate. No secrets have default values.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env files (ingestor-specific, then project-level)
load_dotenv(Path(__file__).parent / ".env")
load_dotenv(Path(__file__).parent.parent / ".env")

# ── Database ──────────────────────────────────────────────────────
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "verdify")
DB_USER = os.environ.get("DB_USER", "verdify")
DB_PASS = os.environ.get("DB_PASSWORD") or os.environ.get("POSTGRES_PASSWORD", "")
DB_DSN = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ── ESP32 ─────────────────────────────────────────────────────────
ESP32_HOST = os.environ.get("ESP32_HOST", "192.168.10.111")
ESP32_PORT = int(os.environ.get("ESP32_PORT", "6053"))
ESP32_API_KEY = os.environ.get("ESP32_API_KEY", "")
EXPECTED_FIRMWARE_VERSION = os.environ.get("EXPECTED_FIRMWARE_VERSION", "")
EXPECTED_FIRMWARE_VERSION_FILE = os.environ.get(
    "EXPECTED_FIRMWARE_VERSION_FILE",
    "/srv/verdify/state/expected-firmware-version",
)

# ── Home Assistant ────────────────────────────────────────────────
HA_URL = os.environ.get("HA_URL", "http://192.168.30.107:8123")
HA_TOKEN_FILE = os.environ.get("HA_TOKEN_FILE", "/mnt/jason/agents/shared/credentials/ha_token.txt")

# ── MQTT (Sentinel occupancy bridge) ─────────────────────────────
MQTT_HOST = os.environ.get("MQTT_HOST", "192.168.30.107")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "")
MQTT_PASS = os.environ.get("MQTT_PASS", "")

# ── Slack ─────────────────────────────────────────────────────────
SLACK_TOKEN_FILE = os.environ.get("SLACK_TOKEN_FILE", "/mnt/jason/agents/shared/credentials/slack_bot_token.txt")
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "C0ANVVAPLD6")

# ── External services ────────────────────────────────────────────
FRIGATE_URL = os.environ.get("FRIGATE_URL", "http://192.168.30.142:5000")
LOKI_URL = os.environ.get("LOKI_URL", "")  # Empty = disabled
GEMINI_API_KEY_FILE = os.environ.get("GEMINI_API_KEY_FILE", "/mnt/jason/agents/shared/credentials/gemini_api_key.txt")

# ── OpenClaw (Iris planner gateway) ──────────────────────────────
OPENCLAW_URL = os.environ.get("OPENCLAW_URL", "http://127.0.0.1:18789")
OPENCLAW_TOKEN = os.environ.get("OPENCLAW_TOKEN", "iris-hooks-verdify-2026-04")

# Contract v1.5: local Gemma-on-cortext is the default iris-planner path.
# Cloud/opus is kept as an explicit operator escalation target only.
OPENCLAW_LOCAL_AGENT_ID = os.environ.get("OPENCLAW_LOCAL_AGENT_ID", "iris-planner-local")
# Prefix for trigger-scoped local sessions. send_to_iris appends
# `:trigger:<uuid>` so Gemma gets a fresh bounded context for every planning
# run; historical memory comes from the gathered DB/context pack.
OPENCLAW_LOCAL_SESSION_KEY = os.environ.get("OPENCLAW_LOCAL_SESSION_KEY", "agent:iris-planner-local:main")
OPENCLAW_OPUS_AGENT_ID = os.environ.get("OPENCLAW_OPUS_AGENT_ID", "iris-planner")
OPENCLAW_OPUS_SESSION_KEY = os.environ.get("OPENCLAW_OPUS_SESSION_KEY", "agent:iris-planner:main")
# DEPRECATED legacy alias. Defaults to the local planner session in v1.5.
OPENCLAW_SESSION_KEY = os.environ.get("OPENCLAW_SESSION_KEY", OPENCLAW_LOCAL_SESSION_KEY)

# Compatibility flag retained for old deploy env files. Routing is local-first
# regardless of this value; explicit `instance="opus"` is the cloud path.
ENABLE_LOCAL_PLANNER = os.environ.get("ENABLE_LOCAL_PLANNER", "true").lower() in (
    "true",
    "1",
    "yes",
)

# ── Greenhouse ────────────────────────────────────────────────────
GREENHOUSE_ID = os.environ.get("GREENHOUSE_ID", "vallery")
LATITUDE = float(os.environ.get("LATITUDE", "40.1672"))
LONGITUDE = float(os.environ.get("LONGITUDE", "-105.1019"))
TIMEZONE = os.environ.get("TZ", "America/Denver")

# ── Paths ─────────────────────────────────────────────────────────
STATE_DIR = Path(os.environ.get("STATE_DIR", "/srv/verdify/state"))
VAULT_DIR = Path(os.environ.get("VAULT_DIR", "/mnt/iris/verdify-vault"))
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/mnt/iris/backups"))

# ── Equipment constants ───────────────────────────────────────────
WATTAGES = {
    "heat1": 1500,
    "heat2": 0,  # heat2 is gas (BTU, not watts)
    "fan1": 52,
    "fan2": 52,
    "fog": 800,
    "vent": 10,  # AquaFog XE 2000: centrifugal atomizer, ~750-850W actual
    "grow_light_main": 630,
    "grow_light_grow": 816,
}
HEAT2_BTU_PER_HOUR = 54000  # Lennox nameplate 75K, altitude-derated ~20% at 5,090 ft
BTU_PER_THERM = 100000

# ── Utility rates ($/unit) ───────────────────────────────────────
ELECTRIC_RATE = float(os.environ.get("ELECTRIC_RATE", "0.111"))  # $/kWh
GAS_RATE = float(os.environ.get("GAS_RATE", "0.83"))  # $/therm
WATER_RATE = float(os.environ.get("WATER_RATE", "0.00484"))  # $/gallon


def get_db_dsn() -> str:
    """Build DB DSN from env vars. Used by standalone scripts."""
    return DB_DSN


def load_token(path: str) -> str:
    """Read and strip a token from a file."""
    return Path(path).read_text().strip()
