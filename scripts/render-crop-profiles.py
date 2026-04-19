#!/usr/bin/env python3
"""Render crop profile pages from crop_catalog + v_crop_catalog_with_profiles.

Outputs `/mnt/iris/verdify-vault/website/greenhouse/crops/{slug}.md` for
every catalog entry. For each crop:
  - Frontmatter with slug, category, season, cycle_days
  - Stage/season band aggregates from v_crop_catalog_with_profiles
  - Active plantings of this crop type (from v_position_current)
  - Historical plantings (from v_crop_history)

Idempotent — writes only when content changes.

Usage:
    python scripts/render-crop-profiles.py [--dry-run] [--slug CROP] [--out DIR]
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

DEFAULT_OUT = Path("/mnt/iris/verdify-vault/website/greenhouse/crops")
DSN = os.environ.get(
    "VERDIFY_DSN",
    f"postgresql://verdify:{os.environ.get('POSTGRES_PASSWORD', 'verdify_tsdb_2026')}@127.0.0.1:5432/verdify",
)


def _yaml_dumps(fm: dict) -> str:
    import yaml

    return yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()


def _render_stage_band_table(profiles: list[dict]) -> str:
    if not profiles:
        return "_No hourly target profiles defined for this crop yet._"
    lines = [
        "| Stage | Season | Hours covered | Temp ideal (24h avg) | VPD ideal (24h avg) | DLI target |",
        "|---|---|---|---|---|---|",
    ]
    for p in sorted(profiles, key=lambda x: (x["growth_stage"], x["season"])):
        t_lo = p.get("temp_ideal_min_24h")
        t_hi = p.get("temp_ideal_max_24h")
        v_lo = p.get("vpd_ideal_min_24h")
        v_hi = p.get("vpd_ideal_max_24h")
        dli = p.get("dli_target_mol")
        temp_range = f"{float(t_lo):.1f}–{float(t_hi):.1f}°F" if t_lo and t_hi else "—"
        vpd_range = f"{float(v_lo):.2f}–{float(v_hi):.2f} kPa" if v_lo and v_hi else "—"
        lines.append(
            f"| {p['growth_stage']} | {p['season']} | {p['hours_covered']} | "
            f"{temp_range} | {vpd_range} | {f'{float(dli):.1f}' if dli else '—'} |"
        )
    return "\n".join(lines)


def _render_current_plantings(current: list[dict]) -> str:
    if not current:
        return "_No active plantings of this crop type right now._"
    lines = ["| Position | Stage | Planted | Days in place |", "|---|---|---|---|"]
    for c in sorted(current, key=lambda x: x["position_label"] or ""):
        lines.append(
            f"| `{c['position_label']}` | {c['crop_stage']} | {c['crop_planted_date']} | {c['crop_days_in_place']} |"
        )
    return "\n".join(lines)


def _render_history(history: list[dict]) -> str:
    if not history:
        return "_No historical plantings recorded yet._"
    lines = ["| Position | Planted | Cleared | Days | Stage at end | Events |", "|---|---|---|---|---|---|"]
    for h in history:
        cleared = h.get("cleared_at")
        cleared_str = str(cleared)[:10] if cleared else "—"
        lines.append(
            f"| `{h.get('position_label') or '—'}` | {h['planted_date']} | {cleared_str} "
            f"| {h.get('days_in_place') or '—'} | {h.get('final_stage') or '—'} | {h['event_count']} |"
        )
    return "\n".join(lines)


async def render_crop(conn: asyncpg.Connection, slug: str) -> tuple[str, str] | None:
    entry = await conn.fetchrow(
        "SELECT * FROM v_crop_catalog_with_profiles WHERE slug = $1",
        slug,
    )
    if entry is None:
        return None
    d = dict(entry)
    # JSONB
    sp = d.get("stage_season_profiles")
    profiles = json.loads(sp) if isinstance(sp, str) else (sp or [])

    current = await conn.fetch(
        """
        SELECT p.* FROM v_position_current p
        WHERE p.crop_catalog_slug = $1 AND p.is_occupied
        """,
        slug,
    )
    history_rows = await conn.fetch(
        """
        SELECT h.* FROM v_crop_history h
        WHERE h.crop_catalog_slug = $1
        ORDER BY h.planted_date DESC
        LIMIT 50
        """,
        slug,
    )

    fm = {
        "title": d["common_name"],
        "date": "2026-04-19",
        "type": "crop-profile",
        "crop": slug,
        "category": d["category"],
        "season": d["season"],
    }
    if d.get("scientific_name"):
        fm["scientific_name"] = d["scientific_name"]
    if d.get("cycle_days_min") and d.get("cycle_days_max"):
        fm["cycle_days"] = f"{d['cycle_days_min']}-{d['cycle_days_max']}"

    fm_yaml = _yaml_dumps(fm)

    body = f"""# {d["common_name"]}

> Rendered from DB: `crop_catalog` + `crop_target_profiles` + `v_position_current` + `v_crop_history`.
> Do not edit by hand — run `scripts/render-crop-profiles.py` to regenerate.

## Catalog Entry

| Field | Value |
|---|---|
| Slug | `{d["slug"]}` |
| Common name | {d["common_name"]} |
| Scientific name | {d.get("scientific_name") or "—"} |
| Category | {d["category"]} |
| Season | {d["season"]} |
| Cycle days | {(f"{d['cycle_days_min']}-{d['cycle_days_max']}") if d.get("cycle_days_min") else "—"} |
| Default DLI | {d.get("default_target_dli") or "—"} |
| Default VPD | {(f"{d['default_target_vpd_low']:.2f}-{d['default_target_vpd_high']:.2f} kPa") if d.get("default_target_vpd_low") else "—"} |

## Stage × Season Target Bands (24h averages)

{_render_stage_band_table(profiles)}

## Current Plantings

{_render_current_plantings([dict(r) for r in current])}

## Planting History

{_render_history([dict(r) for r in history_rows])}
"""

    return f"{slug.replace('_', '-')}.md", f"---\n{fm_yaml}\n---\n\n{body}"


async def run(args: argparse.Namespace) -> int:
    conn = await asyncpg.connect(DSN)
    try:
        if args.slug:
            slugs = [args.slug]
        else:
            rows = await conn.fetch("SELECT slug FROM crop_catalog ORDER BY slug")
            slugs = [r["slug"] for r in rows]

        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)

        changes = 0
        for slug in slugs:
            result = await render_crop(conn, slug)
            if result is None:
                print(f"  SKIP {slug}: not in crop_catalog")
                continue
            filename, content = result
            target = out_dir / filename
            existing = target.read_text() if target.exists() else ""
            if existing == content:
                print(f"  UNCHANGED  {filename}")
                continue
            if args.dry_run:
                print(f"  WOULD WRITE  {filename}")
            else:
                target.write_text(content)
                print(f"  WROTE  {filename}")
            changes += 1
        print(f"\n{'Would change' if args.dry_run else 'Changed'} {changes} crop page(s)")
    finally:
        await conn.close()
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--slug", help="Render only this crop slug")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="Output directory")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
