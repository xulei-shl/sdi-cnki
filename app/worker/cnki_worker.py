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
from app.database import async_session_factory
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

logger = get_logger("cnki_worker")
settings = get_settings()

# Maximum valid data count to auto-trigger LLM analysis (0 = always trigger)
MAX_AUTO_LLM_TRIGGER = 2000

# 心跳间隔：与浏览器步骤解耦，让调用方能区分“步骤耗时”与“进程卡死”
HEARTBEAT_INTERVAL_SEC = 5

# 检索专用单线程 executor：与默认线程池（PDF 下载的 to_thread）隔离，
# 避免 Playwright sync dispatcher loop 泄漏后跨任务污染（详见 20260929 changelog）。
_search_executor = __import__("concurrent.futures", fromlist=["ThreadPoolExecutor"]).ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="cnki-search",
)

STAGE_MESSAGES: dict[str, str] = {
    "launching": "正在启动浏览器",
    "navigating": "正在打开检索页面",
    "authenticating": "正在校验登录状态",
    "searching": "正在填写检索条件",
    "submitting": "正在提交检索",
    "waiting_results": "已提交检索，正在等待结果页返回",
    "collecting": "正在读取检索结果数量",
    "exporting": "正在分批导出元数据",
    "merging": "正在合并导出批次",
    "parsing": "正在解析元数据并入库",
    "done": "检索完成",
}


async def _save_progress(instance_id: int, stage: str, extra: dict | None = None) -> None:
    """把检索阶段写入任务实例，供开放接口轮询（跨进程可见）。"""
    extra = extra or {}
    try:
        async with async_session_factory() as db:
            await db.execute(
                update(TaskInstance)
                .where(TaskInstance.id == instance_id)
                .values(
                    progress_stage=stage,
                    progress_message=STAGE_MESSAGES.get(stage, stage),
                    progress_current=extra.get("current"),
                    progress_total=extra.get("total"),
                    heartbeat_at=timezone.now(),
                )
            )
            await db.commit()
    except Exception as e:
        # 进度上报属于可观测性，失败不能影响检索本身
        logger.warning(f"progress update failed (instance={instance_id}, stage={stage}): {e}")


async def _touch_heartbeat(instance_id: int) -> None:
    try:
        async with async_session_factory() as db:
            await db.execute(
                update(TaskInstance)
                .where(TaskInstance.id == instance_id)
                .values(heartbeat_at=timezone.now())
            )
            await db.commit()
    except Exception as e:
        logger.warning(f"heartbeat update failed (instance={instance_id}): {e}")


async def _heartbeat_loop(instance_id: int, stop: asyncio.Event) -> None:
    """独立心跳：即使某个浏览器步骤长时间不推进，心跳也在走。"""
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_INTERVAL_SEC)
        except asyncio.TimeoutError:
            await _touch_heartbeat(instance_id)


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
        heartbeat_stop = asyncio.Event()

        def _on_stage(stage: str, extra: dict) -> None:
            # 从浏览器线程回到事件循环写进度
            asyncio.run_coroutine_threadsafe(_save_progress(instance_id, stage, extra), loop)

        heartbeat_task = asyncio.create_task(_heartbeat_loop(instance_id, heartbeat_stop))
        try:
            # 必须用专用单线程 executor，不能与默认池共享：
            # PDF 下载（asyncio.to_thread）在同一线程泄漏 Playwright sync 的 dispatcher
            # event loop 后，默认池线程被复用会导致本检索报
            # "Playwright Sync API inside the asyncio loop"（见 docs/changelog/20260929）。
            # 专用单线程同时天然保证同进程内检索串行。
            global _search_executor
            search_result = await loop.run_in_executor(
                _search_executor,
                _run_search_sync,
                search_params,
                instance_no,
                settings.uploads_dir,
                _on_stage,
            )

            await process_search_results(db, instance, search_result)
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)

        await svc.complete(item_id, json.dumps({"status": "completed", "total": instance.search_result_count}))

        if is_api or instance.valid_data_count:
            await _save_progress(instance_id, "done")

        if is_api:
            instance.status = "completed"
            instance.completed_at = timezone.now()
            await db.commit()
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
