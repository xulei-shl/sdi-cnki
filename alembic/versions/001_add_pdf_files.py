"""Add pdf_files table and pdf_file_id to download_results

Revision ID: 001
Revises:
Create Date: 2026-05-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pdf_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("original_url", sa.String(length=500), nullable=True),
        sa.Column("pdf_path", sa.String(length=500), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("ref_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pdf_files_original_url"), "pdf_files", ["original_url"])

    op.add_column("download_results", sa.Column("pdf_file_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_download_results_pdf_file_id"), "download_results", ["pdf_file_id"])
    op.create_foreign_key(
        "fk_download_results_pdf_file_id",
        "download_results", "pdf_files",
        ["pdf_file_id"], ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_download_results_pdf_file_id", "download_results", type_="foreignkey")
    op.drop_index(op.f("ix_download_results_pdf_file_id"), table_name="download_results")
    op.drop_column("download_results", "pdf_file_id")
    op.drop_index(op.f("ix_pdf_files_original_url"), table_name="pdf_files")
    op.drop_table("pdf_files")
