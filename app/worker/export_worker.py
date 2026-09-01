from __future__ import annotations

import json
from datetime import timedelta

from app.utils import timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.export_task import ExportTask
from app.models.task_instance import TaskInstance
from app.services.export_service import create_export_package
from app.routers.sse import broadcast_event
from app.task_queue.crud import TaskQueueService
from app.utils.logging import get_logger

logger = get_logger("export_worker")

settings = get_settings()


async def run_export(db: AsyncSession, task_item_id: int, params_json: str) -> None:
    """执行导出任务：打包 ZIP -> 更新状态 -> SSE 通知。"""
    svc = TaskQueueService(db)
    params = json.loads(params_json)
    export_id = params.get("export_id")
    instance_id = params.get("instance_id")
    include_pdfs = params.get("include_pdfs", True)

    if not export_id or not instance_id:
        raise ValueError("缺少 export_id 或 instance_id 参数")

    result = await db.execute(select(ExportTask).where(ExportTask.id == export_id))
    export_task = result.scalar_one_or_none()
    if not export_task:
        raise ValueError(f"ExportTask {export_id} 不存在")

    export_task.status = "running"
    await db.commit()

    try:
        zip_path = await create_export_package(db, export_task, include_pdfs=include_pdfs)

        file_size = 0
        import os
        if os.path.isfile(zip_path):
            file_size = os.path.getsize(zip_path)

        expiry_hours = int(getattr(settings, "export_link_expiry_hours", 24))
        export_task.status = "completed"
        export_task.file_path = zip_path
        export_task.file_size = file_size
        export_task.expires_at = timezone.now() + timedelta(hours=expiry_hours)
        export_task.completed_at = timezone.now()
        await db.commit()

        # 关键：任务队列行必须显式 complete，否则 task_queue 永远停留在 running
        # （此前导出成功但队列行残留的根因）。失败分支保持 raise，由 Worker 兜底 svc.fail。
        await svc.complete(task_item_id, json.dumps({
            "export_id": export_id,
            "file_path": zip_path,
            "file_size": file_size,
            "status": "completed",
        }, ensure_ascii=False))

        await broadcast_event(
            instance_id,
            "export.completed",
            {
                "export_id": export_id,
                "file_path": zip_path,
                "file_size": file_size,
                "expires_at": export_task.expires_at.isoformat() if export_task.expires_at else None,
            },
        )
        logger.info(f"导出完成 export_id={export_id} 文件大小={file_size}")
    except Exception as e:
        export_task.status = "failed"
        export_task.error_message = str(e)
        export_task.completed_at = timezone.now()
        await db.commit()

        await broadcast_event(
            instance_id, "export.failed", {"export_id": export_id, "error_message": str(e)},
        )
        logger.error(f"导出失败 export_id={export_id}: {e}")
        raise
