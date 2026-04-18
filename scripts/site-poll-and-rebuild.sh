#!/usr/bin/env bash
# site-poll-and-rebuild.sh — mtime-based polling trigger for the Quartz rebuild.
#
# Replaces verdify-site-build.path (inotify) because inotify on NFS mounts
# does not reliably fire for writes originated by the NFS server (i.e. files
# that arrive via Syncthing on the NAS). This script just polls: "has
# anything under the vault website/ been modified since our last build?"
# If yes, rebuild. If no, no-op.
#
# Fires every VERDIFY_SITE_POLL_INTERVAL_SEC (default 10s) via systemd timer.

set -uo pipefail

VAULT=/mnt/iris/verdify-vault/website
MARKER=/var/local/verdify/state/site-build-last-run

mkdir -p "$(dirname "$MARKER")"

# Initialize marker on first run (no build triggered)
if [[ ! -f "$MARKER" ]]; then
    touch "$MARKER"
    exit 0
fi

# Is there any file under website/ newer than the marker?
# -newer compares mtime; -print -quit returns on first match for efficiency.
if find "$VAULT" -type f -newer "$MARKER" -print -quit 2>/dev/null | grep -q .; then
    # Update marker BEFORE rebuild so a mid-build save triggers a second cycle
    # (rather than being missed).
    touch "$MARKER"
    /srv/verdify/scripts/rebuild-site.sh
fi
