"""add pinnie fulfillment fields

Revision ID: 6f8d9a2c4b1e
Revises: 37da7e0d38b9
Create Date: 2026-08-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "6f8d9a2c4b1e"
down_revision = "37da7e0d38b9"
branch_labels = None
depends_on = None


pinnie_size_enum = postgresql.ENUM(
    "PP",
    "P",
    "M",
    "G",
    "GG",
    "XGG",
    name="pinnie_size_enum",
    create_type=False,
)


def upgrade():
    bind = op.get_bind()
    pinnie_size_enum.create(bind, checkfirst=True)

    op.add_column(
        "pinnies",
        sa.Column("pinnie_size", pinnie_size_enum, nullable=True),
    )
    op.add_column(
        "pinnies",
        sa.Column("deposit_paid_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pinnies",
        sa.Column("payment_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pinnies",
        sa.Column("pinnie_delivered_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("pinnies", "pinnie_delivered_at")
    op.drop_column("pinnies", "payment_completed_at")
    op.drop_column("pinnies", "deposit_paid_at")
    op.drop_column("pinnies", "pinnie_size")

    bind = op.get_bind()
    pinnie_size_enum.drop(bind, checkfirst=True)
