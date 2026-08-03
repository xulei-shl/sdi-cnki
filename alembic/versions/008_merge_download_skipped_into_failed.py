"""Merge download_results.download_status skipped into failed

Revision ID: 008
Revises: 007
Create Date: 2026-08-03
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 下载状态精简：skipped 与 failed 语义相同（下载未成功），合并为 failed
    op.execute("UPDATE download_results SET download_status = 'failed' WHERE download_status = 'skipped'")


def downgrade() -> None:
    # 数据不可逆：无法区分合并前原本就是 failed 与合并自 skipped 的行，留空
    pass
