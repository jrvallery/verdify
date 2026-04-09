-- 073-backfill-utility-cost.sql
-- One-time backfill: populate utility_cost from daily_summary monthly aggregates.

INSERT INTO utility_cost (month, category, amount_usd, kwh, notes)
SELECT date_trunc('month', date)::date,
       'electric',
       ROUND(SUM(COALESCE(cost_electric, 0))::numeric, 2),
       ROUND(SUM(COALESCE(kwh_estimated, 0))::numeric, 2),
       'Backfilled from daily_summary'
FROM daily_summary
WHERE cost_electric IS NOT NULL
GROUP BY 1
ON CONFLICT (month, category) DO UPDATE SET
    amount_usd = EXCLUDED.amount_usd,
    kwh        = EXCLUDED.kwh,
    updated_at = now();

INSERT INTO utility_cost (month, category, amount_usd, notes)
SELECT date_trunc('month', date)::date,
       'propane',
       ROUND(SUM(COALESCE(cost_gas, 0))::numeric, 2),
       'Backfilled from daily_summary'
FROM daily_summary
WHERE cost_gas IS NOT NULL
GROUP BY 1
ON CONFLICT (month, category) DO UPDATE SET
    amount_usd = EXCLUDED.amount_usd,
    updated_at = now();

INSERT INTO utility_cost (month, category, amount_usd, gallons, notes)
SELECT date_trunc('month', date)::date,
       'water',
       ROUND(SUM(COALESCE(cost_water, 0))::numeric, 2),
       ROUND(SUM(COALESCE(water_used_gal, 0))::numeric, 2),
       'Backfilled from daily_summary'
FROM daily_summary
WHERE cost_water IS NOT NULL
GROUP BY 1
ON CONFLICT (month, category) DO UPDATE SET
    amount_usd = EXCLUDED.amount_usd,
    gallons    = EXCLUDED.gallons,
    updated_at = now();
