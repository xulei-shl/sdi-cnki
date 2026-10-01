"""JEV 相关性评分测试：纯函数 + 作业链路降级路径。

用临时 SQLite + 直接调用路由/worker 函数（不经 HTTP、不连真实 JEV），
因此无需 CNKI 账号、浏览器与 TypeSafe 密钥。
"""
import sys; sys.path.insert(0, '.')

import json
import tempfile
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import Base
from app.models.api_key import ApiKey
from app.models.jev_score import JevScore
from app.models.llm_config import LlmConfig
from app.models.meta_task import MetaTask
from app.models.task_instance import TaskInstance
from app.models.task_queue import TaskQueueItem
from app.models.task_result import TaskResult
from app.models.user import User
from app.utils import timezone
from app.utils.api_key import generate_api_key
from app.utils.crypto import encrypt_api_key
from app.config import get_settings


# ═══════════════════════════════════════════════════════════
#  纯函数：URL 归一 / 评分公式 / 请求构建 / 答案解析
# ═══════════════════════════════════════════════════════════


def test_normalize_jev_api_url_covers_common_inputs():
    from app.services.jev_provider import JEV_DEFAULT_API_URL, normalize_jev_api_url

    assert normalize_jev_api_url("https://api.typesafe.ai") == JEV_DEFAULT_API_URL
    assert normalize_jev_api_url("https://api.typesafe.ai/") == JEV_DEFAULT_API_URL
    assert normalize_jev_api_url("https://api.typesafe.ai/v1") == JEV_DEFAULT_API_URL
    # 完整端点原样返回，不重复拼路径
    assert normalize_jev_api_url(JEV_DEFAULT_API_URL) == JEV_DEFAULT_API_URL
    assert normalize_jev_api_url("") == JEV_DEFAULT_API_URL


def test_calculate_relevance_matches_reference_formula():
    from app.services.jev_provider import calculate_relevance

    # noul × (level / 4)，保留两位
    assert calculate_relevance(1.0, 4) == 1.0
    assert calculate_relevance(1.0, 0) == 0.0
    assert calculate_relevance(0.9, 4) == 0.9
    assert calculate_relevance(0.5, 2) == 0.25
    assert calculate_relevance(0.85, 3) == 0.64
    # 越界值被夹紧，不产生非法分数
    assert calculate_relevance(1.4, 9) == 1.0
    assert calculate_relevance(-1, -5) == 0.0


def test_level_label_clamps_to_known_range():
    from app.services.jev_provider import level_label

    assert level_label(0) == "完全不相关"
    assert level_label(4) == "完全匹配"
    assert level_label(2) == "中度相关"
    assert level_label(99) == "完全匹配"
    assert level_label(-3) == "完全不相关"


def test_build_candidate_text_truncates():
    from app.services.jev_provider import MAX_ITEM_CHARS, build_candidate_text

    assert build_candidate_text(None, None, None) == ""
    text = build_candidate_text("题名", "关键词", "摘要")
    assert "题名：题名" in text and "关键词：关键词" in text
    assert len(build_candidate_text("T" * 5000, None, None)) == MAX_ITEM_CHARS


def test_build_jev_request_shape():
    from app.services.jev_provider import (
        JEV_DEFAULT_MODEL,
        RELEVANCE_LEVELS,
        build_jev_request,
    )

    items = [{"task_result_id": 7, "text": "A"}, {"task_result_id": 8, "text": "B"}]
    body = build_jev_request("阅读推广", items, JEV_DEFAULT_MODEL)

    assert body["model"] == JEV_DEFAULT_MODEL
    assert body["state"]["request"] == "阅读推广"
    assert [r["content"] for r in body["state"]["results"]] == ["A", "B"]
    # 每篇一对 noul + score，外加一个批级 choice 弃权信号
    assert set(body["questions"]) == {"r0", "s0", "r1", "s1", "has_match"}
    assert body["questions"]["r0"]["type"] == "noul"
    assert body["questions"]["s1"]["type"] == "score"
    assert body["questions"]["s0"]["criteria"] == RELEVANCE_LEVELS
    assert body["questions"]["has_match"]["type"] == "choice"


def test_parse_jev_answers_scores_each_item():
    from app.services.jev_provider import parse_jev_answers

    items = [{"task_result_id": 1, "text": "A"}, {"task_result_id": 2, "text": "B"}]
    answers = {
        "r0": {"type": "noul", "noul": 0.9},
        "s0": {"type": "score", "score": 4, "confidence": 0.9},
        "r1": {"type": "noul", "noul": 0.5},
        "s1": {"type": "score", "score": 2, "confidence": 0.4},
        "has_match": {"type": "choice", "choice": "yes"},
    }
    scores, has_match = parse_jev_answers(answers, items)
    assert has_match is True
    assert [s["task_result_id"] for s in scores] == [1, 2]
    assert scores[0]["relevance_score"] == 0.9
    assert scores[0]["relevance_level"] == 4
    assert scores[0]["noul_prob"] == 0.9
    assert scores[0]["level_confidence"] == 0.9
    assert scores[1]["relevance_score"] == 0.25
    assert scores[1]["relevance_level"] == 2


def test_parse_jev_answers_drops_invalid_instead_of_zero_filling():
    """严格校验：缺失/类型错/非有限的条目不产分，绝不兜底成 0。

    0 分意味着「打了低分」，会让下游把一条无法判定的文献当成低质量文献过滤掉。
    """
    from app.services.jev_provider import parse_jev_answers

    items = [{"task_result_id": i, "text": "x"} for i in range(5)]
    answers = {
        # 正常
        "r0": {"type": "noul", "noul": 1.0}, "s0": {"type": "score", "score": 4},
        # score 缺失
        "r1": {"type": "noul", "noul": 1.0},
        # noul 缺失
        "s2": {"type": "score", "score": 4},
        # type 不符
        "r3": {"type": "score", "noul": 1.0}, "s3": {"type": "noul", "score": 4},
        # 非有限值
        "r4": {"type": "noul", "noul": float("nan")}, "s4": {"type": "score", "score": 2},
    }
    scores, has_match = parse_jev_answers(answers, items)
    assert [s["task_result_id"] for s in scores] == [0]
    assert has_match is None  # 无 has_match 答案时为 None，不臆造


def test_parse_jev_answers_handles_garbage_input():
    from app.services.jev_provider import parse_jev_answers

    items = [{"task_result_id": 1, "text": "x"}]
    assert parse_jev_answers(None, items) == ([], None)
    assert parse_jev_answers({"r0": "not-a-dict"}, items) == ([], None)


# ═══════════════════════════════════════════════════════════
#  作业链路
# ═══════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def env(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="jev_test_")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp}/t.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # progress 模块用独立会话写进度，必须指向测试库，否则会写到真实 data/ 库上
    import app.worker.progress as progress_mod

    monkeypatch.setattr(progress_mod, "async_session_factory", factory)

    raw, prefix, key_hash = generate_api_key()
    async with factory() as db:
        admin = User(username="admin", password_hash="x", role="admin", is_active=True)
        db.add(admin)
        db.add(ApiKey(name="agent-1", key_prefix=prefix, key_hash=key_hash))
        await db.commit()
        await db.refresh(admin)

    yield {"factory": factory, "tmp": tmp, "admin_id": admin.id}
    await engine.dispose()


async def _setup_instance(db, *, relevance_status="pending", relevance_error=None, records=None):
    """落一个待评分的 API 作业实例，返回 (instance, records)。"""
    user = User(username="api_service", password_hash="x", role="user", is_active=False)
    db.add(user)
    await db.flush()
    task = MetaTask(
        name="开放接口检索（内部）", creator_id=user.id,
        search_params=json.dumps({"search_mode": "basic", "queries": ["阅读推广"], "max_export": 50}),
        is_active=False, source="api",
    )
    db.add(task)
    await db.flush()

    records = records if records is not None else [
        {"title": "阅读推广与人工智能", "keywords": "阅读推广;人工智能", "abstract": "摘要内容", "is_duplicate": False}
    ]
    instance = TaskInstance(
        meta_task_id=task.id, creator_id=user.id, instance_no="T20261001001",
        status="search_completed", source="api", relevance_status=relevance_status,
        relevance_error=relevance_error,
        search_result_count=len(records),
        valid_data_count=sum(1 for r in records if not r["is_duplicate"]),
        duplicate_count=sum(1 for r in records if r["is_duplicate"]),
        execution_params=json.dumps(
            {"search_params": {"search_mode": "basic", "queries": ["阅读推广"]},
             "relevance": {"enabled": True, "topic": None}},
            ensure_ascii=False,
        ),
    )
    db.add(instance)
    await db.flush()
    rows = []
    for r in records:
        row = TaskResult(task_instance_id=instance.id, **r)
        db.add(row)
        rows.append(row)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    await db.refresh(instance)
    return instance, rows


def _enqueue_jev(db, instance):
    from app.task_queue.crud import TaskQueueService

    return TaskQueueService(db).enqueue(
        queue_type="jev", task_type="jev_scoring",
        params_json=json.dumps({"instance_id": instance.id, "instance_no": instance.instance_no}),
        task_key=f"jev_{instance.instance_no}", timeout_sec=1800,
    )


async def _add_jev_config(db, *, is_active=True, api_key="sk-test"):
    cfg = LlmConfig(
        name="jev", model_name="jev-latest", api_endpoint="https://api.typesafe.ai",
        api_key_encrypted=encrypt_api_key(api_key, get_settings().aes_encryption_key),
        config_type="jev", is_active=is_active, created_by=1,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@pytest.mark.asyncio
async def test_resolve_jev_config_picks_jev_row_only(env, monkeypatch):
    from app.services.jev_provider import JevNotConfiguredError, resolve_jev_config

    async with env["factory"]() as db:
        db.add(LlmConfig(
            name="chat", model_name="gpt-4o", api_endpoint="https://api.openai.com",
            api_key_encrypted=encrypt_api_key("sk-llm", get_settings().aes_encryption_key),
            config_type="llm", is_active=True, created_by=env["admin_id"],
        ))
        await db.commit()

        # 只有 llm 行时不应被误当作 JEV 配置
        with pytest.raises(JevNotConfiguredError):
            await resolve_jev_config(db)

        await _add_jev_config(db, is_active=False)
        with pytest.raises(JevNotConfiguredError):
            await resolve_jev_config(db)

        await _add_jev_config(db, is_active=True)
        config = await resolve_jev_config(db)
        assert config.model == "jev-latest"
        assert config.api_url == "https://api.typesafe.ai/v1/systemone"
        assert config.api_key == "sk-test"


@pytest.mark.asyncio
async def test_jev_worker_scores_and_completes(env, monkeypatch):
    import app.worker.jev_worker as jev_worker

    async with env["factory"]() as db:
        await _add_jev_config(db)
        instance, rows = await _setup_instance(db, records=[
            {"title": "阅读推广与人工智能", "keywords": "阅读推广", "abstract": "摘要A", "is_duplicate": False},
            {"title": "体育教学研究", "keywords": "体育", "abstract": "摘要B", "is_duplicate": False},
        ])
        item = await _enqueue_jev(db, instance)

        async def fake_score_batch(topic, batch, config):
            return {
                "scores": [
                    {"task_result_id": batch[0]["task_result_id"], "relevance_score": 0.9,
                     "relevance_level": 4, "noul_prob": 0.9, "level_confidence": 0.88},
                ],
                "has_match": True, "error": None, "latency_ms": 123.0,
                "raw_response": {"answers": {}},
            }

        monkeypatch.setattr(jev_worker, "_score_batch", fake_score_batch)
        await jev_worker.run_jev_scoring(db, item.id, item.params_json)

        await db.refresh(instance)
        assert instance.status == "completed"
        assert instance.relevance_status == "completed"
        assert instance.completed_at is not None

        scores = (await db.execute(
            select(JevScore).where(JevScore.task_instance_id == instance.id)
        )).scalars().all()
        assert len(scores) == 2
        by_id = {s.task_result_id: s for s in scores}
        first = by_id[rows[0].id]
        second = by_id[rows[1].id]
        assert first.status == "completed" and first.relevance_score == 0.9
        assert first.latency_ms == 123
        # 同批内未产分的条目：status=failed 且分数为 NULL（不是 0）
        assert second.status == "failed"
        assert second.relevance_score is None


@pytest.mark.asyncio
async def test_jev_worker_skips_duplicates(env, monkeypatch):
    import app.worker.jev_worker as jev_worker

    async with env["factory"]() as db:
        await _add_jev_config(db)
        instance, records = await _setup_instance(db, records=[
            {"title": "有效文献", "keywords": "k", "abstract": "a", "is_duplicate": False},
            {"title": "重复文献", "keywords": "k", "abstract": "a", "is_duplicate": True},
        ])
        item = await _enqueue_jev(db, instance)
        seen: list[list] = []

        async def fake_score_batch(topic, batch, config):
            seen.append([i["task_result_id"] for i in batch])
            return {"scores": [], "has_match": None, "error": "boom",
                    "latency_ms": 1.0, "raw_response": None}

        monkeypatch.setattr(jev_worker, "_score_batch", fake_score_batch)
        await jev_worker.run_jev_scoring(db, item.id, item.params_json)

        # 重复条目不参与评分，不为它花 JEV 的钱
        assert len(seen) == 1 and len(seen[0]) == 1
        rows = (await db.execute(
            select(JevScore).where(JevScore.task_instance_id == instance.id)
        )).scalars().all()
        assert len(rows) == 1

        await db.refresh(instance)
        assert instance.status == "completed"
        assert instance.relevance_status == "failed"


@pytest.mark.asyncio
async def test_job_still_succeeds_when_jev_not_configured(env, monkeypatch):
    """核心契约：未配置 JEV 不得让作业失败——CNKI 结果必须照常返回。"""
    import app.worker.jev_worker as jev_worker

    async with env["factory"]() as db:
        instance, _ = await _setup_instance(db)
        item = await _enqueue_jev(db, instance)

        async def boom(*a, **kw):
            raise AssertionError("未配置时不应发起任何 JEV 调用")

        monkeypatch.setattr(jev_worker, "call_jev_api", boom)
        await jev_worker.run_jev_scoring(db, item.id, item.params_json)

        await db.refresh(instance)
        assert instance.status == "completed"
        assert instance.relevance_status == "unavailable"
        assert instance.relevance_error


@pytest.mark.asyncio
async def test_job_still_succeeds_when_all_batches_fail(env, monkeypatch):
    import app.worker.jev_worker as jev_worker

    async with env["factory"]() as db:
        await _add_jev_config(db)
        instance, _ = await _setup_instance(db)
        item = await _enqueue_jev(db, instance)

        async def always_fail(topic, batch, config):
            return {"scores": [], "has_match": None, "error": "JEV 503",
                    "latency_ms": 5.0, "raw_response": None}

        monkeypatch.setattr(jev_worker, "_score_batch", always_fail)
        await jev_worker.run_jev_scoring(db, item.id, item.params_json)

        await db.refresh(instance)
        # 全部批次失败 → 作业仍成功，只是没有分
        assert instance.status == "completed"
        assert instance.relevance_status == "failed"
        assert "503" in (instance.relevance_error or "")


@pytest.mark.asyncio
async def test_partial_failure_is_reported_as_partial(env, monkeypatch):
    import app.worker.jev_worker as jev_worker

    async with env["factory"]() as db:
        await _add_jev_config(db)
        # 25 条 → 2 批（批大小 20），让第二批可以独立失败
        records = [
            {"title": f"文献{i}", "keywords": "k", "abstract": "a", "is_duplicate": False}
            for i in range(25)
        ]
        instance, _ = await _setup_instance(db, records=records)
        item = await _enqueue_jev(db, instance)

        async def flaky(topic, batch, config):
            if len(batch) < 20:
                return {"scores": [], "has_match": None, "error": "timeout",
                        "latency_ms": 1.0, "raw_response": None}
            return {
                "scores": [
                    {"task_result_id": i["task_result_id"], "relevance_score": 0.8,
                     "relevance_level": 4, "noul_prob": 0.8, "level_confidence": 0.7}
                    for i in batch
                ],
                "has_match": True, "error": None, "latency_ms": 2.0, "raw_response": None,
            }

        monkeypatch.setattr(jev_worker, "_score_batch", flaky)
        await jev_worker.run_jev_scoring(db, item.id, item.params_json)

        await db.refresh(instance)
        assert instance.status == "completed"
        assert instance.relevance_status == "partial"
        assert "timeout" in (instance.relevance_error or "")


@pytest.mark.asyncio
async def test_jev_worker_finalizes_even_on_unexpected_error(env, monkeypatch):
    import app.worker.jev_worker as jev_worker

    async with env["factory"]() as db:
        await _add_jev_config(db)
        instance, _ = await _setup_instance(db)
        item = await _enqueue_jev(db, instance)

        async def explode(*a, **kw):
            raise ValueError("意外异常")

        monkeypatch.setattr(jev_worker, "_score_batch", explode)
        await jev_worker.run_jev_scoring(db, item.id, item.params_json)

        await db.refresh(instance)
        # 异常也必须落终态，绝不能悬在 search_completed 让调用方永远轮询
        assert instance.status == "completed"
        assert instance.relevance_status == "failed"


@pytest.mark.asyncio
async def test_jev_worker_handles_empty_results(env, monkeypatch):
    import app.worker.jev_worker as jev_worker

    async with env["factory"]() as db:
        await _add_jev_config(db)
        instance, _ = await _setup_instance(db, records=[])
        item = await _enqueue_jev(db, instance)

        async def boom(*a, **kw):
            raise AssertionError("无文献时不应调用 JEV")

        monkeypatch.setattr(jev_worker, "call_jev_api", boom)
        await jev_worker.run_jev_scoring(db, item.id, item.params_json)

        await db.refresh(instance)
        assert instance.status == "completed"
        assert instance.relevance_status == "completed"


@pytest.mark.asyncio
async def test_resolve_topic_prefers_explicit_then_derives():
    from app.worker.jev_worker import resolve_topic

    assert resolve_topic({"relevance": {"enabled": True, "topic": "自定义定题"}}) == "自定义定题"
    # 空白字符串视为未传，回退派生
    assert resolve_topic({"relevance": {"topic": "  "}, "search_params": {"queries": ["阅读推广"]}}) \
        == "检索关键词：阅读推广"
    assert "未指定检索条件" in resolve_topic({"relevance": {"enabled": True}, "search_params": {}})


@pytest.mark.asyncio
async def test_cnki_worker_enqueues_jev_and_defers_terminal_state(env, monkeypatch):
    """检索完成后必须入队 jev，且不能立刻置 completed。"""
    import app.worker.cnki_worker as cnki_worker

    async with env["factory"]() as db:
        user = User(username="api_service", password_hash="x", role="user", is_active=False)
        db.add(user)
        await db.flush()
        task = MetaTask(
            name="开放接口检索（内部）", creator_id=user.id,
            search_params=json.dumps({"queries": ["x"]}), is_active=False, source="api",
        )
        db.add(task)
        await db.flush()
        instance = TaskInstance(
            meta_task_id=task.id, creator_id=user.id, instance_no="T20261001009",
            # 与真实链路一致：process_search_results 已把实例置为 search_completed
            status="search_completed", source="api", relevance_status="pending",
            valid_data_count=5,
            execution_params=json.dumps(
                {"search_params": {"queries": ["x"]}, "relevance": {"enabled": True, "topic": None}},
                ensure_ascii=False,
            ),
        )
        db.add(instance)
        await db.commit()
        await db.refresh(instance)

        from app.task_queue.crud import TaskQueueService
        svc = TaskQueueService(db)
        exec_params = json.loads(instance.execution_params)
        await cnki_worker._dispatch_api_relevance(db, svc, instance, exec_params)
        await db.refresh(instance)

        # 状态停在 search_completed（对外映射 running），等待 jev 收尾。
        # 若这里误置 completed，调用方会在评分仍在跑时就看到 succeeded，
        # 拿到一批 relevance_score 全为 null 的记录。
        assert instance.status == "search_completed"
        assert instance.relevance_status == "pending"
        row = (await db.execute(
            select(TaskQueueItem).where(TaskQueueItem.task_key == "jev_T20261001009")
        )).scalar_one()
        assert row.queue_type == "jev" and row.status == "pending"

        # 对外状态此时仍是 running 而非 succeeded
        from app.routers.openapi_v1 import _build_status
        assert (await _build_status(db, instance))["state"] == "running"


@pytest.mark.asyncio
async def test_cnki_worker_completes_immediately_when_relevance_disabled(env):
    import app.worker.cnki_worker as cnki_worker

    async with env["factory"]() as db:
        user = User(username="api_service", password_hash="x", role="user", is_active=False)
        db.add(user)
        await db.flush()
        task = MetaTask(
            name="t", creator_id=user.id, search_params=json.dumps({"queries": ["x"]}),
            is_active=False, source="api",
        )
        db.add(task)
        await db.flush()
        instance = TaskInstance(
            meta_task_id=task.id, creator_id=user.id, instance_no="T20261001010",
            status="running", source="api", relevance_status=None, valid_data_count=5,
            execution_params=json.dumps({"search_params": {}, "relevance": {"enabled": False}}),
        )
        db.add(instance)
        await db.commit()
        await db.refresh(instance)

        from app.task_queue.crud import TaskQueueService
        await cnki_worker._dispatch_api_relevance(
            db, TaskQueueService(db), instance, json.loads(instance.execution_params)
        )
        await db.refresh(instance)

        assert instance.status == "completed"
        assert instance.relevance_status is None
        rows = (await db.execute(select(TaskQueueItem))).scalars().all()
        assert rows == []


# ═══════════════════════════════════════════════════════════
#  recovery：JEV 失败不得把作业打成 failed
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_reclaim_stale_jev_row_also_finalizes_instance(env):
    """进程崩溃 → 队列行被超时回收时，实例同样必须落终态。

    reclaim_stale_running 只改队列行，不会调用 reconcile_failed_task。若不补这层，
    jev worker 崩溃/重启后实例永久停在 search_completed（对外 running），调用方
    永远轮询不到终态——与 20260930 的 cnki 事故同一类缺陷。
    """
    from app.task_queue.crud import TaskQueueService

    async with env["factory"]() as db:
        instance, _ = await _setup_instance(db)
        item = await _enqueue_jev(db, instance)
        # 模拟 worker 崩溃：行停在 running 且已超过 timeout_sec
        await db.execute(
            update(TaskQueueItem)
            .where(TaskQueueItem.id == item.id)
            .values(status="running", started_at=timezone.now() - timedelta(seconds=99999))
        )
        await db.commit()

        reclaimed = await TaskQueueService(db).reclaim_stale_running("jev")
        assert reclaimed == 1

        await db.refresh(instance)
        assert instance.status == "completed"
        assert instance.relevance_status == "failed"

        from app.routers.openapi_v1 import _build_status
        assert (await _build_status(db, instance))["state"] == "succeeded"


@pytest.mark.asyncio
async def test_recovery_keeps_job_succeeded_when_jev_task_dies(env):
    """反向验证：把 _reconcile_jev 换回统一 failed 口径，本测试必须失败。"""
    from app.worker.recovery import reconcile_failed_task

    async with env["factory"]() as db:
        instance, _ = await _setup_instance(db)
        item = await _enqueue_jev(db, instance)
        await db.execute(
            update(TaskQueueItem).where(TaskQueueItem.id == item.id).values(
                status="failed", retry_count=99
            )
        )
        await db.commit()

        await reconcile_failed_task(db, item.id, "worker 崩溃")

        await db.refresh(instance)
        # 文献已入库：作业必须是成功的，只是相关性失败
        assert instance.status == "completed"
        assert instance.relevance_status == "failed"
        assert "相关性评分" in (instance.relevance_error or "")

        # 调用方视角：终态是 succeeded，能取回文献，只是没有分
        from app.routers.openapi_v1 import _build_status
        status = await _build_status(db, instance)
        assert status["state"] == "succeeded"
        assert status["result_ready"] is True
        assert status["relevance"]["state"] == "failed"
        assert status["counts"]["valid"] == 1


# ═══════════════════════════════════════════════════════════
#  开放接口：字段裁剪 / 排序 / 阈值过滤
# ═══════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_results_expose_relevance_and_honour_filters(env):
    from app.routers.openapi_v1 import get_metadata_job_results

    class _FakeRequest:
        base_url = "http://testserver/"

    async with env["factory"]() as db:
        instance, rows = await _setup_instance(db, relevance_status="completed", records=[
            {"title": "高相关", "keywords": "k", "abstract": "a", "is_duplicate": False},
            {"title": "低相关", "keywords": "k", "abstract": "a", "is_duplicate": False},
            {"title": "未评分", "keywords": "k", "abstract": "a", "is_duplicate": False},
        ])
        await db.execute(
            update(TaskInstance).where(TaskInstance.id == instance.id).values(status="completed")
        )
        high, low = rows[0].id, rows[1].id
        for rid, score in ((high, 0.9), (low, 0.2)):
            db.add(JevScore(task_result_id=rid, task_instance_id=instance.id,
                            status="completed", relevance_score=score,
                            relevance_level=4 if score > 0.5 else 1))
        await db.commit()

        async def fetch(**kwargs):
            params = dict(format="json", limit=50, offset=0, inline=False, client=None, db=db)
            params.update(kwargs)
            return await get_metadata_job_results(instance.id, _FakeRequest(), **params)

        # 未评分条目必须是 null，绝不是 0
        full = await fetch()
        assert full["total"] == 3
        by_title = {r["title"]: r for r in full["records"]}
        assert by_title["高相关"]["relevance_score"] == 0.9
        assert by_title["低相关"]["relevance_score"] == 0.2
        assert by_title["未评分"]["relevance_score"] is None
        assert by_title["未评分"]["relevance_level"] is None

        # core 视图带上相关性字段
        core = await fetch(fields="core")
        assert set(core["records"][0]) == {
            "id", "title", "authors", "source_journal",
            "publish_year", "original_url", "relevance_score", "relevance_level",
        }

        # 默认排序仍按 id 升序
        assert [r["id"] for r in full["records"]] == sorted(r["id"] for r in full["records"])

        # sort=relevance：高分在前，未打分沉底
        ranked = await fetch(sort="relevance")
        assert [r["relevance_score"] for r in ranked["records"]] == [0.9, 0.2, None]

        # min_relevance 过滤掉低分与未打分
        filtered = await fetch(min_relevance=0.5)
        assert filtered["total"] == 1
        assert filtered["records"][0]["title"] == "高相关"
        assert filtered["next_offset"] is None

        # 显式字段裁剪
        custom = await fetch(fields="title,relevance_score")
        assert set(custom["records"][0]) == {"title", "relevance_score"}


@pytest.mark.asyncio
async def test_results_readable_during_scoring_with_null_scores(env):
    """评分进行中 /results 已可调用，但分数全为 null。

    文档必须如实说明：调用方若在 state=running 时取结果，拿到的是完整元数据
    加 null 分数，而不是 400。result_ready 此时仍为 false，是「全部就绪」的信号。
    """
    from app.routers.openapi_v1 import _build_status, get_metadata_job_results

    class _FakeRequest:
        base_url = "http://testserver/"

    async with env["factory"]() as db:
        instance, rows = await _setup_instance(db, relevance_status="running", records=[
            {"title": "评分中的文献", "keywords": "k", "abstract": "a", "is_duplicate": False},
        ])
        await db.commit()

        res = await get_metadata_job_results(
            instance.id, _FakeRequest(), format="json", limit=50, offset=0,
            inline=False, client=None, db=db,
        )
        assert res["total"] == 1
        assert res["records"][0]["title"] == "评分中的文献"
        assert res["records"][0]["relevance_score"] is None

        status = await _build_status(db, instance)
        assert status["state"] == "running"
        assert status["result_ready"] is False
        assert status["relevance"]["state"] == "running"
        assert status["counts"]["relevance"] == {"total": 0, "scored": 0, "failed": 0}


@pytest.mark.asyncio
async def test_inflight_quota_counts_jev_queue_rows(env):
    """JEV 阶段仍占用在途配额，否则调用方能无限堆积评分任务。"""
    from app.routers.openapi_v1 import _inflight_job_ids

    async with env["factory"]() as db:
        instance, _ = await _setup_instance(db)
        item = await _enqueue_jev(db, instance)
        assert await _inflight_job_ids(db) == [instance.id]

        await db.execute(
            update(TaskQueueItem).where(TaskQueueItem.id == item.id).values(status="completed")
        )
        await db.commit()
        assert await _inflight_job_ids(db) == []