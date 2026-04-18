#!/usr/bin/env bash
# rebuild-site.sh — Debounced Quartz rebuild + nginx refresh.
# Invoked by verdify-site-build.service (triggered by verdify-site-build.path
# file watcher on /mnt/iris/verdify-vault/website/) and runnable manually:
#
#   make site-rebuild    (convenience target)
#   /srv/verdify/scripts/rebuild-site.sh
#
# Uses flock to serialize concurrent invocations. If a build is already
# running, the new request skips — the running build will pick up the
# newer changes when it re-reads the filesystem.

set -uo pipefail

LOCK=/var/lock/verdify-site-build.lock
LOG=/srv/verdify/state/site-build.log
mkdir -p "$(dirname "$LOG")"

{
    flock -n 9 || {
        echo "$(date -Is) build already running — skipping (changes will be picked up)"
        exit 0
    }

    # Small debounce so multi-file Syncthing drops coalesce into one build
    sleep 5

    echo "$(date -Is) rebuild starting"
    cd /srv/verdify/verdify-site
    if npx quartz build 2>&1 | tail -5; then
        if docker restart verdify-site > /dev/null 2>&1; then
            pages=$(find /srv/verdify/verdify-site/public -name '*.html' | wc -l)
            echo "$(date -Is) rebuild complete — $pages pages emitted, nginx restarted"
        else
            echo "$(date -Is) quartz built but docker restart failed"
            exit 1
        fi
    else
        echo "$(date -Is) quartz build FAILED"
        exit 1
    fi
} 9>"$LOCK" 2>&1 | tee -a "$LOG"
