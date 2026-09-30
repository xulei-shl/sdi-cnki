"""实例「审核/下载阶段结束」状态判定测试。

实例状态是**派生值**：是否已终态应由 task_results / download_results 的数据决定，
而不是由各 worker 写死常量。本文件钉死该不变量，防止历史事故重演——
对「审核通过部分已全部下载成功」的实例重跑分析，会把终态 `completed` 打回
`analyzing_completed`，使实例在页面上永久显示「审核中」。
"""
import sys; sys.path.insert(0, '.')

import json
import tempfile

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base
from app.models.download_result import DownloadResult
from app.models.llm_analysis_result import LlmAnalysisResult
from app.models.meta_task import MetaTask
from app.models.task_instance import TaskInstance
from app.models.task_queue import TaskQueueItem
from app.models.task_result import TaskResult
from app.models.user import User
from app.services.download_progress import resolve_review_status


@pytest_asyncio.fixture
async def env():
    tmp = tempfile.mkdtemp(prefix="review_status_test_")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp}/t.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as db:
        user = User(username="reviewer", password_hash="x", role="admin", is_active=True)
        db.add(user)
        await db.flush()
        task = MetaTask(name="测试模板", creator_id=user.id, search_params="{}")
        db.add(task)
        await db.commit()
        ids = {"user_id": user.id, "meta_task_id": task.id}

    yield {"factory": factory, "tmp": tmp, **ids}
    await engine.dispose()


async def _make_instance(
    db,
    env,
    *,
    instance_no: str,
    approved: int = 0,
    unreviewed: int = 0,
    downloaded: int = 0,
) -> int:
    """造一个实例：approved 条审核通过、unreviewed 条未审，其中 downloaded 条已下载成功。"""
    inst = TaskInstance(
        meta_task_id=env["meta_task_id"],
        creator_id=env["user_id"],
        instance_no=instance_no,
        status="analyzing_completed",
        auto_run=True,
        source="web",
        valid_data_count=approved + unreviewed,
        execution_params=json.dumps(
            {"search_params": {"query": "x"}, "prompt_template_id": None, "llm_config_ids": []}
        ),
    )
    db.add(inst)
    await db.flush()

    rows = []
    for i in range(approved + unreviewed):
        rows.append(
            TaskResult(
                task_instance_id=inst.id,
                title=f"文献{i}",
                is_duplicate=False,
                is_passed=True if i < approved else None,
            )
        )
    db.add_all(rows)
    await db.flush()

    for row in rows[:downloaded]:
        db.add(
            DownloadResult(
                task_result_id=row.id,
                task_instance_id=inst.id,
                download_status="completed",
                pdf_path=f"/tmp/{row.id}.pdf",
            )
        )
    await db.commit()
    return inst.id


@pytest.mark.asyncio
async def test_no_approved_records_stays_in_review(env):
    """没有任何审核通过记录 → 仍待人工审核。"""
    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-R1", approved=0, unreviewed=3)
        assert await resolve_review_status(db, iid) == "analyzing_completed"


@pytest.mark.asyncio
async def test_partial_download_stays_in_review(env):
    """审核通过的部分只下了一部分 → 仍需人工处理（正常路径不受影响）。"""
    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-R2", approved=5, downloaded=2)
        assert await resolve_review_status(db, iid) == "analyzing_completed"


@pytest.mark.asyncio
async def test_all_approved_downloaded_is_completed(env):
    """审核通过的全部已下载成功 → 已完成。"""
    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-R3", approved=5, downloaded=5)
        assert await resolve_review_status(db, iid) == "completed"


@pytest.mark.asyncio
async def test_retry_analysis_does_not_downgrade_completed(env, monkeypatch):
    """回归：对已完成实例重跑分析，结束后必须仍是 completed。

    历史事故（实例 T20260830002）：批量下载把实例置为 completed，随后用户点
    「重新分析」，llm_worker 结束时无条件写入 analyzing_completed，终态被打回
    「审核中」，页面永久显示未完成。
    """
    from app.routers.task_instances import retry_llm_analysis
    from app.worker import llm_worker

    async def _fake_configs(db, ids):
        return [object()]

    async def _fake_template(db, tid, exec_params):
        return object()

    # 本用例只关心状态流转，跳过 LLM 配置/提示词加载
    monkeypatch.setattr(llm_worker, "_load_llm_configs", _fake_configs)
    monkeypatch.setattr(llm_worker, "_load_prompt_template", _fake_template)

    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-R4", approved=7, downloaded=7)
        await db.execute(
            update(TaskInstance).where(TaskInstance.id == iid).values(status="completed")
        )
        # 每条记录都已有成功分析结果 → 重跑时无待分析记录，直接走收尾分支
        for tr_id in (
            await db.execute(select(TaskResult.id).where(TaskResult.task_instance_id == iid))
        ).scalars().all():
            db.add(
                LlmAnalysisResult(
                    task_result_id=tr_id, task_instance_id=iid, status="completed", attempt_count=1
                )
            )
        await db.commit()

        user = (await db.execute(select(User).where(User.id == env["user_id"]))).scalar_one()
        await retry_llm_analysis(instance_id=iid, current_user=user, db=db)

        item = (
            await db.execute(select(TaskQueueItem).where(TaskQueueItem.queue_type == "llm"))
        ).scalar_one()
        assert item.status == "pending"

        await llm_worker.run_llm_analysis(db, item.id, item.params_json)

        inst = (await db.execute(select(TaskInstance).where(TaskInstance.id == iid))).scalar_one()
        assert inst.status == "completed", "重跑分析不得把已完成实例打回审核中"
        assert inst.completed_at is not None
