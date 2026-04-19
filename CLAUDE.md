# Verdify — Agent Working Guide

This repo is worked by several Claude agents in parallel plus a human coordinator (Jason). Every session that edits code here should read this file first.

## What Verdify is

An AI-driven climate controller for a single 367 sq ft greenhouse in Longmont, CO. **Production** — plants are alive, the ESP32 is in the loop every 5 s, the planner runs on real data. Keeping the greenhouse operational ("Track A") always outranks SaaS/cloud refactor progress ("Track B"). See `README.md` for the architecture one-pager.

## Agents

Five persistent agents, each owning one scope. Branches are prefixed by agent name; worktrees live at `/mnt/iris/verdify-worktrees/{agent}/`. Per-agent scope docs live in `docs/agents/`.

| Agent | Owns | Branch prefix | Scope doc |
|---|---|---|---|
| [`firmware`](docs/agents/firmware.md) | ESP32 C++ (`greenhouse_logic.h`), ESPHome YAML, firmware replay, OTA, sensor health | `firmware/*` | `docs/agents/firmware.md` |
| [`ingestor`](docs/agents/ingestor.md) | `ingestor/*.py`, setpoint dispatcher, HA/Shelly/Tempest sync, `alert_monitor`, daily snapshot | `ingestor/*` | `docs/agents/ingestor.md` |
| [`genai`](docs/agents/genai.md) | `iris_planner.py`, `mcp/server.py`, `templates/`, prompts, scorecard/lessons/plan-evaluation | `genai/*` | `docs/agents/genai.md` |
| [`web`](docs/agents/web.md) | `api/main.py`, `scripts/generate-*`, `scripts/vault-*`, Quartz `site/` | `web/*` | `docs/agents/web.md` |
| [`saas`](docs/agents/saas.md) | Cloud Run, Cloud SQL, GCE MQTT, Firebase Auth, future React app | `saas/*` | `docs/agents/saas.md` |
| [`coordinator`](docs/agents/coordinator.md) | Schemas, migrations, CI, infra, cross-cutting refactors, review + merge | `coordinator/*` or direct to main | `docs/agents/coordinator.md` |

**Find your scope doc and read it before touching files.** Scope docs name what's yours, what adjacent agents touch, and what to route through coordinator.

## Shared territory

No agent owns these. Changes here go through coordinator (Jason) — file a focused PR, don't edit autonomously:

- `verdify_schemas/` — cross-layer Pydantic contracts; touched by every agent
- `db/migrations/` — schema migrations; serialized, reviewed holistically
- `docker-compose.yml`, `systemd/`, `traefik/`, `mqtt/`, `.github/workflows/` — infra
- `CLAUDE.md` (this file), `README.md`, `docs/agents/**` — organizational docs
- `pyproject.toml` — tool config

Rule: if the file listed here is in your diff, pause and ask coordinator.

## How agents coordinate

1. **Schema changes land first.** If your work needs a new `verdify_schemas/` model or a field addition, land that in a schema-only PR (coordinator reviews). Next cycle, the consumer PR (yours) lands against the new schema.
2. **Migrations are serialized.** One migration PR at a time across the whole repo. Coordinator approves the sequence.
3. **When you need another agent's territory**, file a focused PR into their scope, don't reach across. Label it `requested-by: {your-agent}` in the PR body. The owning agent reviews on their next cycle.
4. **Drift guards are the wire protocol.** If `verdify_schemas/tests/test_drift_guards.py` passes, two agents can merge independently — the boundary is intact.
5. **Hand off by doc, not by DM.** Anything a future session of any agent needs to know goes into that agent's `docs/agents/{name}.md` or a memory file, not into chat.

## Branches & sprints

- Each agent has its own sprint counter. Example: `ingestor/sprint-5-...`, `firmware/sprint-7-...`, `saas/sprint-11-...`.
- The old dual-stream numbering retires. The prior operational sprints (17–23) are documented in each agent's scope doc where they overlap.
- Sprints land as **one commit per sprint** with a detailed multi-section message (see `e96f9ba`, `47f8154` for examples).

## Worktrees & memory

- Worktrees: `/mnt/iris/verdify-worktrees/{firmware,ingestor,genai,web,saas}/`. The `main` worktree at `/mnt/iris/verdify` is coordinator-only.
- Persistent agent memory: `~/.claude-agents/verdify-{agent}/projects/-mnt-iris-verdify-worktrees-{agent}/memory/`.
- User-level and feedback memories (about Jason, how he likes to work) are shared across all agent dirs — duplicate them at the start of each agent's life.

## Backlog

See `docs/BACKLOG.md` for the cycle index. Per-agent backlogs in `docs/backlog/{agent}.md`. Cross-cutting work (schemas, infra, Grafana, deps) in `docs/backlog/cross-cutting.md`.

## Checks before commit

- `make lint` (ruff) — required, no exceptions.
- `make test` — required; 1 pre-existing flaky timeout (`test_dew_point_risk_computes`) is tolerated, everything else must pass.
- `make firmware-check` — required for `firmware` agent only.
- For UI/site changes, verify render locally; type-checks and tests don't catch visual regressions.
