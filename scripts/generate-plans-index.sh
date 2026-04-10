#!/bin/bash
# generate-plans-index.sh — Regenerate plans/index.md with summary stats table.
# Queries daily_summary + plan_journal for the last 14 days.
set -euo pipefail

INDEX="/srv/verdify/verdify-site/content/plans/index.md"
DB_CMD="docker exec verdify-timescaledb psql -U verdify -d verdify -t -A"
TODAY=$(date +%Y-%m-%d)

# Query last 14 days of stats
ROWS=$($DB_CMD -c "
  SELECT ds.date,
    (SELECT COUNT(*) FROM plan_journal pj
     WHERE pj.plan_id LIKE 'iris-' || to_char(ds.date, 'YYYYMMDD') || '%') AS plans,
    ROUND(COALESCE(ds.temp_min,0)::numeric,0) || '-' || ROUND(COALESCE(ds.temp_max,0)::numeric,0) AS temp_range,
    ROUND(COALESCE(ds.stress_hours_vpd_high,0)::numeric,1) AS vpd_stress,
    ROUND(COALESCE(ds.cost_total,0)::numeric,2) AS cost,
    COALESCE((SELECT LEFT(pj.experiment, 50) FROM plan_journal pj
      WHERE pj.plan_id LIKE 'iris-' || to_char(ds.date, 'YYYYMMDD') || '%'
      ORDER BY pj.created_at DESC LIMIT 1), '-') AS experiment,
    COALESCE((SELECT pj.outcome_score::text FROM plan_journal pj
      WHERE pj.plan_id LIKE 'iris-' || to_char(ds.date, 'YYYYMMDD') || '%'
      AND pj.outcome_score IS NOT NULL
      ORDER BY pj.created_at DESC LIMIT 1), '-') AS score
  FROM daily_summary ds
  WHERE ds.date >= (CURRENT_DATE - INTERVAL '14 days')
  ORDER BY ds.date DESC
")

# Preserve everything above '## Recent Plans', then replace the table
# Read existing header (everything before '## Recent Plans')
HEADER=""
if [[ -f "$INDEX" ]]; then
  HEADER=$(sed '/^## Recent Plans$/,$d' "$INDEX")
fi

# If no header found (new file), generate default
if [[ -z "$HEADER" ]]; then
  HEADER="---
title: Daily Plans
tags: [plans, greenhouse, ai]
date: ${TODAY}
---

# Daily Plans

Every day, Iris runs 3 planning cycles (6 AM, 12 PM, 6 PM MDT) to manage greenhouse setpoints.

---
"
else
  # Update the date in frontmatter
  HEADER=$(echo "$HEADER" | sed "s/^date: .*/date: ${TODAY}/")
  # Ensure trailing newline for spacing before ## Recent Plans
  HEADER=$(echo "$HEADER" | sed -e :a -e '/^\n*$/{$d;N;ba}')
fi

# Build output
{
  echo "$HEADER"
  echo ""
  echo "## Recent Plans"
  echo ""
  echo "| Date | Plans | Temp Range | VPD Stress | Cost | Experiment | Score |"
  echo "|------|-------|------------|------------|------|------------|-------|"

  while IFS='|' read -r d plans temp_range vpd cost experiment score; do
    [[ -z "$d" ]] && continue
    d="${d## }"; d="${d%% }"
    plans="${plans## }"; plans="${plans%% }"
    temp_range="${temp_range## }"; temp_range="${temp_range%% }"
    vpd="${vpd## }"; vpd="${vpd%% }"
    cost="${cost## }"; cost="${cost%% }"
    experiment="${experiment## }"; experiment="${experiment%% }"
    score="${score## }"; score="${score%% }"
    # Truncate experiment for table width
    experiment="${experiment:0:40}"
    echo "| [${d}](/plans/${d}) | ${plans} | ${temp_range}°F | ${vpd}h | \$${cost} | ${experiment} | ${score} |"
  done <<< "$ROWS"

  echo ""
  echo "---"
  echo ""
  echo "*Auto-generated from daily_summary + plan_journal data.*"
} > "$INDEX"

# Count rows for logging
COUNT=$(echo "$ROWS" | grep -c '[0-9]' || true)
echo "Plans index: ${COUNT} days"
