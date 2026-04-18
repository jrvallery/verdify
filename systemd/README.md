# systemd unit files (tracked copies)

These are every systemd `.service`, `.timer`, and `.path` unit that runs on `vm-docker-iris`. Canonical install location is `/etc/systemd/system/`; these copies exist so a fresh VM rebuild can restore them from git:

```bash
sudo cp systemd/*.service systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now \
  verdify-ingestor.service \
  verdify-mcp.service \
  verdify-api.service \
  verdify-setpoint-server.service \
  verdify-site-poll.timer
# verdify-forecast.service and verdify-site-build.service are triggered
# by cron/timer/poller and do not need to be enabled directly.
```

## Files

| File | Type | Purpose | How it starts |
|---|---|---|---|
| `verdify-ingestor.service` | `simple` (always-on) | ESP32 → TimescaleDB data pipeline, 15 periodic tasks | `enable --now` |
| `verdify-mcp.service` | `simple` (always-on) | MCP server on localhost:8000; 18 tools for Iris planner | `enable --now` |
| `verdify-api.service` | `simple` (always-on) | FastAPI crop catalog + ESP32 /setpoints endpoint (port 8300) | `enable --now` |
| `verdify-setpoint-server.service` | `simple` (always-on) | Grow-light control + setpoint HTTP surface | `enable --now` |
| `verdify-forecast.service` | `oneshot` | Open-Meteo 72 h forecast sync | invoked by cron via `scripts/forecast-sync.py` |
| `verdify-site-poll.timer` | `Timer` | Fires every 10 s | `enable --now` |
| `verdify-site-poll.service` | `oneshot` | `scripts/site-poll-and-rebuild.sh` — mtime check vs marker; rebuilds if vault changed | triggered by timer |
| `verdify-site-build.service` | `oneshot` | `scripts/rebuild-site.sh` (flock + 5 s debounce + `npx quartz build` + `docker restart verdify-site`) | invoked from poll script, or `make site-rebuild` |

## Why polling instead of inotify for site-build

inotify on NFS mounts does not reliably fire for writes originated by the NFS server (e.g. a file that arrives via Syncthing on the NAS). The original `verdify-site-build.path` (inotify-backed) unit confirmed this in production — it didn't trigger on a real Mac→Obsidian save, even though the VM could see the new mtime. Replaced 2026-04-18 with the 10-second `verdify-site-poll.timer`, which is filesystem-agnostic. Latency: 10–20 s typical, worst 20 s.

## Secrets referenced by these units

These `.env` / secrets files live on the VM outside the git tree and are preserved by Proxmox VM snapshots:

- `/srv/verdify/.env` — `POSTGRES_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`
- `/srv/verdify/api/.env` — API-specific
- `/srv/verdify/ingestor/.env` — `ESP32_HOST`, `ESP32_PORT`, `ESP32_API_KEY`, DB credentials
- `/srv/greenhouse/esphome/secrets.yaml` — WiFi SSID/password, ESP32 API key, OTA password
- Fleet-shared credentials in `/mnt/jason/agents/shared/credentials/`

Canonical recovery (if VM snapshots are unavailable): Orbit vault → `/mnt/jason/agents/root/secrets/` → `/mnt/jason/agents/shared/credentials/` → per-VM `.env`. See fleet `ARCHITECTURE.md` and the credential-management doc.
