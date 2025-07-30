"""initial migration

Revision ID: initial_migration
Revises: 
Create Date: 2024-01-XX XX:XX:XX.XXXXXX

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
import uuid
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'initial_migration'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Create all tables
    op.create_table(
        'user',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_superuser', sa.Boolean(), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )

    op.create_table(
        'greenhouse',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('owner_id', postgresql.UUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('outside_temperature', sa.Float(), nullable=False),
        sa.Column('outside_humidity', sa.Float(), nullable=False),
        sa.Column('type', sa.String(), nullable=True),
        sa.Column('latitude', sa.Float(), nullable=True),
        sa.Column('longitude', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Add other tables following the same pattern...
    # You'll need to add tables for Zone, Controller, Sensor, Equipment,
    # ZoneClimateHistory, and GreenhouseClimateHistory

def downgrade() -> None:
    # Drop all tables in reverse order
    op.drop_table('greenhouse')
    op.drop_table('user')
    # Add other drop_table commands...
