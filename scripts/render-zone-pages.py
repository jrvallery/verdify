#!/usr/bin/env python3
"""Render zone pages from v_zone_full + v_position_current.

Generates `/mnt/iris/verdify-vault/website/greenhouse/zones/{slug}.md` for
every active zone, pulling sensors, equipment, water systems, and current
plantings from the Sprint 22/23 topology tables + history views.

Idempotent: compares rendered content against existing file, only writes
when the content (below the frontmatter) changes, so Quartz's 10s poll
doesn't rebuild on every run.

Usage:
    python scripts/render-zone-pages.py [--dry-run] [--zone SLUG] [--out DIR]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from verdify_schemas.vault import VaultFrontmatter  # noqa: E402

DEFAULT_OUT = Path("/mnt/iris/verdify-vault/website/greenhouse/zones")
DSN = os.environ.get(
    "VERDIFY_DSN",
    f"postgresql://verdify:{os.environ.get('POSTGRES_PASSWORD', 'verdify_tsdb_2026')}@127.0.0.1:5432/verdify",
)


class ZoneFrontmatter(VaultFrontmatter):
    """Frontmatter for the rendered zone pages."""

    title: str
    date: str  # ISO date string
    type: str = "zone"
    zone: str
    zone_name: str | None = None
    sensor: str | None = None
    orientation: str | None = None
    water_systems: list[str]
    position_scheme: str | None = None
    peak_temp: str | None = None
    status: str


def _render_shelves_table(shelves: list[dict]) -> str:
    if not shelves:
        return "_No shelves defined for this zone._"
    lines = ["| Shelf | Kind | Tier | Position scheme |", "|---|---|---|---|"]
    for s in sorted(shelves, key=lambda x: (x.get("tier") or -1, x.get("slug") or "")):
        lines.append(
            f"| {s.get('name') or s.get('slug')} | {s['kind']} | {s.get('tier') if s.get('tier') is not None else '—'} | `{s.get('position_scheme') or '—'}` |"
        )
    return "\n".join(lines)


def _render_equipment_table(equipment: list[dict]) -> str:
    if not equipment:
        return "_No equipment assigned to this zone._"
    lines = [
        "| Equipment | Kind | Model | Watts | Cost/hr |",
        "|---|---|---|---|---|",
    ]
    for e in sorted(equipment, key=lambda x: (x["kind"], x["slug"])):
        watts = f"{e['watts']:.0f}W" if e.get("watts") else "—"
        cost = f"${e['cost_per_hour_usd']:.3f}" if e.get("cost_per_hour_usd") else "—"
        lines.append(f"| `{e['slug']}` ({e['name']}) | {e['kind']} | {e.get('model') or '—'} | {watts} | {cost} |")
    return "\n".join(lines)


def _render_sensors_table(sensors: list[dict]) -> str:
    if not sensors:
        return "_No sensors assigned to this zone._"
    lines = ["| Sensor | Kind | Protocol | Model | Addr |", "|---|---|---|---|---|"]
    for s in sorted(sensors, key=lambda x: x["slug"]):
        addr = s.get("modbus_addr") or s.get("gpio_pin") or "—"
        lines.append(f"| `{s['slug']}` | {s['kind']} | {s['protocol']} | {s.get('model') or '—'} | {addr} |")
    return "\n".join(lines)


def _render_water_systems_table(water_systems: list[dict]) -> str:
    if not water_systems:
        return "_No water systems in this zone._"
    lines = [
        "| System | Kind | Heads | Nozzles | Mount | Fert |",
        "|---|---|---|---|---|---|",
    ]
    for w in sorted(water_systems, key=lambda x: (x["kind"], x["slug"])):
        lines.append(
            f"| `{w['slug']}` ({w['name']}) | {w['kind']} | "
            f"{w.get('head_count') or '—'} | {w.get('nozzle_count') or '—'} | "
            f"{w.get('mount') or '—'} | {'yes' if w.get('is_fert_path') else 'no'} |"
        )
    return "\n".join(lines)


def _render_current_crops_table(crops: list[dict]) -> str:
    if not crops:
        return "_No active crops in this zone._"
    lines = [
        "| Position | Crop | Stage | Planted | Days in place |",
        "|---|---|---|---|---|",
    ]
    for c in sorted(crops, key=lambda x: x["position_label"]):
        if not c.get("is_occupied"):
            continue
        lines.append(
            f"| `{c['position_label']}` | {c['crop_name']}"
            f"{' (' + c['crop_variety'] + ')' if c.get('crop_variety') else ''} "
            f"| {c.get('crop_stage') or '—'} | {c.get('crop_planted_date') or '—'} "
            f"| {c.get('crop_days_in_place') or 0} |"
        )
    if len(lines) == 2:  # no occupied rows appended
        return "_No active crops in this zone._"
    return "\n".join(lines)


def _yaml_dumps(fm: dict) -> str:
    """Emit YAML without importing pyyaml (keep the script dependency-light)."""
    import yaml

    return yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()


async def render_zone(conn: asyncpg.Connection, zone_slug: str) -> tuple[str, str] | None:
    """Return (filename, markdown_body) for the zone, or None if not found."""
    row = await conn.fetchrow(
        "SELECT * FROM v_zone_full WHERE greenhouse_id = 'vallery' AND zone_slug = $1",
        zone_slug,
    )
    if row is None:
        return None
    d = dict(row)
    # JSONB arrays arrive as str — parse them.
    for k in ("shelves", "sensors", "equipment", "water_systems"):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])

    # Current plantings
    plantings = await conn.fetch(
        "SELECT * FROM v_position_current WHERE zone_slug = $1 AND greenhouse_id = 'vallery'",
        zone_slug,
    )
    plantings_list = [dict(r) for r in plantings]

    status = d.get("zone_status") or "active"
    position_scheme = ", ".join(s.get("position_scheme") for s in d["shelves"] if s.get("position_scheme")) or None

    water_system_slugs = [w["slug"] for w in d["water_systems"]]

    fm = ZoneFrontmatter(
        title=f"{d['zone_name']}",
        date="2026-04-19",
        zone=zone_slug,
        zone_name=d["zone_name"],
        sensor=(f"Modbus addr {d['sensor_modbus_addr']}" if d.get("sensor_modbus_addr") else "Derived"),
        orientation=d.get("orientation"),
        water_systems=water_system_slugs,
        position_scheme=position_scheme,
        peak_temp=f"{d['peak_temp_f']}°F" if d.get("peak_temp_f") else None,
        status=status,
    )
    fm_yaml = _yaml_dumps(fm.model_dump(exclude_none=True))

    body = f"""# {d["zone_name"]}

> Rendered from DB: zones + shelves + positions + sensors + equipment + water_systems.
> Source of truth: `v_zone_full` (migration 087) + `v_position_current` (migration 089).
> Do not edit by hand — run `scripts/render-zone-pages.py` to regenerate.

## Current Plantings

{_render_current_crops_table(plantings_list)}

## Shelves

{_render_shelves_table(d["shelves"])}

## Sensors

{_render_sensors_table(d["sensors"])}

## Equipment

{_render_equipment_table(d["equipment"])}

## Water Systems

{_render_water_systems_table(d["water_systems"])}

## Zone Profile

| Field | Value |
|---|---|
| Slug | `{zone_slug}` |
| Name | {d["zone_name"]} |
| Orientation | {d.get("orientation") or "—"} |
| Status | {status} |
| Sensor Modbus addr | {d.get("sensor_modbus_addr") or "—"} |
| Peak temperature | {(str(d["peak_temp_f"]) + "°F") if d.get("peak_temp_f") else "—"} |
| Position scheme | `{position_scheme or "—"}` |
| Active crops (FK) | {d.get("active_crops_fk_count") or 0} |
"""

    rendered = f"---\n{fm_yaml}\n---\n\n{body}"
    return f"{zone_slug}.md", rendered


async def run(args: argparse.Namespace) -> int:
    conn = await asyncpg.connect(DSN)
    try:
        if args.zone:
            zones = [args.zone]
        else:
            rows = await conn.fetch(
                "SELECT slug FROM zones WHERE greenhouse_id = 'vallery' AND status = 'active' ORDER BY slug"
            )
            zones = [r["slug"] for r in rows]

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)

        changes = 0
        for slug in zones:
            result = await render_zone(conn, slug)
            if result is None:
                print(f"  SKIP {slug}: not found in v_zone_full")
                continue
            filename, content = result
            target = out_dir / filename
            existing = target.read_text() if target.exists() else ""
            if existing == content:
                print(f"  UNCHANGED  {filename}")
                continue
            if args.dry_run:
                print(f"  WOULD WRITE  {filename} ({len(content)} chars, {content.count('\n')} lines)")
            else:
                target.write_text(content)
                print(f"  WROTE  {filename}")
            changes += 1

        print(f"\n{'Would change' if args.dry_run else 'Changed'} {changes} zone page(s)")
    finally:
        await conn.close()
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zone", help="Render only this zone slug (default: all active zones)")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="Output directory")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
