"""Add meta_task_dedup_scopes table for multi dedup scope support

Revision ID: 004
Revises: 003
Create Date: 2026-05-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meta_task_dedup_scopes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("meta_task_id", sa.Integer(), sa.ForeignKey("meta_tasks.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("dedup_meta_task_id", sa.Integer(), sa.ForeignKey("meta_tasks.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.UniqueConstraint("meta_task_id", "dedup_meta_task_id", name="idx_mtds_unique"),
    )

    op.execute("""
        INSERT INTO meta_task_dedup_scopes (meta_task_id, dedup_meta_task_id)
        SELECT id, dedup_scope_meta_task_id
        FROM meta_tasks
        WHERE dedup_scope_meta_task_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_table("meta_task_dedup_scopes")
