"""add pinnie batch settings

Revision ID: 9c2e7a4b6d1f
Revises: 6f8d9a2c4b1e
Create Date: 2026-08-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9c2e7a4b6d1f"
down_revision = "6f8d9a2c4b1e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pinnies",
        sa.Column("pinnie_batch_number", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_pinnies_batch_number_positive",
        "pinnies",
        "pinnie_batch_number IS NULL OR pinnie_batch_number > 0",
    )

    pinnie_settings = op.create_table(
        "pinnie_settings",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column(
            "current_batch_number",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_pinnie_settings_singleton"),
        sa.CheckConstraint(
            "current_batch_number > 0",
            name="ck_pinnie_settings_current_batch_positive",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.bulk_insert(
        pinnie_settings,
        [{"id": 1, "current_batch_number": 1}],
    )


def downgrade():
    op.drop_table("pinnie_settings")
    op.drop_constraint(
        "ck_pinnies_batch_number_positive",
        "pinnies",
        type_="check",
    )
    op.drop_column("pinnies", "pinnie_batch_number")
