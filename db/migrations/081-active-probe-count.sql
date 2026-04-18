-- Migration 081: active_probe_count on diagnostics (Sprint 17 / FW-10)
--
-- Context: when a zone probe goes stale (Modbus timeout > 5 min), the
-- firmware previously kept averaging its last-cached value into the
-- aggregate, silently contaminating the planner's view of the greenhouse.
-- FW-10 excludes stale probes from the averaging lambdas and emits an
-- active_probe_count (0–4) so the planner + downstream analytics can see
-- how many zones actually contributed to any given climate row.
--
-- When count < 4, aggregate avg_temp / rh / vpd values represent a
-- subset of the greenhouse — not the whole thing — and should be treated
-- with reduced confidence in band-compliance scoring.

BEGIN;

ALTER TABLE diagnostics
    ADD COLUMN IF NOT EXISTS active_probe_count INTEGER;

CREATE INDEX IF NOT EXISTS idx_diagnostics_probe_count
    ON diagnostics (active_probe_count, ts DESC)
    WHERE active_probe_count < 4;

COMMENT ON COLUMN diagnostics.active_probe_count IS
    'FW-10: number of zone probes (0-4) contributing to avg_temp/rh/vpd aggregates at this sample. <4 means one or more probes are stale (>5 min Modbus timeout).';

COMMIT;
