"""add in progress game session status

Revision ID: f7c9a1b2d4e5
Revises: e4f6c8a1b2d3
Create Date: 2026-05-27 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "f7c9a1b2d4e5"
down_revision = "e4f6c8a1b2d3"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE game_session_status_enum ADD VALUE IF NOT EXISTS 'IN_PROGRESS'")


def downgrade():
    op.execute(
        """
        UPDATE game_sessions
        SET status = 'CLOSED'::game_session_status_enum
        WHERE status = 'IN_PROGRESS'::game_session_status_enum
        """
    )
    op.execute("ALTER TYPE game_session_status_enum RENAME TO game_session_status_enum_old")
    op.execute(
        """
        CREATE TYPE game_session_status_enum AS ENUM (
            'SCHEDULED',
            'OPEN',
            'CLOSED',
            'FINISHED',
            'CANCELLED'
        )
        """
    )
    op.execute(
        """
        ALTER TABLE game_sessions
        ALTER COLUMN status DROP DEFAULT
        """
    )
    op.execute(
        """
        ALTER TABLE game_sessions
        ALTER COLUMN status TYPE game_session_status_enum
        USING status::text::game_session_status_enum
        """
    )
    op.execute(
        """
        ALTER TABLE game_sessions
        ALTER COLUMN status SET DEFAULT 'SCHEDULED'::game_session_status_enum
        """
    )
    op.execute("DROP TYPE game_session_status_enum_old")
