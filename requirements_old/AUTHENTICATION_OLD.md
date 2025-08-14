Authentication
This section defines end to end authentication and authorization for Project Verdify across users (App ↔ API) and devices (Controller ↔ API). It specifies credential types, lifecycles, enforcement rules, error codes, and reference flows.
 
1) Principles & Scope
•	Two principals:
1.	User (human, via App) → JWT (Bearer).
2.	Device (controller firmware) → device_token (opaque, long lived until controller deletion).
•	Least privilege: Device tokens can only call device endpoints for their own controller (config/plan/telemetry/bootstrap). Users cannot use device endpoints unless elevated backend role is explicitly granted (out of scope for MVP).
•	Transport security: All calls use TLS (HTTPS/WSS/MQTTS). Reject clear text.
•	Identifiers:
o	device_name: verdify-aabbcc (claim & bootstrap only; user facing).
o	controller_uuid: UUIDv4 (server side identity after claim; used in URLs).
•	MVP session policy:
o	User JWT: short lived (e.g., 1h); no refresh token in MVP.
o	Device token: valid until controller is deleted or token revoked.
 
2) Identities
2.1 Users (App)
•	Auth method: Email + password → API issues JWT (Bearer).
•	JWT contents (claims):
o	sub = user UUID
o	exp = expiry (e.g., 3600s)
o	scope = user
o	iat, iss, aud as standard
•	Usage: Authorization header Authorization: Bearer <jwt>.
2.2 Devices (Controllers)
•	Pre claim identity: device_name + claim_code (from captive portal).
•	Post claim identity: controller_uuid + device_token (opaque, random 32 bytes, base64/hex encoded).
•	Usage (HTTP): X-Device-Token: <token> header on device endpoints.
(Deliberately not Bearer to avoid overlap with user auth.)

3) Credential Types
Credential	Holder	Format	Lifetime	Storage (server)
JWT (Bearer)	User	JWS (HS256/RS256), Authorization	Short (e.g., 1 hour)	Signing key(s), no DB storage
device_token	Controller	Opaque random (≥ 32 bytes), header X-Device-Token	Until controller deletion or explicit revoke	Hashed (Argon2id/bcrypt) with salt; last 4 chars stored for audit
claim_code	Controller	Short code shown on device portal	Until claimed or TTL (e.g., 24h)	Hashed; tied to device_name
Agentic note: Generate device tokens using CSPRNG; recommend 32 random bytes → hex (64 chars).

4) Lifecycle
4.1 Claim & Bootstrap (Device)
1.	Device → API: POST /v1/controllers/hello (no auth) with { device_name, claim_code, hardware_profile, firmware, ts_utc }.
2.	User → API: POST /v1/controllers/claim (JWT) with { device_name, claim_code, greenhouse_id }.
3.	API:
o	Verifies device_name + claim_code (unused, not expired).
o	Creates controller_uuid and associates greenhouse.
o	Issues device_token (stores hash, returns plaintext only once).
o	Invalidates claim_code.
4.	Device → API: GET /v1/controllers/by-name/{device_name}/bootstrap?claim_code=...
o	On success returns { controller_uuid, device_token } (one time).
o	Thereafter device uses controller_uuid + device_token for all calls.
4.2 Use
•	Device endpoints require X-Device-Token and path/controller match:
o	GET /v1/controllers/{controller_uuid}/config
o	GET /v1/controllers/{controller_uuid}/plan
o	POST /v1/telemetry/ingest (body includes controller_uuid; must match token binding)
o	(Optional future) POST /v1/controllers/{controller_uuid}/status
4.3 Rotate / Revoke
•	Rotate: POST /v1/controllers/{controller_uuid}/tokens/rotate (JWT). API issues new token, marks old token revoked_at=now(); grace period optional (MVP: none).
•	Revoke: POST /v1/controllers/{controller_uuid}/tokens/revoke (JWT) → immediate 401 for device until bootstrap flow is re done.
•	Delete controller: Automatically revokes all tokens (device will receive 404/401; requires re claim).
 
5) Enforcement
5.1 REST API Gateways & Middlewares
•	User routes: Require Authorization: Bearer <jwt>; validate signature and exp.
•	Device routes: Require X-Device-Token; look up hashed token → resolve controller_uuid.
o	Path binding: If URL embeds {controller_uuid}, must equal token’s bound controller.
o	Body binding (ingest): If body contains controller_uuid, must equal token’s bound controller.
•	Rate limits: Per principal (JWT subject / controller_uuid).
•	TLS required: Reject non TLS (MVP enforcement via reverse proxy).
Reference pseudocode (device route):
def require_device(request):
    token = request.headers.get("X-Device-Token")
    if not token: raise HTTPException(401, "missing_device_token")
    rec = db.device_tokens.find_by_token_hash(hash(token))
    if not rec or rec.revoked_at: raise HTTPException(401, "invalid_device_token")
    path_uuid = request.path_params.get("controller_uuid")
    body_uuid = request.json.get("controller_uuid") if request.method == "POST" else None
    if path_uuid and path_uuid != rec.controller_uuid: raise HTTPException(403, "controller_mismatch")
    if body_uuid and body_uuid != rec.controller_uuid: raise HTTPException(403, "controller_mismatch")
    return rec.controller_uuid

5.2 Auth Endpoint Level Requirements (Summary)
Endpoint (examples)	Auth required	Principal	Notes
POST /v1/auth/login	None	User	Issues JWT
POST /v1/controllers/hello	None	Device	Pre claim ping
POST /v1/controllers/claim	JWT	User	Issues device_token
GET /v1/controllers/by-name/{device_name}/bootstrap	claim_code query only	Device	One time token delivery
GET /v1/controllers/{uuid}/config (ETag)	X-Device-Token	Device	Device only
GET /v1/controllers/{uuid}/plan (ETag)	X-Device-Token	Device	Device only
POST /v1/telemetry/ingest	X-Device-Token	Device	Must match body.uuid
CRUD /v1/greenhouses/*, /v1/zones/*, etc.	JWT	User	App only
(Optional) /v1/mqtt/auth, /v1/mqtt/acl	Shared secret	Broker	See §6
Constraint (MUST): Device tokens cannot access user CRUD endpoints; JWTs cannot access device endpoints.


7) Error Handling & Status Codes
Scenario	HTTP	Code	Notes
Missing/invalid JWT	401	invalid_jwt	Bearer rejected
Missing device token	401	missing_device_token	Header absent
Invalid/revoked device token	401	invalid_device_token	Hash not found or revoked
Controller/route mismatch	403	controller_mismatch	Token bound to different controller
Claim code not found/expired	410	claim_code_expired	Or 404 not_found if unknown
Device already claimed	409	already_claimed	Idempotency guard
Rate limit exceeded	429	rate_limited	Retry After header
Clear text (non TLS) request	400	tls_required	Should be blocked at proxy
Response body (example):
{ "error": "invalid_device_token", "message": "Device token is invalid or revoked" }
 
8) Data Structures (Server Side)
Table: device_token
•	id uuid pk
•	controller_uuid uuid fk
•	token_hash text not null
•	created_at timestamptz not null default now()
•	revoked_at timestamptz null
•	last_seen_at timestamptz null
•	last4 text (last 4 hex chars for audit)
•	capabilities jsonb default '{}' (future: {"http":true,"mqtt":true})
Agentic enforcement:
•	MUST hash tokens (Argon2id preferred).
•	MUST enforce one active token per controller in MVP (unique partial index where revoked_at is null).
•	MUST log last_seen_at on each authenticated use.

10) Constraints (MUST/SHOULD)
•	MUST require TLS for all auth bearing endpoints.
•	MUST bind each device token to exactly one controller_uuid.
•	MUST reject device requests where {controller_uuid} in path/body does not match the token’s binding.
•	MUST store device tokens hashed; only show plaintext once on issuance/rotation.
•	MUST invalidate claim_code after successful bootstrap.
•	MUST treat device_name as claim/bootstrap only; not valid for authenticated device calls after bootstrap.
•	SHOULD rate limit by controller_uuid and user sub.
•	SHOULD log auth failures with minimal PII.
•	SHOULD support token rotation endpoint even if rarely used in MVP.
 
Open Questions
1.	Roles & permissions (post MVP): Do we need user roles (e.g., owner, viewer) and resource scoping (per greenhouse) for the App? If yes, define JWT roles claim and authorization matrix.
2.	Token rotation policy: Beyond deletion/revocation, should device tokens expire periodically (e.g., 180 days) with a grace window and App initiated rotation workflow?
3.	MQTT enablement timing: If MQTT is enabled later, should we require a separate device credential pair for MQTT (username/password) or reuse the same device_token?

Open Questions
1.	Plan expiry window: What is the maximum allowed gap before a plan is considered stale (e.g., 24 hours) and the controller should rely exclusively on failsafe rails?
2.	Resource contention: May lighting and irrigation overlap if they share power constraints/circuits? If not, specify a global controller level lock or schedule conflict rules.
3.	Post MVP access model: When should we introduce multi owner or role based permissions (viewer/operator/admin), and how should existing greenhouses migrate?
