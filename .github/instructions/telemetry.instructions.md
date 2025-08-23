---
applyTo: "**"
description: "Telemetry ingestion guarantees"
---

# Telemetry Ingest

- Require `X-Device-Token` for telemetry/config fetch. 401/403 if missing/bad.
- Sensors endpoint: batch accepts `readings[]` with strict enum validation; accept bulk, reject invalid items with 422.
- `Idempotency-Key`: dedupe identical payloads + key; re‑serve stored response.
- Status endpoint: ensure schema parity with docs; record plan/config version, override/fallback flags.
- Config fetch by controller device name honors `If-None-Match` and returns `ETag`.
- Plan payload.version must equal entity version on update; reject mismatches (409/422). Single active plan enforced.