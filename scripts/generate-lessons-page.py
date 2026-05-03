#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""Generate the Lessons Learned page from planner_lessons table.

Outputs: /srv/verdify/verdify-site/content/greenhouse/lessons.md
"""

import os
import re
import subprocess
import sys
from datetime import date

import yaml

sys.path.insert(0, "/mnt/iris/verdify")
from verdify_schemas import LessonsVaultFrontmatter  # noqa: E402

DB_CONTAINER = "verdify-timescaledb"
DB_USER = "verdify"
DB_NAME = "verdify"
OUTPUT_PATH = "/srv/verdify/verdify-site/content/greenhouse/lessons.md"


def query_db(sql: str) -> str:
    """Run a SQL query via docker exec and return raw output."""
    result = subprocess.run(
        ["docker", "exec", DB_CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-F", "\t", "-c", sql],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"DB error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def plan_id_to_link(plan_id: str) -> str:
    """Convert a plan_id like 'iris-20260325-1201' to a markdown link.

    URL: /plans/2026-03-25 (no trailing slash)
    Label: the plan_id itself
    """
    m = re.match(r"iris-(\d{4})(\d{2})(\d{2})", plan_id)
    if not m:
        return plan_id  # Can't parse — return as plain text
    plan_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return f"[{plan_id}](/plans/{plan_date})"


def fetch_lessons(active: bool) -> list[dict]:
    """Fetch lessons from the database."""
    flag = "true" if active else "false"
    sql = f"""
        SELECT id, category, condition, lesson, confidence,
               times_validated, source_plan_ids,
               created_at::date, last_validated::date,
               superseded_by
        FROM planner_lessons
        WHERE is_active = {flag}
        ORDER BY id;
    """
    raw = query_db(sql)
    if not raw:
        return []

    lessons = []
    for line in raw.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 10:
            continue
        # Parse source_plan_ids from postgres array format {a,b,c}
        raw_ids = parts[6].strip("{}")
        plan_ids = [p.strip() for p in raw_ids.split(",") if p.strip()] if raw_ids else []

        lessons.append(
            {
                "id": int(parts[0]),
                "category": parts[1],
                "condition": parts[2],
                "lesson": parts[3],
                "confidence": parts[4],
                "times_validated": int(parts[5]),
                "source_plan_ids": plan_ids,
                "created_at": parts[7],
                "last_validated": parts[8],
                "superseded_by": int(parts[9]) if parts[9].strip() else None,
            }
        )
    return lessons


def render_lesson(lesson: dict, include_superseded_note: bool = False) -> str:
    """Render a single lesson as markdown."""
    lines = []
    # Build a short title from the lesson text — take first sentence or clause
    text = lesson["lesson"]
    # Try first sentence (period-terminated)
    dot = text.find(". ")
    title = text[:dot] if 0 < dot <= 80 else text[:60].rsplit(" ", 1)[0]
    lines.append(f"### #{lesson['id']} — {title}")
    lines.append("")

    conf = lesson["confidence"].capitalize()
    lines.append(
        f"**Category:** {lesson['category'].capitalize()} | "
        f"**Confidence:** {conf} | "
        f"**Validated:** {lesson['times_validated']}×"
    )
    lines.append("")
    lines.append(f"**When:** {lesson['condition']}")
    lines.append("")
    lines.append(f"**Finding:** {lesson['lesson']}")
    lines.append("")

    # Source plan links
    if lesson["source_plan_ids"]:
        first_link = plan_id_to_link(lesson["source_plan_ids"][0])
        last_link = plan_id_to_link(lesson["source_plan_ids"][-1])
        lines.append(f"**First proven:** {first_link} | **Last confirmed:** {last_link}")
    else:
        lines.append(f"**Created:** {lesson['created_at']}")

    if include_superseded_note and lesson.get("superseded_by"):
        lines.append("")
        lines.append(f"*Superseded by lesson #{lesson['superseded_by']}*")

    lines.append("")
    return "\n".join(lines)


def generate_page() -> str:
    """Generate the full lessons.md content."""
    active = fetch_lessons(active=True)
    superseded = fetch_lessons(active=False)
    today = date.today().isoformat()

    parts = []

    # Sprint 22: frontmatter validated through LessonsVaultFrontmatter
    fm = LessonsVaultFrontmatter(
        date=date.today(),
        tags=["greenhouse", "planning", "lessons"],
        aliases=["intelligence/lessons", "operations/lessons-learned"],
    )
    yaml_block = yaml.safe_dump(
        fm.model_dump(mode="json", exclude_none=True),
        sort_keys=False,
        default_flow_style=None,
    )
    yaml_block = re.sub(r"^title: .*$", "title: AI Greenhouse Lessons Learned", yaml_block, flags=re.MULTILINE)
    yaml_block += (
        "description: \"Generated and validated lessons from Verdify's AI greenhouse planning cycles: "
        'what worked, what failed, and what Iris reads before future plans."\n'
    )
    parts.append("---")
    parts.append(yaml_block.rstrip())
    parts.append("---")
    parts.append("")
    parts.append("[//]: # (auto-generated by scripts/generate-lessons-page.py; source: planner_lessons)")
    parts.append("")

    # Intro
    parts.append("# AI Greenhouse Lessons Learned")
    parts.append("")
    parts.append(
        "Findings validated through hypothesis-driven planning cycles. "
        "Each lesson was tested, measured, and confirmed before graduating here."
    )
    parts.append("")

    # Active lessons
    parts.append("## Active Lessons")
    parts.append("")
    if active:
        for lesson in active:
            parts.append(render_lesson(lesson))
    else:
        parts.append("*No active lessons yet.*")
        parts.append("")

    # Superseded lessons
    parts.append("## Superseded Lessons")
    parts.append("")
    if superseded:
        for lesson in superseded:
            parts.append(render_lesson(lesson, include_superseded_note=True))
    else:
        parts.append("*No superseded lessons yet.*")
        parts.append("")

    # Lesson Lifecycle
    parts.append("## Lesson Lifecycle")
    parts.append("")
    parts.append("1. **Hypothesis** — Planner proposes a theory during a planning cycle")
    parts.append("2. **Test** — Specific setpoint changes are made with measurable expected outcomes")
    parts.append("3. **Validate** — Next cycle scores the result (1–10) and extracts findings")
    parts.append('4. **Graduate** — If finding is significant, it\'s added to this page at confidence "low"')
    parts.append("5. **Confirm** — Each re-validation bumps confidence (low → medium at 3×, high at 5×)")
    parts.append("6. **Supersede** — If a better approach is found, old lesson is marked superseded")
    parts.append("")

    return "\n".join(parts)


def main():
    content = generate_page()
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        f.write(content)
    print(f"Lessons page written to {OUTPUT_PATH} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
