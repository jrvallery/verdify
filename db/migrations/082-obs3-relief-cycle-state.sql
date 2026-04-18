-- Migration 082: OBS-3 relief-cycle state exposure (Sprint 18)
--
-- Context: Sprint 16 (OBS-1e) made the firmware's silent overrides visible
-- via the override_events stream — relief_cycle_breaker fires when the
-- ControlState.relief_cycle_count hits max_relief_cycles. But the planner
-- still can't see the COUNT itself, only the event when it hits the limit.
-- She also can't see vent_latch_timer_ms — the 30-min post-relief timeout
-- (FW-8) that keeps VENTILATE latched after the counter exhausts.
--
-- Sprint 18 exposes both values every control cycle so:
-- - The planner's MCP tools can read current counter state and adjust
--   max_relief_cycles deliberately instead of blind.
-- - Post-deploy sensor-health can trend them.
-- - Grafana can plot counter trajectories overlaid with mode changes.

BEGIN;

ALTER TABLE diagnostics
    ADD COLUMN IF NOT EXISTS relief_cycle_count INTEGER,
    ADD COLUMN IF NOT EXISTS vent_latch_timer_s INTEGER;

CREATE INDEX IF NOT EXISTS idx_diagnostics_relief_active
    ON diagnostics (relief_cycle_count, ts DESC)
    WHERE relief_cycle_count > 0;

COMMENT ON COLUMN diagnostics.relief_cycle_count IS
    'OBS-3: ControlState.relief_cycle_count at this sample — how many consecutive SEALED_MIST → THERMAL_RELIEF cycles have fired without a VPD-in-band reset. Hits max_relief_cycles → firmware latches VENTILATE (relief_cycle_breaker override).';
COMMENT ON COLUMN diagnostics.vent_latch_timer_s IS
    'OBS-3: ControlState.vent_latch_timer_ms converted to seconds. Nonzero when firmware is in the post-relief VENTILATE latch (FW-8). Resets to 0 on successful seal entry or after 1800 s (30 min) timeout.';

COMMIT;
