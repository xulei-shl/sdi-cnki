"""实例「审核/下载阶段结束」状态判定测试。

实例状态是**派生值**：是否已终态应由 task_results / download_results 的数据决定，
而不是由各 worker 写死常量或各自实现。本文件钉死该不变量，防止两类历史异常重演：

1. 对「审核通过部分已全部下载成功」的实例重跑分析，把终态 `completed` 打回
   `analyzing_completed`，实例在页面上永久显示「审核中」；
2. 同一份数据（部分记录下载失败）在「批量刚跑完」被判 `completed`，
   在「重跑时无待下载记录」却被判 `analyzing_completed`——状态取决于用户点了几次下载。
"""
import sys; sys.path.insert(0, '.')

import json
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, update
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


async def _load_inst(db, instance_id) -> TaskInstance:
    return (
        await db.execute(select(TaskInstance).where(TaskInstance.id == instance_id))
    ).scalar_one()


async def _make_instance(
    db,
    env,
    *,
    instance_no: str,
    approved: int = 0,
    unreviewed: int = 0,
    downloaded: int = 0,
    failed: int = 0,
) -> int:
    """造一个实例：approved 条审核通过、unreviewed 条未审；

    其中前 downloaded 条已下载成功，紧随其后的 failed 条已标记下载失败。
    """
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

    for idx, row in enumerate(rows[: downloaded + failed]):
        status = "completed" if idx < downloaded else "failed"
        db.add(
            DownloadResult(
                task_result_id=row.id,
                task_instance_id=inst.id,
                download_status=status,
                pdf_path=f"/tmp/{row.id}.pdf" if status == "completed" else "",
            )
        )
    await db.commit()
    return inst.id


async def _enqueue_download(db, instance_id: int, instance_no: str) -> int:
    # 与真实调用一致（TaskQueueService.enqueue(replace=True)）：task_key 唯一，重触发先删旧行
    await db.execute(
        delete(TaskQueueItem).where(TaskQueueItem.task_key == f"download_{instance_no}")
    )
    item = TaskQueueItem(
        queue_type="download",
        task_type="pdf_download",
        task_key=f"download_{instance_no}",
        params_json=json.dumps({"instance_id": instance_id, "instance_no": instance_no}),
        status="pending",
    )
    db.add(item)
    await db.commit()
    return item.id


# ═══════════════════════════════════════════════════════════
#  resolve_review_status —— 唯一的终态判定入口
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_no_valid_data_is_completed(env):
    """无有效数据（全部重复）→ 无事可做，视为完成。"""
    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-R0", approved=0, unreviewed=0)
        assert await resolve_review_status(db, await _load_inst(db, iid)) == "completed"


@pytest.mark.asyncio
async def test_no_approved_records_stays_in_review(env):
    """有数据但没有任何审核通过记录 → 仍待人工审核。"""
    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-R1", approved=0, unreviewed=3)
        inst = await _load_inst(db, iid)
        assert await resolve_review_status(db, inst) == "analyzing_completed"


@pytest.mark.asyncio
async def test_all_approved_downloaded_is_completed(env):
    """审核通过的全部已下载成功 → 已完成。"""
    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-R3", approved=5, downloaded=5)
        inst = await _load_inst(db, iid)
        assert await resolve_review_status(db, inst) == "completed"


@pytest.mark.asyncio
async def test_partial_download_stays_in_review(env):
    """审核通过的部分只成功了一部分 → 仍需人工处理。"""
    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-R2", approved=5, downloaded=2)
        inst = await _load_inst(db, iid)
        assert await resolve_review_status(db, inst) == "analyzing_completed"


# ═══════════════════════════════════════════════════════════
#  download_worker —— 「无待下载记录」分支
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_download_no_records_all_downloaded_is_completed(env):
    from app.worker.download_worker import run_download

    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-D1", approved=3, downloaded=3)
        item_id = await _enqueue_download(db, iid, "T-D1")
        await run_download(db, item_id, json.dumps({"instance_id": iid, "instance_no": "T-D1"}))

        inst = await _load_inst(db, iid)
        assert inst.status == "completed"
        assert inst.completed_at is not None
        assert inst.error_message is None


@pytest.mark.asyncio
async def test_download_no_records_partial_failure_stays_in_review(env):
    """有失败记录 → 留在审核态并提示行级重试（与“批量刚跑完”同规则）。"""
    from app.worker.download_worker import run_download

    async with env["factory"]() as db:
        iid = await _make_instance(
            db, env, instance_no="T-D2", approved=3, downloaded=1, failed=2
        )
        item_id = await _enqueue_download(db, iid, "T-D2")
        await run_download(db, item_id, json.dumps({"instance_id": iid, "instance_no": "T-D2"}))

        inst = await _load_inst(db, iid)
        assert inst.status == "analyzing_completed"
        assert "均已标记下载失败" in inst.error_message


@pytest.mark.asyncio
async def test_download_no_records_none_approved_stays_in_review(env):
    from app.worker.download_worker import run_download

    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-D3", approved=0, unreviewed=3)
        item_id = await _enqueue_download(db, iid, "T-D3")
        await run_download(db, item_id, json.dumps({"instance_id": iid, "instance_no": "T-D3"}))

        inst = await _load_inst(db, iid)
        assert inst.status == "analyzing_completed"
        assert "请先在页面完成人工审核" in inst.error_message


@pytest.mark.asyncio
async def test_download_no_records_no_valid_data_is_completed(env):
    from app.worker.download_worker import run_download

    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-D4", approved=0, unreviewed=0)
        item_id = await _enqueue_download(db, iid, "T-D4")
        await run_download(db, item_id, json.dumps({"instance_id": iid, "instance_no": "T-D4"}))

        inst = await _load_inst(db, iid)
        assert inst.status == "completed"
        assert inst.completed_at is not None


# ═══════════════════════════════════════════════════════════
#  download_worker —— 批量刚跑完（含行为变更）
# ═══════════════════════════════════════════════════════════


def _stub_pdf_download(monkeypatch, worker, *, fail_titles: set[str] | None = None):
    """把真实 PDF 下载替换成写一个占位文件（失败项返回 None）。"""
    fail_titles = fail_titles or set()

    def _fake(*, article_title, output_dir):
        if article_title in fail_titles:
            return None
        path = Path(output_dir) / f"{article_title}.pdf"
        path.write_bytes(b"%PDF-fake")
        return str(path)

    monkeypatch.setattr(worker, "download_pdf", _fake)
    # 下载目录改到临时目录，避免污染仓库 data/
    monkeypatch.setattr(worker.settings, "data_dir", tempfile.mkdtemp(prefix="dl_out_"))


@pytest.mark.asyncio
async def test_download_all_success_is_completed(env, monkeypatch):
    from app.worker import download_worker

    _stub_pdf_download(monkeypatch, download_worker)

    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-D5", approved=2)
        item_id = await _enqueue_download(db, iid, "T-D5")
        await download_worker.run_download(
            db, item_id, json.dumps({"instance_id": iid, "instance_no": "T-D5"})
        )

        inst = await _load_inst(db, iid)
        assert inst.status == "completed"
        assert inst.error_message is None


@pytest.mark.asyncio
async def test_download_partial_failure_stays_in_review(env, monkeypatch):
    """行为变更：批量跑完但有失败时不再报「已完成」，与「重跑无记录」分支保持一致。"""
    from app.worker import download_worker

    _stub_pdf_download(monkeypatch, download_worker, fail_titles={"文献1"})

    async with env["factory"]() as db:
        iid = await _make_instance(db, env, instance_no="T-D6", approved=2)
        item_id = await _enqueue_download(db, iid, "T-D6")
        await download_worker.run_download(
            db, item_id, json.dumps({"instance_id": iid, "instance_no": "T-D6"})
        )

        inst = await _load_inst(db, iid)
        assert inst.status == "analyzing_completed", "有失败记录时不得报「已完成」"
        assert "部分记录下载失败" in inst.error_message

        # 同一份数据再次触发下载（无待下载记录）应得出同一状态，不因点击次数而漂移
        item_id2 = await _enqueue_download(db, iid, "T-D6")
        await download_worker.run_download(
            db, item_id2, json.dumps({"instance_id": iid, "instance_no": "T-D6"})
        )
        assert (await _load_inst(db, iid)).status == "analyzing_completed"


# ═══════════════════════════════════════════════════════════
#  llm_worker —— 重跑分析不得覆盖终态
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_retry_analysis_does_not_downgrade_completed(env, monkeypatch):
    """回归：对已完成实例重跑分析，结束后必须仍是 completed。

    历史事故（实例 T20260830002）：批量下载把实例置为 completed，随后用户点
    「重新分析」，llm_worker 结束时写死 analyzing_completed，终态被打回「审核中」。
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

        inst = await _load_inst(db, iid)
        assert inst.status == "completed", "重跑分析不得把已完成实例打回审核中"
        assert inst.completed_at is not None
