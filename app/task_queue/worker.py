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
    ):
        self.queue_type = queue_type
        self.session_factory = session_factory
        self.concurrency = concurrency
        self.poll_interval = poll_interval
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
                    svc = TaskQueueService(db)
                    await svc.fail(item_id, str(e))

    async def run(self) -> None:
        self._running = True
        logger.info(f"Worker [{self.queue_type}] started (concurrency={self.concurrency})")
        while self._running:
            try:
                async with self.session_factory() as db:
                    svc = TaskQueueService(db)
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
