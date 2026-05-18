# Verdify Site Content Map

This is the working contract for `lab.verdify.ai` content. The content source tree is `/mnt/iris/verdify-vault/website`; the repo-owned Quartz source tree is `site/`; Quartz builds into `/srv/verdify/verdify-site/public`.

Current active source size after the 2026-05-16 refocus pass: 110 Markdown pages. Legacy `/greenhouse/lessons` and `/intelligence/lessons` are aliases for the generated `/reference/lessons` page.

## Editorial Principle

The site story is: Verdify is a public AI-assisted greenhouse control loop in Longmont's high-elevation dry climate. Every page should support the same narrative: crop profiles define targets, Iris writes bounded tactical plans, the ESP32 owns deterministic relay control every 5 seconds, telemetry judges outcomes, and public scorecards make failures and lessons inspectable. Avoid framing Verdify as off-grid, fully autonomous, or self-improving unless the page immediately grounds the claim in the validated lesson lifecycle.

## Route Families

| Route | Role | Source type | Primary data/source | Graph layer | Update cadence |
|---|---|---|---|---|---|
| `/` | Public narrative entry point | Hand-authored | Current positioning, live overview panels | `site-home` | Manual |
| `/start/about` | Project context | Hand-authored | Greenhouse/project description | None | Manual |
| `/start/ai-greenhouse` | Primary AI greenhouse story | Hand-authored | Iris/Hermes planning loop, safety split, proof path | `site-home`, `site-intelligence` | Manual copy, live graphs |
| `/start/climate` | Climate system overview | Hand-authored | Greenhouse physics + live climate panels | `site-climate` | Manual copy, live graphs |
| `/start/evidence` | Live proof overview | Hand-authored | Operations, planning quality, economics, generated archives | `site-evidence-operations`, `site-evidence-planning-quality`, `site-evidence-economics` | Manual copy, live graphs |
| `/start/resource-use` | Resource-use entry point | Hand-authored | Water, energy, lighting, and operating-cost proof | `site-climate-water`, `site-evidence-economics` | Manual copy, live graphs |
| `/start/contact` | Contact page | Hand-authored | Public inquiry form | None | Manual |
| `/data/operations` | Live operations view | Hand-authored | System health, active plan, alerts, controller state | `site-evidence-operations` | Manual copy, live graphs |
| `/data/economics` | Canonical cost proof | Hand-authored | Utility consumption and cost allocation | `site-evidence-economics` | Manual copy, live graphs |
| `/data/planning-quality` | Planner quality proof | Hand-authored | Planner score, compliance, lessons, forecast accuracy | `site-evidence-planning-quality` | Manual copy, live graphs |
| `/data/baseline-vs-iris` | Baseline comparison | Generated | `daily_summary`, `plan_journal`, `v_planner_performance` | None | Generated |
| `/data/plans` | Canonical daily plan archive | Generated index + generated day pages | `daily_summary`, `plan_journal`, setpoint context | None | Generated/backfilled |
| `/data/forecast` | Forecast page | Generated | `weather_forecast`, `fn_forecast_correction`, `forecast_deviation_log` | None | Every 30 minutes |
| `/greenhouse` | Physical greenhouse overview | Hand-authored | Structure, zones, equipment, crops | None | Manual |
| `/greenhouse/structure` | Physical shell reference | Hand-authored | Dimensions, glazing, light transmission | `site-greenhouse-zones`, `site-climate-lighting` | Manual copy, live graphs |
| `/greenhouse/equipment` | Equipment inventory | Partially generated | `v_equipment_relay_map`, `equipment` | `site-greenhouse-equipment` | Generated sections |
| `/greenhouse/growing` | Crop/growing overview | Hand-authored | Crop targets and stress context | `site-greenhouse-crops` | Manual copy, live graphs |
| `/greenhouse/hydroponics` | Hydroponic system reference | Hand-authored | NFT system sensors and chemistry | `greenhouse-hydroponics` | Manual copy, live graphs |
| `/greenhouse/lighting` | Lighting/DLI reference | Hand-authored | DLI, grow-light behavior, solar context | `site-climate-lighting` | Manual copy, live graphs |
| `/greenhouse/soil` | Soil/substrate reference | Hand-authored | Root-zone probes and crop-steering gaps | None | Manual |
| `/greenhouse/cameras` | Camera evidence reference | Hand-authored | Public-safe camera evidence and limits | None | Manual |
| `/greenhouse/crops/*` | Crop profiles | Hybrid: hand-authored narrative plus generated reference blocks | `crop_catalog`, crop profile views, current positions | `site-greenhouse-crops` | Generated blocks |
| `/greenhouse/zones/*` | Zone profiles | Hybrid: hand-authored narrative plus generated reference blocks, except `center.md` | `v_zone_full`, topology/position views | `site-greenhouse-zones`, crop panels | Generated blocks |
| `/reference/intelligence` | AI/planning overview | Hand-authored | Planning loop, live health panels | `site-intelligence` | Manual copy, live graphs |
| `/reference/planning-loop` | Planning loop deep dive | Hand-authored | Planner behavior, forecast accountability | `site-intelligence-planning` | Manual copy, live graphs |
| `/reference/ai-tunables` | AI tunable traceability reference | Generated | `tunable_registry`, MCP contracts, `entity_map`, firmware source, setpoint audit tables, plan rationales | None | Generated |
| `/reference/lessons` | Planner lesson library | Generated | `planner_lessons` | None | Generated |
| `/reference/data-model` | Data model reference | Hand-authored | Tables/views/functions and controller health | `site-intelligence-data` | Manual copy, live graphs |
| `/reference/architecture` | System architecture | Hand-authored | High-level component map | None | Manual |
| `/reference/safety` | Safety architecture | Hand-authored | ESP32/dispatcher/LLM control split | None | Manual |
| `/reference/known-limits` | Known issues | Hand-authored | Operational limitations and gaps | None | Manual |
| `/reference/firmware-change-protocol` | Firmware operating procedure | Hand-authored | Firmware change safety protocol | None | Manual |

## Source Rules

- `/plans` is the canonical public daily-plan route. `scripts/generate-daily-plan.py --backfill` must be able to regenerate every linked day page from DB state.
- Former `/evidence/plans` content is archived outside the active website tree at `/mnt/iris/verdify-vault/archive/website-legacy-2026-04-28/evidence/plans`. Do not restore it unless there is a deliberate redirect/history decision.
- Former `/greenhouse/lessons` and `/intelligence/lessons` narrative content is archived outside the active website tree at `/mnt/iris/verdify-vault/archive/website-simplification-2026-04-28/intelligence/lessons.md`. Use generated `/reference/lessons` as the source of truth; legacy routes remain aliases.
- Generated pages must carry an explicit source marker near the top. `make site-doctor` checks this for known generated routes.
- `make site-doctor` also flags Unicode replacement characters; these indicate source corruption, not just browser rendering issues.
- Hand-authored pages may embed live Grafana panels, but the prose must describe the live panel that is actually embedded. Use `scripts/site-doctor.py --semantic-report /tmp/verdify-site-semantic.md` before large copy passes.
- Public images live under `/mnt/iris/verdify-vault/website/static/photos`. Use `docs/site-image-audit.md` as the working image catalog. Do not publish old backups, camera snapshots, contact sheets, or generic plant photos as crop-specific proof.
- Do not use ASCII diagrams or raw Mermaid blocks on public pages. Use the repo-owned Quartz classes in `site/quartz/styles/custom.scss` instead: `flow-steps`, `system-map`, `metric-grid`, `timeline-row`, `score-split`, `floor-plan`, and `data-table`.
- Crop, zone, and equipment pages are hybrid pages. Their narrative sections are curated by hand, while explicit `data-auto-render` blocks are regenerated from DB-style source data. `scripts/render-crop-profiles.py`, `scripts/render-zone-pages.py`, and `scripts/render-equipment-page.py` update only marked blocks by default; use `--replace-page` only when the intent is to replace curated prose.
- Generated/reference blocks should render as `metric-grid`, `metric-card`, or `data-table` HTML components rather than raw Markdown tables. Forecast, daily plan, plans index, crop, and zone generators now emit these components directly.
- Crop pages include a generated `Latest Vision` block when `image_observations` has crop-linked camera analysis. The renderer copies selected snapshots into `/static/vision/` for public thumbnails.
- `docs/site-image-manifest.json` is the machine-readable public photo manifest. `make site-doctor` checks `/static/photos/` references against that manifest and fails on unapproved or out-of-place photo use.
- Do not edit `/srv/verdify/verdify-site/public`; it is build output.
- Do not edit `/srv/verdify/verdify-site/quartz` for normal CSS/component work; it is synced from repo-owned `site/quartz` during rebuild.
- Quartz emits most leaf pages as `route.html`, not `route/index.html`. `site/nginx.conf` must redirect slash-form leaf URLs such as `/greenhouse/zones/east/` to slashless `/greenhouse/zones/east`; serving `route.html` directly at the slash URL breaks Quartz's relative CSS/JS asset paths. Directory index routes such as `/greenhouse/` still serve `index.html`.

## Current Notes

- Cooling equipment proof is live on `site-climate-cooling` panel IDs `938` and `939`.
- Soil-moisture-vs-VPD proof is live on `site-climate-water` panel ID `218`.
- Public navigation is intentionally simplified to Home, AI Greenhouse, Climate, Evidence, Resource Use, Operations, Plans, About, and Contact. Generated/reference pages remain available by direct links but are hidden from the top-level nav unless they support a primary workflow.
- The 2026-04-28 simplification pass rewrote `/`, `/evidence`, `/intelligence`, `/greenhouse`, `/greenhouse/growing`, and `/intelligence/broken`; fixed replacement-character corruption in active source; and added a redirect at `/intelligence/lessons/`.
- The 2026-04-28 generated-block cleanup converted active crop, zone, and equipment auto-render blocks from Markdown tables into web components. It also fixed truncated position schemes caused by literal pipe characters in shelf notation and added `site-doctor` guards for self-aliases, raw Mermaid blocks, box-drawing ASCII diagrams, stale Grafana panel IDs, and image placement.
- The unused live Grafana dashboard `site-evidence-compliance` was exported to `/mnt/iris/verdify/grafana/dashboards/archive/2026-04-28/site-evidence-compliance.json`, removed from provisioning, and no longer appears in Grafana search after the 2026-04-27/28 restart.
- The site now has source-level internal link validation, but it intentionally treats `section/page` and `/section/page` as valid root routes because existing content uses both conventions.
