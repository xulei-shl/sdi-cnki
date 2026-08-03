"""下载进度统计（累计口径，实例视角，跨运行累计）。

供两个调用方复用，保证“同口径”：
- GET /task-instances/{id}/download-progress 接口
- download_worker 每批下载完成后的 download.progress 广播

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
