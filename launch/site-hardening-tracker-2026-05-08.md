# Verdify Launch Site Hardening Tracker — 2026-05-08

This tracker covers the 38-item public launch hardening request. It is organized by route/path ownership so parallel agents can work without colliding.

## Build Sources

- Content source edited by humans/agents: `/mnt/iris/verdify-vault/website`
- Active Quartz/build source: `/mnt/iris/verdify-worktrees/web/site`
- Rebuild command: `/mnt/iris/verdify/scripts/rebuild-site.sh`
- Public smoke/check command: `make site-doctor`

## Workstreams

| ID | Owner | Paths | Requested items | Status |
| --- | --- | --- | --- | --- |
| A | Dirac `019e0875-adc6-7480-b938-407f7991852d` | `site/quartz*`, `/mnt/iris/verdify-worktrees/web/site/quartz*`, redirects, nav, footer, route smoke tests | 0.1, 1 URL/nav path alignment, 37 SEO/social, 38 route smoke | Complete; canonical `/start`, `/data`, `/reference` routes live |
| B | Galileo `019e043d-101b-7912-936b-02706c3ae6e4` | `/`, `/evidence/**`, public evidence snapshot/API/static proof | 0.3, 1, 2, 3, 4, 5, 25 | Complete; API snapshot deployed |
| C | Bernoulli `019e043d-10c3-7fa1-a78b-59a0457a0987` | `/intelligence/**`, model naming constants/prose | 0.4, 7, 8, 9, 10, 11, 12, 13, 15, 16, 31, 32 | Complete; canonical reference copies live |
| D | Copernicus `019e043d-1136-72f1-88df-0c4a483efe5b` | `scripts/generate-plans-index*`, daily plan pages, `/plans/**`, generated page lint cases | 6, 0.2, 14.4, 37.5, 38.1–38.4 | Complete; full archive regenerated |
| E | Ohm `019e043d-11a4-7732-9310-45d30f9da602` | `/greenhouse/crops/**`, `/greenhouse/zones/**`, crop source/generator consistency | 18, 19, 20, crop consistency lint | Complete; active-control count reconciled to 4 |
| F | Noether `019e043d-12a4-7132-8336-4000f3b212bc` | `/greenhouse/hydroponics`, `/greenhouse/soil`, `/greenhouse/lighting`, `/greenhouse/cameras`, `/greenhouse/equipment`, `/greenhouse/structure`, `/climate`, `/slack`, `/forecast`, `/about`, `/contact`, `/press` | 21–24, 26–36 | Complete; Press Kit and page copy live |

Note: the environment hit the agent thread limit after creating one new worker, so the remaining workstreams were assigned to the five existing workspace sub-agents rather than spawning seven more fresh threads.

## Route Alignment Target

The requested public URL structure is:

- Start: `/start/overview`, `/start/ai-greenhouse`, `/start/greenhouse`, `/start/climate`, `/start/evidence`, `/start/plans`, `/start/contact`
- Greenhouse: `/greenhouse/crops`, `/greenhouse/zones`, `/greenhouse/equipment`, `/greenhouse/hydroponics`, `/greenhouse/lighting`, `/greenhouse/soil`, `/greenhouse/cameras`, `/greenhouse/structure`
- Data: `/data/planning-loop`, `/data/slack-ops`, `/data/planning-quality`, `/data/baseline-vs-iris`, `/data/operations`, `/data/economics`, `/data/forecast`
- Reference: `/reference/intelligence`, `/reference/openclaw`, `/reference/inference`, `/reference/context-window`, `/reference/architecture`, `/reference/safety`, `/reference/data-model`, `/reference/build-notes`, `/reference/related-work`, `/reference/faq`, `/reference/lessons`, `/reference/about`, `/reference/press`

Compatibility redirects/aliases must keep current launch links working, especially `/`, `/greenhouse`, `/climate`, `/evidence/**`, `/intelligence/**`, `/plans`, `/slack`, `/forecast`, `/about`, `/contact`.

## Completion Criteria

- All public pages share the same nav/footer.
- Navigation labels and canonical URLs align by section.
- Current high-value old URLs redirect or alias to canonical routes.
- Static proof pages share a single current evidence snapshot source or explicitly label stale build-time values.
- Crop counts agree across crops, zones, planning loop, and generated docs.
- Press/media kit exists and links to contact with press topic.
- Site lint and smoke checks cover stale snapshots, raw wiki links, malformed image MIME, empty launch-facing sections, and daily-plan artifacts.
- `make site-doctor` passes after integration.
- Public smoke routes return 200 after rebuild.

## Main-Thread Progress

- 2026-05-08 10:40 MDT: Added this tracker and assigned route/path workstreams to Dirac, Galileo, Bernoulli, Copernicus, Ohm, and Noether.
- 2026-05-08 10:43 MDT: Expanded `/api/v1/public/evidence-snapshot` toward the canonical evidence object: top-level health, score, plan, cost, water, relay, crop, plan-count, climate-row, lesson-count, timezone, and controller-mode fields now coexist with the older nested `planning_quality` and `operations` objects for backward compatibility.
- 2026-05-08 10:45 MDT: Rebuilt/deployed `verdify-api`; public evidence snapshot now returns current top-level fields with `data_health_status=ok`, `active_control_crops=5`, `public_plan_records=171`, and physical `active_relays=[]` at verification time.
- 2026-05-08 10:46 MDT: Evidence/Home worker completed homepage, Evidence, Planning Quality, Operations, Baseline, and Economics copy/static snapshot pass. Remaining dependency: automating those static Markdown values from the canonical snapshot instead of hand-refreshing.
- 2026-05-08 11:00 MDT: Reconciled crop taxonomy: public API `active_control_crops` and home metrics now count non-center occupied active-control crop profiles from `v_position_current`, returning 4. The live DB still has a fifth active crop record for center-zone orchid, documented as observed/reference while center is offline.
- 2026-05-08 11:01 MDT: Promoted canonical route content copies under `/start`, `/data`, and `/reference`; retained legacy route content for compatibility during launch. Nav/footer now point at canonical route families.
- 2026-05-08 11:02 MDT: Regenerated all daily plan archive pages from 2026-03-24 through 2026-05-08 with the fixed daily-page renderer and refreshed `/data/plans`.
- 2026-05-08 11:03 MDT: Full site rebuild completed: Quartz parsed 131 Markdown files and emitted 279 pages. `verdify-site` nginx restarted successfully.
- 2026-05-08 11:04 MDT: Verification complete. `make lint` passed, TypeScript `npx tsc --noEmit` passed, `make site-doctor` passed with 0 errors and 79 warnings. Public route smoke returned 200 for `/start/overview`, `/start/evidence`, `/data/operations`, `/data/planning-quality`, `/data/plans`, `/data/forecast`, `/data/slack-ops`, `/reference/inference`, `/reference/planning-loop`, `/reference/known-limits`, `/reference/about`, `/reference/press`, `/press`, `/contact`, and `/`.
- 2026-05-08 11:32 MDT: Follow-up launch review cleanup completed. Public API `/api/v1/status` now uses the same active-control crop taxonomy as home metrics/evidence snapshot, returning `active_crops=4`. The launch pack now links canonical `/reference`, `/data`, and `/start` routes instead of legacy `/intelligence` and `/evidence` URLs. `scripts/lint_public_site.py` now fails unresolved wiki links while allowing valid Quartz-resolved Obsidian links; `make site-doctor` now passes with 0 errors and 0 warnings.
- 2026-05-08 11:44 MDT: Added `scripts/update-evidence-snapshots.py` to refresh Operations and Planning Quality static cards from `/api/v1/public/evidence-snapshot`; refreshed `/data/**` and legacy `/evidence/**` copies. Canonicalized the custom SiteNav/footer and high-value vault links to `/start`, `/data`, and `/reference`. Copied Slack screenshots into `/data/slack-ops/` so canonical Slack Ops image URLs resolve. Full rebuild completed with 131 Markdown files parsed, 279 pages emitted, and nginx restarted.
- 2026-05-08 11:46 MDT: Final snapshot refresh and rebuild completed. Final checks passed: `make lint`, Python compile for API/lint/snapshot updater, `scripts/lint_public_site.py --warnings-fail`, `make site-doctor` with 0 errors/0 warnings, public route smoke for canonical launch routes, API smoke for evidence snapshot, and Slack screenshot asset fetch.
- 2026-05-08 11:57 MDT: Fixed Grafana unit/axis-label regressions found in the website graph audit. The homepage `Greenhouse Power vs Solar Irradiance` panel now uses watts on the left axis and W/m² on the right axis instead of USD. Related solar/light panels, write-rate panels, PPFD/DLI panels, and water-flow panels had stale currency defaults removed or exact per-series units added. Live Grafana provisioning reloaded, render cache was cleared, and the corrected static PNG render was verified.

## Residual Non-Blocking Warnings

- Generated daily plan detail pages still live under `/plans/YYYY-MM-DD`; the canonical archive index lives at `/data/plans/` and links through to those preserved daily URLs. Moving daily detail pages under `/data/plans/YYYY-MM-DD` should be done in the plan generators, not by hand-copying output.
- Compatibility pages remain under legacy `/evidence/**`, `/intelligence/**`, `/forecast`, `/slack`, `/about`, and `/press` routes for launch-link safety. Primary nav and high-value internal links now use canonical `/start`, `/data`, and `/reference` routes.
