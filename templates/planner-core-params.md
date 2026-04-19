# Planner Core Parameters — Mandatory Emission List

## The canonical list

Every planner transition must emit **all 24 Tier 1 tunables**. The authoritative
list lives in two places that are kept in sync:

1. `ingestor/iris_planner.py` — the `_PLANNER_KNOWLEDGE` block enumerates all
   24 in the "24 Tier 1 Tunables" table Iris reads on every event.
2. `scripts/validate-plan-coverage.sh` — the `CORE=` variable (line 8) is the
   executable spec. CI and `gather-plan-context.sh` section 28 invoke it to
   assert each transition carries the full set.

If those two disagree, the shell script wins.

## Why emit the full set every transition

1. **Clean supersession.** The DB trigger deactivates older plans' waypoints
   when a new plan writes the same parameter at a future ts. If you skip a
   Tier 1 param, the previous plan's value stays "active" for it indefinitely.
2. **Chart continuity.** Dashboards and the daily plan page trace setpoint
   lines across the forecast window; gaps show up as stale.
3. **Audit trail.** Every plan explicitly documents all 24 tuning levers,
   not just what changed.

## Tier 2 — do NOT emit

The following are **band-driven**, computed every 5 minutes from
`fn_band_setpoints()` against active crop profiles. The planner cannot set
them; the ingestor dispatcher (`ingestor/tasks.py` `BAND_DRIVEN` set) silently
drops them if they appear in a plan:

- `temp_high`, `temp_low`
- `vpd_high`, `vpd_low`
- `vpd_target_south`, `vpd_target_west`, `vpd_target_east`, `vpd_target_center`
- `mister_engage_delay_s`, `mister_all_delay_s`
- `safety_min`, `safety_max`, `safety_vpd_min`, `safety_vpd_max`

To shift thermal or VPD band edges, tune `bias_heat` / `bias_cool` and
`vpd_hysteresis` (all Tier 1). Emitting a Tier 2 param is a silent no-op —
not an error, but not an effect either.

## Historical note

Earlier revisions of this doc listed 10 "mandatory" params that included
`temp_high`/`temp_low`/`vpd_high`/`vpd_low`. That was wrong: those four
were already Tier 2 at the time the list was written. The doc was
rewritten 2026-04-18 after an audit caught the contradiction against
`ingestor/tasks.py` dispatch logic.
