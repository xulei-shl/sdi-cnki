from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_instance import TaskInstance
from app.models.task_result import TaskResult
from app.utils.normalize import normalize


async def check_duplicate(
    db: AsyncSession,
    title_norm: str,
    journal_norm: str,
    year: int | None,
    meta_task_id: int,
    current_instance_id: int,
    dedup_scope_meta_task_ids: list[int] | None = None,
) -> Optional[int]:
    if year is None:
        return None
    stmt = select(TaskResult).where(
        TaskResult.title_normalized == title_norm,
        TaskResult.source_journal_normalized == journal_norm,
        TaskResult.publish_year == year,
    )
    result = await db.execute(stmt)
    existing_records = result.scalars().all()
    if not existing_records:
        return None

    scope_ids: set[int] = set(dedup_scope_meta_task_ids) if dedup_scope_meta_task_ids else set()

    dup_ref_id: Optional[int] = None
    for existing in existing_records:
        inst_stmt = select(TaskInstance).where(TaskInstance.id == existing.task_instance_id)
        inst_result = await db.execute(inst_stmt)
        existing_instance = inst_result.scalar_one_or_none()
        if not existing_instance:
            continue
        if existing_instance.meta_task_id == meta_task_id:
            return existing.id
        if existing_instance.meta_task_id in scope_ids:
            dup_ref_id = existing.id

    return dup_ref_id


async def batch_check_and_mark(
    db: AsyncSession,
    records: list[dict],
    meta_task_id: int,
    instance_id: int,
    dedup_scope_meta_task_ids: list[int] | None = None,
) -> tuple[list[dict], int]:
    duplicates = 0
    for record in records:
        title = record.get("title", "") or ""
        journal = record.get("source_journal", "") or ""
        year = record.get("publish_year")
        title_norm = normalize(title)
        journal_norm = normalize(journal)
        record["title_normalized"] = title_norm
        record["source_journal_normalized"] = journal_norm
        dup_ref = await check_duplicate(
            db, title_norm, journal_norm, year, meta_task_id, instance_id,
            dedup_scope_meta_task_ids=dedup_scope_meta_task_ids,
        )
        if dup_ref is not None:
            record["is_duplicate"] = True
            record["duplicate_ref_id"] = dup_ref
            duplicates += 1
        else:
            record["is_duplicate"] = False
            record["duplicate_ref_id"] = None
    return records, duplicates
