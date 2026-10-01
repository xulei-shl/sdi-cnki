"""JEV 相关性评分 worker：给已入库的文献打相关性分。

核心契约（开放接口依赖）：**本 worker 无论成功失败，实例都必须落到终态
`completed`**。CNKI 检索此时已经成功、文献已入库，若因评分失败把作业打成
`failed`，等于销毁一次成功的检索结果——调用方既拿不到文献，也拿不到分数。

因此：
- 未配置 JEV      → relevance_status='unavailable'，作业照常 succeeded；
- 单条答案非法    → 该条 status='failed'、score 为 NULL，其余继续；
- 整批请求失败    → 该批全部 failed，其余批继续；
- 全部批次失败    → relevance_status='failed'，作业仍 succeeded。

失败只体现在 `relevance_status` / `counts.relevance.failed` 上，不影响文献交付。
"""

from __future__ import annotations

import asyncio
import json
import time

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jev_score import JevScore
from app.models.task_instance import TaskInstance
from app.models.task_result import TaskResult
from app.services.jev_provider import (
    JevNotConfiguredError,
    build_candidate_text,
    build_jev_request,
    call_jev_api,
    parse_jev_answers,
    resolve_jev_config,
)
from app.services.search_topic import format_search_conditions
from app.task_queue.crud import TaskQueueService
from app.utils import timezone
from app.utils.logging import get_logger
from app.worker.progress import save_progress, with_heartbeat

logger = get_logger("jev_worker")

# 单次请求送多少条候选。官方建议一次可并行评估多个问题，批量越大请求数越少，
# 但单次 state 也会变长；20 是官方精排示例的取值。
JEV_BATCH_SIZE = 20
# 批与批之间的并发数。JEV 有速率限制（429/529），这里保守取 3。
JEV_BATCH_CONCURRENCY = 3


def resolve_topic(exec_params: dict) -> str:
    """定题描述：调用方显式传入优先，否则由检索条件派生。

    与 LLM 分析走同一个 `format_search_conditions`，保证两条判定链路看到的
    是同一份定题描述。
    """
    relevance = exec_params.get("relevance") or {}
    topic = (relevance.get("topic") or "").strip()
    if topic:
        return topic
    return format_search_conditions(exec_params.get("search_params"))


def chunked(items: list, size: int) -> list[list]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def _score_batch(
    topic: str,
    batch: list[dict],
    config,
) -> dict:
    """对一批候选打分，纯 HTTP，不碰 DB，可并发执行。

    返回 {scores, has_match, error, latency_ms, raw_response}。
    """
    started = time.monotonic()
    result = {"has_match": None, "raw_response": None}
    try:
        body = build_jev_request(topic, batch, config.model)
        response = await call_jev_api(body, config)
        scores, has_match = parse_jev_answers(response.get("answers"), batch)
        result["scores"] = scores
        result["has_match"] = has_match
        result["raw_response"] = response
    except Exception as e:
        message = str(e)[:300]
        logger.warning(f"JEV 批次打分失败（{len(batch)} 条）: {message}")
        result["scores"] = []
        result["error"] = message
    result["latency_ms"] = (time.monotonic() - started) * 1000
    return result


async def _persist_scores(
    db: AsyncSession,
    instance_id: int,
    batch: list[dict],
    scores: list[dict],
    latency_ms: float,
    raw_response: dict | None,
) -> None:
    """写入一批评分结果（delete-then-insert，重跑幂等）。"""
    by_result_id = {s["task_result_id"]: s for s in scores}
    for item in batch:
        result_id = item["task_result_id"]
        await db.execute(delete(JevScore).where(JevScore.task_result_id == result_id))
        score = by_result_id.get(result_id)
        db.add(
            JevScore(
                task_result_id=result_id,
                task_instance_id=instance_id,
                status="completed" if score else "failed",
                relevance_score=score["relevance_score"] if score else None,
                relevance_level=score["relevance_level"] if score else None,
                noul_prob=score["noul_prob"] if score else None,
                level_confidence=score["level_confidence"] if score else None,
                latency_ms=int(latency_ms),
                raw_response=json.dumps(raw_response, ensure_ascii=False) if raw_response else None,
                error_message=None if score else "JEV 未返回该条的有效答案",
                finished_at=timezone.now(),
            )
        )
    await db.commit()


async def _finalize(
    db: AsyncSession,
    svc: TaskQueueService,
    item_id: int,
    instance: TaskInstance,
    relevance_status: str,
    relevance_error: str | None,
) -> None:
    """收尾：统计、置终态、完成队列行。**任何分支都必须走到实例终态。**"""
    rows = (
        await db.execute(
            select(JevScore.status, JevScore.relevance_score).where(
                JevScore.task_instance_id == instance.id
            )
        )
    ).all()
    scored = sum(1 for status, score in rows if status == "completed" and score is not None)
    failed = sum(1 for status, _ in rows if status != "completed")

    instance.relevance_status = relevance_status
    instance.relevance_error = relevance_error
    instance.status = "completed"
    instance.completed_at = timezone.now()
    await db.commit()

    await svc.complete(
        item_id,
        json.dumps(
            {"scored": scored, "failed": failed, "relevance_status": relevance_status},
            ensure_ascii=False,
        ),
    )
    await save_progress(instance.id, "done")
    logger.info(
        f"Instance {instance.instance_no}: relevance {relevance_status}, "
        f"scored={scored}, failed={failed}"
    )


async def run_jev_scoring(
    db: AsyncSession,
    item_id: int,
    params_json: str,
) -> None:
    """主入口。"""
    svc = TaskQueueService(db)
    params = json.loads(params_json)
    instance_id = params.get("instance_id")

    instance = (
        await db.execute(select(TaskInstance).where(TaskInstance.id == instance_id))
    ).scalar_one_or_none()
    if not instance:
        await svc.fail(item_id, f"Instance {instance_id} not found")
        return

    try:
        exec_params = (
            json.loads(instance.execution_params)
            if isinstance(instance.execution_params, str)
            else (instance.execution_params or {})
        )

        # 未配置不是错误：文献照常交付，只是没有分数
        try:
            config = await resolve_jev_config(db)
        except JevNotConfiguredError as e:
            logger.warning(f"Instance {instance.instance_no}: {e}")
            await _finalize(db, svc, item_id, instance, "unavailable", str(e))
            return

        stmt = select(TaskResult).where(
            TaskResult.task_instance_id == instance_id,
            TaskResult.is_duplicate == False,
        )
        records = list((await db.execute(stmt)).scalars().all())
        if not records:
            await _finalize(db, svc, item_id, instance, "completed", None)
            return

        topic = resolve_topic(exec_params)
        items = [
            {
                "task_result_id": r.id,
                "text": build_candidate_text(r.title, r.keywords, r.abstract),
            }
            for r in records
        ]

        instance.relevance_status = "running"
        instance.relevance_error = None
        await db.commit()

        async def _run_batches() -> None:
            batches = chunked(items, JEV_BATCH_SIZE)
            completed_batches = 0
            any_ok = False
            err: str | None = None

            # 按「波次」推进：波内并发发 HTTP，波间串行写库。
            # 直接 gather 全部批次会让长尾批次阻塞进度上报；而让每批自己写库则
            # 会并发写同一个 AsyncSession，触发 lessons.md 记录的
            # "This session is provisioning a new connection" 故障。
            for wave in chunked(batches, JEV_BATCH_CONCURRENCY):
                results = await asyncio.gather(
                    *(_score_batch(topic, batch, config) for batch in wave)
                )
                for batch, result in zip(wave, results):
                    await _persist_scores(
                        db,
                        instance_id,
                        batch,
                        result["scores"],
                        result["latency_ms"],
                        result["raw_response"],
                    )
                    if result["scores"]:
                        any_ok = True
                    else:
                        err = result.get("error") or err
                    completed_batches += 1
                await save_progress(
                    instance.id,
                    "scoring",
                    {"current": completed_batches, "total": len(batches)},
                )

            return any_ok, err

        any_success, last_error = await with_heartbeat(instance.id, _run_batches())

        if not any_success:
            await _finalize(db, svc, item_id, instance, "failed", last_error or "JEV 全部批次失败")
            return

        # 部分批次失败时如实记为 partial，不静默当作全成功
        partial = last_error is not None
        await _finalize(
            db,
            svc,
            item_id,
            instance,
            "partial" if partial else "completed",
            last_error if partial else None,
        )

    except Exception as e:
        logger.error(f"JEV scoring failed for instance {instance_id}: {e}", exc_info=True)
        # 兜底：文献已入库，绝不能因评分异常让作业悬在 search_completed 或被打成 failed
        await _finalize(db, svc, item_id, instance, "failed", str(e)[:300])