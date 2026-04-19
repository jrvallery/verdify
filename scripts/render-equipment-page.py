#!/usr/bin/env python3
"""Render the equipment/relay map page from v_equipment_relay_map + equipment table.

Output: /mnt/iris/verdify-vault/website/greenhouse/equipment.md

Replaces the hand-typed Relay Map tables in equipment.md with DB-driven
content. Preserves the non-auto sections (Climate Control, Misting,
Lighting, etc.) — for now this renderer only regenerates the Relay Map
and appends an equipment catalog section.

Idempotent: only writes when content changes.

Usage:
    python scripts/render-equipment-page.py [--dry-run] [--out PATH]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_OUT = Path("/mnt/iris/verdify-vault/website/greenhouse/equipment.md")
DSN = os.environ.get(
    "VERDIFY_DSN",
    f"postgresql://verdify:{os.environ.get('POSTGRES_PASSWORD', 'verdify_tsdb_2026')}@127.0.0.1:5432/verdify",
)

FRONTMATTER = """---
title: Equipment
tags: [equipment, hardware, reference]
date: 2026-04-19
type: reference
---
"""


def _render_relay_table(rows: list[dict], board: str) -> str:
    filtered = [r for r in rows if r["board"] == board]
    if not filtered:
        return f"_No pins assigned on {board}._"
    lines = ["| Pin | Equipment | Zone | Purpose |", "|---|---|---|---|"]
    for r in sorted(filtered, key=lambda x: x["pin"]):
        eq = f"`{r['equipment_slug']}` ({r['equipment_name']})" if r.get("equipment_slug") else "_unused_"
        zone = r.get("zone_slug") or "—"
        lines.append(f"| {r['pin']} | {eq} | {zone} | {r['purpose']} |")
    return "\n".join(lines)


def _render_equipment_catalog(equipment: list[dict]) -> str:
    lines = [
        "| Slug | Kind | Name | Model | Zone | Watts | Cost/hr |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in sorted(equipment, key=lambda x: (x["kind"], x["slug"])):
        watts = f"{e['watts']:.0f}W" if e.get("watts") else "—"
        cost = f"${e['cost_per_hour_usd']:.3f}" if e.get("cost_per_hour_usd") else "—"
        zone = e.get("zone_slug") or "—"
        lines.append(
            f"| `{e['slug']}` | {e['kind']} | {e['name']} | {e.get('model') or '—'} | {zone} | {watts} | {cost} |"
        )
    return "\n".join(lines)


async def render(conn: asyncpg.Connection) -> str:
    relay_rows = await conn.fetch(
        "SELECT * FROM v_equipment_relay_map WHERE greenhouse_id = 'vallery' ORDER BY board, pin"
    )
    relay = [dict(r) for r in relay_rows]

    equipment_rows = await conn.fetch(
        """
        SELECT e.slug, e.kind, e.name, e.model, e.watts, e.cost_per_hour_usd,
               z.slug AS zone_slug
        FROM equipment e LEFT JOIN zones z ON z.id = e.zone_id
        WHERE e.greenhouse_id = 'vallery' AND e.is_active
        ORDER BY e.kind, e.slug
        """
    )
    equipment = [dict(r) for r in equipment_rows]

    body = f"""# Equipment Inventory

> Rendered from DB: equipment catalog + switches + zones.
> Source of truth: `v_equipment_relay_map` (migration 087) + `equipment` (migration 085).
> Do not edit by hand — run `scripts/render-equipment-page.py` to regenerate.

## Equipment Catalog

{_render_equipment_catalog(equipment)}

## Relay Map — PCF8574 pin assignments

### Output Expander 1 (pcf_out_1, 0x20)

{_render_relay_table(relay, "pcf_out_1")}

### Output Expander 2 (pcf_out_2, 0x21)

{_render_relay_table(relay, "pcf_out_2")}

### GPIO (direct pins)

{_render_relay_table(relay, "gpio")}
"""

    return FRONTMATTER + "\n" + body


async def run(args: argparse.Namespace) -> int:
    conn = await asyncpg.connect(DSN)
    try:
        content = await render(conn)
    finally:
        await conn.close()

    target = Path(args.out)
    existing = target.read_text() if target.exists() else ""
    if existing == content:
        print(f"  UNCHANGED  {target}")
        return 0
    if args.dry_run:
        print(f"  WOULD WRITE  {target} ({len(content)} chars)")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    print(f"  WROTE  {target}")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default=str(DEFAULT_OUT), help="Output file")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
