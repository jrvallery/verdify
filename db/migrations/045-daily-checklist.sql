-- Migration 045: Daily checklist tables + seed data + view (Task 3.11, E-GRO-02)

-- ============================================================
-- 1. daily_checklist_template
-- ============================================================

CREATE TABLE IF NOT EXISTS daily_checklist_template (
    id SERIAL PRIMARY KEY,
    task TEXT NOT NULL,
    frequency TEXT NOT NULL DEFAULT 'daily',
    zone TEXT,
    role TEXT DEFAULT 'grower',
    priority INT DEFAULT 2,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    notes TEXT,
    CONSTRAINT chk_frequency CHECK (frequency IN ('daily', 'weekly', 'biweekly', 'monthly')),
    CONSTRAINT chk_priority CHECK (priority BETWEEN 1 AND 3),
    CONSTRAINT chk_role CHECK (role IN ('grower', 'operator', 'admin'))
);

COMMENT ON TABLE daily_checklist_template IS 'Recurring greenhouse tasks. Priority: 1=critical, 2=normal, 3=nice-to-have.';

-- ============================================================
-- 2. daily_checklist_log
-- ============================================================

CREATE TABLE IF NOT EXISTS daily_checklist_log (
    id SERIAL PRIMARY KEY,
    template_id INT NOT NULL REFERENCES daily_checklist_template(id),
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    completed_at TIMESTAMPTZ,
    completed_by TEXT,
    notes TEXT,
    skipped BOOLEAN DEFAULT false,
    skip_reason TEXT,
    UNIQUE(template_id, date)
);

CREATE INDEX IF NOT EXISTS idx_checklist_log_date ON daily_checklist_log(date);

COMMENT ON TABLE daily_checklist_log IS 'Per-day completion log for checklist tasks. One entry per task per day.';

-- ============================================================
-- 3. Seed data
-- ============================================================

INSERT INTO daily_checklist_template (task, frequency, zone, role, priority, notes) VALUES
    ('Check seedling moisture', 'daily', 'east', 'grower', 1, 'East shelf seedlings — feel soil, water if dry to touch'),
    ('Inspect hydro reservoir level', 'daily', 'east', 'grower', 2, 'Top off if below fill line. Note water clarity.'),
    ('Check hydro pH/EC readings', 'daily', 'east', 'grower', 2, 'Target pH 5.8-6.2, EC 1.2-2.0. Log anomalies.'),
    ('Inspect for pests/disease', 'daily', NULL, 'grower', 2, 'All zones — check undersides of leaves, stems, soil surface.'),
    ('Water canna lilies if dry', 'weekly', 'south', 'grower', 2, 'South wall planters. Every 2-3 days in spring.'),
    ('Check mister nozzles for clogs', 'weekly', NULL, 'operator', 2, 'South + west walls. Run manual burst, visually inspect spray pattern.'),
    ('Inspect drip heads', 'weekly', NULL, 'operator', 2, 'South wall + center rail. Check for leaks, uneven flow.'),
    ('Clean hydro reservoir', 'biweekly', 'east', 'grower', 2, 'Drain, scrub, refill with fresh nutrient solution.'),
    ('Check grow light bulbs', 'monthly', NULL, 'operator', 3, 'Main overhead + grow shelf. Note any burned-out or dim bulbs.'),
    ('Fertilize starts', 'weekly', 'east', 'grower', 2, 'East shelf — dilute liquid fertilizer per recipe.')
ON CONFLICT DO NOTHING;

-- ============================================================
-- 4. v_daily_checklist view
-- ============================================================

CREATE OR REPLACE VIEW v_daily_checklist AS
WITH last_done AS (
    SELECT template_id, MAX(date) FILTER (WHERE completed_at IS NOT NULL) AS last_completed
    FROM daily_checklist_log
    GROUP BY template_id
)
SELECT
    t.id AS template_id,
    t.task,
    t.zone,
    t.priority,
    t.frequency,
    t.role,
    -- is_due_today: based on frequency and last completion date
    CASE t.frequency
        WHEN 'daily' THEN true
        WHEN 'weekly' THEN (ld.last_completed IS NULL OR CURRENT_DATE - ld.last_completed > 6)
        WHEN 'biweekly' THEN (ld.last_completed IS NULL OR CURRENT_DATE - ld.last_completed > 13)
        WHEN 'monthly' THEN (ld.last_completed IS NULL OR CURRENT_DATE - ld.last_completed > 29)
    END AS is_due_today,
    ld.last_completed,
    log.completed_at,
    log.completed_by,
    log.skipped,
    log.skip_reason,
    log.notes AS log_notes
FROM daily_checklist_template t
LEFT JOIN last_done ld ON ld.template_id = t.id
LEFT JOIN daily_checklist_log log ON log.template_id = t.id AND log.date = CURRENT_DATE
WHERE t.is_active = true
ORDER BY
    (log.completed_at IS NOT NULL) ASC,  -- incomplete first
    t.priority ASC,
    t.zone NULLS LAST;

COMMENT ON VIEW v_daily_checklist IS 'Today''s checklist: shows all active tasks, whether due today, completion status. Incomplete + due items sort first.';
