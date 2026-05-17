# Backlog: Verdify business refocus

Coordinator-owned queue for the 2026-05 refocus from "public AI greenhouse / possible SaaS" to **Verdify as a consulting brand with the Longmont greenhouse as the public lab proof asset**.

This is a strategy backlog, not an operational sprint. Track A greenhouse reliability still outranks every item here.

## Decision frame

Verdify should stay the parent brand.

Recommended public positioning:

> Verdify builds bounded AI agents for real-world operations.

Recommended commercial line:

> Agentic automation for physical operations.

Brand architecture:

| Layer | Name | Role |
|---|---|---|
| Parent brand | Verdify | Company, public identity, commercial umbrella |
| Proof asset | Verdify Lab / The Longmont AI Greenhouse | Public evidence, telemetry, failures, lessons |
| Consulting arm | Verdify Services or Verdify Systems | Paid advisory, implementation, managed automation |
| Product/IP later | Verdify Platform | Only if reusable software becomes a real product |
| Vertical labels | Verdify CEA, Verdify Physical Ops, Verdify Workflow Automation | Website taxonomy, not separate brands |

One-site decision:

- Keep the commercial story, lab, evidence, and architecture on `verdify.ai`.
- Do not create a second consulting brand or separate marketing domain now.
- Use the greenhouse as the flagship proof point, not as the whole company category.

## Non-negotiables

- **Track A first.** No refocus task can justify risky firmware, schema, or production changes unless it also protects the live greenhouse.
- **No overclaiming.** Verdify sells bounded, auditable automation. It does not claim autonomous control, proven yield uplift, or production SaaS maturity until evidence exists.
- **AI does not own relays.** Public language must keep the control split precise: AI proposes bounded tactics; deterministic controllers and validators enforce safety; telemetry verifies outcomes.
- **Greenhouse remains public evidence.** The lab pages, daily plans, failures, scorecards, and telemetry should become more useful commercially, not disappear behind a marketing facade.
- **Repo splits must reduce risk.** Separate GitHub repos only when the deploy path, secrets posture, and ownership model become clearer than the current monorepo.

## P0 - Decisions and risk gates

| ID | Owner | Task | Acceptance |
|---|---|---|---|
| R0.1 | coordinator + Jason | Ratify the refocus decision record | One short internal doc states: Verdify is the brand, `verdify.ai` is one integrated site, greenhouse is Verdify Lab, SaaS is product-later, consulting is the commercial path |
| R0.2 | coordinator | Track A impact review | List which refocus tasks touch firmware, DB, MCP, public API, Grafana, or deploy scripts; anything operational gets routed through the existing agent gates |
| R0.3 | Jason + attorney | Trademark/name clearance | Attorney or formal clearance process reviews Verdify / Verdify Systems / Verdify AI classes, geography, likelihood of confusion, domains, and social handles before formal entity launch |
| R0.4 | coordinator + web | Public claim inventory | Current site copy is inventoried for "greenhouse-only", "not commercial", "autonomous", "self-improving", yield/profit, SaaS, and lab-only language |
| R0.5 | coordinator | GitHub/repo inventory | Current repos, remotes, nested `verdify-site`, vault source, runtime deploy paths, secrets, CI, and public/private status are documented before any split |
| R0.6 | coordinator | Agent model decision | Current agents are mapped to the refocus: which stay operational, which own commercial site/content, and whether `saas` becomes "product later" instead of active multi-tenant work |

Trademark note: a quick public check shows another [`verdify.tech`](https://www.verdify.tech/about) business using Verdify for personalized nutrition software, and the USPTO's [online trademark tools](https://www.uspto.gov/trademarks/basics/online-tools) are the authoritative place to search active/inactive records. This backlog item is not legal advice; it is a gate to get real clearance before committing the company/entity name.

## P1 - Commercial website layer

Goal: make `verdify.ai` read as a real-world automation company with a public greenhouse proof point.

| ID | Owner | Task | Acceptance |
|---|---|---|---|
| W-R1.1 | web + coordinator | New site information architecture | Top navigation supports Services, Solutions, Lab, Evidence, Architecture, About, Contact without breaking existing proof routes |
| W-R1.2 | web + Jason | Homepage repositioning | First viewport leads with bounded AI agents for real-world operations, then immediately points to the Longmont AI greenhouse as public proof |
| W-R1.3 | web + Jason | `/services` overview | Page explains advisory, implementation, and managed automation offers without sounding like generic AI consulting |
| W-R1.4 | web + Jason | `/services/agentic-ops-assessment` | One concrete paid offer exists with scope, outcomes, timeline, buyer fit, and inquiry CTA |
| W-R1.5 | web | Solutions pages | Publish initial pages for physical operations, workflow automation, and controlled environments |
| W-R1.6 | web + genai + firmware | Bounded AI architecture page | Page explains deterministic safety, dispatcher/validator pattern, audit trails, human approval, and physical-control boundaries |
| W-R1.7 | web + saas/coordinator | Contact/assessment intake | Decide static email, simple form, or external scheduling; if a form ships, spam/secrets/privacy handling is explicit |
| W-R1.8 | web | Redirect/route cleanup | Current `start/*`, `reference/*`, `intelligence/*`, `data/*`, and greenhouse routes remain reachable with clear commercial-era navigation |

Suggested top-level site story:

1. Bounded AI agents for real-world operations.
2. Public proof: Verdify Lab, the Longmont AI greenhouse.
3. What Verdify does: physical ops automation, workflow automation, controlled-environment systems.
4. Why Verdify is different: deterministic safety, audit trails, human approval, measurable outcomes.
5. Offers: assessment, pilot, managed AgentOps.
6. Buyers: local businesses, facilities teams, labs, growers, natural products, light industrial, nonprofits/schools.
7. CTA: book an Agentic Ops Assessment.

## P1 - Consulting business package

| ID | Owner | Task | Acceptance |
|---|---|---|---|
| B-R1.1 | Jason | Offer ladder | Define 3 offers: assessment, implementation pilot, managed AgentOps/retainer |
| B-R1.2 | Jason + coordinator | Pricing guardrails | Initial pricing bands, minimum engagement, payment terms, and what Verdify will not take on are written down |
| B-R1.3 | Jason + web | Consulting deck | 8-12 slide deck uses Verdify Lab as proof, explains bounded automation, and ends in one clear assessment offer |
| B-R1.4 | Jason | Ideal customer profile | Rank first outreach targets: Boulder County operators, facilities/HVAC-adjacent teams, labs, natural products, controlled environments, workflow-heavy SMBs |
| B-R1.5 | Jason + coordinator | Due diligence packet | Create a shareable packet: architecture, sample dashboard, example plan, scorecard, failure story, security/privacy stance, and engagement process |
| B-R1.6 | Jason | Outreach CRM | Track prospects outside the ops repo; no customer data should land in the greenhouse operations repository |

## P1 - GitHub, repo, and project organization

Goal: separate public/commercial assets from live greenhouse operations without making deploys more fragile.

Recommended target shape:

| Repo/project | Visibility | Purpose | Notes |
|---|---|---|---|
| `verdify-lab` or current `verdify` | Private by default | Live greenhouse ops: ingestor, firmware, MCP, DB, Grafana, operational scripts | Keep this as the source of truth until split work is proven |
| `verdify-site` | Public or private, decided after scrub | Marketing/lab website runtime and Quartz customizations | A nested `verdify-site` repo already exists; choose one canonical site source before more edits |
| `verdify-public-data` | Public later | Scrubbed sample datasets, scorecard exports, selected artifacts | Generated from ops, never hand-edited with secrets |
| `verdify-firmware` | Public later, maybe subset | ESP32 controller reference implementation | Do not extract during firmware freeze unless read-only packaging is safe |
| `verdify-agents` | Private | Agent playbooks, scope docs, operational memory templates | Keep customer and greenhouse secrets out |
| `verdify-platform` | Deferred | Reusable product/software if consulting reveals repeatable demand | Do not build before buyer proof |

| ID | Owner | Task | Acceptance |
|---|---|---|---|
| O-R1.1 | coordinator | Repo boundary decision | Decide which repos exist now, later, or never; document source of truth for each deploy path |
| O-R1.2 | coordinator + web | Site repo canonicalization | Resolve drift between repo-owned `site/`, nested `verdify-site`, vault content, and `/srv/verdify/verdify-site`; one path is canonical |
| O-R1.3 | coordinator | Public/private visibility matrix | For every repo/artifact, document visibility, license, secret risk, customer/privacy risk, and release trigger |
| O-R1.4 | coordinator | Secret/privacy scrub checklist | Before any repo opens, run a checklist for `.env`, local IPs, home/security details, family names/photos, credentials, raw logs, and customer data |
| O-R1.5 | coordinator + web | Site CI split | Website build/preview can run without greenhouse secrets, live DB, or production Grafana credentials |
| O-R1.6 | coordinator | GitHub Projects layout | Create one org-level project board with tracks: Track A Ops, Commercial Site, Consulting Package, Repo Split, Lab Evidence, Product Later |
| O-R1.7 | coordinator | Agent scope update plan | Prepare a later PR to update `docs/agents/*` after repo/project boundaries are decided |

## P2 - Verdify Lab evidence upgrades

Goal: turn the greenhouse into a stronger sales proof point without pretending it is the product.

| ID | Owner | Task | Acceptance |
|---|---|---|---|
| L-R2.1 | web + genai | Weekly lab artifact | Publish "Verdify this week": weather faced, goals, plans, telemetry, score, failures, repairs, lessons |
| L-R2.2 | web + ingestor + genai | Lifecycle case study | One canonical example shows forecast -> plan -> tunables -> telemetry -> score -> lesson |
| L-R2.3 | ingestor + web | Public evidence dataset | Scrubbed sample exports are generated reproducibly and linked from the evidence pages |
| L-R2.4 | firmware + web | Safety/control receipts | Public architecture pages cite firmware loop cadence, relay ownership, fallback behavior, and freeze protocol accurately |
| L-R2.5 | genai + web | Lessons and failure library | Lessons are framed as evidence-backed operational learning, not vague self-improvement |
| L-R2.6 | web + Jason | Lab naming pass | Site consistently uses "Verdify Lab" / "Longmont AI Greenhouse" for the proof asset |

## P2 - Product-later extraction

Goal: avoid burning time on SaaS before consulting demand identifies repeatable product.

| ID | Owner | Task | Acceptance |
|---|---|---|---|
| P-R2.1 | saas + coordinator | Reclassify SaaS backlog | Existing multi-tenant SaaS tasks are marked product-later unless they are needed for site/contact reliability or Track A safety |
| P-R2.2 | coordinator + Jason | Reusable engagement patterns | Capture repeatable pieces from consulting work: intake rubric, data connector checklist, telemetry scorecard, bounded-agent architecture, security review |
| P-R2.3 | saas | Cloud posture cleanup | Keep only cloud work that supports reliability, public site, or future optional product extraction; avoid cloud-only greenhouse cutover unless operationally justified |
| P-R2.4 | genai + coordinator | Client-safe agent architecture | Define which planner/agent components are generic enough for client work and which are greenhouse-specific |

## Suggested first execution slice

Do these in order:

1. Complete R0.3 trademark/name clearance enough to know whether "Verdify Systems" / "Verdify AI" is viable.
2. Complete R0.5 and O-R1.2 so the website source-of-truth question is settled before commercial copy moves.
3. Ship W-R1.1/W-R1.2 as a small site IA + homepage PR.
4. Ship W-R1.3/W-R1.4 as the first commercial offer PR.
5. Ship L-R2.1 as the first weekly lab artifact so the proof cadence supports outreach.
6. Pause broad SaaS/multi-tenant work via P-R2.1 until at least one consulting assessment is sold or a concrete product pattern emerges.

## Success criteria

- A new visitor understands within one screen that Verdify is a real-world automation company, not just a greenhouse diary.
- The greenhouse remains inspectable as public evidence: telemetry, plans, scorecards, failures, and lessons still have first-class routes.
- The first paid offer can be explained in one sentence and linked from the homepage.
- Public claims match current evidence and do not imply direct LLM relay control or proven yield/profit outcomes.
- Repo/project boundaries make secrets safer and agent work clearer, without destabilizing the live greenhouse deploy path.
