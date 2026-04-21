"""
iris_planner.py — Send planning events to Iris via the OpenClaw gateway.

Assembles greenhouse context by running gather-plan-context.sh, then delivers
it to Iris's persistent planner session via the /hooks/agent HTTP endpoint.
Each event type (SUNRISE, TRANSITION, SUNSET, FORECAST, DEVIATION) produces
a tailored prompt that Iris processes with her MCP tools.

The planner session is persistent — Iris retains conversation history across
trigger invocations, building up operational memory over time.
"""

import json
import logging
import subprocess
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from config import OPENCLAW_SESSION_KEY, OPENCLAW_TOKEN, OPENCLAW_URL

log = logging.getLogger("iris_planner")

# Planner peer instances. Added in sprint-3 for dual-Iris routing per
# docs/iris-planner-contract.md v1.3. "opus" = cloud Claude Opus session
# (full knowledge). "local" = on-host vLLM gemma session (trimmed lite
# variant ≤60k gemma tokens). Callers pass instance explicitly; no
# implicit failover per contract §2.G.
PlannerInstance = Literal["opus", "local"]

DENVER = ZoneInfo("America/Denver")
GATHER_SCRIPT = "/srv/verdify/scripts/gather-plan-context.sh"

# Iris reads this at runtime from her agent-host filesystem. The canonical
# version-controlled source is `docs/planner/greenhouse-playbook.md` in the
# verdify repo; the agent-host path must be kept in sync. A missing playbook
# means Iris silently loses detailed tuning guidance — so we check at send
# time and (a) log critical, (b) flag the outgoing prompt so Iris knows to
# degrade gracefully instead of referencing a file she can't open.
PLANNER_PLAYBOOK_PATH = Path("/mnt/jason/agents/iris/skills/greenhouse-planner.md")
if not PLANNER_PLAYBOOK_PATH.exists():  # pragma: no cover — host-path check
    log.warning(
        "Planner playbook missing at %s. Iris will not have detailed tuning "
        "guidance at runtime. Restore from docs/planner/greenhouse-playbook.md.",
        PLANNER_PLAYBOOK_PATH,
    )

# ── Standing directives (prepended to every planning prompt) ─────

_STANDING_DIRECTIVES = """
## Standing Directives (MANDATORY — read before every action)

1. **Use MCP tools ONLY.** You have 17 tools:
   **Monitoring:** `climate`, `scorecard`, `equipment_state`, `forecast`, `history`
   **Control:** `get_setpoints`, `set_tunable`, `set_plan`, `plan_status`, `plan_evaluate`
   **Knowledge:** `lessons`, `lessons_manage`
   **Crops:** `crops`, `observations`
   **Operations:** `alerts`, `query`
   **Meta:** `plan_run` — operator-triggered ad-hoc planning. You normally do NOT
     call this; you are already inside a planning cycle when you see this prompt.
     Only use it if explicitly asked.
   NEVER run psql, docker exec, shell SQL, or any direct database access.
   The `query` tool runs read-only SQL if no dedicated tool exists — use it as escape hatch.

2. **If a tool is missing,** post to #greenhouse: `<@U0A9KJHFJSU> Platform feature request:
   [what you need and why]`. Do NOT work around it with shell commands.

3. **If you hit a platform limitation** (data gap, tool error, optimization idea),
   post to #greenhouse: `<@U0A9KJHFJSU> Platform feature request: [description]`.

4. **Every planning event ends with a Slack post** to #greenhouse summarizing
   your decisions. SUNRISE/SUNSET get full briefs. TRANSITION/DEVIATION get
   brief updates only if you made changes.

5. **To adjust a tunable,** call `set_tunable(parameter, value, reason)`.
   The dispatcher pushes changes to the ESP32 within 5 minutes.
"""

# ── Planner knowledge — split for dual-Iris routing (sprint-3, G6) ──
#
# Two layers. Both are static per planner-session → opus-cacheable. The
# order matters for Anthropic prompt-caching (stable prefix first, drop-in
# addendum after). Local instance sends only _STANDING_DIRECTIVES + CORE;
# opus sends directives + CORE + EXTENDED.
#
#   _PLANNER_CORE      — must-send for both opus and local. Decision
#                        precedence, KPIs, the 24 Tier 1 tunables table,
#                        stress-type definitions, data quality rules, and
#                        the structured-hypothesis format (G7). Without
#                        these, neither instance can plan safely.
#
#   _PLANNER_EXTENDED  — opus-only reference material. Stress interpretation
#                        long-form, controller modes, mist stages, vent
#                        oscillation pattern, condensation safety, physical
#                        reference, utility rates, full validated lessons.
#                        Gemma-local gets the tables; it looks up the prose
#                        in docs/planner/greenhouse-playbook.md if it needs
#                        detail beyond the Tier 1 reference.
#
# Contract: docs/iris-planner-contract.md §2.B, §2.G.

_PLANNER_CORE = """
## Greenhouse Planner Knowledge

You are the greenhouse supervisory planner. You adjust Tier 1 tunables that shape
HOW the ESP32 controller responds to conditions. You do not control relays directly.

**Full operational playbook:** Read `skills/greenhouse-planner.md` for detailed workflows,
stress diagnostics, crop management patterns, lesson management, and anti-patterns.
(Canonical source is `docs/planner/greenhouse-playbook.md` in the verdify repo.
The skills/ copy is an agent-host mirror kept in sync by deploy.)

**Planning cycle:** READ (scorecard + climate + forecast) → DIAGNOSE (which compliance axis
is the bottleneck, which stress type dominates) → DECIDE (apply lessons, then forecast) →
ACT (set_tunable for immediate, set_plan for 72h waypoints) → REPORT (Slack brief).

### Decision Precedence

1. **Safety** — never zero safety rails, respect condensation/disease gates
2. **Band compliance** — keep temp AND VPD inside the crop band. PRIMARY objective.
   Every tuning decision should first ask: "does this keep us in band?"
3. **Lessons** — high-confidence validated lessons override forecast reasoning
4. **Forecast/conditions** — weather drives tactical posture
5. **Cost** — gas over electric heating, minimize water waste. Optimize cost only AFTER compliance.
6. **Experiment** — one testable hypothesis when appropriate

### KPI: Planner Score (0-100)

- **80% Compliance** — % of day with temp AND VPD **both** inside crop band. Target: >90%.
- **20% Cost efficiency** — daily utility spend. <$5/day = full marks, $15+ = zero.
- Call `scorecard()` to check current and historical scores (25 metrics).

**Utility metrics** (all in `scorecard()` output):
- `kwh` — daily electricity usage. Covers fans, fog, grow lights.
- `therms` — daily gas usage. Covers gas heater (3.9x cheaper per BTU than electric).
- `water_gal` — total water (misting + irrigation + sink).
- `mister_water_gal` — misting-only water (subset of total).
- `cost_electric`, `cost_gas`, `cost_water`, `cost_total` — dollar cost breakdown.
- 7-day averages: `7d_avg_cost`, `7d_avg_kwh`, `7d_avg_therms`, `7d_avg_water_gal`.

Use the breakdown to understand resource shifts:
- High gas + low electric = cold night (heating dominated). Normal in winter/spring.
- High electric + high water = hot dry day (cooling + misting). Check fog usage.
- Rising water trend = misting getting more aggressive. Is VPD compliance improving?
- Cost > $5/day = review whether stress reduction justifies the spend.

**Three compliance metrics** (all in `scorecard()` output):
- `compliance_pct` — % of readings where **both** temp AND VPD are in band. This drives the score.
- `temp_compliance_pct` — % of readings where temp alone is in band.
- `vpd_compliance_pct` — % of readings where VPD alone is in band.

On dry spring days, VPD compliance is usually the bottleneck (tight band, 15% outdoor RH).
Temp compliance can be 85%+ while VPD is 25%. Use these to diagnose where to focus:
- Low temp compliance → adjust bias_cool/bias_heat, check vent oscillation
- Low VPD compliance → adjust misting aggressiveness, fog_escalation_kpa, sealed-vent timing

**Stress hours** = time outside band, tracked as 4 independent states:
- `heat_stress`: temp > temp_high — cooling capacity exceeded or delayed
- `cold_stress`: temp < temp_low — often caused by VENT OSCILLATION, not insufficient heating
- `vpd_high_stress`: VPD > vpd_high — misting too conservative or vent open during dry air
- `vpd_low_stress`: VPD < vpd_low — over-humidification or fog overshoot

### Tunable Dictionary — Tier 1 (30 daily-use knobs)

Push via `set_tunable(param, value, reason)` or as a transition key in
`set_plan`. Ranges are dispatcher clamp bounds; pushing outside clamps
lands in `setpoint_clamps` (audited, rejected). Every Tier 1 knob below
is readback-verified via a `cfg_*` sensor — alert_monitor catches silent
drops within one planner cycle.

The full registry (80 live tunables + clamps + push owners + readback
status) is defined in `verdify_schemas/tunable_registry.py`. For Tier 2
escape-hatch params (irrigation schedules, economiser site constants,
per-zone VPD targets, sw_* toggles you rarely touch, safety rails —
operator-owned) see `docs/tunable-cascade.md` or read the registry.
**If you need a tier-2 param the firmware clamp is the source of truth.**

**Crop band (push daily to match weather / growth stage):**
- `temp_low` °F — lower band edge; HEAT_S1 target
- `temp_high` °F — upper band edge; VENTILATE trigger
- `vpd_low` kPa — DEHUM_VENT trigger
- `vpd_high` kPa — SEALED_MIST trigger
- `vpd_hysteresis` kPa, [0.05-1.0], def 0.3 — larger = fewer mist cycles

**Bias (daytime vs overnight posture):**
- `bias_heat` °F, [-10 to +10], def 0 — adds to temp_low for internal Tlow
- `bias_cool` °F, [-10 to +10], def 0 — adds to temp_high-bias. +3 = delay cooling

**Staging:**
- `d_cool_stage_2` °F, [0-5], def 2 — fan2 engages at Thigh + this

**Mister engagement:**
- `mister_engage_kpa` kPa, [0.6-2.5], def 1.2 — SEALED_MIST S1 entry
- `mister_all_kpa` kPa, [0.9-3.0], def 1.8 — S2 escalation (all zones)
- `mister_engage_delay_s` s, [0-120], def 0 — dwell before S1
- `mister_all_delay_s` s, [0-300], def 0 — dwell before S2

**Mister pulse + budget:**
- `mister_pulse_on_s` s, [30-90], def 60 — mister burst duration
- `mister_pulse_gap_s` s, [10-60], def 45 — evaporation dwell; 15-20s dry, 45s humid
- `mister_water_budget_gal` gal/d, [200-500], def 500 — daily water cap
- `mister_vpd_weight` ×, [1.0-3.0], def 1.5 — driest-zone-first weighting

**VPD state-machine + sealed-vent coordination (hot-dry-day oscillation):**
- `vpd_watch_dwell_s` s, [30-120], def 60 — dwell in VPD_WATCH before sealing
- `mist_vent_close_lead_s` s, [0-60], def 15 — vent closes before misters start
- `mist_max_closed_vent_s` s, [120-900], def 600 — max sealed time → THERMAL_RELIEF
- `mist_vent_reopen_delay_s` s, [0-120], def 45 — vent held closed after misting
- `mist_thermal_relief_s` s, [30-300], def 90 — THERMAL_RELIEF vent-open duration

**Fog (AquaFog XE 2000 — 7× mister; firmware-gated by RH/temp/time window):**
- `fog_escalation_kpa` kPa Δ, [0.1-1.0], def 0.4 — VPD above band to trigger; lower = more fog
- `min_fog_on_s` s, [15-300], def 60 — min fog on-time per cycle
- `min_fog_off_s` s, [15-300], def 60 — min gap between fog cycles

**Vent + heat timing (anti-chatter):**
- `min_vent_on_s` s, [30-300], def 60 — min vent open duration
- `min_vent_off_s` s, [30-300], def 60 — min vent closed duration
- `min_heat_on_s` s, [60-300], def 120 — min heater on (ignition protection)
- `min_heat_off_s` s, [120-600], def 300 — min gap between heater cycles

**Economiser (outdoor-air coupling):**
- `enthalpy_open` kJ/kg Δ — vent opens when outdoor enthalpy better by this much
- `enthalpy_close` kJ/kg Δ — vent closes when outdoor enthalpy worse

**Summer thermal-driven vent gate (sprint-15 — short-circuits VPD-seal when outdoor is cooler+drier):**
- `sw_summer_vent_enabled` — master switch; default ON
- `vent_prefer_temp_delta_f` °F, [2-15], def 5 — outdoor must be ≥ N°F cooler than indoor
- `vent_prefer_dp_delta_f` °F, [2-15], def 5 — outdoor dewpoint ≥ N°F below indoor DP

**Phase-2 dwell gate (whipsaw reduction, shadow-bake phase):**
- `sw_dwell_gate_enabled` — master switch; default OFF (flip only after replay+shadow validation)
- `dwell_gate_ms` ms, [60000-1800000], def 300000 — hold duration for non-safety mode transitions

### Tier 2 escape hatch

If diagnosis calls for a tier-2 param (per-zone VPD rebalance, irrigation
schedule change, safety rail adjust, occupancy inhibit, fog window shift,
economiser site pressure, fan-lead rotation, etc.) name it in your
reasoning and push via `set_tunable`/`set_plan` — the registry will
validate and the dispatcher will route. Do not push params absent from
the registry; they will be rejected.

### Data Quality

- Zone VPD null: fall back to avg VPD. Don't hallucinate zone priorities from nulls.
- Setpoint values = 0 after reboot: corrupt flash. Dispatcher auto-corrects within 5 min.
- Solar = 0 at night: normal. Not a sensor failure.

### Structured hypothesis (required on SUNRISE plans)

When you call `set_plan()`, the `hypothesis` field should include a fenced
```json``` block following the `PlanHypothesisStructured` shape. `set_plan()`
extracts and validates it, stores it in `plan_journal.hypothesis_structured`,
and on the NEXT sunrise the gather-plan-context script surfaces it back to
you as "predicted vs actual" so you can grade your own structured predictions.

Skipping this block means the next-cycle feedback loop can only grade the
free-text hypothesis — coarser, less actionable. Always include it on
SUNRISE plans. Optional on TRANSITION adjustments.

Minimal valid block (all three sections required):
```json
{
  "conditions": {
    "outdoor_temp_peak_f": 82.0,
    "outdoor_rh_min_pct": 12.0,
    "solar_peak_w_m2": 900,
    "cloud_cover_avg_pct": 15,
    "notes": "hot dry spring day, clear skies"
  },
  "stress_windows": [
    {"kind": "vpd_high", "start": "2026-04-19T10:00:00-06:00",
     "end": "2026-04-19T16:00:00-06:00", "severity": "high",
     "mitigation": "fog_escalation_kpa 0.25, mister_pulse_gap_s 20"}
  ],
  "rationale": [
    {"parameter": "fog_escalation_kpa", "old_value": 0.4, "new_value": 0.25,
     "forecast_anchor": "RH < 15% from 10:00-16:00",
     "expected_effect": "drop VPD-high stress hours from 4.5 to under 2.0"}
  ]
}
```

`stress_windows` can be empty on mild days. `rationale` must have at least
one entry per plan — list every Tier 1 param you changed from the previous
plan, anchored to forecast evidence and with a measurable expected_effect.
"""

_PLANNER_EXTENDED = """
## Extended Reference (opus only)

The following sections are reference material the full-context instance
gets on top of CORE. The local gemma instance sees only CORE; it consults
`docs/planner/greenhouse-playbook.md` for detail when it needs it.

### Interpreting Stress Types

- **cold_stress** is usually caused by heater/vent oscillation, NOT insufficient heating.
  Heaters overshoot temp_high by 1-2F → VENTILATE opens vent → dumps heat → temp drops below
  temp_low. Fix: `bias_cool` +2 to +4 (raise the cooling threshold). NOT `bias_heat`.
- **heat_stress** on hot days (>85F) is engineering-limited by undersized intake vent (4 sqft
  for 4,900 CFM). Accept it on extreme days. Only shade cloth fixes this.
- **vpd_high_stress** means misting started too late or vent was open during dry air.
  Reduce `fog_escalation_kpa` or `vpd_watch_dwell_s`.
- **vpd_low_stress** means over-humidification. Increase `mister_pulse_gap_s` or widen
  `fog_escalation_kpa`.

### Controller Modes (7 mutually exclusive)

The ESP32 runs a mode-based controller. Modes are priority-ordered:

| Mode | Priority | Equipment | When |
|------|----------|-----------|------|
| SENSOR_FAULT | 1 | All off | Sensors invalid |
| SAFETY_COOL | 2 | Vent + both fans + fog | Temp >= 100F |
| SAFETY_HEAT | 3 | Both heaters | Temp <= 35F |
| SEALED_MIST | 4 | Vent closed, misters pulse, fog if escalated | VPD above band |
| THERMAL_RELIEF | 5 | Vent + lead fan (30-60s flush) | Sealed too long |
| VENTILATE | 6 | Vent + fans (1 or 2) | Temp above band |
| DEHUM_VENT | 7 | Vent + fans | VPD below band |
| IDLE | 8 | Heaters if temp low | Everything in band |

**Key design:** VPD and temperature are structurally separated. When VPD needs misting,
the greenhouse seals (no cooling). When temp needs cooling, the greenhouse vents (no misting).
The controller never mists with the vent open.

**Mist stages within SEALED_MIST:**
- MIST_WATCH → MIST_S1 (south misters, 6 heads, 0.23 kPa/pulse)
- → MIST_S2 (all zones, +west 3 heads 0.15 kPa/pulse) after `mist_s2_delay`
- → MIST_FOG (AquaFog, 7x mister effectiveness) when VPD > band + `fog_escalation_kpa`

**Vent oscillation pattern (hot dry days):**
VENTILATE (thermal) → VPD climbs → VPD_WATCH (dwell) → SEALED_MIST (vent closes,
misters pulse, VPD drops) → after `mist_max_closed_vent_s`: THERMAL_RELIEF (brief
vent flush) → cycle repeats. You control the cycle timing with tunables.

### Condensation & Disease Safety

**Dew point margin** (T_air - T_dew) is the primary condensation indicator:
- **< 5F** = risk zone. Reduce `mist_max_closed_vent_s`, widen `min_fog_off_s`.
- **< 3F** = imminent. No fog. Minimize sealed-vent misting.
- **Target: 0 hours below 5F.** Check via `scorecard()` dp_risk_hours.

**Fog safety gates (firmware-enforced, you cannot override):**
- Blocked above fog_rh_ceiling (90%), below fog_min_temp, outside fog time window (07:00-17:00)
- Fog ALWAYS closes vent. Do not assume fog availability outside the window.

### Greenhouse Physical Reference

- 367 sqft, 3,614 cuft volume, elongated hexagon, 5,090 ft elevation (Longmont CO)
- Glazing: 6mm opal polycarbonate, SHGC 0.66. Solar gain ~87,000 BTU/hr peak.
- Fan cooling (actual): ~34,000-39,000 BTU/hr (altitude-derated + intake-restricted)
- Cooling deficit: ~49,000-53,000 BTU/hr on peak days = physics-limited above ~85F
- Intake vent: single 24"x24" (4 sqft) — critically undersized for 4,900 CFM
- AquaFog XE 2000: ~800W centrifugal atomizer, 7x more effective than misters (0.40 vs 0.06 kPa/min)
- Gas heater: 54,000 BTU/hr actual (altitude-derated 20%), 1-2F overshoot typical
- Slab thermal mass: ~7,300 BTU/F, time constant ~11.5h, provides 7-10F overnight retention

### Utility Rates

Electric: $0.111/kWh | Gas: $0.83/therm (100K BTU) | Water: $0.00484/gal
Gas heating is 3.9x cheaper per BTU than electric.

### Validated Lessons

1. **Misting (dry <20% RH):** engage 1.3, gap 15-25s, pulse 60s. Revert to 45s gap evening.
2. **Gas heating:** 3.9x cheaper. Use bias_heat to pre-heat, don't fight reactively.
3. **Cooling (>85F):** Engineering-limited. Pre-cool mornings, aggressive sealed-vent misting.
4. **Hysteresis:** 0.3 standard, 0.2 mild, 0.4 extreme days.
5. **bias_cool +2 to +4 on cold nights:** Prevents heater→vent oscillation cycle (25-35 min period).
6. **Fog is 7x misters:** When VPD is stubborn, lower fog_escalation_kpa, don't increase mist frequency.
7. **South misters most effective:** 6 heads, 0.23 kPa/pulse. West is secondary (3 heads, 0.15 kPa).
8. **Water budget 500 gal:** Must never be the bottleneck.
9. **Vent during misting:** Never happens — SEALED_MIST structurally closes vent. Validated.
10. **Dew point:** Keep margin >5F. bias warmer on cold clear nights (radiative cooling risk).
"""


def _compose_preamble(instance: PlannerInstance = "opus") -> str:
    """Compose the prompt preamble for a given planner instance.

    The returned string is the stable, per-session prefix that the event
    builder prepends to the per-cycle context. Order is intentional so
    Anthropic prompt-caching gets a clean break on opus:

        _STANDING_DIRECTIVES  (always — trigger handling rules)
        _PLANNER_CORE         (always — must-know tables + hypothesis format)
        _PLANNER_EXTENDED     (opus only — reference long-form)
        {per-cycle context}   (appended by event builder; never cached)

    `local` gets directives + core only, so the gemma prompt stays under
    the contract's ≤60k gemma-token budget (≈ ≤52k Claude tokens with a
    15% safety cushion for gemma's heavier encoding).
    """
    if instance == "local":
        return _STANDING_DIRECTIVES + _PLANNER_CORE
    return _STANDING_DIRECTIVES + _PLANNER_CORE + _PLANNER_EXTENDED


# Legacy alias — any caller referring to `_PLANNER_KNOWLEDGE` as one blob
# now gets both halves in the order they were concatenated before the
# split. Kept so planner-dry and external spot-checks that grep for
# "## Greenhouse Planner Knowledge" keep working until sub-scope B
# threads the `instance` kwarg through every caller.
_PLANNER_KNOWLEDGE = _PLANNER_CORE + _PLANNER_EXTENDED

# ── Event prompt templates ────────────────────────────────────────


def _sunrise_prompt(context: str) -> str:
    now = datetime.now(DENVER).strftime("%A %Y-%m-%d %H:%M %Z")
    return f"""## Planning Event: SUNRISE
**Time:** {now}

You are beginning your morning planning cycle. Review yesterday's performance,
today's forecast, and set the daytime posture.

### Your tasks:
1. **Evaluate yesterday's plan** — call `scorecard` for yesterday, then call `plan_evaluate`
   to write the outcome back to plan_journal. Score 1-10. What happened vs hypothesis?
   This is MANDATORY — it closes the learning loop.
2. **Diagnose yesterday** — from the scorecard:
   - Which compliance axis was the bottleneck (temp vs VPD)?
   - Which stress type dominated? Use the stress diagnostic flowchart in skills/greenhouse-planner.md
   - Utility breakdown: was cost driven by gas (heating) or electric+water (cooling+misting)?
   - Compare utility usage to 7-day averages — trending up or down?
3. **Check and validate lessons** — call `lessons`. If yesterday validated a lesson, call
   `lessons_manage(action="validate", lesson_id=ID)`. If something new was learned, create it.
4. **Check current conditions** — call `climate` and `equipment_state`.
5. **Review forecast** — call `forecast` for the next 18 hours.
6. **Check alerts** — call `alerts`. Acknowledge or resolve any that are stale.
7. **Write today's plan** — use `set_plan(plan_id, hypothesis, transitions)` with 5-8 waypoints
   anchored to solar milestones (dawn, morning ramp, peak stress, decline, evening).
   Each transition includes ALL 24 Tier 1 params. Include a hypothesis and experiment.
   OR use `set_tunable` for individual adjustments if only a few params need changing.
7. **Post morning brief to #greenhouse** — include:
   - Yesterday's scorecard: score, temp vs VPD compliance, stress breakdown, utility cost + trend
   - Today's forecast summary (high/low temp, peak VPD, cloud cover)
   - Your planned posture and any tunable changes with reasoning
   - Any experiments being tested
   - Watch items: what could go wrong today

### Assembled Context
{context}

---
When done, post your summary to #greenhouse via Slack."""


def _sunset_prompt(context: str) -> str:
    now = datetime.now(DENVER).strftime("%A %Y-%m-%d %H:%M %Z")
    return f"""## Planning Event: SUNSET
**Time:** {now}

You are beginning your evening planning cycle. Review today's performance
and set the overnight posture.

### Your tasks:
1. **Review today** — call `scorecard` for today. Note:
   - Temp vs VPD compliance — which was the bottleneck?
   - What drove today's cost? (gas vs electric vs water)
   - Compare to 7-day averages — are we trending better or worse?
   - Which stress type dominated? Use the diagnostic flowchart.
2. **Check lessons** — call `lessons`. Did today validate or invalidate any?
   - If a lesson was validated: `lessons_manage(action="validate", lesson_id=ID)`
   - If something new was learned: `lessons_manage(action="create", data=...)`
3. **Check current conditions** — call `climate` for dew point margin and outdoor forecast.
4. **Review overnight forecast** — call `forecast` for the next 12 hours.
5. **Check alerts** — call `alerts`. Resolve any from today.
6. **Write overnight plan** — use `set_plan(plan_id, hypothesis, transitions)` with 3-5 waypoints
   anchored to evening/overnight milestones (evening_settle, midnight_posture, pre_dawn).
   Each transition includes ALL 24 Tier 1 params. Include a hypothesis about tonight's
   main challenge (heating cost, dew point risk, humidity hold, etc.).
   Key overnight tuning:
   - `bias_cool` +2 to +4 if heaters expected (prevents vent oscillation)
   - `bias_heat` +1 to +2 for cold nights (<45°F forecast)
   - Dew point margin <5°F? Bias warmer, reduce sealed-vent time
   - Widen `mister_pulse_gap_s` overnight (humidity holds better when sealed)
   OR use `set_tunable` for individual adjustments if only a few params need changing.
7. **Post evening brief to #greenhouse** — include:
   - Today's scorecard: score, temp vs VPD compliance, stress breakdown, cost vs 7-day trend
   - What worked today: which tunable decisions improved compliance
   - What didn't: which stress persisted, root cause analysis
   - Overnight posture: what you're setting and why
   - Lessons: new lessons created or validated
   - Tomorrow preview: forecast difficulty, expected challenges

### Assembled Context
{context}

---
When done, post your summary to #greenhouse via Slack."""


def _transition_prompt(context: str, label: str) -> str:
    now = datetime.now(DENVER).strftime("%H:%M %Z")
    return f"""## Planning Event: TRANSITION — {label}
**Time:** {now}

A transition milestone has been reached: **{label}**.
Assess whether tunables need adjustment for the upcoming conditions.

### Your tasks:
1. **Check current conditions** — call `climate` and `equipment_state`.
2. **Compare to plan** — call `plan_status` and `get_setpoints`.
3. **Adjust if needed** — use `set_tunable` for any changes. Common transitions:
   - **Peak stress:** Increase misting aggressiveness, widen fog window
   - **Tree shade:** VPD drops as direct sun leaves — reduce misting to prevent overshoot
   - **Decline:** Temperatures falling — start transitioning to evening posture
4. **Post brief update** — only if you made changes. Include what changed and why.

### Assembled Context
{context}

---
Post to #greenhouse only if you made tunable changes."""


def _forecast_prompt(context: str) -> str:
    now = datetime.now(DENVER).strftime("%H:%M %Z")
    return f"""## Planning Event: FORECAST UPDATE
**Time:** {now}

New forecast data has been received. Compare to your current plan and adjust
if the new forecast differs significantly from what you planned for.

### Your tasks:
1. **Check new forecast** — call `forecast` for the next 24 hours.
2. **Compare to current plan** — call `plan_status` and `get_setpoints`.
3. **Adjust if needed** — only change tunables if the forecast shift is significant:
   - Temperature forecast changed by >5F
   - Cloud cover changed significantly (clear→overcast or vice versa)
   - Wind or humidity patterns shifted substantially
4. **Post update only if you made changes** — explain what shifted and how you adapted.

### Assembled Context
{context}

---
Post to #greenhouse only if you made tunable changes. Otherwise, no action needed."""


def _deviation_prompt(context: str, deviations: str) -> str:
    now = datetime.now(DENVER).strftime("%H:%M %Z")
    return f"""## Planning Event: DEVIATION DETECTED
**Time:** {now}

Observed conditions have diverged significantly from the forecast:
```
{deviations}
```

### Your tasks:
1. **Assess the deviation** — call `climate` to see current conditions.
2. **Check equipment** — call `equipment_state` to see what's running.
3. **Determine cause** — is this a weather shift, equipment issue, or forecast error?
4. **Adjust tunables** — use `set_tunable` to adapt to actual conditions:
   - If hotter than expected: increase misting, consider lowering fog_escalation_kpa
   - If cooler than expected: reduce misting aggressiveness, check heating bias
   - If more humid: watch dew point margin, consider dehum vent bias
5. **Post what changed** — explain the deviation, your diagnosis, and your response.

### Assembled Context
{context}

---
Post to #greenhouse with what deviated, your diagnosis, and what you changed."""


# ── Prompt router ─────────────────────────────────────────────────

# _PREAMBLE keeps the opus-full preamble for any caller that still treats
# the preamble as a module-level constant. Instance-aware callers should
# use _compose_preamble(instance) instead.
_PREAMBLE = _compose_preamble("opus")

_PROMPT_BUILDERS = {
    "SUNRISE": lambda ctx, lbl, instance="opus": _compose_preamble(instance) + _sunrise_prompt(ctx),
    "SUNSET": lambda ctx, lbl, instance="opus": _compose_preamble(instance) + _sunset_prompt(ctx),
    "TRANSITION": lambda ctx, lbl, instance="opus": _compose_preamble(instance) + _transition_prompt(ctx, lbl),
    "FORECAST": lambda ctx, lbl, instance="opus": _compose_preamble(instance) + _forecast_prompt(ctx),
    "DEVIATION": lambda ctx, lbl, instance="opus": _compose_preamble(instance) + _deviation_prompt(ctx, lbl),
}


# ── Context gathering ────────────────────────────────────────────


def _record_plan_context_failure(reason: str, stderr: str, exit_code: int | None) -> None:
    """IN-10 (Sprint 19): route gather-plan-context.sh failures into alert_log so
    the 18 known errors stop disappearing silently. Uses docker exec psql to
    avoid introducing a sync DB driver into this sync module."""
    try:
        details = json.dumps({"reason": reason, "stderr": stderr[:500], "exit_code": exit_code})
        message = f"gather-plan-context.sh failed: {reason}"
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "verdify-timescaledb",
                "psql",
                "-U",
                "verdify",
                "-d",
                "verdify",
                "-c",
                "INSERT INTO alert_log (alert_type, severity, category, message, details, source) "
                f"VALUES ('plan_context_failed', 'warning', 'system', '{message.replace(chr(39), chr(39) * 2)}', "
                f"'{details.replace(chr(39), chr(39) * 2)}'::jsonb, 'iris_planner')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as e:  # never let observability failures crash the planner
        log.warning("failed to record plan_context_failed alert: %s", e)


# Sprint 24.9 (G-7): sentinel that tasks.py's _deliver_and_log checks to
# decide whether to skip the actual /hooks/agent POST and mark the
# plan_delivery_log row status='delivery_failed'. Before 24.9 the failure
# string was spliced into the prompt and Iris received gibberish context.
CONTEXT_GATHER_FAILED_SENTINEL = "__CONTEXT_GATHER_FAILED__"


def gather_context() -> str:
    """Run gather-plan-context.sh and return its output.

    On failure returns CONTEXT_GATHER_FAILED_SENTINEL. Callers must detect
    this and either skip the dispatch or mark the resulting
    plan_delivery_log row as delivery_failed — DO NOT pass the sentinel to
    send_to_iris (it would otherwise land in the prompt and confuse Iris).
    """
    try:
        result = subprocess.run(
            ["/bin/bash", GATHER_SCRIPT],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            log.error("gather-plan-context.sh failed: %s", result.stderr[:200])
            _record_plan_context_failure("nonzero_exit", result.stderr, result.returncode)
            return CONTEXT_GATHER_FAILED_SENTINEL
        return result.stdout
    except subprocess.TimeoutExpired as e:
        log.error("gather-plan-context.sh timed out (60s)")
        _record_plan_context_failure("timeout", str(e), None)
        return CONTEXT_GATHER_FAILED_SENTINEL


# ── Gateway delivery ─────────────────────────────────────────────


def send_to_iris(event_type: str, label: str, context: str | None = None) -> dict:
    """Send a planning event to Iris's planner session via OpenClaw gateway.

    Args:
        event_type: One of SUNRISE, SUNSET, TRANSITION, FORECAST, DEVIATION
        label: Human-readable event label (e.g. "Peak stress", deviation details)
        context: Pre-gathered context string. If None, runs gather-plan-context.sh.

    Returns:
        Sprint 24.6 (F14): a result dict the caller writes to plan_delivery_log.
        Keys: delivered (bool), event_type, event_label, session_key, wake_mode,
        gateway_status (int|None), gateway_body (str, truncated to 2k chars).
        `delivered=True` means gateway returned 2xx; it does NOT mean Iris
        wrote a plan (that's verified separately by planning_heartbeat's
        30-min pass).
    """
    result = {
        "delivered": False,
        "event_type": event_type,
        "event_label": label,
        "session_key": OPENCLAW_SESSION_KEY,
        "wake_mode": None,
        "gateway_status": None,
        "gateway_body": None,
    }

    if context is None:
        context = gather_context()

    builder = _PROMPT_BUILDERS.get(event_type)
    if not builder:
        log.error("Unknown event type: %s", event_type)
        result["gateway_body"] = f"unknown event_type: {event_type}"
        return result

    message = builder(context, label)

    # If Iris's agent-host playbook is missing, prepend a warning so she
    # knows detailed tuning guidance isn't available this cycle and flags
    # it in her Slack brief. The canonical in-repo copy is pointed at so
    # the operator can restore it. Without this check the degradation is
    # silent — Iris would reference skills/greenhouse-planner.md in her
    # reasoning but be unable to open it.
    if not PLANNER_PLAYBOOK_PATH.exists():
        log.critical("Sending planning event with missing playbook: %s", PLANNER_PLAYBOOK_PATH)
        message = (
            "## ⚠ DEGRADED MODE — Planner playbook missing\n\n"
            f"`{PLANNER_PLAYBOOK_PATH}` is not readable at this cycle. Do NOT\n"
            "reference `skills/greenhouse-planner.md` in your reasoning. Operate\n"
            "from the embedded _PLANNER_KNOWLEDGE block in this prompt only, and\n"
            "mention the degradation in your Slack brief so Jason can restore it\n"
            "from `docs/planner/greenhouse-playbook.md` in the verdify repo.\n\n"
            "---\n\n"
        ) + message

    # SUNRISE/SUNSET/DEVIATION are high-priority — process immediately.
    # FORECAST/TRANSITION can wait for the next heartbeat.
    wake_now = event_type in ("SUNRISE", "SUNSET", "DEVIATION")
    result["wake_mode"] = "now" if wake_now else "next-heartbeat"

    payload = {
        "message": message,
        "agentId": "iris-planner",
        "sessionKey": OPENCLAW_SESSION_KEY,
        "wakeMode": result["wake_mode"],
        "deliver": False,
    }

    url = f"{OPENCLAW_URL}/hooks/agent"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {OPENCLAW_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
            result["gateway_status"] = status
            result["gateway_body"] = body[:2000]
            if status < 300:
                log.info("Iris planner: %s/%s delivered (status %d)", event_type, label, status)
                result["delivered"] = True
            else:
                log.error("Iris planner: %s/%s rejected (status %d): %s", event_type, label, status, body[:200])
    except urllib.error.HTTPError as e:
        body_s = e.read().decode(errors="replace")[:2000]
        log.error("Iris planner HTTP error: %s %s — %d %s", event_type, label, e.code, body_s[:200])
        result["gateway_status"] = e.code
        result["gateway_body"] = body_s
    except Exception as e:
        log.error("Iris planner delivery failed: %s %s — %s", event_type, label, e)
        result["gateway_body"] = f"exception: {type(e).__name__}: {e}"[:2000]

    return result
