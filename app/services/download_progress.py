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
from app.utils import timezone


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


async def sync_review_status(db: AsyncSession, instance) -> str:
    """人工审核/行级下载后重算实例状态（只前进，不回退、不覆盖其他状态）。

    `batch-update` / 单条通过/拒绝只改 task_results，行级重试下载只改
    download_results，实例状态却是派生值；不在此重算，用户「先逐条下载完再
    批量拒绝剩余」或「审核完只逐条下载」后实例会永远停在审核中。

    只在审核阶段（analyzing_completed）生效：分析/下载在途时状态由各自 worker 收尾，
    完成态也不允许被审核动作改写。

    额外要求「无待审核记录」：审核动作是逐条进行的，若只因已通过记录均已下载完
    就置为 completed，会把仍在逐条审核的入口锁掉。批量下载那条路径已经用
    resolve_review_status 表达“用户确认只下载已通过的”这一个显式选择，此处不重复。
    """
    if instance.status != "analyzing_completed":
        return instance.status

    unreviewed = (
        await db.execute(
            select(func.count(TaskResult.id)).where(
                TaskResult.task_instance_id == instance.id,
                TaskResult.is_duplicate == False,
                TaskResult.is_passed == None,
            )
        )
    ).scalar() or 0
    if unreviewed:
        return instance.status

    status = await resolve_review_status(db, instance)
    if status != "completed":
        return instance.status

    instance.status = "completed"
    if not instance.completed_at:
        instance.completed_at = timezone.now()
    instance.error_message = None
    await db.commit()

    from app.routers.sse import broadcast_event
    await broadcast_event(instance.id, "task.completed", {
        "status": "completed",
        "completed_at": instance.completed_at.isoformat(),
    })
    return instance.status
