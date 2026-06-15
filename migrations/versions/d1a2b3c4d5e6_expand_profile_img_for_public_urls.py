"""expand profile image metadata

Revision ID: d1a2b3c4d5e6
Revises: c3b8a1f4d2e6
Create Date: 2026-06-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d1a2b3c4d5e6"
down_revision = "c3b8a1f4d2e6"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "users",
        "profile_img",
        existing_type=sa.String(length=255),
        type_=sa.String(length=2048),
        existing_nullable=True,
    )
    op.add_column(
        "users",
        sa.Column("profile_img_public_id", sa.String(length=255), nullable=True),
    )


def downgrade():
    op.drop_column("users", "profile_img_public_id")
    op.alter_column(
        "users",
        "profile_img",
        existing_type=sa.String(length=2048),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
