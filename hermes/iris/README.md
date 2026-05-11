# Hermes — Iris profile

Canonical config for the `hermes-iris` agent container that replaces OpenClaw
as Verdify's planner gateway after Phase 7 canary cutover. Tracks Phase 5 of
the Iris loop overhaul (`docs/planner/iris-loop-overhaul.md` once promoted
out of the coordinator plan workspace).

## Files

- `config.yaml` — Hermes profile config. OpenAI GPT-5.5 high-reasoning,
  single profile, MCP-only tool surface. Allowlist tightens the toolset
  to Verdify's MCP server; `query` (raw SQL) is excluded.
- `SOUL.md` — durable identity, authoritative-source priority order,
  behavioral contract. Short by design — per-cycle context comes from
  `gather-plan-context.sh` via the ingestor.
- `.env` — **gitignored**. Holds `OPENAI_API_KEY`, `VERDIFY_MCP_TOKEN`,
  `HERMES_IRIS_API_KEY`. Lives only on the host runtime.

## Deployment

```bash
# One-time host setup
sudo mkdir -p /srv/verdify/hermes/iris
sudo chown -R verdify:verdify /srv/verdify/hermes/iris

# Copy versioned config; .env is created/edited on the host directly
cp hermes/iris/config.yaml hermes/iris/SOUL.md /srv/verdify/hermes/iris/

# Bring up the service
docker compose up -d hermes-iris

# Smoke
curl -X POST http://127.0.0.1:8642/v1/runs \
     -H "Authorization: Bearer $HERMES_IRIS_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"input": "ping", "session_id": "smoke-test"}'
```

## Gateway switch

`ingestor/config.py` exposes `AI_GATEWAY_PROVIDER` (default `openclaw`) and
`AI_GATEWAY_BY_EVENT` (dict of event_type → provider). Switch a single event
to Hermes by setting (in the systemd env file or shell):

```bash
AI_GATEWAY_BY_EVENT='{"MANUAL": "hermes"}'
```

The Phase 7 canary order is: MANUAL → FORECAST_DEVIATION → TRANSITION:decline
→ SOLAR_MAX → TRANSITION:peak_stress → SUNSET → SUNRISE. 48h soak between
each step.

## Rollback

One env-var change reverts to OpenClaw:

```bash
AI_GATEWAY_PROVIDER=openclaw
AI_GATEWAY_BY_EVENT='{}'
systemctl restart verdify-ingestor
```

The `hermes-iris` container can stay up; rollback only changes the
ingestor's send-side dispatcher target.
