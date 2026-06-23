"""Add prompt_type column to prompt_templates for fallback_analysis marker

Revision ID: 006
Revises: 005
Create Date: 2026-06-23
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("prompt_templates",
        sa.Column("prompt_type", sa.String(20),
                  server_default="general", nullable=False)
    )
    op.create_index("ix_prompt_templates_prompt_type", "prompt_templates", ["prompt_type"])


def downgrade() -> None:
    op.drop_index("ix_prompt_templates_prompt_type", table_name="prompt_templates")
    op.drop_column("prompt_templates", "prompt_type")
