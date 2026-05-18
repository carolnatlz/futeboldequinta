"""add reserved checkin status

Revision ID: e4f6c8a1b2d3
Revises: c52c0d9c4a12
Create Date: 2026-05-18 12:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e4f6c8a1b2d3"
down_revision = "c52c0d9c4a12"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE checkin_status_enum ADD VALUE IF NOT EXISTS 'RESERVED'")
    op.execute(
        """
        UPDATE game_checkins AS gc
        SET status = 'RESERVED'::checkin_status_enum,
            cancelled_at = NULL
        FROM users AS u
        WHERE gc.user_id = u.id
          AND u.role = 'ORGANIZER'::user_role_enum
          AND gc.status IN ('CONFIRMED'::checkin_status_enum, 'WAITLIST'::checkin_status_enum)
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE game_checkins
        SET status = 'CONFIRMED'::checkin_status_enum
        WHERE status = 'RESERVED'::checkin_status_enum
        """
    )
    op.execute("ALTER TYPE checkin_status_enum RENAME TO checkin_status_enum_old")
    op.execute(
        """
        CREATE TYPE checkin_status_enum AS ENUM (
            'CONFIRMED',
            'WAITLIST',
            'CANCELLED',
            'NO_SHOW',
            'ATTENDED'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE game_checkins
        ALTER COLUMN status DROP DEFAULT
        """
    )
    op.execute(
        """
        ALTER TABLE game_checkins
        ALTER COLUMN status TYPE checkin_status_enum
        USING status::text::checkin_status_enum
        """
    )
    op.execute(
        """
        ALTER TABLE game_checkins
        ALTER COLUMN status SET DEFAULT 'CONFIRMED'::checkin_status_enum
        """
    )
    op.execute("DROP TYPE checkin_status_enum_old")
