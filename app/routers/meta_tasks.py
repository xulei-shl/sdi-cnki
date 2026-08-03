from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, model_validator
from sqlalchemy import select, func, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.meta_task import MetaTask
from app.models.meta_task_dedup_scope import MetaTaskDedupScope
from app.models.meta_task_llm_config import MetaTaskLlmConfig
from app.models.system_prompt import SystemPrompt
from app.models.task_instance import TaskInstance
from app.models.task_result import TaskResult
from app.models.user import User
from app.routers.task_instances import _cleanup_instance_side_effects
from app.utils.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.utils.oplog import log_operation
from app.routers import get_current_user_from_header, require_admin_user

router = APIRouter()

MAX_EXPORT_VALUES = {50, 100, 150, 200, 250, 300, 350, 400, 450, 500}
DATE_RANGE_VALUES = {"week", "month", "half-year", "year", "ytd", "last-year"}


async def _validate_prompt_access(
    db: AsyncSession, prompt_id: int | None, user, error_prefix: str = "",
) -> None:
    if prompt_id is None:
        return
    result = await db.execute(select(SystemPrompt).where(SystemPrompt.id == prompt_id))
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise ValidationError(f"{error_prefix}提示词模板不存在")
    if user.role != "admin" and prompt.creator_id != user.id:
        raise ValidationError(f"{error_prefix}只能使用自己的提示词")


def validate_search_params(params: dict) -> None:
    mode = params.get("search_mode", "basic")
    if mode == "professional":
        ga = params.get("query_group_a")
        gb = params.get("query_group_b")
        if ga is not None:
            if not isinstance(ga, list) or not all(isinstance(q, str) for q in ga):
                raise ValidationError("query_group_a 必须是非空字符串数组")
        if gb is not None:
            if not isinstance(gb, list) or not all(isinstance(q, str) for q in gb):
                raise ValidationError("query_group_b 必须是非空字符串数组")
        ga_clean = [q.strip() for q in ga if q.strip()] if ga else []
        gb_clean = [q.strip() for q in gb if q.strip()] if gb else []
        params["query_group_a"] = ga_clean
        params["query_group_b"] = gb_clean
        au = params.get("au_group")
        if au is not None:
            if not isinstance(au, list) or not all(isinstance(a, str) for a in au):
                raise ValidationError("au_group 必须是字符串数组")
            au_clean = [a.strip() for a in au if a.strip()]
            params["au_group"] = au_clean
        fu = params.get("fu_group")
        if fu is not None:
            if not isinstance(fu, list) or not all(isinstance(f, str) for f in fu):
                raise ValidationError("fu_group 必须是字符串数组")
            fu_clean = [f.strip() for f in fu if f.strip()]
            params["fu_group"] = fu_clean
        if not ga_clean and not gb_clean and not params.get("au_group") and not params.get("fu_group"):
            raise ValidationError("query_group_a/query_group_b/au_group/fu_group 至少需要一组非空值")
    else:
        queries = params.get("queries")
        query = params.get("query")
        if not queries and not query:
            raise ValidationError("queries 或 query 为必填项")
        if queries:
            if not isinstance(queries, list) or not all(isinstance(q, str) for q in queries):
                raise ValidationError("queries 必须是非空字符串数组")
            queries = [q for q in queries if q.strip()]
            if not queries:
                raise ValidationError("queries 至少需要一个非空检索词")
            params["queries"] = queries
        else:
            params["queries"] = [query.strip()]
    max_export = params.get("max_export")
    if max_export is None:
        raise ValidationError("max_export 为必填项")
    if max_export not in MAX_EXPORT_VALUES:
        raise ValidationError(f"max_export 必须为 {sorted(MAX_EXPORT_VALUES)} 中的一个")
    date_range = params.get("date_range")
    year_from = params.get("year_from")
    year_to = params.get("year_to")
    if date_range and (year_from is not None or year_to is not None):
        raise ValidationError("date_range 与 year_from/year_to 互斥，不能同时传入")
    if date_range and date_range not in DATE_RANGE_VALUES:
        raise ValidationError(f"date_range 必须为 {sorted(DATE_RANGE_VALUES)} 中的一个")


class MetaTaskCreate(BaseModel):
    name: str
    description: Optional[str] = None
    search_params: dict
    prompt_template_id: Optional[int] = None
    llm_config_ids: list[int]
    schedule_cron: Optional[str] = None
    is_periodic: bool = False
    dedup_scope_meta_task_ids: list[int] = []

    @model_validator(mode="after")
    def _validate(self):
        validate_search_params(self.search_params)
        return self


class MetaTaskUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    search_params: Optional[dict] = None
    prompt_template_id: Optional[int] = None
    llm_config_ids: Optional[list[int]] = None
    schedule_cron: Optional[str] = None
    is_periodic: Optional[bool] = None
    is_active: Optional[bool] = None
    dedup_scope_meta_task_ids: Optional[list[int]] = None

    @model_validator(mode="after")
    def _validate(self):
        if self.search_params is not None:
            validate_search_params(self.search_params)
        return self


@router.get("")
async def list_meta_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None),
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    where = []
    if current_user.role != "admin":
        where.append(MetaTask.creator_id == current_user.id)
    if keyword:
        where.append(MetaTask.name.ilike(f"%{keyword}%"))
    stmt = (
        select(MetaTask)
        .where(*where)
        .options(
            selectinload(MetaTask.llm_config_links).selectinload(MetaTaskLlmConfig.llm_config),
            selectinload(MetaTask.creator),
            selectinload(MetaTask.dedup_scope_links),
        )
        .order_by(desc(MetaTask.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    tasks = result.unique().scalars().all()
    count_stmt = select(func.count(MetaTask.id)).where(*where)
    total = (await db.execute(count_stmt)).scalar()

    prompt_ids = list({t.prompt_template_id for t in tasks if t.prompt_template_id})
    prompt_map = {}
    if prompt_ids:
        prompts = await db.execute(select(SystemPrompt).where(SystemPrompt.id.in_(prompt_ids)))
        prompt_map = {p.id: p.name for p in prompts.scalars().all()}

    all_dedup_ids = list({link.dedup_meta_task_id for t in tasks for link in t.dedup_scope_links})
    dedup_name_map = {}
    if all_dedup_ids:
        dedup_tasks = await db.execute(select(MetaTask).where(MetaTask.id.in_(all_dedup_ids)))
        dedup_name_map = {dt.id: dt.name for dt in dedup_tasks.scalars().all()}

    items = []
    for t in tasks:
        llm_names = [link.llm_config.name for link in t.llm_config_links if link.llm_config]
        inst_count = await db.execute(
            select(func.count(TaskInstance.id)).where(TaskInstance.meta_task_id == t.id)
        )
        dedup_ids = sorted([link.dedup_meta_task_id for link in t.dedup_scope_links])
        dedup_names = [dedup_name_map.get(did, "") for did in dedup_ids]
        items.append({
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "search_params": t.search_params,
            "prompt_template_id": t.prompt_template_id,
            "prompt_template_name": prompt_map.get(t.prompt_template_id) if t.prompt_template_id else None,
            "llm_config_names": llm_names,
            "creator_id": t.creator_id,
            "creator_name": t.creator.username if t.creator else "",
            "is_active": t.is_active,
            "execution_count": t.execution_count,
            "last_executed_at": t.last_executed_at.isoformat() if t.last_executed_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else "",
            "dedup_scope_meta_task_ids": dedup_ids,
            "dedup_scope_meta_task_names": dedup_names,
        })
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("")
async def create_meta_task(
    data: MetaTaskCreate,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    if not data.llm_config_ids:
        raise ValidationError("At least one LLM config is required")
    await _validate_prompt_access(db, data.prompt_template_id, current_user)
    task = MetaTask(
        name=data.name,
        description=data.description,
        creator_id=current_user.id,
        prompt_template_id=data.prompt_template_id,
        search_params=json.dumps(data.search_params, ensure_ascii=False),
        schedule_cron=data.schedule_cron,
        is_periodic=data.is_periodic,
        is_active=True,
    )
    db.add(task)
    await db.flush()
    for idx, llm_id in enumerate(data.llm_config_ids):
        link = MetaTaskLlmConfig(meta_task_id=task.id, llm_config_id=llm_id, priority=idx)
        db.add(link)
    for dedup_id in data.dedup_scope_meta_task_ids:
        if dedup_id != task.id:
            link = MetaTaskDedupScope(meta_task_id=task.id, dedup_meta_task_id=dedup_id)
            db.add(link)
    await db.commit()
    await db.refresh(task)
    await log_operation(db, current_user.id, "create", "meta_task", task.id, f"Created meta task {task.name}")
    return {"id": task.id, "name": task.name}


@router.get("/dedup-candidates")
async def list_dedup_candidates(
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户可作为去重范围参考的任务模板"""
    where = []
    if current_user.role != "admin":
        where.append(MetaTask.creator_id == current_user.id)
    stmt = select(MetaTask).where(*where).options(
        selectinload(MetaTask.creator),
    ).order_by(MetaTask.name)
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return [
        {"id": t.id, "name": t.name, "creator_name": t.creator.username if t.creator else "", "created_at": t.created_at.isoformat() if t.created_at else ""}
        for t in tasks
    ]


@router.get("/{task_id}")
async def get_meta_task(
    task_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(MetaTask)
        .where(MetaTask.id == task_id)
        .options(
            selectinload(MetaTask.llm_config_links).selectinload(MetaTaskLlmConfig.llm_config),
            selectinload(MetaTask.creator),
            selectinload(MetaTask.dedup_scope_links),
        )
    )
    result = await db.execute(stmt)
    task = result.unique().scalar_one_or_none()
    if not task:
        raise NotFoundError("MetaTask", task_id)
    if current_user.role != "admin" and task.creator_id != current_user.id:
        raise PermissionDeniedError()
    llm_configs = [
        {"id": link.llm_config_id, "name": link.llm_config.name if link.llm_config else "", "priority": link.priority}
        for link in sorted(task.llm_config_links, key=lambda x: x.priority)
    ]
    recent_instances = await db.execute(
        select(TaskInstance)
        .where(TaskInstance.meta_task_id == task.id)
        .order_by(desc(TaskInstance.created_at))
        .limit(5)
    )
    prompt_template_name = None
    if task.prompt_template_id:
        pt = await db.execute(select(SystemPrompt.name).where(SystemPrompt.id == task.prompt_template_id))
        prompt_template_name = pt.scalar()

    instances = [
        {"id": inst.id, "instance_no": inst.instance_no, "status": inst.status, "created_at": inst.created_at.isoformat() if inst.created_at else ""}
        for inst in recent_instances.scalars().all()
    ]
    dedup_ids = sorted([link.dedup_meta_task_id for link in task.dedup_scope_links])
    dedup_names = []
    if dedup_ids:
        dt = await db.execute(select(MetaTask).where(MetaTask.id.in_(dedup_ids)))
        dedup_map = {d.id: d.name for d in dt.scalars().all()}
        dedup_names = [dedup_map.get(did, "") for did in dedup_ids]

    return {
        "id": task.id,
        "name": task.name,
        "description": task.description,
        "search_params": json.loads(task.search_params) if task.search_params else {},
        "prompt_template_id": task.prompt_template_id,
        "prompt_template_name": prompt_template_name,
        "llm_configs": llm_configs,
        "schedule_cron": task.schedule_cron,
        "is_periodic": task.is_periodic,
        "is_active": task.is_active,
        "execution_count": task.execution_count,
        "last_executed_at": task.last_executed_at.isoformat() if task.last_executed_at else None,
        "creator_id": task.creator_id,
        "creator_name": task.creator.username if task.creator else "",
        "created_at": task.created_at.isoformat() if task.created_at else "",
        "recent_instances": instances,
        "dedup_scope_meta_task_ids": dedup_ids,
        "dedup_scope_meta_task_names": dedup_names,
    }


@router.put("/{task_id}")
async def update_meta_task(
    task_id: int,
    data: MetaTaskUpdate,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MetaTask).where(MetaTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError("MetaTask", task_id)
    if current_user.role != "admin" and task.creator_id != current_user.id:
        raise PermissionDeniedError()
    if data.name is not None:
        task.name = data.name
    if data.description is not None:
        task.description = data.description
    if data.search_params is not None:
        task.search_params = json.dumps(data.search_params, ensure_ascii=False)
    if data.prompt_template_id is not None:
        await _validate_prompt_access(db, data.prompt_template_id, current_user)
        task.prompt_template_id = data.prompt_template_id
    if data.dedup_scope_meta_task_ids is not None:
        existing_dedup = await db.execute(
            select(MetaTaskDedupScope).where(MetaTaskDedupScope.meta_task_id == task_id)
        )
        for link in existing_dedup.scalars().all():
            await db.delete(link)
        await db.flush()
        for dedup_id in data.dedup_scope_meta_task_ids:
            if dedup_id != task.id:
                link = MetaTaskDedupScope(meta_task_id=task.id, dedup_meta_task_id=dedup_id)
                db.add(link)
    if data.schedule_cron is not None:
        task.schedule_cron = data.schedule_cron
    if data.is_periodic is not None:
        task.is_periodic = data.is_periodic
    if data.is_active is not None:
        task.is_active = data.is_active
    if data.llm_config_ids is not None:
        existing = await db.execute(
            select(MetaTaskLlmConfig).where(MetaTaskLlmConfig.meta_task_id == task_id)
        )
        for link in existing.scalars().all():
            await db.delete(link)
        await db.flush()
        for idx, llm_id in enumerate(data.llm_config_ids):
            link = MetaTaskLlmConfig(meta_task_id=task.id, llm_config_id=llm_id, priority=idx)
            db.add(link)
    await db.commit()
    return {"id": task.id, "name": task.name}


@router.delete("/{task_id}")
async def delete_meta_task(
    task_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MetaTask)
        .where(MetaTask.id == task_id)
        .options(
            selectinload(MetaTask.task_instances)
                .selectinload(TaskInstance.task_results)
                    .selectinload(TaskResult.llm_analysis),
            selectinload(MetaTask.task_instances)
                .selectinload(TaskInstance.task_results)
                    .selectinload(TaskResult.download_result),
        )
    )
    task = result.unique().scalar_one_or_none()
    if not task:
        raise NotFoundError("MetaTask", task_id)
    if current_user.role != "admin" and task.creator_id != current_user.id:
        raise PermissionDeniedError()

    instances = task.task_instances or []
    running_statuses = {"search_queued", "running", "analyzing", "downloading", "download_queued"}
    for inst in instances:
        if inst.status in running_statuses:
            raise ValidationError(
                f"任务实例 {inst.instance_no} 当前状态为 {inst.status}，无法删除模板"
            )

    if instances:
        for inst in instances:
            await _cleanup_instance_side_effects(db, inst)

        # 删除所有任务实例（ORM 级联 task_results → llm_analysis_results, download_results）
        for inst in instances:
            await db.delete(inst)

    # 删除任务模板（ORM 级联 meta_task_llm_configs, meta_task_dedup_scopes）
    await db.delete(task)
    await db.commit()
    await log_operation(db, current_user.id, "delete", "meta_task", task_id, f"Deleted meta task {task.name}")
    return {"message": "Meta task deleted"}


@router.post("/{task_id}/clone")
async def clone_meta_task(
    task_id: int,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MetaTask)
        .where(MetaTask.id == task_id)
        .options(
            selectinload(MetaTask.llm_config_links),
            selectinload(MetaTask.dedup_scope_links),
        )
    )
    task = result.unique().scalar_one_or_none()
    if not task:
        raise NotFoundError("MetaTask", task_id)
    if current_user.role != "admin" and task.creator_id != current_user.id:
        raise PermissionDeniedError()

    new_task = MetaTask(
        name=f"{task.name}（副本）",
        description=task.description,
        creator_id=current_user.id,
        prompt_template_id=task.prompt_template_id,
        search_params=task.search_params,
        schedule_cron=task.schedule_cron,
        is_periodic=task.is_periodic,
        is_active=True,
    )
    db.add(new_task)
    await db.flush()

    for link in task.llm_config_links:
        db.add(MetaTaskLlmConfig(
            meta_task_id=new_task.id,
            llm_config_id=link.llm_config_id,
            priority=link.priority,
        ))

    existing_dedup_ids = [link.dedup_meta_task_id for link in task.dedup_scope_links]
    valid_dedup_ids = []
    if existing_dedup_ids:
        existing_tasks = await db.execute(
            select(MetaTask.id).where(MetaTask.id.in_(existing_dedup_ids))
        )
        valid_ids = {row[0] for row in existing_tasks.fetchall()}
        for dedup_id in existing_dedup_ids:
            if dedup_id not in valid_ids:
                continue
            if dedup_id == new_task.id:
                continue
            valid_dedup_ids.append(dedup_id)
            db.add(MetaTaskDedupScope(meta_task_id=new_task.id, dedup_meta_task_id=dedup_id))

    existing_links = await db.execute(
        select(MetaTaskDedupScope).where(
            or_(
                MetaTaskDedupScope.meta_task_id == task.id,
                MetaTaskDedupScope.meta_task_id == new_task.id,
            )
        )
    )
    existing_pairs = {(r.meta_task_id, r.dedup_meta_task_id) for r in existing_links.scalars().all()}

    if (task.id, new_task.id) not in existing_pairs:
        db.add(MetaTaskDedupScope(meta_task_id=task.id, dedup_meta_task_id=new_task.id))
    if (new_task.id, task.id) not in existing_pairs:
        db.add(MetaTaskDedupScope(meta_task_id=new_task.id, dedup_meta_task_id=task.id))

    await db.commit()
    await db.refresh(new_task)
    await log_operation(db, current_user.id, "clone", "meta_task", task_id,
                        f"Cloned meta task {task.name} -> {new_task.name}")
    return {"id": new_task.id, "name": new_task.name}


class ExecuteMetaTaskBody(BaseModel):
    auto_run: bool = True

@router.post("/{task_id}/execute")
async def execute_meta_task(
    task_id: int,
    body: ExecuteMetaTaskBody,
    current_user = Depends(get_current_user_from_header),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MetaTask).where(MetaTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundError("MetaTask", task_id)
    if current_user.role != "admin" and task.creator_id != current_user.id:
        raise PermissionDeniedError()
    from app.routers.task_instances import _create_instance
    instance = await _create_instance(db, task, current_user, auto_run=body.auto_run)
    if body.auto_run:
        from app.task_queue.crud import TaskQueueService
        svc = TaskQueueService(db)
        await svc.enqueue(
            queue_type="cnki",
            task_type="cnki_search",
            params_json=json.dumps({"instance_id": instance.id, "instance_no": instance.instance_no}),
            task_key=instance.instance_no,
            commit=False,
            timeout_sec=5400,
        )
        instance.status = "search_queued"
        await db.commit()
    from app.routers.sse import broadcast_event
    await broadcast_event(instance.id, "task.progress", {"status": instance.status})
    await log_operation(db, current_user.id, "execute", "meta_task", task_id, f"Executed meta task {task.name}")
    return {"instance_id": instance.id, "instance_no": instance.instance_no}
