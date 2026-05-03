# Prior-Art Launch Rollup - 2026-05-03

This note captures Jason's second launch-feedback pass. Treat this as planning input and positioning memory, not as a fully verified literature review. Before publishing externally, verify each specific paper/project claim from primary sources.

Verdify should not look like a generic smart-greenhouse repo. It should look like a public AI-control-system case study:

- Edge-safe control owns real-time behavior.
- LLM tactical planning proposes bounded intent.
- Telemetry, plans, costs, failures, and lessons are public.
- Every plan is a falsifiable physical hypothesis.

Preferred launch line:

> Verdify makes AI physical-control decisions falsifiable. It publishes the plan, the outcome, the cost, the failure, and the lesson.

Avoid primary framing around "self-improving AI solar greenhouse". Use "public AI greenhouse control loop", "self-correcting", "self-tuning", or "learning from outcomes" unless the page immediately explains the lesson lifecycle.

## Backlog Extraction

Before broad launch:

- Related Work page.
- Safety Architecture / "Why the AI does not control relays" page.
- Baseline vs Iris score table.
- Related-work comparison table.
- Static object-model/control-loop diagram.
- Why not RL / why not direct LLM control FAQ.
- Builder path with BOM, MQTT examples, sample plan JSON, scorecard JSON, and code-transparency stance.
- Keep canonical lessons curated and raw lessons clearly separated.

Soon after launch:

- Open-source or publish a sanitized `verdify-plan-schema`.
- Publish one full daily plan lifecycle: forecast -> plan -> tunables -> telemetry -> score -> lesson.
- Add counterfactual replay roadmap.
- Add crop-steering roadmap: substrate sensors, pH/EC/DO, DLI correction, shade cloth automation.
- Add progressive autonomy L1-L4 roadmap.

