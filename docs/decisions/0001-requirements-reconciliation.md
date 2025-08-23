# ADR 0001 — Requirements Reconciliation Snapshot (API.md v2.0 + DATABASE.md v2.0)

Date: 2025-08-21
Status: Accepted
Motivation: Resolve minor drifts and ambiguities between API.md and DATABASE.md v2.0.

## Decisions

1) Controller naming: label vs name
- Decision: Use `label` as authoritative (API.md). Expose `fw_version`, `hw_version`, `last_seen` in controller public schema.
- Rationale: API.md examples and field names consistently use label.

2) Device token storage table
- Decision: Use `controller_token` (DATABASE.md §2.2). Store hashed token (sha256 base64), with `expires_at`, `revoked_at`.
- Rationale: Matches DDL section and security model.

3) ETag strength and format
- Decision: Use weak ETags with prefix `W/"config:v{n}:{sha}"` and `W/"plan:v{n}:{sha}"`.
- Rationale: API.md examples prefer weak; deterministic across canonicalized JSON.

4) Auth schemes and headers
- Decision: User endpoints use Bearer JWT; device endpoints require `X-Device-Token`.
- Rationale: Non-negotiable per API.md; enforce via dependencies.

5) Timestamps & units
- Decision: Use UTC RFC3339 with trailing `Z`; metric units only.
- Rationale: API.md non-negotiable.

## Implications
- Schema DTOs and DB models will reflect `label` for controllers; migrations will include `controller_token`.
- ETag helper must canonicalize JSON and strip volatile fields before hashing.
- Security dependencies will validate headers, set session context variables for RLS later (T14).

## References
- requirements/API.md
- requirements/DATABASE.md
