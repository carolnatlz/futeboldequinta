"""add checkin audit fields

Revision ID: ea4e6393a4df
Revises: b8c1d2e3f4a5
Create Date: 2026-05-29 05:02:30.577118

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ea4e6393a4df'
down_revision = 'b8c1d2e3f4a5'
branch_labels = None
depends_on = None

checkin_update_source_enum = sa.Enum(
    'SELF_SERVICE',
    'ADMIN_PANEL',
    'TEAM_DRAW',
    'SYSTEM',
    name='checkin_update_source_enum',
)


def upgrade():
    checkin_update_source_enum.create(op.get_bind(), checkfirst=True)

    with op.batch_alter_table('game_checkins', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_updated_by_user_id', sa.UUID(), nullable=True))
        batch_op.add_column(sa.Column('last_updated_by_role', sa.Enum('ADMIN', 'PLAYER', 'ORGANIZER', name='user_role_enum'), nullable=True))
        batch_op.add_column(sa.Column('last_updated_source', checkin_update_source_enum, nullable=True))
        batch_op.create_foreign_key(
            'fk_game_checkins_last_updated_by_user_id_users',
            'users',
            ['last_updated_by_user_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('game_checkins', schema=None) as batch_op:
        batch_op.drop_constraint('fk_game_checkins_last_updated_by_user_id_users', type_='foreignkey')
        batch_op.drop_column('last_updated_source')
        batch_op.drop_column('last_updated_by_role')
        batch_op.drop_column('last_updated_by_user_id')
    checkin_update_source_enum.drop(op.get_bind(), checkfirst=True)
