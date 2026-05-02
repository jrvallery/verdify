# Verdify Launch Command Center

Updated: 2026-05-02
Launch owner: coordinator / iris-dev
Launch posture: **not broad-launch ready until P0 gates are closed**

Source triage: [`feedback-triage-2026-05-02.md`](feedback-triage-2026-05-02.md)

Verdify's public launch narrative is:

> An ESP32 runs my greenhouse. Claude tunes its setpoints three times a day. The plans, telemetry, costs, failures, and lessons are public.

This replaces weaker launch framing like "self-improving AI greenhouse" when addressing skeptical technical audiences. The safety split must stay above the fold: the LLM does not flip relays; it writes tactical parameters and the ESP32 enforces real-time control and safety.

## Readiness Gates

| Gate | Owner | Status | Acceptance |
|---|---|---|---|
| L0.1 Privacy/security scrub | coordinator + Jason | pending | No children's names, sensitive household details, local IPs, raw device IDs, tokens, alert channels, or exposed camera/security layout on public pages/dashboards. |
| L0.2 Public proof path | web + saas/coordinator | pending | Homepage or `/launch` shows live proof without auth bounce: current temp, VPD, outdoor temp, last plan timestamp, last plan score. Static fallback snapshot exists if Grafana fails. |
| L0.3 Lessons credibility | web + genai | pending | Default lessons page shows 15-20 distinct curated lessons with duplicate families collapsed into a canonical lesson plus validation count. Raw firehose remains accessible but labeled. |
| L0.4 Daily plan readability | web + genai | pending | Daily plan pages lead with score, hypothesis, result, and changed parameters; unchanged parameter dumps are behind `<details>` or raw view. |
| L0.5 Launch story page | web + Jason | pending | `/` or `/launch` has a hero number, snow/greenhouse visual, launch one-liner, proof cards, architecture link, and known-limits link. |
| L0.6 Social preview | web | pending | Explicit `og:title`, `og:description`, `og:image`, Twitter card tags; verified with a local/static inspector and live URL after deploy. |
| L0.7 Grafana public QA | web + saas/coordinator | pending | `graphs.verdify.ai` dashboards and embedded panels load in incognito Chrome/Safari/mobile and in-app browsers, or pages show static fallback snapshots. |
| L0.8 Launch assets | Jason + web | pending | 30-90s operations screen recording, architecture SVG, BOM, cost callout, outage story, and audience-specific launch copy drafts exist. |
| L0.9 Public API lockdown | coordinator + web + saas | pending | Unauthenticated internet-facing API routes are read-only/launch-safe; mutating routes return 401/403 or are not publicly routed; `/docs`/OpenAPI exposure is intentional. |
| L0.10 Robots/indexing policy | coordinator + web + saas | pending | `robots.txt`, sitemap, page metadata, Grafana/API headers, and Traefik `X-Robots-Tag` agree on what indexes and what stays noindex. |
| L0.11 Public metrics/freshness contract | ingestor + coordinator + web | pending | One public-safe metrics/data-health contract powers launch proof cards and stale-data labels; no hard-coded homepage counters. |

Broad launch means HN/Reddit. X/LinkedIn soft launch can happen after L0.1-L0.6 and L0.9-L0.11 if Jason explicitly accepts remaining proof-path risk.

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
- Verify any public claim about "42 climate states", "every 5 seconds", and relay safety.
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

- `Show HN: 40 days of public planning data from an LLM-tuned ESP32 greenhouse`
- `Show HN: I let Claude tune my greenhouse three times a day; here are the receipts`

Positioning line:

> Verdify is a live experiment in AI-assisted physical control: the AI plans, the controller enforces, the telemetry judges, and the failures are public.

Avoid as primary framing:

- "fully autonomous"
- "AI grows food"
- "solar-powered" without clarifying grid/gas/Powerwall reality
- "self-improving" without immediately showing lesson lifecycle evidence
