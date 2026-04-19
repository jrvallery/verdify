-- 090-saas-greenhouse-id-gaps.sql — saas agent Sprint 10 Phase 2
--
-- Plugs the multi-tenant gap left by 075: seven operations tables never got
-- greenhouse_id. Multi-tenant queries on harvests/treatments/irrigation/etc
-- silently bleed across tenants without this. Matches the 075 pattern:
-- DEFAULT 'vallery' REFERENCES greenhouses(id) so existing rows backfill
-- automatically.
--
-- Tables addressed:
--   harvests              (db/init/01-schema.sql:313, created 006)
--   treatments            (01-schema.sql:285, created 006)
--   irrigation_log        (created 032)
--   irrigation_schedule   (created 032)
--   lab_results           (01-schema.sql:429, created 012)
--   maintenance_log       (01-schema.sql:386)
--   consumables_log       (inventory table)
--
-- Indexes only on the time-series-like tables (harvests, treatments,
-- irrigation_log). irrigation_schedule / lab_results / maintenance_log /
-- consumables_log are low-cardinality — the greenhouse_id filter is cheap
-- without a dedicated index.
--
-- After this lands, the matching verdify_schemas models (Treatment, Harvest,
-- IrrigationLog, IrrigationSchedule, LabResult, MaintenanceLog,
-- ConsumablesLog) declare greenhouse_id as well. The bi-directional
-- drift-guard extension then prevents this class of gap from recurring.

BEGIN;

ALTER TABLE harvests            ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE treatments          ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE irrigation_log      ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE irrigation_schedule ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE lab_results         ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE maintenance_log     ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);
ALTER TABLE consumables_log     ADD COLUMN IF NOT EXISTS greenhouse_id TEXT DEFAULT 'vallery' REFERENCES greenhouses(id);

CREATE INDEX IF NOT EXISTS idx_harvests_ghid       ON harvests       (greenhouse_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_treatments_ghid     ON treatments     (greenhouse_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_irrigation_log_ghid ON irrigation_log (greenhouse_id, ts DESC);

COMMIT;
