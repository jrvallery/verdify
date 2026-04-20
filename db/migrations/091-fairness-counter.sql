-- Migration 091: daily_summary.mister_fairness_overrides_today (Sprint 24-alignment)
--
-- Firmware sprint-2 (4471743) added a zone-fairness watchdog that overrides
-- the stress-scoring mister selector when a zone has been stressed for 10+
-- minutes without firing. Each override increments an on-device counter that
-- resets at midnight local time. Without this column, the counter never
-- reaches the DB and the 7-day watch to validate the fairness fix would
-- require journalctl scraping.
--
-- Source: ESP32 template sensor `mister_fairness_overrides_today` (id, same
-- as name sanitized). Routed via ingestor entity_map.DAILY_ACCUM_MAP →
-- state.daily → write_daily_summary midnight upsert. Same lifecycle as the
-- other cycles_*/runtime_* daily accumulators.

BEGIN;

ALTER TABLE daily_summary
    ADD COLUMN IF NOT EXISTS mister_fairness_overrides_today INTEGER;

COMMENT ON COLUMN daily_summary.mister_fairness_overrides_today IS
    'Firmware zone-fairness watchdog override count for the day. Each value '
    'represents one time select_overdue_zone() chose a zone because it had '
    'been stressed ≥10 min without firing. Sprint-2 expectation: 0-5/day if '
    'the 90-day starvation pattern is real; 0 if scoring was already fair.';

COMMIT;
