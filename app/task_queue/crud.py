from __future__ import annotations

from typing import Any

from app.utils import timezone

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_queue import TaskQueueItem


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
    ) -> TaskQueueItem:
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
        stmt = (
            select(TaskQueueItem)
            .where(
                TaskQueueItem.queue_type == queue_type,
                TaskQueueItem.status == "pending",
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
        if item:
            item.status = "completed"
            item.completed_at = timezone.now()
            if result_json:
                item.result_json = result_json
            await self.db.commit()

    async def fail(self, item_id: int, error_message: str) -> None:
        stmt = select(TaskQueueItem).where(TaskQueueItem.id == item_id)
        result = await self.db.execute(stmt)
        item = result.scalar_one_or_none()
        if item:
            item.retry_count += 1
            if item.retry_count >= item.max_retries:
                item.status = "failed"
            else:
                item.status = "retrying"
            item.error_message = error_message
            item.completed_at = timezone.now()
            await self.db.commit()

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
