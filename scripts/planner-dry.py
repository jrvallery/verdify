#!/usr/bin/env python3
"""planner-dry — render every planner event-type prompt locally, without any
API calls, and assert that invariants the audit cares about still hold. Run
via `make planner-dry`. Fails loud (exit 1) if an invariant breaks so prompt
regressions can't land silently.

Checks:
  1. iris_planner imports (fails on Python syntax, missing dependency, or
     missing playbook at PLANNER_PLAYBOOK_PATH).
  2. `_STANDING_DIRECTIVES` still says "17 tools" — G2 tool-inventory guard.
  3. `_PLANNER_KNOWLEDGE` still carries the "Structured hypothesis" section —
     G7 write-side guard.
  4. Every event-type prompt builder (SUNRISE, SUNSET, TRANSITION, FORECAST,
     DEVIATION) renders a non-empty string with the expected anchors.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("OPENCLAW_URL", "x")
os.environ.setdefault("OPENCLAW_TOKEN", "x")
os.environ.setdefault("OPENCLAW_SESSION_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ingestor"))

import iris_planner as p  # noqa: E402

assert "17 tools" in p._STANDING_DIRECTIVES, "tool-count guard (G2): '17 tools' missing"
assert p.PLANNER_PLAYBOOK_PATH.exists(), f"playbook missing at {p.PLANNER_PLAYBOOK_PATH}"
assert "Structured hypothesis" in p._PLANNER_KNOWLEDGE, (
    "structured-hypothesis guidance (G7) missing from _PLANNER_KNOWLEDGE"
)

for event in ("SUNRISE", "SUNSET", "TRANSITION", "FORECAST", "DEVIATION"):
    message = p._PROMPT_BUILDERS[event]("<context stub>", "<label stub>")
    assert isinstance(message, str) and len(message) > 1000, f"{event} prompt suspiciously short: {len(message)} chars"
    assert "17 tools" in message, f"{event} prompt missing _STANDING_DIRECTIVES preamble"
    print(f"  {event:10s} {len(message):>6} chars")

print("planner-dry: all prompts render")
