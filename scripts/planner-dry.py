#!/usr/bin/env python3
"""planner-dry — render every planner event-type prompt locally, without any
API calls, and assert that invariants the audit cares about still hold. Run
via `make planner-dry`. Fails loud (exit 1) if an invariant breaks so prompt
regressions can't land silently.

Checks:
  1. iris_planner imports (fails on Python syntax, missing dependency, or
     missing playbook at PLANNER_PLAYBOOK_PATH).
  2. `_STANDING_DIRECTIVES` still says "17 tools" — G2 tool-inventory guard.
  3. `_PLANNER_CORE` still carries the "Structured hypothesis" section —
     G7 write-side guard (CORE must include it so both opus and local see it).
  4. Sprint-3 split invariants: `_PLANNER_CORE` has the Tier 1 table;
     `_PLANNER_EXTENDED` has the validated-lessons list and NOT the Tier 1
     table (prevents duplication).
  5. Every event-type prompt builder renders a non-empty string for BOTH
     instances (opus, local). Assertions:
       - opus string > local string (EXTENDED adds bytes).
       - local preamble ≤ ~52000 Claude tokens (≈ 208000 chars at 4:1; we
         approximate with char-length since the anthropic tokenizer hits
         the network and this script must stay offline).
       - "17 tools" preamble appears in both.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("OPENCLAW_URL", "x")
os.environ.setdefault("OPENCLAW_TOKEN", "x")
os.environ.setdefault("OPENCLAW_SESSION_KEY", "x")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ingestor"))

import iris_planner as p  # noqa: E402

# Contract v1.3 §5-Q4: ≤60k gemma tokens for the local preamble. Claude
# tokenizer is the proxy; target ≤52k Claude tokens = ~208k chars (4:1
# approximation) for the local-lite composed preamble. Opus has no hard
# budget beyond the model's context window.
LOCAL_PREAMBLE_MAX_CHARS = 52_000 * 4

# Invariants that must hold regardless of instance.
assert "17 tools" in p._STANDING_DIRECTIVES, "tool-count guard (G2): '17 tools' missing"
assert p.PLANNER_PLAYBOOK_PATH.exists(), f"playbook missing at {p.PLANNER_PLAYBOOK_PATH}"

# Sprint-3 split + Sprint-4 dictionary expansion: CORE must have the hypothesis
# format AND the full 86-tunable dictionary. EXTENDED must have the long-form
# reference AND not duplicate the dictionary.
assert "Structured hypothesis" in p._PLANNER_CORE, (
    "structured-hypothesis guidance (G7) missing from _PLANNER_CORE — must ship to both instances"
)
assert "Tunable Dictionary (all 86" in p._PLANNER_CORE, (
    "Tunable Dictionary header missing from _PLANNER_CORE — sprint-4 expanded Tier 1 → all 86"
)
# Drift guard: every tunable name in ALL_TUNABLES must appear literally in CORE.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from verdify_schemas.tunables import ALL_TUNABLES  # noqa: E402

_missing_tunables = sorted(t for t in ALL_TUNABLES if t not in p._PLANNER_CORE)
assert not _missing_tunables, f"CORE dictionary missing {len(_missing_tunables)} ALL_TUNABLES: {_missing_tunables[:10]}"
assert "Validated Lessons" in p._PLANNER_EXTENDED, "full lessons list belongs in EXTENDED"
assert "Tunable Dictionary" not in p._PLANNER_EXTENDED, (
    "Dictionary should not be duplicated in EXTENDED — CORE is the single source"
)

# Preamble sanity for both instances.
opus_preamble = p._compose_preamble("opus")
local_preamble = p._compose_preamble("local")
assert len(opus_preamble) > len(local_preamble), (
    f"opus preamble ({len(opus_preamble)}) must be larger than local ({len(local_preamble)})"
)
assert len(local_preamble) <= LOCAL_PREAMBLE_MAX_CHARS, (
    f"local preamble {len(local_preamble)} chars > {LOCAL_PREAMBLE_MAX_CHARS} char budget "
    f"(≈ 52k Claude tokens / 60k gemma tokens — contract §5-Q4)"
)
print(f"  preamble opus  = {len(opus_preamble):>6} chars (≈ {len(opus_preamble) // 4:>5} Claude-tokens)")
print(f"  preamble local = {len(local_preamble):>6} chars (≈ {len(local_preamble) // 4:>5} Claude-tokens)")
print(f"  delta          = {len(opus_preamble) - len(local_preamble):>6} chars (EXTENDED)")

# Every event-type builder renders cleanly for both instances.
for event in ("SUNRISE", "SUNSET", "TRANSITION", "FORECAST", "DEVIATION"):
    for instance in ("opus", "local"):
        message = p._PROMPT_BUILDERS[event]("<context stub>", "<label stub>", instance)
        assert isinstance(message, str) and len(message) > 1000, (
            f"{event}/{instance} prompt suspiciously short: {len(message)} chars"
        )
        assert "17 tools" in message, f"{event}/{instance} prompt missing _STANDING_DIRECTIVES preamble"
        print(f"  {event:10s} {instance:5s} {len(message):>6} chars")

print("planner-dry: all prompts render; split invariants hold")
