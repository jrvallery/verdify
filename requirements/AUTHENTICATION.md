# Authentication & Authorization Specification

## Overview

This specification defines end-to-end authentication and authorization for Project Verdify across users (App ↔ API) and devices (Controller ↔ API). It specifies credential types, lifecycles, enforcement rules, error codes, and reference flows.

## Related Documentation

- [API Specification](./API.md) - REST API endpoints and schemas
- [Controller Specification](./CONTROLLER.md) - ESPHome firmware requirements
- [Configuration Management](./CONFIGURATION.md) - Device configuration workflows
- [Database Schema](./DATABASE.md) - Data model and constraints
- [Project Overview](./OVERVIEW.md) - System architecture and goals

## 1. Principles & Scope

### 1.1 Authentication Principals

The system supports two distinct authentication principals:

1. **User (human, via App)** → JWT (Bearer token)
2. **Device (controller firmware)** → device_token (opaque, long-lived until controller deletion)

### 1.2 Core Principles

- **Least privilege**: Device tokens can only call device endpoints for their own controller (config/plan/telemetry/bootstrap). Users cannot use device endpoints unless elevated backend role is explicitly granted (out of scope for MVP)
- **Transport security**: All calls use TLS (HTTPS/WSS/MQTTS). Reject clear text connections
- **Identifiers**:
  - `device_name`: `verdify-aabbcc` (claim & bootstrap only; user facing)
  - `controller_uuid`: UUIDv4 (server-side identity after claim; used in URLs)

### 1.3 MVP Session Policy

- **User JWT**: Short-lived (e.g., 1 hour); no refresh token in MVP
- **Device token**: Valid until controller is deleted or token revoked
- **CSRF Protection**: All state-changing endpoints (POST /auth/register, POST /auth/login) require CSRF tokens for browser-based requests

### 1.4 CSRF Protection

**Overview**: To prevent cross-site request forgery attacks on authentication endpoints, CSRF tokens are required for all state-changing operations from web browsers.

**Implementation**:
- **Token Generation**: `GET /api/v1/auth/csrf` returns a CSRF token valid for 1 hour
- **Token Requirement**: `POST /api/v1/auth/register` and `POST /api/v1/auth/login` require `X-CSRF-Token` header
- **Validation**: Server validates token against stored session or signed JWT
- **Browser Integration**: Frontend must fetch CSRF token before authentication calls

**CSRF Token Flow**:
```
1. Frontend: GET /api/v1/auth/csrf → { "csrf_token": "abc123..." }
2. Frontend: POST /api/v1/auth/login 
   Headers: { "X-CSRF-Token": "abc123..." }
   Body: { "email": "...", "password": "..." }
3. Server: Validates CSRF token before processing login
```

**Security Notes**:
- CSRF tokens are not required for device endpoints (use device tokens instead)
- API-only clients (mobile apps, scripts) can bypass CSRF by omitting Origin header
- SameSite cookie attribute provides additional CSRF protection

## 2. Identity Types

### 2.1 Users (App)

- **Auth method**: Email + password → API issues JWT (Bearer)
- **JWT contents (claims)**:
  - `sub` = user UUID
  - `exp` = expiry (e.g., 3600s)
  - `scope` = user
  - `iat`, `iss`, `aud` as standard
- **Usage**: `Authorization` header with `Authorization: Bearer <jwt>`

### 2.2 Devices (Controllers)

- **Pre-claim identity**: `device_name` + `claim_code` (from captive portal)
- **Post-claim identity**: `controller_uuid` + `device_token` (opaque, random 32 bytes, base64/hex encoded)
- **Usage (HTTP)**: `X-Device-Token: <token>` header on device endpoints
  - *Note*: Deliberately not Bearer to avoid overlap with user auth

## 3. Credential Types

| Credential | Holder | Format | Lifetime | Storage (server) |
|------------|--------|--------|----------|------------------|
| JWT (Bearer) | User | JWS (HS256/RS256), Authorization | Short (e.g., 1 hour) | Signing key(s), no DB storage |
| device_token | Controller | Opaque random (≥ 32 bytes), header X-Device-Token | Until controller deletion or explicit revoke | Hashed (Argon2id/bcrypt) with salt; last 4 chars stored for audit |
| claim_code | Controller | Short code shown on device portal | Until claimed or TTL (e.g., 24h) | Hashed; tied to device_name |

> **Note**: Generate device tokens using CSPRNG; recommend 32 random bytes → hex (64 chars)

## 4. Credential Lifecycle

### 4.1 Claim & Bootstrap (Device)

1. **Device → API**: `POST /v1/controllers/hello` (no auth) with:
   ```json
   {
     "device_name": "verdify-aabbcc",
     "claim_code": "ABC123",
     "hardware_profile": "esp32",
     "firmware": "1.0.0",
     "ts_utc": "2024-01-01T00:00:00Z"
   }
   ```

2. **User → API**: `POST /v1/controllers/claim` (JWT) with:
   ```json
   {
     "device_name": "verdify-aabbcc",
     "claim_code": "ABC123",
     "greenhouse_id": "uuid"
   }
   ```

3. **API Processing**:
   - Verifies `device_name` + `claim_code` (unused, not expired)
   - Creates `controller_uuid` and associates greenhouse
   - Issues `device_token` (stores hash, returns plaintext only once)
   - Invalidates `claim_code`

4. **Device → API**: `GET /v1/controllers/by-name/{device_name}/bootstrap?claim_code=...`
   - On success returns `{ controller_uuid, device_token }` (one time)
   - Thereafter device uses `controller_uuid` + `device_token` for all calls

### 4.2 Use

Device endpoints require `X-Device-Token` and path/controller match:

- `GET /v1/controllers/{controller_uuid}/config`
- `GET /v1/controllers/{controller_uuid}/plan`
- `POST /v1/telemetry/ingest` (body includes `controller_uuid`; must match token binding)
- *(Optional future)* `POST /v1/controllers/{controller_uuid}/status`

### 4.3 Rotate / Revoke

**Automatic Rotation Policy:**
- Device tokens automatically expire after 180 days
- Controllers must handle 401 responses by re-initiating claim flow
- Database includes `expires_at` timestamp for all device tokens
- API validates token expiry on every request

**Manual Operations:**
- **Rotate**: `POST /v1/controllers/{controller_uuid}/tokens/rotate` (JWT)
  - API issues new token, marks old token `revoked_at=now()`
  - Grace period optional (MVP: none)
  - New token extends expiry by another 180 days
- **Revoke**: `POST /v1/controllers/{controller_uuid}/tokens/revoke` (JWT)
  - Immediate 401 for device until bootstrap flow is re-done
  - Sets `revoked_at=now()` in database

**Token Lifecycle Management:**
```
1. Token issued → expires_at = now() + 180 days
2. Every API call → validate expires_at > now()
3. If expired → return 401, device must re-claim
4. On rotation → new expires_at = now() + 180 days
5. Cleanup job removes expired tokens older than 30 days
```

**Security Benefits:**
- Limits blast radius of compromised tokens
- Forces periodic re-authentication
- Enables audit trail of token usage
- **Delete controller**: Automatically revokes all tokens
  - Device will receive 404/401; requires re-claim

## 5. Enforcement

### 5.1 REST API Gateways & Middlewares

- **User routes**: Require `Authorization: Bearer <jwt>`; validate signature and exp
- **Device routes**: Require `X-Device-Token`; look up hashed token → resolve `controller_uuid`
  - **Path binding**: If URL embeds `{controller_uuid}`, must equal token's bound controller
  - **Body binding (ingest)**: If body contains `controller_uuid`, must equal token's bound controller
- **Rate limits**: Per principal (JWT subject / controller_uuid)
- **TLS required**: Reject non-TLS (MVP enforcement via reverse proxy)

#### Reference Pseudocode (Device Route)

```python
def require_device(request):
    token = request.headers.get("X-Device-Token")
    if not token: 
        raise HTTPException(401, "missing_device_token")
    
    rec = db.device_tokens.find_by_token_hash(hash(token))
    if not rec or rec.revoked_at: 
        raise HTTPException(401, "invalid_device_token")
    
    path_uuid = request.path_params.get("controller_uuid")
    body_uuid = request.json.get("controller_uuid") if request.method == "POST" else None
    
    if path_uuid and path_uuid != rec.controller_uuid: 
        raise HTTPException(403, "controller_mismatch")
    if body_uuid and body_uuid != rec.controller_uuid: 
        raise HTTPException(403, "controller_mismatch")
    
    return rec.controller_uuid
```

### 5.2 Auth Endpoint Level Requirements

| Endpoint (examples) | Auth required | Principal | Notes |
|---------------------|---------------|-----------|-------|
| `POST /v1/auth/login` | None | User | Issues JWT |
| `POST /v1/controllers/hello` | None | Device | Pre-claim ping |
| `POST /v1/controllers/claim` | JWT | User | Issues device_token |
| `GET /v1/controllers/by-name/{device_name}/bootstrap` | claim_code query only | Device | One-time token delivery |
| `GET /v1/controllers/{uuid}/config` (ETag) | X-Device-Token | Device | Device only |
| `GET /v1/controllers/{uuid}/plan` (ETag) | X-Device-Token | Device | Device only |
| `POST /v1/telemetry/ingest` | X-Device-Token | Device | Must match body.uuid |
| CRUD `/v1/greenhouses/*`, `/v1/zones/*`, etc. | JWT | User | App only |
| *(Optional)* `/v1/mqtt/auth`, `/v1/mqtt/acl` | Shared secret | Broker | See MQTT section |

> **Constraint (MUST)**: Device tokens cannot access user CRUD endpoints; JWTs cannot access device endpoints

## 6. Error Handling & Status Codes

| Scenario | HTTP | Code | Notes |
|----------|------|------|-------|
| Missing/invalid JWT | 401 | `invalid_jwt` | Bearer rejected |
| Missing device token | 401 | `missing_device_token` | Header absent |
| Invalid/revoked device token | 401 | `invalid_device_token` | Hash not found or revoked |
| Controller/route mismatch | 403 | `controller_mismatch` | Token bound to different controller |
| Claim code not found/expired | 410 | `claim_code_expired` | Or 404 not_found if unknown |
| Device already claimed | 409 | `already_claimed` | Idempotency guard |
| Rate limit exceeded | 429 | `rate_limited` | Retry-After header |
| Clear text (non-TLS) request | 400 | `tls_required` | Should be blocked at proxy |

### Response Body Example

```json
{
  "error": "invalid_device_token",
  "message": "Device token is invalid or revoked"
}
```

## 7. Data Structures (Server Side)

### Table: device_token

```sql
CREATE TABLE device_token (
    id uuid PRIMARY KEY,
    controller_uuid uuid NOT NULL REFERENCES controllers(id),
    token_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz NULL,
    last_seen_at timestamptz NULL,
    last4 text, -- last 4 hex chars for audit
    capabilities jsonb DEFAULT '{}' -- future: {"http":true,"mqtt":true}
);
```

### Enforcement Requirements

- **MUST** hash tokens (Argon2id preferred)
- **MUST** enforce one active token per controller in MVP (unique partial index where `revoked_at` is null)
- **MUST** log `last_seen_at` on each authenticated use

## 8. Implementation Constraints

### MUST Requirements

- ✅ **MUST** require TLS for all auth-bearing endpoints
- ✅ **MUST** bind each device token to exactly one `controller_uuid`
- ✅ **MUST** reject device requests where `{controller_uuid}` in path/body does not match the token's binding
- ✅ **MUST** store device tokens hashed; only show plaintext once on issuance/rotation
- ✅ **MUST** invalidate `claim_code` after successful bootstrap
- ✅ **MUST** treat `device_name` as claim/bootstrap only; not valid for authenticated device calls after bootstrap

### SHOULD Requirements

- ⚠️ **SHOULD** rate limit by `controller_uuid` and user `sub`
- ⚠️ **SHOULD** log auth failures with minimal PII
- ⚠️ **SHOULD** support token rotation endpoint even if rarely used in MVP

## 9. Open Questions

> **Open Questions Reference**: All open questions have been consolidated in [GAPS.md](./GAPS.md) for systematic resolution. See sections on Security & Access Control and Future Protocol Support.

---

*This specification is part of the Project Verdify requirements suite. For implementation details, see the related documentation linked above.*
