"""create pinnies table

Revision ID: 1a2b3c4d5e6f
Revises: d1a2b3c4d5e6
Create Date: 2026-07-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1a2b3c4d5e6f"
down_revision = "d1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pinnies",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("pinnie_name", sa.String(length=120), nullable=True),
        sa.Column("pinnie_number", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pinnie_number"),
        sa.UniqueConstraint("user_id"),
    )


def downgrade():
    op.drop_table("pinnies")
