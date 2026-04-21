#!/bin/bash
# firmware-replay-diff.sh — Build replay_emit from two git refs and diff
# their per-row outputs. The diff identifies minutes where old and new
# firmware produced different mode, relay, or override decisions.
#
# Usage: scripts/firmware-replay-diff.sh OLD_REF NEW_REF [CSV_PATH]
#        (default CSV_PATH: firmware/test/data/replay_overrides.csv)
#
# Output: writes summary to stdout. Full diff saved to /tmp/replay_diff.tsv.
# Exit code 0 if diff is empty or only within allowed-divergence bounds;
# non-zero if unexpected divergence > threshold.
#
# Design: two git worktrees, each compiles its own replay_emit binary, both
# run against the same CSV, outputs compared line-by-line. Sidesteps the
# header-namespacing issues with dual-compile into one binary.
set -euo pipefail

OLD_REF=${1:?"Usage: $0 OLD_REF NEW_REF [CSV_PATH]"}
NEW_REF=${2:?"Usage: $0 OLD_REF NEW_REF [CSV_PATH]"}
CSV=${3:-firmware/test/data/replay_overrides.csv}

if [ ! -f "$CSV" ]; then
    echo "CSV not found: $CSV — run make replay-corpus-refresh first" >&2
    exit 2
fi
CSV_ABS=$(readlink -f "$CSV")

BUILD_DIR=${BUILD_DIR:-/tmp/firmware-replay-diff}
mkdir -p "$BUILD_DIR"

build_ref() {
    local ref="$1"
    local out="$2"
    local worktree="$BUILD_DIR/wt-$ref"
    rm -rf "$worktree"
    # git worktree needs to run from the main repo; assume caller is in it
    git worktree add --force "$worktree" "$ref" >&2
    (cd "$worktree/firmware/test" \
     && g++ -std=c++17 -O2 -I../lib -o replay_emit replay_emit.cpp) \
     || { echo "Build failed for $ref" >&2; return 1; }
    cp "$worktree/firmware/test/replay_emit" "$out"
    git worktree remove --force "$worktree" >&2 || true
}

OLD_BIN="$BUILD_DIR/replay_emit.old"
NEW_BIN="$BUILD_DIR/replay_emit.new"

echo "[1/4] Building OLD ($OLD_REF)..." >&2
build_ref "$OLD_REF" "$OLD_BIN"
echo "[2/4] Building NEW ($NEW_REF)..." >&2
build_ref "$NEW_REF" "$NEW_BIN"

echo "[3/4] Running both against $CSV..." >&2
OLD_OUT="$BUILD_DIR/trace.old.tsv"
NEW_OUT="$BUILD_DIR/trace.new.tsv"
"$OLD_BIN" "$CSV_ABS" > "$OLD_OUT"
"$NEW_BIN" "$CSV_ABS" > "$NEW_OUT"

echo "[4/4] Diffing..." >&2
DIFF_OUT="/tmp/replay_diff.tsv"

# Column-aware diff: compare mode + relay bitmask (columns 2-8) between files
# ignoring rows where everything matches.
paste <(tail -n +2 "$OLD_OUT") <(tail -n +2 "$NEW_OUT") | \
    awk -F'\t' '{
        # OLD: cols 1-11; NEW: cols 12-22
        # Compare ts match (sanity), then mode(2) through override_bits(11)
        old_key = $2 FS $3 FS $4 FS $5 FS $6 FS $7 FS $8 FS $9 FS $10 FS $11
        new_key = $13 FS $14 FS $15 FS $16 FS $17 FS $18 FS $19 FS $20 FS $21 FS $22
        if (old_key != new_key) {
            print $1 "\tOLD\t" old_key
            print $12 "\tNEW\t" new_key
            diff_rows++
        }
    }
    END { printf "%d divergent rows\n", diff_rows+0 > "/dev/stderr" }' > "$DIFF_OUT"

TOTAL_ROWS=$(($(wc -l < "$OLD_OUT") - 1))
DIVERGENT_LINES=$(wc -l < "$DIFF_OUT")
DIVERGENT_ROWS=$((DIVERGENT_LINES / 2))  # each divergence emits 2 lines (OLD + NEW)

echo
echo "═══ Replay diff summary ═══"
echo "  OLD ref: $OLD_REF"
echo "  NEW ref: $NEW_REF"
echo "  CSV:     $CSV ($TOTAL_ROWS rows)"
echo "  Divergent rows: $DIVERGENT_ROWS"
echo "  Full diff:      $DIFF_OUT"

if [ "$DIVERGENT_ROWS" -eq 0 ]; then
    echo "  ✓ No divergence. Behavior preserved."
    exit 0
fi

# Threshold: for HEAD-vs-HEAD, must be 0. For real change, Jason/operator
# reviews diff manually. CI uses a THRESHOLD_PCT env var to allow planned
# divergence (e.g. Phase 2 dwell-gate expected to reduce transitions).
THRESHOLD_PCT=${THRESHOLD_PCT:-0}
DIVERGENT_PCT=$(awk -v d="$DIVERGENT_ROWS" -v t="$TOTAL_ROWS" \
    'BEGIN { printf "%.2f", (t>0) ? (100.0*d/t) : 0 }')

echo "  Divergent pct:  ${DIVERGENT_PCT}% (threshold: ${THRESHOLD_PCT}%)"

if awk -v d="$DIVERGENT_PCT" -v t="$THRESHOLD_PCT" 'BEGIN { exit !(d > t) }'; then
    echo "  ✗ Divergence exceeds threshold. Review $DIFF_OUT before merging."
    exit 1
fi

echo "  ✓ Divergence within allowed threshold."
exit 0
