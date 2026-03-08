"""add rejection flag and defaults

Revision ID: 1b2f8c3f6d01
Revises: 07099972f819
Create Date: 2026-03-08 03:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1b2f8c3f6d01'
down_revision = '07099972f819'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'users',
        sa.Column('is_rejected', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )
    op.alter_column('users', 'is_active', server_default=sa.text('false'))


def downgrade():
    op.alter_column('users', 'is_active', server_default=None)
    op.drop_column('users', 'is_rejected')
