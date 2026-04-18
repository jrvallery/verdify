# systemd unit files (tracked copies)

These are the systemd `.service`, `.timer`, and `.path` units that run on `vm-docker-iris`. The canonical install location is `/etc/systemd/system/` and these copies exist so a fresh VM rebuild can restore them from git:

```bash
sudo cp systemd/*.{service,timer,path} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now verdify-site-poll.timer
```

## Files

| File | Purpose |
|---|---|
| `verdify-site-poll.timer` | Fires every 10s |
| `verdify-site-poll.service` | Runs `scripts/site-poll-and-rebuild.sh` — mtime check against marker, rebuilds if vault changed |
| `verdify-site-build.service` | Invoked by the polling service or manually; runs `scripts/rebuild-site.sh` (flock-serialized, 5s debounce, `npx quartz build`, `docker restart verdify-site`) |

## Why polling instead of inotify

inotify on NFS mounts does not reliably fire for writes originated by the NFS server (e.g. a file that arrives via Syncthing on the NAS). We used `verdify-site-build.path` (inotify-backed) initially; testing with a real Mac→Syncthing save confirmed it did not trigger, even though the VM could see the new mtime. Switched to a 10-second `verdify-site-poll.timer` on 2026-04-18 which is filesystem-agnostic. Latency: 10–20s typical, worst 20s, vs. inotify's theoretical 12–14s that didn't actually work.

## Other systemd units (not in this folder)

`verdify-ingestor.service`, `verdify-mcp.service`, `verdify-api.service`, `verdify-forecast.service`, `verdify-setpoint-server.service` — these were installed by earlier sprints and live only at `/etc/systemd/system/`. They should be added here at some point so a VM rebuild is fully reproducible from git. Not urgent for the site pipeline.
