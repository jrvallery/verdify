#!/usr/bin/env bash
# site-poll-and-rebuild.sh — content-signature polling trigger for Quartz.
#
# Replaces verdify-site-build.path (inotify) because inotify on NFS mounts
# does not reliably fire for writes originated by the NFS server (i.e. files
# that arrive via Syncthing on the NAS). Syncthing can also preserve source
# mtimes, so a simple "find -newer marker" check can miss Obsidian/Mac edits.
# This script compares a metadata signature for the whole website tree instead.
# That catches additions, deletions, renames, ctime changes, and preserved-mtime
# file updates without hashing large image/media contents every 10 seconds.
#
# Fires every VERDIFY_SITE_POLL_INTERVAL_SEC (default 10s) via systemd timer.

set -uo pipefail

VAULT=/mnt/iris/verdify-vault/website
STATE_DIR=/var/local/verdify/state
SIGNATURE="$STATE_DIR/site-content.signature"
MARKER="$STATE_DIR/site-build-last-run"

mkdir -p "$STATE_DIR"

if [[ ! -d "$VAULT" ]]; then
    echo "$(date -Is) vault content path missing: $VAULT" >&2
    exit 1
fi

current_signature="$(
    cd "$VAULT" || exit 1
    find . -type f \
        ! -path './.git/*' \
        ! -path './.obsidian/*' \
        ! -path './.stfolder/*' \
        ! -path './@eaDir/*' \
        -printf '%P\t%s\t%T@\t%C@\n' 2>/dev/null \
        | LC_ALL=C sort \
        | sha256sum \
        | awk '{print $1}'
)"
last_signature="$(cat "$SIGNATURE" 2>/dev/null || true)"

if [[ "$current_signature" != "$last_signature" ]]; then
    echo "$(date -Is) content signature changed — rebuilding site"
    rebuild_output="$(/srv/verdify/scripts/rebuild-site.sh 2>&1)"
    rebuild_status=$?
    printf '%s\n' "$rebuild_output"
    if grep -q "build already running" <<<"$rebuild_output"; then
        echo "$(date -Is) rebuild lock was busy — leaving signature unchanged for retry"
        exit 0
    elif [[ $rebuild_status -eq 0 ]]; then
        printf '%s\n' "$current_signature" > "$SIGNATURE"
        # Human-readable marker for status/debugging. The signature file is the
        # actual trigger state; the marker is no longer used for change detection.
        touch "$MARKER"
    else
        echo "$(date -Is) rebuild failed — keeping old signature so the next poll retries"
        exit 1
    fi
else
    # Keep the legacy marker present for scripts/operators that stat it, but do
    # not advance it on no-op polls; it represents last successful build time.
    [[ -f "$MARKER" ]] || touch "$MARKER"
fi
