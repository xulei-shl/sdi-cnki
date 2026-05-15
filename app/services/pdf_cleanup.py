"""PDF file cleanup with reference counting."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.download_result import DownloadResult
from app.models.pdf_file import PdfFile
from app.utils.logging import get_logger

logger = get_logger("pdf_cleanup")


async def decrement_pdf_refs_for_instance(db: AsyncSession, instance_id: int) -> None:
    """Decrement ref_count for all PdfFiles linked to this instance's downloads."""
    stmt = (
        select(PdfFile)
        .join(DownloadResult, DownloadResult.pdf_file_id == PdfFile.id)
        .where(DownloadResult.task_instance_id == instance_id)
    )
    r = await db.execute(stmt)
    pdf_files = r.scalars().all()

    for pf in pdf_files:
        pf.ref_count = max(0, (pf.ref_count or 0) - 1)
        if pf.ref_count <= 0:
            _delete_physical_file(pf.pdf_path)
            await db.delete(pf)

    await db.commit()


def _delete_physical_file(pdf_path: str | None) -> None:
    if not pdf_path:
        return
    try:
        p = Path(pdf_path)
        if p.exists():
            os.remove(str(p))
            logger.info(f"Deleted PDF file: {pdf_path}")
    except Exception as e:
        logger.warning(f"Failed to delete PDF file {pdf_path}: {e}")
