# Backlog — Cycle Index

Per-agent backlogs live in `docs/backlog/{agent}.md`. This file is the index + "who's on what this cycle."

## Current cycle (as of 2026-04-18)

| Agent | Sprint | Status | Detail |
|---|---|---|---|
| `ingestor` | `sprint-23` | **In review** — commit `47f8154` on `iris-dev/sprint-23-pydantic-gaps`, awaiting merge + live restart | `docs/backlog/ingestor.md` |
| `genai` | (bundled with sprint-23) | MCP harvest/treatment bug fix + `HarvestCreate`/`TreatmentCreate` envelopes shipped in the same commit | `docs/backlog/genai.md` |
| `web` | **Grafana normalized** | Website cleanup, SEO/content-structure refactor, mobile-safe Grafana embed hardening, self-hosted analytics, live API scorecard/pagination rollout, planner compliance/stress split, and the full Grafana normalization pass are complete. The 2026-04-30 dashboard pass normalized units, colors, labels, stale SQL, render automation, and website embed mismatches. Final live audit: 56 dashboards / 912 panels, 912/912 rendered OK, 0 style findings, 0 accuracy findings. Current web gates: `make lint`, `make site-doctor`, and `tests/test_06_website.py` clean; repo-level `make test` is blocked by coordinator-owned schema drift noted in `docs/backlog/web.md`. | `docs/backlog/web.md` |
| `firmware` | — | No active sprint. Last shipped: Sprint 17 (sensor fault resilience + OTA rollback) | `docs/backlog/firmware.md` |
| `saas` | `sprint-10` pending | Next up after coordinator schedules | `docs/backlog/saas.md` |
| `coordinator` | — | Cross-cutting queue | `docs/backlog/cross-cutting.md` |

## How to use this

- **Agents:** start of a session, read your own `docs/backlog/{agent}.md`. Pick the highest-priority item not blocked by a handshake.
- **Coordinator:** this file gets updated at sprint kickoff + sprint end. Treat it as the shipping status board.
- **Cross-cutting work** (schemas, migrations, infra, deps) lives in `docs/backlog/cross-cutting.md` and is scheduled by coordinator.

## Current findings to schedule

- **Web:** Site simplification pass reduced the public entry path, fixed corrupted text, and consolidated detailed Climate subpages into `/climate`. Remaining editorial cleanup is now limited to hiding/archive review for any redundant reference routes that are still intentionally public.
- **Web:** Image cleanup removed broken/public backup assets and documented current photo fit. The manual image catalog now has a machine-readable manifest checked by `site-doctor`; crop-specific photos for basil/cucumbers/tomatoes remain a content acquisition issue, not a rendering blocker.
- **Web:** Raw ASCII/Mermaid diagrams were removed from hand-authored public pages. Forecast, daily-plan, plans-index, crop, and zone generated outputs now use web components instead of generated Markdown tables.
- **Web:** Analytics are now self-hosted. Umami tracks browser-side visitor/page/referrer/device metrics, while GoAccess reads Traefik access logs for crawler, request, status-code, and non-JavaScript traffic. Operational details live in `docs/analytics.md`.
- **Web:** SEO structure now treats `/ai-greenhouse`, `/greenhouse`, `/climate`, `/intelligence`, `/evidence`, and `/plans` as the main public information architecture. Tag pages and individual generated daily plans are intentionally `noindex`; `/plans` remains the indexable archive.
- **Web:** Grafana normalization implementation completed on 2026-04-30 across 56 live dashboards / 912 panels plus website embeds and sensor/catalog sources. VPD/DLI/stress/runtime units, entity colors, stale SQL, and website embed mismatches are normalized and deployed. Follow-up: add an automated `make grafana-normalization-audit` gate and formalize a sensor/dashboard metadata catalog.

## Sprint numbering

Per-agent counters. Past global sprints (17–22) map into individual agents' histories; see each agent's scope doc for the relevant prior work.
