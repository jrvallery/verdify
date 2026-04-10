#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""
forecast-action-engine.py — Evaluate forecast data against rules, trigger preemptive adjustments.

Runs every 15 minutes. Reads weather_forecast for next 24-48h, evaluates rules from
forecast_action_rules table, writes preemptive setpoint adjustments or alerts.

Usage:
    forecast-action-engine.py           # evaluate and act
    forecast-action-engine.py --dry-run # evaluate but don't write
    forecast-action-engine.py --test    # simulate a trigger for testing
"""

import asyncio
import json
import logging
import os
import sys
import urllib.request
from datetime import UTC, datetime

import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [forecast-engine] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

DRY_RUN = "--dry-run" in sys.argv
SLACK_TOKEN_FILE = "/mnt/jason/agents/shared/credentials/slack_bot_token.txt"
SLACK_CHANNEL = "C0ANVVAPLD6"

INTERVAL_MAP = {"24h": "24 hours", "48h": "48 hours", "12h": "12 hours", "6h": "6 hours"}


def get_db_url():
    pw = "verdify"
    if os.path.exists("/srv/verdify/.env"):
        with open("/srv/verdify/.env") as f:
            for line in f:
                if line.strip().startswith("POSTGRES_PASSWORD="):
                    pw = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    return f"postgresql://verdify:{pw}@localhost:5432/verdify"


def post_slack(text):
    try:
        token = open(SLACK_TOKEN_FILE).read().strip()
        data = json.dumps({"channel": SLACK_CHANNEL, "text": text}).encode()
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=data,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log.warning("Slack post failed: %s", e)


async def main():
    conn = await asyncpg.connect(get_db_url())
    now = datetime.now(UTC)

    try:
        # Get enabled rules ordered by priority
        rules = await conn.fetch("SELECT * FROM forecast_action_rules WHERE enabled = true ORDER BY priority")

        if not rules:
            log.info("No enabled rules")
            return

        log.info("Evaluating %d forecast rules", len(rules))
        actions_taken = 0

        for rule in rules:
            rule_id = rule["id"]
            name = rule["name"]
            metric = rule["metric"]
            op = rule["operator"]
            threshold = float(rule["threshold"])
            window = INTERVAL_MAP.get(rule["time_window"], "24 hours")
            param = rule["param"]
            adj_value = rule["adjustment_value"]
            action_type = rule["action_type"]
            cooldown_h = rule["cooldown_hours"]

            # Check cooldown — skip if triggered recently
            last_trigger = await conn.fetchval(
                "SELECT MAX(triggered_at) FROM forecast_action_log WHERE rule_id = $1 AND action_taken != 'evaluated_ok'",
                rule_id,
            )
            if last_trigger and (now - last_trigger).total_seconds() < cooldown_h * 3600:
                continue  # Still in cooldown

            # Query forecast for the triggering condition
            op_sql = {"<": "<", ">": ">", "<=": "<=", ">=": ">="}[op]

            # Get the most recent forecast per hour (dedup accumulation mode)
            trigger_row = await conn.fetchrow(
                f"""
                SELECT ts, {metric} AS val
                FROM (
                    SELECT DISTINCT ON (ts) ts, {metric}
                    FROM weather_forecast
                    WHERE ts > now() AND ts < now() + interval '{window}'
                    ORDER BY ts, fetched_at DESC
                ) sub
                WHERE {metric} {op_sql} $1
                ORDER BY ts LIMIT 1
            """,
                threshold,
            )

            if trigger_row is None:
                # Condition not met — log as evaluated_ok
                await conn.execute(
                    "INSERT INTO forecast_action_log (rule_id, rule_name, action_taken, forecast_condition) VALUES ($1, $2, 'evaluated_ok', $3)",
                    rule_id,
                    name,
                    json.dumps({"metric": metric, "threshold": threshold, "window": window}),
                )
                continue

            trigger_val = float(trigger_row["val"])
            trigger_ts = trigger_row["ts"]
            forecast_snapshot = {
                "metric": metric,
                "operator": op,
                "threshold": threshold,
                "trigger_value": str(trigger_val),
                "trigger_hour": trigger_ts.strftime("%Y-%m-%d %H:%M"),
                "window": window,
            }

            log.info(
                "RULE TRIGGERED: %s — %s %s %s (actual: %s at %s)", name, metric, op, threshold, trigger_val, trigger_ts
            )

            if action_type == "setpoint" and param and adj_value is not None:
                # Get current value
                old_val = await conn.fetchval(
                    "SELECT value FROM setpoint_changes WHERE parameter = $1 ORDER BY ts DESC LIMIT 1", param
                )

                plan_id = f"preemptive-{now.strftime('%Y%m%d-%H%M')}"

                if not DRY_RUN:
                    await conn.execute(
                        "INSERT INTO setpoint_plan (ts, parameter, value, plan_id, source, reason) "
                        "VALUES (now(), $1, $2, $3, 'preemptive', $4)",
                        param,
                        float(adj_value),
                        plan_id,
                        f"Forecast: {name} — {metric} {op} {threshold} (actual {trigger_val} at {trigger_ts.strftime('%H:%M')})",
                    )

                    # Also write to setpoint_changes for immediate dispatch
                    await conn.execute(
                        "INSERT INTO setpoint_changes (ts, parameter, value, source) VALUES (now(), $1, $2, 'preemptive')",
                        param,
                        float(adj_value),
                    )

                await conn.execute(
                    "INSERT INTO forecast_action_log (rule_id, rule_name, triggered_at, forecast_condition, action_taken, plan_id, param, old_value, new_value) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                    rule_id,
                    name,
                    now,
                    json.dumps(forecast_snapshot),
                    "setpoint_written" if not DRY_RUN else "dry_run",
                    plan_id,
                    param,
                    float(old_val) if old_val else None,
                    float(adj_value),
                )

                log.info(
                    "  → %s %s: %s → %s (plan: %s)%s",
                    action_type,
                    param,
                    old_val,
                    adj_value,
                    plan_id,
                    " [DRY RUN]" if DRY_RUN else "",
                )
                actions_taken += 1

            elif action_type == "alert":
                msg = f"\u26a0\ufe0f *Forecast Alert:* {name} — {metric} {op} {threshold} (forecast: {trigger_val} at {trigger_ts.strftime('%H:%M UTC')})"
                if not DRY_RUN:
                    post_slack(msg)

                await conn.execute(
                    "INSERT INTO forecast_action_log (rule_id, rule_name, triggered_at, forecast_condition, action_taken) "
                    "VALUES ($1, $2, $3, $4, $5)",
                    rule_id,
                    name,
                    now,
                    json.dumps(forecast_snapshot),
                    "alert_posted" if not DRY_RUN else "dry_run",
                )
                actions_taken += 1

            elif action_type == "log":
                await conn.execute(
                    "INSERT INTO forecast_action_log (rule_id, rule_name, triggered_at, forecast_condition, action_taken) "
                    "VALUES ($1, $2, $3, $4, 'logged')",
                    rule_id,
                    name,
                    now,
                    json.dumps(forecast_snapshot),
                )
                log.info("  → logged (no action)")
                actions_taken += 1

        log.info("Done: %d rules evaluated, %d actions taken", len(rules), actions_taken)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
