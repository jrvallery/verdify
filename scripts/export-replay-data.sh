#!/bin/bash
# export-replay-data.sh — Export v_greenhouse_state to CSV for replay harness
# Usage: ./scripts/export-replay-data.sh [days]  (default: 10)
set -euo pipefail

DAYS=${1:-10}
OUTDIR=/srv/verdify/firmware/test/data
mkdir -p "$OUTDIR"
OUTFILE="$OUTDIR/replay_data.csv"

echo "Exporting last ${DAYS} days from v_greenhouse_state..."
docker exec verdify-timescaledb psql -U verdify -d verdify -c "
COPY (
    SELECT * FROM v_greenhouse_state
    WHERE ts >= now() - interval '${DAYS} days'
    ORDER BY ts
) TO STDOUT WITH CSV HEADER
" > "$OUTFILE"

ROWS=$(wc -l < "$OUTFILE")
echo "Exported $((ROWS - 1)) rows to $OUTFILE"
