"""add manual player position to team assignments

Revision ID: b8c1d2e3f4a5
Revises: a4b5c6d7e8f9
Create Date: 2026-05-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b8c1d2e3f4a5"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


player_position_enum = postgresql.ENUM(
    "GOL",
    "ATAQUE",
    "DEFESA",
    name="player_position_enum",
    create_type=False,
)


def upgrade():
    bind = op.get_bind()
    player_position_enum.create(bind, checkfirst=True)
    op.add_column(
        "game_team_assignments",
        sa.Column("manual_player_position", player_position_enum, nullable=True),
    )


def downgrade():
    op.drop_column("game_team_assignments", "manual_player_position")
