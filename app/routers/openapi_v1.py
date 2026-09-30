"""开放接口 v1：供 agent / 第三方系统提交元数据检索作业并取回结果。

设计要点：
- 提交即返回（202），作业走既有 cnki 队列 —— 该队列全局串行（并发=1），
  与网页触发的检索共用同一个 CNKI 账号与浏览器会话，二者天然排队互不抢登录态；
- 作业队列优先级高于网页任务（priority 更小），API 作业优先出队；
- 状态接口带阶段 stage + 独立心跳 heartbeat，调用方据此区分“耗时长”与“卡死”；
- 结果以 JSON 为主返回，原始 Excel 通过短期签名 URL 或内联下载获取；
- 作业实例 source=api，不在网页列表/统计中展示，也不触发通知 / SSE / LLM / PDF 链路；
- 入口限制在途作业数，避免调用方并发提交把网页检索长时间挤在队列后面。
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import create_artifact_token, decode_artifact_token, hash_password
from app.models.api_key import ApiKey
from app.models.meta_task import MetaTask
from app.models.task_instance import TaskInstance
from app.models.task_queue import TaskQueueItem
from app.models.task_result import TaskResult
from app.models.user import User
from app.routers import require_admin_user
from app.routers.meta_tasks import validate_search_params
from app.routers.task_instances import CNKI_TIMEOUT_SEC, _allocate_instance_no
from app.task_queue.crud import TaskQueueService
from app.utils import timezone
from app.utils.api_key import PREFIX_LENGTH, generate_api_key, verify_api_key
from app.utils.exceptions import (
    AppError,
    AuthenticationError,
    NotFoundError,
    RateLimitedError,
    ValidationError,
)
from app.utils.logging import get_logger
from app.utils.oplog import log_operation

logger = get_logger("openapi_v1")
settings = get_settings()

router = APIRouter()

# 接口内部使用的服务账号与隐藏模板（不参与网页展示）
API_SERVICE_USERNAME = "api_service"
API_META_TASK_NAME = "开放接口检索（内部）"

# 数量上限固定为 100；默认沿用当前逻辑的默认值 50
API_ALLOWED_MAX_EXPORT = (50, 100)
API_DEFAULT_MAX_EXPORT = 50

# 同时在途的 API 作业上限：cnki 队列全局串行，多提交只会排队等待，
# 却会把网页检索挤到后面，因此在入口就把压力反馈给调用方。
API_MAX_INFLIGHT_JOBS = 2
# 触发限流时建议调用方退避的秒数（单次检索典型耗时 25~60s）
API_RATE_LIMIT_RETRY_AFTER_SEC = 30

# 小于网页任务的 0，使 dequeue 的 priority ASC 排序让 API 作业优先出队
API_QUEUE_PRIORITY = -1
API_ARTIFACT_TOKEN_TTL_MIN = 30
API_MAX_INLINE_BYTES = 5 * 1024 * 1024
API_LONG_POLL_MAX_SEC = 25
API_KEY_LAST_USED_THROTTLE_SEC = 60

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

STATE_MAP = {
    "pending": "queued",
    "search_queued": "queued",
    "running": "running",
    "search_completed": "running",
    "completed": "succeeded",
    "failed": "failed",
}
TERMINAL_STATES = {"succeeded", "failed", "cancelled", "timeout"}
RESULT_READY_STATES = ("search_completed", "completed")


# ═══════════════════════════════════════════════════════════
#  AUTH — API Key
# ═══════════════════════════════════════════════════════════


async def verify_api_key_header(authorization: str | None, db: AsyncSession) -> ApiKey:
    if not authorization:
        raise AuthenticationError("Missing API key")
    raw = authorization.replace("Bearer ", "").strip()
    if not raw:
        raise AuthenticationError("Missing API key")
    rows = (
        await db.execute(
            select(ApiKey).where(ApiKey.key_prefix == raw[:PREFIX_LENGTH], ApiKey.is_active == True)
        )
    ).scalars().all()
    for key in rows:
        if key.expires_at and key.expires_at < timezone.now():
            continue
        if verify_api_key(raw, key.key_hash):
            # 每次轮询都写库代价过高，按节流更新时间
            now = timezone.now()
            if not key.last_used_at or (now - key.last_used_at).total_seconds() > API_KEY_LAST_USED_THROTTLE_SEC:
                key.last_used_at = now
                await db.commit()
            return key
    raise AuthenticationError("Invalid API key")


async def get_api_client(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    return await verify_api_key_header(authorization, db)


# ═══════════════════════════════════════════════════════════
#  KEY MANAGEMENT — 管理员通过网页登录态管理
# ═══════════════════════════════════════════════════════════


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=3650)


@router.post("/keys", status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    current_user=Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    raw, prefix, key_hash = generate_api_key()
    key = ApiKey(
        name=body.name,
        key_prefix=prefix,
        key_hash=key_hash,
        expires_at=timezone.now() + timedelta(days=body.expires_in_days) if body.expires_in_days else None,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    await log_operation(db, current_user.id, "create", "api_key", key.id, f"Created API key {body.name}")
    return {
        "id": key.id,
        "name": key.name,
        "api_key": raw,
        "key_prefix": prefix,
        "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        "warning": "API Key 仅此一次返回，请立即保存",
    }


@router.get("/keys")
async def list_api_keys(current_user=Depends(require_admin_user), db: AsyncSession = Depends(get_db)):
    keys = (await db.execute(select(ApiKey).order_by(ApiKey.id.desc()))).scalars().all()
    return {
        "items": [
            {
                "id": k.id,
                "name": k.name,
                "key_prefix": k.key_prefix,
                "is_active": k.is_active,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "created_at": k.created_at.isoformat() if k.created_at else None,
            }
            for k in keys
        ]
    }


@router.delete("/keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    current_user=Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    key = (await db.execute(select(ApiKey).where(ApiKey.id == key_id))).scalar_one_or_none()
    if not key:
        raise NotFoundError("ApiKey", key_id)
    key.is_active = False
    await db.commit()
    await log_operation(db, current_user.id, "revoke", "api_key", key_id, f"Revoked API key {key.name}")
    return {"id": key.id, "name": key.name, "is_active": False}


# ═══════════════════════════════════════════════════════════
#  JOBS — 提交 / 轮询 / 结果 / 文件
# ═══════════════════════════════════════════════════════════


class MetadataJobRequest(BaseModel):
    """检索条件。basic 模式用 query/queries，professional 模式用 query_group_a/query_group_b。"""

    search_mode: Optional[str] = None
    query: Optional[str] = None
    queries: Optional[list[str]] = None
    query_group_a: Optional[list[str]] = None
    query_group_b: Optional[list[str]] = None
    au_group: Optional[list[str]] = None
    fu_group: Optional[list[str]] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    date_range: Optional[str] = None
    core_only: bool = False
    synonym_extend: bool = False
    include_no_fulltext: bool = False
    max_export: Literal[50, 100] = Field(
        default=API_DEFAULT_MAX_EXPORT, description="导出条数上限，仅支持 50 或 100"
    )
    idempotency_key: Optional[str] = Field(default=None, max_length=64)


def _build_search_params(body: MetadataJobRequest) -> dict:
    params = {k: v for k, v in body.model_dump(exclude_none=True).items() if k != "idempotency_key"}
    validate_search_params(params)
    return params


async def _get_or_create_service_actor(db: AsyncSession) -> tuple[User, MetaTask]:
    """取得（或创建）接口内部服务账号与其隐藏模板。

    MetaTask.creator_id / TaskInstance.meta_task_id 均为非空，故必须存在这两个载体。
    模板 source=api 且 is_active=False，不在网页列表中展示。
    """
    user = (await db.execute(select(User).where(User.username == API_SERVICE_USERNAME))).scalar_one_or_none()
    if user is None:
        user = User(
            username=API_SERVICE_USERNAME,
            password_hash=hash_password(secrets.token_urlsafe(32)),
            role="user",
            is_active=False,
        )
        db.add(user)
        await db.flush()

    task = (
        await db.execute(
            select(MetaTask).where(MetaTask.creator_id == user.id, MetaTask.source == "api")
        )
    ).scalar_one_or_none()
    if task is None:
        task = MetaTask(
            name=API_META_TASK_NAME,
            description="开放接口内部占位模板，仅供 API 检索作业引用。",
            creator_id=user.id,
            search_params=json.dumps(
                {"search_mode": "basic", "queries": ["api-placeholder"], "max_export": API_DEFAULT_MAX_EXPORT},
                ensure_ascii=False,
            ),
            is_periodic=False,
            is_active=False,
            source="api",
        )
        db.add(task)
        await db.flush()
    return user, task


async def _get_instance(db: AsyncSession, job_id: int, *, refresh: bool = False) -> TaskInstance:
    stmt = select(TaskInstance).where(TaskInstance.id == job_id, TaskInstance.source == "api")
    if refresh:
        stmt = stmt.execution_options(populate_existing=True)
    instance = (await db.execute(stmt)).scalar_one_or_none()
    if not instance:
        raise NotFoundError("MetadataJob", job_id)
    return instance


async def _queue_position(db: AsyncSession, instance: TaskInstance) -> int:
    """排在该作业之前、尚未执行的 cnki 队列任务数（同优先级的更早 API 作业）。"""
    ahead = (
        await db.execute(
            select(func.count(TaskQueueItem.id)).where(
                TaskQueueItem.queue_type == "cnki",
                TaskQueueItem.status.in_(("pending", "retrying")),
                or_(
                    TaskQueueItem.priority < API_QUEUE_PRIORITY,
                    and_(
                        TaskQueueItem.priority == API_QUEUE_PRIORITY,
                        TaskQueueItem.created_at <= instance.created_at,
                    ),
                ),
            )
        )
    ).scalar() or 0
    return max(int(ahead) - 1, 0)


async def _inflight_job_ids(db: AsyncSession) -> list[int]:
    """返回仍占用 cnki 串行槽位的 API 作业 id。

    以队列行为准，而非 TaskInstance.status：实例状态可能因异常遗留而长期停在
    中间态（历史事故见 docs/changelog/20260930），若按实例计数会永久占掉配额，
    把限流变成自我拒绝服务。队列行才是真正占据串行槽位的对象，且超时会被
    reclaim_stale_running 回收。

    识别 API 作业的依据是 priority 等于本模块入队时用的 API_QUEUE_PRIORITY
    （网页检索入队用默认值 0）；引用同一常量可避免优先级调整后二者漂移。
    """
    rows = (
        await db.execute(
            select(TaskQueueItem.params_json).where(
                TaskQueueItem.queue_type == "cnki",
                TaskQueueItem.task_type == "cnki_search",
                TaskQueueItem.priority == API_QUEUE_PRIORITY,
                TaskQueueItem.status.in_(("pending", "retrying", "running")),
            )
        )
    ).scalars().all()
    ids: list[int] = []
    for params_json in rows:
        try:
            instance_id = json.loads(params_json or "").get("instance_id")
        except (ValueError, AttributeError):
            continue
        if instance_id is not None:
            ids.append(int(instance_id))
    return ids


async def _estimate_remaining_seconds(db: AsyncSession, instance: TaskInstance) -> int | None:
    """按最近 10 个已完成的 API 作业均值估算剩余时间；无历史则不猜测。"""
    if not instance.started_at:
        return None
    rows = (
        await db.execute(
            select(TaskInstance.started_at, TaskInstance.completed_at)
            .where(
                TaskInstance.source == "api",
                TaskInstance.status == "completed",
                TaskInstance.started_at.isnot(None),
                TaskInstance.completed_at.isnot(None),
            )
            .order_by(TaskInstance.id.desc())
            .limit(10)
        )
    ).all()
    durations = [(c - s).total_seconds() for s, c in rows if s and c]
    if not durations:
        return None
    avg = sum(durations) / len(durations)
    elapsed = (timezone.now() - instance.started_at).total_seconds()
    return max(int(avg - elapsed), 0)


async def _build_status(db: AsyncSession, instance: TaskInstance, *, deduplicated: bool = False) -> dict:
    now = timezone.now()
    state = STATE_MAP.get(instance.status, "running")
    terminal = state in TERMINAL_STATES
    payload: dict = {
        "job_id": instance.id,
        "job_no": instance.instance_no,
        "state": state,
        "stage": instance.progress_stage,
        "stage_message": instance.progress_message,
        "batch": (
            {"current": instance.progress_current, "total": instance.progress_total}
            if instance.progress_current is not None or instance.progress_total is not None
            else None
        ),
        # 排队中的任务数；priority 低于我们的网页任务会插队，故为估算值
        "queue_position": await _queue_position(db, instance) if state == "queued" else 0,
        "elapsed_seconds": int((now - instance.started_at).total_seconds()) if instance.started_at else 0,
        "heartbeat_age_seconds": int((now - instance.heartbeat_at).total_seconds()) if instance.heartbeat_at else None,
        "heartbeat_at": instance.heartbeat_at.isoformat() if instance.heartbeat_at else None,
        "eta_seconds": None,
        "next_poll_after_ms": 0 if terminal else (5000 if state == "queued" else 2000),
        "result_ready": state == "succeeded",
        "result_url": f"/api/v1/open/metadata-jobs/{instance.id}/results" if state == "succeeded" else None,
        "counts": None,
        "error": instance.error_message if state == "failed" else None,
    }
    if state == "running":
        payload["eta_seconds"] = await _estimate_remaining_seconds(db, instance)
    if instance.status in RESULT_READY_STATES:
        payload["counts"] = {
            "total": instance.search_result_count or 0,
            "valid": instance.valid_data_count or 0,
            "duplicate": instance.duplicate_count or 0,
        }
    if deduplicated:
        payload["deduplicated"] = True
    return payload


@router.post("/metadata-jobs", status_code=202)
async def create_metadata_job(
    body: MetadataJobRequest,
    client: ApiKey = Depends(get_api_client),
    db: AsyncSession = Depends(get_db),
):
    search_params = _build_search_params(body)
    svc = TaskQueueService(db)

    # 幂等：相同 idempotency_key 直接返回既有作业，不重复排队
    queue_task_key: str | None = None
    if body.idempotency_key:
        queue_task_key = f"api_{body.idempotency_key}"
        existing = (
            await db.execute(select(TaskQueueItem).where(TaskQueueItem.task_key == queue_task_key))
        ).scalar_one_or_none()
        if existing:
            existing_params = json.loads(existing.params_json or "{}")
            instance = (
                await db.execute(
                    select(TaskInstance).where(TaskInstance.id == existing_params.get("instance_id"))
                )
            ).scalar_one_or_none()
            if instance:
                return await _build_status(db, instance, deduplicated=True)

    # 在途上限：置于幂等检查之后（同 key 重试应拿回既有作业，而不是被自家配额拒），
    # 且置于分配流水号 / 建实例之前，保证被拒绝的请求不留任何副作用。
    inflight = await _inflight_job_ids(db)
    if len(inflight) >= API_MAX_INFLIGHT_JOBS:
        listed = "、".join(f"#{i}" for i in sorted(inflight))
        raise RateLimitedError(
            f"在途作业已达上限 {API_MAX_INFLIGHT_JOBS} 个（{listed}）。"
            f"请改为轮询上述已有作业，或等待 {API_RATE_LIMIT_RETRY_AFTER_SEC} 秒后再提交。",
            retry_after=API_RATE_LIMIT_RETRY_AFTER_SEC,
        )

    user, meta_task = await _get_or_create_service_actor(db)
    instance_no = await _allocate_instance_no(db)
    execution_params = {
        "search_params": search_params,
        "prompt_template_id": None,
        "llm_config_ids": [],
        "api_key_id": client.id,
    }
    instance = TaskInstance(
        meta_task_id=meta_task.id,
        creator_id=user.id,
        instance_no=instance_no,
        status="search_queued",
        auto_run=True,
        source="api",
        execution_params=json.dumps(execution_params, ensure_ascii=False),
    )
    db.add(instance)
    await db.flush()

    await svc.enqueue(
        queue_type="cnki",
        task_type="cnki_search",
        params_json=json.dumps({"instance_id": instance.id, "instance_no": instance_no}, ensure_ascii=False),
        task_key=queue_task_key or instance_no,
        priority=API_QUEUE_PRIORITY,
        commit=False,
        timeout_sec=CNKI_TIMEOUT_SEC,
    )
    meta_task.execution_count = (meta_task.execution_count or 0) + 1
    meta_task.last_executed_at = timezone.now()
    await db.commit()
    await db.refresh(instance)

    logger.info(
        f"API metadata job queued: instance={instance_no} key={client.name} max_export={body.max_export}"
    )
    return await _build_status(db, instance)


@router.get("/metadata-jobs/{job_id}")
async def get_metadata_job(
    job_id: int,
    wait: int = Query(0, ge=0, le=API_LONG_POLL_MAX_SEC, description="长轮询最多挂起秒数；状态一变立即返回"),
    client: ApiKey = Depends(get_api_client),
    db: AsyncSession = Depends(get_db),
):
    instance = await _get_instance(db, job_id)
    deadline = time.monotonic() + wait
    while True:
        payload = await _build_status(db, instance)
        if not wait or payload["state"] in TERMINAL_STATES or time.monotonic() >= deadline:
            return payload
        await asyncio.sleep(1.0)
        instance = await _get_instance(db, job_id, refresh=True)


def _serialize_result(row: TaskResult) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "authors": row.authors,
        "organ": row.organ,
        "source_journal": row.source_journal,
        "first_duty": row.first_duty,
        "keywords": row.keywords,
        "abstract": row.abstract,
        "publish_time": row.publish_time,
        "fund": row.fund,
        "publish_year": row.publish_year,
        "volume": row.volume,
        "issue": row.issue,
        "pages": row.pages,
        "clc": row.clc,
        "issn": row.issn,
        "original_url": row.original_url,
        "doi": row.doi,
        "reference_format": row.reference_format,
        "is_duplicate": row.is_duplicate,
    }


@router.get("/metadata-jobs/{job_id}/results")
async def get_metadata_job_results(
    job_id: int,
    request: Request,
    format: Literal["json", "excel"] = Query("json"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    inline: bool = Query(False, description="format=excel 时是否直接内联返回文件（受体积上限约束）"),
    client: ApiKey = Depends(get_api_client),
    db: AsyncSession = Depends(get_db),
):
    instance = await _get_instance(db, job_id)
    if instance.status not in RESULT_READY_STATES:
        raise ValidationError(f"作业尚未产出结果，当前状态：{instance.status}")

    if format == "excel":
        return _excel_payload(instance, request, inline)

    total = (
        await db.execute(select(func.count(TaskResult.id)).where(TaskResult.task_instance_id == job_id))
    ).scalar() or 0
    rows = (
        await db.execute(
            select(TaskResult)
            .where(TaskResult.task_instance_id == job_id)
            .order_by(TaskResult.id)
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    next_offset = offset + len(rows)
    return {
        "job_id": instance.id,
        "job_no": instance.instance_no,
        "count": len(rows),
        "total": total,
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset if next_offset < total else None,
        "records": [_serialize_result(r) for r in rows],
    }


def _excel_payload(instance: TaskInstance, request: Request, inline: bool):
    path = instance.search_result_file_path
    if not path or not os.path.isfile(path):
        raise NotFoundError("元数据 Excel 文件", instance.instance_no)
    filename = f"cnki_metadata_{instance.instance_no}.xlsx"
    size = os.path.getsize(path)
    if inline:
        if size > API_MAX_INLINE_BYTES:
            raise AppError(
                f"Excel 文件 {size} 字节超过内联上限 {API_MAX_INLINE_BYTES}，请改用 download_url 下载",
                code="PAYLOAD_TOO_LARGE",
                status_code=413,
            )
        return FileResponse(path, filename=filename, media_type=EXCEL_MEDIA_TYPE)

    token = create_artifact_token(instance.id, API_ARTIFACT_TOKEN_TTL_MIN)
    base = str(request.base_url).rstrip("/")
    return {
        "job_id": instance.id,
        "job_no": instance.instance_no,
        "filename": filename,
        "size_bytes": size,
        "content_type": EXCEL_MEDIA_TYPE,
        "download_url": f"{base}/api/v1/open/metadata-jobs/{instance.id}/artifact?token={token}",
        "expires_at": (timezone.now() + timedelta(minutes=API_ARTIFACT_TOKEN_TTL_MIN)).isoformat(),
    }


@router.get("/metadata-jobs/{job_id}/artifact")
async def download_metadata_artifact(
    job_id: int,
    token: Optional[str] = Query(None, description="短期签名令牌，可脱离 API Key 使用"),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    if token:
        decode_artifact_token(token, job_id)
    else:
        await verify_api_key_header(authorization, db)

    instance = await _get_instance(db, job_id)
    path = instance.search_result_file_path
    if not path or not os.path.isfile(path):
        raise NotFoundError("元数据 Excel 文件", instance.instance_no)
    return FileResponse(
        path,
        filename=f"cnki_metadata_{instance.instance_no}.xlsx",
        media_type=EXCEL_MEDIA_TYPE,
    )
