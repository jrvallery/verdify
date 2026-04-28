-- Migration 094: controller v2 diagnostics
--
-- Exposes the timers and assist flag needed to diagnose the band-first FSM:
-- sealed attempt runtime, VPD dwell, backoff lockout, and hot/dry vent mist assist.

ALTER TABLE diagnostics
    ADD COLUMN IF NOT EXISTS sealed_timer_s integer,
    ADD COLUMN IF NOT EXISTS vpd_watch_timer_s integer,
    ADD COLUMN IF NOT EXISTS mist_backoff_timer_s integer,
    ADD COLUMN IF NOT EXISTS vent_mist_assist_active integer;

CREATE INDEX IF NOT EXISTS idx_diagnostics_v2_backoff
    ON diagnostics (mist_backoff_timer_s, ts DESC)
    WHERE mist_backoff_timer_s > 0;

CREATE INDEX IF NOT EXISTS idx_diagnostics_v2_vent_mist_assist
    ON diagnostics (vent_mist_assist_active, ts DESC)
    WHERE vent_mist_assist_active = 1;

COMMENT ON COLUMN diagnostics.sealed_timer_s IS
    'Controller v2: seconds spent in the current SEALED_MIST attempt.';
COMMENT ON COLUMN diagnostics.vpd_watch_timer_s IS
    'Controller v2: seconds VPD has remained above band before humidification/backoff decisions.';
COMMENT ON COLUMN diagnostics.mist_backoff_timer_s IS
    'Controller v2: seconds remaining/elapsed in post-timeout mist backoff lockout.';
COMMENT ON COLUMN diagnostics.vent_mist_assist_active IS
    'Controller v2: 1 when VENTILATE is also carrying mister demand for high VPD.';
