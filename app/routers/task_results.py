from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.task_instance import TaskInstance
from app.models.task_result import TaskResult
from app.services.download_progress import sync_review_status
from app.utils.exceptions import NotFoundError
from app.routers import get_current_user_from_header

router = APIRouter()


class PassRequest(BaseModel):
    is_passed: bool = True


@router.get("")
async def list_task_results(
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    return {"items": []}


@router.put("/{result_id}/pass")
async def mark_pass(
    result_id: int,
    data: PassRequest = PassRequest(),
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TaskResult).where(TaskResult.id == result_id))
    row = result.scalar_one_or_none()
    if not row:
        raise NotFoundError("TaskResult", result_id)
    row.is_passed = data.is_passed
    await _sync_instance(db, row)
    await db.commit()
    return {"id": row.id, "is_passed": row.is_passed}


@router.put("/{result_id}/reject")
async def mark_reject(
    result_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TaskResult).where(TaskResult.id == result_id))
    row = result.scalar_one_or_none()
    if not row:
        raise NotFoundError("TaskResult", result_id)
    row.is_passed = False
    await _sync_instance(db, row)
    await db.commit()
    return {"id": row.id, "is_passed": row.is_passed}


async def _sync_instance(db: AsyncSession, row: TaskResult) -> None:
    """单条审核也会改变「审核通过集合」，重算实例派生状态。"""
    inst = (
        await db.execute(
            select(TaskInstance).where(TaskInstance.id == row.task_instance_id)
        )
    ).scalar_one_or_none()
    if inst:
        await sync_review_status(db, inst)
