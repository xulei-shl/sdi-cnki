from __future__ import annotations

import asyncio
import time
from typing import Callable, Awaitable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.task_queue.crud import TaskQueueService
from app.utils.logging import get_logger

logger = get_logger("worker")


class BaseWorker:
    def __init__(
        self,
        queue_type: str,
        session_factory: async_sessionmaker[AsyncSession],
        concurrency: int = 1,
        poll_interval: float = 5.0,
        reclaim_interval: float = 60.0,
    ):
        self.queue_type = queue_type
        self.session_factory = session_factory
        self.concurrency = concurrency
        self.poll_interval = poll_interval
        self.reclaim_interval = reclaim_interval
        self._running = False
        self._semaphore = asyncio.Semaphore(concurrency)

    async def process(self, db: AsyncSession, item_id: int, params_json: str) -> None:
        raise NotImplementedError

    async def _process_wrapper(self, item_id: int, params_json: str) -> None:
        async with self._semaphore:
            async with self.session_factory() as db:
                try:
                    await self.process(db, item_id, params_json)
                except Exception as e:
                    logger.error(f"Worker error: {e}", exc_info=True)
                    try:
                        # 若 process 内的异常已破坏事务（如 IntegrityError/PendingRollbackError），
                        # 先回滚再标记失败，否则 svc.fail 自身会再次抛错，队列行只能等超时回收。
                        await db.rollback()
                    except Exception:
                        pass
                    svc = TaskQueueService(db)
                    await svc.fail(item_id, str(e))

    async def run(self) -> None:
        self._running = True
        logger.info(f"Worker [{self.queue_type}] started (concurrency={self.concurrency})")
        last_reclaim = 0.0
        while self._running:
            try:
                now = time.monotonic()
                async with self.session_factory() as db:
                    svc = TaskQueueService(db)
                    # 周期性兜底：回收超时仍处于 running 的滞留任务（进程崩溃后无法自动完成的行）
                    if now - last_reclaim >= self.reclaim_interval:
                        try:
                            reclaimed = await svc.reclaim_stale_running(self.queue_type)
                            if reclaimed:
                                logger.info(
                                    f"Worker [{self.queue_type}] reclaimed {reclaimed} stale running task(s)"
                                )
                        except Exception as e:
                            logger.error(f"Worker [{self.queue_type}] reclaim error: {e}", exc_info=True)
                        last_reclaim = now
                    item = await svc.dequeue(self.queue_type)
                if item:
                    logger.info(f"Worker [{self.queue_type}] picked task {item.id}")
                    asyncio.create_task(self._process_wrapper(item.id, item.params_json))
                else:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker [{self.queue_type}] loop error: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)
        logger.info(f"Worker [{self.queue_type}] stopped")

    def stop(self) -> None:
        self._running = False
