# Backlog — Cycle Index

Per-agent backlogs live in `docs/backlog/{agent}.md`. This file is the index + "who's on what this cycle."

## Current cycle (as of 2026-04-20)

| Agent | Sprint | Status | Detail |
|---|---|---|---|
| `coordinator` | v1.4 landed | **Cross-cutting landed this cycle**: contract `iris-planner-contract.md` v1.4 (`c88490a`), migration 093 applied to prod (`b624f5c` + live ALTER ~08:05 MDT), Pydantic v1.4 audit fields (`d822485`), schema CI unbreak (`ec9e1df`) | `docs/backlog/cross-cutting.md` |
| `ingestor` | `sprint-25` pending | Waits on genai Sub-scope B MCP PR. Post-24.7 staging already landed: `planner_routing.py` with v1.4 defaults + OPENCLAW_{OPUS,LOCAL}_{AGENT_ID,SESSION_KEY} env vars in `config.py`. Will consume `send_to_iris(instance=)` + `acknowledge_trigger` when genai ships | `docs/backlog/ingestor.md` |
| `genai` | `sprint-3-B` pending | Sub-scope A (prompt split `_PLANNER_CORE` + `_PLANNER_EXTENDED`) committed local on `genai/sprint-3-mcp-contract` (`8bbac41`). Sub-scope B blocked on Q5 FastMCP header smoke test — Iris has `53141f39` in her queue | `docs/backlog/genai.md` |
| `web` | — | Sprint-4 Grafana panels shipped via PR #16 (`9a9a05e`) this morning. No active sprint | `docs/backlog/web.md` |
| `firmware` | phase-1+ | Phase-0 shipped as sprint-10 (`8d2656d`) + sprints 7-9 overnight (`8c64030`, `dda9057`, and the 212b1c5 fog-window fix). No active sprint queued | `docs/backlog/firmware.md` |
| `saas` | `sprint-10` shipped | Rescope landed. Open task: apply migration 090 to prod DB; unblocked (coordinator has `docker exec psql` access) but awaits operator authorization | `docs/backlog/saas.md` |
| `iris-dev` | rollout in flight | OpenClaw config done (context fix + `iris-planner-local` profile). Session boot + smoke test queued post-sprint-25. /loop operating mode is permanent | — |

## Recent ships (2026-04-19 → 2026-04-20)

In chronological order:

- `4cc5df5` ingestor: 6 cfg_* readback sensors routed for firmware sprint-3
- `c085d82` firmware/sprint-3: per-zone VPD target readback sensors
- `3b1d93a` ingestor/sprint-24-alignment: firmware sprint-2 fairness wire-up + mister_state routing + drift allowlist (+merge `b25c09e`)
- `e1b11b0` firmware/sprint-4: leak_detected debounce against pipe bleed-down
- `9e3bca3` ingestor/sprint-24.6: planner observability F14 `plan_delivery_log` + escalation (+merge `2985e78`)
- `1594cb9` ingestor sprint-25 schema PR spec (+merge `95b730d`)
- `c2bb9ba` firmware/sprint-5: replay-corpus auto-refresh + fw_version bump per deploy
- `97c4ea1` firmware/sprint-6: midnight-transition investigation (no firmware issue)
- `212b1c5` firmware/sprint-8: fix R2-3 self-mutation + midnight-wrap fog window + SAFETY_HEAT symmetry
- `8c64030` firmware/sprint-7: per-zone cycle counters for misters and drips
- `0d7445b` genai/sprint-1 squash-merged via PR #14 (9-item sprint)
- **2026-04-19 PM onwards (dual-Iris rollout)**:
- `00231cf` docs: `iris-planner-contract.md` v1.3
- `c88490a` docs: `iris-planner-contract.md` v1.4 (reconcile with `plan_delivery_log`)
- `b624f5c` coordinator: migration 093 + ai.yaml `planner_routing` / `planner_sla`
- `dda9057` firmware/sprint-9: heat2 latch + validate_setpoints asserts + R2-3 comment + SAFETY_HEAT fan
- `51c4781` ingestor/sprint-24.7: alert-hardening — OBS-3 + flap fix + MIDNIGHT watcher + sprint-25 prep (+merge `91cc335`)
- **2026-04-20 overnight**:
- `98ff9a1` ingestor/sprint-24.8: midnight_posture milestone perpetually 24h in the future (+merge `5c95ad4`)
- `8d2656d` firmware/sprint-10 phase-0: both-fan relief + dt_ms clamp + tunable margins + sealed dehum override + day/night setpoints
- **2026-04-20 morning**:
- `d822485` coordinator: `verdify_schemas/` v1.4 audit fields + migration 093 applied to prod TimescaleDB
- `6c2f5b3` genai/sprint-2 (PR #15): planner_stale threshold 8h→14h + cadence note (+merge `9a27fe7`)
- `ec9e1df` coordinator: unbreak schema CI — asyncpg importorskip on physics-invariants test
- `9a9a05e` web/sprint-4 (PR #16): Grafana panels for planner instance metrics

## How to use this

- **Agents:** start of a session, read your own `docs/backlog/{agent}.md`. Pick the highest-priority item not blocked by a handshake.
- **Coordinator:** this file gets updated at sprint kickoff + sprint end. Treat it as the shipping status board. iris-dev refreshes during /loop idle cycles.
- **Cross-cutting work** (schemas, migrations, infra, deps) lives in `docs/backlog/cross-cutting.md` and is scheduled by coordinator.

## Sprint numbering

Per-agent counters. Past global sprints (17–22) map into individual agents' histories; see each agent's scope doc for the relevant prior work.

## Known open PRs (as of 2026-04-20 ~08:50 MDT)

- **#6** DRAFT — `copilot/fix-8a7fddcf-*` (voice-note ingestion; dormant Aug 2025, no recent activity)
- All contract-v1.4-era PRs (#15, #16) merged this morning. No agent PRs outstanding.

## Contract v1.4 rollout — current state

**Phase 1 (contract + schema) ✅ complete** (iris-dev + coordinator):
- Contract `docs/iris-planner-contract.md` v1.4 landed
- Migration 093 applied to prod TimescaleDB
- Pydantic v1.4 audit fields in `verdify_schemas/`
- Routing + SLA config in `config/ai.yaml`
- OpenClaw config: context window fix + `iris-planner-local` agent profile staged in `~/.openclaw/openclaw.json`

**Phase 2 (MCP + dispatch) 🟡 in flight** (genai):
- Sub-scope A (prompt split) ✅ committed local `8bbac41`
- Sub-scope B blocked on Q5 FastMCP header smoke test — awaiting Iris

**Phase 3 (ingestor consumption) 🔴 blocked** (ingestor):
- Sprint-25 omnibus waits on Phase 2 Sub-scope B
- Pre-staged: `planner_routing.py`, env vars, new trigger_id insert path

**Phase 4 (session boot + smoke test) 🔴 blocked** (iris-dev):
- Waits on Phases 2 + 3 merging so the contract is end-to-end live

**Phase 5 (cutover) 🔴 blocked** (ingestor):
- First-week HEARTBEAT `X-Heartbeat-Readonly: true` safety window
- TRANSITION + minor FORECAST/DEVIATION → `instance="local"`

The single un-blocker for everything downstream is Iris's Q5 answer.
