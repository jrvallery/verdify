from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from testcontainers.postgres import PostgresContainer


def _docker_available() -> bool:
    try:
        import docker  # type: ignore

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


@pytest.mark.slow
def test_alembic_upgrade_head_on_timescale_container():
    if not _docker_available():
        pytest.skip("Docker not available; skipping Timescale migration test")
    """
    Spin up a TimescaleDB container and run Alembic migrations to head.

    Verifies existence of key meta tables and hypertables.
    """
    image = "timescale/timescaledb:latest-pg15"
    with PostgresContainer(image=image) as pg:
        # Get connection URL in a form psycopg can use
        conn_url = pg.get_connection_url()
        parsed = urlparse(conn_url)

        # Set env for app.settings used by Alembic env.py
        os.environ["POSTGRES_SERVER"] = parsed.hostname or "localhost"
        os.environ["POSTGRES_PORT"] = str(parsed.port or 5432)
        os.environ["POSTGRES_USER"] = parsed.username or "postgres"
        os.environ["POSTGRES_PASSWORD"] = parsed.password or ""
        # Strip leading '/' in path
        os.environ["POSTGRES_DB"] = (parsed.path or "/postgres").lstrip("/")

        # Configure Alembic
        backend_dir = Path(__file__).resolve().parents[1]
        alembic_ini = backend_dir / "alembic.ini"
        cfg = Config(str(alembic_ini))

        # Run migrations
        command.upgrade(cfg, "head")

        # Validate schema via psycopg connection
        with psycopg.connect(conn_url) as conn:
            with conn.cursor() as cur:
                # Meta tables
                cur.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'sensor_kind_meta'"
                )
                assert cur.fetchone() is not None

                cur.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_name = 'actuator_kind_meta'"
                )
                assert cur.fetchone() is not None

                # Hypertable existence via Timescale catalog
                cur.execute(
                    "SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = 'sensor_reading'"
                )
                assert cur.fetchone() is not None

                cur.execute(
                    "SELECT 1 FROM timescaledb_information.hypertables WHERE hypertable_name = 'controller_status'"
                )
                assert cur.fetchone() is not None
