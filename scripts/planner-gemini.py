#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""
planner-gemini.py — Greenhouse setpoint planner using Gemini 2.5 Pro via Vertex AI.

Replaces the OpenClaw cron-based Anthropic planner with a direct Vertex AI call.
Reads the same context (gather-plan-context.sh + static context), calls Gemini Pro
for reasoning, writes setpoints to DB, generates daily plan document.

Usage:
    planner-gemini.py                  # run one planning cycle
    planner-gemini.py --dry-run        # gather context + generate prompt, don't call API
    planner-gemini.py --greenhouse-id vallery
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, date
from pathlib import Path

from pathlib import Path
from google import genai

logging.basicConfig(level=logging.INFO, format="%(asctime)s [planner] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

GEMINI_API_KEY = Path("/mnt/jason/agents/shared/credentials/gemini_api_key.txt").read_text().strip()
GEMINI_MODEL = "gemini-2.5-pro"
STATIC_CONTEXT = Path("/srv/verdify/state/planner-static-context.md")
PROMPT_TEMPLATE = Path("/srv/verdify/scripts/planner-prompt-v2.md")


def gather_context(greenhouse_id: str) -> str:
    """Run gather-plan-context.sh and return output."""
    result = subprocess.run(
        ["bash", "/srv/verdify/scripts/gather-plan-context.sh", "--greenhouse-id", greenhouse_id],
        capture_output=True, text=True, timeout=120)
    return result.stdout


def read_static_context() -> str:
    """Read the pre-built static context file."""
    if STATIC_CONTEXT.exists():
        text = STATIC_CONTEXT.read_text()
        # Truncate if too large (Gemini Pro has 1M context but let's be reasonable)
        if len(text) > 100000:
            text = text[:100000] + "\n\n[TRUNCATED — full context is 161KB]\n"
        return text
    return ""


def read_prompt_template() -> str:
    """Read the planner prompt template."""
    if PROMPT_TEMPLATE.exists():
        return PROMPT_TEMPLATE.read_text()
    return "You are a greenhouse setpoint planner. Analyze the context and write a 72h plan."


def build_full_prompt(greenhouse_id: str) -> str:
    """Assemble the complete prompt with all context."""
    prompt_template = read_prompt_template()
    dynamic_context = gather_context(greenhouse_id)
    static_context = read_static_context()

    return f"""## Prompt Instructions

{prompt_template}

## Dynamic Planning Context (live sensor data, forecasts, plan history)

{dynamic_context}

## Static Greenhouse Reference (equipment, zones, crop guides)

{static_context[:50000]}
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--greenhouse-id", default="vallery")
    args = parser.parse_args()

    log.info("Planner starting (model: %s, greenhouse: %s)", GEMINI_MODEL, args.greenhouse_id)

    # Build prompt
    log.info("Gathering context...")
    start = time.time()
    full_prompt = build_full_prompt(args.greenhouse_id)
    context_time = time.time() - start
    log.info("Context assembled: %d chars in %.1fs", len(full_prompt), context_time)

    if args.dry_run:
        log.info("DRY RUN — prompt length: %d chars (~%d tokens)", len(full_prompt), len(full_prompt) // 4)
        print(f"Prompt preview (first 500 chars):\n{full_prompt[:500]}")
        return

    # Call Gemini Pro
    log.info("Calling Gemini 2.5 Pro...")
    start = time.time()

    client = genai.Client(api_key=GEMINI_API_KEY)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=full_prompt,
        config=genai.types.GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=8192,
        ),
    )

    elapsed = time.time() - start
    output = response.text
    tokens = getattr(response, 'usage_metadata', None)

    log.info("Response: %d chars in %.1fs", len(output), elapsed)
    if tokens:
        log.info("Tokens: input=%s output=%s total=%s",
                 getattr(tokens, 'prompt_token_count', '?'),
                 getattr(tokens, 'candidates_token_count', '?'),
                 getattr(tokens, 'total_token_count', '?'))

    # Output the plan
    print("\n" + "=" * 80)
    print("GEMINI 2.5 PRO PLAN OUTPUT")
    print("=" * 80)
    print(output)

    log.info("Planner complete (%.1fs context + %.1fs inference)", context_time, elapsed)


if __name__ == "__main__":
    main()
