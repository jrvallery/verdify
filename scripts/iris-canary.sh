#!/usr/bin/env bash
# iris-canary.sh — Phase 7 helper for Hermes canary promotion + rollback.
#
# Mutates /etc/verdify/ingestor.env and /etc/verdify/ai_gateway_by_event.json
# then restarts verdify-ingestor. Requires sudo. Full runbook in
# docs/iris-loop-phase-7-canary.md.
#
# Usage:
#   scripts/iris-canary.sh promote MANUAL              # promote one event to hermes
#   scripts/iris-canary.sh rollback SUNRISE            # roll one event back to openclaw
#   scripts/iris-canary.sh rollback-all                # full revert
#   scripts/iris-canary.sh status                      # show current routing + last-24h gateway breakdown

set -euo pipefail

ENV_FILE=${INGESTOR_ENV:-/etc/verdify/ingestor.env}
MAP_FILE=${INGESTOR_MAP:-/etc/verdify/ai_gateway_by_event.json}

VALID_EVENTS=(SUNRISE SUNSET SOLAR_MAX TRANSITION FORECAST_DEVIATION MANUAL)

usage() {
    sed -n '2,15p' "$0"
    exit 2
}

assert_event() {
    local ev=$1
    for v in "${VALID_EVENTS[@]}"; do
        [[ "$ev" == "$v" ]] && return 0
    done
    echo "error: '$ev' is not a recognized event_type. Valid: ${VALID_EVENTS[*]}" >&2
    exit 2
}

read_map() {
    if [[ -f "$MAP_FILE" ]]; then
        sudo cat "$MAP_FILE"
    else
        echo '{}'
    fi
}

write_map() {
    local new=$1
    echo "$new" | sudo tee "$MAP_FILE" >/dev/null
    if sudo test -f "$ENV_FILE"; then
        if sudo grep -q '^AI_GATEWAY_BY_EVENT=' "$ENV_FILE"; then
            sudo sed -i "s|^AI_GATEWAY_BY_EVENT=.*|AI_GATEWAY_BY_EVENT='$new'|" "$ENV_FILE"
        else
            echo "AI_GATEWAY_BY_EVENT='$new'" | sudo tee -a "$ENV_FILE" >/dev/null
        fi
    else
        echo "warning: $ENV_FILE not found — created map file only ($MAP_FILE)" >&2
    fi
}

restart_ingestor() {
    if systemctl --no-pager status verdify-ingestor >/dev/null 2>&1; then
        sudo systemctl restart verdify-ingestor
    else
        echo "warning: verdify-ingestor systemd unit not present; skip restart" >&2
    fi
}

cmd_promote() {
    local ev=$1
    assert_event "$ev"
    local cur new
    cur=$(read_map)
    new=$(echo "$cur" | jq --arg e "$ev" '. + {($e): "hermes"}')
    write_map "$new"
    restart_ingestor
    echo "✓ promoted $ev → hermes. AI_GATEWAY_BY_EVENT=$new"
}

cmd_rollback() {
    local ev=$1
    assert_event "$ev"
    local cur new
    cur=$(read_map)
    new=$(echo "$cur" | jq --arg e "$ev" 'del(.[$e])')
    write_map "$new"
    restart_ingestor
    echo "✓ rolled back $ev → openclaw. AI_GATEWAY_BY_EVENT=$new"
}

cmd_rollback_all() {
    if sudo test -f "$ENV_FILE"; then
        sudo sed -i "s|^AI_GATEWAY_PROVIDER=.*|AI_GATEWAY_PROVIDER=openclaw|" "$ENV_FILE"
        sudo sed -i "s|^AI_GATEWAY_BY_EVENT=.*|AI_GATEWAY_BY_EVENT='{}'|" "$ENV_FILE"
    fi
    echo '{}' | sudo tee "$MAP_FILE" >/dev/null
    restart_ingestor
    echo "✓ full rollback complete. AI_GATEWAY_PROVIDER=openclaw, AI_GATEWAY_BY_EVENT={}"
}

cmd_status() {
    echo "── AI_GATEWAY_PROVIDER ──"
    if sudo test -f "$ENV_FILE"; then
        sudo grep '^AI_GATEWAY_PROVIDER' "$ENV_FILE" || echo "(unset → openclaw)"
    else
        echo "(env file $ENV_FILE missing → openclaw)"
    fi
    echo "── AI_GATEWAY_BY_EVENT ($MAP_FILE) ──"
    read_map
    echo ""
    echo "── plan_delivery_log breakdown (last 24h) ──"
    if command -v docker >/dev/null && docker ps --format '{{.Names}}' | grep -q verdify-timescaledb; then
        docker exec verdify-timescaledb psql -U verdify -d verdify -c "
            SELECT event_type,
                   CASE WHEN hermes_run_id IS NOT NULL THEN 'hermes' ELSE 'openclaw' END AS gateway,
                   COUNT(*) AS n,
                   COUNT(*) FILTER (WHERE gateway_status BETWEEN 200 AND 299) AS ok,
                   COUNT(*) FILTER (WHERE gateway_status >= 400 OR gateway_status = 0) AS bad
              FROM plan_delivery_log
             WHERE delivered_at > now() - interval '24 hours'
             GROUP BY event_type, gateway
             ORDER BY event_type, gateway;
        "
    else
        echo "(verdify-timescaledb container not running — skip delivery breakdown)"
    fi
}

case "${1:-}" in
    promote)        [[ $# -lt 2 ]] && usage; cmd_promote "$2" ;;
    rollback)       [[ $# -lt 2 ]] && usage; cmd_rollback "$2" ;;
    rollback-all)   cmd_rollback_all ;;
    status)         cmd_status ;;
    -h|--help|"")   usage ;;
    *)              echo "unknown subcommand: $1" >&2; usage ;;
esac
