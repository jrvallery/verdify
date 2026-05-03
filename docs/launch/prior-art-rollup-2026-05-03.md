# Prior-Art Launch Rollup - 2026-05-03

This note captures Jason's second launch-feedback pass. Treat this as planning input and positioning memory, not as a fully verified literature review. Before publishing externally, verify each specific paper/project claim from primary sources.

## Core Position

Verdify should not look like a generic smart-greenhouse repo. It should look like a public AI-control-system case study:

- Edge-safe control owns real-time behavior.
- LLM tactical planning proposes bounded intent.
- Telemetry, plans, costs, failures, and lessons are public.
- Every plan is a falsifiable physical hypothesis.

Preferred launch line:

> Verdify makes AI physical-control decisions falsifiable. It publishes the plan, the outcome, the cost, the failure, and the lesson.

Avoid primary framing around "self-improving AI solar greenhouse". Use "public AI greenhouse control loop", "self-correcting", "self-tuning", or "learning from outcomes" unless the page immediately explains the lesson lifecycle.

## Architecture Lessons

### AgroNova

Pattern to borrow: edge-safe / cloud-smart greenhouse control. Local deterministic control remains operational during cloud or internet failure; the LLM layer adds weather and agronomic context.

Verdify action:

- Add a public "Why the AI does not control relays" page.
- State the failure behavior plainly: if local inference, the cloud peer, Wi-Fi, or the planner is down, the ESP32 keeps enforcing the last safe bounded plan and firmware safeguards.
- Position Verdify's 72-hour tactical planning and public scorecards as stronger than threshold-triggered consultative LLM advice.

### IOGRUCloud

Pattern to study: progressive autonomy levels, VPD-first cascading setpoints, and commercial-scale adaptive climate control. Do not compete on energy-saving claims.

Verdify action:

- Adopt an L1-L4 autonomy roadmap for safety and public communication.
- Place Verdify on that ladder explicitly.
- Use VPD-primary architecture as a first-class explanation, not a side note.

### Hydro0x01 / HydroNode

Pattern to borrow: builder packaging. Their open-source packaging answers what it does, what stack it uses, how to install it, and how to contribute.

Verdify action:

- Add a Build Notes or Reference Implementation section.
- Include architecture diagram, ESP32 role, MQTT topic examples, DB table overview, example daily plan JSON, example scorecard JSON, hardware BOM, "what I would do differently", and "what is not production-safe yet".

### HAGR

Pattern to borrow: grow-room vocabulary and Home Assistant audience fit. HAGR uses AI around telemetry; Verdify uses AI as a tactical planner whose output is scored.

Verdify action:

- Add crop-steering language where accurate: generative/vegetative steering, day/night VPD bands, dryback/irrigation windows, DLI target vs actual, substrate sensing roadmap, pH/EC/DO maturity model.
- Pre-write the comparison line for Home Assistant discussions.

### Mycodo

Pattern to borrow: modular control objects: sensors, actuators, functions, rules, profiles.

Verdify action:

- Publish a Verdify object model diagram:
  `Crop profile -> target bands -> forecast/state -> Iris plan -> tunables -> ESP32 state machine -> telemetry -> scorecard -> lessons -> next plan`.
- Do not position as "Mycodo plus AI"; position as a public learning loop built on instrumentation.

### iGrow, GreenLight-Gym, WUR Autonomous Greenhouse Challenge

Pattern to borrow: measurable optimization, baseline comparison, and simulator/counterfactual thinking.

Verdify action:

- Add a Baseline vs Iris table with temp compliance, VPD compliance, stress hours/day, water/day, energy/day, cost/day, and planner score.
- Add a counterfactual replay roadmap: replay recent telemetry with alternate tunables before considering RL.
- Use reality-first framing: Verdify runs against actual weather and plants, not only a simulator.

### FarmBot / OpenAg

Pattern to borrow: public educational packaging and climate-recipe language.

Verdify action:

- Add a human-accessible build story with photos, system diagram, equipment/wiring diagram, what broke, what it costs, and what others can copy.
- Consider "climate recipe" language for crop bands, but avoid OpenAg-style reproducibility overclaims.

### Agentic AI Research

Pattern to borrow: Think-Act-Learn style framing, but avoid overclaiming "self-improving" if the literature uses that term for stronger tool-generating agents.

Verdify action:

- Add "why not direct LLM control?" and "why not RL?" FAQ answers.
- Pre-write HN responses around determinism: Iris writes parameters, dispatcher validates, firmware applies hysteresis/dwell/safety.
- Verify and cite relevant literature before external launch copy: T-A-L, IoTGPT-style reliability critiques, IOGRUCloud, LLM/RAG greenhouse architecture, AgroNova.

## Positioning Table To Build

Create a page or section comparing:

| System | Control style | AI role | Public telemetry | Public scorecards | Public lessons |
|---|---|---|---|---|---|
| Mycodo | Rules/PID | None | Local | No | No |
| Hydro0x01 | Rules + dashboard | Diagnostics/roadmap | Local | No | No |
| HAGR | Home Assistant crop steering | Summaries/assistant | Local | No | No |
| AgroNova | Local rules + LLM advisory | Contextual recommendations | Paper screenshots | No | No |
| iGrow | Simulator + optimization | RL/optimization | Paper/repo | Experimental | No |
| Verdify | ESP32 safety + LLM tactical planning | Plans tunables | Yes | Yes | Yes |

Verify each row before publishing.

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
