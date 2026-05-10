#!/bin/bash
# Compatibility wrapper. The Python generator is the canonical implementation.
set -euo pipefail

PYTHON=${PYTHON:-/srv/greenhouse/.venv/bin/python}
exec "$PYTHON" /srv/verdify/scripts/generate-plans-index.py "$@"
