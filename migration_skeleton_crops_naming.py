"""Crops table naming parity: zonecrop -> zone_crop

Revision ID: crops_table_naming
Revises: schema_parity_v1
Create Date: 2025-08-18 12:50:00.000000

This migration renames crop tables to match SQLModel class names:
- zonecrop -> zone_crop
- zonecropobservation -> zone_crop_observation

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "crops_table_naming"
down_revision: Union[str, None] = "schema_parity_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename crop tables to match model naming convention"""

    # Check if old table names exist before renaming
    # (In case a later migration already handled this)

    # Rename zonecrop to zone_crop
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'zonecrop') THEN
                ALTER TABLE zonecrop RENAME TO zone_crop;
            END IF;
        END $$;
    """
    )

    # Rename zonecropobservation to zone_crop_observation
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'zonecropobservation') THEN
                ALTER TABLE zonecropobservation RENAME TO zone_crop_observation;
            END IF;
        END $$;
    """
    )

    # Update foreign key references if they exist
    op.execute(
        """
        DO $$
        BEGIN
            -- Update FK constraint name if it exists
            IF EXISTS (SELECT 1 FROM information_schema.table_constraints
                      WHERE constraint_name LIKE '%zonecrop%' AND table_name = 'zone_crop_observation') THEN
                ALTER TABLE zone_crop_observation
                RENAME CONSTRAINT zonecropobservation_zone_crop_id_fkey TO zone_crop_observation_zone_crop_id_fkey;
            END IF;
        END $$;
    """
    )


def downgrade() -> None:
    """Reverse the table name changes"""

    # Rename zone_crop_observation back to zonecropobservation
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'zone_crop_observation') THEN
                ALTER TABLE zone_crop_observation RENAME TO zonecropobservation;
            END IF;
        END $$;
    """
    )

    # Rename zone_crop back to zonecrop
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'zone_crop') THEN
                ALTER TABLE zone_crop RENAME TO zonecrop;
            END IF;
        END $$;
    """
    )

    # Revert FK constraint name
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.table_constraints
                      WHERE constraint_name = 'zone_crop_observation_zone_crop_id_fkey') THEN
                ALTER TABLE zonecropobservation
                RENAME CONSTRAINT zone_crop_observation_zone_crop_id_fkey TO zonecropobservation_zone_crop_id_fkey;
            END IF;
        END $$;
    """
    )
