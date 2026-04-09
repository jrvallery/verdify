-- 054-planner-learning-loop.sql
-- A11: Planner Learning Loop — hypothesis tracking + persistent lessons
--
-- Closes the learning loop: each plan run validates the previous plan's
-- hypothesis, records lessons learned, and consults accumulated lessons.

-- plan_journal: one row per plan, tracks hypothesis → outcome
CREATE TABLE plan_journal (
    plan_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    -- Conditions at planning time
    conditions_summary TEXT,
    -- What was tried and why
    hypothesis TEXT,
    experiment TEXT,
    expected_outcome TEXT,
    params_changed TEXT[],
    -- Filled by NEXT plan run (validation)
    actual_outcome TEXT,
    outcome_score SMALLINT CHECK (outcome_score BETWEEN 1 AND 10),
    lesson_extracted TEXT,
    validated_at TIMESTAMPTZ
);

CREATE INDEX idx_journal_created ON plan_journal (created_at DESC);

-- planner_lessons: persistent lessons that accumulate across plans
CREATE TABLE planner_lessons (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now(),
    category TEXT NOT NULL,
    condition TEXT NOT NULL,
    lesson TEXT NOT NULL,
    confidence TEXT DEFAULT 'low' CHECK (confidence IN ('low', 'medium', 'high')),
    times_validated INT DEFAULT 1,
    last_validated TIMESTAMPTZ DEFAULT now(),
    source_plan_ids TEXT[],
    superseded_by INT REFERENCES planner_lessons(id),
    is_active BOOLEAN DEFAULT true
);

CREATE INDEX idx_lessons_active ON planner_lessons (is_active, category);
