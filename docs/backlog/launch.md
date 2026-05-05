# Backlog: launch

Cross-agent launch board owned by coordinator / iris-dev. This file tracks launch-critical work that cuts across agent scopes. The canonical launch narrative and gates live in [`docs/launch/README.md`](../launch/README.md).

## Active Sprint - Launch Readiness and Release Freeze

Sprint plan: [`docs/launch/sprint-2026-05-04-launch-readiness.md`](../launch/sprint-2026-05-04-launch-readiness.md).

Goal: move from P0-safe/P1-credible to broad-launch ready by closing operational data-health, branch/release drift, live proof certification, and Jason-owned launch-copy decisions.

Current launch posture:

- P0 gates are complete.
- Major P1 public credibility pages are live in the vault: Related Work, Safety Architecture, Build Notes, FAQ, Baseline vs Iris, sample CSVs, architecture SVG, object-model SVG, and curated lessons.
- `make site-doctor` passed on 2026-05-04 MDT after the release-merge pass with 88 pages, 209 Grafana iframes, 496 internal links, and 0 findings.
- Public proof API is reachable and reports `data_health_status=warn` with 0 open critical/high alerts; remaining warnings are visible in `data_health_warnings`.
- Web branch/release state: `web/sprint-4-iris-instance-panel` has merged `origin/main`; push or PR the launch-readiness delta before launch.

Immediate next steps:

1. Keep public data-health at `warn` or better; route any new critical/high alert before broad launch.
2. Use [`docs/launch/frozen-launch-package-2026-05-04.md`](../launch/frozen-launch-package-2026-05-04.md) for HN title, first comment, soft-launch thread, subreddit angles, identity posture, and launch calendar unless Jason deliberately changes it.
3. Treat the operations clip as explicitly deferred unless Jason records it before posting.
4. Maintain the first [Verdify Weekly Operations Log](/updates/) cadence artifact.

## P0 — Launch Blockers

| ID | Status | Owner | Task | Acceptance | Dependencies |
|---|---|---|---|---|---|
| L0.1 | done | coordinator + Jason | Privacy/security scrub of public pages and dashboards | Public site and generated HTML expose no children's names, local IPs, camera/security layout, raw dollar-sign rendering, ambiguous cloud/solar claims, or sensitive details; API/Grafana are noindex | Jason attribution decision remains |
| L0.2 | done | web + ingestor | Add live homepage or `/launch` proof cards | Homepage renders live proof from public read-only API: indoor temp, VPD, outdoor temp, planner score, plan count, data health; stale data is labeled | Public metrics API |
| L0.3 | done | web + genai | Curate lessons page and raw split | Default page shows canonical lessons; duplicate bias/mist families collapsed with validation counts; raw machine stream remains labeled behind details | Lesson canonicalization rule implemented |
| L0.4 | done | web + genai | Make daily plan pages readable | Representative page `/plans/2026-04-29` leads with score, hypothesis, result/rationale, changed parameters; unchanged parameter dump hidden behind details/raw | Plan renderer delta logic |
| L0.5 | done | web | Launch story and hero number | Homepage has real greenhouse visuals, control-split line, live proof cards, known-limits/evidence paths, and first-visit guided path | Jason can still tune final copy |
| L0.6 | done | web | Social preview / OG card | `og:title`, `og:description`, `og:image`, Twitter card tags verified for verdify.ai; image uses the snow greenhouse photo | Image chosen |
| L0.7 | done | web + saas/coordinator | Public Grafana proof path | Grafana health, anonymous dashboard boot, d-solo routes, renderer path, and JS app bundles verified; human mobile/in-app smoke remains recommended before HN | Grafana/Traefik config |
| L0.8 | done | web | Copy correctness pass | Dollar signs render as USD; "solar-powered" replaced with solar-aligned/grid/gas wording; "self-improving" softened on launch-critical pages | None |
| L0.9 | done | coordinator + web + saas | Public API lockdown | Public API proof routes are read-only; mutating POST/PUT/DELETE routes require `X-Verdify-API-Key`; `/docs` is hidden by default and `/openapi.json` is noindexed for contract checks | Public API strategy |
| L0.10 | done | coordinator + web + saas | Robots/indexing policy | Root `robots.txt`, canonical metadata, Grafana/API headers, and Traefik `X-Robots-Tag` agree; raw/API/Grafana surfaces noindex | Indexing decision |
| L0.11 | done | ingestor + coordinator + web | Public metrics/freshness contract | Public API returns homepage counters, latest plan/score, climate freshness, active alerts, and data-health status; web has no hard-coded proof numbers | Public API strategy |
| L0.12 | done | coordinator + ingestor + web | Operational data-health launch gate | Public proof API reports `warn` with 0 open critical/high alerts; any future critical/high alert pauses broad launch until routed | Public API check, 2026-05-04 evening MDT |
| L0.13 | done | web + saas/coordinator | Final public proof certification | `make site-doctor` passes with 0 findings; live smoke checks pass for core pages, Updates, sample CSV, API noindex, Grafana noindex, and OG/Twitter metadata | 2026-05-04 evening MDT |

## P1 — Strong Launch Assets

| ID | Status | Owner | Task | Acceptance | Dependencies |
|---|---|---|---|---|---|
| L1.1 | done | web + firmware + ingestor + genai | Architecture SVG | Shareable diagram shows ESP32 -> ingestor/Home Assistant -> TimescaleDB -> OpenClaw/Iris local Gemma4 + cloud peer -> plan_journal -> dispatcher -> ESP32; labels evidence loop and safety split without brittle table/view/dashboard counts | Agent factual review |
| L1.2 | done | web + firmware + Jason | Bill of materials | Sensor/probe/ESP32/relay/mister/heater list exists with enough detail for homelab readers | Privacy scrub |
| L1.3 | done | web + saas/coordinator | Cost callout | Public page gives one clear operating-cost/API-cost summary without corrupted dollar signs | Current cost query |
| L1.4 | done | web + coordinator | Outage story | Evidence page owns April 22-25 zero-plan/VPD-stress run as a transparent incident, not an unexplained archive gap | Data pull from plan archive |
| L1.5 | done | ingestor + web | Public sample dataset | 7-day climate CSV and 30-day plan-outcome CSV are scrubbed, generated by script, and linked from data/evidence pages | Privacy scrub |
| L1.6 | deferred | Jason + web | 30-90s dashboard clip | Timestamped screen recording is useful but not launch-blocking; frozen package explicitly allows launch without it | `docs/launch/frozen-launch-package-2026-05-04.md` |
| L1.7 | done | genai + coordinator + Jason | Launch response pack | HN/Reddit answer notes cover PID vs LLM, deterministic safety, VPD physics, shade-cloth limits, Mycodo/HAGR/Koidra/AgroNova/iGrow comparisons, and what "self-improving" does and does not mean | `docs/launch/launch-response-pack.md` |
| L1.8 | done | ingestor + genai + coordinator | Lesson duplicate detection support | Public lesson generator identifies duplicate candidate families by normalized lesson signature before publishing | L0.3 |
| L1.9 | done | web + coordinator | Related Work page | Public page positions Verdify against AgroNova, IOGRUCloud, Hydro0x01, HAGR, Mycodo, iGrow, GreenLight-Gym, FarmBot/OpenAg, WUR, and commercial CEA, with externally verified primary-source claims | `/intelligence/related-work` |
| L1.10 | done | web + firmware + genai | Safety Architecture page | Page "Why the AI does not control relays" explains LLM tactical intent, dispatcher validation, ESP32 enforcement cadence, hard safety guards, cloud/wifi failure behavior, and scorecard closure | `/intelligence/safety-architecture` |
| L1.11 | done | ingestor + web + coordinator | Baseline vs Iris score table | Public table compares baseline and Iris periods for temp compliance, VPD compliance, cumulative stress-axis hours/day, water/day, estimated electric energy/day, cost/day, and planner score, with definitions and caveats | `/evidence/baseline-vs-iris`; default baseline = 2026-04-22..25 outage |
| L1.12 | done | web + coordinator | Related-work comparison table | Publish a verified table comparing control style, AI role, public telemetry, public scorecards, and public lessons across peer projects | `/intelligence/related-work` |
| L1.13 | done | genai + web + coordinator | "Why not RL / direct LLM control?" FAQ | FAQ gives concise technical answers for deterministic safety, VPD physics, intrinsic interpretability, counterfactual replay roadmap, and why RL is future simulator work, not launch framing | `/intelligence/faq` |
| L1.14 | done | web + firmware + ingestor + genai | Builder / reference implementation path | Public build notes include BOM, wiring/equipment overview, MQTT topic examples, DB table overview, example daily plan JSON, example scorecard JSON, what is not production-safe yet, and code-transparency stance | `/intelligence/build-notes` |
| L1.15 | done | web + genai | Verdify object-model diagram | Static diagram shows Crop profile -> target bands/climate recipe -> forecast/state -> Iris plan -> tunables -> ESP32 state machine -> telemetry -> scorecard -> lessons -> next plan | `/static/verdify-object-model.svg` |

## P2 — Launch Cadence

| ID | Owner | Task | Acceptance | Dependencies |
|---|---|---|---|---|
| L2.1 | done | web + genai | Weekly "Verdify this week" page/template | Template summarizes weather, scores, lessons, failures, and repairs | `/updates/` |
| L2.2 | saas | Waitlist/newsletter capture | Capture path exists or explicit no-capture decision is documented | Jason product decision |
| L2.3 | coordinator | Repo/code transparency decision | Public page links repo/prompt/firmware or states why code is private | Jason decision |
| L2.4 | web | Audience-specific landing anchors | Homelab, Home Assistant, AI/agents, and greenhouse readers have direct links/sections | L0.5 |
| L2.5 | coordinator + firmware + genai | Progressive autonomy roadmap | Verdify is placed on an L1-L4 autonomy ladder with deployment safeguards and upgrade gates | done in `/intelligence/safety-architecture` |
| L2.6 | genai + coordinator | Counterfactual replay roadmap | Public roadmap explains replaying recent telemetry with alternate tunables before considering RL or simulator-trained policies | L1.13 |
| L2.7 | web + genai + ingestor | Full daily lifecycle artifact | One public example shows forecast -> plan -> tunables -> telemetry -> score -> lesson, with sample JSON/CSV artifacts | L1.14 |
| L2.8 | web + ingestor + Jason | Crop-steering maturity roadmap | Public roadmap covers substrate sensors, dryback/irrigation windows, pH/EC/DO, DLI correction, and shade cloth automation without implying these are complete | L1.14 |
| L2.9 | genai + ingestor + web | Plan-memory semantic retrieval hardening | If Verdify publicly claims semantic search over previous plans, add explicit embeddings or retrieval indexes for `plan_journal` outcomes; until then, public copy should describe prior plans as structured memory | Current implementation exposes plan history through structured context, scorecards, and lessons |
| L2.10 | web + coordinator | Branch/release cleanup | Launch source has merged `origin/main`; push or PR the launch-readiness delta before broad launch | Launch-readiness sprint |

## Jason Decisions

- [x] Launch identity: project-first, attributed through Jason's normal technical identity unless deliberately changed before posting.
- [x] Family/home privacy boundary: no family names, camera model details, local IPs, private security layout, or extra home-specific details in launch comments.
- [x] Public code stance: selected public artifacts now; full repo/prompts private pending scrub, with explanation on Build Notes.
- [x] Public API stance: read-only proof API; writes require key.
- [x] Indexing stance: search-index broad launch pages; raw/API/Grafana surfaces noindex.
- [x] Waitlist/newsletter stance: defer capture for launch; avoid adding a form/secrets path before HN/Reddit.
- [x] HN title and first comment: frozen in `docs/launch/frozen-launch-package-2026-05-04.md`.
- [x] Launch week calendar and availability for comments: Tuesday, May 5, 2026 or Wednesday, May 6, 2026 after final smoke check; first 4-6 hours need live comment coverage.
- [x] Baseline period for "Baseline vs Iris" comparison: 2026-04-22..25 planner-offline window vs 2026-04-26..2026-05-02 Iris-online window.
- [x] External related-work citation comfort level and whether to name commercial comparators directly: cite primary-source/public pages and avoid first/best/largest claims.
- [x] Climate-recipe terminology: use sparingly where defined by crop target bands; do not lead launch copy with reproducibility claims.
