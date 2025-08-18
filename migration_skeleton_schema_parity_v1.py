"""Schema parity fixes: ENUM to TEXT conversion and missing constraints

Revision ID: schema_parity_v1
Revises: 52e718e4b837
Create Date: 2025-08-18 12:45:00.000000

This migration addresses critical schema/model drift identified in bundle review:
1. Convert PostgreSQL ENUMs to TEXT for easier iteration
2. Add missing Plan schema fields and constraints
3. Add missing Config/Idempotency uniqueness constraints
4. Fix Controller climate controller partial unique index

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "schema_parity_v1"
down_revision: Union[str, None] = "52e718e4b837"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert ENUMs to TEXT and add missing constraints"""

    # === ENUM to TEXT Conversions ===

    # 1. Convert sensor.scope from ENUM to TEXT
    op.execute("ALTER TABLE sensor ALTER COLUMN scope TYPE TEXT USING scope::TEXT")

    # 2. Convert actuator.kind from ENUM to TEXT
    op.execute("ALTER TABLE actuator ALTER COLUMN kind TYPE TEXT USING kind::TEXT")

    # 3. Convert controller_button.button_kind from ENUM to TEXT
    op.execute(
        "ALTER TABLE controller_button ALTER COLUMN button_kind TYPE TEXT USING button_kind::TEXT"
    )

    # 4. Drop the now-unused ENUM types
    op.execute("DROP TYPE IF EXISTS sensorscope")
    op.execute("DROP TYPE IF EXISTS actuatorkind")
    op.execute("DROP TYPE IF EXISTS buttonkind")

    # === Plan Schema Additions ===

    # Add missing Plan fields
    op.add_column(
        "plan",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "plan",
        sa.Column(
            "effective_from",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "plan",
        sa.Column(
            "effective_to",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '1 year'"),
        ),
    )
    op.add_column(
        "plan",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Add partial unique index for active plans (only one active per greenhouse)
    op.execute(
        """
        CREATE UNIQUE INDEX uq_plan_greenhouse_active
        ON plan(greenhouse_id)
        WHERE is_active = true
    """
    )

    # === Missing Constraint Additions ===

    # Config snapshot uniqueness
    op.create_unique_constraint(
        "uq_config_snapshot_greenhouse_version",
        "config_snapshot",
        ["greenhouse_id", "version"],
    )

    # Idempotency key uniqueness and indexing
    op.create_unique_constraint(
        "uq_idempotency_key_controller", "idempotency_key", ["key", "controller_id"]
    )
    op.create_index("ix_idempotency_key_expires_at", "idempotency_key", ["expires_at"])

    # === State Machine Cleanup ===

    # Add missing must_off_fan_groups column if not exists
    op.add_column(
        "state_machine_fallback",
        sa.Column(
            "must_off_fan_groups",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )

    # === Controller Climate Fix ===

    # Drop incorrect unique constraint on (greenhouse_id, is_climate_controller)
    op.execute(
        "ALTER TABLE controller DROP CONSTRAINT IF EXISTS uq_controller_greenhouse_climate"
    )

    # Add partial unique index ensuring only one climate controller per greenhouse
    op.execute(
        """
        CREATE UNIQUE INDEX uq_controller_greenhouse_climate_partial
        ON controller(greenhouse_id)
        WHERE is_climate_controller = true
    """
    )


def downgrade() -> None:
    """Reverse the schema parity changes"""

    # === Reverse Controller Climate Fix ===
    op.execute("DROP INDEX IF EXISTS uq_controller_greenhouse_climate_partial")

    # === Reverse State Machine Cleanup ===
    op.drop_column("state_machine_fallback", "must_off_fan_groups")

    # === Reverse Missing Constraints ===
    op.drop_index("ix_idempotency_key_expires_at", table_name="idempotency_key")
    op.drop_constraint(
        "uq_idempotency_key_controller", "idempotency_key", type_="unique"
    )
    op.drop_constraint(
        "uq_config_snapshot_greenhouse_version", "config_snapshot", type_="unique"
    )

    # === Reverse Plan Schema ===
    op.execute("DROP INDEX IF EXISTS uq_plan_greenhouse_active")
    op.drop_column("plan", "updated_at")
    op.drop_column("plan", "effective_to")
    op.drop_column("plan", "effective_from")
    op.drop_column("plan", "is_active")

    # === Reverse ENUM Conversions ===
    # Note: This is complex to reverse perfectly as we'd need to recreate ENUMs
    # For now, leave as TEXT (safer for iteration)
    pass
