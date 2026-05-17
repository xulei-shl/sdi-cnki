from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    poolclass=NullPool,
    connect_args={"check_same_thread": False, "timeout": 5},
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def _migrate_system_prompts(conn):
    """为 system_prompts 表添加 creator_id 列（兼容已有数据库）。"""
    for row in await conn.execute(text("PRAGMA table_info(system_prompts)")):
        if row[1] == "creator_id":
            return
    await conn.execute(
        text("ALTER TABLE system_prompts ADD COLUMN creator_id INTEGER REFERENCES users(id) DEFAULT 1")
    )


async def init_db():
    async with engine.begin() as conn:
        from app.models import Base
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_system_prompts(conn)
        await _seed_default_configs(conn)


async def _seed_default_configs(conn):
    """插入默认系统配置（幂等，仅空表时执行）。"""
    from sqlalchemy import text as sql_text
    result = await conn.execute(sql_text("SELECT COUNT(*) FROM system_configs"))
    if result.scalar() > 0:
        return
    defaults = [
        ("webhook_enterprise_wechat", "", "企业微信群机器人 Webhook URL"),
        ("cnki_search_timeout", "1800", "CNKI 检索超时（秒）"),
        ("llm_analysis_batch_size", "5", "LLM 批量分析并发数"),
        ("cnki_queue_concurrency", "1", "CNKI 检索队列并发数"),
        ("llm_queue_concurrency", "5", "LLM 分析队列并发数"),
        ("download_queue_concurrency", "1", "PDF 下载队列并发数"),
        ("export_queue_concurrency", "1", "导出打包队列并发数"),
    ]
    for key, value, description in defaults:
        await conn.execute(
            sql_text(
                "INSERT INTO system_configs (key, value, description, updated_by, updated_at) "
                "VALUES (:key, :value, :desc, 1, datetime('now'))"
            ),
            {"key": key, "value": value, "desc": description},
        )
