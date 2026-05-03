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
cd /srv/verdify/verdify-site
if npx quartz build 2>&1 | tee -a "$LOG" | tail -3; then
  # Quartz build deletes+recreates public/, which breaks Docker bind mount.
  # Restart nginx to pick up the new directory.
  echo "[$(date)] Build succeeded. Restarting site container..." | tee -a "$LOG"
  docker restart verdify-site 2>/dev/null || true
  echo "[$(date)] Done. Plan published to verdify.ai/plans/$DATE" | tee -a "$LOG"
else
  echo "[$(date)] ERROR: quartz build failed! Site NOT restarted." | tee -a "$LOG"
  exit 1
fi
