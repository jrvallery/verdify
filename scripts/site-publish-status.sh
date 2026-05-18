#!/usr/bin/env bash
# site-publish-status.sh — quick operator trace for the Verdify website pipeline.

set -uo pipefail

VAULT=${VERDIFY_SITE_VAULT:-/mnt/iris/verdify-vault/website}
RUNTIME=${VERDIFY_SITE_RUNTIME:-/srv/verdify/verdify-site}
PUBLIC=${VERDIFY_SITE_PUBLIC:-"$RUNTIME/public"}
BUILD_ROOT=${VERDIFY_SITE_BUILD_ROOT:-"$RUNTIME/.builds"}
STATE_DIR=/var/local/verdify/state
SIGNATURE="$STATE_DIR/site-content.signature"
MARKER="$STATE_DIR/site-build-last-run"
LOG=/srv/verdify/state/site-build.log

content_signature() {
    cd "$VAULT" || exit 1
    find . -type f \
        ! -path './.git/*' \
        ! -path './.obsidian/*' \
        ! -path './.stfolder/*' \
        ! -path './@eaDir/*' \
        -printf '%P\0' 2>/dev/null \
        | LC_ALL=C sort -z \
        | while IFS= read -r -d '' file; do
            case "$file" in
                *.md|*.txt|*.json|*.csv|*.html|*.css|*.js|*.ts|*.tsx|*.yaml|*.yml|robots.txt)
                    printf 'H\t%s\t' "$file"
                    sha256sum "$file" | awk '{print $1}'
                    ;;
                *)
                    stat -c 'M\t%n\t%s\t%Y' "$file"
                    ;;
            esac
        done \
        | sha256sum \
        | awk '{print $1}'
}

echo "Verdify site publishing status"
echo
echo "Paths"
echo "  vault:   $VAULT"
echo "  content: $(readlink -f "$RUNTIME/content" 2>/dev/null || echo missing)"
echo "  public:  $PUBLIC"
echo "  builds:  $BUILD_ROOT"
echo

if [[ ! -d "$VAULT" ]]; then
    echo "ERROR: vault path is missing"
    exit 1
fi

current_sig="$(content_signature)"
last_sig="$(cat "$SIGNATURE" 2>/dev/null || true)"

echo "Trigger"
echo "  current signature: ${current_sig:-missing}"
echo "  last built:        ${last_sig:-missing}"
if [[ "$current_sig" == "$last_sig" ]]; then
    echo "  pending rebuild:   no"
else
    echo "  pending rebuild:   yes"
fi
echo

echo "Timestamps"
stat -c '  marker:  %y %n' "$MARKER" 2>/dev/null || echo "  marker:  missing"
stat -c '  public:  %y %n' "$PUBLIC/index.html" 2>/dev/null || echo "  public:  missing index.html"
latest_staging="$(find "$BUILD_ROOT" -maxdepth 1 -type d -name 'public.*' -printf '%T@ %TY-%Tm-%Td %TH:%TM:%TS %p\n' 2>/dev/null | LC_ALL=C sort -nr | head -1 | cut -d' ' -f2- || true)"
echo "  staging: ${latest_staging:-none}"
echo

echo "Timer"
systemctl is-active verdify-site-poll.timer >/dev/null 2>&1 \
    && echo "  verdify-site-poll.timer: active" \
    || echo "  verdify-site-poll.timer: NOT active"
systemctl is-active verdify-site-poll.service >/dev/null 2>&1 \
    && echo "  verdify-site-poll.service: running" \
    || echo "  verdify-site-poll.service: idle"
echo

echo "Latest content mtimes"
find "$VAULT" -type f -printf '  %TY-%Tm-%Td %TH:%TM:%TS %p\n' 2>/dev/null \
    | LC_ALL=C sort -r \
    | head -8
echo

echo "Latest build log"
tail -8 "$LOG" 2>/dev/null || echo "  no build log"
