#!/bin/bash
# run.sh — Run the full Verdify smoke test suite
# Usage: ./tests/run.sh          # all tests
#        ./tests/run.sh -k api   # only API tests
#        ./tests/run.sh -v       # verbose
set -euo pipefail

cd /srv/verdify
source /srv/greenhouse/.venv/bin/activate

echo "═══════════════════════════════════════════════════════"
echo "  Verdify Smoke Tests — $(date '+%Y-%m-%d %H:%M %Z')"
echo "═══════════════════════════════════════════════════════"
echo ""

python -m pytest tests/ \
    --tb=short \
    -q \
    "$@"
