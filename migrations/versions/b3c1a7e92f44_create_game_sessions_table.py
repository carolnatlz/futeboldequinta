"""create game_sessions table

Revision ID: b3c1a7e92f44
Revises: 8d7f2f4e1c3a
Create Date: 2026-05-17 23:05:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b3c1a7e92f44"
down_revision = "8d7f2f4e1c3a"
branch_labels = None
depends_on = None


game_session_status_enum = postgresql.ENUM(
    "SCHEDULED",
    "OPEN",
    "CLOSED",
    "FINISHED",
    "CANCELLED",
    name="game_session_status_enum",
    create_type=False,
)


def upgrade():
    game_session_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "game_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            game_session_status_enum,
            nullable=False,
            server_default="SCHEDULED",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_date"),
    )


def downgrade():
    op.drop_table("game_sessions")
    game_session_status_enum.drop(op.get_bind(), checkfirst=True)
