"""下载进度统计（累计口径，实例视角，跨运行累计）+ 由其派生的实例终态判定。

供多个调用方复用，保证“同口径”：
- GET /task-instances/{id}/download-progress 接口
- download_worker 每批下载完成后的 download.progress 广播
- resolve_review_status：分析/下载阶段结束后实例该处于什么状态

口径说明：
total = 本实例人工审核通过的非重复记录数（已成功的记录也计入 total，
断点续传/重跑场景不漂移）；
success/failed = download_results 表按状态分组统计（含单条重试通道写入的
failed 记录；历史 skipped 已合并进 failed，此处兼容旧数据）。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.download_result import DownloadResult
from app.models.task_result import TaskResult


async def get_download_progress_stats(db: AsyncSession, instance_id: int) -> dict:
    total = (
        await db.execute(
            select(func.count(TaskResult.id)).where(
                TaskResult.task_instance_id == instance_id,
                TaskResult.is_duplicate == False,
                TaskResult.is_passed == True,
            )
        )
    ).scalar() or 0

    success = failed = 0
    for status, cnt in (
        await db.execute(
            select(DownloadResult.download_status, func.count(DownloadResult.id))
            .where(DownloadResult.task_instance_id == instance_id)
            .group_by(DownloadResult.download_status)
        )
    ).all():
        if status == "completed":
            success = cnt
        elif status in ("failed", "skipped"):
            # skipped 已合并进 failed（下载状态精简），保留对旧数据的兼容
            failed += cnt
    return {"success": success, "failed": failed, "total": total}


async def resolve_review_status(
    db: AsyncSession, instance, stats: dict | None = None
) -> str:
    """审核/下载阶段结束后，实例应处的状态（由数据派生，不看操作顺序）。

    - 无有效数据（全部为重复）→ 无事可做：completed
    - 没有「审核通过的非重复记录」→ 仍待人工审核：analyzing_completed
    - 审核通过的全部已下载成功 → 已完成：completed
    - 其余（部分成功/部分失败）→ 待人工处理：analyzing_completed

    调用方**必须**用它代替硬编码状态：实例状态是派生值，而“是否已终态”这条
    规则过去由各 worker 各自实现，于是出现两类异常（见 tasks/lessons.md）：
    1. 「对已完成实例重跑分析」被写成 analyzing_completed，把终态打回审核中；
    2. 同一份数据（部分记录下载失败）在“批量刚跑完”分支被判为 completed，
       在“重跑时无待下载记录”分支却被判为 analyzing_completed——
       状态取决于用户点了几次下载。

    `stats` 可选：调用方已查过时传入，避免重复查询。
    """
    if not (instance.valid_data_count or 0):
        return "completed"
    if stats is None:
        stats = await get_download_progress_stats(db, instance.id)
    if stats["total"] > 0 and stats["success"] >= stats["total"]:
        return "completed"
    return "analyzing_completed"
