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
    with op.batch_alter_table("meta_tasks") as batch_op:
        batch_op.add_column(sa.Column("dedup_scope_meta_task_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_meta_tasks_dedup_scope",
            ["dedup_scope_meta_task_id"],
        )
        batch_op.create_foreign_key(
            "fk_meta_tasks_dedup_scope",
            "meta_tasks",
            ["dedup_scope_meta_task_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("meta_tasks") as batch_op:
        batch_op.drop_constraint("fk_meta_tasks_dedup_scope", type_="foreignkey")
        batch_op.drop_index("ix_meta_tasks_dedup_scope")
        batch_op.drop_column("dedup_scope_meta_task_id")
