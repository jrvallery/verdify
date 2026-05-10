#!/bin/bash
# publish-daily-plan.sh — compatibility wrapper for planner-triggered site refresh.
set -euo pipefail

DATE=${1:-$(date +%Y-%m-%d)}
exec /srv/verdify/scripts/publish-site-content.sh --date "$DATE" --reason planner
