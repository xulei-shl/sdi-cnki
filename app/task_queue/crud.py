from __future__ import annotations

from datetime import timedelta
from typing import Any

from app.utils import timezone

from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_queue import TaskQueueItem

# retrying 状态被重新拾取前的退避时间：失败后至少等待这么久才重试，
# 避免对外部服务（CNKI/LLM 等）在短时间内连续重试 3 次。
RETRY_DELAY_SECONDS = 30


class TaskQueueService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def enqueue(
        self,
        queue_type: str,
        task_type: str,
        params_json: str,
        task_key: str | None = None,
        priority: int = 0,
        max_retries: int = 3,
        timeout_sec: int = 1800,
        commit: bool = True,
        replace: bool = False,
    ) -> TaskQueueItem:
        """入队。replace=True 时先删除同 task_key 的旧行（任意状态），
        避免唯一约束冲突导致 500 或残留（如下载卡死后重新触发）。"""
        if replace and task_key:
            await self.db.execute(delete(TaskQueueItem).where(TaskQueueItem.task_key == task_key))
        item = TaskQueueItem(
            queue_type=queue_type,
            task_type=task_type,
            task_key=task_key,
            params_json=params_json,
            priority=priority,
            max_retries=max_retries,
            timeout_sec=timeout_sec,
            status="pending",
        )
        self.db.add(item)
        if commit:
            await self.db.commit()
            await self.db.refresh(item)
        return item

    async def dequeue(self, queue_type: str) -> TaskQueueItem | None:
        # pending 与 retrying 都可被拾取：retrying 是失败后待重试的任务，
        # 若只拾取 pending，重试机制将永远失效并造成永久卡死。
        # retrying 需满足退避时间（started_at 为 fail() 记录的失败时间点）。
        cutoff = timezone.now() - timedelta(seconds=RETRY_DELAY_SECONDS)
        stmt = (
            select(TaskQueueItem)
            .where(
                TaskQueueItem.queue_type == queue_type,
                or_(
                    TaskQueueItem.status == "pending",
                    and_(
                        TaskQueueItem.status == "retrying",
                        TaskQueueItem.started_at <= cutoff,
                    ),
                ),
            )
            .order_by(TaskQueueItem.priority.asc(), TaskQueueItem.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await self.db.execute(stmt)
        item = result.scalar_one_or_none()
        if item:
            item.status = "running"
            item.started_at = timezone.now()
            await self.db.commit()
        return item

    async def complete(self, item_id: int, result_json: str | None = None) -> None:
        stmt = select(TaskQueueItem).where(TaskQueueItem.id == item_id)
        result = await self.db.execute(stmt)
        item = result.scalar_one_or_none()
        # 已被删除实例的清理逻辑标记为 cancelled 的行不再复活（删除场景）
        if item and item.status != "cancelled":
            item.status = "completed"
            item.completed_at = timezone.now()
            if result_json:
                item.result_json = result_json
            await self.db.commit()

    async def fail(self, item_id: int, error_message: str) -> None:
        stmt = select(TaskQueueItem).where(TaskQueueItem.id == item_id)
        result = await self.db.execute(stmt)
        item = result.scalar_one_or_none()
        # 已被标记为 cancelled 的行不再改写状态（删除场景）
        if item and item.status != "cancelled":
            item.retry_count += 1
            if item.retry_count >= item.max_retries:
                item.status = "failed"
            else:
                item.status = "retrying"
                # 用 started_at 记录失败时间点，作为重试退避的基准
                item.started_at = timezone.now()
            item.error_message = error_message
            item.completed_at = timezone.now()
            await self.db.commit()

    async def reclaim_stale_running(self, queue_type: str) -> int:
        """兜底回收：将运行超过自身 timeout_sec 仍处于 running 的队列任务标记为 failed。

        进程崩溃 / 重启 / 异常导致 in-flight 任务消失时，队列行会永远停留在 running；
        Worker 只拾取 pending/retrying，这些行若无人回收将永久堵塞。
        此处按任务自身的 timeout_sec 判定“超时即视为死亡”，标记为 failed 后可被重新触发。
        """
        now = timezone.now()
        result = await self.db.execute(
            select(TaskQueueItem).where(
                TaskQueueItem.queue_type == queue_type,
                TaskQueueItem.status == "running",
            )
        )
        reclaimed = 0
        for item in result.scalars().all():
            if not item.started_at:
                continue
            timeout = item.timeout_sec or 1800
            if (now - item.started_at).total_seconds() > timeout:
                item.status = "failed"
                item.error_message = "自动回收：任务运行超过配置时限(timeout_sec)仍处于 running，已标记失败，请重新触发"
                item.completed_at = now
                reclaimed += 1
        if reclaimed:
            await self.db.commit()
        return reclaimed

    async def retry_failed(self, item_id: int) -> None:
        stmt = select(TaskQueueItem).where(TaskQueueItem.id == item_id)
        result = await self.db.execute(stmt)
        item = result.scalar_one_or_none()
        if item:
            item.status = "pending"
            item.error_message = None
            item.retry_count = 0
            item.completed_at = None
            await self.db.commit()

    async def queue_length(self, queue_type: str | None = None) -> dict[str, int]:
        where = [TaskQueueItem.status == "pending"]
        if queue_type:
            where.append(TaskQueueItem.queue_type == queue_type)
        stmt = select(TaskQueueItem.status, func.count()).where(and_(*where)).group_by(TaskQueueItem.status)
        result = await self.db.execute(stmt)
        counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0, "retrying": 0}
        for row in result:
            counts[row[0]] = row[1]
        return counts
