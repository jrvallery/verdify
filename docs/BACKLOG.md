# Backlog — Cycle Index

Per-agent backlogs live in `docs/backlog/{agent}.md`. This file is the index + "who's on what this cycle."

## Launch command (2026-05-02)

Broad launch is now a cross-agent release train. Canonical launch gates live in [`docs/launch/README.md`](launch/README.md); task tracking lives in [`docs/backlog/launch.md`](backlog/launch.md).

Current launch posture: **not broad-launch ready** until the P0 gates are complete.

2026-05-03 update: Jason's prior-art review is tracked in [`docs/launch/prior-art-rollup-2026-05-03.md`](launch/prior-art-rollup-2026-05-03.md). It adds post-P0 launch assets around Related Work, Safety Architecture, Baseline vs Iris, builder packaging, counterfactual replay, and progressive autonomy. These are P1/P2 credibility assets, not Track A firmware blockers.

Next launch sprint: [`Launch Sprint: L1 Credibility Package`](launch/sprint-2026-05-03-l1-credibility.md). It focuses on the assets that make the broad launch defensible: related work, safety architecture, baseline evidence, FAQ/response pack, builder path, object-model diagram, and Jason-owned launch decisions.

| Owner | Launch focus | Backlog |
|---|---|---|
| `coordinator` / Jason | Privacy/security scrub, launch sequencing, identity/code-transparency decisions, final copy approval | `docs/backlog/launch.md` |
| `web` | Launch page/homepage proof path, lessons curation, daily-plan readability, OG card, Grafana public/fallback QA, metrics consumption, architecture/BOM/cost/outage pages | `docs/backlog/web.md` |
| `genai` | Lesson canonicalization semantics, planner narrative, HN response pack, weekly summary inputs | `docs/backlog/genai.md` |
| `ingestor` | Public metrics/data-health contract, plan delta support, sample export, freshness gates | `docs/backlog/ingestor.md` |
| `firmware` | Safety/control-split facts, BOM/control claims, no launch-blocking OTA unless Track A safety requires it | `docs/backlog/firmware.md` |
| `saas` | Public Grafana/access checks, waitlist/capture option, Cloudflare/Traefik/public API implications | `docs/backlog/saas.md` |

## Current cycle (as of 2026-04-20)

| Agent | Sprint | Status | Detail |
|---|---|---|---|
| `coordinator` | v1.4 landed | **Cross-cutting landed this cycle**: contract `iris-planner-contract.md` v1.4 (`c88490a`), migration 093 applied to prod (`b624f5c` + live ALTER ~08:05 MDT), Pydantic v1.4 audit fields (`d822485`), schema CI unbreak (`ec9e1df`) | `docs/backlog/cross-cutting.md` |
| `ingestor` | `sprint-25` pending | Waits on genai Sub-scope B MCP PR. Post-24.7 staging already landed: `planner_routing.py` with v1.4 defaults + OPENCLAW_{OPUS,LOCAL}_{AGENT_ID,SESSION_KEY} env vars in `config.py`. Will consume `send_to_iris(instance=)` + `acknowledge_trigger` when genai ships | `docs/backlog/ingestor.md` |
| `genai` | `sprint-3-B` pending | Sub-scope A (prompt split `_PLANNER_CORE` + `_PLANNER_EXTENDED`) committed local on `genai/sprint-3-mcp-contract` (`8bbac41`). Sub-scope B blocked on Q5 FastMCP header smoke test — Iris has `53141f39` in her queue | `docs/backlog/genai.md` |
| `web` | — | Sprint-4 Grafana panels shipped via PR #16 (`9a9a05e`) this morning. No active sprint | `docs/backlog/web.md` |
| `firmware` | phase-1+ | Phase-0 shipped as sprint-10 (`8d2656d`) + sprints 7-9 overnight (`8c64030`, `dda9057`, and the 212b1c5 fog-window fix). No active sprint queued | `docs/backlog/firmware.md` |
| `saas` | `sprint-10` shipped | Rescope landed. Open task: apply migration 090 to prod DB; unblocked (coordinator has `docker exec psql` access) but awaits operator authorization | `docs/backlog/saas.md` |
| `iris-dev` | rollout in flight | OpenClaw config done (context fix + `iris-planner-local` profile). Session boot + smoke test queued post-sprint-25. /loop operating mode is permanent | — |

## Recent ships (2026-04-19 → 2026-04-20)

In chronological order:

- `4cc5df5` ingestor: 6 cfg_* readback sensors routed for firmware sprint-3
- `c085d82` firmware/sprint-3: per-zone VPD target readback sensors
- `3b1d93a` ingestor/sprint-24-alignment: firmware sprint-2 fairness wire-up + mister_state routing + drift allowlist (+merge `b25c09e`)
- `e1b11b0` firmware/sprint-4: leak_detected debounce against pipe bleed-down
- `9e3bca3` ingestor/sprint-24.6: planner observability F14 `plan_delivery_log` + escalation (+merge `2985e78`)
- `1594cb9` ingestor sprint-25 schema PR spec (+merge `95b730d`)
- `c2bb9ba` firmware/sprint-5: replay-corpus auto-refresh + fw_version bump per deploy
- `97c4ea1` firmware/sprint-6: midnight-transition investigation (no firmware issue)
- `212b1c5` firmware/sprint-8: fix R2-3 self-mutation + midnight-wrap fog window + SAFETY_HEAT symmetry
- `8c64030` firmware/sprint-7: per-zone cycle counters for misters and drips
- `0d7445b` genai/sprint-1 squash-merged via PR #14 (9-item sprint)
- **2026-04-19 PM onwards (dual-Iris rollout)**:
- `00231cf` docs: `iris-planner-contract.md` v1.3
- `c88490a` docs: `iris-planner-contract.md` v1.4 (reconcile with `plan_delivery_log`)
- `b624f5c` coordinator: migration 093 + ai.yaml `planner_routing` / `planner_sla`
- `dda9057` firmware/sprint-9: heat2 latch + validate_setpoints asserts + R2-3 comment + SAFETY_HEAT fan
- `51c4781` ingestor/sprint-24.7: alert-hardening — OBS-3 + flap fix + MIDNIGHT watcher + sprint-25 prep (+merge `91cc335`)
- **2026-04-20 overnight**:
- `98ff9a1` ingestor/sprint-24.8: midnight_posture milestone perpetually 24h in the future (+merge `5c95ad4`)
- `8d2656d` firmware/sprint-10 phase-0: both-fan relief + dt_ms clamp + tunable margins + sealed dehum override + day/night setpoints
- **2026-04-20 morning**:
- `d822485` coordinator: `verdify_schemas/` v1.4 audit fields + migration 093 applied to prod TimescaleDB
- `6c2f5b3` genai/sprint-2 (PR #15): planner_stale threshold 8h→14h + cadence note (+merge `9a27fe7`)
- `ec9e1df` coordinator: unbreak schema CI — asyncpg importorskip on physics-invariants test
- `9a9a05e` web/sprint-4 (PR #16): Grafana panels for planner instance metrics

## How to use this

- **Agents:** start of a session, read your own `docs/backlog/{agent}.md`. Pick the highest-priority item not blocked by a handshake.
- **Coordinator:** this file gets updated at sprint kickoff + sprint end. Treat it as the shipping status board. iris-dev refreshes during /loop idle cycles.
- **Cross-cutting work** (schemas, migrations, infra, deps) lives in `docs/backlog/cross-cutting.md` and is scheduled by coordinator.

## Current findings to schedule

- **Web:** Site simplification pass reduced the public entry path and fixed corrupted text. Remaining editorial cleanup: fold detailed Climate subpages into `/climate`, finish hiding or archiving redundant reference routes, and remove drafting scaffolds from hidden reference pages.
- **Web:** Image cleanup removed broken/public backup assets and documented current photo fit. The manual image catalog now has a machine-readable manifest checked by `site-doctor`; crop-specific photos for basil/cucumbers/tomatoes remain a content acquisition issue, not a rendering blocker.
- **Web:** Raw ASCII/Mermaid diagrams were removed from hand-authored public pages. Forecast, daily-plan, plans-index, crop, and zone generated outputs now use web components instead of generated Markdown tables.

## Sprint numbering

Per-agent counters. Past global sprints (17–22) map into individual agents' histories; see each agent's scope doc for the relevant prior work.

## Known open PRs (as of 2026-04-20 ~08:50 MDT)

- **#6** DRAFT — `copilot/fix-8a7fddcf-*` (voice-note ingestion; dormant Aug 2025, no recent activity)
- All contract-v1.4-era PRs (#15, #16) merged this morning. No agent PRs outstanding.

## Contract v1.4 rollout — current state

**Phase 1 (contract + schema) ✅ complete** (iris-dev + coordinator):
- Contract `docs/iris-planner-contract.md` v1.4 landed
- Migration 093 applied to prod TimescaleDB
- Pydantic v1.4 audit fields in `verdify_schemas/`
- Routing + SLA config in `config/ai.yaml`
- OpenClaw config: context window fix + `iris-planner-local` agent profile staged in `~/.openclaw/openclaw.json`

**Phase 2 (MCP + dispatch) 🟡 in flight** (genai):
- Sub-scope A (prompt split) ✅ committed local `8bbac41`
- Sub-scope B blocked on Q5 FastMCP header smoke test — awaiting Iris

**Phase 3 (ingestor consumption) 🔴 blocked** (ingestor):
- Sprint-25 omnibus waits on Phase 2 Sub-scope B
- Pre-staged: `planner_routing.py`, env vars, new trigger_id insert path

**Phase 4 (session boot + smoke test) 🔴 blocked** (iris-dev):
- Waits on Phases 2 + 3 merging so the contract is end-to-end live

**Phase 5 (cutover) 🔴 blocked** (ingestor):
- First-week HEARTBEAT `X-Heartbeat-Readonly: true` safety window
- TRANSITION + minor FORECAST/DEVIATION → `instance="local"`

The single un-blocker for everything downstream is Iris's Q5 answer.

---

## Firmware stabilization + Phase 3 architecture (2026-04-21 → 2026-04-23)

### Context

The "fix-it-forward" spiral (sprint-15 regressions → 86°F whipsaw incident on 2026-04-21 12:40 MDT, then a 97°F / 5.03 kPa peak at 15:30 MDT with firmware held in `relief_cycle_breaker`) triggered a 4-phase stabilization plan at `.claude-agents/iris-dev/plans/yo-iris-dev-you-help-humming-stonebraker.md`. Ten coordinator PRs shipped against that plan over 72 hours.

### Ships (2026-04-21 → 2026-04-23)

- `1623e9c` **Phase 0** (#27) — replay-diff harness + 15 bulletproof invariants + CI gates (`firmware-replay-diff`, `firmware-invariants`, `no-new-fire-and-forget`, `service-restart-drift-guard`) + freeze rules (#1–#9) added to `CLAUDE.md`. Baseline green on 30-day corpus.
- `a8b96cc` **Phase 1a** (#28) — `verdify_schemas/tunable_registry.py` with `TunableDef` model + 13-entry seed + `test_registry_clamps_match_controls_yaml` drift guard. Replaces 4-place-drift tunable sync with single source of truth.
- `ba9482f` **Phase 1b** (#29) — `set_tunable` writes to `setpoint_plan` (not `setpoint_changes`), closing the 5-min overwrite gap that caused the initial sprint-15 regression. `set_plan` tightened to preserve `iris-oneshot-*` entries.
- `a140721` **Phase 2 firmware** (#30) — mode-dwell gate + symmetric cooling hysteresis behind `sw_dwell_gate_enabled=false` flag. Replay projects ≥70% transition reduction on stress windows. Gate flipped live 2026-04-21 19:14 MDT, reverted 19:50 after detecting design flaw (gate held THERMAL_RELIEF — a 90s-by-design mode — for 5 min, accelerating the breaker it was supposed to prevent).
- `24b9a34` **Phase 1c** (#31) — 10 new `cfg_*` readback sensors (mister pulse, vpd watch, mist vent coordination, fog escalation). Closes silent-push-corruption risk; `alert_monitor` now verifies landings for all Tier-1 tunables.
- `3209439` **Phase 1b.2** (#32) — registry expanded to 80 entries (every live `SETPOINT_MAP` entry minus 14 slated for deletion). 30 tier-1 planner knobs / 50 tier-2 escape hatch. Clamps validated against `controls.yaml` by drift guard; no mismatches.
- `4a8560e` **Phase 1d** (#33) — slim `_PLANNER_CORE` prompt from 86-tunable dictionary to Tier 1 only (~30 knobs). Reverses sprint-4's "planner must know every param" policy. `test_core_contains_tier1_tunable_dictionary` drift guard scoped to Tier 1.
- `b89ab21` **Phase 2 replay preview tool** (#34) — `make firmware-dwell-preview` runs replay with flag on vs off; quantifies worst-hour whipsaw reduction. First run: 47% worst-hour reduction with post-fix code.
- `a97236e` **Phase 2 firmware fix** (#35) — dwell gate exempts `THERMAL_RELIEF` from dwell via `transient_relief` preempt. Bench tests: 108→109. Not yet deployed — awaiting operator freeze-rule override + 48h bake window.
- `150c133` **PR-A** (#36) — lower `VENTILATE` mode's FW-9b fog trigger from `vpd_max_safe` (3.0 kPa) to `vpd_high_eff + fog_escalation_kpa` (~1.45 kPa production band). Closes measured 653-min/7d concurrent vent+fog gap. Intentional 10.41% replay divergence authorized via new `REPLAY_DIFF_THRESHOLD_PCT:` PR-body override mechanism added in the same PR (CI workflow change).

### Current state (2026-04-23 13:50 MDT)

- PR-A (#36) + Phase 2 fix (#35) merged to main, **undeployed**. Awaiting:
  - Operator freeze-rule override authorization per CLAUDE.md rule 2 (1 OTA/week) + rule 3 (48h bake; last OTA 2026-04-21 16:31, window opens 2026-04-23 ~16:31 MDT).
- PR-B was scoped to add breaker-VPD-emergency-override; **dropped** after verifying yesterday's breaker-latch window (17:53–18:22 MDT, VPD climbed 1.88→2.44 kPa with fog OFF under old code) would have had fog firing continuously under PR-A's lowered threshold.

### 24-hour operational assessment (2026-04-22 → 2026-04-23)

- **Band compliance 45.9%** over last 24h (1,435 samples). Temp-high 14.5%, VPD-high 19.8%.
- **Peaks:** 96.4°F / 5.09 kPa VPD at 15:30 MDT on 4/22 (vs 97°F / 5.03 on 4/21 — same pattern).
- **15 `firmware_relief_ceiling` + 15 `firmware_vent_latched` critical events** (relief cycle breaker class; Phase 2 dwell gate + PR-A target this).
- **Equipment utilization during 14:00-16:00 peak:** fans 67%, fog 20%, misters ~15% combined. User-identified gap — both cooling and humidification axes underutilized exactly when stress is highest.

---

## Phase 3 architecture decision (2026-04-23)

**Supersedes** the original plan.md Phase 3 ("9-mode → 6-mode consolidation"). User proposed **per-zone voting machines + central coordinator**. Five research agents dispatched to validate; all returned. Architecture validated, plan below.

### The problem (data-backed)

Current firmware is **mode-monolithic**: `determine_mode()` picks one of 8 modes; `resolve_equipment()` maps mode → fixed relay prescription. Modes are mutually exclusive. This forces the firmware to bifurcate on stress days:

- Temp axis wants cooling → `VENTILATE` (fans+vent, fog/mister OFF)
- VPD axis wants humidification → `SEALED_MIST` (vent closed, fog/mister ON, fans often off during mist pulses)

The AI planner has **thermostat-knob authority** only — pushes 25 distinct tunables/week (3,004 pushes), but every one is a threshold/dwell/bias. Zero actuator-level authority. Equipment selection is 100% firmware-mode-determined.

### Five research agents — findings summary

| Agent | Key finding |
|---|---|
| Zone heterogeneity | 80% of hours have temp spread >2°F across 4 zones; 51% have VPD spread >0.3 kPa. Consistent directional ranking: south hottest/wettest, north coldest/driest. Opposing-vote rate 1.1% temp / 1.8% VPD — sum-of-votes works, explicit tie-break still needed. Divergence *not* amplified by stress (active fans homogenize air). |
| Stress taxonomy | 43 stress events in 30d. **51% (22/43) are FIRMWARE_WHIPSAW** — mode churn >20/hr even at moderate thermals. **HOT_ONLY does not exist** (0/43) — every hot event is also dry. HOT_DRY events median 3.4h, all 4 recent relief_ceiling-triggering events are HOT_DRY. |
| Probe reliability | South probe: 14.35% NULL (~4-day outage dominates). North/east/west: ≤0.6%. Drift-before-death pattern: south reports lies before going dead — confidence model needs outlier-veto, not just age decay. Recommended: `confidence=100` if age ≤90s, linear decay to 0 over 90-300s, abstain after 300s. Plus ×0.5 weight when probe deviates >5°F from peer median. |
| Threshold calibration | From 7-day histogram of simulated vote aggregates (`temp_sum`, `vpd_sum` ∈ [-12, +12]): `fan1≥1` fires top 8%, `fan2≥5` top 5%, `fog≥7` (on `vpd_sum`) top 7%, `vent≥2 AND outdoor<indoor-3`, `heat1≤-2` bottom 21%, `heat2≤-6` bottom 0.7%. Replayed against yesterday's 15:30 peak — proposed thresholds would have fired fog (vpd_sum=+12 > 7) while actual firmware had fog OFF. |
| Failure modes | 12 failure modes enumerated. **8 require coordinator-level guardrails** (quorum, CRITICAL veto, per-actuator dwell, fog/vent interlock, occupancy veto, warmup window, tunable TTL, WDT-bounded tick). Reboot rate ~800/day in April makes warmup non-optional. 839 `setpoint_unconfirmed` events in 180d makes tunable TTL the highest-leverage new guardrail. |

### Validated architecture — three layers

**Layer 1 — Zone FSMs (×4, one per zone)**

Each zone emits a ballot per tick:
```cpp
struct ZoneVote {
    int8_t   temp_want;     // -3..+3 (negative = want warm, positive = want cool)
    int8_t   vpd_want;      // -3..+3 (negative = want dehum, positive = humidify)
    uint8_t  severity;      // 0=LOW, 1=NORMAL, 2=HIGH, 3=CRITICAL
    uint8_t  confidence;    // 0-100
};
```

Vote derived from that zone's temp/VPD vs that zone's band. Severity escalates with duration-out-of-band. Confidence drops with probe staleness. Outlier self-veto if deviation >5°F from peer median.

**Layer 2 — Coordinator (six-step loop each tick)**

1. **COLLECT** 4 ballots + outdoor sensors + water budget + occupancy
2. **QUORUM** check — <2 live zones → safe-shape all-off
3. **VETO** — any `CRITICAL` severity → safety-shape (SAFETY_COOL/HEAT pattern)
4. **AGGREGATE** `temp_sum = Σ sev_weight × conf × temp_want`, `vpd_sum` similarly
5. **DECIDE** each relay from rules over aggregates + per-zone outputs for misters
6. **GUARDRAILS** — per-actuator dwell, interlocks, warmup, tunable TTL, WDT

Relay rules become one-liners:
```
r.fan1 = temp_sum >= 1 && dwell_elapsed(fan1);
r.fog  = vpd_sum  >= 7 && fog_permitted && (vent_closed || vpd > vpd_critical);
r.mister_south = votes[S].vpd_want >= 1 && water_budget_ok && !occupancy_inhibit;
...
```

Each threshold is a tunable the AI can push.

**Layer 3 — Mode (derived)**

The existing 8-mode enum stays for Grafana/alerts/replay telemetry. But `derive_mode(relay_outputs, votes, state)` runs *after* relay decisions, not before. Mode is a label, not a driver.

### Coordinator guardrails (mandatory implementation constraints)

From failure-mode analysis — cannot be deferred:

1. **Quorum rule** (≥2 live zones or abstain all-off)
2. **CRITICAL veto path** (bypasses aggregation)
3. **Per-actuator dwell** (separate from per-zone hysteresis — replaces Phase 2's mode-level dwell)
4. **Fog/vent interlock** enforced post-aggregation (sprint-15.1 learning)
5. **Occupancy hard-veto** (after aggregation, no zone override)
6. **Warmup window** (≥10 ticks before any actuator ON post-reboot) — reboot rate ~800/day makes this non-optional
7. **Tunable TTL** — stale setpoints snap to defaults, emit `planner_stale` alert (highest-leverage new guardrail per 839 `setpoint_unconfirmed` events in 180d)
8. **WDT-bounded tick** (<100ms) + fail-closed all-off on exception

### Migration plan — 6 PRs

**Short-term (this week, tactical relief):**

- [x] **PR-A** (#36 merged `150c133`) — VENTILATE fog trigger at band+escalation, not safety-threshold. Closes ~38% of concurrent-gap measured in corpus.
- [x] **PR-B** dropped — PR-A handles the breaker-latch high-VPD window. Verified against 2026-04-22 17:53 event.

**Strategic (weeks 2-16, Phase 3 proper):**

- [ ] **PR-1 — Zone FSM + vote struct (pure refactor, zero behavior change).** Define `ZoneVote`, `ZoneBand`, `compute_*_want()`, `probe_confidence()`. Refactor existing per-zone logic (mist_pulse_controller) into explicit `compute_vpd_vote(zone)`. Emit votes to diagnostic sensor for shadow observation. Replay-diff zero. Tunables: 32 zone-band thresholds added (8 per zone × 4 zones) + probe confidence timings.

- [ ] **PR-2 — Coordinator skeleton + fog/mister under coordinator.** New `coordinator()` function with quorum/veto/aggregate/guardrails structure. Feature flag `use_coordinator` (default off). **Partial rollout:** fog + misters only move under coordinator control; fans/vent/heat stay mode-driven. Shadow mode 14 days. Why partial: fog/mister is where the user-visible duty-cycle gap lives and smallest blast radius.

- [ ] **PR-3 — Fan + vent + heat under coordinator + all 8 guardrails.** Full relay resolution moves to coordinator. Per-actuator dwell, quorum, warmup, occupancy, budget, interlocks, tunable TTL. Shadow mode **21 days** (longer than PR-2 because broader surface). Invariant suite expands to 30 (original 15 + 15 coordinator-specific).

- [ ] **PR-4 — `determine_mode()` retired.** Mode becomes derived label via `derive_mode(relay_outputs, state)`. Feature flag flipped `use_coordinator=true`. Delete `determine_mode()` 2 weeks after flip.

### New invariants required (added to `firmware/test/invariants.h`)

15 coordinator-specific invariants on top of the existing 15:

1. `confidence=0` → vote excluded from aggregation
2. Quorum < 2 → all moisture+heat off
3. Any CRITICAL → safety-shape fires
4. `temp_sum` arithmetic matches weighted formula
5. Fog ON ⟹ (vent closed OR vpd > vpd_critical)
6. Mister ON ⟹ water_budget_ok AND !occupancy_inhibit
7. Occupancy inhibit ⟹ 0 moisture relays
8. Heat ON ⟹ temp_sum ≤ threshold for ≥ dwell_min_ms continuously
9. Post-reboot: no actuator ON first 10 ticks
10. Stale tunable (age > TTL) → snaps to default + alert emitted
11. Coordinator tick wall-time < 100ms
12. Exception in coordinator → all-off (not last-latched)
13. Mister minutes ≥ sum of per-zone vpd_want≥1 minutes × confidence_factor
14. No actuator transitions faster than dwell_min_ms
15. Conflict resolution logged with `tiebreak_reason`

### Open decisions

- [ ] **Replace plan.md Phase 3 section.** Current doc has "6-mode consolidation" narrative; research says voting-coordinator is correct.
- [ ] **Zone bands — per-zone vs global + offset.** Per-zone = 32 new tunables; global + offset = 4 new + ~8 offsets. Research leans per-zone; cost is Iris prompt surface.
- [ ] **South probe hardware mitigation.** 14.35% NULL is independent of Phase 3 — needs a new probe / Modbus audit. Separate track alongside firmware work.
- [ ] **Iris tunable tiering.** Phase 3 adds ~32 tunables. Need to decide which are Tier 1 (daily tuning) vs Tier 2 (escape-hatch) so the prompt we just slimmed in Phase 1d doesn't rebloat.
- [ ] **Shadow-mode length.** PR-3 nominally 21 days; can we start shadow telemetry earlier (PR-1) to accumulate observation hours before PR-2 ships?

### Risks

- Coordinator surface is larger than mode-based — 25-30 new tunables, 15 new invariants, 21-day shadow bake. More room for silent-push corruption (mitigated by guardrail #7 tunable TTL).
- Per-zone bands require per-zone probe reliability; south probe is unreliable. Either fix the probe or weight south's votes lower by default until fixed.
- Mode-derived telemetry may break downstream consumers (alert_monitor rules, scorecard, Iris's mental model). Needs audit during PR-4.
- Reboot rate is ~800/day — warmup guardrail MUST be robust, otherwise every reboot creates a 10-tick all-off window that could briefly lose a stress event. Might need to persist `last_healthy_vote` across boot.

### Timeline (calendar weeks)

```
W1 (now):   PR-A shipped ✅ | PR #35 + PR-A deploy when bake opens
W2-3:       PR-1 refactor + shadow vote telemetry
W4:         PR-1 bake
W5-6:       PR-2 coordinator skeleton (fog+misters)
W7-8:       PR-2 14-day shadow
W9-10:      PR-3 full relay coordinator
W11-13:     PR-3 21-day shadow
W14:        Flip use_coordinator=true
W16:        PR-4 delete determine_mode
```

Total: ~16 weeks (vs. original plan's 8 weeks for 6-mode consolidation). Longer because architecture is more ambitious; validates more thoroughly.

### Known open firmware PRs (as of 2026-04-23 13:50 MDT)

- PR #35 (Phase 2 fix) + PR #36 (PR-A) both merged but awaiting combined OTA deploy.
- No outstanding firmware PRs.
