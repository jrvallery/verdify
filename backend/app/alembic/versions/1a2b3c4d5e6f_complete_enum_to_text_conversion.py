"""Complete ENUM to TEXT conversion for remaining enums

Revision ID: 1a2b3c4d5e6f
Revises: 9f3a8e1d2c4b
Create Date: 2025-08-18 14:30:00.000000

Converts remaining PostgreSQL ENUMs to TEXT for consistency:
1. greenhouse_member.role (GreenhouseRole)
2. greenhouse_invite.status (InviteStatus)
3. zone_crop_observation.observation_type (ObservationType)

This completes the ENUM→TEXT migration strategy started in 9f3a8e1d2c4b.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, None] = '9f3a8e1d2c4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert remaining ENUMs to TEXT"""

    # 1. Convert greenhouse_member.role from ENUM to TEXT
    op.execute("ALTER TABLE greenhouse_member ALTER COLUMN role TYPE TEXT USING role::TEXT")

    # 2. Convert greenhouse_invite.status from ENUM to TEXT
    op.execute("ALTER TABLE greenhouse_invite ALTER COLUMN status TYPE TEXT USING status::TEXT")

    # 3. Convert zone_crop_observation.observation_type from ENUM to TEXT
    op.execute("ALTER TABLE zone_crop_observation ALTER COLUMN observation_type TYPE TEXT USING observation_type::TEXT")

    # 4. Drop the now-unused ENUM types
    op.execute("DROP TYPE IF EXISTS greenhouserole CASCADE")
    op.execute("DROP TYPE IF EXISTS invitestatus CASCADE")
    op.execute("DROP TYPE IF EXISTS observationtype CASCADE")


def downgrade() -> None:
    """Reverse the ENUM to TEXT conversion"""

    # Note: This is complex to reverse perfectly as we'd need to recreate ENUMs
    # For now, leave as TEXT (safer for iteration)
    # In production, we'd implement full rollback if needed
    pass
