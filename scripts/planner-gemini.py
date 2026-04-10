#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""
planner-gemini.py — Greenhouse setpoint planner using Gemini via Google AI Studio.

Gathers live context, renders the planner prompt template, calls Gemini,
parses the structured JSON response, and writes waypoints + journal to the DB.

Usage:
    planner-gemini.py                  # run one planning cycle
    planner-gemini.py --dry-run        # gather context + render prompt, don't call API
    planner-gemini.py --greenhouse-id vallery
"""

import argparse
import asyncio
import json
import logging
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import asyncpg

sys.path.insert(0, str(Path(__file__).parent.parent / "ingestor"))
from ai_config import ai
from config import DB_DSN

logging.basicConfig(level=logging.INFO, format="%(asctime)s [planner] %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DENVER = ZoneInfo("America/Denver")


def gather_context(greenhouse_id: str) -> str:
    """Run gather-plan-context.sh and return live sensor/forecast data."""
    result = subprocess.run(
        ["bash", str(Path(__file__).parent / "gather-plan-context.sh"),
         "--greenhouse-id", greenhouse_id],
        capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        log.warning("gather-plan-context.sh returned %d: %s", result.returncode, result.stderr[:200])
    return result.stdout


def read_static_context() -> str:
    """Read the pre-built static greenhouse reference."""
    ctx_cfg = ai.config["context"]
    static_path = ai.template_path("planner", "static_context")
    if static_path.exists():
        text = static_path.read_text()
        max_chars = ctx_cfg.get("max_static_chars", 50000)
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[TRUNCATED at {max_chars} chars]\n"
        return text
    return ""


def build_prompt(greenhouse_id: str) -> str:
    """Render the planner prompt with live context injected."""
    dynamic_context = gather_context(greenhouse_id)
    static_context = read_static_context()
    return ai.render_template("planner", "prompt",
                             dynamic_context=dynamic_context,
                             static_context=static_context)


def parse_plan_json(text: str) -> dict:
    """Extract and parse JSON from Gemini's response."""
    # Strip markdown code fences if present
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*\n', '', text)
    text = re.sub(r'\n```\s*$', '', text)
    return json.loads(text)


async def write_plan_to_db(plan: dict, greenhouse_id: str) -> dict:
    """Write the parsed plan to the database. Returns summary stats."""
    conn = await asyncpg.connect(DB_DSN)
    stats = {"waypoints": 0, "journal": False, "validation": False, "lesson": False}

    try:
        async with conn.transaction():
            # 1. Deactivate all future waypoints from previous plans
            await conn.execute("SELECT fn_deactivate_future_plans()")

            # 2. Insert waypoints
            plan_id = plan["plan_id"]
            waypoints = plan.get("waypoints", [])
            for wp in waypoints:
                await conn.execute("""
                    INSERT INTO setpoint_plan (ts, parameter, value, plan_id, source, reason)
                    VALUES ($1, $2, $3, $4, 'iris', $5)
                """, datetime.fromisoformat(wp["ts"]), wp["parameter"],
                    float(wp["value"]), plan_id, wp.get("reason", ""))
            stats["waypoints"] = len(waypoints)

            # 3. Insert plan journal entry
            await conn.execute("""
                INSERT INTO plan_journal
                    (plan_id, conditions_summary, hypothesis, experiment,
                     expected_outcome, params_changed, greenhouse_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, plan_id,
                plan.get("conditions_summary", ""),
                plan.get("hypothesis", ""),
                plan.get("experiment", ""),
                plan.get("expected_outcome", ""),
                [wp["parameter"] for wp in waypoints[:10]],  # First 10 unique params
                greenhouse_id)
            stats["journal"] = True

            # 4. Validate previous plan if provided
            prev = plan.get("previous_plan_validation")
            if prev and prev.get("plan_id") and prev.get("score"):
                await conn.execute("""
                    UPDATE plan_journal SET
                        actual_outcome = $1,
                        outcome_score = $2,
                        lesson_extracted = $3,
                        validated_at = now()
                    WHERE plan_id = $4
                """, prev.get("actual_outcome", ""),
                    int(prev["score"]),
                    prev.get("lesson"),
                    prev["plan_id"])
                stats["validation"] = True

                # 5. Insert lesson if extracted
                lesson_text = prev.get("lesson")
                if lesson_text:
                    await conn.execute("""
                        INSERT INTO planner_lessons
                            (category, condition, lesson, confidence, source_plan_ids)
                        VALUES ('auto', 'auto-extracted', $1, 'low', $2)
                    """, lesson_text, [plan_id])
                    stats["lesson"] = True

    finally:
        await conn.close()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Verdify greenhouse setpoint planner")
    parser.add_argument("--dry-run", action="store_true", help="Render prompt without calling API")
    parser.add_argument("--greenhouse-id", default="vallery")
    args = parser.parse_args()

    log.info("Planner starting (model: %s, greenhouse: %s)",
             ai.model_name("planner"), args.greenhouse_id)

    # Build prompt
    log.info("Gathering context...")
    start = time.time()
    prompt = build_prompt(args.greenhouse_id)
    context_time = time.time() - start
    log.info("Context assembled: %d chars in %.1fs (~%d tokens)",
             len(prompt), context_time, len(prompt) // 4)

    if args.dry_run:
        print(prompt[:2000])
        print(f"\n... [{len(prompt)} chars total]")
        return

    # Call Gemini
    log.info("Calling %s...", ai.model_name("planner"))
    start = time.time()

    from google import genai
    client = ai.get_client("planner")
    response = client.models.generate_content(
        model=ai.model_name("planner"),
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            temperature=ai.temperature("planner"),
            max_output_tokens=ai.max_tokens("planner"),
            response_mime_type="application/json",
        ),
    )

    elapsed = time.time() - start
    output = response.text
    tokens = getattr(response, 'usage_metadata', None)

    log.info("Response: %d chars in %.1fs", len(output), elapsed)
    if tokens:
        log.info("Tokens: input=%s output=%s",
                 getattr(tokens, 'prompt_token_count', '?'),
                 getattr(tokens, 'candidates_token_count', '?'))

    # Parse JSON response
    try:
        plan = parse_plan_json(output)
    except json.JSONDecodeError as e:
        log.error("Failed to parse Gemini response as JSON: %s", e)
        log.error("Raw output (first 500 chars): %s", output[:500])
        sys.exit(1)

    log.info("Plan %s: %d waypoints, hypothesis: %s",
             plan.get("plan_id", "?"),
             len(plan.get("waypoints", [])),
             plan.get("hypothesis", "?")[:100])

    # Write to DB
    stats = asyncio.run(write_plan_to_db(plan, args.greenhouse_id))
    log.info("DB writes: %d waypoints, journal=%s, validation=%s, lesson=%s",
             stats["waypoints"], stats["journal"], stats["validation"], stats["lesson"])

    log.info("Planner complete (%.1fs context + %.1fs inference + DB write)",
             context_time, elapsed)


if __name__ == "__main__":
    main()
