# Verdify Website Analytics

Last updated: 2026-04-29.

Verdify uses two self-hosted analytics layers:

- **Umami** for browser-side product analytics: unique visitors, pageviews, visits, referrers, browsers, devices, countries, events, and paths.
- **GoAccess** for server-side access-log analytics: crawler traffic, requests that do not execute JavaScript, status codes, bandwidth, user agents, and referrers from Traefik access logs.

The two tools answer different questions. Umami describes real browser sessions on the public site. GoAccess describes every HTTP request that reaches Traefik, including crawlers, failed requests, static assets, and clients that block JavaScript.

## Public Endpoints

- Umami dashboard: `https://analytics.verdify.ai`
- GoAccess dashboard: `https://logs.verdify.ai`
- Public Umami script used by Quartz: `https://analytics.verdify.ai/script.js`
- Login-free Umami read-only share view: `https://analytics.verdify.ai/share/dceaeb6aa6d60a01/Verdify`

The management VM Traefik owns the public `*.verdify.ai` routing and Authentik integration. `analytics.verdify.ai` is split there into two routes. The public script and collection endpoint remain unauthenticated so the website can report pageviews. The dashboard and all other paths are protected by Authentik forward auth.

After Authentik, `analytics.verdify.ai/` is redirected by the Verdify-local Traefik to Umami's read-only share URL so users do not hit Umami's native login page. Full Umami administration is still available by going directly to `/login` after Authentik and using the stored Umami admin credential.

`logs.verdify.ai` is protected by Authentik forward auth because GoAccess is static HTML with no built-in login. The Verdify-local GoAccess route has no additional basic-auth layer; public protection is handled at the management VM.

Authentik outpost/callback paths are also routed on both protected hosts by the management VM Traefik:

- `https://analytics.verdify.ai/outpost.goauthentik.io/`
- `https://logs.verdify.ai/outpost.goauthentik.io/`

Authentik provider IDs:

- `verdify-analytics`: provider pk `18`, client ID `LnRIMSGxhJI6hbhLLfwopFlOcG5TRj1vfwXggnZ5`
- `verdify-logs`: provider pk `17`, client ID `FPTvsHgSMoIilwQFbr6XVR60ALqs6gPA8H4bEGkQ`

## Runtime Layout

Compose services in `/srv/verdify/docker-compose.yml`:

- `umami-db`: Postgres 16 for Umami.
- `umami`: Umami application. Local compose exposes a normal local Traefik route plus a root-only redirect to `/share/dceaeb6aa6d60a01/Verdify`; public auth splitting is handled by the management VM Traefik.
- `goaccess`: periodic log parser that reads Traefik access logs and writes the HTML report.
- `goaccess-site`: nginx static server for the GoAccess report. Local compose does not add basic auth; public access is protected by management VM Authentik.

The Verdify host should not define a local `authentik@file` middleware for these routes. The public Authentik split lives in `/opt/stacks/management/traefik/dynamic/web-sites.yml` on the management VM.

Runtime paths:

- Traefik access log: `/srv/verdify/traefik/logs/access.log`
- GoAccess config: `/srv/verdify/goaccess/goaccess.conf`
- GoAccess report output: `/srv/verdify/analytics/goaccess/index.html`
- Umami admin credential note: `/srv/verdify/analytics/umami-admin.txt`
- Umami DB Docker volume: `verdify_umami_db_data`

Do not commit or print the Umami password. It is stored only in the runtime credential note.

## Quartz Integration

Quartz analytics are configured in `site/quartz.config.ts`:

```ts
analytics: {
  provider: "umami",
  host: "https://analytics.verdify.ai",
  websiteId: "bde6b2d3-31df-4d54-a86e-751ffb2571da",
},
```

The website ID belongs to the Umami site record:

- Name: `Verdify`
- Domain: `verdify.ai`
- ID: `bde6b2d3-31df-4d54-a86e-751ffb2571da`

After editing Quartz config, run:

```bash
make lint
make site-rebuild
make site-doctor
pytest tests/test_06_website.py
```

## Verification

Check the services:

```bash
docker compose -f /srv/verdify/docker-compose.yml --env-file /srv/verdify/.env ps umami-db umami goaccess goaccess-site traefik
```

Check local Umami through the Verdify-local Traefik:

```bash
curl -ksS -I -H 'Host: analytics.verdify.ai' https://127.0.0.1/
curl -ksS -I -H 'Host: analytics.verdify.ai' https://127.0.0.1/share/dceaeb6aa6d60a01/Verdify
curl -ksS -I -H 'Host: analytics.verdify.ai' https://127.0.0.1/script.js
```

Expected: local root returns HTTP 302 to the share URL; the share URL and script return HTTP 200. This is local-only and does not prove public Authentik behavior.

Check public protected dashboard routing:

```bash
curl -ksS -o /dev/null -w '%{redirect_url}\n' https://analytics.verdify.ai/
curl -ksS -o /dev/null -w '%{redirect_url}\n' https://logs.verdify.ai/
```

Expected: protected public routes return HTTP 302 to Authentik. The analytics redirect URL should include client ID `LnRIMSGxhJI6hbhLLfwopFlOcG5TRj1vfwXggnZ5`; the logs redirect URL should include client ID `FPTvsHgSMoIilwQFbr6XVR60ALqs6gPA8H4bEGkQ`.

After completing Authentik in a browser, `analytics.verdify.ai/` should land on `/share/dceaeb6aa6d60a01/Verdify`, not Umami's native login page. `logs.verdify.ai/` should land on the GoAccess report, not a basic-auth prompt.

Check direct GoAccess service output:

```bash
docker exec verdify-goaccess-site wget -qO- http://127.0.0.1/ | head
```

Expected: generated GoAccess HTML.

Check public Umami collection paths:

```bash
curl -ksS -I -H 'Host: analytics.verdify.ai' https://127.0.0.1/script.js
curl -ksS -H 'Host: analytics.verdify.ai' \
  -H 'Content-Type: application/json' \
  -X POST https://127.0.0.1/api/send \
  -d '{"type":"event","payload":{"website":"bde6b2d3-31df-4d54-a86e-751ffb2571da","hostname":"verdify.ai","url":"https://verdify.ai/?check=1"}}'
```

Expected: `script.js` returns HTTP 200 and `/api/send` accepts the event.

Check Traefik access logging:

```bash
tail -n 20 /srv/verdify/traefik/logs/access.log
```

Expected: common-format request lines.

## Data Freshness

Umami starts accumulating data once the deployed Quartz bundle loads `script.js`. Historical browser analytics before 2026-04-29 are not backfilled.

GoAccess starts from the retained Traefik access log. The log file was enabled on 2026-04-29, so earlier request history is not present unless restored from another source.
