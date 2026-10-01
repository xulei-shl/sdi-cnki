"""CNKI search worker - runs sync Camoufox in thread pool, processes results async."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.utils import timezone
from typing import Any

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.meta_task import MetaTask
from app.models.task_instance import TaskInstance
from app.models.task_result import TaskResult
from app.services.cnki.browser import CnkiBrowser
from app.services.cnki.professional_interactor import ProfessionalCnkiInteractor
from app.services.cnki.exceptions import NoResultsError, CnkiSearchError
from app.services.excel_parser import parse_excel_to_records, CNKI_COLUMN_MAP
from app.services.dedup_service import batch_check_and_mark
from app.task_queue.crud import TaskQueueService
from app.utils.logging import get_logger
from app.worker.progress import save_progress as _save_progress, with_heartbeat as _with_heartbeat

logger = get_logger("cnki_worker")
settings = get_settings()

# Maximum valid data count to auto-trigger LLM analysis (0 = always trigger)
MAX_AUTO_LLM_TRIGGER = 2000

# JEV 相关性评分队列的作业超时：50~100 篇按批打分，批间串行等待上游推理
JEV_TIMEOUT_SEC = 1800

# 检索专用单线程 executor：与默认线程池（PDF 下载的 to_thread）隔离，
# 避免 Playwright sync dispatcher loop 泄漏后跨任务污染（详见 20260929 changelog）。
_search_executor = __import__("concurrent.futures", fromlist=["ThreadPoolExecutor"]).ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="cnki-search",
)


def _extract_queries(params: dict) -> list[str]:
    """Extract queries array from search_params with backward compat."""
    queries = params.get("queries")
    if queries and isinstance(queries, list):
        return [q.strip() for q in queries if q.strip()]
    single = params.get("query")
    if single and isinstance(single, str) and single.strip():
        return [single.strip()]
    return []


def build_professional_search_params(params: dict) -> dict | None:
    """Normalize any search params to a single professional (专业检索) execution.

    Basic mode merges all keywords into one expression as group A
    (SU=(k1 + k2 + ...) OR TKA=(k1 + k2 + ...)), executed in a single search so
    the export limit (max_export) is strictly respected. Returns None when there
    are no keywords (the search should be skipped). Professional-mode params are
    returned unchanged.
    """
    pro_params = dict(params)
    if pro_params.get("search_mode") == "professional":
        return pro_params

    queries = _extract_queries(pro_params)
    if not queries:
        return None
    pro_params["search_mode"] = "professional"
    pro_params["query_group_a"] = queries
    pro_params["query_group_b"] = []
    pro_params.pop("queries", None)
    pro_params.pop("query", None)
    return pro_params


def _run_search_sync(
    params: dict,
    instance_no: str,
    uploads_dir: str,
    on_stage=None,
) -> dict:
    """Run search in a single browser session.

    Both modes execute exactly ONE professional (专业检索) search so the export
    limit (max_export) is strictly respected:
      - professional mode: user-defined groups A/B (+ author/fund filters)
      - basic mode: all keywords are merged into one expression as group A,
        i.e. SU=(k1 + k2 + ...) OR TKA=(k1 + k2 + ...)
    """
    base_dir = Path(uploads_dir) / instance_no
    base_dir.mkdir(parents=True, exist_ok=True)

    pro_params = build_professional_search_params(params)
    if pro_params is None:
        return {"final_file": None, "total": 0, "exported": 0, "batches": [], "no_results": True}

    if on_stage:
        on_stage("launching", {})
    with CnkiBrowser(headless=True) as browser:
        browser.goto(CnkiBrowser.HOME_URL)
        interactor = ProfessionalCnkiInteractor(browser, base_dir, on_stage=on_stage)
        result = interactor.execute_search(pro_params)
    return result


async def process_search_results(
    db: AsyncSession,
    instance: TaskInstance,
    search_result: dict,
) -> None:
    """Parse Excel, dedup, insert into DB."""
    final_file = search_result.get("final_file")
    if not final_file or search_result.get("no_results"):
        instance.status = "search_completed"
        instance.search_result_count = 0
        instance.valid_data_count = 0
        instance.duplicate_count = 0
        instance.search_completed_at = timezone.now()
        instance.search_result_file_path = None
        await db.commit()
        logger.info(f"Instance {instance.instance_no}: no results")
        return

    await _save_progress(instance.id, "parsing")
    instance.search_result_file_path = final_file
    file_path = Path(final_file)
    if not file_path.exists():
        logger.error(f"Final file not found: {final_file}")
        instance.status = "failed"
        instance.error_message = f"Final file not found: {final_file}"
        await db.commit()
        return

    records = parse_excel_to_records(file_path)
    total = len(records)
    logger.info(f"Instance {instance.instance_no}: parsed {total} records from Excel")

    meta_task_id = instance.meta_task_id
    dedup_scope_ids = [link.dedup_meta_task_id for link in (instance.meta_task.dedup_scope_links or [])] if instance.meta_task else []
    marked_records, duplicate_count = await batch_check_and_mark(
        db, records, meta_task_id, instance.id,
        dedup_scope_meta_task_ids=dedup_scope_ids or None,
    )

    inserted = 0
    for rec in marked_records:
        task_result = TaskResult(
            task_instance_id=instance.id,
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
        inserted += 1

    instance.status = "search_completed"
    instance.search_result_count = total
    instance.valid_data_count = total - duplicate_count
    instance.duplicate_count = duplicate_count
    instance.search_completed_at = timezone.now()
    await db.commit()
    logger.info(
        f"Instance {instance.instance_no}: inserted {inserted}, "
        f"duplicates={duplicate_count}, valid={total - duplicate_count}"
    )


async def _dispatch_api_relevance(
    db: AsyncSession,
    svc: TaskQueueService,
    instance: TaskInstance,
    exec_params: dict,
) -> None:
    """检索完成后收尾 API 作业：按需入队 JEV 评分，否则直接置终态。

    关键语义：实例**不能**在这里置 completed。
    调用方（开放接口）的契约是「拿到终态即代表相关性判断已结束」，否则轮询会在
    JEV 仍在跑时提前看到 succeeded，拿到一批 relevance_score 全为 null 的记录。
    因此有相关性判断时把实例停在 search_completed（对外映射为 running），
    由 jev_worker 收尾时再置 completed；入队失败也必须落到终态，否则调用方永远轮询不到。
    """
    relevance = exec_params.get("relevance") or {}
    enabled = bool(relevance.get("enabled", True))
    has_data = bool(instance.valid_data_count)

    if not enabled or not has_data:
        instance.status = "completed"
        instance.completed_at = timezone.now()
        if enabled and not has_data:
            # 请求了判断但无文献可判：不是错误，如实记为「无待评内容」
            instance.relevance_status = "completed"
            instance.relevance_error = None
        await db.commit()
        return

    instance.relevance_status = "pending"
    try:
        await svc.enqueue(
            queue_type="jev",
            task_type="jev_scoring",
            params_json=json.dumps(
                {"instance_id": instance.id, "instance_no": instance.instance_no},
                ensure_ascii=False,
            ),
            task_key=f"jev_{instance.instance_no}",
            timeout_sec=JEV_TIMEOUT_SEC,
        )
    except Exception as e:
        # 入队失败不能让作业悬在 search_completed：CNKI 结果已拿到，直接收尾并如实标记
        logger.error(f"enqueue jev scoring failed for {instance.instance_no}: {e}", exc_info=True)
        instance.status = "completed"
        instance.completed_at = timezone.now()
        instance.relevance_status = "failed"
        instance.relevance_error = f"相关性评分任务入队失败：{str(e)[:300]}"
    await db.commit()


async def run_cnki_search(
    db: AsyncSession,
    item_id: int,
    params_json: str,
) -> None:
    """Main entry: run search sync, then process results async."""
    svc = TaskQueueService(db)
    params = json.loads(params_json)
    instance_id = params.get("instance_id")
    instance_no = params.get("instance_no")

    stmt = select(TaskInstance).where(TaskInstance.id == instance_id).options(
        selectinload(TaskInstance.meta_task).selectinload(MetaTask.dedup_scope_links),
        selectinload(TaskInstance.creator),
    )
    result = await db.execute(stmt)
    instance = result.unique().scalar_one_or_none()
    if not instance:
        await svc.fail(item_id, f"Instance {instance_id} not found")
        return

    instance.status = "running"
    instance.started_at = timezone.now()
    await db.commit()

    # 开放接口任务：只取元数据，不进入通知 / SSE / LLM / 下载链路
    is_api = (instance.source or "web") == "api"

    try:
        exec_params = json.loads(instance.execution_params) if isinstance(instance.execution_params, str) else instance.execution_params
        search_params = exec_params.get("search_params", {})

        loop = asyncio.get_running_loop()

        def _on_stage(stage: str, extra: dict) -> None:
            # 从浏览器线程回到事件循环写进度
            asyncio.run_coroutine_threadsafe(_save_progress(instance_id, stage, extra), loop)

        global _search_executor
        search_coro = loop.run_in_executor(
            _search_executor,
            _run_search_sync,
            search_params,
            instance_no,
            settings.uploads_dir,
            _on_stage,
        )
        search_result = await _with_heartbeat(instance_id, search_coro)

        await process_search_results(db, instance, search_result)

        await svc.complete(item_id, json.dumps({"status": "completed", "total": instance.search_result_count}))

        if is_api or instance.valid_data_count:
            await _save_progress(instance_id, "done")

        if is_api:
            await _dispatch_api_relevance(db, svc, instance, exec_params)
            return

        from app.routers.sse import broadcast_event
        await broadcast_event(
            instance_id,
            "task.progress",
            {
                "status": "search_completed",
                "total": instance.search_result_count,
                "valid": instance.valid_data_count,
                "duplicate": instance.duplicate_count,
            },
        )

        from app.services.notification import send_notification
        await send_notification(db, {
            "user_id": instance.creator.id if instance.creator else None,
            "instance_id": instance_id,
            "stage": "检索",
            "meta_task_name": instance.meta_task.name if instance.meta_task else "",
            "username": instance.creator.username if instance.creator else "",
            "instance_no": instance.instance_no,
            "status": "search_completed",
            "started_at": instance.started_at.isoformat() if instance.started_at else "",
            "completed_at": timezone.now().isoformat(),
            "stats": {
                "total": instance.search_result_count or 0,
                "valid": instance.valid_data_count or 0,
                "duplicate": instance.duplicate_count or 0,
                "analyzed": 0,
                "downloaded": 0,
            },
        }, module_key="检索")

        # Auto-complete when no valid data (all duplicates / empty result)
        if not instance.valid_data_count:
            instance.status = "completed"
            instance.completed_at = timezone.now()
            await db.commit()
            await broadcast_event(instance_id, "task.completed", {
                "status": "completed",
                "completed_at": timezone.now().isoformat(),
            })
            return

        if instance.valid_data_count and instance.valid_data_count > 0 and instance.valid_data_count <= MAX_AUTO_LLM_TRIGGER:
            await svc.enqueue(
                queue_type="llm",
                task_type="llm_analysis",
                params_json=json.dumps({"instance_id": instance_id, "instance_no": instance.instance_no}),
                task_key=f"llm_{instance.instance_no}",
                timeout_sec=3600,
                replace=True,
            )
            logger.info(f"Auto-enqueued LLM analysis for instance {instance.instance_no} ({instance.valid_data_count} articles)")
    except NoResultsError:
        instance.status = "completed"
        instance.search_result_count = 0
        instance.valid_data_count = 0
        instance.duplicate_count = 0
        instance.search_completed_at = timezone.now()
        instance.completed_at = timezone.now()
        await db.commit()
        await svc.complete(item_id, '{"status": "completed", "total": 0}')
        if is_api:
            return
        from app.routers.sse import broadcast_event
        await broadcast_event(instance_id, "task.progress", {
            "status": "completed",
            "total": 0,
            "valid": 0,
            "duplicate": 0,
        })
        await broadcast_event(instance_id, "task.completed", {
            "status": "completed",
            "completed_at": timezone.now().isoformat(),
        })
    except Exception as e:
        logger.error(f"CNKI search failed: {e}", exc_info=True)
        instance.status = "failed"
        instance.error_message = str(e)[:500]
        await db.commit()
        if is_api:
            await svc.fail(item_id, str(e)[:500])
            return
        from app.services.notification import send_notification
        await send_notification(db, {
            "user_id": instance.creator.id if instance.creator else None,
            "stage": "检索",
            "meta_task_name": instance.meta_task.name if instance.meta_task else "",
            "username": instance.creator.username if instance.creator else "",
            "instance_no": instance.instance_no,
            "status": "failed",
            "error_message": str(e)[:500],
            "started_at": instance.started_at.isoformat() if instance.started_at else "",
            "completed_at": timezone.now().isoformat(),
            "stats": {},
        }, module_key="检索")
        await svc.fail(item_id, str(e)[:500])
