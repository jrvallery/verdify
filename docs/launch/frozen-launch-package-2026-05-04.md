# Frozen Launch Package - 2026-05-04

Owner: Jason / coordinator
Status: ready for final human read-through

This is the launch package to use once the public proof path passes the final smoke check and `data_health_status` remains `warn` or better.

## Posting Stance

- Identity: project-first, attributed to Jason's normal technical identity. Do not add family names, home-specific security details, camera model details, or private operational diagrams in launch comments.
- Code stance: selected public artifacts now; full live repo and prompts stay private until scrubbed.
- API stance: public read-only proof API; write routes require a key; API/OpenAPI remain noindex.
- Indexing stance: broad launch pages are indexable; raw/API/Grafana surfaces stay noindex.
- Waitlist stance: deferred. No form or secrets path before HN/Reddit.
- Clip stance: useful but not blocking. If no 30-90s operations clip is recorded before posting, launch without it and do not promise one in the first comment.

## HN Title

Use this first:

`Show HN: An OpenClaw agent plans my greenhouse, but an ESP32 owns the relays`

Backups:

- `Show HN: Local Gemma4 plans my ESP32 greenhouse; the receipts are public`
- `Show HN: Public planning data from a local-AI-tuned ESP32 greenhouse`

## HN First Comment

I built this in a 367 sq ft greenhouse in Longmont, Colorado. The interesting part is the split between local agentic planning and deterministic edge control. Iris is an OpenClaw agent with a local Gemma4-26B path for routine inference. It reads live telemetry, forecast, crop bands, prior plans, scorecards, validated lessons, and the website pages that document the greenhouse's physical constraints. It writes bounded setpoints, but an ESP32 owns deterministic relay control and safety every 5 seconds.

The site publishes the plan archive, telemetry, scorecards, costs, lessons, and known failures. I am trying to make the AI layer falsifiable: every plan says what it expects, the next cycle measures what happened, and useful findings become lessons.

This is not a claim that an LLM should directly control hardware. It should not. The LLM is the slow planning layer; firmware is the real-time layer. The public scorecards are here because I want criticism on the architecture, scoring method, data gaps, and where the evidence is still weak.

Useful starting points:

- Safety Architecture: why the AI does not control relays.
- Evidence: live operations, planning quality, economics, baseline comparison, and public sample data.
- Plans and Lessons: the daily plan archive and the lesson stream Iris reads before future plans.
- Related Work: how Verdify differs from Mycodo, HAGR, iGrow, GreenLight-Gym, AgroNova, IOGRUCloud, and commercial CEA systems.

## X / LinkedIn Soft-Launch Lede

I built Verdify in a 367 sq ft greenhouse in Colorado.

An ESP32 runs the greenhouse locally. Iris is an OpenClaw agent with local Gemma4 inference, memory, forecasts, scorecards, and lessons. Iris writes bounded tactics; the ESP32 owns relay control and safety every 5 seconds.

The plans, telemetry, costs, failures, and lessons are public.

Start with the Safety Architecture and Evidence pages.

## Reddit Angles

Home Assistant / ESPHome:

> The interesting part is not that I used AI near a greenhouse. It is that the AI is not in the relay loop. ESPHome/ESP32 owns deterministic control; Iris writes bounded setpoints and every setpoint has telemetry and scorecard evidence.

Homelab / self-hosted:

> This is a local-first physical-control lab notebook: TimescaleDB, Grafana, Quartz, ESPHome, Home Assistant, OpenClaw, local Gemma4, public dashboards, and public failure records.

Greenhouse / hydroponics:

> The hard problem is VPD and thermal tradeoffs in a small dry-climate greenhouse. The AI planning layer is useful only if the scorecards show fewer bad tradeoffs; the public evidence is there for that criticism.

AI / agents:

> Verdify treats every physical-control plan as a falsifiable hypothesis. The agent can plan, but firmware enforces and telemetry judges.

## Comment-Coverage Window

Preferred broad launch window: Tuesday-Thursday morning Pacific. Be available for the first 4-6 hours after posting.

If launching this week, use Tuesday, May 5, 2026 or Wednesday, May 6, 2026 after the final smoke check. Delay if the public proof API returns `fail` or if any unresolved critical/high operational alert is open.

## Do Not Say

- Fully autonomous.
- AI grows food.
- Off-grid solar greenhouse.
- First, best, or largest.
- Yield improvement or profit improvement.
- The AI controls the greenhouse without immediately explaining that firmware owns relays.
