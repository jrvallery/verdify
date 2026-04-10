#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""
compute-grow-light-daily.py — Compute grow light runtime from equipment_state events.

Runs nightly at 00:10 UTC via cron to populate daily_summary.runtime_grow_light_min
and daily_summary.cycles_grow_light for yesterday.

Also does a one-time backfill for all historical days when run with --backfill.

Usage:
    compute-grow-light-daily.py            # compute yesterday only
    compute-grow-light-daily.py --backfill # backfill all historical days
"""

import asyncio
import logging
import os
import sys

import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [grow-light] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def get_db_url() -> str:
    pw = "verdify"
    env_file = "/srv/verdify/.env"
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.strip().startswith("POSTGRES_PASSWORD="):
                    pw = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return f"postgresql://verdify:{pw}@localhost:5432/verdify"


RUNTIME_SQL = """
WITH light_events AS (
    SELECT ts, equipment, state,
        LEAD(ts) OVER (PARTITION BY equipment ORDER BY ts) AS next_ts,
        LEAD(state) OVER (PARTITION BY equipment ORDER BY ts) AS next_state
    FROM equipment_state
    WHERE equipment IN ('grow_light_main', 'grow_light_grow')
      AND date_trunc('day', ts)::date = $1
)
SELECT
    COALESCE(SUM(
        CASE WHEN state = true AND next_state = false AND next_ts IS NOT NULL
        THEN EXTRACT(EPOCH FROM (next_ts - ts)) / 60.0
        ELSE 0 END
    ), 0) AS runtime_min,
    COALESCE(SUM(
        CASE WHEN state = true THEN 1 ELSE 0 END
    ), 0) AS cycles
FROM light_events;
"""


async def compute_day(conn, day) -> tuple[float, int]:
    """Compute grow light runtime and cycles for a single day."""
    row = await conn.fetchrow(RUNTIME_SQL, day)
    return float(row["runtime_min"]), int(row["cycles"])


async def main():
    backfill = "--backfill" in sys.argv
    db_url = get_db_url()
    conn = await asyncpg.connect(db_url)

    try:
        if backfill:
            # Get all days that have grow light events
            days = await conn.fetch("""
                SELECT DISTINCT date_trunc('day', ts)::date AS day
                FROM equipment_state
                WHERE equipment IN ('grow_light_main', 'grow_light_grow')
                ORDER BY 1
            """)
            log.info("Backfilling %d days with grow light events", len(days))
            updated = 0
            for row in days:
                day = row["day"]
                runtime, cycles = await compute_day(conn, day)
                if runtime > 0 or cycles > 0:
                    await conn.execute("""
                        UPDATE daily_summary
                        SET runtime_grow_light_min = $2, cycles_grow_light = $3
                        WHERE date = $1
                    """, day, runtime, cycles)
                    updated += 1
            log.info("Backfill complete: %d days updated", updated)
        else:
            # Yesterday only
            yesterday = await conn.fetchval("SELECT CURRENT_DATE - 1")
            runtime, cycles = await compute_day(conn, yesterday)
            await conn.execute("""
                UPDATE daily_summary
                SET runtime_grow_light_min = $2, cycles_grow_light = $3
                WHERE date = $1
            """, yesterday, runtime, cycles)
            log.info("Yesterday (%s): %.1f min runtime, %d cycles", yesterday, runtime, cycles)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
