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

        if not records:
            instance.status = "completed"
            instance.completed_at = timezone.now()
            await db.commit()
            await svc.complete(item_id, '{"status": "completed", "downloaded": 0}')
            return

        output_dir = Path(settings.downloads_dir) / instance_no
        output_dir.mkdir(parents=True, exist_ok=True)

        success = 0
        failed = 0
        skipped = 0

        def _process_sync(rec_list: list, out_dir: Path) -> list[dict]:
            results = []
            for rec in rec_list:
                try:
                    pdf_path = download_pdf(
                        article_title=rec.title,
                        output_dir=out_dir,
                    )
                    if pdf_path:
                        size = Path(pdf_path).stat().st_size
                        results.append({
                            "id": rec.id,
                            "status": "completed",
                            "pdf_path": str(pdf_path),
                            "file_size": size,
                        })
                    else:
                        results.append({
                            "id": rec.id,
                            "status": "skipped",
                            "error": "All 3 sources failed (zhesheke/wanfang/cnki)",
                        })
                except Exception as e:
                    results.append({"id": rec.id, "status": "skipped", "error": str(e)[:200]})
            return results

        loop = asyncio.get_event_loop()
        dl_results = await loop.run_in_executor(
            None, _process_sync, list(records), output_dir,
        )

        for dlr in dl_results:
            dr = DownloadResult(
                task_result_id=dlr["id"],
                task_instance_id=instance_id,
                pdf_path=dlr.get("pdf_path", ""),
                file_size=dlr.get("file_size", 0),
                download_status=dlr["status"],
                error_message=dlr.get("error", ""),
            )
            db.add(dr)
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
            await db.flush()

        instance.status = "completed"
        instance.completed_at = timezone.now()
        await db.commit()

        await svc.complete(item_id, json.dumps({
            "status": "completed",
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "total": len(records),
        }, ensure_ascii=False))

        from app.routers.sse import broadcast_event
        await broadcast_event(instance_id, "download.progress", {
            "success": success, "failed": failed, "skipped": skipped, "total": len(records),
        })
        await broadcast_event(instance_id, "task.completed", {
            "status": "completed", "completed_at": timezone.now().isoformat(),
        })

        from app.services.wecom_notifier import send_notification
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
        })

    except Exception as e:
        logger.error(f"Download failed: {e}", exc_info=True)
        try:
            instance.error_message = str(e)[:500]
            await db.commit()
        except Exception:
            pass
        try:
            from app.services.wecom_notifier import send_notification
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
            })
        except Exception:
            pass
        await svc.fail(item_id, str(e)[:500])
