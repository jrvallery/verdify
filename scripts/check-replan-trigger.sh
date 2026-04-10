#!/bin/bash
# check-replan-trigger.sh — If a deviation trigger exists and is fresh, run the planner.
# Called every 5 min by cron. The deviation_check ingestor task writes replan-needed.json
# when observed conditions diverge significantly from forecast.
set -euo pipefail

TRIGGER="/srv/verdify/state/replan-needed.json"
PLANNER="/srv/verdify/scripts/planner.py"
PUBLISHER="/srv/verdify/scripts/publish-daily-plan.sh"
LOG="/srv/verdify/state/replan.log"
COOLDOWN="/srv/verdify/state/replan-cooldown"

# Exit if no trigger
[ -f "$TRIGGER" ] || exit 0

# Exit if trigger is older than 10 minutes (stale)
AGE=$(( $(date +%s) - $(stat -c %Y "$TRIGGER") ))
[ "$AGE" -gt 600 ] && exit 0

# Exit if we replanned in the last 30 minutes (cooldown)
if [ -f "$COOLDOWN" ]; then
    COOLDOWN_AGE=$(( $(date +%s) - $(stat -c %Y "$COOLDOWN") ))
    [ "$COOLDOWN_AGE" -lt 1800 ] && exit 0
fi

echo "[$(date)] REPLAN triggered (age=${AGE}s)" >> "$LOG"
source /srv/greenhouse/.venv/bin/activate

# Run planner (MODE: REPLAN set automatically by planner.py)
python3 "$PLANNER" >> "$LOG" 2>&1
RESULT=$?

if [ "$RESULT" -eq 0 ]; then
    echo "[$(date)] Replan succeeded, publishing..." >> "$LOG"
    bash "$PUBLISHER" >> "$LOG" 2>&1
    touch "$COOLDOWN"
    rm -f "$TRIGGER"
    echo "[$(date)] Replan complete" >> "$LOG"
else
    echo "[$(date)] Replan FAILED (exit $RESULT)" >> "$LOG"
fi
