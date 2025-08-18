"""fix enum case for greenhouse rbac

Revision ID: 28bf57b69a7f
Revises: 592471aa0e5c
Create Date: 2025-08-17 18:10:57.263951

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '28bf57b69a7f'
down_revision = '592471aa0e5c'
branch_labels = None
depends_on = None


def upgrade():
    # 1) Create new enums with lowercase values
    op.execute("CREATE TYPE greenhouse_role_v2 AS ENUM ('owner','operator')")
    op.execute("CREATE TYPE invite_status_v2 AS ENUM ('pending','accepted','revoked','expired')")

    # 2) Alter columns to new types with case conversion
    op.execute("""
        ALTER TABLE greenhouse_member
        ALTER COLUMN role TYPE greenhouse_role_v2
        USING lower(role::text)::greenhouse_role_v2
    """)
    op.execute("""
        ALTER TABLE greenhouse_invite
        ALTER COLUMN role TYPE greenhouse_role_v2
        USING lower(role::text)::greenhouse_role_v2
    """)
    op.execute("""
        ALTER TABLE greenhouse_invite
        ALTER COLUMN status TYPE invite_status_v2
        USING lower(status::text)::invite_status_v2
    """)

    # 3) Drop old types and rename new types
    op.execute("DROP TYPE greenhouserole")
    op.execute("DROP TYPE invitestatus")
    op.execute("ALTER TYPE greenhouse_role_v2 RENAME TO greenhouserole")
    op.execute("ALTER TYPE invite_status_v2 RENAME TO invitestatus")

    # 4) Convert datetime columns to timezone-aware with explicit UTC casting
    op.execute("""
        ALTER TABLE greenhouse_invite
        ALTER COLUMN expires_at TYPE TIMESTAMPTZ
        USING (expires_at AT TIME ZONE 'UTC')
    """)
    op.execute("""
        ALTER TABLE greenhouse_invite
        ALTER COLUMN created_at TYPE TIMESTAMPTZ
        USING (created_at AT TIME ZONE 'UTC')
    """)
    op.execute("""
        ALTER TABLE greenhouse_invite
        ALTER COLUMN updated_at TYPE TIMESTAMPTZ
        USING (updated_at AT TIME ZONE 'UTC')
    """)
    op.execute("""
        ALTER TABLE greenhouse_member
        ALTER COLUMN created_at TYPE TIMESTAMPTZ
        USING (created_at AT TIME ZONE 'UTC')
    """)

    # 5) Replace unique constraint with partial unique index for pending invites
    op.drop_constraint("uq_greenhouse_invite_active", "greenhouse_invite", type_="unique")
    op.create_index(
        "uq_greenhouse_invite_pending",
        "greenhouse_invite",
        ["greenhouse_id", "email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'")
    )

    # 6) Add performance indexes
    op.create_index("ix_greenhouse_invite_expires_at", "greenhouse_invite", ["expires_at"])
    op.create_index("ix_greenhouse_invite_status_email", "greenhouse_invite", ["status", "email"])


def downgrade():
    # 1) Drop performance indexes
    op.drop_index("ix_greenhouse_invite_status_email", "greenhouse_invite")
    op.drop_index("ix_greenhouse_invite_expires_at", "greenhouse_invite")

    # 2) Restore unique constraint and drop partial index
    op.drop_index("uq_greenhouse_invite_pending", "greenhouse_invite")
    op.create_unique_constraint("uq_greenhouse_invite_active", "greenhouse_invite", ["greenhouse_id", "email"])

    # 3) Convert datetime columns back to timezone-naive with explicit casting
    op.execute("""
        ALTER TABLE greenhouse_member
        ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE
        USING (created_at AT TIME ZONE 'UTC')
    """)
    op.execute("""
        ALTER TABLE greenhouse_invite
        ALTER COLUMN updated_at TYPE TIMESTAMP WITHOUT TIME ZONE
        USING (updated_at AT TIME ZONE 'UTC')
    """)
    op.execute("""
        ALTER TABLE greenhouse_invite
        ALTER COLUMN created_at TYPE TIMESTAMP WITHOUT TIME ZONE
        USING (created_at AT TIME ZONE 'UTC')
    """)
    op.execute("""
        ALTER TABLE greenhouse_invite
        ALTER COLUMN expires_at TYPE TIMESTAMP WITHOUT TIME ZONE
        USING (expires_at AT TIME ZONE 'UTC')
    """)

    # 4) Create old enums with uppercase values
    op.execute("CREATE TYPE greenhouse_role_v2 AS ENUM ('OWNER','OPERATOR')")
    op.execute("CREATE TYPE invite_status_v2 AS ENUM ('PENDING','ACCEPTED','REVOKED','EXPIRED')")

    # 5) Alter columns back to uppercase types
    op.execute("""
        ALTER TABLE greenhouse_member
        ALTER COLUMN role TYPE greenhouse_role_v2
        USING upper(role::text)::greenhouse_role_v2
    """)
    op.execute("""
        ALTER TABLE greenhouse_invite
        ALTER COLUMN role TYPE greenhouse_role_v2
        USING upper(role::text)::greenhouse_role_v2
    """)
    op.execute("""
        ALTER TABLE greenhouse_invite
        ALTER COLUMN status TYPE invite_status_v2
        USING upper(status::text)::invite_status_v2
    """)

    # 6) Drop lowercase types and rename uppercase types
    op.execute("DROP TYPE greenhouserole")
    op.execute("DROP TYPE invitestatus")
    op.execute("ALTER TYPE greenhouse_role_v2 RENAME TO greenhouserole")
    op.execute("ALTER TYPE invite_status_v2 RENAME TO invitestatus")
