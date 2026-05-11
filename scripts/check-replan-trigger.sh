#!/bin/bash
# check-replan-trigger.sh — If a deviation trigger exists and is fresh, route to Iris.
#
# The planning_heartbeat task in the ingestor also checks this trigger file every
# 60s and routes to Iris (via send_to_iris → Hermes). This cron script is a
# fallback in case the ingestor is down. Both paths are idempotent — whichever
# picks up the trigger first deletes it.
set -euo pipefail

TRIGGER="/srv/verdify/state/replan-needed.json"
GATHER="/srv/verdify/scripts/gather-plan-context.sh"
LOG="/srv/verdify/state/replan.log"
COOLDOWN="/srv/verdify/state/replan-cooldown"

HERMES_URL="${HERMES_URL:-http://127.0.0.1:8642}"
HERMES_API_KEY="${HERMES_IRIS_API_KEY:-}"
HERMES_SESSION_PREFIX="${HERMES_SESSION_PREFIX:-hermes:iris:main}"

# Source ingestor .env for HERMES_IRIS_API_KEY when not in the environment.
if [ -z "$HERMES_API_KEY" ] && [ -r /srv/verdify/ingestor/.env ]; then
    HERMES_API_KEY=$(grep -E '^HERMES_IRIS_API_KEY=' /srv/verdify/ingestor/.env | head -1 | cut -d= -f2- || echo "")
fi

[ -f "$TRIGGER" ] || exit 0

AGE=$(( $(date +%s) - $(stat -c %Y "$TRIGGER") ))
[ "$AGE" -gt 600 ] && exit 0

if [ -f "$COOLDOWN" ]; then
    COOLDOWN_AGE=$(( $(date +%s) - $(stat -c %Y "$COOLDOWN") ))
    [ "$COOLDOWN_AGE" -lt 1800 ] && exit 0
fi

echo "[$(date)] REPLAN triggered (age=${AGE}s) — routing to Iris via Hermes" >> "$LOG"

CONTEXT=$(bash "$GATHER" 2>/dev/null || echo "(context gathering failed)")

DEVIATIONS=$(python3 -c "import json; d=json.load(open('$TRIGGER')); print(json.dumps(d.get('deviations',[]),indent=2))" 2>/dev/null || echo "[]")
REASON=$(python3 -c "import json; d=json.load(open('$TRIGGER')); print(d.get('reason','Unknown'))" 2>/dev/null || echo "Unknown deviation")

MESSAGE=$(cat <<EOFMSG
## Planning Event: DEVIATION DETECTED
**Time:** $(date '+%H:%M %Z')

Observed conditions have diverged significantly from the forecast:
\`\`\`
${DEVIATIONS}
\`\`\`

### Your tasks:
1. **Assess the deviation** — call \`climate\` to see current conditions.
2. **Check equipment** — call \`equipment_state\` to see what's running.
3. **Determine cause** — is this a weather shift, equipment issue, or forecast error?
4. **Adjust tunables** — use \`set_tunable\` to adapt to actual conditions.
5. **Post what changed** — explain the deviation, your diagnosis, and your response.

### Assembled Context
${CONTEXT}

---
Post to #greenhouse with what deviated, your diagnosis, and what you changed.
EOFMSG
)

TRIGGER_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
SESSION_ID="${HERMES_SESSION_PREFIX}:trigger:${TRIGGER_ID}"

PAYLOAD=$(python3 -c "
import json, sys
msg = sys.stdin.read()
print(json.dumps({
    'input': msg,
    'session_id': '$SESSION_ID',
    'metadata': {
        'trigger_id': '$TRIGGER_ID',
        'event_type': 'FORECAST_DEVIATION',
        'event_label': '$REASON',
        'planner_instance': 'local',
        'source': 'check-replan-trigger.sh',
    },
}))
" <<< "$MESSAGE")

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${HERMES_URL}/v1/runs" \
    -H "Authorization: Bearer ${HERMES_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    --max-time 30)

if [ "$HTTP_CODE" -lt 300 ]; then
    echo "[$(date)] Iris notified (HTTP $HTTP_CODE). Deviation: $REASON" >> "$LOG"
    touch "$COOLDOWN"
    rm -f "$TRIGGER"
    echo "[$(date)] Replan complete (routed to Iris)" >> "$LOG"
else
    echo "[$(date)] Iris notification FAILED (HTTP $HTTP_CODE). Deviation: $REASON" >> "$LOG"
fi
