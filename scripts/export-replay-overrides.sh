#!/bin/bash
# export-replay-overrides.sh — Export climate + occupancy as-of join for the
# evaluate_overrides() replay harness (Sprint 16 OBS-1e validation).
# Usage: ./scripts/export-replay-overrides.sh [days]  (default: all history)
set -euo pipefail

DAYS=${1:-0}  # 0 = all history
# OUTDIR is env-overridable so Makefile targets can pin output directly into
# the firmware worktree's test/data/. Default preserves the original location
# for standalone invocations from the main repo.
OUTDIR=${OUTDIR:-/srv/verdify/firmware/test/data}
mkdir -p "$OUTDIR"
OUTFILE="$OUTDIR/replay_overrides.csv"

if [ "$DAYS" -eq 0 ]; then
    WHERE="c.temp_avg IS NOT NULL AND c.vpd_avg IS NOT NULL AND c.rh_avg IS NOT NULL"
    echo "Exporting all history from climate + occupancy..."
else
    WHERE="c.ts >= now() - interval '${DAYS} days' AND c.temp_avg IS NOT NULL AND c.vpd_avg IS NOT NULL AND c.rh_avg IS NOT NULL"
    echo "Exporting last ${DAYS} days..."
fi

docker exec verdify-timescaledb psql -U verdify -d verdify -c "
COPY (
    WITH occ AS (
        SELECT ts, (value = 'occupied') AS occ
        FROM system_state WHERE entity = 'occupancy' ORDER BY ts
    )
    SELECT
        c.ts,
        c.temp_avg, c.vpd_avg, c.rh_avg,
        COALESCE(c.outdoor_rh_pct, 30) AS outdoor_rh_pct,
        COALESCE(c.enthalpy_delta, -5) AS enthalpy_delta,
        NULL::float AS sp_temp_high, NULL::float AS sp_temp_low,
        NULL::float AS sp_vpd_high, NULL::float AS sp_vpd_low,
        0.0::float AS sp_bias_cool,
        NULL::float AS sp_vpd_hysteresis,
        NULL::float AS sp_watch_dwell_s,
        COALESCE(
            (SELECT o.occ FROM occ o WHERE o.ts <= c.ts ORDER BY o.ts DESC LIMIT 1),
            false
        ) AS occupied
    FROM climate c
    WHERE ${WHERE}
    ORDER BY c.ts
) TO STDOUT WITH (FORMAT csv, DELIMITER E'\t', HEADER, NULL '')
" > "$OUTFILE"

ROWS=$(wc -l < "$OUTFILE")
echo "Exported $((ROWS - 1)) rows to $OUTFILE"
