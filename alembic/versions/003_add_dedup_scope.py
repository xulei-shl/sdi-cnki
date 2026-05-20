"""Add dedup_scope_meta_task_id to meta_tasks table

Revision ID: 003
Revises: 002
Create Date: 2026-05-20
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meta_tasks", sa.Column("dedup_scope_meta_task_id", sa.Integer(), nullable=True))
    op.create_index(
        op.f("ix_meta_tasks_dedup_scope"),
        "meta_tasks",
        ["dedup_scope_meta_task_id"],
    )
    op.create_foreign_key(
        "fk_meta_tasks_dedup_scope",
        "meta_tasks", "meta_tasks",
        ["dedup_scope_meta_task_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_meta_tasks_dedup_scope", "meta_tasks", type_="foreignkey")
    op.drop_index(op.f("ix_meta_tasks_dedup_scope"), table_name="meta_tasks")
    op.drop_column("meta_tasks", "dedup_scope_meta_task_id")
