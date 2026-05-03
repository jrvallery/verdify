# Launch Sprint: L1 Credibility Package

Date: 2026-05-03
Owner: coordinator / iris-dev
Target window: 3 working days, plus Jason-owned launch-day recording and comment coverage

Implementation status, 2026-05-03:

- Engineering/content assets completed: Related Work, Safety Architecture, Baseline vs Iris, FAQ, response pack, builder path, object-model diagram, and backlog status updates.
- Remaining human-owned launch actions: 30-90s operations clip, final HN title/comment approval, launch identity posture, launch calendar, and comment-coverage availability. Waitlist/newsletter capture is explicitly deferred.

## Goal

Verdify is past P0 hardening. The next sprint gets the public launch from "safe to show" to "hard to dismiss."

The sprint closes the assets a skeptical technical reader will look for after the homepage:

- Is the control architecture safe?
- Is Verdify aware of prior work?
- Can the data prove improvement against a baseline?
- Can builders understand enough to reproduce the pattern?
- Are the likely HN/Reddit objections answered before they dominate the thread?

Broad launch is still gated by Jason's attribution, code-transparency, video, and launch-calendar decisions.

## Sprint thesis

Verdify should launch as a public AI-control-system case study, not as a generic smart-greenhouse repo.

The working line remains:

> An ESP32 runs my greenhouse locally. Iris is an OpenClaw agent with local Gemma4 inference, greenhouse memory, semantic context, forecasts, prior plans, scorecards, and lessons. Iris writes bounded tactics; the ESP32 owns relay control and safety every 5 seconds. The plans, telemetry, costs, failures, and lessons are public.

The sprint must keep three constraints visible:

1. The LLM does not flip relays.
2. The controller remains deterministic and local.
3. The claims are falsifiable through telemetry, scorecards, failures, and lessons.

## In Scope

| Workstream | Launch IDs | Primary owner | Support | Done when |
|---|---|---|---|---|
| Related Work page | L1.9, L1.12 | web + coordinator | genai | Public page and comparison table position Verdify against AgroNova, IOGRUCloud, Hydro0x01, HAGR, Mycodo, iGrow, GreenLight-Gym, FarmBot/OpenAg, WUR, and commercial CEA using verified, non-overclaimed claims. |
| Safety Architecture page | L1.10, L1.15, L2.5 | web + firmware | genai + coordinator | "Why the AI does not control relays" explains LLM tactical intent, dispatcher validation, ESP32 cadence, safety rails, cloud/wifi/planner failure behavior, and an object-model loop diagram. |
| Baseline vs Iris evidence | L1.11 | ingestor + web | coordinator | Public table compares baseline and current planner periods for compliance, stress, water, energy, cost, and score with clear definitions and caveats. |
| FAQ + response pack | L1.7, L1.13 | genai + coordinator | web | HN/Reddit response notes and public FAQ answer PID, RL, direct LLM control, VPD physics, shade cloth, interpretability, and self-correcting claims. |
| Builder / reference path | L1.14 | web | firmware + ingestor + Jason | Build notes include BOM, wiring/equipment overview, MQTT examples, DB overview, example daily plan JSON, example scorecard JSON, non-production-safe caveats, and code-transparency stance. |
| Launch-day assets | L1.6 + Jason decisions | Jason + coordinator | web + saas | 30-90s operations clip exists or is explicitly deferred; identity, code stance, baseline window, citation comfort, waitlist decision, and HN first comment are decided. |

## Out of Scope

- Behavior-changing firmware OTA unless Track A greenhouse safety requires it.
- SaaS Sprint 10 hardening, React app, auth, or multi-tenant onboarding.
- RL, GreenLight-Gym integration, or counterfactual replay implementation.
- New public write APIs.
- Marketing copy that depends on unverified yield, profit, or energy-saving claims.

## Sequencing

### Day 0: Decisions and facts

- Jason decides attribution mode, public code stance, baseline period, citation comfort, waitlist stance, and whether "climate recipe" terminology is adopted now.
- Firmware supplies exact public-safe safety facts: ESP32 cadence, relay ownership, safety rails, watchdog behavior, and failure behavior under cloud/wifi/planner outage.
- Coordinator verifies related-work claims from primary sources before public copy lands.
- Ingestor drafts the baseline metric query or view shape.

### Day 1: Draft public assets

- Web drafts Related Work, Safety Architecture, object-model diagram, and Builder path.
- GenAI drafts FAQ and HN/Reddit response pack.
- Ingestor produces baseline/current comparison data and identifies caveats.
- Coordinator checks that every public claim maps to data, a source, or a stated caveat.

### Day 2: Integrate and tighten

- Web publishes the pages into the public IA and links them from home/evidence/intelligence.
- GenAI folds FAQ answers into the site and response pack.
- Ingestor exports one representative lifecycle bundle if it is low-risk; otherwise it becomes the first post-launch evidence follow-up.
- Coordinator reviews for overclaiming, privacy leakage, source quality, and story coherence.

### Day 3: Launch readiness pass

- Run `make lint`, `make test`, `make site-doctor`, `git diff --check`, and targeted live URL smoke checks.
- Smoke test homepage, Related Work, Safety Architecture, Baseline vs Iris, Builder path, data downloads, OG metadata, Grafana embeds, and API lockdown.
- Jason performs mobile/in-app browser smoke tests and records or explicitly defers the operations clip.
- Freeze HN title, first comment, X thread, and subreddit-specific angles.

## Exit Criteria

The sprint is done when:

- L1.7, L1.9, L1.10, L1.12, L1.13, L1.14, and L1.15 are marked done.
- L1.11 is published or explicitly deferred with a documented reason and a post-launch date.
- Jason decisions are recorded in `docs/backlog/launch.md`.
- Public launch pages have no raw local details, family/privacy leaks, unsupported "first/best/largest" claims, or raw dollar-sign rendering.
- All checks pass and the site is deployed.
- The response pack exists outside chat so Jason can use it during launch comments.

## Recommended Cuts If Time Slips

Do not cut Safety Architecture or FAQ. They are the strongest defense against launch-thread failure.

If time slips, defer in this order:

1. Full daily lifecycle artifact, as long as the sample datasets remain live.
2. Waitlist/newsletter capture.
3. Crop-steering maturity roadmap.
4. Weekly "Verdify this week" template.
5. Counterfactual replay roadmap page.

## Risk Register

| Risk | Mitigation |
|---|---|
| Related Work copy overclaims or misquotes peers | Use primary sources only; phrase uncertain claims as "Verdify's reading" or omit them. |
| Baseline comparison looks like an academic A/B test when it is not | Label the period, weather caveats, crop mix, and data limits directly in the table. |
| Safety page implies firmware behavior that is not true | Firmware fact review is required before publication. |
| Builder path invites unsafe copying | Include "not production-safe yet" caveats and separate architecture pattern from literal wiring instructions. |
| Launch decisions block engineering work | Record Jason-owned decisions separately from code blockers; publish only after the decisions are explicit. |
| Site adds too many pages and diffuses the story | Home page keeps one path: live proof -> safety -> evidence -> lessons -> related work/build notes. |

## Launch Board Mapping

This sprint pulls from:

- `docs/backlog/launch.md`: L1.7, L1.9, L1.10, L1.11, L1.12, L1.13, L1.14, L1.15, L1.6
- `docs/backlog/web.md`: W-L1.9, W-L1.10, W-L1.11, W-L1.12, W-L1.14, W-L1.15
- `docs/backlog/genai.md`: G-L1.7, G-L1.13, G-L2.6, G-L2.7
- `docs/backlog/ingestor.md`: I-L1.11, I-L2.7, I-L2.8
- `docs/backlog/firmware.md`: F-L1.10, F-L1.14, F-L2.5
- `docs/backlog/saas.md`: S-L2.2 only as a Jason decision, not as engineering scope
