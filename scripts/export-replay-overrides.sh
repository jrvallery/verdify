#!/bin/bash
# export-replay-overrides.sh — Export climate + occupancy + outdoor sensors +
# equipment_state + mode_reason as-of joins for the replay harness.
#
# Originally built for Sprint 16 OBS-1e. Phase-0 stabilization plan extended
# the schema to support the replay_diff harness and 15-invariant suite
# (see docs/plans/firmware-stabilization-plan.md — the plan file at
# .claude-agents/iris-dev/plans/yo-iris-dev-you-help-humming-stonebraker.md).
#
# Usage: ./scripts/export-replay-overrides.sh [days]  (default: all history)
set -euo pipefail

DAYS=${1:-0}  # 0 = all history
# OUTDIR is env-overridable so Makefile targets can pin output directly into
# the firmware worktree's test/data/. Default preserves the original location
# for standalone invocations from the main repo.
OUTDIR=${OUTDIR:-/srv/verdify/firmware/test/data}
mkdir -p "$OUTDIR"
OUTFILE="$OUTDIR/replay_overrides.csv"

if [ "$DAYS" -eq 0 ]; then
    WHERE="c.temp_avg IS NOT NULL AND c.vpd_avg IS NOT NULL AND c.rh_avg IS NOT NULL"
    echo "Exporting all history from climate + occupancy + equipment_state + mode_reason..."
else
    WHERE="c.ts >= now() - interval '${DAYS} days' AND c.temp_avg IS NOT NULL AND c.vpd_avg IS NOT NULL AND c.rh_avg IS NOT NULL"
    echo "Exporting last ${DAYS} days..."
fi

# The replay CSV is tab-separated; header row required. NULLs export as
# empty strings (NULL '' in the COPY options).
#
# Column ordering is append-only: the replay harness validates required
# columns by header name, so adding columns is backward-compatible. Old
# columns kept for bench-test compatibility with existing replay_overrides.cpp.
#
# New Phase-0 columns:
#   outdoor_temp_f        — Tempest, for sprint-15 gate + new invariants
#   outdoor_dewpoint_f    — computed from Tempest temp+rh
#   outdoor_data_age_s    — seconds since last outdoor push; drives gate eligibility
#   solar_irradiance_w_m2 — Tempest, for sunrise-ramp invariants
#   indoor_dew_point      — from climate.dew_point (Magnus inside firmware)
#   eq_<relay>            — forward-filled equipment_state at row ts (0/1)
#   mode_reason           — sprint-15.1 diagnostic enum; drives invariant #10
#   greenhouse_state      — for invariant #6 transition counting
docker exec verdify-timescaledb psql -U verdify -d verdify -c "
COPY (
    WITH occ AS (
        SELECT ts, (value = 'occupied') AS occ
        FROM system_state WHERE entity = 'occupancy' ORDER BY ts
    ),
    modestate AS (
        -- forward-fill greenhouse_state and mode_reason at each climate ts
        SELECT ts, entity, value FROM system_state
        WHERE entity IN ('greenhouse_state','mode_reason')
    ),
    eqstate AS (
        -- forward-fill equipment state as 0/1 at each climate ts
        SELECT ts, equipment, state::int AS on FROM equipment_state
        WHERE equipment IN ('fog','vent','fan1','fan2','heat1','heat2',
                            'mister_south','mister_west','mister_center')
    )
    SELECT
        c.ts,
        c.temp_avg, c.vpd_avg, c.rh_avg,
        COALESCE(c.outdoor_rh_pct, 30) AS outdoor_rh_pct,
        COALESCE(c.enthalpy_delta, -5) AS enthalpy_delta,
        -- Phase-0 additions: outdoor sensor suite
        c.outdoor_temp_f,
        -- Computed indoor dewpoint (Magnus); NULL if inputs missing
        c.dew_point AS indoor_dew_point,
        -- Tempest solar (W/m²); often NULL overnight
        c.solar_irradiance_w_m2,
        -- Placeholder: outdoor_data_age_s isn't tracked in climate directly.
        -- We reconstruct by looking at age of most-recent outdoor push to
        -- pulled_outdoor_temp_f via setpoint_changes (source='plan' or 'band').
        -- For replay simplicity, set 0 when outdoor_temp_f is fresh (same ts),
        -- else NULL (invariants will treat NULL as 'stale' / gate-ineligible).
        CASE WHEN c.outdoor_temp_f IS NULL THEN NULL
             ELSE EXTRACT(EPOCH FROM (c.ts - (
                SELECT max(sc.ts) FROM setpoint_changes sc
                WHERE sc.parameter = 'outdoor_temp' AND sc.ts <= c.ts
             )))::int END AS outdoor_data_age_s,
        -- Legacy setpoint placeholders kept so existing replay_overrides.cpp parses
        NULL::float AS sp_temp_high, NULL::float AS sp_temp_low,
        NULL::float AS sp_vpd_high, NULL::float AS sp_vpd_low,
        0.0::float AS sp_bias_cool,
        NULL::float AS sp_vpd_hysteresis,
        NULL::float AS sp_watch_dwell_s,
        COALESCE(
            (SELECT o.occ FROM occ o WHERE o.ts <= c.ts ORDER BY o.ts DESC LIMIT 1),
            false
        ) AS occupied,
        -- Phase-0: greenhouse_state + mode_reason (forward-filled)
        (SELECT m.value FROM modestate m
         WHERE m.entity='greenhouse_state' AND m.ts <= c.ts
         ORDER BY m.ts DESC LIMIT 1) AS greenhouse_state,
        (SELECT m.value FROM modestate m
         WHERE m.entity='mode_reason' AND m.ts <= c.ts
         ORDER BY m.ts DESC LIMIT 1) AS mode_reason,
        -- Phase-0: equipment state bitmask (one column per relay)
        COALESCE((SELECT e.on FROM eqstate e WHERE e.equipment='fog' AND e.ts<=c.ts ORDER BY e.ts DESC LIMIT 1), 0) AS eq_fog,
        COALESCE((SELECT e.on FROM eqstate e WHERE e.equipment='vent' AND e.ts<=c.ts ORDER BY e.ts DESC LIMIT 1), 0) AS eq_vent,
        COALESCE((SELECT e.on FROM eqstate e WHERE e.equipment='fan1' AND e.ts<=c.ts ORDER BY e.ts DESC LIMIT 1), 0) AS eq_fan1,
        COALESCE((SELECT e.on FROM eqstate e WHERE e.equipment='fan2' AND e.ts<=c.ts ORDER BY e.ts DESC LIMIT 1), 0) AS eq_fan2,
        COALESCE((SELECT e.on FROM eqstate e WHERE e.equipment='heat1' AND e.ts<=c.ts ORDER BY e.ts DESC LIMIT 1), 0) AS eq_heat1,
        COALESCE((SELECT e.on FROM eqstate e WHERE e.equipment='heat2' AND e.ts<=c.ts ORDER BY e.ts DESC LIMIT 1), 0) AS eq_heat2,
        COALESCE((SELECT e.on FROM eqstate e WHERE e.equipment='mister_south' AND e.ts<=c.ts ORDER BY e.ts DESC LIMIT 1), 0) AS eq_mister_south,
        COALESCE((SELECT e.on FROM eqstate e WHERE e.equipment='mister_west' AND e.ts<=c.ts ORDER BY e.ts DESC LIMIT 1), 0) AS eq_mister_west,
        COALESCE((SELECT e.on FROM eqstate e WHERE e.equipment='mister_center' AND e.ts<=c.ts ORDER BY e.ts DESC LIMIT 1), 0) AS eq_mister_center
    FROM climate c
    WHERE ${WHERE}
    ORDER BY c.ts
) TO STDOUT WITH (FORMAT csv, DELIMITER E'\t', HEADER, NULL '')
" > "$OUTFILE"

ROWS=$(wc -l < "$OUTFILE")
echo "Exported $((ROWS - 1)) rows to $OUTFILE"
