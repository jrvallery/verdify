#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""
planner.py — Greenhouse setpoint planner (provider-agnostic: Anthropic Claude, Google Gemini).

Gathers live context, renders the planner prompt template, calls the configured
AI model, parses the structured JSON response, and writes waypoints + journal to the DB.
Model and provider configured in /srv/verdify/config/ai.yaml.

Usage:
    planner.py                  # run one planning cycle
    planner.py --dry-run        # gather context + render prompt, don't call API
    planner.py --greenhouse-id vallery
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
from ai_config import ai, TEMPLATES_DIR
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
    """Read the compact operational reference (not the full site content)."""
    ref_path = TEMPLATES_DIR / "planner-reference.md"
    if ref_path.exists():
        return ref_path.read_text()
    # Fallback to the old static context if reference doesn't exist
    static_path = ai.template_path("planner", "static_context")
    if static_path.exists():
        text = static_path.read_text()
        max_chars = ai.config["context"].get("max_static_chars", 50000)
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[TRUNCATED at {max_chars} chars]\n"
        return text
    return ""


def check_replan_trigger() -> tuple[bool, str]:
    """Check if a replan trigger is active."""
    trigger_file = Path("/srv/verdify/state/replan-needed.json")
    if trigger_file.exists():
        try:
            age = time.time() - trigger_file.stat().st_mtime
            if age < 900:  # 15 min
                data = json.loads(trigger_file.read_text())
                reasons = [f"{d['param']} deviation (observed {d['observed']} vs forecast {d['forecasted']})"
                          for d in data.get("deviations", [])[:3]]
                return True, "; ".join(reasons) if reasons else "Forecast deviation detected"
        except Exception:
            pass
    return False, ""


def compute_milestones() -> str:
    """Compute solar ephemeris + forecast milestones as a formatted table."""
    import subprocess
    result = subprocess.run(
        ["bash", "-c", """
DB="docker exec verdify-timescaledb psql -U verdify -d verdify -t -A"

echo "date|sunrise|solar_noon|sunset|peak_alt|daylight|peak_solar|peak_temp|driest|peak_vpd|cloud_shift|stress_hrs|high_f|low_rh|tree_shade"

# Join solar ephemeris (1-min resolution) with forecast milestones
$DB -c "
WITH solar AS (
  SELECT ts, ts AT TIME ZONE 'America/Denver' AS mdt,
    (ts AT TIME ZONE 'America/Denver')::date AS day,
    fn_solar_altitude(ts) AS alt
  FROM generate_series(
    (date_trunc('day', now() AT TIME ZONE 'America/Denver') + interval '4 hours') AT TIME ZONE 'America/Denver',
    (date_trunc('day', now() AT TIME ZONE 'America/Denver') + interval '3 days 22 hours') AT TIME ZONE 'America/Denver',
    interval '1 minute') AS ts
),
ephem AS (
  SELECT day,
    to_char(min(CASE WHEN alt > 0 THEN mdt END), 'HH24:MI') AS sunrise,
    to_char((array_agg(mdt ORDER BY alt DESC))[1], 'HH24:MI') AS solar_noon,
    to_char(max(CASE WHEN alt > 0 THEN mdt END), 'HH24:MI') AS sunset,
    round(max(alt)::numeric, 1) AS peak_alt,
    round(count(*) FILTER (WHERE alt > 0) / 60.0, 1) AS daylight_hrs
  FROM solar GROUP BY day
),
fc AS (
  SELECT DISTINCT ON (ts) ts,
    ts AT TIME ZONE 'America/Denver' AS mdt,
    (ts AT TIME ZONE 'America/Denver')::date AS day,
    temp_f, rh_pct, cloud_cover_pct, vpd_kpa,
    GREATEST(COALESCE(direct_radiation_w_m2, 0), 0) AS solar_w
  FROM weather_forecast WHERE ts > now() AND ts < now() + interval '72 hours'
  ORDER BY ts, fetched_at DESC
),
forecast AS (
  SELECT day,
    to_char((array_agg(mdt ORDER BY solar_w DESC))[1], 'HH24:MI') AS peak_solar,
    to_char((array_agg(mdt ORDER BY temp_f DESC) FILTER (WHERE extract(hour FROM mdt) BETWEEN 8 AND 20))[1], 'HH24:MI') AS peak_temp,
    to_char((array_agg(mdt ORDER BY rh_pct ASC) FILTER (WHERE extract(hour FROM mdt) BETWEEN 8 AND 20))[1], 'HH24:MI') AS driest,
    to_char((array_agg(mdt ORDER BY vpd_kpa DESC) FILTER (WHERE extract(hour FROM mdt) BETWEEN 8 AND 20))[1], 'HH24:MI') AS peak_vpd,
    COALESCE((SELECT to_char(mdt, 'HH24:MI') || CASE WHEN cloud_cover_pct > lag_c THEN ' cloud' ELSE ' clear' END
      FROM (SELECT mdt, cloud_cover_pct, lag(cloud_cover_pct) OVER (ORDER BY ts) AS lag_c FROM fc f2 WHERE f2.day = fc.day) cc
      WHERE abs(cloud_cover_pct - COALESCE(lag_c, cloud_cover_pct)) > 30 ORDER BY mdt LIMIT 1), '-') AS cloud_shift,
    count(*) FILTER (WHERE vpd_kpa > 1.5) || 'h' AS stress_hrs,
    round(max(temp_f)::numeric, 0) AS high_f,
    round(min(rh_pct)::numeric, 0) AS low_rh
  FROM fc GROUP BY day
),
shade AS (
  SELECT DISTINCT ON ((ts AT TIME ZONE 'America/Denver')::date)
    (ts AT TIME ZONE 'America/Denver')::date AS day,
    extract(epoch FROM (ts AT TIME ZONE 'America/Denver') - (ts AT TIME ZONE 'America/Denver')::date::timestamp) / 60.0 AS mins
  FROM climate WHERE ts > now() - interval '14 days'
    AND extract(hour FROM ts AT TIME ZONE 'America/Denver') BETWEEN 9 AND 12
    AND lux > 500 AND solar_irradiance_w_m2 > 300
  ORDER BY (ts AT TIME ZONE 'America/Denver')::date, ts
),
shade_model AS (
  SELECT regr_slope(mins, extract(doy FROM day)::double precision) AS slope,
         regr_intercept(mins, extract(doy FROM day)::double precision) AS intercept
  FROM shade
)
SELECT to_char(e.day, 'Dy MM-DD'),
  e.sunrise, e.solar_noon, e.sunset, e.peak_alt, e.daylight_hrs,
  f.peak_solar, f.peak_temp, f.driest, f.peak_vpd, f.cloud_shift,
  f.stress_hrs, f.high_f, f.low_rh,
  to_char('00:00'::time + make_interval(secs => (sm.intercept + sm.slope * extract(doy FROM e.day)::double precision) * 60), 'HH24:MI')
FROM ephem e
LEFT JOIN forecast f ON e.day = f.day
CROSS JOIN shade_model sm
ORDER BY e.day;
" 2>/dev/null
"""],
        capture_output=True, text=True, timeout=30)
    raw = result.stdout.strip() if result.returncode == 0 else ""
    if not raw:
        return "(milestones unavailable)"

    # Parse milestones table and compute suggested transition timestamps
    from datetime import datetime, timedelta, timezone
    now = datetime.now(tz=timezone(timedelta(hours=-6)))  # MDT
    horizon_end = now + timedelta(hours=72)
    now_minutes = now.hour * 60 + now.minute  # minutes since midnight today

    lines = raw.split('\n')
    suggested = ["\nSUGGESTED TRANSITION TIMESTAMPS (use these exact times, not round hours):",
                 "date|pre_dawn|tree_shade|peak_stress|cloud_shift|decline|evening"]

    day_index = 0  # 0=today, 1=tomorrow, etc.
    for line in lines:
        parts = line.split('|')
        if len(parts) >= 15 and parts[0].strip().startswith(('Mon','Tue','Wed','Thu','Fri','Sat','Sun')):
            day = parts[0].strip()
            sunrise = parts[1].strip()   # HH:MM
            sunset = parts[3].strip()    # index 3
            peak_solar = parts[6].strip() # index 6
            peak_vpd = parts[9].strip()   # index 9
            cloud = parts[10].strip()     # index 10
            stress_hrs = parts[11].strip() # index 11 — e.g. "0h" or "5h"
            high_f = parts[12].strip()     # index 12 — e.g. "58" or "92"
            tree = parts[14].strip()      # index 14

            def shift(t, delta_min):
                if not t or t == '-': return '-'
                try:
                    h, m = int(t[:2]), int(t[3:5])
                    total = h * 60 + m + delta_min
                    return f"{(total // 60) % 24:02d}:{total % 60:02d}"
                except: return t

            pre_dawn = shift(sunrise, -60)
            decline = shift(peak_solar, 120)

            # Cloud shift: discard if before pre_dawn or after sunset (not actionable)
            cloud_time = cloud.split()[0] if cloud and cloud != '-' and cloud != 'none' else '-'
            if cloud_time != '-':
                try:
                    ct_min = int(cloud_time[:2]) * 60 + int(cloud_time[3:5])
                    pd_min = int(pre_dawn[:2]) * 60 + int(pre_dawn[3:5]) if pre_dawn != '-' else 300
                    ss_min = int(sunset[:2]) * 60 + int(sunset[3:5]) if sunset else 1200
                    if ct_min < pd_min or ct_min > ss_min:
                        cloud_time = '-'
                except (ValueError, IndexError):
                    pass

            # Peak stress: discard if empty, 00:00, null, or mild day (high < 65°F, 0h stress)
            peak_stress = peak_vpd if peak_vpd and peak_vpd not in ('00:00', '') else '-'
            try:
                if stress_hrs.rstrip('h') == '0' and float(high_f) < 65:
                    peak_stress = '-'
            except (ValueError, TypeError):
                pass

            # Avoid decline == peak_stress timestamp collision (push decline +60 min)
            if decline != '-' and peak_stress != '-' and decline == peak_stress:
                decline = shift(peak_solar, 180)

            # Horizon enforcement: cap milestones that exceed 72h from now
            # On the last day (day_index=3), compute cutoff time
            row_date = now.date() + timedelta(days=day_index)
            def minutes_of(t):
                if not t or t == '-': return -1
                try: return int(t[:2]) * 60 + int(t[3:5])
                except: return -1

            def cap_horizon(t):
                """Replace with '-' if this timestamp is beyond the 72h horizon."""
                m = minutes_of(t)
                if m < 0: return t
                ts = datetime(row_date.year, row_date.month, row_date.day,
                              m // 60, m % 60, tzinfo=timezone(timedelta(hours=-6)))
                return '-' if ts > horizon_end else t

            def cap_past(t):
                """On today only, replace with '-' if this milestone is in the past."""
                if day_index != 0: return t
                m = minutes_of(t)
                if m < 0: return t
                return '-' if m <= now_minutes else t

            pre_dawn = cap_past(cap_horizon(pre_dawn))
            tree = cap_past(cap_horizon(tree))
            peak_stress = cap_past(cap_horizon(peak_stress))
            cloud_time = cap_past(cap_horizon(cloud_time))
            decline = cap_past(cap_horizon(decline))
            sunset_val = cap_past(cap_horizon(sunset))

            suggested.append(f"{day}|{pre_dawn}|{tree}|{peak_stress}|{cloud_time}|{decline}|{sunset_val}")
            day_index += 1

    return raw + '\n' + '\n'.join(suggested)


def build_prompt(greenhouse_id: str) -> str:
    """Render the planner prompt with live context injected."""
    dynamic_context = gather_context(greenhouse_id)
    static_context = read_static_context()
    milestones = compute_milestones()
    current_time = datetime.now(DENVER).isoformat()
    replan_mode, replan_reason = check_replan_trigger()
    if replan_mode:
        log.info("REPLAN MODE: %s", replan_reason)
    return ai.render_template("planner", "prompt",
                             dynamic_context=dynamic_context,
                             static_context=static_context,
                             milestones=milestones,
                             current_time=current_time,
                             replan_mode=replan_mode,
                             replan_reason=replan_reason)


def parse_plan_json(text: str) -> dict:
    """Extract and parse JSON from model response.
    Handles code fences, preamble text, and truncated output."""
    text = text.strip()
    # Strip markdown code fences (may appear anywhere, not just at start)
    text = re.sub(r'```(?:json)?\s*\n', '', text)
    text = re.sub(r'\n```', '', text)
    # Strip any preamble text before the first {
    brace_start = text.find('{')
    if brace_start > 0:
        text = text[brace_start:]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to recover truncated JSON by closing open structures
        # Find the last complete waypoint entry
        last_brace = text.rfind('},')
        if last_brace > 0:
            truncated = text[:last_brace + 1] + '\n  ]\n}'
            log.warning("JSON truncated — recovered by closing at position %d", last_brace)
            return json.loads(truncated)
        raise


# Parameters the AI must NOT set — these are band-driven by the dispatcher
BAND_DRIVEN = {
    "temp_high", "temp_low", "vpd_high", "vpd_low",
    "vpd_target_south", "vpd_target_west", "vpd_target_east", "vpd_target_center",
    "mister_engage_delay_s", "mister_all_delay_s",
    "mister_center_penalty",
}


async def write_plan_to_db(plan: dict, greenhouse_id: str) -> dict:
    """Write the parsed plan to the database. Returns summary stats."""
    conn = await asyncpg.connect(DB_DSN)
    stats = {"waypoints": 0, "journal": False, "validation": False,
             "lesson": False, "filtered": 0}

    try:
        async with conn.transaction():
            # 1. Deactivate all future waypoints from previous plans
            await conn.execute("SELECT fn_deactivate_future_plans()")

            # 2. Flatten transitions (keyed dict) or waypoints (flat list) into rows
            plan_id = plan["plan_id"]
            waypoints = []
            if "transitions" in plan:
                # New format: keyed dict per transition
                for t in plan["transitions"]:
                    ts = t["ts"]
                    reason = t.get("reason", t.get("label", ""))
                    for param, value in t.get("params", {}).items():
                        waypoints.append({"ts": ts, "parameter": param,
                                         "value": value, "reason": reason})
            else:
                # Old format: flat waypoint list
                waypoints = plan.get("waypoints", [])

            # Filter out band-driven params
            filtered = [wp for wp in waypoints if wp["parameter"] in BAND_DRIVEN]
            waypoints = [wp for wp in waypoints if wp["parameter"] not in BAND_DRIVEN]

            # Guard: if Gemini returned no usable waypoints, abort to preserve existing plan
            if not waypoints:
                log.error("No usable waypoints after filtering — aborting to preserve existing plan")
                return {"waypoints": 0, "journal": False, "validation": False,
                        "lesson": False, "filtered": len(filtered), "aborted": True}

            # Ensure immediate coverage: duplicate the first transition at now()
            # so there's no gap between fn_deactivate_future_plans() and the first planned ts
            if waypoints:
                first_ts = min(wp["ts"] for wp in waypoints)
                now_ts = datetime.now(DENVER).isoformat()
                if first_ts > now_ts:
                    now_wps = [{"ts": now_ts, "parameter": wp["parameter"],
                               "value": wp["value"],
                               "reason": "Immediate coverage (copied from first transition)"}
                              for wp in waypoints if wp["ts"] == first_ts]
                    waypoints.extend(now_wps)
                    log.info("Added %d immediate-coverage waypoints at %s",
                            len(now_wps), now_ts[:16])
            if filtered:
                log.warning("Filtered %d band-driven waypoints: %s",
                           len(filtered),
                           {wp["parameter"] for wp in filtered})
            for wp in waypoints:
                await conn.execute("""
                    INSERT INTO setpoint_plan (ts, parameter, value, plan_id, source, reason)
                    VALUES ($1, $2, $3, $4, 'iris', $5)
                """, datetime.fromisoformat(wp["ts"]), wp["parameter"],
                    float(wp["value"]), plan_id, wp.get("reason", ""))
            stats["waypoints"] = len(waypoints)
            stats["filtered"] = len(filtered)

            # 3. Insert plan journal entry
            # Build expected_outcome with performance target if present
            expected = plan.get("expected_outcome", "")
            perf_target = plan.get("performance_target")
            if perf_target:
                target_parts = [expected] if expected else []
                target_parts.append(f"target_score={perf_target.get('target_score', '?')}")
                target_parts.append(f"target_compliance={perf_target.get('target_compliance_pct', '?')}%")
                exp_stress = perf_target.get("expected_stress_hours", {})
                if exp_stress:
                    stress_str = ", ".join(f"{k}={v}" for k, v in exp_stress.items())
                    target_parts.append(f"expected_stress=[{stress_str}]")
                target_parts.append(f"expected_cost=${perf_target.get('expected_cost', '?')}")
                expected = " | ".join(target_parts)
            await conn.execute("""
                INSERT INTO plan_journal
                    (plan_id, conditions_summary, hypothesis, experiment,
                     expected_outcome, params_changed, greenhouse_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, plan_id,
                plan.get("conditions_summary", ""),
                plan.get("hypothesis", ""),
                plan.get("experiment", ""),
                expected,
                [wp["parameter"] for wp in waypoints[:10]],
                greenhouse_id)
            stats["journal"] = True

            # 4. Validate previous plan if provided
            prev = plan.get("previous_plan_validation")
            if prev and prev.get("plan_id") and prev.get("score"):
                # Score is 0-100 from scorecard; clamp to 1-10 for DB column
                raw_score = int(prev["score"])
                db_score = max(1, min(10, round(raw_score / 10)))
                dominant = prev.get("dominant_stress", "")
                outcome_text = prev.get("actual_outcome", "")
                if dominant:
                    outcome_text = f"[dominant: {dominant}] {outcome_text}"
                await conn.execute("""
                    UPDATE plan_journal SET
                        actual_outcome = $1,
                        outcome_score = $2,
                        lesson_extracted = $3,
                        validated_at = now()
                    WHERE plan_id = $4
                """, outcome_text,
                    db_score,
                    prev.get("lesson"),
                    prev["plan_id"])
                stats["validation"] = True

                # 5. Insert or merge lesson if extracted (dedup by exact text)
                lesson_text = prev.get("lesson")
                if lesson_text:
                    existing = await conn.fetchval(
                        "SELECT id FROM planner_lessons WHERE lesson = $1 AND is_active = true LIMIT 1",
                        lesson_text)
                    if existing:
                        await conn.execute("""
                            UPDATE planner_lessons SET
                                times_validated = times_validated + 1,
                                last_validated = now(),
                                source_plan_ids = array_append(source_plan_ids, $1)
                            WHERE id = $2
                        """, plan_id, existing)
                    else:
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
        print(prompt)
        return

    # Call AI model
    provider = ai.config["models"]["planner"]["provider"]
    model_name = ai.model_name("planner")
    log.info("Calling %s (provider: %s)...", model_name, provider)
    start = time.time()

    client = ai.get_client("planner")

    if provider == "anthropic":
        response = client.messages.create(
            model=model_name,
            max_tokens=ai.max_tokens("planner"),
            temperature=ai.temperature("planner"),
            messages=[{"role": "user", "content": prompt}],
        )
        elapsed = time.time() - start
        output = response.content[0].text
        log.info("Response: %d chars in %.1fs", len(output), elapsed)
        log.info("Tokens: input=%s output=%s",
                 response.usage.input_tokens, response.usage.output_tokens)
    else:
        from google import genai
        response = client.models.generate_content(
            model=model_name,
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
        log.error("Failed to parse response as JSON: %s", e)
        log.error("Raw output (first 500 chars): %s", output[:500])
        sys.exit(1)

    transitions = plan.get("transitions", plan.get("waypoints", []))
    log.info("Plan %s: %d transitions, hypothesis: %s",
             plan.get("plan_id", "?"),
             len(transitions),
             plan.get("hypothesis", "?")[:100])

    # Write to DB
    stats = asyncio.run(write_plan_to_db(plan, args.greenhouse_id))
    log.info("DB writes: %d waypoints (%d band-driven filtered), journal=%s, validation=%s, lesson=%s",
             stats["waypoints"], stats["filtered"], stats["journal"], stats["validation"], stats["lesson"])

    log.info("Planner complete (%.1fs context + %.1fs inference + DB write)",
             context_time, elapsed)


if __name__ == "__main__":
    main()
