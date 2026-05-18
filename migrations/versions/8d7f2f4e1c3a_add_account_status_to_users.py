"""replace user booleans with account status

Revision ID: 8d7f2f4e1c3a
Revises: 2fd86ec70ed8
Create Date: 2026-05-17 22:05:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "8d7f2f4e1c3a"
down_revision = "2fd86ec70ed8"
branch_labels = None
depends_on = None


account_status_enum = postgresql.ENUM(
    "PENDING",
    "APPROVED",
    "REJECTED",
    name="account_status_enum",
)


def upgrade():
    account_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "users",
        sa.Column("account_status", account_status_enum, nullable=True),
    )

    op.execute(
        """
        UPDATE users
        SET account_status = CASE
            WHEN is_rejected IS TRUE THEN 'REJECTED'::account_status_enum
            WHEN is_active IS TRUE THEN 'APPROVED'::account_status_enum
            ELSE 'PENDING'::account_status_enum
        END
        """
    )

    op.alter_column(
        "users",
        "account_status",
        existing_type=account_status_enum,
        nullable=False,
        server_default="PENDING",
    )

    op.drop_column("users", "is_rejected")
    op.drop_column("users", "is_active")


def downgrade():
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_rejected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.execute(
        """
        UPDATE users
        SET
            is_active = CASE
                WHEN account_status = 'APPROVED' THEN TRUE
                ELSE FALSE
            END,
            is_rejected = CASE
                WHEN account_status = 'REJECTED' THEN TRUE
                ELSE FALSE
            END
        """
    )

    op.alter_column(
        "users",
        "is_rejected",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=None,
    )

    op.drop_column("users", "account_status")
    account_status_enum.drop(op.get_bind(), checkfirst=True)
