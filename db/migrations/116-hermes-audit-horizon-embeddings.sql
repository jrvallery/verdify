-- 116-hermes-audit-horizon-embeddings.sql
-- =============================================================================
-- Hermes end-to-end audit repair.
--
-- 1. Carry trigger_id / planner_instance through setpoint_plan so the dispatcher
--    can stamp setpoint_changes with the originating Hermes trigger.
-- 2. Rebuild v_active_plan with the audit columns.
-- 3. Expand verdify_embeddings to include crop observations as first-class
--    semantic context alongside lessons, plans, site docs, and playbook chunks.
-- 4. Retire superseded past active plan rows while keeping the current winner
--    for each parameter and preserving future waypoints.
-- =============================================================================

BEGIN;

ALTER TABLE setpoint_plan
  ADD COLUMN IF NOT EXISTS trigger_id UUID,
  ADD COLUMN IF NOT EXISTS planner_instance TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint
         WHERE conrelid = 'plan_delivery_log'::regclass
           AND contype = 'u'
           AND conkey = ARRAY[
               (SELECT attnum FROM pg_attribute
                 WHERE attrelid = 'plan_delivery_log'::regclass
                   AND attname = 'trigger_id')
           ]::smallint[]
    ) THEN
        ALTER TABLE plan_delivery_log
          ADD CONSTRAINT plan_delivery_log_trigger_id_key UNIQUE (trigger_id);
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_setpoint_plan_trigger_id
  ON setpoint_plan (trigger_id)
  WHERE trigger_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_setpoint_plan_instance
  ON setpoint_plan (planner_instance, created_at DESC)
  WHERE planner_instance IS NOT NULL;

COMMENT ON COLUMN setpoint_plan.trigger_id IS
  'Hermes planner trigger UUID copied from plan_delivery_log. Used by dispatcher '
  'to stamp setpoint_changes.trigger_id for final ESP32 push audit.';

COMMENT ON COLUMN setpoint_plan.planner_instance IS
  'Planner instance label copied from the Hermes audit banner (local | opus). '
  'Propagated through v_active_plan into setpoint_changes.';

UPDATE setpoint_plan sp
   SET trigger_id = COALESCE(sp.trigger_id, pj.trigger_id),
       planner_instance = COALESCE(sp.planner_instance, pj.planner_instance)
  FROM plan_journal pj
 WHERE sp.plan_id = pj.plan_id
   AND (sp.trigger_id IS NULL OR sp.planner_instance IS NULL);

CREATE OR REPLACE VIEW v_active_plan AS
SELECT DISTINCT ON (parameter)
       parameter,
       value,
       ts,
       plan_id,
       reason,
       created_at,
       trigger_id,
       planner_instance
  FROM setpoint_plan
 WHERE ts <= now()
   AND is_active = true
 ORDER BY parameter, created_at DESC, ts DESC;

-- Past rows that no longer win v_active_plan are stale active drift. Keep the
-- current row per parameter and leave future waypoints active for the schedule.
WITH ranked AS (
    SELECT ctid,
           row_number() OVER (
               PARTITION BY parameter
               ORDER BY created_at DESC, ts DESC
           ) AS rn
      FROM setpoint_plan
     WHERE is_active = true
       AND ts <= now()
)
UPDATE setpoint_plan sp
   SET is_active = false
  FROM ranked r
 WHERE sp.ctid = r.ctid
   AND r.rn > 1;

-- Add crop/manual/vision observations to the unified embedding corpus.
ALTER TABLE IF EXISTS verdify_embeddings
  DROP CONSTRAINT IF EXISTS verdify_embeddings_source_type_check;

ALTER TABLE IF EXISTS verdify_embeddings
  ADD CONSTRAINT verdify_embeddings_source_type_check
  CHECK (source_type IN ('lesson','plan','site_doc','playbook','observation'));

CREATE OR REPLACE FUNCTION fn_search_embeddings(
    query_embedding vector(3072),
    p_top_k         INTEGER DEFAULT 10,
    p_source_types  TEXT[]  DEFAULT ARRAY['lesson','plan','site_doc','playbook','observation']
)
RETURNS TABLE (
    source_type TEXT,
    source_id   TEXT,
    chunk_idx   INTEGER,
    content     TEXT,
    metadata    JSONB,
    distance    FLOAT
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.source_type, e.source_id, e.chunk_idx, e.content, e.metadata,
           (e.embedding <=> query_embedding)::float AS distance
      FROM verdify_embeddings e
      LEFT JOIN planner_lessons pl
        ON e.source_type = 'lesson'
       AND pl.id::text = e.source_id
     WHERE e.source_type = ANY(p_source_types)
       AND (
             e.source_type <> 'lesson'
             OR (pl.is_active = true AND pl.superseded_by IS NULL)
           )
     ORDER BY e.embedding <=> query_embedding
     LIMIT p_top_k;
END;
$$;

COMMENT ON FUNCTION fn_search_embeddings(vector, INTEGER, TEXT[]) IS
  'Top-K cosine-similarity retrieval over verdify_embeddings. Source types: '
  'lesson, plan, site_doc, playbook, observation.';

COMMIT;
