from __future__ import annotations

import json
import os
from fastapi import APIRouter, Depends, Query

from app.utils import timezone
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.export_task import ExportTask
from app.models.task_instance import TaskInstance
from app.routers import get_current_user_from_header
from app.routers.sse import broadcast_event
from app.task_queue.crud import TaskQueueService
from app.utils.exceptions import NotFoundError, ValidationError

router = APIRouter()


@router.post("/task-instances/{instance_id}/export")
async def start_export(
    instance_id: int,
    current_user=Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TaskInstance).where(TaskInstance.id == instance_id))
    instance = result.scalar_one_or_none()
    if not instance:
        raise NotFoundError("TaskInstance", instance_id)
    if instance.status not in ("analyzing_completed", "download_queued", "downloading", "completed", "failed"):
        raise ValidationError(f"状态 {instance.status} 不允许导出，需要 analyzing_completed/download_queued/downloading/completed/failed")

    export_task = ExportTask(
        task_instance_id=instance_id,
        creator_id=current_user.id,
        status="pending",
    )
    db.add(export_task)
    await db.commit()
    await db.refresh(export_task)

    svc = TaskQueueService(db)
    await svc.enqueue(
        queue_type="export",
        task_type="export_package",
        params_json=json.dumps({
            "export_id": export_task.id,
            "instance_id": instance_id,
            "instance_no": instance.instance_no,
        }),
        task_key=f"export_{instance.instance_no}_{export_task.id}",
    )

    return {"export_id": export_task.id, "status": "pending", "message": "导出任务已入队"}


@router.get("/exports/{export_id}/status")
async def get_export_status(
    export_id: int,
    current_user=Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ExportTask).where(ExportTask.id == export_id))
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError("ExportTask", export_id)

    return {
        "id": task.id,
        "task_instance_id": task.task_instance_id,
        "status": task.status,
        "file_path": task.file_path,
        "file_size": task.file_size,
        "error_message": task.error_message,
        "expires_at": task.expires_at.isoformat() if task.expires_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: int,
    current_user=Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ExportTask).where(ExportTask.id == export_id))
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError("ExportTask", export_id)

    if task.status != "completed":
        raise ValidationError("导出尚未完成")
    if not task.file_path or not os.path.isfile(task.file_path):
        raise NotFoundError("Export file", "文件不存在")

    if task.expires_at and timezone.now() > task.expires_at:
        raise ValidationError("下载链接已过期")

    filename = os.path.basename(task.file_path)
    return FileResponse(
        path=task.file_path,
        filename=filename,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
