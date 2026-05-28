"""create game_team_assignments table

Revision ID: a4b5c6d7e8f9
Revises: f7c9a1b2d4e5
Create Date: 2026-05-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a4b5c6d7e8f9"
down_revision = "f7c9a1b2d4e5"
branch_labels = None
depends_on = None


team_code_enum = postgresql.ENUM(
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    name="team_code_enum",
    create_type=False,
)

game_team_assignment_source_enum = postgresql.ENUM(
    "AUTO",
    "MANUAL",
    name="game_team_assignment_source_enum",
    create_type=False,
)


def upgrade():
    bind = op.get_bind()
    team_code_enum.create(bind, checkfirst=True)
    game_team_assignment_source_enum.create(bind, checkfirst=True)

    op.create_table(
        "game_team_assignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("game_session_id", sa.UUID(), nullable=False),
        sa.Column("team_code", team_code_enum, nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("manual_player_name", sa.String(length=120), nullable=True),
        sa.Column(
            "source_type",
            game_team_assignment_source_enum,
            nullable=False,
            server_default="AUTO",
        ),
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
        sa.CheckConstraint(
            "user_id IS NOT NULL OR manual_player_name IS NOT NULL",
            name="ck_game_team_assignment_player_reference",
        ),
        sa.ForeignKeyConstraint(
            ["game_session_id"],
            ["game_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "game_session_id",
            "user_id",
            name="uq_game_team_assignment_session_user",
        ),
    )


def downgrade():
    op.drop_table("game_team_assignments")
    bind = op.get_bind()
    game_team_assignment_source_enum.drop(bind, checkfirst=True)
    team_code_enum.drop(bind, checkfirst=True)
