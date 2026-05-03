# Verdify Launch Command Center

Updated: 2026-05-03
Launch owner: coordinator / iris-dev
Launch posture: **P0 hardening deployed; broad-launch timing now depends on Jason's identity/copy/video decisions**

Source triage:

- [`feedback-triage-2026-05-02.md`](feedback-triage-2026-05-02.md)
- [`prior-art-rollup-2026-05-03.md`](prior-art-rollup-2026-05-03.md)
- [`launch-response-pack.md`](launch-response-pack.md)

Active sprint:

- [`sprint-2026-05-03-l1-credibility.md`](sprint-2026-05-03-l1-credibility.md) - engineering/content assets are complete; Jason-owned video, final copy, identity posture, and launch calendar remain.

Verdify's public launch narrative is:

> An ESP32 runs my greenhouse locally. Iris is an OpenClaw agent with local Gemma4 inference, greenhouse memory, semantic context, forecasts, prior plans, scorecards, and lessons. Iris writes bounded tactics; the ESP32 owns relay control and safety every 5 seconds. The plans, telemetry, costs, failures, and lessons are public.

This replaces weaker launch framing like "self-improving AI greenhouse" or "Claude tunes setpoints three times a day" when addressing skeptical technical audiences. The sharper story is local-first agentic planning: OpenClaw routes routine reasoning to local Gemma4 and escalates heavier reviews when needed. The safety split must stay above the fold: the LLM does not flip relays; it writes tactical parameters and the ESP32 enforces real-time control and safety.

The prior-art posture is: Verdify is not claiming to be the first smart greenhouse, the biggest autonomous greenhouse deployment, or the best RL optimizer. Verdify's contribution is the public falsifiability loop: plan, telemetry, score, cost, failure, and lesson are all visible for a real physical greenhouse.

## Readiness Gates

| Gate | Owner | Status | Acceptance |
|---|---|---|---|
| L0.1 Privacy/security scrub | coordinator + Jason | done | Public Markdown and generated HTML scrubbed for family names, local IPs, camera model/security layout, ambiguous cloud/solar claims, and raw dollar-sign rendering. API/Grafana surfaces carry `X-Robots-Tag: noindex, nofollow`. |
| L0.2 Public proof path | web + saas/coordinator | done | Homepage shows live read-only API proof cards for current temp, VPD, outdoor temp, planner score, plan count, and data-health status, with freshness/stale labeling. |
| L0.3 Lessons credibility | web + genai | done | Default lessons page shows 20 canonical lessons distilled from active machine rows, with validation counts; raw machine stream is behind a labeled details section. |
| L0.4 Daily plan readability | web + genai | done | Daily plan pages lead with cycle metrics, score/outcome, hypothesis/rationale, and changed secondary parameters; full secondary dumps are behind `<details>`. |
| L0.5 Launch story page | web + Jason | done | Homepage now leads with the OpenClaw/Iris local-inference story plus the ESP32 safety split, greenhouse visuals, live proof cards, Grafana fallbacks, and direct evidence/architecture paths. |
| L0.6 Social preview | web | done | Homepage emits explicit OG/Twitter tags and uses the real snow greenhouse photo for `og:image`. |
| L0.7 Grafana public QA | web + saas/coordinator | done | Public dashboard and d-solo URLs return anonymous Viewer boot data; app bundles load with 200 responses; Grafana health and headers verified. Jason should still smoke-test mobile/in-app browsers before HN. |
| L0.8 Launch assets | Jason + web | split | Architecture SVG, equipment/BOM surface, cost callout, and April 22-25 outage story exist. The 30-90s screen recording and final audience copy remain Jason-owned launch-day assets, not code blockers. |
| L0.9 Public API lockdown | coordinator + web + saas | done | Public API exposes read-only proof/data-health endpoints; mutating routes require `X-Verdify-API-Key` unless explicitly overridden for dev; `/docs` is hidden by default and `/openapi.json` is noindexed for contract checks. |
| L0.10 Robots/indexing policy | coordinator + web + saas | done | Root `robots.txt`, canonical metadata, API/Grafana noindex headers, and Traefik security headers are aligned. |
| L0.11 Public metrics/freshness contract | ingestor + coordinator + web | done | `/api/v1/public/home-metrics` and `/api/v1/public/data-health` power live proof cards and stale-data status without hard-coded homepage counters. |

Broad launch means HN/Reddit. The remaining launch decisions are attribution, public code stance, baseline period, final HN/Reddit copy, and whether to record the short operations clip before posting.

## Agent Assignments

### Web

Launch owner for public experience.

- Curate and split lessons page: curated default, raw machine lessons, retired/duplicate families.
- Add live proof hero metrics and/or `/launch`.
- Collapse daily plan parameter dumps to deltas, keep raw details available.
- Add architecture SVG, BOM, cost callout, and outage/known-limits path.
- Fix Markdown dollar-sign rendering and "solar-powered" wording.
- Add OG/Twitter metadata and validate share card.
- Validate public Grafana embeds and static fallbacks.

### GenAI / Planner

Launch owner for narrative integrity of the planner loop.

- Define lesson canonicalization semantics: duplicate family, validation count, supersession, raw confidence.
- Prepare launch-safe language for "self-improving" claims.
- Prepare HN answer material for "why not PID?" and "is the LLM in the control loop?"
- Add weekly "Verdify this week" summary inputs: weather faced, score, lessons graduated, failures.
- Help web lead daily plans with hypothesis/result/rationale rather than raw waypoint dumps.

### Ingestor / Data

Launch owner for public evidence data surfaces.

- Provide live metrics source for homepage cards: indoor temp, VPD, outdoor temp, last plan timestamp, last score.
- Provide public data-health/trust status so stale proof degrades visibly instead of silently.
- Provide data for plan-page deltas from previous waypoint/defaults.
- Support lesson duplicate detection/canonicalization if web/genai need SQL views.
- Provide outage and sample-dataset exports for public receipts.
- Add freshness checks so launch pages fail closed when proof data is stale.

### Firmware

Launch owner for safety and hardware truth, not for pre-launch OTA work.

- No behavior-changing OTA is launch-blocking unless Track A greenhouse safety requires it.
- Supply facts for the architecture/BOM/control-split page: ESP32 loop cadence, relay ownership, sensors, probes, misters, heaters, safety states.
- Verify any public claim about the 8-state firmware controller, "every 5 seconds", and relay safety.
- Keep firmware freeze rules in force during marketing launch.

### SaaS / Infrastructure

Launch owner for public access and capture.

- Verify public Grafana / Cloudflare / Traefik behavior from unauthenticated browsers.
- Lock down or explicitly approve public API/OpenAPI exposure before broad launch.
- Align robots/indexing headers across site, Grafana, and API.
- Decide whether waitlist/newsletter capture is static, Cloud Run, or external service.
- Support public API or static fallback strategy for launch cards.
- Keep Secret Manager and cloud hardening separate from launch-critical local Track A unless a public credential risk is found.

### Coordinator / Jason

Launch owner for sequencing and identity decisions.

- Decide attribution: real identity vs pseudonymous Reddit/HN timing.
- Approve privacy scrub boundaries for family/home details.
- Decide public API stance: no public API, read-only proof API, or authenticated API.
- Decide indexing stance: immediate search indexing vs staged/noindex for raw/generated surfaces.
- Choose whether repo/code/prompt is public, partially public, or explicitly private.
- Record the launch video clip.
- Write final HN first comment and audience-specific Reddit copy.
- Be live for HN comments for the first 4-6 hours.

## Launch Sequence

1. **Fix site and proof path.** Close every L0 gate above.
2. **Soft launch.** X/LinkedIn thread with greenhouse visual, control split, proof links, honest failures.
3. **Show HN.** 5-7 days later, Tuesday-Thursday morning Pacific. Use a technical title and be present in comments.
4. **Reddit stagger.** Different lede per subreddit, 2-3 days apart. No copy-paste cross-posting.
5. **Weekly proof cadence.** Publish "Verdify this week": weather, score, lessons, failures, repairs.

## Suggested Copy

HN title candidates:

- `Show HN: Local Gemma4 agent tunes my ESP32 greenhouse; the receipts are public`
- `Show HN: An OpenClaw agent plans my greenhouse, but an ESP32 owns the relays`
- `Show HN: Public planning data from a local-AI-tuned ESP32 greenhouse`

Positioning line:

> Verdify is a live experiment in AI-assisted physical control: the AI plans, the controller enforces, the telemetry judges, and the failures are public.

Avoid as primary framing:

- "fully autonomous"
- "AI grows food"
- "solar-powered" without clarifying grid/gas/Powerwall reality
- "self-improving" without immediately showing lesson lifecycle evidence
