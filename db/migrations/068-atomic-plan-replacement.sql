-- 068-atomic-plan-replacement.sql
-- Replace per-param supersession with atomic full-plan replacement.
-- The planner will call fn_deactivate_future_plans() before writing a new plan.

-- Drop supersession trigger from parent and all chunks
DROP TRIGGER IF EXISTS trg_plan_supersede ON setpoint_plan;
DO $$
DECLARE r RECORD;
BEGIN
    FOR r IN SELECT inhrelid::regclass::text AS chunk
             FROM pg_inherits WHERE inhparent = 'setpoint_plan'::regclass
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_plan_supersede ON %s', r.chunk);
    END LOOP;
END $$;

DROP FUNCTION IF EXISTS deactivate_superseded_plans();

-- Atomic replacement: deactivate ALL future waypoints in one call
CREATE OR REPLACE FUNCTION fn_deactivate_future_plans()
RETURNS void AS $$
BEGIN
    UPDATE setpoint_plan SET is_active = false WHERE ts > now() AND is_active = true;
END;
$$ LANGUAGE plpgsql;
