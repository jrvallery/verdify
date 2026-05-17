-- 117-gpu-power-telemetry.sql
-- =============================================================================
-- Public GPU power telemetry for the Verdify site.
--
-- Source metric: DCGM_FI_DEV_POWER_USAGE from the Cortex GPU host. This mirrors
-- the primary Grafana GPU power dataset without exposing Grafana/Auth tokens to
-- public browsers.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS gpu_power (
    ts            TIMESTAMPTZ NOT NULL,
    host          TEXT        NOT NULL DEFAULT 'cortex',
    gpu           TEXT        NOT NULL,
    device        TEXT,
    model_name    TEXT,
    watts         DOUBLE PRECISION NOT NULL CHECK (watts >= 0 AND watts < 1000),
    source        TEXT        NOT NULL DEFAULT 'dcgm',
    raw           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    greenhouse_id TEXT        NOT NULL DEFAULT 'vallery' REFERENCES greenhouses(id),
    PRIMARY KEY (greenhouse_id, ts, host, gpu)
);

SELECT create_hypertable('gpu_power', 'ts', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_gpu_power_host_ts
  ON gpu_power (greenhouse_id, host, ts DESC);

CREATE INDEX IF NOT EXISTS idx_gpu_power_gpu_ts
  ON gpu_power (greenhouse_id, gpu, ts DESC);

DO $$
BEGIN
    -- Migration 118 extends this view. If this migration is re-run after 118,
    -- do not replace the newer shape with the original power-only projection.
    IF to_regclass('public.v_gpu_power_latest') IS NULL
       OR NOT EXISTS (
           SELECT 1
             FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'v_gpu_power_latest'
              AND column_name = 'vm_name'
       ) THEN
        EXECUTE $view$
            CREATE OR REPLACE VIEW v_gpu_power_latest AS
            WITH latest AS (
                SELECT DISTINCT ON (greenhouse_id, host, gpu)
                       ts, host, gpu, device, model_name, watts, source, raw, greenhouse_id
                  FROM gpu_power
                 ORDER BY greenhouse_id, host, gpu, ts DESC
            )
            SELECT *,
                   EXTRACT(EPOCH FROM now() - ts)::int AS age_s
              FROM latest
        $view$;
    END IF;
END$$;

COMMENT ON TABLE gpu_power IS
  'GPU power draw samples mirrored from the Cortex DCGM exporter for public Verdify site charts.';

COMMENT ON COLUMN gpu_power.watts IS
  'Instantaneous GPU board power draw in watts from DCGM_FI_DEV_POWER_USAGE.';

COMMIT;
