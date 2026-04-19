# Backlog: `web`

Owned by the [`web`](../agents/web.md) agent.

## In flight

None.

## Next up (candidates)

- [ ] **Scorecard endpoint + page.** `fn_planner_scorecard()` data isn't exposed via the public API or rendered on the site. Add `GET /api/v1/scorecard?date=` (with `response_model=`) and a Quartz page that renders the last 7 days. Coordinates with `genai`'s scorecard schema work.
- [ ] **Harvest + treatment UI in vault.** `Harvest` / `Treatment` rows now exist in DB (coordinator added schemas Sprint 22). No vault page renders them. Add `vault-harvest-writer.py` + `vault-treatment-writer.py` following the daily/crop writer pattern.
- [ ] **Vault image handling.** `ImageObservation` schema shipped Sprint 22 but no renderer shows images on crop pages. Add thumbnail gallery + latest-photo frontmatter.
- [ ] **API pagination + filtering.** `/api/v1/crops` returns everything; as crop count grows this won't scale. Add `?limit=`/`?offset=` + `?stage=` / `?zone=` filters with proper response model updates.

## Ideas (not yet committed)

- Public `/api/v1/status` telemetry endpoint (subset of ingestor's self-health) — for uptime monitoring integrations.
- Replace Quartz poll-and-rebuild with a webhook from ingestor when new data lands (kill the 10 s polling timer).

## Recent history

- Sprint 22: 4 vault writers migrated to `verdify_schemas.vault` models + `yaml.safe_dump`; 8 API endpoints gained `response_model=`.
- Sprint 20-era: hydroponics page relaunch after calibration; planner page; forecast page via Jinja from DB.
- Pre-Sprint 20: Quartz migration, inotify → polling timer swap, `/mnt/iris/verdify-vault` content move.

## Gates / reminders

- Vault writer changes must render byte-identical frontmatter against existing files (diff before commit). Obsidian dataview queries depend on key names + order.
- Every new API endpoint needs `response_model=` — OpenAPI `/docs` is a contract.
- Quartz build must succeed before pushing to vault; broken site builds don't auto-recover.
