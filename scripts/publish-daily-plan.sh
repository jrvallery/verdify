#!/bin/bash
# publish-daily-plan.sh — Generate today's daily plan document and rebuild the site
# Called by the planner cron after writing setpoints.
set -euo pipefail

DATE=${1:-$(date +%Y-%m-%d)}
LOG="/srv/verdify/state/publish.log"
PYTHON=${PYTHON:-/srv/greenhouse/.venv/bin/python}

echo "[$(date)] Generating daily plan for $DATE..." | tee -a "$LOG"
"$PYTHON" /srv/verdify/scripts/generate-daily-plan.py --date "$DATE" 2>&1 | tee -a "$LOG"

echo "[$(date)] Regenerating plans index..." | tee -a "$LOG"
bash /srv/verdify/scripts/generate-plans-index.sh 2>&1 | tee -a "$LOG"

echo "[$(date)] Regenerating lessons page..." | tee -a "$LOG"
"$PYTHON" /srv/verdify/scripts/generate-lessons-page.py 2>&1 | tee -a "$LOG"

echo "[$(date)] Regenerating planner static context..." | tee -a "$LOG"
bash /srv/verdify/scripts/gather-static-context.sh 2>&1 | tee -a "$LOG"

echo "[$(date)] Building site..." | tee -a "$LOG"
if /srv/verdify/scripts/rebuild-site.sh 2>&1 | tee -a "$LOG"; then
  echo "[$(date)] Done. Plan published to verdify.ai/plans/$DATE and verdify.ai/data/plans" | tee -a "$LOG"
else
  echo "[$(date)] ERROR: site rebuild failed. Plan source was generated, but public site was not updated." | tee -a "$LOG"
  exit 1
fi
