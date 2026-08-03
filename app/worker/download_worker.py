"""PDF download worker - 调度 pdf_downloader 三来源下载。"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.utils import timezone

from sqlalchemy import select, exists
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.task_instance import TaskInstance
from app.models.task_result import TaskResult
from app.models.download_result import DownloadResult
from app.services.pdf_downloader import download_pdf
from app.task_queue.crud import TaskQueueService
from app.utils.logging import get_logger

logger = get_logger("download_worker")
settings = get_settings()

# 每批下载条数：=1 即严格串行（与历史行为一致，外部站点压力最小），
# 同时保持每批落库 + SSE 进度 + 崩溃续传。如需提速可上调（外部站点压力随之增加）。
BATCH_DOWNLOAD_SIZE = 1


async def run_download(db: AsyncSession, item_id: int, params_json: str) -> None:
    svc = TaskQueueService(db)
    params = json.loads(params_json)
    instance_id = params.get("instance_id")
    instance_no = params.get("instance_no")

    stmt = select(TaskInstance).where(TaskInstance.id == instance_id).options(
        selectinload(TaskInstance.meta_task), selectinload(TaskInstance.creator),
    )
    result = await db.execute(stmt)
    instance = result.unique().scalar_one_or_none()
    if not instance:
        await svc.fail(item_id, f"Instance {instance_id} not found")
        return

    instance.status = "downloading"
    instance.download_started_at = timezone.now()
    await db.commit()

    from app.routers.sse import broadcast_event

    try:
        rec_stmt = (
            select(TaskResult)
            .where(
                TaskResult.task_instance_id == instance_id,
                TaskResult.is_duplicate == False,
                TaskResult.is_passed == True,
                ~exists().where(
                    DownloadResult.task_result_id == TaskResult.id,
                    DownloadResult.download_status == 'completed',
                )
            )
        )
        rec_result = await db.execute(rec_stmt)
        records = rec_result.scalars().all()
        total = len(records)

        if not records:
            # 有有效记录但均未人工审核通过时，不能“假完成”：
            # 直接置 completed 会让用户以为下载成功，实际 0 个文件。
            # 停留回 analyzing_completed（审核态），提示用户先在页面标记通过。
            if (instance.valid_data_count or 0) > 0:
                instance.status = "analyzing_completed"
                instance.error_message = "无可下载记录：请先在页面完成人工审核（标记通过）后再触发下载"
            else:
                instance.status = "completed"
                instance.completed_at = timezone.now()
            await db.commit()
            await svc.complete(item_id, '{"status": "completed", "downloaded": 0}')
            await broadcast_event(instance_id, "task.progress", {
                "status": instance.status,
                "downloaded": 0,
                "message": instance.error_message or "",
            })
            return

        output_dir = Path(settings.downloads_dir) / instance_no
        output_dir.mkdir(parents=True, exist_ok=True)

        success = 0
        failed = 0
        skipped = 0

        def _download_one(rec: TaskResult) -> dict:
            """同步下载单条记录（在 to_thread 中执行）。"""
            try:
                pdf_path = download_pdf(
                    article_title=rec.title,
                    output_dir=output_dir,
                )
                if pdf_path:
                    size = Path(pdf_path).stat().st_size
                    return {
                        "id": rec.id,
                        "status": "completed",
                        "pdf_path": str(pdf_path),
                        "file_size": size,
                    }
                return {
                    "id": rec.id,
                    "status": "skipped",
                    "error": "All 3 sources failed (zhesheke/wanfang/cnki)",
                }
            except Exception as e:
                return {"id": rec.id, "status": "skipped", "error": str(e)[:200]}

        # 分批下载：每批下载完成后立即写库并广播进度。
        # 好处：1) “下载中”期间有真实可见的进度；2) 进程崩溃时已下载记录已落库，
        # 重新触发后通过 exists(completed) 自动跳过，实现断点续传。
        for i in range(0, total, BATCH_DOWNLOAD_SIZE):
            batch = list(records[i:i + BATCH_DOWNLOAD_SIZE])
            dl_results = await asyncio.gather(
                *[asyncio.to_thread(_download_one, rec) for rec in batch]
            )

            for dlr in dl_results:
                # 更新或插入：task_result_id 是唯一约束，若该记录此前已有失败记录，
                # 直接 INSERT 会撞唯一键导致整个下载任务异常卡死。
                existing_dr = await db.execute(
                    select(DownloadResult).where(DownloadResult.task_result_id == dlr["id"])
                )
                dr = existing_dr.scalar_one_or_none()
                if dr is None:
                    dr = DownloadResult(
                        task_result_id=dlr["id"],
                        task_instance_id=instance_id,
                        pdf_path=dlr.get("pdf_path", ""),
                        file_size=dlr.get("file_size", 0),
                        download_status=dlr["status"],
                        error_message=dlr.get("error", ""),
                    )
                    db.add(dr)
                else:
                    dr.task_instance_id = instance_id
                    dr.download_status = dlr["status"]
                    dr.pdf_path = dlr.get("pdf_path", "")
                    dr.file_size = dlr.get("file_size", 0)
                    dr.error_message = dlr.get("error", "")
                if dlr["status"] == "completed":
                    success += 1
                    tr = await db.execute(select(TaskResult).where(TaskResult.id == dlr["id"]))
                    tr_row = tr.scalar_one_or_none()
                    if tr_row:
                        tr_row.local_pdf_path = dlr.get("pdf_path", "")
                elif dlr["status"] == "failed":
                    failed += 1
                else:
                    skipped += 1

            await db.commit()  # 每批落库

            await broadcast_event(instance_id, "download.progress", {
                "success": success, "failed": failed, "skipped": skipped, "total": total,
            })
            logger.info(f"Download progress {instance_no}: {success + failed + skipped}/{total}")

        instance.status = "completed"
        instance.completed_at = timezone.now()
        instance.error_message = None  # 清除历史错误/超时回收提示，避免残留展示
        await db.commit()

        await svc.complete(item_id, json.dumps({
            "status": "completed",
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "total": total,
        }, ensure_ascii=False))

        await broadcast_event(instance_id, "download.progress", {
            "success": success, "failed": failed, "skipped": skipped, "total": total,
        })
        await broadcast_event(instance_id, "task.completed", {
            "status": "completed", "completed_at": timezone.now().isoformat(),
        })

        from app.services.notification import send_notification
        await send_notification(db, {
            "user_id": instance.creator.id if instance.creator else None,
            "instance_id": instance_id,
            "stage": "下载",
            "meta_task_name": instance.meta_task.name if instance.meta_task else "",
            "username": instance.creator.username if instance.creator else "",
            "instance_no": instance.instance_no,
            "status": "completed",
            "started_at": instance.started_at.isoformat() if instance.started_at else "",
            "completed_at": timezone.now().isoformat(),
            "stats": {
                "total": instance.search_result_count or 0,
                "valid": instance.valid_data_count or 0,
                "duplicate": instance.duplicate_count or 0,
                "analyzed": 0,
                "downloaded": success,
            },
        }, module_key="下载")

    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        try:
            # 异常可能已破坏当前事务：先回滚，确保后续用全新事务可靠落库
            await db.rollback()
        except Exception:
            pass
        try:
            # 失败/异常时把实例回退到审核态（而不是悬挂在 downloading/download_queued），
            # 用户可重新触发下载；已落库的记录会在重跑时自动跳过（断点续传）。
            if instance.status in ("downloading", "download_queued"):
                instance.status = "analyzing_completed"
            instance.error_message = f"下载失败：{str(e)[:200]}（已下载的记录将自动跳过，可重新触发）"
            await db.commit()
        except Exception:
            pass
        try:
            from app.services.notification import send_notification
            await send_notification(db, {
                "user_id": instance.creator.id if instance.creator else None,
                "stage": "下载",
                "meta_task_name": instance.meta_task.name if instance.meta_task else "",
                "username": instance.creator.username if instance.creator else "",
                "instance_no": instance.instance_no,
                "status": "failed",
                "error_message": str(e)[:500],
                "started_at": instance.started_at.isoformat() if instance.started_at else "",
                "completed_at": timezone.now().isoformat(),
                "stats": {},
            }, module_key="下载")
        except Exception:
            pass
        await svc.fail(item_id, str(e)[:500])
