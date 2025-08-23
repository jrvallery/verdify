# 0001 — Requirements Reconciliation Snapshot (v2.0)

Date: 2025-08-21
Status: Accepted

Scope: Aligns minor ambiguities between API.md and DATABASE.md v2.0. API.md is authoritative for wire format; DATABASE.md is authoritative for DDL.

Decisions

- Controller identity label vs name
  - Use label on the wire (API.md authoritative). Persist both label (display) and unique device_name slug for constraints.
  - Expose fw_version, hw_version, last_seen in controller representations.

- Device token store naming
  - Use controller_token table per DATABASE.md §2.2. Store hashed tokens (sha256 base64), with expires_at and revoked_at. Enforce single active per controller unless rotated.

- ETag strength and format
  - Use weak ETags: W/"config:v{n}:{sha}" and W/"plan:v{n}:{sha}". Compute sha over canonical JSON (sorted keys, stable array ordering).

- Error envelope
  - Standardized shape: { error_code, message, details?, timestamp, request_id } across all handlers, mapping FastAPI/validation and DB conflicts accordingly.

- Timestamps and units
  - All timestamps UTC ISO-8601 with trailing Z. Metric units only on wire and storage.

- Endpoint prefixing
  - All endpoints under /api/v1.

- Auth schemes
  - User JWT (Authorization: Bearer). Device auth via X-Device-Token.

Rationale

These choices match provided examples and ensure stable client/server behavior and deterministic caching for config/plan.
