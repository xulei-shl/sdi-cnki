"""Add user_notification_configs table for per-user webhook settings

Revision ID: 005
Revises: 004
Create Date: 2026-05-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_notification_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True),
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(datetime('now', 'localtime'))"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(datetime('now', 'localtime'))"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("user_notification_configs")
