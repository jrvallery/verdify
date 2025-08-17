---
applyTo: "**"
description: "Telemetry ingestion guarantees"
---

# Telemetry Ingest

- Idempotency: honor `Idempotency-Key`; do not reprocess identical bodies keyed by (controller, key, body hash). Return the same result with 202 if repeated.
- Rate limit: token-bucket per controller; return `429` with `X-RateLimit-*` and `Retry-After`.
- Security: require `X-Device-Token`. Map token → controller → greenhouse.
- Do not accept controller identity in body for security; derive from token.
