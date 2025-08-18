"""add_unique_constraint_sensor_zone_kind

Revision ID: c491311ca35b
Revises: 28bf57b69a7f
Create Date: 2025-08-18 07:05:28.485886

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'c491311ca35b'
down_revision = '28bf57b69a7f'
branch_labels = None
depends_on = None


def upgrade():
    # Add unique constraint to ensure one sensor per (zone, kind) combination
    op.create_index(
        "uq_sensor_zone_kind",
        "sensor_zone_map",
        ["zone_id", "kind"],
        unique=True
    )


def downgrade():
    # Remove the unique constraint
    op.drop_index("uq_sensor_zone_kind", "sensor_zone_map")
