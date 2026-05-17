#!/usr/bin/env /srv/greenhouse/.venv/bin/python3
"""Backfill public inference-infra telemetry from Nexus Prometheus.

The live ingestor samples DCGM/node-exporter metrics directly every minute.
This script mirrors historical samples from the primary Nexus Prometheus via
Grafana's datasource proxy, then upserts them into Verdify TimescaleDB for the
public Resource Use / Inference panels.

Examples:
  scripts/backfill-nexus-infra-metrics.py --hours 24
  scripts/backfill-nexus-infra-metrics.py --hours 24 --apply
  scripts/backfill-nexus-infra-metrics.py --prometheus-url http://prometheus:9090 --start 2026-05-01T00:00:00Z --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


GRAFANA_URL_DEFAULT = "https://grafana.vallery.net"
GRAFANA_TOKEN_FILE_DEFAULT = "/mnt/agents/root/secrets/iris_grafana_token.txt"
PROMETHEUS_DATASOURCE_UID_DEFAULT = "prometheus"

GPU_METRICS = {
    "DCGM_FI_DEV_POWER_USAGE": "watts",
    "DCGM_FI_DEV_GPU_UTIL": "gpu_util_pct",
    "DCGM_FI_DEV_GPU_TEMP": "temperature_c",
    "DCGM_FI_DEV_FB_USED": "memory_used_mb",
    "DCGM_FI_DEV_FB_FREE": "memory_free_mb",
}

GPU_INSTANCE_MAP = {
    "192.168.30.105:9400": {
        "host": "cortex",
        "vm_name": "vm-docker-ai",
        "purpose": "Iris/Hermes inference, embeddings, retrieval, and agent workloads",
    },
    "192.168.30.142:9400": {
        "host": "sentinel",
        "vm_name": "vm-docker-frigate",
        "purpose": "Camera and vision inference for Frigate, greenhouse video, and visual evidence",
    },
    "192.168.30.108:9400": {
        "host": "immich",
        "vm_name": "vm-docker-immich",
        "purpose": "Photo/media ML, CLIP search, and archive embeddings",
    },
}

CPU_INSTANCE_MAP = {
    "192.168.30.150:9100": {
        "host": "iris",
        "vm_name": "vm-docker-iris",
        "purpose": "Verdify greenhouse ingestor, planner support, MCP, API, and site data jobs",
    },
    "192.168.30.105:9100": {
        "host": "cortex",
        "vm_name": "vm-docker-ai",
        "purpose": "Local inference, embeddings, retrieval, and agent workloads",
    },
    "192.168.30.142:9100": {
        "host": "sentinel",
        "vm_name": "vm-docker-frigate",
        "purpose": "Camera ingest, Frigate, and vision workloads",
    },
    "192.168.30.151:9100": {
        "host": "web",
        "vm_name": "vm-docker-web",
        "purpose": "Public website publishing and edge-adjacent web jobs",
    },
    "192.168.30.212:9100": {
        "host": "opal",
        "vm_name": "pve-opal",
        "purpose": "Proxmox host for the Cortex GPU VM",
    },
    "192.168.30.211:9100": {
        "host": "oro",
        "vm_name": "pve-oro",
        "purpose": "Proxmox host for Sentinel, Web, and GPU/edge workloads",
    },
    "192.168.30.213:9100": {
        "host": "onyx",
        "vm_name": "pve-onyx",
        "purpose": "Proxmox host for Iris and HA-capable services",
    },
    "192.168.30.214:9100": {
        "host": "olivine",
        "vm_name": "pve-olivine",
        "purpose": "Proxmox management and quorum host",
    },
    "192.168.30.215:9100": {
        "host": "ore",
        "vm_name": "pve-ore",
        "purpose": "Proxmox host for the Immich GPU VM",
    },
}


@dataclass
class PrometheusClient:
    grafana_url: str | None
    prometheus_url: str | None
    datasource_uid: str
    token: str | None
    timeout_s: int

    def query_range(self, query: str, start: datetime, end: datetime, step_s: int) -> list[dict[str, Any]]:
        params = urllib.parse.urlencode(
            {
                "query": query,
                "start": str(int(start.timestamp())),
                "end": str(int(end.timestamp())),
                "step": str(step_s),
            }
        )
        if self.prometheus_url:
            url = f"{self.prometheus_url.rstrip('/')}/api/v1/query_range?{params}"
            headers = {"Accept": "application/json"}
        else:
            base = (self.grafana_url or GRAFANA_URL_DEFAULT).rstrip("/")
            path = f"/api/datasources/proxy/uid/{urllib.parse.quote(self.datasource_uid)}/api/v1/query_range"
            url = f"{base}{path}?{params}"
            headers = {"Accept": "application/json"}
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:240]
            raise RuntimeError(f"Prometheus query failed: HTTP {exc.code} for {query!r}: {body}") from exc

        if payload.get("status") != "success":
            raise RuntimeError(f"Prometheus query failed for {query!r}: {payload}")
        return payload.get("data", {}).get("result", [])


def parse_ts(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def load_token(path: str) -> str | None:
    token_path = Path(path)
    if not token_path.exists():
        return None
    token = token_path.read_text().strip()
    return token or None


def load_dsn() -> str:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]

    env = {}
    env_path = Path("/srv/verdify/ingestor/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key] = value.strip().strip('"').strip("'")

    host = os.environ.get("DB_HOST") or env.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT") or env.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME") or env.get("DB_NAME", "verdify")
    user = os.environ.get("DB_USER") or env.get("DB_USER", "verdify")
    password = (
        os.environ.get("DB_PASSWORD")
        or os.environ.get("DB_PASS")
        or env.get("DB_PASSWORD")
        or env.get("DB_PASS")
        or "verdify"
    )
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def host_meta(instance: str, mapping: dict[str, dict[str, str]]) -> dict[str, str]:
    if instance in mapping:
        return mapping[instance]
    host = instance.split(":", 1)[0].split(".", 1)[0]
    return {"host": host, "vm_name": host, "purpose": "Unmapped Nexus Prometheus target"}


def value_to_float(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def valid_gpu_value(field: str, value: float) -> bool:
    if field == "watts":
        return 0 <= value < 1000
    if field == "gpu_util_pct":
        return 0 <= value <= 100
    if field == "temperature_c":
        return 0 <= value < 130
    if field in {"memory_used_mb", "memory_free_mb"}:
        return value >= 0
    return True


def matrix_to_gpu_rows(results_by_metric: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: dict[tuple[datetime, str, str], dict[str, Any]] = {}
    for metric_name, series_list in results_by_metric.items():
        field = GPU_METRICS[metric_name]
        for series in series_list:
            metric = series.get("metric", {})
            instance = metric.get("instance", "")
            meta = host_meta(instance, GPU_INSTANCE_MAP)
            gpu = str(metric.get("gpu") or metric.get("UUID") or "unknown")
            for ts_raw, value_raw in series.get("values", []):
                value = value_to_float(value_raw)
                if value is None:
                    continue
                if not valid_gpu_value(field, value):
                    continue
                ts = datetime.fromtimestamp(float(ts_raw), tz=UTC)
                key = (ts, meta["host"], gpu)
                row = rows.setdefault(
                    key,
                    {
                        "ts": ts,
                        "host": meta["host"],
                        "vm_name": meta.get("vm_name"),
                        "purpose": meta.get("purpose"),
                        "gpu": gpu,
                        "device": metric.get("device"),
                        "model_name": metric.get("modelName"),
                        "raw": {"instance": instance, "labels": metric},
                    },
                )
                row[field] = value
    return [row for row in rows.values() if row.get("watts") is not None]


def matrix_to_cpu_rows(results_by_field: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: dict[tuple[datetime, str], dict[str, Any]] = {}
    for field, series_list in results_by_field.items():
        for series in series_list:
            metric = series.get("metric", {})
            instance = metric.get("instance", "")
            meta = host_meta(instance, CPU_INSTANCE_MAP)
            for ts_raw, value_raw in series.get("values", []):
                value = value_to_float(value_raw)
                if value is None:
                    continue
                ts = datetime.fromtimestamp(float(ts_raw), tz=UTC)
                key = (ts, meta["host"])
                row = rows.setdefault(
                    key,
                    {
                        "ts": ts,
                        "host": meta["host"],
                        "vm_name": meta.get("vm_name"),
                        "purpose": meta.get("purpose"),
                        "raw": {"instance": instance, "labels": metric},
                    },
                )
                row[field] = int(round(value)) if field == "cores" else value
    return list(rows.values())


def fetch_rows(
    client: PrometheusClient,
    start: datetime,
    end: datetime,
    step_s: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gpu_results = {}
    gpu_filter = f'{{instance=~"{instance_regex(GPU_INSTANCE_MAP)}"}}'
    for metric in GPU_METRICS:
        gpu_results[metric] = client.query_range(f"{metric}{gpu_filter}", start, end, step_s)

    cpu_instance_filter = f'instance=~"{instance_regex(CPU_INSTANCE_MAP)}"'
    cpu_filter = f"{{{cpu_instance_filter}}}"
    cpu_idle_filter = f'{{{cpu_instance_filter},mode="idle"}}'
    cpu_results = {
        "cpu_util_pct": client.query_range(
            f"100 * (1 - avg by (instance) (rate(node_cpu_seconds_total{cpu_idle_filter}[5m])))",
            start,
            end,
            step_s,
        ),
        "load1": client.query_range(f"node_load1{cpu_filter}", start, end, step_s),
        "cores": client.query_range(
            f"count by (instance) (node_cpu_seconds_total{cpu_idle_filter})", start, end, step_s
        ),
        "memory_used_pct": client.query_range(
            f"100 * (1 - (node_memory_MemAvailable_bytes{cpu_filter} / node_memory_MemTotal_bytes{cpu_filter}))",
            start,
            end,
            step_s,
        ),
    }

    return matrix_to_gpu_rows(gpu_results), matrix_to_cpu_rows(cpu_results)


async def upsert_gpu(conn: Any, rows: list[dict[str, Any]], greenhouse_id: str) -> None:
    await conn.executemany(
        """
        INSERT INTO gpu_power (
            ts, host, vm_name, purpose, gpu, device, model_name, watts,
            gpu_util_pct, temperature_c, memory_used_mb, memory_free_mb, source, raw, greenhouse_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, 'nexus_prometheus', $13::jsonb, $14)
        ON CONFLICT (greenhouse_id, ts, host, gpu) DO UPDATE SET
            vm_name = EXCLUDED.vm_name,
            purpose = EXCLUDED.purpose,
            device = COALESCE(EXCLUDED.device, gpu_power.device),
            model_name = COALESCE(EXCLUDED.model_name, gpu_power.model_name),
            watts = EXCLUDED.watts,
            gpu_util_pct = EXCLUDED.gpu_util_pct,
            temperature_c = EXCLUDED.temperature_c,
            memory_used_mb = EXCLUDED.memory_used_mb,
            memory_free_mb = EXCLUDED.memory_free_mb,
            source = EXCLUDED.source,
            raw = EXCLUDED.raw
        """,
        [
            (
                row["ts"],
                row["host"],
                row.get("vm_name"),
                row.get("purpose"),
                row["gpu"],
                row.get("device"),
                row.get("model_name"),
                row["watts"],
                row.get("gpu_util_pct"),
                row.get("temperature_c"),
                row.get("memory_used_mb"),
                row.get("memory_free_mb"),
                json.dumps(row.get("raw") or {}),
                greenhouse_id,
            )
            for row in rows
        ],
    )


async def upsert_cpu(conn: Any, rows: list[dict[str, Any]], greenhouse_id: str) -> None:
    await conn.executemany(
        """
        INSERT INTO infra_cpu (
            ts, host, vm_name, purpose, cpu_util_pct, load1, cores,
            memory_used_pct, source, raw, greenhouse_id
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'nexus_prometheus', $9::jsonb, $10)
        ON CONFLICT (greenhouse_id, ts, host) DO UPDATE SET
            vm_name = EXCLUDED.vm_name,
            purpose = EXCLUDED.purpose,
            cpu_util_pct = EXCLUDED.cpu_util_pct,
            load1 = EXCLUDED.load1,
            cores = EXCLUDED.cores,
            memory_used_pct = EXCLUDED.memory_used_pct,
            source = EXCLUDED.source,
            raw = EXCLUDED.raw
        """,
        [
            (
                row["ts"],
                row["host"],
                row.get("vm_name"),
                row.get("purpose"),
                row.get("cpu_util_pct"),
                row.get("load1"),
                row.get("cores"),
                row.get("memory_used_pct"),
                json.dumps(row.get("raw") or {}),
                greenhouse_id,
            )
            for row in rows
        ],
    )


def instance_regex(mapping: dict[str, dict[str, str]]) -> str:
    return "|".join(replace_regex_chars(instance) for instance in mapping)


def replace_regex_chars(value: str) -> str:
    return value.replace(".", "[.]")


async def run(args: argparse.Namespace) -> None:
    end = parse_ts(args.end) if args.end else datetime.now(UTC)
    start = parse_ts(args.start) if args.start else end - timedelta(hours=args.hours)
    if start >= end:
        raise SystemExit("--start must be before --end")

    token = None if args.prometheus_url else load_token(args.token_file)
    client = PrometheusClient(
        grafana_url=args.grafana_url,
        prometheus_url=args.prometheus_url,
        datasource_uid=args.datasource_uid,
        token=token,
        timeout_s=args.timeout,
    )

    conn = None
    if args.apply:
        import asyncpg

        conn = await asyncpg.connect(load_dsn())
    total_gpu_rows = 0
    total_cpu_rows = 0
    gpu_hosts: set[str] = set()
    cpu_hosts: set[str] = set()
    chunk_delta = timedelta(hours=args.chunk_hours) if args.chunk_hours else None
    try:
        cursor = start
        while cursor < end:
            chunk_end = min(end, cursor + chunk_delta) if chunk_delta else end
            gpu_rows, cpu_rows = fetch_rows(client, cursor, chunk_end, args.step)
            total_gpu_rows += len(gpu_rows)
            total_cpu_rows += len(cpu_rows)
            gpu_hosts.update(row["host"] for row in gpu_rows)
            cpu_hosts.update(row["host"] for row in cpu_rows)
            print(
                f"chunk={cursor.isoformat()}..{chunk_end.isoformat()} "
                f"gpu_rows={len(gpu_rows)} cpu_rows={len(cpu_rows)} apply={args.apply}"
            )
            if conn:
                async with conn.transaction():
                    if gpu_rows:
                        await upsert_gpu(conn, gpu_rows, args.greenhouse_id)
                    if cpu_rows:
                        await upsert_cpu(conn, cpu_rows, args.greenhouse_id)
            if not chunk_delta:
                break
            cursor = chunk_end
    finally:
        if conn:
            await conn.close()

    print(
        f"range={start.isoformat()}..{end.isoformat()} step={args.step}s "
        f"gpu_rows={total_gpu_rows} cpu_rows={total_cpu_rows} apply={args.apply}"
    )
    print(f"gpu_hosts={sorted(gpu_hosts)}")
    print(f"cpu_hosts={sorted(cpu_hosts)}")
    if args.apply:
        print(f"upserted gpu_rows={total_gpu_rows} cpu_rows={total_cpu_rows}")
    else:
        print("dry_run=true; pass --apply to write rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grafana-url", default=os.environ.get("NEXUS_GRAFANA_URL", GRAFANA_URL_DEFAULT))
    parser.add_argument("--token-file", default=os.environ.get("NEXUS_GRAFANA_TOKEN_FILE", GRAFANA_TOKEN_FILE_DEFAULT))
    parser.add_argument(
        "--datasource-uid",
        default=os.environ.get("NEXUS_PROMETHEUS_DATASOURCE_UID", PROMETHEUS_DATASOURCE_UID_DEFAULT),
    )
    parser.add_argument("--prometheus-url", default=os.environ.get("NEXUS_PROMETHEUS_URL"))
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--step", type=int, default=300, help="Prometheus query_range step in seconds")
    parser.add_argument(
        "--chunk-hours", type=float, default=24.0, help="Query/write history in chunks; set 0 to disable"
    )
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--greenhouse-id", default=os.environ.get("GREENHOUSE_ID", "vallery"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
