# Grafana Website Visual Audit

Generated from the 2026-04-28 website-facing Grafana cleanup.

## Scope

- Website source: `/mnt/iris/verdify-vault/website`
- Unique website Grafana embeds reviewed: 164
- Total website Grafana iframe embeds: 243
- Live dashboards referenced by website embeds: 18
- Full live dashboard catalog: `docs/grafana-panel-catalog.md`

This audit is intentionally stricter than `scripts/audit-grafana.py`. The catalog proves that Grafana returned PNGs, but a PNG can still be blank, show `No data`, show `Data is missing a time field`, or plot data outside the visible time range. The visual pass rendered contact sheets from the exact website iframe URLs and inspected the actual images.

## Cleanup Plan

1. Render every unique website iframe as a PNG using the exact iframe time range.
2. Classify failures into:
   - blank/tiny stat panels,
   - true `No data` panels,
   - table/string panels rendered with the wrong panel type,
   - time-series panels with data outside the visible range,
   - SQL/schema drift.
3. Fix root causes in the site-facing dashboard JSON and, where the story needs a wider window, in the website iframe URL.
4. Restart Grafana so provisioned dashboards match the JSON source.
5. Re-render the affected panels and then re-render all unique website embeds.
6. Re-run `site-doctor`, lint, tests, and site rebuild before declaring the website clean.

## Fixes Applied

- Date-backed daily panels now render daily rows at midday instead of midnight UTC, preventing yesterday's `daily_summary` row from falling outside Grafana's default last-24h view.
- Daily-summary stat panels now coalesce empty sums/averages to zero where appropriate.
- Monthly and long-history panels now use explicit iframe ranges such as `now-180d`.
- Daily trend panels that need history now use explicit iframe ranges such as `now-30d`.
- Plan-compliance panels now query the live `v_plan_compliance` schema correctly: `plan_achieved` and `overshoot`.
- The evidence daily cost panel now uses `cost_gas` and `cost_water`, matching the current `daily_summary` schema.
- Mister-effectiveness panels now query `v_mister_effectiveness.equipment` and render categorical bars by `Zone`.
- Forecast-bias panels are stats instead of time series because `fn_forecast_correction()` returns an aggregate row, not a timestamped series.
- String status panels now use a renderable form:
  - controller state is a mapped stat,
  - active plan is a table,
  - last reset is a table.
- The DIF panel now timestamps daily rows at midday and the website iframe requests `now-14d`, so it no longer renders as data outside the visible range.

## Post-Fix Result

- Full post-fix website visual render: 164/164 unique embedded PNGs returned HTTP 200.
- No post-fix PNGs were in the tiny/blank failure cluster that identified the original broken stat panels.
- Targeted visual fixes were re-rendered and inspected after each patch batch.
- Remaining `No data`-like output should be treated as a content/story choice only if it is intentionally explaining absence; website-facing operational panels should prefer zero, a table row, or a wider explicit time range.

## Repeatable Commands

The ad hoc visual artifacts were written under `/tmp/verdify-site-postfix-panels/` during this audit. For future cleanup, repeat the same pattern:

1. Extract unique iframe refs from `/mnt/iris/verdify-vault/website`.
2. Render each ref through `https://graphs.verdify.ai/render/d-solo/{uid}/?...`.
3. Use ImageMagick `montage` contact sheets for human review.
4. Treat HTTP 200 as necessary but not sufficient.

`make site-doctor` still remains the structural gate for stale `panelId` references, missing images, generated-page markers, links, build output, and nginx bind mount health.
