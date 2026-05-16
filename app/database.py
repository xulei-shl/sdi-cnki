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
    connect_args={"check_same_thread": False},
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
