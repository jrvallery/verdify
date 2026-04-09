# Verdify Operations Runbook

**VM:** vm-docker-iris (192.168.30.150)
**Last updated:** 2026-03-29

---

## Service Inventory

| Service | Type | Restart | Check |
|---------|------|---------|-------|
| verdify-ingestor | systemd | `sudo systemctl restart verdify-ingestor` | `systemctl status verdify-ingestor` |
| verdify-setpoint-server | systemd | `sudo systemctl restart verdify-setpoint-server` | `curl -s http://127.0.0.1:8200/setpoints \| head -3` |
| verdify-timescaledb | Docker | `cd /srv/verdify && docker compose restart timescaledb` | `docker exec verdify-timescaledb pg_isready` |
| verdify-grafana | Docker | `cd /srv/verdify && docker compose restart grafana` | `docker exec verdify-grafana curl -s http://localhost:3000/api/health` |
| verdify-traefik | Docker | `cd /srv/verdify && docker compose restart traefik` | `curl -sk https://127.0.0.1:443/` |

## Quick Health Check

```bash
bash /mnt/jason/agents/iris/health-check.sh
```

Expected: 22/22 passing, HEALTHY.

## Log Locations

| Service | Log Command |
|---------|------------|
| Ingestor | `journalctl -u verdify-ingestor -f` |
| Setpoint server | `journalctl -u verdify-setpoint-server -f` |
| TimescaleDB | `docker logs verdify-timescaledb --tail 50` |
| Grafana | `docker logs verdify-grafana --tail 50` |
| Liveness | `tail -20 /srv/verdify/state/liveness.log` |
| Alert monitor | part of ingestor (task_loop) |

## Common Failure Modes

### ESP32 unreachable (ping fails)
**Symptoms:** Climate data stops, equipment state stale, health check fails on "Climate" freshness.
**Fix:**
1. Check ESP32 power (physical)
2. Check WiFi (ESP32 connects to IoT VLAN 192.168.10.x)
3. Restart ingestor: `sudo systemctl restart verdify-ingestor`
4. If ESP32 needs reboot: power cycle the controller box

### Ingestor crash loop
**Symptoms:** `systemctl status verdify-ingestor` shows repeated restarts.
**Fix:**
1. Check logs: `journalctl -u verdify-ingestor --since "10 min ago" --no-pager`
2. Common causes: ESP32 unreachable, DB connection refused, Python error
3. RestartSec=30 prevents tight loops

### No data in Grafana ("No data" panels)
**Symptoms:** Dashboard panels blank.
**Fix:**
1. Check data freshness: `docker exec verdify-timescaledb psql -U verdify -d verdify -c "SELECT MAX(ts) FROM climate;"`
2. If stale: restart ingestor
3. If data exists but Grafana blank: reload dashboards:
   ```bash
   GRAFANA_PW=$(grep GRAFANA_ADMIN_PASSWORD /srv/verdify/.env | cut -d= -f2)
   docker exec verdify-grafana curl -s -u "admin:${GRAFANA_PW}" -X POST http://localhost:3000/api/admin/provisioning/dashboards/reload
   ```

### Setpoint server unreachable
**Symptoms:** ESP32 can't pull /setpoints, enthalpy goes NaN.
**Fix:**
1. Check: `curl -s http://127.0.0.1:8200/setpoints | head -3`
2. Restart: `sudo systemctl restart verdify-setpoint-server`
3. Verify UFW allows ESP32: `sudo ufw status | grep 8200`

### Grow lights don't toggle
**Symptoms:** gl_auto_mode is ON but lights don't turn on/off.
**Fix:**
1. Chain: ESP32 → HTTP POST :8200 → setpoint-server → HA REST → Lutron
2. Check setpoint-server: `curl -s http://127.0.0.1:8200/lights`
3. Check HA: `curl -s -H "Authorization: Bearer $(cat /mnt/jason/agents/shared/credentials/ha_token.txt)" http://192.168.30.107:8123/api/states/light.greenhouse_main`
4. Physical: check Lutron Caseta bridge power, check physical switch position

### Modbus bus failure (sensors return NaN)
**Symptoms:** Zone temperatures NULL, soil sensors offline.
**Fix:**
1. Check which probes respond: stop ingestor, run ESPHome logs for 30s
2. Common cause: loose RS485 connection at daisy chain splice
3. Physical: check A/B wiring at each junction point
4. Bus order: Case(1) → North(2) → West(3) → South(4) → East(5) → Intake(6) → Soil(7,8,9)

## Backup & Restore

### Daily backup (automatic)
Runs at 01:00 UTC via cron:
```
docker exec verdify-timescaledb pg_dump -U verdify -Fc verdify > /mnt/iris/backups/verdify-YYYYMMDD.dump
```
Retention: 7 days.

### Manual backup
```bash
docker exec verdify-timescaledb pg_dump -U verdify -Fc verdify > /mnt/iris/backups/verdify-manual-$(date +%Y%m%d-%H%M).dump
```

### Restore from backup
```bash
# Stop services
sudo systemctl stop verdify-ingestor verdify-setpoint-server

# Drop and recreate DB
docker exec verdify-timescaledb psql -U verdify -c "DROP DATABASE IF EXISTS verdify_restore;"
docker exec verdify-timescaledb psql -U verdify -c "CREATE DATABASE verdify_restore;"
cat /mnt/iris/backups/verdify-YYYYMMDD.dump | docker exec -i verdify-timescaledb pg_restore -U verdify -d verdify_restore

# Swap databases
docker exec verdify-timescaledb psql -U verdify -c "ALTER DATABASE verdify RENAME TO verdify_old;"
docker exec verdify-timescaledb psql -U verdify -c "ALTER DATABASE verdify_restore RENAME TO verdify;"

# Restart services
sudo systemctl start verdify-ingestor verdify-setpoint-server
```

## Ports & Firewall

| Port | Binding | Service | Access |
|------|---------|---------|--------|
| 443 | 0.0.0.0 | Traefik | Public (graphs.verdify.ai) |
| 22 | 0.0.0.0 | SSH | Fleet |
| 8200 | 0.0.0.0 | Setpoint server | ESP32 only (UFW: 192.168.10.0/24) |
| 9100 | 0.0.0.0 | Node exporter | Prometheus (nexus) |
| 9323 | 0.0.0.0 | Docker metrics | Prometheus (nexus) |
| 5432 | 127.0.0.1 | TimescaleDB | Localhost only |
| 3000 | Docker internal | Grafana | Via Traefik only |

## Secrets

| File | Contains | Perms |
|------|----------|-------|
| /srv/verdify/.env | POSTGRES_PASSWORD, GRAFANA_ADMIN_PASSWORD, GRAFANA_API_TOKEN | 600 |
| /srv/verdify/ingestor/.env | DB credentials, ESP32_API_KEY (noise_psk) | 600 |
| /srv/greenhouse/esphome/secrets.yaml | WiFi SSID/pass, OTA password, API key | 600 |
| /mnt/jason/agents/shared/credentials/ | HA token, Slack bot token | Fleet shared |

## Architecture

```
Internet → Cloudflare → Nexus Traefik → Iris Traefik (443) → Grafana (3000)

ESP32 (192.168.10.111) ←→ Ingestor (aioesphomeapi, port 6053)
                        ←  Setpoint server (HTTP pull, port 8200)

Ingestor (PID 1, systemd) runs:
  - esp32_loop: persistent aioesphomeapi subscription
  - flush_loop: 60s climate/diagnostics writes
  - task_loop: 11 periodic tasks (shelly, tempest, ha_sensor, alerts, dispatcher, forecast, etc.)
  - mqtt_loop: Sentinel occupancy via MQTT
  - setpoint_listener: LISTEN/NOTIFY for real-time ESP32 push

Cron (9 jobs): token sync, daily summary, vault writers, frigate snapshots, checklist, hydro map, DB backup, liveness
```
