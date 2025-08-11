"""Add cascading deletions for greenhouse controllers

Revision ID: 95c745e65778
Revises: 73088fa7ea0e
Create Date: 2025-08-11 12:07:45.445520

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '95c745e65778'
down_revision = '73088fa7ea0e'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
