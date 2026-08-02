from __future__ import annotations

from sqlalchemy import event, text
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


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

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


async def _cleanup_orphan_dedup_scopes():
    """清理 meta_task_dedup_scopes 中指向已删除任务模板的孤儿记录。"""
    async with engine.begin() as conn:
        from sqlalchemy import text as sql_text
        await conn.execute(
            sql_text(
                "DELETE FROM meta_task_dedup_scopes "
                "WHERE dedup_meta_task_id NOT IN (SELECT id FROM meta_tasks)"
            )
        )


async def _seed_instance_no_counters(conn):
    """从现存实例回填每日编号计数器，保证编号永不复用。

    取每天现存实例的最大 seq 作为计数器初值；当天首个新建实例从 max+1 开始，
    不会与现存实例冲突，也不受后续删除影响。
    """
    await conn.execute(
        text(
            "INSERT OR IGNORE INTO instance_no_counters (date, last_seq) "
            "SELECT substr(instance_no, 2, 8) AS d, "
            "MAX(CAST(substr(instance_no, 10) AS INTEGER)) AS s "
            "FROM task_instances GROUP BY d"
        )
    )


async def init_db():
    async with engine.begin() as conn:
        from app.models import Base
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_system_prompts(conn)
        await _seed_default_admin(conn)
        await _seed_default_configs(conn)
        await _seed_instance_no_counters(conn)
    await _cleanup_orphan_dedup_scopes()


async def _seed_default_admin(conn):
    """插入默认管理员（幂等，仅空表时执行）。"""
    from sqlalchemy import text as sql_text
    result = await conn.execute(sql_text("SELECT COUNT(*) FROM users"))
    if result.scalar() > 0:
        return
    from app.dependencies import hash_password
    await conn.execute(
        sql_text(
            "INSERT INTO users (username, password_hash, email, role, is_active, created_at, updated_at) "
            "VALUES ('admin', :pw, 'admin@example.com', 'admin', 1, datetime('now', 'localtime'), datetime('now', 'localtime'))"
        ),
        {"pw": hash_password("admin123")},
    )


async def _seed_default_configs(conn):
    """插入默认系统配置（幂等，INSERT OR IGNORE）。"""
    from sqlalchemy import text as sql_text
    defaults = [
        ("cnki_search_timeout", "1800", "CNKI 检索超时（秒）"),
        ("llm_analysis_batch_size", "5", "LLM 批量分析并发数"),
        ("cnki_queue_concurrency", "1", "CNKI 检索队列并发数"),
        ("llm_queue_concurrency", "5", "LLM 分析队列并发数"),
        ("download_queue_concurrency", "1", "PDF 下载队列并发数"),
        ("export_queue_concurrency", "1", "导出打包队列并发数"),
        ("email_api_url", "http://localhost:9000", "邮件服务地址"),
        ("email_api_key", "", "邮件服务 API Key，未配置则跳过所有邮件发送"),
    ]
    for key, value, description in defaults:
        await conn.execute(
            sql_text(
                "INSERT OR IGNORE INTO system_configs (key, value, description, updated_by, updated_at) "
                "VALUES (:key, :value, :desc, 1, datetime('now'))"
            ),
            {"key": key, "value": value, "desc": description},
        )
