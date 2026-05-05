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

**Launch narrative + lesson credibility support** (coordinated through [`docs/backlog/launch.md`](launch.md)).

- [x] **G-L0.3 Lesson canonicalization semantics.** Implemented in `scripts/generate-lessons-page.py`: normalized signatures collapse near-duplicate machine lessons into canonical families with validation counts and raw visibility behind a labeled details section.
- [x] **G-L0.4 Daily-plan story support.** Implemented in `scripts/generate-daily-plan.py`: default reading path leads with outcome/score/hypothesis/rationale and changed parameters, while raw secondary parameters stay behind `<details>`.
- [x] **G-L1.7 Launch response pack.** Added `docs/launch/launch-response-pack.md` with concise technical answers for HN/Reddit: why not PID, LLM not in real-time loop, ESP32 safety ownership, VPD physics, shade-cloth limits, peer comparisons, and self-correcting language.
- [x] **G-L1.13 FAQ support.** Added `/intelligence/faq` with answers for direct LLM control, PID, RL, self-correcting, VPD, physics limits, yield claims, solar wording, rebuildability, and peer comparisons.
- [ ] **G-L2.1 Weekly proof cadence.** Define the weekly "Verdify this week" planner summary inputs: weather faced, planner score, stress windows, lessons graduated, failures, repairs.
- [ ] **G-L2.6 Counterfactual replay roadmap.** Define planner-facing requirements for replaying recent telemetry with alternate tunables before any RL/simulator path.
- [ ] **G-L2.7 Daily lifecycle artifact.** Help web publish one complete forecast -> plan -> tunables -> telemetry -> score -> lesson example with planner-side annotations.

Sprint 23 MCP `HarvestCreate`/`TreatmentCreate` envelope is merged into main; genai's MCP boundary is typed.

**Planner loop hardening + local-first Iris** (2026-05-03 trace; coordinator-requested).

Target state: the existing OpenClaw `iris-planner` agent performs greenhouse
planning and plan evaluation against local Gemma4 on cortext. Routine and
required planning stays local by default; any cloud peer is an explicit operator
escalation path, not the normal planning route. The ESP32 remains the
safety-critical controller.

- [x] **G-P0.1 Local Gemma4 target contract.** Planner docs, routing comments, dry-run expectations, and live OpenClaw config now treat `iris-planner` as local Gemma4 on cortext. Live `plan_delivery_log.session_key` rows use trigger-scoped `agent:iris-planner:main:trigger:<uuid>` sessions and the OpenClaw profile points at `vllm/gemma4-26b` with no fallback.
- [ ] **G-P0.2 Prompt terminology cleanup.** Replace stale `opus/local` planner language with `local_gemma4` plus an explicit `cloud_escalation` override. Keep historical labels readable in DB queries, but make new prompts and operator docs local-first.
- [ ] **G-P0.3 Full-context planner pack.** Rework `gather-plan-context.sh` output into a Gemma4-sized context pack with: current climate/equipment, 24h hourly history, 7d score trend, prior plan outcomes, current/future active plan, next 48-72h forecast, forecast accuracy/deviation summaries, recent setpoint confirmations, recent clamps/range rejects, open alerts, crops/positions, water/energy constraints, and context-completeness flags.
- [ ] **G-P0.4 Distilled site + lessons memory.** Generate a compact planner digest from public/site context and operational docs: safety architecture, baseline-vs-Iris lessons, response-pack claims, greenhouse physical constraints, validated planner lessons, anti-patterns, and current launch story. Feed this as stable memory instead of pasting raw website pages into every prompt.
- [x] **G-P0.5 Explicit tuning rubric.** `_PLANNER_CORE` / local Gemma directives now state the planning approach: use assembled context first, diagnose dominant stress, tune Tier 1 tactical knobs only, respect registry min/max, prefer `set_plan` for solar/fixed-boundary postures, use `set_tunable` only for immediate corrections, and reserve `acknowledge_trigger` for true no-op or validation cycles.
- [x] **G-P0.6 MCP `plan_run` audit parity.** Manual/ad-hoc `plan_run` now creates a MANUAL trigger row, sends local-first through `send_to_iris`, returns audit fields, and resolves through the same `plan_delivery_log` correlation path.
- [x] **G-P0.7 Strict registry validation at MCP boundary.** `PlanTransition` / `set_plan` and `set_tunable` now reject values outside `tunable_registry` min/max before writing `setpoint_plan`. Errors include offending parameter, requested value, registry range, and nearest safe value so Iris can self-correct.
- [x] **G-P0.8 Local planner smoke.** Live smoke sent MANUAL/FORECAST/DEVIATION/TRANSITION/SUNRISE/SUNSET validation triggers to local Gemma4, verified acknowledgements with matching `trigger_id`, rejected an out-of-range `vpd_hysteresis=0.6`, restored a valid tactical nudge through dispatcher readback, and audited active/future plan rows with zero registry violations.
- [ ] **G-P1.1 Post-plan self-critique.** After each full plan, have Iris record a short structured rationale: forecast assumptions, expected stress windows, tunables intentionally changed, tunables intentionally left alone, and what evidence would falsify the plan.

## Tracked list

| # | Item | Type | Blocks | Effort | Status |
|---|---|---|---|---|---|
| G1 | Rewrite `templates/planner-core-params.md` to match dispatcher reality — drop Tier 2 band params from mandatory-emit, clarify band comes from crop profile + `bias_*`/`hysteresis` tuning | Doc | — | XS | **done** (600b7b9) |
| G2 | Reconcile MCP tool inventory in `iris_planner.py` `_STANDING_DIRECTIVES`: add `plan_run` with usage note (or remove the tool), fix the "18 tools" count | Doc + maybe code | — | XS | **done** (600b7b9) |
| G3 | Ship typed projection for `fn_planner_scorecard()` — 25 explicit fields; validate in MCP `scorecard` tool response. Landed as `ScorecardResponse` upgrade in `verdify_schemas/mcp_responses.py` | Schema + MCP | unblocks `web` scorecard endpoint | M | **done** (6df34a6) |
| G4 | Vendor `skills/greenhouse-planner.md` into the repo (`docs/planner/greenhouse-playbook.md`); add a startup assertion in `iris_planner.py` that the file exists | Code + docs | — | S | **done** (b309a5c) |
| G4b | Deploy-time sync of the agent-host copy from the in-repo canonical (currently manual; needs a Makefile target or systemd path unit). Host file still says "18 MCP tools" — drops to "17" once the sync lands | Cleanup | — | XS | pending |
| G5 | Delete dead templates (`planner-prompt.j2`, `planner-prompt.md`), keep or relocate `planner-reference.md`, prune `config/ai.yaml` `templates:` + `schedules.planner` stanzas to match live code | Cleanup | — | S | **done** (0a6b20a) |
| G5b | Either add `make planner-dry` target to Makefile or drop it from `docs/agents/genai.md` gate list (doc cites it but target doesn't exist) | Cleanup | — | XS | **done** (8737dd3) |
| G6 | Split planner prompt into immutable rubric (cacheable) + per-cycle context (non-cacheable). Measure cache-hit rate after | Prompt refactor | cost | L | pending |
| G7 | Close the hypothesis loop: inject prior plan's `hypothesis_structured` + `actual_outcome` into the next SUNRISE prompt as a "what did yesterday predict vs deliver" block | Prompt + MCP read path | — | M | **done** (d6de832) |
| G8 | Lessons state machine: `LessonState` literal (`proposed`/`validated`/`superseded`/`retired`), transition guards, `lessons_manage` `supersede(old_id, new_id)` action | Schema + MCP | — | M | pending |
| G9 | Multi-model eval: shadow Gemini 2.5 Pro call on N% of cycles; store both plans + outcome; publish weekly comparison page | Infra + prompt | coordinator sign-off | L | pending |
| G10 | Harden `scripts/gather-plan-context.sh`: aggregate per-section exit codes, emit a "context completeness" header Iris can read and flag | Script | — | M | **done** (58ade59) |
| G11 | Rename `scripts/smoke-sprint20.py` → `smoke-feedback-loop.py`; adopt purpose-named smoke scripts going forward | Cleanup | — | XS | pending |
| G12 | Either populate or drop `plan_journal.conditions_summary` (propose migration to coordinator) | Coordinator handshake | — | S | pending |
| G13 | Scorecard "why did we fail": when `planner_score < 80`, compute top-2 contributing stress windows + include in next plan context | Prompt + MCP | unblocked by G3 | M | pending |
| G14 | One-line clarification in `docs/agents/genai.md`: vault-writer scripts (`generate-*`) are `web` scope; genai owns the data models they consume | Doc | — | XS | **done** (600b7b9) |
| G15 | **Infra drift**: `db/migrations/076-078` and `db/schema.sql` are stale vs live `fn_planner_scorecard()` (live emits 25 metrics incl. temp/vpd_compliance_pct, kwh/therms/water_gal/mister_water_gal, cost_electric/gas/water; migrations don't). Resynced by coordinator migration 096 + schema dump update | Coordinator handshake | — | S | **done** |
| G-Kn-B | **Expand `_PLANNER_CORE` tunable table from 24 → 86.** Current Tier 1 table covers high-frequency params but leaves 62 (irrigation, per-zone VPD, switches, fog safety gates) undocumented to Iris even though she can push them. Absorb `docs/tunable-cascade.md` structure into a compact name/unit/range/default/readback-flag format | Prompt | — | M | **done this sprint** (sprint-4) |
| G-Kn-C | **Surface recent clamps to Iris** — new section in `gather-plan-context.sh` showing top-10 clamped params (24h) with count/avg-requested/avg-applied/reason. Without this Iris repeats the same out-of-range push and wonders why it never lands | Context script | — | S | **done this sprint** (sprint-4) |
| G-Kn-D | **Surface delivery history to Iris** — new section in `gather-plan-context.sh` showing 24h `plan_delivery_log` grouped by (event_type, status) so Iris sees her own silent-drop pattern | Context script | — | S | **done this sprint** (sprint-4) |
| G-Kn-E | **Prompt drift fixed** — tunable content in `_PLANNER_KNOWLEDGE` was mechanically linked to `docs/tunable-cascade.md` (now referenced as canonical). Semantics kept in sync manually; future editors update cascade + prompt in same PR | Prompt + doc | — | XS | **done this sprint** (sprint-4) |
| G-Kn-Fix | **Section-27 bug**: `gather-plan-context.sh` aborted at `validate-plan-coverage.sh` non-zero exit because of `set -euo pipefail`, silently killing sections 28–31 (including sprint-1's G10 completeness header). Trailing `|| true` unblocks downstream sections. Real production-signal gap — context was being truncated for months | Context script | — | XS | **done this sprint** (sprint-4) |
| G-Kn-A | Wire coordinator's `v_tunable_dynamics` view into `gather-plan-context.sh` (avg/min/max/stddev per tunable over 7d window). Closes Gap A from iris-dev's trace | Context script | blocks on `v_tunable_dynamics` coordinator PR | M | pending |
| G-Kn-F | Per-tunable variance awareness in prompt — derived from G-Kn-A's dynamics view. Warn Iris when her pushes show zero effect (stddev unchanged post-push) | Prompt + script | depends on G-Kn-A | S | pending |
| G16 | **`planner_stale` alert threshold 8h→14h.** False alarm 2026-04-19 14:27 UTC misled a sibling agent into reporting Iris as hung. Iris was fine — alert threshold sits below the SUNSET↔SUNRISE cadence (~12.7h) guaranteeing a daily false-positive. Cross-scope PR into ingestor (`ingestor/tasks.py:666` + `scripts/alert-monitor.py:284`, both `28800`→`50400`) | Cross-scope (ingestor) | — | XS | **done this sprint** |
| G17 | Planning-cadence note at top of `docs/planner/greenhouse-playbook.md` explaining SUNRISE/SUNSET-only full plans + what a genuine stall looks like (no SUNRISE in 14h AND no `set_tunable` in 8h AND OpenClaw failing). Prevents future sibling agents from misdiagnosing the gap as an incident | Doc | — | XS | **done this sprint** |
| G18 | (follow-up to G16) Replace flat `plan_age > 50400` check with a two-factor semantic check: no SUNRISE/SUNSET event delivered in 14h AND no `setpoint_changes WHERE source='iris' AND ts > now() - interval '8 hours'`. More accurate than a single age threshold. Ingestor may want to own this outright | Cross-scope (ingestor) | — | M | pending |

## Ideas (not committed)

- MCP `replan(reason: str)` tool — let Iris explicitly request a replan from
  within the conversation, short-circuiting the event-driven trigger.

## Gates / reminders

- `make lint` (ruff), `make test` — required, no exceptions.
- `make planner-dry` — before prompt ships.
- `scripts/smoke-sprint20.py` (post-G11: `smoke-feedback-loop.py`) —
  end-to-end against live stack.
- Cost sanity — coordinator reviews if avg plan-cycle cost inflates >20%.
- Model swaps or routing-policy changes (local ↔ cloud, Gemma/version bumps, or behavior-impacting model changes) — require coordinator sign-off.

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
