from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.utils import timezone
from app.config import get_settings

settings = get_settings()

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, func, desc, or_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import asyncio

from app.database import get_db
from app.models.download_result import DownloadResult
from app.models.meta_task import MetaTask
from app.models.task_instance import TaskInstance
from app.models.task_queue import TaskQueueItem
from app.models.task_result import TaskResult
from app.utils.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.utils.logging import get_logger as _get_logger
from app.utils.oplog import log_operation
from app.routers import get_current_user_from_header
from app.services.excel_parser import parse_excel_to_records
from app.services.dedup_service import batch_check_and_mark

router = APIRouter()

# 实例级下载串行锁，同一实例内的单条重试下载逐条执行
_instance_dl_locks: dict[int, asyncio.Lock] = {}


async def _create_instance(db: AsyncSession, task: MetaTask, user, auto_run: bool = True) -> TaskInstance:
    today = timezone.now().strftime("%Y%m%d")
    last = await db.execute(
        select(func.max(TaskInstance.instance_no))
        .where(TaskInstance.instance_no.like(f"T{today}%"))
    )
    last_no = last.scalar()
    seq = 1
    if last_no:
        seq = int(last_no[-3:]) + 1
    instance_no = f"T{today}{seq:03d}"
    execution_params = {
        "search_params": json.loads(task.search_params) if isinstance(task.search_params, str) else task.search_params,
        "prompt_template_id": task.prompt_template_id,
        "llm_config_ids": [],
    }
    from app.models.meta_task_llm_config import MetaTaskLlmConfig
    links = await db.execute(
        select(MetaTaskLlmConfig).where(MetaTaskLlmConfig.meta_task_id == task.id).order_by(MetaTaskLlmConfig.priority)
    )
    execution_params["llm_config_ids"] = [link.llm_config_id for link in links.scalars().all()]
    instance = TaskInstance(
        meta_task_id=task.id,
        creator_id=user.id,
        instance_no=instance_no,
        status="pending",
        auto_run=auto_run,
        execution_params=json.dumps(execution_params, ensure_ascii=False),
    )
    db.add(instance)
    await db.flush()
    task.execution_count = (task.execution_count or 0) + 1
    task.last_executed_at = timezone.now()
    await db.commit()
    await db.refresh(instance)
    return instance


@router.get("")
async def list_task_instances(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    template_name: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if current_user.role != "admin":
        where.append(TaskInstance.creator_id == current_user.id)
    if status_filter:
        where.append(TaskInstance.status == status_filter)
    if keyword:
        where.append(TaskInstance.instance_no.ilike(f"%{keyword}%"))
    if template_name:
        mt_ids = await db.execute(
            select(MetaTask.id).where(MetaTask.name.ilike(f"%{template_name}%"))
        )
        mt_ids_list = [r[0] for r in mt_ids.all()]
        if mt_ids_list:
            where.append(TaskInstance.meta_task_id.in_(mt_ids_list))
        else:
            where.append(TaskInstance.meta_task_id == -1)
    stmt = (
        select(TaskInstance)
        .where(*where)
        .options(selectinload(TaskInstance.meta_task), selectinload(TaskInstance.creator))
        .order_by(desc(TaskInstance.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    instances = result.unique().scalars().all()
    total = await db.execute(select(func.count(TaskInstance.id)).where(*where))
    items = []
    for inst in instances:
        items.append({
            "id": inst.id,
            "instance_no": inst.instance_no,
            "meta_task_id": inst.meta_task_id,
            "meta_task_name": inst.meta_task.name if inst.meta_task else "",
            "status": inst.status,
            "creator_id": inst.creator_id,
            "creator_name": inst.creator.username if inst.creator else "",
            "search_result_count": inst.search_result_count,
            "valid_data_count": inst.valid_data_count,
            "duplicate_count": inst.duplicate_count,
            "auto_run": inst.auto_run,
            "created_at": inst.created_at.isoformat() if inst.created_at else "",
            "started_at": inst.started_at.isoformat() if inst.started_at else None,
            "completed_at": inst.completed_at.isoformat() if inst.completed_at else None,
        })
    return {"items": items, "total": total.scalar(), "page": page, "page_size": page_size}


@router.patch("/{instance_id}/params")
async def update_task_instance_params(
    instance_id: int,
    data: dict,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TaskInstance).where(TaskInstance.id == instance_id)
    result = await db.execute(stmt)
    inst = result.scalar_one_or_none()
    if not inst:
        raise NotFoundError("TaskInstance", instance_id)
    if current_user.role != "admin" and inst.creator_id != current_user.id:
        raise PermissionDeniedError()
    if inst.status != "pending":
        raise ValidationError("Only pending instances can be modified")

    search_params = data.get("search_params")
    if not search_params:
        raise ValidationError("search_params is required")

    execution_params = json.loads(inst.execution_params) if isinstance(inst.execution_params, str) else inst.execution_params
    execution_params["search_params"] = search_params
    inst.execution_params = json.dumps(execution_params, ensure_ascii=False)
    await db.commit()
    await db.refresh(inst)
    return {
        "id": inst.id,
        "execution_params": json.loads(inst.execution_params) if inst.execution_params else {},
    }


@router.get("/{instance_id}")
async def get_task_instance(
    instance_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(TaskInstance)
        .where(TaskInstance.id == instance_id)
        .options(selectinload(TaskInstance.meta_task), selectinload(TaskInstance.creator))
    )
    result = await db.execute(stmt)
    inst = result.unique().scalar_one_or_none()
    if not inst:
        raise NotFoundError("TaskInstance", instance_id)
    if current_user.role != "admin" and inst.creator_id != current_user.id:
        raise PermissionDeniedError()
    from app.models.llm_analysis_result import LlmAnalysisResult
    from app.models.download_result import DownloadResult

    llm_completed = 0
    llm_passed = 0
    llm_rejected = 0
    llm_failed = 0
    analysis_stmt = select(
        LlmAnalysisResult.status,
        LlmAnalysisResult.parsed_result,
    ).where(LlmAnalysisResult.task_instance_id == instance_id)
    for row in (await db.execute(analysis_stmt)).all():
        if row.status == "completed":
            llm_completed += 1
            if row.parsed_result:
                try:
                    p = json.loads(row.parsed_result)
                    is_rel = p.get("is_relevant")
                    if is_rel is None:
                        is_rel = p.get("is_target_topic")
                    if is_rel is True:
                        llm_passed += 1
                    elif is_rel is False:
                        llm_rejected += 1
                except (json.JSONDecodeError, TypeError):
                    pass
        elif row.status == "failed":
            llm_failed += 1

    manual_passed = (
        await db.execute(
            select(func.count(TaskResult.id)).where(
                TaskResult.task_instance_id == instance_id,
                TaskResult.is_duplicate == False,
                TaskResult.is_passed == True,
            )
        )
    ).scalar() or 0
    manual_rejected = (
        await db.execute(
            select(func.count(TaskResult.id)).where(
                TaskResult.task_instance_id == instance_id,
                TaskResult.is_duplicate == False,
                TaskResult.is_passed == False,
            )
        )
    ).scalar() or 0

    download_success = 0
    download_failed = 0
    download_skipped = 0
    download_pending = 0
    for row in (
        await db.execute(
            select(
                DownloadResult.download_status,
                func.count(DownloadResult.id),
            ).where(
                DownloadResult.task_instance_id == instance_id
            ).group_by(DownloadResult.download_status)
        )
    ).all():
        if row[0] == "completed":
            download_success = row[1]
        elif row[0] == "failed":
            download_failed = row[1]
        elif row[0] == "skipped":
            download_skipped = row[1]
        elif row[0] == "pending":
            download_pending = row[1]

    return {
        "id": inst.id,
        "meta_task_id": inst.meta_task_id,
        "meta_task_name": inst.meta_task.name if inst.meta_task else "",
        "instance_no": inst.instance_no,
        "status": inst.status,
        "auto_run": inst.auto_run,
        "creator_id": inst.creator_id,
        "creator_name": inst.creator.username if inst.creator else "",
        "execution_params": json.loads(inst.execution_params) if inst.execution_params else {},
        "search_result_file_path": inst.search_result_file_path,
        "search_result_count": inst.search_result_count,
        "valid_data_count": inst.valid_data_count,
        "duplicate_count": inst.duplicate_count,
        "error_message": inst.error_message,
        "started_at": inst.started_at.isoformat() if inst.started_at else None,
        "search_completed_at": inst.search_completed_at.isoformat() if inst.search_completed_at else None,
        "analysis_completed_at": inst.analysis_completed_at.isoformat() if inst.analysis_completed_at else None,
        "download_started_at": inst.download_started_at.isoformat() if inst.download_started_at else None,
        "completed_at": inst.completed_at.isoformat() if inst.completed_at else None,
        "created_at": inst.created_at.isoformat() if inst.created_at else "",
        "llm_analysis_completed_count": llm_completed,
        "llm_analysis_passed_count": llm_passed,
        "llm_analysis_rejected_count": llm_rejected,
        "llm_analysis_failed_count": llm_failed,
        "manual_review_passed_count": manual_passed,
        "manual_review_rejected_count": manual_rejected,
        "download_success_count": download_success,
        "download_failed_count": download_failed,
        "download_skipped_count": download_skipped,
        "download_pending_count": download_pending,
    }


@router.delete("/{instance_id}")
async def _cleanup_instance_side_effects(db: AsyncSession, inst: TaskInstance) -> None:
    """清理实例的关联副作用：悬挂指针、PDF引用、队列任务。

    不提交、不删除实例本身，供删除实例和删除模板时复用。
    """
    # 清理 duplicate_ref_id 悬挂指针
    deleted_result_ids = select(TaskResult.id).where(
        TaskResult.task_instance_id == inst.id
    )
    await db.execute(
        update(TaskResult)
        .where(TaskResult.duplicate_ref_id.in_(deleted_result_ids))
        .values(duplicate_ref_id=None, is_duplicate=False)
    )

    # PdfFile 引用计数递减 + 物理文件清理
    from app.services.pdf_cleanup import decrement_pdf_refs_for_instance
    await decrement_pdf_refs_for_instance(db, inst.id)

    # 取消队列中关联的待处理/运行中任务
    keys = [inst.instance_no, f"llm_{inst.instance_no}", f"download_{inst.instance_no}", f"llm_retry_{inst.instance_no}"]
    await db.execute(
        update(TaskQueueItem)
        .where(TaskQueueItem.task_key.in_(keys))
        .where(TaskQueueItem.status.in_(["pending", "running", "retrying"]))
        .values(status="cancelled")
    )


async def delete_instance(
    instance_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(TaskInstance)
        .where(TaskInstance.id == instance_id)
        .options(
            selectinload(TaskInstance.task_results)
                .selectinload(TaskResult.llm_analysis),
            selectinload(TaskInstance.task_results)
                .selectinload(TaskResult.download_result),
        )
    )
    result = await db.execute(stmt)
    inst = result.unique().scalar_one_or_none()
    if not inst:
        raise NotFoundError("TaskInstance", instance_id)
    if current_user.role != "admin" and inst.creator_id != current_user.id:
        raise PermissionDeniedError()

    await _cleanup_instance_side_effects(db, inst)

    # 递减父模板执行计数
    task_stmt = select(MetaTask).where(MetaTask.id == inst.meta_task_id)
    task_result = await db.execute(task_stmt)
    task = task_result.scalar_one_or_none()
    if task:
        task.execution_count = max(0, (task.execution_count or 0) - 1)

    # 删除实例（ORM 级联 task_results → llm_analysis_results, download_results）
    await db.delete(inst)
    await db.commit()
    await log_operation(db, current_user.id, "delete", "task_instance", instance_id, f"Deleted instance {inst.instance_no}")
    return {"message": "Instance deleted"}


@router.delete("/{instance_id}/clean")
async def delete_instance_with_pdfs(
    instance_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    """向前兼容：完全删除实例，级联清理 PDF 引用和队列任务。"""
    return await delete_instance(instance_id, current_user, db)


@router.get("/{instance_id}/results")
async def list_instance_results(
    instance_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    include_duplicate: bool = Query(False),
    review_status: Optional[str] = Query(None),
    analysis_status: Optional[str] = Query(None),
    analysis_result: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    publish_year: Optional[int] = Query(None),
    min_score: Optional[int] = Query(None, ge=0, le=10),
    download_status: Optional[str] = Query(None),
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TaskInstance).where(TaskInstance.id == instance_id)
    result = await db.execute(stmt)
    inst = result.scalar_one_or_none()
    if not inst:
        raise NotFoundError("TaskInstance", instance_id)
    if current_user.role != "admin" and inst.creator_id != current_user.id:
        raise PermissionDeniedError()
    where = [TaskResult.task_instance_id == instance_id]
    if not include_duplicate:
        where.append(TaskResult.is_duplicate == False)
    if review_status == "passed":
        where.append(TaskResult.is_passed == True)
    elif review_status == "rejected":
        where.append(TaskResult.is_passed == False)
    elif review_status == "pending":
        where.append(TaskResult.is_passed == None)
    if analysis_status:
        from app.models.llm_analysis_result import LlmAnalysisResult
        subq = select(LlmAnalysisResult.task_result_id).where(
            LlmAnalysisResult.status == analysis_status,
            LlmAnalysisResult.task_instance_id == instance_id,
        ).subquery()
        where.append(TaskResult.id.in_(select(subq.c)))
    if keyword:
        where.append(TaskResult.title.ilike(f"%{keyword}%"))
    if publish_year:
        where.append(TaskResult.publish_year == publish_year)
    if download_status:
        from app.models.download_result import DownloadResult
        if download_status == "pending":
            has_dr = select(DownloadResult.task_result_id).where(
                DownloadResult.task_instance_id == instance_id,
            ).subquery()
            dr_pending = select(DownloadResult.task_result_id).where(
                DownloadResult.download_status == "pending",
                DownloadResult.task_instance_id == instance_id,
            ).subquery()
            where.append(or_(
                ~TaskResult.id.in_(select(has_dr.c)),
                TaskResult.id.in_(select(dr_pending.c)),
            ))
        else:
            dr_subq = select(DownloadResult.task_result_id).where(
                DownloadResult.download_status == download_status,
                DownloadResult.task_instance_id == instance_id,
            ).subquery()
            where.append(TaskResult.id.in_(select(dr_subq.c)))
    if min_score is not None:
        from app.models.llm_analysis_result import LlmAnalysisResult
        score_subq = (
            select(LlmAnalysisResult.task_result_id)
            .where(
                LlmAnalysisResult.task_instance_id == instance_id,
                LlmAnalysisResult.parsed_result.isnot(None),
                func.json_extract(LlmAnalysisResult.parsed_result, '$.relevance_score') >= min_score,
            )
            .subquery()
        )
        where.append(TaskResult.id.in_(select(score_subq.c)))
    if analysis_result == "passed":
        from app.models.llm_analysis_result import LlmAnalysisResult
        passed_subq = (
            select(LlmAnalysisResult.task_result_id)
            .where(
                LlmAnalysisResult.task_instance_id == instance_id,
                LlmAnalysisResult.parsed_result.isnot(None),
                func.json_extract(LlmAnalysisResult.parsed_result, '$.is_target_topic') == 1,
            )
            .subquery()
        )
        where.append(TaskResult.id.in_(select(passed_subq.c)))
    elif analysis_result == "rejected":
        from app.models.llm_analysis_result import LlmAnalysisResult
        rejected_subq = (
            select(LlmAnalysisResult.task_result_id)
            .where(
                LlmAnalysisResult.task_instance_id == instance_id,
                LlmAnalysisResult.parsed_result.isnot(None),
                func.json_extract(LlmAnalysisResult.parsed_result, '$.is_target_topic') == 0,
            )
            .subquery()
        )
        where.append(TaskResult.id.in_(select(rejected_subq.c)))
    stmt = (
        select(TaskResult)
        .where(*where)
        .options(
            selectinload(TaskResult.llm_analysis),
            selectinload(TaskResult.download_result),
        )
        .order_by(TaskResult.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    rows = result.unique().scalars().all()
    count = await db.execute(select(func.count(TaskResult.id)).where(*where))
    items = []
    for row in rows:
        parsed = json.loads(row.llm_analysis.parsed_result) if row.llm_analysis and row.llm_analysis.parsed_result else None
        items.append({
            "id": row.id,
            "title": row.title,
            "authors": row.authors,
            "source_journal": row.source_journal,
            "publish_year": row.publish_year,
            "is_duplicate": row.is_duplicate,
            "duplicate_ref_id": row.duplicate_ref_id,
            "is_passed": row.is_passed,
            "local_pdf_path": row.local_pdf_path,
            "keywords": row.keywords,
            "abstract": row.abstract,
            "fund": row.fund,
            "organ": row.organ,
            "original_url": row.original_url,
            "doi": row.doi,
            "llm_analysis": {
                "status": row.llm_analysis.status if row.llm_analysis else None,
                "parsed_result": parsed,
                "error_message": row.llm_analysis.error_message if row.llm_analysis else None,
            } if row.llm_analysis else None,
            "download": {
                "download_status": row.download_result.download_status if row.download_result else "pending",
                "pdf_path": row.download_result.pdf_path if row.download_result else None,
                "file_size": row.download_result.file_size if row.download_result else None,
                "error_message": row.download_result.error_message if row.download_result else None,
            } if row.download_result else None,
        })
    return {"items": items, "total": count.scalar(), "page": page, "page_size": page_size}


@router.post("/{instance_id}/results/batch-update")
async def batch_update_results(
    instance_id: int,
    data: dict,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    action = data.get("action")
    result_ids = data.get("result_ids")
    if action not in ("pass", "reject"):
        raise ValidationError("Invalid action")
    if not result_ids:
        raise ValidationError("result_ids is required")
    value = True if action == "pass" else False
    for rid in result_ids:
        r = await db.execute(select(TaskResult).where(TaskResult.id == rid, TaskResult.task_instance_id == instance_id))
        row = r.scalar_one_or_none()
        if row:
            row.is_passed = value
    await db.commit()
    return {"message": f"{len(result_ids)} results updated"}


@router.post("/{instance_id}/download")
async def start_download(
    instance_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    import json
    stmt = select(TaskInstance).where(TaskInstance.id == instance_id)
    result = await db.execute(stmt)
    inst = result.scalar_one_or_none()
    if not inst:
        raise NotFoundError("TaskInstance", instance_id)
    if inst.status not in ("analyzing_completed", "downloading", "download_queued"):
        raise ValidationError(f"Cannot download in status: {inst.status}")
    inst.status = "download_queued"
    from app.task_queue.crud import TaskQueueService
    svc = TaskQueueService(db)
    await svc.enqueue(
        queue_type="download",
        task_type="pdf_download",
        params_json=json.dumps({"instance_id": instance_id, "instance_no": inst.instance_no}),
        task_key=f"download_{inst.instance_no}",
    )
    await db.commit()
    from app.routers.sse import broadcast_event
    await broadcast_event(instance_id, "task.progress", {"status": "download_queued"})
    return {"message": "Download queued"}


@router.post("/{instance_id}/results/{result_id}/retry-download")
async def retry_single_download(
    instance_id: int,
    result_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TaskInstance).where(TaskInstance.id == instance_id)
    result = await db.execute(stmt)
    inst = result.scalar_one_or_none()
    if not inst:
        raise NotFoundError("TaskInstance", instance_id)
    if current_user.role != "admin" and inst.creator_id != current_user.id:
        raise PermissionDeniedError()

    tr = await db.execute(
        select(TaskResult).where(TaskResult.id == result_id, TaskResult.task_instance_id == instance_id)
    )
    task_result = tr.scalar_one_or_none()
    if not task_result:
        raise NotFoundError("TaskResult", result_id)
    if task_result.is_passed != True:
        raise ValidationError("只能对已通过人工审核的记录重试下载")
    if task_result.is_duplicate:
        raise ValidationError("重复记录无法下载")

    existing = await db.execute(
        select(DownloadResult).where(DownloadResult.task_result_id == result_id)
    )
    download_result = existing.scalar_one_or_none()

    output_dir = Path(settings.downloads_dir) / inst.instance_no
    output_dir.mkdir(parents=True, exist_ok=True)

    from app.services.pdf_downloader import download_pdf

    _log = _get_logger("retry_download")

    # 同一实例内的单条下载串行执行，避免多个浏览器同时跑
    if instance_id not in _instance_dl_locks:
        _instance_dl_locks[instance_id] = asyncio.Lock()

    async with _instance_dl_locks[instance_id]:
        try:
            pdf_path = await asyncio.to_thread(
                download_pdf,
                article_title=task_result.title,
                output_dir=output_dir,
            )

            if download_result:
                download_result.download_status = "completed" if pdf_path else "failed"
                download_result.pdf_path = str(pdf_path) if pdf_path else ""
                download_result.file_size = Path(pdf_path).stat().st_size if pdf_path else 0
                download_result.error_message = "" if pdf_path else "单条重试下载失败"
                download_result.retry_count = (download_result.retry_count or 0) + 1
            else:
                download_result = DownloadResult(
                    task_result_id=result_id,
                    task_instance_id=instance_id,
                    download_status="completed" if pdf_path else "failed",
                    pdf_path=str(pdf_path) if pdf_path else "",
                    file_size=Path(pdf_path).stat().st_size if pdf_path else 0,
                    error_message="" if pdf_path else "单条重试下载失败",
                    retry_count=1,
                )
                db.add(download_result)

            if pdf_path:
                task_result.local_pdf_path = str(pdf_path)

            await db.commit()
            return {
                "id": download_result.id,
                "download_status": download_result.download_status,
                "pdf_path": download_result.pdf_path or None,
                "file_size": download_result.file_size or None,
            }

        except Exception as e:
            _log.error(f"单条重试下载失败 [result_id={result_id}]: {e}", exc_info=True)
            if download_result:
                download_result.download_status = "failed"
                download_result.error_message = str(e)[:500]
                download_result.retry_count = (download_result.retry_count or 0) + 1
            else:
                download_result = DownloadResult(
                    task_result_id=result_id,
                    task_instance_id=instance_id,
                    download_status="failed",
                    error_message=str(e)[:500],
                    retry_count=1,
                )
                db.add(download_result)
            await db.commit()
            return {
                "id": download_result.id,
                "download_status": "failed",
                "pdf_path": None,
                "file_size": None,
            }


@router.post("/{instance_id}/retry-analysis")
async def retry_llm_analysis(
    instance_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TaskInstance).where(TaskInstance.id == instance_id)
    result = await db.execute(stmt)
    inst = result.scalar_one_or_none()
    if not inst:
        raise NotFoundError("TaskInstance", instance_id)
    if current_user.role != "admin" and inst.creator_id != current_user.id:
        raise PermissionDeniedError()
    if inst.status in ("pending", "search_queued", "running", "search_completed", "analyzing"):
        raise ValidationError(f"Cannot retry analysis in status: {inst.status}")

    from app.task_queue.crud import TaskQueueService
    svc = TaskQueueService(db)
    await svc.enqueue(
        queue_type="llm",
        task_type="llm_analysis",
        params_json=json.dumps({"instance_id": instance_id, "instance_no": inst.instance_no, "retry_failed_only": True}),
        task_key=f"llm_retry_{inst.instance_no}",
    )
    inst.status = "analyzing"
    await db.commit()
    from app.routers.sse import broadcast_event
    await broadcast_event(instance_id, "task.progress", {"status": "analyzing", "analyzed": 0, "total": 0})
    return {"message": "LLM retry analysis queued"}


@router.post("/{instance_id}/run")
async def run_task_instance(
    instance_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TaskInstance).where(TaskInstance.id == instance_id)
    result = await db.execute(stmt)
    inst = result.scalar_one_or_none()
    if not inst:
        raise NotFoundError("TaskInstance", instance_id)
    if current_user.role != "admin" and inst.creator_id != current_user.id:
        raise PermissionDeniedError()
    if inst.status != "pending":
        raise ValidationError(f"Cannot run instance with status: {inst.status}")
    from app.task_queue.crud import TaskQueueService
    svc = TaskQueueService(db)
    await svc.enqueue(
        queue_type="cnki",
        task_type="cnki_search",
        params_json=json.dumps({"instance_id": instance_id, "instance_no": inst.instance_no}),
        task_key=inst.instance_no,
    )
    inst.status = "search_queued"
    await db.commit()
    from app.routers.sse import broadcast_event
    await broadcast_event(instance_id, "task.progress", {"status": "search_queued"})
    await log_operation(db, current_user.id, "run", "task_instance", instance_id, f"Run instance {inst.instance_no}")
    return {"message": "Instance queued for execution"}


@router.post("/{instance_id}/complete")
async def complete_task_instance(
    instance_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TaskInstance).where(TaskInstance.id == instance_id)
    result = await db.execute(stmt)
    inst = result.scalar_one_or_none()
    if not inst:
        raise NotFoundError("TaskInstance", instance_id)
    if current_user.role != "admin" and inst.creator_id != current_user.id:
        raise PermissionDeniedError()
    if inst.status != "search_completed":
        raise ValidationError(f"Cannot complete instance with status: {inst.status}")
    inst.status = "completed"
    inst.completed_at = timezone.now()
    await db.commit()
    from app.routers.sse import broadcast_event
    await broadcast_event(instance_id, "task.completed", {
        "status": "completed",
        "completed_at": timezone.now().isoformat(),
    })
    await log_operation(db, current_user.id, "complete", "task_instance", instance_id, f"Complete instance {inst.instance_no}")
    return {"message": "Instance completed"}


@router.post("/{instance_id}/import-excel")
async def import_excel_results(
    instance_id: int,
    file: UploadFile = File(...),
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TaskInstance).where(TaskInstance.id == instance_id)
    result = await db.execute(stmt)
    inst = result.scalar_one_or_none()
    if not inst:
        raise NotFoundError("TaskInstance", instance_id)
    if current_user.role != "admin" and inst.creator_id != current_user.id:
        raise PermissionDeniedError()
    if inst.status != "pending":
        raise ValidationError(f"任务实例状态不允许导入，当前状态：{inst.status}")
    if inst.auto_run:
        raise ValidationError("仅「确认后运行」创建的实例支持 Excel 导入")
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls", ".csv")):
        raise ValidationError("仅支持 .xlsx、.xls、.csv 格式的文件")

    settings = get_settings()
    instance_no = inst.instance_no
    upload_dir = Path(settings.uploads_dir) / instance_no
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name
    dest = upload_dir / f"imported_{safe_name}"

    try:
        content = await file.read()
        dest.write_bytes(content)
    except Exception as e:
        raise ValidationError(f"文件保存失败：{str(e)}")

    try:
        records = parse_excel_to_records(str(dest))
    except Exception as e:
        if dest.exists():
            dest.unlink()
        raise ValidationError(f"文件无法读取，请确认是有效的 Excel 文件：{str(e)}")

    if not records:
        if dest.exists():
            dest.unlink()
        raise ValidationError("未解析到有效数据，请确认上传的是 CNKI 导出的 Excel 文件")

    if len(records) > 500:
        if dest.exists():
            dest.unlink()
        raise ValidationError(f"数据行数超过上限（最多 500 条），当前 {len(records)} 条")

    meta_task_id = inst.meta_task_id
    dedup_scope_ids: list[int] = []
    if inst.meta_task_id:
        mt = await db.execute(
            select(MetaTask).where(MetaTask.id == inst.meta_task_id).options(selectinload(MetaTask.dedup_scope_links))
        )
        meta_task_obj = mt.scalar_one_or_none()
        if meta_task_obj:
            dedup_scope_ids = [link.dedup_meta_task_id for link in meta_task_obj.dedup_scope_links]
    marked_records, duplicate_count = await batch_check_and_mark(
        db, records, meta_task_id, instance_id,
        dedup_scope_meta_task_ids=dedup_scope_ids or None,
    )

    for rec in marked_records:
        task_result = TaskResult(
            task_instance_id=instance_id,
            duplicate_ref_id=rec.get("duplicate_ref_id"),
            title=rec.get("title", ""),
            authors=rec.get("authors", ""),
            organ=rec.get("organ", ""),
            source_journal=rec.get("source_journal", ""),
            first_duty=rec.get("first_duty", ""),
            keywords=rec.get("keywords", ""),
            abstract=rec.get("abstract", ""),
            publish_time=rec.get("publish_time", ""),
            fund=rec.get("fund", ""),
            publish_year=rec.get("publish_year"),
            volume=rec.get("volume", ""),
            issue=rec.get("issue", ""),
            pages=rec.get("pages", ""),
            clc=rec.get("clc", ""),
            issn=rec.get("issn", ""),
            original_url=rec.get("original_url", ""),
            doi=rec.get("doi", ""),
            reference_format=rec.get("reference_format", ""),
            title_normalized=rec.get("title_normalized", ""),
            source_journal_normalized=rec.get("source_journal_normalized", ""),
            is_duplicate=rec.get("is_duplicate", False),
            is_passed=rec.get("is_passed"),
        )
        db.add(task_result)

    total = len(records)
    valid = total - duplicate_count
    inst.status = "search_completed"
    inst.search_result_file_path = str(dest)
    inst.search_result_count = total
    inst.valid_data_count = valid
    inst.duplicate_count = duplicate_count
    inst.search_completed_at = timezone.now()
    inst.started_at = timezone.now()

    is_auto_completed = False
    if valid > 0 and valid <= 2000:
        from app.task_queue.crud import TaskQueueService
        svc = TaskQueueService(db)
        await svc.enqueue(
            queue_type="llm",
            task_type="llm_analysis",
            params_json=json.dumps({"instance_id": instance_id, "instance_no": instance_no}),
            task_key=f"llm_{instance_no}",
            timeout_sec=3600,
        )
    elif valid == 0:
        inst.status = "completed"
        inst.completed_at = timezone.now()
        is_auto_completed = True

    await db.commit()

    await log_operation(db, current_user.id, "import", "task_instance", instance_id,
                        f"Excel 导入 {instance_no}：共 {total} 条，有效 {valid} 条，重复 {duplicate_count} 条")

    final_status = "completed" if is_auto_completed else "search_completed"
    from app.routers.sse import broadcast_event
    await broadcast_event(instance_id, "task.progress", {
        "status": final_status,
        "total": total,
        "valid": valid,
        "duplicate": duplicate_count,
    })
    if is_auto_completed:
        await broadcast_event(instance_id, "task.completed", {
            "status": "completed",
            "completed_at": timezone.now().isoformat(),
        })

    return {
        "message": "Excel 数据导入成功",
        "total": total,
        "valid": valid,
        "duplicate": duplicate_count,
    }
