#!/usr/bin/env bash
# Firmware OTA preflight guard.
#
# Enforces the phase-0 deploy rules that can be checked locally before compile
# or upload. Forecast heat is reported as context, not a deploy blocker.

set -euo pipefail

DB=(docker exec verdify-timescaledb psql -U verdify -d verdify -t -A -F '|' -c)

fail() { echo "✗ $1" >&2; exit 1; }
pass() { echo "✓ $1"; }
warn() { echo "⚠ $1"; }
override_enabled() { [[ "${ALLOW_FIRMWARE_DEPLOY_GUARD_OVERRIDE:-0}" == "1" ]]; }
override_authorized() {
    override_enabled \
        && [[ "${FIRMWARE_DEPLOY_OPERATOR_SIGNOFF:-0}" == "1" ]] \
        && [[ -n "${FIRMWARE_DEPLOY_OVERRIDE_REASON:-}" ]]
}
guard_or_fail() {
    local message="$1"
    if override_authorized; then
        warn "$message — operator override active (${FIRMWARE_DEPLOY_OVERRIDE_REASON:-no reason supplied})"
    else
        if override_enabled; then
            fail "$message; override requested but FIRMWARE_DEPLOY_OPERATOR_SIGNOFF=1 and FIRMWARE_DEPLOY_OVERRIDE_REASON are required"
        fi
        fail "$message"
    fi
}

open_bad="$("${DB[@]}" "SELECT count(*) FROM alert_log WHERE disposition IN ('open','acknowledged') AND resolved_at IS NULL AND severity IN ('critical','high')" | tr -d '[:space:]')"
if [[ "${open_bad:-0}" -gt 0 ]]; then
    guard_or_fail "$open_bad unresolved critical/legacy-high alert(s); no firmware OTA while severe alerts are unresolved"
fi
pass "No unresolved critical/legacy-high alerts"

max_temp="$("${DB[@]}" "SELECT COALESCE(max(temp_f), -999) FROM weather_forecast WHERE ts > now() AND ts <= now() + interval '24 hours'" | tr -d '[:space:]')"
if awk -v t="$max_temp" 'BEGIN { exit !(t > 85.0) }'; then
    warn "Forecast max next 24h is ${max_temp}F (>85F); proceed with normal post-OTA health validation"
else
    pass "Forecast max next 24h is ${max_temp}F"
fi

last_good="firmware/artifacts/last-good.ota.bin"
if [[ -f "$last_good" ]]; then
    pass "Rollback artifact available: $last_good"
else
    guard_or_fail "No last-good rollback artifact at $last_good; auto-rollback would be unavailable"
fi

if [[ -f "$last_good" ]]; then
    last_good_age_s=$(( $(date +%s) - $(stat -c %Y "$last_good") ))
else
    last_good_age_s=0
fi
if [[ "${last_good_age_s:-0}" -lt 172800 ]]; then
    guard_or_fail "48-hour bake not satisfied; $last_good mtime age is ${last_good_age_s}s"
fi
pass "48-hour bake check passed for $last_good mtime"

week_versions="$("${DB[@]}" \
    "WITH first_seen AS (
       SELECT firmware_version, min(ts) AS first_ts
         FROM diagnostics
        WHERE firmware_version IS NOT NULL AND firmware_version <> ''
        GROUP BY firmware_version
     )
     SELECT count(*)
       FROM first_seen
      WHERE first_ts >= date_trunc('week', now() AT TIME ZONE 'America/Denver') AT TIME ZONE 'America/Denver'" \
    | tr -d '[:space:]')"
if [[ "${week_versions:-0}" -gt 0 ]]; then
    guard_or_fail "$week_versions firmware version(s) first appeared this calendar week; weekly OTA limit already used"
fi
pass "Weekly OTA limit clear"
