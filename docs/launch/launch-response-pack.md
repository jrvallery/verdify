# Launch Response Pack

Date: 2026-05-03
Owner: coordinator / iris-dev

Use this during HN/Reddit/X launch comments. The tone should stay technical, direct, and non-defensive.

## Core Positioning

Verdify is a public AI-assisted physical-control experiment. The AI plans, the controller enforces, telemetry judges, and failures are public.

Short version:

> An ESP32 runs my greenhouse locally. Iris is an OpenClaw agent with local Gemma4 inference, greenhouse memory, semantic context, forecasts, prior plans, scorecards, and lessons. Iris writes bounded tactics; the ESP32 owns relay control and safety every 5 seconds. The plans, telemetry, costs, failures, and lessons are public.

Do not lead with:

- fully autonomous
- AI grows food
- off-grid solar greenhouse
- self-improving AI, unless immediately grounded in the lesson lifecycle

## HN First Comment Draft

I built this in a 367 sq ft greenhouse in Longmont, Colorado. The interesting part is the split between local agentic planning and deterministic edge control. Iris is an OpenClaw agent with a local Gemma4-26B path for routine inference. It reads live telemetry, forecast, crop bands, prior plans, scorecards, validated lessons, and the website pages that document the greenhouse's physical constraints. It writes bounded setpoints, but an ESP32 owns deterministic relay control and safety every 5 seconds.

The site publishes the plan archive, telemetry, scorecards, costs, lessons, and known failures. I am trying to make the AI layer falsifiable: every plan says what it expects, the next cycle measures what happened, and useful findings become lessons.

This is not a claim that an LLM should directly control hardware. It should not. The LLM is the slow planning layer; firmware is the real-time layer. The public scorecards are here because I want criticism on the architecture, scoring method, data gaps, and where the evidence is still weak.

## Likely Questions

### Why not PID?

PID is useful for stable single-loop control. This greenhouse is a coupled multi-objective system: temp and VPD fight each other, ventilation can cool while importing dry air, misting can lower VPD while trapping heat, and cost/water/equipment limits matter. The ESP32 still owns deterministic control. Iris is used for slow-loop tactics across forecast, crop targets, lessons, and constraints.

### Is the LLM in the real-time control loop?

No. Iris writes tactical parameters. The dispatcher validates them. The ESP32 evaluates mode and relays every 5 seconds. If the planner or network path fails, firmware keeps enforcing the last valid setpoints and safety rails.

### Why local Gemma4 instead of only a hosted model?

The greenhouse creates lots of routine reasoning events: heartbeats, transitions, minor forecast shifts, and small deviations. Those should be cheap, local, and inspectable. OpenClaw lets Iris route routine work to a local Gemma4-26B instance and reserve heavyweight cloud reasoning for milestone reviews or major changes. Both paths use the same MCP tools, trigger IDs, dispatcher validation, and ESP32 safety boundary.

### What memory does Iris use?

Iris is not reasoning from a blank prompt. The context bundle includes live telemetry, 72-hour forecast, crop bands, equipment state, scorecards, previous plan hypotheses, outcome reviews, active lessons, alerts, and the static site pages that describe the greenhouse structure, zones, equipment, crops, known limits, and build notes. Embedding-backed similarity exists for observations where available; plan outcomes are exposed as structured memory through `plan_journal`, scorecards, and lessons.

### What happens when local inference or the cloud peer is down?

The greenhouse continues running. The planner stops producing fresh tactics, the archive shows the gap, and data-health goes stale if telemetry is affected. The April 22-25 outage is public because the claim is auditability, not perfection.

### Why not RL?

RL is credible for greenhouse control, especially with GreenLight-Gym-style simulators. It is not the launch claim. Verdify has one real greenhouse, so exploration mistakes are physical. The next credible step is counterfactual replay against recent telemetry before simulator-trained policy work.

### Is "self-improving" an overclaim?

Use "self-correcting" or "learning from outcomes" instead. Verdify does not rewrite its own code. It journals hypotheses, scores outcomes, promotes validated lessons, and feeds those lessons into the next plan.

### What is VPD?

VPD is vapor pressure deficit: the drying pressure plants experience. It is usually more useful than RH alone because it combines temperature and moisture into a plant-stress metric. In Colorado spring, VPD can be the binding constraint even when temperature looks fine.

### Does Verdify prove better yield or profit?

No. The climate-control evidence is stronger than the crop-yield evidence. Harvest and crop lifecycle logging exist, but public yield/profit claims need more records and a clearer comparator. The launch claim is plans, telemetry, scorecards, costs, failures, and lessons.

### Is the greenhouse solar powered?

Use "solar-aligned." The home has rooftop solar and batteries, but the greenhouse still uses grid power and gas heat when physics requires it. Costs are tracked and published.

### Can I rebuild this?

Not as a turnkey kit today. The site publishes architecture, equipment, sample data, plan examples, scorecard examples, and build notes. Full source/prompt release needs a careful scrub because the live system controls real equipment and contains operational details.

## Comparisons

### Mycodo

Mycodo is the mature open-source Raspberry Pi environmental control reference. Verdify is not trying to replace it. Verdify asks what becomes possible once instrumentation and control are connected to a public planning, scoring, and lesson loop.

### HAGR

HAGR is a strong Home Assistant grow-room reference with crop-steering vocabulary and AI summaries. Verdify uses AI as a tactical planner whose setpoints are enforced by deterministic firmware and scored against measured reality.

### AgroNova

AgroNova validates the edge-safe/cloud-smart architecture: local rule-based control plus LLM-supported context. Verdify's distinction is public operations evidence: plans, scorecards, costs, failures, and lessons.

### IOGRUCloud

IOGRUCloud is a reported commercial-scale AI/IoT climate platform. Verdify should not compete on scale or deployment evidence. Verdify's value is transparent home-scale falsifiability.

### iGrow / GreenLight-Gym

iGrow and GreenLight-Gym are the formal optimization/simulator side of the field. Verdify is the inverse experiment: one real greenhouse, public telemetry, slow-loop LLM planning, and no claim of beating expert growers.

### Commercial CEA

Koidra, Source.ag, and Blue Radix are commercial grower-augmentation systems. Verdify is a public lab notebook, not a commercial greenhouse climate computer.

## Phrases To Use

- "The AI plans; firmware enforces."
- "Iris is local-first, but never safety-critical."
- "OpenClaw routes routine reasoning to local Gemma4 and escalates major reviews."
- "Every plan is a hypothesis."
- "The greenhouse keeps running if the planner goes away."
- "This is an operational comparison, not a controlled A/B trial."
- "The evidence layer is the product right now."
- "Software cannot create shade cloth or more vent area."

## Phrases To Avoid

- "The AI controls the greenhouse" without immediately clarifying the ESP32 safety split.
- "Autonomous food production."
- "Off-grid solar greenhouse."
- "Yield improvement" or "profit improvement" until crop outcome evidence matures.
- "First" or "largest."
