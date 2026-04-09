#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""
crop-parser.py — Parse natural-language crop updates → structured DB records.

Usage:
    crop-parser.py --message "Planted basil in HYDRO-5"
    crop-parser.py --message "Harvested lettuce from HYDRO-12, 200g" --operator emily
    crop-parser.py --message "Strawberries in HYDRO-3 look wilted" --image-url http://...
"""

import asyncio
import json
import os
import re
import sys
from datetime import date

import asyncpg

# ── Position taxonomy ──
POSITION_RE = re.compile(
    r'(HYDRO-\d{1,2}|'
    r'(?:NORTH|SOUTH|EAST|WEST)-SHELF-[TB]\d|'
    r'CENTER-HANG-[12]|'
    r'CENTER-FLOOR-\d)', re.IGNORECASE
)

ZONE_FROM_POSITION = {
    "HYDRO": "east",
    "NORTH": "north", "SOUTH": "south", "EAST": "east", "WEST": "west",
    "CENTER": "center",
}

VALID_STAGES = [
    "seed", "germinating", "seedling", "vegetative", "flowering",
    "fruiting", "harvest_ready", "harvested", "removed", "failed"
]

# ── Action detection ──
ACTION_PATTERNS = [
    (r'\bplant(?:ed|ing)?\b', "planted"),
    (r'\bsow(?:ed|n|ing)?\b', "planted"),
    (r'\bstart(?:ed|ing)?\b', "planted"),
    (r'\bmov(?:ed|ing|e)\b', "moved"),
    (r'\btransplant(?:ed|ing)?\b', "moved"),
    (r'\bharvest(?:ed|ing)?\b', "harvested"),
    (r'\bpick(?:ed|ing)?\b', "harvested"),
    (r'\bpull(?:ed|ing)?\b', "harvested"),
    (r'\bremov(?:ed|ing|e)\b', "removed"),
    (r'\bdied?\b|\bfail(?:ed|ing)?\b|\bdead\b', "failed"),
    (r'\bprun(?:ed|ing|e)\b', "pruned"),
    (r'\bwater(?:ed|ing)?\b', "watered"),
    (r'\bfertiliz(?:ed|ing|e)\b|\bfed\b|\bfeed(?:ing)?\b', "fertilized"),
    (r'\bwilt(?:ed|ing|s)?\b|\byellow(?:ing|ed)?\b|\bspot(?:s|ted)?\b|\bbug(?:s)?\b|\bpest\b|\bmold(?:y)?\b|\brot(?:ting|ten)?\b', "observed"),
    (r'\blook(?:s|ing)?\b.*\b(?:good|great|healthy|strong|bad|sick|off)\b', "observed"),
]

# ── Common crop names ──
CROPS = [
    "basil", "tomato", "tomatoes", "lettuce", "strawberry", "strawberries",
    "pepper", "peppers", "cilantro", "mint", "oregano", "thyme", "rosemary",
    "cucumber", "cucumbers", "spinach", "kale", "arugula", "chard",
    "canna", "canna lily", "canna lilies", "marigold", "petunia",
    "sage", "dill", "parsley", "chives", "lavender",
]
CROP_RE = re.compile(r'\b(' + '|'.join(CROPS) + r')(?:s|es)?\b', re.IGNORECASE)

# Singularize
SINGULAR = {"tomatoes": "tomato", "strawberries": "strawberry", "peppers": "pepper",
            "cucumbers": "cucumber", "canna lilies": "canna lily"}


def get_db_url() -> str:
    pw = "verdify"
    if os.path.exists("/srv/verdify/.env"):
        with open("/srv/verdify/.env") as f:
            for line in f:
                if line.strip().startswith("POSTGRES_PASSWORD="):
                    pw = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return f"postgresql://verdify:{pw}@localhost:5432/verdify"


def parse_message(msg: str) -> dict:
    result = {
        "crop": None, "variety": None, "position": None, "zone": None,
        "action": None, "stage": None, "count": None, "weight_g": None,
        "notes": msg, "needs_clarification": None,
    }

    # Position
    pos_match = POSITION_RE.search(msg)
    if pos_match:
        result["position"] = pos_match.group(0).upper()
        prefix = result["position"].split("-")[0]
        result["zone"] = ZONE_FROM_POSITION.get(prefix, "unknown")

    # Crop name
    crop_match = CROP_RE.search(msg)
    if crop_match:
        name = crop_match.group(0).lower()
        result["crop"] = SINGULAR.get(name, name).title()

    # Action
    for pattern, action in ACTION_PATTERNS:
        if re.search(pattern, msg, re.IGNORECASE):
            result["action"] = action
            break

    # Stage (explicit mention)
    for stage in VALID_STAGES:
        if re.search(r'\b' + stage + r'\b', msg, re.IGNORECASE):
            result["stage"] = stage
            break

    # Default stage from action
    if not result["stage"]:
        if result["action"] == "planted":
            result["stage"] = "seedling"
        elif result["action"] == "harvested":
            result["stage"] = "harvested"
        elif result["action"] == "failed":
            result["stage"] = "failed"
        elif result["action"] == "removed":
            result["stage"] = "removed"

    # Count
    count_match = re.search(r'(\d+)\s*(?:plants?|seeds?|starts?|pots?|pods?)', msg, re.IGNORECASE)
    if count_match:
        result["count"] = int(count_match.group(1))

    # Weight (for harvests)
    weight_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:g|grams?|oz|ounces?|lb|lbs?|kg)', msg, re.IGNORECASE)
    if weight_match:
        result["weight_g"] = float(weight_match.group(1))
        unit = re.search(r'(oz|lb|kg)', msg, re.IGNORECASE)
        if unit:
            u = unit.group(1).lower()
            if u == "oz":
                result["weight_g"] *= 28.35
            elif u in ("lb", "lbs"):
                result["weight_g"] *= 453.6
            elif u == "kg":
                result["weight_g"] *= 1000

    # Clarification needed?
    if result["action"] in ("planted", "moved") and not result["position"]:
        result["needs_clarification"] = "Which position? (e.g. HYDRO-5, EAST-SHELF-T1)"
    elif result["action"] in ("planted",) and not result["crop"]:
        result["needs_clarification"] = "What crop? (e.g. basil, tomato, lettuce)"
    elif not result["action"]:
        # Default to observation if we have a crop or position
        if result["crop"] or result["position"]:
            result["action"] = "observed"
        else:
            result["needs_clarification"] = "I couldn't understand that. Try: 'Planted basil in HYDRO-5' or 'Strawberries in HYDRO-3 look wilted'"

    return result


async def execute(parsed: dict, operator: str, image_url: str | None) -> dict:
    response = {"action": parsed["action"], "crop_id": None,
                "position": parsed["position"], "message": "", "needs_clarification": parsed["needs_clarification"]}

    if parsed["needs_clarification"]:
        response["message"] = parsed["needs_clarification"]
        return response

    conn = await asyncpg.connect(get_db_url())
    try:
        action = parsed["action"]

        if action == "planted":
            crop_id = await conn.fetchval("""
                INSERT INTO crops (name, variety, position, zone, stage, planted_date, count, is_active)
                VALUES ($1, $2, $3, $4, $5, CURRENT_DATE, $6, true) RETURNING id
            """, parsed["crop"], parsed["variety"], parsed["position"], parsed["zone"],
                parsed["stage"] or "seedling", parsed["count"])

            await conn.execute("""
                INSERT INTO crop_events (crop_id, event_type, new_stage, operator, source, notes)
                VALUES ($1, 'planted', $2, $3, 'slack', $4)
            """, crop_id, parsed["stage"] or "seedling", operator, parsed["notes"])

            response["crop_id"] = crop_id
            response["message"] = f"Got it — {parsed['crop']} planted in {parsed['position']}, stage: {parsed['stage'] or 'seedling'}"

        elif action == "moved":
            # Find existing crop to move
            crop = await conn.fetchrow(
                "SELECT id, position, stage FROM crops WHERE name ILIKE $1 AND is_active ORDER BY id DESC LIMIT 1",
                f"%{parsed['crop']}%"
            ) if parsed["crop"] else None

            if crop:
                old_pos = crop["position"]
                await conn.execute(
                    "UPDATE crops SET position = $1, zone = $2, updated_at = now() WHERE id = $3",
                    parsed["position"], parsed["zone"], crop["id"]
                )
                await conn.execute("""
                    INSERT INTO crop_events (crop_id, event_type, operator, source, notes)
                    VALUES ($1, 'moved', $2, 'slack', $3)
                """, crop["id"], operator, f"Moved from {old_pos} to {parsed['position']}")
                response["crop_id"] = crop["id"]
                response["message"] = f"Moved {parsed['crop']} from {old_pos} to {parsed['position']}"
            else:
                response["needs_clarification"] = f"Can't find active crop '{parsed['crop']}' to move"
                response["message"] = response["needs_clarification"]

        elif action == "harvested":
            crop = await conn.fetchrow(
                "SELECT id, position FROM crops WHERE name ILIKE $1 AND is_active ORDER BY id DESC LIMIT 1",
                f"%{parsed['crop']}%" if parsed["crop"] else "%"
            )
            if not crop and parsed["position"]:
                crop = await conn.fetchrow(
                    "SELECT id, name FROM crops WHERE position = $1 AND is_active", parsed["position"]
                )

            if crop:
                await conn.execute(
                    "UPDATE crops SET stage = 'harvested', is_active = false, updated_at = now() WHERE id = $1",
                    crop["id"]
                )
                weight_note = f", {parsed['weight_g']:.0f}g" if parsed.get("weight_g") else ""
                await conn.execute("""
                    INSERT INTO crop_events (crop_id, event_type, new_stage, operator, source, notes)
                    VALUES ($1, 'harvested', 'harvested', $2, 'slack', $3)
                """, crop["id"], operator, parsed["notes"])
                response["crop_id"] = crop["id"]
                response["message"] = f"Harvested from {crop.get('position', '?')}{weight_note}"
            else:
                response["needs_clarification"] = "Which crop? I can't find it."
                response["message"] = response["needs_clarification"]

        elif action in ("failed", "removed"):
            crop = await conn.fetchrow(
                "SELECT id, position FROM crops WHERE name ILIKE $1 AND is_active ORDER BY id DESC LIMIT 1",
                f"%{parsed['crop']}%" if parsed["crop"] else "%"
            )
            if crop:
                await conn.execute(
                    "UPDATE crops SET stage = $1, is_active = false, updated_at = now() WHERE id = $2",
                    action, crop["id"]
                )
                await conn.execute("""
                    INSERT INTO crop_events (crop_id, event_type, new_stage, operator, source, notes)
                    VALUES ($1, $2, $2, $3, 'slack', $4)
                """, crop["id"], action, operator, parsed["notes"])
                response["crop_id"] = crop["id"]
                response["message"] = f"Marked {parsed['crop']} as {action} in {crop['position']}"
            else:
                response["needs_clarification"] = f"Can't find '{parsed['crop']}'"
                response["message"] = response["needs_clarification"]

        elif action in ("observed", "pruned", "watered", "fertilized"):
            # Find crop if identifiable
            crop_id = None
            if parsed["crop"]:
                row = await conn.fetchrow(
                    "SELECT id FROM crops WHERE name ILIKE $1 AND is_active ORDER BY id DESC LIMIT 1",
                    f"%{parsed['crop']}%"
                )
                crop_id = row["id"] if row else None
            elif parsed["position"]:
                row = await conn.fetchrow(
                    "SELECT id FROM crops WHERE position = $1 AND is_active", parsed["position"]
                )
                crop_id = row["id"] if row else None

            obs_type = action if action != "observed" else "general"
            await conn.execute("""
                INSERT INTO observations (obs_type, zone, position, crop_id, photo_path, observer, source, notes)
                VALUES ($1, $2, $3, $4, $5, $6, 'slack', $7)
            """, obs_type, parsed["zone"], parsed["position"], crop_id,
                image_url, operator, parsed["notes"])

            if action in ("pruned", "watered", "fertilized") and crop_id:
                await conn.execute("""
                    INSERT INTO crop_events (crop_id, event_type, operator, source, notes)
                    VALUES ($1, $2, $3, 'slack', $4)
                """, crop_id, action, operator, parsed["notes"])

            response["crop_id"] = crop_id
            crop_name = parsed["crop"] or "greenhouse"
            response["message"] = f"Noted — {obs_type} observation for {crop_name}"
            if parsed["position"]:
                response["message"] += f" at {parsed['position']}"

    finally:
        await conn.close()

    return response


async def main():
    args = sys.argv[1:]
    message = ""
    operator = "unknown"
    image_url = None

    i = 0
    while i < len(args):
        if args[i] == "--message" and i + 1 < len(args):
            message = args[i + 1]; i += 2
        elif args[i] == "--operator" and i + 1 < len(args):
            operator = args[i + 1]; i += 2
        elif args[i] == "--image-url" and i + 1 < len(args):
            image_url = args[i + 1]; i += 2
        else:
            i += 1

    if not message:
        print(json.dumps({"error": "No --message provided"}))
        sys.exit(1)

    parsed = parse_message(message)
    result = await execute(parsed, operator, image_url)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
