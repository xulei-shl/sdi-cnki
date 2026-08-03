"""CNKI search worker - runs sync Camoufox in thread pool, processes results async."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.utils import timezone
from typing import Any

from sqlalchemy import select, func
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

logger = get_logger("cnki_worker")
settings = get_settings()

# Maximum valid data count to auto-trigger LLM analysis (0 = always trigger)
MAX_AUTO_LLM_TRIGGER = 2000


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

    with CnkiBrowser(headless=True) as browser:
        browser.goto(CnkiBrowser.HOME_URL)
        interactor = ProfessionalCnkiInteractor(browser, base_dir)
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

    try:
        exec_params = json.loads(instance.execution_params) if isinstance(instance.execution_params, str) else instance.execution_params
        search_params = exec_params.get("search_params", {})

        loop = asyncio.get_event_loop()
        search_result = await loop.run_in_executor(
            None,
            _run_search_sync,
            search_params,
            instance_no,
            settings.uploads_dir,
        )

        await process_search_results(db, instance, search_result)
        await svc.complete(item_id, json.dumps({"status": "completed", "total": instance.search_result_count}))

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
