-- 118-inference-infra-telemetry.sql
-- =============================================================================
-- Public inference infrastructure telemetry for the Verdify site.
--
-- Extends the GPU mirror from power-only Cortex samples to the full five-GPU
-- inference fleet, and adds node-exporter CPU samples for public-safe VM/host
-- utilization panels.
-- =============================================================================

BEGIN;

ALTER TABLE gpu_power
    ADD COLUMN IF NOT EXISTS vm_name TEXT,
    ADD COLUMN IF NOT EXISTS purpose TEXT,
    ADD COLUMN IF NOT EXISTS gpu_util_pct DOUBLE PRECISION CHECK (
        gpu_util_pct IS NULL OR (gpu_util_pct >= 0 AND gpu_util_pct <= 100)
    ),
    ADD COLUMN IF NOT EXISTS temperature_c DOUBLE PRECISION CHECK (
        temperature_c IS NULL OR (temperature_c >= 0 AND temperature_c < 130)
    ),
    ADD COLUMN IF NOT EXISTS memory_used_mb DOUBLE PRECISION CHECK (
        memory_used_mb IS NULL OR memory_used_mb >= 0
    ),
    ADD COLUMN IF NOT EXISTS memory_free_mb DOUBLE PRECISION CHECK (
        memory_free_mb IS NULL OR memory_free_mb >= 0
    );

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'gpu_power'::regclass
           AND contype = 'p'
           AND conname = 'gpu_power_pkey'
    ) AND NOT EXISTS (
        SELECT 1
          FROM pg_constraint c
          JOIN pg_attribute a
            ON a.attrelid = c.conrelid
           AND a.attnum = ANY(c.conkey)
         WHERE c.conrelid = 'gpu_power'::regclass
           AND c.contype = 'p'
           AND a.attname = 'greenhouse_id'
    ) THEN
        ALTER TABLE gpu_power DROP CONSTRAINT gpu_power_pkey;
        ALTER TABLE gpu_power ADD PRIMARY KEY (greenhouse_id, ts, host, gpu);
    END IF;
END$$;

UPDATE gpu_power
   SET vm_name = COALESCE(vm_name, 'vm-docker-ai'),
       purpose = CASE
           WHEN purpose IS NULL OR purpose LIKE '%OpenClaw%' THEN
               'Iris/Hermes inference, embeddings, retrieval, and agent workloads'
           ELSE purpose
       END
 WHERE host = 'cortex';

CREATE TABLE IF NOT EXISTS infra_cpu (
    ts              TIMESTAMPTZ NOT NULL,
    host            TEXT        NOT NULL,
    vm_name         TEXT,
    purpose         TEXT,
    cpu_util_pct    DOUBLE PRECISION CHECK (
        cpu_util_pct IS NULL OR (cpu_util_pct >= 0 AND cpu_util_pct <= 100)
    ),
    load1           DOUBLE PRECISION,
    cores           INTEGER CHECK (cores IS NULL OR cores > 0),
    memory_used_pct DOUBLE PRECISION CHECK (
        memory_used_pct IS NULL OR (memory_used_pct >= 0 AND memory_used_pct <= 100)
    ),
    source          TEXT        NOT NULL DEFAULT 'node_exporter',
    raw             JSONB       NOT NULL DEFAULT '{}'::jsonb,
    greenhouse_id   TEXT        NOT NULL DEFAULT 'vallery' REFERENCES greenhouses(id),
    PRIMARY KEY (greenhouse_id, ts, host)
);

SELECT create_hypertable('infra_cpu', 'ts', if_not_exists => TRUE);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'infra_cpu'::regclass
           AND contype = 'p'
           AND conname = 'infra_cpu_pkey'
    ) AND NOT EXISTS (
        SELECT 1
          FROM pg_constraint c
          JOIN pg_attribute a
            ON a.attrelid = c.conrelid
           AND a.attnum = ANY(c.conkey)
         WHERE c.conrelid = 'infra_cpu'::regclass
           AND c.contype = 'p'
           AND a.attname = 'greenhouse_id'
    ) THEN
        ALTER TABLE infra_cpu DROP CONSTRAINT infra_cpu_pkey;
        ALTER TABLE infra_cpu ADD PRIMARY KEY (greenhouse_id, ts, host);
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_infra_cpu_host_ts
  ON infra_cpu (greenhouse_id, host, ts DESC);

UPDATE infra_cpu
   SET vm_name = COALESCE(vm_name, 'vm-docker-ai'),
       purpose = CASE
           WHEN purpose IS NULL OR purpose IN (
               'Local inference, embeddings, retrieval, and agent workloads',
               'Iris/OpenClaw inference, embeddings, retrieval, and agent workloads'
           ) THEN
               'Hermes planner, embeddings, retrieval, and agent workloads'
           ELSE purpose
       END
 WHERE host = 'cortex';

DROP VIEW IF EXISTS v_gpu_power_latest;

CREATE OR REPLACE VIEW v_gpu_power_latest AS
WITH latest AS (
    SELECT DISTINCT ON (greenhouse_id, host, gpu)
           ts,
           host,
           vm_name,
           purpose,
           gpu,
           device,
           model_name,
           watts,
           gpu_util_pct,
           temperature_c,
           memory_used_mb,
           memory_free_mb,
           source,
           raw,
           greenhouse_id
      FROM gpu_power
     ORDER BY greenhouse_id, host, gpu, ts DESC
)
SELECT *,
       EXTRACT(EPOCH FROM now() - ts)::int AS age_s
  FROM latest;

CREATE OR REPLACE VIEW v_infra_cpu_latest AS
WITH latest AS (
    SELECT DISTINCT ON (greenhouse_id, host)
           ts,
           host,
           vm_name,
           purpose,
           cpu_util_pct,
           load1,
           cores,
           memory_used_pct,
           source,
           raw,
           greenhouse_id
      FROM infra_cpu
     ORDER BY greenhouse_id, host, ts DESC
)
SELECT *,
       EXTRACT(EPOCH FROM now() - ts)::int AS age_s
  FROM latest;

COMMENT ON TABLE infra_cpu IS
  'Public-safe CPU and memory utilization samples mirrored from node exporters for Verdify inference and site infrastructure panels.';

COMMENT ON COLUMN gpu_power.gpu_util_pct IS
  'Instantaneous GPU compute utilization percentage from DCGM_FI_DEV_GPU_UTIL.';

COMMENT ON COLUMN gpu_power.temperature_c IS
  'GPU temperature in Celsius from DCGM_FI_DEV_GPU_TEMP.';

COMMIT;
