#!/usr/bin/env python3
"""
generate-daily-plan.py — Generate or update daily plan documents for verdify.ai

Usage:
  # Backfill all historical days from plan_journal + daily_summary
  python3 generate-daily-plan.py --backfill

  # Generate/update today's plan document for a specific cycle
  python3 generate-daily-plan.py --date 2026-03-30 --cycle morning --plan-id iris-20260330-0600

  # Generate from live DB data (called by planner cron)
  python3 generate-daily-plan.py --today --cycle morning --plan-id iris-20260330-0600

Output: /srv/verdify/verdify-site/content/plans/YYYY-MM-DD.md
"""

import argparse
import json
import subprocess
from datetime import date, datetime
from pathlib import Path

CONTENT_DIR = Path("/srv/verdify/verdify-site/content/plans")
DB_CMD = "docker exec verdify-timescaledb psql -U verdify -d verdify -t -A"


def _yaml_escape(val: str) -> str:
    """Escape a string for safe inclusion in double-quoted YAML values."""
    if not val:
        return ""
    return val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def db_query(sql: str) -> str:
    """Run a psql query and return stripped output."""
    result = subprocess.run(f'{DB_CMD} -c "{sql}"', shell=True, capture_output=True, text=True, timeout=15)
    return result.stdout.strip()


def db_query_rows(sql: str) -> list[list[str]]:
    """Run a psql query and return list of rows (pipe-delimited)."""
    raw = db_query(sql)
    if not raw:
        return []
    return [row.split("|") for row in raw.split("\n") if row.strip()]


def db_query_json(sql: str) -> dict | list | None:
    """Run a psql query expecting JSON output."""
    raw = db_query(sql)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def get_daily_summary(d: date) -> dict:
    """Get daily_summary row as dict."""
    return (
        db_query_json(f"""
        SELECT row_to_json(ds) FROM (
            SELECT date, temp_min, temp_max, temp_avg, vpd_min, vpd_max, vpd_avg,
                   rh_min, rh_max, co2_avg, dli_final,
                   cost_electric, cost_gas, cost_water, cost_total,
                   water_used_gal, mister_water_gal,
                   stress_hours_heat, stress_hours_cold, stress_hours_vpd_high, stress_hours_vpd_low,
                   runtime_fan1_min, runtime_fan2_min, runtime_fog_min,
                   runtime_heat1_min, runtime_heat2_min, runtime_vent_min,
                   runtime_grow_light_min,
                   runtime_mister_south_h, runtime_mister_west_h, runtime_mister_center_h,
                   runtime_drip_wall_h
            FROM daily_summary WHERE date = '{d}'
        ) ds
    """)
        or {}
    )


def get_plans_for_date(d: date) -> list[dict]:
    """Get all plan_journal entries whose plan_id references this date."""
    date_str = d.strftime("%Y%m%d")
    rows = db_query_rows(f"""
        SELECT plan_id,
               to_char(created_at AT TIME ZONE 'America/Denver', 'YYYY-MM-DD HH24:MI') as created,
               conditions_summary, hypothesis, experiment, expected_outcome,
               actual_outcome, outcome_score, lesson_extracted,
               array_to_string(params_changed, ','),
               CASE WHEN validated_at IS NULL THEN 'pending' ELSE 'validated' END
        FROM plan_journal
        WHERE plan_id LIKE 'iris-{date_str}%'
          AND plan_id NOT LIKE 'iris-reactive%'
        ORDER BY created_at
    """)
    plans = []
    for row in rows:
        if len(row) >= 11:
            plans.append(
                {
                    "plan_id": row[0].strip(),
                    "created": row[1].strip(),
                    "conditions_summary": row[2].strip(),
                    "hypothesis": row[3].strip(),
                    "experiment": row[4].strip(),
                    "expected_outcome": row[5].strip(),
                    "actual_outcome": row[6].strip(),
                    "outcome_score": row[7].strip(),
                    "lesson_extracted": row[8].strip(),
                    "params_changed": row[9].strip(),
                    "status": row[10].strip(),
                }
            )
    return plans


def get_waypoints_for_plan(plan_id: str) -> list[dict]:
    """Get setpoint_plan waypoints for a given plan_id."""
    rows = db_query_rows(f"""
        SELECT to_char(ts AT TIME ZONE 'America/Denver', 'YYYY-MM-DD HH24:MI') as apply_mdt,
               parameter, value, reason
        FROM setpoint_plan
        WHERE plan_id = '{plan_id}'
        ORDER BY ts, parameter
    """)
    waypoints = []
    for row in rows:
        if len(row) >= 4:
            waypoints.append(
                {
                    "time": row[0].strip(),
                    "parameter": row[1].strip(),
                    "value": row[2].strip(),
                    "reason": row[3].strip(),
                }
            )
    return waypoints


def get_zone_snapshot(d: date, hour: int = 6) -> dict:
    """Get zone conditions at a specific hour of the given date."""
    ts = f"{d} {hour:02d}:00:00-06"
    return (
        db_query_json(f"""
        SELECT json_build_object(
            'temp_south', round(temp_south::numeric,1),
            'temp_east', round(temp_east::numeric,1),
            'temp_west', round(temp_west::numeric,1),
            'temp_north', round(temp_north::numeric,1),
            'vpd_south', round(vpd_south::numeric,2),
            'vpd_east', round(vpd_east::numeric,2),
            'vpd_west', round(vpd_west::numeric,2),
            'vpd_north', round(vpd_north::numeric,2),
            'rh_south', round(rh_south::numeric,1),
            'rh_east', round(rh_east::numeric,1),
            'rh_west', round(rh_west::numeric,1),
            'rh_north', round(rh_north::numeric,1),
            'outdoor_temp_f', round(outdoor_temp_f::numeric,1),
            'outdoor_rh_pct', round(outdoor_rh_pct::numeric,1),
            'co2_ppm', round(co2_ppm::numeric,0),
            'lux', round(lux::numeric,0),
            'soil_moisture_south_1', round(COALESCE(soil_moisture_south_1,0)::numeric,1),
            'soil_moisture_south_2', round(COALESCE(soil_moisture_south_2,0)::numeric,1),
            'soil_moisture_west', round(COALESCE(soil_moisture_west,0)::numeric,1)
        )
        FROM climate
        WHERE ts >= '{ts}'::timestamptz - interval '30 minutes'
          AND ts <= '{ts}'::timestamptz + interval '30 minutes'
        ORDER BY ts
        LIMIT 1
    """)
        or {}
    )


def get_active_setpoints_at(d: date) -> dict:
    """Get the active setpoint values as of a given date."""
    ts = f"{d} 12:00:00-06"
    rows = db_query_rows(f"""
        SELECT DISTINCT ON (parameter) parameter, value
        FROM setpoint_changes
        WHERE ts <= '{ts}'::timestamptz
        ORDER BY parameter, ts DESC
    """)
    return {row[0].strip(): row[1].strip() for row in rows if len(row) >= 2}


def get_hourly_pattern(d: date) -> list[dict]:
    """Get hourly temp/vpd/rh pattern for the day."""
    rows = db_query_rows(f"""
        SELECT to_char(date_trunc('hour', ts) AT TIME ZONE 'America/Denver', 'HH24:00') as hour,
               round(avg(temp_avg)::numeric,1) as temp,
               round(avg(vpd_avg)::numeric,2) as vpd,
               round(avg(rh_avg)::numeric,1) as rh
        FROM climate
        WHERE ts >= '{d}'::date AT TIME ZONE 'America/Denver'
          AND ts < ('{d}'::date + 1) AT TIME ZONE 'America/Denver'
        GROUP BY date_trunc('hour', ts)
        ORDER BY date_trunc('hour', ts)
    """)
    return [
        {"hour": r[0].strip(), "temp": r[1].strip(), "vpd": r[2].strip(), "rh": r[3].strip()}
        for r in rows
        if len(r) >= 4
    ]


def get_stress_context(d: date) -> list[dict]:
    """Get 7-day stress context ending on this date."""
    rows = db_query_rows(f"""
        SELECT date, round(stress_hours_heat::numeric,1), round(stress_hours_vpd_high::numeric,1),
               round(stress_hours_cold::numeric,1), round(stress_hours_vpd_low::numeric,1)
        FROM daily_summary
        WHERE date >= '{d}'::date - 6 AND date <= '{d}'
        ORDER BY date
    """)
    return [
        {
            "date": r[0].strip(),
            "heat": r[1].strip(),
            "vpd_high": r[2].strip(),
            "cold": r[3].strip(),
            "vpd_low": r[4].strip(),
        }
        for r in rows
        if len(r) >= 5
    ]


def classify_cycle(plan_id: str) -> str:
    """Classify a plan_id into morning/midday/evening/overnight."""
    # Extract time portion: iris-20260325-0605 → 0605
    parts = plan_id.split("-")
    if len(parts) >= 3:
        time_part = parts[-1]
        if len(time_part) == 4:
            hour = int(time_part[:2])
            if hour < 10:
                return "morning"
            elif hour < 15:
                return "midday"
            elif hour < 21:
                return "evening"
            else:
                return "overnight"
    return "unknown"


def r(v, digits=1):
    """Round a numeric value for display."""
    if v is None:
        return "—"
    try:
        return f"{float(v):.{digits}f}"
    except (ValueError, TypeError):
        return str(v) if v else "—"


CORE_PARAMS = [
    "temp_high",
    "temp_low",
    "vpd_high",
    "vpd_hysteresis",
    "d_cool_stage_2",
    "mister_engage_kpa",
    "mister_all_kpa",
    "mister_pulse_on_s",
    "mister_pulse_gap_s",
    "mister_vpd_weight",
]
PARAM_SHORT = {
    "temp_high": "high",
    "temp_low": "low",
    "vpd_high": "vpd_h",
    "vpd_hysteresis": "hyst",
    "d_cool_stage_2": "d_cool",
    "mister_engage_kpa": "engage",
    "mister_all_kpa": "all",
    "mister_pulse_on_s": "pulse",
    "mister_pulse_gap_s": "gap",
    "mister_vpd_weight": "wt",
}


def format_waypoints_table(waypoints: list[dict]) -> str:
    """Format waypoints as a pivoted table: rows = transition times, columns = 10 core params."""
    if not waypoints:
        return "*No waypoints recorded.*\n"

    # Group by timestamp
    from collections import defaultdict

    by_time = defaultdict(dict)
    notes_by_time = {}
    for wp in waypoints:
        t = wp["time"]
        param = wp["parameter"]
        by_time[t][param] = wp["value"]
        if wp.get("reason") and param in CORE_PARAMS:
            notes_by_time.setdefault(t, wp["reason"][:60])

    # Group by day
    times = sorted(by_time.keys())

    lines = []
    current_day = None
    for t in times:
        day = t[:10]
        if day != current_day:
            current_day = day
            try:
                d = datetime.strptime(day, "%Y-%m-%d")
                day_label = d.strftime("%A %B %d")
            except ValueError:
                day_label = day
            lines.append(f"\n#### {day_label}\n")
            lines.append("| Time | high | low | vpd_h | hyst | d_cool | engage | all | pulse | gap | wt | Notes |")
            lines.append("|------|------|-----|-------|------|--------|--------|-----|-------|-----|----|-------|")

        vals = by_time[t]
        time_str = t[11:16] if len(t) > 11 else t
        cols = [time_str]
        for p in CORE_PARAMS:
            v = vals.get(p, "")
            cols.append(str(v) if v else "·")
        note = notes_by_time.get(t, "")
        note = note.replace("|", "—")[:40]
        cols.append(note)
        lines.append("| " + " | ".join(cols) + " |")

    # Also include non-core params as a separate small table
    non_core = [wp for wp in waypoints if wp["parameter"] not in CORE_PARAMS]
    if non_core:
        lines.extend(["", "**Other parameters:**", "", "| Time | Parameter | Value |", "|------|-----------|-------|"])
        for wp in non_core:
            lines.append(f"| {wp['time'][11:16]} | `{wp['parameter']}` | {wp['value']} |")

    return "\n".join(lines) + "\n"


def generate_frontmatter(d: date, plans: list[dict], summary: dict, setpoints: dict) -> str:
    """Generate YAML frontmatter for the daily plan."""
    title = d.strftime("%B %d, %Y")

    latest_plan = plans[-1] if plans else {}
    latest_cycle = classify_cycle(latest_plan.get("plan_id", "")) if latest_plan else "none"

    # Core setpoint values (from active setpoints at that date)
    sp = {}
    core_params = [
        "temp_high",
        "temp_low",
        "vpd_high",
        "vpd_hysteresis",
        "d_cool_stage_2",
        "mister_engage_kpa",
        "mister_all_kpa",
        "mister_pulse_on_s",
        "mister_pulse_gap_s",
        "mister_vpd_weight",
    ]
    for p in core_params:
        sp[p] = setpoints.get(p, "")

    lines = [
        "---",
        f'title: "{title}"',
        f"date: {d}",
        "tags: [daily-plan]",
        "type: plan",
        "",
        f"latest_cycle: {latest_cycle}",
        f"latest_plan_id: {latest_plan.get('plan_id', 'none')}",
        f"plan_count: {len(plans)}",
        "",
        "# Climate summary",
        "climate:",
        f"  temp_min_f: {r(summary.get('temp_min'))}",
        f"  temp_max_f: {r(summary.get('temp_max'))}",
        f"  temp_avg_f: {r(summary.get('temp_avg'))}",
        f"  vpd_min_kpa: {r(summary.get('vpd_min'), 2)}",
        f"  vpd_max_kpa: {r(summary.get('vpd_max'), 2)}",
        f"  vpd_avg_kpa: {r(summary.get('vpd_avg'), 2)}",
        f"  rh_min_pct: {r(summary.get('rh_min'))}",
        f"  rh_max_pct: {r(summary.get('rh_max'))}",
        f"  dli_sensor_mol: {r(summary.get('dli_final'))}",
        "",
        "# Stress hours",
        "stress:",
        f"  heat_hours: {r(summary.get('stress_hours_heat'))}",
        f"  vpd_high_hours: {r(summary.get('stress_hours_vpd_high'))}",
        f"  cold_hours: {r(summary.get('stress_hours_cold'))}",
        f"  vpd_low_hours: {r(summary.get('stress_hours_vpd_low'))}",
        "",
        "# Economics",
        "cost:",
        f"  electric: {r(summary.get('cost_electric'), 2)}",
        f"  gas: {r(summary.get('cost_gas'), 2)}",
        f"  water: {r(summary.get('cost_water'), 3)}",
        f"  total: {r(summary.get('cost_total'), 2)}",
        "",
        "# Water",
        "water:",
        f"  total_gal: {r(summary.get('water_used_gal'), 0)}",
        f"  mister_gal: {r(summary.get('mister_water_gal'), 0)}",
        "",
        "# Equipment runtimes (minutes unless noted)",
        "equipment:",
        f"  fan1_min: {r(summary.get('runtime_fan1_min'), 0)}",
        f"  fan2_min: {r(summary.get('runtime_fan2_min'), 0)}",
        f"  fog_min: {r(summary.get('runtime_fog_min'), 0)}",
        f"  heat1_min: {r(summary.get('runtime_heat1_min'), 0)}",
        f"  heat2_min: {r(summary.get('runtime_heat2_min'), 0)}",
        f"  vent_min: {r(summary.get('runtime_vent_min'), 0)}",
        f"  grow_light_min: {r(summary.get('runtime_grow_light_min'), 0)}",
        f"  mister_south_h: {r(summary.get('runtime_mister_south_h'), 2)}",
        f"  mister_west_h: {r(summary.get('runtime_mister_west_h'), 2)}",
        f"  mister_center_h: {r(summary.get('runtime_mister_center_h'), 2)}",
        "",
        "# Active setpoints (end of day / latest cycle)",
        "setpoints:",
    ]
    for p in core_params:
        lines.append(f"  {p}: {sp.get(p, '')}")

    # Experiment from latest plan
    if latest_plan:
        lines.extend(
            [
                "",
                "# Experiment",
                "experiment:",
                f'  hypothesis: "{_yaml_escape(latest_plan.get("hypothesis", ""))}"',
                f'  test: "{_yaml_escape(latest_plan.get("experiment", ""))}"',
                f'  expected_outcome: "{_yaml_escape(latest_plan.get("expected_outcome", ""))}"',
                f'  outcome_score: "{_yaml_escape(latest_plan.get("outcome_score", ""))}"',
                f'  status: "{_yaml_escape(latest_plan.get("status", "pending"))}"',
            ]
        )

    lines.append("---")
    return "\n".join(lines)


def get_previous_plan(plan_created: str) -> dict | None:
    """Get the plan that was active BEFORE a given plan's creation time.

    This is used by the Reflection section to show what hypothesis was being tested
    before the current plan validated it.
    """
    rows = db_query_rows(f"""
        SELECT plan_id,
               to_char(created_at AT TIME ZONE 'America/Denver', 'YYYY-MM-DD HH24:MI') as created,
               conditions_summary, hypothesis, experiment, expected_outcome,
               actual_outcome, outcome_score, lesson_extracted
        FROM plan_journal
        WHERE created_at < '{plan_created}'::timestamptz
          AND plan_id NOT LIKE 'iris-reactive%'
        ORDER BY created_at DESC LIMIT 1
    """)
    if rows and len(rows[0]) >= 9:
        row = rows[0]
        return {
            "plan_id": row[0].strip(),
            "created": row[1].strip(),
            "hypothesis": row[3].strip(),
            "experiment": row[4].strip(),
            "expected_outcome": row[5].strip(),
            "actual_outcome": row[6].strip(),
            "outcome_score": row[7].strip(),
            "lesson_extracted": row[8].strip(),
        }
    return None


def get_cycle_label(plan: dict) -> tuple[str, str]:
    """Return (emoji_label, formatted_time) for a plan's cycle.

    Uses plan_id time to determine cycle type. If the plan came from a
    deviation trigger, labels it as a Deviation Replan.
    """
    plan_id = plan.get("plan_id", "")
    created = plan.get("created", "")

    # Format time for display: "06:06 AM"
    time_display = ""
    if created and len(created) >= 16:
        try:
            dt = datetime.strptime(created, "%Y-%m-%d %H:%M")
            time_display = dt.strftime("%I:%M %p").lstrip("0")
        except ValueError:
            time_display = created[11:16]

    # Check for deviation trigger
    if "deviation" in plan_id.lower() or "reactive" in plan_id.lower():
        return f"⚠️ Deviation Replan ({time_display})", time_display

    cycle_type = classify_cycle(plan_id)
    labels = {
        "morning": "🌅 Morning Cycle",
        "midday": "☀️ Midday Cycle",
        "evening": "🌆 Evening Cycle",
        "overnight": "🌙 Overnight Cycle",
        "unknown": "📋 Planning Cycle",
    }
    label = labels.get(cycle_type, "📋 Planning Cycle")
    return f"{label} ({time_display})", time_display


def generate_cycle_section(plan: dict, prev_plan: dict | None, waypoints: list[dict]) -> str:
    """Generate a single cycle section with Reflection + Hypothesis + Setpoints.

    Each planning cycle is a first-class entry in chronological order.
    The Reflection validates the PREVIOUS cycle's hypothesis.
    The Hypothesis is THIS cycle's forward look.
    """
    label, _ = get_cycle_label(plan)
    plan_id = plan.get("plan_id", "")
    lines = [f"## {label} — `{plan_id}`", ""]

    # --- Reflection: validates the previous cycle ---
    lines.append("### Reflection")
    lines.append("")

    if plan.get("status") == "pending":
        # This is the latest (current) cycle — hasn't been validated yet
        lines.append("⏳ *Pending — will be validated at next planning cycle.*")
        lines.append("")
    elif prev_plan:
        # Show what previous cycle hypothesized and how it turned out
        prev_id = prev_plan.get("plan_id", "unknown")
        prev_label, _ = get_cycle_label(prev_plan)
        lines.append(f"_Validating previous cycle: `{prev_id}`_")
        lines.append("")

        prev_hypothesis = prev_plan.get("hypothesis", "")
        if prev_hypothesis:
            lines.append(f"**Previous hypothesis:** {prev_hypothesis}")
        else:
            lines.append("**Previous hypothesis:** *(not recorded)*")

        # The actual_outcome and score come from THIS plan's validation of the previous one
        actual = plan.get("actual_outcome", "")
        score = plan.get("outcome_score", "")
        if actual:
            lines.append(f"**Result:** {actual}")
        if score:
            lines.append(f"**Score:** {score}/10")
        lines.append("")

        lesson = plan.get("lesson_extracted", "")
        if lesson:
            lines.append(f"> **New finding:** {lesson} → Added to [Lessons Learned](/greenhouse/lessons)")
            lines.append("")
    else:
        # First ever cycle or no previous plan found
        lines.append("_First planning cycle — no previous hypothesis to validate._")
        lines.append("")

    # --- Hypothesis: THIS cycle's forward look ---
    lines.append("### Hypothesis")
    lines.append("")

    conditions = plan.get("conditions_summary", "")
    if conditions:
        lines.append(f"**Conditions:** {conditions}")

    experiment = plan.get("experiment", "")
    if experiment:
        lines.append(f"**Testing:** {experiment}")

    expected = plan.get("expected_outcome", "")
    if expected:
        lines.append(f"**Expected outcome:** {expected}")
    lines.append("")

    # --- Setpoints: waypoints for THIS plan_id only ---
    if waypoints:
        lines.append("#### Setpoints")
        lines.append("")
        lines.append(format_waypoints_table(waypoints))

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def generate_daily_summary_section(summary: dict, hourly: list[dict], summary_date: date = None) -> str:
    """Generate end-of-day summary section."""
    if not summary:
        return ""

    lines = ["## End-of-Day Summary", ""]

    # Climate table
    lines.extend(
        [
            "### Climate",
            "",
            "| Metric | Min | Avg | Max |",
            "|--------|-----|-----|-----|",
            f"| Temperature (°F) | {r(summary.get('temp_min'))} | {r(summary.get('temp_avg'))} | {r(summary.get('temp_max'))} |",
            f"| VPD (kPa) | {r(summary.get('vpd_min'), 2)} | {r(summary.get('vpd_avg'), 2)} | {r(summary.get('vpd_max'), 2)} |",
            f"| Relative Humidity (%) | {r(summary.get('rh_min'))} | — | {r(summary.get('rh_max'))} |",
            "",
        ]
    )

    # Stress
    lines.extend(
        [
            "### Stress Hours",
            "",
            f"- **Heat stress (>85°F):** {r(summary.get('stress_hours_heat'))}h",
            f"- **VPD stress (>2.0 kPa):** {r(summary.get('stress_hours_vpd_high'))}h",
            f"- **Cold stress (<55°F):** {r(summary.get('stress_hours_cold'))}h",
            "",
        ]
    )

    # Economics
    lines.extend(
        [
            "### Economics",
            "",
            "| Electric | Gas | Water | **Total** |",
            "|----------|-----|-------|-----------|",
            f"| ${r(summary.get('cost_electric'), 2)} | ${r(summary.get('cost_gas'), 2)} | ${r(summary.get('cost_water'), 3)} | **${r(summary.get('cost_total'), 2)}** |",
            "",
        ]
    )

    # Equipment runtimes
    lines.extend(
        [
            "### Equipment Runtimes",
            "",
            "| Equipment | Runtime |",
            "|-----------|---------|",
            f"| Fan 1 | {r(summary.get('runtime_fan1_min'), 0)} min |",
            f"| Fan 2 | {r(summary.get('runtime_fan2_min'), 0)} min |",
            f"| Vent | {r(summary.get('runtime_vent_min'), 0)} min |",
            f"| Fog | {r(summary.get('runtime_fog_min'), 0)} min |",
            f"| Heat 1 (electric) | {r(summary.get('runtime_heat1_min'), 0)} min |",
            f"| Heat 2 (gas) | {r(summary.get('runtime_heat2_min'), 0)} min |",
            f"| Grow lights | {r(summary.get('runtime_grow_light_min'), 0)} min |",
            f"| Mister south | {r(summary.get('runtime_mister_south_h'), 2)}h |",
            f"| Mister west | {r(summary.get('runtime_mister_west_h'), 2)}h |",
            f"| Mister center | {r(summary.get('runtime_mister_center_h'), 2)}h |",
            "",
        ]
    )

    # Water
    water_total = summary.get("water_used_gal")
    mister_water = summary.get("mister_water_gal")
    if water_total is not None:
        lines.extend(
            [
                "### Water",
                "",
                f"- **Total:** {r(water_total, 0)} gal",
                f"- **Mister:** {r(mister_water, 0)} gal",
                "",
            ]
        )

    # Crop health (from Gemini Vision observations)
    crop_health = db_query_rows(f"""
        SELECT c.name, c.zone, ROUND(AVG(o.health_score)::numeric, 2) AS avg_health,
            COUNT(*) AS obs_count,
            string_agg(DISTINCT LEFT(o.notes, 50), '; ' ORDER BY LEFT(o.notes, 50)) AS notes
        FROM observations o JOIN crops c ON o.crop_id = c.id
        WHERE o.source = 'gemini-vision' AND o.ts::date = '{summary_date or date.today()}'
        GROUP BY c.name, c.zone ORDER BY c.name
    """)
    if crop_health:
        lines.extend(
            [
                "### Crop Health (Gemini Vision)",
                "",
                "| Crop | Zone | Health | Obs | Notes |",
                "|------|------|--------|-----|-------|",
            ]
        )
        for row in crop_health:
            if len(row) >= 5:
                health_pct = f"{float(row[2].strip()) * 100:.0f}%" if row[2].strip() else "—"
                notes = row[4].strip()[:60] if row[4].strip() else "—"
                lines.append(f"| {row[0].strip()} | {row[1].strip()} | {health_pct} | {row[3].strip()} | {notes} |")
        lines.append("")

    # Hourly pattern (compact)
    if hourly:
        lines.extend(
            ["### Hourly Pattern", "", "| Hour | Temp °F | VPD kPa | RH % |", "|------|---------|---------|------|"]
        )
        for h in hourly:
            lines.append(f"| {h['hour']} | {h['temp']} | {h['vpd']} | {h['rh']} |")
        lines.append("")

    return "\n".join(lines)


def generate_day(d: date) -> str:
    """Generate the complete daily plan document for a given date.

    Structure: Title → [Cycle sections chronologically] → End-of-Day Summary → 7-Day Stress

    Each cycle gets its own ## section with Reflection + Hypothesis + Setpoints.
    The day reads like a lab notebook — chronological, no collapsing.
    """
    title = d.strftime("%B %d, %Y")

    summary = get_daily_summary(d)
    plans = get_plans_for_date(d)
    setpoints = get_active_setpoints_at(d)
    hourly = get_hourly_pattern(d)
    stress_ctx = get_stress_context(d)

    # Frontmatter
    frontmatter = generate_frontmatter(d, plans, summary, setpoints)

    # Title
    body = [f"# {title}", ""]

    if not plans:
        body.extend(["*No planning cycles recorded for this day.*", ""])
    else:
        # Each plan gets its own cycle section, chronologically
        for plan in plans:
            prev_plan = get_previous_plan(plan["created"])
            waypoints = get_waypoints_for_plan(plan["plan_id"])
            body.append(generate_cycle_section(plan, prev_plan, waypoints))

    # End-of-day summary (unchanged)
    if summary:
        body.append(generate_daily_summary_section(summary, hourly, d))

    # 7-day stress context (unchanged)
    if stress_ctx:
        body.extend(
            [
                "## 7-Day Stress Context",
                "",
                "| Date | Heat (h) | VPD High (h) | Cold (h) |",
                "|------|----------|--------------|----------|",
            ]
        )
        for s in stress_ctx:
            body.append(f"| {s['date']} | {s['heat']} | {s['vpd_high']} | {s['cold']} |")
        body.append("")

    return frontmatter + "\n\n" + "\n".join(body)


def backfill():
    """Backfill all days that have plan_journal entries or daily_summary data."""
    # Find all dates with plans
    plan_dates = db_query_rows("""
        SELECT DISTINCT substring(plan_id from 'iris-(\\d{8})')::date as plan_date
        FROM plan_journal
        WHERE plan_id NOT LIKE 'iris-reactive%' AND plan_id NOT LIKE 'iris-fix%'
        ORDER BY plan_date
    """)

    # Find all dates with daily_summary
    summary_dates = db_query_rows("""
        SELECT date FROM daily_summary
        WHERE date >= '2026-03-24' AND cost_total IS NOT NULL
        ORDER BY date
    """)

    all_dates = set()
    for row in plan_dates:
        if row and row[0].strip():
            try:
                all_dates.add(date.fromisoformat(row[0].strip()))
            except ValueError:
                pass
    for row in summary_dates:
        if row and row[0].strip():
            try:
                all_dates.add(date.fromisoformat(row[0].strip()))
            except ValueError:
                pass

    print(f"Backfilling {len(all_dates)} days: {sorted(all_dates)}")

    for d in sorted(all_dates):
        print(f"  Generating {d}...", end=" ")
        try:
            content = generate_day(d)
            output = CONTENT_DIR / f"{d}.md"
            output.write_text(content)
            plans = get_plans_for_date(d)
            print(f"OK ({len(plans)} plans, {len(content)} chars)")
        except Exception as e:
            print(f"ERROR: {e}")


def main():
    parser = argparse.ArgumentParser(description="Generate daily plan documents")
    parser.add_argument("--backfill", action="store_true", help="Backfill all historical days")
    parser.add_argument("--date", type=str, help="Date to generate (YYYY-MM-DD)")
    parser.add_argument("--today", action="store_true", help="Generate today's plan")
    parser.add_argument("--cycle", type=str, choices=["morning", "midday", "evening"], help="Current planning cycle")
    parser.add_argument("--plan-id", type=str, help="Current plan ID")
    args = parser.parse_args()

    CONTENT_DIR.mkdir(parents=True, exist_ok=True)

    if args.backfill:
        backfill()
    elif args.today or args.date:
        d = date.today() if args.today else date.fromisoformat(args.date)
        content = generate_day(d)
        output = CONTENT_DIR / f"{d}.md"
        output.write_text(content)
        print(f"Generated {output} ({len(content)} chars)")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
