#!/bin/bash
# check-replan-trigger.sh — If a deviation trigger exists and is fresh, route to Iris.
# Called every 5 min by cron. The deviation_check ingestor task writes replan-needed.json
# when observed conditions diverge significantly from forecast.
#
# NOTE: The planning_heartbeat task in the ingestor also checks this trigger file
# every 60s and routes to Iris. This cron script is a fallback in case the ingestor
# is down. Both paths are idempotent — whichever picks up the trigger first deletes it.
set -euo pipefail

TRIGGER="/srv/verdify/state/replan-needed.json"
GATHER="/srv/verdify/scripts/gather-plan-context.sh"
LOG="/srv/verdify/state/replan.log"
COOLDOWN="/srv/verdify/state/replan-cooldown"

OPENCLAW_URL="http://127.0.0.1:18789"
OPENCLAW_TOKEN="iris-hooks-verdify-2026-04"
OPENCLAW_SESSION="agent:iris-planner:main"

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

echo "[$(date)] REPLAN triggered (age=${AGE}s) — routing to Iris" >> "$LOG"

# Gather context
CONTEXT=$(bash "$GATHER" 2>/dev/null || echo "(context gathering failed)")

# Read deviation details from trigger
DEVIATIONS=$(python3 -c "import json,sys; d=json.load(open('$TRIGGER')); print(json.dumps(d.get('deviations',[]),indent=2))" 2>/dev/null || echo "[]")
REASON=$(python3 -c "import json; d=json.load(open('$TRIGGER')); print(d.get('reason','Unknown'))" 2>/dev/null || echo "Unknown deviation")

# Build the message for Iris
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

# Send to Iris via OpenClaw gateway
PAYLOAD=$(python3 -c "
import json, sys
msg = sys.stdin.read()
print(json.dumps({
    'message': msg,
    'agentId': 'iris-planner',
    'sessionKey': '$OPENCLAW_SESSION',
    'deliver': False
}))
" <<< "$MESSAGE")

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST "${OPENCLAW_URL}/hooks/agent" \
    -H "Authorization: Bearer ${OPENCLAW_TOKEN}" \
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
