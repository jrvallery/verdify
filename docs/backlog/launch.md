# Backlog: launch

Cross-agent launch board owned by coordinator / iris-dev. This file tracks launch-critical work that cuts across agent scopes. The canonical launch narrative and gates live in [`docs/launch/README.md`](../launch/README.md).

## P0 — Launch Blockers

| ID | Owner | Task | Acceptance | Dependencies |
|---|---|---|---|---|
| L0.1 | coordinator + Jason | Privacy/security scrub of public pages and dashboards | Public site and Grafana expose no children's names, local IPs, camera/security layout, tokens, alert channels, private hostnames, or raw device identifiers | Jason attribution decision |
| L0.2 | web + ingestor | Add live homepage or `/launch` proof cards | Five numbers render without auth bounce: indoor temp, VPD, outdoor temp, last plan timestamp, last plan score; stale data is labeled | Ingestor source query/API |
| L0.3 | web + genai | Curate lessons page and raw split | Default page shows distinct canonical lessons; duplicate bias/mist families collapsed with validation counts; raw page/toggle remains | Lesson canonicalization rule |
| L0.4 | web + genai | Make daily plan pages readable | Representative page `/plans/2026-04-29` leads with reflection, score, hypothesis, changed parameters; unchanged parameter dump hidden behind details/raw | Plan renderer delta logic |
| L0.5 | web | Launch story and hero number | Homepage or `/launch` has hero visual, hero number, control-split line, proof cards, known-limits path, and first-visit guided path | Jason copy approval |
| L0.6 | web | Social preview / OG card | `og:title`, `og:description`, `og:image`, Twitter card tags verified for verdify.ai; image uses real greenhouse visual | Image choice |
| L0.7 | web + saas/coordinator | Public Grafana proof path | Key embed/full-dashboard links work in incognito Chrome/Safari/mobile/in-app browsers, or static fallback snapshots are present | Grafana/Cloudflare/Traefik config |
| L0.8 | web | Copy correctness pass | Dollar signs render correctly; "solar-powered" becomes defensible solar-aligned wording; "self-improving" is paired with evidence or softened | None |
| L0.9 | coordinator + web + saas | Public API lockdown | Unauthenticated public API is read-only/launch-safe; mutating POST/PUT/DELETE routes return 401/403 or are not internet-routed; `/docs` and OpenAPI are hidden or explicitly approved | Public API strategy |
| L0.10 | coordinator + web + saas | Robots/indexing policy | `robots.txt`, sitemap, page meta, Grafana/API headers, and Traefik `X-Robots-Tag` agree; raw generated pages and API/Grafana surfaces noindex unless approved | Indexing decision |
| L0.11 | ingestor + coordinator + web | Public metrics/freshness contract | Stable public-safe DB view or API returns homepage counters, latest plan/score, climate freshness, active alerts, and data-health status; web has no hard-coded proof numbers | Public API strategy |

## P1 — Strong Launch Assets

| ID | Owner | Task | Acceptance | Dependencies |
|---|---|---|---|---|
| L1.1 | web + firmware + ingestor + genai | Architecture SVG | Shareable diagram shows ESP32 -> MQTT/Home Assistant -> TimescaleDB -> Iris/Claude -> plan_journal -> dispatcher -> ESP32; labels table/view/dashboard counts and safety split | Agent factual review |
| L1.2 | web + firmware + Jason | Bill of materials | Sensor/probe/ESP32/relay/mister/heater list exists with enough detail for homelab readers | Privacy scrub |
| L1.3 | web + saas/coordinator | Cost callout | Public page gives one clear operating-cost/API-cost summary without corrupted dollar signs | Current cost query |
| L1.4 | web + coordinator | Outage story | Evidence page owns April 22-25 zero-plan/VPD-stress run as a transparent incident, not an unexplained archive gap | Data pull from plan archive |
| L1.5 | ingestor + web | Public sample dataset | 7- or 30-day scrubbed CSV/Parquet/JSON export exists and is linked from data/evidence page | Privacy scrub |
| L1.6 | Jason + web | 30-90s dashboard clip | Timestamped screen recording shows outdoor stress, indoor VPD/temp, equipment response, and recovery | L0.7 public proof path |
| L1.7 | genai + Jason | Launch response pack | HN/Reddit answer notes cover PID vs LLM, deterministic safety, VPD physics, shade cloth limits, and known failures | L1.1/L1.4 |
| L1.8 | ingestor + genai + coordinator | Lesson duplicate detection support | Public lesson generator can identify duplicate candidate families by normalized lesson signature before publishing; cleanup has a reproducible query/test | L0.3 |

## P2 — Launch Cadence

| ID | Owner | Task | Acceptance | Dependencies |
|---|---|---|---|---|
| L2.1 | web + genai | Weekly "Verdify this week" page/template | Template summarizes weather, scores, lessons, failures, and repairs | P1 data surfaces |
| L2.2 | saas | Waitlist/newsletter capture | Capture path exists or explicit no-capture decision is documented | Jason product decision |
| L2.3 | coordinator | Repo/code transparency decision | Public page links repo/prompt/firmware or states why code is private | Jason decision |
| L2.4 | web | Audience-specific landing anchors | Homelab, Home Assistant, AI/agents, and greenhouse readers have direct links/sections | L0.5 |

## Jason Decisions

- [ ] Launch identity: fully attributed, attributed only on X/LinkedIn, pseudonymous on HN/Reddit, or delay until after interview loop.
- [ ] Family/home privacy boundary: names/photos/location specificity.
- [ ] Public code stance: repo public, selected snippets, or private with explanation.
- [ ] Public API stance: no public API, read-only proof API, or authenticated API.
- [ ] Indexing stance: search-index broad launch pages now vs staged/noindex raw surfaces.
- [ ] Waitlist/newsletter stance: collect emails now or defer.
- [ ] HN title and first comment.
- [ ] Launch week calendar and availability for comments.
