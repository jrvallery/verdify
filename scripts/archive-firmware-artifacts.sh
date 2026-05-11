#!/usr/bin/env bash
# Archive the exact ESPHome build outputs for a firmware version.
#
# Run after ESPHome compile. With --promote-last-good, also updates the
# rollback target used by scripts/firmware-rollback.sh.

set -euo pipefail

usage() {
    echo "Usage: $0 FIRMWARE_VERSION [--promote-last-good]" >&2
}

FW_VERSION="${1:-}"
if [[ -z "$FW_VERSION" ]]; then
    usage
    exit 2
fi
shift || true

PROMOTE=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --promote-last-good) PROMOTE=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
    esac
done

REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
REPO_ROOT="$(cd "$REPO_ROOT" && pwd)"
cd "$REPO_ROOT"
BUILD_DIR="$REPO_ROOT/firmware/.esphome/build/greenhouse/.pioenvs/greenhouse"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-$REPO_ROOT/firmware/artifacts}"
DEST="$ARTIFACT_ROOT/$FW_VERSION"

required=(
    firmware.ota.bin
    firmware.bin
    firmware.elf
    firmware.map
)

for f in "${required[@]}"; do
    if [[ ! -f "$BUILD_DIR/$f" ]]; then
        echo "Missing build artifact: $BUILD_DIR/$f" >&2
        exit 1
    fi
done

mkdir -p "$DEST"
for f in "${required[@]}"; do
    cp "$BUILD_DIR/$f" "$DEST/$f"
done

if [[ -f "$BUILD_DIR/project_description.json" ]]; then
    cp "$BUILD_DIR/project_description.json" "$DEST/project_description.json"
fi
if [[ -f "$REPO_ROOT/firmware/.esphome/storage/greenhouse.yaml.json" ]]; then
    cp "$REPO_ROOT/firmware/.esphome/storage/greenhouse.yaml.json" "$DEST/esphome-storage.json"
fi

{
    echo "firmware_version=$FW_VERSION"
    echo "archived_at=$(date -Is)"
    echo "source_ref=$(git rev-parse --abbrev-ref HEAD)"
    echo "source_sha=$(git rev-parse HEAD)"
    if git diff --quiet -- . && git diff --cached --quiet -- .; then
    echo "source_dirty=0"
    else
        echo "source_dirty=1"
    fi
    if [[ -n "${FIRMWARE_DEPLOYED_AT:-}" ]]; then
        echo "deployed_at=$FIRMWARE_DEPLOYED_AT"
    fi
    echo "esphome_bin=${ESPHOME_BIN:-/srv/greenhouse/.venv/bin/esphome}"
    echo "build_dir=$BUILD_DIR"
    echo "artifact_dir=$DEST"
    echo "addr2line=/home/jason/.platformio/packages/toolchain-xtensa-esp-elf/bin/xtensa-esp32-elf-addr2line -pfiaC -e firmware.elf <PC> <BT...>"
} > "$DEST/metadata.env"

(
    cd "$DEST"
    sha256sum "${required[@]}" > SHA256SUMS
)

if [[ "$PROMOTE" -eq 1 ]]; then
    cp "$DEST/firmware.ota.bin" "$ARTIFACT_ROOT/last-good.ota.bin"
    printf '%s\n' "$FW_VERSION" > "$ARTIFACT_ROOT/last-good.version"
    cp "$DEST/metadata.env" "$ARTIFACT_ROOT/last-good.metadata.env"
    if [[ -n "${FIRMWARE_DEPLOYED_AT:-}" ]]; then
        touch -d "$FIRMWARE_DEPLOYED_AT" "$ARTIFACT_ROOT/last-good.ota.bin"
    fi
fi

echo "Archived firmware artifacts: $DEST"
if [[ "$PROMOTE" -eq 1 ]]; then
    echo "Promoted rollback target: $FW_VERSION"
fi
