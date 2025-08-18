"""fix enum case for greenhouse rbac

Revision ID: 592471aa0e5c
Revises: 42200736b281
Create Date: 2025-08-17 18:09:09.976898

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '592471aa0e5c'
down_revision = '42200736b281'
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
