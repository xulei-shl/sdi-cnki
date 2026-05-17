from __future__ import annotations

import json
from typing import Optional

from app.utils import timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.meta_task import MetaTask
from app.models.task_instance import TaskInstance
from app.models.task_result import TaskResult
from app.utils.exceptions import NotFoundError, ValidationError
from app.utils.oplog import log_operation
from app.routers import get_current_user_from_header

router = APIRouter()


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
        from app.utils.exceptions import PermissionDeniedError
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
        from app.utils.exceptions import PermissionDeniedError
        raise PermissionDeniedError()
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
    }


@router.delete("/{instance_id}")
async def delete_instance(
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
        from app.utils.exceptions import PermissionDeniedError
        raise PermissionDeniedError()
    if inst.status != "pending" and inst.search_result_count != 0:
        raise ValidationError("Only pending instances can be deleted")
    task_stmt = select(MetaTask).where(MetaTask.id == inst.meta_task_id)
    task_result = await db.execute(task_stmt)
    task = task_result.scalar_one_or_none()
    if task:
        task.execution_count = max(0, (task.execution_count or 0) - 1)
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
    """Full delete: decrement PDF ref_count, remove physical files, delete records."""
    stmt = select(TaskInstance).where(TaskInstance.id == instance_id)
    result = await db.execute(stmt)
    inst = result.scalar_one_or_none()
    if not inst:
        raise NotFoundError("TaskInstance", instance_id)
    if current_user.role != "admin" and inst.creator_id != current_user.id:
        from app.utils.exceptions import PermissionDeniedError
        raise PermissionDeniedError()

    from app.services.pdf_cleanup import decrement_pdf_refs_for_instance
    await decrement_pdf_refs_for_instance(db, instance_id)

    await db.delete(inst)
    await db.commit()
    await log_operation(db, current_user.id, "delete", "task_instance", instance_id, f"Deleted instance {inst.instance_no}")
    return {"message": "Instance deleted"}


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
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(TaskInstance).where(TaskInstance.id == instance_id)
    result = await db.execute(stmt)
    inst = result.scalar_one_or_none()
    if not inst:
        raise NotFoundError("TaskInstance", instance_id)
    if current_user.role != "admin" and inst.creator_id != current_user.id:
        from app.utils.exceptions import PermissionDeniedError
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
        score = None
        if parsed:
            score = parsed.get("relevance_score")
        if min_score is not None and (score is None or score < min_score):
            continue
        if analysis_result == "passed":
            if parsed is None or not parsed.get("is_target_topic"):
                continue
        elif analysis_result == "rejected":
            if parsed is None or parsed.get("is_target_topic") is not False:
                continue
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
        from app.utils.exceptions import PermissionDeniedError
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
        from app.utils.exceptions import PermissionDeniedError
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
