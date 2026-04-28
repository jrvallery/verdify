# Backlog: `web`

Owned by the [`web`](../agents/web.md) agent.

## In flight

None.

## Next up (candidates)

None. Web-owned website/API/Grafana backlog is currently clear.

## Ideas (not yet committed)

- Public `/api/v1/status` telemetry endpoint (subset of ingestor's self-health) — for uptime monitoring integrations.
- Replace Quartz poll-and-rebuild with a webhook from ingestor when new data lands (kill the 10 s polling timer).

## Recent history

- 2026-04-28 climate route consolidation: folded the public heating, cooling, humidity/VPD, water, lighting, and controller evidence into `/climate/`; archived the six old detailed climate reference pages under `/mnt/iris/verdify-vault/archive/website-climate-consolidation-2026-04-28`; repointed internal climate subsystem links to the consolidated hub and anchors.
- 2026-04-28 API + full Grafana closure: applied the scorecard endpoint and crop pagination changes to the live `/srv/verdify/api/main.py` runtime without dropping live-only setpoint params, restarted `verdify-api.service` by terminating the user-owned uvicorn process and letting systemd auto-restart it, and verified `/api/v1/scorecard` plus crop `limit`/`offset` live on port 8300. Cleaned all 55 live Grafana dashboards / 904 panels: added missing units, line-width defaults, and `spanNulls` defaults; moved daily-summary time filters to noon timestamps; refined the audit so intentional selected-period panels are not flagged as current-value mistakes; restarted Grafana; and completed a full serial PNG render with 904/904 OK, 0 style findings, 0 accuracy findings.
- 2026-04-28 site simplification sprint: added replacement-character detection to `make site-doctor`; fixed source corruption in active pages; simplified Quartz Explorer navigation to canonical public routes; rewrote `/`, `/evidence`, `/intelligence`, `/greenhouse`, `/greenhouse/growing`, and `/intelligence/broken`; archived stale hand-authored `/intelligence/lessons`; and added a redirect to generated `/greenhouse/lessons`.
- 2026-04-28 backlog closure sprint: made crop/zone renderers partial-update safe by default with explicit `--replace-page`; regenerated crop/zone auto-render blocks; converted generated forecast, daily plan, and plans-index tables to web components; added `/api/v1/scorecard?date=` and crop `limit`/`offset` filtering in `api/main.py`; added operation vault writers for harvest/treatment logs; added latest vision galleries to crop pages from `image_observations`; added `docs/site-image-manifest.json` and image-placement checks in `site-doctor`; refreshed `docs/grafana-panel-catalog.md` against 55 live dashboards / 904 panels.
- 2026-04-28 final cleanup: added `scripts/render-equipment-page.py` for the equipment catalog and relay-map blocks; switched generated block markers away from Quartz-visible Markdown comments to empty `data-auto-render` block elements; fixed restored stale crop/zone Grafana panel IDs; corrected west-zone replacement characters; and added explicit 180-day ranges to crop light-availability embeds.
- 2026-04-28 Quartz ownership alignment: vendored the full runtime Quartz source tree under `site/quartz` with docs, package lock, TypeScript config, and runtime config; moved global photo treatment CSS into repo-owned source; updated `scripts/rebuild-site.sh` so builds sync `site/` into `/srv/verdify/verdify-site` before `npx quartz build`.
- 2026-04-28 image audit and cleanup: added `docs/site-image-audit.md`; categorized the public photo library; replaced the corrupted Intelligence image and generic basil image; archived a broken contact-sheet asset, camera snapshot, weak atmospheric images, and the old `static/verdify-static-backup` tree outside the public website source.
- 2026-04-28 crop/zone generated-block cleanup: converted active crop and zone auto-render blocks from raw Markdown tables into `metric-grid`, `metric-card`, and `data-table` components; fixed pipe-truncated shelf position schemes; updated crop/zone renderers to emit web-friendly blocks going forward; added `site-doctor` guards for self-aliases, raw Mermaid blocks, and box-drawing ASCII diagrams.
- 2026-04-28 diagram/table cleanup: added reusable Quartz styles for flow steps, system maps, metric grids, timelines, score splits, floor plans, and data rows; replaced raw Mermaid/ASCII diagrams in architecture, planning, controller, hydroponics, structure, and zone pages; improved global Markdown table styling for remaining generated/reference tables; fixed nginx trailing-slash handling so slash-form leaf routes redirect to their slashless canonical URL while directory index routes still serve; removed the self-alias that caused `/greenhouse/hydroponics` to emit as a redirect stub.
- 2026-04-28 planning-quality evidence surface: added Grafana dashboard `site-evidence-planning-quality` with 16 rendered panels covering planner score, compliance, stress, forecast-vs-plan-vs-actual temperature/VPD, plan compliance, plan accuracy, cost/stress, water/mist response, raw scorecard rows, planning cycles, and extracted lessons. Added `/evidence/planning-quality` and linked it from the evidence index/dashboard directory.
- 2026-04-28 Grafana catalog refresh after planning-quality addition: regenerated `docs/grafana-panel-catalog.md`; live Grafana now inventories 55 dashboards / 904 panels with 0 render failures. Website source now embeds 19 dashboard UIDs through 259 Grafana iframes across 34 pages.
- 2026-04-28 website Grafana visual cleanup: added `docs/grafana-website-visual-audit.md`; rendered the 164 unique website iframe PNGs and fixed blank stat panels, `No data` panels caused by schema/time-range drift, forecast-bias time-series misuse, active-plan/controller string rendering, mister-effectiveness schema drift, daily-summary midnight timestamps, and the DIF panel's data-outside-range render.
- 2026-04-28 full Grafana audit: added `scripts/audit-grafana.py`; generated `docs/grafana-panel-catalog.md` with every live dashboard/panel, panel story, dependencies, freshness marker, render result, and style/accuracy notes. Rendered all 888 panels across 54 live dashboards; fixed `greenhouse-energy-cost` panel 924 by replacing a heavy duplicate 30-day climate/forecast join with time-range-aware hourly/latest-forecast queries. Final render result: 888/888 OK.
- 2026-04-27/28 Grafana closure: added live cooling equipment state/runtime panels (`site-climate-cooling` panel IDs 938/939), added `site-climate-water` soil-moisture-vs-VPD panel ID 218, updated `/climate/cooling` and `/climate/water`, removed provisioned `site-evidence-compliance`, restarted Grafana to clear the stale provisioning bind mount, and verified `make site-doctor` with 0 findings.
- 2026-04-27/28 cleanup: added `scripts/site-doctor.py` + `make site-doctor`; repaired all stale Grafana iframe panel IDs found by the audit; added generated-page source markers to daily plan and lessons generators plus current vault output. Gate now reports 0 findings.
- 2026-04-27/28 content-map pass: added `docs/site-content-map.md`; backfilled canonical `/plans/YYYY-MM-DD` pages; fixed daily-plan frontmatter/body fence output; added source-level internal link validation to `make site-doctor`.
- 2026-04-27/28 archive pass: moved legacy `/evidence/plans` source pages to `/mnt/iris/verdify-vault/archive/website-legacy-2026-04-28`; updated active evidence links to canonical `/plans`; exported unused live dashboard `site-evidence-compliance` to `/mnt/iris/verdify/grafana/dashboards/archive/2026-04-28`.
- 2026-04-27/28 semantic cleanup: added `scripts/site-doctor.py --semantic-report` for iframe/heading/panel-title review; removed duplicate or misleading embeds from cooling, water, evidence, and intelligence pages; documented remaining missing Grafana panels.
- 2026-04-27/28 site audit: mapped Quartz/vault/public pipeline, generated page sources, Grafana dashboard layers, and live embed drift. Findings added above.
- Sprint 22: 4 vault writers migrated to `verdify_schemas.vault` models + `yaml.safe_dump`; 8 API endpoints gained `response_model=`.
- Sprint 20-era: hydroponics page relaunch after calibration; planner page; forecast page via Jinja from DB.
- Pre-Sprint 20: Quartz migration, inotify → polling timer swap, `/mnt/iris/verdify-vault` content move.

## Gates / reminders

- Vault writer changes must render byte-identical frontmatter against existing files (diff before commit). Obsidian dataview queries depend on key names + order.
- Every new API endpoint needs `response_model=` — OpenAPI `/docs` is a contract.
- Quartz build must succeed before pushing to vault; broken site builds don't auto-recover.
- Do not edit `/srv/verdify/verdify-site/public`; edit `/mnt/iris/verdify-vault/website` or the generator scripts, then rebuild.
- Do not edit `/srv/verdify/verdify-site/quartz` for normal work. Edit repo-owned `site/quartz`; `scripts/rebuild-site.sh` syncs it into runtime.
- Do not add public ASCII diagrams or raw Mermaid blocks. Use the web-friendly classes in `site/quartz/styles/custom.scss`.
- Validate Grafana embeds against live dashboard panel IDs before declaring site/dashboard changes done.
- For copy/dashboard consistency reviews, generate a semantic inventory with `scripts/site-doctor.py --semantic-report /tmp/verdify-site-semantic.md`.
- For full dashboard/panel reviews, run `scripts/audit-grafana.py --render all --render-workers 1 --render-timeout 75 --render-retries 5 --json-report /tmp/verdify-grafana-audit.json --markdown-report docs/grafana-panel-catalog.md`. Use `--resume-json` to reuse prior successful renders; parallel full renders trigger Grafana 429s.
- For page-structure work, start from `docs/site-content-map.md` and keep `/plans` as the canonical daily-plan archive. Legacy `/evidence/plans` source is archived outside `website/`.
