# Verdify Website Simplification Proposal

Generated from a source audit on 2026-04-28. Active source: `/mnt/iris/verdify-vault/website`.

Update: the recommended first sprint was implemented on 2026-04-28. Home, Evidence, Intelligence, Greenhouse, Growing, and Known Limits were simplified; active replacement-character corruption was fixed; `/intelligence/lessons` was archived and redirected to generated `/greenhouse/lessons`; and Explorer navigation was reduced to canonical public routes.

## Current State

- 81 active Markdown pages.
- 37 daily plan archive pages under `/plans`.
- 18 generated/reference crop, zone, lesson, equipment, and forecast pages.
- 26 hand-authored narrative pages.
- 259 Grafana iframes across 34 pages.
- 19 embedded dashboard UIDs.
- `make site-doctor` passes: 0 broken links, 0 stale Grafana panel IDs, 0 generated-marker findings.

The technical wiring is now healthy. The content is not.

The site currently reads like an internal knowledge base that was made public. It has too many equally weighted pages, repeated explanations, inconsistent numbers, and several corrupted text artifacts. The strongest story is present, but it is scattered.

## Biggest Problems

### 1. Public navigation exposes too much internal structure

Quartz Explorer currently shows most folders and hand-authored pages. That makes the site feel like a vault browser instead of a deliberate public website.

The most confusing areas:

- `/climate` has seven public pages: overview plus controller, cooling, heating, humidity, lighting, water.
- `/greenhouse` has structure, growing, hydroponics, equipment, lessons, crop profiles, and zone profiles.
- `/intelligence` has overview, planning, architecture, data model, known issues, lessons, and firmware protocol.
- `/evidence` has operations, planning quality, economics, dashboards, and the daily plan archive.

Many of these are useful references, but not all should be primary navigation.

### 2. The same story is told too many times

The repeated core story appears on Home, Climate, Intelligence, Planning, Architecture, Evidence, and About:

- 367 sq ft greenhouse in Longmont at about 5,090 ft.
- ESP32 evaluates climate every 5 seconds.
- Iris/Claude plans around forecast and crop bands.
- The greenhouse scores plans and learns lessons.
- Colorado dry air plus solar gain creates the control problem.

Those are the right claims, but they should have one canonical version. Today, pages disagree in detail:

- `intelligence/index.md` says 30 context sections, while `intelligence/planning.md` says 14.
- `about.md` says 44 tables, 54 views, 54 dashboards; `intelligence/data.md` says 47 tables, 56 views; current Grafana audit says 55 dashboards.
- Home has fixed counters like 221K climate readings, 250 days, 115 plans, 75 lessons that will drift unless generated.
- Some pages use `AI`, some `Iris`, some `Claude Opus 4.6`, some `OpenClaw`; the public story needs one naming convention.

### 3. Corrupted Unicode exists in source

This is not just a browser rendering issue. The source contains U+FFFD replacement characters.

Pages with confirmed replacement-character corruption:

- `greenhouse/index.md`: 43 replacement characters.
- `greenhouse/growing.md`: 40.
- `intelligence/lessons.md`: 39.
- `greenhouse/zones/west.md`: 24.
- `intelligence/broken.md`: 9.

There are also valid but noisy glyphs in public content and generated pages: emoji status markers, box-drawing diagrams, special arrows, and symbols. These are acceptable in private notes, but they make the public site look inconsistent and are risky in generated archives.

### 4. Duplicate lessons pages conflict

There are two public lessons surfaces:

- `/greenhouse/lessons` is generated from `planner_lessons` and is the real source.
- `/intelligence/lessons` is hand-authored, stale, corrupted, and aliased to `greenhouse/lessons`.

The hand-authored page should be archived or converted into a short redirect/link page. It should not remain as an independent source.

### 5. “What this page should answer” copy makes the site feel unfinished

Several pages expose editorial scaffolding as public copy:

- `climate/index.md`
- `climate/humidity.md`
- `climate/lighting.md`
- `climate/water.md`
- `evidence/economics.md`
- `evidence/operations.md`

That phrasing is useful while drafting, but it weakens the finished public narrative.

### 6. Dashboard pages duplicate evidence pages

`/evidence/dashboards` partly repeats Operations, Economics, Climate, and Planning Quality. It is useful as an internal dashboard browser, but it should not be a first-class public story page.

### 7. Generated detail pages belong behind summaries

Crop profiles, zone profiles, daily plans, and generated lessons are valuable evidence, but they should not dominate navigation. They should be linked from summary pages and hidden from the left explorer unless the visitor deliberately enters that archive/reference path.

## Proposed Public Story

The public site should tell one clear story:

> Verdify is a self-improving, AI-enabled, automated solar-powered greenhouse. It senses, plans, acts, measures outcomes, and learns. The evidence is live.

This is the foundational narrative. It combines the unique dimensions into one storyline: Longmont's high-elevation dry climate, a solar-powered physical system, automation, AI planning, closed-loop measurement, and continuous improvement. Every page should use data to support some part of that story rather than introducing a separate framing.

Everything should ladder up to five questions:

1. What is this greenhouse and why is it hard?
2. What is the controller trying to hold?
3. How does the AI planner decide what to do?
4. Did the plan work?
5. What are the known limits and next improvements?

## Proposed Site Structure

### Primary navigation

Keep only these in top-level public navigation:

1. `/` — Home
2. `/greenhouse` — The Physical System
3. `/climate` — The Control Problem
4. `/intelligence` — The Planning Loop
5. `/evidence` — Live Proof
6. `/about` — Project Context

### Secondary/reference routes

Keep these routes, but hide them from the main explorer:

- `/plans` and `/plans/YYYY-MM-DD`
- `/forecast`
- `/greenhouse/crops/*`
- `/greenhouse/zones/*`
- `/greenhouse/lessons`
- `/greenhouse/equipment`
- `/intelligence/architecture`
- `/intelligence/data`
- `/intelligence/firmware-change-protocol`

### Archive or remove from active public content

Archive these after their useful content is folded into canonical pages:

- `/intelligence/lessons` — duplicate/stale/corrupted; use generated `/greenhouse/lessons`.
- `/intelligence/broken` — fold into a “Known Limits” section on `/evidence` or `/intelligence`.
- `/evidence/dashboards` — keep as hidden support route or archive after key dashboard links move into `/evidence`.
- Individual climate pages (`controller`, `cooling`, `heating`, `humidity`, `lighting`, `water`) — fold the best copy into `/climate`; keep as hidden technical references only if needed.
- `greenhouse/structure`, `greenhouse/growing`, `greenhouse/hydroponics` — fold concise versions into `/greenhouse`; keep details hidden or linked as references.

## Proposed Page Reductions

Target public navigation should shrink from roughly 26 narrative pages to 6 canonical pages plus generated/reference archives.

| Current area | Current public pages | Proposed public pages | Notes |
|---|---:|---:|---|
| Home/About | 2 | 2 | Rewrite Home around the core claim; About stays personal/project context. |
| Greenhouse | 7 hand/generated entry pages plus crops/zones | 1 primary | Fold structure, growing, hydroponics, equipment summary into `/greenhouse`; hide generated details. |
| Climate | 7 | 1 primary | Fold temperature, VPD, light, water, heating/cooling into one control-problem page. |
| Intelligence | 7 | 1 primary | Fold overview/planning/architecture/known limits into one planning-loop page; hide references. |
| Evidence | 5 plus plans archive | 1 primary plus `/plans` archive | Evidence becomes the dashboard-backed proof page; Planning Quality remains a major section or subpage. |

Recommended end state:

- 6 primary pages.
- 8-12 hidden/reference pages.
- Generated archives still available but not navigationally dominant.

## Canonical Page Plan

### `/`

Purpose: high-confidence first impression.

Keep:

- One real hero photo.
- One concise claim: real greenhouse, closed-loop AI planning, live evidence.
- Four proof tiles: climate, planning quality, operations, economics.
- Links to the five primary routes.

Remove:

- Duplicated explanations of crop bands, VPD, and economics.
- Fixed counters unless generated from live data.
- Overlong dashboard stack.

### `/greenhouse`

Purpose: explain the physical plant and why it is a good proving ground.

Fold in:

- Core facts from `greenhouse/index.md`.
- Best measured structure facts from `greenhouse/structure.md`.
- Crop/zone summary from `greenhouse/growing.md`.
- Hydroponics one-paragraph summary from `greenhouse/hydroponics.md`.
- Equipment summary from `greenhouse/equipment.md`.

Keep detailed crop and zone pages as generated references, linked from compact tables.

### `/climate`

Purpose: show the physical control problem.

Fold in:

- Temperature vs target band.
- VPD vs target band.
- Solar gain and altitude constraint.
- Heating, cooling, lighting, water as subsections, not separate primary pages.
- Known physical limit: shade cloth needed for hot days.

Use fewer panels. Prioritize:

- Temperature vs target band.
- VPD vs target band.
- Zone temperature/VPD comparison.
- Equipment state timeline.
- Daily cost/water/light rollup.

### `/intelligence`

Purpose: explain how decisions are made.

Fold in:

- Planning loop from `intelligence/planning.md`.
- Three-layer architecture from `intelligence/architecture.md`.
- Known limits from `intelligence/broken.md`, rewritten as concise operational constraints.
- Link to generated lessons and plan archive.

Use one consistent vocabulary:

- “Iris” for the planner.
- “ESP32 controller” for the real-time control loop.
- “Crop band” for horticultural targets.
- “Tunables” for planner outputs.
- “Scorecard” for outcome measurement.

### `/evidence`

Purpose: prove the claims with live data.

Make it the strongest data page, not a directory.

Sections:

- Operations now.
- Planning quality.
- Climate control proof.
- Economics.
- Archives: daily plans, generated lessons, dashboards.

This can absorb `/evidence/operations`, `/evidence/planning-quality`, and `/evidence/economics` as sections, or keep those three as hidden “open full view” routes if the page gets too heavy.

### `/about`

Purpose: personal/project background.

Keep it short and human. Remove drifting system metrics and product-roadmap assertions unless they are maintained from a source of truth.

## Navigation Changes

Update `site/quartz.layout.ts` Explorer filtering so public navigation only exposes canonical pages by default.

Hide:

- Date-named plan pages, already hidden.
- `greenhouse/crops/*`
- `greenhouse/zones/*`
- `greenhouse/lessons`
- `greenhouse/equipment`
- `forecast`
- `intelligence/architecture`
- `intelligence/data`
- `intelligence/firmware-change-protocol`
- `evidence/dashboards`

Consider replacing Explorer with a fixed nav component for the public site. The current folder explorer reinforces the “public vault” feel.

## Text Cleanup Rules

Apply these rules during rewrite:

- ASCII-first prose in hand-authored pages: no emoji, no corrupted arrows, no decorative glyphs.
- Use `F`, `kPa`, `W/m2`, `sq ft`, `BTU/hr` consistently unless Grafana units require symbols.
- Avoid “What this page should answer” headings in public pages.
- Avoid “proof layer” repetition; say what the data proves once, then show it.
- Use “Iris” only after defining it once as the AI planner.
- Do not name specific model versions in public copy unless they are generated/current.
- Keep fixed counts out of prose unless generated: dashboard count, table count, lesson count, plan count, sensor count.
- Every public claim should be traceable to either a live panel, a generated page, or a stable physical fact.

## Data/Graph Cleanup Rules

For each canonical page, limit embedded panels to the smallest set that supports the story:

- Home: 4-6 panels max.
- Greenhouse: 0-3 panels plus photos.
- Climate: 6-8 panels.
- Intelligence: 4-6 panels.
- Evidence: 10-16 panels, because this is the data-heavy proof page.

Move supporting dashboards behind “open full dashboard” links instead of embedding every panel in prose pages.

## Implementation Sequence

1. Fix source corruption and public glyph policy.
   - Replace U+FFFD characters in five affected pages.
   - Remove emoji/box drawing from hand-authored public pages.
   - Add a `site-doctor` warning for replacement characters.

2. Add navigation filtering.
   - Hide generated/archive/reference routes from Explorer.
   - Keep direct links working.

3. Rewrite Home.
   - One positioning claim.
   - One photo-led hero.
   - Four proof links.
   - Remove drifting counters or generate them.

4. Consolidate Greenhouse.
   - Fold structure/growing/hydroponics/equipment summaries into `/greenhouse`.
   - Hide or archive old hand-authored subpages after redirects/links are in place.

5. Consolidate Climate.
   - Rewrite `/climate` as the canonical physical control story.
   - Keep detailed climate pages hidden or archive if redundant.

6. Consolidate Intelligence.
   - Rewrite `/intelligence` around crop band -> Iris -> ESP32 -> scorecard -> lessons.
   - Archive `/intelligence/lessons`.
   - Fold `/intelligence/broken` into known limits.

7. Consolidate Evidence.
   - Decide whether Planning Quality remains its own canonical page or becomes a major section on `/evidence`.
   - Hide `/evidence/dashboards` from primary nav.

8. Validate.
   - `make site-doctor`
   - Visual pass on the five canonical pages.
   - Public curl checks after rebuild.

## Recommended First Sprint

Do not rewrite everything at once. First sprint should establish the new shape:

1. Add replacement-character detection to `site-doctor`.
2. Fix corrupted text in the five affected pages.
3. Hide generated/reference/archive routes from Explorer.
4. Rewrite `/` and `/evidence` only.
5. Archive `/intelligence/lessons`.

That gives the site an immediate quality lift without risking the whole content system.
