"""开放接口 v1 测试：提交 / 状态 / 结果 / 网页隔离。

用独立的临时 SQLite 库直接调用路由函数（不经 HTTP），因此不需要 CNKI 账号或浏览器。
"""
import sys; sys.path.insert(0, '.')

import json
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.dependencies import create_artifact_token, decode_artifact_token
from app.models import Base
from app.models.api_key import ApiKey
from app.models.task_instance import TaskInstance
from app.models.task_queue import TaskQueueItem
from app.models.task_result import TaskResult
from app.models.user import User
from app.utils import timezone
from app.utils.api_key import generate_api_key, verify_api_key
from app.utils.exceptions import AuthenticationError, NotFoundError, ValidationError


class _FakeRequest:
    """仅用于 _excel_payload 拼接绝对下载地址。"""

    base_url = "http://testserver/"


@pytest_asyncio.fixture
async def env():
    tmp = tempfile.mkdtemp(prefix="openapi_v1_test_")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp}/t.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    raw, prefix, key_hash = generate_api_key()
    async with factory() as db:
        admin = User(username="admin", password_hash="x", role="admin", is_active=True)
        db.add(admin)
        key = ApiKey(name="agent-1", key_prefix=prefix, key_hash=key_hash)
        db.add(key)
        await db.commit()
        await db.refresh(admin)
        await db.refresh(key)
        ids = {"admin_id": admin.id, "key_id": key.id}

    yield {"factory": factory, "raw_key": raw, "tmp": tmp, **ids}
    await engine.dispose()


async def _load_actors(db, env):
    admin = (await db.execute(select(User).where(User.id == env["admin_id"]))).scalar_one()
    key = (await db.execute(select(ApiKey).where(ApiKey.id == env["key_id"]))).scalar_one()
    return admin, key


# ═══════════════════════════════════════════════════════════
#  纯函数
# ═══════════════════════════════════════════════════════════


def test_api_key_roundtrip():
    raw, prefix, key_hash = generate_api_key()
    assert raw.startswith("sk-")
    assert len(prefix) == 12
    assert raw.startswith(prefix)
    assert verify_api_key(raw, key_hash)
    assert not verify_api_key(raw + "tampered", key_hash)
    assert not verify_api_key(raw, "not-a-bcrypt-hash")


def test_artifact_token_binds_job():
    token = create_artifact_token(7, 30)
    decode_artifact_token(token, 7)
    with pytest.raises(AuthenticationError):
        decode_artifact_token(token, 8)
    with pytest.raises(AuthenticationError):
        decode_artifact_token("garbage", 7)


def test_request_defaults_and_max_export_limit():
    from app.routers.openapi_v1 import MetadataJobRequest, _build_search_params

    params = _build_search_params(MetadataJobRequest(query="人工智能"))
    assert params["max_export"] == 50
    assert params["queries"] == ["人工智能"]

    assert MetadataJobRequest(query="x", max_export=100).max_export == 100
    with pytest.raises(PydanticValidationError):
        MetadataJobRequest(query="x", max_export=200)
    with pytest.raises(PydanticValidationError):
        MetadataJobRequest(query="x", max_export=10)

    with pytest.raises(ValidationError):
        _build_search_params(MetadataJobRequest())


def test_search_params_validation_is_reused():
    from app.routers.openapi_v1 import MetadataJobRequest, _build_search_params

    pro = _build_search_params(
        MetadataJobRequest(search_mode="professional", query_group_a=[" 阅读推广 ", ""], query_group_b=["AI"])
    )
    assert pro["query_group_a"] == ["阅读推广"]
    assert pro["query_group_b"] == ["AI"]


# ═══════════════════════════════════════════════════════════
#  提交 / 状态 / 结果
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_submit_creates_queued_api_job(env):
    from app.routers.openapi_v1 import API_QUEUE_PRIORITY, MetadataJobRequest, create_metadata_job

    async with env["factory"]() as db:
        _, key = await _load_actors(db, env)
        payload = await create_metadata_job(
            MetadataJobRequest(query="人工智能", max_export=100), client=key, db=db
        )

    assert payload["state"] == "queued"
    assert payload["stage"] is None
    assert payload["next_poll_after_ms"] == 5000
    assert payload["result_ready"] is False
    assert payload["queue_position"] >= 0

    async with env["factory"]() as db:
        instance = (
            await db.execute(select(TaskInstance).where(TaskInstance.id == payload["job_id"]))
        ).scalar_one()
        assert instance.source == "api"
        assert instance.status == "search_queued"
        assert json.loads(instance.execution_params)["search_params"]["max_export"] == 100

        item = (
            await db.execute(select(TaskQueueItem).where(TaskQueueItem.queue_type == "cnki"))
        ).scalar_one()
        assert item.priority == API_QUEUE_PRIORITY
        assert item.priority < 0, "API 任务优先级数值必须小于网页任务的 0，API 才优先出队"
        assert json.loads(item.params_json)["instance_id"] == payload["job_id"]


@pytest.mark.asyncio
async def test_idempotency_key_returns_same_job(env):
    from app.routers.openapi_v1 import MetadataJobRequest, create_metadata_job

    async with env["factory"]() as db:
        _, key = await _load_actors(db, env)
        first = await create_metadata_job(
            MetadataJobRequest(query="AI", idempotency_key="agent-run-1"), client=key, db=db
        )
        second = await create_metadata_job(
            MetadataJobRequest(query="AI", idempotency_key="agent-run-1"), client=key, db=db
        )
        queued = (await db.execute(select(func.count(TaskQueueItem.id)))).scalar()

    assert first["job_id"] == second["job_id"]
    assert second["deduplicated"] is True
    assert queued == 1


@pytest.mark.asyncio
async def test_status_reports_stage_heartbeat_and_results(env):
    from app.routers.openapi_v1 import (
        MetadataJobRequest,
        create_metadata_job,
        get_metadata_job,
        get_metadata_job_results,
    )

    async with env["factory"]() as db:
        _, key = await _load_actors(db, env)
        job_id = (await create_metadata_job(MetadataJobRequest(query="AI"), client=key, db=db))["job_id"]

        # 结果未产出前取结果应报未完成
        with pytest.raises(ValidationError):
            await get_metadata_job_results(
                job_id, _FakeRequest(), format="json", limit=50, offset=0, inline=False, client=key, db=db
            )

        # 模拟检索完成：进度 + 心跳 + 元数据落库 + 导出文件落盘
        xlsx = Path(env["tmp"]) / "merged.xlsx"
        xlsx.write_bytes(b"fake-xlsx-bytes")
        await db.execute(
            update(TaskInstance)
            .where(TaskInstance.id == job_id)
            .values(
                status="completed",
                search_result_file_path=str(xlsx),
                search_result_count=1,
                valid_data_count=1,
                duplicate_count=0,
                progress_stage="done",
                progress_message="检索完成",
                progress_current=1,
                progress_total=1,
                heartbeat_at=timezone.now(),
            )
        )
        db.add(TaskResult(task_instance_id=job_id, title="测试文献", authors="张三", doi="10.1/x"))
        await db.commit()

        status = await get_metadata_job(job_id, wait=0, client=key, db=db)
        assert status["state"] == "succeeded"
        assert status["stage"] == "done"
        assert status["stage_message"] == "检索完成"
        assert status["result_ready"] is True
        assert status["next_poll_after_ms"] == 0
        assert status["counts"] == {"total": 1, "valid": 1, "duplicate": 0}
        assert status["heartbeat_age_seconds"] is not None
        assert status["result_url"].endswith(f"/metadata-jobs/{job_id}/results")

        results = await get_metadata_job_results(
            job_id, _FakeRequest(), format="json", limit=50, offset=0, inline=False, client=key, db=db
        )
        assert results["total"] == 1
        assert results["next_offset"] is None
        assert results["records"][0]["title"] == "测试文献"

        excel = await get_metadata_job_results(
            job_id, _FakeRequest(), format="excel", limit=50, offset=0, inline=False, client=key, db=db
        )
        assert excel["size_bytes"] == len(b"fake-xlsx-bytes")
        assert "token=" in excel["download_url"]
        assert excel["download_url"].startswith("http://testserver/api/v1/open/")
        assert excel["expires_at"]

        with pytest.raises(NotFoundError):
            await get_metadata_job(999999, wait=0, client=key, db=db)


@pytest.mark.asyncio
async def test_artifact_token_scoped_to_job(env):
    from app.routers.openapi_v1 import (
        MetadataJobRequest,
        create_metadata_job,
        download_metadata_artifact,
    )

    async with env["factory"]() as db:
        _, key = await _load_actors(db, env)
        job_id = (await create_metadata_job(MetadataJobRequest(query="AI"), client=key, db=db))["job_id"]
        xlsx = Path(env["tmp"]) / "artifact.xlsx"
        xlsx.write_bytes(b"x")
        await db.execute(
            update(TaskInstance)
            .where(TaskInstance.id == job_id)
            .values(search_result_file_path=str(xlsx))
        )
        await db.commit()

        # 无 token 时必须带 API Key
        with pytest.raises(AuthenticationError):
            await download_metadata_artifact(job_id, token=None, authorization=None, db=db)

        good = create_artifact_token(job_id, 30)
        resp = await download_metadata_artifact(job_id, token=good, authorization=None, db=db)
        assert resp.path == str(xlsx)

        # 其他作业的 token 不能下载本作业文件
        with pytest.raises(AuthenticationError):
            await download_metadata_artifact(job_id, token=create_artifact_token(job_id + 1, 30), authorization=None, db=db)


@pytest.mark.asyncio
async def test_api_key_auth_rejects_unknown_key(env):
    from app.routers.openapi_v1 import verify_api_key_header

    async with env["factory"]() as db:
        with pytest.raises(AuthenticationError):
            await verify_api_key_header(None, db)
        with pytest.raises(AuthenticationError):
            await verify_api_key_header("Bearer sk-not-a-real-key", db)
        key = await verify_api_key_header(f"Bearer {env['raw_key']}", db)
        assert key.name == "agent-1"


# ═══════════════════════════════════════════════════════════
#  网页隔离
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_api_jobs_hidden_from_web_views(env):
    from app.routers.meta_tasks import list_meta_tasks
    from app.routers.openapi_v1 import MetadataJobRequest, create_metadata_job
    from app.routers.system_configs import get_stats
    from app.routers.task_instances import list_task_instances

    async with env["factory"]() as db:
        admin, key = await _load_actors(db, env)
        await create_metadata_job(MetadataJobRequest(query="AI"), client=key, db=db)
    async with env["factory"]() as db:
        admin, key = await _load_actors(db, env)

        instances = await list_task_instances(
            page=1, page_size=20, keyword=None, template_keyword=None,
            status_filter=None, current_user=admin, db=db,
        )
        assert instances["total"] == 0, "API 作业不得出现在网页实例列表"

        tasks = await list_meta_tasks(page=1, page_size=20, keyword=None, current_user=admin, db=db)
        assert tasks["total"] == 0, "API 内部模板不得出现在网页元任务列表"

        stats = await get_stats(current_user=admin, db=db)
        assert stats["task_instance_count"] == 0
        assert stats["meta_task_count"] == 0
        assert stats["running_instances"] == 0


@pytest.mark.asyncio
async def test_api_job_does_not_trigger_llm_or_notifications():
    """API 作业必须跳过自动 LLM 入队与通知：以源码断言固化该隔离约定。"""
    import inspect

    from app.worker import cnki_worker

    source = inspect.getsource(cnki_worker.run_cnki_search)
    assert 'is_api = (instance.source or "web") == "api"' in source
    assert "if is_api:" in source
    assert "if is_api or instance.valid_data_count:" in source
