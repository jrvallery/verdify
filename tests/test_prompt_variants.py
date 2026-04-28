"""Unit tests for the CORE / EXTENDED prompt split (sprint-3, G6).

These tests import `ingestor/iris_planner.py` from the worktree directly
(not from /srv/verdify) with stubbed OpenClaw env so they run offline and
don't depend on live services. Same import pattern as scripts/planner-dry.py.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types

import pytest

_WORKTREE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Contract §5-Q4: the local preamble must fit under ~60k gemma tokens.
# Claude tokenizer is the proxy (no gemma tokenizer in venv). 52k Claude
# tokens at a 4:1 char:token approximation = 208k chars. Checked in
# scripts/planner-dry.py as the authoritative gate; duplicated here so a
# pytest run catches the same budget violation.
_LOCAL_PREAMBLE_MAX_CHARS = 52_000 * 4


@pytest.fixture(scope="module")
def iris_planner():
    """Import iris_planner with stubbed config module, same pattern as planner-dry."""
    os.environ.setdefault("OPENCLAW_URL", "x")
    os.environ.setdefault("OPENCLAW_TOKEN", "x")
    os.environ.setdefault("OPENCLAW_SESSION_KEY", "x")

    cfg = types.ModuleType("config")
    cfg.OPENCLAW_URL = "x"
    cfg.OPENCLAW_TOKEN = "x"
    cfg.OPENCLAW_SESSION_KEY = "x"
    cfg.OPENCLAW_OPUS_AGENT_ID = "iris-planner"
    cfg.OPENCLAW_OPUS_SESSION_KEY = "x"
    cfg.OPENCLAW_LOCAL_AGENT_ID = "iris-planner-local"
    cfg.OPENCLAW_LOCAL_SESSION_KEY = "x"
    cfg.ENABLE_LOCAL_PLANNER = False
    sys.modules["config"] = cfg

    spec = importlib.util.spec_from_file_location(
        "iris_planner_variants",
        os.path.join(_WORKTREE, "ingestor", "iris_planner.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestComposePreamble:
    def test_both_instances_return_non_empty_strings(self, iris_planner):
        opus = iris_planner._compose_preamble("opus")
        local = iris_planner._compose_preamble("local")
        assert isinstance(opus, str) and len(opus) > 1000
        assert isinstance(local, str) and len(local) > 1000

    def test_opus_is_strict_superset_of_local(self, iris_planner):
        """Everything in local is also in opus (CORE is included in both)."""
        opus = iris_planner._compose_preamble("opus")
        local = iris_planner._compose_preamble("local")
        # Opus = directives + CORE + EXTENDED. Local = directives + CORE.
        # So local must be a prefix of opus (byte-exact) when the split is clean.
        assert opus.startswith(local), "local preamble must be a prefix of opus (same directives + CORE)"

    def test_lite_smaller_than_full(self, iris_planner):
        opus = iris_planner._compose_preamble("opus")
        local = iris_planner._compose_preamble("local")
        assert len(local) < len(opus)

    def test_local_preamble_fits_gemma_budget(self, iris_planner):
        """Contract §5-Q4: ≤60k gemma tokens → ≤52k Claude tokens → ≤208k chars."""
        local = iris_planner._compose_preamble("local")
        assert len(local) <= _LOCAL_PREAMBLE_MAX_CHARS, (
            f"local preamble {len(local)} chars exceeds {_LOCAL_PREAMBLE_MAX_CHARS} char budget "
            f"(≈ 52k Claude tokens / 60k gemma tokens)"
        )

    def test_default_instance_is_opus(self, iris_planner):
        default = iris_planner._compose_preamble()
        opus = iris_planner._compose_preamble("opus")
        assert default == opus


class TestSplitInvariants:
    def test_core_contains_structured_hypothesis(self, iris_planner):
        """G7: structured hypothesis guidance must reach both instances."""
        assert "Structured hypothesis" in iris_planner._PLANNER_CORE

    def test_core_contains_tier1_tunable_dictionary(self, iris_planner):
        """Phase-1d: prompt dropped from ~86 ALL_TUNABLES to Tier 1 only
        (the ~30 daily-use knobs from verdify_schemas.tunable_registry).
        Sprint-4's "dictionary of all 86" policy was the root cause of a
        prompt-bloat spiral (see plan: phase 1d). The registry is now the
        authoritative full list; the prompt only needs Tier 1 names
        literal + an escape-hatch reference for Tier 2."""
        from verdify_schemas.tunable_registry import REGISTRY

        assert "Tunable Dictionary — Tier 1" in iris_planner._PLANNER_CORE, "Tier 1 dictionary header missing"
        assert "docs/tunable-cascade.md" in iris_planner._PLANNER_CORE, (
            "escape-hatch reference to full cascade doc missing"
        )
        # Every Tier 1 param must appear as a literal token in CORE.
        tier1 = {n for n, d in REGISTRY.items() if d.planner_pushable and d.tier == 1}
        missing = sorted(t for t in tier1 if t not in iris_planner._PLANNER_CORE)
        assert not missing, f"CORE Tier-1 dictionary missing {len(missing)} params: {missing[:10]}"

    def test_core_contains_decision_precedence(self, iris_planner):
        assert "Decision Precedence" in iris_planner._PLANNER_CORE

    def test_extended_contains_validated_lessons(self, iris_planner):
        """Validated lessons are opus-only reference material."""
        assert "Validated Lessons" in iris_planner._PLANNER_EXTENDED

    def test_extended_contains_controller_modes(self, iris_planner):
        assert "Controller Modes" in iris_planner._PLANNER_EXTENDED

    def test_extended_does_not_duplicate_dictionary(self, iris_planner):
        """Dictionary header must appear exactly once (in CORE) — no duplication."""
        assert "Tunable Dictionary" not in iris_planner._PLANNER_EXTENDED

    def test_legacy_knowledge_alias_unchanged(self, iris_planner):
        """_PLANNER_KNOWLEDGE is the legacy concatenation; any consumer still
        using it sees both halves in their original order."""
        expected = iris_planner._PLANNER_CORE + iris_planner._PLANNER_EXTENDED
        assert iris_planner._PLANNER_KNOWLEDGE == expected


class TestPromptBuilders:
    @pytest.mark.parametrize("event", ["SUNRISE", "SUNSET", "TRANSITION", "FORECAST", "DEVIATION"])
    @pytest.mark.parametrize("instance", ["opus", "local"])
    def test_builder_renders_for_every_event_instance_pair(self, iris_planner, event, instance):
        builder = iris_planner._PROMPT_BUILDERS[event]
        message = builder("<context stub>", "<label stub>", instance)
        assert isinstance(message, str) and len(message) > 1000
        # Every prompt carries the standing directives so Iris sees the MCP tool inventory.
        assert "22 tools" in message

    @pytest.mark.parametrize("event", ["SUNRISE", "SUNSET", "TRANSITION", "FORECAST", "DEVIATION"])
    def test_local_prompt_smaller_than_opus_for_every_event(self, iris_planner, event):
        builder = iris_planner._PROMPT_BUILDERS[event]
        opus_msg = builder("<context stub>", "<label stub>", "opus")
        local_msg = builder("<context stub>", "<label stub>", "local")
        assert len(local_msg) < len(opus_msg)

    def test_builder_default_instance_is_opus(self, iris_planner):
        """Back-compat: existing callers that don't pass `instance` get opus."""
        builder = iris_planner._PROMPT_BUILDERS["SUNRISE"]
        default_msg = builder("<context stub>", "<label stub>")
        opus_msg = builder("<context stub>", "<label stub>", "opus")
        assert default_msg == opus_msg
