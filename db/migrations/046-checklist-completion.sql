-- Migration 046: Add index for fast checklist lookups
ALTER TABLE daily_checklist_log ADD COLUMN IF NOT EXISTS completed_by TEXT;
CREATE INDEX IF NOT EXISTS idx_checklist_log_date_completed ON daily_checklist_log(date, completed_at);
