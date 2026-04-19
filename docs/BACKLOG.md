# Backlog — Cycle Index

Per-agent backlogs live in `docs/backlog/{agent}.md`. This file is the index + "who's on what this cycle."

## Current cycle (as of 2026-04-18)

| Agent | Sprint | Status | Detail |
|---|---|---|---|
| `ingestor` | `sprint-23` | **In review** — commit `47f8154` on `iris-dev/sprint-23-pydantic-gaps`, awaiting merge + live restart | `docs/backlog/ingestor.md` |
| `genai` | (bundled with sprint-23) | MCP harvest/treatment bug fix + `HarvestCreate`/`TreatmentCreate` envelopes shipped in the same commit | `docs/backlog/genai.md` |
| `web` | — | No active sprint. Sprint 22 vault migration shipped recently. | `docs/backlog/web.md` |
| `firmware` | — | No active sprint. Last shipped: Sprint 17 (sensor fault resilience + OTA rollback) | `docs/backlog/firmware.md` |
| `saas` | `sprint-10` pending | Next up after coordinator schedules | `docs/backlog/saas.md` |
| `coordinator` | — | Cross-cutting queue | `docs/backlog/cross-cutting.md` |

## How to use this

- **Agents:** start of a session, read your own `docs/backlog/{agent}.md`. Pick the highest-priority item not blocked by a handshake.
- **Coordinator:** this file gets updated at sprint kickoff + sprint end. Treat it as the shipping status board.
- **Cross-cutting work** (schemas, migrations, infra, deps) lives in `docs/backlog/cross-cutting.md` and is scheduled by coordinator.

## Sprint numbering

Per-agent counters. Past global sprints (17–22) map into individual agents' histories; see each agent's scope doc for the relevant prior work.
