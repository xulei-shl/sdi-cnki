"""Add email_enabled, email_to, module_flags, email_module_flags to user_notification_configs

Revision ID: 007
Revises: 006
Create Date: 2026-08-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_notification_configs",
        sa.Column("email_enabled", sa.Boolean(), server_default=sa.text("0"), nullable=False)
    )
    op.add_column("user_notification_configs",
        sa.Column("email_to", sa.Text(), nullable=True)
    )
    op.add_column("user_notification_configs",
        sa.Column("module_flags", sa.Text(), nullable=True)
    )
    op.add_column("user_notification_configs",
        sa.Column("email_module_flags", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("user_notification_configs", "email_module_flags")
    op.drop_column("user_notification_configs", "module_flags")
    op.drop_column("user_notification_configs", "email_to")
    op.drop_column("user_notification_configs", "email_enabled")