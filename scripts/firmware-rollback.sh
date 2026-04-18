#!/usr/bin/env bash
# firmware-rollback.sh — Flash a previously-saved OTA binary back to the ESP32.
#
# FW-15 (Sprint 17). Invoked automatically by `make firmware-deploy` when
# post-deploy `sensor-health` fails, and runnable manually via
# `make firmware-rollback`.
#
# Uses ESPHome's espota2 module directly (the same transport esphome
# upload uses) to flash an arbitrary .ota.bin over the network without
# recompiling. The rollback target is /mnt/iris/verdify/firmware/artifacts/
# previous.ota.bin — saved by firmware-deploy before each OTA.

set -uo pipefail

ROLLBACK_BIN="${1:-/mnt/iris/verdify/firmware/artifacts/last-good.ota.bin}"
ESP32_HOST="${ESP32_HOST:-192.168.10.111}"
ESP32_OTA_PORT="${ESP32_OTA_PORT:-3232}"
SECRETS_YAML="${SECRETS_YAML:-/srv/greenhouse/esphome/secrets.yaml}"
LOG=/var/local/verdify/state/firmware-rollback.log
mkdir -p "$(dirname "$LOG")"

exec > >(tee -a "$LOG") 2>&1

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  FIRMWARE ROLLBACK  —  $(date -Is)"
echo "══════════════════════════════════════════════════════════════"
echo "  Target: $ESP32_HOST:$ESP32_OTA_PORT"
echo "  Binary: $ROLLBACK_BIN"

if [[ ! -f "$ROLLBACK_BIN" ]]; then
    echo "  ✗ Rollback binary not found — cannot auto-roll-back."
    echo "  MANUAL RECOVERY: re-run previous commit's firmware-deploy,"
    echo "                   or serial-console the ESP32 to flash recovery image."
    exit 1
fi

# Extract OTA password from secrets.yaml. Runtime password — not committed.
if [[ ! -f "$SECRETS_YAML" ]]; then
    echo "  ✗ secrets.yaml not found at $SECRETS_YAML"
    exit 1
fi
OTA_PW=$(grep -E "^ota_password:" "$SECRETS_YAML" | cut -d'"' -f2)
if [[ -z "$OTA_PW" ]]; then
    # Try unquoted form
    OTA_PW=$(awk '/^ota_password:/ {print $2; exit}' "$SECRETS_YAML" | tr -d '"'"'")
fi
if [[ -z "$OTA_PW" ]]; then
    echo "  ✗ Could not parse ota_password from $SECRETS_YAML"
    exit 1
fi

echo "  Flashing previous binary via ESPHome OTA protocol..."
/srv/greenhouse/.venv/bin/python - <<PYEOF
import sys
from pathlib import Path
from esphome import espota2
rc, version = espota2.run_ota(
    remote_host="$ESP32_HOST",
    remote_port=$ESP32_OTA_PORT,
    password="$OTA_PW",
    filename=Path("$ROLLBACK_BIN"),
)
sys.exit(rc)
PYEOF

RC=$?
if [[ $RC -eq 0 ]]; then
    echo "  ✓ Rollback successful. Previous firmware flashed."
    echo "  Wait 60s, then run 'make sensor-health' to verify recovery."
    exit 0
else
    echo "  ✗ Rollback failed (espota rc=$RC). ESP32 may still be on the"
    echo "    bad firmware. Try manual retry: make firmware-rollback"
    echo "    If that fails, serial-flash via USB."
    exit $RC
fi
