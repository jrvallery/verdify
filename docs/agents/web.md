# Agent: `web`

The FastAPI crop catalog, every vault markdown writer, every page generator, and the Quartz static site that serves `verdify.ai`.

## Owns

- `api/main.py` + sibling modules — FastAPI endpoints (crop catalog, health, observations, zones, setpoint echo)
- `scripts/generate-*.py` — `generate-daily-plan.py`, `generate-forecast-page.py`, `generate-lessons-page.py`, etc.
- `scripts/vault-*.py` — `vault-daily-writer.py`, `vault-crop-writer.py`
- `site/` — Quartz content + build config
- `/mnt/iris/verdify-vault/` — Obsidian vault (source of site content; NOT in this git repo but owned by this agent's deploy pipeline)
- Systemd units: `verdify-api.service`, `verdify-forecast-page.*`, `verdify-site-poll.*`, `verdify-site-build.service`, `verdify-setpoint-server.service`

## Does not own

- Schemas the API returns or the frontmatter models (`verdify_schemas/api.py`, `vault.py` — coordinator)
- The DB the API reads (ingestor writes, coordinator migrates)
- The planner output that feeds daily plan pages (genai)

## Handshakes

| With agent | When | Protocol |
|---|---|---|
| `ingestor` | Needs a new DB column to render in a page | Ingestor adds the write path + coordinator adds migration; web consumes next cycle |
| `genai` | New plan section, new lesson category | Genai defines shape in `plan.py` / `lessons.py`; web renderer consumes through the schema |
| `coordinator` | Adding a response model or frontmatter schema | Coordinator merges `verdify_schemas/api.py` or `vault.py` change; web endpoint gets `response_model=` wiring after |

## Gates

- Vault writer changes must produce byte-for-byte identical frontmatter on existing files (`diff` against pre-regen file) — Obsidian dataview queries depend on key names and order.
- FastAPI endpoints must have `response_model=` declared (Sprint 22 pattern). OpenAPI `/docs` populates from these; regressions here mislead downstream consumers.
- Quartz build must succeed (`make site-build` or equivalent) before pushing to vault.

## Ask coordinator before

- Changing a vault frontmatter key (breaks Obsidian dataview silently)
- Adding an API endpoint (affects external consumers incl. Cloud Run api)
- Reworking the vault directory layout (site routing depends on it)
- Touching Quartz configuration that changes URL structure

## Recent arc (pre-agent-org)

- Sprint 20-era: Site relaunch, planning page, hydroponics page
- Sprint 22: 4 vault writers migrated to `verdify_schemas` models + yaml.safe_dump; 8 API endpoints gained `response_model=`

See `docs/backlog/web.md` for next work.
