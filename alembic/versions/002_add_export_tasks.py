"""Add export_tasks table for M9 export packaging

Revision ID: 002
Revises: 001
Create Date: 2026-05-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_instance_id", sa.Integer(), nullable=False),
        sa.Column("creator_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_foreign_key("fk_export_task_instance", "export_tasks", "task_instances",
                          ["task_instance_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_export_user", "export_tasks", "users",
                          ["creator_id"], ["id"], ondelete="CASCADE")
    op.create_index(op.f("ix_export_task_instance"), "export_tasks", ["task_instance_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_export_task_instance"), table_name="export_tasks")
    op.drop_constraint("fk_export_task_instance", "export_tasks", type_="foreignkey")
    op.drop_constraint("fk_export_user", "export_tasks", type_="foreignkey")
    op.drop_table("export_tasks")
