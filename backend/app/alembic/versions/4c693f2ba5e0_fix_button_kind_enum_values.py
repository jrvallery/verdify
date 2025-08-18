"""fix_button_kind_enum_values

Revision ID: 4c693f2ba5e0
Revises: c491311ca35b
Create Date: 2025-08-18 07:39:47.692461

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '4c693f2ba5e0'
down_revision = 'c491311ca35b'
branch_labels = None
depends_on = None


def upgrade():
    # Update the ButtonKind enum values to match the model
    # First, we need to handle any existing data and update the enum

    # Drop the old enum type and recreate with correct values
    op.execute("ALTER TYPE buttonkind RENAME TO buttonkind_old")
    op.execute("CREATE TYPE buttonkind AS ENUM ('cool', 'heat', 'humid')")

    # Update the controller_button table to use the new enum
    # We need to map old values to new ones where possible
    op.execute("""
        ALTER TABLE controller_button
        ALTER COLUMN button_kind TYPE buttonkind
        USING (
            CASE
                WHEN button_kind::text = 'TEMP_UP' THEN 'heat'::buttonkind
                WHEN button_kind::text = 'TEMP_DOWN' THEN 'cool'::buttonkind
                WHEN button_kind::text = 'HUMIDITY_UP' THEN 'humid'::buttonkind
                WHEN button_kind::text = 'HUMIDITY_DOWN' THEN 'humid'::buttonkind
                ELSE 'cool'::buttonkind  -- default fallback
            END
        )
    """)

    # Drop the old enum type
    op.execute("DROP TYPE buttonkind_old")


def downgrade():
    # Reverse the enum change
    op.execute("ALTER TYPE buttonkind RENAME TO buttonkind_new")
    op.execute("CREATE TYPE buttonkind AS ENUM ('EMERGENCY_STOP', 'TEMP_UP', 'TEMP_DOWN', 'HUMIDITY_UP', 'HUMIDITY_DOWN', 'OVERRIDE_30MIN')")

    # Update controller_button table back to old enum values
    op.execute("""
        ALTER TABLE controller_button
        ALTER COLUMN button_kind TYPE buttonkind
        USING (
            CASE
                WHEN button_kind::text = 'heat' THEN 'TEMP_UP'::buttonkind
                WHEN button_kind::text = 'cool' THEN 'TEMP_DOWN'::buttonkind
                WHEN button_kind::text = 'humid' THEN 'HUMIDITY_UP'::buttonkind
                ELSE 'TEMP_UP'::buttonkind
            END
        )
    """)

    op.execute("DROP TYPE buttonkind_new")
