"""fix_zone_crop_table_names_and_field_names

Revision ID: a500c302750c
Revises: df42b94e7925
Create Date: 2025-08-16 20:16:29.444676

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a500c302750c'
down_revision = 'df42b94e7925'
branch_labels = None
depends_on = None


def upgrade():
    # ### Rename tables and columns to preserve data ###

    # 1. Rename tables
    op.rename_table('zonecrop', 'zone_crop')
    op.rename_table('zonecropobservation', 'zone_crop_observation')

    # 2. Rename columns in zone_crop table
    op.alter_column('zone_crop', 'planted_at', new_column_name='start_date')
    op.alter_column('zone_crop', 'harvested_at', new_column_name='end_date')

    # 3. Update foreign key constraint in zone_crop_observation to reference new table name
    op.drop_constraint('zonecropobservation_zone_crop_id_fkey', 'zone_crop_observation', type_='foreignkey')
    op.create_foreign_key(None, 'zone_crop_observation', 'zone_crop', ['zone_crop_id'], ['id'], ondelete='CASCADE')

    # ### end manual commands ###


def downgrade():
    # ### Reverse the changes ###

    # 1. Restore foreign key constraint
    op.drop_constraint(None, 'zone_crop_observation', type_='foreignkey')
    op.create_foreign_key('zonecropobservation_zone_crop_id_fkey', 'zone_crop_observation', 'zone_crop', ['zone_crop_id'], ['id'], ondelete='CASCADE')

    # 2. Restore column names in zone_crop table
    op.alter_column('zone_crop', 'start_date', new_column_name='planted_at')
    op.alter_column('zone_crop', 'end_date', new_column_name='harvested_at')

    # 3. Restore table names
    op.rename_table('zone_crop_observation', 'zonecropobservation')
    op.rename_table('zone_crop', 'zonecrop')

    # ### end manual commands ###
