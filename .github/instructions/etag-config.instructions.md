---
applyTo: "**"
description: "ETag & config/plan delivery"
---

# ETag + Materialization

- Generate **strong ETags**: `config:v<version>:<sha8>` / `plan:v<version>:<sha8>`.
- Support `If-None-Match` → return `304` when unchanged.
- `Last-Modified` header should reflect materialization time.
- Config/Plan payloads must match schemas; exclude volatile fields from hash.
