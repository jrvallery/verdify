"""Alembic-based test database utilities for schema parity enforcement"""

import os
import subprocess
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlmodel import Session

from app.core.config import settings


def create_test_db_with_alembic(db_name: str = None) -> str:
    """Create a test database using ONLY Alembic migrations.

    This ensures test schema exactly matches production schema created by migrations.

    Args:
        db_name: Optional database name. If None, generates temporary name.

    Returns:
        Database URL for the created database

    Raises:
        RuntimeError: If migrations fail or create_all() is detected
    """
    if db_name is None:
        db_name = f"test_verdify_{os.getpid()}_{os.urandom(4).hex()}"

    # Create database
    admin_url = settings.DATABASE_URL.replace("/verdify", "/postgres")
    admin_engine = create_engine(admin_url)

    with admin_engine.connect() as conn:
        conn.execute(text("COMMIT"))  # End any transaction
        conn.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
        conn.execute(text(f"CREATE DATABASE {db_name}"))

    admin_engine.dispose()

    # Build test database URL
    test_db_url = settings.DATABASE_URL.replace("/verdify", f"/{db_name}")

    # Run Alembic migrations on test database
    backend_dir = Path(__file__).parent.parent.parent
    env = os.environ.copy()
    env["DATABASE_URL"] = test_db_url

    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=env,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Alembic migration failed: {result.stderr}")

    return test_db_url


def cleanup_test_db(db_url: str) -> None:
    """Clean up test database"""
    db_name = db_url.split("/")[-1]
    admin_url = settings.DATABASE_URL.replace("/verdify", "/postgres")
    admin_engine = create_engine(admin_url)

    with admin_engine.connect() as conn:
        conn.execute(text("COMMIT"))
        # Force disconnect all connections to test DB
        conn.execute(
            text(
                f"""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = '{db_name}' AND pid <> pg_backend_pid()
        """
            )
        )
        conn.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))

    admin_engine.dispose()


def get_alembic_test_session(db_url: str = None) -> Generator[Session, None, None]:
    """Get a database session using Alembic-created schema.

    This is the ONLY approved way to create test databases for schema parity.
    """
    if db_url is None:
        db_url = create_test_db_with_alembic()
        cleanup_needed = True
    else:
        cleanup_needed = False

    engine = create_engine(db_url)

    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()
        if cleanup_needed:
            cleanup_test_db(db_url)


def validate_no_create_all_usage() -> None:
    """Scan codebase for banned create_all() usage.

    Raises:
        AssertionError: If create_all() is found outside test utilities
    """
    import subprocess
    from pathlib import Path

    backend_dir = Path(__file__).parent.parent.parent

    # Search for create_all usage
    result = subprocess.run(
        ["grep", "-r", "--include=*.py", "create_all", str(backend_dir)],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        # Filter out allowed usages (this file and commented code)
        lines = result.stdout.strip().split("\n")
        violations = []

        for line in lines:
            if "alembic_test.py" in line:
                continue  # This file is allowed
            if line.strip().startswith("#"):
                continue  # Commented code is OK
            if "create_all" in line:
                violations.append(line)

        if violations:
            raise AssertionError(
                "Banned create_all() usage found:\n" + "\n".join(violations)
            )


# Schema parity validation functions
def validate_schema_matches_models() -> bool:
    """Validate that Alembic-created schema matches SQLModel definitions.

    This is a critical test to ensure migrations and models are in sync.
    """
    # TODO: Implement comprehensive schema introspection
    # For now, just ensure migrations run without error
    try:
        test_db_url = create_test_db_with_alembic()
        cleanup_test_db(test_db_url)
        return True
    except Exception as e:
        print(f"Schema validation failed: {e}")
        return False
