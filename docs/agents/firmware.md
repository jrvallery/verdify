# Agent: `firmware`

ESP32 controller code, build pipeline, replay validation, OTA, sensor health.

## Owns

- `firmware/**/*.h`, `firmware/**/*.cpp`, `firmware/**/*.yaml`, `firmware/test/**`
- Firmware build + compile (`make firmware-check`)
- Replay corpus validation (`firmware/test/test_greenhouse_logic.cpp` + golden CSV)
- OTA auto-rollback (Sprint 17 work)
- Firmware versioning, heating diagnostics, override flag emission
- Sensor staleness exclusion + probe health

## Does not own

- The DB tables firmware writes to (that's `ingestor` — ESP32 → ingestor → DB)
- The planner tunables firmware applies (that's `genai` — planner emits, firmware enforces)
- The drift guards that assert firmware ↔ schema alignment (shared `verdify_schemas/` — route to coordinator)

## Handshakes

| With agent | When | Protocol |
|---|---|---|
| `ingestor` | Adding a new sensor or override flag that needs a DB column | Schema + migration via coordinator first, then firmware emits, then ingestor reads |
| `genai` | Changing which tunables the planner controls | Planner agent owns the tunables list (`verdify_schemas/tunables.py`); firmware reads it — don't add tunables unilaterally |
| `coordinator` | Any change to `ALL_TUNABLES`, `EquipmentId`, `override_events` shape | Coordinator merges the schema change; firmware PR lands after |

## Gates

**Replay is a permanent gate for firmware changes.** Any structural change to `greenhouse_logic.h` must pass `firmware/test/test_greenhouse_logic.cpp` *and* replay against 8 months of real telemetry (see `CLAUDE.md` at repo root — `make firmware-check`). See `docs/BCDR-AND-OPERATIONS.md` and the prior `docs/BACKLOG-SAAS-ALIGNED.md` sprint notes for context on why.

## Ask coordinator before

- Adding an override flag that isn't already in `firmware/lib/greenhouse_types.h`
- Changing the 7-mode state machine's transition logic (physics invariant territory)
- Bumping firmware version in a way that requires ingestor / planner code changes
- Touching `controls.yaml` in ways that rename or remove entities (entity_map.py depends on these)

## Recent arc (pre-agent-org, for context)

- Sprint 15: ESP32 reboot resilience, firmware hardening
- Sprint 16: OBS-1e silent-override event emission
- Sprint 17: Sensor fault resilience, per-probe staleness, OTA auto-rollback
- Sprint 18: Deterministic dispatch (Milestone A2)

See `docs/backlog/firmware.md` for next work.
