# Launch Sprint: Readiness and Release Freeze

Date: 2026-05-04
Owner: coordinator / Jason, with web as public-experience lead
Target window: 2-3 working days plus launch-day comment coverage

## Goal

Move Verdify from "credible and safe to show" to "ready for broad HN/Reddit launch."

The site has the P0 hardening and the major credibility pages. This sprint is not about adding another large page set. It is about removing the remaining launch risks: data-health drift, branch/release drift, final copy uncertainty, and unverified public proof paths on launch-day browsers.

## Current Facts

- P0 launch gates are complete.
- Public credibility assets are live in the vault: Safety Architecture, Related Work, Build Notes, FAQ, Baseline vs Iris, architecture SVG, object-model SVG, sample CSVs, and curated lessons.
- `make site-doctor` passed on 2026-05-04 MDT after the release-merge pass with 88 pages, 209 Grafana iframes across 29 pages, 496 internal links, and 0 findings.
- `https://api.verdify.ai/api/v1/public/home-metrics` is reachable and returns live proof data. The launch-readiness check now reports `data_health_status=warn` with 0 open critical/high alerts.
- API/OpenAPI and Grafana d-solo surfaces return noindex headers.
- `web/sprint-4-iris-instance-panel` has merged `origin/main`; push or PR the launch-readiness delta before launch.
- The frozen launch package is `docs/launch/frozen-launch-package-2026-05-04.md`.
- The first weekly cadence artifact is `/updates/`.

## Sprint Outcomes

| ID | Owner | Outcome | Done when |
|---|---|---|---|
| LR-1 | coordinator + ingestor + web | Data-health launch gate | Done: public proof API reports `warn`, with 0 open critical/high alerts. |
| LR-2 | web + coordinator | Branch/release consolidation | Done locally: `origin/main` merged; push or PR remains before broad launch. |
| LR-3 | web + saas/coordinator | Public proof certification | Done: homepage, Safety Architecture, Related Work, Build Notes, FAQ, Baseline vs Iris, Updates, sample CSVs, API headers, Grafana d-solo, and OG/Twitter metadata pass live smoke checks. |
| LR-4 | Jason + coordinator | Launch package freeze | Done: frozen package records HN title, first comment, X/LinkedIn lede, subreddit angles, identity posture, code stance, waitlist stance, and launch calendar. |
| LR-5 | Jason + web | Operations clip decision | Done: clip is explicitly deferred unless recorded before posting; no page depends on it. |
| LR-6 | web + genai | First weekly cadence artifact | Done: `/updates/` exists with first launch-readiness note and reusable update template. |

## Work Plan

### Day 0 - Stabilize the launch board

- Update `docs/launch/README.md`, `docs/backlog/launch.md`, and `docs/backlog/web.md` so P0/P1 status matches the live site and the remaining launch gates are explicit.
- Merge `origin/main` into `web/sprint-4-iris-instance-panel` and keep this as the launch-readiness branch.
- Verify public data-health is `warn` or better with 0 open critical/high alerts.

### Day 1 - Close proof and release gaps

- Keep data-health at `warn` or better.
- Ensure active vault pages are represented by generator/source docs where appropriate.
- Rerun `make site-doctor`.
- Smoke check live pages and headers:
  - `https://verdify.ai/`
  - `/intelligence/safety-architecture/`
  - `/intelligence/related-work/`
  - `/intelligence/build-notes/`
  - `/intelligence/faq/`
  - `/evidence/baseline-vs-iris/`
  - `/updates/`
  - `/static/data/verdify-sample-7d-climate.csv`
  - `https://api.verdify.ai/api/v1/public/home-metrics`
  - `https://api.verdify.ai/api/v1/public/data-health`
  - `https://graphs.verdify.ai/d-solo/site-home/?orgId=1&panelId=2&theme=dark`

### Day 2 - Freeze launch copy

- Freeze HN title and first comment in `docs/launch/frozen-launch-package-2026-05-04.md`.
- Freeze X/LinkedIn soft-launch thread.
- Freeze subreddit-specific ledes; do not cross-post identical copy.
- Use project-first attribution through Jason's normal technical identity unless deliberately changed before posting.
- Treat the operations clip as explicitly deferred unless recorded before posting.
- Publish the first "Verdify this week" update so the launch has a follow-up cadence.

## Exit Criteria

- Live data-health is `ok`/`warn`.
- `make site-doctor` passes with 0 findings after branch consolidation.
- Public live URL smoke checks pass and API/Grafana noindex headers are still present.
- Branch status is not ambiguous: launch branch has merged `origin/main` and must be pushed or PR'd before posting.
- Jason decisions are recorded in `docs/backlog/launch.md`.
- Launch copy avoids "first," "largest," "fully autonomous," direct LLM relay control, yield/profit claims, and off-grid solar claims.
- The launch response pack and first weekly cadence artifact exist outside chat.

## Risks

| Risk | Mitigation |
|---|---|
| Data-health remains `fail` on launch day | Either delay broad launch or lead with the degraded proof state as an honest operational incident. Do not show a fail state as normal. |
| Branch drift hides launch fixes | Rebase/merge intentionally or retire the stale branch before editing more source. |
| Launch thread fixates on direct LLM control | Keep Safety Architecture above the fold and use the response pack language: Iris plans; firmware enforces. |
| Related-work claims get challenged | Cite primary sources and avoid first/best/largest comparisons. |
| Video delays launch | Treat the clip as useful but not a code blocker; explicitly defer if it slips. |
| Track A greenhouse work interrupts launch | Operational safety wins. Pause marketing launch if live critical/high alerts represent real greenhouse risk. |
