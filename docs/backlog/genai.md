# Backlog: `genai`

Owned by the [`genai`](../agents/genai.md) agent.

## In flight

Portions of Sprint 23 (MCP harvest/treatment bug fix, `HarvestCreate`/`TreatmentCreate` envelopes) are bundled into the `ingestor` sprint commit. Once that merges, genai's boundary is fully typed through MCP.

## Next up (candidates)

- [ ] **Scorecard function output schema.** `fn_planner_scorecard()` returns a `{metric: value}` dict; MCP `scorecard` tool returns it untyped. Define a typed projection (`PlannerScorecard` with 25 fields as explicit properties, one per metric) and validate on MCP response.
- [ ] **Planner prompt refactor — isolate the immutable rubric from the per-cycle context.** Currently a single Jinja template; caching is impossible because the rubric changes on every render. Split to enable prompt caching.
- [ ] **Lessons validation workflow.** `LessonValidate` exists as a shape but the full lifecycle (create → validate → deactivate) isn't encoded as a state machine. Add `LessonState` literal + transition guards.
- [ ] **Multi-model planner.** Evaluate Gemini 2.5 Pro (already wired in cloud) against Claude Opus on identical plan cycles for a week; publish comparison on site.
- [ ] **Agentic hypothesis tracking.** `PlanHypothesisStructured` is stored per plan but not consumed by the next cycle. Close the loop: planner reads prior hypotheses + outcomes at prompt time.

## Ideas (not yet committed)

- MCP tool `replan(reason: str)` — lets Iris explicitly request a replan from within the conversation, short-circuiting the event-driven trigger.
- Scorecard "why did we fail" — when `planner_score < 80`, compute the top-2 contributing stress windows and include in the next plan context.

## Recent history

- Sprint 22 (bundle): 8 API endpoints gained `response_model=`; `verdify_schemas/api.py` introduced.
- Sprint 21: Plan/PlanTransition/PlanEvaluation/TunableParameter validation across MCP boundary.
- Sprint 20: Unified plan schema + feedback loop + manifestation.

## Gates / reminders

- `make planner-dry` before prompt ships.
- `scripts/smoke-sprint20.py` must pass end-to-end against live stack.
- Cost sanity: coordinator reviews if avg plan-cycle cost inflates >20%.
- Model swaps (Claude ↔ Gemini, version bumps) require coordinator sign-off.
