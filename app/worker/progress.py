"""任务进度上报与心跳（跨进程可见，供开放接口轮询）。

抽取自 cnki_worker：JEV 评分 worker 需要完全相同的「阶段可见 + 独立心跳」能力，
两处各写一份必然漂移（心跳间隔、失败容忍度、阶段文案）。

设计要点（沿用原实现，勿轻易改动）：
- 进度写入用**独立会话**，避免与 worker 主事务互相污染；
- 进度上报属于可观测性，写失败只告警不抛出，绝不能影响检索/评分本身；
- 心跳与业务步骤解耦：某一步长时间不推进时心跳仍在走，调用方据此区分
  「这一步耗时长」与「进程卡死」。
"""

from __future__ import annotations

import asyncio

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.task_instance import TaskInstance
from app.utils import timezone
from app.utils.logging import get_logger

logger = get_logger("task_progress")

# 心跳间隔：与浏览器步骤解耦，让调用方能区分“步骤耗时”与“进程卡死”
HEARTBEAT_INTERVAL_SEC = 5

STAGE_MESSAGES: dict[str, str] = {
    "launching": "正在启动浏览器",
    "navigating": "正在打开检索页面",
    "authenticating": "正在校验登录状态",
    "searching": "正在填写检索条件",
    "submitting": "正在提交检索",
    "waiting_results": "已提交检索，正在等待结果页返回",
    "collecting": "正在读取检索结果数量",
    "exporting": "正在分批导出元数据",
    "merging": "正在合并导出批次",
    "parsing": "正在解析元数据并入库",
    "scoring": "正在进行相关性评分",
    "done": "检索完成",
}


async def save_progress(instance_id: int, stage: str, extra: dict | None = None) -> None:
    """把阶段写入任务实例，供开放接口轮询（跨进程可见）。"""
    extra = extra or {}
    try:
        async with async_session_factory() as db:
            await db.execute(
                update(TaskInstance)
                .where(TaskInstance.id == instance_id)
                .values(
                    progress_stage=stage,
                    progress_message=STAGE_MESSAGES.get(stage, stage),
                    progress_current=extra.get("current"),
                    progress_total=extra.get("total"),
                    heartbeat_at=timezone.now(),
                )
            )
            await db.commit()
    except Exception as e:
        # 进度上报属于可观测性，失败不能影响业务本身
        logger.warning(f"progress update failed (instance={instance_id}, stage={stage}): {e}")


async def touch_heartbeat(instance_id: int) -> None:
    try:
        async with async_session_factory() as db:
            await db.execute(
                update(TaskInstance)
                .where(TaskInstance.id == instance_id)
                .values(heartbeat_at=timezone.now())
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"heartbeat update failed (instance={instance_id}): {e}")


async def heartbeat_loop(instance_id: int, stop: asyncio.Event) -> None:
    """独立心跳：即使某个步骤长时间不推进，心跳也在走。"""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_INTERVAL_SEC)
        except asyncio.TimeoutError:
            await touch_heartbeat(instance_id)


async def with_heartbeat(instance_id: int, coro):
    """在心跳守护下 await 一个协程/awaitable，结束后确保心跳任务被取消。

    供 worker 复用，避免每个 worker 各写一遍 try/finally + cancel/gather。
    """
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    task = asyncio.create_task(heartbeat_loop(instance_id, stop))
    try:
        return await coro
    finally:
        stop.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)