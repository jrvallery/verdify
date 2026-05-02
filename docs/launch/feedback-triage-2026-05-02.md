# Launch Feedback Triage — 2026-05-02

This file distills the external launch feedback into repo-tracked work. The active board is [`docs/backlog/launch.md`](../backlog/launch.md).

## Launch Blockers

1. **Lessons page credibility.** Repeated auto-extracted lessons make the learning loop look ungoverned. Default page needs curated/canonical lessons; raw machine output must be clearly labeled.
2. **"Live" proof path.** Readers must see at least one live or clearly fresh proof surface without auth bounce. Homepage needs current climate/plan/score numbers.
3. **Daily plan readability.** The story is in reflection, hypothesis, outcome, and parameter rationale; unchanged waypoint dumps bury it.
4. **Homepage framing.** The launch hook should be "ESP32 runs the greenhouse; Claude tunes setpoints; receipts are public" with a hero number and real greenhouse image.
5. **Public Grafana reliability.** Full dashboard links and embeds must work for anonymous readers or have static fallbacks.
6. **Copy defensibility.** Avoid overclaiming "self-improving", clarify "solar-powered", fix dollar-sign rendering.
7. **Privacy/security.** Scrub names, exact household/security details, local IPs, hostnames, raw device IDs, camera/security layout, and alert-channel metadata.
8. **Public API exposure.** Internet-facing API routes must be read-only or authenticated before launch; OpenAPI/docs exposure must be deliberate.
9. **Robots/indexing consistency.** Site metadata, sitemap, Grafana/API headers, and `robots.txt` must agree.
10. **Metrics contract.** Launch proof needs one public-safe metrics/freshness contract; no page should hard-code counters or pretend stale data is live.

## Strong Launch Assets

- Architecture SVG showing the safety split and data/control loop.
- Bill of materials for homelab/Home Assistant readers.
- Cost callout for HN/self-hosted readers.
- Outage story that owns April 22-25 as evidence, not a hidden flaw.
- 30-90s dashboard screen recording during a stress event.
- 7- or 30-day sample dataset.
- Public data-health/trust status that explains stale or degraded proof surfaces.
- Audience-specific launch copy for HN, X, Reddit, Home Assistant, homelab, greenhouse/hydroponics.

## Audience Ledes

| Audience | Lede | Needed proof |
|---|---|---|
| HN / agents | LLM writes tactical plans; deterministic controller enforces safety; public receipts | Architecture, plan archive, scorecard, lesson lifecycle |
| Homelab/self-hosted | One VM, TimescaleDB, Grafana, public telemetry | Architecture, cost, dashboards, sample dataset |
| Home Assistant / ESP32 | ESPHome/ESP32/RS485 probes with slow-loop planner | BOM, entities, control split |
| Greenhouse/hydroponics | VPD and dry high-altitude plant stress are the hard problem | VPD story, outage/known limits, crop outcomes |

## Non-Goals Before Launch

- No launch-driven firmware OTA.
- No SaaS hardening detour unless a public credential/access risk is found.
- No broad marketing copy until L0 launch gates close.
- No "AI directly controls relays" implication.
