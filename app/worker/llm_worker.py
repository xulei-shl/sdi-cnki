from __future__ import annotations

import asyncio
import json
from typing import Any

from app.utils import timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.llm_analysis_result import LlmAnalysisResult
from app.models.llm_config import LlmConfig
from app.models.prompt_template import PromptTemplate
from app.models.system_prompt import SystemPrompt
from app.models.task_instance import TaskInstance
from app.models.task_result import TaskResult
from app.services.json_parser import parse_llm_json
from app.services.llm_provider import call_llm_with_retry
from app.task_queue.crud import TaskQueueService
from app.utils.crypto import decrypt_api_key
from app.utils.logging import get_logger

logger = get_logger("llm_worker")
settings = get_settings()
BATCH_SIZE = 5


async def run_llm_analysis(
    db: AsyncSession,
    item_id: int,
    params_json: str,
) -> None:
    svc = TaskQueueService(db)
    params = json.loads(params_json)
    instance_id = params.get("instance_id")

    stmt = select(TaskInstance).where(TaskInstance.id == instance_id).options(
        selectinload(TaskInstance.meta_task), selectinload(TaskInstance.creator),
    )
    result = await db.execute(stmt)
    instance = result.unique().scalar_one_or_none()
    if not instance:
        await svc.fail(item_id, f"Instance {instance_id} not found")
        return

    instance.status = "analyzing"
    await db.commit()

    from app.routers.sse import broadcast_event
    await broadcast_event(instance_id, "task.progress", {"status": "analyzing", "analyzed": 0, "total": 0})

    try:
        retry_failed_only = params.get("retry_failed_only", False)

        exec_params = json.loads(instance.execution_params) if isinstance(instance.execution_params, str) else instance.execution_params
        llm_config_ids = exec_params.get("llm_config_ids", [])
        prompt_template_id = exec_params.get("prompt_template_id")

        db_configs = await _load_llm_configs(db, llm_config_ids)
        if not db_configs:
            raise Exception("No active LLM configs available")

        prompt_template = await _load_prompt_template(db, prompt_template_id, exec_params)

        stmt = select(TaskResult).where(
            TaskResult.task_instance_id == instance_id,
            TaskResult.is_duplicate == False,
        ).options(selectinload(TaskResult.llm_analysis))
        r = await db.execute(stmt)
        all_results = list(r.scalars().all())
        if retry_failed_only:
            task_results = [
                tr for tr in all_results
                if not tr.llm_analysis or tr.llm_analysis.status == "failed"
            ]
        else:
            task_results = all_results
        total = len(task_results)

        if total == 0:
            await _finish_with_no_data(db, instance, svc, item_id, instance_id)
            return

        analyzed = 0
        failed = 0

        for i in range(0, total, BATCH_SIZE):
            batch = task_results[i:i + BATCH_SIZE]
            coros = [_call_llm(tr, db_configs, prompt_template) for tr in batch]
            llm_results = await asyncio.gather(*coros)

            for tr, (success, err, data) in zip(batch, llm_results):
                await _write_analysis_result(db, tr, data, instance_id)
                if success:
                    analyzed += 1
                else:
                    failed += 1

            await db.commit()

            await broadcast_event(instance_id, "task.progress", {
                "status": "analyzing",
                "analyzed": analyzed,
                "total": total,
                "failed": failed,
            })
            logger.info(f"LLM progress: {analyzed}/{total} analyzed, {failed} failed")

        instance.status = "analyzing_completed"
        instance.analysis_completed_at = timezone.now()
        await db.commit()

        await svc.complete(item_id, json.dumps({"analyzed": analyzed, "failed": failed}))
        await broadcast_event(instance_id, "task.completed", {
            "status": "analyzing_completed",
            "analyzed": analyzed,
            "total": total,
            "failed": failed,
            "completed_at": timezone.now().isoformat(),
        })

        from app.services.notification import send_notification
        await send_notification(db, {
            "user_id": instance.creator.id if instance.creator else None,
            "instance_id": instance_id,
            "stage": "分析",
            "meta_task_name": instance.meta_task.name if instance.meta_task else "",
            "username": instance.creator.username if instance.creator else "",
            "instance_no": instance.instance_no,
            "status": "analyzing_completed",
            "started_at": instance.started_at.isoformat() if instance.started_at else "",
            "completed_at": timezone.now().isoformat(),
            "stats": {
                "total": instance.search_result_count or 0,
                "valid": instance.valid_data_count or 0,
                "duplicate": instance.duplicate_count or 0,
                "analyzed": analyzed,
                "downloaded": 0,
            },
        }, module_key="分析")
        logger.info(f"LLM analysis completed for instance {instance.instance_no}: {analyzed} ok, {failed} failed")

    except Exception as e:
        logger.error(f"LLM analysis failed: {e}", exc_info=True)
        instance.status = "failed"
        instance.error_message = str(e)[:500]
        await db.commit()
        await svc.fail(item_id, str(e)[:500])
        await broadcast_event(instance_id, "task.failed", {
            "status": "failed",
            "error_message": str(e)[:500],
        })
        from app.services.notification import send_notification
        await send_notification(db, {
            "user_id": instance.creator.id if instance.creator else None,
            "instance_id": instance_id,
            "stage": "分析",
            "meta_task_name": instance.meta_task.name if instance.meta_task else "",
            "username": instance.creator.username if instance.creator else "",
            "instance_no": instance.instance_no,
            "status": "failed",
            "error_message": str(e)[:500],
            "started_at": instance.started_at.isoformat() if instance.started_at else "",
            "completed_at": timezone.now().isoformat(),
            "stats": {},
        }, module_key="分析")


async def _load_llm_configs(db: AsyncSession, config_ids: list[int]) -> list[dict[str, Any]]:
    if not config_ids:
        return []
    configs = []
    for cfg_id in config_ids:
        stmt = select(LlmConfig).where(LlmConfig.id == cfg_id, LlmConfig.is_active == True)
        r = await db.execute(stmt)
        cfg = r.scalar_one_or_none()
        if cfg:
            api_key = decrypt_api_key(cfg.api_key_encrypted, settings.aes_encryption_key)
            configs.append({
                "id": cfg.id,
                "api_key": api_key,
                "api_endpoint": cfg.api_endpoint,
                "model_name": cfg.model_name,
            })
    return configs


async def _load_prompt_template(
    db: AsyncSession,
    prompt_template_id: int | None,
    exec_params: dict | None = None,
) -> str | None:
    if prompt_template_id:
        stmt = select(SystemPrompt).where(SystemPrompt.id == prompt_template_id, SystemPrompt.is_active == True)
        r = await db.execute(stmt)
        sp = r.scalar_one_or_none()
        return sp.content if sp else None

    stmt = select(PromptTemplate).where(
        PromptTemplate.prompt_type == "fallback_analysis",
        PromptTemplate.is_active == True,
    )
    r = await db.execute(stmt)
    fallback = r.scalar_one_or_none()
    if fallback:
        search_conditions = _format_search_conditions(exec_params or {})
        if "{{search_conditions}}" in fallback.content:
            return fallback.content.replace("{{search_conditions}}", search_conditions)
        return fallback.content + "\n\n--- 本次检索条件 ---\n" + search_conditions

    return None


def _format_search_conditions(exec_params: dict) -> str:
    search_params = exec_params.get("search_params") or {}
    if isinstance(search_params, str):
        search_params = json.loads(search_params)

    parts = []
    search_mode = search_params.get("search_mode", "basic")

    if search_mode == "professional":
        group_a = search_params.get("query_group_a") or []
        group_b = search_params.get("query_group_b") or []
        if group_a and group_b:
            parts.append(f"主题A关键词组：{'、'.join(group_a)}")
            parts.append(f"主题B关键词组：{'、'.join(group_b)}")
        elif group_a:
            parts.append(f"主题关键词组：{'、'.join(group_a)}")
        elif group_b:
            parts.append(f"主题关键词组：{'、'.join(group_b)}")
        au = search_params.get("au_group") or []
        if au:
            parts.append(f"作者：{'、'.join(au)}")
        fu = search_params.get("fu_group") or []
        if fu:
            parts.append(f"基金：{'、'.join(fu)}")
    else:
        queries = search_params.get("queries") or []
        if queries:
            parts.append(f"检索关键词：{'、'.join(queries)}")

    year_from = search_params.get("year_from")
    year_to = search_params.get("year_to")
    if year_from and year_to:
        parts.append(f"出版年份：{year_from}—{year_to}")
    elif year_from:
        parts.append(f"出版年份：{year_from}年起")
    elif year_to:
        parts.append(f"出版年份：{year_to}年止")

    date_range = search_params.get("date_range")
    if date_range:
        range_labels = {
            "week": "最近一周", "month": "最近一个月",
            "half-year": "最近半年", "year": "最近一年",
            "ytd": "今年以来", "last-year": "去年全年",
        }
        parts.append(f"更新时间：{range_labels.get(date_range, date_range)}")

    if search_params.get("core_only"):
        parts.append("来源范围：仅核心期刊")

    if not parts:
        return "未指定检索条件"

    return "\n".join(parts)


def _build_messages(prompt_template: str | None, tr: TaskResult) -> list[dict[str, str]]:
    title = tr.title or ""
    keywords = tr.keywords or ""
    abstract = tr.abstract or ""

    if not prompt_template:
        logger.warning("无可用提示词模板，使用最小兜底提示词")
        prompt_template = "请评估以下学术文献与用户定题的相关性，并以 JSON 格式输出评分。"

    parts = [prompt_template]
    parts.extend([
        "\n\n--- 文献信息 ---",
        f"\n【题名】{title}" if title else "\n【题名】无",
        f"\n【关键词】{keywords}" if keywords else "\n【关键词】无",
        f"\n【摘要】{abstract}" if abstract else "\n【摘要】无",
    ])
    return [{"role": "user", "content": "".join(parts)}]


async def _call_llm(
    tr: TaskResult,
    configs: list[dict[str, Any]],
    prompt_template: str | None,
) -> tuple[bool, str, dict]:
    """Call LLM for a single task result. No DB operations — safe to run concurrently.
    Returns (success, error_message, analysis_data_dict)."""
    try:
        messages = _build_messages(prompt_template, tr)
        raw_response, used_config_id, model_name = await call_llm_with_retry(configs, messages)

        try:
            parsed = parse_llm_json(raw_response)
            parsed_result_str = json.dumps(parsed, ensure_ascii=False)
            return True, "", {
                "task_result_id": tr.id,
                "status": "completed",
                "raw_response": raw_response,
                "parsed_result": parsed_result_str,
                "llm_config_id": used_config_id,
            }
        except ValueError as e:
            return False, str(e)[:500], {
                "task_result_id": tr.id,
                "status": "failed",
                "raw_response": raw_response,
                "error_message": str(e)[:500],
                "llm_config_id": used_config_id,
            }
    except Exception as e:
        return False, str(e)[:500], {
            "task_result_id": tr.id,
            "status": "failed",
            "raw_response": "",
            "error_message": str(e)[:500],
        }


async def _write_analysis_result(
    db: AsyncSession,
    tr: TaskResult,
    data: dict,
    instance_id: int,
) -> None:
    """Write one analysis result to DB. Must NOT be called concurrently on the same session."""
    await db.execute(
        delete(LlmAnalysisResult).where(LlmAnalysisResult.task_result_id == tr.id)
    )
    analysis = LlmAnalysisResult(
        task_result_id=tr.id,
        task_instance_id=instance_id,
        status=data["status"],
        raw_response=data.get("raw_response", ""),
        parsed_result=data.get("parsed_result"),
        error_message=data.get("error_message"),
        llm_config_id=data.get("llm_config_id"),
        attempt_count=1,
        finished_at=timezone.now(),
    )
    db.add(analysis)


async def _finish_with_no_data(
    db: AsyncSession,
    instance: TaskInstance,
    svc: TaskQueueService,
    item_id: int,
    instance_id: int,
) -> None:
    instance.status = "analyzing_completed"
    instance.analysis_completed_at = timezone.now()
    await db.commit()

    await svc.complete(item_id, '{"analyzed": 0, "failed": 0}')

    from app.routers.sse import broadcast_event
    await broadcast_event(instance_id, "task.completed", {
        "status": "analyzing_completed",
        "analyzed": 0,
        "total": 0,
        "failed": 0,
        "completed_at": timezone.now().isoformat(),
    })
    logger.info(f"Instance {instance.instance_no}: no results to analyze")
