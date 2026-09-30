"""任务失败后的业务对象回收。

worker 在真正开始执行业务逻辑之前（如解析 params_json 失败、实例/任务不存在）
抛出的异常，只会被 worker 层把队列行标记为 retrying/failed，而业务对象会停留在
入队时的中间态（search_queued / download_queued / pending export_task），造成
“永久卡死”（导出永远转圈、实例永远排队中）的假象。

本模块由 BaseWorker._process_wrapper 在队列行失败后调用，把业务对象从中间态
回退到可恢复状态，保证任何失败都有明确的终止态与重试路径：

- export   : key = export_{instance_no}_{export_id} -> export_task -> failed
- cnki     : key = {instance_no}                     -> search_queued -> pending
- llm      : key = llm_{instance_no} / llm_retry_*   -> analyzing -> analyzing_completed
- download : key = download_{instance_no}            -> download_queued -> analyzing_completed

定位业务对象时以 `params_json.instance_id` 为准，`task_key` 仅作兜底：开放接口带
`idempotency_key` 时入队的 task_key 是 `api_<key>` 而非 instance_no，只靠 task_key
会让这类作业失败后永久卡在中间态。API 作业（source=api）没有“重新触发”入口，
因此统一回收到终态 failed，而不是像网页那样回退到可重试的中间态。
"""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.export_task import ExportTask
from app.models.task_instance import TaskInstance
from app.models.task_queue import TaskQueueItem
from app.utils import timezone

logger = logging.getLogger("recovery")


def _extract_instance_id(params_json: str | None) -> int | None:
    """从队列行 params_json 取出 instance_id；解析失败返回 None（不抛错）。"""
    try:
        value = json.loads(params_json or "").get("instance_id")
    except (ValueError, AttributeError):
        return None
    return int(value) if value is not None else None


async def reconcile_failed_task(db: AsyncSession, item_id: int, error_message: str) -> None:
    """根据队列行类型回退关联业务对象状态（幂等，仅处理中间态）。"""
    row = (
        await db.execute(select(TaskQueueItem).where(TaskQueueItem.id == item_id))
    ).scalar_one_or_none()
    if not row:
        return
    key = row.task_key or ""
    # task_key 不一定等于 instance_no（见模块 docstring），故优先用 instance_id 定位。
    instance_id = _extract_instance_id(row.params_json)
    try:
        if row.queue_type == "export" and key.startswith("export_"):
            await _reconcile_export(db, key, error_message)
        elif row.queue_type == "download" and key.startswith("download_"):
            await _reconcile_instance(db, key[len("download_"):], ("download_queued",), "analyzing_completed", error_message, "下载", instance_id)
        elif row.queue_type == "llm":
            instance_no = key.removeprefix("llm_retry_").removeprefix("llm_")
            await _reconcile_instance(db, instance_no, ("analyzing", "search_completed"), "analyzing_completed", error_message, "分析", instance_id)
        elif row.queue_type == "cnki":
            await _reconcile_instance(db, key, ("search_queued",), "pending", error_message, "检索", instance_id)
    except Exception as e:
        logger.error(f"Reconcile failed for task item {item_id}: {e}", exc_info=True)


async def _reconcile_instance(
    db: AsyncSession,
    instance_no: str,
    from_statuses: tuple[str, ...],
    to_status: str,
    error_message: str,
    stage: str,
    instance_id: int | None = None,
) -> None:
    inst = None
    if instance_id is not None:
        inst = (
            await db.execute(select(TaskInstance).where(TaskInstance.id == instance_id))
        ).scalar_one_or_none()
    if inst is None and instance_no:
        inst = (
            await db.execute(select(TaskInstance).where(TaskInstance.instance_no == instance_no))
        ).scalar_one_or_none()
    if not inst or inst.status not in from_statuses:
        return
    # API 作业没有“重新触发”入口，调用方只会一直轮询，必须落到终态 failed。
    is_api = (inst.source or "web") == "api"
    if is_api:
        to_status = "failed"
    suffix = "（作业已失败，请重新提交）" if is_api else "（可重新触发）"
    inst.status = to_status
    inst.error_message = f"{stage}任务执行失败：{error_message[:500]}{suffix}"
    await db.commit()
    logger.warning(f"Reconciled instance {inst.instance_no}: {to_status}（{error_message[:200]}）")


async def _reconcile_export(db: AsyncSession, key: str, error_message: str) -> None:
    try:
        export_id = int(key.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        return
    task = (
        await db.execute(select(ExportTask).where(ExportTask.id == export_id))
    ).scalar_one_or_none()
    if not task or task.status not in ("pending", "running"):
        return
    task.status = "failed"
    task.error_message = f"导出任务执行失败：{error_message[:500]}"
    task.completed_at = timezone.now()
    await db.commit()
    from app.routers.sse import broadcast_event
    await broadcast_event(task.task_instance_id, "export.failed", {
        "export_id": export_id,
        "error_message": error_message[:500],
    })
    logger.warning(f"Reconciled export task {export_id} -> failed（{error_message[:200]}）")
