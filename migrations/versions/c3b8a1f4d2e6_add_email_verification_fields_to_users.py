"""add email verification fields to users

Revision ID: c3b8a1f4d2e6
Revises: ea4e6393a4df
Create Date: 2026-05-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c3b8a1f4d2e6"
down_revision = "ea4e6393a4df"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("email_verification_sent_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("email_verification_sent_at")
        batch_op.drop_column("email_verified_at")
