# Backlog: `genai`

Owned by the [`genai`](../agents/genai.md) agent. Rewritten 2026-04-18 after a
full-scope audit. Items are prioritized; pull from the top.

## Audit summary (2026-04-18)

Three findings at HIGH severity:

1. **Tier 2 contradiction.** `templates/planner-core-params.md` lists
   `temp_high`/`temp_low`/`vpd_high`/`vpd_low` as mandatory-emit, but the
   ingestor dispatcher (`ingestor/tasks.py:1088`) silently drops these as
   band-driven. If Iris obeys the doc, 4 params per transition go to
   `/dev/null`.
2. **Tool-count mismatch.** `ingestor/iris_planner.py:33` claims "18 tools"
   and names 16. `mcp/server.py` defines 17 — `plan_run` exists, is live,
   unbriefed.
3. **`skills/greenhouse-planner.md` is unversioned.** Prompt tells Iris to
   read it; file lives at `/mnt/jason/agents/iris/skills/…`, not in-repo.
   No CI drift guard.

Full findings preserved in genai agent memory (`project_genai_audit_2026_04_18.md`).

## In flight

- Sprint 23 MCP `HarvestCreate`/`TreatmentCreate` envelope — already merged
  into an ingestor sprint commit (`47f8154`). Once the parent merges to
  main, genai's MCP boundary is fully typed.

## Tracked list

| # | Item | Type | Blocks | Effort | Status |
|---|---|---|---|---|---|
| G1 | Rewrite `templates/planner-core-params.md` to match dispatcher reality — drop Tier 2 band params from mandatory-emit, clarify band comes from crop profile + `bias_*`/`hysteresis` tuning | Doc | — | XS | **done** (600b7b9) |
| G2 | Reconcile MCP tool inventory in `iris_planner.py` `_STANDING_DIRECTIVES`: add `plan_run` with usage note (or remove the tool), fix the "18 tools" count | Doc + maybe code | — | XS | **done** (600b7b9) |
| G3 | Ship typed projection for `fn_planner_scorecard()` — 25 explicit fields; validate in MCP `scorecard` tool response. Landed as `ScorecardResponse` upgrade in `verdify_schemas/mcp_responses.py` | Schema + MCP | unblocks `web` scorecard endpoint | M | **done** (6df34a6) |
| G4 | Vendor `skills/greenhouse-planner.md` into the repo (`docs/planner/greenhouse-playbook.md`); add a startup assertion in `iris_planner.py` that the file exists | Code + docs | — | S | pending |
| G5 | Delete dead templates (`planner-prompt.j2`, `planner-prompt.md`), keep or relocate `planner-reference.md`, prune `config/ai.yaml` `templates:` + `schedules.planner` stanzas to match live code | Cleanup | — | S | pending |
| G5b | Either add `make planner-dry` target to Makefile or drop it from `docs/agents/genai.md` gate list (doc cites it but target doesn't exist) | Cleanup | — | XS | pending |
| G6 | Split planner prompt into immutable rubric (cacheable) + per-cycle context (non-cacheable). Measure cache-hit rate after | Prompt refactor | cost | L | pending |
| G7 | Close the hypothesis loop: inject prior plan's `hypothesis_structured` + `actual_outcome` into the next SUNRISE prompt as a "what did yesterday predict vs deliver" block | Prompt + MCP read path | — | M | pending |
| G8 | Lessons state machine: `LessonState` literal (`proposed`/`validated`/`superseded`/`retired`), transition guards, `lessons_manage` `supersede(old_id, new_id)` action | Schema + MCP | — | M | pending |
| G9 | Multi-model eval: shadow Gemini 2.5 Pro call on N% of cycles; store both plans + outcome; publish weekly comparison page | Infra + prompt | coordinator sign-off | L | pending |
| G10 | Harden `scripts/gather-plan-context.sh`: aggregate per-section exit codes, emit a "context completeness" header Iris can read and flag | Script | — | M | pending |
| G11 | Rename `scripts/smoke-sprint20.py` → `smoke-feedback-loop.py`; adopt purpose-named smoke scripts going forward | Cleanup | — | XS | pending |
| G12 | Either populate or drop `plan_journal.conditions_summary` (propose migration to coordinator) | Coordinator handshake | — | S | pending |
| G13 | Scorecard "why did we fail": when `planner_score < 80`, compute top-2 contributing stress windows + include in next plan context | Prompt + MCP | unblocked by G3 | M | pending |
| G14 | One-line clarification in `docs/agents/genai.md`: vault-writer scripts (`generate-*`) are `web` scope; genai owns the data models they consume | Doc | — | XS | **done** (600b7b9) |
| G15 | **Infra drift**: `db/migrations/076-078` and `db/schema.sql` are stale vs live `fn_planner_scorecard()` (live emits 25 metrics incl. temp/vpd_compliance_pct, kwh/therms/water_gal/mister_water_gal, cost_electric/gas/water; migrations don't). Route to coordinator for a resync migration | Coordinator handshake | — | S | pending |

## Ideas (not committed)

- MCP `replan(reason: str)` tool — let Iris explicitly request a replan from
  within the conversation, short-circuiting the event-driven trigger.

## Gates / reminders

- `make lint` (ruff), `make test` — required, no exceptions.
- `make planner-dry` — before prompt ships.
- `scripts/smoke-sprint20.py` (post-G11: `smoke-feedback-loop.py`) —
  end-to-end against live stack.
- Cost sanity — coordinator reviews if avg plan-cycle cost inflates >20%.
- Model swaps (Claude ↔ Gemini, version bumps) — require coordinator sign-off.

## Handshake state

| With | Waiting on | Blocking them on |
|---|---|---|
| `web` | — | G3 `PlannerScorecard` (their scorecard endpoint is blocked) |
| `coordinator` | — | G12 migration, G9 model-swap review |
| `ingestor` | Sprint 23 bundle merge to main | — |
| `firmware` | — | — |

## Recent arc

- Sprint 20 (`f3b0bc6`): Unified plan schema + feedback loop + manifestation.
- Sprint 21 (`76a8731`): Full-stack Pydantic coverage — DB ↔ API ↔ MCP ↔ vault ↔ external.
- Sprint 22 (`e96f9ba`): API `response_model=`, vault migration, CI drift guards, ERD.
- Sprint 23 (`47f8154`): Pydantic rollout gaps — ingestor writes, Open-Meteo, MCP harvest/treatment fix.
