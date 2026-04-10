# Planner Core Parameters — Mandatory Emission List

## Required Parameters (MUST emit in every plan)

These 10 parameters MUST have a waypoint in EVERY scheduled plan, even if the value is unchanged from the previous plan. This ensures:
1. **Chart continuity** — homepage and dashboard setpoint lines extend through the full forecast window
2. **Clean supersession** — the DB trigger deactivates older plans' waypoints when a new plan writes the same parameter. If you skip a param, the old plan's value stays "active" indefinitely.
3. **Audit trail** — every plan explicitly documents what ALL key setpoints are, not just what changed

| # | Parameter | Unit | Typical Range | Why Mandatory |
|---|-----------|------|---------------|---------------|
| 1 | `temp_high` | °F | 78-85 | Homepage "Target Max" line. Controls COOL_S1 trigger. |
| 2 | `temp_low` | °F | 55-62 | Homepage "Target Min" line. Controls HEAT_S1 trigger. |
| 3 | `vpd_high` | kPa | 1.4-2.2 | Homepage "VPD Target" line. HUMID_S1 = vpd_high + hysteresis. |
| 4 | `vpd_hysteresis` | kPa | 0.2-0.5 | Determines mister engage point (vpd_high + this). |
| 5 | `d_cool_stage_2` | °F | 2-5 | COOL_S2 threshold = temp_high + this. Controls dual-fan staging. |
| 6 | `mister_engage_kpa` | kPa | 1.2-1.8 | Primary misting threshold. Critical for VPD control. |
| 7 | `mister_all_kpa` | kPa | 1.4-2.2 | HUMID_S2 all-zone threshold. |
| 8 | `mister_pulse_on_s` | s | 30-90 | Mister pulse duration. Changes between day/night. |
| 9 | `mister_pulse_gap_s` | s | 20-60 | Gap between mister pulses. Key tuning parameter. |
| 10 | `mister_vpd_weight` | - | 1.0-3.0 | Zone rotation VPD weighting. |

## How to Emit

Even when keeping the same value:
```sql
INSERT INTO setpoint_plan (ts, parameter, value, plan_id, source, reason) VALUES
  ('2026-03-30 06:00:00-06', 'temp_low', 58, 'iris-20260330-0600', 'iris', 'Holding steady'),
  ('2026-03-30 06:00:00-06', 'temp_high', 82, 'iris-20260330-0600', 'iris', 'Holding steady'),
  ...;
```

## What Happens If You Skip

- The parameter's active waypoint stays from an OLDER plan
- v_active_plan returns a stale plan_id for that param
- Charts show the old plan's line, not the current plan
- The ESP32 Controller Health dashboard's oscillation heatmap lights up

## Context Section

`gather-plan-context.sh` section 20b shows CURRENT ACTIVE SETPOINTS for all 12 core parameters. Copy any you're not changing.
