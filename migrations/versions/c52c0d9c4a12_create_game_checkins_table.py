"""create game_checkins table

Revision ID: c52c0d9c4a12
Revises: b3c1a7e92f44
Create Date: 2026-05-18 00:05:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "c52c0d9c4a12"
down_revision = "b3c1a7e92f44"
branch_labels = None
depends_on = None


checkin_status_enum = postgresql.ENUM(
    "CONFIRMED",
    "WAITLIST",
    "CANCELLED",
    "NO_SHOW",
    "ATTENDED",
    name="checkin_status_enum",
    create_type=False,
)


def upgrade():
    checkin_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "game_checkins",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_session_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            checkin_status_enum,
            nullable=False,
            server_default="CONFIRMED",
        ),
        sa.Column(
            "checked_in_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["game_session_id"],
            ["game_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_session_id",
            "user_id",
            name="uq_game_checkin_session_user",
        ),
    )

    op.create_index(
        "ix_game_checkins_game_session_id",
        "game_checkins",
        ["game_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_game_checkins_user_id",
        "game_checkins",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_game_checkins_status",
        "game_checkins",
        ["status"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_game_checkins_status", table_name="game_checkins")
    op.drop_index("ix_game_checkins_user_id", table_name="game_checkins")
    op.drop_index("ix_game_checkins_game_session_id", table_name="game_checkins")
    op.drop_table("game_checkins")
    checkin_status_enum.drop(op.get_bind(), checkfirst=True)
