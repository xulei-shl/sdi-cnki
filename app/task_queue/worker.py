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
        self._consumers: list[asyncio.Task] = []

    async def process(self, db: AsyncSession, item_id: int, params_json: str) -> None:
        raise NotImplementedError

    async def _process_wrapper(self, item_id: int, params_json: str) -> None:
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

    async def _consumer(self) -> None:
        """单个消费者：dequeue 拿到任务后立即执行。

        与旧的“主循环 dequeue + 信号量排队执行”不同，这里每个消费者在拿到任务时
        就是真正开始执行 —— dequeue 原子写入 running 即代表正在执行，
        不再出现“队列行 running 但实际在等并发信号量”的假象（如下载排队中卡死）。
        """
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
                if item is not None:
                    logger.info(f"Worker [{self.queue_type}] picked task {item.id}")
                    await self._process_wrapper(item.id, item.params_json)
                else:
                    await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker [{self.queue_type}] consumer error: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)

    async def run(self) -> None:
        self._running = True
        logger.info(f"Worker [{self.queue_type}] started (concurrency={self.concurrency})")
        self._consumers = [
            asyncio.create_task(self._consumer(), name=f"worker-{self.queue_type}-{i}")
            for i in range(self.concurrency)
        ]
        try:
            await asyncio.gather(*self._consumers)
        except asyncio.CancelledError:
            for t in self._consumers:
                t.cancel()
            await asyncio.gather(*self._consumers, return_exceptions=True)
            raise
        logger.info(f"Worker [{self.queue_type}] stopped")

    def stop(self) -> None:
        self._running = False
